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
| Base | Cited Q&A (RAG) plus version history (SVT), joined at paragraph level. |
| The twist | Kept as an added feature and chosen later. Candidates below. |
| History data | All of dataset M in one system-versioned table, with real timestamps. |
| Search data | Paragraphs from M's newest version of each article, cleaned to plain text, one vector each. |
| Paragraph unit | One paragraph, short ones merged up to about 300 words, with the article title and section heading added before embedding. |
| Embedding model | bge-m3 on a Colab T4. Modal credits are the fallback. Questions use the same model. |
| Answer model | A cloud model on hackathon credits, kept as a setting. |
| Shipped S vectors | Kept for whole-article search and for the Swedish and English articles. |

Still open: the twist, the split of work, and the organisers' answers on outside data and what
"scaling" must show.

## How it fits together

```
Dataset M (all versions) --load--> article         (system-versioned)  --as of--> article time travel
                                      | clean and split
                                      v
                                   passage         (system-versioned)  --as of--> paragraph history
                                      | text -> bge-m3 on a GPU -> vectors
                                      v
                                   passage_vector  (VECTOR + index)    --search--> cited answer
Dataset S (shipped vectors) -----> article_vector                      --search--> whole-article search
```

| Table | Holds | Main columns |
| --- | --- | --- |
| `article` | Every saved version of every article, system-versioned with real timestamps | `page_id`, `rev_id`, `user`, `anonymous`, `comment`, `sha1`, `text` |
| `passage` | Each paragraph of an article, system-versioned so its changes are kept | `passage_id`, `page_id`, `position`, `heading`, `text`, `text_hash` |
| `passage_vector` | One vector per current paragraph, with a vector index | `passage_id`, `embedding VECTOR(1024)` |
| `article_vector` | The shipped vectors from dataset S | `lang`, `page_id`, `embedding VECTOR(1024)` |

The `article` table comes from the starter. The other three are proposals; their columns are
settled when phase 2 starts. At question time the question is embedded with the same model,
MariaDB returns the closest paragraphs, and the cloud model writes the answer from them.

## Phases

Each phase ends with something that can be demoed.

1. **Data in.** Load all of M into the versioned table. Load S with its shipped article vectors.
   Done when a query returns an article as it stood on a chosen date.
2. **Paragraphs.** Clean M's newest version of each article, split into paragraphs, embed on a
   GPU, load with a vector index. Done when the 37 test questions find the right article more
   often than the starter's 76% in the top 5.
3. **Cited answers.** Question in, top paragraphs out, the cloud model writes a short answer
   where every sentence links to its paragraph. Done when the page answers in Finnish and English.
4. **Paragraph history.** Track each paragraph across versions: first-seen date, changes, revert
   count. Done when clicking a paragraph in an answer opens its timeline.
5. **One added feature.** Pick one candidate below.
6. **Scale and polish.** Run search over L for timing numbers, re-measure index recall, tidy the
   page, rehearse the demo.

Phases 1 to 4 are the base. Phase 4 is the riskiest part of it, because paragraphs get reworded
and moved between versions.

## Added-feature candidates

| Candidate | What the user sees | Extra work | Outside data |
| --- | --- | --- | --- |
| Contested-paragraph heatmap | Paragraphs shaded by how often they were fought over, with a summary of what each fight is about | Medium | No |
| Dispute ranking for all articles | A ranked list of the most contested Finnish history articles, including slow fights over years | Low | No |
| Citation history | Per paragraph: sourced or not, and when it gained or lost a citation | Medium | No |
| Source check | Whether a cited web page really backs the sentence | High | Yes |
| Ask the past | The same question answered as of a chosen year | Medium to high | No |
| Vandalism survival time | How long later-reverted text stayed visible | Low | No |

The first two are the safest picks. No published study covers edit wars on Finnish Wikipedia.
Details: `docs/research/edit-wars.md`, `docs/research/wikipedia-problems.md`.

## Risks to test early

- **Vector index on a versioned table.** Unconfirmed, as is combining vector search with
  `FOR SYSTEM_TIME AS OF`. Test in an hour. Fallback (already assumed here): vectors in a
  separate plain table joined by paragraph id.
- **Tracking a paragraph across versions.** Exact hash matching loses a paragraph when one word
  changes. Start with exact matching plus a similarity fallback; test on *Talvisota*.
- **Cleaning wikitext.** The starter's cleaner drops templates, tables and references. Check the
  output is good enough to embed and to show.
- **Embedding consistency.** Colab vectors must match query-time vectors. Compare a few against
  the shipped S vectors.
- **Size.** History table 7 to 10 GB. Paragraph vectors about 4 KB each.
- **Naming editors.** Show patterns and link to diffs; do not label named editors as vandals.

## Questions for the organisers

1. May we use data beyond the provided datasets, such as the web pages that articles cite?
2. What must "scaling across datasets" show: a run on L, or measurements plus a plan?
3. Which MariaDB feature do you most hope a team uses, and what would disappoint you?
4. Does a vector index work on a system-versioned table?
5. What is the demo format and length?
