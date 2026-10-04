"""Audit doubts are recorded and shipped; no published verdict changes."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DIET = REPO / "data" / "domains" / "diet-and-mortality" / "reasoning"


def test_doubted_diet_pairs_keep_their_verdicts():
    audit = json.loads((DIET / "contradiction_audit.json").read_text())["verdicts"]
    doubts = json.loads((DIET / "audit_doubts.json").read_text())["items"]
    assert [d["audit_pair"] for d in doubts] == [1, 5]
    for d in doubts:
        assert audit[d["audit_pair"] - 1]["verdict"] == "genuine" == d["verdict"]


def test_doubts_shipped_to_both_new_libraries():
    for slug in ("diet-and-mortality", "ml-fairness"):
        s = json.loads((REPO / "frontend" / "public" / "data" / "library" / slug
                        / "stats.json").read_text())
        assert s["audit_doubts"], slug
