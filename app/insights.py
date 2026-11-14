"""Trust and editor features on top of the base (B's design, read-only SQL; model calls count against
the daily answer cap in app/answer.py).
The database does the work: system-versioned paragraph lifetimes (passage_history), stored
vectors (passage_vector, history_vector), the revert table. Nothing here embeds new text, so it
runs on a machine without the model; only /ask/l (dataset L) and the optional LLM summaries need
more.

    GET /api/health?ids=1,2          source health per passage (live since, versions, restored)
    GET /api/rewind?ids=1,2          each passage as it read at the end of every year since 2003
    GET /api/find?title=...          article titles for the pickers
    GET /api/radar                   articles with the most reverts between named editors
    GET /api/radar/<page_id>         that article's most-restored paragraphs (diff links only)
    GET /api/contradictions/<id>     near-identical paragraphs elsewhere that give other numbers
    GET /api/cite?text=...           passages that back a sentence, with their <ref> markup
    GET /api/explain/<id>/<rev_id>   what one edit changed (facts; an LLM summary when a key is set)
    GET /ask/l?q=...                 /ask over dataset L (all 568k fi articles): same JSON as /ask

    python -m app.insights           # self-check on the hero articles (read-only, ~30 s)
"""
import difflib
import re
from contextlib import closing
from datetime import datetime
from functools import lru_cache

from flask import Blueprint, request

from app.db import connect
from scripts.wikitext import clean

bp = Blueprint("insights", __name__)
FIRST_YEAR = 2003
SAME = 0.35            # cosine distance for a past paragraph under the same heading to count as "the same one"
VERY_NEAR = 0.15       # ... or under any heading (headings get renamed)
CONTESTED = 2          # this exact wording removed and put back this often -> "often restored"
SECTION_CONTESTED = 8  # ... or the section's earlier versions restored this often (and half its versions)


def _rows(sql, params=()):
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


def _ids(arg, limit=12):
    try:
        return list(dict.fromkeys(int(x) for x in (arg or "").split(",") if x.strip()))[:limit]
    except ValueError:
        return []


def _alive(end):
    return end.year > 2100                    # current rows end at TIMESTAMP's maximum (2106)


def _year_ends():
    now = datetime.now()
    return [(y, datetime(y, 12, 31, 23, 59, 59) if y < now.year else now) for y in range(FIRST_YEAR, now.year + 1)]


def _passages(ids):
    marks = ",".join("?" * len(ids))
    return _rows(f"SELECT passage_id, page_id, heading, text_hash, text FROM passage WHERE passage_id IN ({marks})", ids)


@lru_cache(maxsize=256)
def _page_lifetimes(page_id):
    """Every paragraph lifetime of one article: (text_hash, heading, start, end, rev_id)."""
    return _rows("SELECT h.text_hash, t.heading, h.row_start, h.row_end, h.rev_id FROM passage_history "
                 "FOR SYSTEM_TIME ALL h JOIN passage_text t USING (text_hash) WHERE h.page_id = ?", (page_id,))


# ---- source health ---------------------------------------------------------------------------------
def health(ids):
    """{passage_id: {live_since, first_seen, rewrites, comebacks, contested}}. A section's
    "comebacks" are lifetimes of a text that had been replaced before: someone restored it, the
    usual trace of a revert. Headings that were renamed count as a new section (a known limit)."""
    out = {}
    for pid, page_id, heading, h, _ in _passages(ids):
        rows = _page_lifetimes(page_id)
        own = [r for r in rows if r[0] == h]
        section = [r for r in rows if r[1] == heading]
        lives = {}
        for r in section:
            lives[r[0]] = lives.get(r[0], 0) + 1
        current = [r for r in own if _alive(r[3])]
        spans = current or own
        out[pid] = {"live_since": max(r[2] for r in spans).date().isoformat() if spans else None,
                    "first_seen": min(r[2] for r in section).date().isoformat() if section else None,
                    "rewrites": len(lives), "comebacks": sum(n - 1 for n in lives.values()), "restored": max(0, len(own) - 1),
                    "contested": len(own) - 1 >= CONTESTED or (sum(n - 1 for n in lives.values()) >= SECTION_CONTESTED
                                                               and sum(n - 1 for n in lives.values()) * 2 >= len(lives))}
    return out


