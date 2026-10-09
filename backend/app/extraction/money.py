"""The money rule (config/money.json) — the only spending limit.

  ceiling   = account_total_inr - safety_buffer_inr          (₹1450)
  remaining = ceiling - ledger cumulative                     (console unknown)
            = ceiling - console_spent_inr
                      - ledger spend recorded after console_spent_date
                                                              (console known)

The ledger may overstate the console (projections round up), so measuring
on the ledger is the conservative choice. `effective_cap_inr` turns the rule
into a ledger-terms ceiling (cumulative + remaining), which SpendLedger
enforces at call time in every path. Growth pacing:

  weekly_budget = min(weekly_budget_max_inr, remaining / weeks_left)
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def config_path() -> Path:
    env = os.environ.get("MONEY_CONFIG_PATH")
    return Path(env) if env else _REPO_ROOT / "config" / "money.json"


def load() -> dict | None:
    p = config_path()
    return json.loads(p.read_text()) if p.exists() else None


def ceiling_inr(cfg: dict) -> float:
    return float(cfg["account_total_inr"]) - float(cfg["safety_buffer_inr"])


def _spend_after(entries: list[dict], date: str) -> float:
    """Ledger spend recorded after the end of `date` (India time)."""
    end = dt.datetime.combine(dt.date.fromisoformat(date) + dt.timedelta(days=1),
                              dt.time(), tzinfo=IST).timestamp()
    return sum(float(e.get("cost_inr", 0.0)) for e in entries if float(e.get("ts", 0)) >= end)


def remaining_inr(cfg: dict, cumulative_inr: float, entries: list[dict]) -> float:
    if cfg.get("console_spent_inr") is None:
        rem = ceiling_inr(cfg) - cumulative_inr
    else:
        if not cfg.get("console_spent_date"):
            raise ValueError("config/money.json: console_spent_inr needs console_spent_date (YYYY-MM-DD)")
        rem = (ceiling_inr(cfg) - float(cfg["console_spent_inr"])
               - _spend_after(entries, cfg["console_spent_date"]))
    return max(0.0, rem)


def effective_cap_inr(cumulative_inr: float, entries: list[dict]) -> float | None:
    """Ledger-terms ceiling: the money rule, further lowered by a per-run cap
    (RUN_CAP_LEDGER_INR, an absolute ledger total set by a manual weekly run
    with run_budget_inr) when one is in force."""
    cfg = load()
    cap = None if cfg is None else cumulative_inr + remaining_inr(cfg, cumulative_inr, entries)
    run_cap = os.environ.get("RUN_CAP_LEDGER_INR")
    if run_cap:
        cap = float(run_cap) if cap is None else min(cap, float(run_cap))
    return cap


def weeks_left(cfg: dict, today: dt.date | None = None) -> int:
    today = today or dt.datetime.now(IST).date()
    start = dt.date.fromisoformat(cfg["growth_horizon_start"])
    elapsed = max(0, (today - start).days // 7)
    return max(1, int(cfg["growth_horizon_weeks"]) - elapsed)


def weekly_budget_inr(remaining: float, cfg: dict, today: dt.date | None = None) -> float:
    return round(min(float(cfg["weekly_budget_max_inr"]), remaining / weeks_left(cfg, today)), 2)


def queued_affordable(projection_inr: float, remaining: float, weekly: float, cfg: dict,
                      mult: float = 1.5) -> bool:
    return projection_inr * mult + int(cfg["queued_domain_reserve_weeks"]) * weekly <= remaining + 1e-9


def status(today: dt.date | None = None) -> dict:
    """Everything a run or a report needs, computed from the ledger + config."""
    from backend.app.extraction.spend_ledger import SpendLedger
    cfg = load() or {}
    snap = SpendLedger.load().snapshot()
    led = SpendLedger.load()._read()
    rem = remaining_inr(cfg, snap["cumulative_inr"], led.entries) if cfg else snap["remaining_inr"]
    out = {"ceiling_inr": ceiling_inr(cfg) if cfg else snap["cap_inr"],
           "ledger_inr": round(snap["cumulative_inr"], 2), "remaining_inr": round(rem, 2),
           "console_spent_inr": cfg.get("console_spent_inr"),
           "console_spent_date": cfg.get("console_spent_date")}
    if cfg:
        out["weeks_left"] = weeks_left(cfg, today)
        out["weekly_budget_inr"] = weekly_budget_inr(rem, cfg, today)
    return out


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
