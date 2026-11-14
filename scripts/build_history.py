"""Passage lifetimes over the full history (Phase 3, level B): every version of an article is cut
with the same rule as today's passages (build_passages.passages), and each distinct passage text
gets its lifetimes with Wikipedia's real edit times.

    python scripts/build_history.py 1256 1150 440    # these articles (pilot)
    python scripts/build_history.py --verify 1256    # lifetimes vs the versions, AS OF spot checks

Tables (dropped and rebuilt on each run):
  passage_text     one row per distinct text: page, first version, title, heading, text, seconds alive
  passage_history  system-versioned: one row per lifetime of a text in an article, so
                   FOR SYSTEM_TIME AS OF '2008-06-01' = the passages live on that date
Also writes data/history/passages.parquet: texts alive >= 1 day that have no vector yet, in the
format embed_passages.py / modal_embed.py read.
"""
import argparse
import sys
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq

from build_passages import REDIRECT, SCHEMA, passages
from common import ROOT, connect

DAY = 86400
TABLES = """
CREATE TABLE passage_text (
  text_hash   BINARY(32) NOT NULL PRIMARY KEY,
  page_id     INT UNSIGNED NOT NULL,
  rev_id      INT UNSIGNED NOT NULL,        -- first version that had this text
  title       VARCHAR(255) NOT NULL,
  heading     VARCHAR(255),
  text        TEXT NOT NULL,
  alive_secs  BIGINT UNSIGNED NOT NULL,     -- total time live, over all its lifetimes
  KEY (page_id)
) CHARACTER SET utf8mb4;
CREATE TABLE passage_history (
  page_id     INT UNSIGNED NOT NULL,
  text_hash   BINARY(32) NOT NULL,
  rev_id      INT UNSIGNED NOT NULL,        -- the version that started this lifetime
  row_start   TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
  row_end     TIMESTAMP(6) GENERATED ALWAYS AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end),
  PRIMARY KEY (page_id, text_hash),
  KEY (text_hash)
) WITH SYSTEM VERSIONING;
CREATE TABLE IF NOT EXISTS history_vector (  -- pilot: kept apart from passage_vector (B's search)
  text_hash   BINARY(32) NOT NULL PRIMARY KEY,
  embedding   VECTOR(1024) NOT NULL,
  VECTOR INDEX (embedding) M=16 DISTANCE=cosine
)"""


def lifetimes(versions, page_id):
    """versions: [(rev_id, title, text, start, end)] by time -> (texts, spans).
    texts: {hash: passage dict + alive_secs}; spans: [(hash, rev_id, start, end or None)]."""
    now = datetime.now(UTC).replace(tzinfo=None)
    texts, spans, open_ = {}, [], {}            # open_: hash -> (rev_id, start) of the live span
    for rev_id, title, text, start, end in versions:
        live = {} if REDIRECT.match(text) else {p["text_hash"]: p for p in passages(
            page_id, rev_id, title, text)}
        for h in list(open_):                    # texts that disappeared in this version
            if h not in live:
                spans.append((h, *open_.pop(h), start))
        for h, p in live.items():
            if h not in texts:
                texts[h] = {**p, "alive_secs": 0}
            if h not in open_:
                open_[h] = (rev_id, start)
            texts[h]["alive_secs"] += (min(end, now) - start).total_seconds()
    spans += [(h, rev, start, None) for h, (rev, start) in open_.items()]   # still live today
    return texts, spans


def build(con, cur, page_ids):
    for stmt in ("DROP TABLE IF EXISTS passage_text", "DROP TABLE IF EXISTS passage_history"):
        cur.execute(stmt)
    for stmt in TABLES.split(";"):
        cur.execute(stmt)
    cur.execute("SET time_zone = '+00:00'")
    cur.execute("SET system_versioning_insert_history = 1")
    cur.execute("SELECT text_hash FROM passage_vector")
    have = {h for (h,) in cur.fetchall()} | _hist_hashes(cur)
    to_embed = []
    for page_id in page_ids:
        cur.execute("SELECT rev_id, title, text, row_start, row_end FROM article FOR SYSTEM_TIME ALL "
                    "WHERE page_id = ? ORDER BY row_start", (page_id,))
        texts, spans = lifetimes(cur.fetchall(), page_id)
        cur.executemany("INSERT INTO passage_text VALUES (?,?,?,?,?,?,?)",
                        [(h, p["page_id"], p["rev_id"], p["title"], p["heading"], p["text"],
                          int(p["alive_secs"])) for h, p in texts.items()])
        closed = [(page_id, h, rev, start, end) for h, rev, start, end in spans if end]
        live = [(page_id, h, rev, start) for h, rev, start, end in spans if not end]
        if closed:
            cur.executemany("INSERT INTO passage_history (page_id, text_hash, rev_id, row_start, "
                            "row_end) VALUES (?,?,?,?,?)", closed)
        cur.executemany("INSERT INTO passage_history (page_id, text_hash, rev_id, row_start) "
                        "VALUES (?,?,?,?)", live)
        con.commit()
        to_embed += [p for h, p in texts.items() if p["alive_secs"] >= DAY and h not in have]
        print(f"{page_id}: {len(texts)} texts, {len(spans)} lifetimes "
              f"({sum(p['alive_secs'] >= DAY for p in texts.values())} alive >= 1 day)", flush=True)
    out = ROOT / "data" / "history" / "passages.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([{k: p[k] for k in SCHEMA.names} for p in to_embed],
                                        SCHEMA), out)
    print(f"{len(to_embed)} texts to embed -> {out}")


def _hist_hashes(cur):
    cur.execute("SHOW TABLES LIKE 'history_vector'")
    if not cur.fetchone():
        return set()
    cur.execute("SELECT text_hash FROM history_vector")
    return {h for (h,) in cur.fetchall()}


def verify(cur, page_id):
    """For 5 versions: the texts live AS OF just after the version was saved = that version's passages."""
    cur.execute("SELECT rev_id, title, text, row_start FROM article FOR SYSTEM_TIME ALL "
                "WHERE page_id = ? ORDER BY row_start", (page_id,))
    versions = cur.fetchall()
    bad = 0
    for i in sorted({0, len(versions) // 3, len(versions) // 2, len(versions) * 2 // 3,
                     len(versions) - 1}):
        rev_id, title, text, start = versions[i]
        want = set() if REDIRECT.match(text) else {p["text_hash"] for p in passages(
            page_id, rev_id, title, text)}
        cur.execute("SELECT text_hash FROM passage_history FOR SYSTEM_TIME AS OF TIMESTAMP ? "
                    "WHERE page_id = ?", (start.strftime("%Y-%m-%d %H:%M:%S.%f"), page_id))
        got = {h for (h,) in cur.fetchall()}
        bad += got != want
        print(f"  version {i + 1}/{len(versions)} ({start:%Y-%m-%d}): {len(got)} live, "
              f"{'ok' if got == want else f'MISMATCH (want {len(want)})'}")
    print("verify:", "all ok" if not bad else f"{bad} mismatches")
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page_ids", nargs="+", type=int)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    con = connect()
    cur = con.cursor()
    if args.verify:
        cur.execute("SET time_zone = '+00:00'")
        sys.exit(0 if all(verify(cur, p) for p in args.page_ids) else 1)
    build(con, cur, args.page_ids)


if __name__ == "__main__":
    main()
