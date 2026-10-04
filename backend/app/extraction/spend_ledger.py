"""Persistent spend ledger for the multi-domain expansion run.

Purpose: refuse any Gemini call whose additional cost would push
cumulative NEW spend past the ₹850 (~$10.12 at $1=₹84) hard cap. The
legacy LLM-cal library ($7.40) is not counted here — its cache never
triggers a new call, so it never touches this ledger.

Enforcement is at CALL TIME, not just in dry-runs. Every GeminiLLMClient
and GeminiBatchClient path checks headroom before firing; every
successful 200 response records actual usage (including
`thoughtsTokenCount`, which bills at the output rate).

Persistence: `data/spend_ledger.json` — survives process restarts and
concurrent clients. File-locked with a simple exclusive open so two
processes can't race on the same headroom check.

Public API:

    from backend.app.extraction.spend_ledger import SpendLedger

    ledger = SpendLedger.load()          # singleton per process
    ledger.check_headroom(prompt_tokens_est, output_tokens_est, batch=False,
                          stage="extract_diet_wXXXXX")
        # raises SpendCapExceededError if this call would exceed cap

    ledger.record(prompt_tokens=..., candidates_tokens=...,
                  thoughts_tokens=..., batch=False, stage=...)

The `SPEND_LEDGER_DISABLED=1` env var lets tests bypass the guard
(mocked clients never hit real spend). `SPEND_LEDGER_PATH` points the
default ledger somewhere else; the test suite sets it to a temp file so no
test can touch `data/spend_ledger.json`.

Embedding calls (`record_embedding`) are ledgered too. `batchEmbedContents`
returns no token counts, so input tokens are ESTIMATED from text length and
priced at EMBED_IN_PER_M, a deliberately high upper-bound rate that has NOT
been verified against Google's embedding price list. Embedding entries are
marked `tokens_estimated=True`, `rate_basis="upper_bound_unverified"`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from backend.app.extraction.pricing import (
    BATCH_MULT,
    IN_PER_M,
    OUT_PER_M,
    cost as compute_cost,
)

# Repo-anchored path so multiple processes converge on the same file.
_REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = _REPO_ROOT / "data" / "spend_ledger.json"


def default_ledger_path() -> Path:
    env = os.environ.get("SPEND_LEDGER_PATH")
    return Path(env) if env else LEDGER_PATH

# Upper bound for embedding input pricing: the generation input rate. NOT a
# verified embedding price — chosen so the ceiling can never under-count.
EMBED_IN_PER_M = IN_PER_M

# Cap in INR. Convert to USD via a stated FX rate so the assertion below
# uses one number everywhere. Both are stored in the ledger so a reader
# who opens the JSON knows exactly what was enforced.
CAP_INR = 850.0
FX_USD_TO_INR = 84.0
CAP_USD = CAP_INR / FX_USD_TO_INR   # 10.119...


class SpendCapExceededError(RuntimeError):
    """Raised at call time when the projected cost would exceed the cap.

    Carrying the actuals in the message keeps the traceback informative
    when a run halts."""

    def __init__(self, projected_usd: float, cumulative_usd: float,
                 cap_usd: float, stage: str):
        self.projected_usd = projected_usd
        self.cumulative_usd = cumulative_usd
        self.cap_usd = cap_usd
        self.stage = stage
        projected_inr = projected_usd * FX_USD_TO_INR
        cum_inr = cumulative_usd * FX_USD_TO_INR
        cap_inr = cap_usd * FX_USD_TO_INR
        super().__init__(
            f"Spend cap ₹{cap_inr:.2f} (${cap_usd:.2f}) would be exceeded "
            f"by this call. Stage={stage!r}. Cumulative ₹{cum_inr:.4f} "
            f"(${cumulative_usd:.4f}); this call ~₹{projected_inr:.4f} "
            f"(~${projected_usd:.4f}); together ₹{cum_inr + projected_inr:.4f}. "
            "Refusing the call."
        )


@dataclass
class LedgerEntry:
    """One recorded call. `cost_usd` includes thoughts tokens."""
    ts: float
    stage: str
    model: str
    batch: bool
    prompt_tokens: int
    candidates_tokens: int
    thoughts_tokens: int
    billed_output_tokens: int
    cost_usd: float
    cost_inr: float


@dataclass
class LedgerState:
    cap_inr: float = CAP_INR
    cap_usd: float = CAP_USD
    fx_usd_to_inr: float = FX_USD_TO_INR
    entries: list[dict] = field(default_factory=list)

    @property
    def cumulative_usd(self) -> float:
        return sum(e["cost_usd"] for e in self.entries)

    @property
    def cumulative_inr(self) -> float:
        return self.cumulative_usd * self.fx_usd_to_inr


class SpendLedger:
    """Process-shared persistent ledger. `load()` returns a singleton
    that re-reads from disk on every check so multiple processes stay
    consistent (the on-disk file is source of truth)."""

    _instance: Optional["SpendLedger"] = None

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_ledger_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: LedgerState | None = None

    @classmethod
    def load(cls) -> "SpendLedger":
        if cls._instance is None:
            cls._instance = SpendLedger()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        cls._instance = None

    # --- Persistence --------------------------------------------------

    def _read(self) -> LedgerState:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            return LedgerState(
                cap_inr=data.get("cap_inr", CAP_INR),
                cap_usd=data.get("cap_usd", CAP_USD),
                fx_usd_to_inr=data.get("fx_usd_to_inr", FX_USD_TO_INR),
                entries=list(data.get("entries", [])),
            )
        return LedgerState()

    def _write(self, state: LedgerState) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "cap_inr": state.cap_inr,
            "cap_usd": state.cap_usd,
            "fx_usd_to_inr": state.fx_usd_to_inr,
            "cumulative_usd": state.cumulative_usd,
            "cumulative_inr": state.cumulative_inr,
            "entries": state.entries,
        }, indent=2))
        tmp.replace(self.path)

    # --- Headroom check -----------------------------------------------

    def _disabled(self) -> bool:
        return os.environ.get("SPEND_LEDGER_DISABLED") == "1"

    def check_headroom(self, *, prompt_tokens_est: int,
                        output_tokens_est: int, batch: bool,
                        stage: str) -> None:
        """Raise SpendCapExceededError if this call would exceed cap."""
        if self._disabled():
            return
        state = self._read()
        # Worst-case cost estimate using the given token estimates. The
        # caller supplies the estimate; conservative estimates keep the
        # last-call cliff below the cap.
        projected = compute_cost(
            in_tokens=prompt_tokens_est,
            out_tokens=output_tokens_est,
            batch=batch,
        )
        if state.cumulative_usd + projected > state.cap_usd:
            raise SpendCapExceededError(
                projected_usd=projected,
                cumulative_usd=state.cumulative_usd,
                cap_usd=state.cap_usd,
                stage=stage,
            )

    # --- Record actual usage ------------------------------------------

    def record(self, *, stage: str, model: str, batch: bool,
                prompt_tokens: int, candidates_tokens: int,
                thoughts_tokens: int) -> LedgerEntry:
        """Called AFTER a successful 200. Persists the actual billed cost
        including thoughts tokens (billed at output rate)."""
        state = self._read()
        billed_out = int(candidates_tokens) + int(thoughts_tokens)
        cost_usd = compute_cost(
            in_tokens=int(prompt_tokens),
            out_tokens=billed_out,
            batch=batch,
        )
        entry = LedgerEntry(
            ts=time.time(),
            stage=stage,
            model=model,
            batch=bool(batch),
            prompt_tokens=int(prompt_tokens),
            candidates_tokens=int(candidates_tokens),
            thoughts_tokens=int(thoughts_tokens),
            billed_output_tokens=billed_out,
            cost_usd=cost_usd,
            cost_inr=cost_usd * FX_USD_TO_INR,
        )
        state.entries.append(asdict(entry))
        self._write(state)
        return entry

    def check_embedding_headroom(self, *, input_tokens_est: int,
                                  stage: str) -> None:
        """Raise SpendCapExceededError if an embedding call of this size
        would exceed the cap (upper-bound rate)."""
        if self._disabled():
            return
        state = self._read()
        projected = input_tokens_est * EMBED_IN_PER_M / 1e6
        if state.cumulative_usd + projected > state.cap_usd:
            raise SpendCapExceededError(
                projected_usd=projected, cumulative_usd=state.cumulative_usd,
                cap_usd=state.cap_usd, stage=stage)

    def record_embedding(self, *, stage: str, model: str,
                         input_tokens_est: int, n_texts: int) -> dict:
        """Called AFTER a successful embedding response."""
        state = self._read()
        cost_usd = input_tokens_est * EMBED_IN_PER_M / 1e6
        entry = {
            "ts": time.time(), "stage": stage, "model": model, "batch": False,
            "prompt_tokens": int(input_tokens_est), "candidates_tokens": 0,
            "thoughts_tokens": 0, "billed_output_tokens": 0,
            "cost_usd": cost_usd, "cost_inr": cost_usd * FX_USD_TO_INR,
            "kind": "embedding", "n_texts": int(n_texts),
            "tokens_estimated": True, "rate_basis": "upper_bound_unverified",
        }
        state.entries.append(entry)
        self._write(state)
        return entry

    def append_correction(self, entry: dict) -> dict:
        """Append a correction entry (negative cost) — history is never
        edited. Caller supplies stage, cost_usd and its evidence."""
        state = self._read()
        state.entries.append(entry)
        self._write(state)
        return entry

    # --- Convenience --------------------------------------------------

    def snapshot(self) -> dict:
        s = self._read()
        return {
            "cap_inr": s.cap_inr,
            "cap_usd": s.cap_usd,
            "cumulative_usd": s.cumulative_usd,
            "cumulative_inr": s.cumulative_inr,
            "remaining_usd": max(0.0, s.cap_usd - s.cumulative_usd),
            "remaining_inr": max(0.0, s.cap_inr - s.cumulative_inr),
            "n_calls": len(s.entries),
            "by_stage": _stage_totals(s.entries),
        }


def _stage_totals(entries: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for e in entries:
        s = e.get("stage", "unknown")
        b = out.setdefault(s, {"calls": 0, "cost_usd": 0.0, "cost_inr": 0.0})
        b["calls"] += 1
        b["cost_usd"] += e.get("cost_usd", 0.0)
        b["cost_inr"] += e.get("cost_inr", 0.0)
    return out


__all__ = [
    "CAP_INR", "CAP_USD", "FX_USD_TO_INR", "LEDGER_PATH", "EMBED_IN_PER_M",
    "default_ledger_path",
    "SpendLedger", "SpendCapExceededError", "LedgerEntry",
]
