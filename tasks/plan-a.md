# Plan A: data and time

Owner: **A**. Branch: `a-data-time`, merged into `planning` by PR. Tick your boxes here.
The shared plan (idea, decisions, who owns which file, contracts, risks) is `tasks/plan.md`.

**Order:** 1.A6 pilot (3 hero articles, passages + CPU vectors, send both files to B) → 1.A6 full
run → load passages (B can then build FULLTEXT) → 1.A7 GPU embedding, and 2.A1 reverts while it
runs → 1.A8 load vectors, send `passage_vectors.parquet` to B → 2.A2 endpoints + real `stats()` →
2.A3 pages.

**You own:** `schema.sql`, `scripts/*`, `app/history.py`, `app/templates/article.html`,
`app/static/history.*`. **You call, don't edit:** `app/embed.py`, `app/db.py`.

**B needs from you, in this order:** pilot files → `passages.parquet` → `passage_vectors.parquet`
→ real `stats()` (2.A2) → `/article/<page_id>` page (2.A3).

---

### Task 1.A2: B can reach the database (deferred: each person runs a local MariaDB for now)

**Description:** Install Tailscale on the machine and both laptops. Set `DB_BIND` in the machine's
`.env` to its Tailscale IP and restart the container, so MariaDB listens only on the Tailscale
network. Create a separate MariaDB login for each person.

**Acceptance criteria:**
- [ ] B runs `SELECT 1` from their laptop against the machine's Tailscale IP with their own login.
- [ ] Connecting to the machine's public IP on port 3306 fails.

**Verification:** B's `mariadb -h <tailscale-ip> -u <user> -p wiki -e "SELECT 1"` works; the same
against the public IP times out.
**Dependencies:** 1.A1. **Files:** setup note in README. **Scope:** XS.

### Task 1.A6 (A): passages (done 2026-11-14, except sending the pilot to B)

**Result:** 19,699 articles (43 redirects skipped, 5 with no text left) → **66,642 passages**,
all distinct texts; median 79 words, 95% under 265, 10 over 300 (single long paragraphs, kept
whole). 20 s for all of them. Markup left in 48 passages (<0.1%). Pilot: Talvisota, Suomen
sisällissota, Jatkosota → 163 passages, embedded on the CPU in 4.2 min, in `data/pilot/`.
Test questions find the right section ("Milloin talvisota alkoi?" → Talvisota lead).

**Description:** `scripts/build_passages.py` reads the current rows of `article` (= M's newest
version of each article; one query, 20 s, instead of scanning 12 GB of Parquet), cleans the
wikitext to plain text with `scripts/wikitext.py` (the SVT starter's cleaner plus heading levels,
entities, galleries, soft hyphens),
cuts it into one passage per section (lead included; sections over ~300 words split at
paragraphs; reference and link sections skipped) and writes `data/passages.parquet`
in the 1.0 format. Takes `--titles`, `--out` and `--show N`. **Pilot first:** the 3 hero articles,
embedded on the CPU with `app.embed.embed()`, sent to B as both files, so B builds on real
passages from the start.

**Acceptance criteria:**
- [ ] Pilot files (3 hero articles, passages + vectors) sent to B. (Made: `data/pilot/`; send them.)
- [x] On 3 hero articles (*Talvisota*, *Suomen sisällissota*, Jatkosota) the passages read cleanly:
      no template, table or reference markup left; `heading` NULL only for the lead; no empty texts.
- [x] Full run finishes; passage count (~67k expected) and distinct `text_hash` count noted.

**Verification:** print 10 random passages and read them; counts in the PR.
**Dependencies:** 1.S. **Files:** `scripts/build_passages.py`, `scripts/wikitext.py`. **Scope:** M.

### Task 1.A7 (A): embed the passages (done 2026-11-14)

**Result:** all 66,642 passages embedded on Modal (up to 4 × A10G) in **6.4 min, 174
passages/s**; `data/passage_vectors.parquet`, 276 MB. Run: `modal run scripts/modal_embed.py`
(only `embed()` runs remotely; image has bge-m3 baked in, revision pinned). GPU = CPU checked
two ways: pilot 163 passages embedded both ways, cosine 1.00000; 5 random stored GPU vectors
re-embedded locally, cosine 1.0.

