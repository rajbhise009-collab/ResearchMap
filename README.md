# ResearchMap

A literature-based discovery (LBD) system. Ingests scientific papers for
one domain, decomposes each into structured knowledge, builds a
relationship layer across papers, and ranks evidence-backed research
opportunities with fully traceable justification.

**Core rule:** LLMs extract, code reasons. Every score and ranking is
deterministic Python — no LLM ever judges "importance." See `CLAUDE.md`
for the full working discipline.

## Quick start (macOS, no terminal needed)

Two ways to open it, use whichever you prefer:

- **Double-click `ResearchMap.app`** in Finder. Native launcher — no
  Terminal window opens. macOS notifications appear during setup;
  quit from the Dock icon (right-click → Quit) to stop the local
  server cleanly.
- **Double-click `ResearchMap.command`** — same thing but through a
  Terminal window that shows what's happening. Press any key in that
  window to quit.

Both need Node.js (nodejs.org, LTS build) and Python 3 (`xcode-select
--install` installs it). The launchers tell you which is missing if
either isn't there.

**First launch of `ResearchMap.app`**: macOS Gatekeeper blocks unsigned
apps on first open. Right-click the .app → **Open** → **Open** in the
dialog. Once approved, future launches are one double-click.

<details>
<summary>Terminal equivalent</summary>

```bash
./ResearchMap.command
```
</details>

## Publish to the web (free)

The static export is self-contained — no server, no keys, search runs
in the browser. Two zero-cost paths are wired up:

### GitHub Pages

Push to `main`; `.github/workflows/deploy-pages.yml` builds and deploys
automatically. **One-time setup**: in the repository's Settings → Pages,
set **Source** to **GitHub Actions**. The workflow uses no secrets, no
env vars, no billing plan.

The build passes `BASE_PATH=/<repo-name>` so the site works at
`https://<user>.github.io/<repo>/`.

### Vercel

`vercel.json` is set up for a zero-config import. Sign in at vercel.com,
click **Add New** → **Project**, pick this repo, keep defaults, deploy.
Free tier. No env vars needed.

### Any other static host

`npm run build` produces `frontend/out/` — a self-contained folder of
HTML, JS, CSS, and JSON. Upload the folder to any static host (Netlify,
Cloudflare Pages, S3+CloudFront, plain nginx). If the deploy is under a
subpath, build with `BASE_PATH=/subpath npm run build`.

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
