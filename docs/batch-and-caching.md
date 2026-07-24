# Batch mode & context caching — for the 200-paper run

Both are cost/throughput optimizations for the **full 200-paper corpus
run only**. Neither is used for the 21-paper abstract-vs-fulltext
comparison — that run must stay byte-for-byte identical to the abstract
arm (synchronous `generateContent`, no batch, no cache indirection), or
it confounds input source with request path.

## Batch mode — WIRED

`backend/app/extraction/batch_client.py` (`GeminiBatchClient`).

- **Why**: 50% of standard cost, target 24h turnaround (usually
  faster). Non-urgent full-corpus full-text extraction is the textbook
  use case.
- **Endpoints**: `POST /models/{model}:batchGenerateContent` to submit
  inline requests (each tagged with a `metadata.key` = paper id);
  `GET /batches/{id}` to poll `state`; results collected from the
  succeeded job's inline responses, mapped back by key.
- **Sizing**: inline batches cap at 20MB. `chunk_requests` splits the
  corpus into <18MB sub-batches deterministically (sorted keys). The
  full-text 200-paper corpus (papers up to ~99k tokens ≈ 400KB each)
  will span a few sub-batches.
- **Provenance**: batch extractions carry `model = gemini-batch:<model>`
  in the cache key and `PaperExtractionRow`, so they never collide with
  synchronous ones and the comparison stays clean.
- **NOT executed yet**: the client is built and unit-tested (HTTP
  mocked). A live batch submission belongs to the 200-paper run, which
  needs its own spend approval.
- **Free-tier caveat**: batch mode on the free tier shares the same
  daily quota pool, so it does not rescue a free-tier daily-cap
  exhaustion — its win is cost (50% off) on a paid tier, plus not
  tying up a synchronous connection.

## Context caching — DECLINED (with reasoning), implicit caching noted

Explicit context caching (`cachedContents` create + reference) is
**deliberately not wired**, because it does not fit this workload:

1. **The only shared content is the instruction prefix (~1,500
   tokens).** Explicit caching has a **minimum of 2,048–4,096 tokens**
   (model-dependent). Our prefix is below that floor, so it cannot be
   cached explicitly.
2. **Each paper's body is unique.** Context caching pays off when many
   requests share a *large* common context (e.g. one long document
   queried repeatedly). Our pattern is the opposite: a small shared
   prefix + a large unique body per paper. There is nothing large to
   cache and reuse.

**Implicit caching is already on** for Gemini 2.5+ models (so
3.6-flash) and opportunistically discounts the repeated instruction
prefix when it can, with zero code. The prompt is already structured
prefix-first (static instructions + schema, then the variable paper
block), which is the layout implicit caching rewards. Cached-token
counts, when they occur, appear in the response `usageMetadata`.

**If you want explicit caching anyway** (e.g. a future workload with a
genuinely large shared context — a fixed rubric document, few-shot
exemplars over the min-token floor), say so and it's a small addition:
create one `cachedContents` object for the shared block and reference
its name in each `generateContent` call. It just isn't worth it for
per-paper extraction with a sub-floor prefix.

## Summary

| Optimization | Status | Applies to |
|:-------------|:-------|:-----------|
| Batch mode (50% off) | wired + tested, not executed | 200-paper run |
| Implicit context caching | auto-on for 3.6-flash | all runs (free) |
| Explicit context caching | declined — sub-floor prefix, unique bodies | n/a |
| 21-paper comparison | synchronous, no batch/explicit-cache | comparison only |