**Description:** `scripts/embed_passages.py` embeds each distinct passage with `app.embed.embed()`
(input = title \n heading \n text, max 1,024 tokens, normalised) and writes `data/passage_vectors.parquet`. Runs on a GPU
for a few minutes (~67k passages): Modal (per-second billing, $100 per person) or a Verda GPU machine; Colab or
Kaggle as a free fallback. The script exists (written for the pilot) and checks every hash
against its input before embedding. **CPU measured: 0.7 passages/s** on A's laptop (pilot,
median 174 words), so the full 66,642 would take roughly 12–25 hours: GPU needed.

**Acceptance criteria:**
- [x] 20-article pilot: paragraphs per second measured, full-run time estimated. (3 hero
      articles: CPU 0.7/s; GPU run then measured directly.)
- [x] Full run: one vector per distinct `text_hash`.
- [x] GPU vectors and vectors from the machine that serves questions match, cosine > 0.99
      (passages instead of five questions: same function, stronger check).

**Verification:** row count = distinct hash count from 1.A6; GPU vs CPU cosine printed.
**Note:** any process that embeds needs ~5 GB free memory while bge-m3 loads; short of it,
loading fails with misleading errors (see `app/embed.py`).
**Dependencies:** 1.A6. **Files:** `scripts/embed_passages.py` (uses the shared `app/embed.py`). **Scope:** M.

### Task 1.A8 (A): load paragraphs and vectors (done 2026-11-14)

**Result:** passages 0.3 min, vectors 2.7 min (~400/s with the index built as rows go in).
recall@10 **99.4–99.8%** at ef_search 80 (M=16 holds at 66k vectors); search median 11–17 ms
warm, ~0.3–0.5 s for the first queries after a restart (index cache cold). Real questions find
the right article in fi and sv ("Mitä tapahtui Mainilassa 1939?" → Mainilan laukaukset).

**Description:** `scripts/load_vectors.py` loads `passages.parquet` into `passage` and
`passage_vectors.parquet` into `passage_vector` (each file on its own, whichever exists, so
passages and their FULLTEXT index can go in before the GPU run ends). Recall is measured inside
the script like the starter's `index_recall.py` (exact top 10 with `IGNORE INDEX` vs the
index's top 10, 50 random stored vectors as queries). Both people run it on their own database.

**Acceptance criteria:**
- [x] `passage` and `passage_vector` row counts match the files.
- [x] Every `passage.text_hash` has a vector.
- [x] Recall@10 ≥ 95% (if lower, raise `M` or `ef_search` and note the setting).

**Verification:** `python scripts/load_vectors.py --verify` (counts, the join check, recall).
**Dependencies:** 1.A6 (passages), 1.A7 (vectors). **Files:** `scripts/load_vectors.py`. **Scope:** S.

### Task 2.A1 (A): revert detection (done 2026-11-14, on the server)

**Result:** **46,015 reverts in 6,856 articles**, built in 16 s by one `INSERT ... SELECT`
(window functions over all 862,076 versions). 31,519 (68%) undid an anonymous edit, i.e. mostly
vandalism cleanup. *Talvisota*: **328**, exactly the starter's number. Excluded as the reverting
version: 483 versions with no sha1 (hidden by admins) and 202 blanked ones. 82% of detected
reverts have an undo/rollback/review-reject edit summary (*Kumottu*, *kumottiin*, *Hylättiin*,
*rv*, *PAL*) against 3% of other edits.

**Description:** `scripts/build_reverts.py` fills `revert_event` from `article` with the SQL
from `docs/architecture.md`, done without a self-join (LEAD gives the first undone editor). One
file instead of a `.sql`, so it carries its own check.

**Acceptance criteria:**
- [x] *Talvisota* shows a revert count in the same range as the starter README's 328. (328.)
- [x] 10 random reverts checked against their Wikipedia diffs look right. (9 carry a revert
      summary; the 10th is 5 named edits undone after 2 min with no summary, likely a self-revert.)

**Verification:** `python scripts/build_reverts.py --verify 30`: 30 random articles + Talvisota
recomputed in plain Python, all identical to the table.
**Dependencies:** 1.A5. **Files:** `scripts/build_reverts.py`. **Scope:** S.

### Task 2.A2 (A): time-view endpoints and stats() (done 2026-11-14)