@bp.get("/api/health")
def api_health():
    ids = _ids(request.args.get("ids"))
    return {"health": {str(k): v for k, v in health(ids).items()}} if ids else ({"error": "ids is required"}, 400)


# ---- rewind ----------------------------------------------------------------------------------------
@lru_cache(maxsize=512)
def rewind_one(passage_id):
    """One passage through the years: for each year end, the paragraph of its article that was
    live then and is nearest in meaning (stored vectors, no model), or none within SAME."""
    from app.timeqa import diff
    found = _passages([passage_id])
    if not found:
        return None
    _, page_id, heading, h, text = found[0]
    rows = _rows("""SELECT h.text_hash, h.row_start, h.row_end, t.heading,
                           VEC_DISTANCE_COSINE(v.embedding, (SELECT embedding FROM passage_vector WHERE text_hash = ?)) d
                    FROM passage_history FOR SYSTEM_TIME ALL h JOIN history_vector v USING (text_hash)
                    JOIN passage_text t USING (text_hash) WHERE h.page_id = ?""", (h, page_id))
    rows = [(th, s, e, d) for th, s, e, hd, d in rows if d <= VERY_NEAR or (d <= SAME and hd == heading)]
    revs = _rows("SELECT rev_id, row_start, row_end FROM article FOR SYSTEM_TIME ALL WHERE page_id = ?", (page_id,))
    years, picked = [], {}
    for y, at in _year_ends():
        rev = next((r for r, s, e in revs if s <= at < e), None)
        live = [(d, th) for th, s, e, d in rows if s <= at < e]
        best = min(live) if live else None
        if rev is None:
            years.append({"year": y, "state": "no_article"})
        elif not best:
            years.append({"year": y, "state": "absent", "rev_id": rev})
        else:
            th = bytes(best[1])
            picked[th] = None
            years.append({"year": y, "state": "same" if th == bytes(h) else "changed", "rev_id": rev,
                          "hash": th.hex()[:12], "distance": round(float(best[0]), 3)})
    if picked:
        marks = ",".join("?" * len(picked))
        texts = {bytes(k).hex()[:12]: (hd, t) for k, hd, t in
                 _rows(f"SELECT text_hash, heading, text FROM passage_text WHERE text_hash IN ({marks})", list(picked))}
    versions = {}
    for e in years:
        if e.get("state") == "changed" and e["hash"] not in versions:
            hd, t = texts[e["hash"]]
            versions[e["hash"]] = {"heading": hd, "text": t, **diff(t, text)}
    return {"passage_id": passage_id, "page_id": page_id, "years": years, "versions": versions}


@bp.get("/api/rewind")
def api_rewind():
    ids = _ids(request.args.get("ids"), 8)
    if not ids:
        return {"error": "ids is required"}, 400
    return {"passages": {str(i): r for i in ids if (r := rewind_one(i))}}


# ---- edit-war radar --------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def radar():
    """Articles by reverts between named editors (both sides signed in: disagreement, not cleanup),
    with reverts per year. Counts only, never names (CLAUDE.md boundaries)."""
    top = _rows("""SELECT r.page_id, a.title, COUNT(*) AS total,
                          SUM(NOT r.anonymous AND NOT r.undone_anonymous) AS named, MAX(r.reverted_at)
                   FROM revert_event r JOIN article a ON a.page_id = r.page_id
                   GROUP BY r.page_id, a.title ORDER BY named DESC, total DESC LIMIT 30""")
    ids = [t[0] for t in top]
    marks = ",".join("?" * len(ids))
    per_year = {}
    for p, y, n in _rows(f"SELECT page_id, YEAR(reverted_at), COUNT(*) FROM revert_event WHERE page_id IN ({marks}) "
                         "AND NOT anonymous AND NOT undone_anonymous GROUP BY page_id, YEAR(reverted_at)", ids):
        per_year.setdefault(p, {})[y] = n
    years = [y for y, _ in _year_ends()]
    return {"years": years, "articles": [
        {"page_id": p, "title": t, "reverts": int(total), "named": int(named), "last": last.date().isoformat(),
         "per_year": [per_year.get(p, {}).get(y, 0) for y in years]} for p, t, total, named, last in top]}


