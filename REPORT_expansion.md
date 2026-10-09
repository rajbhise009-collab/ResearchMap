# REPORT — scheduled expansion: more domains, unattended growth (2026-10-09)

## Money

| item | INR |
|:--|--:|
| Ledger at the start of this run | 958.55 |
| Social media & teens: batch extraction (100 papers) | 128.32 |
| Social media & teens: claim embeddings (422 claims) | 2.05 |
| Social media & teens: disagreement check, batch (179 pairs) | 25.24 |
| Social media & teens: future-work embeddings | 0.50 |
| Social media & teens: future-work matcher, batch (129 pairs) | 20.70 |
| Social media & teens: method-transfer confirmation (1 lead) | 0.18 |
| **Spent this run** | **176.99** (of the ₹320 allocation) |
| **Ledger total** | **1135.54** |
| Ceiling (config/money.json: 1500 − 50) | 1450.00 |
| **Remaining** | **314.46** |
| Weekly pace, recalculated each run: min(₹60, remaining ÷ 12 weeks) | **26.21 / week** |

The money rule is enforced at call time in every path (`SpendLedger`). If you fill in `console_spent_inr` with `console_spent_date`, remaining becomes 1450 − console − ledger spend after that date. Domain selection, snowballs, audits, full-text retrieval and every test were free. No test made a paid call.

## Domains

**Scoring** (`docs/findings/domain-selection-2026-10-09.md`): 12 candidates, with these weights:

- contestedness 0.45 (0.7 reputation + 0.3 coherence predictor);
- full text 0.25, measured by sending 25 papers each through the real retrieval code;
- audience 0.15;
- 1 − advice risk 0.15.

| domain | status | why |
|:--|:--|:--|
| Nudges and choice architecture | **queued** (prepared, full text found) | Highest score (0.677). A sharp meta-analysis dispute. Didn't fit the run's remaining ₹143 completely (extraction alone projects ₹181 padded). By the money rule, the first weekly run should start building it. |
| Social media & adolescent mental health | **built** | 0.676, the most contested candidate (predictor 0.83). |
| Ego depletion | **queued** | 0.668. Blind audit 67 % → 87 % after one rubric fix. |
| Growth mindset | **queued** | 0.646. Blind audit 67 % → 87 % after one fix. |
| Minimum wage | **not ready** | 0.663. Blind audit 60 % → 67 % after the fix (80 % required). |
| Deep-RL evaluation | **not ready** | 0.621. 53 % → 67 %. |
| Microplastics & health | **not ready** | 0.620. 60 % → 67 %. |

The three failures share a cause. The shared rubric code keeps a paper as borderline on an outcome term alone, or when anchor and topic words sit far apart. In broad fields that admits general papers. Fixing it needs your decision (LAUNCH.md §11).

## The new library: Social media & adolescent mental health

- **Papers:** 100 (99 read; 1 extraction failed; 22 full text). Pre-labelled with the full 4-pass dedupe and the title rule before trimming. Blind audit 87 % in/out agreement.
- **Results: 32**, by type:
  - 2 disagreements;
  - 4 limitations repeated across teams (self-report bias across 6 teams, cross-sectional design, small samples, heterogeneity);
  - 26 open questions, each a verbatim quote from its paper;
  - plus 5 set aside after checking.
- **Disagreements:** 6 pairs flagged, hand-audited against the abstracts by the builder (not experts):
  - **genuine:** "Smartphones and teenagers' well-being: a real decline, or too small to matter?" (47 later papers cite both sides) and "Depression across generations: a real rise, or an artifact of recall?" (17);
  - **set aside:** 3 artifact, 1 duplicate.
- **Method-transfer lead:** 1 lead, judged "not addressing" by the confirmation step, so set aside.
- **Coherence predictor:** scored this domain 0.833 ("high"); it produced 2 genuine disagreements (outcome row added to multi-domain.md).
- **Not-advice note:** points readers who are struggling to a doctor or a local support service.

Every library's page, search index and vocabulary, generated search test set (15 phrases + 5 refusals), share image, sitemap entries, /method tables and findings-doc rows were regenerated.

## Unattended growth (Part 4)

`weekly-grow.yml` now:

- grows every built, non-frozen library from `data/library_registry.json`, with the week's money shared round-robin;
- builds a queued library in two phases when "projection ×1.5 + 4 weeks of growth" fits;
- retries transient API errors with backoff;
- on a stop after spending, commits only bookkeeping (`data/`), so nothing paid is lost and next week resumes;
- treats money running out as **BUDGET EXHAUSTED** (collect only, site live, one Issue saying what you can do);
- can be paused and resumed via `config/growth.json`.

Each weekly Issue lists papers added per library, new libraries, spend this week and lifetime, remaining money and weeks left, and flagged pairs to audit. Runbook: `docs/OPERATIONS.md`.

**End-to-end test** (`tools/grow/e2e_mock.py`, mocked OpenAlex and Gemini, temporary ledger and money config):

**Clean pass: 39/39**, with every publish gate run for real in scenarios 1, 2 and 7 (`docs/releases/growth-e2e-passed.json`, tested commit `ddfab60`).

