# Frontend: pages and API

The pages are plain HTML, CSS and JavaScript in `app/templates` and `app/static`, served by Flask
(`app/ask.py` for the page routes). No build step; a library only from a CDN with an exact version
pinned. The browser gets all data from the JSON routes below through `app/static/api.js`; nothing
else calls `fetch`, and the frontend never touches the database.

## Rules every page keeps

1. **CC BY-SA:** every piece of Wikipedia text links to the exact version it came from
   (`https://fi.wikipedia.org/?oldid=<rev_id>`); the footer names the licence.
2. **No editor names, never "vandal".** Patterns (counts, "often restored") and diff links only.
3. **UI in English, article text in Finnish.** Answers come in the question's language; passages
   can be machine-translated on request (`/api/translate`, Opus-MT on our server).
4. Keyboard-usable, readable on a projector, works at laptop and phone width; reduced motion
   respected.

## Pages

| Page | What it does | Data |
| --- | --- | --- |
| `/` Ask | Question box with example questions. The answer is sentences with `[n]` markers: hover previews the passage, click opens its card (a bottom sheet on phones); uncited sentences are marked. Source chips list every source with health dots and an "also in English / only in Finnish" pill. A **rewind slider** shows each cited passage as it read at the end of any year since 2003. Then-vs-now answers show "then" and "now" sources and word diffs. An "Other Wikipedias add" block lists what en/sv Wikipedia say that the cited Finnish articles don't. "Show in English / Finnish" translates the answer sentence by sentence. | `/ask`, `/api/health`, `/api/rewind`, `/api/translate` |
| `/article/<id>` | Edit timeline per month (named-editor reverts vs anonymous cleanup); click a month or pick a date to read the article as it stood then; the version box links that exact version and its diff; "Explain this edit". | template variables, `/api/explain/<id>/<rev>` |
| `/compare/<id>` | The Finnish article next to its English and Swedish counterparts, section by section: each en/sv paragraph with its closest Finnish one and a label (covered, partly, in another Finnish article, lost, missing). | template variables (`app/xlang.py`) |
| `/graph/<id>` | Force-directed graph of the article and its linked neighbours (real wiki links), with a year slider: nodes and links as they were that year. | `/api/graph/<id>`, `/api/graph/<id>/path`, `/api/related` |
| `/drift` | Which words Finnish Wikipedia used for a topic (civil war / war of liberation, prison / concentration camps, …), year by year, and the edits where one word replaced another. | `app/static/drift.json` (built by `tools/make_drift.py`) |
| `/tools` | Editor tools: citation finder, contradiction finder, edit-war radar. | `/api/cite`, `/api/contradictions/<id>`, `/api/radar` |

## API

All routes are same-origin JSON. Errors are `{"error": "..."}` with 400 (bad input), 404 (unknown
article), 422 (the model declined), 429 (answer caps: `ASK_HOURLY_PER_VISITOR` per IP, `ASK_DAILY_LIMIT` a day), 500 (model or
database down).

