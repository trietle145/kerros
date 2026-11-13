# Architecture: cited Q&A and time views

2026-11-13. Retrieval approach decided: **hybrid (B)**. The rest follows from decisions already
made (see `plan.md`). The time side was decided the same day (see "The time side"). Feature
ideas stay an open list in `ideas.md`.

## What the core does

A person asks a question about Finnish history in Finnish, Swedish or English. The app finds the
Wikipedia paragraphs that answer it and writes a short answer where every sentence cites its
paragraph by number. Each citation links to the exact Wikipedia revision the text came from. A
second mode summarises one article with the same citations.

This is the RAG track's core: retrieval from MariaDB, an answer with sources, a summary.

Next to it sit two time views from the SVT track: read any article as it stood on a chosen date,
and see an article's edit timeline with its reverts. The two sides meet on the source card under
an answer: each cited source has a History button.

## Approaches for retrieval

| | How it finds paragraphs | Good at | Weak at |
| --- | --- | --- | --- |
| A. Vector only | Nearest paragraph vectors to the question vector | Meaning, cross-language | Exact names, years, rare words |
| **B. Hybrid (chosen)** | Paragraph vectors and MariaDB `FULLTEXT` in one SQL statement, merged by rank (reciprocal rank fusion) | Meaning *and* exact names and years, e.g. "president 1956–1982" | Finnish word endings may weaken the keyword half (to test) |
| C. Two-stage | Shipped article vectors pick the top articles, then paragraph vectors within them | Cheap, uses the S vectors | Misses facts in articles the first stage skipped |

**Decision: B, built as A first.** B is A plus one more query, so A works on day one and B
follows. B is also a strong "MariaDB feature used well" point, and MariaDB documents the pattern:
[Optimizing Hybrid Search Query with Reciprocal Rank Fusion](https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf).
C stays useful later for cross-language features.

## System overview

```mermaid
flowchart LR
  subgraph offline["Offline, run once"]
    M[("Dataset M<br/>862k versions")] -->|load_m.py| A["article<br/>system-versioned"]
    A -->|"newest revision:<br/>clean + split"| P["passage<br/>current paragraphs"]
    P -->|distinct texts| E["bge-m3<br/>on a GPU"]
    E --> PV["passage_vector"]
    S[("Dataset S<br/>shipped vectors")] -->|load_s.py| AV["article_vector"]
    A -->|"build_reverts.sql,<br/>once after loading"| RV["revert_event"]
  end
  subgraph online["Online, per request"]
    Q["Question"] --> QE["bge-m3"]
    QE --> R{{"Hybrid SQL:<br/>vector + FULLTEXT, fused by rank"}}
    R --> L["Cloud model:<br/>answer with [n]"]
    L --> UI["Web page"]
    T["Time views:<br/>as-of reader, edit timeline"] --> UI
    UI -.->|"History button<br/>on a source"| T
  end
  PV --> R
  P --> R
  A -->|FOR SYSTEM_TIME| T
  RV --> T
```

Everything in the offline box runs once (or overnight); everything in the online box runs per
request. The two tracks meet in one place: a cited paragraph (`passage`) carries the
`page_id` and `rev_id` that the time views read from `article`.

## Tables and how they join

```mermaid
erDiagram
  article ||--o{ passage : "newest revision is cut into"
  passage }o--|| passage_vector : "text_hash"
  article ||--o| article_vector : "page_id (Finnish)"
  article ||--o{ revert_event : "found once from sha1"
  article {
    int page_id PK
    int rev_id
    int parent_id
    varchar user
    bool anonymous
    text comment
    varchar sha1
    mediumtext text
    timestamp row_start "hidden, real edit time"
    timestamp row_end "hidden, next edit time"
  }
  passage {
    int passage_id PK
    int page_id
    int rev_id "citation target"
    smallint position
    varchar heading
    text text "FULLTEXT"
    binary text_hash
  }
  passage_vector {
    binary text_hash PK
    varchar model
    vector embedding "VECTOR INDEX M=16 cosine"
  }
  article_vector {
    char lang PK
    int page_id PK
    vector embedding "VECTOR INDEX M=16 cosine"
  }
  revert_event {
    int page_id PK
    int rev_id PK "the reverting version"
    datetime reverted_at
    varchar user
    bool anonymous
    int restored_rev_id "the earlier version brought back"
    datetime undone_since "when the undone text first appeared"
    int undone_edits
    varchar undone_user
    bool undone_anonymous
  }
```

