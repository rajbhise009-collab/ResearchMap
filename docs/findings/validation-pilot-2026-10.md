# Validation pilot — retrospective time-split test (2026-10-09)

**Status: pilot, inconclusive. The current libraries are too small to test the
project's claim either way.** Phase 6 is still owed. Free: cached embeddings
and matcher verdicts only, no API call. Code: `backend/app/validation/time_split.py`.
Raw results: `data/validation/`.

## What was tested

The documented matching rule (docs/opportunity-criteria.md, "Matching rule
for retrospective validation"), for the open-question scorer:

1. **Freeze** a library at year Y: only papers ≤ Y, their claims and
   future-work items, and only matcher verdicts between frozen papers. The
   unchanged Phase-4 scorer ranks the open questions it finds.
2. **Later evidence R:** the library's own papers from Y+1 to Y+2.
3. **Match (no language model):**
   - some claim in R is within cosine τ of the open question;
   - that claim had no near-duplicate before the freeze.
4. **Metric:** precision@K against the pool's base rate (one-sided
   hypergeometric p-value), and against a "newest source paper first"
   baseline. Citation counts are not used: today's counts leak the future.

## Results

| library | freeze Y | papers ≤ Y | later papers Y+1..Y+2 | τ | open questions ranked | addressed later | base rate | engine P@5 | newest-first P@5 |
|:--|--:|--:|:--|--:|--:|--:|--:|--:|--:|
| diet-and-mortality | 2015 | 60 | 20 (146 claims, 89 new) | 1.0 | 0 | 0 | 0.0 | — | — |
| diet-and-mortality | 2016 | 69 | 18 (123 claims, 48 new) | 0.5822 | 1 | 1 | 1.0 | — | — |
| ml-fairness | 2018 | 48 | 21 (103 claims, 69 new) | 0.7571 | 12 | 1 | 0.083 | 0.0 | 0.2 |
| ml-fairness | 2019 | 64 | 12 (51 claims, 27 new) | 0.7393 | 15 | 1 | 0.067 | 0.0 | 0.0 |
| social-media-teen-mental-health | 2016 | 66 | 18 (87 claims, 35 new) | 0.7111 | 5 | 0 | 0.0 | 0.0 | 0.0 |
| social-media-teen-mental-health | 2017 | 79 | 10 (47 claims, 3 new) | 0.7111 | 8 | 0 | 0.0 | 0.0 | 0.0 |

No engine ranking beat chance, and none could have. The ranked pools hold
0–15 open questions, and at most one per library was addressed later. At
those sizes a perfect ranker and a random one are statistically
indistinguishable.

## What the pilot did establish

- **The rule's threshold must be calibrated within the field.** The first
  attempt calibrated τ against claims from *other* libraries. That gave
  τ ≈ 0.58, below the *ordinary* within-field similarity (the median
  future-work-to-claim cosine inside ML fairness is 0.59). Every open
  question then "matched". The same τ used for novelty marked 98 of 103
  later claims as already known.
- **The fix extends the rule; it doesn't overturn it.**
  - The negatives are claims from papers *older* than the open question's
    source paper, which cannot address something not yet written. No
    language model is involved.
  - Novelty uses its own near-duplicate threshold: the 99th percentile of
    claim similarity between different pre-freeze papers.

  Both are recorded in the code. They are proposed for the policy doc,
  pending the owner's approval.
- **The machinery is sound:** frozen corpora carry nothing from after the
  freeze, and runs are deterministic (`backend/tests/validation/`).

## Why the libraries cannot carry the test

| need | 100-paper libraries |
|:--|:--|
| A frozen corpus big enough to rank dozens of open questions | 48–79 papers, 0–15 ranked questions |
| Later evidence that represents the field, not a snowball sample | 10–21 later papers from the same snowball |
| Enough addressed questions to tell rankings apart | 0–1 per library |

## Options (owner decision; none started)

1. **Field-level evidence, cheap.** R = the works in OpenAlex that cite an
   open question's source paper in Y+1..Y+k (free metadata), matched on
   embeddings of their abstracts, not extracted claims.
   - Cost: about ₹5–15 of embeddings for a few thousand abstracts.
   - Catch: it changes the rule's unit from "claim in R" to "abstract in R",
     a policy change that needs approval.
2. **Bigger historical corpora, faithful to the rule.** Snowball one library
   to about 400 papers, with at least 150 before and 100 after the freeze
   year; extract them; re-run.
   - Cost: about ₹400–450 (batch extraction plus matcher), more than the
     ₹314 the money rule has left, most of which is paced for weekly growth.
3. **Wait.** Weekly growth adds recent papers, not historical ones, so it
   does not help a time-split test by itself.

Recommendation: option 1 as the next pilot. It is cheap, field-level, keeps
the matching free of language-model judgement, and its abstract-level unit is
a stated, testable deviation.
