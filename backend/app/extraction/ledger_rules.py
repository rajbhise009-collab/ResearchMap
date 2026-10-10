"""The spend ledger is append-only (data/spend_ledger.json).

One rule, used by SpendLedger on every write and by tools/ci/check_ledger.py
on every push: the entries already recorded are kept exactly, in order, and
new ones only go on the end; the cumulative total is the sum of the entries.
A correction is a NEW entry (see `corrects_indices`), never an edit.
"""
from __future__ import annotations

TOLERANCE_INR = 0.005          # half a paisa: float rounding only


def append_only_violation(old: dict | None, new: dict) -> str | None:
    """None if `new` is a valid successor of `old` (or of nothing), else why not."""
    new_entries = new.get("entries", [])
    total = sum(float(e.get("cost_inr", 0.0)) for e in new_entries)
    if "cumulative_inr" in new and abs(float(new["cumulative_inr"]) - total) > TOLERANCE_INR:
        return f"cumulative_inr {new['cumulative_inr']} != sum of entries {total}"
    if old is None:
        return None
    old_entries = old.get("entries", [])
    if len(new_entries) < len(old_entries):
        return f"entries shrank from {len(old_entries)} to {len(new_entries)}"
    for i, (a, b) in enumerate(zip(old_entries, new_entries)):
        if a != b:
            return f"entry {i} was changed (entries are never edited; append a correction instead)"
    return None


class LedgerAppendOnlyError(RuntimeError):
    pass
