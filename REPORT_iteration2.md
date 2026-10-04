# ResearchMap — iteration 2 report

**2026-09-30.** Autonomous run. Local commits, not pushed. Zero paid
API calls this run; **OpenAlex free-tier credits used: 6** (5 for
cites-both queries in PB1 + 1 to verify filter syntax live). Legacy
LLM-cal library manifest hash confirmed unchanged
(`44981e91c40dfe6d`).

## Per-part status

| part | status | commit |
|:--|:--|:--|
| P0 preflight | done | (baseline) |
| PA1 Next.js 14.2.15 → 14.2.35 + postcss override | **done** | one commit |
| PA2 contradiction audit verdicts + coverage honesty | **done** | one commit |
| PA3 BibTeX / CSV export + how-to-cite | **done** | one commit |
| PB1 OpenAlex cites-both (5 genuine diet pairs) | **done** | one commit |
| PB2 static SVG timeline per contradiction page | **done** | one commit |
| PC1 privacy-respecting analytics + footer note | **done** | one commit |
| PC2 predictor outcomes doc + fairness-miss diagnostic (no refit) | **done** | one commit |
| PC3 blind expert-review packet + scorer + tests | **done** | one commit |
| PD weekly refresh GitHub Actions workflow | **skipped** — usage limit hit | — |
| PE full headless-Chrome verification per library + screenshots | **compact PE only**; headless-Chrome skipped — usage limit | — |
| PF local-model feasibility | **plan doc only** — 8 GB RAM + ollama installed but no models pulled; plan written per brief | one commit |

## Verdict mapping (PA2) — Diet contradictions

Reproducible key: (a_paper_id, b_paper_id, a_text[:60], b_text[:60])
— NOT index. Order in the raw shortlist:

| # | topic | verdict |
|:--|:--|:--|
| 1 | red meat / stroke | **genuine** |
| 2 | alcohol / MI dose-shape (NEJM 2003 men vs Lancet 2018 IPD) | **artifact** — regime-conflation |
| 3 | alcohol / stroke — is there an association? | **genuine** |
| 4 | alcohol / ischemic stroke dose-shape (J vs linear) | **genuine** |
| 5 | red meat / type 2 diabetes | **genuine** |
| 6 | alcohol / all-cause mortality (BMJ 2011 vs Stockwell 2016) | **genuine** |
| 7 | same paper pair as 6, near-identical restatement | **duplicate** |

**5 genuine + 1 artifact + 1 duplicate.**

## Headline numbers (post-PA2)

| library | papers | claims-read | raw flagged | audited genuine | full-text |
|:--|--:|--:|--:|--:|--:|
| LLM calibration (frozen) | 113 | 113 (100%) | 0 | 0 | 67 |
| Diet & mortality | 100 | 59 (59%) | 7 | **5** | 17 |
| ML fairness | 100 | 51 (51%) | 0 | 0 | 50 |

Coverage note baked into `stats.json` per library. For diet and
fairness the note reads *"Claims read from N of 100 papers. The
remaining M were not extracted (budget halt); their content is not
reflected in the scorer's output. Treat any 'zero' finding as
bounded above, not a clean negative."*

## Predictor table (PC2, DO NOT REFIT)

| library | predictor score | label | genuine | coverage | confound |
|:--|--:|:--|--:|:--|:--|
| llm-calibration | 0.818 | high | 0 | 100% | none |
| diet-and-mortality | 0.440 | moderate | 5 | 59% | partial extraction; hand-audit not expert review |
| ml-fairness | 0.667 | high | 0 | 51% | partial + scorer-mismatch hypothesis (definitional not empirical disagreement), untested [wording corrected 2026-10-04] |

