# Plan: Wikipedia trust tool on MariaDB

2026-11-14. The one planning file: idea, decisions, phases, tasks, feature pool, risks.
Technical design (tables, queries, data flow) is in [`docs/architecture.md`](../docs/architecture.md);
sources are in [`docs/research/`](../docs/research/). Phases 1 and 2 are concrete. Phases 3 and 4
are open and get re-planned once the base works.

## The idea

A web app that answers questions about Finnish history from Wikipedia. Every sentence of an answer
cites the paragraph it came from, linked to the exact Wikipedia revision, and every source can be
followed back through time: how the article looked on a chosen date, when it was edited, and
where editors reverted each other.

- **Readers** get answers they can check.
- **Editors** see which articles and passages are unstable or fought over.
- **Why it stands out:** it joins both MariaDB tracks in one database (vector search + system-versioned
  history), works at paragraph level instead of whole articles, and uses the full history: 862,076
  versions of 19,742 articles, 2003 to October 2026, with their real timestamps.

## Decisions

| Topic | Decision |
| --- | --- |
| Team | 2 people, each with their own local MariaDB. Split (revised 2026-11-14): **A = data and time** (passages, embedding, loading, reverts, time views), **B = search, answers and app** (retrieval, hybrid, reranker, prompts, Flask, evaluation). Each file has one owner; see "How the two people split the work". |
| Audience | Readers and editors. |
| Form | Web app (Flask) first. Extension or MCP server later, on the same JSON API. |
| Base | Cited Q&A over today's paragraphs (RAG) + article as of a date and edit timeline with reverts (SVT). |
| Highlight | One feature **through time**, added on top of the base. Which one is open (Phase 3). |
| History data | All of dataset M in one system-versioned `article` table with real timestamps. |
| Search data | Passages from M's newest version of each article, cleaned to plain text, one bge-m3 vector each (~67k). |
| Passage unit | One section (lead included); sections over ~300 words split at paragraphs; no merging across sections, no overlap; reference/link sections skipped. Embedding input `title \n heading \n text`. Details: `docs/architecture.md`, "Chunking, embedding and keyword search". |
| Retrieval | Hybrid: vectors + `FULLTEXT` in boolean mode with Finnish prefix terms (`Kekko*`), fused by RRF (k = 60, top 50 per side). Built vector-only first. |
| Vector index | Fixed, recommended by MariaDB: `M=16 DISTANCE=cosine` on every vector index, `SET mhnsw_ef_search = 80` on every search connection. Defaults found only 79% of the true top 10. |
| Answer model | Claude API ($20 per person) or Gemini, read from `.env`. |
| S vectors | Loaded as shipped, for whole-article search and the sv/en articles. |
| Hosting (**open**) | **Now:** MariaDB in Docker on A's PC (M loaded); local copies per person are cheap since M loads in ~12 min. **Leading option:** one always-on rented CPU server (4 vCPU, 16 GB RAM, 60 GB disk; Verda if CPU-only machines exist, else Hetzner/DigitalOcean, or MariaDB's own cloud if the mentors offer it) running `docker-compose.yml`: MariaDB now, plus the Flask app and Caddy (public HTTPS) once the app exists. MariaDB is never public: the app reaches it inside Docker, the team over Tailscale with their own logins. Deploy = `git pull && docker compose up -d --build`. |
| GPU | Embedding runs on a GPU for a few minutes (~67k passages): Modal ($100 per person) or a Verda GPU machine, then the vectors file is shared and each person loads it into their own database. |

**Fixed before embedding** (changing them later means embedding again): the chunking rule and the
exact text that is embedded. Everything else can be rebuilt from the Parquet files.

## Data

| Set | On disk | Contents | Use |
| --- | --- | --- | --- |
| M | Yes, `data/m/` (16 Parquet files, checksums verified) | Every version of 19,742 fi articles, raw wikitext, real timestamps, no vectors | All of it → `article`. Newest version → paragraphs → our vectors. |
| S | Yes, `data/s/` (checksums verified) | Current fi/sv/en articles (19,285 / 4,921 / 5,254), one shipped bge-m3 vector per article | Shipped vectors → `article_vector` |
| L | Not yet | All 568,416 fi articles, current only, no vectors | Scale numbers only (Phase 4) |

Source: https://github.com/MariaDB/mariadb-wikipedia-datasets (releases `*-2026-10`). `data/` is
never committed.

