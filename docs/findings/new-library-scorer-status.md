# New-library scorer status

**Date:** 2026-10-02 (iteration-3 update). Diagnostic — numbers come
from the shipped `frontend/public/data/library/<slug>/stats.json`
snapshots and from the files under `data/domains/<slug>/reasoning/`.

The reasoning engine runs five scorers; each either ran or was
skipped. "Skipped" is not the same as "ran and produced zero".

## Summary

| library | papers | claims read | unresolved_contradictions | persistent_limitations | orphaned_future_work | structural_holes |
|:--|--:|--:|--:|--:|--:|--:|
| llm-calibration | 113 | 113 (100%) | 0 | 1 | 63 | 12 (2 substantive) |
| diet-and-mortality | 100 | **100 (100%)** | 5 confirmed | 2 | — skipped (paid) | — skipped (needs embeddings) |
| ml-fairness | 100 | **73 (73%)** | 0 | 1 | — skipped (paid) | — skipped (needs embeddings) |

## What iteration 3 changed

- **Diet** went from 59/100 to **100/100 extracted**. All 41 remaining
  papers extracted via sync Gemini-flash v1.1.0. No new contradictions
  surfaced (still 5 audited-genuine, 1 artifact, 1 duplicate).
- **ml-fairness** went from 51/100 to **73/100 extracted** (hit the
  ₹300 run cap mid-way). Still **0 contradictions** after
  classifying 135 additional pairs (of 698 new shortlisted pairs).
- Persistent-limitations: diet=2 ("small-sample-size",
  "residual-confounding"), ml-fairness=1 ("accuracy-fairness-tradeoff").
  These are a free, code-only count (categories with ≥3 unique
  own-work-scope limitation sources), not the full Phase-4 scorer.
- Orphaned-future-work matching is **paid, skipped by design** on the
  new libraries. Lowest-value output per rupee; not planned to run.
- Structural-hole scoring + LLM confirmations: **deferred.** The
  scorer needs claim embeddings + an addressal-graph the multi-domain
  pipeline doesn't build yet. Running the LLM-confirm step for ~15
  top leads per library would be ~₹60-120 — out of this run's budget.

## llm-calibration

Unchanged. All five scorers ran against the full 113-paper
extraction. 76 total opportunities. The 0 for `unresolved_contradictions`
is a real zero. No further runs planned.

## diet-and-mortality (now complete)

- **unresolved_contradictions**: ran. Full-coverage shortlist produced
  37 additional pair candidates on top of the previous run (128 → 165
  classifier calls). **No new genuine contradictions emerged.** The
  audit stays at 5 genuine + 1 artifact + 1 duplicate.
- **persistent_limitations**: 2 categories recur in ≥3 papers.
  Reported as counts; the full scorer (with corrected-independence
  calculation and the LLM-cal rubric) is out of scope for this run.
- `orphaned_future_work`, `structural_holes`: skipped as above.

## ml-fairness

- **unresolved_contradictions**: ran at 73/100 extraction coverage. 752
  total shortlist pairs, 54 already classified, 698 new candidates. The
  spend cap hit after 135 of 698 new pairs were classified (0 new
  contradicts, 36 supports, 99 nones). Still **0 contradictions.**
- Famous impossibility papers: iteration 2 found 6 in the extracted
  set. At 73/100 coverage, we picked up more pairs involving them —
  all classified as `supports` (same theorem, different authors) or
  `none` (distinct impossibility results on different metric
  combinations), none as `contradicts`. The hypothesis that these are
  **definitional / theoretical disagreements the empirical-claim
  classifier doesn't catch** remains the leading explanation,
  **labelled as hypothesis, not stated as fact**.
- `persistent_limitations`: 1 category.
- `orphaned_future_work`, `structural_holes`: skipped.

### What a full-coverage ml-fairness run would need

- Extract remaining 27 papers: ~₹60-100 at the observed sync rate
  (would need a separate approved spend window).
- Run contradiction classifier on remaining 563 shortlist pairs:
  ~₹150-200.
- Total to finish ml-fairness contradictions: **~₹250-₹300**.
- Does not meaningfully fit under the current ₹850 ledger cap without
  explicit cap raise, since we're at ₹824 cumulative after this run.

## Cost to run the full ml-fairness contradictions pass

Not a decision for this iteration. The information is here so a next
spend window has concrete numbers; the scorer-match hypothesis would
need a different experimental design (compare classifier verdicts to
a labelled hand-set of fairness-literature pairs) before another
₹250 is a sensible spend.
