"""Mandatory pre-spend dry-run: project the cost of arms 2 & 3.

No API calls. For every paper that is NOT already cached, render the
exact prompt it would send and estimate input tokens (chars/3, the same
conservative estimator the TPM guard uses). Output tokens are estimated
from observed per-paper averages, rounded UP (safe direction for a cost
cap). Applies gemini-3.6-flash rates; arm 3 gets the batch 50% discount.

Also VERIFIES the 9 cached v1.1.0 abstracts register as cache HITS
before any spend — a miss here would re-pay for done work.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.extractor import Extractor  # noqa: E402
from backend.app.extraction.prompt_versions import load  # noqa: E402
from backend.app.extraction.rate_limiter import estimate_tokens  # noqa: E402
from backend.app.ingestion.fulltext import load_cached_fulltext  # noqa: E402
from backend.app.corpus.run_live_extraction import (  # noqa: E402
    stratify_thirty,
    _load_papers_by_openalex_id,
)

MODEL = "gemini:gemini-3.6-flash"
V11 = load("v1.1.0").hash

# gemini-3.6-flash standard-tier rates ($/1M). NOTE: these are the rates
# recorded in PROGRESS.md from the pricing page and were flagged as not
# independently re-verified for 3.x; treat the dollar figures as
# indicative. Batch = 50% off.
IN_PER_M = 1.50
OUT_PER_M = 7.50
BATCH_MULT = 0.5

# Observed/estimated output tokens per paper (rounded UP for safety).
OUT_ABSTRACT = 1800    # v1.0.0 abstract run averaged ~1350-1550
OUT_FULLTEXT = 4000    # full text yields more claims/limits → higher, padded


def _render(extractor: Extractor, paper) -> str:
    return extractor._render(paper)


def main() -> int:
    picks = stratify_thirty()
    papers_by_oid = _load_papers_by_openalex_id()
    cache = ExtractionCache()

    # --- Arm 2: v1.1.0 abstracts (all 30; 9 should be cache hits).
    ex_abs = Extractor.__new__(Extractor)  # avoid live client; we only render
    # Minimal manual init for rendering + cache lookup:
    ex_abs._prompt = load("v1.1.0")
    ex_abs._input_source = "abstract"

    arm2_hits = arm2_miss = 0
    arm2_in = 0
    for r in picks:
        paper = papers_by_oid.get(r["openalex_id"])
        if paper is None:
            continue
        cached = cache.get(paper.id, MODEL, "abstract", V11)
        if cached is not None:
            arm2_hits += 1
            continue
        arm2_miss += 1
        arm2_in += estimate_tokens(_render(ex_abs, paper))
    arm2_out = arm2_miss * OUT_ABSTRACT
    arm2_cost = arm2_in / 1e6 * IN_PER_M + arm2_out / 1e6 * OUT_PER_M

    # --- Arm 3: v1.1.0 full text (21 with full text), BATCH-discounted.
    ex_ft = Extractor.__new__(Extractor)
    ex_ft._prompt = load("v1.1.0")
    ex_ft._input_source = "fulltext"

    arm3_hits = arm3_miss = 0
    arm3_in = 0
    max_single_in = 0
    for r in picks:
        paper = papers_by_oid.get(r["openalex_id"])
        if paper is None:
            continue
        ft = load_cached_fulltext(paper.id)
        if not ft:
            continue  # abstract_only — not in arm 3
        paper.fulltext = ft
        cached = cache.get(paper.id, MODEL, "fulltext", V11)
        if cached is not None:
            arm3_hits += 1
            continue
        arm3_miss += 1
        in_tok = estimate_tokens(_render(ex_ft, paper))
        arm3_in += in_tok
        max_single_in = max(max_single_in, in_tok)
    arm3_out = arm3_miss * OUT_FULLTEXT
    arm3_cost = (arm3_in / 1e6 * IN_PER_M + arm3_out / 1e6 * OUT_PER_M) * BATCH_MULT

    total = arm2_cost + arm3_cost

    print("=== PRE-SPEND DRY RUN (no API calls) ===\n")
    print(f"Rates: input ${IN_PER_M}/1M, output ${OUT_PER_M}/1M; "
          f"arm 3 batch = 50% off")
    print(f"Output/paper estimate (padded): abstract={OUT_ABSTRACT}, "
          f"fulltext={OUT_FULLTEXT}\n")

    print(f"ARM 2  v1.1.0 abstracts  (standard tier)")
    print(f"  cache HITS (skip, $0): {arm2_hits}")
    print(f"  to extract:            {arm2_miss}")
    print(f"  input tokens:  {arm2_in:>8,}")
    print(f"  output tokens: {arm2_out:>8,} (est)")
    print(f"  cost:          ${arm2_cost:.4f}\n")

    print(f"ARM 3  v1.1.0 full text  (BATCH, 50% off)")
    print(f"  cache HITS (skip, $0): {arm3_hits}")
    print(f"  to extract:            {arm3_miss}")
    print(f"  input tokens:  {arm3_in:>8,}  (largest single call: {max_single_in:,})")
    print(f"  output tokens: {arm3_out:>8,} (est)")
    print(f"  cost:          ${arm3_cost:.4f}\n")

    print(f"PROJECTED TOTAL: ${total:.4f}")
    print(f"Account cap: $3.00 | dry-run gate: $1.50")
    if total > 1.50:
        print("\n*** OVER $1.50 GATE — STOP and review the per-arm breakdown "
              "above before spending. ***")
    else:
        print("\nUnder the $1.50 gate — cleared to proceed.")

    # Cache-hit sanity: arm 2 must show 9 hits, arm 3 must show 0.
    print(f"\n[verify] arm-2 cache hits = {arm2_hits} (expected 9), "
          f"arm-3 cache hits = {arm3_hits} (expected 0)")
    return 0 if total <= 1.50 else 2


if __name__ == "__main__":
    raise SystemExit(main())
