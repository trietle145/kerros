# Architecture: cited Q&A and time views

As built, 2026-11-14. Retrieval: **hybrid, five lists fused in one SQL statement**. On top of
the cited Q&A: then-vs-now answers ("Time-aware retrieval"), the cross-language gaps
("Cross-language gaps"), and dataset L at scale ("Scale: S → M → L"). What MariaDB cost us to
learn is in "MariaDB: what it costs". Scores: [`eval/README.md`](../eval/README.md). Pages and
API: [`docs/frontend.md`](frontend.md).

## What the core does

A person asks a question about Finnish history in Finnish, Swedish or English. The app finds the
Wikipedia paragraphs that answer it and writes a short answer where every sentence cites its
paragraph by number. Each citation links to the exact Wikipedia revision the text came from.

This is the RAG track's core: retrieval from MariaDB and an answer with sources.

Next to it sit two time views from the SVT track: read any article as it stood on a chosen date,
and see an article's edit timeline with its reverts. The two sides meet on the source card under
an answer: each cited source has a History button.

The highlight joins them in one question: *"what did Wikipedia say about this in 2008, and what
has changed since?"* (section "Time-aware retrieval"). Built and working on all 862,076 versions.

A third view compares across languages: what English and Swedish Wikipedia say that the Finnish
article does not, and when the Finnish article covered it (section "Cross-language gaps").

## Design choices at a glance (for the pitch)

Every choice below was measured on our data (2026-11-14). Numbers are what to quote; the
trade-off column is what to say when a judge pushes back.

