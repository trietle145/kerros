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
| Team | 2 people. Phase 1–2 split: **A = database and history**, **B = paragraphs, vectors and answers**. |
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
| GPU | Embedding runs on a GPU for a few minutes (~67k passages): Modal ($100 per person) or a Verda GPU machine, then the vectors are loaded into the shared database. |

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

```
            A: database and history                 B: paragraphs, vectors, answers
Phase 1     1.A1 Verda machine + docker compose     1.B1 Paragraphs from Parquet (no DB needed)
            1.A2 Tailscale + logins for B           1.B2 Embed on a GPU (Modal / Verda)
            1.A3 Schema + smoke test                1.B3 Download S, write load_s.py
            1.A4 load_m.py, 20-article test         1.B4 Load passages + vectors   (needs 1.A3)
            1.A5 Full M load, overnight             1.B5 Load S vectors            (needs 1.A3)
Phase 2     2.A1 Revert detection  (needs 1.A5)     2.B1 Vector search + eval
            2.A2 Time views + endpoints             2.B2 Cited answers
            2.A3 Page: as-of reader, timeline       2.B3 Page: ask box, sources
                         \____ 2.J1 History button joins both sides ____/
                                     2.B4 Hybrid search (FULLTEXT)
```

The two halves only meet at the database tables and two files whose shape is agreed in task 1.0.
B can work for most of Phase 1 without a running database.

**Working on one shared database:** each person has their own login; bulk loads run on the
database machine itself (fastest); say so before dropping, reloading or changing a table, since
it hits both people at once.

---

## Phase 1: get running (data in)

Goal: one shared MariaDB runs, both people can reach it, and all four data tables are filled.

**Before starting:** claim the Verda, Modal and Claude credits, and ask the MariaDB mentors whether
they host a database for teams (that would replace 1.A1).

### Task 1.0 (both, 15 min): agree the hand-over formats

**Description:** Fix the two files B produces and A's database accepts, and the `.env` keys, so the
halves can be built in parallel.

**Acceptance criteria:**
- [ ] `data/passages.parquet` columns: `page_id, rev_id, title, position, heading, text, text_hash`
      (`text_hash` = SHA-256 of the embedding input `title \n heading \n text`, 32 bytes).
- [ ] `data/passage_vectors.parquet` columns: `text_hash, model, embedding` (1024 float32, normalised).
- [ ] `.env.example` (already committed) has every key both people need.

**Verification:** both people have read and agreed; `.env` is git-ignored.
**Dependencies:** none. **Files:** `.env.example`. **Scope:** XS.

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

### Task 1.A2: B can reach the database

**Description:** Install Tailscale on the machine and both laptops. Set `DB_BIND` in the machine's
`.env` to its Tailscale IP and restart the container, so MariaDB listens only on the Tailscale
network. Create a separate MariaDB login for each person.

**Acceptance criteria:**
- [ ] B runs `SELECT 1` from their laptop against the machine's Tailscale IP with their own login.
- [ ] Connecting to the machine's public IP on port 3306 fails.

**Verification:** B's `mariadb -h <tailscale-ip> -u <user> -p wiki -e "SELECT 1"` works; the same
against the public IP times out.
**Dependencies:** 1.A1. **Files:** setup note in README. **Scope:** XS.

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

### Task 1.B1: passages from the Parquet files