1. **Week 1:** batches across every growing library (round-robin); the first queued library starts building; published.
2. **Week 2:** papers collected and billed once; the queued library finished and published on a **six-library site**; its flagged pairs labelled "not yet checked" and not counted; leads confirmed before display.
3. **Missing secret:** clean stop, nothing pushed; the set secret appears nowhere.
4. **OpenAlex down after collecting:** bookkeeping-only commit (spend kept on main), site files unchanged, no blocking branch.
5. **Next week:** runs normally.
6. **Money runs out mid-run:** status BUDGET EXHAUSTED, nothing new submitted, the Issue says what you can do.
7. **Failing gate:** site unchanged, `grow/<date>` branch, the Issue shows the output.
8. **With that branch open:** collects, starts nothing new.
9. **Pause, then resume.**
10. **Daily health:** site down opens the Issue; site up closes it.

The real ledger was never touched, and no secret appeared in any Issue.

Getting to a clean pass took four runs. Each failed run exposed a real problem, now fixed:

- an inherited money config capping the test ledgers;
- smoke checks that stalled on a busy machine;
- two checks written for the original libraries that didn't fit a new one;
- money running out while finishing a queued library was treated as an error.

What the end-to-end runs caught and I fixed:

- test isolation: an inherited money config capped the test ledgers;
- a smoke check that stalls on a busy machine;
- earlier: missing data in a fresh checkout, gate order, and stale result pages.

## Five-plus libraries in the UI (Part 5)

- **Data-driven:** the library picker, footer, /about, /method, search routing and the "this looks like it's about <library>" suggestion now come from data.
- **Suggestion:** checks all libraries in parallel and names the strongest match.
- **Out-of-scope panel:** shows 3 libraries, then "All N".
- **Synthetic 8-library build** (`tools/qa/synthetic_libs.py`): 23/23, desktop and 320 px.
- **Collision tests:** cover every built library, plus the new library's terms.
- **Search fix:** everyday words ("teenage", "kids", "phone", "tiktok") now map to the indexed vocabulary, so natural questions aren't refused.

## Reader-facing problems found and fixed in this run

- **Wrong library size:** 85 result cards in three libraries said "this library is 113 papers" (LLM calibration's size). Each card now states its own library's size, and a test checks every shipped card.
- **Generic disagreement titles:** the new library's disagreements were titled "Two papers disagree on the finding". They now have hand-written question titles with no verdict words.
- **Leaking error messages:** OpenAlex and cites-both errors carried the request URL, which includes the API key. They now carry only the status code. Two scratch logs that had captured a key were deleted; the key was never printed or committed.

## Verification and publishing

**Local, final build:**

- 775 tests passed.
- Typecheck, production build and the consistency script (before and after the build, four libraries) pass.
- The docs check passes and is now stable: the coherence predictor's modularity was nondeterministic, so the check flipped between runs; fixed.
- Curious-visitor checks: 76/76 on Chromium and 76/76 on WebKit.
- Smoke checks: 108/108 (every library on Chromium and WebKit, desktop and iPhone 13: its card, /gaps, a gap page with a working .bib export, one settled search, the refusal, axe with zero serious issues, no console errors).
- Synthetic eight-library UI test: 23/23.

**Pushed** (each confirmed by exit code 0 and `git ls-remote`): `iteration-2` → `e738c14`, then `main` → `e738c14` (fast-forward from `8e90824`).

**Production, about 4 minutes later** (https://researchmap-one.vercel.app):

- `libraries.json` lists the four libraries.
- Smoke checks: **108/108**.
- Curious-visitor checks: **76/76**. Three hostile URLs are refused by Vercel's edge (400/403) before reaching the site, as in the last run.
- Live check:

```
PASS  https works  — GET https://researchmap-one.vercel.app/ -> 200
PASS  sitemap.xml served, hosts match  — status 200, 620 URLs, 0 with another host
PASS  robots.txt served, sitemap host matches  — status 200, sitemap lines ['https://researchmap-one.vercel.app/sitemap.xml']
PASS  robots.txt allows indexing
PASS  home: security headers  — X-Content-Type-Options: nosniff; Referrer-Policy: strict-origin-when-cross-origin; Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(); X-Frame-Options: DENY
PASS  home: canonical and og:url host = researchmap-one.vercel.app
PASS  home: og:image returns 200  — https://researchmap-one.vercel.app/og/default.png -> 200
PASS  gap page: security headers  — X-Content-Type-Options: nosniff; Referrer-Policy: strict-origin-when-cross-origin; Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(); X-Frame-Options: DENY
PASS  gap page: canonical and og:url host = researchmap-one.vercel.app
PASS  gap page: og:image returns 200  — https://researchmap-one.vercel.app/og/diet-and-mortality.png -> 200
WARN  analytics script (/_vercel/insights/script.js)  — status 404 — enable Web Analytics in the Vercel dashboard
PASS  http -> https  — http://researchmap-one.vercel.app/ -> https://researchmap-one.vercel.app/ (200)
SKIP  www <-> apex redirect  — not applicable to researchmap-one.vercel.app
SKIP  *.vercel.app redirect  — the base URL is the vercel.app host

0 failed, 11 passed, 1 warnings, 2 skipped
```

No revert was needed. This report is committed after the checks above.

## Steps only you can do

1. Add the GitHub secrets `GEMINI_API_KEY` (a new key restricted to the Generative Language API) and `OPENALEX_API_KEY`, then run **Weekly grow** once.
2. Optional: enter the console's real spend in `config/money.json` (`console_spent_inr`, `console_spent_date`). To add money, raise `account_total_inr`.
3. Audit the disagreements each weekly Issue flags.
4. Decide on the three not-ready rubrics (minimum wage, deep-RL evaluation, microplastics).
5. Carried over: Vercel Web Analytics; name, domain, `NEXT_PUBLIC_SITE_URL` and contact email; legal review of /terms and /privacy; the expert review.

Phase 6 (validation) is still owed.
