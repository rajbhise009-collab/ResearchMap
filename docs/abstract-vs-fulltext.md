# Abstract vs. full text — controlled extraction comparison

**Status: PARTIAL — the extraction comparison is blocked on the
Gemini free-tier daily quota (see below). Methodology and full-text
coverage are final; the numeric comparison table is PENDING a quota
reset or a higher-quota key.**

## Question

Does extracting from arXiv full text instead of the abstract yield
materially more of what the reasoning-engine scorers need — own-work
limitations and future-work items — which the abstract-only run
starved (~8 own-work limitations, ~6 future-work items across 30
papers)?

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
| Model | `gemini-3.6-flash` (identical) |
| Prompt | `v1.1.0` (identical, `prompt_hash` identical) |
| Only variable | input source: **abstract** vs. **full text** |

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

Full-text sizes: 6.5k–99k tokens (mean ~22k). The largest is well
under Gemini 3.6 Flash's context, so the chunker (`chunk_fulltext`)
stays dormant on this corpus — a documented safety mechanism, not an
active path here.

**The comparison below is over the 21 papers with full text**, so
that abstract-side and fulltext-side counts are on the same set.

## PAIRED comparison table — PENDING (quota-blocked)

Filled by `python -m backend.app.corpus.compare_abstract_fulltext` once
both v1.1.0 extraction sets exist. **Both columns are over the SAME 21
paired papers.**

| Metric (per paper, n=21 paired) | Abstract (v1.1.0) | Full text (v1.1.0) | Δ / ratio |
|:--------------------------------|:-----------------:|:------------------:|:---------:|
| Claims / paper | _pending_ | _pending_ | |
| Limitations / paper | _pending_ | _pending_ | |
| **Own-work (`this_work`) limitations / paper** | _pending_ | _pending_ | |
| Prior-work limitations / paper | _pending_ | _pending_ | |
| **Future-work items / paper** | _pending_ | _pending_ | |
| Methodologies / paper | _pending_ | _pending_ | |
| `source_scope` agreement vs hand labels | _pending_ | _pending_ | |
| Tokens in / out per paper | _pending_ | _pending_ | |

The two bold rows are the whole point: full text must lift own-work
limitations and future-work items above the threshold where the two
starved scorers become viable. **The verdict — does it or doesn't
it — goes here in plain language, including "it doesn't" if that is
what the numbers say.**

### 30-paper abstract set (CONTEXT ONLY — different, larger set)

Reported separately so it is never confused with the paired
comparison. These are the v1.1.0 abstract extractions over all 30
papers (21 paired + 9 abstract_only).

| Metric (per paper, n=30) | v1.1.0 abstract |
|:-------------------------|:---------------:|
| Claims / paper | _pending_ |
| Own-work limitations / paper | _pending_ |
| Future-work items / paper | _pending_ |

### v1.0.0 → v1.1.0 diff (CONTEXT — 30-paper abstract set)

Whether the v1.1.0 prompt changes moved the numbers vs. the v1.0.0
baseline (both 30-paper abstract runs, same model).

| Metric (per paper, n=30 abstract) | v1.0.0 | v1.1.0 | Δ |
|:----------------------------------|:------:|:------:|:--:|
| Claims / paper | 5.9 | _pending_ | |
| Own-work limitations / paper | ~0.4 | _pending_ | |
| `source_scope` agreement vs hand | 73% | _pending_ | |
| Promotional claims (spot-check) | present | _pending_ | |

## Why this is blocked, and how to resume

The `gemini-3.6-flash` **free-tier daily request quota** (`quotaId:
GenerateRequestsPerDayPerProjectPerModel-FreeTier`) was exhausted by
today's runs (the v1.0.0 baseline of 30 + the v1.1.0 abstract re-run).
Confirmed via a `QuotaFailure` response, not inferred.

State at the wall:
- v1.1.0 **abstract** extraction: **8 / 30 complete**, cached.
- v1.1.0 **fulltext** extraction: **0 / 21**.
- Full-text retrieval: **21 / 30 complete** (no Gemini quota used).

Everything is cached and idempotent, so resuming loses no work. When
the quota resets (daily, ~midnight Pacific) OR with a higher-quota
key, two commands finish the experiment:

```
# finish the v1.1.0 abstract run (22 remaining; 8 are cache hits)
python -m backend.app.corpus.run_live_extraction

# run the v1.1.0 fulltext extraction over the 21 full-text papers
python -m backend.app.corpus.run_live_extraction --input-source fulltext
```

Then this table gets filled from the two runs' per-paper reports and
the cached extractions, and `PROGRESS.md` updated.

**Alternative if you don't want to wait:** approve a different free
model with a separate daily quota (e.g. `gemini-2.5-flash-lite`, still
available). Caveat: that makes v1.1.0 not directly comparable to the
`gemini-3.6-flash` v1.0.0 baseline — but the abstract-vs-fulltext
comparison stays internally valid as long as BOTH sides use the same
model. Set `GEMINI_MODEL` and the client validates it at startup.
