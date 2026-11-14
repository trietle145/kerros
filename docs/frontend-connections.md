# Frontend connections: who calls what, and what is live

Written 2026-11-14 from the code (`frontend` branch and `origin/a-data-time` at 811780f) and from
calls against Flask on this PC. Contract: `docs/frontend.md`; graph contract: `tasks/plan-graph.md`
(branch `b-search-app`). The browser only calls `app/static/api.js`; nothing else does `fetch`.

## Call chains

| `api.js` call | Flask route (file, owner) | State | Behind it | MariaDB |
| --- | --- | --- | --- | --- |
| `ask(q, asOf)` | `GET /ask?q=&as_of=` (`app/answer.py`, A) | **Stub** on `frontend` (one fixed Talvisota answer). **Live** on `a-data-time`, plain answers only | `app/search.py`: bge-m3 embeds the question in the Flask process, then one SQL statement fuses three lists by RRF → `app/llm.py`: one Claude call → `app/history.py` `stats()` | `passage_vector`, `passage` (FULLTEXT), `article_vector`; `article FOR SYSTEM_TIME ALL` + `revert_event` for the counts |
| `ask` with a dated question | same route | **Planned** (A4, `app/timeqa.py` does not exist yet) | `as_of` is read and ignored; `kind` is always `"plain"` | later: `passage_history FOR SYSTEM_TIME AS OF` |
| `related(q)` | `GET /api/related?q=` (`app/graph.py`, G3) | **Missing** (404) | planned: `search(q, k=20)` grouped by article | as `/ask` |
| `graph(pageId)` | `GET /api/graph/<page_id>` (`app/graph.py`, G1/G2/G4) | **Missing** (404) | planned: in-memory link index + node choice + yearly snapshots; `tools/make_fixtures.py` already does exactly this | `article` (current and `AS OF` year ends), `article_vector`, `passage`, `revert_event` |
| `path(pageId, q)` | `GET /api/graph/<id>/path?q=` (`app/graph.py`, G5) | **Missing** (404) | planned: one LLM call, heuristic fallback | none new |
| *History* link (page, not `api.js`) | `GET /article/<page_id>` (`app/history.py`, A) | **Live** | `scripts/wikitext.clean` | `article FOR SYSTEM_TIME AS OF`, `revert_event` |
| *Graph* link (page) | `GET /graph/<page_id>?q=` (`app/ask.py`, B) | Live (page only) | — | none |

`app/graph.py` is not in any branch, and `app/main.py` (frozen, A) must register its blueprint.
Until then the three graph calls always get fixtures.

## Where it runs

- **Local development:** browser → Flask on this PC (`flask --app app.main run`, default port 5000)
  → MariaDB through the SSH tunnel on `127.0.0.1:3307` (settings in `.env`). The question is
  embedded on this PC: with A's search merged, the first `/ask` loads bge-m3 and needs ~5 GB free
  memory (see `app/embed.py`); the model call needs `LLM_API_KEY` in `.env`. Both packages
  (`sentence-transformers`, `anthropic`) are already in `.venv`.
- **Deployed app:** `ssh -N -L 5000:127.0.0.1:5000 root@135.181.8.213`, then
  http://127.0.0.1:5000: browser → tunnel → Flask on the Verda server → MariaDB on the same
  machine. It serves the server's copy of the repo (A's branch, updated from a git bundle), so
  this branch's pages, `api.js` and fixtures appear there only after a merge and a redeploy. Not
  checked from this PC (no SSH from the agents); `docker-compose.yml` on `a-data-time` has only the
  `db` service, so how Flask is started on the server is A's knowledge.
- The tunnel to the deployed app and a local Flask both want port 5000: run the local one with
  `--port 5001` when both are open.

## What `api.js` does when a call does not work (checked)

| Live result | `api.js` | Seen |
| --- | --- | --- |
| 200 JSON | returns it with `_source: "live"` | fake server |
| 404 / 405 (route missing) | fixture, `_source: "fixture"`, `_error: "HTTP 404"` | Flask, `/api/graph/1256` → 404 → `graph-1256.json` |
| 5xx, HTML or JSON | fixture, `_error` = the JSON's `error` or `"HTTP 500"` | Flask with the database down |
| network error, timeout (60 s `ask`, 30 s `path`, 15 s others) | fixture, `_error` = the reason | fake server that never answers: fixture after 15.0 s |
| other 4xx (400, 422) | rejects with `Error(<error from the JSON>)` | fake server |
| `?mock=1` on the page URL | fixture, no live call | Flask |

An unknown `page_id` gets `graph-1256.json` / `path-1256.json`, so compare `data.main` with the id
you asked for. The UI should show `_error` next to the "sample data" hint: a failed live answer
otherwise looks like an answer to a different question.

## Mismatches and gaps the frontend must survive

1. **No `/api/related`, `/api/graph`, `/api/graph/<id>/path`** anywhere yet (404, Flask's HTML page).
2. **Then-vs-now is fixture-only.** No live response has `kind: "then_vs_now"`, `as_of`,
   `compare_to`, `diffs` or `sources[].era`; `health` does not exist either. Then-vs-now sources in
   the contract carry no `passage_id` or `score`: do not rely on them.
3. **Error shapes differ.** Contract: 400 and 500 as `{"error"}`. A's new code also returns
   **422** `{"error": "the model declined to answer this question"}` (not in the contract), and its
   500 is JSON `{"error": "answering failed: <Type>: <detail>"}`. The stub on `frontend` has no
   error handling: with the database down it returns Flask's **HTML** 500 page (measured, after
   ~2 s). `/article/<id>` pages fail the same way, and no script can catch a page navigation.
4. **Real answers are bigger than the examples:** 8 sources (at most 2 per article), 2 to 5
   sentences, `text` is the whole passage (up to ~300 words, paragraphs separated by `\n`),
   `heading` is `null` for the lead, `score` is an RRF sum (about 0.01 to 0.05; never show it as a
   percentage). Several sources are usually not cited by any sentence.
5. **Uncited and empty cases are real:** a sentence can have `cites: []`; when search finds
   nothing the answer is one English sentence with `sources: []`.
6. **Language:** the answer follows the question's language (fi, sv, en); passages stay Finnish.
7. **Timing:** 2 to 8 s per answer (`docs/frontend.md`; not measured here, the database was down),
   longer for the first question after a restart, which also loads bge-m3. Show progress, and
   disable the form while waiting. Graph fixtures are 28 to 50 KB and load at once; the planned
   live `/api/graph` builds its link index on first use (~7 s, plan-graph.md).
8. **Graph data facts** (same in fixtures and the planned route): `snapshots[year].links` holds
   real wiki links only, both ends present that year. A `related` node has no link to the main
   node, so the renderer must draw the dashed line itself from `relation`. A node's first year is
   `created`; nodes older than the main article are in every snapshot. `lead` can be empty or
   start with leftover image markup (e.g. Karjalankannas, `thumb|325px|…`).
9. **Fixture differences from live data:** `related*.json` ranks by article-vector similarity to
   one article (`score` = 1 − cosine distance, so near 1, unlike the live RRF score); answer
   sentences and `score` values in `ask-*.json` are hand-written around real passages, revision
   ids and counts; `ask-plain.json` passages are cut after a few sentences.

## Regenerating the fixtures

`.venv\Scripts\python.exe tools\make_fixtures.py` (database tunnel open; SELECT only, ~30 s) rewrites
`related*.json` and the `graph-*`/`path-*` pairs and checks each one. `ask-*.json` are edited by hand.
