"""Does search find the right article, and how fast? (2.B1, now A's)

    python eval/evaluate.py              # each list alone and fused (= our search), 37 questions
    python eval/evaluate.py --misses     # also list questions whose article wasn't in the top 5

Questions: eval/test-questions.tsv, from the RAG starter (a question in fi, sv or en and the Finnish
title of the article that answers it). A hit = that Finnish article among the top distinct articles.
The starter's own score (whole-article vectors, a hit in any language) was 76% top-5, 86% top-10.
"""
import argparse
import csv
import statistics
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import connect      # noqa: E402
from app.embed import embed     # noqa: E402
from app.search import rank     # noqa: E402

ARTICLE_SQL = """SELECT v.page_id FROM (SELECT page_id, VEC_DISTANCE_COSINE(embedding, ?) AS d
                 FROM article_vector WHERE lang = 'fi' ORDER BY d LIMIT 30) v ORDER BY v.d LIMIT 10"""


def passages(lists, names_only=True):
    return lambda vector, question: [r["page_id"] for r in rank(vector, question, 10, 1, lists,
                                                                names_only)]


def whole_articles(vector, question):
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(ARTICLE_SQL, (vector,))
        return [p for (p,) in cur.fetchall()]


def report(name, ranks, ms):
    hit = lambda k: sum(1 for r in ranks if r and r <= k) / len(ranks)     # noqa: E731
    mrr = sum(1 / r for r in ranks if r) / len(ranks)
    print(f"{name:28} hit@1 {hit(1):4.0%}  hit@5 {hit(5):4.0%}  hit@10 {hit(10):4.0%}  MRR {mrr:.2f}"
          f"  sql median {statistics.median(ms):.0f} ms, max {max(ms):.0f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--misses", action="store_true")
    args = ap.parse_args()
    questions = list(csv.DictReader(open(Path(__file__).parent / "test-questions.tsv", encoding="utf-8"),
                                    delimiter="\t"))
    with closing(connect()) as con:
        cur = con.cursor()
        for q in questions:
            cur.execute("SELECT page_id FROM article WHERE title = ?", (q["expected_fi_title"],))
            row = cur.fetchone()
            q["page_id"] = row[0] if row else None
    missing = [q["expected_fi_title"] for q in questions if not q["page_id"]]
    questions = [q for q in questions if q["page_id"]]
    t = time.perf_counter()
    vectors = embed([q["question"] for q in questions])
    print(f"{len(questions)} questions ({len(missing)} expected articles not in M: {missing}); "
          f"embedding {(time.perf_counter() - t) * 1000 / len(questions):.0f} ms per question")
    modes = (("whole articles (S vectors)", whole_articles),
             ("vec", passages(("vec",))), ("vec + ft (all words)", passages(("vec", "ft"), False)),
             ("vec + ft (names)", passages(("vec", "ft"))), ("vec + art", passages(("vec", "art"))),
             ("all, ft all words", passages(("vec", "ft", "art"), False)),
             ("passages (ours)", passages(("vec", "ft", "art"))))
    for name, fn in modes:
        ranks, ms = [], []
        for q, v in zip(questions, vectors):
            t = time.perf_counter()
            found = fn(v, q["question"])
            ms.append((time.perf_counter() - t) * 1000)
            q[name] = found.index(q["page_id"]) + 1 if q["page_id"] in found else None
            ranks.append(q[name])
        report(name, ranks, ms)
    if args.misses:
        for q in questions:
            if not q["passages (ours)"] or q["passages (ours)"] > 5:
                print(f"  miss ({q['lang']}): {q['question']}  -> want {q['expected_fi_title']}, "
                      f"rank {q['passages (ours)']}, whole-article rank {q['whole articles (S vectors)']}")


if __name__ == "__main__":
    main()
