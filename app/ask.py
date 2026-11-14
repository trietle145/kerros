"""Page routes (owner: B, frontend). Pages only: data comes from the JSON API (answer.py,
history.py), see docs/frontend.md."""
from flask import Blueprint, render_template

bp = Blueprint("ask", __name__)


@bp.get("/")
def index():
    return render_template("base.html")
