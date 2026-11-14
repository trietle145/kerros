"""Fixtures for the frontend (app/static/fixtures/): graph-<id>.json, path-<id>.json and
related*.json. Real data, read from MariaDB with SELECT statements only. Follows
tasks/plan-graph.md (G1 link index, G2 node choice, G4 yearly snapshots, G5 heuristic path) and
the parsing rules in docs/DATA_NOTES.md, so the live /api/graph can return the same shapes.

    .venv\\Scripts\\python.exe tools\\make_fixtures.py            # heroes + every article in related*.json
    .venv\\Scripts\\python.exe tools\\make_fixtures.py 440 8617   # graph + path for these page_ids only

Every run checks itself with asserts (parser rules, hero cases, every file written).
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.common import connect  # noqa: E402

OUT = ROOT / "app/static/fixtures"
HEROES = (1256, 8295, 1150)          # Talvisota, Mainilan laukaukset, Suomen sisällissota
SPARSE = 241905                      # a neighbour of 8295 with 7 linked articles: shows the "related" fill-up
LAST = 2026                          # the dataset ends 2026-10-01: this year = the current version
LINK = re.compile(r"\[\[([^\[\]|#]*)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")
REDIRECT = re.compile(r"\s*#(OHJAUS|REDIRECT)", re.I)
NAMESPACES = {"luokka", "tiedosto", "kuva", "file", "image", "category", "wikipedia", "malline",
              "käyttäjä", "en", "s", "wikt", "gutenberg"}
ORDER = {"mutual": 0, "out": 1, "in": 2}
WHY = {"mutual": "it and the main article link to each other", "out": "the main article links to it",
       "in": "it links to the main article", "related": "it is close in content to the main article"}


def namespaced(title):
    return ":" in title and title.split(":", 1)[0].strip().lower() in NAMESPACES


def parse_links(text):
    """Wikitext -> the linked titles, normalised (DATA_NOTES.md, parsing rules 1-4)."""
    out = set()
    for m in LINK.finditer(text):
        t = m.group(1).replace("_", " ").strip().lstrip(":").strip()
        if t and not namespaced(t):
            out.add(t[0].upper() + t[1:])
    return out


def marks(ids):
    return ",".join("?" * len(ids))


def trim(text, n):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


class Index:
    """All current articles, read once: title/rev per article, out- and in-links (rule 5)."""

    def __init__(self, cur):
        cur.execute("SELECT page_id, title, rev_id, text FROM article")
        rows = cur.fetchall()
        self.redirect = {title: next(iter(parse_links(text)), None)
                         for _, title, _, text in rows if REDIRECT.match(text)}
        self.info = {p: (title, rev) for p, title, rev, _ in rows if title not in self.redirect}
        self.ids = {title: p for p, (title, _) in self.info.items()}
        assert not any(namespaced(t) for t in self.ids), "a real title looks like a namespace link"
        self.out = {p: self.links(p, text) for p, title, _, text in rows if p in self.info}
        self.inn = defaultdict(set)
        for p, targets in self.out.items():
            for t in targets:
                self.inn[t].add(p)

    def links(self, page_id, text):
        """Page ids one version links to: redirects resolved, outside targets and self links dropped."""
        if REDIRECT.match(text):                     # an old version that was a redirect: no links
            return set()
        return {self.ids.get(self.redirect.get(t, t)) for t in parse_links(text)} - {None, page_id}


def choose(cur, idx, main):
    """Main + up to 19 neighbours: mutual, then out, then in links, nearest article vector first
    within each group. Fewer than 10 linked: fill up to 10 with the nearest fi articles (related)."""
    out, inn = idx.out[main], idx.inn[main]
    relation = {p: "mutual" if p in out and p in inn else "out" if p in out else "in" for p in out | inn}
    cur.execute("SELECT embedding FROM article_vector WHERE lang = 'fi' AND page_id = ?", (main,))
    vec = cur.fetchone()                             # None for the 457 articles without a vector
    dist = {}
    if vec and relation:
        cur.execute("SELECT page_id, VEC_DISTANCE_COSINE(embedding, ?) FROM article_vector "
                    f"WHERE lang = 'fi' AND page_id IN ({marks(relation)})", (vec[0], *relation))
        dist = dict(cur.fetchall())
    chosen = sorted(relation, key=lambda p: (ORDER[relation[p]], dist.get(p, 9), p))[:19]
    if vec and len(chosen) < 10:
        for p, _ in nearest(cur, vec[0], 40):
            if len(chosen) < 10 and p != main and p not in relation and p in idx.info:
                chosen.append(p)
                relation[p] = "related"
    return [main, *chosen], {main: "main", **relation}


def nearest(cur, vec, n):
    """[(page_id, distance)]: vector search in its own subquery so the index is used."""
    cur.execute("SELECT page_id, d FROM (SELECT page_id, VEC_DISTANCE_COSINE(embedding, ?) d "
                f"FROM article_vector WHERE lang = 'fi' ORDER BY d LIMIT {int(n)}) v ORDER BY d", (vec,))
    return cur.fetchall()


def leads(cur, ids):
    cur.execute(f"SELECT page_id, text FROM passage WHERE position = 0 AND page_id IN ({marks(ids)})", ids)
    return dict(cur.fetchall())


def graph(cur, idx, main):
    """The /api/graph/<page_id> JSON (plan-graph.md, "API contract")."""
    ids, relation = choose(cur, idx, main)
    lead = leads(cur, ids)
    cur.execute("SELECT page_id, YEAR(MIN(row_start)) FROM article FOR SYSTEM_TIME ALL "
                f"WHERE page_id IN ({marks(ids)}) GROUP BY page_id", ids)
    created = dict(cur.fetchall())
    cur.execute(f"SELECT page_id, COUNT(*) FROM revert_event WHERE page_id IN ({marks(ids)}) "
                "GROUP BY page_id", ids)
    reverts = dict(cur.fetchall())
    nodes = [{"id": p, "title": idx.info[p][0], "relation": relation[p], "lead": trim(lead.get(p, ""), 300),
              "rev_id": idx.info[p][1], "created": created[p], "reverts": reverts.get(p, 0)} for p in ids]
    years, snapshots = list(range(created[main], LAST + 1)), {}
    for year in years:
        if year == LAST:
            revs, out = {p: idx.info[p][1] for p in ids}, idx.out
        else:
            cur.execute("SELECT page_id, rev_id, text FROM article FOR SYSTEM_TIME AS OF "
                        f"'{year}-12-31 23:59:59' WHERE page_id IN ({marks(ids)})", ids)
            rows = cur.fetchall()
            revs = {p: rev for p, rev, _ in rows}
            out = {p: idx.links(p, text) for p, _, text in rows}
        # a link is kept only when both ends are chosen nodes that existed that year
        snapshots[str(year)] = {"revs": {str(p): revs[p] for p in ids if p in revs},
                                "links": sorted([s, t] for s in revs for t in out[s] if t in revs)}
    return {"main": main, "nodes": nodes, "years": years, "snapshots": snapshots}


def path(idx, g):
    """G5's fallback order: most linked-to (most general) first, the main article last."""
    relation = {n["id"]: n["relation"] for n in g["nodes"][1:]}
    steps = sorted(relation, key=lambda p: (-len(idx.inn[p]), p))[:4]
    out = [{"id": p, "why": (f"Start with the broadest topic here: {len(idx.inn[p]):,} articles link to it, "
                             f"and {WHY[relation[p]]}." if i == 0 else
                             f"Next, a narrower topic ({len(idx.inn[p]):,} articles link to it); {WHY[relation[p]]}.")}
           for i, p in enumerate(steps)]
    out.append({"id": g["main"], "why": "End with the article you opened, now that its background is in place."})
    return {"path": out, "source": "heuristic"}


