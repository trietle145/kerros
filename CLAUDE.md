# Project: Wikipedia trust tool on MariaDB (Junction hackathon, MariaDB challenge)

> Updated 2026-11-14. Items marked **OPEN** are not decided yet.
> The plan and task list: `tasks/plan.md`.

## Goal
Build a Wikipedia tool that is missing or underused, with MariaDB at the core. Judged on:
creative use of MariaDB RAG (vector search) and/or SVT (system-versioned tables), technical
execution and scaling across datasets, usefulness to readers or editors, design and demo quality.
Doing RAG and SVT together earns extra credit.

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
  Which one is **OPEN**. Front-runner: an answer time slider (the same question answered as of
  a chosen year, and what changed since). Safety net: the edit-war radar, which needs only
  `revert_event`. Sorted list: `tasks/plan.md`, Phase 3.
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
- Keep the shipped S article vectors for whole-article search and the sv/en articles.
- **Vector index setting (fixed, recommended by MariaDB):** `VECTOR INDEX (embedding) M=16
  DISTANCE=cosine` on every vector table, and `SET mhnsw_ef_search = 80` on every connection that
  searches. Defaults (M=6) found only 79% of the true top 10. Re-measure recall with
  `index_recall.py` when the number of vectors changes, but start from these values.
- Answer-writing model: Claude API ($20 per person) or Gemini, kept as a setting in `.env`.
- **Hosting (OPEN).** Now: MariaDB runs locally in Docker on A's PC; since M loads in ~12 min,
  each person can run their own local copy for development (share only the embedded vectors as a
  file). Leading option for the team and the demo: **one always-on rented CPU server** (4 vCPU,
  16 GB RAM, 60 GB disk; Verda credits if CPU-only machines exist, else Hetzner/DigitalOcean, or
  MariaDB's own cloud if the mentors offer it) running `docker-compose.yml` with MariaDB plus,
  once it exists, the Flask app and Caddy for public HTTPS. Data downloaded and loaded on the
  server. MariaDB is never public: the app reaches it inside Docker, the team over Tailscale
  (`DB_BIND` = Tailscale IP), each with their own login. Deploy = `git pull && docker compose up
  -d --build`. Embedding all paragraphs runs once on a GPU (Modal or Verda); questions are
  embedded on the server's CPU.
- Working habits on the PC: planning work goes on the `planning` branch, create `.venv` first,
  data under `data/` (never committed).

## Phases (tasks with acceptance criteria in `tasks/plan.md`)
Split between two people (revised 2026-11-14): **A = data and time** (passages, embedding,
loading, reverts, time views), **B = search, answers and app** (retrieval, hybrid, reranker,
prompts, Flask, eval). One owner per file and fixed contracts: `tasks/plan.md`, "How the two
people split the work".
1. Get running: MariaDB on D:, shared over Tailscale; M loaded (overnight); paragraphs built,
   embedded on a GPU and loaded; S vectors loaded.
2. The base: cited answers (vector, then hybrid; beat the starter's 76% top-5), time views
   (article as of a date, timeline with reverts), History button joining them.
3. The highlight through time (**OPEN**, planned after Phase 2).
4. Scale numbers on L, polish, demo rehearsal (**OPEN**).

## Architecture (docs/architecture.md)
- Core = cited Q&A + article summaries. Retrieval (decided): hybrid, paragraph vectors plus
  FULLTEXT fused by rank in one SQL statement. Build vector-only first, then add the keyword half.
- Tables: `article` (versioned, every revision), `passage` (current paragraphs, plain table, keeps
  `page_id`, `rev_id`, `heading`, `text_hash`, FULLTEXT on text), `passage_vector` (keyed by
  `text_hash`, VECTOR(1024) + index), `article_vector` (shipped S vectors), `revert_event`
  (one row per revert). Definitions: `schema.sql`.
- Time side (decided): two core views, article as of a date and an edit timeline with reverts.
  Reverts are found once after loading and stored in `revert_event`. The Q&A answers from the
  newest text; `/ask` takes an optional `as_of` that is unused for now. Each cited source has a
  History button to the timeline. Yearly partitions on `article` stay.
- Keep these three choices: vectors keyed by text hash (old versions can get vectors later);
  every paragraph keeps its source `rev_id` (citations link to `?oldid=`); the full history is
  loaded even though the core reads only the newest revision.
- Feature ideas (edit wars, vandalism, cross-language, contradictions...) live in `tasks/plan.md`
  (Phase 3) and add tables next to these; they must not require changing the core.
- Points to settle when the time features are built are in docs/architecture.md, "Notes for the
  time features".

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

## Project docs
- `tasks/plan.md`: the one planning file (idea, decisions, phases and tasks, feature pool, risks).
- `docs/architecture.md`: the base (cited Q&A and time views) and what the time features add.
- `docs/research/wikipedia-problems.md`: problems worth solving, ranked, with sources.
- `docs/research/edit-wars.md`: edit wars and vandalism, detection methods, 8 feature ideas.

## Current state of this folder (2026-11-14)
- `.venv` exists (Python 3.13, `mariadb` + `pyarrow`). Datasets M (`data/m/`, 16 Parquet files)
  and S (`data/s/`) are downloaded, checksums verified. `data/` and `.venv/` are git-ignored.
  Code so far: `scripts/common.py`, `load_m.py`, `load_s.py`.
- MariaDB 12.3.3 runs on this PC in Docker (`docker compose up -d`), data volume on D:, host port
  **3307** (a MySQL 9.4 Windows service holds 3306; leave it alone). Schema applied, ef_search=80
  confirmed, login `triet`. **All of M is loaded** (19,742 articles, 862,076 versions, 6.1 GB,
  11.5 min; `load_m.py --verify 30` all ok). **S vectors loaded** into `article_vector`
  (29,460 rows, 0.7 min; `load_s.py --verify` ok, search ~1 ms warm). The Verda machine with
  `docker-compose.yml` stays the plan for an always-on shared host.
- `.env.example` lists every setting; copy to `.env` (git-ignored) and fill in.
- Next: shared skeleton (1.S), then in parallel A: passages (1.A6), B: search + eval (2.B1).

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
