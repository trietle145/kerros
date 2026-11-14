"""Cut the current version of each Finnish article into passages (task 1.A6).

One passage per section, the lead included; a section over ~300 words is split at paragraph
boundaries; never merged across sections, no overlap; reference and link sections are skipped.
Reads the current rows of the versioned `article` table (= M's newest version of each article).

    python scripts/build_passages.py --titles "Talvisota,Jatkosota" --out data/pilot/passages.parquet
    python scripts/build_passages.py                 # all articles -> data/passages.parquet
    python scripts/build_passages.py --show 10       # print 10 random passages from the output

The embedding input and its hash are fixed decisions (CLAUDE.md): changing embedding_input()
means embedding everything again.
"""
import argparse
import hashlib
import random
import re
import statistics
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from common import ROOT, connect
from wikitext import clean

MAX_WORDS = 300
SKIP = {"lähteet", "viitteet", "aiheesta muualla", "katso myös", "kirjallisuutta",
        "kirjallisuus", "lähdeluettelo", "huomautukset"}
REDIRECT = re.compile(r"\s*#(UUDELLEENOHJAUS|REDIRECT)", re.I)
SCHEMA = pa.schema([("page_id", pa.uint32()), ("rev_id", pa.uint32()), ("title", pa.string()),
                    ("position", pa.uint16()), ("heading", pa.string()), ("text", pa.string()),
                    ("text_hash", pa.binary(32))])


def embedding_input(title, heading, text):
    """The exact text that is embedded; the lead has no heading, so its middle line is empty."""
    return f"{title}\n{heading or ''}\n{text}"


def sections(wikitext):
    """Yield (heading, [blocks]); heading None for the lead. Skipped sections drop their subsections."""
    heading, blocks, skip_level = None, [], None
    for kind, text in clean(wikitext):
        if kind[0] != "h":
            if not skip_level:
                blocks.append(text)
            continue
        level = int(kind[1:])
        if skip_level and level > skip_level:
            continue
        if blocks:
            yield heading, blocks
        heading, blocks = text, []
        skip_level = level if text.lower() in SKIP else None
    if blocks:
        yield heading, blocks


def pieces(blocks):
    """Split one section's blocks into pieces of up to MAX_WORDS words, at block boundaries.
    ponytail: one block over MAX_WORDS stays whole (embed() truncates at 1,024 tokens, ~500 words)."""
    piece, words = [], 0
    for b in blocks:
        n = len(b.split())
        if piece and words + n > MAX_WORDS:
            yield "\n".join(piece)
            piece, words = [], 0
        piece.append(b)
        words += n
    yield "\n".join(piece)


def passages(page_id, rev_id, title, wikitext):
    position = 0
    for heading, blocks in sections(wikitext):
        for text in pieces(blocks):
            yield {"page_id": page_id, "rev_id": rev_id, "title": title, "position": position,
                   "heading": heading, "text": text, "text_hash": hashlib.sha256(
                       embedding_input(title, heading, text).encode("utf-8")).digest()}
            position += 1


def build(titles, out):
    cur = connect().cursor()
    sql = "SELECT page_id, rev_id, title, text FROM article"
    if titles:
        sql += " WHERE title IN (%s)" % ",".join("?" * len(titles))
    start = time.time()
    cur.execute(sql, titles or ())
    rows, articles, redirects = [], 0, 0
    for page_id, rev_id, title, text in cur:
        if REDIRECT.match(text):
            redirects += 1
            continue
        articles += 1
        rows += passages(page_id, rev_id, title, text)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, SCHEMA), out)
    words = sorted(len(r["text"].split()) for r in rows)
    print(f"{articles} articles ({redirects} redirects skipped) -> {len(rows)} passages, "
          f"{len({r['text_hash'] for r in rows})} distinct texts, in {time.time() - start:.0f} s")
    print(f"words per passage: median {statistics.median(words):.0f}, "
          f"95% under {words[int(len(words) * .95)]}, max {words[-1]}; written to {out}")


def show(path, n):
    rows = pq.read_table(path).to_pylist()
    for r in random.sample(rows, min(n, len(rows))):
        print(f"--- {r['title']} / {r['heading'] or '(lead)'} #{r['position']} "
              f"https://fi.wikipedia.org/?oldid={r['rev_id']}\n{r['text']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", help="comma-separated article titles (default: all)")
    ap.add_argument("--out", default=str(ROOT / "data" / "passages.parquet"))
    ap.add_argument("--show", type=int, metavar="N", help="print N random passages from --out and exit")
    args = ap.parse_args()
    out = Path(args.out)
    if args.show:
        return show(out, args.show)
    build(args.titles.split(",") if args.titles else None, out)


if __name__ == "__main__":
    main()
