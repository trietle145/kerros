# Architecture: core cited Q&A

2026-11-13. **Draft:** the retrieval approach (below) waits on the team's pick; the rest follows
from decisions already made (see `plan.md`).

## What the core does

A person asks a question about Finnish history in Finnish, Swedish or English. The app finds the
Wikipedia paragraphs that answer it and writes a short answer where every sentence cites its
paragraph by number. Each citation links to the exact Wikipedia revision the text came from. A
second mode summarises one article with the same citations.

This is the RAG track's core: retrieval from MariaDB, an answer with sources, a summary.

## Approaches for retrieval

| | How it finds paragraphs | Good at | Weak at |
| --- | --- | --- | --- |
| A. Vector only | Nearest paragraph vectors to the question vector | Meaning, cross-language | Exact names, years, rare words |
| **B. Hybrid (recommended)** | Paragraph vectors and MariaDB `FULLTEXT` in one SQL statement, merged by rank (reciprocal rank fusion) | Meaning *and* exact names and years, e.g. "president 1956–1982" | Finnish word endings may weaken the keyword half (to test) |
| C. Two-stage | Shipped article vectors pick the top articles, then paragraph vectors within them | Cheap, uses the S vectors | Misses facts in articles the first stage skipped |

**Recommendation: B, built as A first.** B is A plus one more query, so A works on day one and B
follows. B is also a strong "MariaDB feature used well" point, and MariaDB documents the pattern:
[Optimizing Hybrid Search Query with Reciprocal Rank Fusion](https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf).
C stays useful later for cross-language features.

## Data flow

```
OFFLINE
  dataset M (parquet) --load_m.py--> article            versioned, every revision
                                       |
                                       | build_passages.py: newest revision per article,
                                       | wikitext -> plain text, split into paragraphs
                                       v
                                     passage            current paragraphs + where they came from
                                       |
                                       | distinct texts -> GPU (Colab T4), bge-m3
                                       v
                                     passage_vector     one vector per distinct paragraph text
  dataset S (parquet) --load_s.py--> article_vector     shipped whole-article vectors (fi, sv, en)

ASK
  question -> bge-m3 (same model) -> question vector
           -> one SQL query: vector top-k (+ FULLTEXT top-k, fused) -> top paragraphs
           -> cap at 2 paragraphs per article, keep ~8
           -> cloud model: "answer in the question's language, cite [n] after every sentence"
           -> check every [n] exists; flag sentences with no citation
           -> page: answer, numbered sources, link to fi.wikipedia.org/?oldid=<rev_id>, the SQL used
```

## Tables

```sql
-- Loading now (starter schema + two columns). Every saved version, real timestamps.
article (page_id PK, title, rev_id, parent_id, user, anonymous, comment, minor, sha1, len,
         text MEDIUMTEXT COMPRESSED, row_start, row_end)  WITH SYSTEM VERSIONING,
         partitioned by year

-- Current paragraphs of each article. Plain table, rebuilt from the newest revision.
passage (
  passage_id  INT AUTO_INCREMENT PRIMARY KEY,
  page_id     INT UNSIGNED NOT NULL,
  rev_id      INT UNSIGNED NOT NULL,      -- the revision the text came from: citations link here
  position    SMALLINT NOT NULL,          -- order within the article
  heading     VARCHAR(255),               -- section heading, for context and links
  text        TEXT NOT NULL,              -- plain text shown to readers
  text_hash   BINARY(32) NOT NULL,        -- SHA-256 of the text: joins to its vector
  KEY (page_id, position), KEY (text_hash),
  FULLTEXT (text)                         -- the keyword half of hybrid search
)

-- One vector per distinct paragraph text, not per position.
passage_vector (
  text_hash   BINARY(32) PRIMARY KEY,
  embedding   VECTOR(1024) NOT NULL,
  VECTOR INDEX (embedding) M=16 DISTANCE=cosine
)

-- Shipped from dataset S.
article_vector (lang CHAR(2), page_id INT UNSIGNED, embedding VECTOR(1024) NOT NULL,
                PRIMARY KEY (lang, page_id), VECTOR INDEX (embedding) M=16 DISTANCE=cosine)
```

## Three choices that keep the feature ideas open

1. **Vectors are keyed by text hash, not by paragraph position.** The same text is embedded once,
   however many articles or revisions contain it. Old paragraph versions can get vectors later by
   embedding only the texts not seen yet, which is what "ask the past" and "meaning drift" need.
2. **Every paragraph keeps the revision it came from.** Citations point at an exact revision, and
   the history features can join any paragraph back to the versioned `article` table.
3. **The full history loads now, even though the core only reads the newest revision.** The
   edit-war, vandalism and "what changed" ideas all start from that table, and the load takes all
   night.

Nothing in `ideas.md` needs the core to change; those ideas add tables (revert events, paragraph
lifetimes) next to these.

## Code layout

| Path | Does |
| --- | --- |
| `scripts/load_m.py` | Parquet → versioned `article` table (real timestamps, resumable) |
| `scripts/load_s.py` | Shipped S vectors → `article_vector` |
| `scripts/build_passages.py` | Newest revision → cleaned paragraphs → `passage`; writes the distinct texts to embed |
| `notebooks/embed_passages.ipynb` | Colab: bge-m3 over the distinct texts → parquet of `text_hash, embedding` |
| `scripts/load_vectors.py` | That parquet → `passage_vector`, then builds the vector index |
| `app/db.py` | Connection and the retrieval queries |
| `app/embed.py` | Question → vector (bge-m3, same model and settings as the notebook) |
| `app/llm.py` | Answer and summary prompts; provider read from a setting |
| `app/main.py` | Flask: the page, `/ask`, `/summarise/<page_id>`, and a JSON API the extension or MCP can use later |
| `eval/evaluate.py` | The 37 test questions: right article in the top 5 and top 10, against the starter's 76% / 86% |

## Settings decided for now

- Paragraph = one paragraph, short ones merged up to ~300 words; the title and section heading are
  prepended only when embedding, not in the stored text.
- `SET mhnsw_ef_search = 80`; re-measure recall once all paragraph vectors are in.
- Vector search goes in a subquery and is joined afterwards, so the index is used.
- Top 8 paragraphs, at most 2 per article, go to the model.
- The answer is in the question's language; the sources stay in their own language.

## Open

- Which retrieval approach (B recommended).
- Which cloud model, and which credits pay for it.
- How the Colab vectors and the question vectors are checked to match: compare a handful of
  question vectors made both ways before relying on it.
- How well `FULLTEXT` handles Finnish word endings, and whether the starter's wikitext cleaner is
  good enough for paragraphs.
