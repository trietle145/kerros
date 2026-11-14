# Roadmap from now to the demo (A + B)

Written Sat 14 Nov 2026, ~11:30 Finnish time. **Assumed demo: Sunday 15 Nov morning** (correct
this if the schedule says otherwise). The shared plan (ideas, contracts, ownership) stays in
`tasks/plan.md`; task details already written stay in `plan-b.md`, `plan-graph.md` (B) and
`plan-a.md` (A, on `a-data-time`). This file is the **order and the split from here on**.

## Where we are

| Done | Open |
| --- | --- |
| Server with all data (M history, S vectors, 66,642 passages + vectors, reverts) | **B's base: `search()`, cited answers, ask page: no code yet. This is the critical path.** |
| A's base: passages, embeddings, reverts, `/article` as-of page + timeline, real `stats()` | Phase 3 data: 283k historical texts embedding on Modal now; load + speed test next |
| Phase 3 pilot: "then vs now" works on 3 hero articles (2–8 ms) | Time-aware chat answers, source health, graph add-on, L at scale, polish, demo |

## The split

- **A (Triet): data, time, and the time-aware chat answers.** Everything that needs history:
  the then-vs-now question path end to end (routing, retrieval, diff, the answer text), source
  health, L at scale.
- **B: search, base answers, the pages.** `search()`, cited answers, the ask page, hybrid,
  showing A's time answers on the page, the graph add-on, the UI polish pass.

New contracts (add to `tasks/plan.md` when merged):

| Function | Owner | Shape |
| --- | --- | --- |
| `app.llm.complete(system: str, user: str) -> str` | B (2.B2) | One generic model call, provider from `.env`. A's time answers use it too, so there is one LLM code path. Until it exists A uses a local stub. |
| `app.timeqa.route(question) -> dict \| None` | A | `{"topic": str, "as_of": "YYYY-MM-DD", "compare_to": "YYYY-MM-DD"}` for a time question, `None` otherwise |
| `app.timeqa.answer(question) -> dict` | A | Same JSON as `/ask`, plus `"era": "then"\|"now"` on each source and `"diffs": [{"then": n, "now": m, "html": "..."}]` |

## UI: design now or later?

**Later.** Build plain, working pages now on the stack we have (Flask + Jinja + plain CSS, no
build step); keep the JSON contracts stable so the look can change without touching logic.
Decide only the **page flow** now, because that's what the code depends on:

```
/ (ask)  →  answer with numbered sources  →  source card: History button → /article/<id> (as-of + timeline)
   └─ a time question ("in 2008 ... since?")  →  then / what changed view with diffs, both versions cited
   └─ Graph button (add-on) → /graph/<id>
```

One polish block (B5 below, ~2 h on Sunday morning) gives it a consistent look. Design and demo
are 20% of the score, so that block is protected, but it comes after everything works.

---

## Phase R1: base demo path (now → Sat ~18:00)

### A1: load historical vectors, speed test at full size (in progress)
**Description:** Load the 283k Modal vectors into `history_vector` (`load_vectors.py data/history
--history`), then time the then-vs-now query at ~350k vectors and tune `LIMIT` if too few
candidates survive the time filter.
**Acceptance:** `history_vector` ≈ 350k rows; 3 test questions each return ≥ 5 passages live on
the date; median query < 200 ms. **Verify:** timing script output in `plan-a.md`.
**Files:** `scripts/load_vectors.py`. **Scope:** S.

### A2: housekeeping
**Description:** Reload `passage` on the server without the 117 `#OHJAUS` junk rows (tell B first:
~20 s, passage ids change); merge A's PR; update the server copy.
**Acceptance:** `SELECT COUNT(*) FROM passage WHERE text LIKE 'OHJAUS%'` = 0. **Scope:** XS.

### B1 (= 2.B1): `search()` + eval
As in `plan-b.md`. **Acceptance:** top-5 > 76% on the 37 questions; < 100 ms per search.

### B2 (= 2.B2): cited answers + `complete()`
As in `plan-b.md`, plus the generic `complete(system, user)` from the contract above.
**Acceptance:** 5 fi + 5 en questions answered in their language, every `[n]` valid.

