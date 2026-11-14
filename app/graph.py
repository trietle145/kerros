"""The article graph through time (owner: A, backend): which articles an article links to, and how
those links grew. Edges are real wiki links parsed from the raw wikitext (deterministic, every
line traceable to an edit); vectors only break ties when ranking neighbours. Plan and contract:
tasks/plan-graph.md (b-search-app) and docs/frontend.md (frontend). The page is B's.

    GET /api/graph/<page_id>      nodes (main + up to 19 linked neighbours), links today and per year
    python -m app.graph           # self-check: parser rules, then the index and one graph (needs the DB)
"""
import re
from contextlib import closing
from functools import lru_cache

from flask import Blueprint

from app.db import connect
from app.history import stats

bp = Blueprint("graph", __name__)

LINK = re.compile(r"\[\[([^\[\]|#]*)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")
NAMESPACES = {"luokka", "tiedosto", "kuva", "file", "image", "category", "wikipedia", "malline",
              "käyttäjä", "en", "s", "wikt", "gutenberg", "sv", "de", "commons", "media"}
REDIRECT = re.compile(r"\s*#(?:UUDELLEENOHJAUS|OHJAUS|REDIRECT)\s*\[\[([^\]|#]+)", re.I)
MAX_NODES = 20


def norm(title):
    t = title.replace("_", " ").strip()
    return t[:1].upper() + t[1:]


def parse_links(text):
    """Wikitext -> set of linked article titles (normalised). Namespace links ([[Luokka:X]],
    [[Tiedosto:X]], interwiki, [[:Luokka:X]]) are skipped by a known prefix list, because 44 real
    titles contain a colon (Kustaa III:n sota); #section and |label are dropped."""
    out = set()
    for target, _, _ in LINK.findall(text):
        target = target.strip()
        if target.startswith(":") or not target:
            continue
        if ":" in target and target.split(":", 1)[0].strip().lower() in NAMESPACES:
            continue
        out.add(norm(target))
    return out


@lru_cache(maxsize=1)
def link_index():
    """Built once (~6 s): titles, redirects, out-links and in-links of the current articles."""
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute("SELECT page_id, title, text FROM article")
        rows = cur.fetchall()
    ids = {norm(t): p for p, t, _ in rows}
    title = {p: t for p, t, _ in rows}
    redirect = {p: norm(m[1]) for p, _, text in rows if (m := REDIRECT.match(text))}
    resolve = lambda t: ids.get(t) if ids.get(t) not in redirect else ids.get(redirect[ids[t]])  # noqa: E731
    out, inn, outside = {}, {}, {}
    for p, _, text in rows:
        if p in redirect:
            continue
        links = parse_links(text)
        out[p] = {q for t in links if (q := resolve(t)) and q != p}
        outside[p] = sorted(t for t in links if not resolve(t))
        for q in out[p]:
            inn.setdefault(q, set()).add(p)
    return {"title": title, "redirect": redirect, "ids": ids, "resolve": resolve, "out": out,
            "inn": inn, "outside": outside}


def neighbourhood(page_id):
    """Main + up to 19 linked neighbours: mutual links first, then out-links, then in-links; ties
    broken by vector distance to the main article (whole-article S vectors)."""
    ix = link_index()
    out, inn = ix["out"].get(page_id, set()), ix["inn"].get(page_id, set())
    relation = {q: "mutual" if q in out and q in inn else "out" if q in out else "in" for q in out | inn}
    dist = {}
    if relation:
        with closing(connect()) as con:
            cur = con.cursor()
            cur.execute("SELECT embedding INTO @v FROM article_vector WHERE lang = 'fi' AND page_id = ?",
                        (page_id,))
            marks = ",".join("?" * len(relation))
            cur.execute(f"SELECT page_id, VEC_DISTANCE_COSINE(embedding, @v) FROM article_vector "
                        f"WHERE lang = 'fi' AND page_id IN ({marks})", tuple(relation))
            dist = {p: d for p, d in cur.fetchall() if d is not None}
    order = {"mutual": 0, "out": 1, "in": 2}
    chosen = sorted(relation, key=lambda q: (order[relation[q]], dist.get(q, 9), q))[:MAX_NODES - 1]
    return [page_id] + chosen, relation


