# Frontend prototype: shared spec for all agents

Repo: `C:\Users\hvhun\junction_hackathon`, branch `frontend` (stay on it; do NOT commit, push,
switch branch or stash). Five agents work in this same folder at the same time, so **edit only
the files you own** (table below). Read before you start: `docs/frontend.md` (rules + API
contract), `git show b-search-app:tasks/plan-graph.md` (the graph plan + its API contract),
`git show b-search-app:docs/DATA_NOTES.md` (database facts, link parsing rules), `CLAUDE.md`.

## What we are building

A locally hosted prototype of two screens that feel like one polished product:

1. **Ask page `/`**: question box, example questions, loading state, cited answer (sentences
   with `[n]` markers linked to source cards), source cards, then-vs-now view, and a
   "Related articles" list where each article has a **Graph** button.
2. **Graph page `/graph/<page_id>?q=<question>`**: an Obsidian-style **force-directed network**
   (not a tree): the main article pinned in the centre, 10-20 neighbour articles, colour by
   relation, node size by links inside the graph, a ring for often-reverted articles, dashed
   lines for `related`, hover highlights a node's neighbours and fades the rest, click opens a
   side panel, a **year slider** with a play button shows how the connections grew, and a
   **Learning path** button numbers 4-6 nodes in reading order.

