# Kerros: Finnish history from Wikipedia, with sources and their history

Junction 2026, MariaDB challenge (team LakeBandits). Ask a question about Finnish history in
English, Finnish or Swedish. Kerros answers from Finnish Wikipedia, and every sentence cites the
exact paragraph and revision it came from. Then it shows how that text got there: when it was
written, how often it was rewritten or reverted, what it said in an earlier year, and what the
English and Swedish Wikipedias say that the Finnish article doesn't.

MariaDB does the hard parts: vector search, keyword search and a temporal filter run in one SQL
statement; real Wikipedia edit times live in system-versioned tables.

## What it does

- **Cited answers.** Hybrid search (five ranked lists: passage vectors, FULLTEXT, Finnish and
  en/sv article vectors, title mentions) fused by RRF in one statement; Claude writes 2–5
  sentences, each citing its paragraph; citations are checked in code.
- **Then vs now.** *"What did Wikipedia say about the red prisoners in 2007, and what has
  changed?"* The date becomes `FOR SYSTEM_TIME AS OF` on paragraph lifetimes; the answer cites the
  version live on that date and today's, with a word diff.
- **History of every source.** Edit timeline with reverts, the article as of any date, source
  health (live since, rewrites, restored), a rewind slider per cited paragraph, "explain this edit".
- **Other Wikipedias.** What English and Swedish Wikipedia say that the Finnish article lacks, and
  whether the Finnish article once said it: in answers and on `/compare/<id>`.
- **Editor tools.** Citation finder, contradiction finder, edit-war radar, language drift
  (*civil war* vs *war of liberation*, year by year).
- **Scale.** The same search over dataset L (all 568k Finnish articles).

## Scores

| | Ours | RAG starter |
| --- | --- | --- |
| Right article in top 5 / top 10 (37 starter questions, dataset M) | **92% / 95%** | 76% / 86% |
| The same on dataset L (all Finnish articles) | **91% / 94%** | — |
| Correct facts in answers (21 new questions) | **95%** | — |
| Citations that support their sentence | **96%** | — |
| Vector index recall@10 (`M=16`, `ef_search=80`) | 98.6–99.2% | — |

Method, per-list comparisons and the scale table: [`eval/README.md`](eval/README.md).

## Data

From [mariadb-wikipedia-datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets):
**S** (19k Finnish history articles plus 10k Swedish and English ones, with article vectors),
**M** (every saved version of 19.7k Finnish articles since 2003: 862,076 versions, raw wikitext),
**L** (all 568k Finnish articles, current text). Wikipedia text is CC BY-SA; every passage shown
links to its exact version.

## Run it

Needs Docker, Python 3.11+, ~16 GB RAM (bge-m3 needs ~5 GB free) and an Anthropic API key.

```bash
git clone https://github.com/trietle145/LakeBandits_junction && cd LakeBandits_junction
cp .env.example .env              # passwords, LLM_API_KEY; DB_PORT=3307 if 3306 is taken
docker compose up -d              # MariaDB 12, schema.sql applied on first start
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # macOS: brew install mariadb-connector-c first

# Datasets into data/ (git-ignored), checksums verified
for set in s m; do
  mkdir -p data/$set && cd data/$set
  curl -s https://api.github.com/repos/MariaDB/mariadb-wikipedia-datasets/releases/tags/$set-2026-10 \
    | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 | xargs -n1 curl -sSLO
  sha256sum -c SHA256SUMS && cd ../..
done
```

Then build the tables in this order. Each script has a `--verify` (or self-check) and its usage
in the docstring; embedding runs on Modal GPUs (`pip install modal && python -m modal setup`).

| Step | Command | Time |
| --- | --- | --- |
| Full history → `article` | `python scripts/load_m.py` | ~12 min |
| S article vectors, en/sv links | `python scripts/load_s.py`, `python scripts/load_langlinks.py` | ~1 min |
| Passages, embedded, loaded | `python scripts/build_passages.py`, `modal run scripts/modal_embed.py`, `python scripts/load_vectors.py` | ~10 min |
| Reverts | `python scripts/build_reverts.py` | 16 s |
| Paragraph lifetimes | `python scripts/build_history.py --all`, embed the new texts, `python scripts/load_vectors.py data/history --history` | ~50 min |
| Cross-language gaps | `python scripts/build_xlang.py passages`, embed, `load`, `label` | ~10 min |

```bash
flask --app app.main run --debug        # http://127.0.0.1:5000 (production: gunicorn -c gunicorn.conf.py app.main:app)
```

## Repository layout

| Path | What |
| --- | --- |
| `app/*.py` | Backend: Flask blueprints for search, answers, time, history, cross-language, insights |
| `app/templates`, `app/static` | Frontend: pages, plain HTML/CSS/JS, no build step |
| `scripts/` | Loaders and builders for the tables, server setup |
| `eval/` | Search, answer and scale evaluations ([results](eval/README.md)) |
| `tools/` | Generators for the frontend's fixtures and the drift data |
| `schema.sql`, `docker-compose.yml` | The database |

Docs: [`docs/architecture.md`](docs/architecture.md) (design, tables, measurements, MariaDB
lessons) and [`docs/frontend.md`](docs/frontend.md) (pages and JSON API). Planning notes and
research live on the `planning` branch.

Built on the MariaDB starters:
[RAG](https://github.com/MariaDB/mariadb-vector-wikipedia-rag) and
[system versioning](https://github.com/MariaDB/mariadb-system-versioning-wikipedia).