Download sizes (compressed Parquet, checked 2026-11-14): S 145 MB, M 301 MB, L 472 MB, under 1 GB
in all. M unpacks to 12.2 GB because every version is a full copy, so **M is the slow load**
(measured: 11.5 min on a laptop, 6.1 GB in the table). L is one version per article and should load in well under an hour; what makes L
slow is embedding its paragraphs (rough guess 1–2 million) and building their index.

## How the two people split the work

Revised 2026-11-14. Done already: 1.A1, 1.A3–1.A5 (M loaded), 1.B3, 1.B5 (S vectors loaded).
1.A2 (Tailscale) is deferred: each person runs their own MariaDB (README, "Local setup").

```
            A: data and time                          B: search, answers, app
Both        1.S  Shared skeleton (one person, ~45 min, pushed before anything else)
Phase 1     1.A6 Passages from Parquet (pilot first)   2.B1 Search + eval on S article vectors
            1.A7 Embed passages on a GPU               2.B2 Cited answers (prompts, LLM, [n] check)
            1.A8 Load passages + vectors, recall       2.B3 Ask page + /ask JSON
Phase 2     2.A1 Revert detection                      2.B1 again on passages   (needs 1.A8)
            2.A2 Time endpoints + stats()              2.B4 Hybrid search       (needs passages loaded)
            2.A3 Time pages                            2.B5 Reranker, measured  (optional)
                                                       2.J1 History button      (needs 2.A2)
```

**Task details live with their owner:** A's tasks in `tasks/plan-a.md` on branch `a-data-time`,
B's in `tasks/plan-b.md` on branch `b-search-app`. This file keeps what both share: the idea,
decisions, ownership, contracts, shared tasks (1.0, 1.S, done tasks), checkpoints, risks.

Neither person waits on the other at the start. B builds search and the eval on the S article
vectors (already loaded) and the answer flow on the first pilot passages that A sends (3 hero
articles, CPU-embedded, within the first hours). A sends real data as it is ready:
passages first (B can then build the FULLTEXT half), vectors after the GPU run.

### Who owns which file

Only the owner edits a file. Everything else is read or imported. This is what keeps merges clean.

| Owner | Files |
| --- | --- |
| **Shared** (written in 1.S, then frozen: change only after telling the other, in its own small commit) | `requirements.txt`, `app/main.py` (creates the app, registers the two blueprints, nothing else), `app/db.py` (connect + `SET mhnsw_ef_search = 80`), `app/embed.py` (`embed()` for passages *and* questions), `app/templates/base.html` |
| **A** | `schema.sql`, `scripts/common.py`, `scripts/wikitext.py`, `scripts/build_passages.py`, `scripts/embed_passages.py`, `scripts/load_vectors.py`, `scripts/build_reverts.py`, `app/history.py` (blueprint + `stats()`), `app/templates/article.html`, `app/static/history.*` |
| **B** | `app/search.py` (vector, prefix terms, RRF), `app/rerank.py`, `app/llm.py` (prompts, provider), `app/ask.py` (blueprint), `app/templates/ask.html`, `app/static/ask.*`, `eval/` |
| Docs | A: `tasks/plan-a.md`, B: `tasks/plan-b.md` (tick your own tasks there). `tasks/plan.md` and `CLAUDE.md` are shared: change them in a small PR of their own. `.env.example`: add keys only under your own `# A` / `# B` heading. |

### Contracts (fixed in 1.S; both code against them from the start)

- `app.embed.embed(texts: list[str]) -> list[bytes]`: bge-m3 dense, normalised, max 1,024
  tokens, 1024 little-endian float32 per text. A's `embed_passages.py` and B's question search
  both call it, so passages and questions can never be embedded differently.
- `app.search.search(question: str, k=8, as_of=None) -> list[dict]` (B), each dict:
  `passage_id, page_id, rev_id, title, heading, text, score`.
- `app.history.stats(page_ids: list[int]) -> dict[int, dict]` (A): `{page_id: {"edits": n,
  "reverts": m}}`. Stub returns zeros until 2.A2, so B's source cards work from day one.
- Routes: A owns `/article/<page_id>?as_of=YYYY-MM-DD` and `/article/<page_id>/timeline`;
  B owns `/`, `/ask` and `/summarise/<page_id>`. B's source card links to `/article/<page_id>`.
