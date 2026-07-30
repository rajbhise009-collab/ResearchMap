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
- **Provenance**: the client's own `name` is `gemini-batch:<model>`, but
  for the abstract-vs-fulltext comparison and the domain-corpus build the
  batch results are deliberately cached under the **synchronous**
  `gemini:<model>` identity. Batch is the same model at temp 0 — a
  delivery mechanism, not a model change — so caching under the sync
  identity keeps batch and synchronous extractions of the same
  (paper, input_source, prompt) directly comparable, which is exactly
  what the comparison needs. (`run_batch_fulltext.py` /
  `run_batch_corpus.py` set the cache model explicitly to `gemini:<model>`
  for this reason.)

## ⚠️ Batch mode has run exactly ONCE — verify collection every run

Batch mode was executed live for the first time on **2026-07-25** (arm 3
of the abstract-vs-fulltext comparison, 21 full-text papers). It is NOT a
well-worn path. One real bug surfaced on that first run:

- **`BATCH_STATE_*` vs `JOB_STATE_*`**: the live v1beta API reports job
  state as `BATCH_STATE_RUNNING` / `BATCH_STATE_SUCCEEDED`, but the
  client's terminal-state check only matched the `JOB_STATE_*` prefix
  documented on some surfaces. Left unfixed, `job.done`/`job.succeeded`
  would have stayed `False` forever and **collect would never fire** —
  the batch would silently never be harvested. Caught pre-collect by
  dumping the raw job and inspecting state; fixed to match on the state
  **suffix** (SUCCEEDED/FAILED/CANCELLED/EXPIRED) so both prefixes work;
  regression test `test_batchjob_terminal_flags_batch_state_prefix`.

- **Results shape (still single-path)**: `results()` parses only
  **inline** responses. The first run returned inline (21 keys, 0 empty),
  but the API *may* return a downloadable file for larger jobs. That path
  is not implemented. Every batch run MUST verify the collected count
  equals the submitted count before trusting the cache.

**Mandatory per-run check** (do not skip on the corpus run): after a
batch SUCCEEDS, confirm `len(results) == len(submitted)` and every result
is non-empty valid JSON with the right `paper_id`, THEN run the
validating collect and confirm the cached-file count rose by exactly the
number collected. If results come back empty or short, the job may be
file-based — stop and implement the file-download path rather than
accepting a partial corpus.
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
| Batch mode (50% off) | executed once (2026-07-25, 21 papers); collect-verify mandatory | corpus run |
| Implicit context caching | auto-on for 3.6-flash | all runs (free) |
| Explicit context caching | declined — sub-floor prefix, unique bodies | n/a |
| 21-paper comparison | synchronous, no batch/explicit-cache | comparison only |
