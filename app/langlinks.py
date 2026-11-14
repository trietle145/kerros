"""The same topic in other languages (owner: A, backend): a Finnish article's Swedish and English
Wikipedia counterparts, matched by Wikidata id in dataset S (data/s). Read once, on first use.
Without data/s every article simply has no counterparts.

    python -m app.langlinks      # self-check (needs data/s)
"""
from functools import lru_cache

import pyarrow.parquet as pq

from scripts.common import ROOT

S = ROOT / "data" / "s"


@lru_cache(maxsize=1)
def _counterparts():
    """{fi page_id: {"en": {"title", "url"}, "sv": {...}}} for Finnish articles with a counterpart."""
    by_qid = {}
    for lang in ("en", "sv"):
        path = S / f"articles-{lang}.parquet"
        if path.exists():
            for r in pq.read_table(path, columns=["wikidata_id", "title", "url"]).to_pylist():
                if r["wikidata_id"]:
                    by_qid.setdefault(r["wikidata_id"], {})[lang] = {"title": r["title"], "url": r["url"]}
    fi = S / "articles-fi.parquet"
    if not fi.exists():
        return {}
    return {r["page_id"]: by_qid[r["wikidata_id"]]
            for r in pq.read_table(fi, columns=["page_id", "wikidata_id"]).to_pylist()
            if r["wikidata_id"] in by_qid}


def other_languages(page_id):
    """-> {"en": {"title", "url"}, "sv": {...}}, only the languages that exist (often empty)."""
    return _counterparts().get(page_id, {})


if __name__ == "__main__":
    c = _counterparts()
    print(f"{len(c):,} Finnish articles with a counterpart; "
          f"{sum('en' in v for v in c.values()):,} English, {sum('sv' in v for v in c.values()):,} Swedish")
    assert other_languages(1256)["en"]["title"] == "Winter War", other_languages(1256)
    assert other_languages(999999999) == {}
    print("Talvisota ->", other_languages(1256))
    print("ok")
