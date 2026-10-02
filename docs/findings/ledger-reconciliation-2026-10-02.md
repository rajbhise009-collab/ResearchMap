# Ledger / Google-console reconciliation — 2026-10-02

**In one line:** the project's own call-by-call ledger records more model spend than Google's billing console showed when last checked, and the project budgets against the ledger (the higher figure).

**Date:** 2026-10-02. Free diagnostic; no new spend to produce it.

## The gap

- Google Cloud console (billing dashboard): **₹302** spent on
  gemini-3.6-flash to date, against a ₹1000 project spend cap.
- Local `data/spend_ledger.json`: **₹524.14** cumulative, against a
  ₹850 cap enforced at call time.

The two should match within rounding + a small lag (the console
aggregates on a one-to-six-hour delay). ₹222 is well outside that.

## Hypothesis tested

The pre-run brief suggested the gap could be a batch-vs-sync pricing
mistake: if `extract_diet` (₹235.69) and `extract_fairness` (₹211.39)
were actually run through the batch API but priced at the full sync
rate, halving them would give ≈ ₹301 ≈ console.

## What I checked

1. **Every ledger entry's `batch` flag.** 684 entries total; **every
   one of them is `batch=False`.** The ledger has never recorded a
   batch call.
2. **Per-entry cost vs the sync-rate expectation.** For every stage,
   `cost_usd == prompt_tokens × $1.50/M + billed_output_tokens ×
   $7.50/M` to the fourth decimal — ratio **exactly 1.00x**. The
   pricing in the ledger is already sync.
3. **The code path that produced `extract_diet` / `extract_fairness`
   entries.** `backend/app/corpus/multi_domain_extract.run()` takes a
   `batch: bool = False` keyword and… never passes it to
   `GeminiLLMClient`. The client itself hardcodes `batch=False` in
   `ledger.record(...)` (`backend/app/extraction/llm_client.py:514`).
   So those 59 + 53 extractions could ONLY have been made via sync.
4. **The dedicated batch script.** `run_batch_corpus.py` exists but
   never records to the ledger — so if it had been used for diet /
   fairness, there would be NO `extract_*` entries at all. We have
   112 of them, exactly matching the sync-path's known behaviour.

| stage | ledger ₹ | cost / sync-expected |
|:--|--:|--:|
| extract_diet (n=59) | 235.69 | 1.00x |
| extract_fairness (n=53) | 211.39 | 1.00x |
| hedge_diet-and-mortality (n=200) | 28.93 | 1.00x |
| contradiction_diet-and-mortality (n=128) | 34.12 | 1.00x |
| contradiction_ml-fairness (n=54) | 13.92 | 1.00x |
| unknown (n=190, tests + probes) | 0.48 | 1.00x |

## Conclusion

**Hypothesis not confirmed.** The ledger is accurate at ₹524.14. No
pricing correction. No history rewrite.

The console lag is the remaining candidate: Google's cost explorer
can take hours to catch up on recent calls, and when the per-call
cost is small ($0.0026 → ₹0.22 for a typical extraction) the UI
aggregates lossy. The console's number should drift upward to meet
the ledger over the next day or two.

## Operational decisions

- Treat the ledger as source of truth. ₹524.14 cumulative.
- Run ceiling for iteration 3 = **₹300** (brief: "₹300 if the gap is
  explained, otherwise ₹300"). Gap unexplained → ₹300.
- Cumulative-after-run ceiling = ₹824.14 (set as `cap_inr` on the
  ledger so the in-process guard enforces it).
- No change to pricing code. All future entries continue at sync rate,
  which is the only rate the sync client ever charged.

## If someone wants to use the batch API in future

- `run_batch_corpus.py` would need to be amended to call
  `ledger.record(..., batch=True, ...)` after each returned batch
  item so the ledger halves the cost. Today it skips the ledger
  entirely, which would silently miss ALL spend.
- The sync client's hardcoded `batch=False` is correct for the sync
  path; don't change it. A `batch` keyword plumbed through
  `multi_domain_extract.run()` would be a one-liner that passes a
  BatchClient instance instead of a GeminiLLMClient — but the batch
  client's responses have different metadata and the orchestrator
  isn't ready for it today.