Free fairness-miss diagnostic: found 6 impossibility/incompatibility
papers in the fairness corpus (Kleinberg-Mullainathan-Raghavan 2016,
Berk 2018, Friedler 2016 "(im)possibility", Corbett-Davies 2017,
Menon-Williamson 2018, Chouldechova/Roth 2018). Pairs involving them:
0 marked `contradicts`, 1 `supports` ("state the same impossibility
theorem"), 3 `none` ("distinct impossibility theorems involving
DIFFERENT combinations of fairness criteria"). Reading: the classifier
is behaving correctly for its prompt — two impossibility theorems
about different metric combinations aren't logically contradictory.
Hypothesis (not proven): the scorer's built-in notion of disagreement
is empirical-claim vs empirical-claim; fairness's famous
disagreements are definitional. Full write-up in
`docs/findings/domain-coherence-predictor.md`.

## Cites-both (PB1)

5 OpenAlex `filter=cites:A,cites:B` queries, 1 credit each. Results
baked at build time into each genuine gap card's `cites_both` block.

| pair | total cites both | top-N shown |
|:--|--:|--:|
| red meat / stroke | 47 | 10 |
| alcohol / stroke — presence | 147 | 10 |
| alcohol / ischemic stroke dose-shape | 22 | 10 |
| red meat / T2D | 11 | 10 |
| alcohol / mortality J-shape vs null | 106 | 10 |

UI copy: *"These papers cite BOTH of the two disagreeing papers —
that means they discuss the disagreement, not that they resolved or
settled it."* Empty-state copy: *"No later papers in OpenAlex cite
both sides. This is what an unaddressed disagreement looks like —
not a signal that either side is correct."* Never uses "resolved" or
"settled".

## Decisions I need from you

1. **PD (weekly-refresh GitHub Actions workflow)** was NOT built —
   this run's usage limit hit before that part. The design in the
   brief is clear (schedule + workflow_dispatch, cites-both against
   genuine pairs + cites-orphan-fw candidates, dedupe via 4-pass,
   open ONE issue per run, minimal permissions, Python module +
   tests + dry-run). Say the word and it's the next commit's
   scope.
2. **PE (headless-Chrome per-library verification + screenshots)**
   also not run — same reason. What I DID verify: 387 tests pass,
   frontend build clean, git status clean, LLM-cal manifest hash
   unchanged, all snapshot JSONs regenerated. What I didn't verify:
   the per-library rendering in a real browser. Two options:
   (a) I can do a compact headless check in the next session as its
   own commit, or (b) you eyeball the live Vercel deploy after push
   and I fix anything visible.
3. **PC3 blind review packet is ready** at
   `docs/review/diet-contradictions/`. Nothing sent. Whenever you
   recruit reviewers, hand them `packet.html` (printable) +
   `response_form.csv`; keep `_answer_key_DO_NOT_SHARE/` on your
   side. When responses come back, run
   `python -m backend.app.review.score_responses --responses file.csv --key .../answer_key.json`.
4. **PF local-model test** needs you to `ollama pull
   llama3.2:3b-instruct-q4_K_M` (~2 GB, one interactive command).
   Instructions in `docs/local-model-plan.md`.

## Manual steps you must do

- **Nothing has been pushed.** Review the 9 iteration-2 commits on
  `main` and push when you're happy:
  `git log --oneline origin/main..main` shows the local-vs-remote gap.
- If you upgrade Vercel to Pro for custom-event analytics, the
  scrubber at `frontend/lib/analytics-scrub.ts` is ready — wire
  it into `Ask.tsx`'s search-verdict path. Until then no query
  logging happens.

## Test + build status

- **387 backend tests pass** (baseline 363; +5 audit, +6 export, +3
  cites-both, +2 scrubber, +7 review scorer, +1 fix elsewhere).
- Frontend typecheck clean.
- Static export builds clean (313 paper pages, 83 gap pages —
  union across the 3 libraries).
- `npm audit`: down from 3 vulnerabilities (2 high, 1 critical) to
  **1 critical** — the remainder is the Next.js rollup of server-
  runtime advisories that don't apply to `output: "export"` sites;
  documented in `docs/security-audit.md`.

## Files worth checking

- `data/domains/diet-and-mortality/reasoning/contradiction_audit.json`
- `data/domains/diet-and-mortality/reasoning/cites_both.json`
- `docs/findings/domain-coherence-predictor.md` (new §"Measured record — n=3")
- `docs/review/diet-contradictions/*` (blind review packet)
- `docs/local-model-plan.md`
- `docs/security-audit.md`
- `REPORT_iteration2.md` (this file)
