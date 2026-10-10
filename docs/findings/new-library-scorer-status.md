# New-library scorer status

**Date:** 2026-10-02 (iteration-4 update; scorer sections updated
2026-10-07 when all four scorers were run on the new libraries). Every number below comes from
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
| diet-and-mortality | 101 | 101 (100%) | 152 / 152 pairs | 5 (of 10 flagged) | 2 | 4 | 0 (0 substantive) |
| ml-fairness | 101 | 101 (100%) | 91 / 91 pairs | 0 | 1 | 57 | 0 (0 substantive) |
| social-media-teen-mental-health | 101 | 100 (99%) | 197 / 197 pairs | 2 (of 6 flagged) | 4 | 26 | 0 (0 substantive) |
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

Since 2026-10-07 this is the full Phase-4 scorer, the same code and
thresholds as LLM calibration (at least 3 independent papers report the same
own-work limitation category). Each result is published as a gap card.

## Orphaned future work

Ran on diet-and-mortality on 2026-10-07 (two-stage matcher: cosine
shortlist, then a language-model check of each candidate pair). Skipped for
ml-fairness: its projected cost, doubled as the safety gate requires, did
not fit the remaining budget. See `multi-domain.md` §8.

## Structural holes

Ran on both new libraries on 2026-10-07 with topic groups scaled to library
size (k = 10) and the leads checked by a language model (at most 15 per
library). Counts are in the table above; why they are low is in
`multi-domain.md` §8.

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
