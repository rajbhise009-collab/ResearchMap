"""gemini-3.6-flash pricing — the single source of truth for cost.

Rates VERIFIED 2026-07-26 against Google's published pricing (two
independent sources; confirmed by reconciling actual console spend):
  input  $1.50 / 1M tokens
  output $7.50 / 1M tokens
  batch  50% off both (0.75 / 3.75)

CRITICAL — thinking tokens. gemini-3.6-flash is a reasoning model: each
response carries a `thoughtsTokenCount` that is billed AT THE OUTPUT
RATE but is NOT part of `candidatesTokenCount`. Earlier accounting
counted only candidates and under-reported spend by ~40% (a "$3" gate
was really ~$5). Billed output = candidates + thoughts. Always use
`billed_output_tokens()`.
"""

from __future__ import annotations

IN_PER_M = 1.50
OUT_PER_M = 7.50
BATCH_MULT = 0.5

# Projection factors for dry-runs (output tokens per unit, INCLUDING
# thinking, from observed usage 2026-07). Thinking is task-dependent, so
# these are per-task and deliberately padded upward — a gate must never
# under-project.
OUT_TOKENS_ABSTRACT = 2500     # abstract extraction (obs ~1.1k cand + thinking)
OUT_TOKENS_FULLTEXT = 5000     # full-text extraction (obs ~2.3k cand + ~2.2k thoughts)
OUT_TOKENS_PAIR = 380          # contradiction pair (obs ~360 cand+thoughts; heavy thinking)


def billed_output_tokens(usage: dict) -> int:
    """Output tokens that actually bill = visible output + hidden thinking."""
    return int(usage.get("candidatesTokenCount", 0) or 0) + \
        int(usage.get("thoughtsTokenCount", 0) or 0)


def cost(in_tokens: int, out_tokens: int, *, batch: bool = False) -> float:
    """Dollar cost. `out_tokens` MUST already include thinking tokens
    (use billed_output_tokens for actuals)."""
    mult = BATCH_MULT if batch else 1.0
    return (in_tokens * IN_PER_M / 1e6 + out_tokens * OUT_PER_M / 1e6) * mult


__all__ = [
    "IN_PER_M", "OUT_PER_M", "BATCH_MULT",
    "OUT_TOKENS_ABSTRACT", "OUT_TOKENS_FULLTEXT", "OUT_TOKENS_PAIR",
    "billed_output_tokens", "cost",
]