**Result:** Talvisota as of 2005/2015/2025 → the right `rev_id` in 10–138 ms; timeline 234
months, 2,143 edits, 328 reverts, 7 ms; `stats()` 7 ms for 4 pages, unknown pages get zeros
(B's source cards now show real numbers with no change on their side). Bad `as_of` → 400,
before the article existed → 404.

**JSON shapes** (for 2.A3 and B): `/article/<id>?as_of=` → `{page_id, title, rev_id, as_of,
valid_from, valid_to (null = still current), user, comment, url, blocks: [[kind, text], ...]}`
with kind `p`, `li`, `h2`, `h3`...; `/article/<id>/timeline` → `{page_id, months: [{month:
"YYYY-MM", edits, reverts, cleanup}]}` (cleanup = reverts that undid an anonymous edit).

**Description:** `/article/<page_id>?as_of=<date>` returns the article as it stood then (cleaned for
reading); `/article/<page_id>/timeline` returns edits and reverts per month; `stats()` replaces
its stub with real edit and revert counts.

**Acceptance criteria:**
- [x] AS OF returns the right `rev_id` for 3 dates on *Talvisota*.
- [x] The timeline matches the edit counts in `article FOR SYSTEM_TIME ALL`.
- [x] Both answer in under 1 second.

**Verification:** `python -m app.history` (compares with direct SQL, asserts timings, 400/404).
**Dependencies:** 1.S, 2.A1. **Files:** `app/history.py`. **Scope:** S.

### Task 2.A3 (A): time-view pages (done 2026-11-14, functional; visual polish later)

**Result:** `/article/<id>` renders the page (JSON with `&format=json`): SVG timeline of every
month (sqrt-scaled bars, reverts split into named-editor vs anonymous-cleanup, each bar a link
to the article as of that month's end), native date picker, version box (saved / replaced /
summary / diff link, no user names), cleaned article text. 44–63 ms per page on the server.

**Description:** An article page with a date picker (the as-of reader) and a timeline chart of edits
with reverts marked; picking a month opens the article as of that month.

**Acceptance criteria:**
- [x] Moving the date changes the text shown and the linked `?oldid=`.
- [x] Editors appear as patterns and links to diffs, never labelled as vandals.

**Verification:** manual check on the 3 hero articles (functionality confirmed by Triet);
`python -m app.history` asserts the oldid changes with the date.
**Dependencies:** 2.A2. **Files:** `app/templates/article.html`, `app/static/history.*`. **Scope:** M.

---

## Phase 3 pilot: time-aware retrieval (level B), 2026-11-14

Question type from the brief: *"what did Wikipedia say about this in 2015, and what has changed
since?"* Time is a **filter** (system-versioned lifetimes), not something mixed into the vectors:
the date is stripped from the question before embedding.

**Sizing pilot** (real chunking rule over every version, 3 hero + 200 random articles): 0
mismatches between old-version splitting and today's hashes, so historical vectors line up with
the current ones. Extrapolated to all 862,076 versions: ~350–450k distinct texts alive ≥ 1 day
(5–7× today's 66,642), ~40 min on Modal with 4 GPUs (~15 with 12), ~2 GB of vectors, chunking
~70 min on one core.

**End-to-end pilot** (3 hero articles, `scripts/build_history.py 1256 1150 440`):
- `passage_text` 6,238 texts, `passage_history` (system-versioned) 8,002 lifetimes, built in
  4 min. `--verify`: for 15 versions 2003–2026, `FOR SYSTEM_TIME AS OF` returns exactly that
  version's passages.
- 3,459 texts embedded on Modal in 0.9 min, into a separate `history_vector` table (kept out of
  B's `passage_vector` until B's search exists).
- Query: vector search `LIMIT 200` in a subquery, then `JOIN passage_history FOR SYSTEM_TIME AS
  OF`, then the article version live on that date for the citation: **2–8 ms** (3,622 vectors).
- "What changed since": today's counterpart found **by meaning** (nearest current passage of the
  same article, distance 0.00–0.16), not by heading; headings get renamed. Then a word diff.
  Real finds: Red terror victims "noin 1 650" → "1 400–1 650"; prisoners "noin 80 000" →
  "76 000" plus a new sentence on ~10,000 Reds fleeing; "Moskovan neuvottelut" (2008) is now
  "Suomen ja Neuvostoliiton neuvottelut aluemuutoksista".

**Still open before the full run:**
- Speed and survivor count at ~400k vectors (LIMIT 200 then the time filter; raise the LIMIT if
  too few candidates survive).
- Rewritten paragraphs make a messy inline diff: show side by side when similarity is low.
- Retrieval quality of the topic part is B's search (hybrid, eval); the pilot used plain vectors.
- Citation-drop signal (for source-health badges) exists but needs filtering: refs moving
  between reference sections, and blankings that were reverted.

**Full run** = `scripts/build_history.py <all page ids>` (to parallelise first) →
`modal run scripts/modal_embed.py --src data/history/passages.parquet` → load `history_vector`.
