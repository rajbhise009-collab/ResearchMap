# Abstract vs. full text — controlled extraction comparison

**Status: COMPLETE.** Both v1.1.0 extraction sets exist (arm 2 abstracts
standard tier; arm 3 full text via the Gemini batch API, 50% off), all on
`gemini-3.6-flash` at temperature 0. Numbers below are final, produced by
`python -m backend.app.corpus.compare_abstract_fulltext`
(`data/live_samples/abstract_vs_fulltext_numbers.json`).

## Question

Does extracting from arXiv full text instead of the abstract yield
materially more of what the reasoning-engine scorers need — own-work
limitations and future-work items — which the abstract-only run
starved (~0.2 own-work limitations and ~0.2 future-work items per
paper)?

**Answer: yes, decisively.** Full text lifts own-work limitations
**11.5×** (0.19 → 2.19 per paper) and future-work items **12.6×**
(0.14 → 1.76 per paper). See the verdict below.

## Design (clean single-variable comparison — PAIRED)

The comparison runs on the **21 papers that have BOTH an abstract and
full text** — same paper set on both sides, so the only variable is
input source. Comparing 30 abstracts against 21 full texts would
confound input source with paper set: the 9 full-text misses are all
journal-only, and journal papers may report limitations differently
than arXiv preprints, so a 30-vs-21 comparison would measure a
venue-mix difference on top of the input-source difference.

| Axis | Value |
|:-----|:------|
| Papers | the **21** papers with both abstract and full text (paired) |
| Model | `gemini-3.6-flash` (identical, temp 0) |
| Prompt | `v1.1.0` (identical, `prompt_hash` `eb8a0554bc13`) |
| Only variable | input source: **abstract** vs. **full text** |

The abstract arm ran on the synchronous standard tier; the full-text
arm ran through the **batch API** (50% off, ~93 s turnaround here).
Batch is the *same model at temp 0* — a delivery mechanism, not a model
change — so both arms cache under the same `gemini:gemini-3.6-flash`
identity, and the comparison stays single-variable.

The 30-paper abstract numbers are reported **separately, clearly
labelled as a different (larger) set**, for context only — they are
NOT the comparison.

The `input_source` dimension is part of the cache key and provenance
(`extraction_id`, `PaperExtractionRow.input_source`, migration 006),
so the two runs coexist without collision and are individually
traceable.

## Full-text coverage (final)

Retrieved via `backend/app/corpus/retrieve_corpus_fulltext.py` (arXiv,
free). Manifest: `data/live_samples/fulltext_manifest.json`.

| | count |
|:--|--:|
| Full text recovered | **21 / 30 (70%)** |
| abstract_only (kept, flagged) | 9 |

The 9 abstract_only papers are all journal-only (IEEE Intelligent
Systems, Scientific Reports ×2, Zenodo, Preprints.org, ACM Computing
Surveys [PDF fetch failed — likely paywalled], and 3 off-domain
journals). Coverage skews toward on-domain arXiv preprints — which is
the right direction, since on-domain papers are the ones the reasoning
engine most needs full text for.

Full-text sizes: 6.5k–99k tokens (mean ~22k; measured batch input
averaged 27.3k tokens/paper incl. prompt). The largest is well under
Gemini 3.6 Flash's context, so the chunker (`chunk_fulltext`) stayed
dormant on this corpus — a documented safety mechanism, not an active
path here. No call shipped more than one paper's text; one extraction
call per paper, no multi-pass.

**The comparison below is over the 21 papers with full text**, so
that abstract-side and fulltext-side counts are on the same set.

## PAIRED comparison table (n=21, same papers both columns)

Both columns are over the SAME 21 paired papers, same model, same
prompt — only the input source differs.

| Metric (per paper, n=21 paired) | Abstract (v1.1.0) | Full text (v1.1.0) | ratio |
|:--------------------------------|:-----------------:|:------------------:|:-----:|
| Claims / paper | 4.10 | 6.10 | 1.5× |
| Limitations / paper | 1.29 | 3.62 | 2.8× |
| **Own-work (`this_work`) limitations / paper** | **0.19** | **2.19** | **11.5×** |
| Prior-work limitations / paper | 1.10 | 1.43 | 1.3× |
| **Future-work items / paper** | **0.14** | **1.76** | **12.6×** |
| Methodologies / paper | 1.19 | 1.48 | 1.2× |
| Tokens in / out per paper | 1,639 / 1,103 | 27,288 / 2,218 | 16.6× in |

The two bold rows are the whole point.

## VERDICT — does full text lift the two starved scorers above viability?

**Yes — unambiguously, and it is the difference between the two
scorers being runnable and not.**

