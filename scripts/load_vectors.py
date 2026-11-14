"""Load passages.parquet into `passage` and passage_vectors.parquet into `passage_vector` (1.A8).

    python scripts/load_vectors.py                 # data/passages.parquet + data/passage_vectors.parquet
    python scripts/load_vectors.py data/pilot      # the pilot files (both people run this)
    python scripts/load_vectors.py --verify        # counts, every passage has a vector, recall@10
    python scripts/load_vectors.py data/history --history   # Phase 3: vectors only, into history_vector
    python scripts/load_vectors.py data/l --l               # dataset L shards -> l_passage, l_vector
    python scripts/load_vectors.py --l --verify             # counts + recall@10 for L

Each file loads on its own if the other is missing, so passages (and their FULLTEXT index) can go
in before the GPU run ends. `passage` is replaced each time (it is rebuilt from the file);
vectors are added with INSERT IGNORE, keyed by text hash, so they survive a passage rebuild.
"""
import argparse
import random
import sys
import time
from pathlib import Path

import mariadb
import pyarrow.parquet as pq

from common import ROOT, connect

BATCH = 500


def batches(cur, con, sql, rows, label):
    start = time.time()
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
        con.commit()
        done, secs = min(i + BATCH, len(rows)), time.time() - start
        if done % 10_000 < BATCH or done == len(rows):
            print(f"{label}: {done}/{len(rows)} in {secs / 60:.1f} min ({done / secs:.0f}/s), "
                  f"ETA {(len(rows) - done) / (done / secs) / 60:.1f} min", flush=True)


def load(cur, con, folder):
    passages, vectors = folder / "passages.parquet", folder / "passage_vectors.parquet"
    if passages.exists():
        cur.execute("TRUNCATE TABLE passage")
        rows = [(r["page_id"], r["rev_id"], r["title"], r["position"], r["heading"], r["text"],
                 r["text_hash"]) for r in pq.read_table(passages).to_pylist()]
        batches(cur, con, "INSERT INTO passage (page_id, rev_id, title, position, heading, text, "
                "text_hash) VALUES (?,?,?,?,?,?,?)", rows, "passages")
    if vectors.exists():
        t = pq.read_table(vectors)
        emb = t.column("embedding").combine_chunks().values.to_numpy().astype("<f4").reshape(-1, 1024)
        cur.execute("SELECT text_hash FROM passage_vector")
        have = {h for (h,) in cur.fetchall()}
        rows = [(h, m, e.tobytes()) for h, m, e in zip(t.column("text_hash").to_pylist(),
                                                       t.column("model").to_pylist(), emb)
                if h not in have]
        print(f"{len(have)} vectors already loaded, {len(rows)} new", flush=True)
        batches(cur, con, "INSERT IGNORE INTO passage_vector (text_hash, model, embedding) "
                "VALUES (?,?,?)", rows, "vectors")


def stream_vectors(cur, con, path, table, cols="text_hash, embedding"):
    """A vectors Parquet file -> table, in batches (millions of vectors never sit in memory)."""
    start, done = time.time(), 0
    names = [c.strip() for c in cols.split(",")]
    for batch in pq.ParquetFile(path).iter_batches(batch_size=BATCH, columns=names):
        emb = batch.column("embedding").values.to_numpy().astype("<f4").reshape(-1, 1024)
        rows = zip(*[batch.column(c).to_pylist() for c in names if c != "embedding"],
                   (e.tobytes() for e in emb))
        rows = list(rows)
        for attempt in range(10):     # parallel loaders deadlock or time out on the vector index lock
            try:
                cur.executemany(f"INSERT IGNORE INTO {table} ({cols}) "
                                f"VALUES ({','.join('?' * len(names))})", rows)
                con.commit()
                break
            except mariadb.OperationalError as e:
                con.rollback()
                if not ("Deadlock" in str(e) or "Lock wait timeout" in str(e)) or attempt == 9:
                    raise
        done += len(emb)
        if done % 20_000 < BATCH:
            secs = time.time() - start
            print(f"{table}: {done:,} in {secs / 60:.1f} min ({done / secs:.0f}/s)", flush=True)