Full definitions: `schema.sql`.

## Asking a question

```mermaid
sequenceDiagram
  actor U as Reader
  participant W as Flask app
  participant E as bge-m3
  participant D as MariaDB
  participant L as Cloud model
  U->>W: question
  W->>E: embed the question
  E-->>W: vector (1024)
  W->>D: one query: vector top-k + FULLTEXT top-k, fused by rank
  D-->>W: top paragraphs with page_id, rev_id, heading
  W->>W: keep ~8, at most 2 per article
  W->>L: question + numbered paragraphs
  L-->>W: answer, [n] after every sentence
  W->>W: check every [n] exists, flag uncited sentences
  W-->>U: answer + sources linked to ?oldid=rev_id
```

The summary mode is the same flow with one article's paragraphs instead of a search.

## The time side

Decided: two time views are part of the core, reverts are found once and stored, the Q&A answers
from the newest text unless a date is given, and the two sides meet on the source card.

```mermaid
flowchart TD
  ANS["Answer with numbered sources"] --> CARD["Source card:<br/>title, section, '412 edits, 9 reverts this year'"]
  CARD -->|History button| TL["Edit timeline:<br/>edits per month, reverts marked"]
  TL -->|pick a month| ASOF["Article as of that date"]
  ASOF -->|"compare with today"| DIFF["What changed"]
  TL -.-> Q1[("article<br/>FOR SYSTEM_TIME ALL")]
  TL -.-> Q2[("revert_event")]
  ASOF -.-> Q3[("article<br/>FOR SYSTEM_TIME AS OF")]
  CARD -.-> Q2
```

**The two views, one query each**

```sql
-- Read an article as it stood on a date.
SELECT title, rev_id, text FROM article FOR SYSTEM_TIME AS OF '2015-06-01' WHERE page_id = ?;

-- Edit timeline: edits per month (reverts per month come from revert_event the same way).
SELECT DATE_FORMAT(row_start, '%Y-%m') AS month, COUNT(*) AS edits
FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? GROUP BY month;
```

Both depend only on dataset M being loaded into `article`. Nothing else is needed.

**Reverts are found once.** A revert is a version whose text (same `sha1`) already existed earlier
in the same article, with other versions in between. After the load, one statement fills
`revert_event` (sketch, not yet run):

```sql
INSERT INTO revert_event
SELECT x.page_id, x.rev_id, x.row_start, x.user, x.anonymous,
       x.prev_rev_id, x.prev_end, x.rn - x.prev_rn - 1,
       u.user, u.anonymous
FROM (
  SELECT v.*, LAG(rev_id)  OVER w AS prev_rev_id,   -- the earlier version with the same text
              LAG(row_end) OVER w AS prev_end,      -- = when the first undone edit was saved
              LAG(rn)      OVER w AS prev_rn
  FROM (SELECT page_id, rev_id, user, anonymous, sha1, row_start, row_end,
               ROW_NUMBER() OVER (PARTITION BY page_id ORDER BY row_start) AS rn
        FROM article FOR SYSTEM_TIME ALL) v
  WINDOW w AS (PARTITION BY page_id, sha1 ORDER BY row_start)
) x
JOIN article FOR SYSTEM_TIME ALL u            -- the first undone edit: who was reverted
  ON u.page_id = x.page_id AND u.row_start = x.prev_end
WHERE x.rn - x.prev_rn > 1;                   -- something in between was undone
```

Each row answers: who undid whom, when, how many edits were undone, and how long the undone text
stayed visible (`reverted_at - undone_since`). The edit-war and vandalism ideas in `ideas.md`
become plain queries on this table. Known limit: an exact-text match misses partial reverts and
rewordings.

**Time in the Q&A.** Questions are answered from the newest text. The ask endpoint accepts an
optional `as_of` date from the start and ignores it for now, so "ask the past" can be added later
without changing the interface. It stays in `ideas.md`.

