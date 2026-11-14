# Trust and editor features (branch `features`)

New pages and read-only JSON routes on top of the base (ask, history, graph). Backend lives in two new
files, `app/insights.py` and `app/lessons.py`, registered with one line each in `app/main.py`; no existing
backend file was changed. Everything below runs on the database alone (stored vectors, system-versioned
`passage_history`, `revert_event`); only `/ask/l` and the optional LLM summaries need the model or a key.

## Pages

| Page | What it does | Data |
| --- | --- | --- |
| `/` Ask | Sources are no longer a column of boxes: each `[n]` marker previews its passage on hover and opens a card on click (bottom sheet on phones). A row of source chips under the answer lists every source. A **rewind slider** shows each cited passage as it read at the end of any year since 2003. Source health dots on the chips. | `/ask`, `/api/health`, `/api/rewind` |
| `/drift` | **Language drift**: which words Finnish Wikipedia used for a topic (civil war / war of liberation, prison / concentration camps, red and white terror, Finlandization), year by year, and the edits where one word replaced another. | `app/static/drift.json`, built by `tools/make_drift.py` |
| `/tools` | **Editor tools**: citation finder, contradiction finder, edit-war radar. | `/api/cite`, `/api/contradictions/<id>`, `/api/radar` |
| `/lesson/<page_id>` | The graph's reading path as a short lesson with a quiz. | `/api/lesson/<id>` |
| `/article/<id>` | Gains "Explain this edit"; edit summaries no longer show editor names. | `/api/explain/<id>/<rev>` |

## Routes (`app/insights.py`, `app/lessons.py`)

| Route | Returns |
| --- | --- |
| `GET /api/health?ids=1,2` | per passage: `live_since`, `first_seen`, `rewrites` (versions of its section), `comebacks`, `restored`, `contested` |
| `GET /api/rewind?ids=1,2` | per passage: `years[]` (`state` same / changed / absent / no_article, `rev_id`, `hash`) and `versions{hash: {text, similarity, ops}}` |
| `GET /api/radar` | the 30 articles with most reverts between named editors, with reverts per year (counts only) |
| `GET /api/radar/<page_id>` | that article's most-restored paragraphs, each restore as a Wikipedia diff link |
| `GET /api/contradictions/<page_id>` | paragraph pairs that state the same quantity with different numbers |
| `GET /api/cite?text=...` | passages backing a sentence, with the `<ref>` markup near the best-matching sentence |
| `GET /api/explain/<page_id>/<rev_id>` | facts of one edit (words, refs, numbers, sections) and changed spans; an LLM `summary` when a key is set |
| `GET /api/find?title=...` | article titles for the pickers |
| `GET /api/lesson/<page_id>?q=` | `steps[]` (title, why, lead, `url` to the exact version) and `quiz[]` |
| `GET /ask/l?q=` | `/ask` over dataset L (all 568k articles); same JSON as `/ask`, plus `"scope": "l"` |

## Measured (server database, over the SSH tunnel)

health 0.1 s, rewind 0.3 s, radar 2.3 s, contradictions 1.9 s, citation finder 3.4 s, explain 2.8 s, lesson ~1 s
after the graph is cached. Drift: one scan of 495k paragraph texts plus their 593k lifetimes, ~90 s once
(`.venv\Scripts\python.exe tools\make_drift.py`), then a 21 KB file.

## Rules kept

No editor names anywhere (radar and explain show counts and diff links only; `no_names` strips user links and
names from edit summaries). Every passage links to the exact version it came from. UI text English, article text
Finnish. Plain HTML/CSS/JS, no build step. Reduced motion respected; chart colours validated with the dataviz
palette check (worst colour-blind separation ΔE 8.4, contrast at least 3:1 on the dark surface).

## Known limits

- Rewind and health match a passage to its past self by vector distance within the article (headings get renamed),
  so a heavily rewritten section can show as "changed" or "not written yet" rather than as a clean history.
- "Often restored" is a trace of reverts and rewordings, not proof of a dispute; the UI says so by showing counts only.
- The citation finder is keyword-based (no embedding on the laptop); it finds paragraphs sharing names, numbers and
  stems, not paraphrases.
- Quizzes use the language model when `LLM_API_KEY` is set and fall back to year-blank questions from the text itself.
- Drift terms and their regexes are listed in `tools/make_drift.py`; adding a topic is one dictionary entry and a re-run.
