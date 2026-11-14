"""Load dataset S's shipped bge-m3 article vectors (fi, sv, en) into `article_vector`.
Based on mariadb-vector-wikipedia-rag/load.py --vectors.

    python scripts/load_s.py                 # load (resumable; log: data/load_s.log if redirected)
    python scripts/load_s.py --verify        # counts per language + nearest articles to Talvisota

The vector index is built row by row as rows go in, so the rate printed is the real one.
"""
import argparse
import struct
import sys
import time

import pyarrow.parquet as pq

from common import ROOT, connect

LANGS = ("fi", "sv", "en")
BATCH = 500
S = ROOT / "data" / "s"


def vectors(lang):
    return pq.read_table(S / f"vectors-bge-m3-{lang}.parquet").to_pylist()


def titles():
    out = {}
    for lang in LANGS:
        for r in pq.read_table(S / f"articles-{lang}.parquet", columns=["page_id", "title"]).to_pylist():
            out[lang, r["page_id"]] = r["title"]
    return out


def load(con, cur):
    cur.execute("SELECT lang, page_id FROM article_vector")
    loaded = set(cur.fetchall())
    rows = [r for lang in LANGS for r in vectors(lang) if (r["lang"], r["page_id"]) not in loaded]
    print(f"{len(loaded)} vectors already loaded, {len(rows)} to load", flush=True)
    start = time.time()
    for i in range(0, len(rows), BATCH):
        # MariaDB takes a VECTOR as raw bytes: 1024 little-endian float32 numbers.
        cur.executemany("INSERT IGNORE INTO article_vector (lang, page_id, model, truncated, embedding)"
                        " VALUES (?,?,?,?,?)",
                        [(r["lang"], r["page_id"], r["model"], r["truncated"],
                          struct.pack("<1024f", *r["embedding"])) for r in rows[i:i + BATCH]])
        con.commit()
        done, secs = min(i + BATCH, len(rows)), time.time() - start
        print(f"{done}/{len(rows)} vectors in {secs / 60:.1f} min ({done / secs:.0f}/s), "
              f"ETA {(len(rows) - done) / (done / secs) / 60:.1f} min; last: {rows[done - 1]['lang']}",
              flush=True)


def verify(cur):
    want = {lang: pq.ParquetFile(S / f"vectors-bge-m3-{lang}.parquet").metadata.num_rows for lang in LANGS}
    cur.execute("SELECT lang, COUNT(*) FROM article_vector GROUP BY lang")
    have = dict(cur.fetchall())
    ok = all(have.get(lang) == n for lang, n in want.items())
    print(f"counts: {have} (expected {want}) {'ok' if ok else 'MISMATCH'}")

    name = titles()
    page_id = next(p for (lang, p), t in name.items() if lang == "fi" and t == "Talvisota")
    cur.execute("SET mhnsw_ef_search = 80")
    cur.execute("SELECT embedding FROM article_vector WHERE lang = 'fi' AND page_id = ?", (page_id,))
    (vec,) = cur.fetchone()
    t = time.time()
    cur.execute("SELECT lang, page_id, VEC_DISTANCE_COSINE(embedding, ?) AS d FROM article_vector "
                "ORDER BY d LIMIT 8", (vec,))
    hits = cur.fetchall()
    print(f"nearest to Talvisota ({(time.time() - t) * 1000:.0f} ms):")
    for lang, p, d in hits:
        print(f"  {d:.3f} {lang} {name.get((lang, p))}")
    ok = ok and hits[0][:2] == ("fi", page_id)
    print("verify:", "all ok" if ok else "FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="check the loaded vectors and exit")
    args = ap.parse_args()
    con = connect()
    cur = con.cursor()
    if args.verify:
        sys.exit(0 if verify(cur) else 1)
    load(con, cur)
    cur.execute("SELECT lang, COUNT(*) FROM article_vector GROUP BY lang")
    print("in the table:", dict(cur.fetchall()), flush=True)


if __name__ == "__main__":
    main()