@bp.get("/api/radar")
def api_radar():
    return radar()


@lru_cache(maxsize=128)
def contested(page_id):
    """The article's paragraphs whose text was restored most often, each with the edits that
    restored it (Wikipedia diff links: the reader judges, we only count)."""
    lives = {}
    for th, hd, s, e, rev in _page_lifetimes(page_id):
        lives.setdefault(bytes(th), []).append((s, rev, hd, _alive(e)))
    top = sorted(((len(v), k) for k, v in lives.items() if len(v) > 1), reverse=True)[:12]
    if not top:
        return []
    marks = ",".join("?" * len(top))
    texts = {bytes(k): t for k, t in _rows(f"SELECT text_hash, text FROM passage_text WHERE text_hash IN ({marks})",
                                            [k for _, k in top])}
    out = []
    for n, k in top:
        spans = sorted(lives[k])
        out.append({"heading": spans[0][2], "times": n - 1, "live": spans[-1][3],
                    "text": texts[k][:400] + ("…" if len(texts[k]) > 400 else ""),
                    "first": spans[0][0].date().isoformat(),
                    "restores": [{"at": s.date().isoformat(), "diff": f"https://fi.wikipedia.org/?diff={rev}"}
                                 for s, rev, _, _ in spans[1:]][-8:]})
    return out


@bp.get("/api/radar/<int:page_id>")
def api_radar_page(page_id):
    title = _rows("SELECT title FROM article WHERE page_id = ?", (page_id,))
    if not title:
        return {"error": f"no article {page_id}"}, 404
    return {"page_id": page_id, "title": title[0][0], "paragraphs": contested(page_id)}


# ---- article lookup by title (for the tool pages' pickers) ------------------------------------------
@bp.get("/api/find")
def api_find():
    """Titles that start with (then contain) the text: current rows only, ~19.7k, no index needed."""
    t = (request.args.get("title") or "").strip()[:100]
    if len(t) < 2:
        return {"articles": []}
    rows = _rows("SELECT page_id, title FROM article WHERE title LIKE ? AND text NOT LIKE '#%' "
                 "ORDER BY title NOT LIKE ?, CHAR_LENGTH(title) LIMIT 8", (f"%{t}%", f"{t}%"))
    return {"articles": [{"page_id": p, "title": x} for p, x in rows]}


# ---- contradictions --------------------------------------------------------------------------------
NUM = re.compile(r"(?<![\d.,])(\d{1,3}(?:[  ]\d{3})+|\d+(?:,\d+)?)\s+([a-zåäöA-ZÅÄÖ-]{3,})")
SKIP_UNITS = {"vuonn", "vuode", "vuosi", "luvun", "luvul", "luvull", "sivua", "ja", "tai"}


def facts(text):
    """Numbers with the word after them: {(unit stem, ...): number}. '80 000 punavankia' ->
    ('punav', 80000). Years and page numbers are left out."""
    out = {}
    for n, unit in NUM.findall(text):
        v = float(n.replace(" ", "").replace(" ", "").replace(",", "."))
        stem = unit.lower()[:5]
        if stem in SKIP_UNITS or (1000 <= v <= 2100 and " " not in n and " " not in n) or v < 10:
            continue
        out.setdefault(stem, (v, f"{n} {unit}"))
    return out


def disagreements(a, b):
    """Same quantity (same unit word), different number of the same size."""
    fa, fb = facts(a), facts(b)
    return [{"here": fa[u][1], "there": fb[u][1]} for u in fa.keys() & fb.keys()
            if fa[u][0] != fb[u][0] and 0.5 <= fa[u][0] / fb[u][0] <= 2]


