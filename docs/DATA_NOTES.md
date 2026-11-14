# Data notes: what is in the live database

Explored 2026-11-14 on the shared server (MariaDB 12.3.3, database `wiki`) with a read-only
login, for planning a knowledge-graph view. All numbers below were measured, not taken from
the docs, unless marked. Times are over the SSH tunnel, warm.

## The five tables at a glance

| Table | Rows | What one row is | Key |
| --- | --- | --- | --- |
| `article` | 19,742 current, 862,076 with history (load figure) | One version of one fi article, raw wikitext | `(page_id, row_end)` |
| `passage` | 66,642 (19,694 articles) | One section (or ~300-word part of one) of the newest version, plain text | `passage_id`; unique `(page_id, position)` |
| `passage_vector` | 66,642 | bge-m3 vector of one passage | `text_hash` |
| `article_vector` | 29,460 (fi 19,285, sv 4,921, en 5,254) | Dataset S whole-article vector | `(lang, page_id)` |
| `revert_event` | 46,015 (6,856 articles) | One revert found by sha1 | `(page_id, rev_id)` |

`information_schema.tables.table_rows` is an InnoDB estimate (it says 58,563 passages); use
`COUNT(*)` when the number matters.

### How they join

```
article.page_id ──┬── passage.page_id            (passage.rev_id = article.rev_id of the current row, always)
                  ├── article_vector.page_id     (only WHERE lang = 'fi'; sv/en page_ids are other wikis)
                  └── revert_event.page_id       (revert_event.rev_id / restored_rev_id = article.rev_id in history)
passage.text_hash ─── passage_vector.text_hash   (1:1 today: every passage has a vector, every hash is distinct)
```

Checked:
- All 19,694 passage articles join to a current `article` row with the same `rev_id` and title.
- 48 current articles have no passages: mostly redirects, plus a few odd pages (*Spear Air*).
- All 19,285 fi vectors match an M article; **457 M articles have no fi vector** (S is a
  slightly smaller, older snapshot, Aug 2025).
- sv and en rows have **no title or text anywhere in the database**, only `page_id` + vector.
  There is no fi↔sv/en mapping table. They can only be reached through vector similarity.
- `article` has **no index on `title`** and none on `rev_id`. Title lookups on current rows are
  fine (19,742 rows, ~0.06 s); always pair `rev_id` with `page_id` in history.
- `passage.title` has only the FULLTEXT index (title, heading, text), no B-tree.

## `article`: system versioning