@lru_cache(maxsize=256)
def graph(page_id):
    """The /api/graph JSON for one article (cached: the history doesn't change)."""
    ix = link_index()
    page_id = ix["resolve"](norm(ix["title"].get(page_id, ""))) or page_id   # a redirect -> its target
    if page_id not in ix["out"]:
        return None
    nodes, relation = neighbourhood(page_id)
    marks = ",".join("?" * len(nodes))
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(f"SELECT page_id, text FROM passage WHERE position = 0 AND page_id IN ({marks})",
                    tuple(nodes))
        lead = dict(cur.fetchall())
        cur.execute(f"SELECT page_id, rev_id FROM article WHERE page_id IN ({marks})", tuple(nodes))
        rev = dict(cur.fetchall())
        cur.execute(f"SELECT page_id, YEAR(MIN(row_start)) FROM article FOR SYSTEM_TIME ALL "
                    f"WHERE page_id IN ({marks}) GROUP BY page_id", tuple(nodes))
        created = dict(cur.fetchall())
        first, last = created[page_id], 2026
        snapshots = {}
        for year in range(first, last):                       # each year's end, as Wikipedia stood
            cur.execute(f"SELECT page_id, rev_id, text FROM article FOR SYSTEM_TIME AS OF "
                        f"TIMESTAMP '{year}-12-31 23:59:59' WHERE page_id IN ({marks})", tuple(nodes))
            snapshots[str(year)] = _snapshot(cur.fetchall(), set(nodes), ix)
    today = {q: ix["out"].get(q, set()) & set(nodes) for q in nodes}
    snapshots[str(last)] = {"revs": {str(q): rev[q] for q in nodes if q in rev},
                            "links": sorted([a, b] for a in nodes for b in today[a])}
    counts = stats(nodes)
    return {"main": page_id,
            "nodes": [{"id": q, "title": ix["title"][q], "relation": relation.get(q, "main"),
                       "lead": (lead.get(q) or "")[:300], "rev_id": rev.get(q), "created": created.get(q),
                       "edits": counts[q]["edits"], "reverts": counts[q]["reverts"],
                       "url": f"https://fi.wikipedia.org/?oldid={rev.get(q)}"} for q in nodes],
            "years": list(range(first, last + 1)), "snapshots": snapshots,
            "outside": ix["outside"].get(page_id, [])[:30]}


def _snapshot(rows, nodes, ix):
    """One year's versions -> {"revs": {page_id: rev_id}, "links": [[from, to], ...]} among the nodes."""
    links = set()
    for p, _, text in rows:
        for t in parse_links(text):
            q = ix["resolve"](t)
            if q in nodes and q != p:
                links.add((p, q))
    return {"revs": {str(p): r for p, r, _ in rows}, "links": sorted(list(l) for l in links)}


@bp.get("/api/graph/<int:page_id>")
def api_graph(page_id):
    g = graph(page_id)
    return g if g else ({"error": f"no article {page_id}"}, 404)


WHY = {"mutual": "it and the main article link to each other", "out": "the main article links to it",
       "in": "it links to the main article"}


def reading_path(page_id):
    """Reading order among the shown nodes, no model: the most linked-to (most general) articles
    first, the opened article last."""
    g = graph(page_id)
    if not g:
        return None
    inn = link_index()["inn"]
    rel = {n["id"]: n["relation"] for n in g["nodes"] if n["id"] != g["main"]}
    steps = sorted(rel, key=lambda p: (-len(inn.get(p, ())), p))[:4]
    path = [{"id": p, "why": (f"Start with the broadest topic here: {len(inn.get(p, ())):,} articles link "
                              f"to it, and {WHY[rel[p]]}." if i == 0 else
                              f"Next, a narrower topic ({len(inn.get(p, ())):,} articles link to it); "
                              f"{WHY[rel[p]]}.")} for i, p in enumerate(steps)]
    path.append({"id": g["main"], "why": "End with the article you opened, now that its background is in place."})
    return {"path": path, "source": "heuristic"}


@bp.get("/api/graph/<int:page_id>/path")
def api_path(page_id):
    p = reading_path(page_id)
    return p if p else ({"error": f"no article {page_id}"}, 404)


@bp.get("/api/related")
def api_related():
    """Articles behind a question: the hybrid search's passages grouped by article (best passage
    as the snippet), up to 10, for the graph buttons under an answer."""
    from flask import request
    from app.search import search
    q = (request.args.get("q") or "").strip()
    if not q:
        return {"error": "q is required"}, 400
    hits = search(q, k=10, per_article=1)
    return {"articles": [{"page_id": h["page_id"], "title": h["title"], "score": h["score"],
                          "snippet": h["text"][:220] + ("…" if len(h["text"]) > 220 else "")} for h in hits]}


if __name__ == "__main__":
    import time
    assert parse_links("[[Kustaa III:n sota]] [[Luokka:Sodat]] [[:Luokka:X]] [[Tiedosto:a.jpg|kuva]] "
                       "[[en:Winter War]] [[Talvisota#Tausta|sota]] [[J._V._Snellman]]") == {
        "Kustaa III:n sota", "Talvisota", "J. V. Snellman"}
    print("parser ok")
    t = time.time()
    ix = link_index()
    print(f"index: {sum(len(v) for v in ix['out'].values()):,} links over {len(ix['out']):,} articles, "
          f"{len(ix['redirect'])} redirects, {time.time() - t:.1f} s")
    assert 1256 in ix["out"][8295], "Mainilan laukaukset should link to Talvisota"
    t = time.time()
    g = graph(8295)
    print(f"graph(8295): {len(g['nodes'])} nodes, years {g['years'][0]}–{g['years'][-1]}, "
          f"{len(g['snapshots']['2005']['links'])} links in 2005 vs {len(g['snapshots']['2026']['links'])} now, "
          f"{time.time() - t:.1f} s; outside: {g['outside'][:5]}")
    assert any(n["id"] == 1256 for n in g["nodes"])
    assert len(g["snapshots"]["2005"]["links"]) < len(g["snapshots"]["2026"]["links"])
    t = time.time()
    graph(8295)
    print(f"cached: {(time.time() - t) * 1000:.0f} ms;", "relations:",
          {r: sum(n["relation"] == r for n in g["nodes"]) for r in ("main", "mutual", "out", "in")})
    print("ok")