The existing Article history page (`/article/<page_id>`, A's route) only gets the shared look.

Decided by the user: force network; Ask + Graph scope; real fixtures with fallback; dark theme
(plan-graph.md); smooth, satisfying transitions between screens; dynamic, professional polish.

## Hard rules (from docs/frontend.md)

- No build step. Plain HTML/CSS/JS (ES modules are fine). A library only from a CDN with an exact
  pinned version. The graph uses `force-graph` (UMD global `ForceGraph`), loaded by a script tag
  in `graph.html`; check the pinned version really exists on the CDN.
- The browser never talks to the database, only to same-origin JSON routes.
- Do NOT edit A's files: `app/answer.py`, `app/history.py`, `app/db.py`, `app/embed.py`,
  `app/main.py`, `scripts/*`, `schema.sql`, `docs/architecture.md`, `tasks/*`.
- CC BY-SA: every Wikipedia text shown links to its exact version
  (`https://fi.wikipedia.org/?oldid=<rev_id>`); in an earlier year use that year's `rev_id`.
- Never show editor names, never the word "vandal". Reverts are a count ("often reverted").
- UI text English; article titles and text Finnish. Keyboard-usable; readable on a projector;
  works at laptop and phone width. Respect `prefers-reduced-motion`.
- Never print or copy the contents of `.env`.
- Smallest code that works; no frameworks, no abstractions nobody asked for.

## File ownership

| Agent | Owns (create/edit) |
| --- | --- |
| **connector** | `app/static/api.js`, `app/static/fixtures/*.json`, `tools/make_fixtures.py`, `docs/frontend-connections.md` |
| **graph-core** | `app/static/graph/core.js` |
| **graph-time** | `app/static/graph/main.js`, `app/static/graph/time.js`, `app/static/graph/panel.js`, `app/static/graph/graph.css` |
| **ui** | `app/ask.py`, `app/templates/base.html`, `app/templates/ask.html`, `app/templates/graph.html`, `app/static/app.css`, `app/static/ask.js`, `app/static/transitions.js` (if needed), light restyle of `app/templates/article.html` + `app/static/history.css` |
| **evaluator** | nothing in the repo; writes only to `.claude/frontend-team/eval/` (untracked, durable) |

Need something from a file you don't own? Write the request at the end of your final report;
the lead passes it on. Do not edit it yourself.

## Contract 1: data layer `app/static/api.js` (connector)

ES module. Every function tries the real route first and falls back to a fixture when the route
is missing (404/405), fails (5xx, network), or `?mock=1` is in the page URL. Each result carries
`_source: "live" | "fixture"` so the UI can show a small "sample data" hint.

```js
import { ask, related, graph, path } from "/static/api.js";
await ask(q, asOf)        // GET /ask?q=&as_of=        -> /ask JSON (docs/frontend.md). A 400 rejects with Error(message from JSON).
await related(q)          // GET /api/related?q=       -> {articles:[{page_id,title,snippet,score}]}
await graph(pageId)       // GET /api/graph/<page_id>  -> {main,nodes,years,snapshots} (plan-graph.md)
await path(pageId, q)     // GET /api/graph/<id>/path?q= -> {path:[{id,why}], source}
```

Fixtures in `app/static/fixtures/`: `ask-plain.json`, `ask-then-vs-now.json` (both from the
examples in docs/frontend.md; a question containing a year or "muuttunut" gets the then-vs-now
one), `related.json`, `graph-<page_id>.json`, `path-<page_id>.json`. Graph fixtures are **real
data**, pulled once read-only from the database, for hero articles 1256 (Talvisota), 8295
(Mainilan laukaukset), 1150 (Suomen sisällissota). An unknown page_id falls back to
`graph-1256.json`. Graph JSON shape, exactly as in plan-graph.md:

```json
{"main": 8295,
 "nodes": [{"id": 8295, "title": "...", "relation": "main|mutual|out|in|related",
            "lead": "...", "rev_id": 24242554, "created": 2004, "reverts": 12}],
 "years": [2004, 2005, 2026],
 "snapshots": {"2004": {"revs": {"8295": 14180}, "links": [[8295, 1256]]}}}
```

A node exists in a year when it has an entry in that year's `revs`; links are directed
`[source, target]`; the last year is the current version.

## Contract 2: graph renderer `app/static/graph/core.js` (graph-core)

Owns the canvas only: force-graph setup, physics, custom node/link painting, hover highlight,
drag, zoom, entry animation, in/out animations for nodes and links. Knows nothing about years,
panels or fetch.

```js
import { createGraph } from "/static/graph/core.js";
const g = createGraph(el, { nodes, main });   // nodes: the /api/graph nodes (all of them, positions computed once and kept)
g.apply({ visible: Set<id>, links: [[s,t],...], added: [[s,t],...], removed: [[s,t],...], revs: {id: rev_id} });
                                              // show exactly this state; nodes that stay must not move;
                                              // added links flash green, removed links flash red then fade
g.highlightPath(ids | null);                  // number these nodes 1..n, emphasise links between consecutive ones
g.focus(id);                                  // gently centre/zoom on a node
g.select(id | null);                          // persistent selected style
g.on("select", id => {}); g.on("hover", id => {});   // node click / hover (null when leaving)
g.resize(); g.destroy();
```

## Contract 3: page wiring, time and panel (graph-time)

`main.js` (loaded as `<script type="module">` by graph.html) reads `document.body.dataset.pageId`
and `.q`, calls `api.graph`, creates the graph, builds the per-year state from `snapshots`
(`time.js`: `stateFor(data, year, prevYear)` -> the object `g.apply` takes), and renders its
components **into containers the ui agent provides in graph.html**:

| Container id | Filled by graph-time with |
| --- | --- |
| `#graph-canvas` | (passed to `createGraph`) |
| `#graph-timeline` | year slider (`<input type=range>`), play/pause, current year, counts ("12 articles, 31 links") |
| `#graph-panel` | on select: title, relation, lead, "created <year>", "often reverted" when high, Open on Wikipedia (that year's rev_id), History (`/article/<id>`), "Make this the main node" (navigates to `/graph/<id>?q=`); learning-path steps |
| `#graph-legend` | the five relations (colour + line style + label), ring meaning |
| `#graph-nodelist` | an accessible, keyboard-reachable list of the visible nodes (selecting one = clicking the node) |
| `#graph-status` | loading / error / "sample data" text (`aria-live`) |

graph-time styles the inside of these containers in `graph/graph.css` using the tokens below;
the ui agent places and sizes the containers and owns everything else on the page. The
Learning path button lives inside `#graph-panel` or `#graph-timeline` (graph-time decides).

## Contract 4: design tokens (ui defines them in `app/static/app.css` on `:root`)

Everyone else only *reads* them (CSS `var(--x)`, or `getComputedStyle` for canvas colours, with
a hard-coded fallback so the code works before app.css exists):

`--bg --surface --surface-2 --border --text --muted --accent --accent-ink`
`--rel-main --rel-mutual --rel-out --rel-in --rel-related --ring --added --removed`
`--radius --ease-out --ease-in-out --dur-fast --dur --dur-slow --font --font-mono`

## Ports (so servers don't collide) and how to run

`.venv\Scripts\flask.exe --app app.main run --port <yours>` from the repo root. The database is
reachable on 127.0.0.1:3307 through `.env` (the stub `/ask` needs it). Ports: connector 5001,
graph-core 5002, graph-time 5003, ui 5004, evaluator 5005. Stop your server when you finish.
If Flask can't start for you, test static files with `python -m http.server <port>` in `app/`
and say so in your report.

## Rounds

Minimum three rounds. After each round the evaluator scores the result 1-10 and writes
per-agent feedback; you then get that feedback and improve. Round 1 goal: everything works end
to end on fixtures. Later rounds: polish, motion, edge cases.

## Final report (every agent, every round), short

What you built or changed (files), how you checked it (what you actually ran or looked at),
what does not work yet, and requests for other agents.
