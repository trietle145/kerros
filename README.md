# LakeBandits_junction

Junction hackathon, MariaDB challenge. A web app that answers questions about Finnish history
from Wikipedia, cites the paragraph behind every sentence, and shows how that text changed over
time. Built on MariaDB vector search (RAG) and system-versioned tables (SVT).

Status: Phase 1. Dataset M (full history) and the S article vectors are loaded; loaders in
`scripts/`. Progress is ticked in `tasks/plan.md`.

## Local setup (each person runs their own MariaDB, ~20 min)

Needs Docker, Git and Python 3.11+.

```bash
git clone https://github.com/trietle145/LakeBandits_junction && cd LakeBandits_junction
git checkout planning
cp .env.example .env          # fill in passwords; DB_USER/DB_PASSWORD = MARIADB_USER/MARIADB_PASSWORD;
                              # DB_PORT=3307 if something already uses 3306
docker compose up -d          # MariaDB 12 + schema.sql applied on first start
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # macOS: brew install mariadb-connector-c first

# Datasets into data/ (git-ignored), checksums verified
for set in m s; do
  mkdir -p data/$set && cd data/$set
  curl -s https://api.github.com/repos/MariaDB/mariadb-wikipedia-datasets/releases/tags/$set-2026-10 \
    | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 | xargs -n1 curl -sSLO
  sha256sum -c SHA256SUMS && cd ../..
done

python scripts/load_m.py > data/load_m.log   # ~12 min, all history; then --verify 20
python scripts/load_s.py > data/load_s.log   # <1 min, article vectors; then --verify

python -m app.embed                  # downloads bge-m3 once (~2.3 GB into HF_HOME), self-check
flask --app app.main run --debug     # http://127.0.0.1:5000
```

Files we make (passages, vectors) are shared as Parquet files, not through git; each person loads
them into their own database.

## Read first

- [CLAUDE.md](CLAUDE.md): the whole project on one page (goal, decisions, data, stack, state).
- [tasks/plan.md](tasks/plan.md): the plan: idea, decisions, phases with tasks for persons A and B, feature pool, risks.
- [docs/architecture.md](docs/architecture.md): tables, data flow, the base and what the time features add.
- [docs/research/](docs/research/): Wikipedia problems and edit wars, with sources.

## Challenge resources

- Datasets (S, M, L): https://github.com/MariaDB/mariadb-wikipedia-datasets
- RAG starter: https://github.com/MariaDB/mariadb-vector-wikipedia-rag
- SVT starter: https://github.com/MariaDB/mariadb-system-versioning-wikipedia
- Mentors (MariaDB Foundation, on site): Kaj Arnö, Robert Silén.
