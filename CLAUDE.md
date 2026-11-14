# Project: Wikipedia trust tool on MariaDB (Junction hackathon, MariaDB challenge)

> Updated 2026-11-14 evening. Items marked **OPEN** are not decided yet.
> Plans, task lists and research: the `planning` branch (`tasks/`, `docs/research/`).

## Goal
Build a Wikipedia tool that is missing or underused, with MariaDB at the core. The topic is free
(Finnish history is just what the datasets contain). **Rubric, 20% each:** effective and creative
use of MariaDB (RAG and/or SVT); implementation and **scalability across the provided datasets**
(S, M and L); usefulness for readers or editors; design and demo quality; **originality**. Bonus
(0%, tie-breaker): technical ambition on SVT or combining both tracks. The brief's "very advanced"
example: a RAG assistant that answers *"what did Wikipedia say about this in 2015, and what has
changed since?"* A plain cited-Q&A chatbot is the most common hackathon idea; originality has to
come from the time side.

## Resources (from the challenge page)
- Team repo: https://github.com/trietle145/LakeBandits_junction. Planning docs are on the
  `planning` branch.
- Datasets (S, M, L): https://github.com/MariaDB/mariadb-wikipedia-datasets
- RAG starter: https://github.com/MariaDB/mariadb-vector-wikipedia-rag
- SVT starter: https://github.com/MariaDB/mariadb-system-versioning-wikipedia
- MariaDB brings: the server with native vector search, system-versioned tables, the three
  datasets, the starter docs and mentors on site. Any LLM, embedding model or frontend is allowed.
- Mentors from the MariaDB Foundation, on site throughout: Kaj Arnö (Executive Chairman) and
  Robert Silén (AI Lead). They help with data modelling, query design and scaling.

## The idea
A web app that answers questions about Finnish history from Wikipedia and shows, for every
paragraph it uses, where the text came from and how it got there. Each answer sentence links to
its source paragraph; each paragraph opens its own history (first seen, changes, reverts).
The paragraph is the unit that joins RAG (a vector) and SVT (a versioned row).

## Decisions
- Team of 2. Audience: both readers and editors. Web app first; extension or MCP later.
- Base = cited Q&A (RAG) + two time views (SVT): an article as of a date, and an edit timeline
  with reverts. Build this first. In the base the two tracks sit side by side and meet only at
  the History button on a cited source.
