"""Time views (owner: A): an article as of a date, its edit timeline, and edit/revert counts for
the source cards. All times are UTC, like Wikipedia's.

    python -m app.history        # self-check against direct SQL on Talvisota (needs the database)
"""
from contextlib import closing
from datetime import UTC, datetime

from flask import Blueprint, request

from app.db import connect
from scripts.wikitext import clean

bp = Blueprint("history", __name__)
FOREVER = datetime(2038, 1, 1)      # current rows end at MariaDB's maximum TIMESTAMP (2038)


def _rows(sql, params=()):
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


def stats(page_ids):
    """{page_id: {"edits": n, "reverts": m}} for the source cards."""
    out = {p: {"edits": 0, "reverts": 0} for p in page_ids}
    if not page_ids:
        return out
    marks = ",".join("?" * len(page_ids))
    for key, sql in (("edits", "article FOR SYSTEM_TIME ALL"), ("reverts", "revert_event")):
        for p, n in _rows(f"SELECT page_id, COUNT(*) FROM {sql} WHERE page_id IN ({marks}) "
                          "GROUP BY page_id", tuple(page_ids)):
            out[p][key] = n
    return out


@bp.get("/article/<int:page_id>")
def article(page_id):
    """The article as it stood on ?as_of=YYYY-MM-DD[THH:MM[:SS]] (default: now), cleaned for reading."""
    as_of = request.args.get("as_of")
    try:
        moment = datetime.fromisoformat(as_of) if as_of else datetime.now(UTC).replace(tzinfo=None)
    except ValueError:
        return {"error": "as_of must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"}, 400
    found = _rows("SELECT title, rev_id, user, comment, row_start, row_end, text FROM article "
                  "FOR SYSTEM_TIME AS OF TIMESTAMP ? WHERE page_id = ?",
                  (moment.strftime("%Y-%m-%d %H:%M:%S"), page_id))
    if not found:
        return {"error": f"article {page_id} did not exist on {moment:%Y-%m-%d}"}, 404
    title, rev_id, user, comment, start, end, text = found[0]
    return {"page_id": page_id, "title": title, "rev_id": rev_id, "as_of": moment.isoformat(),
            "valid_from": start.isoformat(), "valid_to": None if end >= FOREVER else end.isoformat(),
            "user": user, "comment": comment, "url": f"https://fi.wikipedia.org/?oldid={rev_id}",
            "blocks": clean(text)}


@bp.get("/article/<int:page_id>/timeline")
def timeline(page_id):
    """Edits and reverts per month; cleanup = reverts that undid an anonymous edit."""
    months = {}
    for m, n in _rows("SELECT DATE_FORMAT(row_start, '%Y-%m') m, COUNT(*) FROM article "
                      "FOR SYSTEM_TIME ALL WHERE page_id = ? GROUP BY m", (page_id,)):
        months[m] = {"month": m, "edits": n, "reverts": 0, "cleanup": 0}
    for m, n, anon in _rows("SELECT DATE_FORMAT(reverted_at, '%Y-%m') m, COUNT(*), "
                            "SUM(undone_anonymous) FROM revert_event WHERE page_id = ? GROUP BY m",
                            (page_id,)):
        months[m].update(reverts=n, cleanup=int(anon))
    if not months:
        return {"error": f"no article {page_id}"}, 404
    return {"page_id": page_id, "months": [months[m] for m in sorted(months)]}


if __name__ == "__main__":
    import time
    from app.main import app
    client, page = app.test_client(), 1256          # Talvisota
    for day in ("2005-06-01", "2015-06-01", "2025-06-01"):
        t = time.perf_counter()
        got = client.get(f"/article/{page}?as_of={day}").get_json()
        ms = (time.perf_counter() - t) * 1000
        (want,) = _rows("SELECT rev_id FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? "
                        "AND row_start <= ? AND row_end > ?", (page, day, day))[0]
        assert got["rev_id"] == want and ms < 1000, (day, got["rev_id"], want, ms)
        print(f"as of {day}: rev {want}, {len(got['blocks'])} blocks, {ms:.0f} ms")
    t = time.perf_counter()
    months = client.get(f"/article/{page}/timeline").get_json()["months"]
    ms = (time.perf_counter() - t) * 1000
    s = stats([page])[page]
    assert sum(m["edits"] for m in months) == s["edits"] and ms < 1000
    assert sum(m["reverts"] for m in months) == s["reverts"] == 328
    assert client.get(f"/article/{page}?as_of=1999-01-01").status_code == 404
    assert client.get(f"/article/{page}?as_of=nonsense").status_code == 400
    print(f"timeline: {len(months)} months, {s['edits']} edits, {s['reverts']} reverts, {ms:.0f} ms")
    print("ok")