- `/ask` JSON: `{"answer": [{"text": "...", "cites": [1, 3]}], "sources": [{"n": 1, ...search dict,
  "url": "https://fi.wikipedia.org/?oldid=<rev_id>", "edits": n, "reverts": m}]}`; a sentence
  with empty `cites` is shown as uncited.
- Data files: `passages.parquet` and `passage_vectors.parquet` as in task 1.0, sent by Drive or
  USB, never git. B loads them with A's `load_vectors.py`.

### Git

- `planning` is the integration branch (1.S and the shared docs are there); `main` gets
  `planning` at the Phase checkpoints.
- A works on `a-data-time`, B on `b-search-app`. Merge into `planning` by pull request, small
  and often (one task per PR is a good size); the other person skims and approves.
- Before opening a PR, bring `planning` in: `git pull origin planning`. With one owner per file
  this never conflicts.
- A file you don't own: ask first, change it in its own PR.

---

## Phase 1: get running (data in)

Goal: each person has a local MariaDB with all four data tables filled.

**Before starting:** claim the Verda, Modal and Claude credits, and ask the MariaDB mentors whether
they host a database for teams (that would replace 1.A1).

Remaining Phase 1 tasks are A's: 1.A2 (deferred), 1.A6–1.A8 in `tasks/plan-a.md`.

### Task 1.0 (both, 15 min): agree the hand-over formats

**Description:** Fix the two files A produces and both databases accept, and the `.env` keys, so the
halves can be built in parallel.

**Acceptance criteria:**
- [ ] `data/passages.parquet` columns: `page_id, rev_id, title, position, heading, text, text_hash`
      (`text_hash` = SHA-256 of the embedding input `title \n heading \n text`, 32 bytes).
- [ ] `data/passage_vectors.parquet` columns: `text_hash, model, embedding` (1024 float32, normalised).
- [ ] `.env.example` (already committed) has every key both people need.

**Verification:** both people have read and agreed; `.env` is git-ignored.
**Dependencies:** none. **Files:** `.env.example`. **Scope:** XS.

### Task 1.S (one person, ~45 min, before the split): shared skeleton (done, on `planning`)

**Description:** Write the shared files from "Who owns which file" and the contract stubs, so
both people can code against them at once. After this task the shared files are frozen.
`app/main.py` creates the Flask app and registers A's `history` and B's `ask` blueprints;
`app/db.py` connects through `scripts/common.env()` and sets `mhnsw_ef_search = 80`;
`app/embed.py` holds `embed()`; `app/history.py` and `app/ask.py` start as stubs (`stats()`
returns zeros, `/ask` returns a fixed example in the contract's JSON shape).

**Acceptance criteria:**
- [x] `flask --app app.main run` serves `/` and `/ask` (stub) and `/article/<id>` (stub).
- [x] `python -m app.embed` self-check passes (4096 bytes per vector, normalised, similar > unrelated).
- [ ] `requirements.txt` installs cleanly in a fresh `.venv`; README setup uses it. (README done;
      installed into A's existing `.venv`, so the fresh install is checked on B's machine.)

**Verification:** the three commands above, on both machines.
**Dependencies:** 1.0. **Files:** `requirements.txt`, `app/main.py`, `app/db.py`, `app/embed.py`,
`app/history.py`, `app/ask.py`, `app/templates/base.html`. **Scope:** M.

### Task 1.A1: shared MariaDB on a cloud machine (done on the fallback: A's PC, MariaDB 12.3.3, port 3307)

**Description:** Rent one machine on Verda (CPU-only if offered; ≥ 8 GB RAM, ≥ 60 GB disk),
install Docker, clone the repo, fill in `.env` and run `docker compose up -d`. The compose file
starts `mariadb:lts` with the fixed vector settings and applies `schema.sql` on the first start.
Download datasets M and S from GitHub straight onto the machine into `data/`.
**Fallback** if Verda does not work out: the same compose file on A's PC, with Docker Desktop's
disk image moved to D: (C: has 2.9 GB free).

**Acceptance criteria:**
- [x] `SELECT VERSION()` returns 11.7 or later.
- [x] `SHOW TABLES` lists the five tables from `schema.sql`.
- [x] M and S are on the machine with checksums verified.

**Verification:** `SELECT VEC_DISTANCE_COSINE(VEC_FromText('[1,0]'), VEC_FromText('[0,1]'));` returns 1.
**Dependencies:** none. **Files:** `docker-compose.yml`, `.env.example` (both exist). **Scope:** S.

### Task 1.A3: smoke test

**Description:** Prove the MariaDB features we rely on work on this install (`schema.sql` was
applied by the container in 1.A1).

**Acceptance criteria:**
- [x] `SELECT @@mhnsw_ef_search` returns 80.
- [x] With 3 fake rows, a vector search (subquery + `ORDER BY VEC_DISTANCE_COSINE ... LIMIT`) and a
      `FULLTEXT` search each return rows. (Vector search tested on the real S vectors instead:
      index used, ~1 ms warm. FULLTEXT tested by hand.)
- [x] Finnish word endings: noted whether `MATCH ... AGAINST('Kekkonen')` finds a row containing "Kekkosen".
      (It does not; `Kekko*` in boolean mode does. See `docs/architecture.md`.)

`scripts/smoke.sql` was not written; the checks above were run by hand.

**Verification:** a `scripts/smoke.sql` that runs clean, its output pasted in the PR.
**Dependencies:** 1.A1. **Files:** `scripts/smoke.sql`. **Scope:** S.

### Task 1.A4: M loader, 20-article test (done)

**Description:** `scripts/load_m.py` writes every version of each article from `data/m/*.parquet`
into `article` with its real timestamp, based on the SVT starter's `load.py`. Resumable (skips pages
already loaded) and takes `--limit N`. Runs on the database machine itself, where M was downloaded.

