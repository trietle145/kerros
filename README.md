# LakeBandits_junction

Junction hackathon, MariaDB challenge. A web app that answers questions about Finnish history
from Wikipedia, cites the paragraph behind every sentence, and shows how that text changed over
time. Built on MariaDB vector search (RAG) and system-versioned tables (SVT).

Status: planning. Docs and `schema.sql` only; no code yet. Start at Phase 1 in `tasks/plan.md`.

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
