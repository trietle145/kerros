# UX critique: Wikipedia trust tool (pre-demo)

Tested 2026-11-14 against http://127.0.0.1:5006 (headless Edge, CDP), 1440x900, 1920x1080, 390x844 with touch emulation, reduced motion.
Scripts: `ux/s1.mjs`, `ux/s2.mjs`, `ux/s3.mjs`. Screenshots: `ux/shots/*.png` (names below).
Environment caveat: on this server `/article/1256` returns a raw Flask **500** (2 s) and live `/ask` did not answer within 70 s. So the history page was judged from the template and CSS, not from a working render. Those failures are themselves a demo risk (see 3.2 and 3.8).

## 1. Verdict: 7/10

The visual design is distinctive and calm. The dark serif reading column, the pill citation markers, the then-vs-now diff and the Obsidian-style graph look like one product and would hold up on a projector. The new popover is a good idea, but the hover preview covers the next lines **and the next markers**, so moving from [1] to [2] does not work. On phone the card covers half the screen with no close button, and the old "all sources at a glance" view is gone with nothing to replace it. The biggest demo risks are not visual: the History button leads to a raw white 500 page, a live answer can spin on "Writing the answer…" for 60 s with no way out, and the back link from History drops `?mock=1`.

## 2. Citation popovers: 6/10

**What works**
- Markers look clickable: filled accent pills, 27 px, with a 0.45 rem invisible hit area (`app.css:189-193`). Hovering a marker lights up its sentence and the other sentences that cite it (`04-peek-450ms.png`). This makes the answer–source link feel real.
- Tooltip timing follows the rules: 280 ms before the first preview, instant after that (`ask.js:228-234`). Motion is origin-aware (`transformOrigin` at the marker, `ask.js:174`), 140 ms for the preview and 200 ms for the card, using the strong ease-out curve. Under reduced motion it opens instantly (`60-reduced-card-30ms.png`).
- The card content is right: title, section, passage, a "Show more" toggle, edits and reverts, and three clear actions (`07-card-near-bottom.png`). "Open on Wikipedia" uses `deep_url` (the exact version, scrolled to the passage).
- Escape closes the card and returns focus to its marker. A click outside closes it. When you come back from History or Graph, the card reopens so the title can morph back (`43-back-arrived.png`).
- In then-vs-now, the card has an amber left edge and a "Then · 1 June 2007" pill (`13-tvn-card.png`).

**Problems, ranked by impact**

1. **The preview covers the next markers and four lines of the text being read.** With [1] previewed, [2] and [3] sit under the popover. Moving the pointer to [2] lands on the popover, and clicking at [2]'s position does nothing (`04-peek-450ms.png`, `06-card-200ms.png`: the s1 script clicked [2] and got no card). Clicking the preview itself does nothing either, even though it says "Click the number for the full source". *Fix:* (a) In `place()` (`ask.js:166`), prefer **above** when there is room, because text above has already been read; fall back to below. (b) Make the preview clickable to promote it to the card: in the `results` click handler, `else if (pop.contains(e.target) && pop.dataset.mode === "peek") showPop(popCite, "card")`. (c) Make the preview shorter: drop the hint line after the first time it is shown (keep a flag in sessionStorage).
2. **In then-vs-now, the card hides exactly the comparison it supports.** Opening [1] ("Then") covers the "What changed since" heading and half of the "now" sentences (`13-tvn-card.png`). Fix (a) above solves most of this. Also give the markers their era: `.cite[data-era="then"]` with an amber ring, set in `sentence()` (`ask.js:63`). Today [1] to [4] all look the same in the answer, so the era is only visible after you open a card.
3. **Phone: the card is a 358x325 px box that flips above and covers the question and the earlier text** (`52-phone-card.png`). It has no close control, the only way out is tapping outside, and the status line still says "point at a number to preview, click to open" (`51-phone-answer.png`). *Fix:* below 52 rem, render the card as a bottom sheet: `position: fixed; inset: auto 0 0; max-height: 60dvh`, padded with `env(safe-area-inset-bottom)`, with a visible "Close" button (`app.css` phone block, `popHtml`). Change the hint text when `!fine.matches` ("tap a number to see its source").
4. **There is no way to scan all sources at once, and attribution is less visible.** The old column showed "4 articles, which sections" at a glance. Now that takes four clicks, and CC BY-SA appears only in the page footer. *Fix:* add one quiet row under the answer: `Sources: [1] Talvisota · Lead  [2] Mainilan laukaukset · …`. These are chips that open the same popover, plus "Text: Wikipedia, CC BY-SA 4.0". About 10 lines in `render()`, reusing `.cite` and `showPop`.
5. **The preview shows the first lines of the passage, not the sentence that supports the claim.** For [1] the claim is "without a declaration of war", but the preview shows the article's opening dates (`04-peek-450ms.png`). *Fix (ask.js only):* in the preview, start the excerpt at the passage sentence with the most word overlap with the cited answer sentence, and wrap the overlapping words in `<mark>`. This is cheap string work, and it is the moment a judge would see the trust feature work.
6. **When the card is opened from the keyboard, it stays open after focus leaves it.** Tabbing past "Graph" moves into Related articles while the card still floats over the text. The `focusout` handler only closes the preview (`ask.js:249`). *Fix:* add `pop.addEventListener("focusout", e => { if (isCard() && !pop.contains(e.relatedTarget) && e.relatedTarget !== popCite) closePop(); })`. Also, per the motion rules, keyboard-opened cards should not animate: skip `animate()` when `e.detail === 0`.
7. **"2,143 edits · 328 reverts" reads as if it described the passage, but it counts the whole article.** *Fix:* label it "article: 2,143 edits · 328 reverts", or show the passage `health` pills where they exist.
8. Small issues: the exit uses `ease-in` (`ask.js:207`). Use `var(--ease-out)` at 110 ms. "Lead" as a heading means nothing to readers; use "Introduction". Closing the card does not make the reading highlight fade back.

