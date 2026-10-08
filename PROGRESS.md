# PROGRESS

## Scheduled expansion — more domains, unattended growth (2026-10-09) ✅

- Money: config/money.json is the only limit (₹1450 ceiling on the ledger; console figure optional);
  enforced at call time in SpendLedger. Ledger ₹1135.54, remaining ₹314.46, ₹26.21/week over 12 weeks.
- Domain selection (docs/findings/domain-selection-2026-10-09.md): 12 candidates; built
  **social media & adolescent mental health** (₹176.99; 100 papers, 32 results, 2 hand-audited
  genuine disagreements); **nudges** prepared and queued (did not fit the run's ₹320 completely);
  ego depletion and growth mindset queued; minimum wage, deep-RL evaluation, microplastics
  not-ready (blind audit < 80% after one fix).
- Growth: every non-frozen library, round-robin budget from the money rule, queued libraries built
  two-phase by the workflow, bookkeeping-only commits on stops, pause/resume (config/growth.json).
- UI scales to any number of libraries (tools/qa/synthetic_libs.py, 8 libraries).
- Still owed: **Phase 6 validation**. Unchanged.
- Details: REPORT_expansion.md.

## Final run — publish-ready, unsupervised-safe, weekly growth (2026-10-08) ✅

- Part 1: ML fairness future-work matching (₹32.22, batch). Ledger ₹958.55 / ₹1200.
- Part 2: set-aside results moved out of the results list on every library and surface
  (LLM-cal 76→66, Diet 12, ML 3→1→55 after Part 1); `frontend/scripts/consistency.mjs`
  gates the build.
- Part 3: curious-user hunt — 13 issues fixed (incl. a search crash on `constructor`);
  `tools/qa/hunt.py` (76 checks, Chromium + WebKit), `test_hardening.py`,
  `tools/qa/smoke.py`.
- Part 4: `weekly-grow.yml` + `daily-health.yml` (replacing weekly-refresh.yml);
  `backend/app/grow/`, `tools/grow/` (runner, issues, health, offline e2e). Fresh-checkout
  data committed (extraction cache, LLM-cal reasoning, embeddings, slim records).
- Part 5: `docs/OPERATIONS.md`, `docs/LAUNCH.md` §9/§11, growth copy on /method and /about
  (counted, not promised).
- Still owed: **Phase 6 validation** (retrospective time-split test). Unchanged by this run.
- Details: REPORT_final.md.

## Launch readiness (2026-10-05) ✅

No paid calls (ledger byte-identical). **631 tests green.** Validation
(Phase 6) is still owed. Details: `REPORT_launch.md`.

- Shared links open in the owning library (build-time owner map); storage
  failures never break the site; on-brand 404.
- One site URL (`NEXT_PUBLIC_SITE_URL`) and one site name
  (`frontend/site.config.json`); per-page metadata, share images, sitemap,
  robots (noindex outside production), manifest, icons.
- Trust pages (/about, /method, /privacy, /terms, /contact);
  `npm run launch-check`; copy that does not exceed the data.
- QA (tools/qa): shared links, console, failure modes, Chromium+WebKit
  search, axe WCAG 2.1 AA, keyboard, crawl, Lighthouse; fixes for contrast,
  focus, CLS, page weight and double-prefixed DOI links.
- Repo audit: public, no secrets; the old answer key is still served by SHA
  on GitHub (owner decision needed).

## Iteration 6 — owner decisions applied (2026-10-04) ✅

No paid calls (ledger unchanged at the frozen cap). **626 tests green.**
Validation (Phase 6) is still owed. Details: `REPORT_iteration6.md`.

- ml-fairness: AI Fairness 360 preprint merged into the 2019 journal
  version (merge-policy survivor rule, `merged_from` kept, extraction
  unioned); 100 -> 99 papers, 95 -> 91 shortlisted pairs, 4 self-supports
  dropped; 0 flagged before and after.
- Dedup pass 5 (title similarity + numeric and abstract guards) in
  `normalizer.py`; `docs/merge-policy.md` extended;
  `docs/findings/duplicate-check-v2.md`; no further merges.
- LLM-cal: `44981e91c40dfe6d` documented as a frozen label; content
  fingerprint in `data/llm_cal_fingerprint.json`, checked by tests.
- Audit doubts shipped (library page + multi-domain.md); second diet
  expert packet `docs/review/diet-contradictions-v2/` (v1 untouched; key
  outside the repo).

## Iteration 5 — honesty + ledger integrity fixes (2026-10-04) ✅

No paid calls (ledger cap frozen at the corrected cumulative). **605 tests
green.** Validation (Phase 6) is still owed. Details: `REPORT_iteration5.md`.

- Public findings no longer state an untested explanation as fact
  (multi-domain §2 rewritten; RESEARCHMAP-FINDINGS §5; footer notes);
  `test_public_claims.py` guards it.
- Every doc number generated from data: `backend/app/corpus/doc_numbers.py`
  (`--check` fails on stale blocks).
- Ledger: 190 mock-test entries proven and removed by one appended
  correction (`ledger_audit.py`, `docs/findings/ledger-unknown-entries.md`);
  tests can no longer touch the real ledger (session guard).
- Spend gate coded: x2 classification / x1.5 extraction preflight with the
  projection recorded, 1.5x per-call overrun halt; embeddings ledgered.
- Duplicate check (`duplicate_check.py`, `docs/findings/duplicate-check.md`):
  one preprint/published pair in ml-fairness; the 4-pass dedup never ran
  on the new libraries.

## Public-deploy prep — MIT license, dev-mode gate, attribution, keyless CI (2026-09-27) ✅

Shipping-prep pass to publish ResearchMap as a public product. No paid API
calls; corpus frozen at 113 papers; spend unchanged at $7.40. **349 tests
green** (was 348; +1 attribution).

### Architectural + content audit

- **Nothing in the public build can cost money.** `frontend/out/` is pure
  static HTML/JS/CSS + JSON. No API routes ship. The two runtime `fetch`
  calls are `search-index.json` (static file, free) and `/api/preflight`
  (free-tier OpenAlex when a backend exists — 404s with a graceful
  fallback on static hosts). No paid-API strings (`gemini`, `anthropic`,
  `openai`, `API_KEY`) anywhere in `out/`.
- **No full-text leakage.** Scanned all 197 files under
  `frontend/public/data/`. Max text lengths — abstract 3306 (OpenAlex,
  not full text), claim 256, limitation 258, future_work 237, methodology
  272. No `body`/`fulltext`/`ocr_text`/`pdf_text` fields survive from
  Unpaywall/Europe PMC/arXiv PDFs.

### Dev mode env-gated

`ENABLE_DEV` build-time env → exposed to client as
`NEXT_PUBLIC_ENABLE_DEV`. In `DevMode.tsx`, both the URL seed effect and
the `setDev` callback early-return unless it is `"1"`. Wired into
`scripts/rm-lib.sh` (line 178) so `.command`/`.app` builds get dev on.
`vercel.json` and `deploy-pages.yml` don't set it — `?dev=1` is inert on
public deploys, banner never renders, all `<Dev*>` blocks stay hidden.
Reverses the 2026-08-01 "no gating" recommendation for public deploys
specifically; local dev is unchanged.

### Attribution + framing on every page

`backend/app/api/language.py` now owns an `ATTRIBUTION` block credited to
OpenAlex (CC0), Semantic Scholar, Unpaywall, Europe PMC, arXiv. The
layout footer renders it on every page — landing, `/gap/[slug]`,
`/paper/[wid]`, `/library`, `/papers`, `/gaps`, `/findings/[slug]`,
`/404`. Same for the new `FOOTER_SCOPE`: `"Working prototype · one
library · 113 papers on language-model reliability. Not a comprehensive
research tool."` — so a public visitor landing on a shared gap or paper
link sees the frame, not just the landing eyebrow.

`PLUMBING_TERMS` narrowed `"openalex"` → `"openalex:"` (the ID prefix)
so the bare source-name is a legitimate word in the footer.
`test_attribution_block_names_the_five_required_sources` locks the list.

### LICENSE

MIT at `/LICENSE`. Chose MIT over Apache-2.0: research prototype, no
patentable algorithm, MIT's brevity wins for academic uptake. Includes a
DATA-SOURCE ATTRIBUTION section clarifying upstream data terms (CC0,
etc.) are separate — code is MIT-licensed, the data is not relicensed.

### Deploy configs — snapshot is committed, keyless CI

**Blocker found and fixed.** The old `vercel.json` and `deploy-pages.yml`
ran `python -m backend.app.api.export` at build time — that would have
failed in fresh-clone CI because `data/reasoning/`,
`data/relationships/`, `data/cache/`, and
`data/live_samples/expanded_corpus_manifest.json` are all gitignored.
The 2026-08-01 "Verified end-to-end from a fresh state" claim was made
with those files locally present.

Fix: unignored `frontend/public/data/` and committed the 2.1 MB / 197-
file snapshot to the repo. Dropped Python entirely from both CI paths.
Both configs now just `npm ci && npm run build`. Regenerating the
snapshot stays a local dev step (`npm run snapshot`) when the manifest
changes. Trade: repo grew by 2.1 MB and the snapshot can drift from
source if snapshot isn't re-run — but the alternative (commit 15 MB of
intermediate data) is worse.

Verified: root build (Vercel-shaped) and subpath build
(`BASE_PATH=/ResearchMap`, GH-Pages-shaped) both produce a working
static export with attribution + framing on every page and dev-mode
gated off.

### Outstanding

- Live verification on the deployed public URL (task 8) — blocked on
  Raj connecting the Vercel/GH-Pages side.
- Phase 6 (validation) still outstanding, unchanged.

## Coherence predictor + reusable scaling tool + preflight wiring (2026-08-09) ✅

Two new capabilities, both designed to spend less and know more before
spending. No paid API calls; corpus frozen at 113 papers; spend unchanged
at $7.40. 348 tests green (was 320; +14 coherence, +6 scaling, +8
preflight).

### Part A — metadata-only domain-coherence pre-flight

`backend/app/coherence/` — features + verdict + fetch CLI + 9-domain
sample cached under `data/coherence/`. Uses free OpenAlex `filter=`
list calls (90 credits total of a 100,000/day quota; $0). Features:
intracorpus reference rate, citation reciprocity, greedy-Louvain
modularity, review ratio, temporal churn (JS divergence over cited-
work distributions), venue HHI, Jaccard title-term spread.

Composite scores (`contested_score`, `method_transfer_score`) are
unweighted hypothesis-driven means — no data-fit weights because n=1
is not enough to fit anything without overfitting.

The finding at `docs/findings/domain-coherence-predictor.md` reports
honestly: discriminates 7 of 9 domains by reputation, gets **the one
measured domain (llm-calibration) wrong** (predicts contested, we
measured zero contradictions). Documents the v0.1→v0.2 reversal where
initial "reviews signal consolidation" got flipped by data. Includes
what full validation would cost (~$12-16 for two-domain contrast,
~$18-24 for three).

### Part B — reusable scaling tool

`backend/app/reasoning/scaling_tool.py` + `run_scaling_tool.py`. Takes
any ReasoningCorpus + ScorerSpec list, returns per-N per-scorer curves
with log-log slope + fit-confidence band + machine-readable caveats
per curve.

**The single most important thing this fixes**: the fixed-k lesson
from the hand-run study. Every scorer that can bound yield by
construction declares a `bounded_yield` ceiling; the tool either
flags the curve `parameter_bound:_caps_yield_at_N` (if unmasked and
no `scale_with_n`) or notes the parameter was scaled with N — either
way the caveat rides IN the report, not just in a companion doc.

All-zero curves get `all_zeros:bound_only` — the true rate is bounded
at ~1/candidates, never proven absent. Log-log fits with too few
non-zero points get `fit_confidence: low` or `unmeasurable`; the
report never silently extrapolates from an unmeasurable curve.

Reproduces the hand-run scaling study (`docs/findings/corpus-scaling-
study.md`) exactly on candidate/orphan/persistent/structural curves.
One INVESTIGATED divergence: log-log regression over all 5 points
gives candidate slope 1.77; doc's endpoint-only fit gives 1.89.
Regression is the more principled number; documented in the test
message. Cost projection at N=800: tool $36 vs doc $40, 10% lower
because of the honest slope.

Also fixed a projection bug found during test: my first draft used
`pairs = N^slope` with implicit intercept 1 — that gave $293 at N=800
vs the doc's $40. Anchoring the projection at the measured reference
point fixes it and matches the doc within 10%.

### Part C — wired into "Build a library for this"

`/api/preflight?q=…` — runs Part A live on the user's OOD subject
using OpenAlex free (~10 credits per uncached query; on-disk cache
under `data/coherence/queries/`). Returns a plain-language
consumer summary (three lines: coverage, diagnostic, cost/time) and
full internals under `dev`.

Frontend `OutOfDomain` component fetches the endpoint when the user
opens the panel and renders `PreflightBlock`. Dev-mode surface shows
raw features, verdict scores, cost projection, and the top OpenAlex
titles for the query — same policy as everywhere else: transparency,
not concealment.

Degrades gracefully on the static export: if the fetch fails (no
backend behind the static hosting), the panel shows a "live pre-
flight isn't available on this deployment" note and falls back to
the static translation-layer copy. The button STILL isn't wired to
build anything — that stays a human transaction per the not_yet copy.

### Honesty invariants (pinned by test)

- Diagnostic language ALWAYS includes "hypothesis" / "haven't
  validated" / "not a guarantee" (`test_diagnostic_never_promises_it
  _is_validated`).
- Dev verdict ALWAYS carries the n=1 caveat
  (`test_dev_verdict_carries_the_n1_caveat`).
- Consumer copy ALWAYS omits "click here to build", "starting the
  build" (`test_consumer_never_says_the_button_works`).
- Bounded-yield parameters ALWAYS surface as machine-readable caveats
  in the scaling report (`test_bounded_scorer_without_scaling_gets
  _flagged`).

### How to run

```bash
# .app: preflight fetches live on first click, cached thereafter.
# .command: same, terminal-native.
# Bare tools:
python -m backend.app.coherence.fetch --all          # 8-domain feature table
python -m backend.app.reasoning.run_scaling_tool     # reproduce scaling study
curl 'http://127.0.0.1:PORT/api/preflight?q=protein+structure'  # live preflight

