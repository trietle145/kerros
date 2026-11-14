"""Time-aware answers (owner: A, backend): "what did Wikipedia say about X in 2008, and what has
changed since?" Meaning lives in the vector, time lives in the table: the date is taken out of the
question and becomes FOR SYSTEM_TIME AS OF on passage_history (docs/architecture.md,
"Time-aware retrieval").

    python -m app.timeqa         # self-check: routing + diff rules, then 3 demo questions (~$0.1)
"""
import difflib
import re
from contextlib import closing
from datetime import UTC, date, datetime

from app.db import connect
from app.embed import embed

FIRST_YEAR = 2003        # dataset M starts in 2003; earlier years are history, not "as of"
CUES = {"wikipedia", "wikipedian", "wikipediassa", "sanoi", "kertoi", "kirjoitti", "muuttunut",
        "muuttui", "muutettu", "said", "say", "wrote", "stood", "changed", "change", "sade", "stod",
        "skrev", "ändrats", "ändrades"}
DROP = CUES | {"vuonna", "vuodesta", "jälkeen", "sitten", "nyt", "nykyään", "since", "now", "today",
               "then", "sedan", "nu", "år", "in", "ja", "mitä", "what", "how", "has", "vad", "och",
               "on", "and", "it", "about", "om", "siitä", "asiasta", "the", "did", "of", "article",
               "artikkeli", "artikkelia", "artikkelin", "artikkelissa", "page", "sivu", "kuvasi",
               "kuvaili", "describe", "described", "beskrev", "artikeln"}
YEAR = re.compile(r"\b(20[0-2]\d)\b")
ISO = re.compile(r"\b(20[0-2]\d)-(\d\d)-(\d\d)\b")
FI_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20[0-2]\d)\b")
CANDIDATES = 500         # nearest historical texts before the time filter (measured: enough survive)
DISTANCE_NEW = 0.35      # a "now" counterpart further than this means the content was removed

THEN_SQL = """
SELECT t.text_hash, t.page_id, t.title, t.heading, t.text, v.d
FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) AS d
      FROM history_vector ORDER BY d LIMIT {n}) v
JOIN passage_history FOR SYSTEM_TIME AS OF TIMESTAMP ? h USING (text_hash)
JOIN passage_text t USING (text_hash)
ORDER BY v.d"""
ARTICLES = 5             # stage one: today's top articles for the topic
PAGES_SQL = """
SELECT t.text_hash, t.page_id, t.title, t.heading, t.text, VEC_DISTANCE_COSINE(v.embedding, ?) AS d
FROM passage_history FOR SYSTEM_TIME AS OF TIMESTAMP ? h
JOIN history_vector v USING (text_hash) JOIN passage_text t USING (text_hash)
WHERE h.page_id IN ({marks}) ORDER BY d LIMIT 4"""
NOW_SQL = """
SELECT p.passage_id, p.page_id, p.rev_id, p.title, p.heading, p.text,
       VEC_DISTANCE_COSINE(v.embedding, (SELECT embedding FROM history_vector WHERE text_hash = ?)) AS d
FROM passage p JOIN passage_vector v USING (text_hash)
WHERE p.page_id = ? ORDER BY d LIMIT 1"""


def route(question, as_of=None):
    """-> {"topic", "as_of", "compare_to"} for a question about how Wikipedia stood on a date, else None.
    A year counts only from FIRST_YEAR on and with a cue word (history questions are full of years);
    an explicit as_of (from the UI) always counts. ponytail: rules only; an LLM router if they miss."""
    today = datetime.now(UTC).date()
    words = re.findall(r"\w+", question.lower())
    day = None
    if as_of:
        day = date.fromisoformat(as_of[:10])
    elif m := ISO.search(question):
        day = date(int(m[1]), int(m[2]), int(m[3]))
    elif m := FI_DATE.search(question):
        day = date(int(m[3]), int(m[2]), int(m[1]))
    elif (m := YEAR.search(question)) and CUES & set(words):
        day = date(int(m[1]), 7, 1)                     # a bare year: the middle of that year
    if not day or not (FIRST_YEAR <= day.year) or day > today:
        return None
    topic = " ".join(w for w in re.findall(r"[\w–-]+", question)       # history years (1918) stay
                     if w.lower() not in DROP and not YEAR.fullmatch(w))
    return {"topic": topic or question, "as_of": day.isoformat(), "compare_to": today.isoformat()}


