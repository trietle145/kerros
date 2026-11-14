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
