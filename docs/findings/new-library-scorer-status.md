# New-library scorer status

**Date:** 2026-10-01. Diagnostic only — no scorer was run for this
report; the numbers come straight from the shipped
`frontend/public/data/library/<slug>/stats.json` snapshots and from
the files under `data/domains/<slug>/reasoning/`.

The reasoning engine runs five scorers; each either ran or was
skipped. "Skipped" is not the same as "ran and produced zero" — the
distinction matters for the honesty copy in the UI.

## Summary

| library | papers | claims read | unresolved_contradictions | persistent_limitations | orphaned_future_work | structural_holes | structural_holes_substantive |
|:--|--:|--:|--:|--:|--:|--:|--:|
| llm-calibration | 113 | 113 (100%) | 0 | 1 | 63 | 12 | 2 |
| diet-and-mortality | 100 | 59 (59%) | 5 ran + audited | — skipped | — skipped | — skipped | — skipped |
| ml-fairness | 100 | 51 (51%) | 0 ran (no genuine) | — skipped | — skipped | — skipped | — skipped |

## llm-calibration

**All five scorers ran** against the full 113-paper extraction. The
`unresolved_contradictions` zero is a real zero — the pipeline looked
and found none. The other four yielded 76 opportunities total (1 + 63 +
12, with 2 of the 12 structural holes classified "substantive"). No
further runs needed.

## diet-and-mortality

- **unresolved_contradictions**: **ran** on the 59 extracted papers.
  Raw shortlist of 7 pairs; hand audit (not expert review — the
  pipeline builder's read) classified **5 genuine, 1 artifact
  (regime-conflation), 1 duplicate**. See
  `data/domains/diet-and-mortality/reasoning/contradiction_audit.json`.
- **persistent_limitations**: **skipped.** Gate-3 cut; the scorer
  needs the same extraction over the remaining 41 papers to be
  meaningful.
- **orphaned_future_work**: **skipped.** Needs the same extraction.
- **structural_holes**: **skipped.** Needs methodology embeddings
  across the extracted set; the embedding call runs on cached
  extractions and is free. Reasoning requires the complete corpus
  for its "hole = absent methodology pair" definition to hold.
- **structural_holes_substantive**: **skipped** (depends on the
  previous).

### Cost to finish

| step | papers | tokens est. | cost @ gemini-3.6-flash | INR @ ₹84 |
|:--|--:|--:|--:|--:|
| extract remaining 41 abstracts (no full text) | 41 | ~2k in + ~1k out each | $0.19 total | **~₹16** |
| extract remaining 17 full-text (OA papers Unpaywall found) | 17 | ~12k in + ~2.5k out each | $0.32 total | **~₹27** |
| optional: re-run contradiction classifier against 7 new "nones" that could flip after full extraction | 7 pairs | ~5k in + ~1k out each | $0.08 | **~₹7** |

**Diet full-coverage total: ~₹50** (one Gemini run, within the
₹850 persistent cap at `data/spend_ledger.json`).

The scorers themselves (contradiction classifier excepted) are
**free** on cached extractions — no LLM call needed. Running them
over the fully-extracted diet corpus is zero additional spend.

## ml-fairness

- **unresolved_contradictions**: **ran** on the 51 extracted papers.
  Raw shortlist = 0; hand-audit confirmed 0. Separately, the
  "fairness-miss diagnostic" (`docs/findings/domain-coherence-predictor.md`
  §"Measured record — n=3") found 6 impossibility/incompatibility
  papers in the extracted set; pairs involving them were labelled
  `supports` (same theorem) or `none` (distinct impossibility theorems
  on different metric combinations). Reading: the classifier is
  behaving correctly for its empirical-disagreement prompt;
  definitional disagreements in the fairness literature don't match
  that shape.
- **persistent_limitations**, **orphaned_future_work**,
  **structural_holes**, **structural_holes_substantive**: all
  **skipped**, same Gate-3 cut as Diet.

### Cost to finish

| step | papers | tokens est. | cost @ gemini-3.6-flash | INR @ ₹84 |
|:--|--:|--:|--:|--:|
| extract remaining 49 abstracts (no full text) | 49 | ~2k in + ~1k out each | $0.22 total | **~₹19** |
| extract remaining ~50 full-text | 50 | ~12k in + ~2.5k out each | $0.95 total | **~₹80** |
| optional: contradiction classifier variant tuned for definitional disagreement (new prompt; needs 8-10 domains + hold-out set to validate — not just a free rerun) | — | — | — | — |

**ml-fairness full-coverage total: ~₹100.** The variant classifier is a
research step, not a budget line — the current one is correct for its
prompt. Running the other four scorers against the full extraction is
**free** on cached data.

## Combined fresh spend if both finish

- Diet remaining extraction: ~₹50
- ml-fairness remaining extraction: ~₹100
- Running `persistent_limitations`, `orphaned_future_work`,
  `structural_holes`, `structural_holes_substantive` on both: **free**
  (code-only, cached JSON).

**Total to go from today's partial-extraction state to full coverage
of all three libraries with all five scorers: ~₹150.** Spend ledger
cap is ₹850; cumulative spend to date is ₹524.6 (prior iterations),
so there is ~₹325 headroom even without raising the cap.

## Not run and will not run free

- Contradiction classifier variant for definitional disagreement
  (ml-fairness fallback hypothesis). Needs a hold-out set + 8-10
  domains to validate before deployment, not just a quick re-prompt.
  Explicitly out of scope for this diagnostic.

## No action taken

Nothing in this document changed any published data file. No LLM
calls were made. The purpose was to make the published-vs-skipped
breakdown explicit so a future spending decision has concrete INR
numbers attached.
