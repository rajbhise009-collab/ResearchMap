# Finding: full text is required to extract discussion-section signals

**Status: established result** (promoted from `docs/abstract-vs-fulltext.md`).
This is a methodological claim about extraction, independent of the
ResearchMap product — it stands on its own for citation.

## Claim

For literature-based-discovery scorers that depend on a paper's **own-work
limitations** and **future-work** statements, extracting from the abstract
alone is insufficient: those signals live in the discussion/conclusion
sections, which abstracts systematically omit. Extracting from full text
instead of the abstract recovers them at roughly an **order of magnitude**
higher yield.

## Evidence

**Design.** Paired comparison, n=21 papers that have BOTH an arXiv full
text and an abstract. Same papers on both sides, same model, same prompt —
the single manipulated variable is input source (abstract vs. full text).
A paired design avoids confounding input source with paper set (the
full-text-missing papers skew journal-only and may report limitations
differently).

**Conditions.**
- Model: `gemini-3.6-flash`, temperature 0.0 (identical both arms).
- Prompt: `v1.1.0`, `prompt_hash eb8a0554bc13` (identical both arms).
- Full-text arm delivered via the Gemini batch API; batch is the same
  model at temp 0, a delivery mechanism, not a model change.

**Result (per paper, n=21 paired):**

| Signal | Abstract | Full text | Ratio |
|:-------|:--------:|:---------:|:-----:|
| **Own-work (`this_work`) limitations** | **0.19** | **2.19** | **11.5×** |
| **Future-work items** | **0.14** | **1.76** | **12.6×** |
| Prior-work limitations *(negative control)* | 1.10 | 1.43 | 1.3× |
| Limitations (all scopes) | 1.29 | 3.62 | 2.8× |
| Claims | 4.10 | 6.10 | 1.5× |
| Methodologies | 1.19 | 1.48 | 1.2× |

**The negative control is the crux.** Prior-work limitations — which
authors *do* state in abstracts and related-work framing — barely move
(1.3×). Only the two own-paper-scoped, discussion-section signals move an
order of magnitude. This rules out "full text just yields more of
everything" (a uniform ~2× inflation): the lift is specific to the signals
whose textual home is the sections abstracts exclude. That specificity is
the mechanism, and it is what makes the finding a claim about *where the
information lives*, not merely about input length.

## Why this is a lower bound

The comparison model, `gemini-3.6-flash`, is a small/fast "Flash"-tier
model. Small models tend to *under*-exploit long inputs — long-context
comprehension degrades with scale — so a small model reading a full paper
is handicapped relative to a stronger one. The test is therefore biased
**against** full text. Full text wins anyway, by ~12×, so the effect is a
**conservative lower bound**: a stronger extraction model would widen the
gap, not close it.

Symmetric caution for anyone replicating: had full text *tied or lost* on
this model, that would have been *ambiguous* (small-model failure to use
long context), not evidence against full text. It did not — but the
asymmetry matters for interpreting a null result on a small model.

## Scope and limits of the claim

- Domain: LLM-calibration / uncertainty literature (the ResearchMap seed
  domain). The mechanism (own-work limitations and future work live in
  discussion sections) is domain-general, but the magnitudes are measured
  here only.
- n=21 is small; the effect size (>10×) is large relative to n, but the
  point estimate has wide uncertainty. The claim is directional and
  order-of-magnitude, not a precise multiplier.
- Full-text coverage is ~70% (arXiv); the remaining ~30% are abstract-only
  and carry the abstract-arm yield. Any corpus mixing the two must flag
  `abstract_only` so downstream scoring can correct for mixed-fidelity
  bias.
- "Viability" is defined operationally: at 0.19 own-work limitations/paper,
  a ~200-paper corpus yields ~40 total — too sparse for cross-paper
  recurrence detection (the persistent-limitations scorer) or orphaned
  future-work detection. At 2.19/paper (~440 total) those scorers have
  enough input to run. The finding is that full text crosses that
  operational threshold and abstracts do not.

## Provenance

- Numbers: `data/live_samples/abstract_vs_fulltext_numbers.json`
- Method + full accounting: `docs/abstract-vs-fulltext.md`
- Extractions: cached under `gemini:gemini-3.6-flash`, `input_source ∈
  {abstract, fulltext}`, `prompt_hash eb8a0554bc13`.
- Total cost of the two extraction arms: $0.83 (batch-discounted full-text
  arm).
