"""Stage-level spend gate — the pre-run check that sits in front of the
per-call ledger ceiling.

Before a paid stage starts:
  1. its projection is RECORDED (append-only `data/spend_projections.jsonl`,
     or the path in env `SPEND_PROJECTIONS_PATH`), whether or not it runs;
  2. the stage is REFUSED if projection x multiplier exceeds the ledger's
     remaining headroom (cap minus cumulative).

Multipliers (from the run briefs; past dry-runs undershot by up to 2.5x on
thinking-heavy stages):
  classification  x2.0
  extraction      x1.5

During a stage, `OverrunMonitor` halts once the running cost per call
exceeds projection x 1.5.

This module only gates. It never calls an API and never writes the ledger.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from backend.app.extraction.spend_ledger import SpendLedger

CLASSIFICATION_GATE_MULT = 2.0
EXTRACTION_GATE_MULT = 1.5
OVERRUN_FACTOR = 1.5

_REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECTIONS_PATH = _REPO_ROOT / "data" / "spend_projections.jsonl"


def projections_path() -> Path:
    env = os.environ.get("SPEND_PROJECTIONS_PATH")
    return Path(env) if env else PROJECTIONS_PATH


class SpendGateRefused(RuntimeError):
    """The stage's padded projection does not fit the remaining ceiling."""


def preflight(*, stage: str, projected_inr: float, n_calls: int,
              multiplier: float, ledger: SpendLedger | None = None) -> dict:
    """Record the projection, then refuse if projection x multiplier exceeds
    remaining headroom. Returns the recorded row (with `allowed`)."""
    ledger = ledger or SpendLedger.load()
    snap = ledger.snapshot()
    padded = projected_inr * multiplier
    row = {
        "ts": time.time(), "stage": stage, "n_calls": n_calls,
        "projected_inr": round(projected_inr, 4),
        "multiplier": multiplier, "padded_inr": round(padded, 4),
        "cumulative_inr": round(snap["cumulative_inr"], 4),
        "cap_inr": snap["cap_inr"],
        "remaining_inr": round(snap["remaining_inr"], 4),
        "allowed": padded <= snap["remaining_inr"],
    }
    p = projections_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    if not row["allowed"]:
        raise SpendGateRefused(
            f"stage {stage!r}: projection ₹{projected_inr:.2f} x{multiplier} = "
            f"₹{padded:.2f} exceeds remaining ₹{snap['remaining_inr']:.2f} "
            f"(cap ₹{snap['cap_inr']:.2f}, spent ₹{snap['cumulative_inr']:.2f}). "
            "Not started.")
    return row


class OverrunMonitor:
    """Tracks actual spend since construction; `check(calls)` returns a halt
    reason once the running cost per call exceeds projection x factor.
    Checked from `min_calls` onward so one long first response can't halt a
    stage on its own."""

    def __init__(self, projected_inr_per_call: float, *,
                 factor: float = OVERRUN_FACTOR, min_calls: int = 3,
                 ledger: SpendLedger | None = None):
        self.per_call = projected_inr_per_call
        self.factor = factor
        self.min_calls = min_calls
        self.ledger = ledger or SpendLedger.load()
        self.start = self.ledger.snapshot()["cumulative_inr"]

    def spent(self) -> float:
        return self.ledger.snapshot()["cumulative_inr"] - self.start

    def check(self, calls: int) -> str | None:
        if calls < self.min_calls or not self.per_call:
            return None
        actual = self.spent() / calls
        if actual > self.per_call * self.factor:
            return (f"cost per call ₹{actual:.4f} exceeds {self.factor}x "
                    f"projection ₹{self.per_call:.4f}")
        return None


__all__ = ["CLASSIFICATION_GATE_MULT", "EXTRACTION_GATE_MULT", "OVERRUN_FACTOR",
           "SpendGateRefused", "preflight", "OverrunMonitor", "projections_path"]
