"""Ask page and /ask (owner: B). Stub until 2.B3: /ask returns one fixed example in the
contract's JSON shape (tasks/plan.md, "Contracts"), so both sides can build against it."""
from flask import Blueprint, render_template, request

from app.history import stats

bp = Blueprint("ask", __name__)

EXAMPLE = {"passage_id": 0, "page_id": 1256, "rev_id": 24273471, "title": "Talvisota",
           "heading": None, "text": "Talvisota oli Neuvostoliiton ja Suomen välinen sota "
                                    "30. marraskuuta 1939 – 13. maaliskuuta 1940.", "score": 1.0}


@bp.get("/")
def index():
    return render_template("base.html")


@bp.route("/ask", methods=["GET", "POST"])
def ask():
    question = request.values.get("q", "")        # as_of is accepted and ignored for now
    sources = [EXAMPLE]
    counts = stats([s["page_id"] for s in sources])
    return {"question": question,
            "answer": [{"text": "Talvisota käytiin vuosina 1939–1940.", "cites": [1]}],
            "sources": [{"n": n, **s, "url": f"https://fi.wikipedia.org/?oldid={s['rev_id']}",
                         **counts[s["page_id"]]} for n, s in enumerate(sources, 1)]}
