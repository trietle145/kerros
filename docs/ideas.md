# Feature ideas

2026-11-13. A pool to pick from once the core (cited answers over Wikipedia) works. None of them is
decided. "Needs" says what each one adds on top of the core architecture in `architecture.md`.

The strongest pitch is probably one reader idea plus one editor idea that share the same data.
An outside review suggested **trust badges on answers** plus the **edit-war radar** as the pair,
with "ask the past" on one article as a stretch. Nothing is picked yet.

Ideas that need paragraph history should build it for a pilot set of about 200 articles first;
the most edited articles cost the most, so measure on those.
Starred ideas (★) are new since the first plan.

## For readers

| Idea | What the user sees | Needs |
| --- | --- | --- |
| Contested-paragraph lens | An article with each paragraph shaded by how much it was fought over. Click one to see its wording flip over the years, with a one-line summary of the dispute. | Revert events + paragraph lifetimes from the history table |
| Trust badges on answers | Each source paragraph in an answer marked "stable since 2014", "recently changed" or "contested". | The same data as the lens, shown in the Q&A |
| ★ Three languages, one history | The same question answered from the Finnish, Swedish and English articles side by side, with where they disagree highlighted (for example what the 1918 war is called, or casualty numbers). 2,919 topics exist in all three languages. | Swedish and English articles split into paragraphs too |
| Ask the past | The same question answered as Wikipedia stood in a chosen year, and what changed in the answer since. | Vectors for old paragraph versions (the core keys vectors by text hash, so this only means embedding more texts) |
| ★ What changed since | Pick an article and two dates; get a short summary of what was added, removed and reworded in between, each change linked to its edit. | History table + a model summary of the diff |
| ★ How the story grew | A timeline of how an article about an event grew: when key facts, names and sections first appeared. | History table |

## For editors

| Idea | What the user sees | Needs |
| --- | --- | --- |
| Edit-war radar | A ranked list of the most fought-over Finnish history articles, using mutual reverts between named editors, including slow fights that come back over years. No published study covers Finnish. | Revert events table |
| Vandalism survival time | How long later-reverted edits stayed visible, per article and over time, and which low-traffic articles keep vandalism longest. | Revert events table |
| ★ Contradiction finder | Facts that disagree between articles, for example two articles giving different years for the same event or different term dates for a president. Found by retrieving near-identical paragraphs across articles and asking a model whether they conflict. | Core vectors + a model check |
| Citation history | Per paragraph: sourced or not, and when it gained or lost a citation. | Reference tags parsed out of each version's wikitext |
| ★ Meaning drift | Paragraphs whose meaning drifted a long way over many small edits while the citation stayed the same. Measured as the vector distance between a paragraph's first and current wording. | Vectors for old paragraph versions |
| Source check | Whether a cited web page really backs the sentence. Book sources stay unchecked. | Fetching cited pages (outside data, ask the organisers) |

## Ideas that change how people reach it

- **Browser extension:** the lens and badges shown on top of real fi.wikipedia.org pages.
- **MCP server:** other AI assistants ask our database for cited, trust-rated Finnish history answers.

Both only need the core's HTTP API, so they can come at the end.