| Choice | Why | Evidence | Trade-off |
| --- | --- | --- | --- |
| **Passage = one section** (long ones split at paragraphs, ≤ ~300 words), not fixed windows, not whole articles | An edit changes only its own section, so passage boundaries stay stable across versions: that is what makes history per passage possible. Sections are also a natural size to cite | 66,642 passages, median 79 words. Old versions split the same way give **0 hash mismatches** with today's passages | 10 single paragraphs over 300 words are kept whole |
| **Keep the whole-article vectors too, fused with passages** | Whole articles find the *topic*, passages find the *fact* and give the paragraph to cite | Passages alone: hit@1 43%, hit@10 70%. Articles alone: hit@1 22%, hit@10 78%. Fused: hit@5 76%, hit@10 84–86% (= the starter's best, with paragraph-level citations) | One extra vector query (~4 ms) |
| **Cross-language search as a join** (en/sv article vectors of dataset S → their Finnish article by Wikidata id, `article_langlink`) | An English question meets an English article vector first, then crosses to the Finnish passages, in the same SQL statement | **hit@5 73% → 92%, hit@10 86% → 95%**, hit@1 35% → 51%; no extra model, no translation call, ~3 ms | Only for the 7,256 Finnish articles with an en/sv counterpart in S |
| **Title mentions as a fifth list** (an en/sv title written verbatim in the question) | Long articles have diluted whole-article vectors: "Finnish Civil War" did not rank its own article | Fixes the then-vs-now question on the Finnish Civil War; eval unchanged | Two-word titles and up only |
| **Keyword half = names and years only** (capitalised words, numbers; Finnish prefix terms like `kekko*`) | FULLTEXT has no Finnish stemming; prefix terms on every word over-match common stems | Every word: hit@5 70%. Names and years: **76%**, and faster (35 → 24 ms) | Chosen on the 37 eval questions: confirm on new questions |
| **Fusion by RRF in one SQL statement** (`UNION ALL` + `GROUP BY`, k = 60) | No FULL OUTER JOIN in MariaDB; one round trip; the pattern MariaDB documents | Whole hybrid search: 24 ms median | Weights are equal per list (not tuned) |
| **Vector index `M=16`, `ef_search=80`** | The default `M=6` found only 79% of the true top 10 | recall@10 **99.2–99.8%** at 66k vectors, 11–17 ms | Bigger index than the default |
| **bge-m3, pinned, one `embed()` for passages and questions** | Multilingual (fi/sv/en questions on Finnish text); the same model as the shipped S vectors | GPU-made and CPU-made vectors: cosine **1.0**. Embedded on Modal (66k in 6.4 min, 283k in 15 min); questions on the server's CPU | Needs ~5 GB free memory to load; English/Swedish questions match a bit worse than Finnish |
| **Vectors keyed by text hash** | An unchanged passage is embedded once, however many versions contain it | 862,076 versions → 530,885 distinct texts → **353,166 embedded** (texts live ≥ 1 day; vandalism costs no GPU time) | — |
| **Real edit times via `system_versioning_insert_history`** | `AS OF '2008-06-01'` means "what Wikipedia showed that day" | For 15 versions 2003–2026, `AS OF` returns exactly that version's passages | — |
| **Reverts by window functions** | One `INSERT … SELECT` over all versions instead of a Python loop | **46,015 reverts in 16 s**; Talvisota 328 = the SVT starter's count; 82% carry an undo/rollback summary (3% of other edits) | sha1 misses partial reverts |
| **Time is a filter, never in the vector** | Validity is a date range; a year in the question would pull towards passages that *mention* that year | Then-vs-now answers find real revisions (Red prisoners 80,000 → 76,000; Mainila "probably" → "possibly") | Needs a date router |
| **Today's counterpart by meaning, not by heading** | Headings get renamed | *Moskovan neuvottelut* (2008) → *Suomen ja Neuvostoliiton neuvottelut aluemuutoksista*, distance 0.13 | — |
| **Answers: Claude Opus 5.5, one sentence per line ending in `[n]`, validated in code** | Every claim checkable; invalid numbers dropped, uncited sentences shown as uncited; cited sources renumbered 1, 2, … and shown first | 19/19 sentences cited in the tests, fi/en/sv; ~3–4 s, ~$0.03 per answer | Cost per answer; server-side fallback to Opus 4.8 if a request is declined |
| **Cross-language gaps labelled in SQL** (en/sv paragraph vs every Finnish paragraph, now and through history) | "What does English Wikipedia say that Finnish doesn't, and did Finnish ever say it?": both tracks again | 35,829 en/sv paragraphs for 7,256 articles labelled in 5 min | Fixed distance cut-offs; "partly" is the grey zone |
| **Scale on dataset L in the same tables and index settings** | The scalability criterion: 1.5M passages of all 568k Finnish articles | Embedded on Modal in ~1 h; load and search numbers in "Scale: S → M → L" | Index build is one writer at a time (~65–740 inserts/s) |
| **One always-on CPU server, MariaDB never public** | Cheap; GPU only for embedding runs; team access by SSH tunnel | ~€1.50/day; all data loaded and verified on it | One machine = one point of failure |

## Approaches for retrieval

| | How it finds paragraphs | Good at | Weak at |
| --- | --- | --- | --- |
| A. Vector only | Nearest paragraph vectors to the question vector | Meaning, cross-language | Exact names, years, rare words |
| **B. Hybrid (chosen)** | Paragraph vectors and MariaDB `FULLTEXT` in one SQL statement, merged by rank (reciprocal rank fusion) | Meaning *and* exact names and years, e.g. "president 1956–1982" | Finnish word endings: handled by prefix search (below) |
| C. Two-stage | Shipped article vectors pick the top articles, then paragraph vectors within them | Cheap, uses the S vectors | Misses facts in articles the first stage skipped |

**Decision: B, built as A first.** B is A plus one more query, so A works on day one and B
follows. B is also a strong "MariaDB feature used well" point, and MariaDB documents the pattern:
[Optimizing Hybrid Search Query with Reciprocal Rank Fusion](https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf).

**As built (2026-11-14): five ranked lists fused by RRF in one statement** (`app/search.py`):

| List | What it ranks | Each hit contributes |
| --- | --- | --- |
| `vec` | nearest passage vectors | that passage |
| `ft` | `FULLTEXT` on names and years (Finnish prefix terms) | that passage |
| `art` | nearest Finnish whole-article vectors (dataset S) | its article's lead passage |
| `xl` | nearest English/Swedish whole-article vectors (S), joined to their Finnish article through `article_langlink` (Wikidata id) | that Finnish article's lead passage |
| `name` | English/Swedish titles of two words or more written verbatim in the question | that Finnish article's lead passage |

Measured on the starter's 37 questions (right Finnish article among the top distinct articles):

| Lists | hit@1 | hit@5 | hit@10 | SQL median |
| --- | --- | --- | --- | --- |
| passage vectors | 43% | 65% | 70% | 4 ms |
| + whole-article vectors | 35% | 73% | 86% | 8 ms |
| + FULLTEXT, every word | 43% | 70% | 84% | 35 ms |
| + FULLTEXT, names and years | 38% | 76% | 84% | 15 ms |
| **+ en/sv article vectors + title mentions (built)** | **51%** | **92%** | **95%** | 18–25 ms |
| starter (whole articles, a hit in any language) | — | 76% | 86% | — |

Why the `xl` list works: an English question is closest to the *English* article on the topic,
and the shipped S vectors include 10,175 English and Swedish articles. Matching by Wikidata id
turns that into the Finnish article inside the same statement, with no translation call. Before
it, *"What caused the Finnish Civil War?"* found the 1808 Finnish War; *Suomen sisällissota* is
now in the top 2. The `name` list catches long articles whose whole-article vector is too diluted
to rank even for its exact title.

Remaining misses (2 of 37): English questions that name no article (*"The 1918 war between the
Reds and the Whites"*, *"Who led the Senate that declared Finland independent?"*). The lever left
is translating the question to Finnish before searching (one small model call per question).

## Chunking, embedding and keyword search

Decided 2026-11-14 after looking at other Wikipedia RAG systems and measuring our own articles.

**What others do.** DPR and the original RAG paper cut Wikipedia into disjoint 100-word blocks,
each carrying its article title (21M passages); a later study found the fixed cut breaks
sentences. Cohere's multilingual Wikipedia set is paragraph-level (2.4M Finnish passages). The
MariaDB RAG starter embeds whole articles (76% top-5) and lists chunks and hybrid + RRF as its own
next steps. Anthropic's contextual retrieval puts context in front of each chunk and adds BM25:
top-20 failure rate 5.7% → 3.7% (context) → 2.9% (+ keyword search) → 1.9% (+ reranking).

**Our articles** (newest versions, crude cleaning, measured 2026-11-14): 19,600 articles (142
redirects skipped), 6.8 million words. Median article 180 words, 69% under 300 words. Raw
paragraphs are small (median 39 words, half under 40). Sections are a natural size (median 77
words, 95% under 300).

**Chunking: one passage per section.**
- The lead (text before the first heading) is its own passage; each section is one passage.
- A section over ~300 words is split at paragraph boundaries into pieces of up to ~300 words.
- Never merge across sections; no overlap.
- Skip reference and link sections: Lähteet, Viitteet, Aiheesta muualla, Katso myös,
  Kirjallisuutta. The en/sv paragraphs (cross-language gaps) skip their own equivalents
  (References, Bibliography, Literature, Källor, …) and book lists under neutral headings.
- Expected: about 67,000 passages, median ~80 words, 95% under ~265 words.
- Why sections, not fixed windows: an edit changes only its own section's passage, so passage
  boundaries stay stable across versions. The time features (paragraph lifetimes, "ask the past")
  depend on that; fixed windows would shift with every edit.

**Embedding.**
- bge-m3 dense, 1024 dimensions, normalised, cosine; the same model as the shipped S vectors and
  the starter's measurements.
- Passage input: `title + "\n" + heading + "\n" + text`. Question input: the question as typed.
  Max length 1,024 tokens (a 300-word Finnish passage is roughly 600 tokens).
- `text_hash` = SHA-256 of that exact embedding input, so one hash means one vector, and an
  unchanged section in an old version reuses its vector.
- ~67k passages: minutes on a GPU, roughly 1–3 hours on a CPU.

**Keyword half: prefix search for Finnish.** MariaDB `FULLTEXT` matches whole words and has no
Finnish stemming. Measured on 12.3: `MATCH … AGAINST('Kekkonen')` finds only "Kekkonen";
`AGAINST('Kekko*' IN BOOLEAN MODE)` also finds "Kekkosen" and "Kekkoselle"; years and hyphenated
names ("YYA-sopimus") match exactly. So Python turns the question into boolean prefix terms:
- words of 6+ letters keep all but their last 3 letters (at least 4) and get `*`:
  Kekkonen → `Kekko*`, talvisota → `talvis*`, presidentti → `presiden*`;
- numbers and shorter words stay exact; a few question words (mikä, milloin, kuka…) are dropped;
- the index covers `FULLTEXT(title, heading, text)`, so a question naming an article finds its
  passages.
Known cost: short stems over-match (`Turk*` → Turku and Turkki); the vector half outvotes them in
the fusion. Tune the rule against the evaluation.

**Fusion: reciprocal rank fusion in one SQL statement.** Top 50 from the vector side and top 50
from the keyword side; each passage scores `1/(60 + rank)` per side it appears in; sum, order,
keep the top. MariaDB 12.3 has no `FULL OUTER JOIN` (tested), so the two lists are combined with
`UNION ALL` + `GROUP BY passage_id` (MariaDB's RRF guide uses `LEFT JOIN … UNION`). English and
Swedish questions get little from the keyword half; RRF then follows the vector order.

**Not now.** LLM-written context per chunk (title + heading give most of it), late chunking
(sections are already self-contained), bge-m3 sparse vectors (no MariaDB index; `FULLTEXT`
plays that role), a reranker (measure later: top 50 → rerank → top 8–12; adds CPU latency).

Sources: [wiki_dpr](https://huggingface.co/datasets/wiki_dpr/blob/main/README.md) ·
[DPR pre-processing study](https://manveertamber.github.io/assets/pdf/pre-processing.pdf) ·
[Cohere Wikipedia embeddings](https://huggingface.co/datasets/Cohere/wikipedia-2023-11-embed-multilingual-v3) ·
[MariaDB RAG starter](https://github.com/MariaDB/mariadb-vector-wikipedia-rag) ·
[MariaDB RRF guide](https://mariadb.com/docs/server/reference/sql-structure/vectors/optimizing-hybrid-search-query-with-reciprocal-rank-fusion-rrf) ·
[Contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) ·
[Late chunking](https://arxiv.org/html/2409.04701v3) ·
[BGE-M3](https://arxiv.org/abs/2402.03216)

## System overview

```mermaid
flowchart LR
  subgraph offline["Offline, run once"]
    M[("Dataset M<br/>862k versions")] -->|load_m.py| A["article<br/>system-versioned"]
    A -->|"newest revision:<br/>clean + split"| P["passage<br/>current paragraphs"]
    P -->|distinct texts| E["bge-m3<br/>on a GPU"]
    E --> PV["passage_vector"]
    S[("Dataset S<br/>shipped vectors")] -->|load_s.py| AV["article_vector"]
    S -->|"load_langlinks.py<br/>(Wikidata ids)"| LL["article_langlink"]
    S -->|"build_xlang.py"| XL["xlang_passage<br/>+ xlang_vector"]
    A -->|"build_reverts.py,<br/>once after loading"| RV["revert_event"]
    A -->|"build_history.py"| PH["passage_history<br/>+ history_vector"]
  end
  subgraph online["Online, per request"]
    Q["Question"] --> QE["bge-m3"]
    QE --> R{{"Hybrid SQL: 5 lists<br/>(vectors, FULLTEXT, en/sv join), fused by rank"}}
    R --> L["Cloud model:<br/>answer with [n]"]
    L --> UI["Web page"]
    T["Time views:<br/>as-of reader, edit timeline"] --> UI
    UI -.->|"History button<br/>on a source"| T
  end
  PV --> R
  P --> R
  AV --> R
  LL --> R
  PH -->|"FOR SYSTEM_TIME AS OF<br/>(then-vs-now)"| R
  XL -->|"other Wikipedias add"| UI
  A -->|FOR SYSTEM_TIME| T
  RV --> T
```

Everything in the offline box runs once (or overnight); everything in the online box runs per
request. The two tracks meet in one place: a cited paragraph (`passage`) carries the
`page_id` and `rev_id` that the time views read from `article`.

## Tables and how they join

```mermaid
erDiagram
  article ||--o{ passage : "newest revision is cut into"
  passage }o--|| passage_vector : "text_hash"
  article ||--o| article_vector : "page_id (Finnish)"
  article ||--o{ revert_event : "found once from sha1"
  article {
    int page_id PK
    int rev_id
    int parent_id
    varchar user
    bool anonymous
    text comment
    varchar sha1
    mediumtext text
    timestamp row_start "hidden, real edit time"
    timestamp row_end "hidden, next edit time"
  }
  passage {
    int passage_id PK
    int page_id
    int rev_id "citation target"
    varchar title "FULLTEXT with heading, text"
    smallint position
    varchar heading
    text text
    binary text_hash "SHA-256 of the embedding input"
  }
  passage_vector {
    binary text_hash PK
    varchar model
    vector embedding "VECTOR INDEX M=16 cosine"
  }
  article_vector {
    char lang PK
    int page_id PK
    vector embedding "VECTOR INDEX M=16 cosine"
  }
  revert_event {
    int page_id PK
    int rev_id PK "the reverting version"
    datetime reverted_at
    varchar user
    bool anonymous
    int restored_rev_id "the earlier version brought back"
    datetime undone_since "when the undone text first appeared"
    int undone_edits
    varchar undone_user
    bool undone_anonymous
  }
```

Full definitions: `schema.sql`.

Tables added on top of the core (each by its own script, none changes the core tables):

| Table | Rows | What it holds | Made by |
| --- | --- | --- | --- |
| `passage_text` | 530,885 | every distinct passage text ever, with its first version and time live | `build_history.py` |
| `passage_history` | 593,195 | system-versioned, one row per passage lifetime (real edit times) | `build_history.py` |
| `history_vector` | 353,166 | vectors of texts live ≥ 1 day, plus today's | `load_vectors.py --history` |
| `article_langlink` | 10,175 | en/sv article → Finnish article (Wikidata id, dataset S) | `load_langlinks.py` |
| `xlang_passage`, `xlang_vector` | 35,829 | en/sv paragraphs with a label against Finnish | `build_xlang.py` |
| `l_passage`, `l_vector` | 1,545,854 | dataset L passages and vectors, same definitions as `passage` / `passage_vector` | `load_vectors.py --l` |

## Asking a question

```mermaid
sequenceDiagram
  actor U as Reader
  participant W as Flask app
  participant E as bge-m3
  participant D as MariaDB
  participant L as Cloud model
  U->>W: question
  W->>E: embed the question
  E-->>W: vector (1024)
  W->>D: one query: 5 ranked lists (vectors, FULLTEXT, en/sv join), fused by rank
  D-->>W: top paragraphs with page_id, rev_id, heading
  W->>W: keep ~8, at most 2 per article
  W->>L: question + numbered paragraphs
  L-->>W: answer, [n] after every sentence
  W->>W: check every [n] exists, flag uncited sentences, renumber cited sources first
  W->>D: other-Wikipedias block: en/sv paragraphs labelled missing, close to the question
  W-->>U: answer + sources linked to ?oldid=rev_id (+ what en/sv Wikipedia add)
```

**Answer generation as built** (`app/answer.py`, `app/llm.py`): the top 8 passages (at most 2
per article) are numbered and sent with the question to Claude Opus 5.5 (`effort: low`). The
system prompt asks for 2–5 sentences in the question's language, one per line, each ending with
the passage number(s) it uses, using only facts in the passages. Code then parses the lines,
drops any citation number that wasn't sent, and keeps sentences without one marked as uncited.
A declined request is retried on Claude Opus 4.8 inside the same API call (server-side
fallback). Measured: ~3–4 s per answer warm (search ~0.5 s, the rest is the model), ~13 s for
the first question after a restart while bge-m3 loads, ~$0.03 per answer. Provider and model
are `.env` settings.

After parsing, the sources are renumbered: the ones the answer cites come first as 1, 2, … in the
order they are first cited, then the rest (`renumber()`; the page shows them under "Cited in the
answer" and "Related passages, not cited"). Each source card says whether the article also exists
in English or Swedish, and the answer can carry an "Other Wikipedias add" block (section
"Cross-language gaps").

## The time side

Two time views sit next to the Q&A: an article as of a date and its edit timeline with reverts.
Reverts are found once and stored. The two sides meet on the source card, and in the then-vs-now
answers ("Time-aware retrieval").

```mermaid
flowchart TD
  ANS["Answer with numbered sources"] --> CARD["Source card:<br/>title, section, '412 edits, 9 reverts this year'"]
  CARD -->|History button| TL["Edit timeline:<br/>edits per month, reverts marked"]
  TL -->|pick a month| ASOF["Article as of that date"]
  ASOF -->|"compare with today"| DIFF["What changed"]
  TL -.-> Q1[("article<br/>FOR SYSTEM_TIME ALL")]
  TL -.-> Q2[("revert_event")]
  ASOF -.-> Q3[("article<br/>FOR SYSTEM_TIME AS OF")]
  CARD -.-> Q2
```

**The two views, one query each**

```sql
-- Read an article as it stood on a date.
SELECT title, rev_id, text FROM article FOR SYSTEM_TIME AS OF '2015-06-01' WHERE page_id = ?;

-- Edit timeline: edits per month (reverts per month come from revert_event the same way).
SELECT DATE_FORMAT(row_start, '%Y-%m') AS month, COUNT(*) AS edits
FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? GROUP BY month;
```

Both depend only on dataset M being loaded into `article`. Nothing else is needed.

**Reverts are found once.** A revert is a version whose text (same `sha1`) already existed earlier
in the same article, with other versions in between. After the load, one statement fills
`revert_event` (built in `build_reverts.py`: 46,015 reverts in 16 s; the shape below):

```sql
INSERT INTO revert_event
SELECT x.page_id, x.rev_id, x.row_start, x.user, x.anonymous,
       x.prev_rev_id, x.prev_end, x.rn - x.prev_rn - 1,
       u.user, u.anonymous
FROM (
  SELECT v.*, LAG(rev_id)  OVER w AS prev_rev_id,   -- the earlier version with the same text
              LAG(row_end) OVER w AS prev_end,      -- = when the first undone edit was saved
              LAG(rn)      OVER w AS prev_rn
  FROM (SELECT page_id, rev_id, user, anonymous, sha1, row_start, row_end,
               ROW_NUMBER() OVER (PARTITION BY page_id ORDER BY row_start) AS rn
        FROM article FOR SYSTEM_TIME ALL) v
  WINDOW w AS (PARTITION BY page_id, sha1 ORDER BY row_start)
) x
JOIN article FOR SYSTEM_TIME ALL u            -- the first undone edit: who was reverted
  ON u.page_id = x.page_id AND u.row_start = x.prev_end
WHERE x.rn - x.prev_rn > 1;                   -- something in between was undone
```

Each row answers: who undid whom, when, how many edits were undone, and how long the undone text
stayed visible (`reverted_at - undone_since`). The edit-war radar and source health are plain
queries on this table. Known limit: an exact-text match misses partial reverts and
rewordings. To check on the first run: versions with no `sha1` and blanked pages all share one
"text", so they would show up as false reverts and need filtering out.

**Time in the Q&A.** Built: a question about how Wikipedia stood on a date (or any question with
`as_of`) goes to the then-vs-now path through the same `/ask` (section "Time-aware retrieval");
other questions are answered from the newest text.

**The source card** is a UI choice with no storage of its own: its numbers come from a count on
`article` and on `revert_event` for that `page_id`.

**Partitions.** The history table keeps the starter's yearly partitions. They cost about 25% more
disk and do not speed up queries at this size, but they show time partitioning in use and let old
years be archived.

## Three choices that made the time features possible

1. **Vectors are keyed by text hash, not by paragraph position.** The same text is embedded once,
   however many articles or revisions contain it. Old paragraph versions can get vectors later by
   embedding only the texts not seen yet: that is how 862,076 versions needed only 353,166 vectors.
2. **Every paragraph keeps the revision it came from.** Citations point at an exact revision, and
   the history features can join any paragraph back to the versioned `article` table.
3. **The full history is loaded, though the plain Q&A reads only the newest revision.** Then-vs-now
   answers, source health, rewind, the edit-war radar and drift all start from that table.

Each feature added its own tables (revert events, paragraph lifetimes, en/sv paragraphs) next to
the core ones; none changed them.

## Code layout

| Path | Does |
| --- | --- |
| `scripts/load_m.py` | Parquet → versioned `article` table (real timestamps, resumable) |
| `scripts/load_s.py` | Shipped S vectors → `article_vector` |
| `scripts/build_reverts.py` | Fills `revert_event` from `article`, once after loading |
| `scripts/build_passages.py` | Newest revision → cleaned text → one passage per section → `passages.parquet`; distinct embedding inputs to embed |
| `scripts/embed_passages.py` | bge-m3 over the distinct texts → parquet of `text_hash, embedding` (streamed); local CPU/GPU |
| `scripts/modal_embed.py` | The same, with `embed()` on up to 8 Modal GPUs |
| `scripts/load_vectors.py` | That parquet → `passage_vector` (or `history_vector` with `--history`); `--verify` measures recall |
| `scripts/build_history.py` | Every version → passages → `passage_text` + system-versioned `passage_history` (lifetimes) |
| `scripts/load_langlinks.py` | en/sv → Finnish article map (`article_langlink`) from dataset S Wikidata ids |
| `scripts/build_xlang.py` | en/sv paragraphs → `xlang_passage` / `xlang_vector`, labelled against Finnish (`passages`, `load`, `label`, `prune`, `--verify`) |
| `scripts/server_setup.sh` | One-command setup of the shared server |
| `scripts/restart_app.sh` | Restart gunicorn on the server (tmux `web`); `gunicorn.conf.py` warms bge-m3 and the link index |
| `app/db.py` | Connection (sets `mhnsw_ef_search = 80`) |
| `app/embed.py` | `embed()`: bge-m3 (pinned revision) for passages *and* questions |
| `app/search.py` | Hybrid retrieval: five lists (passage vectors, names/years FULLTEXT, fi article vectors, en/sv article vectors via `article_langlink`, title mentions), RRF in one statement; `tables=` runs it on L |
| `app/answer.py` | `/ask`: search → Claude → validated cited sentences, cited sources first; time questions go to `timeqa` |
| `app/timeqa.py` | Time questions: routing, passages live on a date (two-stage + global), today's counterpart, word diffs, then-vs-now answer |
| `app/xlang.py` | Cross-language gaps: the `/compare/<page_id>` page, `/api/xlang/<page_id>`, the other-Wikipedias block and the en/sv pills for `/ask` |
| `app/graph.py` | `/api/graph/<page_id>` (wiki links through time), reading path, `/api/related` |
| `app/llm.py` | `complete()`: the one model call; provider and model from `.env` |
| `app/history.py` | Time views: article as of a date (page + JSON), timeline, `stats()` for source cards |
| `app/insights.py` | Trust and editor routes: source health, rewind, edit-war radar, contradictions, citation finder, explain an edit, `/ask/l` |
| `app/translate.py` | `/api/translate`: Opus-MT models on our own server (no API, no key) |
| `app/ask.py` | Page routes: `/` (ask), `/graph/<page_id>`, `/drift`, `/tools` |
| `app/main.py` | Flask app: registers the blueprints; the JSON routes are the API an extension or MCP can use later |
| `schema.sql` | The core tables + `article_langlink`; the history, xlang and L scripts create their own |
| `eval/evaluate.py` | Retrieval eval on the starter's 37 questions, per list and fused; `--l` = the same over dataset L |
| `eval/scale.py` | Per vector table (S, M, M history, L): rows, index recall@10 against an exact scan, search time |
| `eval/answers.py` | Answer eval: 25 new questions, fact match, refusals, a judge call per answer for citation support |
| `tools/make_fixtures.py` | Real-data JSON fixtures for the frontend (`app/static/fixtures/`) |
| `tools/make_drift.py` | `app/static/drift.json` for the drift page: one scan of every paragraph text and lifetime |

## Evaluation

Full tables and method: [`eval/README.md`](../eval/README.md).

- **Search** (starter's 37 questions, right article in the top 5 / 10): 92% / 95% on M, against
  the starter's 76% / 86%; 91% / 94% on dataset L.
- **Answers** (25 new questions): 95% correct facts, 96% of citations support their sentence,
  3/3 refusals on questions Wikipedia can't answer.
- **Vector index:** recall@10 98.6–99.2% at `M=16`, `ef_search = 80`; 4 ms median on M's passages.

## Time-aware retrieval: MariaDB does the time

This is the brief's "both tracks" example: *"what did Wikipedia say about this in 2015, and what has
changed since?"* It is also the strongest answer to the rubric's "effective and creative use of
MariaDB": the hard parts are done by the database, not by application code.

**The idea in one line: meaning lives in the vector, time lives in the table.** The date is
stripped from the question before embedding; it becomes a `FOR SYSTEM_TIME AS OF` filter. Dates
are never mixed into the embeddings: a passage's text doesn't say when it was live, validity is
a range, and a year in the question would pull toward passages that *mention* that year.

```sql
-- "the Moscow peace, as Wikipedia had it on 1 June 2008": one statement, both tracks
SELECT t.page_id, t.title, t.heading, t.text, v.d
FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) AS d
      FROM history_vector ORDER BY d LIMIT 200) v                          -- meaning: vector index
JOIN passage_history FOR SYSTEM_TIME AS OF TIMESTAMP '2008-06-01' h        -- time: system versioning
  USING (text_hash)
JOIN passage_text t USING (text_hash)
ORDER BY v.d LIMIT 8;
```

**What each MariaDB feature contributes**

| MariaDB feature | What it does for us | Without it |
| --- | --- | --- |
| **System-versioned tables + `system_versioning_insert_history`** | `article` (862,076 versions) and `passage_history` (passage lifetimes) carry Wikipedia's *real* edit times, so `AS OF '2008-06-01'` means "what Wikipedia showed that day". Verified: for 15 versions 2003–2026, `AS OF` returns exactly that version's passages. | Hand-written valid-from/valid-to columns and range logic in every query |
| **Native vector index (HNSW, `M=16`, cosine)** | Nearest passages in 2–17 ms; recall@10 ≥ 99% | A separate vector database to keep in sync |
| **Vector search + temporal join in one statement** | Search by meaning, filter by time, cite the version live on that date: one round trip | Two systems glued together in Python |
| **Vectors keyed by text hash** | A passage unchanged across hundreds of versions is embedded once; old versions reuse today's vectors (pilot: 0 hash mismatches between old-version splitting and today's passages). Only texts live ≥ 1 day are embedded, so vandalism costs no GPU time. | Millions of near-identical vectors |
| **Window functions over `FOR SYSTEM_TIME ALL`** | `revert_event`: 46,015 reverts found in one `INSERT ... SELECT`, 16 s over all versions | Python looping over every version |
| **`VEC_DISTANCE_COSINE` inside an article** | "What has changed since": today's counterpart of an old passage found by meaning, so renamed sections still match (*Moskovan neuvottelut* 2008 → *Suomen ja Neuvostoliiton neuvottelut aluemuutoksista*) | Brittle heading matching |
| **`FULLTEXT` + vectors fused by RRF in SQL** | Hybrid retrieval for names and years in Finnish (prefix terms) | A separate search engine |

**Tables added** (`scripts/build_history.py`): `passage_text` (every distinct passage text ever,
with first version and total time live), `passage_history` (system-versioned, one row per
lifetime), `history_vector` (vectors of all texts live ≥ 1 day plus today's; kept apart from
`passage_vector` until the search code is ready to use both).

**Flow for a then-vs-now question:** route (topic + dates) → time-filtered vector search (above)
→ the article version live on that date for the citation (`article FOR SYSTEM_TIME AS OF`) →
today's counterpart by vector distance within the article → word diff → the LLM writes "then"
and "what changed", citing both versions.

**Routing** (`app/timeqa.py`): history questions are full of years (1918, 1939), so a year alone
doesn't make a time question. It needs a year from 2003 on (where M starts) **and** a cue that
the question is about Wikipedia itself (*Wikipedia, sanoi, kertoi, muuttunut, said, changed,
sade, ändrats*); an exact date (`2008-06-01`, `1.6.2008`) or an `as_of` from the UI also counts.
The year and cue words are removed; the rest is the topic that gets embedded. *"What happened in
Finland in 1918?"* and *"Mitä tapahtui vuonna 2008?"* stay plain questions.

**Measured on the full history:** `passage_history` built from all 862,076 versions in 32 min
(530,885 distinct texts, 593,195 lifetimes); 283,065 new texts embedded on Modal in ~15 min;
`history_vector` = 353,166 vectors. A then-vs-now answer takes **~8–17 s** (the model reads up to
12 passages), a plain one ~3 s.

**Global vs two-stage time search.** The global search (vector `LIMIT 500` over all years, then
the `AS OF` filter) leaves 6–170 passages live on the date per question in ~250 ms: the nearest
neighbours are mostly other years' versions of the same paragraphs, so the limit has to be large.
A two-stage variant (today's hybrid search picks ~10 articles, then their passages live on the
date are ranked by exact distance) finds the right sections (*Moskovan rauhan ehdot* @ 2008 →
*Rauhanehdot*) but is blind to topics whose articles were written after the date. **Built: both,
merged** (`then_passages`): two-stage first (today's five-list search picks the top 5 articles,
their 4 nearest passages live on the date by exact distance), then the global search fills the
rest, one passage per (article, section). The two-stage half inherits the cross-language lists,
so *"How has the Wikipedia article on the Finnish Civil War changed since 2007?"* now compares
*Suomen sisällissota* 2007 with today (it found the Sigismund war before). Words like
"article/artikkeli/the" are dropped from the topic.

**What it finds** (real answers): Red prisoners after the civil war, as of 2007 vs now: *~80,000*
→ *76,000*, convicted *~68,000* → *~70,000*, new sentences on the 1927 amnesty and 1973
compensation. Red terror, as of 2006: *~1,650* victims → *1,400–1,650*. Mainila shots, as of 2006:
the war-game origin *"probably"* → *"possibly"*, border-guard observations now *"has been
claimed"*. Finnish Civil War, asked in English as of 2007: the capture of Vyborg went from
*400–800 Reds killed, 5,000–6,000 captured* to *500–800 killed, 12,000–15,000 captured*, with
troop strengths added.

## Cross-language gaps

**The question:** what do English and Swedish Wikipedia say about a topic that the Finnish article
does not, and did the Finnish article ever say it? Dataset S ships 5,254 English and 4,921
Swedish articles on Finnish history; 7,256 Finnish articles have at least one counterpart.

**How** (`scripts/build_xlang.py`, `app/xlang.py`): the en/sv articles are cut with the same
section rule as the Finnish passages (35,829 paragraphs, reference and bibliography sections
skipped) and embedded with the same bge-m3. Each paragraph is then labelled from distances
computed in MariaDB, one set-based query per article against today's Finnish passages and one
against every Finnish passage lifetime (`passage_history FOR SYSTEM_TIME ALL`):

| Label | Rule (cosine distance) | Count (en + sv) |
| --- | --- | --- |
| covered | a Finnish paragraph < 0.28 today; `since` = the first day a close one was live | 13,026 |
| lost | a Finnish paragraph < 0.27 once, none < 0.33 today; dates, and where it lives now | 425 |
| elsewhere | another Finnish article covers it better (< 0.36), e.g. Mainila → *Mainilan laukaukset* | 2,488 |
| partly | the closest Finnish paragraph is on the topic (< 0.36) | 8,779 |
| missing | no Finnish paragraph says this | 11,111 |

All 7,256 articles labelled in 5 minutes. Cut-offs were read off 505 hand-checked pairs on 8
articles.

**Where it shows:** `/compare/<page_id>` (per section: the en/sv paragraph next to the closest
Finnish one, with its label and distance), `/api/xlang/<page_id>`, and on `/ask` an "Other
Wikipedias add" block: up to 3 *missing* en/sv paragraphs from the cited articles' counterparts
that are about as close to the question as the cited Finnish passages and never farther than
0.42 (on 24 test questions it shows on 13), plus an "also in English / only in Finnish" pill per
source.

**Limits:** distance measures "about the same thing", not "states the same facts". *covered* and
*missing* are reliable; *partly* is the grey zone (e.g. English on the December battles at Summa
next to Finnish on the February offensive, distance 0.347). Fix if it matters: a small model
judges only the 8,779 *partly* pairs (~$3–5 once). Only articles with a counterpart in S.

## Scale: S → M → L

The rubric asks for scalability across the datasets. Dataset L is all 568,416 Finnish articles
(current text, Markdown). It goes through the same pipeline into tables with the same
definitions (`l_passage`, `l_vector`: FULLTEXT, `VECTOR INDEX M=16`), so the app's tables stay
untouched and every query runs on L by swapping two table names (`rank(..., tables=...)`).

| Step | L | For comparison (M, today) |
| --- | --- | --- |
| Passages | 1,545,854 from 568,416 articles, built in 63 s | 66,543 |
| Embedding (bge-m3, Modal GPUs) | ~1 h (~420 passages/s) | 6.4 min |
| Loading into the vector index | ~50–740 inserts/s, one writer: hours | minutes |

**Search, measured with the 37 eval questions** (`eval/scale.py`, `eval/evaluate.py --l`; load
stopped at ~700k of L's 1.55M vectors for the measurement; details in
[`eval/README.md`](../eval/README.md)):

| Table | Vectors | recall@10 | index search (median / p95) | exact scan | hit@5 / hit@10 |
| --- | --- | --- | --- | --- | --- |
| S whole articles | 29,460 | 99.2% | 17 / 127 ms | 55 ms | 63% / 77% (alone) |
| M passages | 66,543 | 98.6% | 4.1 / 7.0 ms | 127 ms | 92% / 95% (five lists) |
| M every version | 353,166 | *running* | | | — |
| L passages | ~700,000 | *running* | | | 91% / 94% (five lists) |

The fused search holds its hit rate from M to L; plain passage-vector search drops to 49% hit@5
on L, because near-duplicate paragraphs from other articles crowd out the right one.

## MariaDB: what it costs

What we had to learn to make MariaDB do this; each one is a sentence in the pitch.

- **Keep the vector search in a subquery** and join afterwards, or the index is not used
  (1 ms vs 50 ms). Pass the query vector as a parameter, not a subquery, for the same reason.
- **Index settings matter:** the default `M=6` found 79% of the true top 10; `M=16` with
  `mhnsw_ef_search = 80` gives 99%+.
- **A trailing `LIMIT` on the last `UNION ALL` branch limits the whole union.** Our fifth list
  silently cut the fusion to the first list's 50 rows; the eval caught it.
- **One writer at a time into a vector index.** Parallel loaders gave ~1.4× and then deadlocks
  and lock-wait timeouts; the loader retries a batch on both. Insert speed falls as the graph
  grows (~740/s at the start, ~50/s past 600k vectors), so an index of millions loads for hours.
- **Size the caches, and leave room.** The vector-index cache (`mhnsw_max_cache_size`, default
  16 MB) and the InnoDB buffer pool decide whether inserts and searches hit the disk. Both resize
  live (`SET GLOBAL`). Raising them to 7 + 5 GB with the app running locked up the 16 GB server;
  the load now runs with 5 + 4 GB, the app off, and a free-memory guard.
- **`COUNT(*)` on a vector table is slow** (it reads gigabytes): read progress from the loader's
  log instead. `docker compose restart` keeps the old settings; `up -d` re-reads `.env`.

## Known limits and next steps

- **Search misses** English questions that name no article (*"Who led the Senate that declared
  Finland independent?"*). Lever: translate the question to Finnish before searching (one small
  model call).
- **Answers** can miss a fact whose total sits in a passage the search didn't rank (eval: Red
  prison-camp deaths). Levers: a reranker over the top 50, or more passages per article.
- **Cross-language labels** use fixed distance cut-offs: *covered* and *missing* are reliable,
  *partly* is the grey zone. A small model could judge only the 8,779 *partly* pairs (~$3–5 once).
- **Dataset L** is loaded to ~700k of 1.55M vectors; the rest loads at ~50 inserts/s (hours).
- **Reverts** are exact-text matches (sha1): partial reverts and rewordings are missed.
