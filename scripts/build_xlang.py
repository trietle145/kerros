"""What English and Swedish Wikipedia say that the Finnish article does not (backend, A).
Each en/sv article in dataset S that has a Finnish counterpart is cut into paragraphs with the same
section rule as the Finnish passages, embedded with the same bge-m3, and every paragraph gets a
label from vector distances computed in MariaDB:

  covered    the Finnish article has a close paragraph today (distance < 0.28); `since` = the first
             day a close Finnish paragraph appeared, from passage_history
  lost       the Finnish article had a close paragraph once (< 0.27) but not today (> 0.33);
             lost_from/lost_until, plus other_page_id if it now lives in another Finnish article
  elsewhere  another Finnish article covers it better (< 0.36): a sub-article ("Mainilan laukaukset")
  partly     the closest Finnish paragraph is on the topic, with less detail (< 0.36)
  missing    no Finnish paragraph says this
Thresholds were read off 505 hand-checked pairs on 8 articles (spike, 2026-11-14).
ponytail: fixed cut-offs, an LLM judge for "partly" if the eval asks for it.

    python scripts/build_xlang.py passages        # here: data/xlang/passages.parquet (~1 min)
    modal run scripts/modal_embed.py --src data/xlang/passages.parquet     # -> passage_vectors.parquet
    python scripts/build_xlang.py load            # server: xlang_passage + xlang_vector
    python scripts/build_xlang.py label           # server: a label for every paragraph (one SQL per article)
    python scripts/build_xlang.py --verify        # counts, every paragraph labelled, spot checks
"""
import argparse
import time
from collections import defaultdict
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

import build_passages
from common import ROOT, connect
from load_vectors import batches, stream_vectors

OUT = ROOT / "data" / "xlang"
build_passages.SKIP |= {"references", "notes", "citations", "sources", "bibliography", "further reading",
                        "external links", "see also", "explanatory notes", "works cited", "footnotes",
                        "referenser", "källor", "noter", "fotnoter", "externa länkar", "litteratur", "se även", "gallery", "bilder", "galleri"}
SCHEMA = build_passages.SCHEMA.append(pa.field("lang", pa.string())).append(pa.field("fi_page_id", pa.uint32()))
COVERED, LOST_PAST, LOST_NOW, NEAR = 0.28, 0.27, 0.33, 0.36
FOREVER = datetime(2038, 1, 1)
TABLES = ["""CREATE TABLE IF NOT EXISTS xlang_passage (
  lang          CHAR(2) NOT NULL,
  page_id       INT UNSIGNED NOT NULL,       -- the en/sv article
  position      SMALLINT UNSIGNED NOT NULL,
  fi_page_id    INT UNSIGNED NOT NULL,       -- its Finnish counterpart (article_langlink)
  title         VARCHAR(255) NOT NULL,
  heading       VARCHAR(255),
  text          TEXT NOT NULL,
  text_hash     BINARY(32) NOT NULL,
  label         ENUM('covered','partly','elsewhere','lost','missing'),
  d             FLOAT,                       -- distance to the closest paragraph of the Finnish article today
  fi_passage_id INT UNSIGNED,                -- that paragraph
  since         DATE,                        -- covered: first day a close Finnish paragraph was live
  lost_from     DATE,
  lost_until    DATE,
  other_page_id INT UNSIGNED,                -- elsewhere / lost: the Finnish article that covers it now
  other_d       FLOAT,
  PRIMARY KEY (lang, page_id, position),
  KEY (fi_page_id, label)
) CHARACTER SET utf8mb4""",
          """CREATE TABLE IF NOT EXISTS xlang_vector (
  text_hash  BINARY(32) NOT NULL PRIMARY KEY,
  embedding  VECTOR(1024) NOT NULL           -- no index: every search is within a few articles
)"""]


def make_passages():
    S = ROOT / "data" / "s"
    fi = {r["wikidata_id"]: r["page_id"] for r in pq.read_table(S / "articles-fi.parquet",
          columns=["page_id", "wikidata_id"]).to_pylist() if r["wikidata_id"]}
    rows = []
    for lang in ("en", "sv"):
        for r in pq.read_table(S / f"articles-{lang}.parquet").to_pylist():
            if r["wikidata_id"] in fi and not build_passages.REDIRECT.match(r["text"]):
                rows += [{**p, "lang": lang, "fi_page_id": fi[r["wikidata_id"]]}
                         for p in build_passages.passages(r["page_id"], r["rev_id"], r["title"], r["text"], markdown=True)]
    OUT.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, SCHEMA), OUT / "passages.parquet")
    print(f"{len(rows):,} paragraphs from {len({(r['lang'], r['page_id']) for r in rows}):,} en/sv articles")


def load(cur, con):
    for t in TABLES:
        cur.execute(t)
    cur.execute("TRUNCATE TABLE xlang_passage")
    rows = [(r["lang"], r["page_id"], r["position"], r["fi_page_id"], r["title"], r["heading"], r["text"], r["text_hash"])
            for r in pq.read_table(OUT / "passages.parquet").to_pylist()]
    batches(cur, con, "INSERT INTO xlang_passage (lang, page_id, position, fi_page_id, title, heading, text, text_hash) "
            "VALUES (?,?,?,?,?,?,?,?)", rows, "xlang_passage")
    stream_vectors(cur, con, OUT / "passage_vectors.parquet", "xlang_vector")


