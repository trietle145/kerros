"""The answer API (owner: A, backend). The frontend (ask.py, templates, static) calls these JSON
routes and never touches the database. Stub until search + answers land: /ask returns one fixed
example in the contract's shape (docs/frontend.md, "API contract").
"""
from flask import Blueprint, request

from app.history import stats

bp = Blueprint("answer", __name__)

EXAMPLE = {"passage_id": 0, "page_id": 1256, "rev_id": 24273471, "title": "Talvisota",
           "heading": None, "text": "Talvisota oli Neuvostoliiton ja Suomen välinen sota "
                                    "30. marraskuuta 1939 – 13. maaliskuuta 1940.", "score": 1.0}


def answer(question, as_of=None):
    """question -> the /ask JSON. Stub: a fixed example until search() and complete() exist."""
    sources = [EXAMPLE]
    counts = stats([s["page_id"] for s in sources])
    return {"question": question, "kind": "plain",
            "answer": [{"text": "Talvisota käytiin vuosina 1939–1940.", "cites": [1]}],
            "sources": [{"n": n, **s, "url": f"https://fi.wikipedia.org/?oldid={s['rev_id']}",
                         **counts[s["page_id"]]} for n, s in enumerate(sources, 1)]}


@bp.route("/ask", methods=["GET", "POST"])
def ask():
    question = (request.values.get("q") or "").strip()
    if not question:
        return {"error": "q is required"}, 400
    return answer(question, request.values.get("as_of"))
