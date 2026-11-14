"""Retrieval (owner: A, backend): question -> the passages that answer it.

Hybrid: five ranked lists fused by reciprocal rank fusion (RRF, k = 60) in one SQL statement
(docs/architecture.md, "Chunking, embedding and keyword search"):
  vec  nearest passage vectors                          (meaning, cross-language)
  ft   FULLTEXT in boolean mode with Finnish prefix terms (names, years, rare words)
  art  nearest whole-article vectors (dataset S), each contributing its article's lead passage
  xl   nearest English/Swedish article vectors (dataset S), mapped to their Finnish article by
       Wikidata id (article_langlink), each contributing that article's lead passage: an English
       question meets an English article first, then crosses over
  name en/sv article titles (two words or more) written verbatim in the question, longest first;
       catches long articles whose whole-article vector is too diluted to rank ("Finnish Civil War")
Each vector search stays in its own subquery so MariaDB uses the vector index. No FULL OUTER JOIN
in MariaDB, so the lists are combined with UNION ALL + GROUP BY.

    python -m app.search          # self-check of the prefix-term rule (no database needed)
"""
import re
from contextlib import closing

from app.db import connect
from app.embed import embed

CANDIDATES = 50          # per list, before fusion
RRF_K = 60
STOP = {"mikä", "mitkä", "mitä", "milloin", "kuka", "ketkä", "kenen", "missä", "mistä", "mihin",
        "miksi", "miten", "kuinka", "minkä", "joka", "jotka", "oli", "olivat", "ovat", "sekä",
        "the", "what", "when", "who", "which", "where", "how", "vad", "när", "vem", "vilken", "hur"}

LISTS = {
    "vec": """SELECT p.passage_id, ROW_NUMBER() OVER (ORDER BY v.d) AS r
              FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) AS d
                    FROM passage_vector ORDER BY d LIMIT {n}) v
              JOIN passage p USING (text_hash)""",
    "ft": """SELECT passage_id, ROW_NUMBER() OVER (ORDER BY s DESC) AS r
             FROM (SELECT passage_id, MATCH (title, heading, text) AGAINST (? IN BOOLEAN MODE) AS s
                   FROM passage WHERE MATCH (title, heading, text) AGAINST (? IN BOOLEAN MODE)
                   ORDER BY s DESC LIMIT {n}) f""",
    "art": """SELECT p.passage_id, ROW_NUMBER() OVER (ORDER BY v.d) AS r
              FROM (SELECT page_id, VEC_DISTANCE_COSINE(embedding, ?) AS d
                    FROM article_vector WHERE lang = 'fi' ORDER BY d LIMIT 30) v
              JOIN passage p ON p.page_id = v.page_id AND p.position = 0""",
    "xl": """SELECT p.passage_id, ROW_NUMBER() OVER (ORDER BY v.d) AS r
             FROM (SELECT lang, page_id, VEC_DISTANCE_COSINE(embedding, ?) AS d
                   FROM article_vector WHERE lang IN ('en', 'sv') ORDER BY d LIMIT 30) v
             JOIN article_langlink l ON l.lang = v.lang AND l.page_id = v.page_id
             JOIN passage p ON p.page_id = l.fi_page_id AND p.position = 0""",
    "name": """SELECT p.passage_id, ROW_NUMBER() OVER (ORDER BY CHAR_LENGTH(l.title) DESC) AS r
               FROM article_langlink l JOIN passage p ON p.page_id = l.fi_page_id AND p.position = 0
               WHERE l.title LIKE '% %' AND INSTR(?, l.title) > 0""",  # no LIMIT here: a trailing LIMIT cuts the whole UNION
}
ALL = ("vec", "ft", "art", "xl", "name")


def fulltext_terms(question, names_only=False):
    """Boolean-mode terms: words of 6+ letters keep all but their last 3 letters (at least 4) and
    get `*` (Kekkonen -> kekko*), because FULLTEXT has no Finnish stemming; numbers and shorter
    words stay exact; question words are dropped. names_only: keep only numbers and capitalised
    words after the first (names, places, years), the job the keyword half is for.
    ponytail: crude stemmer, tune on the eval."""
    terms = []
    words = re.findall(r"\w+", question)
    for i, w in enumerate(words):
        if names_only and not (w.isdigit() or (i > 0 and w[:1].isupper())):
            continue
        w = w.lower()
        if w in STOP or len(w) < 3:
            continue
        terms.append(w if w.isdigit() or len(w) < 6 else w[:max(4, len(w) - 3)] + "*")
    return " ".join(dict.fromkeys(terms))


def rank(vector, question="", k=8, per_article=2, lists=ALL, names_only=True):
    """Top k passages, at most per_article from one article (None = no cap).
    ponytail: per_article=2 is a starting value, not measured; the eval decides."""
    terms = fulltext_terms(question, names_only) if "ft" in lists else ""
    parts, params = [], []
    for name in lists:
        if name == "ft" and not terms:
            continue
        parts.append(LISTS[name].format(n=CANDIDATES))
        params += {"ft": [terms, terms], "name": [question]}.get(name, [vector])
    sql = f"""SELECT p.passage_id, p.page_id, p.rev_id, p.title, p.heading, p.text, x.score
              FROM (SELECT passage_id, SUM(1 / ({RRF_K} + r)) AS score
                    FROM ({" UNION ALL ".join(parts)}) u GROUP BY passage_id) x
              JOIN passage p USING (passage_id)
              ORDER BY x.score DESC LIMIT {CANDIDATES * 2}"""
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    out, seen = [], {}
    for passage_id, page_id, rev_id, title, heading, text, score in rows:
        if per_article and seen.get(page_id, 0) >= per_article:
            continue
        seen[page_id] = seen.get(page_id, 0) + 1
        out.append({"passage_id": passage_id, "page_id": page_id, "rev_id": rev_id, "title": title,
                    "heading": heading, "text": text, "score": round(float(score), 5)})
        if len(out) == k:
            break
    return out


def search(question, k=8, as_of=None, per_article=2):
    """The contract in tasks/plan.md. as_of is not used here: dated questions go to app.timeqa."""
    return rank(embed([question])[0], question, k, per_article)


if __name__ == "__main__":
    assert fulltext_terms("Milloin Kekkonen oli presidentti?") == "kekko* presiden*"
    assert fulltext_terms("talvisota 1939–1940") == "talvis* 1939 1940"
    assert fulltext_terms("YYA-sopimus") == "yya sopi*"
    assert fulltext_terms("Who was it?") == "was"
    assert fulltext_terms("Milloin Kekkonen oli presidentti vuonna 1956?", names_only=True) == "kekko* 1956"
    assert fulltext_terms("Which peace treaty ended the Winter War?", names_only=True) == "wint* war"
    print("ok")