def related(cur, idx, page_id):
    """Stand-in for /api/related?q=: the 10 fi articles nearest to one article's stored vector
    (the live route will group search(q) passages by article; its score is an RRF score)."""
    cur.execute("SELECT embedding FROM article_vector WHERE lang = 'fi' AND page_id = ?", (page_id,))
    hits = [(p, d) for p, d in nearest(cur, cur.fetchone()[0], 20) if p in idx.info][:10]
    lead = leads(cur, [p for p, _ in hits])
    return {"articles": [{"page_id": p, "title": idx.info[p][0], "snippet": trim(lead.get(p, ""), 220),
                          "score": round(1 - d, 3)} for p, d in hits]}


def check(g, p):
    """What the frontend relies on, for every file written."""
    main, ids = g["main"], [n["id"] for n in g["nodes"]]
    created = {n["id"]: n["created"] for n in g["nodes"]}
    assert ids[0] == main and len(set(ids)) == len(ids) <= 20
    assert g["years"] == list(range(created[main], LAST + 1))
    for year in g["years"]:
        snap = g["snapshots"][str(year)]
        assert str(main) in snap["revs"], f"main node missing in {year}"
        assert set(snap["revs"]) == {str(i) for i in ids if created[i] <= year}, f"nodes in {year}"
        assert all(str(s) in snap["revs"] and str(t) in snap["revs"] and s != t for s, t in snap["links"])
    assert 2 <= len(p["path"]) <= 6 and p["path"][-1]["id"] == main and {s["id"] for s in p["path"]} <= set(ids)


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return (OUT / name).stat().st_size


