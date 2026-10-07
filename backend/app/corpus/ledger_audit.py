"""Ledger integrity audit — free, reads `data/spend_ledger.json` only.

  python -m backend.app.corpus.ledger_audit                 # print + write data/ledger_audit.json
  python -m backend.app.corpus.ledger_audit --append-correction
  python -m backend.app.corpus.ledger_audit --freeze-cap    # cap := cumulative (₹0 new spend)
  python -m backend.app.corpus.ledger_audit --set-cap 990   # owner-approved ceiling (INR)

Mock-test entries. `backend/tests/extraction/test_llm_client.py` drives
GeminiLLMClient through an httpx MockTransport (api_key="fake") whose 200
responses carry usageMetadata promptTokenCount=5, candidatesTokenCount=3.
Before iteration 4 the test suite had no ledger isolation, so each run of
that file recorded exactly 10 such entries to the real ledger under stage
"unknown" (no run context set), model "gemini-3.6-flash". An entry is
classed as PROVEN mock only if it has that exact signature AND sits in a
burst of exactly 10 identical entries spanning under one second (ten real
network round-trips cannot complete that fast). Anything else stays counted.

Corrections are APPENDED as one negative entry; no entry is edited or
removed. Re-running --append-correction is a no-op once it is present.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.extraction.spend_ledger import SpendLedger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_OUT = REPO_ROOT / "data" / "ledger_audit.json"
CORRECTION_STAGE = "correction_mock_test_entries"
MOCK_SIGNATURE = {"stage": "unknown", "prompt_tokens": 5,
                  "candidates_tokens": 3, "thoughts_tokens": 0}
BURST_SIZE = 10           # _ok() 200s recorded per run of test_llm_client.py
BURST_MAX_SPAN_S = 1.0


def _is_sig(e: dict) -> bool:
    return all(e.get(k) == v for k, v in MOCK_SIGNATURE.items())


def proven_mock_indices(entries: list[dict]) -> tuple[list[int], list[dict]]:
    """Indices of entries proven to come from mock-transport test runs, and
    the bursts they form."""
    sig = [i for i, e in enumerate(entries) if _is_sig(e)]
    bursts, cur = [], []
    for i in sig:
        if cur and (i != cur[-1] + 1 or entries[i]["ts"] - entries[cur[0]]["ts"] > BURST_MAX_SPAN_S):
            bursts.append(cur)
            cur = []
        cur.append(i)
    if cur:
        bursts.append(cur)
    proven, info = [], []
    for b in bursts:
        span = entries[b[-1]]["ts"] - entries[b[0]]["ts"]
        ok = len(b) == BURST_SIZE and span < BURST_MAX_SPAN_S
        info.append({"first_index": b[0], "last_index": b[-1], "n": len(b),
                     "span_s": round(span, 4), "ts_first": entries[b[0]]["ts"],
                     "proven_mock": ok})
        if ok:
            proven.extend(b)
    return proven, info


def audit(entries: list[dict]) -> dict:
    by_stage: dict = defaultdict(lambda: {"calls": 0, "inr": 0.0, "models": set(),
                                         "batch": set()})
    for e in entries:
        b = by_stage[e.get("stage", "unknown")]
        b["calls"] += 1
        b["inr"] += e.get("cost_inr", 0.0)
        b["models"].add(e.get("model"))
        b["batch"].add(bool(e.get("batch")))
    proven, bursts = proven_mock_indices(entries)
    sig_all = [i for i, e in enumerate(entries) if _is_sig(e)]
    unknown = [i for i, e in enumerate(entries) if e.get("stage") == "unknown"]
    correction = [e for e in entries if e.get("stage") == CORRECTION_STAGE]
    raw_inr = sum(e.get("cost_inr", 0.0) for e in entries
                  if e.get("stage") != CORRECTION_STAGE)
    return {
        "n_entries": len(entries),
        "by_stage": {s: {"calls": v["calls"], "inr": round(v["inr"], 4),
                         "models": sorted(m for m in v["models"] if m),
                         "batch": sorted(v["batch"])}
                     for s, v in sorted(by_stage.items())},
        "unknown_stage": {
            "n": len(unknown),
            "inr": round(sum(entries[i]["cost_inr"] for i in unknown), 4),
            "n_with_mock_signature": len(sig_all),
            "n_proven_mock": len(proven),
            "proven_mock_inr": round(sum(entries[i]["cost_inr"] for i in proven), 4),
            "proven_mock_usd": sum(entries[i]["cost_usd"] for i in proven),
            "n_unknown_not_proven": len(set(unknown) - set(proven)),
            "bursts": bursts,
        },
        "proven_mock_indices": proven,
        "raw_cumulative_inr": round(raw_inr, 4),
        "correction_present": bool(correction),
        "corrected_cumulative_inr": round(sum(e.get("cost_inr", 0.0) for e in entries), 4)
        if correction else round(raw_inr - sum(entries[i]["cost_inr"] for i in proven), 4),
    }


def append_correction(ledger: SpendLedger) -> dict | None:
    entries = ledger._read().entries
    if any(e.get("stage") == CORRECTION_STAGE for e in entries):
        return None
    proven, _ = proven_mock_indices(entries)
    usd = sum(entries[i]["cost_usd"] for i in proven)
    return ledger.append_correction({
        "ts": time.time(), "stage": CORRECTION_STAGE, "model": "n/a",
        "batch": False, "prompt_tokens": 0, "candidates_tokens": 0,
        "thoughts_tokens": 0, "billed_output_tokens": 0,
        "cost_usd": -usd, "cost_inr": -usd * 84.0,
        "kind": "correction", "corrects_indices": proven,
        "reason": ("entries written by mock-transport unit tests "
                   "(test_llm_client.py, api_key='fake'), not billed API calls"),
        "evidence": "docs/findings/ledger-unknown-entries.md",
    })


def freeze_cap(ledger: SpendLedger) -> float:
    """Set the cap to the current cumulative: any new paid call is refused."""
    state = ledger._read()
    state.cap_inr = round(state.cumulative_inr, 6)
    state.cap_usd = state.cap_inr / state.fx_usd_to_inr
    ledger._write(state)
    return state.cap_inr


def set_cap(ledger: SpendLedger, cap_inr: float) -> float:
    """Owner-approved ceiling. Only the cap field changes; entries never do."""
    state = ledger._read()
    if cap_inr < state.cumulative_inr:
        raise ValueError(f"cap ₹{cap_inr} is below cumulative ₹{state.cumulative_inr:.2f}")
    state.cap_inr = float(cap_inr)
    state.cap_usd = state.cap_inr / state.fx_usd_to_inr
    ledger._write(state)
    return state.cap_inr


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--append-correction", action="store_true")
    p.add_argument("--freeze-cap", action="store_true")
    p.add_argument("--set-cap", type=float)
    a = p.parse_args()
    ledger = SpendLedger.load()
    if a.append_correction:
        e = append_correction(ledger)
        print("correction:", "already present" if e is None else
              f"appended ₹{e['cost_inr']:.4f} over {len(e['corrects_indices'])} entries")
    if a.freeze_cap:
        print(f"cap frozen at ₹{freeze_cap(ledger):.4f}")
    if a.set_cap is not None:
        print(f"cap set to ₹{set_cap(ledger, a.set_cap):.2f}")
    rep = audit(ledger._read().entries)
    out = {k: v for k, v in rep.items() if k != "proven_mock_indices"}
    out["proven_mock_index_range"] = ([min(rep["proven_mock_indices"]),
                                       max(rep["proven_mock_indices"])]
                                      if rep["proven_mock_indices"] else None)
    out["cap_inr"] = ledger._read().cap_inr
    AUDIT_OUT.write_text(json.dumps(out, indent=2) + "\n")
    u = rep["unknown_stage"]
    print(f"unknown: {u['n']} entries ₹{u['inr']:.4f}; proven mock {u['n_proven_mock']} "
          f"(₹{u['proven_mock_inr']:.4f}); not proven {u['n_unknown_not_proven']}")
    print(f"raw ₹{rep['raw_cumulative_inr']:.2f} → corrected ₹{rep['corrected_cumulative_inr']:.2f}"
          f"; cap ₹{out['cap_inr']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