@lru_cache(maxsize=64)
def contradictions(page_id, near=0.22):
    """For each paragraph of the article: its nearest paragraphs in other articles (stored
    vectors, vector index in a subquery), kept when they state the same quantity differently."""
    mine = _rows("SELECT passage_id, rev_id, heading, text, text_hash FROM passage WHERE page_id = ? ORDER BY position", (page_id,))
    out, seen = [], set()
    with closing(connect()) as con:
        cur = con.cursor()
        for pid, rev, heading, text, h in mine:
            if not facts(text):
                continue
            cur.execute("SELECT embedding FROM passage_vector WHERE text_hash = ?", (h,))
            vec = cur.fetchone()
            if not vec:
                continue
            # the vector as a parameter, not a subquery: only then does MariaDB use the vector index
            cur.execute("""SELECT q.passage_id, q.page_id, q.rev_id, q.title, q.heading, q.text, v.d
                           FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) AS d
                                 FROM passage_vector ORDER BY d LIMIT 8) v
                           JOIN passage q USING (text_hash) WHERE q.page_id <> ? AND v.d <= ?""", (vec[0], page_id, near))
            for qid, qpage, qrev, qtitle, qheading, qtext, d in cur.fetchall():
                found = disagreements(text, qtext)
                if found and (min(pid, qid), max(pid, qid)) not in seen:
                    seen.add((min(pid, qid), max(pid, qid)))
                    out.append({"distance": round(float(d), 3), "facts": found,
                                "here": {"passage_id": pid, "heading": heading, "text": text,
                                         "url": f"https://fi.wikipedia.org/?oldid={rev}"},
                                "there": {"passage_id": qid, "page_id": qpage, "title": qtitle, "heading": qheading,
                                          "text": qtext, "url": f"https://fi.wikipedia.org/?oldid={qrev}"}})
    return sorted(out, key=lambda c: c["distance"])


@bp.get("/api/contradictions/<int:page_id>")
def api_contradictions(page_id):
    title = _rows("SELECT title FROM article WHERE page_id = ?", (page_id,))
    if not title:
        return {"error": f"no article {page_id}"}, 404
    return {"page_id": page_id, "title": title[0][0], "pairs": contradictions(page_id)}


# ---- citation finder -------------------------------------------------------------------------------
REF = re.compile(r"<ref(?:\s+name\s*=\s*\"?([^\">/]+)\"?)?\s*(?:/>|>(.*?)</ref>)", re.S)


def ref_label(body):
    """'{{Kirjaviite | Tekijä = X | Nimi = Y | Vuosi = 1999 }}' -> 'X: Y (1999)'; plain text as is."""
    fields = dict((k.strip().lower(), v.strip()) for k, v in re.findall(r"\|\s*([^=|{}]+?)\s*=\s*([^|{}]*)", body))
    pick = lambda *ks: next((fields[k] for k in ks if fields.get(k)), "")   # noqa: E731
    title = pick("nimi", "title", "otsikko", "teos")
    if title:
        who, year = pick("tekijä", "author", "last", "sukunimi"), pick("vuosi", "year", "julkaistu", "date")
        return (f"{who}: " if who else "") + title + (f" ({year})" if year else "")
    text = " ".join(clean(body)[0][1:] if clean(body) else []) or re.sub(r"<[^>]+>|\{\{|\}\}|\[|\]", "", body)
    return re.sub(r"\s+", " ", text).strip()[:160]


# A sentence ends at . ! ? after a letter or a 4-digit year (never after the "30." of "30. marraskuuta"),
# together with the <ref>s that follow it: in wikitext the reference comes after the full stop.
WIKI_END = re.compile(r"(?:(?<=[^\W\d])|(?<=\d{4}))[.!?](?:\s*<ref[^>]*?/>|\s*<ref[^>]*>.*?</ref>)*(?=\s|$)", re.S)


