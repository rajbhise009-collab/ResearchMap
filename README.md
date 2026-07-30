# ResearchMap

A literature-based discovery (LBD) system. Ingests scientific papers for
one domain, decomposes each into structured knowledge, builds a
relationship layer across papers, and ranks evidence-backed research
opportunities with fully traceable justification.

**Core rule:** LLMs extract, code reasons. Every score and ranking is
deterministic Python — no LLM ever judges "importance." See `CLAUDE.md`
for the full working discipline.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # optional — offline seed run needs nothing set
```

## Run the offline seed pipeline

The seed corpus (`data/seed/`) is committed. The full pipeline and test
suite run with zero API keys and zero network access.

```bash
# End-to-end ingestion over the seed corpus, JSON to stdout
python -m backend.cli ingest --source seed

# Tests
pytest backend/tests -v
```

## API and frontend

Both read cached reasoning output — no API keys, no `DATABASE_URL`.

```bash
# Read-only API — run from the repo ROOT (app.py uses absolute
# backend.-prefixed imports; running from backend/ fails with
# ModuleNotFoundError). OpenAPI docs at /docs.
.venv/bin/uvicorn backend.app.api.app:app --reload

# Frontend (static export, no runtime backend needed)
cd frontend
npm install
npm run snapshot   # regenerate public/data from cached output
npm run dev        # http://localhost:3000
npm run build      # self-contained static site → frontend/out/
```

## Phase status

See `PROGRESS.md`.

## Repository layout

See the "Repository layout" section of `CLAUDE.md`.
