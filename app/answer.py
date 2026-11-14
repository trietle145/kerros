"""The answer API (owner: A, backend): question -> hybrid search -> the model writes a short answer
whose every sentence cites the passages it uses. The frontend (ask.py, templates, static) calls
these JSON routes and never touches the database. Contract: docs/frontend.md, "API contract".

    python -m app.answer         # self-check: 3 questions (fi, en, sv), citations validated (~$0.1)
"""
import re
import threading
from datetime import date
from urllib.parse import quote

from flask import Blueprint, request

from app import xlang
from app.embed import embed
from app.history import stats
from app.llm import RefusedError, complete
from app.search import rank
from app.translate import guess_lang
from scripts.common import env

bp = Blueprint("answer", __name__)
DAILY_LIMIT = int(env().get("ASK_DAILY_LIMIT") or 300)   # model answers per day (~$0.03 each)
_used, _lock = {"day": None, "n": 0}, threading.Lock()


def take_answer():
    """False once today's DAILY_LIMIT answers are used. ponytail: in memory, so per worker and reset
    on restart; gunicorn runs one worker. A shared counter in MariaDB if that changes."""
    with _lock:
        if _used["day"] != date.today():
            _used.update(day=date.today(), n=0)
        if _used["n"] >= DAILY_LIMIT:
            return False
        _used["n"] += 1
        return True

SYSTEM = """You answer questions using only the numbered Wikipedia passages you are given.
- Answer in the language of the question (Finnish, Swedish or English), even though the passages are Finnish.
- Write 2 to 5 short sentences. Put each sentence on its own line.
- End every sentence with the number(s) of the passage(s) it is based on, like [2] or [1][3].
- Use only facts stated in the passages. If they do not answer the question, say so in one sentence without a number.
- No headings, lists or text before or after the sentences."""
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def parse(text, n_sources):
    """Model text -> [{"text", "cites"}]: one sentence per line, citation numbers taken out of the
    text; numbers outside 1..n_sources are dropped, so every cite points at a passage that was sent."""
    out = []
    for line in filter(None, (l.strip().lstrip("-• ") for l in text.splitlines())):
        cites = [int(n) for group in CITE.findall(line) for n in group.split(",")]
        cites = list(dict.fromkeys(c for c in cites if 1 <= c <= n_sources))
        out.append({"text": re.sub(r"\s+([.,!?])", r"\1", CITE.sub("", line)).strip(), "cites": cites})
    return out


def renumber(answer, sources, diffs=()):
    """Cited sources first, numbered 1, 2, ... in the order the answer first cites them; the uncited
    ones follow. Rewrites the numbers in answer cites, sources and then/now diffs in place."""
    cited = list(dict.fromkeys(c for s in answer for c in s["cites"]))
    order = cited + [s["n"] for s in sources if s["n"] not in cited]
    new = {old: i for i, old in enumerate(order, 1)}
    for s in answer:
        s["cites"] = [new[c] for c in s["cites"]]
    for s in sources:
        s["n"] = new[s["n"]]
    sources.sort(key=lambda s: s["n"])
    for d in diffs:
        d["then"], d["now"] = new[d["then"]], new[d["now"]]


def deep_url(rev_id, heading, text):
    """The exact version, scrolled to the passage: #section anchor plus a text fragment
    (:~:text=first 5 words,last 5 words) that browsers highlight. A browser without support, or a
    small wording mismatch with the rendered page, falls back to the section (or the top)."""
    enc = lambda s: quote(s, safe="").replace("-", "%2D")                    # noqa: E731
    words = text.split()
    frag = enc(" ".join(words[:5])) + ("," + enc(" ".join(words[-5:])) if len(words) > 10 else "")
    anchor = quote(heading.replace(" ", "_"), safe="") if heading else ""
    return f"https://fi.wikipedia.org/?oldid={rev_id}#{anchor}:~:text={frag}"