## 3. Per feature

### 3.1 Landing: 8/10
Strong headline and kicker, a clear input and good examples (`01-landing-1440.png`). Issues: (1) The time feature, the product's originality, is a small grey "Optional: as Wikipedia stood on mm/dd/yyyy" with a US date mask in a UK-English UI. *Fix:* label it "See Wikipedia as it was on…" and give it a then-vs-now example right next to it, or make that example chip the first one. (2) The then-vs-now chip is the longest and sits last; put it first, since it is the demo. (3) At 900 px tall the footer is half cut off. This is minor.

### 3.2 Loading and errors: 5/10
The skeleton and the three steps look good (`02-submit-200ms.png`). But the steps are timers: after 2.4 s it sits on "Writing the answer…" for up to 60 s (`63-live-result.png`, still loading at 9 s; `/ask` did not answer within 70 s). There is no elapsed time, no cancel, and the Ask button stays live. *Fix (`ask.js` `showLoading`):* after 8 s add "Still writing, usually under 20 s · Cancel" (use an AbortController in `api.js`). After 25 s offer "Show a saved example". The History link leads to a **raw white Flask 500** (`30-history-1440.png`). Add a Flask `errorhandler(500)` that renders `base.html` with a notice and a link back. This is a real demo-killer if the DB tunnel drops.

### 3.3 Answer reading: 7/10
The serif text at 1.3 rem with 1.62 line height reads beautifully, and the uncited sentence is honestly flagged (`61-long-question.png`). Issues: the status line packs "ANSWER · 4 sources · instructions · sample data" into one muted row. On phone it wraps into three lines above the answer (`51-phone-answer.png`). After the first open, the instructions are noise. *Fix:* keep "Answer · 4 sources" and move the hint into a first-run-only line. A long question is clipped in the input with no wrap; acceptable.

### 3.4 Then vs now: 7/10
This is the best screen for originality: the two labelled parts, then the word diff with "61% the same" and links to "2007 version [1] → version now [2]" (`11-tvn-full.png`). Issues: (1) The date field stays empty even though the answer is "as of 1 June 2007". Fill `asOf` from `res.as_of` so the UI says what it did. (2) The first diff is a wall of red and green (~20 lines). Collapse equal runs longer than ~25 words into "…" with a toggle. (3) The era is not visible on the markers (see 2.2). (4) The diff legend chips "removed / added" are tiny; fine on a laptop, weak on a projector.

### 3.5 Related articles: 6/10
Clean two-column cards, each with a Graph button (`10-related.png`, `11-tvn-full.png`). But 10 cards make a long page, and Graph is the only action. Readers would expect the title to open the article (with its History). *Fix:* show 4 with "Show all 10", make the title a link to `/article/<id>`, and keep Graph as the secondary action. Both "sample data" pills repeat on every section in mock mode; that is fine for testing, but remember the demo runs live.

### 3.6 Graph page: 7/10
It is visually the wow moment: glow on the main node, revert rings, a floating legend, and the year slider with a bar sparkline (`20-graph-1256.png`, `22-graph-8295-1920.png`). Issues: (1) **During play, edges are drawn to nodes that are not there yet.** At 2004, green lines end in empty space (`21-graph-playing.png`, from Talvisota toward ~(810,525) and ~(690,628)). Filter links whose endpoints are absent in the current year (`app/static/graph/time.js` / `core.js`). (2) The graph does not show which nodes were **sources of the answer**, which is the link back to the Ask flow. Pass the cited page_ids (they are already in sessionStorage `lastAsk`) and give those nodes a small numbered badge matching [1]..[n]. (3) The subtitle and the panel repeat the same sentence ("explore how the sources connect…"). (4) Node labels are about 11 px, too small for a projector at 1920; scale the label font with zoom, minimum 13 px. (5) Phone (`54-phone-graph.png`): the graph uses about 35% of the height and the legend is hidden. Acceptable.

