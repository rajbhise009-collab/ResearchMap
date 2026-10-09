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

E2E_RESULT

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

PUBLISH_RESULT

## Steps only you can do

1. Add the GitHub secrets `GEMINI_API_KEY` (a new key restricted to the Generative Language API) and `OPENALEX_API_KEY`, then run **Weekly grow** once.
2. Optional: enter the console's real spend in `config/money.json` (`console_spent_inr`, `console_spent_date`). To add money, raise `account_total_inr`.
3. Audit the disagreements each weekly Issue flags.
4. Decide on the three not-ready rubrics (minimum wage, deep-RL evaluation, microplastics).
5. Carried over: Vercel Web Analytics; name, domain, `NEXT_PUBLIC_SITE_URL` and contact email; legal review of /terms and /privacy; the expert review.

Phase 6 (validation) is still owed.