# Tests
cd backend && ../.venv/bin/python -m pytest -q
```

---

## Outstanding — Phase 6 (validation)

**Validation has not been built.** The commits labelled "Phase 6" in the
git log (`cceac22` "Phase 6: read-only FastAPI + static snapshot export")
actually shipped Phase 7 (API) per the plan in `CLAUDE.md`. Phase 6 —
the retrospective time-split test that is the project's publishable
claim — was skipped in that push and remains the next real piece of
work. Nothing shipped since should be described as "complete" without
this caveat. See CLAUDE.md § Phase index for the full reconciliation.

## The .app becomes a genuine app (2026-08-02) ✅

Double-clicking `ResearchMap.app` no longer just opens a browser tab. It
now opens a chromeless native-feeling window (Chrome `--app=URL` mode)
against a real full-stack server: FastAPI serving both the frontend and
the live `/api/*` endpoints from a single URL that also works from any
other browser tab.

Corpus frozen at 113 papers; no paid API calls; spend unchanged at $7.40.
320 tests green.

### One server, two surfaces

`backend/app/api/app.py` now mounts `frontend/out/` at `/` behind all its
`/api/*` routes. `_FrontendStatic` (a small `StaticFiles` subclass) does
two things the default doesn't:

- Falls back to `out/404.html` (with a real 404 status) for unknown
  paths, so readers see the on-brand not-found page instead of an
  `{"detail":"Not Found"}` blob.
- Serves a 308 redirect from `/gap/xyz` to `/gap/xyz/` — Next's static
  export ships each route as `<slug>/index.html`, and a shared link
  missing its trailing slash would otherwise 404.

The mount only activates when `out/` exists, so the API-only deploy
(`uvicorn` without a build) still works.

### Launcher: uvicorn with a graceful fallback

`scripts/rm-lib.sh` now:

- Bootstraps a minimal Python venv on first run (`fastapi`, `uvicorn`,
  `pydantic`, `numpy` — ~30 MB total) if `.venv/bin/uvicorn` isn't
  present. Developers who already installed the full requirements.txt
  are left alone.
- Prefers **uvicorn** for the full-stack experience (frontend + live
  `/api/*` from one origin).
- Falls back to `python3 -m http.server` (with the on-brand 404 handler)
  when the Python backend can't be installed — offline first launch, no
  internet at conference wifi, whatever. The URL still shows the site;
  only `/api/*` is unavailable, and the "Serving …" line tells the user
  which mode is running.
- Fixed a subtle process-leak bug in the background-launch path: without
  `exec` inside the subshell, `$!` was the wrapper subshell's PID (which
  exits immediately), so uvicorn survived as an orphan with PPID=1 after
  a "clean" shutdown. `( cd "$REPO" && exec "$uv" ... ) &` fixes it.

### `rm_open window` — the "genuine app" feel

New `rm_open` function in the shared library takes a mode:

- `window` — Chrome's `--app=URL` mode: chromeless standalone window,
  favicon in the title bar, its own Dock icon, no browser tabs or
  address bar. A dedicated Chrome user-data-dir keeps this profile
  isolated from the user's regular Chrome (no logged-in accounts, no
  extensions). Falls back to `open URL` when Chrome isn't installed.
- `browser` — default browser tab; the launcher's classic behaviour.

`ResearchMap.app` uses `window`. `ResearchMap.command` uses `browser`
(Terminal users typically want browser tabs so they can use dev tools,
extensions, and multiple tabs).

`rm_shutdown` was updated to kill the Chrome app window first (so its
"connection refused" alert doesn't flash while the server is being torn
down), then the server.

### Verified

`.app` launch from a truly fresh state:
- Native window opened in ~2s
- Uvicorn serving both frontend and API from one URL
- Every endpoint checked from an independent HTTP client (as if
  browsing the URL from another app): landing 200, /api/language 200,
  /api/search 200, gap detail 200, unknown path 404
- SIGTERM (Dock → Quit) shuts down uvicorn AND the Chrome app window —
  zero leaked processes

`.command` launch: same full-stack behaviour, opens default browser.

### How to run

Same as before, but now full-stack:

```bash
# Native app window (Chrome app mode; fallback to default browser)
double-click ResearchMap.app     # in Finder

# Terminal + default browser
./ResearchMap.command

# Bare API only (no frontend, no launcher)
.venv/bin/uvicorn backend.app.api.app:app --reload

# Tests
cd backend && ../.venv/bin/python -m pytest -q
```

---

## Two delivery paths: native .app + public web (2026-08-01) ✅

Same build, two ways to open it. Corpus frozen at 113 papers; no paid API
calls; spend unchanged at $7.40. 320 tests green.

### Path A — `ResearchMap.app` (macOS bundle)

Double-clickable in Finder, runs silently — no Terminal window opens.
Uses native macOS notifications for setup progress and modal dialogs for
errors. Dock icon stays for the app's lifetime; right-click → Quit
(SIGTERM) shuts down cleanly.

- **Bundle**: standard `Contents/{Info.plist, MacOS/ResearchMap,
  Resources/AppIcon.icns}`.
- **Icon**: typographic mark in the site's design language — warm paper
  squircle, deep-teal serif "R", subtle bookmark accent. SVG source at
  `resources/icon/icon.svg`; rasterised at every required size (16, 32,
  128, 256, 512 at 1x and 2x) and bundled by `iconutil` into a proper
  `.icns`. Reads cleanly at 32×32 in the Dock.
- **Shared logic**: `scripts/rm-lib.sh` holds every side-effecting op
  (prereq check, install, snapshot, build, port pick, server lifecycle).
  Both `.command` and `.app` source it and supply their own UI shims
  (`ui_step`, `ui_ok`, `ui_note`, `ui_fail`) — the terminal launcher
  writes ANSI to stdout; the app writes to `~/Library/Logs/ResearchMap/`
  and surfaces user-facing messages via `osascript`.
- **Bundle guardrail**: the exec checks it sits inside its repo (looking
  for `backend/` and `scripts/rm-lib.sh` adjacent). If someone drags the
  .app out of the folder, they get a dialog explaining why.
- **Gatekeeper**: bundle is unsigned; first launch needs right-click →
  Open. Documented in the README.
- **Verified**: end-to-end from a stashed clone-shape state (no
  `node_modules`, no `frontend/out`, no `.next`, no `public/data`) —
  installed deps, snapshotted, built, served, opened browser, quit on
  SIGTERM with zero leaked processes.

### Path B — public web (GitHub Pages + Vercel)

Static export deploys as-is. No server, no runtime keys, no billing.

- **`basePath` support** in `next.config.mjs` via `BASE_PATH` env var.
  `basePath` + `assetPrefix` set together so Next rewrites every URL —
  routes, static assets — through the prefix. `frontend/lib/basePath.ts`
  exposes the same value at runtime for `/public/` fetches (which Next
  does *not* auto-prefix); every runtime fetch now goes through
  `asset(...)`.
- **Favicon** meta wired to `<link rel="icon">` in the layout head with
  the basePath applied — Next's `metadata.icons` doesn't respect
  `basePath` and would 404 on subpath deploys.
- **`.github/workflows/deploy-pages.yml`** — on push to `main`: setup
  node+python, `npm ci`, run the export, build with
  `BASE_PATH=/<repo>`, upload artifact, deploy to Pages. Concurrency
  guard cancels older runs. No secrets, no env vars, no billing plan.
- **`vercel.json`** — zero-config import. Vercel deploys at the domain
  root (no basePath). Free tier.
- **Verified**: both variants build cleanly; every asset URL correctly
  prefixed. Full JS-driven headless-Chrome test with the site staged
  under `/ResearchMap/` — landing, gap detail, paper detail, library,
  favicon, search-index fetch, and OOD refusal all work.

### Dev-mode policy: keep it fully accessible on public deploys

**Recommendation** (implemented): `?dev=1` continues to expose trust
scores, component scores, cosine similarities, manifest hash, spend,
provenance, and raw JSON on public deploys — no gating.

Reasoning: transparency isn't a feature of ResearchMap, it IS
ResearchMap. The "LLMs extract, code reasons" premise requires
inspectability. `?dev=1` is opt-in, comes with a clear "Developer mode is
on" banner, and anyone who types the URL parameter is technical enough
to interpret raw numbers. Splitting into public/dev build modes
fragments the codebase for no offsetting benefit.

**Flag**: the `SPEND_TO_DATE_USD = 7.4` figure is the maintainer's
cumulative history, not methodological transparency. If someone forks
and deploys, that number becomes misleading until they edit the constant
(clearly named in `backend/app/api/data.py`). Not gating it via env var
by default — but say the word and I'll add one.

### Framing for public visitors

- Landing eyebrow now reads **"Working prototype · One library"** so a
  first-time visitor immediately understands scope.
- "Build a library for this" panel copy rewritten to unambiguously read
  as a preview, not a broken button: "This panel is a preview, not a
  working button." The panel still shows honest cost estimates ($8–15,
  3–5 hours) so visitors know what would be involved.

### What Raj needs to do to publish

1. Push this branch to a GitHub remote.
2. Repository Settings → Pages → **Source: GitHub Actions**.
3. That's it. The workflow runs on push to `main` and deploys to
   `https://<your-username>.github.io/<repo>/`.

For Vercel: sign in at vercel.com, Add New → Project, pick the repo,
deploy. Nothing else to configure.

### How to run

```bash
# macOS native  →  double-click ResearchMap.app in Finder
# Terminal      →  ./ResearchMap.command
# API           →  .venv/bin/uvicorn backend.app.api.app:app --reload
# Tests         →  cd backend && ../.venv/bin/python -m pytest -q
```

---

## Hardened for first-time users (2026-08-01) ✅

Four related pieces of work: a regression test for the search gate's
worst-documented failure mode, a double-click launcher for macOS, a full
premium UI pass, and repo-path portability. Corpus frozen at 113 papers;
no paid API calls; spend unchanged at $7.40. 320 tests green (was 311,
+9 collision tests).

### Search gate: same-word-different-field collisions

The gate refused 4 of 5 obvious collisions on the unknown-word penalty
alone, but "calibration of medical imaging equipment" slipped through as
`borderline` — `calibration`, `medical`, and `imag` are all understood
(library holds LLM-medical and vision-language papers), leaving only
`equipment` unknown, which barely tipped coverage below the rescue
threshold. Rescue then fired on a single strong hit against an EHR paper.

The signal that separates same-word-different-field from real membership
is **breadth** — a real domain-adjacent question hits many documents (a
body of work); a collision picks up one high-scoring document that
stacked hits on the frequent term and nothing else. Medical-imaging
matched 20% of docs; legal-contract-review-with-AI (correctly borderline)
matched 33%. Rescue now requires `breadth >= 0.24` alongside the existing
coverage and best thresholds. Applied identically in the TypeScript twin;
the parity test still holds.

Regression harness in `test_search.py::TERMINOLOGY_COLLISIONS` locks in
all eight collision variants plus an explicit "breadth is the signal"
test.

### `ResearchMap.command` — Finder double-click launcher

For anyone who doesn't open a Terminal:

- Detects Python 3 and Node.js; loads nvm and Homebrew paths so a
  non-interactive shell sees them.
- Installs frontend deps on first run (`npm install`), snapshots data,
  builds the static site, picks a free port, starts a local server,
  opens the browser.
- Custom static handler serves `out/404.html` for unknown paths so the
  reader never sees Python's stock "Error response" body.
- Every failure path prints plain English with a log path — never a
  Python traceback or an npm error dump surfaced raw. Terminal is held
  open with "press return to close" so the message isn't lost.
- Clean shutdown on any key, on Ctrl-C, or on Terminal being closed
  (SIGINT/SIGTERM/HUP/EXIT all route to the same idempotent shutdown).
- Verified end-to-end from a truly fresh state (no node_modules, no
  prior build, empty public/data) — zero leaked processes afterwards.

### Premium UI pass

Rebuilt the CSS as a considered design system rather than a pile of
ad-hoc rules:

- **Type**: modular scale (1.200) on tuned optical sizes; Charter and
  Iowan Old Style ship locally on macOS/iOS, so no network fonts and no
  CLS; tabular figures where numbers align.
- **Palette**: warm off-white light and matched-not-inverted warm-neutral
  dark; layered surfaces (paper → raise-1 → raise-2); one accent (deep
  teal in light, muted teal in dark) that carries every interactive
  affordance; explicit `data-theme=light|dark` overrides via `?theme=`
  URL param so headless-Chrome iteration can verify both palettes.
- **Motion**: tokenised durations and cubic-bezier easing; every
  transition respects `prefers-reduced-motion`.

New behaviours:

- **⌘K palette** (also Ctrl-K, "/", and `#palette` in the URL). Search-
  as-you-type, keyboard-nav, honest inline OOD refusal so a query the
  library can't cover doesn't quietly show weak matches.
- **Search-as-you-type on the landing form** with a 140ms debounce and a
  skeleton state during the first index load.
- **Sticky "On this page" sidebar** on gap + paper detail pages, using
  IntersectionObserver to highlight the current section — no scrollspy
  library, no runtime cost.
- **Real 404** (`app/not-found.tsx`) on-brand and honest ("That page
  isn't here"); launcher serves it for unknown paths.
- **Two-column hero** on the landing so the desktop layout is balanced;
  stacks below the query on mobile.
- **Accessibility**: skip-to-content link on every page, semantic
  landmarks, keyboard focus rings on every focusable element,
  `overflow-x: hidden` as the defensive floor. Verified in built HTML.

Honesty invariants (verified in the rendered static export):

- Zero `<progress>`, `role="progressbar"`, or `aria-valuenow` anywhere.
- No confidence percentages, gauges, coloured ticks — strength stays a
  word with a sentence describing what it means.
- Caveats stay first-class and inline, in a full-size cream panel, never
  in a footnote or tooltip.
- OOD refusal behaviour unchanged — still routes to the honest empty
  panel; fixed a double-period bug the redesign surfaced there.
- Dev toggle removed from the footer; only entry point is now `?dev=1`,
  and once on the toggle shows inside the developer banner as a
  "turn off" button. Zero visible entry point in the consumer UI.
- Zero-contradictions empty state still self-explaining.

### Repo-path portability

Twenty-eight Python scripts under `backend/app/{api,corpus,reasoning,
relationships,extraction}/` hardcoded the repo's absolute path in a
`REPO_ROOT` constant. Fixed all to `Path(__file__).resolve().parents[3]`.
Anyone can now `git clone` and move the repo without editing anything.

### First-run verification

Launched with `node_modules/`, `frontend/out/`, `frontend/.next/`, and
`frontend/public/data/` all stashed. The launcher installed deps, ran
the export, built 199 pages, picked a free port, served, opened,
shut down cleanly. No leaked processes. Full API suite runs with
`env -i` (no `DATABASE_URL`, no API keys).

### How to run

```bash
# Double-click ResearchMap.command in Finder — no terminal knowledge required.
# Terminal equivalent (both work):
./ResearchMap.command

# API (from repo root, no env vars needed)
.venv/bin/uvicorn backend.app.api.app:app --reload   # docs at /docs

# Tests
cd backend && ../.venv/bin/python -m pytest -q
```

---

## Consumer rebuild — plain language, honest search (2026-07-31) ✅

Rebuilt the frontend as a consumer product. Corpus frozen at 113 papers;
**no paid API calls** — spend unchanged at $7.40.

### The core constraint: a query box that can't promise "ask anything"

The backend holds one subject. A search box implies otherwise, so the gate
that decides *in-domain / borderline / out-of-domain* is the load-bearing
piece of the whole rebuild.

**No paid call was needed.** The corpus embeddings came from a paid model,
so embedding a fresh query into that space would cost money per search and
need a live server — which the static export doesn't have. Instead
`backend/app/api/search_index.py` builds a term-weight index over the
library's own vocabulary at build time and ships it as JSON; the browser
matches against it. Free, serverless, and it is *what makes the honest
refusal possible* — an index that knows the library's whole vocabulary can
tell "I have nothing on this" apart from "I have something weak".

The gate took several passes to get right. Notes for whoever touches it:

- **Rarity is the wrong signal.** The first version scored domain fit by
  IDF and rated "treatment options for early stage melanoma" as in-domain:
  every word except *melanoma* appears somewhere in any large text, and
  rare words scored *highest*. Domain-defining terms are the **frequent**
  ones here (hallucination 119 docs, uncertainty 56, calibration 44).
- **An absent word outweighs several bland present ones** (`UNKNOWN_WEIGHT
  = 3.5`). Nobody types "melanoma" by accident, so an unseen word is
  almost always the subject of the question.
- **Breadth separates covered from incidental.** "Image recognition
  accuracy" is understood word-for-word and matches a few papers, but the
  library has no body of work on it — true in-domain questions match
  42–71 of 189 documents, generic-ML ones 8–26. Hence `BREADTH_IN_DOMAIN`.
- **Everyday phrasing must reach the technical term.** Nobody types
  "hallucination"; they type "makes things up". `DOMAIN_SYNONYMS` maps
  them. Expansion helps *ranking* but is deliberately excluded from the
  coverage figure, so it can never talk an out-of-domain query into
  looking understood.
- "AI" survives tokenising despite being two letters, and "know"/"trust"
  are not stopwords — *"does the model know when it doesn't know"* is this
  library's central question.

Result: 28/28 on the hand-labelled query set across all three verdicts.

### Plain language: one module, not scattered strings

`backend/app/api/language.py` is the single source for every consumer
word, exported to `language.json`; the frontend renders it and carries no
copy of its own. Headlines are built from the papers' own text (an
unfollowed question is shown as the researcher wrote it), never from
internal titles like "Orphaned future-work direction from W2514278201".

The jargon ban is split, which matters: `PLUMBING_TERMS` (scorer,
`component_score`, cosine…) can never appear anywhere, including inside
quotes; `AUTHORED_BANNED` (corpus, epistemic, "structural hole") is banned
in copy we write but allowed inside sentences quoted verbatim from papers —
"corpus fidelity" and "epistemic uncertainty" are the field's own words and
rewriting a researcher's sentence would put words in their mouth. Developer
copy is exempt by design.

### Honesty that survived the rewrite

- Strength is three words with a sentence each — Strong / Worth a look /
  Unverified lead. No bars, no percentages, no ticks anywhere in the CSS.
- An unconfirmed method-transfer lead can never read as "Strong",
  whatever its raw numbers say.
- Fixed a real inversion found by reading the rendered page: a lead that
  *had* been checked still carried "a promising match we haven't verified".
  The confirmation note now replaces that caveat — and says the check was
  done by a language model, not a specialist.
- Findings reports are raw working notes and read like it, so each is
  topped with a note saying exactly that rather than being paraphrased
  into something it isn't.

### Developer mode

Toggle in the footer. State is React context mirrored to `?dev=1` —
no localStorage, no sessionStorage, no cookies. Reveals raw scores,
component scores, scorer + parameters, query analysis (coverage, breadth,
matched terms), pipeline provenance, corpus composition, spend, and the
underlying JSON for the current view.

### Tests (311 total, all green)

- `test_language.py` — jargon and numeric-internal leaks, weak results
  always carrying a caveat, the 113-paper caveat naming its real limit.
- `test_search.py` — the in-domain, borderline and out-of-domain sets,
  including the incidental-vocabulary-overlap case the gate exists for.
- `test_search_parity.py` — **compiles `frontend/lib/search.ts` and runs
  it against the Python**, asserting identical tokens, verdicts, coverage,
  breadth and ranking. Comments promising two implementations agree are
  worth nothing on their own.
- `test_rendered_output.py` — audits the built HTML with markup stripped,
  catching template-level leaks the source tests cannot see.

### Routes

`/` query · `/gaps` browse · `/gap/[slug]` full story · `/papers`,
`/paper/[wid]` · `/library` composition + findings · `/findings/[slug]`.
200 static pages, 98 kB first load (the index is fetched lazily).

---

## Phases 5–7 — ranking, API, frontend (2026-07-30) ✅

Built to completion in one pass over the frozen 113-paper corpus. **No paid
API calls** — everything reads cached reasoning/relationship/manifest files.

### Phase 5 — ranking + evidence assembly (`backend/app/ranking/`)

- **`schema.py`** — versioned evidence-card schema, `SCHEMA_VERSION = "1.0.0"`.
  `ConfidenceTier` (high ≥ 0.60, medium ≥ 0.35, else low) via `tier_for()`.
  `gap_type`, `confidence`, `confidence_tier`, `trust`, and `confirm_status`
  are first-class fields on `EvidenceCard` — not buried in `component_scores`.
  Every card carries `caveats`, `supporting_papers`, a resolvable
  `evidence_trail`, and `relationship_ids`. Models are `extra="forbid"`.
- **`assemble.py`** — `build_evidence_cards()` runs all reasoning scorers,
  ranks by **trust = score × confidence** (descending), assigns rank, resolves
  each trail id back to its concrete claim / limitation / future-work / method
  / relationship / paper record, and attaches every applicable caveat:
  `corpus_relative` (orphaned future work), `mixed_fidelity` (abstract-only
  supporters), `generic_category`, `construct_gated`, `semantic_lead`
  (structural holes). Structural-hole `confirm_status` (substantive / trivial /
  not_addressing) read from the cached confirmations file.
- **Tests** — `backend/tests/ranking/test_evidence_cards.py`: tier thresholds,
  cards resolve to real paper IDs, **no orphan references**, trust-ordering,
  card shape, abstract-only → mixed_fidelity. All green.

Result over the corpus: **76 opportunities** — 1 persistent-limitation
(high tier), 0 contradictions, 63 orphaned-future-work (medium), 12
structural-hole leads (low, 2 substantive).

### Phase 6 — read-only FastAPI (`backend/app/api/`)

- **`data.py`** — file-backed data layer, `lru_cache` singletons, **runs with
  no `DATABASE_URL`** (reads the same files the scorers read). Card/paper
  lookups, corpus stats (ft/abstract split, core/peripheral, per-scorer yields,
  spend-to-date, manifest hash), findings loader.
- **`app.py`** — endpoints: `GET /api/opportunities` (filter
  `gap_type`/`min_confidence`/`tier`/`scorer`, paginated), `/api/opportunities/{id}`,
  `/api/papers` (filter `domain_centrality`/`input_source`), `/api/papers/{id}`,
  `/api/relationships`, `/api/corpus/stats`, `/api/findings` (+`/{slug}`).
  Auto OpenAPI at `/docs`. CORS for `localhost:3000`.
- **`export.py`** — static snapshot generator → `frontend/public/data/`
  (meta, opportunities + per-opportunity, papers + per-paper, relationships,
  stats, findings). Powers the static-export site with zero runtime backend.
- **Tests** — `backend/tests/api/test_api.py`: runs-without-DATABASE_URL,
  pagination, filters, 404s, honest-presentation invariants (every card has
  gap_type + tier + evidence_trail; orphans carry corpus_relative; holes carry
  confirm_status + semantic_lead), papers/relationships/stats/findings, OpenAPI.
  All green.

### Phase 7 — Next.js + TypeScript frontend (`frontend/`)

Static export (`output: "export"`); server components read the JSON snapshot
from `public/data` at build time — no runtime fetch, works over `file://`.

- **Views** — Overview (composition, per-scorer plain-language notes, honest
  empty-state for 0 contradictions linking findings, spend + manifest hash);
  Opportunities (trust-ranked list, filter by gap_type/tier); Opportunity detail
  (explanation, component scores, full evidence trail linking to source papers,
  all caveats); Papers (filter centrality/source, abstract-only flagged); Paper
  detail (claims/limitations/future-work/methodologies, in-corpus citation links,
  abstract-only fidelity caveat); Findings (markdown reports via react-markdown).
- **Honest presentation** — confidence tier + caveats are visually first-class;
  weak cards (low tier / unconfirmed holes) are de-emphasised (`.card.weak`);
  corpus-relative orphans state "unaddressed WITHIN this 113-paper corpus, not
  the field" inline; abstract-only papers carry the "~11× fewer own-work
  limitations" note everywhere; no progress bars / green ticks / "high
  confidence" badges. Every opportunity's evidence trail is one click away.

**Build**: `npm run typecheck` clean; `npm run build` prerenders **200 static
pages** to `frontend/out/` (self-contained, no hosting cost). Full backend suite
green.

### How to run

```bash
# Backend API (no env vars needed) — run from the repo root; app.py uses
# absolute backend.-prefixed imports, so it must NOT be run from backend/.
.venv/bin/uvicorn backend.app.api.app:app --reload   # docs at /docs

# Frontend — regenerate snapshot, then dev or static build
cd frontend
npm run snapshot     # python export → public/data
npm run dev          # http://localhost:3000
npm run build        # static site → frontend/out/  (open out/index.html)
```

---

## Phase 0 — foundation ✅

Built:

- **Repo scaffolding**: `requirements.txt`, `.env.example` (every env var
  listed empty), `.gitignore` (excludes `.env` + `data/cache/`),
  `README.md`, `pytest.ini`, `CLAUDE.md` (standing rules).
- **Pydantic v2 schemas** in `backend/app/models/schemas.py`. `Paper`,
  `Claim`, `Evidence`, `Methodology`, `Limitation`, `FutureWork`,
  `ClaimRelationship`, `Opportunity`, plus the `PaperExtraction` bundle
  the LLM produces. `extra="forbid"`, DOI normalisation, self-loop
  prevention on relationships, uniqueness of IDs inside extraction
  bundles.
- **DB tables** in `backend/app/db/tables.py` (SQLAlchemy 2.x
  Declarative) mirroring every schema. SQL migrations at
  `backend/app/db/migrations/001_init.sql` (all base tables, indexes,
  check constraints) and `002_pgvector.sql` (vector columns for the
  Phase 3 relationship layer).
- **`config.py`** — pydantic-settings singleton, reads every env var,
  `SecretStr` for sensitive values, custom `__repr__` that never leaks a
  key. Capability flags (`can_use_openalex_live`, `can_use_gemini`,
  `has_database`) so the pipeline can decide live-vs-offline without
  every module re-reading env.
- **Interfaces**:
  - `LLMClient` (`extract` only — no ranking/judgment surface),
    `MockLLMClient` reading canned extractions from
    `data/seed/extractions/`, `GeminiLLMClient` explicit
    `NotImplementedError` for Phase 2.
  - `LitSource` abstract base, `SeedLitSource` serving the committed
    seed corpus.
- **Seed corpus**: 35 papers under `data/seed/papers/` and 35 matching
  extractions under `data/seed/extractions/`. Domain: transformer-based
  time-series forecasting. Every file carries `"seed_sample": true`,
  every ID is `seed:NNNN`, no DOIs — nothing is confusable with a real
  publication. The roster includes:
  - 6 flagship transformer proposals (Informer, Autoformer, FEDformer,
    PatchTST, Crossformer, iTransformer).
  - 3 DLinear-family "linear beats transformer" papers.
  - 3 rebuttal / conditional-win papers.
  - 3 distribution-shift papers.
  - 3 long-horizon studies, 3 few-shot, 3 channel-independence,
    3 frequency, 3 efficiency, 3 transfer, 2 negative-results — chosen
    so the corpus contains genuine cross-paper contradictions and
    unfollowed future-work threads for the Phase 4 reasoning engine.
  - Deterministic citation graph wired between them (99 edges).

Generator: `python -m backend.app.ingestion.seed_generator`.

## Phase 1 — ingestion ✅

Built:

- **`OpenAlexClient`** (`backend/app/ingestion/openalex.py`). Uses the
  public JSON API with the polite-pool `mailto` convention, cursor
  pagination, tenacity-backed exponential retry on 5xx/429, and refuses
  to instantiate without `OPENALEX_MAILTO` set.
- **`SemanticScholarClient`** (`backend/app/ingestion/semantic_scholar.py`).
  Enrichment-first — `.enrich(papers)` looks up each paper by DOI and
  yields the S2 version for merging. Supports offset pagination for
  search and unauthenticated fallback.
- **`normalizer.py`** — `from_openalex()`, `from_semantic_scholar()`,
  DOI/title normalisation, and `deduplicate()` collapsing by DOI first
  then by (normalised title, year). Deterministic merge preference:
  prefer DOI-bearing → prefer abstract-bearing → prefer higher citation
  count → OpenAlex tiebreak. Merges preserve encounter order and union
  citation lists.
- **`pipeline.py`** — one `run_ingestion()` entrypoint plus
  `resolve_sources(prefer="auto"|"live"|"seed")`. `"auto"` falls back to
  the seed corpus when `OPENALEX_MAILTO` is unset, so the pipeline never
  makes surprise network calls.
- **`backend/cli.py`** — the phase-1 demo command:

  ```
  python -m backend.cli ingest --source seed --limit 100
  ```

  Emits `{ query, source_preference, count, papers[] }` JSON to stdout.

## Self-audit

1. **NotImplementedError inventory.** Five hits, all intentional:
   two abstract `LitSource` methods, one abstract `LLMClient.extract`,
   and the `GeminiLLMClient` deferred stub (with a message pointing at
   Phase 2). No function silently returns fake data.
2. **Three outputs trace to real paper IDs.** For `seed:0007`,
   `seed:0022`, `seed:0034` — every paper file's `id`, its extraction's
   `paper_id`, its first `Claim.paper_id`, and its first
   `Limitation.paper_id` all match the seed ID. No orphan objects.
3. **Pytest.** 38 passed, 0 failed. Suite covers schema validation,
   DOI/title normalisation, OpenAlex + S2 mappers, dedup by DOI and by
   title-year, HTTP-mocked search + pagination + `mailto` presence,
   pipeline resolution, end-to-end offline ingestion, CLI subprocess
   run, and settings-repr secret leak check.
4. **Pipeline over seed corpus emits valid JSON.**
   `python -m backend.cli ingest --source seed --limit 100` returns 35
   papers, all IDs unique, years 2021–2024, 99 citation-out edges,
   headline citation count 810.
5. **Pydantic validation.** The end-to-end pipeline test round-trips
   every emitted paper through `Paper.model_validate()`.
6. **No reasoning / ranking leaked into the LLM boundary.** `LLMClient`
   exposes only `.extract()`; the schema check documents the rule as a
   docstring warning. The only `score()`-shaped code lives in
   `normalizer._pick_primary`, which deterministically selects which
   duplicate wins — a merge preference, not a paper-importance judgment.

## What you need to set for live ingestion

- `OPENALEX_API_KEY` — **mandatory since 2026-02-13**. OpenAlex retired
  the polite-pool mailto convention on that date; unauthenticated calls
  now return HTTP 409 once the shared 100-credit/day pool is spent.
  The client refuses to instantiate without a key. Free keys at
  https://openalex.org/settings/api. Passed as `?api_key=…` query
  parameter (docs are explicit that no header form is supported).
- `SEMANTIC_SCHOLAR_API_KEY` — optional; enrichment still works
  unauthenticated but with a stricter rate limit.
- `DATABASE_URL` — a Postgres URL with `pgvector` installed. Not needed
  for Phase 0/1 (nothing writes to the DB yet); it's the first thing
  Phase 3 will consume.

Nothing else is required. The offline seed pipeline runs with **none of
these set** — confirmed against a clean subprocess env in the pytest
suite (`_isolated_env` fixture blanks every relevant var).

## What was NOT built (deliberately)

- No extraction pipeline yet — Phase 2 wires `MockLLMClient` and
  `GeminiLLMClient` into an end-to-end extractor. `MockLLMClient`
  already returns the pre-authored seed extractions, so Phase 2 is
  really about the live Gemini path plus the disk cache under
  `data/cache/`.
- No relationship layer (Phase 3), no reasoning engine (Phase 4), no
  ranking / opportunity generation (Phase 5), no HTTP API (Phase 6),
  no frontend (Phase 7). Every future phase is listed in `CLAUDE.md`.

## Patch — 2026-07-22 — OpenAlex auth model migration

**Bug.** The Phase-1 OpenAlex client was built on the polite-pool
`mailto` convention. OpenAlex made API keys mandatory on 2026-02-13 and
returns HTTP 409 once the shared 100-credit unauthenticated pool is
spent, so the old client would 409 against the live API.

**Fix.** Replaced `OPENALEX_MAILTO` with `OPENALEX_API_KEY` everywhere:
`config.py` (SecretStr field, capability flag, secret-safe `__repr__`),
`.env.example`, the user's `.env`, `OpenAlexClient` instantiation guard
+ every request path, all 7 client tests, both docs. Verified auth
shape against `developers.openalex.org/api-reference/authentication` —
key is a **query parameter** only (`?api_key=…`), no header form is
supported; the tests assert we don't accidentally send it as
`Authorization` or `x-api-key`.

**Credit-awareness added.** Client now parses these response headers
into a `CreditLedger` per session:

    X-RateLimit-Limit          daily credit budget
    X-RateLimit-Remaining      credits left in today's budget
    X-RateLimit-Credits-Used   cost of this request
    X-RateLimit-Reset          seconds until midnight-UTC reset

`client.credits.as_dict()` reports `calls`, `credits_used_this_run`,
`per_endpoint_credits`, and the last-seen `daily_limit`/
`daily_remaining`/`seconds_until_reset`.

**Filter preference.** New `OpenAlexClient.search_filtered(filter=…,
search=…, sort=…, limit=…)` method sends filter-only calls as a
`works.list` endpoint (1 credit per page) instead of `works.search`
(10 credits per page). The docstring points callers at this method
whenever a structured filter would give the same result set.

**409 handling.** New `OpenAlexQuotaError` raised on 409, carrying the
last-seen daily limit and remaining count. Tenacity retries no longer
mask quota exhaustion.

## Live-call proof — 2026-07-22

Ran one **real** call against the live OpenAlex API (not mocked,
network-observable, credit-charged). Query:

    search: "language model calibration" OR "uncertainty quantification
            language models" OR "selective prediction" OR "hallucination
            detection" OR "confidence estimation large language models"
            OR "abstention language models"
    filter: type:article|preprint, publication_year:>2018
    sort  : cited_by_count:desc
    per-page: 25

**Result.** 25 papers returned. Full raw JSON (including
`X-RateLimit-*` headers, OpenAlex `meta` block, and every work's full
inverted-index abstract) saved to `/tmp/researchmap_live_sample.json`.

**Credit ledger for the run.**

    {
      "calls": 1,
      "credits_used_this_run": 10,
      "per_endpoint_credits": {"works.search": 10},
      "daily_limit": 10000,
      "daily_remaining": 9989,
      "seconds_until_reset": 73655
    }

That's 10 credits (single `works.search` page) against the user's
10,000-credit daily quota, leaving 9,989 remaining. The 1-credit
difference between "10 used, 9,989 remaining out of 10,000" appears to
be OpenAlex's own accounting overhead — reported verbatim, not
massaged.

**Confirmation this is real API data.** Response includes real OpenAlex
IDs (`W4384071683`, `W4399803256`, `W4404534210`, …) that resolve at
`openalex.org/works/…`, real citation counts, real DOIs, real 2019-2024
publication years, and a bearer of legitimately-cited abstracts. Papers
mix on-topic hits (Farquhar et al. 2024 semantic-entropy hallucination
detection at `W4399803256`; Hüllermeier & Waegeman aleatoric/epistemic
uncertainty at `W3014596384`; three hallucination surveys) with a
long tail of chemistry / materials-science papers that OR-match one
phrase but aren't calibration research — exactly what raw retrieval
looks like before topical filtering, and useful signal for how much
work the Phase 2+ pipeline will need to do.

## Self-audit — 2026-07-22

1. **NotImplementedError inventory.** Unchanged from Phase 1 baseline:
   five hits, all intentional (three abstract-base-class methods, one
   `GeminiLLMClient` deferral for Phase 2, one docstring reference to
   the deferral). No silent hardcoded fakes.
2. **Three outputs trace to real paper IDs.** Live-call proof papers
   `openalex:W4399803256`, `openalex:W4384071683`, `openalex:W3014596384`
   are resolvable at `api.openalex.org/works/{id}`; every field in the
   proof file came from the response body, not fabricated.
3. **Pytest.** 41 passed, 0 failed. New coverage: refuses without
   `OPENALEX_API_KEY`, sends `api_key` as query param and *not* as
   header or `mailto`, records per-page + per-endpoint credit usage,
   filter-only path bills as `works.list` (1 credit) not `works.search`
   (10 credits), and 409 raises `OpenAlexQuotaError`.
4. **Pipeline over seed corpus still emits valid JSON.**
   Auth refactor did not regress the offline path — the seed-run
   subprocess test still passes.
5. **Pydantic validation.** Every paper in the live response either
   validated cleanly via `from_openalex` or was skipped as malformed
   (the client's normal behaviour); nothing wrote through
   unvalidated.
6. **No reasoning / ranking leaked into the LLM boundary.** `LLMClient`
   surface unchanged. The `sort=cited_by_count:desc` on OpenAlex is a
   *provider-side* sort and does not touch our reasoning layer.
7. **PROGRESS.md updated** — this section.

## Patch — 2026-07-22 — retrieval-quality fix + hit-rate assessment

**Cause.** V1 was 40% off-target because bare-OR search picked up
chemistry/materials-science papers where "uncertainty quantification"
and "calibration" mean something entirely different from what LLM
researchers use those terms for. Cross-domain terminology collision.

**Two changes.**

(a) **Anchored the query.** Every result must now contain BOTH an
LLM/NLP token AND a topic term:

    search : ("language model" OR "LLM" OR "large language model"
              OR "neural text generation")
             AND
             (calibration OR "uncertainty quantification" OR abstention
              OR "selective prediction" OR "hallucination detection"
              OR "confidence estimation" OR "epistemic uncertainty")

(b) **Topical filter added.** Verified against the live OpenAlex API
(not guessed): `Computer Science` is field 17, `Artificial
Intelligence` is subfield 1702 under it. Filter used:

    filter: primary_topic.subfield.id:1702,
            type:article|preprint,
            publication_year:>2018

Chose `primary_topic.subfield.id` over `topics.subfield.id` because the
primary version is stricter — it drops papers where AI is only a
tangential topic. Same 10-credit cost as before.

## Live-call proof v2 — 2026-07-22

25 papers, real API, `works.search` = 10 credits (9,967 remaining of
10,000). Raw JSON at `scratch/live_sample_raw.json`, readable dump
with full abstracts at `scratch/live_sample_readable.md`. Both are
gitignored — `scratch/` was added to `.gitignore` alongside them.

**Real-data confirmation.** IDs like `W4399803256` (Farquhar semantic
entropy), `W4378189609` (HELM), `W4327810158` (GPT-4 technical report),
`W4404534210` (LLM hallucination survey) all resolve at
`api.openalex.org/works/{id}` with matching abstracts and citation
counts.

**Hit-rate assessment.** Of the 25:

- **2 core on-topic** (paper is primarily about the target constructs):
  `W4404534210` (hallucination survey), `W4399803256` (Farquhar et al.
  semantic-entropy hallucination detection).
- **3 adjacent on-topic** (LLM paper with a documented dedicated
  calibration/uncertainty section): `W4327810158` (GPT-4 tech report,
  has post-RLHF calibration subsection), `W4281690148` (BIG-Bench,
  calibration among task categories), `W4378189609` (HELM, calibration
  is one of 7 headline metrics).
- **20 off-topic** — general LLM/AI surveys, prompting surveys,
  explainability (distinct from calibration), knowledge-graphs review,
  autoencoders/RNN/self-supervised/zero-shot reviews, LLM applications
  (clinical, nano-photonics), and one XAI manifesto. Full list in the
  turn transcript.

**Score: 5/25 = 20% on-topic, 80% noise. Still above the 15% ceiling.**

**Progress vs. v1.** The topical filter eliminated *all* chemistry /
materials-science contamination — the class the user flagged in v1 is
gone (zero out of 25). What replaced it is a different noise class:
highly-cited general AI/LLM surveys that mention our target terms in
passing among many topics, promoted to the top by
`sort=cited_by_count:desc`.

**Proposed third refinement (NOT applied — waiting for approval).**
Two-part:

1. **Drop `sort=cited_by_count:desc`, use default relevance sort.**
   Citation-order promotes generic high-impact surveys over targeted
   calibration papers. Relevance-order will rank on match quality
   instead.
2. **Move search from `search=` query param to
   `filter=title_and_abstract.search:…`.** The `search=` parameter
   matches across the full indexed text; the title+abstract filter
   requires our terms to be prominent enough to appear in the paper's
   own summary. Together these should promote papers where
   calibration/hallucination is the actual subject, not a bibliography
   entry.
   Same credit cost (`works.search` = 10 credits/page either way).

If those two together still leave >15% noise, the third fallback is
narrowing to specific OpenAlex topic IDs (finer-grained than the
Artificial Intelligence subfield). That requires one lookup call to
map "LLM safety / hallucination / calibration" to concrete
topic IDs — not going to guess this either.

## Self-audit — 2026-07-22 (post-retrieval-fix)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No silent fakes.
2. **Three outputs trace to real paper IDs.** `openalex:W4399803256`,
   `openalex:W4378189609`, `openalex:W4327810158` — each resolves via
   the OpenAlex singleton endpoint with matching titles/years, and
   every field written to `scratch/live_sample_raw.json` came from
   the response body verbatim.
3. **Pytest.** 41 passed, 0 failed. Retrieval-quality fix touched no
   test-covered code — the query construction lives in the one-shot
   proof script.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** Each of the 25 live results either mapped
   cleanly through `from_openalex` (as measured by the readable dump
   containing 25 well-formed entries) or would have been skipped.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   `sort=cited_by_count:desc` and my hit-rate assessment are BOTH
   provider-side / analyst-side judgments, not decisions embedded in
   the extraction interface.
7. **PROGRESS.md updated** — this section, plus the failure-mode
   entry added to `docs/opportunity-criteria.md` verbatim under
   `## Named failure modes` (only that section; the other four
   headers stay empty).

## Patch — 2026-07-22 — v3 retrieval refinement applied

Both parts:

1. Dropped `sort=cited_by_count:desc`. Default relevance ordering now
   governs — citation-based sort was promoting high-impact generic
   surveys over targeted calibration papers.
2. Moved the boolean query from `search=X` to
   `filter=title_and_abstract.search:X`. The `search=` param covers
   full indexed text; the filter version requires the query terms to
   appear in title or abstract — a much tighter signal.

Same 10-credit cost — moving the query into the filter doesn't leave
the search-price tier because `title_and_abstract.search` is still a
search endpoint. Balance: 9,957 / 10,000.

## Live-call proof v3 — 2026-07-22

Real API. Scratch files overwritten. Real-data spot check: IDs
`W4285429195` (Kadavath), `W4327810286` (SelfCheckGPT), `W3199958362`
(Jiang calibration) all resolve at `api.openalex.org/works/{id}` with
matching abstracts and citation counts.

**Strict grading — primary-subject-only:**

- **Strict hits: 16/25 = 64%.** Sample: Kadavath *Mostly Know What
  They Know*, SelfCheckGPT, LM-Polygraph benchmark, three UQ-for-LLMs
  surveys (2024/2025 vintages), Farquhar-adjacent metamorphic
  hallucination detectors, Jiang *Calibration of LMs*, the
  What-LLMs-know-vs-what-users-think paper (explicit "calibration
  gap"), and the recent epistemic-failure-modes taxonomy.
- **Near-misses: 3/25.** BIG-Bench (calibration is one task type),
  HELM (calibration is 1 of 7 metrics), *LLMs are not Fair Evaluators*
  (proposes a "calibration framework" but for judge order-bias in
  LLM-as-judge, adjacent to but not the confidence-calibration
  literature).
- **Off-topic: 6/25 = 24%.** Sample: *Zero-Shot Time Series
  Forecasters* (mentions "poor uncertainty calibration" of GPT-4 as
  an aside), SPeC (uses "calibration" for prompt-variance tuning, not
  confidence-accuracy alignment), MiniLLM (KD paper mentioning
  calibration as a downstream result), chatHPC, geoscience LLM
  survey, LLMs for language teaching.

Full paper list with abstracts is in `scratch/live_sample_readable.md`.

**Delta over v2.** Strict hit rate 20% → 64%. Off-topic 80% → 24%.
Both refinements pulled their weight — dropping the citation sort
demoted high-citation generic LLM surveys, and the title/abstract
filter dropped papers that only mentioned our terms deep in the body.

**Still above the 15% noise ceiling by 9 percentage points.** Also:
strict grading exposed a known-dedup edge case — the same
Jiang/Neubig calibration paper appears as `W3199958362` (2021
journal) and `W3162385798` (2020 preprint) with different years and
no shared DOI in the OpenAlex records. Our current
DOI-then-normalized-title-year dedup will not collapse this pair.
Noting; not fixing in this batch.

## Ingestion redesign assessment — seed + citation snowball

**Request.** Replace keyword-query ingestion with: pick 10-20
hand-curated seed papers, expand 2 hops via OpenAlex citation edges,
apply the AI subfield filter as a gate, dedupe.

### What already exists in the ingestion layer

- **`OpenAlexClient.get_by_id(paper_id)`** — singleton fetch, 0
  credits (this is the free tier per OpenAlex pricing). Handles the
  seed-lookup step directly.
- **`Paper.citations_out`** — populated from OpenAlex
  `referenced_works`. This is exactly the outgoing (backward-in-time)
  citation edge list — the first half of a snowball hop is already
  built.
- **`OpenAlexClient.search_filtered(filter=…)`** — 1 credit per page
  of up to 200 results. Can be pointed at any filter — including the
  ones we'd need for snowballing.
- **`deduplicate(papers)`** — collapses by DOI then by
  normalized-title+year. Works fine at the end of a snowball run.
- **`normalizer.from_openalex(record)`** — accepts any OpenAlex Work
  JSON and produces a validated `Paper`. Every fetched candidate,
  whether by ID, cites-filter, or referenced-works-filter, comes out
  the other side as a `Paper`.

### What is missing

1. **Inbound citation retrieval.** `Paper.citations_in_count` stores
   only the count. To follow forward citations we'd need
   `filter=cites:W123` (1 credit / page) — the client supports this
   filter shape but no method exposes it as "give me the papers that
   cite X." Small addition on top of `search_filtered`.
2. **Batch-fetch primitive.** OpenAlex's
   `filter=ids.openalex:W1|W2|…|W50` collapses up to 50 singleton
   fetches into one 1-credit list call. Snowballing at hop 2 will
   want this. Not implemented.
3. **Snowball orchestrator.** The traversal itself — a
   frontier + visited set + per-hop cap + total-cap loop that (a)
   loads each seed, (b) enumerates outbound and inbound citations
   via the two filter calls above, (c) gates each candidate against
   the AI subfield filter, (d) dedupes into the visited set, (e)
   stops at hop-K or total-N. Also not present.
4. **Provenance tracking.** Each paper's presence in the corpus
   would carry a chain (seed → hop-1 → this) instead of being
   anonymous. Right now `Paper` has no provenance field. The Phase 4
   reasoning engine will want this — "why is this paper here?" is
   part of the evidence trail.
5. **Seed manifest format.** No file schema for a hand-curated seed
   list. Needs at minimum {id, doi, seed_note} per row plus a
   generated-vs-committed marker parallel to the existing
   `seed_sample: true`.
6. **Config knobs.** Max hops, max papers per hop per seed, subfield
   gate ID(s), whether to walk inbound-only / outbound-only / both.
   None wired into `config.py` or CLI yet.

### Failure modes to be aware of

1. **Seed bias / echo-chamber contamination.** If seeds all cluster
   in one subcommunity (e.g. only NeurIPS-lineage calibration papers),
   the snowball will mirror that community's citation network and
   miss parallel work (Nature-published Farquhar semantic-entropy;
   clinical-uncertainty literature). Countermeasure: distribute the
   seed list across venues and years intentionally, and record how
   each seed was chosen in `seed_note` so this bias is auditable.
2. **Hop-2 combinatorial explosion.** A single seed with 100
   references at hop 1 pulls in up to 100 records; each of those has
   ~50 references, so hop-2 can hit ~5,000 candidates per seed. With
   15 seeds that's ~75,000 candidates before dedup. Needs
   aggressive per-hop and per-seed caps or the credit budget goes
   sideways. In credit terms it's cheap (1 credit per 50-batch =
   ~1,500 credits worst case) but dedup + gate cost real time.
3. **AI-subfield gate drops legitimate off-subfield hits.** Farquhar
   *et al.* semantic entropy is a Nature paper — its OpenAlex
   `primary_topic.subfield` may be Biology or general Nature-family
   subfield rather than 1702 Artificial Intelligence. A hard gate
   would drop it. Softer alternatives: use
   `primary_topic.field.id:17` (Computer Science field, broader) as
   the gate; or gate on `topics.subfield.id:1702` (any of the paper's
   topics, not just primary); or gate on ANY of several relevant
   subfields.
4. **Hub-paper dominance.** Any seed that cites Vaswani *Attention
   Is All You Need* will pull in Vaswani → and at hop 2, everything
   citing Vaswani, which is thousands of off-topic papers. The
   snowball must either (a) blacklist known hub papers before
   expanding, or (b) apply per-node "topical stickiness" scoring
   before continuing to hop 2.
5. **Time-direction asymmetry.** Outbound (referenced_works) walks
   BACKWARD in time — you'll find antecedents. Inbound (cites:X)
   walks FORWARD — you'll find successors. A snowball that does
   both at every hop mixes causal directions in one corpus. That
   may be desired (both build the "map" the project wants) but
   should be a deliberate choice with the direction stored on the
   provenance edge.
6. **OpenAlex citation-graph gaps.** Not every reference in an
   OpenAlex Work resolves to an OpenAlex ID — older venues,
   non-Crossref sources, and preprint-vs-published mismatches
   silently drop edges. Snowball will look complete but isn't.
7. **Preprint-vs-published duplication in the snowball.** Same paper
   appears as arXiv preprint (heavy inbound citations) and journal
   publication (fewer inbound but higher `cited_by_count`). Current
   dedup won't collapse the pair unless they share a DOI record.
   This is the same edge case we hit in v3 grading with the two
   Jiang calibration papers.
8. **No stopping rule beyond "N papers".** Without a topical-quality
   score attached to each fetched candidate, the snowball keeps
   expanding into progressively less relevant territory. The
   quality/quantity trade-off has to be an explicit config knob, not
   an emergent property of the walk.
9. **Seed poison.** A single mis-tagged seed (e.g. a hallucination
   paper that turns out to be a chemistry paper about "hallucination"
   in a totally different sense) will pollute an entire branch.
   Countermeasure: require abstract-level review of seeds before
   they enter the manifest, and record `seed_note` explaining topical
   fit.

### My recommendation on the trade-off

The snowball is the right long-run approach — its whole appeal is
that each paper in the corpus has a traceable provenance chain, which
is exactly what the "no orphan conclusions" rule in `CLAUDE.md`
demands. Keyword ingestion can never provide that. But the pieces
missing (inbound-citation retrieval, batch fetch, orchestrator,
provenance model, seed manifest, config knobs) are enough that it
would be a full sub-phase of work, not a small patch.

The keyword pipeline as it stands (v3, 64% strict hits) is good
enough to feed Phase 2 extraction as a smoke test — Phase 2 processes
each paper independently and the extraction schema will surface
off-topic papers as papers with poorly-formed claims, which is
diagnostic in its own right. If you want to do the snowball redesign,
it's cleaner as a separate Phase 1.5 before extraction goes live.

## Self-audit — 2026-07-22 (post-v3)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference).
2. **Three outputs trace to real paper IDs.** `openalex:W4285429195`
   (Kadavath), `openalex:W4327810286` (SelfCheckGPT),
   `openalex:W3199958362` (Jiang calibration) — each resolves via
   the OpenAlex singleton endpoint with matching titles/years, and
   every field written to `scratch/live_sample_raw.json` came from
   the response body verbatim.
3. **Pytest.** 41 passed, 0 failed. Retrieval refinement lived in
   the one-shot proof script, not the test-covered code.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** All 25 v3 results validate cleanly against
   the OpenAlex mapper.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   `title_and_abstract.search` filter and the hit-rate assessment are
   both analyst-side / provider-side decisions, not encoded in the
   extraction interface.
7. **PROGRESS.md updated** — this section. Failure-mode entry in
   `docs/opportunity-criteria.md` unchanged.

## Patch — 2026-07-22 — dedup: cross-year preprint/published collapse

**Motivation (scoring integrity, not cosmetic).** Two records for the
same underlying work — a preprint and a subsequent journal
publication, or the same paper across two venues — would be counted
as independent papers by any downstream scorer that treats "papers
reporting a claim" as a count. That would fake replication where none
occurred and inflate the persistent-limitations scorer,
finding-support scores, and any opportunity scoring that leans on
independence of evidence. This one belongs in ingestion, before
extraction ever sees the corpus.

New third dedup pass added after the DOI and (title, year) passes:

    Pass 3 — same normalized title, |Δyear| ≤ CROSS_YEAR_WINDOW (=2),
             AND at least one shared normalized last-name → merge.

Author normalization reduces every input to a lower-cased,
ASCII-folded last-name token. Handles the format variants OpenAlex
and Semantic Scholar actually emit:

    "John A. Doe"    → "doe"
    "J. Doe"         → "doe"
    "Doe, John"      → "doe"
    "María Müller"   → "muller"      (diacritics stripped)

Overlap is set-intersection on those tokens. Empty on either side is
"no positive evidence" and refuses to merge — protects against
false-positive collapses of two truly distinct same-titled papers
where one record lacks author metadata.

**Also fixed while here: HTML tags in titles.** OpenAlex serves
inline markup in titles (`<i>When</i>`, `<sub>2</sub>`, `<scp>AI</scp>`).
Un-stripped, tag names leaked into the normalized key as `i`, `sub`,
`scp` tokens and defeated title-based dedup. `normalize_title` now
strips HTML tags as its first step. This was the actual reason the
Jiang preprint/journal pair had different normalized titles despite
being identical modulo formatting.

**Verified on the v3 live sample.** Feeding all 25 v3 papers through
`deduplicate()` post-fix collapses **two real preprint→published
pairs**:

- `W3162385798` (2020 arXiv Jiang *How Can We Know When LMs Know?*)
  collapses into `W3199958362` (2021 TACL journal version). Different
  DOIs (arXiv 10.48550/… vs TACL 10.1162/…), different years, same
  authors, same title modulo the `<i>` italic tag on `<i>When</i>`.
- `W4388585881` (2023 arXiv *Survey on Hallucination in LLMs*)
  collapses into `W4404534210` (2024 journal version). Same story.

**These would have inflated replication counts by 2 out of 25 in a
single 25-paper sample** — an 8% inflation rate on any
paper-count-dependent score if the fix hadn't landed. Enough that the
persistent-limitations score would meaningfully change.

**What the fix deliberately does NOT do.**

- No arXiv-specific DOI heuristic. Records with different DOIs are
  still treated as potentially-distinct; the merge only fires when
  title + author + adjacent-year all agree. If we later want to
  treat `10.48550/arxiv.*` as a preprint marker and eagerly-collapse
  against journal DOIs of the same paper, that's a Phase 1.5 add-on.
- No fuzzy title match. Edit-distance / token-set overlap could
  catch harder cases ("Attention Is All You Need" vs
  "Attention Is All You Need (Extended)") but also expands the
  false-positive surface. Held off deliberately.
- No cross-year merge without author evidence. If either record has
  empty authors, we refuse to merge — a safe default that trades a
  small under-dedup risk for zero false-positive risk.

## Self-audit — 2026-07-22 (post-dedup-fix)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No new silent stubs.
2. **Three outputs trace to real paper IDs.** V3 live-sample dedup
   demo above collapses `openalex:W3162385798` into
   `openalex:W3199958362` and `openalex:W4388585881` into
   `openalex:W4404534210`. All four IDs resolve via
   `api.openalex.org/works/{id}`; the collapses are verifiable by
   inspecting `scratch/live_sample_raw.json` against `Paper.model_validate`
   and `deduplicate`.
3. **Pytest.** 49 passed, 0 failed (+8 tests from Phase 1 baseline).
   New coverage:
   - `test_dedup_collapses_preprint_and_published_across_years`
     (the exact v3 case)
   - `test_dedup_does_not_collapse_same_title_different_authors`
     (false-positive safety)
   - `test_dedup_does_not_collapse_when_year_gap_exceeds_window`
   - `test_dedup_refuses_cross_year_merge_when_authors_missing`
   - `test_dedup_cross_year_pass_tolerates_author_format_variants`
   - `test_dedup_cross_year_within_window_but_not_at_zero_or_beyond`
     (boundary — Δ=1,2 merge; Δ=3 doesn't)
   - `test_author_helpers_normalize_expected_formats`
     (`_normalize_last_name`, `_authors_overlap`)
   - `test_normalize_title_strips_inline_html_tags`
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged;
   seed titles have no HTML tags and no cross-year duplicates.
5. **Pydantic validation.** All merges route through `Paper.model_validate`
   in `_merge`.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   dedup fix lives entirely in `backend/app/ingestion/normalizer.py`;
   the `LLMClient` interface still exposes only `.extract()`. Author
   overlap is set intersection on normalized tokens — pure syntactic
   equality, not a judgment call.
7. **PROGRESS.md updated** — this section. Failure-mode entry added
   verbatim to `docs/opportunity-criteria.md` under
   `## Named failure modes` (the other four section headers stay
   empty for hand-fill).


## Next step

Nothing autonomous. Awaiting explicit call on:

1. Whether to do the seed + citation snowball redesign as a **Phase
   1.5** before Phase 2 (assessment stands in the previous section).
2. Whether to proceed to Phase 2 extraction with the v3 keyword
   corpus (now 64% strict hits with cross-year dedup in place) as a
   smoke-test corpus.
3. Whether to add an arXiv-DOI-aware collapse (would catch
   preprint/journal pairs where the DOIs differ but one is
   `10.48550/arxiv.*`). Currently deferred.
## Patch — 2026-07-22 — merge policy + arXiv-DOI pass (change A)

Merge semantics were previously implicit. Made everything explicit and
deterministic. This is one logically-independent change; the arXiv
pass below (change B) is the second.

**Survivor rule — deterministic, order-independent.** Written up in
`docs/merge-policy.md`; realised in `_survivor_key(p)` + `_pick_survivor(a, b)`.
Precedence tiers, higher wins:

    (1) is_pub_doi        — non-arXiv DOI beats arXiv-DOI beats no DOI
    (2) has_venue         — presence of a venue string
    (3) citations_in_count
    tiebreak: lex-lower id

`_pick_survivor(a, b)` and `_pick_survivor(b, a)` return the same
`(survivor, loser)` pair. Removed the previous source-of-record
ranking (OpenAlex > S2 > seed) — provider identity shouldn't decide
which record is canonical, only paper-content signals should.

**Per-field merge policy — every Paper field spelled out** in
`docs/merge-policy.md`. Categories:

- survivor-only: `id`, `source`, `source_id`, `title`
- fill-in (survivor's if truthy, else loser's): `doi`, `abstract`,
  `year`, `authors`, `venue`, `fulltext`
- union: `citations_out` (order-stable, survivor first)
- OR: `oa_fulltext_available`
- policy-controlled: `citations_in_count`
- transitive union: `merged_from`

**`CITATIONS_MERGE_POLICY = "max"`** — named module-level constant.
Rejected `"sum"` (double-counts anyone citing both versions) and
`"survivor"` (silently loses information). `max` is conservative and
grep-able; ranking (Phase 5) will read the constant, not a magic
number.

**`merged_from` list added to the `Paper` schema (Pydantic v2 + DB).**
Every collapse writes the loser's ID (plus any prior `merged_from`)
into the survivor's `merged_from`, transitively. Survivor's own ID is
never in its own list. Order-stable, de-duplicated. This gives Phase 4
the audit trail promised by the *no orphan conclusions* rule — asking
"what did we collapse to get this record?" now has a concrete answer.

Migration `001_init.sql` gained a `merged_from TEXT[] NOT NULL
DEFAULT '{}'` column on `papers`. `PaperRow` mirrors it. No live DB
has run against the migration, so editing it in place was safe.

**Output ordering.** `deduplicate()` now returns `sorted(by_id.values(),
key=lambda p: p.id)`. Feeding it any permutation of the same input
produces byte-identical output. Verified by the new
`test_dedup_is_order_independent` and separately on the live 25-paper
sample.

**Forward-compat commitment for Phase 2.** Merge policy for `Claim`,
`Evidence`, `Methodology`, `Limitation`, `FutureWork`, and
`ClaimRelationship` is written down in `docs/merge-policy.md` under
*Forward-compat commitment for Phase 2* — flagged NOT-YET-IMPLEMENTED
but locked in so Phase 2 doesn't invent policy at the wrong time. Key
promise: no entity attached to a merged-away paper is silently
dropped.

## Patch — 2026-07-22 — arXiv-DOI-aware pass (change B)

New pass 4 in `deduplicate()`. Fires when: one record has an arXiv
DOI (`10.48550/arxiv.*` prefix — case-insensitive), the other has a
non-arXiv DOI, both have the same normalized title, and there's at
least one shared normalized last-name. **No year-window constraint**
— the arXiv/non-arXiv DOI pair is already strong evidence, so long
preprint→journal lags (e.g. 5-year gaps) collapse too.

**Deliberately not merged by pass 4:**

- arXiv-DOI + different authors → different people happen to have
  used the same title.
- Two arXiv DOIs → both preprints, neither is canonical; refuse.
- arXiv-DOI + different title → almost certainly two papers by the
  same prolific author.

**Not in scope, deliberately deferred:** fuzzy / edit-distance title
matching. Would add real false-positive surface without a scoring
model to defend against it — waiting for that until the reasoning
engine has an evaluator that can tell us the trade-off matters.

## Live-call proof — 2026-07-22 (post-policy patch)

Re-ran dedup against the v3 25-paper sample. **Before: 25. After: 23.**
Same collapses as prior patch (both already handled by pass 3):

- `openalex:W3162385798` → `openalex:W3199958362` (Jiang, 2020 arXiv
  → 2021 TACL). Survivor's `merged_from = ["openalex:W3162385798"]`.
- `openalex:W4388585881` → `openalex:W4404534210` (Hallucination
  Survey, 2023 arXiv → 2024 journal). Survivor's `merged_from =
  ["openalex:W4388585881"]`.

Also verified order-independence on the real sample: reversing the
25-paper input list produces a byte-identical output list (compared
via `model_dump()`). That's the property the code change guarantees;
the live sample confirms it in the wild.

**NOT characterised as a rate.** This sample is known ~40% off-target
from the earlier OR-matching issue and has 25 papers — nowhere near a
population estimate. The value here is that the code works on real
API data, not that we've measured how often duplicates occur.

## Self-audit — 2026-07-22 (post-policy patch)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No new silent stubs.
2. **Three outputs trace to real paper IDs.** `openalex:W3199958362`,
   `openalex:W4404534210`, and the untouched `openalex:W4285429195`
   (Kadavath) all resolve at `api.openalex.org/works/{id}` with
   matching titles/years; the two merged records both carry a
   `merged_from` pointer to a second real OpenAlex ID.
3. **Pytest.** 62 passed, 0 failed (+13 tests over the previous batch).
   New coverage:
   - `test_survivor_prefers_non_arxiv_doi_over_arxiv`
   - `test_survivor_falls_through_to_lex_lower_id_on_total_tie`
   - `test_dedup_is_order_independent` (the killer test)
   - `test_merged_from_records_the_collapsed_id`
   - `test_merged_from_accumulates_transitively_over_chain`
   - `test_merged_from_never_includes_survivor_own_id`
   - `test_citations_merge_policy_is_max`
   - `test_pass4_collapses_arxiv_and_non_arxiv_doi_pair`
   - `test_pass4_collapse_survives_wide_year_gap`
   - `test_pass4_does_not_collapse_when_authors_disjoint`
   - `test_pass4_does_not_collapse_two_arxiv_dois`
   - `test_pass4_does_not_collapse_when_titles_differ`
   - `test_is_arxiv_doi_recognises_the_prefix`
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged;
   seed corpus has no arXiv DOIs and no cross-year duplicates.
5. **Pydantic validation.** New `merged_from` field is a
   `list[NonEmptyStr]` with `default_factory=list`; existing seed
   JSON files (which lack the field) still validate via the default.
   No schema regression.
6. **No reasoning / ranking leaked into the LLM boundary.** Survivor
   selection is a pure function of three explicit metadata tiers +
   a lex tiebreak. `CITATIONS_MERGE_POLICY` is a merge rule, not a
   ranking judgment. `LLMClient` interface still exposes only
   `.extract()`.
7. **PROGRESS.md updated** — this section. `docs/merge-policy.md`
   is the source of truth for the policy; PROGRESS.md links to it
   rather than duplicating the field table.

## Next step

Nothing autonomous. Awaiting explicit call on:

1. Whether to do the seed + citation snowball redesign as a **Phase
   1.5** before Phase 2.
2. Whether to proceed to Phase 2 extraction with the v3 keyword
   corpus (64% strict hits, dedup + merge policy now solid) as a
   smoke-test corpus.

## Patch — 2026-07-23 — Phase 1 flagged-item cleanups

Three flagged items from the previous session addressed together:

**Item 1 — `by_id` key vs `merged.id` inconsistency.** Previously,
after a merge where the newcomer won the survivor pick, `by_id`
stayed keyed by the first-seen ID while the stored record's own
`.id` was the survivor's. Downstream index lookups (`title_index`
buckets) then referenced a key that no longer had a `by_id` entry,
so later dedup passes silently missed collapses. New `_rekey(old,
new)` helper rewrites every index (`doi_index`, `title_year_index`,
`title_index`) when the survivor identity flips, and the merge
branch removes/reinstates the `by_id` entry under the survivor's
ID. Regression test:
`test_by_id_key_agrees_with_merged_id_after_newcomer_wins`
exercises a 3-way collapse where the middle record wins over the
first-seen; without the rekey the third record wouldn't find the
survivor.

**Item 2 — Pass 2 author check.** Symmetry with passes 3 and 4:
same-title + same-year is now conditional on ≥1 shared normalized
last-name. Empty authors on either side refuses to merge (positive
evidence rule). New tests:
- `test_pass2_collapses_when_authors_overlap` (positive baseline)
- `test_pass2_does_not_collapse_when_authors_disjoint` (two truly
  distinct papers with the same title in the same year survive)
- `test_pass2_refuses_merge_when_authors_missing`

Two existing tests (`test_dedup_collapses_by_title_year_when_doi_missing`
and `test_dedup_prefers_record_with_doi_and_abstract`) had no
authors on either side; they now include `["Ashish Vaswani"]` /
`["A. Vaswani"]` to keep their semantic intent (pass-2 title+year
merge; DOI preference on merge) while satisfying the new rule.

**Item 3 — Seed corpus regeneration.** All 35 seed paper JSONs on
disk now carry the `merged_from: []` field explicitly. To keep
future regenerations diff-clean, the `PaperExtraction.extracted_at`
timestamp for seed extractions is now a fixed value
(`2026-07-21T00:00:00Z`) instead of `datetime.now()` — regenerating
the corpus produces byte-identical output.

**Tests:** 66 passing (+4 over change B). No live LLM calls made;
no API keys touched.

## Phase 2 — corpus quality diagnosis (2026-07-23) → **GATE A**

Live OpenAlex call — 200 papers under the frozen v3 query strategy
(anchored `title_and_abstract.search:(anchor) AND (topic)`, filter
`primary_topic.subfield.id:1702, type:article|preprint,
publication_year:>2018`, default relevance sort). Single request, 10
credits, daily balance 9,937 / 10,000.

**Artifacts** (all committed):

- `data/live_samples/phase2_diagnostic_raw.json` — raw response,
  meta, credit-ledger headers. sha256[:12] logged for reproducibility.
- `data/labelled/heuristic_full_labels.csv` — every one of the 200
  papers with heuristic label + matched anchor/topic terms.
- `data/labelled/corpus_relevance_review.csv` — 60-paper random
  sample (deterministic seed 20260723) with an empty `on_domain`
  column for hand-labelling.
- `data/labelled/per_clause_leak.md` — the per-clause report.

**Heuristic auto-label distribution (n=200):**

| Label | Count | Share |
|:------|------:|------:|
| on-domain | 180 | 90.0% |
| borderline | 19 | 9.5% |
| off-domain | 1 | 0.5% |

**Important — 90% is NOT precision.** The heuristic is designed
to catch cross-domain contamination (chemistry, materials science,
medicine venues, non-CS primary fields). The AI-subfield filter
already removed those at query time, so the strict off-domain
bucket is near-empty by construction. The `borderline` bucket is
where within-AI application papers accumulate (e.g. Nature Geoscience
review on generative AI, medical LLM summarization, chatHPC). The
60-paper hand-review CSV is the definitive precision measurement.

**Per-topic-term leak (non-on-domain rate = borderline + off-domain
share, the informative view):**

| Topic term | Matches | Non-on-domain hits | Rate |
|:-----------|--------:|-------------------:|-----:|
| epistemic uncertainty | 8 | 2 | 25.0% |
| calibration | 105 | 8 | 7.6% |
| uncertainty quantification | 31 | 2 | 6.5% |
| hallucination | 49 | 2 | 4.1% |
| hallucination detection | 40 | 1 | 2.5% |
| abstention | 6 | 0 | 0.0% |
| selective prediction | 3 | 0 | 0.0% |
| confidence estimation | 7 | 0 | 0.0% |

**Per-anchor-term leak (non-on-domain rate):**

| Anchor term | Matches | Non-on-domain hits | Rate |
|:------------|--------:|-------------------:|-----:|
| large language model | 23 | 4 | 17.4% |
| language model | 31 | 5 | 16.1% |
| llm | 98 | 8 | 8.2% |
| language models | 185 | 14 | 7.6% |
| large language models | 159 | 12 | 7.5% |
| llms | 138 | 10 | 7.2% |
| neural text generation | 0 | 0 | — |

Zero hits on `neural text generation` — worth dropping from the
anchor list unless there's a specific reason it's there.

**Caveats:**

- 13/200 papers came back with no abstract in the OpenAlex response
  body. For those, per-clause attribution is title-only, which
  under-counts a few matches (2 papers had no anchor term visible,
  9 had no topic term visible in title-only). Small enough to not
  move the ranking; noted for honesty.
- The heuristic's on-domain "venue in allowlist" gate is triggered
  by arXiv on many rows. That's intentional (a lot of on-domain
  work lives on arXiv) but it inflates the 90% figure toward
  "papers we won't rule out" rather than "papers we're confident
  are on-domain".
- Random seed for the 60-paper sample is 20260723; the sample is
  reproducible.

**STOP — GATE A.** Do not proceed to Phase 3 (query hardening +
snowball) until Raj has reviewed the 60-paper hand-label CSV and
tells me the actual per-clause leak we're targeting.

## Patch — 2026-07-23 — sequencing repair to unblock labelling

Seven items done, one commit each. No snowball, no live LLM calls,
no v4 corpus, no new phase started.

1. **Git history rewrite.** The 5.3 MB `phase2_diagnostic_raw.json`
   blob that slipped into commit `819f8b7` on Phase 2 was stripped
   from every commit using `git filter-repo --path
   data/live_samples/phase2_diagnostic_raw.json --invert-paths`.
   `.git` shrunk from **2.1 MB → 332 KB** (6× reduction). Blob
   absent from every commit (`git log --all --diff-filter=A` on
   the path returns nothing). Verified `.gitignore` blocks the
   path via `git check-ignore -v`; the recurrence-prevention fix
   (the inline-comment repair from the pre-filter chore commit)
   was dropped by filter-repo along with the leaked blob, so it
   was re-committed as `chore: fix .gitignore inline-comment bug
   (post filter-repo)`.

2. **CLAUDE.md re-sequencing.** The old Phase 5 bundled ranking +
   validation; split into Phase 5 (ranking) and Phase 6
   (validation) with the retrospective time-split test as
   Phase 6's whole content. Phase 7 = API, Phase 8 = frontend.
   Phase 1 now explicitly bounds itself to a small-sample corpus
   with an inline note that snowball / OA-fulltext / scale-up
   ingestion is deferred until Phase 2 tells us what the corpus
   must contain.

3. **`docs/labelling-rubric.md` written** verbatim from the spec.
   Discriminator is contribution, not vocabulary; borderline
   papers are KEPT with a `domain_centrality` tier, not dropped.

4. **Review artifact rebuilt.** New script
   `backend/app/corpus/build_review_artifact.py` consumes the
   existing raw JSON dump (no fresh API call) and emits
   `scratch/corpus_review.csv` + `scratch/corpus_review.md` (both
   gitignored). 60 papers, deterministic same-seed sample as
   `diagnose_v3` (`RNG_SEED=20260723`). Five metadata columns
   prefilled (`openalex_id`, `title`, `venue`, `year`,
   `abstract_full` — FULL untruncated), six blank columns for
   hand labelling (`on_domain`, `has_limitation`, `claim_hedged`,
   `has_future_work`, `compound_claims`, `notes`). The old
   `data/labelled/corpus_relevance_review.csv` was removed as
   superseded.

5. **Dropped `neural text generation`** from `ANCHOR_TERMS` and the
   `diagnose_v3` query. Phase 2 diagnostic showed 0/200 matches.
   Comment retained explaining why.

6. **Failure mode added** verbatim to `docs/opportunity-criteria.md`
   under `## Named failure modes`: within-domain application noise
   (paper uses domain vocabulary correctly but its contribution
   lies in another task — medical summarization mentioning
   hallucination). Consistent with the labelling rubric.

## Self-audit — 2026-07-23 (sequencing repair)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference).
2. **Three outputs trace to real paper IDs.** The rebuilt review
   artifact draws the same 60 papers from the phase-2 raw dump.
   `W4396881553`, `W4309634482`, `W4404534210` are among them and
   all resolve at `api.openalex.org/works/{id}`.
3. **Pytest.** 66 passed, 0 failed. Corpus / heuristic changes
   have no tests directly (they're diagnostic tooling) but the
   normalizer/dedup regression suite is intact.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** Unchanged.
6. **No reasoning / ranking leaked into the LLM boundary.** No
   LLM boundary touched this session. The labelling rubric
   explicitly places contribution-level judgment on the HUMAN
   reviewer, not the LLM extraction interface.
7. **PROGRESS.md updated** — this section. `.gitignore` fix
   verified; blob absent from history.

## What's next

Blocked on your hand-label of `scratch/corpus_review.csv`. Once you
have per-paper `on_domain` verdicts and the pressure-test columns
filled, we'll have:
- Real per-clause leak (not the heuristic-blind version).
- A first data point on whether abstracts alone yield enough
  limitations to score anything — which decides whether Phase 1
  scaling needs OA full text.
- Evidence for or against the four schema pressure-test hypotheses
  (do compound claims exist? do hedged claims dominate?).

Phase 3 (query hardening + snowball) is still blocked on
GATE A. No live LLM calls have ever run.

## Patch — 2026-07-23 — autonomous pre-labelling + schema pressure-test

Session goal was to minimise Raj's manual time. Five items, one
commit each. No live LLM calls. No fresh OpenAlex calls (consumed
the existing on-disk raw dump).

**Item 1 — pre-labelled the 60-paper corpus.** New script
`backend/app/corpus/prelabel.py` encodes my per-paper judgments
against the hand-review sample. Distribution:

| Label | Count | Share |
|:------|------:|------:|
| on-domain | 26 | 43.3% |
| borderline | 13 | 21.7% |
| off-domain | 21 | 35.0% |
| hard cases (flag) | 7 | — |

This diverges sharply from the heuristic's 90% on-domain — the
heuristic was blind to within-domain application noise (LLM papers
whose contribution lies in quantization, pruning, medical
summarization checklists, HCI reliance interventions, etc.).
Contribution-level judgment surfaces those; the labelling rubric
committed earlier this session (`docs/labelling-rubric.md`) puts
this distinction in writing.

`scratch/audit_sample.md` is the artifact Raj reads: stratified
5+5+5 stratified sample with a hard-case addendum, blank
agree/disagree line under each. `scratch/corpus_review.csv` and
`.md` carry all 60 pre-labels + one-sentence reasoning per paper.

**Item 2 — schema pressure-test aggregated.**
`docs/schema-pressure-test.md` reports the four hypothesis findings
across 56 abstracts (4 had no abstract in the OpenAlex response):

- `has_limitation`: **71.4% yes** — abstract-only extraction will
  feed the persistent-limitations scorer at meaningful volume.
  OA full text raises recall, not required for the function.
- `claim_hedged`: **91.1% firm** — assertion strength does NOT
  need to be a separate schema field.
- `has_future_work`: **41.1% present** — the unfollowed-future-
  work scorer will miss ~60% of threads on abstracts alone. OA
  full text is a real gap here.
- `compound_claims`: **58.9% yes** — extractor MUST split
  compound sentences into atomic `Claim` + `Evidence` records.

Concrete decision list at the end of the doc:

1. **Required before Phase 2:** add `Limitation.source_scope`
   (this_work | prior_work). Cheap migration.
2. **Required before Phase 2:** compound-splitting rule in the
   extractor contract; optional `Claim.source_sentence_id` for
   provenance. Cheap.
3. **Rejected:** `Claim.assertion_strength` as a separate field.
   91% firm gives no discriminative power.
4. **Deferred to Phase 1.5:** OA full-text ingestion for
   future-work recall. Do not build speculatively — wait for
   Phase 2 to show that abstract-only is the actual bottleneck.

**Item 3 — drafted `docs/opportunity-criteria.md`.** Previously
empty; now a DRAFT with concrete first-draft content across all
five sections (valid / non-trivial / actionable / failure modes /
matching rule). Marked at the top: pending Raj's revision. The
three pre-existing failure modes (terminology collision,
duplicate inflation, application noise) stay verbatim; three new
DRAFT failure modes added (prior-work limitation misattribution,
compound-claim under-splitting, evaluation-set contamination).

Highlights of the draft:

- Valid: ≥ 3 independent papers (keyed to 4-pass dedup and
  merged_from), no-orphan-conclusions, runtime check that no
  scorer output came from an LLM.
- Non-trivial: cross-cluster gap, unresolved contradiction,
  unfollowed ≥ N-year future work (flagged as under-powered
  without OA full text — see schema pressure-test), cross-domain
  method transfer.
- Actionable: named object, named minimal experiment, named
  contradiction, cost floor.
- Matching rule: frozen-corpus year-Y → year-(Y+k) test with
  top-K precision as the honest metric, deterministic Python
  matching, and an explicit anti-goal against expert-judgment
  leakage.

**Item 4 — autonomy policy in CLAUDE.md.** New section
immediately before the Phase index. Default: maximum autonomy;
build, test, commit, continue to the next phase WITHOUT approval
EXCEPT at five hard stops:

  (a) spend money / call a paid API — stop and cost first;
  (b) needs a credential, account, or human transaction;
  (c) Phase 4 reasoning-engine output — Raj must personally
      judge the top-ranked opportunities;
  (d) any change to a documented policy in `docs/` — extending
      OK, overturning needs approval;
  (e) architecturally irreversible actions.

Outside those: proceed, log, flag.

## Self-audit — 2026-07-23 (autonomous pre-labelling session)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No new silent
   stubs.
2. **Three outputs trace to real paper IDs.** The pre-labels for
   `openalex:W4404534210` (Hallucination Survey), `W4285429195`
   (Kadavath — not in this sample but referenced from earlier
   sessions), and `W7131659145` (Geometric Overflow — sample #04)
   are all traceable back to `scratch/corpus_review.csv` with
   full abstract text, and every OpenAlex ID resolves at
   `api.openalex.org/works/{id}`.
3. **Pytest.** 66 passed, 0 failed. No test-covered code was
   touched — corpus / documentation session.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** Unchanged. Schema pressure-test
   findings recommend two nullable-field additions
   (`Limitation.source_scope`, `Claim.source_sentence_id`) but
   those are recorded as decisions in `docs/schema-pressure-test.md`,
   not applied — the schema patch would be its own commit before
   Phase 2 starts.
6. **No reasoning / ranking leaked into the LLM boundary.** All
   60 labels were assigned by me from abstract text, per the
   labelling rubric. No LLM boundary touched this session.
7. **PROGRESS.md updated** — this section. `docs/opportunity-
   criteria.md` is now a draft (previously blank), and the
   autonomy policy in `CLAUDE.md` unblocks future sessions from
   asking permission on ordinary work.

## What's next

- Raj to read `scratch/audit_sample.md` (15 papers + hard cases).
  Any label the reviewer disagrees on gets updated in
  `backend/app/corpus/prelabel.py` and re-run; corrections
  flow into the CSV and the audit deterministically.
- Once labels are agreed, the true per-clause leak is measurable
  by cross-referencing on-domain / borderline / off-domain
  against the `matched_topic_terms` / `matched_anchor_terms`
  columns already in the CSV.
- After Gate A closes, Phase 3 (query hardening + snowball) can
  proceed autonomously per the new autonomy policy, stopping only
  at the five hard stops.

## SPEND GATE — approval requested to run live extraction

Everything above is committed and offline-runnable. This section is
the halt point per the autonomy policy hard-stop (a).

### Cost estimate — Gemini 2.5 Flash (standard tier)

**Pricing** (verified from ai.google.dev/gemini-api/docs/pricing,
2026):

| Model | Input ($/1M tok) | Output ($/1M tok) |
|:------|-----------------:|------------------:|
| Gemini 2.5 Flash          | $0.30 | $2.50 |
| Gemini 2.5 Flash-Lite     | $0.10 | $0.40 |
| Gemini 2.5 Flash (Batch)  | $0.15 | $1.25 |
| Gemini 2.5 Flash-Lite (Batch) | $0.05 | $0.20 |

**Per-paper token budget** (measured from `prompts/v1.0.0/extract.md`
+ typical OpenAlex abstract):

- Prompt template (rules + schema example + placeholders): ~1,500
  input tokens.
- Paper metadata (title + year + venue + authors + paper_id): ~100.
- Abstract: OpenAlex abstracts run 200–400 tokens; use 300 as the
  average.
- **Input per paper: ~1,900 tokens.**
- Output JSON (≈3 claims × 100 + 2 evidence × 60 + 2 methods × 80 +
  2 limitations × 80 + 2 future_work × 60 + JSON overhead ≈ 100).
- **Output per paper: ~1,000 tokens.**

Retry allowance: `Extractor.max_retries=2`, so up to 3 attempts per
paper. Worst-case token cost = 3× the point estimate. Real hit-rate
on the mock tests: 1 attempt per paper. For the estimate below I
assume 1.1 attempts on average (10% retry rate).

### Estimated dollar cost

| Model | 30 papers | Full 200-paper corpus |
|:------|----------:|----------------------:|
| **Gemini 2.5 Flash (standard, our recommendation)** | **~$0.10** | **~$0.65** |
| Gemini 2.5 Flash-Lite (standard) | ~$0.02 | ~$0.13 |
| Gemini 2.5 Flash (Batch, ~24h latency) | ~$0.05 | ~$0.33 |
| Gemini 2.5 Flash-Lite (Batch) | ~$0.01 | ~$0.07 |

Worst-case (all papers hit the 3-attempt limit): 3× above → **at
most $2 for the full corpus** on standard Flash pricing.

**Recommendation: Gemini 2.5 Flash standard tier.** Flash-Lite is
~5× cheaper but is a smaller model; for a first live extraction we
want the higher-quality outputs to compare against my pre-labels.
The absolute cost difference ($0.65 vs $0.13) is well below noise.

### Env var you need to set

```bash
export GEMINI_API_KEY=<your key>
```

Free at https://ai.google.dev/gemini-api. No credit card required
for the free tier; the extractor will silently upgrade to paid if
the free daily limit is hit (Google's default). Set a hard billing
alert at $5 to be safe — cheap insurance.

### What I have NOT done and will not do without approval

- No live LLM call has been made this session or in any prior
  session — the extractor was built and tested against
  `ProgrammableMockLLMClient` and `MockLLMClient` only. The Gemini
  client is implemented and instantiable but its `.generate()` is
  never invoked from the test suite.
- No API key is required to run the current test suite. `pytest -q`
  → 114 passed, 0 failed, all offline.
- Say "go with 30 papers on Flash" (or your preferred model) and
  I'll run it. Say a subset ("go with 5 for a smoke test") and I'll
  do that.

### After approval — what I would do

1. Read the API key from the environment (never persisted).
2. Run the extractor over the target papers (from
   `data/live_samples/phase2_diagnostic_raw.json`, minus the 6
   excluded per the abstract-recovery manifest).
3. Log per-paper token usage and running cost.
4. Persist extractions to `data/cache/extractions/` (offline cache
   already in place; no DB required for the smoke test).
5. Emit a per-paper diff report comparing my pre-labels to what
   the extractor produced — that's the first real signal of
   whether the abstract-only pipeline is worth pursuing before we
   build OA full-text ingestion.

## Live extraction run — 2026-07-23 — Gemini 3.6 Flash, 30 papers

**The real-extraction gate is now satisfied.** 30 papers extracted with
a real LLM (`extractor` = `gemini:gemini-3.6-flash`), cached under
`data/cache/extractions/`.

### Model + infra changes this run (all committed)

- **Model is config-driven** (`GEMINI_MODEL`, default
  `gemini-flash-latest`) and **validated against `models.list` at
  client startup** — a bad/deprecated name fails loudly, not as a
  mid-run 404. This was needed: the approved `gemini-2.5-flash`
  returned 404 "no longer available to new users", so I switched to
  `gemini-3.6-flash` (current stable, resolves + returns real output).
  **This was a model change from what was approved** — surfaced and
  chosen per the "prefer stable, prefer better model" instruction;
  cost is moot on the free-tier key.
- **Model added to the cache key and to provenance.** Cache key is now
  `(paper_id, model, prompt_hash)`; `PaperExtractionRow.model` column +
  `extraction_id` = `<paper_id>#<model>#<prompt_hash>`. Migration 005.
  Fixes the silent-cross-model-serving correctness bug.
- **429 handling:** transient rate limits retried with exponential
  backoff (8 retries, to 64s), counted separately from failures.
- **Provenance echo bug found + fixed mid-smoke:** the model echoed the
  prompt's example `extractor`/`extracted_at` values. The orchestrator
  now overrides both authoritatively instead of `setdefault`.

### Stratified composition (30 papers)

| on_domain | count | | signal | count |
|:----------|------:|-|:-------|------:|
| on-domain | 20 | | compound_claims=yes (hand) | 21 |
| borderline | 7 | | limitation_scope=prior (hand) | 17 |
| off-domain | 3 | | limitation_scope=own (hand) | 8 |
|  |  | | limitation_scope=both (hand) | 3 |

Smoke = #14 Chainpoll, #15 BIG-Bench, #38 FermiEval — all on/borderline
with compound claims + both scope types, to exercise the splitter and
`source_scope` on the first three papers.

### Measured results

| Metric | Value |
|:-------|:------|
| Papers succeeded | **30 / 30** |
| Hard failures | 0 |
| JSON valid on 1st attempt | **30 / 30 (100%)** |
| Retry rate (parse/validation) | 0 |
| Rate-limit (429) hits | 8 total across runs — **all absorbed by backoff, 0 became failures** |
| Compound-splitter fire rate | **0 / 30** — see note below |
| `source_scope` agreement vs hand labels | **22 / 30 (73%)** |
| Claims / paper | mean 5.9, median 5, range 2–13 |
| Limitations / paper | mean 1.3, median 1, range 0–4 |
| Future-work / paper | mean 0.2 — **25 / 30 had zero** |
| `confidence` field | **~all 1.0** (29/30 papers every claim 1.0) — no signal |
| Tokens (all runs incl. re-runs) | 22,343 in + 24,857 out = 47,200 |
| Per-paper | ~1,400 in / ~1,550 out |
| Reference cost | ~$0.16 clean 30-paper / ~$0.22 incl. network-interruption re-runs (free tier — **not billed**) |
| vs. $0.10 estimate | ~2× — output tokens ~1,550/paper vs. estimated 1,000; model is more verbose |

### Interpreting the surprises

- **Compound-splitter fired 0 times, but that is NOT under-splitting.**
  Gemini 3.6 Flash *pre-atomizes* — it emits "performance and
  calibration both improve" as two separate claims itself, so the
  splitter (which only handles enumerations/semicolons, and would
  indeed miss bare "X and Y" conjunctions) has nothing left to do. The
  splitter stays as a safety net for weaker models. My 58.9%
  compound-abstract prediction was about the source text; the model
  normalizes it away at generation time.
- **`source_scope` 73%** — disagreements cluster on the model
  UNDER-extracting `this_work` limitations (it reliably catches
  prior-work motivation, misses the paper's own mild self-critiques).
  One "disagreement" was the model being *right* (`W4414620308`, where
  my hand-label over-read the abstract). Addressed in prompt proposal
  change #4.
- **`confidence` all 1.0** — the field is dead as written; prompt
  proposal change #2 fixes it.
- **Future-work 25/30 zero** — corpus property, not a prompt bug;
  confirms the OA-full-text prerequisite from the schema pressure-test.

### Artifacts

- `scratch/extraction_spotcheck.md` — **the thing to read**: 5 papers,
  full abstract vs. every extracted claim/limitation/future-work, incl.
  one (#4) I flagged as questionable that turned out to be the
  extractor being right.
- `data/live_samples/extraction_run_*.json` — per-paper token/latency/
  attempt accounting.
- `docs/prompt-v1.1.0-proposal.md` — proposed prompt fixes with the
  specific v1.0.0 behaviour each one addresses. **NOT applied** —
  applying it invalidates the 30-paper cache, so it needs approval
  and should land before Phase 3, not after.

### Price-table source note (per the correction)

`models.list` returns no pricing. The figures I gave last turn came
from a `WebFetch` summary of `ai.google.dev/gemini-api/docs/pricing`.
The 2.5-Flash and 2.5-Flash-Lite rows there match Google's documented
public pricing. The newer-model rows (3.x Flash) came from the same
fetch but I could NOT independently confirm them against a second
source — treat the `gemini-3.6-flash` $1.50/$7.50 figure as
unverified. It does not affect this run: the key is free-tier with no
card, so nothing was billed regardless. All dollar figures in this
section are labelled "reference only".

## Structural holes: k-artifact check + LLM-confirm — 2026-07-30 — STOP

Two checks on the semantic structural-hole matcher.

**1. Flat-in-N was a fixed-k artifact (CORRECTED).** With fixed k=8, cluster
pairs cap at k(k-1)/2=28 regardless of N, so flat yield was by construction
(and ~12 was hitting the output cap). Uncapped sweep with k∝N
(`structural_k_sweep.py`): yield RISES with N — k=N/10 gives 2.8→19.2 over
N=40→100, tracking cluster-pairs; even fixed-k=8 rises 9.6→14 uncapped.
**docs/findings/corpus-scaling-study.md corrected**: structural-hole yield
is size-DEPENDENT, not independent. Made k + output-cap parameters on the
scorer (default k=8 kept).

**2. LLM-confirmed the 12 leads** (dry-run $0.022 < $0.25 gate; batch,
classification only). Verdicts: **2 substantive**, 3 trivial (larger-eval /
apply-to-dataset), 7 not-addressing (topical adjacency). So the semantic
shortlist has ~1-in-6 substantive precision; confirmation is essential.
Survivors: multi-component hallucination metric vs "semantic entropy
doesn't guarantee factuality"; SelfCheckGPT vs "API-only models can't be
evaluated with self-familiarity". Review section rewritten with
confirmed/rejected status per lead. 213 tests green.

## Structural-hole matcher fixed (semantic) — 2026-07-30 — STOP

Free, no API calls. The scaling study flagged structural holes as
method-limited (token-overlap fired 0 at every N). Replaced the
token-overlap proxy with **claim-embedding cosine**: a cluster-A
method-type claim matched to the claims of a cluster-B paper that carries
an own-work limitation (open-problem gate), clusters weakly citation-
bridged. Limitations are NOT separately embedded (would be a paid call);
B's area is represented by its claim embeddings, limitation text in the
evidence trail. Semantic shortlist, not LLM-confirmed.

- **Result: 0 → ~10 leads at every N** (scaling re-run: 9.4/7.8/11/9.6/12
  across N=40..113; slope 0.24 ≈ flat). Token overlap WAS the bottleneck —
  the signal exists (plausible leads, e.g. a hallucination method matched
  to SelfCheckGPT's 238-passage eval limitation) but is size-INDEPENDENT:
  more papers don't add leads, the matcher did.
- Fixed a k-means order-sensitivity (sort paper ids) so the curve is stable.
- 12 leads added to `scratch/opportunities_review.md` (dedicated section,
  all flagged semantic-lead-not-finding). Full 4-scorer scaling finding
  updated: `docs/findings/corpus-scaling-study.md`.
- 213 tests green (+2 structural-hole fixtures). Next lever (documented,
  not done): an LLM confirm step over the ~10 leads to separate leads from
  findings — bounded cost, corpus-size-independent.

## Corpus corrected + Phase 4 re-scored — 2026-07-29 — HARD STOP

Five fixes from the investigation, in order. Only step 4 spent (dry-run
gated $1). True final corpus **113 unique papers** (was 200).

- **1. Dedup at root**: `build_expanded_manifest.py` now uses the full
  4-pass `deduplicate()` with author data (pass #4 arXiv-DOI-aware).
  `finalize_corpus.py` applied it to the live corpus + filtered every
  downstream store (no orphaned refs). **2 duplicate pairs collapsed**
  (the hallucination survey preprint/published; a clinical-safety
  medRxiv/npj pair) — this is why #1 and #11 were the same contradiction.
- **2. Rubric default fixed**: removed the `arxiv`-in-allowlist auto-include;
  changed no-signal default from borderline→**exclude**; added a
  STRONG_TOPIC set so foundational pre-LLM calibration/selective-prediction
  work is kept without an LLM anchor. **89→85 excluded** (relabel);
  #14 (Least Ambiguous Set-Valued Classifiers) confirmed IN. ~4 legit
  calibration classics recovered by the strong-topic terms.
- **3. Same-construct gate**: config `reason_gated_categories`; overloaded
  categories (computational-cost) split by sub-construct
  (evaluation/training/inference/sampling/memory) before clustering. The
  5-paper computational-cost "agreement" (really ≥4 bottlenecks) no longer
  fires.
- **4. Regime-aware contradiction re-run** (cheap partial, $0.51 < $1 gate):
  v1.1 pair prompt feeds sibling claims as regime context; NO schema field,
  NO re-extract. Result: **0 contradictions** (was 2) — the temperature/
  hallucination pair was a regime artifact, now correctly "none". Claim.
  condition schema field documented as backlog (~$5.40) in docs.
- **5. Re-scored**: persistent_limitations **1**, contradictions **0**,
  orphaned_future_work **63** (all weak/corpus-relative), structural_holes
  **0**, disjoint OFF. Fresh `scratch/opportunities_review.md` (15/15 top
  flagged weak). The strongest prior signal was a false positive; the
  corrected engine finds almost nothing solid — the honest truth of a
  113-paper corpus.
- 211 tests green. HARD STOP — re-scored output is Raj's to judge.

## Phase 4 reasoning engine — 2026-07-26 — HARD STOP for Raj's judgement

Deterministic Python only; no LLM in scoring (audited: no `generate()`,
no `Claim.confidence` read). Five scorers, each pure
`(ReasoningCorpus)->list[Opportunity]`, traced to opportunity-criteria.md
with deviations flagged (not invented). Design: `docs/reasoning-engine.md`.

- **Yield (honest, thin by design)**: persistent_limitations 5,
  unresolved_contradictions 2, orphaned_future_work 108 (each weak/corpus-
  relative), structural_holes 2 (coarse token proxy), disjoint_bridging 0
  (OFF by default, under-specified in the doc).
- **Mixed-fidelity correction** implemented (`fidelity.py`, abstract
  up-weighted 3x dampened inverse-propensity, config). Reported both ways;
  a NO-OP on the current qualifying set because all 5 categories reaching
  the 3-paper floor are 100% full-text — the bias made visible (abstract
  papers yield 15/254 own-work lims, never reach the floor).
- **Independence** (first-author collapse) uses OpenAlex authors (free,
  fetched+cached, 200/200). **Ranking** = score×confidence (trust-weighted);
  top item is the genuine temperature↔hallucination contradiction.
- Traceability flags: diversity/time-span boosters and "absence of
  resolution" are NOT in the criteria doc (resolution unverifiable — no
  limitation-resolution relation); stated, not faked.
- Output: `scratch/opportunities_review.md` (top 15, 12 flagged weak),
  `data/reasoning/opportunities.jsonl`. 211 tests green (+11 scorer fixtures).
- **HARD STOP** (autonomy policy c): Raj judges the ranked output before
  Phase 5/6. Not tuned against the seed corpus.

## Two-stage future-work matcher + citation prior — 2026-07-26 — STOP

Fixed future-work matching architecturally (not by threshold). Phase 4
NOT started.

- **Two-stage matcher** (`future_work_llm.py`, `run_futurework_match.py`):
  cosine shortlist (0.70, recall-first) → LLM classifies each (FW, later-
  paper) pair addressed/partial/not_addressed + justification + addressing
  element. Classification only; persisted as `FutureWorkAddressal` rows
  (Pydantic + table + migration 008, drift-tested) with full provenance,
  same as ClaimRelationship. Dry-run gated LLM spend at $1 (corrected
  pricing): 491 candidates, projected $0.85, actual ~$0.85.
- **Re-measured on the same 40 hand labels**: raw cosine 0.74 → P=0.41
  R=0.70 F1=0.52; **two-stage (addressed+partial) → P=0.64 R=0.90 F1=0.75**.
  Genuinely fixes the signal (precision AND recall rise), not just moves
  noise. addressed+partial preferred (recall 0.90 = few false orphans).
- **Citation prior** (deterministic, free): `cites_source` recorded per
  candidate from the 343 citation edges; never LLM-weighted. HONEST result:
  **0 of the 40 labelled pairs carry a citation edge** (50/491 corpus-wide),
  so improvement is UNMEASURABLE on this set — recorded, not claimed.
- **New distribution (n=312)**: addressed 26 / partial 34 / unaddressed
  134 (43%) / indeterminate 118 (38%). Corpus-relative caveat retained.
- **Paraphrase test** (task 4, <$0.01, embeddings only): 9/10 reworded
  planted contradictions still clear 0.78 vs source ⇒ shortlist likely not
  the contradiction bottleneck. Number reported; nothing proposed.
- 200 tests green (+5). LLM boundary, corrected thinking-token pricing,
  model-in-key, prompt hashing, input_source provenance, v1.1.0 prompt all
  kept. No model switch.

## Pin FW threshold + correct probe scope — 2026-07-26 — STOP

Two measurement tasks before Phase 4. Phase 4 NOT started.

**1. Future-work match threshold pinned by measurement (0.80 → 0.74).**
Hand-labelled 40 items in the sensitive [0.70,0.80) band (in-session, no
LLM spend): does a later corpus paper actually address the item? P/R vs
labels — 0.74 is the F1 optimum (P=0.41, R=0.70) and favours recall (a
missed match = a FALSE orphan, the costly error). The old 0.80 called 0/40
band items addressed though 10 (25%) genuinely were — it manufactured
orphans. **Honest finding: precision peaks at ~0.57 at ANY threshold —
future-work↔claim cosine is a weak signal; the orphan scorer inherits the
noise.** New distribution at 0.74 + guard(K=5,T=0.65): addressed 82,
unaddressed 113 (36%), indeterminate 117 (37%). K/T NOT independently
pinnable from this labelled set (they govern a corpus-counterfactual, not
match correctness) — stated, not guessed. Worksheet:
`scratch/futurework_audit.md`. Docs: `docs/relationship-layer.md`.

**2. Probe scope corrected in docs.** The recall probe (10/10, 0 FP)
validates the CLASSIFIER given a shortlisted pair — it does NOT validate
the SHORTLIST. Planted contradictions were built by negating source claims,
so their 0.84–1.0 cosine is a construction artifact, not evidence real
cross-paper contradictions clear 0.78. Recorded "shortlist recall on
naturally-worded contradictions is UNMEASURED" as a known limitation, and
proposed (did not run) a <$0.01 paraphrase test to measure it.

- 195 tests green. LLM boundary intact; thinking-token pricing, model-in-key,
  prompt hashing, input_source provenance, v1.1.0 prompt all kept. No model switch.

## Pre-Phase-4 measurement (cost / recall / orphan guard) — 2026-07-26 — STOP

Three measurement tasks before Phase 4. Phase 4 NOT started.

**0. Cost reconciliation.** Console ~$7 vs tracked $4.16. Cause found:
**uncounted thinking tokens.** gemini-3.6-flash bills `thoughtsTokenCount`
at the output rate; accounting counted only `candidatesTokenCount`. Rates
themselves are CORRECT ($1.50/$7.50, batch 50% off — verified 2 sources +
reconciliation). Corrected cumulative **~$6.9 ≈ console $7** (thinking
adds ~$2.6; contradiction batch had 139k thinking vs 17k output). No
mystery billing — gap fully explained; pre-billing free-tier runs were
genuinely $0. New `extraction/pricing.py` (single source of truth,
`billed_output_tokens` = candidates + thoughts); dry-run OUT estimates
corrected (contradiction 40→380/pair). **Every gate was ~1.7x too loose;
now fixed. Remaining budget: ~$3 of $10.**

**1. Contradiction recall — classifier is NOT biased.** 24-pair labelled
probe (10 planted contradictions by flipping direction/magnitude/negation
+ genuine supports + unrelated controls) through the existing classifier:
**recall 10/10 (100%), FP 0/14 (0%)**, supports 7/7, unrelated 7/7.
Planted contradictions cosine 0.84–1.0 (0/10 below the 0.78 shortlist).
⇒ The 148:2 supports:contradicts ratio is a **true corpus property**, not
bias. **No prompt v1.1 and no threshold change warranted** (0.74 would
cost $3.04, over gate + budget, adding only support/none pairs). Residual
limitation noted: probe tests lexically-similar contradictions; very
differently-worded cross-paper contradictions could sit below 0.78.

**2. Small-corpus guard recalibrated.** Old guard (any later papers ≥10)
gave a non-credible 91% orphan rate. New criterion: orphaned only if ≥
`min_near_later` (5) later papers are TOPICALLY NEAR (claim cosine ≥ 0.65)
and none matched — else indeterminate. New distribution: **13 addressed /
177 unaddressed (57%) / 122 indeterminate (39%)**. **~39% of future-work
items cannot support an orphan judgment at all** at n=200 (was 5%).
Documented in `docs/relationship-layer.md`: orphan claims are
corpus-relative, always reported with the coverage caveat; Phase 4 must
treat indeterminate as unscoreable. K/T tunable.

- 195 tests green (+9). LLM boundary intact (classification only). No
  model switch.

## Phase 3 relationship layer — 2026-07-25 — STOP for review

Deterministic cross-paper relationship layer over the 200-paper corpus.
LLM perceives single pairs; all numbers are code. Design +
calibration: `docs/relationship-layer.md`.

- **Schema**: added provenance to ClaimRelationship (both paper ids,
  detector_model, prompt_hash, similarity) + ClaimEmbedding model/table
  (records input_source); migration 007. Pydantic fields == ORM columns
  == DDL, enforced by a drift test.
- **Storage**: file-backed (`data/relationships/`), serialized from the
  models; numpy cosine. Scale-dependent choice (Postgres ~Phase 6 / tens
  of thousands of claims). DATABASE_URL path kept + tested on SQLite.
- **Embeddings**: `gemini-embedding-001` (768-dim), behind an interface
  with a deterministic mock. 1022 claims + 312 future-work embedded.
- **Shortlist**: cosine, threshold 0.78 (calibrated) + cap 10/claim,
  cross-paper. 522k naive pairs → **437 candidates**. Config-driven.
- **Contradiction**: LLM classifies each pair (batch, 50% off); weight =
  similarity × input-source fidelity (deterministic, no confidence).
  **150 relationships: 148 supports + 2 contradicts** (287 none). The 2
  contradictions are genuine (decoding-temperature vs hallucination).
- **Citation graph**: 343 intra-corpus edges from OpenAlex
  referenced_works (free).
- **Future-work**: 312 items → 13 addressed, 284 unaddressed, **15
  indeterminate_small_corpus** (refused to call orphaned when too few
  later papers exist).
- **Dry-run gate $3**: projected $0.20; actual **$0.157** contradiction +
  ~$0.008 embeddings. Batch collection re-verified (437/437); resumable
  batch state added after a mid-run crash (float32 cosine >1.0 clamp fix)
  let the completed batch be reused with no re-pay.
- 191 tests green (+25). Phase 4 (reasoning engine) NOT started — Raj
  reviews the relationships first.

## OA full-text recovery 19% → 54.5% — 2026-07-25 — STOP for review

The snowball expansion collapsed full-text coverage to 19% (38/200),
leaving the full-text-dependent scorers effectively on n=38. Recovered
non-arXiv OA full text to lift it.

- **OA retrieval** (`ingestion/oa_fulltext.py`): Unpaywall primary
  (`api.unpaywall.org/v2/{doi}?email=`; take first `oa_locations` PDF,
  pypdf-extract) + Europe PMC secondary (search `DOI:` → PMCID → `/{PMCID}/
  fullTextXML`, JATS <body> text, refs dropped). Both interfaces verified
  live, not assumed. Refactored `fetch_pdf_text` → generic
  `fetch_pdf_text_from_url`. Free.
- **Recovery** (`corpus/recover_oa_fulltext.py`): 162 abstract-only
  papers attempted, **71 recovered** (63 Unpaywall, 8 Europe PMC).
  Full text **38 → 109 (19% → 54.5%)**; 91 still abstract_only (kept
  flagged). Full-text source: arXiv 38, Unpaywall 63, Europe PMC 8.
  Manifest hash `44981e91c40dfe6d`.
- **Re-extraction**: dry-run $2.52 < $6 gate, 129 HITS pre-verified,
  actual **$1.78** (71-batch, collection re-verified 71/71). The earlier
  hard-fail `W4416154989` resolved — Europe PMC full text → valid JSON.
  **Corpus now 200/200 extracted.**
- **Mixed-fidelity severity** re-assessed in `docs/opportunity-criteria.md`:
  severe at 19% (n=38), moderate at 54.5% (n=109); correction still
  required (45.5% abstract-only > 30% baseline).
- **Cumulative paid spend ~$3.99 — has crossed the $3 cap figure**;
  flagged for Raj to confirm billing cap. 166 tests green. Phase 3 NOT
  started.

## Corpus expanded 34 → 200 via snowball — 2026-07-25 — STOP for review

Reason: 34 papers too small for the size-dependent Phase-3 scorers. Added
the "Small-corpus false positives" failure mode to
`docs/opportunity-criteria.md` (orphaned-future-work unfalsifiable, and
structural-hole/bridging undefined, below clustering size).

- **Snowball** (`snowball.py`): bounded citation walk from 26 core seeds,
  both directions, depth 2, soft AI gate + LLM-anchor rescue, heuristic
  labelling. 494 traversed → 166 kept (53% yield), trimmed to hit 200
  total. 39 OpenAlex credits, **$0**. Handled failure modes #4 (hub-seed
  dominance: one survey gave 89% of corpus → capped to 21%), #6 (23/26
  seeds have 0 refs in OpenAlex; only 10/26 seeds contribute directly;
  hop-2 fills target), #3 (labeller field-denylist hard-dropping
  mis-tagged on-domain papers → added title-level rescue; on-domain
  64→86).
- **Composition**: 200 papers (109 core, 91 peripheral; 34 original + 166
  snowball). Manifest hash `3e8e67d1907fd2ec`.
- **⚠️ Full-text coverage 82% → 19%** (38/200): snowball reached
  journal literature (Nature/Springer/Elsevier), low arXiv overlap
  (156/166 no arXiv preprint). Size-dependent scorers benefit regardless;
  full-text-dependent scorers (persistent-limitations,
  orphaned-future-work) now draw from only 38 full-text papers. Non-arXiv
  OA retrieval (Unpaywall/Europe PMC) not built — flagged for Raj.
- **Extraction**: BATCH, 199 HITS pre-verified, dry-run $1.75 < $6 gate,
  actual **$1.18** (167-batch). 199/200 cached; 1 permanent hard-fail
  (`W4416154989`, bare-array output both attempts). Fixed a collect crash
  (non-object JSON now a hard-fail, not a crash). Batch collection
  re-verified: 167/167 and 1/1 count-guards passed.
- **Audit sample**: `data/live_samples/snowball_audit_sample.md` (15
  papers) — the only human-review artifact. Known residual false positive
  flagged (ARC benchmark labelled core).
- **Cumulative paid spend ~$2.21.** New tooling: `snowball.py`,
  `domain_corpus.py`, `build_expanded_manifest.py`, `build_audit_sample.py`,
  `run_batch_corpus.py`. Report: `CORPUS_REPORT.md`. Phase 3 NOT started.

## Domain corpus built at full text — 2026-07-25 — STOP for review

Acting on the finding: full text required for the two discussion-section
scorers. Built the full labelled **domain corpus at full text**. Phase 3
NOT started — awaiting review of spend + composition.

- **Finding promoted** to `docs/findings/fulltext-vs-abstract-finding.md`
  (citable: paired n=21, 11.5× own-work limits, 12.6× future-work,
  prior-work flat as negative control, lower-bound framing).
- **Batch bug flagged** in `docs/batch-and-caching.md`: batch has run
  twice now; the `BATCH_STATE` vs `JOB_STATE` status-string bug is
  documented; per-run collect-verification (results == submitted) made
  mandatory. Re-verified on this run: 7/7 returned inline.
- **Corpus: 34 papers** (26 core on-domain + 8 peripheral borderline,
  tagged `domain_centrality`; borderline KEPT). 26 excluded (25
  off-domain + 1 hard-excluded), all recorded with reasons in the
  manifest. This is the entire labelled domain set, not a sample.
- **Full text 27/34 (79.4%)**; 7 abstract-only flagged `abstract_only=
  true` (all `no-arxiv-id`). Retrieval recovered 6 new full texts (21→27).
- **New tooling**: `domain_corpus.py` (selector + centrality),
  `build_corpus_manifest.py` (retrieve + manifest + hash),
  `run_batch_corpus.py` (`--dry-run`/`--submit`/`--collect`, per-paper
  input_source, count-guard).
- **Dry-run gate ($5)**: projected $0.2588, 27 prior extractions
  confirmed as HITS before any paid call. Actual batch spend **$0.1999**
  (7 calls, 195,868 in / 14,123 out). Post-run: **34/34 cached, $0
  remaining**. Manifest hash `e1edaeba3092d1cb`.
- **Cumulative paid extraction spend ~$1.03** of the $3 cap.
- Full report: `CORPUS_REPORT.md`. 161 tests green. No model switch;
  pacing/retry/provenance machinery intact.

## Abstract-vs-fulltext comparison COMPLETE — 2026-07-25 — paid tier

The quota wall (below) is resolved: paid billing (>$3 account cap) let
both v1.1.0 arms finish on `gemini-3.6-flash` (temp 0), keeping full
comparability with the v1.0.0 baseline. **No model switch.**

### Run

- **Arm 2 — v1.1.0 abstracts, standard tier**: 30/30 (9 cache HITS +
  21 fresh), 0 hard-fails, 0 retries of any kind, 0 daily-quota hits.
  34,434 in + 23,176 out tokens → **$0.2255**. Effective 3.1 RPM (8 cap).
- **Arm 3 — v1.1.0 full text, BATCH API (50% off)**: 21/21 cached,
  0 hard-fails. Batch SUCCEEDED in ~93 s, results inline. 573,050 in +
  46,592 out tokens → **$0.6045**. Cached under the sync
  `gemini:gemini-3.6-flash` identity (batch = same model, delivery only)
  so the paired comparison finds it.
- **Total spend $0.83** — under the $1.16 pre-spend dry-run projection
  and the $1.50 gate. Dry-run over-estimated input (661k vs 573k actual;
  safe direction). Mandatory dry-run confirmed the 9 cached abstracts as
  HITS before any paid call.
- Bug caught pre-collect: live API reports `BATCH_STATE_*`, not
  `JOB_STATE_*`; terminal-state check fixed to match on suffix. 79/79
  extraction tests green.

### Result — VERDICT (see `docs/abstract-vs-fulltext.md`)

Paired, n=21, single variable = input source:

| per paper | abstract | full text | ratio |
|:--|--:|--:|--:|
| **own-work limitations** | **0.19** | **2.19** | **11.5×** |
| **future-work items** | **0.14** | **1.76** | **12.6×** |
| prior-work limitations | 1.10 | 1.43 | 1.3× |
| claims | 4.10 | 6.10 | 1.5× |

**Full text lifts the two starved scorers (persistent-limitations,
orphaned-future-work) an order of magnitude — from non-viable on
abstracts to viable.** Lift is concentrated exactly on own-paper-scoped
signals (authors put limitations/future work in discussion sections,
which only full text contains); prior-work limitations, already captured
from abstracts, barely moved. Conservative finding: `gemini-3.6-flash`
is a small model that *under*-exploits long context, biasing the test
AGAINST full text — it wins anyway. **Phase 3/4 scoring of these two gap
types must use full-text extractions.** New tooling:
`run_batch_fulltext.py`, `dryrun_cost.py`, `compare_abstract_fulltext.py`.
Phase 3 NOT started (per instruction).

## v1.1.0 prompt + Phase 1.5 full text — 2026-07-23 — PARTIAL (quota wall)

### Done and committed

- **Prompt v1.1.0** applied (per approval + the 2 adjustments): dropped
  echoed provenance fields; stop extracting promotional claims as
  findings; tightened `this_work` `source_scope` detection; confidence
  left as faithfulness-only (NO signal attempt).
- **Confidence policy** (`docs/confidence-policy.md`): demoted to a
  pre-scoring filter hook, NEVER a scoring input; noted in CLAUDE.md.
- **Compound-splitter note** (`docs/compound-splitter-note.md`): 0/30
  fire rate is model-specific; re-measure on model change; splitter
  stays as safety net; known bare-conjunction gap documented.
- **`input_source` provenance**: added to cache key, `extraction_id`,
  `PaperExtractionRow` (migration 006) so abstract and fulltext runs
  never collide. Same lesson as model-in-key.
- **Phase 1.5 arXiv full-text pipeline** (`ingestion/fulltext.py`):
  arXiv-id resolution, PDF fetch + pypdf text extraction, section-aware
  chunker (dormant on this corpus — max paper 99k tokens), abstract_only
  flagging. 129 tests passing (+13 this session).
- **Full text retrieved: 21/30 (70%)**, 9 abstract_only (all
  journal-only). Manifest: `data/live_samples/fulltext_manifest.json`.
- **Runner extended** with `--input-source fulltext` (loads cached
  arXiv text, skips abstract_only papers).

### BLOCKED — Gemini free-tier daily quota exhausted

Both remaining extraction steps are walled on the `gemini-3.6-flash`
**daily** free-tier request quota (`quotaId:
GenerateRequestsPerDayPerProjectPerModel-FreeTier`), spent by today's
runs. **Confirmed via a QuotaFailure response, not inferred.**

State at the wall:
- v1.1.0 **abstract** re-extraction: **8/30 complete** (cached).
- v1.1.0 **fulltext** extraction: **0/21**.

Consequences:
- The **v1.0.0-vs-v1.1.0 metrics diff** (task 1) cannot be reported yet
  — only 8/30 v1.1.0 abstracts exist. I will NOT compute a 30-paper
  comparison from 8 papers.
- The **abstract-vs-fulltext comparison** (`docs/abstract-vs-fulltext.md`,
  task 4) is scaffolded (methodology + coverage final) with the numeric
  table marked PENDING.

**Nothing is lost** — everything is cached and idempotent. Resume with
two commands once quota resets (~daily) or with a higher-quota key:
```
python -m backend.app.corpus.run_live_extraction                      # finish v1.1.0 abstracts
python -m backend.app.corpus.run_live_extraction --input-source fulltext  # v1.1.0 fulltext
```
Alternative: approve a different free model (e.g. `gemini-2.5-flash-lite`,
separate daily quota) via `GEMINI_MODEL` — caveat in the comparison doc
(breaks comparability with the v1.0.0 baseline; abstract-vs-fulltext
stays internally valid if both sides share the model).

## Resume attempt — 2026-07-24 — free-tier daily quota is a hard wall

Quota "reset" gave only a tiny budget: after the reset I got ~1–2
successful extractions before re-hitting the SAME per-day wall
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, gemini-3.6-flash).
Probed repeatedly — the `retryDelay` bounces (31s→18s→6s→53s) and never
clears, confirming a hard **daily** cap, not a short throttle. The
free-tier daily allowance for this premium model is small (single- to
low-double-digit requests/day).

State: v1.1.0 abstract **9/30** cached; fulltext **0/21**. The
comparison needs ~**42 more synchronous calls** (21 abstract + 21
fulltext). At a handful/day that is roughly a **week** of daily
grinding — not viable interactively.

**Clean resolution that preserves comparability: a paid-tier key for
`gemini-3.6-flash`.** Same model → the v1.0.0 baseline and both
comparison arms stay directly comparable; paid tier removes the daily
cap (only generous per-minute limits remain). A 42-call comparison then
finishes in minutes. This is the recommended unblock; I did not switch
models or tiers autonomously.

### Productive work done despite the wall (committed)

- **429 handling fixed (real bug):** the client honored only the
  `Retry-After` header, which Gemini doesn't send, so it did blind
  exponential backoff wasting minutes per rate-limited call. Now parses
  Google's `RetryInfo.retryDelay` from the 429 body and waits exactly
  that. (Doesn't rescue a daily-cap exhaustion — nothing does but a
  higher quota — but makes per-minute throttling efficient.)
- **Batch mode wired + tested** (`GeminiBatchClient`) for the 200-paper
  run: submit/poll/collect, 20MB chunking, distinct
  `gemini-batch:` provenance. Not executed (its own approval). Never
  used for the comparison. See `docs/batch-and-caching.md`.
- **Context caching decision documented:** explicit caching declined
  (shared prefix ~1,500 tok is below the 2,048–4,096 min; per-paper
  bodies unique). Implicit caching already on for 3.6-flash.
- **Free-vs-paid throughput** for the 200-paper corpus (from measured
  ~40 successful calls/day free-tier ceiling):
  - Free tier: ~5 days per pass; ~8–9 days for the full abstract+
    fulltext experiment.
  - Paid tier: an afternoon (batch mode halves the cost on top).

### Resume recipe (with a paid/higher-quota key)

```
python -m backend.app.corpus.run_live_extraction                          # finish v1.1.0 abstracts (9 cached)
python -m backend.app.corpus.run_live_extraction --input-source fulltext   # v1.1.0 fulltext, 21 papers
python -m backend.app.corpus.compare_abstract_fulltext                     # fills the paired table
```
Everything is cached and idempotent; no work is redone.

## Model switch to gemini-3-flash-preview — 2026-07-24 — quota VERIFIED SMALL

Switched `GEMINI_MODEL` from `gemini-3.6-flash` to
`gemini-3-flash-preview` (the closest real name to "gemini-3-flash";
the bare name 404s). Confirmed it resolves in models.list and returns
200. Re-running all three comparison arms on ONE model for internal
comparability.

**Earlier 3.6-flash extractions are RETAINED but SUPERSEDED.** The
30 v1.0.0 + 8 v1.1.0 abstract extractions on `gemini:gemini-3.6-flash`
stay on disk under their own cache keys. Because the model is part of
the cache key / `extraction_id` / `PaperExtractionRow`, nothing
collides with the new `gemini:gemini-3-flash-preview` extractions —
both model families coexist and the comparison reads only the
new-model set.

**Verified free-tier quota (per the instruction not to trust the
~1,500 RPD figure):** the Gemini API returns NO rate-limit headers on
200 responses, so the only ground truth is the 429 `QuotaFailure`.
Measured: `gemini-3-flash-preview` hit
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` after ~22–25
requests today. **Its real free daily allowance on this project is on
the order of ~20–25 requests/day — NOT ~1,500.** Same order as
3.6-flash. The ~1,500 number does not apply to this project/model.

Arm progress today: **arm 1 (v1.0.0 abstracts) got 17/30** on
gemini-3-flash-preview before the daily wall. Arms 2 and 3 not
started.

### Consequence

The three arms need ~81 calls total. At ~20–25/day the experiment is
a **~4-day grind** on free tier, per the measured cap — not
completable in one session on any single model tried (3.6-flash and
3-flash-preview both cap ~20–40/day for this project).

The 5xx-retry + 10 RPM pacing + RetryInfo backoff are all now in place,
so within a day's allowance the run is efficient; the binding limit is
purely the daily request cap.

### Decision needed (not taken autonomously)

1. **Grind over ~4 days** on gemini-3-flash-preview (resume each day;
   cache makes it idempotent). Comparability preserved.
2. **Switch to a lite model** (`gemini-2.5-flash-lite` /
   `gemini-flash-lite-latest`) which typically carries a much higher
   free RPD — but it is a smaller model, a quality trade-off, and a
   second model switch. Would need all three arms re-run on it.
3. Reconsider paid billing (previously declined).

I did not switch to a lite model or grind further autonomously —
option 2 is a quality decision and I've already switched models once
on instruction. Resume recipe (whichever model, once quota allows):
```
python -m backend.app.corpus.run_live_extraction --prompt-version v1.0.0                     # arm 1 (17 cached)
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0                     # arm 2
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0 --input-source fulltext  # arm 3
python -m backend.app.corpus.compare_abstract_fulltext
```

## Free tier settled — 2026-07-24 — every model caps in the low tens/day → we pay

Tested three flash models for the free-tier daily allowance on this
project. All three cap far below what the comparison needs:

| Model | Free daily cap (measured, via QuotaFailure) | Schema adherence |
|:------|:--------------------------------------------|:-----------------|
| gemini-3.6-flash | ~low tens/day | good (0 validation failures in 30) |
| gemini-3-flash-preview | ~20–25/day | good |
| gemini-2.5-flash-lite | **~8–10/day** (walled at RUN 09) | **poor — 3/8 validation failures (enum drift, e.g. `type:"limitation"`)** |

The ~1,500 RPD figure applies to none of them on this project. The
free-tier daily quota is simply very small across the board.
Per the standing rule ("if Flash-Lite walls ~25/day, stop and we
pay"), Flash-Lite walled at ~8–10/day AND has poor schema adherence,
so it is a dead end on both counts.

**Decision: pay.** The comparison (~81 calls, 3 arms) needs a paid
tier to complete in one sitting. Recommended model on paid:
`gemini-3.6-flash` — the original baseline, good schema adherence,
no daily cap on paid (only generous per-minute limits). `.env`
`GEMINI_MODEL` reset to `gemini-3.6-flash` accordingly.

**Bug fix validated in production:** the per-day-quota abort worked
— arm 1 on flash-lite hit the daily wall at RUN 09 and aborted
cleanly with the resume-after-reset message instead of grinding
retries. Measured saving vs the old behavior across recent runs:
**56 wasted calls eliminated** (63 attempted → 7; 9 calls/paper →
abort on call 1), plus it no longer attempts papers after the wall.

Also confirmed from the AI Studio graph: **not RPM-limited** (peak
3 req/min vs the 10 RPM limit) — pacing is fine; the daily cap is
the only binding constraint.

Smoke guard fixed: a single non-systematic smoke failure (e.g. a
small model's occasional enum drift on one paper) no longer halts
the whole arm; the run stops after smoke only if ALL smoke papers
fail (systematic prompt/model/schema breakage).

**State:** partial flash-lite v1.0.0 abstracts (5) cached but
superseded (dead-end model). The gemini-3.6-flash extractions from
2026-07-23 (30 v1.0.0 + 8 v1.1.0 abstracts) remain the best baseline;
on a paid gemini-3.6-flash the three arms complete and
`compare_abstract_fulltext` fills the paired table.

### Resume on paid gemini-3.6-flash
```
python -m backend.app.corpus.run_live_extraction --prompt-version v1.0.0                          # arm 1 (30 cached from 7-23)
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0                          # arm 2 (8 cached)
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0 --input-source fulltext  # arm 3
python -m backend.app.corpus.compare_abstract_fulltext
```

## Client-side rate limiting + robust retry layer — 2026-07-24

Rebuilt `GeminiLLMClient` so an avoidable 429 is never triggered and
every transient failure recovers cleanly (even if slower).

- **Token-bucket RPM limiter** (`rate_limiter.py`): min inter-request
  interval = 60/`GEMINI_MAX_RPM` (default 8, config-driven), measured
  from request START so a slow call consumes the interval (no idle on
  top). ±10% jitter. Thread-safe, single shared instance.
- **Token-aware TPM pacing**: estimates input tokens (chars/4) and
  holds a request if it would push the rolling-60s window over
  `GEMINI_MAX_TPM` (default 200k, under the 250k ceiling). Logs when a
  hold is TPM-bound vs RPM-bound, so we can see which limit binds
  (full text: 15–99k tokens/paper → TPM binds well under RPM).
- **Retry layer classifies before retrying** (one unified 5-attempt
  budget, 120s cap, RetryInfo-honoring backoff + jitter):
  per-day 429 → `DailyQuotaError`, abort (kept, not weakened);
  per-minute/per-token 429 → transient retry (routed to rpm/tpm
  counters); 5xx / timeouts / connection errors → transient retry.
- **Retries unusable 200s too**: a `validate` callback (built by the
  Extractor: JSON parse + Pydantic schema + paper_id match) runs on
  each 200; a `RetryableResponseError` retries within the same budget;
  on exhaustion it raises a typed hard error naming the paper. Never
  persists a partial/malformed extraction. This is the flash-lite
  enum-drift case, now handled uniformly.
- **Resumability**: each success is cached before the next request, so
  a run that dies at paper N resumes at N+1 with zero rework —
  verified by a kill-and-restart test (`test_resumption_from_killed_
  run_does_no_duplicate_work`).
- **Observability**: `stats_summary()` + the runner print total
  requests, successes, retries by category (rpm/tpm/5xx/conn/schema),
  limiter wait time (rpm/tpm holds), daily-quota hits, and effective
  achieved RPM.

**Scope note:** this addresses the **RPM/TPM** limits, which are what
will bind on **paid** tier. It does **NOT** address the **per-day**
free-tier quota wall we measured (~low tens/day across every model) —
that one is solved only by billing. The per-day abort stays intact so
we never waste calls against it.

Preserved unchanged: per-day abort, model-in-cache-key, prompt-version
hashing, input_source provenance, and the v1.0.0/v1.1.0 prompts
(comparison integrity). Tests: 158 passing (+14: limiter interval &
TPM hold under a mocked clock, 429-subtype routing, 5xx retry,
schema-invalid retry-then-hardfail, limiter-invoked, stats summary,
resumption).

## Resume run — 2026-07-25 — arm 1 complete; daily wall hit; arms 2/3 tomorrow

Ran the resume recipe on `gemini-3.6-flash` (free tier). Results:

### Cache-key migration (recovered the 2026-07-23 work)

The 30 v1.0.0 abstract extractions from 2026-07-23 were cached under
the OLD 2-part key (`<model>__<prompthash>`), before `input_source`
joined the cache key. The new 3-part lookup
(`<model>__abstract__<prompthash>`) missed them, so arm 1 began
re-extracting from scratch (21 fresh calls before the daily wall).
`backend/app/extraction/migrate_cache_keys.py` copies every orphaned
2-part file to its 3-part `abstract` name (all 2-part files predate
full-text extraction, so input_source is unambiguously abstract).
Idempotent. Migrated 61 orphaned files.

**After migration: arm 1 (v1.0.0 abstracts) = 30/30, verified as 30
cache hits with 0 API calls.**

### Arm status

| Arm | State |
|:----|:------|
| 1 — v1.0.0 abstracts | **30/30 complete** (21 fresh today + 9 recovered via migration) |
| 2 — v1.1.0 abstracts | **9/30 cached**, 21 remaining |
| 3 — v1.1.0 full text | 0/21 |

### Daily wall + the fix, in production

Today's successful calls before the wall: **21** (arm 1 re-extraction).
Then arm 2 hit the per-day quota and **aborted cleanly on the FIRST
per-day 429** — `requests=1, successes=0, daily_quota_hits=1`, exit
code 4 — i.e. exactly 1 rejected request, no wasteful retries (the
old behavior burned ~20). The split-budget + per-day-abort work is
doing its job. Measured free-tier daily cap for gemini-3.6-flash on
this project: **~21/day**.

Remaining work: 21 (arm 2) + 21 (arm 3) = **42 calls → ~2 more days**
at ~21/day. Resume tomorrow with the same recipe (arm 1 is now all
cache hits; arm 2 resumes at paper 10; nothing is redone):
```
python -m backend.app.corpus.run_live_extraction --prompt-version v1.0.0
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0
python -m backend.app.corpus.run_live_extraction --prompt-version v1.1.0 --input-source fulltext
python -m backend.app.corpus.compare_abstract_fulltext
```

## Non-negotiable: Phase 3/4 blocked until real extractions exist

Written into `CLAUDE.md` as standing policy. Phases 3 (relationship
layer) and 4 (reasoning engine) MUST NOT be built against the mock
path or the seed corpus. Both phases produce scorers whose behaviour
is only meaningful with real inputs; testing them against the seed
corpus's planted contradictions or mock-generated claims would
validate them against their own answer key.

Gate: at least one `PaperExtraction` on disk must have an
`extractor` value that is not `mock-seed`, `seed-fixture`, or
`programmable-mock` before any Phase 3 or 4 file may be started.

## Flagged, not acted on

**"Commit separately" was requested but ResearchMap is not a git
repo.** No `.git` in the project directory. I structured the two
follow-ups as logically-independent change blocks (change A: merge
policy + `merged_from` + order-independence + docs; change B: arXiv-
DOI-aware pass 4) so they'd map cleanly to two commits if you
`git init` here, but I did NOT initialise the repo or make any
commits. Say the word and I'll init + commit both as separate
commits with messages, or you can do it yourself.

Also would want changed but not acting on:

- The `by_id` internal key can differ from `merged.id` after a
  merge where the loser was first-seen. Currently harmless (output
  is `sorted(by_id.values())` and no downstream code reads the
  key), but it's a latent inconsistency I'd rather clean up. Could
  do this by rekeying `by_id[loser_id] → by_id[survivor_id]` at
  merge time; low-risk but worth its own change.
- The seed-corpus JSON files on disk don't carry the new
  `merged_from` field (they were generated before it existed).
  Currently harmless — `Paper.model_validate` fills the default —
  but a stray `seed_generator` re-run would rewrite them all with
  the field explicitly. Not a bug, worth normalising when
  convenient.
- Pass 2 (`same title, same year`) still has no author check — an
  edge case for two truly distinct same-titled papers in the same
  year. Not observed in the wild yet, but worth extending to
  require author overlap for symmetry with pass 3 / pass 4.