def load_history(cur, con, path):
    """Historical vectors -> history_vector (never touches `passage`); then today's vectors are
    copied in too, so an AS OF search also finds texts that are still live."""
    stream_vectors(cur, con, path, "history_vector")
    cur.execute("INSERT IGNORE INTO history_vector SELECT text_hash, embedding FROM passage_vector")
    con.commit()
    cur.execute("SELECT COUNT(*) FROM history_vector")
    print(f"history_vector: {cur.fetchone()[0]:,} vectors")


def load_l(cur, con, folder):
    """Dataset L shards -> l_passage / l_vector: same definitions as passage / passage_vector
    (FULLTEXT, M=16 vector index), kept apart so the app's tables stay as they are."""
    cur.execute("CREATE TABLE IF NOT EXISTS l_passage LIKE passage")
    cur.execute("CREATE TABLE IF NOT EXISTS l_vector LIKE passage_vector")
    for path in sorted(folder.glob("passages-*.parquet")):
        rows = [(r["page_id"], r["rev_id"], r["title"], r["position"], r["heading"], r["text"],
                 r["text_hash"]) for r in pq.read_table(path).to_pylist()]
        batches(cur, con, "INSERT IGNORE INTO l_passage (page_id, rev_id, title, position, heading, "
                "text, text_hash) VALUES (?,?,?,?,?,?,?)", rows, path.name)
    for path in sorted(folder.glob("passage_vectors-*.parquet")):
        stream_vectors(cur, con, path, "l_vector", "text_hash, model, embedding")


def verify(cur, n=50, passage="passage", vector="passage_vector"):
    cur.execute(f"SELECT (SELECT COUNT(*) FROM {passage}), (SELECT COUNT(*) FROM {vector}), "
                f"(SELECT COUNT(*) FROM {passage} p LEFT JOIN {vector} v USING (text_hash) "
                f"WHERE v.text_hash IS NULL), (SELECT COUNT(DISTINCT model) FROM {vector})")
    passages, vectors, missing, models = cur.fetchone()
    print(f"passages {passages}, vectors {vectors}, passages without a vector {missing}, "
          f"models {models}")
    cur.execute("SET mhnsw_ef_search = 80")
    cur.execute(f"SELECT embedding FROM {vector} ORDER BY RAND() LIMIT ?", (n,))
    queries = [v for (v,) in cur.fetchall()]
    recalls, ms = [], []
    for v in queries:
        cur.execute(f"SELECT text_hash FROM {vector} IGNORE INDEX (embedding) "
                    "ORDER BY VEC_DISTANCE_COSINE(embedding, ?) LIMIT 10", (v,))
        exact = {h for (h,) in cur.fetchall()}
        t = time.perf_counter()
        cur.execute(f"SELECT text_hash FROM {vector} "
                    "ORDER BY VEC_DISTANCE_COSINE(embedding, ?) LIMIT 10", (v,))
        found = {h for (h,) in cur.fetchall()}
        ms.append((time.perf_counter() - t) * 1000)
        recalls.append(len(found & exact) / len(exact))
    recall = sum(recalls) / len(recalls)
    ms.sort()
    print(f"recall@10 {recall:.1%} (worst {min(recalls):.0%}) over {len(queries)} stored vectors, "
          f"ef_search 80; search median {ms[len(ms) // 2]:.1f} ms")
    ok = missing == 0 and models <= 1 and recall >= 0.95
    print("verify:", "all ok" if ok else "FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "data"))
    ap.add_argument("--verify", action="store_true", help="check what is loaded and exit")
    ap.add_argument("--history", action="store_true",
                    help="load FOLDER/passage_vectors.parquet into history_vector only (Phase 3)")
    ap.add_argument("--l", action="store_true",
                    help="dataset L: FOLDER/passages-*.parquet + passage_vectors-*.parquet -> l_passage, l_vector")
    args = ap.parse_args()
    con = connect()
    cur = con.cursor()
    tables = ("l_passage", "l_vector") if args.l else ("passage", "passage_vector")
    if args.verify:
        sys.exit(0 if verify(cur, 50, *tables) else 1)
    if args.history:
        return load_history(cur, con, Path(args.folder) / "passage_vectors.parquet")
    if args.l:
        load_l(cur, con, Path(args.folder))
        return verify(cur, 50, *tables)
    load(cur, con, Path(args.folder))
    verify(cur)


if __name__ == "__main__":
    main()