- The highlight is one feature **through time**, added on top of the base without changing it.
  **Built (2026-11-14): time-aware retrieval** ("then vs
  now" answers). Meaning lives in the vector, time lives in the table: the date is stripped from
  the question and becomes `FOR SYSTEM_TIME AS OF` on a system-versioned `passage_history`;
  dates are never mixed into embeddings. Today's counterpart of an old passage is found by vector
  distance within the article (headings get renamed), then word-diffed. The same table later
  gives source-health badges (stable / rewritten / contested / lost its citation). Design and the
  MariaDB selling points: docs/architecture.md, "Time-aware retrieval". Second highlight, also
  built: cross-language gaps (what en/sv Wikipedia say that Finnish does not, and whether Finnish
  once did; docs/architecture.md, "Cross-language gaps"). Unbuilt idea kept as a fallback: the
  edit-war radar (needs only `revert_event`).
- **Selling point for the MariaDB criterion:** the database does the hard parts. One SQL
  statement does vector search + temporal filter + citation of the version live on that date;
  real Wikipedia edit times via `system_versioning_insert_history`; vectors keyed by text hash so
  unchanged passages across hundreds of versions are embedded once; reverts by window functions
  (16 s over 862k versions); hybrid FULLTEXT + vector RRF in SQL.
- Costly to change later, so settle before embedding: the chunking rule and the exact text that
  is embedded (old versions must be split and embedded the same way). Start the full history
  load early; it takes all night. Everything else can be rebuilt from the Parquet files.
- History: all of dataset M in one system-versioned `article` table with real timestamps.
- Search (decided 2026-11-14, details in docs/architecture.md "Chunking, embedding and keyword
  search"): passages from M's newest version per article, cleaned to plain text. **One passage
  per section** (lead included); sections over ~300 words split at paragraphs; no merging across
  sections, no overlap; reference/link sections skipped. ~67k passages, median ~80 words.
  Embedding input `title \n heading \n text`, bge-m3 dense, max 1,024 tokens; `text_hash` =
  SHA-256 of that input. Same model and settings for passages and questions.
- Hybrid retrieval with RRF (k = 60, top 50 per side), `UNION ALL` + `GROUP BY` (no FULL OUTER
  JOIN in MariaDB). Keyword half = `FULLTEXT(title, heading, text)` in boolean mode with **prefix
  terms** built in Python, because FULLTEXT has no Finnish stemming: words of 6+ letters drop
  their last 3 letters (min 4) and get `*` (Kekkonen → `Kekko*`); numbers and short words exact.
- **As built:** hybrid over **five** lists, RRF in one statement: passage vectors, FULLTEXT on
  **names and years only**, Finnish whole-article S vectors, **English/Swedish S article vectors
  joined to their Finnish article** (`article_langlink`, Wikidata id), and en/sv titles written
  verbatim in the question. Starter's 37 questions: **hit@5 92%, hit@10 95%** (starter 76% / 86%;
  73% / 86% before the en/sv lists); keyword half on every word was worse. Table and reasons:
  docs/architecture.md, "Approaches for retrieval" and "Design choices at a glance (for the pitch)".
- Keep the shipped S article vectors for whole-article search and the sv/en articles.
- **Vector index setting (fixed, recommended by MariaDB):** `VECTOR INDEX (embedding) M=16
  DISTANCE=cosine` on every vector table, and `SET mhnsw_ef_search = 80` on every connection that
  searches. Defaults (M=6) found only 79% of the true top 10. Re-measure recall with
  `index_recall.py` when the number of vectors changes, but start from these values.
- Answer-writing model: **Claude Opus 5.5** (`effort: low`, server-side fallback to Opus 4.8),
  a setting in `.env`; key on the server and in A's local `.env` only. ~$0.03 per answer, ~3–4 s.
- **Hosting (decided 2026-11-14): one always-on Verda CPU server**, `lakebandits-db`,
  CPU.4V.16G, FIN-01, Ubuntu 24.04, 80 GB, ~€1.50/day from the Lake Bandits project (€200
  credits). Set up by `scripts/server_setup.sh`; runs `docker-compose.yml` (MariaDB); the app
  runs beside it under gunicorn in tmux; Caddy for public HTTPS is still to do. MariaDB listens on the server's 127.0.0.1 only; people
  reach it by SSH tunnel (`ssh -N -L 3307:127.0.0.1:3306 root@<server>`, see `SERVER.md`), each
  with their own login (`triet` read-write, `hung` read-only). The repo is private, so the
  server's copy came from a git bundle; deploy later = update its copy, `docker compose up -d
  --build`. Embedding runs on Modal (`scripts/modal_embed.py`); questions are embedded on the
  CPU of whatever machine runs the app. Local Docker MariaDB copies still work for development.
  **Delete (not shut down) the instance after the event**; shut-down instances still bill.
- Branches: `main` has everything merged (as of 2026-11-14 evening). New work goes on a feature
  branch off `main`, merged by PR (into `main`, and `planning` kept in step); B's pages on
  `frontend` (guide `docs/frontend.md`). `b-search-app` holds B's earlier plans (graph plan,
  roadmap, `SERVER.md`); `translate` is a removed experiment (Claude translation: too costly).
  Create `.venv` first (`pip install -r requirements.txt`); data under `data/` (never committed).

## Phases (tasks with acceptance criteria: `tasks/plan.md` on `planning`)
Split between two people (revised again 2026-11-14): **A = all backend** (data, search, answers,
time-aware answers, history, graph data, L at scale), **B = all frontend** (every page, the look,
demo polish). The JSON API is the contract between them: `docs/frontend.md`.
1. Get running (done): M loaded, passages built, embedded on Modal and loaded, S vectors loaded.
2. The base (done): cited answers (hybrid, 92% top-5), time views (article as of a date, timeline
   with reverts), History button joining them.
3. The highlight (built): then-vs-now answers; cross-language gaps (`/compare/<page_id>`, "Other
   Wikipedias add" on answers); graph through time (B's page on `/api/graph`).
4. Scale numbers on L (measured at ~700k vectors), evals (`eval/README.md`), public hosting,
   polish, demo rehearsal (**OPEN**).

## Architecture (docs/architecture.md)
- Core = cited Q&A. Retrieval (decided): hybrid, paragraph vectors plus
  FULLTEXT fused by rank in one SQL statement. Build vector-only first, then add the keyword half.
- Tables: `article` (versioned, every revision), `passage` (current paragraphs, plain table, keeps
  `page_id`, `rev_id`, `heading`, `text_hash`, FULLTEXT on text), `passage_vector` (keyed by
  `text_hash`, VECTOR(1024) + index), `article_vector` (shipped S vectors), `revert_event`
  (one row per revert). Definitions: `schema.sql`.
- Time side (decided): two core views, article as of a date and an edit timeline with reverts.
  Reverts are found once after loading and stored in `revert_event`. A question about how
  Wikipedia stood on a date (or with `as_of`) goes to the then-vs-now path in the same `/ask`;
  others are answered from the newest text. Each cited source has a History button to the
  timeline. Yearly partitions on `article` stay.
- Tables added on top (none changes the core): `passage_text` + system-versioned
  `passage_history` + `history_vector` (time), `article_langlink` and `xlang_passage` /
  `xlang_vector` (cross-language), `l_passage` / `l_vector` (dataset L, same definitions).
- Keep these three choices: vectors keyed by text hash (old versions can get vectors later);
  every paragraph keeps its source `rev_id` (citations link to `?oldid=`); the full history is
  loaded even though the core reads only the newest revision.
- New features add tables next to these; they must not require changing the core.

## Data (from github.com/MariaDB/mariadb-wikipedia-datasets, releases `*-2026-10`)
- **S**: History of Finland, current versions. 19,285 fi, 4,921 sv, 5,254 en articles. Clean
  Markdown (FineWiki, Aug 2025), so references are probably stripped. One bge-m3 vector per
  article (1024 dims, cosine). Category tree included. Use for RAG.
- **M**: 19,742 fi articles, **every saved version** 2003 to 1 Oct 2026 (862,076 versions,
  12.2 GB text). Raw wikitext, so `<ref>` citations are present. Columns: `page_id, title,
  rev_id, parent_id, timestamp, user, anonymous, comment, minor, sha1, bytes, text`. No vectors.
  Use for SVT, edit wars and citation history.
- **L**: all 568,416 fi articles, current version, Markdown, no vectors. Use only to show scaling.
- Links back: `https://fi.wikipedia.org/?curid=<page_id>`, one version: `?oldid=<rev_id>`.
- Download sizes (compressed): S 145 MB, M 301 MB, L 472 MB. M unpacks to 12.2 GB (full copy per
  version), so loading M is the overnight step; loading L is short, embedding L is the slow part.

## Stack (from the starter repos; reuse before writing new code)
- MariaDB 12.x (`mariadb:lts` in Docker). Vector search needs 11.7+;
  `system_versioning_insert_history` needs 10.11+.
- Python 3.11+ (the PC has 3.13), Flask, `bge-m3` for embeddings. Where it runs (Ollama, a GPU
  notebook, a hosted endpoint) is per machine.
- Answer-writing LLM: a cloud model, read from a setting so it can be swapped for Ollama.
- Starter code to reuse:
  - `mariadb-vector-wikipedia-rag`: `schema.sql`, `load.py`, `embed.py`, `app.py`,
    `evaluate.py`, `index_recall.py`, `data/test-questions.tsv` (37 questions + expected article).
  - `mariadb-system-versioning-wikipedia`: `schema.sql` (versioned `article` table, partitioned
    by year, extra `(page_id, row_start)` index), `load.py` (real timestamps), `asof.py`,
    `test_history.py`.

## Known facts that shape the design
- Vector index: `VECTOR INDEX (embedding) M=16 DISTANCE=cosine` + `SET mhnsw_ef_search = 80`
  gave 100% recall@10 on S (99% in Docker), ~5 ms. Defaults gave 79%. Re-measure with
  `index_recall.py` whenever the number of vectors changes (passages, L).
- Put the vector search in a subquery and join afterwards, or the index is not used (1 ms vs 50 ms).
- Vector search plus a filter over a huge category falls back to a full scan (2 s).
- One vector per article finds the topic, not the fact. Passage-level vectors fix this.
- Versioned history: add a `(page_id, row_start)` index or old "as of" dates are slow.
- Reverts: same `sha1` as an earlier version. Most reverts are vandalism cleanup; an edit war is
  *mutual* reverts between named users. sha1 misses partial reverts and rewordings.
- "Anonymous" changed meaning in 2025 (IP addresses replaced by temporary accounts).
- Vectors live in plain tables (`passage_vector`, `article_vector`), so we never need a vector
  index on a versioned or partitioned table.
- A trailing `LIMIT` on the last `UNION ALL` branch limits the whole union (wrap it in a derived
  table). It silently cut the fusion to one list once; the eval caught it.
- One writer at a time into a vector index: parallel loaders deadlock or time out (the loader
  retries). Inserts slow as the graph grows (~740/s at the start, ~65/s past 600k).
- **Server memory (16 GB):** MariaDB normally runs with a 3 GB buffer pool and a 1–3 GB vector
  cache; the app's bge-m3 takes ~3–5 GB. Never run a big vector load and the app together: a 7 + 5
  GB load setting with the app running locked the server up (fixed by stopping the loaders and
  restarting MariaDB). Both caches resize live (`SET GLOBAL`); `docker compose restart` keeps old
  settings, `up -d` re-reads `.env`. `COUNT(*)` on a vector table is slow: read loader logs.

## Project docs
- `README.md`: what the app does, headline scores, how to run it.
- `docs/architecture.md`: design choices with evidence, tables, search, time features,
  cross-language gaps, scale, MariaDB lessons, known limits.
- `docs/frontend.md`: pages, JSON API contract, `api.js` fallback behaviour.
- `eval/README.md`: every score (search on M and L, answers, vector index scale) and the method.
- On `planning` only: `tasks/plan.md`, `tasks/plan-a.md`, `docs/research/`, old frontend notes.

## Current state (2026-11-14 evening)
- **The shared server is the real database** (`root@135.181.8.213`, SSH alias `lakebandits` on
  A's PC; MariaDB on its 127.0.0.1:3306, reached by tunnel). It holds all of M (862,076
  versions), S vectors (29,460), 66,543 passages + vectors (redirect junk removed), `revert_event`
  (46,015), `passage_history` (593,195 lifetimes) + `history_vector` (353,166),
  `article_langlink` (10,175), `xlang_passage` / `xlang_vector` (35,829 labelled en/sv
  paragraphs), and dataset L: `l_passage` (1,545,854) + `l_vector` (loading, see below).
  A's PC has a local Docker copy of M, S and passages (port 3307; usually off).
- **The app** (`main`): `/ask` with five-list hybrid search, cited answers (cited sources first,
  numbered 1, 2, …), then-vs-now answers (two-stage + global time search, word diffs), "Other
  Wikipedias add" + en/sv pills; `/article/<id>` (as of a date, timeline, reverts);
  `/compare/<id>` (en/sv vs Finnish); `/graph/<id>` (B's page on `/api/graph`). Runs on the
  server in tmux `web` via gunicorn: start/restart `bash scripts/restart_app.sh`, view through
  `ssh -N -L 5000:127.0.0.1:5000 lakebandits` → http://127.0.0.1:5000. The server's repo copy is
  updated from a git bundle (`git bundle create … --all`, scp, `git fetch` there; repo private).
- **L load (stopped 2026-11-14 at ~700k of 1.55M vectors, for measuring):** rerun
  `bash /root/l_pipeline.sh` on the server to resume (skips loaded rows; one loader, memory guard;
  ~50 inserts/s at this size, so hours). Keep the app off the server while it loads. Numbers:
  `eval/README.md` and docs/architecture.md, "Scale: S → M → L".
- Loading bge-m3 needs ~5 GB free memory; short of it, it fails with misleading errors. The first
  question after an app restart takes ~13 s (model load); gunicorn warms it at start.
- `.env.example` lists every setting; copy to `.env` (git-ignored) and fill in.
- Next (A): public hosting (Caddy; per-visitor limit on model calls on top of the daily cap);
  translate-before-search for the 2 remaining search misses if needed; a small model as judge for
  the cross-language "partly" label if it goes into the demo.

## Coding style
- Use the `ponytail` skill (level full) for every coding task: the smallest code that works,
  reuse the starter repos and existing helpers (`scripts/common.py`) before writing new code,
  stdlib and MariaDB features before new dependencies. Each non-trivial script leaves one
  runnable check behind (like `load_m.py --verify`).

## Boundaries
- Never commit secrets or API keys; read them from environment variables.
- Do not label named editors as vandals or edit warriors in the UI; show patterns, link to diffs.
- Wikipedia text is CC BY-SA: link back to every article and version shown.
- Use the published dumps and datasets, not bulk calls to the live Wikipedia API
  (rate limit 200 requests a minute).
- Keep the demo path working at all times: build the baseline end to end first, then add features.
