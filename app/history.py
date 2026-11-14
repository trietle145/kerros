"""Time views (owner: A): an article as of a date, its edit timeline, and edit/revert counts for
the source cards. All times are UTC, like Wikipedia's.

    /article/<id>[?as_of=YYYY-MM-DD]   page: timeline chart + the article as it stood then
    add &format=json for the data;   /article/<id>/timeline   edits and reverts per month (JSON)

    python -m app.history        # self-check against direct SQL on Talvisota (needs the database)
"""
from contextlib import closing
from datetime import UTC, datetime, timedelta
from math import sqrt

from flask import Blueprint, render_template, request

from app import xlang
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


def _version(page_id, moment):
    """The version live at `moment`, or None if the article did not exist yet."""
    found = _rows("SELECT title, rev_id, user, comment, row_start, row_end, text FROM article "
                  "FOR SYSTEM_TIME AS OF TIMESTAMP ? WHERE page_id = ?",
                  (moment.strftime("%Y-%m-%d %H:%M:%S"), page_id))
    if not found:
        return None
    title, rev_id, user, comment, start, end, text = found[0]
    return {"page_id": page_id, "title": title, "rev_id": rev_id, "as_of": moment.isoformat(),
            "valid_from": start.isoformat(), "valid_to": None if end >= FOREVER else end.isoformat(),
            "user": user, "comment": comment, "url": f"https://fi.wikipedia.org/?oldid={rev_id}",
            "blocks": clean(text)}


def _months(page_id):
    """[{month, edits, reverts, cleanup}] for months with edits; cleanup = undid an anonymous edit."""
    months = {}
    for m, n in _rows("SELECT DATE_FORMAT(row_start, '%Y-%m') m, COUNT(*) FROM article "
                      "FOR SYSTEM_TIME ALL WHERE page_id = ? GROUP BY m", (page_id,)):
        months[m] = {"month": m, "edits": n, "reverts": 0, "cleanup": 0}
    for m, n, anon in _rows("SELECT DATE_FORMAT(reverted_at, '%Y-%m') m, COUNT(*), "
                            "SUM(undone_anonymous) FROM revert_event WHERE page_id = ? GROUP BY m",
                            (page_id,)):
        months[m].update(reverts=n, cleanup=int(anon))
    return [months[m] for m in sorted(months)]


