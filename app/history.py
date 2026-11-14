"""Time views (owner: A). Stubs until 2.A2; the signatures are the contract in tasks/plan.md."""
from flask import Blueprint, request

bp = Blueprint("history", __name__)


def stats(page_ids):
    """{page_id: {"edits": n, "reverts": m}} for the source cards. Stub: zeros until 2.A2."""
    return {p: {"edits": 0, "reverts": 0} for p in page_ids}


@bp.get("/article/<int:page_id>")
def article(page_id):
    """The article as it stood on ?as_of=YYYY-MM-DD (default: now). Stub until 2.A2/2.A3."""
    return {"page_id": page_id, "as_of": request.args.get("as_of"), "rev_id": None, "text": None}


@bp.get("/article/<int:page_id>/timeline")
def timeline(page_id):
    """Edits and reverts per month. Stub until 2.A2."""
    return {"page_id": page_id, "months": []}
