"""Retrieval (owner: A, backend): question -> the passages that answer it.

Vector search now; the FULLTEXT half and rank fusion (hybrid, docs/architecture.md) come next.
The vector search stays in a subquery and is joined to `passage` afterwards, or MariaDB doesn't
use the vector index.
"""
from contextlib import closing

from app.db import connect
from app.embed import embed

CANDIDATES = 50          # nearest passages fetched before the per-article cap
VECTOR_SQL = """
SELECT p.passage_id, p.page_id, p.rev_id, p.title, p.heading, p.text, v.d
FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) AS d
      FROM passage_vector ORDER BY d LIMIT {n}) v
JOIN passage p USING (text_hash)
ORDER BY v.d"""


def rank(vector, k=8, per_article=2):
    """Top k passages for a query vector, at most per_article from one article (None = no cap).
    ponytail: per_article=2 is a starting value, not measured; the eval decides (docs/architecture.md)."""
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(VECTOR_SQL.format(n=CANDIDATES), (vector,))
        rows = cur.fetchall()
    out, seen = [], {}
    for passage_id, page_id, rev_id, title, heading, text, d in rows:
        if per_article and seen.get(page_id, 0) >= per_article:
            continue
        seen[page_id] = seen.get(page_id, 0) + 1
        out.append({"passage_id": passage_id, "page_id": page_id, "rev_id": rev_id, "title": title,
                    "heading": heading, "text": text, "score": round(1 - d, 4)})
        if len(out) == k:
            break
    return out


def search(question, k=8, as_of=None, per_article=2):
    """The contract in tasks/plan.md. as_of is not used here: dated questions go to app.timeqa."""
    return rank(embed([question])[0], k, per_article)
