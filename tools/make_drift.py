"""Narrative drift data: how often Finnish Wikipedia used competing names for the same thing, year
by year since 2003, and the edits where one name replaced the other. Read-only (SELECT only).

One scan of passage_text finds every paragraph text that uses any term; passage_history (system-
versioned, real edit times) says when each text was live, per article. A term "is used by" an
article at the end of a year when one of its paragraphs live then contains the term.

    .venv\\Scripts\\python.exe tools\\make_drift.py      # ~2-3 min over the tunnel -> app/static/drift.json
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

FIRST, LAST = 2003, 2026
# Each topic: competing terms. Patterns are Finnish stems so every case ending matches
# (vapaussota, vapaussodan, vapaussotaa ...). LIKE prefilters, the regex decides.
TOPICS = [
    {"id": "1918", "title": "The war of 1918",
     "note": "What to call the 1918 war has divided Finland for a century: the winners' 'War of Liberation' or a 'civil war'.",
     # only paragraphs about Finland's 1918 (not the Spanish or Estonian wars of the same name)
     "require": r"1918|suomen (?:sisällis|vapaus|kansalais)so[dt]",
     "synonyms": True,                                # names for the same thing: a swap is a rename
     "terms": [{"term": "sisällissota", "en": "civil war", "like": "sisällisso", "re": r"sisällis(?:so[dt])"},
               {"term": "vapaussota", "en": "war of liberation", "like": "vapausso", "re": r"(?<!viron )(?<!latvian )(?<!liettuan )vapaus(?:so[dt])"},
               {"term": "kansalaissota", "en": "citizens' war", "like": "kansalaisso", "re": r"kansalais(?:so[dt])"},
               {"term": "punakapina", "en": "red rebellion", "like": "punakapin", "re": r"punakapin"},
               {"term": "luokkasota", "en": "class war", "like": "luokkaso", "re": r"luokka(?:so[dt])"}]},
    {"id": "camps", "title": "The prison camps of 1918",
     "note": "The camps for captured Reds: 'prison camp' or 'concentration camp'?",
     "require": r"1918|punavan|punavank|punaist",
     "synonyms": True,
     "terms": [{"term": "vankileiri", "en": "prison camp", "like": "vankileir", "re": r"vankileir"},
               {"term": "keskitysleiri", "en": "concentration camp", "like": "keskitysleir", "re": r"keskitysleir"}]},
    {"id": "terror", "title": "Red and white terror",
     "note": "Did Wikipedia name the violence of both sides, and when?",
     "terms": [{"term": "punainen terrori", "en": "red terror", "like": "terror", "re": r"punai\w* terror"},
               {"term": "valkoinen terrori", "en": "white terror", "like": "terror", "re": r"valkoi\w* terror"}]},
    {"id": "finlandization", "title": "Finlandization",
     "note": "A word for Cold War self-censorship towards the Soviet Union, once contested in Finland itself.",
     "terms": [{"term": "suomettuminen", "en": "Finlandization", "like": "suomettu", "re": r"suomettu"},
               {"term": "YYA-sopimus", "en": "the 1948 treaty", "like": "YYA", "re": r"\bYYA"}]},
]
TERMS = [t for topic in TOPICS for t in topic["terms"]]
YEARS = list(range(FIRST, LAST + 1))
FOREVER = datetime(2038, 1, 1)


def year_end(y):
    return datetime(y, 12, 31, 23, 59, 59) if y < LAST else datetime.now()


def context(text, rx, width=70):
    """The term with a few words around it, cut at word boundaries."""
    m = re.search(rx, text, re.I)
    if not m:
        return ""
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    a = text.rfind(" ", 0, a) + 1 if a else 0
    b = text.find(" ", b) if text.find(" ", b) != -1 else len(text)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def main():
    t0 = time.time()
    cur = connect().cursor()
    likes = sorted({t["like"] for t in TERMS})
    cur.execute("SELECT text_hash, page_id, title, text FROM passage_text WHERE " +
                " OR ".join("text LIKE ?" for _ in likes), [f"%{x}%" for x in likes])
    texts = {}                                           # hash -> (page_id, title, text, {term})
    for h, page_id, title, text in cur:
        hit = {t["term"] for topic in TOPICS for t in topic["terms"]
               if re.search(t["re"], text, re.I) and re.search(topic.get("require", ""), text, re.I)}
        if hit:
            texts[bytes(h)] = (page_id, title, text, hit)
    print(f"scan: {len(texts)} texts use a term ({time.time() - t0:.0f} s)")

    hashes = list(texts)
    spans = []                                           # (hash, page_id, rev_id, start, end)
    for i in range(0, len(hashes), 2000):
        part = hashes[i:i + 2000]
        cur.execute("SELECT text_hash, page_id, rev_id, row_start, row_end FROM passage_history "
                    f"FOR SYSTEM_TIME ALL WHERE text_hash IN ({','.join('?' * len(part))})", part)
        spans += [(bytes(h), p, r, s, e) for h, p, r, s, e in cur]
    print(f"lifetimes: {len(spans)} ({time.time() - t0:.0f} s)")

    # articles live at each year end (the denominator): one pass over all article lifetimes
    cur.execute("SELECT page_id, MIN(row_start) FROM article FOR SYSTEM_TIME ALL GROUP BY page_id")
    born = [s for _, s in cur]
    total = {y: sum(s <= year_end(y) for s in born) for y in YEARS}

    series = {t["term"]: {y: set() for y in YEARS} for t in TERMS}
    for h, page_id, _, start, end in spans:
        for y in YEARS:
            if start <= year_end(y) < end:
                for term in texts[h][3]:
                    series[term][y].add(page_id)

    # flips: on one article, a paragraph using term A ended at the moment one using term B began
    # (same edit), and the new text no longer uses A. Edits replacing one name with another.
    by_page = defaultdict(list)
    for s in spans:
        by_page[s[1]].append(s)
    flips = defaultdict(list)
    rx = {t["term"]: t["re"] for t in TERMS}
    for topic in TOPICS:
        names = [t["term"] for t in topic["terms"]]
        for page_id, rows in by_page.items():
            ends = defaultdict(list)
            for h, _, rev, start, end in rows:
                if end < FOREVER:
                    ends[end].append(h)
            for h, _, rev, start, end in rows:
                for old in ends.get(start, ()):
                    a, b = texts[old][3], texts[h][3]
                    for x in names:
                        for y in names:
                            if x != y and x in a and x not in b and y in b and y not in a:
                                flips[topic["id"]].append({
                                    "from": x, "to": y, "page_id": page_id, "title": texts[h][1],
                                    "rev_id": rev, "at": start.date().isoformat(),
                                    "before": context(texts[old][2], rx[x]), "after": context(texts[h][2], rx[y])})
    out = {"generated": datetime.now().date().isoformat(), "years": YEARS,
           "articles": [total[y] for y in YEARS], "topics": []}
    for topic in TOPICS:
        f = sorted(flips[topic["id"]], key=lambda e: e["at"])
        seen, uniq = set(), []
        for e in f:                                      # one example per article and direction
            if (e["page_id"], e["from"], e["to"]) not in seen:
                seen.add((e["page_id"], e["from"], e["to"]))
                uniq.append(e)
        if not topic.get("synonyms"):
            uniq = []                                    # different things, not names for one: no "renames"
        out["topics"].append({**{k: topic[k] for k in ("id", "title", "note")}, "synonyms": bool(topic.get("synonyms")),
                              "terms": [{"term": t["term"], "en": t["en"],
                                         "counts": [len(series[t["term"]][y]) for y in YEARS]}
                                        for t in topic["terms"]],
                              "flips": uniq[:40], "flip_count": len(uniq),
                              "directions": [{"from": a, "to": b, "count": n} for (a, b), n in
                                             Counter((e["from"], e["to"]) for e in uniq).most_common()]})
    # self-check: counts never exceed the articles alive that year; every flip is a real change
    for topic in out["topics"]:
        for t in topic["terms"]:
            assert all(c <= n for c, n in zip(t["counts"], out["articles"])), t["term"]
        assert all(e["from"] != e["to"] and e["before"] and e["after"] for e in topic["flips"])
    path = ROOT / "app" / "static" / "drift.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for topic in out["topics"]:
        print(topic["id"], {t["term"]: (t["counts"][0], t["counts"][-1]) for t in topic["terms"]},
              "flips", topic["flip_count"])
    print(f"wrote {path} ({path.stat().st_size // 1024} KB, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