def answer(question, as_of=None):
    """question -> the /ask JSON. A question about how Wikipedia stood on a date (or any question
    with as_of) goes to the then-vs-now path (kind "then_vs_now"); the rest are kind "plain"."""
    from app import timeqa
    if r := timeqa.route(question, as_of):
        return timeqa.answer(question, r)
    vector = embed([question])[0]          # once: search and the other-Wikipedias block share it
    sources = rank(vector, question, k=8)
    if not sources:
        return {"question": question, "kind": "plain", "sources": [],
                "answer": [{"text": "No passages found for this question.", "cites": []}]}
    numbered = "\n\n".join(f"[{n}] {s['title']}" + (f" / {s['heading']}" if s["heading"] else "") +
                           f"\n{s['text']}" for n, s in enumerate(sources, 1))
    text = complete(SYSTEM, f"Passages:\n\n{numbered}\n\nQuestion: {question}")
    pages = list({s["page_id"] for s in sources})
    counts, other = stats(pages), xlang.langs(pages)
    lines = parse(text, len(sources))
    sources = [{"n": n, **s, "url": f"https://fi.wikipedia.org/?oldid={s['rev_id']}",
                "deep_url": deep_url(s["rev_id"], s["heading"], s["text"]),
                **counts[s["page_id"]], "langs": other.get(s["page_id"], [])} for n, s in enumerate(sources, 1)]
    renumber(lines, sources)
    cited = [s for s in sources if any(s["n"] in a["cites"] for a in lines)]
    return {"question": question, "kind": "plain", "answer": lines, "sources": sources,
            "lang": guess_lang(" ".join(a["text"] for a in lines)),
            "xlang": xlang.adds(vector, list({s["page_id"] for s in cited}), [s["passage_id"] for s in cited])}


@bp.route("/ask", methods=["GET", "POST"])
def ask():
    question = (request.values.get("q") or "").strip()
    if not question:
        return {"error": "q is required"}, 400
    if not take_answer():
        return {"error": f"The demo's daily limit of {DAILY_LIMIT} answers is used up. Please try again tomorrow."}, 429
    try:
        return answer(question, request.values.get("as_of"))
    except RefusedError as e:
        return {"error": str(e)}, 422
    except Exception as e:             # model or database down: say so instead of a bare 500 page
        return {"error": f"answering failed: {type(e).__name__}: {e}"}, 500


if __name__ == "__main__":
    import time
    assert parse("Talvisota alkoi 1939 [1].\nSe päättyi 1940 [2][9].\nEn tiedä.", 8) == [
        {"text": "Talvisota alkoi 1939.", "cites": [1]}, {"text": "Se päättyi 1940.", "cites": [2]},
        {"text": "En tiedä.", "cites": []}]
    _used.update(day=date.today(), n=DAILY_LIMIT - 1)
    assert take_answer() and not take_answer(), "the daily cap should stop at DAILY_LIMIT"
    _used.update(n=0)
    a, s, d = [{"cites": [3]}, {"cites": [1, 3]}], [{"n": n} for n in (1, 2, 3, 4)], [{"then": 3, "now": 4}]
    renumber(a, s, d)
    assert a == [{"cites": [1]}, {"cites": [2, 1]}] and [x["n"] for x in s] == [1, 2, 3, 4]
    assert d == [{"then": 1, "now": 4}]
    for q in ("Milloin talvisota alkoi ja miten se päättyi?", "Who was Urho Kekkonen?",
              "Vad hände i Åbo år 1827?"):
        t = time.time()
        a = answer(q)
        n = len(a["sources"])
        assert a["answer"] and all(1 <= c <= n for s in a["answer"] for c in s["cites"])
        cited = sum(bool(s["cites"]) for s in a["answer"])
        print(f"\n{q}  ({time.time() - t:.1f} s, {cited}/{len(a['answer'])} sentences cited)")
        for s in a["answer"]:
            print(f"  {s['text']} {s['cites']}")
        print("  sources:", "; ".join(f"[{s['n']}] {s['title']}" for s in a["sources"][:5]), "…")
    print("\nok")
