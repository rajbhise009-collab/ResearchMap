# ResearchMap — iteration 2b report

**2026-10-01.** Autonomous run picking up where iteration 2 left off.
Local commits only, nothing pushed. **Zero new paid API spend;
OpenAlex free credits used this run: 0** (all queries went through
the fixture / canned-response client — no live cites-both or
cites-of-source calls fired).

LLM-cal manifest hash **confirmed unchanged**: `44981e91c40dfe6d`.
Final git status: clean under `frontend/public/data`, `data/domains`
and `docs/`. 405 backend tests pass. Static build clean. Node 22
locally; no dependency bumps.

## The title regression — one-line cause

`backend/app/api/multi_library_export.py:210` built a verdict → headline
map (`"genuine": "Two papers report findings that genuinely disagree"`)
and overwrote `consumer.headline` for every pair with the verdict text.
Diagnosis: PA2 (iteration 2 commit `3fd13e3`) added the audit-verdict
display but put it where the per-pair card title belonged.

## Per-part status

| part | status | commit |
|:--|:--|:--|
| P0 preflight | done | — |
| P1 topic-specific titles + fix search-index shape | **done** | `(P1)` |
| P2 copy honesty (coverage note, denominators, footer, privacy) | **done** | `(P2)` |
| P3 headless-Chrome per-library verification | **done** | `(P3)` |
| P4 weekly refresh workflow + module + tests + docs | **done** | `(P4)` |

## Fix summary — Part 1

- New `backend/app/api/contradiction_titles.py` + 8 regression tests.
  Deterministic topic→question mapping (hand-curated for the 7
  diet-audit topic strings; derived-from-text fallback for anything
  else). Titles **never contain** `genuine|genuinely|settled|
  resolved|confirmed` — the module raises if a hand-curated entry
  slips any of those in.
- Verdict is now a separate `consumer.verdict_label` chip rendered
  under the headline. LLM-cal shows no chip because no audit data
  exists for it; diet shows "Checked by hand against the abstracts:
  a real disagreement" / "Set aside: the two papers measure different
  things" / "Set aside: duplicate of another pair".
- Set-aside cards use topic-naming titles ("Set aside (different
  measures): Alcohol and heart attack…").
- Collision resolver appends a distinguishing clause from the audit
  `reason`, never a number.
- Per-gap `document.title` is set to the headline on load so the
  browser tab reads "Red meat and stroke: …" instead of the shared
  app title.
- Headline flows into: the gaps-list card, the detail h1, the
  `GapExport` HowToCite line and `.bib`/`.csv` filenames (via
  `contradictionExplanation`), and now the per-library search
  index.
- **Search index bug found and fixed as a side-effect**: the
  per-library builder in `multi_library_export.py` wrote docs with
  `{wid, title, terms: list}` while the frontend's `search()` reads
  `{type, ref, title, kind, strength, terms: dict}`. That mismatch
  made Quick-Search (⌘K) return zero hits on diet and ml-fairness.
  Replaced with the authoritative `search_index.build_index`;
  `test_cross_library_collisions.py` updated to tokenize queries
  the same way the index does (`fairness` → stem `fairnes`).

## Fix summary — Part 2 (copy honesty)

- Coverage note now reads: "Claims read from N of M papers. We
  stopped reading to stay within budget, so the remaining X papers
  are not reflected in these results."
- Separate `zero_finding_note`: "Zero here means none were found
  among the papers read. It does not mean none exist." — rendered
  only on libraries whose confirmed count is 0 (so Diet is clean,
  ml-fairness + llm-cal show it). Removed the backwards "bounded
  above" wording and the "budget halt" jargon everywhere.
- Stats card gains a labelled "Claims extracted from N of M papers"
  line to disambiguate the denominator next to "Read in full N of M
  papers" — before, 17 and 59 both appeared with denominator 100
  with no label distinction.
- `LIBRARIES_NOTE.intro` describes the real switch mechanism:
  "use the picker at the top of the page or append ?lib=<slug> to
  any URL (?lib= wins over the stored choice)". The fictional
  "/library/<slug>/" copy is gone.
- Footer scope is a client component that reads the active library
  — "Working prototype · currently shown: 100 papers on diet and
  all-cause mortality" when ?lib=diet-and-mortality.
- Privacy line now states explicitly: query is NOT sent anywhere;
  the scrubber for refused/out-of-domain queries exists in the
  code but is **not wired** (would need Vercel Pro for custom
  events).

## Part 3 — headless-Chrome verification

Chrome `--headless=new --dump-dom --screenshot` against the
production build served on 127.0.0.1:8765. **29 / 29 DOM assertions
pass** (one failure found and fixed mid-pass: ml-fairness /gaps
was missing the zero-finding sentence; `GapsPageClient` now
renders both the coverage_note AND the zero_finding_note).

