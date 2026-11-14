# Plan G: the article graph through time (proposed Phase 3 highlight)

Status: **proposal, to be agreed with Triet.** Written 2026-11-14 from a design interview; no
code exists yet. Data facts behind it: `docs/DATA_NOTES.md`. Shared plan: `tasks/plan.md`.

## What it is

A reader asks about a topic. Next to the cited answer they get a list of related articles; one
click opens a graph of that article and its 10–20 closest neighbours, drawn like Obsidian's graph
view. A year slider shows how the article's connections grew since it was created. A "Learning
path" button asks the LLM in which order to read the shown articles.

Why it fits the challenge: RAG picks the article and ranks its neighbours (vectors), SVT draws
every past year (`FOR SYSTEM_TIME AS OF`), and both meet in one picture. Unlike the answer time
slider it needs **no new tables**: links are read from the article versions already loaded.

## Decisions (from the interview)

| Topic | Decision |
| --- | --- |
| Place in the project | Phase 3 highlight, replacing the answer time slider as front-runner. Built after the base demo path works. |
| Deadline assumed | Sunday morning 15 Nov. Budget ~7 hours. Order: graph → slider → learning path (cut from the end). |
| Architecture | Browser → JSON API (Flask, same app) → MariaDB. The browser never talks to the database. |
| Frontend | Plain HTML + JS, `force-graph` from a CDN (exact version pinned), no build step. English UI, Finnish titles and text. |
| Outside data | No scraping (Context.dev) in v1. The graph stays inside the 19,742 articles. |
| Flow | Question → answer + list of up to 10 related articles → "Graph" on one → graph page with that article as main node. |
| Node | One article. 10–20 nodes: the main article + up to 19 neighbours. |
| Edge | Wiki links from the wikitext (directed). Vector similarity is used for ranking and fill-up only. |
| Layout | Force-directed, main node pinned in the centre, dark theme, labels on hover, side panel on click. |
| Colour | By relation to the main node. Size = links inside the graph. Ring = many reverts (a pattern, never editor names). |
| Slider | Yearly steps from the main article's first year to 2026. Shows how the main article's graph changed. |
| Learning path | The LLM orders 4–6 of the shown articles, general → specific, one sentence each; heuristic fallback. |

**Assumptions I made where an answer left room** (confirm or correct):
1. *Slider:* the nodes are chosen once from today's data and keep their positions. In an earlier
   year a node appears only if it existed then, and a link only if that year's text had it.
   Articles that were linked in the past but are not today are a stretch task (G7).
2. *Learning path:* the LLM chooses and orders among the shown nodes only (it can't invent
   articles). It decides the order itself; the graph ranking does not constrain it.
3. *Where it is built:* in this repo, as new files, by whoever picks this plan up.

## Measured facts that shape it (live server, over the tunnel, 2026-11-14)

- Reading all current wikitext and building the link index in Python: **5.4 s fetch + 1.0 s
  parse**; 19,600 non-redirect articles, **138,730 links inside the set**. Small enough to hold in
  memory, so "who links *to* this article" is a dictionary lookup, not a table scan.
- Linked neighbours (in or out) per article: **median 5**; 71% of articles have fewer than 10,
  1,595 have none. So the vector fill-up is the normal case. Hubs are the other extreme:
  *Talvisota* has 104 out-links, 1,453 in-links, 81 mutual, so ranking matters.
- 23 yearly snapshots of 20 nodes (`AS OF` + `page_id IN (...)`): **1.0–1.3 s**, ~10 MB of text,
  ~370 distinct versions. Fast enough to compute per request and cache.
- 457 articles have no row in `article_vector` (no similarity ranking or fill-up for them).
- Navigation-box templates are not expanded in wikitext, so the live site shows more links.

## Files

