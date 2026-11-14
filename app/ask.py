"""Page routes (owner: B, frontend). Pages only: data comes from the JSON API (answer.py,
history.py), see docs/frontend.md."""
from flask import Blueprint, render_template, request

bp = Blueprint("ask", __name__)


@bp.get("/")
def index():
    return render_template("ask.html")


@bp.get("/graph/<int:page_id>")
def graph(page_id):
    return render_template("graph.html", page_id=page_id, q=request.args.get("q", ""))
