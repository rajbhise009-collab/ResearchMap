"""Paper merges: loser content is folded onto the survivor by the policy
keys (nothing silently lost), and the applied ml-fairness merge matches the
recorded decision."""

from __future__ import annotations

import json

from backend.app.corpus import merges as M
from backend.app.models import Claim, FutureWork, Limitation, PaperExtraction


def _ext(pid, claims, lims=(), fws=()):
    return PaperExtraction.model_construct(
        paper_id=pid,
        claims=[Claim.model_construct(id=f"{pid}:c{i}", paper_id=pid, text=t, type="finding")
                for i, t in enumerate(claims)],
        evidence=[], methodologies=[],
        limitations=[Limitation.model_construct(id=f"{pid}:l{i}", paper_id=pid, text=c,
                                                normalized_category=c) for i, c in enumerate(lims)],
        future_work=[FutureWork.model_construct(id=f"{pid}:f{i}", paper_id=pid, text=t)
                     for i, t in enumerate(fws)])


def test_union_keeps_loser_items_and_reattributes_them():
    s = _ext("openalex:S", ["Toolkit provides metrics."])
    lo = _ext("openalex:L", ["Toolkit provides metrics!", "Toolkit has 9 algorithms."],
              lims=["scope"], fws=["extend to text"])
    u = M.union_extraction(s, [lo])
    assert [c.text for c in u.claims] == ["Toolkit provides metrics.", "Toolkit has 9 algorithms."]
    assert {c.paper_id for c in u.claims} == {"openalex:S"}
    assert len(u.limitations) == 1 and len(u.future_work) == 1
    assert u.limitations[0].paper_id == "openalex:S"


def test_applied_fairness_merge_matches_record():
    root = M.DOMAINS_DIR / "ml-fairness"
    rec = json.loads((root / "merges.json").read_text())["merges"][0]
    pre = {e["wid"]: e for e in json.loads((root / "prelabelled.json").read_text())["entries"]}
    assert rec["survivor"] in pre and all(lo not in pre for lo in rec["losers"])
    assert pre[rec["survivor"]]["merged_from"] == [f"openalex:{lo}" for lo in rec["losers"]]
    log = json.loads((root / "merge_log.json").read_text())
    assert log["after"]["papers"] == log["before"]["papers"] - 1
    assert log["verdicts_dropped_by_merge"] == 4
    assert log["after"]["flagged_contradictions"] == log["before"]["flagged_contradictions"]


def test_no_verdict_pairs_one_paper_with_itself():
    from backend.app.corpus import multi_domain_reason as R
    paper_of = {c.id: e.paper_id for e in R.load_extractions("ml-fairness") for c in e.claims}
    rd = M.DOMAINS_DIR / "ml-fairness" / "reasoning"
    for f in ("contradictions.json", "supports.json", "nones.json"):
        for it in json.loads((rd / f).read_text())["items"]:
            a, b = it["from_claim_id"], it["to_claim_id"]
            if a in paper_of and b in paper_of:
                assert paper_of[a] != paper_of[b], (f, a, b)