New (owner: whoever builds G): `app/graph.py` (blueprint: link index, node choice, snapshots,
path, routes, self-check), `app/templates/graph.html`, `app/static/graph.js`.
Touched: `app/main.py` (one line registering the blueprint; shared and frozen, so tell Triet and
commit it alone), `app/templates/ask.html` (B's: the related-articles list with Graph buttons).
Called, not edited: `app/db.py`, `app/search.py`, `app/llm.py`, `app.history.stats()`.
No new dependency, no new table, no new `.env` key.

## API contract

```
GET /api/related?q=<question>
  → {"articles": [{"page_id": 8295, "title": "...", "snippet": "...", "score": 0.03}]}   # up to 10

GET /graph/<page_id>?q=<question>            → the graph page (HTML)

GET /api/graph/<page_id>
  → {"main": 8295,
     "nodes": [{"id": 8295, "title": "...", "relation": "main|mutual|out|in|related",
                "lead": "...", "rev_id": 24242554, "created": 2004, "reverts": 12}],
     "years": [2004, ..., 2026],
     "snapshots": {"2004": {"revs": {"8295": 14180}, "links": [[8295, 1256]]}, ...}}
  # a node exists in a year when it has a rev there; 2026 = the current version

GET /api/graph/<page_id>/path?q=<question>
  → {"path": [{"id": 1256, "why": "..."}], "source": "llm|heuristic"}
```

Every article shown links to `https://fi.wikipedia.org/?oldid=<rev_id>` (CC BY-SA); in an earlier
year the link uses that year's `rev_id`.

---

### Task G1: link parser and in-memory link index

**Description:** In `app/graph.py`: `parse_links(text) -> set[str]` with the five rules from
`docs/DATA_NOTES.md` ("Parsing rules"), and `link_index()` (cached, built on first use) that reads
the current rows once (`SELECT page_id, title, text FROM article`, fetched in batches) and returns
`titles`, `redirects`, `out[page_id]`, `inn[page_id]`.

**Acceptance criteria:**
- [ ] `parse_links` keeps `Kustaa III:n sota`, drops `Luokka:`/`Tiedosto:`/`Kuva:`/interwiki and
      `[[:Luokka:X]]`, strips `#section` and `|label`, turns `J._V._Snellman` into `J. V. Snellman`.
- [ ] The index has ~138,700 links over ~19,600 articles and builds in under 15 s over the tunnel.
- [ ] *Mainilan laukaukset* (8295) links out to *Talvisota* (1256).

**Verification:** `python -m app.graph` runs these as asserts and prints the counts.
**Dependencies:** none. **Scope:** S (~1 h).

### Task G2: choose the nodes, `/api/graph` for today

**Description:** `neighbourhood(page_id)`: rank candidates as mutual links → out-links → in-links,
ties by cosine distance to the main article's stored vector (one query: `VEC_DISTANCE_COSINE`
over `article_vector WHERE lang = 'fi' AND page_id IN (candidates)`). Keep 19. If fewer than 10
are linked, fill up to 10 with the nearest fi articles by vector (relation `related`). Return the
nodes with lead text (`passage` position 0), `rev_id`, and `reverts` from `app.history.stats()`,
plus today's links among all chosen nodes. A redirect page resolves to its target first.

**Acceptance criteria:**
- [ ] *Talvisota* returns 20 nodes, all `mutual`; *Mainilan laukaukset* returns main + linked
      neighbours with *Talvisota* among them; an article with no links returns 10 `related` nodes.
- [ ] An article without a vector returns its linked neighbours only, no error.
- [ ] Unknown `page_id` → 404. Warm response under 1 s.

**Verification:** asserts for the three hero cases in `python -m app.graph`; `curl /api/graph/8295`.
**Dependencies:** G1. **Scope:** S (~1 h).

### Task G3: graph page and the way in

**Description:** `graph.html` + `graph.js`: force-graph on a dark canvas, main node pinned in the
centre, colour by `relation` with a legend, size by links inside the graph, a ring when `reverts`
is high, dashed lines for `related`. Click a node → side panel: title, lead, "Open on Wikipedia"
(`?oldid=`), "History" (`/article/<page_id>`), "Make this the main node". `/api/related` calls
`search(q, k=20)` and groups passages by article (best passage = snippet); `ask.html` lists them
under the answer, each with a Graph button to `/graph/<page_id>?q=...`.