def wiki_sentences(body):
    out, start = [], 0
    for m in WIKI_END.finditer(body):
        out.append(body[start:m.end()])
        start = m.end()
    return [s for s in out + [body[start:]] if s.strip()]


def plain_sentences(text):
    from app.translate import SPLIT
    return [s for line in text.splitlines() for s in SPLIT.split(line) if s.strip()]


def refs_near(wikitext, heading, sentence):
    """The <ref>s attached to the wikitext sentences of that section that best match `sentence`."""
    named = {m[0].strip(): m[1] for m in REF.findall(wikitext) if m[0] and m[1]}
    body = wikitext
    if heading:
        m = re.search(r"^=+\s*" + re.escape(heading) + r"\s*=+\s*$", wikitext, re.M)
        if m:
            nxt = re.search(r"^==[^=]", wikitext[m.end():], re.M)
            body = wikitext[m.end(): m.end() + (nxt.start() if nxt else len(wikitext))]
    elif (m := re.search(r"^==", wikitext, re.M)):
        body = wikitext[:m.start()]
    keys = set(_stems(sentence))
    scored = []
    for part in wiki_sentences(body):
        found = REF.findall(part)
        if found:
            score = len(keys & set(_stems(re.sub(r"<ref.*?(?:/>|</ref>)", "", part, flags=re.S))))
            scored.append((score, found))
    best = max(scored, key=lambda x: x[0], default=(0, []))
    out = []
    if best[0] >= 2:                                    # only the refs of the one sentence that says it
        for name, inner in best[1]:
            inner = inner or named.get((name or "").strip(), "")
            if inner:
                markup = f'<ref name="{name.strip()}">{inner}</ref>' if name else f"<ref>{inner}</ref>"
                if markup not in [r["markup"] for r in out]:
                    out.append({"markup": markup, "label": ref_label(inner)})
    return out


def _stems(text):
    return [w if w.isdigit() else w[:5] for w in re.findall(r"\w{4,}", text.lower())]


def cite(text, k=6):
    """Passages that back a sentence, by the app's hybrid search (meaning + names and years, the
    same as the answers), one per article, each with the references its article gives for the
    sentence that says it. Needs the embedding model (the server; a laptop forwards /api/cite)."""
    from app.search import search
    keys = set(_stems(text))
    out = []
    for h in search(text, k=12, per_article=1):
        pid, page_id, rev, title, heading, ptext = (h["passage_id"], h["page_id"], h["rev_id"], h["title"],
                                                    h["heading"], h["text"])
        wt = _rows("SELECT text FROM article WHERE page_id = ?", (page_id,))
        best = max(plain_sentences(ptext) or [ptext], key=lambda x: len(keys & set(_stems(x))))
        out.append({"passage_id": pid, "page_id": page_id, "title": title, "heading": heading, "sentence": best,
                    "overlap": len(keys & set(_stems(best))), "url": f"https://fi.wikipedia.org/?oldid={rev}",
                    "refs": refs_near(wt[0][0], heading, best) if wt else []})
        if len(out) == k:
            break
    return out


@bp.get("/api/cite")
def api_cite():
    text = (request.args.get("text") or "").strip()
    if len(text) < 8:
        return {"error": "paste a sentence of at least a few words"}, 400
    return {"text": text, "results": cite(text[:600])}


# ---- explain one edit ------------------------------------------------------------------------------
def _plain(wikitext):
    return [(k, t) for k, t in clean(wikitext)]