- Every version is a row. The current version has `row_end = '2106-02-07 06:28:15.999999'`
  (MariaDB's max TIMESTAMP); older ones are history rows. `row_start` / `row_end` are
  **INVISIBLE**: name them explicitly, `SELECT *` won't show them.
- `row_start` is the real Wikipedia save time (UTC; server and session time zone are UTC).
  `row_end` is the next version's `row_start`. So `AS OF` means "what Wikipedia showed then".
- Date range: first version **2003-02-21**, newest edit **2026-10-01 10:59**.
  Articles existing on 2010-01-01: 8,788. Newest article created 2026-09-27.
- Partitioned **by `row_end` per year** (p0 = ended before 2003, ..., `pn` = current). History
  rows sit in the year their version was *replaced*. `WHERE row_end < X` and `AS OF X` both
  prune partitions (checked with `EXPLAIN PARTITIONS`).
- Columns per version: `rev_id, parent_id, user, anonymous, comment, minor, sha1, len, text`.
  `parent_id` is NULL for the first version.
- Titles: in every sampled page, all versions carry the same title. The dataset seems to store
  the current title on every version, so renames are probably **not** visible. Not proven over
  all pages (that needs a full history scan).
- Example, *Mainilan laukaukset* (page 8295): 177 versions 2004–2026, 159 distinct texts, grew
  from 441 to 17,532 bytes, 15 links in 2005 → 61 today. *Talvisota* has 2,143 versions,
  *Jatkosota* 1,671.

Syntax gotcha: `FOR SYSTEM_TIME AS OF '2010-01-01'` works, `AS OF TIMESTAMP '2010-01-01'`
fails ("Incorrect DATETIME value"); with `TIMESTAMP` add the time: `TIMESTAMP '2010-01-01 00:00:00'`.
`FOR SYSTEM_TIME BEFORE` does not exist in MariaDB.

## Links between articles

**Only the raw wikitext in `article.text` has links.** `passage.text` is clean plain text with
no link markup (14 of 66,642 passages still contain leftover `[[`/`{{`, e.g. an image caption
in *Suinulan verilöyly*). The S Markdown and its category tree are not in the database, and no
data files are on this laptop.

What the wikitext holds (sample of 494 current articles spread over `page_id`, 3.2 MB):

| | Median per article | Note |
| --- | --- | --- |
| Article links `[[Target]]`, `[[Target\|label]]` | 19 (max 530) | |
| Distinct targets **inside the 19,742-article set** | 4 (mean 6.4) | 62 of 494 articles have none |
| Categories `[[Luokka:...]]` | 3 | Only 1 article had none |

- Full set (all current rows parsed, 5.4 s fetch + 1.0 s parse): **138,730 links inside the
  set** over 19,600 non-redirect articles. Linked neighbours (in or out) per article: median 5;
  71% have fewer than 10; 1,595 have none. Hubs: *Talvisota* has 104 out, 1,453 in, 81 mutual.
- 23 yearly `AS OF` snapshots of 20 articles (`page_id IN (...)`): 1.0–1.3 s, ~10 MB of text.
- Only ~32% of article-link occurrences land inside the set. The most-linked missing targets
  are the big general topics: *Helsinki*, *Suomi*, *Turku*, *Venäjä*, *Ruotsi*,
  *Neuvostoliitto*, *Ensimmäinen maailmansota*, the parties (*Suomen Sosialidemokraattinen
  Puolue*, *Kansallinen Kokoomus*). M is the "History of Finland" category tree, not all of fi
  Wikipedia. *Talvisota*, *Jatkosota*, *Suomen sisällissota*, *Urho Kekkonen* and *Suomen
  historia* are in.
- Redirects: 142 current rows are redirects (`#OHJAUS [[X]]` or `#REDIRECT [[X]]`), and only
  62 point inside the set. Some targets use underscores (`[[J._V._Snellman]]`).
- Links inside **templates** (infobox fields) are in the text and count. Navigation boxes
  (`{{Talvisota}}` etc.) are *not expanded*, so their links are missing. The live site shows
  more links than the wikitext gives us.
- Links exist **in every old version too**, so a link graph as of any date can be built from
  `FOR SYSTEM_TIME AS OF`.

Parsing rules learned from the sample (all needed):
1. Pattern `\[\[([^\[\]|#]*)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]`: drop `#section` and `|label`.
2. Skip namespace links by a **known prefix list**, not "contains a colon": 44 real titles
   contain colons (*Kustaa III:n sota*, *Star Wreck V: Lost Contact*). Prefixes seen: `Luokka`,
   `luokka`, `Tiedosto`, `Kuva`, `kuva`, `File`, interwiki/sister `en`, `s`, `wikt`,
   `gutenberg`. Add `Image`, `Category`, `Wikipedia`, `Malline`, `Käyttäjä` to be safe.
3. A leading colon (`[[:Luokka:X]]`) is a link *to* a category page, not a categorisation.
4. Normalise: underscores → spaces, trim, uppercase the first letter (all 19,742 titles start
   uppercase, none contain `_`).
5. Resolve through the redirect map, then the current title → page_id map. Drop self links.

## `article_vector` and `passage_vector`

- `article_vector`: one bge-m3 vector per S article, `model = 'bge-m3'`, 290 of 29,460 marked
  `truncated` (article longer than the model reads). fi page_ids = fi Wikipedia ids (match
  `article`); sv/en page_ids are sv/en Wikipedia ids.
- `passage_vector`: `model = 'BAAI/bge-m3'` (spelled differently from `article_vector`, same
  model), embedding input `title \n heading \n text`.
- Both have `VECTOR INDEX M=16 cosine`; `app.db.connect()` sets `mhnsw_ef_search = 80`.
- **Neighbours of a stored vector need no `embed()`**: read a row's vector into `@v` and search
  with it. Mixed languages work: the nearest rows to *Mainilan laukaukset* include en and sv
  articles (bge-m3 is multilingual), but there are no titles to show for them.
- Example: nearest fi articles to *Mainilan laukaukset* are *Talvisota* (0.28), *Moskovan
  välirauha*, *Välirauha*, *Moskovan rauhansopimus (1940)*, *Jatkosota*, *Talvisodan tausta*
  (0.34). Plausible, but one outlier (*Kornilovin kapina*, 0.33).

## Ready-to-use SQL

Run through `app.db.connect()` (it sets `ef_search`). `%s`/`?` is the connector's parameter
marker (`mariadb` uses `?`).

```sql
-- Current articles: id ↔ title map (19,742 rows, ~0.1 s)
SELECT page_id, title, rev_id, len FROM article;

-- Redirect pages (current), to resolve link targets
SELECT page_id, title, LEFT(text, 300) FROM article WHERE text LIKE '#%';

-- Raw wikitext of current articles in batches (all current text = 134 MB)
SELECT page_id, title, text FROM article WHERE page_id IN (?, ?, ...);

-- One article as it was on a date (uses start_key, prunes partitions)
SELECT rev_id, row_start, title, len, text
FROM article FOR SYSTEM_TIME AS OF '2010-01-01' WHERE page_id = ?;

-- Every article that existed on a date (~0.6 s for 2010; whole set, add a column list)
SELECT page_id, title, rev_id FROM article FOR SYSTEM_TIME AS OF '2010-01-01';

-- Version list of one article (the timeline)
SELECT rev_id, parent_id, row_start, row_end, user, anonymous, minor, len, sha1, comment
FROM article FOR SYSTEM_TIME ALL WHERE page_id = ? ORDER BY row_start;

-- Edits per article in a period (one page; for many pages loop or use IN)
SELECT page_id, COUNT(*) FROM article FOR SYSTEM_TIME ALL
WHERE page_id IN (?, ?) AND row_start >= '2010-01-01' AND row_start < '2011-01-01' GROUP BY page_id;

-- Reverts of one article, newest first
SELECT rev_id, reverted_at, restored_rev_id, undone_since, undone_edits, undone_anonymous
FROM revert_event WHERE page_id = ? ORDER BY reverted_at DESC LIMIT 50;

-- Most reverted articles (46k rows, cheap)
SELECT r.page_id, a.title, COUNT(*) reverts FROM revert_event r JOIN article a USING (page_id)
GROUP BY r.page_id ORDER BY reverts DESC LIMIT 20;

-- Passages of one article in reading order
SELECT position, heading, text, rev_id FROM passage WHERE page_id = ? ORDER BY position;

-- Nearest fi articles to an article, from its stored vector (no embed(); ~0.1–0.4 s)
-- The variable must be set in its own statement; in Python execute it without fetching.
SELECT embedding INTO @v FROM article_vector WHERE lang = 'fi' AND page_id = ?;
SELECT v.page_id, a.title, v.d FROM (
  SELECT page_id, VEC_DISTANCE_COSINE(embedding, @v) d
  FROM article_vector WHERE lang = 'fi' ORDER BY d LIMIT 10) v
JOIN article a USING (page_id) ORDER BY d;

-- Nearest passages to a passage (vector search in the subquery, join after: keeps the index)
SELECT embedding INTO @v FROM passage_vector WHERE text_hash = ?;
SELECT p.page_id, p.title, p.heading, v.d FROM (
  SELECT text_hash, VEC_DISTANCE_COSINE(embedding, @v) d
  FROM passage_vector ORDER BY d LIMIT 10) v
JOIN passage p USING (text_hash) ORDER BY d;
```

Note: `WHERE lang = 'fi'` with the vector index is an index search plus a filter. fi is two
thirds of the table, so 10 results still come back, but ask for more (`LIMIT 30`) if a
filter is narrower.

## Costs to keep in mind

| Query | Cost |
| --- | --- |
| Anything on current `article` rows (no `FOR SYSTEM_TIME`) | 19,742 rows; scans 0.06–1.5 s (LIKE on text ~1.5 s) |
| One page's history (`FOR SYSTEM_TIME ALL WHERE page_id = ?`) | ~0.01–0.06 s, even for 2,143 versions |
| `AS OF` a date, whole set | ~0.6 s |
| `FOR SYSTEM_TIME ALL` without `page_id` / `row_end` filter | full 862k-row, 6 GB scan: avoid |
| `COUNT(*)` on `passage_vector` | 7 s (wide rows); use `passage` counts instead |
| Vector top-k on either vector table | 0.06–0.4 s (first call after a restart is slower) |
| All current wikitext | 134 MB over the tunnel (a 3.2 MB sample took 0.1 s) |

## Open questions

1. **Graph scope.** Only ~1/3 of links stay inside the 19,742 articles. Drop links that leave
   the set, or show the top outside targets (*Helsinki*, *Suomi*) as stub nodes with a title
   only? Dataset L (all 568k fi titles) would name them but isn't loaded.
2. **Categories.** S ships a category tree that isn't in the database or on this laptop. Use
   `[[Luokka:]]` from the wikitext (median 3 per article, flat, no hierarchy), or get S loaded?
3. **Where edges live.** The login is read-only, so a link table can't be created here. Compute
   edges in Python at app start (seconds), or ask Triet for a table (A owns the data side)?
4. **sv/en vectors** have no titles in the DB: leave them out of the graph?
