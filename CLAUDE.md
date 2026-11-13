# Project: Wikipedia trust tool on MariaDB (Junction hackathon, MariaDB challenge)

> Updated 2026-11-13 after the architecture review. Items marked **OPEN** are not decided yet.
> First rough plan as a page: https://claude.ai/artifact/92Jie7dsbM9C85B7KRBF2s

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
  `revert_event`. Sorted list: docs/ideas.md.
- Costly to change later, so settle before embedding: the chunking rule and the exact text that
  is embedded (old versions must be split and embedded the same way). Start the full history
  load early; it takes all night. Everything else can be rebuilt from the Parquet files.
- History: all of dataset M in one system-versioned `article` table with real timestamps.
- Search: paragraphs from M's newest version per article, cleaned to plain text. One paragraph
  per passage, short ones merged up to ~300 words, title + section heading prefixed before
  embedding. One bge-m3 vector each. Where embedding runs is set per machine (`.env`); the rule
  is the same model and settings for paragraphs and questions.
- Keep the shipped S article vectors for whole-article search and the sv/en articles.
- Answer-writing model: a cloud model on hackathon credits, kept as a setting.
- Working habits on the PC: planning work goes on the `planning` branch, create `.venv` first,
  data under `data/` (never committed).

## Phases
Rough; they get re-planned in a later session.
1. Data in: M into the versioned table, S with its vectors.
2. Paragraphs: clean, split, embed, index. Beat the starter's 76% top-5 on the 37 test questions,
   plus our own paragraph-level questions (see docs/architecture.md, Evaluation).
3. Cited answers and article summaries on the web page.
4. One added feature from docs/ideas.md (paragraph history, if needed, on ~200 pilot articles).
5. Scale numbers on L, polish, demo rehearsal.
Before phase 1: the "First hour" checks in docs/architecture.md.

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
- Feature ideas (edit wars, vandalism, cross-language, contradictions...) live in docs/ideas.md
  and add tables next to these; they must not require changing the core.
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
- `docs/plan.md`: the rough plan (idea, decisions, phases, feature candidates, risks).
- `docs/architecture.md`: the base (cited Q&A and time views) and what the time features add.
- `docs/ideas.md`: feature ideas sorted around time; the highlight is not picked yet.
- `docs/research/wikipedia-problems.md`: problems worth solving, ranked, with sources.
- `docs/research/edit-wars.md`: edit wars and vandalism, detection methods, 8 feature ideas.

## Current state of this folder (2026-11-13)
- `.venv` exists (Python 3.13, `mariadb` + `pyarrow`). Dataset M is in `data/m/` (16 Parquet
  files, checksums verified). `data/` and `.venv/` are git-ignored. Only docs and `schema.sql`
  are committed; no code exists yet.
- Nothing is loaded. Blocker: no MariaDB is running. Docker Desktop's disk image is on C: with
  2.9 GB free (D: has 89 GB); move it to D: (or run a portable MariaDB from D:) before loading.
- `schema.sql` (all five tables) is written. Next steps for the load: a Parquet
  loader `scripts/load_m.py` (real timestamps, resumable, `--limit`), a 20-article smoke test,
  then the full load in the background logging to `data/load_m.log`.

## Boundaries
- Never commit secrets or API keys; read them from environment variables.
- Do not label named editors as vandals or edit warriors in the UI; show patterns, link to diffs.
- Wikipedia text is CC BY-SA: link back to every article and version shown.
- Use the published dumps and datasets, not bulk calls to the live Wikipedia API
  (rate limit 200 requests a minute).
- Keep the demo path working at all times: build the baseline end to end first, then add features.