**Description:** `scripts/build_passages.py` reads `data/m/*.parquet` directly (no database), takes
the newest version of each article, cleans the wikitext to plain text (reuse the starter's cleaner),
cuts it into one passage per section (lead included; sections over ~300 words split at
paragraphs; reference and link sections skipped) and writes `data/passages.parquet`
in the 1.0 format. Takes `--limit N` and `--titles`. Run it wherever a copy of M is: A's PC
already has one on D:, the database machine has another.

**Acceptance criteria:**
- [ ] On 3 hero articles (*Talvisota*, *Suomen sisällissota*, one more) the passages read cleanly:
      no template, table or reference markup left.
- [ ] Every row has `rev_id` and `title` (`heading` NULL only for the lead); no empty texts.
- [ ] Full run finishes; passage count (~67k expected) and distinct `text_hash` count noted.

**Verification:** print 10 random passages and read them; counts in the PR.
**Dependencies:** 1.0. **Files:** `scripts/build_passages.py`, `scripts/wikitext.py`. **Scope:** M.

### Task 1.B2: embed the passages

**Description:** `scripts/embed_passages.py` embeds each distinct passage with bge-m3 (input
= title \n heading \n text, max 1,024 tokens, normalised) and writes `data/passage_vectors.parquet`. Runs on a GPU
for a few minutes (~67k passages; 1–3 hours on a CPU also works): Modal (per-second billing, $100 per person) or a Verda GPU machine; Colab or
Kaggle as a free fallback. Time it on 20 articles first.

**Acceptance criteria:**
- [ ] 20-article pilot: paragraphs per second measured, full-run time estimated.
- [ ] Full run: one vector per distinct `text_hash`.
- [ ] Five test questions embedded on the GPU machine and on the machine that will serve questions
      give cosine similarity > 0.99 (same model and settings on both).

**Verification:** row count = distinct hash count from 1.B1; the five-question check printed.
**Dependencies:** 1.B1. **Files:** `scripts/embed_passages.py`, `app/embed.py` (question side, same settings). **Scope:** M.

### Task 1.B3: download S, write its loader (done)

**Description:** Download S from the datasets repo into `data/s/` and check its checksums. Write
`scripts/load_s.py` (from the RAG starter's `load.py`) that loads the shipped article vectors into
`article_vector`.

**Acceptance criteria:**
- [x] S downloaded, checksums verified.
- [x] Loader written and tested against a local file read (database insert happens in 1.B5).

**Verification:** checksum output; loader dry run prints row counts per language.
**Dependencies:** none. **Files:** `scripts/load_s.py`. **Scope:** S.

### Task 1.B4: load paragraphs and vectors

**Description:** `scripts/load_vectors.py` loads `passages.parquet` into `passage` and
`passage_vectors.parquet` into `passage_vector`, then the vector index is built. Set
`mhnsw_ef_search = 80` and measure recall with the starter's `index_recall.py`.

**Acceptance criteria:**
- [ ] `passage` and `passage_vector` row counts match the files.
- [ ] Every `passage.text_hash` has a vector.
- [ ] Recall@10 ≥ 95% (if lower, raise `M` or `ef_search` and note the setting).

**Verification:** counts, the join check, and the recall output in the PR.
**Dependencies:** 1.A3, 1.B2. **Files:** `scripts/load_vectors.py`. **Scope:** S.

### Task 1.B5: load S vectors (done: 0.7 min, ~700 vectors/s with the index built as rows go in)

**Acceptance criteria:**
- [x] `article_vector` has 29,460 rows (19,285 fi + 4,921 sv + 5,254 en).
- [x] Nearest articles to *Talvisota*'s vector are about the Winter War (Talvisodan tausta,
      Jatkosota, Välirauha, Moskovan rauhansopimus).

**Verification:** `python scripts/load_s.py --verify` (count and the neighbour query). Log:
`data/load_s.log`.
**Dependencies:** 1.A3, 1.B3. **Files:** none. **Scope:** XS.

### Checkpoint: Phase 1 done

- [ ] B can query all tables from their own machine.
- [ ] `article` holds all 862,076 versions; `passage`, `passage_vector`, `article_vector` are filled.
- [ ] Paragraph count, embedding time and load time are written into this file (replacing the estimates).
- [ ] Review together before Phase 2.

---

## Phase 2: the base (basic RAG + time views)

Goal: a web page where a question gets a cited answer, and each source opens its article's history.
This is the base the time highlight is built on.

### Task 2.B1: vector search and evaluation

**Description:** `app/db.py` returns the top 8 paragraphs for a question (vector search in a
subquery, joined to `passage` afterwards, at most 2 per article). `eval/evaluate.py` runs the
starter's 37 test questions.

**Acceptance criteria:**
- [ ] Right article in the top 5 for more than 76% of the 37 questions (the starter's score).
- [ ] One search takes under 100 ms on the database side.

**Verification:** `python eval/evaluate.py` prints top-5 / top-10 hit rates.
**Dependencies:** 1.B4. **Files:** `app/db.py`, `eval/evaluate.py`. **Scope:** S.

### Task 2.B2: cited answers

**Description:** `app/llm.py` sends the question and numbered paragraphs to the cloud model, which
answers in the question's language with `[n]` after every sentence. The code checks every `[n]`
exists and flags sentences without one.

**Acceptance criteria:**
- [ ] 5 questions in Finnish and 5 in English get answers in their own language.
- [ ] Every citation points to a paragraph that was sent; uncited sentences are flagged.
- [ ] The provider and model come from `.env`.

**Verification:** a script that runs the 10 questions and prints answers with sources; read by hand.
**Dependencies:** 2.B1. **Files:** `app/llm.py`. **Scope:** S.

### Task 2.B3: ask page

**Description:** Flask `/ask` (JSON) and a page: question box, answer, numbered sources with title,
section and a link to `https://fi.wikipedia.org/?oldid=<rev_id>`. `/ask` accepts an `as_of` date and
ignores it for now.

**Acceptance criteria:**
- [ ] A question typed on the page shows a cited answer and working source links.
- [ ] `/ask` returns the same as JSON.

**Verification:** manual check in the browser on 3 questions.
**Dependencies:** 2.B2. **Files:** `app/main.py`, `app/templates/`. **Scope:** M.

### Task 2.B4: hybrid search

**Description:** Add the `FULLTEXT` half (boolean mode, prefix terms built from the question in
Python: Kekkonen → `Kekko*`) and fuse both rankings by RRF (k = 60, top 50 per side) in one SQL
statement with `UNION ALL` + `GROUP BY` (no FULL OUTER JOIN in MariaDB). See `docs/architecture.md`.

**Acceptance criteria:**
- [ ] Evaluation score is not lower than vector-only; both numbers recorded.
- [ ] A question with an exact name or year (e.g. "president 1956–1982") finds the right paragraph.

**Verification:** `eval/evaluate.py` run for both modes.
**Dependencies:** 2.B1. **Files:** `app/db.py`. **Scope:** S.

### Task 2.A1: revert detection

**Description:** `scripts/build_reverts.sql` fills `revert_event` from `article` (sketch in
`docs/architecture.md`). Filter out versions with no `sha1` and blanked pages, which would show up as
false reverts.

**Acceptance criteria:**
- [ ] *Talvisota* shows a revert count in the same range as the starter README's 328.
- [ ] 10 random reverts checked against their Wikipedia diffs look right.

**Verification:** counts per article; the 10 spot checks noted.
**Dependencies:** 1.A5. **Files:** `scripts/build_reverts.sql`. **Scope:** S.

### Task 2.A2: time-view endpoints

**Description:** `/article/<page_id>?as_of=<date>` returns the article as it stood then (cleaned for
reading); `/article/<page_id>/timeline` returns edits and reverts per month.

**Acceptance criteria:**
- [ ] AS OF returns the right `rev_id` for 3 dates on *Talvisota*.
- [ ] The timeline matches the edit counts in `article FOR SYSTEM_TIME ALL`.
- [ ] Both answer in under 1 second.

**Verification:** compare against direct SQL; timings logged.
**Dependencies:** 1.A5, 2.A1. **Files:** `app/db.py` (time queries), `app/main.py`. **Scope:** S.

### Task 2.A3: time-view pages

**Description:** An article page with a date picker (the as-of reader) and a timeline chart of edits
with reverts marked; picking a month opens the article as of that month.

**Acceptance criteria:**
- [ ] Moving the date changes the text shown and the linked `?oldid=`.
- [ ] Editors appear as patterns and links to diffs, never labelled as vandals.

**Verification:** manual check on the 3 hero articles.
**Dependencies:** 2.A2. **Files:** `app/templates/`, `app/static/`. **Scope:** M.

### Task 2.J1 (both): History button

**Description:** Each source card under an answer shows "N edits, M reverts" and a History button
that opens 2.A3 for that article.

**Acceptance criteria:**
- [ ] From a question, one click reaches the source's timeline, and one more reaches its text on a chosen date.

**Verification:** walk the full demo path by hand: question → answer → source → history → as-of text.
**Dependencies:** 2.B3, 2.A3. **Files:** `app/templates/`. **Scope:** S.

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
| No running database | High | 1.A1 first: shared machine with docker compose; A's PC (D:) as fallback |
| Verda credits run out (a GPU machine left on all weekend) | Medium | CPU-only machine for the database; GPU only for the embedding hour (Modal bills per second) |
| Someone breaks the shared database for both | Medium | Own logins; announce drops and reloads; loaders are resumable |
| Embedding without a GPU takes many hours | High | Modal or Verda GPU; time a 20-article pilot first (1.B2) |
| Wikitext cleaning leaves junk in paragraphs | Medium | Read the 3 hero articles early (1.B1) |
| Paragraph and question vectors made differently | High | Five-question check, cosine > 0.99 (1.B2) |
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