def diff(old, new):
    """Word diff -> {"similarity", "ops": [[op, text]]}, op equal/delete/insert; long unchanged runs
    shortened to their first and last 5 words."""
    a, b = old.split(), new.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            run = a[i1:i2]
            ops.append(["equal", " ".join(run) if len(run) <= 12 else
                        " ".join(run[:5]) + " … " + " ".join(run[-5:])])
            continue
        if tag in ("delete", "replace"):
            ops.append(["delete", " ".join(a[i1:i2])])
        if tag in ("insert", "replace"):
            ops.append(["insert", " ".join(b[j1:j2])])
    return {"similarity": round(sm.ratio(), 2), "ops": ops}


def then_passages(cur, topic, as_of, k=6):
    """Passages live on as_of, nearest to the topic; one per (article, section). Two stages first:
    today's hybrid search (names, cross-language) picks the articles, then their passages live on
    the date are ranked by exact distance. The global nearest-history search fills the rest, so
    text from articles that have since lost the topic can still turn up."""
    from app.search import rank
    vector = embed([topic])[0]
    at = as_of + " 23:59:59"
    pages = list(dict.fromkeys(h["page_id"] for h in rank(vector, topic, 30, None)))[:ARTICLES]
    rows = []
    if pages:
        cur.execute(PAGES_SQL.format(marks=",".join("?" * len(pages))), (vector, at, *pages))
        rows = cur.fetchall()
    cur.execute(THEN_SQL.format(n=CANDIDATES), (vector, at))
    out, seen = [], set()
    for text_hash, page_id, title, heading, text, d in rows + cur.fetchall():
        if (page_id, heading) in seen:
            continue
        seen.add((page_id, heading))
        out.append({"text_hash": text_hash, "page_id": page_id, "title": title, "heading": heading,
                    "text": text, "score": round(1 - d, 4)})
        if len(out) == k:
            break
    return out


SYSTEM = """You compare how Wikipedia described a topic on a past date with how it describes it today,
using only the numbered passages. Passages marked THEN are from the past date; NOW are today's text.
- Answer in the language of the question (Finnish, Swedish or English).
- First 1 to 3 sentences on what Wikipedia said on the past date, then 1 to 3 sentences on what has
  changed since (added, removed, revised figures or wording). If nothing important changed, say so.
- One sentence per line, each ending with the passage number(s) it uses, like [2] or [1][4].
- Use only what the passages say. No headings, lists or text before or after the sentences."""


