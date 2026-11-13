# Rough plan: Wikipedia trust tool on MariaDB

2026-11-13. Online version with the diagram: https://claude.ai/artifact/92Jie7dsbM9C85B7KRBF2s

## The idea

A web app that answers questions about Finnish history from Wikipedia and shows, for every
paragraph it uses, where the text came from and how it got there. Each answer sentence links to
its source paragraph, and each paragraph opens its own history: when it appeared, how it
changed, and whether editors fought over it.

Readers get answers they can check. Editors get a view of which paragraphs are unstable or
contested.

Why it stands out:

- **It joins both tracks in one database.** The same paragraph is a row with a vector (RAG) and
  a row with a full version history (SVT). Neither starter repo does this.
- **It works at paragraph level.** The starters work at whole-article level, which finds the
  topic but misses the fact.
- **It uses the whole history.** All 862,076 saved versions of 19,742 articles, 2003 to
  October 2026, with their real Wikipedia timestamps.

## Decisions so far

| Topic | Decision |
| --- | --- |
| Team | 2 people. Who does what is split later. |
| Audience | Both readers and editors. |
| Form | Web app first. An extension or MCP server can come later, on the same database. |
| Base | Cited Q&A (RAG) plus two time views (SVT): an article as of a date, and an edit timeline with reverts. Built first. |
| The highlight | One feature through time, added on top of the base without changing it. Which one is chosen later; the front-runner is the same question answered as of a chosen year. |
| History data | All of dataset M in one system-versioned table, with real timestamps. |
| Search data | Paragraphs from M's newest version of each article, cleaned to plain text, one vector each. |
| Paragraph unit | One paragraph, short ones merged up to about 300 words, with the article title and section heading added before embedding. |
| Embedding model | bge-m3 for both paragraphs and questions. Where it runs is set up per machine later. |
| Answer model | A cloud model on hackathon credits, kept as a setting. |
| Shipped S vectors | Kept for whole-article search and for the Swedish and English articles. |

Still open: which time feature is the highlight, the split of work, and the organisers' answers
on outside data and what "scaling" must show.

## How it fits together

See `architecture.md` for the tables, the data flow and the code layout. In short: the full
history goes into a system-versioned `article` table; the newest version of each article is cut
into paragraphs in a plain `passage` table; each distinct paragraph text gets one vector; the
shipped S vectors cover whole-article search. Reverts are found once after the load and stored in
`revert_event`, which feeds the edit timeline. Paragraph history (how each paragraph changed) is
a later feature with its own table, computed from the history.

In the base, the Q&A and the time views sit side by side and meet at a History button on each
source. The highlight is what joins them in one query.

## Phases

Rough; they get re-planned in a later session. Each phase ends with something that can be demoed.

1. **Data in.** Load all of M into the versioned table. Load S with its shipped article vectors.
   Done when a query returns an article as it stood on a chosen date.
2. **Paragraphs.** Clean M's newest version of each article, split into paragraphs, embed on a
   GPU, load with a vector index. Done when the 37 test questions find the right article more
   often than the starter's 76% in the top 5.
3. **Cited answers.** Question in, top paragraphs out, the cloud model writes a short answer
   where every sentence links to its paragraph. Done when the page answers in Finnish and English.
4. **One added feature.** Pick from `ideas.md`. If it needs paragraph history, build that for a
   pilot set of about 200 articles first (the most edited ones are the costliest), and keep 3 hero
   articles that must have correct timelines for the demo.
5. **Scale and polish.** Run search over L for timing numbers, re-measure index recall, tidy the
   page, rehearse the demo.

Phases 1 to 3 are the base. Before phase 1, spend the first hour on the checks under "Risks to
test early".

## Added-feature candidates

The full, longer pool of ideas is in `ideas.md`; the architecture for the core is in `architecture.md`.

| Candidate | What the user sees | Extra work | Outside data |
| --- | --- | --- | --- |
| Contested-paragraph heatmap | Paragraphs shaded by how often they were fought over, with a summary of what each fight is about | Medium | No |
| Dispute ranking for all articles | A ranked list of the most contested Finnish history articles, including slow fights over years | Low | No |
| Citation history | Per paragraph: sourced or not, and when it gained or lost a citation | Medium | No |
| Source check | Whether a cited web page really backs the sentence | High | Yes |
| Ask the past | The same question answered as of a chosen year | Medium to high | No |
| Vandalism survival time | How long later-reverted text stayed visible | Low | No |

The highlight should be a feature through time. `ideas.md` sorts the pool that way: "ask the
past" as the front-runner, the dispute ranking as the safety net because it needs only
`revert_event`, and source check parked. No published study covers edit wars on Finnish
Wikipedia. Details: `docs/research/edit-wars.md`, `docs/research/wikipedia-problems.md`.

## Risks to test early

- **Database running at all.** Docker's disk is on a nearly full C: (2.9 GB free). Move it to D:
  or use a portable MariaDB on D:.
- **Vector index settings.** Vectors live in plain tables, so no vector index on a versioned or
  partitioned table is needed. Still re-measure recall once all paragraph vectors are in.
- **Tracking a paragraph across versions** (only if a picked feature needs it). Exact hash
  matching loses a paragraph when one word changes. Start with exact matching plus a similarity
  fallback; test on *Talvisota*.
- **Cleaning wikitext.** The starter's cleaner drops templates, tables and references. Check the
  output is good enough to embed and to show.
- **Embedding consistency.** Paragraph vectors and question vectors must come from the same model and settings. Compare a few against
  the shipped S vectors.
- **Size.** History table 7 to 10 GB. Paragraph vectors about 4 KB each.
- **Naming editors.** Show patterns and link to diffs; do not label named editors as vandals.

## Questions for the organisers

1. May we use data beyond the provided datasets, such as the web pages that articles cite?
2. What must "scaling across datasets" show: a run on L, or measurements plus a plan?
3. Which MariaDB feature do you most hope a team uses, and what would disappoint you?
4. How long is the event, and what is the demo format and length?
