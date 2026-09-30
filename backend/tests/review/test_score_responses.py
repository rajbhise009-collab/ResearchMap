"""Tests for the diet-contradiction reviewer scorer. Synthetic
responses only — no real reviewer data referenced."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.app.review.score_responses import (
    _expected_answer,
    _normalise,
    cohens_kappa,
    load_responses,
    score,
)


@pytest.fixture
def toy_key(tmp_path):
    key = {
        "DO_NOT_SHARE_WITH_REVIEWERS": True,
        "seed": 1,
        "items": [
            {"item_id": "item-01", "provenance": "genuine",
             "audit_verdict": "genuine"},
            {"item_id": "item-02", "provenance": "genuine",
             "audit_verdict": "genuine"},
            {"item_id": "item-03", "provenance": "artifact",
             "audit_verdict": "artifact"},
            {"item_id": "item-04", "provenance": "control",
             "audit_verdict": None},
            {"item_id": "item-05", "provenance": "control",
             "audit_verdict": None},
        ],
    }
    p = tmp_path / "key.json"
    p.write_text(json.dumps(key))
    return p


def _write_csv(tmp_path, name, rows):
    p = tmp_path / f"{name}.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "verdict", "one_line_reason",
                     "reviewer_name_or_blank_for_anon"])
        for row in rows:
            w.writerow(row)
    return p


def test_expected_answer_maps_verdicts():
    assert _expected_answer({"provenance": "genuine",
                              "audit_verdict": "genuine"}) == "genuine_conflict"
    assert _expected_answer({"provenance": "artifact",
                              "audit_verdict": "artifact"}) == "not_conflict"
    assert _expected_answer({"provenance": "control",
                              "audit_verdict": None}) == "not_conflict"


def test_normalise_accepts_common_wording():
    assert _normalise("Genuine") == "genuine_conflict"
    assert _normalise("differ_in_conditions") == "not_conflict"
    assert _normalise("Consistent") == "not_conflict"
    assert _normalise("Can't tell") == "cant_tell"
    assert _normalise("") == "blank"


def test_scoring_agrees_when_reviewer_matches_audit(tmp_path, toy_key):
    # Reviewer perfectly matches the audit on all 5 items.
    csv_path = _write_csv(tmp_path, "alice", [
        ["item-01", "genuine", "", "alice"],
        ["item-02", "genuine", "", "alice"],
        ["item-03", "conditions", "", "alice"],
        ["item-04", "consistent", "", "alice"],
        ["item-05", "consistent", "", "alice"],
    ])
    r = load_responses([csv_path])
    s = score(r, toy_key)
    assert s["overall_agreement"] == 1.0
    ali = s["per_reviewer"]["alice"]
    assert ali["agree"] == 5 and ali["disagree"] == 0
    # Perfect controls handling
    assert ali["overcall_on_controls"] == 0


def test_overcall_on_controls_is_detected(tmp_path, toy_key):
    csv_path = _write_csv(tmp_path, "bob", [
        ["item-01", "genuine", "", "bob"],
        ["item-02", "genuine", "", "bob"],
        ["item-03", "conditions", "", "bob"],
        ["item-04", "genuine", "", "bob"],  # WRONG — control called genuine
        ["item-05", "genuine", "", "bob"],  # WRONG — control called genuine
    ])
    r = load_responses([csv_path])
    s = score(r, toy_key)
    bob = s["per_reviewer"]["bob"]
    assert bob["overcall_on_controls"] == 2
    assert bob["n_control"] == 2


def test_kappa_for_two_reviewers_agreeing(tmp_path, toy_key):
    a = _write_csv(tmp_path, "alice", [
        ["item-01", "genuine", "", "alice"],
        ["item-02", "genuine", "", "alice"],
        ["item-03", "conditions", "", "alice"],
        ["item-04", "consistent", "", "alice"],
        ["item-05", "consistent", "", "alice"],
    ])
    b = _write_csv(tmp_path, "bob", [
        ["item-01", "genuine", "", "bob"],
        ["item-02", "genuine", "", "bob"],
        ["item-03", "conditions", "", "bob"],
        ["item-04", "consistent", "", "bob"],
        ["item-05", "consistent", "", "bob"],
    ])
    r = load_responses([a, b])
    s = score(r, toy_key)
    ks = s["cohens_kappa"]
    assert len(ks) == 1
    k = list(ks.values())[0]
    assert k["n_shared_items"] == 5
    # Perfect agreement — kappa should be 1.0
    assert k["kappa"] == pytest.approx(1.0)


def test_kappa_none_for_too_few_shared():
    assert cohens_kappa([("a", "a"), ("b", "b")]) is None


def test_cant_tell_and_blank_dont_count_as_disagreement(tmp_path, toy_key):
    csv_path = _write_csv(tmp_path, "carol", [
        ["item-01", "genuine", "", "carol"],       # correct
        ["item-02", "can't tell", "", "carol"],   # not scored
        ["item-03", "", "", "carol"],              # blank
        ["item-04", "consistent", "", "carol"],   # correct
        ["item-05", "consistent", "", "carol"],   # correct
    ])
    r = load_responses([csv_path])
    s = score(r, toy_key)
    carol = s["per_reviewer"]["carol"]
    assert carol["agree"] == 3
    assert carol["disagree"] == 0
    assert carol["cant_tell"] == 1
    assert carol["blank"] == 1