if __name__ == "__main__":
    got = parse_links("[[Kustaa III:n sota]] [[Luokka:A]] [[Tiedosto:B.jpg|thumb|[[talvisota#Tausta|sota]]]] "
                      "[[Kuva:C.png]] [[en:D]] [[:Luokka:E]] [[J._V._Snellman|Snellman]] [[ Jatkosota ]]")
    assert got == {"Kustaa III:n sota", "Talvisota", "J. V. Snellman", "Jatkosota"}, got

    t = time.time()
    con = connect()
    cur = con.cursor()
    idx = Index(cur)
    n_links = sum(map(len, idx.out.values()))
    print(f"link index: {len(idx.out):,} articles, {n_links:,} links, {len(idx.redirect)} redirects, "
          f"{time.time() - t:.1f} s")
    assert 19_500 < len(idx.out) < 19_700 and 130_000 < n_links < 145_000      # DATA_NOTES: 19,600 / 138,730
    assert 1256 in idx.out[8295]                                              # Mainila -> Talvisota

    targets = [int(a) for a in sys.argv[1:]]
    if not targets:
        lists = {"related.json": related(cur, idx, 1256), "related-then-vs-now.json": related(cur, idx, 1150)}
        for name, data in lists.items():
            assert len(data["articles"]) == 10 and all(a["snippet"] for a in data["articles"])
            print(f"{name}: {write(name, data):,} bytes, first: {data['articles'][0]['title']}")
        # SPARSE last: its fill-up path has not been run yet (the database went away), see its assert
        targets = list(dict.fromkeys([*HEROES, *(a["page_id"] for d in lists.values() for a in d["articles"]), SPARSE]))

    for main in targets:
        t = time.time()
        g = graph(cur, idx, main)
        p = path(idx, g)
        check(g, p)
        first, last = g["snapshots"][str(g["years"][0])], g["snapshots"][str(LAST)]
        count = defaultdict(int)
        for n in g["nodes"]:
            count[n["relation"]] += 1
        if main == 1256:
            assert len(g["nodes"]) == 20 and count["mutual"] == 19
        if main == SPARSE:                           # fewer than 10 linked -> filled up to 10 neighbours
            assert len(g["nodes"]) == 11 and count["related"] >= 1
        if main == 8295:
            assert 1256 in {n["id"] for n in g["nodes"]}
            assert len(g["snapshots"]["2005"]["links"]) < len(last["links"])
        size = write(f"graph-{main}.json", g)
        write(f"path-{main}.json", p)
        print(f"graph-{main}.json  {g['nodes'][0]['title']}: {size:,} bytes, {len(g['nodes'])} nodes {dict(count)}, "
              f"years {g['years'][0]}-{LAST}, nodes/links {len(first['revs'])}/{len(first['links'])} -> "
              f"{len(last['revs'])}/{len(last['links'])}, path {[s['id'] for s in p['path']]}, {time.time() - t:.1f} s")
    print("ok")
