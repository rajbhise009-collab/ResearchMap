"""Disagreement cards get caveats through the same rules as every other card
type (backend/app/ranking/assemble.py `_caveats`). They used to be exported
with a hard-coded empty list, so a disagreement resting on a summary-only
paper showed no "Based partly on summaries only" panel while every other
card type did."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.api import language
from backend.app.api.multi_library_export import write_multi_domain_snapshot

REPO = Path(__file__).resolve().parents[3]


def _entry(wid, src):
    return {"wid": wid, "title": f"Paper {wid}", "year": 2020, "input_source": src, "domain_centrality": "core"}


def test_a_summary_only_paper_gives_the_mixed_fidelity_caveat():
    from backend.app.api.multi_library_export import _disagreement_caveats
    entries = [_entry("W1", "fulltext"), _entry("W2", "abstract_only")]
    raw = _disagreement_caveats(["openalex:W1", "openalex:W2"], entries, "opp-x")
    assert [c["code"] for c in raw] == ["mixed_fidelity"]
    shown = language.caveats_for({"scorer": "unresolved_contradictions", "caveats": raw, "library_papers": 2})
    assert [c["label"] for c in shown] == ["Based partly on summaries only"]


def test_two_full_text_papers_need_no_caveat():
    from backend.app.api.multi_library_export import _disagreement_caveats
    entries = [_entry("W1", "fulltext"), _entry("W2", "fulltext")]
    assert _disagreement_caveats(["openalex:W1", "openalex:W2"], entries, "opp-x") == []


def _libraries_with_disagreements():
    out = []
    for p in sorted((REPO / "data" / "domains").glob("*/reasoning/contradictions.json")):
        if json.loads(p.read_text()).get("items"):
            out.append(p.parts[-3])
    return out


@pytest.mark.parametrize("slug", _libraries_with_disagreements())
def test_no_disagreement_card_with_a_summary_only_paper_lacks_a_caveat(slug, tmp_path):
    """Regression: export the library for real (into a temporary folder) and
    check every disagreement card. One resting on a summary-only paper must
    carry a caveat panel, and that panel must say so."""
    write_multi_domain_snapshot(slug, tmp_path)
    lib = tmp_path / "library" / slug
    entries = {f"openalex:{e['wid']}": e
               for e in json.loads((REPO / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"]}
    checked = 0
    for f in sorted((lib / "opportunity").glob("opp-contra-*.json")):
        card = json.loads(f.read_text())
        pids = [card.get("a_paper_id"), card.get("b_paper_id")]
        summary_only = [p for p in pids if p in entries and entries[p].get("input_source") != "fulltext"]
        labels = [c["label"] for c in card["consumer"]["caveats"]]
        if summary_only:
            checked += 1
            assert labels, (slug, card["slug"], "rests on a summary-only paper but shows no caveat")
            assert "Based partly on summaries only" in labels, (slug, card["slug"], labels)
        assert [c["code"] for c in card["caveats"]] == [c["code"] for c in card["consumer"]["caveats"]], card["slug"]
    if checked == 0:
        pytest.skip(f"{slug}: no disagreement rests on a summary-only paper")