**Acceptance criteria:**
- [x] `--limit 20` loads 20 articles with all their versions.
- [x] `FOR SYSTEM_TIME AS OF` an old date returns the version that was live then (compare `rev_id`
      with the Parquet file).
- [x] Re-running does not duplicate rows.

**Verification:** row counts per page match the Parquet counts; one AS OF check passes; rows per
second logged, so the full-load time can be estimated.
**Dependencies:** 1.A3. **Files:** `scripts/load_m.py`. **Scope:** M.

### Task 1.A5: full M load (done: 11.5 min, all counts match, verify ok)

**Description:** Run the loader over all of M in the background on the database machine (inside
`tmux` or `nohup`, so it survives a closed SSH session), logging to `data/load_m.log`.

**Acceptance criteria:**
- [x] `SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL` = 862,076.
- [x] `SELECT COUNT(*) FROM article` = 19,742.

**Verification:** both counts; an AS OF query on *Talvisota* takes well under a second.
**Dependencies:** 1.A4. **Files:** none. **Scope:** XS (runs all night).

### Task 1.B3: download S, write its loader (done)

**Description:** Download S from the datasets repo into `data/s/` and check its checksums. Write
`scripts/load_s.py` (from the RAG starter's `load.py`) that loads the shipped article vectors into
`article_vector`.

**Acceptance criteria:**
- [x] S downloaded, checksums verified.
- [x] Loader written and tested against a local file read (database insert happens in 1.B5).

**Verification:** checksum output; loader dry run prints row counts per language.
**Dependencies:** none. **Files:** `scripts/load_s.py`. **Scope:** S.

### Task 1.B5: load S vectors (done: 0.7 min, ~700 vectors/s with the index built as rows go in)

**Acceptance criteria:**
- [x] `article_vector` has 29,460 rows (19,285 fi + 4,921 sv + 5,254 en).
- [x] Nearest articles to *Talvisota*'s vector are about the Winter War (Talvisodan tausta,
      Jatkosota, Välirauha, Moskovan rauhansopimus).

**Verification:** `python scripts/load_s.py --verify` (count and the neighbour query). Log:
`data/load_s.log`.
**Dependencies:** 1.A3, 1.B3. **Files:** none. **Scope:** XS.

### Checkpoint: Phase 1 done

- [ ] Both people have a local database with M and S loaded (README, "Local setup").
- [ ] `article` holds all 862,076 versions; `passage`, `passage_vector`, `article_vector` are filled.
- [ ] Paragraph count, embedding time and load time are written into this file (replacing the estimates).
- [ ] Review together before Phase 2.

---

## Phase 2: the base (basic RAG + time views)

Goal: a web page where a question gets a cited answer, and each source opens its article's history.
This is the base the time highlight is built on.

Tasks: 2.A1–2.A3 in `tasks/plan-a.md` (branch `a-data-time`); 2.B1–2.B5 and 2.J1 in
`tasks/plan-b.md` (branch `b-search-app`). The demo path: question → answer → source → History
button → timeline → article as of a date.