**Acceptance criteria:**
- [ ] Question → related list → Graph → the graph draws in under 3 s; dragging and zooming work.
- [ ] The five relations are told apart by the legend and by more than colour (line style or
      label), and the panel and buttons work with the keyboard.
- [ ] "Make this the main node" redraws around the clicked article.

**Verification:** by hand in the browser on the 3 hero articles.
**Dependencies:** G2; 2.B1 (`search()`) for the related list; 2.B3 for the page it sits on. **Scope:** M (~2 h).

### Task G4: the year slider

**Description:** `/api/graph` adds `years` and `snapshots`: for each year from the main article's
first version to 2025, one query (`SELECT page_id, rev_id, text FROM article FOR SYSTEM_TIME AS OF
'<year>-12-31 23:59:59' WHERE page_id IN (...)`), parse links with G1, keep links among the chosen
nodes; 2026 is the current data. Cache the result per `page_id`. In the page: a slider with a play
button; nodes without a version that year are hidden; links new that year flash green, links
removed flash red; the side panel's Wikipedia link uses that year's `rev_id`.

**Acceptance criteria:**
- [ ] *Mainilan laukaukset*: fewer links in 2005 than in 2026, and no node shown before its
      first version.
- [ ] Snapshots add under 2 s to a cold `/api/graph`; the second call is served from the cache.
- [ ] Dragging the slider never moves the nodes that stay.

**Verification:** an assert on the 2005 vs 2026 link counts in `python -m app.graph`; by hand in
the browser, comparing one year against `/article/<page_id>?as_of=`.
**Dependencies:** G2, G3. **Scope:** M (~1.5 h).

### Task G5: learning path

**Description:** `/api/graph/<page_id>/path?q=`: send the question and the shown nodes (id, title,
lead sentence) to the model through `app/llm.py`; ask for 4–6 ids in reading order, general →
specific, ending at the main article, one English sentence each. Drop any id that was not sent;
if fewer than 3 remain or the call fails, fall back to: most linked-to first, main article last.
The page numbers the path's nodes, highlights the links between them and lists the steps.

**Acceptance criteria:**
- [ ] The path contains only shown nodes and ends at the main article.
- [ ] With the API key removed, the heuristic path is returned and marked `"source": "heuristic"`.

**Verification:** a test with a fake model reply containing an unknown id; by hand on 3 articles.
**Dependencies:** G3; 2.B2 (`app/llm.py`). **Scope:** S (~1 h).

### Task G6: demo pass

**Description:** Pick the demo question and main article (a hub like *Talvisota* looks dense, a
small article shows the slider best), warm the link index at app start, check the page on the
projector resolution, add the timings to the scale slide.

**Acceptance criteria:**
- [ ] The path question → answer → Graph → slider → learning path runs twice in a row without a
      wait over 3 s.

**Dependencies:** G3–G5. **Scope:** S (~0.5 h).

### Stretch (only after G6)

- **G7 Former neighbours:** also parse the main article's own yearly versions and add up to 5
  articles it once linked to but no longer does, shown only in their years.
- **G8 Outside links:** show the most-linked outside targets (*Helsinki*, *Suomi*) as title-only
  stubs; a Context.dev summary on click, cached, only once the mentors allow outside data.
- **G9 Link table:** a `link` table filled offline if the in-memory index becomes too slow on L
  (needs a write grant and A's agreement).

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The base slips and `search()` / `llm.py` are late | High | G1, G2 and G4 need neither; `/api/related` can run on `article_vector` (query in `docs/DATA_NOTES.md`) until `search()` exists |
| Most graphs are mostly `related` (dashed) nodes | Medium | Expected for 71% of articles; pick linked hero articles for the demo; the legend explains the dashed lines |
| Hubs (1,400+ in-links) look arbitrary | Low | Mutual links first, then vector distance; capped at 19 |
| First graph request waits ~7 s for the link index | Low | Build it at app start (G6) |
| The slider shows little for young or tiny articles | Low | Demo on an article from 2003–2005 |
| A revert ring reads as blame | Medium | Count only, no names, wording "often reverted" |
| `app/main.py` is frozen | Low | One-line change, agreed with Triet, in its own commit |
