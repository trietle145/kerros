"""The answer API (owner: A, backend): question -> hybrid search -> the model writes a short answer
whose every sentence cites the passages it uses. The frontend (ask.py, templates, static) calls
these JSON routes and never touches the database. Contract: docs/frontend.md, "API contract".

    python -m app.answer         # self-check: 3 questions (fi, en, sv), citations validated (~$0.1)
"""
import re

from flask import Blueprint, request

from app.history import stats
from app.llm import RefusedError, complete
from app.search import search

bp = Blueprint("answer", __name__)

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


def answer(question, as_of=None):
    """question -> the /ask JSON (kind "plain"). as_of is accepted; dated questions get their own
    path (then vs now) later."""
    sources = search(question, k=8)
    if not sources:
        return {"question": question, "kind": "plain", "sources": [],
                "answer": [{"text": "No passages found for this question.", "cites": []}]}
    numbered = "\n\n".join(f"[{n}] {s['title']}" + (f" / {s['heading']}" if s["heading"] else "") +
                           f"\n{s['text']}" for n, s in enumerate(sources, 1))
    text = complete(SYSTEM, f"Passages:\n\n{numbered}\n\nQuestion: {question}")
    counts = stats(list({s["page_id"] for s in sources}))
    return {"question": question, "kind": "plain", "answer": parse(text, len(sources)),
            "sources": [{"n": n, **s, "url": f"https://fi.wikipedia.org/?oldid={s['rev_id']}",
                         **counts[s["page_id"]]} for n, s in enumerate(sources, 1)]}


@bp.route("/ask", methods=["GET", "POST"])
def ask():
    question = (request.values.get("q") or "").strip()
    if not question:
        return {"error": "q is required"}, 400
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
