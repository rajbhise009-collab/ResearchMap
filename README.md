# ResearchMap

A literature-based discovery (LBD) system. Ingests scientific papers for
one domain, decomposes each into structured knowledge, builds a
relationship layer across papers, and ranks evidence-backed research
opportunities with fully traceable justification.

**Core rule:** LLMs extract, code reasons. Every score and ranking is
deterministic Python — no LLM ever judges "importance." See `CLAUDE.md`
for the full working discipline.

## Quick start (macOS, no terminal needed)

**Double-click `ResearchMap.command`** in Finder. It installs anything
missing, builds the site, opens your browser, and stays running until you
press any key in the Terminal window. Needs Node.js (nodejs.org) and
Python 3 (installs itself when Xcode tools are present); the launcher
tells you which is missing if either isn't there.

<details>
<summary>Terminal equivalent</summary>

```bash
./ResearchMap.command
```
</details>

## Setup (developers)

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

The frontend is a consumer-facing search tool over one library. Because that
library covers a single subject, the search gate classifies every question as
in-domain, borderline, or out-of-domain, and refuses rather than returning
weak matches dressed up as answers. Search is a term-weight index built at
build time from the library's own vocabulary — no embedding calls, no spend,
no server. `backend/app/api/language.py` is the single source of all
user-facing wording; the frontend carries no copy of its own.

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
