# `Claim.confidence` policy

## Decision (2026-07-23)

`Claim.confidence` is **retained as extraction-quality metadata and
demoted to a pre-scoring filter only.** It is **NEVER a scoring input.**

### Why not "make it carry signal"

The v1.0.0 live run returned `confidence: 1.0` on essentially every
claim (29/30 papers had all-1.0). The first instinct — redefine the
field with anchored examples so it discriminates — was rejected for
two reasons:

1. **Empirically it clusters at the ceiling regardless of prompting.**
   Self-reported LLM confidence is known to sit near 1.0; anchored
   examples move it little. We would be adding prompt complexity for a
   field that stays uninformative.

2. **The stronger, structural objection (this is the binding one):**
   if `Opportunity` scoring ever read `Claim.confidence`, an LLM's
   self-assessment would sit in the scoring path. `CLAUDE.md`'s core
   rule is *LLMs extract, code reasons* — no LLM judgment in any
   score. A confidence value the model assigned to its own extraction
   is exactly such a judgment. Letting it influence a score would be a
   quiet violation of the project's central invariant.

### What confidence MAY be used for

- A **pre-scoring filter**: the reasoning engine MAY discard
  extractions below a configured `confidence` threshold *before*
  scoring begins, as a data-cleaning step. This is allowed because the
  filter's output is binary keep/drop and does not propagate the
  model's numeric self-assessment into any score.
- Given the observed ceiling clustering, this filter is currently a
  **no-op** in practice (nothing is below any sane threshold). It
  exists as a documented hook, not an active mechanism.

### What confidence MUST NOT be used for

- It MUST NOT be summed, averaged, weighted, or otherwise fed into any
  component of `Opportunity.score`, `Opportunity.component_scores`,
  `Opportunity.confidence`, the persistent-limitations scorer, the
  support/contradiction scorer, or any ranking.
- Any code that reads `Claim.confidence` outside the pre-scoring
  filter is a bug and a `CLAUDE.md` violation.

### Enforcement

When the reasoning engine (Phase 4) and ranking (Phase 5) are built,
a test must assert that `Claim.confidence` does not appear in any
scoring code path. Until then this document is the standing contract.

### Alternative considered: remove the field

Removing `Claim.confidence` entirely was considered. Rejected because
it cascades (schema, DB, migration, the 35-paper seed corpus, and the
60 already-run extractions) for little gain — demoting to filter-only
achieves the same guarantee (no scoring influence) reversibly.
`Evidence.strength` is a separate field and is out of scope for this
decision; it is code-assigned in principle, not a model self-report,
and will be revisited when the reasoning engine reads it.
