"""Tests for the contradiction-audit reader — verdict lookup and
attach_verdicts. Uses the real diet-and-mortality audit JSON."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.api.contradiction_audit import (
    _key,
    attach_verdicts,
    audit_summary,
    load_audit,
    verdict_lookup,
)


def test_load_audit_diet_reads_expected_fields():
    a = load_audit("diet-and-mortality")
    assert a["domain"] == "diet-and-mortality"
    assert a["basis"] and "hand review" in a["basis"].lower()
    assert len(a["verdicts"]) == 10
    # The iteration-2 audit (first 7) must never be rewritten by later passes.
    assert [v["verdict"] for v in a["verdicts"][:7]] == [
        "genuine", "artifact", "genuine", "genuine", "genuine", "genuine",
        "duplicate"]


def test_verdict_lookup_maps_by_content_not_index():
    table = verdict_lookup("diet-and-mortality")
    k = _key(
        "openalex:W2109401990", "openalex:W2513212958",
        "Unprocessed red meat consumption is not associated with incident stroke.",
        "Consumption of 100 g/day of unprocessed red meat is associated with an 11% increased risk",
    )
    assert k in table
    assert table[k]["verdict"] == "genuine"
    k_swapped = _key(
        "openalex:W2513212958", "openalex:W2109401990",
        "Consumption of 100 g/day of unprocessed red meat is associated with an 11% increased risk",
        "Unprocessed red meat consumption is not associated with incident stroke.",
    )
    assert k_swapped == k


def test_attach_verdicts_for_the_diet_seven():
    raw = [
        {"a_paper_id": "openalex:W2109401990",
         "b_paper_id": "openalex:W2513212958",
         "a_text": "Unprocessed red meat consumption is not associated with incident stroke.",
         "b_text": "Consumption of 100 g/day of unprocessed red meat is associated with an 11% increased risk of stroke."},
        {"a_paper_id": "openalex:W2126726883",
         "b_paper_id": "openalex:W2787107952",
         "a_text": "The decreased risk of myocardial infarction was similar between men consuming less than 10 g",
         "b_text": "Increased alcohol consumption is log-linearly associated with a lower risk of myocardial infarction"},
        {"a_paper_id": "openalex:W2109129984",
         "b_paper_id": "openalex:W2311763102",
         "a_text": "Alcohol consumption is associated with a lower risk of all-cause mortality compared",
         "b_text": "After adjusting for abstainer biases and study quality characteristics, low-volume alcohol"},
    ]
    attached = attach_verdicts("diet-and-mortality", raw)
    assert attached[0]["audit"]["verdict"] == "genuine"
    assert attached[1]["audit"]["verdict"] == "artifact"
    assert attached[2]["audit"]["verdict"] == "duplicate"


# The 2026-10 hand audit of the first 10 diet pairs. It is append-only:
# weekly growth may add newly flagged pairs (unaudited until the owner
# checks them) and the owner may add verdicts, but these entries never change.
DIET_AUDIT_V1_SHA256 = "27ca2303cf768178910e2ed27eb2e344d25dd0b0a3e0de22c1a2b7fb2329b16a"


def test_audit_summary_for_diet_matches_hand_count():
    import hashlib
    audit = json.loads(Path("data/domains/diet-and-mortality/reasoning/contradiction_audit.json").read_text())
    first = audit["verdicts"][:10]
    assert hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest() == DIET_AUDIT_V1_SHA256
    assert [v["verdict"] for v in first].count("genuine") == 5
    p = Path("data/domains/diet-and-mortality/reasoning/contradictions.json")
    items = json.loads(p.read_text()).get("items", [])
    s = audit_summary("diet-and-mortality", items)
    assert s["genuine"] >= 5 and s["artifact"] >= 2 and s["duplicate"] >= 3, s
    assert s["raw_flagged"] == s["genuine"] + s["artifact"] + s["duplicate"] + s["unaudited"], s
    assert s["raw_flagged"] - s["unaudited"] == len(audit["verdicts"]), s   # every verdict maps to a pair
    assert s["confirmed"] == s["genuine"], s


def test_unaudited_domain_gets_unaudited_verdicts():
    raw = [{"a_paper_id": "openalex:W1", "b_paper_id": "openalex:W2",
             "a_text": "a", "b_text": "b"}]
    attached = attach_verdicts("ml-fairness", raw)
    assert attached[0]["audit"]["verdict"] == "unaudited"
    s = audit_summary("ml-fairness", raw)
    assert s["unaudited"] == 1
    assert s["confirmed"] == 0
