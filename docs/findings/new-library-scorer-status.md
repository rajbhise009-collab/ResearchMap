# New-library scorer status

**Date:** 2026-10-02 (iteration-4 update). Every number below comes from
the shipped `frontend/public/data/library/<slug>/stats.json`, the files
under `data/domains/<slug>/reasoning/` (including `coverage.json` and the
hand-audit file), or `data/spend_ledger.json`.

The reasoning engine has five scorers. "Skipped" is not the same as "ran
and produced zero".

## Summary

<!-- gen:scorer-status -->
| library | papers | claims read | disagreement check | confirmed contradictions | persistent limitations | orphaned future work | structural holes |
|:--|--:|--:|:--|--:|--:|:--|:--|
| llm-calibration | 113 | 113 (100%) | 437 / 437 pairs | 0 (of 2 flagged) | 1 | 63 | 12 (2 substantive) |
| diet-and-mortality | 100 | 100 (100%) | 152 / 152 pairs | 5 (of 10 flagged) | 2 | skipped (paid, by design) | not run (pipeline not built) |
| ml-fairness | 99 | 99 (100%) | 91 / 91 pairs | 0 | 1 | skipped (paid, by design) | not run (pipeline not built) |
<!-- /gen:scorer-status -->

"Pairs" are shortlisted claim pairs. Diet and ML-fairness: cosine
similarity ≥ 0.80, at most 2 candidates per claim (their documented
settings). LLM-cal used its own Phase-3 settings (≥ 0.78, up to 10 per
claim; docs/relationship-layer.md), so the counts are not comparable
across libraries.

## What iteration 4 changed

- **Diet:** the 58 shortlisted pairs left unclassified after iteration 3
  were classified (58 calls, ₹16.36 from the ledger). 3 new flags, all one
  paper pair on triglycerides and coronary heart disease; hand audit set
  all three aside (1 artifact, 2 duplicates). Headline unchanged at 5.
- **ML-fairness:** the last 27 papers were extracted through the batch
  API (28 batch results including one retry, ₹72.75), then the 29 new
  shortlisted pairs were classified (₹7.77). 0 flags.
- Both libraries' disagreement checks are now complete for their full
  extraction sets.

## Persistent limitations

Code-only count: a normalised limitation category reported as a
limitation of the paper's own work by at least 3 papers. Not the full
Phase-4 scorer (that needs the claim-embedding and addressal pipeline
the multi-domain libraries don't have). No gap card is published for
these counts.

## Orphaned future work — skipped by design

Matching future-work statements against later papers is paid and the
lowest-value output per rupee. It is not planned for the new libraries.

## Structural holes — not run

The scorer needs the embeddings + addressal graph that the LLM-cal
library has and the multi-domain pipeline does not build. Building it is
engineering work, not spend.

## ML-fairness impossibility-result papers (full coverage)

Pairs touching these papers at the documented settings, from the saved
verdict files:

| paper | shortlisted | classified | contradicts |
|:--|--:|--:|--:|
| Kleinberg, Mullainathan, Raghavan 2016 | 12 | 12 | 0 |
| Chouldechova 2017 | 1 | 1 | 0 |
| Friedler et al. 2016 — "On the (im)possibility of fairness" | 0 | 0 | 0 |
| Berk et al. 2018 | 10 | 10 | 0 |
| Corbett-Davies et al. 2017 | 0 | 0 | 0 |
| Menon & Williamson 2018 | 0 | 0 | 0 |
| "Inherent Trade-Offs in Algorithmic Fairness" 2018 | 2 | 2 | 0 |

Friedler et al.'s paper was never compared with anything: none of its
claims reached the similarity threshold against another paper's claims.
Why the classifier flags no contradictions in this library is not
established. That fairness disagreements are definitional rather than
empirical is a **hypothesis**, not a finding.