def explain(page_id, rev_id):
    """What one edit changed, as facts a reader can check: words in and out, sections touched,
    numbers and references added or removed, the biggest changed spans. Optional LLM summary."""
    cur = _rows("SELECT rev_id, parent_id, comment, len, text, row_start FROM article FOR SYSTEM_TIME ALL "
                "WHERE page_id = ? AND rev_id = ?", (page_id, rev_id))
    if not cur:
        return None
    _, parent_id, comment, size, new, at = cur[0]
    old_row = _rows("SELECT len, text FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? AND rev_id = ?",
                    (page_id, parent_id)) if parent_id else []
    old_size, old = old_row[0] if old_row else (0, "")

    def flat(wt):                                       # words with the heading they sit under
        words, heading = [], None
        for kind, t in _plain(wt):
            if kind.startswith("h"):
                heading = t
            words += [(w, heading) for w in t.split()]
        return words
    a, b = flat(old), flat(new)
    sm = difflib.SequenceMatcher(None, [w for w, _ in a], [w for w, _ in b], autojunk=False)
    spans, added, removed, sections = [], 0, 0, []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        removed += i2 - i1
        added += j2 - j1
        sec = (b[j1][1] if j1 < len(b) else a[i1][1] if i1 < len(a) else None) or "Introduction"
        if sec not in sections:
            sections.append(sec)
        ctx = " ".join(w for w, _ in b[max(0, j1 - 6):j1])
        spans.append({"section": sec, "before": " ".join(w for w, _ in a[i1:i2])[:300],
                      "after": " ".join(w for w, _ in b[j1:j2])[:300], "context": ctx, "size": (i2 - i1) + (j2 - j1)})
    nums = lambda ws: {w.strip(".,;:()") for w, _ in ws if re.fullmatch(r"\d[\d,.]*", w.strip(".,;:()"))}   # noqa: E731
    count = lambda pat, t: len(re.findall(pat, t or ""))                                                    # noqa: E731
    facts_ = {"words_added": added, "words_removed": removed, "bytes": (size or 0) - (old_size or 0),
              "sections": sections[:6], "numbers_in": sorted(nums(b) - nums(a))[:8], "numbers_out": sorted(nums(a) - nums(b))[:8],
              "refs": count(r"<ref[ >]", new) - count(r"<ref[ >]", old),
              "links": count(r"\[\[", new) - count(r"\[\[", old),
              "is_revert": bool(_rows("SELECT 1 FROM revert_event WHERE page_id = ? AND rev_id = ?", (page_id, rev_id)))}
    top = sorted(spans, key=lambda s: -s["size"])[:4]
    summary, source = None, "heuristic"
    try:
        from app.answer import take_answer
        from app.llm import complete
        from scripts.common import env
        if env().get("LLM_API_KEY") and take_answer():          # counts against the daily answer cap
            summary = complete("You explain one Wikipedia edit to a reader in plain English, in 1 or 2 short sentences, "
                               "using only the facts and changed text given. Never mention or guess who made it.",
                               f"Facts: {facts_}\n\nChanged text (Finnish), before -> after:\n" +
                               "\n".join(f"[{s['section']}] '{s['before']}' -> '{s['after']}'" for s in top), max_tokens=300).strip()
            source = "llm"
    except Exception:                                    # no key, no network: the facts still stand
        summary = None
    return {"page_id": page_id, "rev_id": rev_id, "parent_id": parent_id, "at": at.isoformat(),
            "diff": f"https://fi.wikipedia.org/?diff={rev_id}", "facts": facts_, "changes": top,
            "summary": summary, "source": source}


@bp.get("/api/explain/<int:page_id>/<int:rev_id>")
def api_explain(page_id, rev_id):
    e = explain(page_id, rev_id)
    return e if e else ({"error": f"no version {rev_id} of article {page_id}"}, 404)


