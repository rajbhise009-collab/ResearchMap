"""How much one growth run may do (config/growth.json), deterministic.

  target_papers_per_run   papers one run aims to add, all libraries together
                          (default 55), split by fair rotation (split_target)
  per_run_cost_cap_inr    the most one run may COMMIT to new paid work, in
                          padded projection terms (extraction x1.5,
                          classification x2); collecting batches an earlier
                          run submitted is never counted against it
  mode                    batch (default; papers appear next run) or sync
                          (papers appear in the same run, about 2x the cost)

The money rule (config/money.json, backend/app/extraction/money.py) stays
the only hard limit: a run never commits more than the money available
(remaining minus batches submitted but not yet billed), and every paid call
is refused at call time past the ledger ceiling. When a run cannot afford
its target it adds fewer papers and says why (shortfall_reasons).

Follow-on checks are bounded per run (max_*_per_run); what a run does not
reach is carried over to the next (it stays unchecked and hidden, never
lost). openalex_max_calls_per_run bounds the free candidate search.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import REPO_ROOT

GROWTH_CFG = REPO_ROOT / "config" / "growth.json"
MODES = ("batch", "sync")
SYNC_COST_FACTOR = 2.0          # interactive API price / batch price (pricing.py)

DEFAULTS = {
    "target_papers_per_run": 55,
    "per_run_cost_cap_inr": 25.0,
    "mode": "batch",
    "max_disagreement_pairs_per_run": 400,
    "max_fw_pairs_per_run": 400,
    "max_confirm_leads_per_run": 150,
    "openalex_max_calls_per_run": 600,
    "candidate_spare_per_library": 0.5,
    "queued_reserve_runs": 4,
    "min_growth_reserve_per_run_inr": 15.0,
}


@dataclass(frozen=True)
class Settings:
    target_papers_per_run: int
    per_run_cost_cap_inr: float
    mode: str
    max_disagreement_pairs_per_run: int
    max_fw_pairs_per_run: int
    max_confirm_leads_per_run: int
    openalex_max_calls_per_run: int
    candidate_spare_per_library: float
    queued_reserve_runs: int
    min_growth_reserve_per_run_inr: float


def config_path() -> Path:
    env = os.environ.get("GROWTH_CONFIG_PATH")
    return Path(env) if env else GROWTH_CFG


def load(path: Path | None = None) -> Settings:
    """config/growth.json over DEFAULTS; invalid values are refused (a bad
    config must stop the run, never be guessed around)."""
    p = path or config_path()
    raw = json.loads(p.read_text()) if p.exists() else {}
    v = {k: raw.get(k, d) for k, d in DEFAULTS.items()}
    s = Settings(
        target_papers_per_run=int(v["target_papers_per_run"]),
        per_run_cost_cap_inr=float(v["per_run_cost_cap_inr"]),
        mode=str(v["mode"]),
        max_disagreement_pairs_per_run=int(v["max_disagreement_pairs_per_run"]),
        max_fw_pairs_per_run=int(v["max_fw_pairs_per_run"]),
        max_confirm_leads_per_run=int(v["max_confirm_leads_per_run"]),
        openalex_max_calls_per_run=int(v["openalex_max_calls_per_run"]),
        candidate_spare_per_library=float(v["candidate_spare_per_library"]),
        queued_reserve_runs=int(v["queued_reserve_runs"]),
        min_growth_reserve_per_run_inr=float(v["min_growth_reserve_per_run_inr"]),
    )
    bad = [k for k, ok in (
        ("target_papers_per_run", 0 <= s.target_papers_per_run <= 500),
        ("per_run_cost_cap_inr", 0 <= s.per_run_cost_cap_inr <= 2000),
        ("mode", s.mode in MODES),
        ("max_disagreement_pairs_per_run", s.max_disagreement_pairs_per_run >= 0),
        ("max_fw_pairs_per_run", s.max_fw_pairs_per_run >= 0),
        ("max_confirm_leads_per_run", s.max_confirm_leads_per_run >= 0),
        ("openalex_max_calls_per_run", s.openalex_max_calls_per_run > 0),
        ("candidate_spare_per_library", 0 <= s.candidate_spare_per_library <= 3),
        ("queued_reserve_runs", s.queued_reserve_runs >= 0),
        ("min_growth_reserve_per_run_inr", s.min_growth_reserve_per_run_inr >= 0),
    ) if not ok]
    if bad:
        raise ValueError(f"{p}: invalid value(s) for {', '.join(bad)}")
    return s


def run_budget_inr(settings: Settings, available_inr: float, manual_cap_inr: float | None = None) -> float:
    """This run's budget for NEW commitments (padded projections): the
    per-run cap, lowered by a manual run's run_budget_inr, never above the
    money available (the money rule)."""
    b = settings.per_run_cost_cap_inr
    if manual_cap_inr is not None:
        b = min(b, manual_cap_inr)
    return round(max(0.0, min(b, available_inr)), 2)


def split_target(target: int, order: list[str]) -> dict[str, int]:
    """Fair split of the run's target across libraries: an equal share each,
    the remainder going one each to the libraries first in the fair order
    (served longest ago). A library that runs out of candidates frees its
    share for the others at allocation time (allocate: round-robin)."""
    if not order:
        return {}
    base, extra = divmod(max(0, target), len(order))
    return {s: base + (1 if i < extra else 0) for i, s in enumerate(order)}


def candidate_need(share: int, settings: Settings) -> int:
    """How many in-scope candidates to look for in one library: its share
    plus a spare, so a library that runs out can be covered by the others."""
    return share + (int(share * settings.candidate_spare_per_library + 0.999) if share else 0)


def queued_affordable(projection_inr: float, remaining_inr: float, run_budget: float, settings: Settings,
                      mult: float = 1.5) -> bool:
    """A queued library's padded projection plus queued_reserve_runs runs of
    growth must fit the money remaining."""
    return projection_inr * mult + settings.queued_reserve_runs * run_budget <= remaining_inr + 1e-9


def shortfall_reasons(*, target: int, planned: int, budget_inr: float, cap_inr: float, available_inr: float,
                      exhausted: dict[str, int], over_budget: int) -> list[str]:
    """Plain reasons a run plans fewer papers than its target (for the Issue)."""
    if planned >= target:
        return []
    out = [f"planned {planned} of the target {target} papers"]
    if over_budget:
        if budget_inr + 1e-9 < cap_inr and budget_inr + 1e-9 >= available_inr:
            out.append(f"{over_budget} more in-scope candidate(s) did not fit the money available "
                       f"(₹{available_inr:.2f} after batches already submitted; the money rule)")
        else:
            out.append(f"{over_budget} more in-scope candidate(s) did not fit this run's budget "
                       f"(₹{budget_inr:.2f}; per_run_cost_cap_inr or the manual run_budget_inr)")
    for slug, short in sorted(exhausted.items()):
        out.append(f"{slug}: every search tier tried; {short} fewer in-scope candidates than its share "
                   "(the rubric and core scope were not loosened)")
    return out