def label_article(cur, fi_page_id):
    """All en/sv paragraphs of one Finnish article: three set-based distance queries, then the rule."""
    key = lambda r: (r[0], r[1], r[2])                                       # noqa: E731
    cur.execute("SELECT x.lang, x.page_id, x.position, p.passage_id, VEC_DISTANCE_COSINE(xv.embedding, pv.embedding) "
                "FROM xlang_passage x JOIN xlang_vector xv USING (text_hash) "
                "JOIN passage p ON p.page_id = x.fi_page_id JOIN passage_vector pv ON pv.text_hash = p.text_hash "
                "WHERE x.fi_page_id = ?", (fi_page_id,))
    own = {}
    for r in cur.fetchall():
        if key(r) not in own or r[4] < own[key(r)][1]:
            own[key(r)] = (r[3], r[4])
    cur.execute("SELECT x.lang, x.page_id, x.position, h.row_start, h.row_end, "
                "VEC_DISTANCE_COSINE(xv.embedding, hv.embedding) d "
                "FROM xlang_passage x JOIN xlang_vector xv USING (text_hash) "
                "JOIN passage_history FOR SYSTEM_TIME ALL h ON h.page_id = x.fi_page_id "
                "JOIN history_vector hv ON hv.text_hash = h.text_hash "
                "WHERE x.fi_page_id = ? HAVING d < ?", (fi_page_id, COVERED))
    past = defaultdict(list)
    for r in cur.fetchall():
        past[key(r)].append(r[3:])
    cur.execute("SELECT x.lang, x.page_id, x.position, v.embedding FROM xlang_passage x "
                "JOIN xlang_vector v USING (text_hash) WHERE x.fi_page_id = ?", (fi_page_id,))
    out = []
    for lang, page_id, position, vector in cur.fetchall():
        k = (lang, page_id, position)
        fi_pid, d = own.get(k, (None, 1.0))
        h = past.get(k, [])
        row = {"label": None, "d": d, "fi_passage_id": fi_pid, "since": None, "lost_from": None,
               "lost_until": None, "other_page_id": None, "other_d": None}
        other = None
        if d >= LOST_NOW - 0.03:              # far from its own article: the closest Finnish paragraph anywhere
            # the vector as a parameter, not a subquery: only then does MariaDB use the vector index
            cur.execute("SELECT p.page_id, v.d FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) d "
                        "FROM passage_vector ORDER BY d LIMIT 1) v JOIN passage p USING (text_hash) LIMIT 1", (vector,))
            other = cur.fetchone()
            if other and other[0] == fi_page_id:
                other = None
        once = [x for x in h if x[2] < LOST_PAST]
        if d < COVERED:
            row.update(label="covered", since=min(x[0] for x in h).date() if h else None)
        elif once and d > LOST_NOW:
            row.update(label="lost", lost_from=min(x[0] for x in once).date(),
                       lost_until=max(x[1] for x in once).date())
            if other and other[1] < LOST_NOW:
                row.update(other_page_id=other[0], other_d=other[1])
        elif other and other[1] < NEAR and other[1] <= d - 0.015:
            row.update(label="elsewhere", other_page_id=other[0], other_d=other[1])
        else:
            row["label"] = "partly" if d < NEAR else "missing"
        out.append((*row.values(), lang, page_id, position))
    return out


def label(cur, con):
    cur.execute("SET mhnsw_ef_search = 80")
    cur.execute("SELECT DISTINCT fi_page_id FROM xlang_passage WHERE label IS NULL")
    todo = [p for (p,) in cur.fetchall()]
    start = time.time()
    for i, fid in enumerate(todo, 1):       # resumable: only unlabelled articles are picked up
        cur.executemany("UPDATE xlang_passage SET label=?, d=?, fi_passage_id=?, since=?, lost_from=?, lost_until=?, "
                        "other_page_id=?, other_d=? WHERE lang=? AND page_id=? AND position=?", label_article(cur, fid))
        con.commit()
        if i % 200 == 0 or i == len(todo):
            secs = time.time() - start
            print(f"{i}/{len(todo)} articles in {secs / 60:.1f} min, ETA {(len(todo) - i) * secs / i / 60:.1f} min", flush=True)


def verify(cur):
    cur.execute("SELECT COUNT(*), COUNT(label), COUNT(DISTINCT fi_page_id) FROM xlang_passage")
    n, labelled, arts = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM xlang_passage x LEFT JOIN xlang_vector v USING (text_hash) WHERE v.text_hash IS NULL")
    (no_vec,) = cur.fetchone()
    cur.execute("SELECT lang, label, COUNT(*) FROM xlang_passage GROUP BY lang, label")
    print(f"{n:,} paragraphs for {arts:,} Finnish articles, {labelled:,} labelled, {no_vec} without vector")
    print(cur.fetchall())
    assert n and labelled == n and no_vec == 0
    checks = [("en", "Winter War", "Shelling of Mainila and Soviet intentions", "elsewhere"),
              ("sv", "Vinterkriget", "Kvarkentrafiken", "missing"),
              ("en", "Winter War", "Foreign volunteers", "lost")]
    for lang, title, heading, want in checks:
        cur.execute("SELECT label FROM xlang_passage WHERE lang=? AND title=? AND heading=?", (lang, title, heading))
        got = [l for (l,) in cur.fetchall()]
        print(f"{lang} {title} / {heading}: {got} (expected {want})")
        assert want in got, (title, heading, got)
    print("ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", nargs="?", choices=["passages", "load", "label"])
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.step == "passages":
        return make_passages()
    con = connect()
    cur = con.cursor()
    if a.step == "load":
        load(cur, con)
    elif a.step == "label":
        label(cur, con)
    if a.verify or not a.step:
        verify(cur)


if __name__ == "__main__":
    main()
