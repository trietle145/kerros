# Feature ideas

2026-11-13. The base (cited answers plus the two time views in `architecture.md`) is built first.
The highlight is one feature **through time**, added on top. Which one is not decided; the ideas
below are sorted by how well they fit that. "Needs" says what each adds to the base.

**Front-runner:** the answer time slider. It is the only idea that needs vector search and
system versioning in the same query, and readers see it directly. **Safety net:** the edit-war
radar, which needs only the `revert_event` table from the base, so it still works if the
paragraph history slips.

Ideas that need paragraph history should build it for a pilot set of about 200 articles first;
the most edited articles cost the most, so measure on those.

## Through time: highlight candidates

| Idea | For | What the user sees | Needs |
| --- | --- | --- | --- |
| Answer time slider (ask the past) | Readers | Drag a year: the same question is answered as Wikipedia stood then, with the sources of that year and what changed in the answer since. | Paragraph lifetimes (`passage_history`) + vectors for old paragraph texts |
| Trust badges on answers | Readers | Each source paragraph in an answer marked "unchanged since 2014", "rewritten 6 times" or "contested". | Paragraph lifetimes |
| What changed since | Both | Pick an article and two dates; get a short summary of what was added, removed and reworded in between, each change linked to its edit. | Base only for whole articles (two as-of reads + a model summary); paragraph lifetimes make it sharper |
| Contested-paragraph lens | Both | An article with each paragraph shaded by how much it was fought over. Click one to see its wording flip over the years, with a one-line summary of the dispute. | Paragraph lifetimes + `revert_event` |
| Edit-war radar | Editors | A ranked list of the most fought-over Finnish history articles, using mutual reverts between named editors, including slow fights that come back over years. No published study covers Finnish. | `revert_event` only (in the base) |
| Vandalism survival time | Editors | How long later-reverted edits stayed visible, per article and over time. Small on its own; works as a number on the source card or the radar. | `revert_event` only |
| Citation history | Editors | Per paragraph: sourced or not, and when it gained or lost a citation. | Paragraph lifetimes + reference tags parsed from each version's wikitext |
| How the story grew | Readers | A timeline of how an article about an event grew: when key facts, names and sections first appeared. | Paragraph lifetimes |
| Meaning drift (stretch) | Editors | Paragraphs whose meaning moved a long way over many small edits while the citation stayed the same. Measured as the vector distance between first and current wording. | Old-text vectors + matching a paragraph across rewordings, which exact hashes cannot do |

Once paragraph lifetimes exist, the badges, "what changed" and the lens are mostly queries on the
same table. So the realistic package is: time slider as the highlight, badges with it, radar as
the safety net.

## Not about time: parked

| Idea | What the user sees | Why parked |
| --- | --- | --- |
| Three languages, one history | The same question answered from the Finnish, Swedish and English articles side by side, with disagreements highlighted. 2,919 topics exist in all three. | The Swedish and English data has no history |
| Contradiction finder | Facts that disagree between articles, found by retrieving near-identical paragraphs and asking a model whether they conflict. | No time angle; needs many model calls |
| Source check | Whether a cited web page really backs the sentence. | Needs outside data (ask the organisers) |

## Ideas that change how people reach it

- **Browser extension:** the lens and badges shown on top of real fi.wikipedia.org pages.
- **MCP server:** other AI assistants ask our database for cited, trust-rated Finnish history answers.

Both only need the base's HTTP API, so they can come at the end.