def _next_month(y, m):
    return (y + m // 12, m % 12 + 1)


def _chart(months, selected, width=1000, height=150):
    """Bars for every month from the first edit to the last (empty months included, so the x axis
    is real time). Heights are sqrt-scaled so quiet months stay visible next to the spikes."""
    by_month = {m["month"]: m for m in months}
    y, mo = map(int, months[0]["month"].split("-"))
    end = tuple(map(int, months[-1]["month"].split("-")))
    slots = []
    while (y, mo) <= end:
        slots.append(by_month.get(f"{y}-{mo:02d}", {"month": f"{y}-{mo:02d}", "edits": 0,
                                                    "reverts": 0, "cleanup": 0}))
        y, mo = _next_month(y, mo)
    top, w = max(m["edits"] for m in slots), width / len(slots)
    scale = lambda n: height * sqrt(n / top) if n else 0           # noqa: E731
    bars = []
    for i, m in enumerate(slots):
        ny, nm = _next_month(*map(int, m["month"].split("-")))
        bars.append({**m, "x": i * w, "w": max(w - 1, 1), "h": scale(m["edits"]),
                     "h_rev": scale(m["reverts"]), "h_clean": scale(m["cleanup"]),
                     "href": f"?as_of={ny}-{nm:02d}-01", "selected": m["month"] == selected,
                     "year": m["month"][:4] if m["month"].endswith("-01") else None})
    step = 1 if len(slots) <= 12 * 14 else 2
    return {"bars": bars, "width": width, "height": height,
            "years": [b for b in bars if b["year"] and int(b["year"]) % step == 0]}


def _sections(blocks):
    """Blocks -> items for the template, with runs of list items wrapped into one list."""
    out = []
    for kind, text in blocks:
        if kind == "li":
            if not out or out[-1][0] != "ul":
                out.append(("ul", []))
            out[-1][1].append(text)
        else:
            out.append((kind if kind in ("p", "h2") else "h3" if kind[0] == "h" else kind, text))
    return out


@bp.get("/article/<int:page_id>")
def article(page_id):
    """The article as it stood on ?as_of=YYYY-MM-DD[THH:MM[:SS]] (default: now). Page by default,
    JSON with &format=json."""
    as_json = request.args.get("format") == "json"
    as_of = request.args.get("as_of")
    try:
        moment = datetime.fromisoformat(as_of) if as_of else datetime.now(UTC).replace(tzinfo=None)
    except ValueError:
        msg = "as_of must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
        return ({"error": msg}, 400) if as_json else (render_template("article.html", error=msg), 400)
    version = _version(page_id, moment)
    if as_json:
        return version or ({"error": f"article {page_id} did not exist on {moment:%Y-%m-%d}"}, 404)
    months = _months(page_id)
    if not months:
        return render_template("article.html", error=f"No article {page_id}."), 404
    title = version["title"] if version else _rows(
        "SELECT title FROM article WHERE page_id = ?", (page_id,))[0][0]     # today's title
    return render_template(
        "article.html", page_id=page_id, version=version, moment=moment, title=title,
        sections=_sections(version["blocks"]) if version else [],
        chart=_chart(months, (moment - timedelta(seconds=1)).strftime("%Y-%m")),
        edits=sum(m["edits"] for m in months), reverts=sum(m["reverts"] for m in months),
        cleanup=sum(m["cleanup"] for m in months), first_month=months[0]["month"],
        today=datetime.now(UTC).date().isoformat(), other_langs=xlang.langs([page_id]).get(page_id, []))


@bp.get("/article/<int:page_id>/timeline")
def timeline(page_id):
    """Edits and reverts per month; cleanup = reverts that undid an anonymous edit."""
    months = _months(page_id)
    if not months:
        return {"error": f"no article {page_id}"}, 404
    return {"page_id": page_id, "months": months}


if __name__ == "__main__":
    import time
    from app.main import app
    client, page = app.test_client(), 1256          # Talvisota
    for day in ("2005-06-01", "2015-06-01", "2025-06-01"):
        t = time.perf_counter()
        got = client.get(f"/article/{page}?as_of={day}&format=json").get_json()
        ms = (time.perf_counter() - t) * 1000
        (want,) = _rows("SELECT rev_id FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? "
                        "AND row_start <= ? AND row_end > ?", (page, day, day))[0]
        assert got["rev_id"] == want and ms < 1000, (day, got["rev_id"], want, ms)
        t = time.perf_counter()
        html = client.get(f"/article/{page}?as_of={day}").get_data(as_text=True)
        page_ms = (time.perf_counter() - t) * 1000
        assert f"oldid={want}" in html and "<svg" in html and page_ms < 1000, (day, page_ms)
        print(f"as of {day}: rev {want}, {len(got['blocks'])} blocks, json {ms:.0f} ms, "
              f"page {page_ms:.0f} ms")
    t = time.perf_counter()
    months = client.get(f"/article/{page}/timeline").get_json()["months"]
    ms = (time.perf_counter() - t) * 1000
    s = stats([page])[page]
    assert sum(m["edits"] for m in months) == s["edits"] and ms < 1000
    assert sum(m["reverts"] for m in months) == s["reverts"] == 328
    assert client.get(f"/article/{page}?as_of=1999-01-01&format=json").status_code == 404
    assert "did not exist yet" in client.get(f"/article/{page}?as_of=1999-01-01").get_data(as_text=True)
    assert client.get(f"/article/{page}?as_of=nonsense").status_code == 400
    assert client.get("/article/999999999").status_code == 404
    print(f"timeline: {len(months)} months, {s['edits']} edits, {s['reverts']} reverts, {ms:.0f} ms")
    print("ok")
