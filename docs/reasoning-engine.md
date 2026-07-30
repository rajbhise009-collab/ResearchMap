# Reasoning engine (Phase 4) — scorers, weights, traceability

Deterministic Python only. **No LLM anywhere in scoring** — an LLM never
produces a number, a rank, or a judgement here. Embeddings (a fixed model)
are used only as deterministic features, exactly as `opportunity-criteria.md`
§"Matching rule" permits. Each scorer is a pure
`(ReasoningCorpus) -> list[Opportunity]`; the runner enforces criteria 2 & 3
at runtime (non-empty `evidence_trail`, `supporting_paper_ids`, and
`component_scores`).

Runner: `run_reasoning.py` → `scratch/opportunities_review.md` +
`data/reasoning/opportunities.jsonl`. Ranking key = **score × confidence**
(trust-weighted): a `score` can be high while `confidence` is low (corpus-
relative orphans), so the product surfaces trustworthy items first.

## Traceability to opportunity-criteria.md (and where I deviate)

| # | scorer | gap_type | traces to | deviation (flagged) |
|:--|:--|:--|:--|:--|
| 1 | persistent_limitations | UNADDRESSED_LIMITATION | criterion 1 (≥3 independent papers), failure modes (own-work via `source_scope`, dedup/first-author independence) | "methodological diversity" and "time span" as score boosters are NOT in the doc — design choices. "Absence of resolution" is asserted but **not computable** (no limitation-resolution relation exists) — assumed, not verified. |
| 2 | unresolved_contradictions | UNRESOLVED_CONTRADICTION | non-triviality #2 (incompatible findings, named claim IDs, neither cites the other) | none |
| 3 | orphaned_future_work | UNFOLLOWED_FUTURE_WORK | non-triviality #3 (unfollowed ≥ N years) + small-corpus failure mode | `indeterminate` items are excluded (unscoreable), not orphaned; every item carries the corpus-relative caveat |
| 4 | structural_holes | METHOD_TRANSFER | non-triviality #4 (method transfer across an uncrossed citation boundary) + structural-hole failure-mode note | method↔limitation relevance is a **coarse token-overlap proxy** (no semantic embedding), flagged noise-level |
| 5 | disjoint_bridging | METHOD_TRANSFER | **only obliquely** referenced (small-corpus "disjoint-bridging" note) — no dedicated criterion | under-specified in the doc; **OFF by default**, mostly noise until validated against the retrospective test |

Nothing was invented to fill a missing criterion silently — the gaps above
are stated rather than papered over, as instructed.

## Weights (config, chosen with reasoning — never LLM)

All in `backend/app/config.py`. Every scorer maps its raw signal to [0,1]
via `saturating(n,k)=n/(n+k)` (n=k gives 0.5) or explicit clamps.

- `reason_min_independent_papers=3` — the criterion-1 floor.
- Persistent blend: `w_count=0.55, w_diversity=0.25, w_timespan=0.20` —
  count dominates (it is the criterion), diversity/time-span are secondary
  design signals.
- `reason_orphan_min_years=2` — the doc's defensible default.
- `reason_n_clusters=8`, `reason_weak_bridge_max_edges=2` — clustering knobs.
- `reason_enable_disjoint_bridging=false`.

Confidence is a separate deterministic axis from score: it reflects
**reliability** (fraction full-text, independent count, corpus-relative
uncertainty for orphans), and is deliberately capped low for orphans and
structural holes.

## Mixed-fidelity correction (MANDATORY)

Full-text papers yield ~11× more own-work limitations, and availability
tracks venue/OA not merit (`docs/findings/fulltext-vs-abstract-finding.md`),
so a raw paper count ranks arXiv/OA-preprint culture. Correction:
`effective_count` weights each supporting paper by `input_source` —
`abstract` up-weighted (config `reason_fidelity_weight_abstract=3.0`,
`fulltext=1.0`); OFF = every paper 1.0. Both are computed and reported.

**Chosen weight = 3.0, a DAMPENED inverse-propensity.** The measured ratio
is ~11×, but using it directly lets one noisy abstract-only limitation
outweigh three clean full-text ones and defeats the 3-paper robustness
intent (abstract extraction is also lower-precision). 3.0 neutralises much
of the detection gap without inverting the evidence base. Set it to 11.5 for
the full inverse-propensity estimator, or 1.0 to disable.

**On the current corpus the correction is a no-op** — every limitation
category that reaches the 3-paper floor is 100% full-text. That is not a
bug; it is the bias made visible: abstract-only papers yield so few own-work
limitations (15 of 254) that none reaches the floor with abstract support.
The correction changes scores/order only once an abstract paper contributes
to a qualifying category. It is applied to the count-based persistent-
limitations scorer; it is not mechanically applied to the orphan scorer,
whose signal is "no later paper addressed", not a paper count.

## Backlog: `Claim.condition` structured field (future improvement)

The contradiction classifier can conflate claims that hold under different
experimental regimes (a survey's "temperature↑ → hallucination" in general
generation vs. a clinical paper's "temperature=0 doesn't reduce
hallucination" under adversarial fact-injection — see
`docs/findings/phase4-investigations.md`). The **cheap partial applied now**
feeds each claim's sibling claims (same paper) into a regime-aware v1.1
prompt so the model can infer the regime from surrounding text (~$0.51, no
schema change).

**The proper fix, deferred for budget:** add a structured `Claim.condition`
field capturing experimental regime (general / adversarial / clinical /
domain-specific), dataset/benchmark, the manipulation, the operational
definition of the measured property, and the model set — so two claims are
compared only when same construct AND same regime. Cost: add field
(Pydantic + table + migration) + a v1.2.0 extraction prompt + **re-extract
all papers** ≈ **$4.65 (batch) + ~$0.71 rerun ≈ $5.4**, over the current
~$2 budget. Revisit when budget allows.

## Honest limitations (what the reviewer should weigh)

- **Thin by design.** Only 5 limitation categories reach the 3-paper floor
  (mostly generic: computational-cost, small-sample-size…), 2 contradictions
  corpus-wide, 108 orphaned-future-work items (each weak/corpus-relative),
  structural holes fire only under a coarse proxy, disjoint bridging is off.
  This is the honest output of a 200-paper corpus, not tuned for volume.
- **Generic categories** flagged: they likely fail the actionability
  "named object of study" bar.
- **Orphans dominate by raw score but are low-confidence**; the trust-
  weighted ranking and the WEAK flags reflect this.
- **Not validated.** These scores are un-validated until the Phase-6
  retrospective time-split test; nothing should be built on them before the
  human review this phase stops for. Do NOT tune against the seed corpus
  (planted answers).
