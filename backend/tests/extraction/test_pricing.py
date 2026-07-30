"""Pricing — the thinking-token correction must never regress (it caused
a ~40% cost under-report and mis-calibrated every dry-run gate)."""

from __future__ import annotations

from backend.app.extraction import pricing


def test_billed_output_includes_thinking_tokens():
    usage = {"candidatesTokenCount": 100, "thoughtsTokenCount": 900,
             "promptTokenCount": 5000}
    # Output that BILLS is visible + hidden thinking, not just candidates.
    assert pricing.billed_output_tokens(usage) == 1000


def test_billed_output_handles_missing_fields():
    assert pricing.billed_output_tokens({"candidatesTokenCount": 50}) == 50
    assert pricing.billed_output_tokens({}) == 0


def test_cost_batch_is_half_of_standard():
    std = pricing.cost(1_000_000, 1_000_000, batch=False)
    bat = pricing.cost(1_000_000, 1_000_000, batch=True)
    assert std == pricing.IN_PER_M + pricing.OUT_PER_M
    assert bat == std * pricing.BATCH_MULT


def test_verified_rates():
    assert pricing.IN_PER_M == 1.50
    assert pricing.OUT_PER_M == 7.50
    assert pricing.BATCH_MULT == 0.5
