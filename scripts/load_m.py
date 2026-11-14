"""Load every version of every article in dataset M into the system-versioned `article` table,
with Wikipedia's real edit times.

    python scripts/load_m.py --limit 20      # smoke test: 20 articles
    python scripts/load_m.py                 # everything (log: data/load_m.log if redirected)
    python scripts/load_m.py --verify 20     # compare 20 loaded articles with the Parquet files

Safe to stop and run again: articles already in the table are skipped. Each article is written
in one transaction, so a stopped run never leaves half an article behind.

How a version gets its time (same method as mariadb-system-versioning-wikipedia/load.py): with
SET system_versioning_insert_history = 1, MariaDB accepts row_start and row_end from us. Each
version starts when it was saved on Wikipedia and ends when the next one was saved; the newest
version gets no row_end and stays current.

Layout of M that this relies on (checked 2026-11-14): each article's versions are contiguous,
in one file, sorted by time; 20 pairs of versions share a timestamp.
"""
import argparse
import glob
import random
import sys
import time
from datetime import timedelta

import pyarrow as pa
import pyarrow.parquet as pq

from common import ROOT, connect

COLUMNS = ["page_id", "title", "rev_id", "parent_id", "user", "anonymous", "comment", "minor",
           "sha1", "bytes", "text", "timestamp"]
BATCH_BYTES = 8_000_000      # MariaDB's default packet limit is 16 MB, so send rows by size
INSERT = """INSERT INTO article (page_id, title, rev_id, parent_id, user, anonymous, comment, minor,
             sha1, len, text, row_start{end}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?{q})"""


def read_group(pf, i, columns=COLUMNS):
    t = pf.read_row_group(i, columns=columns)
    if "timestamp" in columns:   # UTC; drop the zone so Python needs no time-zone database
        t = t.set_column(t.schema.get_field_index("timestamp"), "timestamp",
                         t.column("timestamp").cast(pa.timestamp("ms")))
    return t.to_pylist()


def articles(files, skip):
    """Yield (page_id, versions) per article, skipping row groups whose articles are all in skip."""
    page_id, versions = None, []
    for path in files:
        pf = pq.ParquetFile(path)
        for i in range(pf.num_row_groups):
            ids = set(pf.read_row_group(i, columns=["page_id"]).column("page_id").to_pylist())
            if ids <= skip and page_id not in ids:
                continue
            for row in read_group(pf, i):
                if row["page_id"] in skip:
                    continue
                if row["page_id"] != page_id:
                    if versions:
                        yield page_id, versions
                    page_id, versions = row["page_id"], []
                versions.append(row)
    if versions:
        yield page_id, versions


def save(con, cur, versions):
    """Write one article: earlier versions as history rows, the newest as the current row."""
    versions.sort(key=lambda v: (v["timestamp"], v["rev_id"]))
    for prev, v in zip(versions, versions[1:]):          # same timestamp: keep order, 1 µs apart
        if v["timestamp"] <= prev["timestamp"]:
            v["timestamp"] = prev["timestamp"] + timedelta(microseconds=1)
    rows = [(v["page_id"], v["title"], v["rev_id"], v["parent_id"], v["user"],
             bool(v["anonymous"]), v["comment"], bool(v["minor"]), v["sha1"], v["bytes"],
             v["text"] or "", v["timestamp"]) for v in versions]
    batch, size = [], 0
    for row, nxt in zip(rows, versions[1:]):             # history: ends when the next one starts
        if batch and size + (row[9] or 0) > BATCH_BYTES:
            cur.executemany(INSERT.format(end=", row_end", q=",?"), batch)
            batch, size = [], 0
        batch.append(row + (nxt["timestamp"],))
        size += row[9] or 0
    if batch:
        cur.executemany(INSERT.format(end=", row_end", q=",?"), batch)
    cur.execute(INSERT.format(end="", q=""), rows[-1])   # current: no row_end
    con.commit()


def verify(cur, files, n):
    """Check n loaded articles: version count, and AS OF a version's start returns that version."""
    cur.execute("SELECT DISTINCT page_id FROM article")
    loaded = [p for (p,) in cur.fetchall()]
    want = set(random.sample(loaded, min(n, len(loaded))))
    bad = 0
    for path in files:
        pf = pq.ParquetFile(path)
        for i in range(pf.num_row_groups):
            ids = set(pf.read_row_group(i, columns=["page_id"]).column("page_id").to_pylist())
            for page_id in ids & want:
                rows = [r for r in read_group(pf, i, ["page_id", "rev_id", "timestamp"])
                        if r["page_id"] == page_id]
                cur.execute("SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE page_id = ?",
                            (page_id,))
                (count,) = cur.fetchone()
                # A whole second after a version was saved, that version (or a later one in the
                # same second) is live. Pick a version with no other edit in that second.
                rows.sort(key=lambda r: r["timestamp"])
                ok_pick = [r for k, r in enumerate(rows) if k + 1 == len(rows)
                           or rows[k + 1]["timestamp"] - r["timestamp"] > timedelta(seconds=1)]
                pick = random.choice(ok_pick)
                cur.execute("SELECT rev_id FROM article FOR SYSTEM_TIME AS OF ? WHERE page_id = ?",
                            (pick["timestamp"] + timedelta(milliseconds=500), page_id))
                (rev,) = cur.fetchone()
                status = "ok" if count == len(rows) and rev == pick["rev_id"] else "MISMATCH"
                bad += status != "ok"
                print(f"  {page_id}: {count}/{len(rows)} versions, as of {pick['timestamp']} -> "
                      f"rev {rev} (expected {pick['rev_id']}) {status}")
                want.discard(page_id)       # an article split over two row groups: check once
    print("verify:", "all ok" if not bad else f"{bad} mismatches")
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="load at most this many new articles")
    ap.add_argument("--verify", type=int, metavar="N", help="check N loaded articles and exit")
    ap.add_argument("files", nargs="*", help="Parquet files (default: data/m/*.parquet)")
    args = ap.parse_args()
    files = args.files or sorted(glob.glob(str(ROOT / "data" / "m" / "*.parquet")))

    con = connect()
    cur = con.cursor()
    cur.execute("SET time_zone = '+00:00'")              # Wikipedia's times are UTC
    if args.verify:
        sys.exit(0 if verify(cur, files, args.verify) else 1)
    cur.execute("SET system_versioning_insert_history = 1")

    cur.execute("SELECT DISTINCT page_id FROM article FOR SYSTEM_TIME ALL")
    loaded = {p for (p,) in cur.fetchall()}
    total_rows = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
    print(f"{len(files)} files, {total_rows} versions; {len(loaded)} articles already loaded",
          flush=True)

    start = time.time()
    pages = rows = mb = 0
    for page_id, versions in articles(files, loaded):
        save(con, cur, versions)
        pages += 1
        rows += len(versions)
        mb += sum(v["bytes"] or 0 for v in versions) / 1e6
        if pages % 100 == 0 or pages == args.limit or len(versions) > 2000:
            secs = time.time() - start
            print(f"{pages} articles, {rows} versions, {mb:.0f} MB in {secs / 60:.1f} min "
                  f"({rows / secs:.0f} versions/s, {mb / secs:.1f} MB/s); "
                  f"last: {versions[-1]['title']} ({len(versions)})", flush=True)
        if args.limit and pages >= args.limit:
            break

    cur.execute("SELECT COUNT(DISTINCT page_id), COUNT(*) FROM article FOR SYSTEM_TIME ALL")
    print("in the table: %d articles, %d versions" % cur.fetchone(), flush=True)
    con.close()


if __name__ == "__main__":
    main()