def answer(question, r):
    """A routed time question -> the /ask JSON with kind "then_vs_now" (docs/frontend.md)."""
    from app.answer import deep_url, parse, renumber   # here: answer.py imports this module
    from app.translate import guess_lang
    from app.history import stats
    from app.llm import complete
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute("SET time_zone = '+00:00'")
        then = then_passages(cur, r["topic"], r["as_of"])
        sources, diffs, lines = [], [], []
        for p in then:                  # cite the article version live on the date
            cur.execute("SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP ? WHERE page_id = ?",
                        (r["as_of"] + " 23:59:59", p["page_id"]))
            rev_id = cur.fetchone()[0]
            then_n = len(sources) + 1
            sources.append({**{k: v for k, v in p.items() if k != "text_hash"}, "era": "then",
                            "n": then_n, "rev_id": rev_id, "passage_id": None,
                            "url": f"https://fi.wikipedia.org/?oldid={rev_id}"})
            cur.execute(NOW_SQL, (p["text_hash"], p["page_id"]))
            now = cur.fetchone()
            if now and now[6] <= DISTANCE_NEW:
                passage_id, page_id, now_rev, title, heading, text, d = now
                m = next((s["n"] for s in sources if s.get("passage_id") == passage_id), None)
                if m is None:
                    m = len(sources) + 1
                    sources.append({"n": m, "era": "now", "passage_id": passage_id, "page_id": page_id,
                                    "rev_id": now_rev, "title": title, "heading": heading, "text": text,
                                    "score": round(1 - d, 4),
                                    "url": f"https://fi.wikipedia.org/?oldid={now_rev}"})
                if text != p["text"]:
                    diffs.append({"then": then_n, "now": m, **diff(p["text"], text)})
    for s in sources:
        lines.append(f"[{s['n']}] {s['era'].upper()} ({r['as_of'] if s['era'] == 'then' else 'today'}): "
                     f"{s['title']}" + (f" / {s['heading']}" if s["heading"] else "") + f"\n{s['text']}")
    text = complete(SYSTEM, f"Past date: {r['as_of']}\n\nPassages:\n\n" + "\n\n".join(lines) +
                    f"\n\nQuestion: {question}") if sources else ""
    counts = stats(list({s["page_id"] for s in sources}))
    out = parse(text, len(sources)) if sources else [
        {"text": "No passages from that date were found for this question.", "cites": []}]
    sources = [{**s, "deep_url": deep_url(s["rev_id"], s["heading"], s["text"]),
                **counts[s["page_id"]]} for s in sources]
    renumber(out, sources, diffs)
    return {"question": question, "kind": "then_vs_now", "as_of": r["as_of"],
            "compare_to": r["compare_to"], "answer": out, "sources": sources, "diffs": diffs,
            "lang": guess_lang(" ".join(a["text"] for a in out))}


if __name__ == "__main__":
    import time
    q = "Mitä Wikipedia sanoi sisällissodan punavangeista vuonna 2007, ja mitä on muuttunut?"
    assert route(q)["as_of"] == "2007-07-01" and "punavangeista" in route(q)["topic"]
    assert route("Milloin talvisota alkoi?") is None
    assert route("What happened in Finland in 1918?") is None             # history year, not "as of"
    assert route("Mitä tapahtui vuonna 2008?") is None                    # no cue: an event question
    assert route("What did Wikipedia say about Kekkonen in 2010?")["as_of"] == "2010-07-01"
    assert route("Kekkonen", as_of="2012-03-04")["as_of"] == "2012-03-04"
    assert route("How has the Wikipedia article on the Finnish Civil War changed since 2007?")[
        "topic"] == "Finnish Civil War"
    assert route("Mitä Wikipedia kertoi Mainilasta 1.6.2006?")["as_of"] == "2006-06-01"
    d = diff("noin 80 000 punavankia jäi", "76 000 punavankia jäi")
    assert d["ops"] == [["delete", "noin 80"], ["insert", "76"], ["equal", "000 punavankia jäi"]]
    print("rules ok")
    for q in ("Mitä Wikipedia sanoi sisällissodan punavangeista vuonna 2007, ja mitä on muuttunut?",
              "What did Wikipedia say about the Mainila shots in 2006, and what has changed since?",
              "Miten Wikipedia kuvasi punaista terroria vuonna 2006 ja mitä on muuttunut?"):
        t = time.time()
        a = answer(q, route(q))
        n = len(a["sources"])
        assert all(1 <= c <= n for s in a["answer"] for c in s["cites"])
        print(f"\n{q}\n  as of {a['as_of']}, {time.time() - t:.1f} s, {n} sources "
              f"({sum(s['era'] == 'then' for s in a['sources'])} then), {len(a['diffs'])} diffs")
        for s in a["answer"]:
            print(f"  {s['text']} {s['cites']}")
        for s in a["sources"][:6]:
            print(f"    [{s['n']}] {s['era']:4} {s['title']} / {s['heading'] or '(lead)'}  ?oldid={s['rev_id']}")
    print("\nok")
