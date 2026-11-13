# Project: Wikipedia trust tool on MariaDB (Junction hackathon, MariaDB challenge)

> Updated 2026-11-13 after the planning session. Items marked **OPEN** are not decided yet.
> Full rough plan: https://claude.ai/artifact/92Jie7dsbM9C85B7KRBF2s

## Goal
Build a Wikipedia tool that is missing or underused, with MariaDB at the core. Judged on:
creative use of MariaDB RAG (vector search) and/or SVT (system-versioned tables), technical
execution and scaling across datasets, usefulness to readers or editors, design and demo quality.
Doing RAG and SVT together earns extra credit.

## The idea
A web app that answers questions about Finnish history from Wikipedia and shows, for every
paragraph it uses, where the text came from and how it got there. Each answer sentence links to
its source paragraph; each paragraph opens its own history (first seen, changes, reverts).
The paragraph is the unit that joins RAG (a vector) and SVT (a versioned row).

## Decisions
- Team of 2. Audience: both readers and editors. Web app first; extension or MCP later.
- Base = cited Q&A (RAG) + version history (SVT), joined at paragraph level. Build this first.
- The "twist" is one added feature, chosen later (**OPEN**). Candidates: contested-paragraph
  heatmap, dispute ranking for all articles, citation history, source check, ask-the-past,
  vandalism survival time.
- History: all of dataset M in one system-versioned `article` table with real timestamps.
- Search: paragraphs from M's newest version per article, cleaned to plain text. One paragraph
  per passage, short ones merged up to ~300 words, title + section heading prefixed before
  embedding. One bge-m3 vector each, embedded on a GPU (Colab T4; Modal as fallback).
- Keep the shipped S article vectors for whole-article search and the sv/en articles.
- Answer-writing model: a cloud model on hackathon credits, kept as a setting.
- Working habits on the PC: checkout `main` first, create `.venv` first, data under `data/`
  (never committed).

## Phases
1. Data in: M into the versioned table, S with its vectors.
2. Paragraphs: clean, split, embed, index. Beat the starter's 76% top-5 on the 37 test questions.
3. Cited answers on the web page.
4. Paragraph history: track each paragraph across versions.
5. One added feature.
6. Scale numbers on L, polish, demo rehearsal.

## Proposed tables (columns settle in phase 2)
- `article` (system-versioned, from the starter + `parent_id`, `anonymous`).
- `passage` (system-versioned): `passage_id, page_id, position, heading, text, text_hash`.
- `passage_vector`: `passage_id, embedding VECTOR(1024)` + vector index.
- `article_vector`: shipped S vectors, `lang, page_id, embedding VECTOR(1024)`.

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
- Python 3.11+, Flask, Ollama running `bge-m3` for embeddings (must match the dataset vectors).
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
- **Unverified:** whether a `VECTOR INDEX` works on a system-versioned table, and whether vector
  search combines with `FOR SYSTEM_TIME AS OF`. Test this early.

## Project docs
- `docs/plan.md`: the rough plan (idea, decisions, phases, feature candidates, risks).
- `docs/research/wikipedia-problems.md`: problems worth solving, ranked, with sources.
- `docs/research/edit-wars.md`: edit wars and vandalism, detection methods, 8 feature ideas.

## Current state of this folder (2026-11-13)
- `.venv` exists (Python 3.13, `mariadb` + `pyarrow`). Dataset M is in `data/m/` (16 Parquet
  files, checksums verified). `data/` and `.venv/` are git-ignored. No commits yet.
- Nothing is loaded. Blocker: no MariaDB is running. Docker Desktop's disk image is on C: with
  3.6 GB free; move it to D: (or run a portable MariaDB from D:) before loading.
- Next steps for the load: starter `schema.sql` (+ `parent_id`, `anonymous` columns), a Parquet
  loader `scripts/load_m.py` (real timestamps, resumable, `--limit`), a 20-article smoke test,
  then the full load in the background logging to `data/load_m.log`.

## Boundaries
- Never commit secrets or API keys; read them from environment variables.
- Do not label named editors as vandals or edit warriors in the UI; show patterns, link to diffs.
- Wikipedia text is CC BY-SA: link back to every article and version shown.
- Use the published dumps and datasets, not bulk calls to the live Wikipedia API
  (rate limit 200 requests a minute).
- Keep the demo path working at all times: build the baseline end to end first, then add features.