### 3.7 History page: n/a here (500). From the template: 6/10
The idea (monthly bars, reverts split into "anonymous cleanup" and "between named editors", an as-of picker, a version box) fits editors well. Issues: (1) `.timeline a:focus { outline: none }` (`history.css:16`) with only a near-invisible fill change, and about 280 month links each a tab stop. Restore a visible focus ring, or make the chart a single tab stop that arrow keys move through. (2) It is styled differently from the Ask page: plain form controls, and no link back to the cited passage. (3) It shows the raw edit summary (`article.html:58`). See section 5.

### 3.8 Cross-screen transitions: 7/10
The title morph and the 160/280 ms root cross-fade are well tuned. The return trip restores the answer instantly with the card reopened (`43-back-arrived.png`). Issues: (1) Going to History has no pressed or pending feedback, and the old page stays frozen for the 2 s server round-trip (`40-to-history-100ms.png`, `-400ms`, identical). Add `aria-busy` and a dim or spinner on the clicked action. (2) The back link on History is built in `base.html:22` as `"/?q=" + q`, which **drops `?mock=1`**. In mock mode, back from History fires a live `/ask` and hangs. The graph page keeps it (`graph.html:13`). (3) Coming back always reopens the card over the text. Morph the title back, then close the card after the transition (`document.startViewTransition(...).finished`), or leave only its marker highlighted.

### 3.9 Phone (390x844): 6/10
No horizontal overflow, good type, and the landing works (`50-phone-landing.png`). The card behaviour (2.3), the "point/click" copy and the three-line status row are the main problems. The tap-highlight is already handled.

## 4. Top 10 changes, ranked by demo payoff

| # | Change | Effort | File |
|---|---|---|---|
| 1 | Styled error page for 5xx, and a clear in-page error with a link back for History or Graph failures | S | `app/main.py` (errorhandler) + `app/templates/base.html` |
| 2 | Preview placed above when there is room, and clickable to open the card: no more covered markers | S | `app/static/ask.js` (`place`, click handler) |
| 3 | Loading: "still writing…" after 8 s, Cancel, saved-example offer after 25 s | S | `app/static/ask.js`, `app/static/api.js` |
| 4 | Back link keeps `?mock=1` (and `as_of`) | S | `app/templates/base.html:22` |
| 5 | One-row "Sources" strip under the answer (chips → same popover) plus CC BY-SA line | S | `app/static/ask.js` `render`, `app/static/app.css` |
| 6 | Era colour on markers; fill the date field from `res.as_of` in then-vs-now | S | `app/static/ask.js`, `app/static/app.css` |
| 7 | Preview shows and highlights the supporting sentence, not the start of the passage | M | `app/static/ask.js` `popHtml` |
| 8 | Phone: card as a bottom sheet with a Close button; touch-specific hint text | M | `app/static/app.css`, `app/static/ask.js` |
| 9 | Graph: no dangling edges during play; badge nodes cited in the answer | M | `app/static/graph/time.js`, `core.js` |
| 10 | Then-vs-now diff: collapse long unchanged runs; History timeline focus ring | S | `app/static/ask.js` `diff`, `app/static/history.css:16` |

## 5. Project rule checks
- **Editor names:** `article.html:58` prints `version.comment` verbatim. Finnish revert summaries often name the user ("Kumottu käyttäjän X muokkaus…"), so this can show an editor's name next to a revert. Strip `käyttäjä(n|ltä) \S+` and `[[Käyttäjä:…]]`, or omit summaries on revert versions. No "vandal" wording found in the UI.
- **Version links:** the card uses `deep_url` (versioned) and diff links use per-era `url`. Related-article cards and graph nodes link only to the graph, not to a version. That is fine as long as the graph panel's "Open on Wikipedia" stays versioned (`panel.js:102` shows "· 2007 version"). History's "today on Wikipedia" uses `?curid=`, which is acceptable for "today".
- **Keyboard:** the popover works with Tab, Enter and Escape, but (a) the card stays open after focus leaves it (`ask.js:249`), and (b) the History timeline removes the focus outline (`history.css:16`). Graph canvas nodes are `aria-hidden`; the "Articles in this graph" list is the keyboard path, which is acceptable.
- **CC BY-SA:** only in the footer now that the source list is gone; see change 5.
