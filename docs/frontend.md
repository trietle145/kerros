# Frontend: plan, pages, functions and API contract

For B (frontend). Branch: `frontend`, merged into `planning` by PR. Written 2026-11-14.
**Scope: what the pages must do and which data they get, not how they look.** Visual design,
layout and styling are yours to decide (use whatever design skills you like). The backend (A)
keeps every JSON shape below stable, so the look can change freely without touching logic.

**Split (supersedes `tasks/roadmap.md` on `b-search-app`):** A = all backend (search, answers,
time-aware answers, history data, graph data, L at scale). B = all frontend (every page, the
look, the demo polish).

## Rules that apply to every page

1. **No database access from the frontend.** Pages get data from the JSON routes below (same
   origin) or from variables the server passes into a template.
2. **CC BY-SA:** every piece of Wikipedia text shown links to the exact version it came from
   (`https://fi.wikipedia.org/?oldid=<rev_id>`). The footer in `base.html` names the licence.
3. **No editor names, never "vandal".** Show patterns (counts, "often reverted") and links to
   diffs only.
4. **Text is Finnish, the UI is English.** Answers come in the question's language.
5. **No build step.** Plain HTML/CSS/JS in `app/templates` and `app/static`; a library only from a
   CDN with an exact version pinned (e.g. `force-graph@1.47.0`).
6. Keyboard-usable, readable on a projector, works at laptop and phone width.

## Files you own

`app/ask.py` (page routes), `app/templates/*` (including `base.html`, and `article.html` + 
`app/static/history.css`, which A wrote for 2.A3 and now hands over), `app/static/*`.
Don't edit: `app/answer.py`, `app/history.py`, `app/timeqa.py`, `app/search.py`, `app/llm.py`,
`app/db.py`, `app/embed.py`, `scripts/*` (A). Need a new field or route? Ask A; A adds it to the
backend and to this file.

## How to run it

- **See the deployed app (no setup):** `ssh -N -L 5000:127.0.0.1:5000 root@135.181.8.213`, then
  open http://127.0.0.1:5000. This runs A's latest deployed code on the server.
