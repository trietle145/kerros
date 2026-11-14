"""English and Swedish counterparts of the Finnish articles -> article_langlink (backend, A).
Matched by Wikidata id in dataset S, so search can go from an en/sv article vector to the Finnish
article inside one SQL statement.

    python scripts/load_langlinks.py      # rebuilds the table (~10k rows, seconds), then checks it
"""
import pyarrow.parquet as pq

from common import ROOT, connect

S = ROOT / "data" / "s"
TABLE = """CREATE TABLE IF NOT EXISTS article_langlink (
  lang        CHAR(2) NOT NULL,              -- en or sv
  page_id     INT UNSIGNED NOT NULL,         -- the en/sv article (as in article_vector)
  fi_page_id  INT UNSIGNED NOT NULL,         -- the Finnish article on the same topic
  title       VARCHAR(255) NOT NULL,         -- the en/sv title
  PRIMARY KEY (lang, page_id),
  KEY (fi_page_id)
) CHARACTER SET utf8mb4"""


def main():
    fi = {r["wikidata_id"]: r["page_id"]
          for r in pq.read_table(S / "articles-fi.parquet", columns=["page_id", "wikidata_id"]).to_pylist()
          if r["wikidata_id"]}
    rows = [(lang, r["page_id"], fi[r["wikidata_id"]], r["title"])
            for lang in ("en", "sv")
            for r in pq.read_table(S / f"articles-{lang}.parquet",
                                   columns=["page_id", "wikidata_id", "title"]).to_pylist()
            if r["wikidata_id"] in fi]
    con = connect()
    cur = con.cursor()
    cur.execute(TABLE)
    cur.execute("TRUNCATE TABLE article_langlink")
    cur.executemany("INSERT INTO article_langlink VALUES (?,?,?,?)", rows)
    con.commit()
    cur.execute("SELECT lang, COUNT(*) FROM article_langlink GROUP BY lang")
    print("article_langlink:", dict(cur.fetchall()))
    cur.execute("SELECT fi_page_id FROM article_langlink WHERE lang = 'en' AND title = 'Winter War'")
    assert cur.fetchone() == (1256,), "Winter War should map to Talvisota (1256)"
    print("ok")


if __name__ == "__main__":
    main()
