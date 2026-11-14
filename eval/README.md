# Evaluation

Three questions, three scripts. All numbers measured on the shared server on 2026-11-14.

| Script | Question it answers | Cost |
| --- | --- | --- |
| `evaluate.py` | Does search find the right article? (`--l`: over dataset L) | free, ~2 min, needs bge-m3 |
| `answers.py` | Are the answers right, and does every citation hold? | ~$2 (≈50 model calls), ~5 min |
| `scale.py` | Does the vector index stay accurate and fast as the tables grow? | free, slow on big tables (exact scans) |

## 1. Search: is the right article found? (`evaluate.py`)

The RAG starter's 37 questions (`test-questions.tsv`: Finnish, Swedish and English questions, each
with the one Finnish article that answers it). A hit = that article among the top 5 / top 10
distinct articles; each article appears once in the list (at most one passage per article).

**Dataset M (19.7k articles, 66.5k passages): what each list adds**

| Search | hit@1 | hit@5 | hit@10 | SQL median |
| --- | --- | --- | --- | --- |
| Starter (whole-article vectors, a hit in any language) | — | 76% | 86% | — |
| Passage vectors only | 43% | 65% | 70% | 4 ms |
| + whole-article vectors | 35% | 73% | 86% | 8 ms |
| + FULLTEXT on every word | 43% | 70% | 84% | 35 ms |
| + FULLTEXT on names and years only | 38% | 76% | 84% | 15 ms |
| **+ en/sv article vectors + title mentions (ours, five lists)** | **51%** | **92%** | **95%** | 18–25 ms |

**Dataset L (all 568k Finnish articles), loaded to ~700k of 1.55M passage vectors**

35 questions: two whose article had no L vectors yet are left out (*Mannerheimin murhayritys
1920*, *Kuorsumaan torpparikapina*).

| Search | hit@1 | hit@5 | hit@10 | MRR | SQL median |
| --- | --- | --- | --- | --- | --- |
| Whole-article vectors (S) | 17% | 63% | 77% | 0.36 | 19 ms |
| Passage vectors only | 14% | 49% | 63% | 0.31 | 727 ms |
| Passage vectors + names FULLTEXT | 14% | 40% | 54% | 0.24 | 727 ms |
| **Ours, five lists** | **49%** | **91%** | **94%** | **0.64** | 212 ms |

Plain vector search falls apart at L's size (near-duplicate paragraphs from other articles crowd
out the right one); the fused lists hold it at the same level as on M. Remaining misses: English
questions that name no article (*"The 1918 war between the Reds and the Whites in Finland"*,
*"Who led the Senate that declared Finland independent in 1917?"*).

## 2. Answers: right facts, faithful citations? (`answers.py`)

25 new English questions (`answer-questions.tsv`), not used for tuning, written from the
passages in the database: 20 facts, 2 then-vs-now, 3 Wikipedia can't answer. Runs the real `/ask`
code path. Checks:

- **fact**: the answer contains the expected fact (regex groups, all must match);
- **citation support**: a judge call per answer, asked whether each sentence's cited passages
  state it (paraphrase and translation allowed);
- **refusal**: on an unanswerable question no sentence carries a citation;
- **routing**: then-vs-now questions go to the time path.

| Check | Result |
| --- | --- |
| Correct facts | **20/21 (95%)** |
| Citations that support their sentence | **82/85 (96%)** |
| Correct refusals | 3/3 |
| Then-vs-now questions routed | 2/2 |
| Answer time | median 3.1 s, max 14.4 s (first question includes model warm-up) |

The one miss (*"How many Reds died in prison camps…"*): the total (11,652) is in the Civil War
article, but search returned per-camp passages; the answer said the passages give only per-camp
figures instead of inventing a total. A retrieval gap, not a hallucination.

## 3. Scale: does the vector index hold up? (`scale.py`)

Per vector table, the same 37 questions: recall@10 of the index against an exact scan, and search
time with and without the index. Index settings everywhere: `M=16`, cosine, `mhnsw_ef_search = 80`.

| Table | Vectors | recall@10 | index search ms (median / p95) | exact scan ms | speed-up |
| --- | --- | --- | --- | --- | --- |
| S whole articles (fi, sv, en) | 29,460 | 99.2% | 17.3 / 127.3 | 55 | 3× |
| M passages, today | 66,543 | 98.6% | 4.1 / 7.0 | 127 | 31× |
| M passages, every version | 353,166 | *running* | | | |
| L passages, all fi articles | ~700,000 | *running* | | | |

Loading L: 1,545,854 passages built in 63 s, embedded on Modal GPUs in ~1 h, then inserted into
the vector index by one writer: ~2,000/s at first, ~50/s past 600k vectors (each insert walks a
bigger graph). Load stopped at ~700k for these measurements.
