# Plan B: search, answers and app

Owner: **B**. Branch: `b-search-app`, merged into `planning` by PR. Tick your boxes here.
The shared plan (idea, decisions, who owns which file, contracts, risks) is `tasks/plan.md`.

**Order:** 2.B1 eval on `article_vector` (S vectors are already loaded; proves the question
embedding) → 2.B2 cited answers on A's pilot passages → 2.B3 ask page → 2.B1 again on all
passages when A sends them → 2.B4 hybrid → 2.J1 History button (after A's 2.A2) → 2.B5 reranker
if time allows.

**You own:** `app/search.py`, `app/rerank.py`, `app/llm.py`, `app/ask.py`,
`app/templates/ask.html`, `app/static/ask.*`, `eval/`. **You call, don't edit:** `app/embed.py`,
`app/db.py`, `app.history.stats()`. Load A's Parquet files with `scripts/load_vectors.py`.

**Until A's files arrive:** `app/ask.py` returns a fixed example in the `/ask` JSON shape; keep
that shape when you replace it.

---

### Task 2.B1 (B): vector search and evaluation

**Description:** `app/search.py` `search()` returns the top 8 paragraphs for a question (vector
search in a subquery, joined to `passage` afterwards, at most 2 per article). `eval/evaluate.py`
runs the starter's 37 test questions. **Starts before passages exist:** the eval runs first
against `article_vector` (already loaded; article-level, same as the starter), and `search()`
runs on A's pilot passages. Switch both to all passages when 1.A8 lands; only the table changes.

**Acceptance criteria:**
- [ ] Eval on `article_vector` reproduces the starter's ~76% top-5 (proves our question embedding
      matches the shipped vectors).
- [ ] On passages: right article in the top 5 for more than 76% of the 37 questions.
- [ ] One search takes under 100 ms on the database side.

**Verification:** `python eval/evaluate.py` prints top-5 / top-10 hit rates.
**Dependencies:** 1.S (start); 1.A8 (passage numbers). **Files:** `app/search.py`, `eval/evaluate.py`. **Scope:** S.

### Task 2.B2 (B): cited answers

**Description:** `app/llm.py` sends the question and numbered paragraphs to the cloud model, which
answers in the question's language with `[n]` after every sentence. The code checks every `[n]`
exists and flags sentences without one.

**Acceptance criteria:**
- [ ] 5 questions in Finnish and 5 in English get answers in their own language.
- [ ] Every citation points to a paragraph that was sent; uncited sentences are flagged.
- [ ] The provider and model come from `.env`.

**Verification:** a script that runs the 10 questions and prints answers with sources; read by hand.
**Dependencies:** 1.S, pilot passages from 1.A6 (not the full search). **Files:** `app/llm.py`. **Scope:** S.

### Task 2.B3 (B): ask page

**Description:** Flask `/ask` (JSON, shape in "Contracts") and a page: question box, answer,
numbered sources with title, section, `stats()` numbers and a link to
`https://fi.wikipedia.org/?oldid=<rev_id>`. `/ask` accepts an `as_of` date and ignores it for now.

**Acceptance criteria:**
- [ ] A question typed on the page shows a cited answer and working source links.
- [ ] `/ask` returns the same as JSON.

**Verification:** manual check in the browser on 3 questions.
**Dependencies:** 2.B2. **Files:** `app/ask.py`, `app/templates/ask.html`, `app/static/ask.*`. **Scope:** M.

### Task 2.B4 (B): hybrid search

**Description:** Add the `FULLTEXT` half (boolean mode, prefix terms built from the question in
Python: Kekkonen → `Kekko*`) and fuse both rankings by RRF (k = 60, top 50 per side) in one SQL
statement with `UNION ALL` + `GROUP BY` (no FULL OUTER JOIN in MariaDB). See `docs/architecture.md`.

**Acceptance criteria:**
- [ ] Evaluation score is not lower than vector-only; both numbers recorded.
- [ ] A question with an exact name or year (e.g. "president 1956–1982") finds the right paragraph.

**Verification:** `eval/evaluate.py` run for both modes.
**Dependencies:** 2.B1; passages loaded (1.A8, passages half). **Files:** `app/search.py`. **Scope:** S.

### Task 2.B5 (B, optional): reranker, measured

**Description:** `app/rerank.py` reorders the fused top 50 with a cross-encoder (e.g.
bge-reranker-v2-m3) before keeping 8. Kept only if it pays for its CPU time.

**Acceptance criteria:**
- [ ] Eval with and without the reranker recorded, plus the added latency per question.
- [ ] Switched by one `.env` key (`RERANK_MODEL`, empty = off); kept on only if top-5 improves.

**Verification:** `eval/evaluate.py` for both settings.
**Dependencies:** 2.B4. **Files:** `app/rerank.py`, `app/search.py`. **Scope:** S.

### Task 2.J1 (B, with A's stats()): History button

**Description:** Each source card under an answer shows "N edits, M reverts" (from `stats()`) and
a History button linking to `/article/<page_id>`. Only B's files change; A's side is the contract.

**Acceptance criteria:**
- [ ] From a question, one click reaches the source's timeline, and one more reaches its text on a chosen date.

**Verification:** walk the full demo path by hand: question → answer → source → history → as-of text.
**Dependencies:** 2.B3, 2.A2 (real numbers), 2.A3 (page to land on). **Files:** `app/templates/ask.html`. **Scope:** S.