Screenshots in `docs/review/screenshots/*.png` (10 pages — home,
/gaps, /papers, one gap detail, one paper detail, ?dev=1, each
per library where applicable). The verification script is at
`/tmp/.../scratchpad/verify_renders.py` and could be committed as a
regression harness in a follow-up if you want it.

| check group | result |
|:--|:--|
| diet /gaps has 5 distinct topic titles, no verdict words in h3 | PASS |
| diet /gaps shows set-aside count = 2 with topic-naming | PASS |
| diet /gaps shows "Checked by hand" chip; LLM-cal does not | PASS |
| ml-fairness /gaps shows "Zero here means" + "Claims read from 51 of 100" | PASS |
| llm-cal /gaps renders cleanly, no verdict chip, 113-paper footer | PASS |
| diet gap detail: topic h1, chip, BibTeX+CSV buttons, timeline section | PASS |
| diet paper detail: single-entry BibTeX | PASS |
| diet /papers lists real diet papers (not LLM-cal) | PASS |
| Footer scope follows selected library | PASS |
| ?dev=1 does NOT load Vercel analytics | PASS |
| Backwards "bounded above" + "budget halt" copy gone | PASS |
| "/library/<slug>/" copy gone from footer | PASS |

What I did NOT verify in-browser (would need to install playwright
and a GUI session): quick-search ⌘K keyboard flow and localStorage
override by ?lib= (the module code enforces it; the DOM check only
confirms the first-load library matches ?lib=).

## Part 4 — weekly refresh

- `backend/app/refresh/weekly_candidates.py` + 10 tests. Fixture
  mode works offline; live mode fails loudly if the OPENALEX_API_KEY
  secret is empty.
- `.github/workflows/weekly-refresh.yml` — schedule
  (`cron: "0 9 * * 1"`) + workflow_dispatch, minimal
  `issues:write + contents:read` permissions, uploads the JSON
  result as a 30-day run artifact, opens one labelled
  `weekly-refresh` issue per run.
- `docs/weekly-refresh.md` — what it does, what it doesn't do, the
  **60-day inactivity pause** on GitHub Actions scheduled workflows,
  dry-run instructions.
- Local dry-run against `backend/tests/refresh/fixture_sample.json`:
  rendered the expected markdown body with "Flagged DOES NOT mean
  confirmed", credits=5, two sample candidates.

## OpenAlex credits used this run

**0.** Everything went through the FixtureClient. The weekly workflow
will spend real credits — expect roughly 1 per genuine pair + 1 per
orphan-FW item per week, deeply inside the 10k/day free-tier limit.

## Headline numbers (post-rebuild)

| library | papers | claims read | confirmed | zero-note |
|:--|--:|--:|--:|:--|
| llm-calibration | 113 | 113 | 0 contradictions (76 other opps) | yes |
| diet-and-mortality | 100 | 59 | 5 | no |
| ml-fairness | 100 | 51 | 0 | yes |

## Decisions you need to make

1. **Push the 4 new commits** (P1, P2, P3, P4) on top of the 10
   iteration-2 commits still local. Nothing has been pushed.
2. **Set `OPENALEX_API_KEY` as a GitHub Actions secret** before the
   first Monday cron fires. The workflow fails loudly otherwise;
   nothing silently runs with no key.
3. If you want a verification-regression harness in CI, say the
   word and I'll move `verify_renders.py` into `backend/tests/` and
   wire it to a `make verify-prod` style target.
4. (Carried over from iteration 2 — unchanged.) `ollama pull
   llama3.2:3b-instruct-q4_K_M` when you want to run the local-model
   feasibility test; recipe in `docs/local-model-plan.md`.

## Manual steps you must do

- Review the 14 local commits on `main` and push when ready
  (`git log --oneline origin/main..main`).
- Set the OPENALEX_API_KEY repo secret (Settings → Secrets →
  Actions) — needed by the weekly workflow.
- When you recruit diet-contradiction reviewers (packet in
  `docs/review/diet-contradictions/`), run the scorer:
  `python -m backend.app.review.score_responses
    --responses <csv> --key .../answer_key.json`.

## Files worth checking

- `backend/app/api/contradiction_titles.py` — the new deterministic
  title-maker.
- `backend/app/refresh/weekly_candidates.py` — the weekly module.
- `.github/workflows/weekly-refresh.yml` — the scheduled job.
- `docs/review/verification.md` — per-check pass/fail list from the
  headless pass.
- `docs/review/screenshots/*.png` — 10 rendered pages.
- `docs/weekly-refresh.md` — how the workflow is meant to be used.
- `REPORT_iteration2b.md` — this file.