| Route | Returns |
| --- | --- |
| `GET/POST /ask?q=[&as_of=YYYY-MM-DD]` | cited answer (shape below); ~3 s, ~8–17 s for then-vs-now |
| `GET/POST /ask/l?q=` | the same over dataset L (all 568k articles), plus `"scope": "l"`; no passage ids, so no health or rewind |
| `GET /article/<id>?as_of=&format=json` | one version: `rev_id, valid_from, valid_to, comment, url, blocks` |
| `GET /article/<id>/timeline` | `{"months": [{"month", "edits", "reverts", "cleanup"}]}` |
| `GET /api/health?ids=1,2` | per passage: `live_since`, `first_seen`, `rewrites`, `comebacks`, `restored`, `contested` |
| `GET /api/rewind?ids=1,2` | per passage: `years[]` (`state` same / changed / absent / no_article, `rev_id`, `hash`) and `versions{hash: {text, similarity, ops}}` |
| `GET /api/xlang/<id>` | en/sv paragraphs of one Finnish article, labelled, in article order |
| `GET /api/graph/<id>` | `main`, `nodes` (`relation` main / mutual / out / in), `years`, `snapshots[year]` (`revs`, `links`), `outside` |
| `GET /api/graph/<id>/path` | up to 4 shown nodes as a reading path (heuristic, no model call) |
| `GET /api/related?q=` | up to 10 articles from the hybrid search, best passage as snippet |
| `GET /api/radar` | the 30 articles with most reverts between named editors, per year (counts only) |
| `GET /api/radar/<id>` | that article's most-restored paragraphs, each restore as a diff link |
| `GET /api/contradictions/<id>` | paragraph pairs that state the same quantity with different numbers |
| `GET /api/cite?text=` | passages that back a sentence, with the `<ref>` markup near the best match |
| `GET /api/explain/<id>/<rev>` | what one edit changed (words, refs, numbers, sections); an LLM `summary` when a key is set |
| `GET /api/find?title=` | article titles for the pickers |
| `POST /api/translate` | `{"text"|"texts", "to", "from"?}` → `{"translation"|"translations", "model"}` |

### `/ask` response

```json
{
  "question": "When did the Winter War start?",
  "kind": "plain",
  "answer": [{"text": "The Winter War began on 30 November 1939.", "cites": [1]}],
  "sources": [{
    "n": 1, "passage_id": 0, "page_id": 1256, "rev_id": 24273471,
    "title": "Talvisota", "heading": null, "text": "Talvisota käytiin …",
    "score": 0.033, "url": "https://fi.wikipedia.org/?oldid=24273471",
    "deep_url": "https://fi.wikipedia.org/?oldid=24273471#:~:text=…",
    "edits": 2143, "reverts": 328, "langs": ["en", "sv"]
  }],
  "xlang": [{"lang": "en", "title": "Winter War", "heading": "…", "text": "…", "url": "…", "distance": 0.39}]
}
```

- Up to 8 sources (at most 2 per article); cited ones first, numbered 1, 2, … in citation order,
  then the uncited ones. A sentence can have `cites: []` (shown as uncited).
- `heading` is `null` for the lead; `text` is the whole passage (up to ~300 words).
- `score` is an RRF sum (~0.01–0.05): never show it as a percentage.
- `deep_url` opens the same version scrolled to the section, with the paragraph highlighted in
  browsers with text fragments. `url` stays the plain citation link.
- `langs`: which of en/sv have the article (empty = Finnish only). `xlang`: up to 3 en/sv
  paragraphs labelled *missing* in Finnish that are about as close to the question as the cited
  passages; empty list = show nothing.

**Then-vs-now** (`kind: "then_vs_now"`, same route) adds `as_of`, `compare_to`, `era` on each
source (`then` / `now`; `then` sources cite the version live on `as_of`, with no `passage_id`)
and `diffs`: `[{"then": n, "now": m, "similarity", "ops": [[op, text], …]}]`, op `equal` /
`delete` / `insert` in reading order.

## When a call fails (`api.js`)

| Live result | `api.js` |
| --- | --- |
| 200 JSON | returned with `_source: "live"` |
| 404 / 405, 5xx, network error, timeout (60 s ask, 30 s path, 15 s others) | a fixture from `app/static/fixtures/`, `_source: "fixture"`, `_error` = the reason |
| other 4xx (400, 422, 429) | rejects with the JSON's `error` |
| `?mock=1` on the page URL | fixture, no live call |

`ask()` never falls back to a fixture unless `?mock=1`: a failed answer shows its error, because a
saved answer would look like an answer to a different question. Fixtures are real data:
`python tools/make_fixtures.py` (database reachable, SELECT only, ~30 s) rewrites the graph, path
and related fixtures; `ask-*.json` are edited by hand.
