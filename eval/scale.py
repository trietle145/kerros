"""Does the vector search hold up as the data grows? From dataset S's 30k article vectors to L's
1.5M passages, per table: rows, recall@10 of the vector index against an exact scan, and search
time with and without the index. Queries: the 37 eval questions.

    python eval/scale.py     # on the database machine, or the times include the network

The question vectors are cached in data/question_vectors.bin (37 x 4 KB), made on the first run on
a machine with the model, so the database server needs no model and no extra memory.
"""
import csv
import statistics
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect     # noqa: E402

CACHE = ROOT / "data" / "question_vectors.bin"
TABLES = (("S  whole articles (fi, sv, en)", "article_vector", "lang, page_id"),
          ("M  passages, today", "passage_vector", "text_hash"),
          ("M  passages, every version", "history_vector", "text_hash"),
          ("L  passages, all fi articles", "l_vector", "text_hash"))
SEARCH = "SELECT {key} FROM {table} {hint} ORDER BY VEC_DISTANCE_COSINE(embedding, ?) LIMIT 10"


def questions():
    if not CACHE.exists():
        from app.embed import embed
        with open(ROOT / "eval" / "test-questions.tsv", encoding="utf-8") as f:
            CACHE.write_bytes(b"".join(embed(r["question"] for r in csv.DictReader(f, delimiter="\t"))))
    data = CACHE.read_bytes()
    return [data[i:i + 4096] for i in range(0, len(data), 4096)]


def timed(cur, sql, v):
    t = time.perf_counter()
    cur.execute(sql, (v,))
    rows = set(cur.fetchall())
    return rows, (time.perf_counter() - t) * 1000


def main():
    vectors = questions()
    print(f"{len(vectors)} questions, top 10, mhnsw_ef_search 80\n")
    print(f"{'table':32} {'rows':>10}  recall@10  index ms (median / p95)  exact scan ms  speed-up")
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute("SET mhnsw_ef_search = 80")
        for name, table, key in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            rows = cur.fetchone()[0]
            if not rows:
                print(f"{name:32} {'empty':>10}")
                continue
            ann, exact = SEARCH.format(key=key, table=table, hint=""), \
                SEARCH.format(key=key, table=table, hint="IGNORE INDEX (embedding)")
            timed(cur, ann, vectors[0])                       # warm the index cache once
            recall, fast, slow = [], [], []
            for v in vectors:
                found, ms = timed(cur, ann, v)
                truth, ms_exact = timed(cur, exact, v)
                recall.append(len(found & truth) / len(truth))
                fast.append(ms)
                slow.append(ms_exact)
            p95 = sorted(fast)[int(len(fast) * 0.95)]
            med, med_exact = statistics.median(fast), statistics.median(slow)
            print(f"{name:32} {rows:>10,}  {statistics.mean(recall):8.1%}   {med:7.1f} / {p95:6.1f}"
                  f"          {med_exact:9.0f}   {med_exact / med:6.0f}x")


if __name__ == "__main__":
    main()