# ---- dataset L -------------------------------------------------------------------------------------
@bp.route("/ask/l", methods=["GET", "POST"])
def ask_l():
    """/ask over dataset L (568k articles' current text, l_passage + l_vector): the same JSON as a
    plain /ask, so the page renders it unchanged. Needs the model and the LLM key (the server)."""
    from app.answer import SYSTEM, deep_url, parse, renumber
    from app.embed import embed
    from app.llm import RefusedError, complete
    from app.search import rank
    from app.answer import DAILY_LIMIT, take_answer
    from app.translate import guess_lang
    question = (request.values.get("q") or "").strip()
    if not question:
        return {"error": "q is required"}, 400
    if not take_answer():
        return {"error": f"The demo's daily limit of {DAILY_LIMIT} answers is used up. Please try again tomorrow."}, 429
    try:
        sources = rank(embed([question])[0], question, 8, 2, tables=("l_passage", "l_vector"))
        if not sources:
            return {"question": question, "kind": "plain", "scope": "l", "sources": [],
                    "answer": [{"text": "No passages found for this question.", "cites": []}]}
        numbered = "\n\n".join(f"[{n}] {s['title']}" + (f" / {s['heading']}" if s["heading"] else "") +
                               f"\n{s['text']}" for n, s in enumerate(sources, 1))
        lines = parse(complete(SYSTEM, f"Passages:\n\n{numbered}\n\nQuestion: {question}"), len(sources))
        # passage_id None: l_passage ids are not passage ids, and /api/health and /api/rewind read
        # passage (M, with history); without an id the page skips both for L answers
        sources = [{"n": n, **s, "passage_id": None, "url": f"https://fi.wikipedia.org/?oldid={s['rev_id']}",
                    "deep_url": deep_url(s["rev_id"], s["heading"], s["text"])} for n, s in enumerate(sources, 1)]
        renumber(lines, sources)
        return {"question": question, "kind": "plain", "scope": "l", "answer": lines, "sources": sources,
                "lang": guess_lang(" ".join(a["text"] for a in lines))}
    except RefusedError as e:
        return {"error": str(e)}, 422
    except Exception as e:
        return {"error": f"answering over dataset L failed: {type(e).__name__}: {e}"}, 500


if __name__ == "__main__":
    import time
    assert facts("voittajien käsiin jäi noin 80 000 punavankia vuonna 1918") == {"punav": (80000.0, "80 000 punavankia")}
    assert disagreements("80 000 punavankia", "76 000 punavankia") == [{"here": "80 000 punavankia", "there": "76 000 punavankia"}]
    assert disagreements("105 päivää", "3 kertaa") == []
    assert ref_label("{{Kirjaviite | Tekijä = Meinander, Henrik | Nimi = Suomen historia | Vuosi = 2006 }}") == \
        "Meinander, Henrik: Suomen historia (2006)"
    wt = 'Sota alkoi 30. marraskuuta 1939.<ref name="a">Kirja 1999</ref> Se päättyi keväällä.<ref>Toinen</ref> Loppu'
    assert wiki_sentences(wt) == ['Sota alkoi 30. marraskuuta 1939.<ref name="a">Kirja 1999</ref>',
                                  ' Se päättyi keväällä.<ref>Toinen</ref>', ' Loppu'], wiki_sentences(wt)
    assert [r["label"] for r in refs_near(wt, None, "Sota alkoi marraskuussa 1939")] == ["Kirja 1999"]
    assert plain_sentences("Sota alkoi 30. marraskuuta 1939. Se päättyi.") == ["Sota alkoi 30. marraskuuta 1939.", "Se päättyi."]
    print("rules ok")
    pid = _rows("SELECT passage_id FROM passage WHERE page_id = 1256 ORDER BY position LIMIT 1 OFFSET 1")[0][0]
    for name, fn in (("health", lambda: health([pid])), ("rewind", lambda: rewind_one(pid)),
                     ("radar", radar), ("contested", lambda: contested(1256)),
                     ("contradictions", lambda: contradictions(1150)),
                     ("cite", lambda: cite("Talvisota alkoi 30. marraskuuta 1939 ilman sodanjulistusta")),
                     ("explain", lambda: explain(1256, _rows("SELECT rev_id FROM revert_event WHERE page_id = 1256 LIMIT 1")[0][0]))):
        t = time.time()
        r = fn()
        print(f"{name}: {time.time() - t:.1f} s")
        assert r, name
    h = health([pid])[pid]
    assert h["rewrites"] >= 1 and h["first_seen"] <= h["live_since"]
    rw = rewind_one(pid)
    assert rw["years"][-1]["state"] == "same", rw["years"][-1]         # today it is itself
    assert all(c["facts"] for c in contradictions(1150))
    assert radar()["articles"][0]["named"] >= radar()["articles"][-1]["named"]
    print("ok")
