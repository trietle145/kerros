"""Cross-language gaps (owner: A, backend): what English and Swedish Wikipedia say that the Finnish
article does not. scripts/build_xlang.py labels every en/sv paragraph once; this module reads them.

    /compare/<page_id>          page: the same, section by section, next to the closest Finnish text
    GET /api/xlang/<page_id>    the en/sv paragraphs of one Finnish article, labelled, in article order
    adds(vector, ...)           for /ask: up to 3 en/sv paragraphs that answer the question and Finnish lacks
    langs(page_ids)             for /ask: which Finnish articles have an English / Swedish counterpart

    python -m app.xlang         # self-check (needs the database with xlang_passage loaded)
"""
from contextlib import closing
from urllib.parse import quote

import mariadb
from flask import Blueprint, render_template

from app.db import connect

bp = Blueprint("xlang", __name__)
LABELS = ("covered", "partly", "elsewhere", "lost", "missing")
SLACK = 0.02     # ponytail: an en/sv paragraph may sit this much farther from the question than the farthest cited Finnish passage
ADD_MAX = 0.42   # and never farther than this: on 24 test questions every useful item was <= 0.42, the noise >= 0.44


def _rows(sql, params=()):
    """Rows, or [] while the xlang tables are not loaded on this database (local copies)."""
    try:
        with closing(connect()) as con:
            cur = con.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
    except mariadb.ProgrammingError as e:
        if "doesn't exist" in str(e):
            return []
        raise


def section_url(lang, title, heading):
    anchor = "#" + quote(heading.replace(" ", "_"), safe="") if heading else ""
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}{anchor}"


def langs(page_ids):
    """{fi_page_id: ["en", "sv"]} for the given Finnish articles (missing = Finnish only)."""
    out = {}
    if page_ids:
        for p, lang in _rows("SELECT fi_page_id, lang FROM article_langlink WHERE fi_page_id IN (%s) ORDER BY lang"
                             % ",".join("?" * len(page_ids)), tuple(page_ids)):
            out.setdefault(p, []).append(lang)
    return out


def adds(vector, page_ids, passage_ids, k=3):
    """en/sv paragraphs labelled `missing` from the counterparts of the cited Finnish articles, that
    are about as close to the question as the farthest cited Finnish passage. [] = show nothing."""
    if not page_ids or not passage_ids:
        return []
    bar = _rows("SELECT MAX(VEC_DISTANCE_COSINE(v.embedding, ?)) FROM passage p JOIN passage_vector v "
                "USING (text_hash) WHERE p.passage_id IN (%s)" % ",".join("?" * len(passage_ids)),
                (vector, *passage_ids))[0][0]
    rows = _rows("SELECT x.lang, x.title, x.heading, x.text, x.fi_page_id, VEC_DISTANCE_COSINE(v.embedding, ?) d "
                 "FROM xlang_passage x JOIN xlang_vector v USING (text_hash) "
                 "WHERE x.fi_page_id IN (%s) AND x.label = 'missing' HAVING d <= ? ORDER BY d LIMIT 12"
                 % ",".join("?" * len(page_ids)), (vector, *page_ids, min(bar + SLACK, ADD_MAX)))
    out, seen = [], set()
    for lang, title, heading, text, fi, d in rows:          # one paragraph per section
        if (lang, title, heading) not in seen and len(out) < k:
            seen.add((lang, title, heading))
            out.append({"lang": lang, "title": title, "heading": heading, "text": text, "fi_page_id": fi,
                        "url": section_url(lang, title, heading), "distance": round(d, 3)})
    return out


def coverage(page_id):
    """{lang: {title, url, counts, items}} for one Finnish article; {} if it has no en/sv counterpart."""
    rows = _rows("SELECT x.lang, x.page_id, x.title, x.heading, x.text, x.label, x.d, x.since, x.lost_from, "
                 "x.lost_until, x.other_page_id, o.title, p.heading, p.text "
                 "FROM xlang_passage x LEFT JOIN passage p ON p.passage_id = x.fi_passage_id "
                 "LEFT JOIN passage o ON o.page_id = x.other_page_id AND o.position = 0 "
                 "WHERE x.fi_page_id = ? AND x.label IS NOT NULL ORDER BY x.lang, x.position", (page_id,))
    out = {}
    for lang, pid, title, heading, text, label, d, since, lfrom, luntil, other, otitle, fh, ft in rows:
        L = out.setdefault(lang, {"title": title, "url": f"https://{lang}.wikipedia.org/?curid={pid}",
                                  "counts": dict.fromkeys(LABELS, 0), "items": []})
        L["counts"][label] += 1
        L["items"].append({
            "heading": heading, "text": text, "label": label, "distance": round(d, 3),
            "url": section_url(lang, title, heading),
            "since": since and since.isoformat(), "lost_from": lfrom and lfrom.isoformat(),
            "lost_until": luntil and luntil.isoformat(),
            "other": {"page_id": other, "title": otitle} if other else None,
            "closest_fi": {"heading": fh, "text": ft} if ft else None})
    return out


def sections(page_id):
    """The other-Wikipedias panel: per language, runs of paragraphs under one heading, each section
    shown with its most notable label (a gap outranks a match)."""
    order = ("missing", "lost", "elsewhere", "partly", "covered")
    out = {}
    for lang, L in coverage(page_id).items():
        secs = []
        for it in L["items"]:
            if not secs or secs[-1]["heading"] != it["heading"]:
                secs.append({"heading": it["heading"], "items": []})
            secs[-1]["items"].append(it)
        for sec in secs:
            sec["first"] = next(i for l in order for i in sec["items"] if i["label"] == l)
        out[lang] = {**L, "sections": secs, "total": len(L["items"])}
    return out


@bp.get("/compare/<int:page_id>")
def page(page_id):
    langs_ = sections(page_id)
    title = _rows("SELECT title FROM passage WHERE page_id = ? AND position = 0", (page_id,))
    if not langs_ or not title:
        return render_template("article.html", error=f"No English or Swedish article to compare with for {page_id}."), 404
    return render_template("compare.html", page_id=page_id, title=title[0][0], xlang=langs_)


@bp.get("/api/xlang/<int:page_id>")
def api(page_id):
    langs_ = coverage(page_id)
    return ({"page_id": page_id, "langs": langs_} if langs_
            else ({"error": f"article {page_id} has no English or Swedish counterpart"}, 404))


if __name__ == "__main__":
    c = coverage(1256)                                         # Talvisota
    assert set(c) == {"en", "sv"} and c["en"]["title"] == "Winter War", c.keys()
    mainila = [i for i in c["en"]["items"] if i["heading"] == "Shelling of Mainila and Soviet intentions"]
    assert mainila and mainila[0]["label"] == "elsewhere" and mainila[0]["other"]["title"] == "Mainilan laukaukset", mainila
    assert langs([1256, 8295]).get(1256) == ["en", "sv"]
    assert coverage(999999999) == {}
    for lang, L in c.items():
        print(lang, L["title"], L["counts"])
    print("ok")
