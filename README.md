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

## Phase status

See `PROGRESS.md`.

## Repository layout

See the "Repository layout" section of `CLAUDE.md`.