- **Develop locally (your templates, the server's data):** open the database tunnel from
  `SERVER.md`, then `flask --app app.main run --debug` and open http://127.0.0.1:5000. Real answers
  (once A's search lands) also load bge-m3 locally: ~5 GB free memory. Until then `/ask` is a
  stub that needs only the database.

## Pages

| Page | Route (owner) | Data |
| --- | --- | --- |
| Ask + answer | `/` (B, `ask.py`) | `GET/POST /ask` (JSON, A) |
| Article history: as of a date + timeline | `/article/<page_id>?as_of=YYYY-MM-DD` (A's route, B's template `article.html`) | template variables (below); JSON with `&format=json` |
| Graph (add-on, later) | `/graph/<page_id>` (B adds to `ask.py`) | `GET /api/graph/<page_id>` (A, **live**) |

### 1. Ask page `/`

**Must do:**
- A question box; submit on Enter. Optional date controls: "as Wikipedia stood on <date>"
  (sends `as_of`) and/or "compare with today". A question that names a year ("…vuonna 2008…,
  mitä on muuttunut?") is detected by the backend too, so the controls are a convenience.
- 3–4 example questions to click (at least one then-vs-now question). A will send the final demo
  questions; use placeholders until then.
- Call `/ask` with `fetch`; show a **loading state** (answers take ~2–8 s, the model writes them),
  then the answer, or the error message from the JSON.
- Render the answer as sentences; each `[n]` citation is a link/marker that highlights or scrolls to
  source card `n`. A sentence with an empty `cites` list is shown as **uncited** (visibly marked).
- Source cards (one per source): title, section heading (or "Lead"), the passage text (shortened,
  expandable), "N edits · M reverts", and three actions: *Open on Wikipedia* (the `url`, i.e. that
  exact version), *History* (`/article/<page_id>`), *Graph* (later).
- **Then-vs-now answers** (`kind: "then_vs_now"`): two parts, "In <year> Wikipedia said…" and
  "What changed since…", with their sources grouped by `era` (`then` / `now`), plus the diffs
  (below): removed words and added words marked, both versions linked.
- Later: source-health badges on cards when the `health` field is present (shape below).

### 2. Article history page `/article/<page_id>`

Exists and works (A, task 2.A3); yours to restyle. **Keep its behaviour:** timeline of edits per
month with reverts marked (named-editor reverts vs anonymous cleanup), each month clickable (opens
the article as of that month's end), a date picker, a version box (saved / replaced / summary /
"what this edit changed" link), the cleaned article text. Variables the route passes to
`article.html`:

| Variable | Content |
| --- | --- |
| `error` | set only on failure (then nothing else is set) |
| `page_id`, `title` | the article |
| `version` | dict: `rev_id, url, valid_from, valid_to (None = current), comment, blocks` (or `None` if the article didn't exist on the date) |
| `moment` | the requested date (datetime) |
| `sections` | `[(kind, text)]`, kind `p`, `h2`, `h3`, or `("ul", [items])` |
| `chart` | `{width, height, bars: [{month, edits, reverts, cleanup, x, w, h, h_rev, h_clean, href, selected, year}], years: [bars with a year label]}`: precomputed SVG geometry, heights sqrt-scaled; use it or draw your own from `/article/<id>/timeline` |
| `edits`, `reverts`, `cleanup`, `first_month`, `today` | totals and date limits |

### 3. Graph page `/graph/<page_id>` (add-on, after the base)

As in `tasks/plan-graph.md` (G3/G4): force-directed graph of the article and its linked
neighbours (real wiki links only, no vector fill-up), optional grey stub nodes for links leaving
the dataset, a year slider (nodes and links as they were that year). Pitch line: *"explore how the
sources connect, and how those connections grew."* Data from A's `/api/graph` (live, contract
below). Good demo articles: *Mainilan laukaukset* (8295: 17 links among its nodes in 2005, 67
today) and *Talvisota* (1256: 25 in 2004, 122 today).

## API contract (A keeps these stable)

### `GET /ask?q=<question>[&as_of=YYYY-MM-DD]` (also POST form)

**Live with real answers** (hybrid search + Claude, ~3–4 s; ~8–17 s for then-vs-now questions). `400 {"error": "..."}` on an empty question; `500 {"error": "..."}`
if the model call fails.

```json
{
  "question": "Milloin talvisota alkoi?",
  "kind": "plain",
  "answer": [{"text": "Talvisota alkoi 30. marraskuuta 1939.", "cites": [1]}],
  "sources": [{
    "n": 1, "passage_id": 0, "page_id": 1256, "rev_id": 24273471,
    "title": "Talvisota", "heading": null, "text": "Talvisota oli Neuvostoliiton ja Suomen …",
    "score": 1.0, "url": "https://fi.wikipedia.org/?oldid=24273471",
    "deep_url": "https://fi.wikipedia.org/?oldid=24273471#:~:text=Talvisota%20k%C3%A4ytiin…",
    "edits": 2143, "reverts": 328
  }]
}
```

**Then-vs-now answer** (planned, task A4; the same route): the extra fields below. Build against
this example until it's live:

```json
{
  "question": "Mitä Wikipedia sanoi sisällissodan punavangeista vuonna 2007, ja mitä on muuttunut?",
  "kind": "then_vs_now", "as_of": "2007-06-01", "compare_to": "2026-10-01",
  "answer": [
    {"text": "Vuonna 2007 Wikipedia kertoi noin 80 000 punavangista.", "cites": [1]},
    {"text": "Nykyään luvuksi annetaan 76 000, ja mukana on myös noin 10 000 Neuvosto-Venäjälle paenneen punakaartilaisen maininta.", "cites": [2]}
  ],
  "sources": [
    {"n": 1, "era": "then", "page_id": 1150, "rev_id": 2943189, "title": "Suomen sisällissota",
     "heading": "Hävinneen kohtalo", "text": "…noin 80 000 punavankia…",
     "url": "https://fi.wikipedia.org/?oldid=2943189", "edits": 3357, "reverts": 344},
    {"n": 2, "era": "now", "page_id": 1150, "rev_id": 24234990, "title": "Suomen sisällissota",
     "heading": "Hävinneen kohtalo", "text": "…vangittuna oli 76 000 punavankia…",
     "url": "https://fi.wikipedia.org/?oldid=24234990", "edits": 3357, "reverts": 344}
  ],
  "diffs": [{
    "then": 1, "now": 2, "similarity": 0.71,
    "ops": [["equal", "Sodan"], ["delete", "voittajien käsiin jäi noin 80"], ["insert", "vangittuna oli 76"],
            ["equal", "000 punavankia."], ["insert", "Tämän jälkeen vielä noin 10 000 vankia armahdettiin."]]
  }]
}
```

**`deep_url`** (on every source, plain and then-vs-now): the same version as `url`, but scrolled
to the passage's section and, in browsers with text-fragment support (Chrome, Edge, Safari,
recent Firefox), with the paragraph highlighted. Use it for "Open on Wikipedia"; if the highlight
words don't match the rendered page, the browser just lands on the section. `url` stays the plain
citation link.

`diffs[].ops` is a list of `[op, text]` with op `equal` / `delete` / `insert`, in reading order:
render it however you like (inline marks, or two columns when `similarity` is low, say < 0.5, since
a mostly rewritten paragraph reads better side by side). Long `equal` runs may be shortened by the
backend with `…`.

**Source health** (planned, task A5; optional field on each source):
`"health": {"live_since": "2014-03-02", "rewrites": 6, "contested": false}`. Show it only when
present.

### `GET /article/<page_id>?as_of=YYYY-MM-DD&format=json`

Live. `404` if the article didn't exist on the date, `400` for a bad date.

```json
{"page_id": 1256, "title": "Talvisota", "rev_id": 14947009, "as_of": "2015-06-01T00:00:00",
 "valid_from": "2015-05-28T19:01:22", "valid_to": "2015-06-03T10:12:51",
 "user": "…", "comment": "…", "url": "https://fi.wikipedia.org/?oldid=14947009",
 "blocks": [["p", "Talvisota oli 30. marraskuuta 1939 – 13. maaliskuuta 1940 …"], ["h2", "Tausta"], ["li", "…"]]}
```

(`user` is in the data but must not be shown; see the rules.)

### `GET /article/<page_id>/timeline`

Live. `{"page_id": 1256, "months": [{"month": "2003-10", "edits": 2, "reverts": 0, "cleanup": 0}, …]}`
(only months with edits; `cleanup` = reverts that undid an anonymous edit).

### `GET /api/graph/<page_id>` (live)

`404` for an unknown article; a redirect page resolves to its target. ~0.4 s the first time per
article, then cached. Edges are real wiki links from the wikitext (no vector fill-up); vectors only
break ties when choosing which neighbours to show.

```json
{"main": 8295,
 "nodes": [{"id": 8295, "title": "Mainilan laukaukset", "relation": "main", "lead": "…",
            "rev_id": 24242554, "created": 2004, "edits": 177, "reverts": 12,
            "url": "https://fi.wikipedia.org/?oldid=24242554"},
           {"id": 1256, "title": "Talvisota", "relation": "out", "…": "…"}],
 "years": [2004, 2005, "…", 2026],
 "snapshots": {"2005": {"revs": {"8295": 214942, "1256": 1324132}, "links": [[8295, 1256], "…"]},
               "2026": {"revs": {"…": 0}, "links": [["…"]]}},
 "outside": ["18. divisioona (jatkosota)", "Diplomatia", "Hitlerin Saksa", "…"]}
```

- `relation`: `main` | `mutual` (both link to each other) | `out` (main links to it) | `in` (it
  links to main). Up to 20 nodes: mutual first, then out, then in.
- `snapshots[year]`: the state at the end of that year (the current year = today). A node
  **exists in a year** when it has an entry in `revs`; `links` are `[from, to]` among the nodes as
  that year's text had them. Use `revs` for that year's Wikipedia link (`?oldid=<rev>`).
- `outside`: titles the main article links to that are **not** in the dataset (up to 30), for
  optional grey title-only stubs; no click-through.

## Tasks (B)

Each one works against the live stub or the example JSON above, so none waits for the backend.

| # | Task | Done when |
| --- | --- | --- |
| F1 | Ask page: question box, example questions, `fetch('/ask')`, loading and error states | Typing a question shows the stub answer; an empty question shows the 400 message |
| F2 | Answer view: sentences with `[n]` markers linked to source cards; uncited sentences marked | Clicking a marker highlights its card; a sentence with `cites: []` looks different |
| F3 | Source cards: title, heading, expandable text, edits/reverts, Wikipedia / History links | All links open the right version and history page |
| F4 | Then-vs-now view from the example JSON: `then` / `now` groups, diff rendering from `ops` | The example renders readably, both version links work; real data swaps in with no code change once A4 is live |
| F5 | Restyle `article.html` (+ `history.css`) keeping the behaviour listed above | Clicking a month and picking a date still change the text and the `oldid` link |
| F6 | One consistent look for all pages (`base.html`, one stylesheet), landing state | Ask page and article page look like one product, on a projector too |
| F7 | Graph page (add-on, after F1–F6 and A's `/api/graph`) | As in `plan-graph.md` G3 (G4 slider if time) |

**Checkpoints:** after F1–F3 the plain demo path works on the stub (and on real answers as soon as
A's search lands); after F4–F6 the full demo path looks finished; F7 only if time is left.
