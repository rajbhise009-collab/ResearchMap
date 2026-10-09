# Validation protocol v1 — pre-registered (2026-10-09)

Written and committed **before** any citing paper was fetched or any
outcome computed. The only numbers in this document are the pool size and
the power calculation, which use the engine's output alone, not outcomes.
Any change after results appear is a v2 protocol with its own record.
Implementation: `backend/app/validation/v1.py`.

## Question

When the engine names a question as unanswered at year Y, is that question
taken up in the next two years more often than chance, more often than
simple popularity predicts, and more often than recency predicts?

## Pool (fixed)

- **Libraries:** all four built libraries: LLM calibration, Diet & mortality,
  ML fairness, Social media & teens.
- **Freeze points:** every year Y at which a library holds at least 30
  papers dated ≤ Y, and whose window is complete (Y + 2 ≤ 2025).
- **Engine:** at each freeze point, the corpus is frozen exactly as in the
  pilot (`backend/app/validation/time_split._frozen`: papers ≤ Y, their
  claims and future-work items, matcher verdicts between frozen papers
  only). The unchanged open-question scorer (`score_orphaned_future_work`)
  ranks the open questions it finds.
- **Units:** each open question is counted once, at the earliest freeze
  point where it appears. Its engine score is the scorer's score there.
- **Pool size: N = 88 open questions** (ML fairness 54, Social media 29,
  Diet 4, LLM calibration 1), from 61 (source paper, freeze year) pairs.

## Outcome (fixed)

An open question O (source paper S, freeze year Y) is **addressed** if any
abstract of a paper that **cites S** and was **published from Y+1-01-01 to
Y+2-12-31** has cosine similarity ≥ τ with O's future-work text.

- **Citing papers:** OpenAlex only (`filter=cites:S,from_publication_date,
  to_publication_date`). No paper dated at or before Y is ever used; any such
  record is dropped and the run fails a test.
- **Missing abstracts:** papers without an abstract in OpenAlex are skipped.
  An open question with no usable citing abstract is not addressed.
- **Caps** (so the whole test fits ₹20 of embeddings):
  - abstracts truncated to their first 600 characters;
  - at most C citing papers per (S, Y), taken in order of publication date,
    then OpenAlex id;
  - C is the largest of 20, 15, 10, 8, 5 for which the projected cost of
    every embedding the run needs, padded ×1.5, is at most ₹20. This is
    computed from text lengths before any embedding call.
- **Embeddings:** the same model as the cached future-work embeddings
  (`GeminiEmbeddingClient`). Every embedding is cached by text hash and
  recorded in the ledger under the money rule.
- **τ:** per library, exactly as in the 2026-10-09 amendment to
  docs/opportunity-criteria.md:
  - for each O with m ≥ 1 usable citing abstracts, 20 draws (seed 20261009)
    of m abstracts from that library's own papers older than S;
  - truncated to 600 characters, sampled with replacement if fewer exist;
  - record the highest cosine to O in each draw;
  - τ_library is the 95th percentile of all draws.
- **Novelty condition:** not used. Citing papers are later by construction,
  and the condition was defined for claims, not abstracts.
- **No language model** judges any match.

## Measures (fixed)

- **AUC** of score against addressed: Mann–Whitney, with ties counted as
  half.
- **Precision@k** for k = 5, 10, 20, on the pooled ranking by score (ties
  broken by future-work id).
- **Random baseline:** a permutation test, 10,000 random orderings (seed
  20261009). This gives one-sided p-values for AUC and each precision@k.
- **Citation baseline:** source-paper citations up to year Y. This is the
  sum of OpenAlex `counts_by_year` for years ≤ Y, never today's count,
  which would leak the future.
- **Recency baseline:** source-paper publication year (newer ranks higher).
- **Intervals:** 95% bootstrap, 2,000 resamples (seed 20261009), for each
  AUC and for the paired difference engine − citation baseline.
- **Popularity-matched subset:** each addressed question is matched 1:1
  with the unaddressed question nearest in log(1 + citations up to Y).
  - caliper 0.5, without replacement;
  - addressed questions processed in future-work-id order;
  - report the engine AUC on the matched set, with its interval.

## Power (computed before the run)

Hanley–McNeil variance; detect AUC 0.65 against 0.5, two-sided α = 0.05,
power 0.80.

| share addressed | N needed | power at N = 88 |
|--:|--:|--:|
| 0.1 | 326 | 0.31 |
| 0.2 | 183 | 0.50 |
| 0.3 | 139 | 0.60 |
| 0.4 | 120 | 0.67 |
| 0.5 | 114 | 0.69 |

**The pool falls short at every share addressed.** Even the most
favourable case needs 114. Power is judged at the observed share (the
table is symmetric above 0.5). With N = 88 the study is underpowered, so,
as pre-registered, it will report effect sizes with intervals only and make
no claim.

## Verdict categories (defined now, reported the same way)

- **Supported:** all of the following hold:
  - the study is powered at the observed share;
  - the engine AUC's 95% interval lies above 0.5;
  - the engine − citation-baseline AUC difference has a 95% interval above 0;
  - the matched-subset AUC interval lies above 0.5.
- **Not supported:** powered, and not "supported". If the engine beats
  random (interval above 0.5) but not the citation baseline, the result is
  reported as **"not supported: popularity"**.
- **Inconclusive:** any of the following:
  - not powered at the observed share;
  - fewer than 10 addressed or 10 unaddressed questions;
  - fewer than 10 matched pairs.

  Effect sizes and intervals are still reported in full.

All three outcomes are published in the same format, in
docs/findings/validation-v1.md. The site says "validated" nowhere unless
the verdict is "supported".