**The source card** is a UI choice with no storage of its own: its numbers come from a count on
`article` and on `revert_event` for that `page_id`.

**Partitions.** The history table keeps the starter's yearly partitions. They cost about 25% more
disk and do not speed up queries at this size, but they show time partitioning in use and let old
years be archived.

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
| `scripts/build_reverts.sql` | Fills `revert_event` from `article`, once after loading |
| `scripts/build_passages.py` | Newest revision → cleaned paragraphs → `passage`; writes the distinct texts to embed |
| `scripts/embed_passages.py` | bge-m3 over the distinct texts → parquet of `text_hash, embedding`; runs wherever a GPU is |
| `scripts/load_vectors.py` | That parquet → `passage_vector`, then builds the vector index |
| `app/db.py` | Connection and the retrieval queries |
| `app/embed.py` | Question → vector (bge-m3, same model and settings as the notebook) |
| `app/llm.py` | Answer and summary prompts; provider read from a setting |
| `app/main.py` | Flask: the page, `/ask` (optional `as_of`, unused for now), `/summarise/<page_id>`, `/article/<page_id>?as_of=`, `/article/<page_id>/timeline`, and a JSON API the extension or MCP can use later |
| `schema.sql` | All four tables; runs on any MariaDB 11.7+ |
| `eval/evaluate.py` | Retrieval and citation checks (below) |

## Evaluation

The starter's 37 test questions only check that the right *article* is found. Our claim is about
paragraphs and citations, so we measure three things:

1. **Article found:** the 37 questions, right article in the top 5 / top 10, against the starter's
   76% / 86%.
2. **Paragraph found:** 20 to 30 of our own questions, each with the paragraph that answers it,
   written by hand from a few hero articles. Right paragraph in the top 5 / top 10.
3. **Citations faithful:** for each answer sentence, does the paragraph it cites actually say it?
   Checked by hand on the same questions at first; a model-graded check later if time allows.

## Runtime is set up per machine

Nothing in the schema or the code depends on where things run. Each machine sets its own `.env`:
database host and port (Docker, portable MariaDB or a cloud database), where bge-m3 runs for
questions (local Ollama or a hosted endpoint), and the cloud model for answers. The one rule:
paragraphs and questions are embedded with the same model and settings.

## First hour: checks before building on them

- A MariaDB 11.7+ is running somewhere with ~15 GB free.
- `schema.sql` runs, and a vector search and a `FULLTEXT` search each return rows on a handful of
  test paragraphs.
- Five questions embedded on the GPU machine and on the query machine give the same vectors
  (cosine similarity above 0.99).
- The starter's wikitext cleaner gives readable paragraphs on 3 hero articles.
- Finnish `FULLTEXT`: does a search for "Kekkonen" find "Kekkosen"? If not, the vector half
  carries word endings and the keyword half carries exact names and years.

## Settings decided for now

- Paragraph = one paragraph, short ones merged up to ~300 words; the title and section heading are
  prepended only when embedding, not in the stored text.
- `SET mhnsw_ef_search = 80`; re-measure recall once all paragraph vectors are in.
- Vector search goes in a subquery and is joined afterwards, so the index is used.
- Top 8 paragraphs, at most 2 per article, go to the model.
- The answer is in the question's language; the sources stay in their own language.

## What adding a feature later costs

No idea in `ideas.md` changes the core tables or the ask flow. They fall into four groups:

| Group | Ideas | What gets added |
| --- | --- | --- |
| Queries over the loaded history | Edit-war radar, vandalism survival time, how the story grew, what changed since | Queries on `revert_event` and `article`, plus pages. No new data. |
| Paragraphs over time | Contested-paragraph lens, trust badges, citation history | A `passage_history` table that tracks paragraph lifetimes across revisions. The biggest single addition; the core's `passage` table stays as it is. |
| More embedding | Ask the past, meaning drift, three languages | More rows in `passage_vector` (old versions, or sv/en paragraphs). Same table, same index, more GPU time. |
| Outside the database | Source check; extension; MCP server | Fetched web pages in their own table; or a thin client on the JSON API. |

## Open

- Which cloud model, and which credits pay for it.
- How well `FULLTEXT` handles Finnish word endings, and whether the starter's wikitext cleaner is
  good enough for paragraphs.