- **Persistent-limitations scorer** (needs own-work limitations to find
  the same limitation recurring across independent papers): abstracts
  yield **0.19 own-work limitations/paper** — across the 21 papers that
  is ~4 total, far too sparse to find any limitation attested by
  multiple papers. Full text yields **2.19/paper** (~46 total over the
  same 21), an **11.5×** lift. At corpus scale (~200 papers) that is the
  difference between ~40 own-work limitations (no cross-paper recurrence
  possible) and ~440 (recurrence detectable). This scorer is **not
  viable on abstracts and becomes viable on full text.**

- **Orphaned-future-work scorer** (needs future-work items to find
  directions no later paper addressed): abstracts yield **0.14
  future-work items/paper** — ~3 total across 21 papers, nothing to
  reason over. Full text yields **1.76/paper** (~37 total), a **12.6×**
  lift. Same story at corpus scale: ~40 → ~350 items. This scorer is
  **not viable on abstracts and becomes viable on full text.**

The lifts are concentrated exactly where they were needed: prior-work
limitations (already adequately captured from abstracts) barely moved
(1.3×), while the two starved, own-paper-scoped signals moved an order
of magnitude. Abstracts systematically omit a paper's own limitations
and future directions — authors put those in the discussion/conclusion
sections, which only full text contains. This is the expected
mechanism, and the data matches it.

**Plain statement:** on abstracts, the persistent-limitations and
orphaned-future-work scorers do not have enough input to produce
meaningful output; on full text they do. Phase 3/4 scoring of these two
gap types must run on full-text extractions, not abstracts.

### Interpretation strength — this is a conservative (lower-bound) result

The comparison model, `gemini-3.6-flash`, is a small/fast "Flash"-tier
model. A smaller model tends to exploit a long full-text input *less*
well than a short abstract — long-context comprehension is where small
models degrade — so this measurement is **biased AGAINST full text**:
the full-text arm is handicapped relative to a stronger model.

Because full text **wins anyway, and by ~12×**, the finding holds
**conservatively**: a stronger extraction model would only widen the
gap, not close it. (Had full text merely tied or lost, the result would
have been ambiguous rather than negative — but that is not the regime
the numbers fall into.)

> Note: an earlier draft of this doc named `gemini-2.5-flash-lite` as
> the comparison model, from a period when free-tier daily quotas forced
> a model switch. That is superseded — paid billing removed the quota
> wall and the entire experiment (both v1.1.0 arms) ran on
> `gemini-3.6-flash`, keeping it directly comparable to the v1.0.0
> baseline.

### 30-paper abstract set (CONTEXT ONLY — different, larger set)

Reported separately so it is never confused with the paired
comparison. v1.1.0 abstract extractions over all 30 papers (21 paired +
9 abstract_only).

| Metric (per paper, n=30) | v1.1.0 abstract |
|:-------------------------|:---------------:|
| Claims / paper | 4.20 |
| Own-work limitations / paper | 0.20 |
| Future-work items / paper | 0.20 |

Consistent with the paired abstract column — the 9 abstract_only papers
do not shift the abstract-side picture, so the paired subset is
representative of the abstract arm.

### v1.0.0 → v1.1.0 diff (CONTEXT — 30-paper abstract set)

Both 30-paper abstract runs, same model (`gemini-3.6-flash`).

| Metric (per paper, n=30 abstract) | v1.0.0 | v1.1.0 | Δ |
|:----------------------------------|:------:|:------:|:--:|
| Claims / paper | 5.97 | 4.20 | −1.77 |
| Own-work limitations / paper | 0.33 | 0.20 | −0.13 |
| Prior-work limitations / paper | 1.07 | 1.07 | 0 |
| Methodologies / paper | 1.20 | 1.10 | −0.10 |

v1.1.0 is slightly more conservative on abstracts (fewer claims, fewer
own-work limitations) — consistent with its tightened `source_scope`
discipline suppressing over-attribution. This does not affect the
abstract-vs-fulltext conclusion, which is measured within v1.1.0 on both
sides. Note that even v1.0.0's more liberal 0.33 own-work
limitations/paper is still an order of magnitude below full text's 2.19
— the starvation is a property of abstracts, not of the prompt version.

## Cost & run accounting (final)

| | Arm 2 abstract (std) | Arm 3 full text (batch) |
|:--|--:|--:|
| Papers extracted | 21 fresh (+9 cache hits = 30) | 21 |
| Input tokens | 34,434 | 573,050 |
| Output tokens | 23,176 | 46,592 |
| Cost | $0.2255 | $0.6045 |
| Retries (rpm/tpm/5xx/conn/schema) | 0 / 0 / 0 / 0 / 0 | n/a (batch) |
| Hard-failures | 0 | 0 |

**Total spend: $0.83** (of the $3 cap; under the $1.16 pre-spend
projection). Dry-run over-estimated input (661k projected vs 573k
actual) — over-estimate in the safe direction, as intended. The 9
cached v1.1.0 abstracts registered as HITS, not re-extractions, as
verified by the dry-run before any paid call.
