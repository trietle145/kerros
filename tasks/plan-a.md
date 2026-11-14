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

### Task 1.A6 (A): passages from the Parquet files

**Description:** `scripts/build_passages.py` reads `data/m/*.parquet` directly (no database), takes
the newest version of each article, cleans the wikitext to plain text (reuse the starter's cleaner),
cuts it into one passage per section (lead included; sections over ~300 words split at
paragraphs; reference and link sections skipped) and writes `data/passages.parquet`
in the 1.0 format. Takes `--limit N` and `--titles`. **Pilot first:** the 3 hero articles,
embedded on the CPU with `app.embed.embed()`, sent to B as both files, so B builds on real
passages from the start.

**Acceptance criteria:**
- [ ] Pilot files (3 hero articles, passages + vectors) sent to B.
- [ ] On 3 hero articles (*Talvisota*, *Suomen sisällissota*, one more) the passages read cleanly:
      no template, table or reference markup left; `heading` NULL only for the lead; no empty texts.
- [ ] Full run finishes; passage count (~67k expected) and distinct `text_hash` count noted.

**Verification:** print 10 random passages and read them; counts in the PR.
**Dependencies:** 1.S. **Files:** `scripts/build_passages.py`, `scripts/wikitext.py`. **Scope:** M.

### Task 1.A7 (A): embed the passages

**Description:** `scripts/embed_passages.py` embeds each distinct passage with `app.embed.embed()`
(input = title \n heading \n text, max 1,024 tokens, normalised) and writes `data/passage_vectors.parquet`. Runs on a GPU
for a few minutes (~67k passages; 1–3 hours on a CPU also works): Modal (per-second billing, $100 per person) or a Verda GPU machine; Colab or
Kaggle as a free fallback. Time it on 20 articles first.

**Acceptance criteria:**
- [ ] 20-article pilot: paragraphs per second measured, full-run time estimated.
- [ ] Full run: one vector per distinct `text_hash`.
- [ ] Five test questions embedded on the GPU machine and on the machine that will serve questions
      give cosine similarity > 0.99 (same model and settings on both).

**Verification:** row count = distinct hash count from 1.A6; the five-question check printed.
**Dependencies:** 1.A6. **Files:** `scripts/embed_passages.py` (uses the shared `app/embed.py`). **Scope:** M.

### Task 1.A8 (A): load paragraphs and vectors

**Description:** `scripts/load_vectors.py` loads `passages.parquet` into `passage` and
`passage_vectors.parquet` into `passage_vector` (each file on its own, whichever exists, so
passages and their FULLTEXT index can go in before the GPU run ends). Set
`mhnsw_ef_search = 80` and measure recall with the starter's `index_recall.py`. Both people run it
on their own database.

**Acceptance criteria:**
- [ ] `passage` and `passage_vector` row counts match the files.
- [ ] Every `passage.text_hash` has a vector.
- [ ] Recall@10 ≥ 95% (if lower, raise `M` or `ef_search` and note the setting).

**Verification:** counts, the join check, and the recall output in the PR.
**Dependencies:** 1.A6 (passages), 1.A7 (vectors). **Files:** `scripts/load_vectors.py`. **Scope:** S.

### Task 2.A1 (A): revert detection

**Description:** `scripts/build_reverts.sql` fills `revert_event` from `article` (sketch in
`docs/architecture.md`). Filter out versions with no `sha1` and blanked pages, which would show up as
false reverts.

**Acceptance criteria:**
- [ ] *Talvisota* shows a revert count in the same range as the starter README's 328.
- [ ] 10 random reverts checked against their Wikipedia diffs look right.

**Verification:** counts per article; the 10 spot checks noted.
**Dependencies:** 1.A5. **Files:** `scripts/build_reverts.sql`. **Scope:** S.

### Task 2.A2 (A): time-view endpoints and stats()

**Description:** `/article/<page_id>?as_of=<date>` returns the article as it stood then (cleaned for
reading); `/article/<page_id>/timeline` returns edits and reverts per month; `stats()` replaces
its stub with real edit and revert counts.

**Acceptance criteria:**
- [ ] AS OF returns the right `rev_id` for 3 dates on *Talvisota*.
- [ ] The timeline matches the edit counts in `article FOR SYSTEM_TIME ALL`.
- [ ] Both answer in under 1 second.

**Verification:** compare against direct SQL; timings logged.
**Dependencies:** 1.S, 2.A1. **Files:** `app/history.py`. **Scope:** S.

### Task 2.A3 (A): time-view pages

**Description:** An article page with a date picker (the as-of reader) and a timeline chart of edits
with reverts marked; picking a month opens the article as of that month.

**Acceptance criteria:**
- [ ] Moving the date changes the text shown and the linked `?oldid=`.
- [ ] Editors appear as patterns and links to diffs, never labelled as vandals.

**Verification:** manual check on the 3 hero articles.
**Dependencies:** 2.A2. **Files:** `app/templates/article.html`, `app/static/history.*`. **Scope:** M.