### Checkpoint: Phase 2 done (the base)

- [ ] The demo path above works end to end on the 3 hero articles.
- [ ] Evaluation numbers recorded (vector-only and hybrid).
- [ ] Review together, then plan Phase 3.

---

## Phase 3: the highlight, through time (open)

To be planned after Phase 2. The base stays as it is; the highlight is added next to it. Points to
settle when building it are in `docs/architecture.md`, "Notes for the time features".

**Front-runner:** the answer time slider. **Safety net:** the edit-war radar (needs only
`revert_event`, so it works even if paragraph history slips).

| Idea | For | What the user sees | Needs |
| --- | --- | --- | --- |
| Answer time slider (ask the past) | Readers | Drag a year: the same question answered as Wikipedia stood then, with that year's sources and what changed since | Paragraph lifetimes (`passage_history`) + vectors for old paragraph texts |
| Trust badges on answers | Readers | Each source marked "unchanged since 2014", "rewritten 6 times" or "contested" | Paragraph lifetimes |
| What changed since | Both | Pick an article and two dates; a short summary of what was added, removed and reworded, linked to the edits | Base only for whole articles; paragraph lifetimes make it sharper |
| Contested-paragraph lens | Both | Each paragraph shaded by how much it was fought over; click to see its wording flip over the years | Paragraph lifetimes + `revert_event` |
| Edit-war radar | Editors | Ranked list of the most fought-over Finnish history articles (mutual reverts between named editors), including slow fights over years. No published study covers Finnish | `revert_event` only |
| Vandalism survival time | Editors | How long later-reverted edits stayed visible; best as a number on the source card or radar | `revert_event` only |
| Citation history | Editors | Per paragraph: sourced or not, and when it gained or lost a citation | Paragraph lifetimes + `<ref>` tags per version |
| How the story grew | Readers | When key facts, names and sections of an article first appeared | Paragraph lifetimes |
| Meaning drift (stretch) | Editors | Paragraphs whose meaning moved far over many small edits | Old-text vectors + matching paragraphs across rewordings |

Once paragraph lifetimes exist, badges, "what changed" and the lens are mostly queries on the same
table. Ideas needing paragraph history start with a pilot of ~200 articles.

**Parked (no time angle or outside data):** three languages side by side (sv/en have no history),
contradiction finder, source check (needs fetched web pages; ask the organisers).
**Later access routes:** browser extension and MCP server, both on the JSON API.

## Phase 4: scale and polish (open)

Outline only: search over L for timing numbers, re-measure index recall at the new size, paragraph
lifetimes for all articles if the highlight needs them, tidy the page, rehearse the demo.

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| No running database | Done | Local MariaDB per person (README "Local setup"); shared server later |
| Merge conflicts between the two people | Medium | One owner per file, contracts fixed in 1.S, `git pull --rebase`, small commits |
| Verda credits run out (a GPU machine left on all weekend) | Medium | CPU-only machine for the database; GPU only for the embedding hour (Modal bills per second) |
| The two local databases drift apart | Low | Same loaders and the same Parquet files on both; rebuild in ~15 min |
| Embedding without a GPU takes many hours | High | Modal or Verda GPU; time a 20-article pilot first (1.A7) |
| Wikitext cleaning leaves junk in paragraphs | Medium | Read the 3 hero articles early (1.A6) |
| Paragraph and question vectors made differently | High | One shared `app.embed.embed()` for both; five-question check, cosine > 0.99 (1.A7) |
| Our bge-m3 differs from the one that made the S vectors (Ollama) | Low | 2.B1 eval on `article_vector` must reproduce the starter's ~76% |
| Finnish word endings weaken `FULLTEXT` | Low | Tested: prefix terms in boolean mode match other word forms; vector half outvotes over-matches |
| Overnight load fails midway | Medium | Loader is resumable (1.A4) |
| Size: history 7–10 GB, vectors ~4 KB each | Low | D: has 89 GB |
| Naming editors | Medium | Show patterns and diff links, never "vandal" |

## Questions for the organisers and mentors

1. May we use data beyond the provided datasets, such as the web pages articles cite?
2. What must "scaling across datasets" show: a run on L, or measurements plus a plan?
3. Is there a hosted MariaDB for teams, or do we run our own?
4. Which MariaDB feature do you most hope a team uses, and what would disappoint you?
5. How long is the event, and what is the demo format and length?