### B3 (= 2.B3) + B4 (= 2.J1): ask page with History buttons
As in `plan-b.md`. **Acceptance:** question → answer → source → History → as-of text, by hand.

### Checkpoint R1 (Sat ~18:00, both)
- [ ] The base demo path works in the browser on the server.
- [ ] A's PR and B's PR merged into `planning`.

---

## Phase R2: the highlight (Sat ~18:00 → night)

### A3: time functions in `app/timeqa.py`
**Description:** `route(question)` (dates + "since/vuonna/nyt" parsed; one small LLM call only if
the rules miss); `then_passages(topic, as_of)` (the pilot query); `counterpart(text_hash)` (nearest
current passage of the same article); `diff(old, new)` (inline word diff, side by side when the
texts are less than ~50% alike).
**Acceptance:** `python -m app.timeqa` runs 5 demo questions: the right dates parsed, passages live
on the date, a counterpart found, readable diffs. **Files:** `app/timeqa.py`. **Scope:** M.

### A4: the then-vs-now answer
**Description:** `answer(question)`: then-passages + diffs → `complete()` writes "In 2008 Wikipedia
said … [n]" and "Since then … [m]", every claim citing the version live then or today.
**Acceptance:** the 5 demo questions get answers whose citations all point at sent passages; works
with the stub before B2 lands. **Dependencies:** A1, A3, B2 (stub until then). **Scope:** S.

### B5a: show time answers on the ask page
**Description:** `/ask` calls `timeqa.route()`; a time question goes to `timeqa.answer()` and the
page shows "then" and "now" side by side with the diff (green added, red removed) and both
version links. **Acceptance:** a time question typed on the page shows the view. **Dependencies:**
A4, B3. **Scope:** S.

### A5: source health (if R2 is on time)
**Description:** `app.history.health(text_hashes)` → "unchanged since 2014", "this section
rewritten N times" (from `passage_history`); "contested" only if cheap. B shows it on source cards
next to `stats()`. **Acceptance:** Talvisota's lead shows a plausible "unchanged since". **Scope:** S.

### B6: hybrid search (= 2.B4)
As in `plan-b.md`, after B5a. **Acceptance:** eval not lower than vector-only.

### Checkpoint R2 (Sat night)
- [ ] A time question works on the page end to end; the 5 demo questions are written down.

---

## Phase R3: scale, add-on, polish, demo (night → Sun morning)

### A6: dataset L at scale (implementation 20%)
**Description:** Markdown passages from L (`build_passages.py`, Markdown path), embed ~2M on Modal
(~1 h on 8 GPUs, ~$10–20), load into separate `l_passage` / `l_vector` tables (kept out of B's
search), measure recall@10 and latency at that size.
**Acceptance:** recall@10 ≥ 95% at ~2M vectors, latency and load times recorded for the slide.
**Scope:** M.

### B7: graph add-on (time-boxed ~2–3 h)
`plan-graph.md` G1–G3 (+ G4 year slider if quick). No vector fill-up; optional grey stubs for
links leaving the dataset; no learning path. Pitch line: *"explore how the sources connect, and
how those connections grew."* A can take G1–G2 (link index + `/api/graph`) if A is ahead.

### B5: UI polish pass (~2 h, protected)
One stylesheet for all pages, a landing state with 3–4 example questions (one time question),
readable on the projector.

### D1 (both): demo script and rehearsal
Pick the hero questions (one plain, one then-vs-now, one History click, one graph); slides with
the numbers (862k versions, 46k reverts, 2M-vector recall/latency, the one-statement SQL); run it
twice in a row without a wait over 3 s.

### Checkpoint R3 (Sun morning)
- [ ] Demo path rehearsed twice; numbers on the slides; server up; instance not deleted yet.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| B's base slips (no code yet) | High | R1 first for B; A takes G1–G2 of the graph and anything else off B's plate |
| No LLM key yet (Claude credits take 1–2 business days) | High | `complete()` switchable: OpenAI credits if they land on the API, or Verda's hosted models (same €200 balance) |
| Time filter leaves too few candidates at 350k vectors | Medium | Raise `LIMIT`, or filter by article first; measured in A1 |
| L embedding too slow or costly | Low | Stop at a subset and extrapolate; scale numbers are what count |
| Graph eats polish time | Medium | Time-boxed; cut G4 first |
