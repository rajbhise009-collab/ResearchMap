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


# --- "A problem several teams hit": the corpus-relative count caveat -------

APPROVED = ("Only counted within these {n} papers. These teams all hit this problem within this library "
            "of {n} papers, not the whole field. Work outside it may already have solved it. "
            "Check before you invest.")


def test_repeated_problem_rule_and_its_exact_wording():
    from types import SimpleNamespace
    from backend.app.ranking.assemble import _caveats
    raw = [c.model_dump() for c in _caveats("persistent_limitations",
                                            SimpleNamespace(id="x", component_scores={}), [], None, 101)]
    assert [c["code"] for c in raw] == ["corpus_relative_problem"]
    shown = language.caveats_for({"scorer": "persistent_limitations", "caveats": raw, "library_papers": 101})
    assert f"{shown[0]['label']}. {shown[0]['text']}" == APPROVED.format(n=101)
    # without a known library size the sentence stays readable (never a literal "{n}")
    blind = language.caveats_for({"scorer": "persistent_limitations", "caveats": raw, "library_papers": None})
    assert "{n}" not in blind[0]["label"] + blind[0]["text"]


def test_other_card_types_do_not_get_the_repeated_problem_caveat():
    from types import SimpleNamespace
    from backend.app.ranking.assemble import _caveats
    for scorer in ("orphaned_future_work", "structural_holes", "unresolved_contradictions"):
        codes = [c.code for c in _caveats(scorer, SimpleNamespace(id="x", component_scores={}), [], None, 50)]
        assert "corpus_relative_problem" not in codes, scorer


def test_time_span_is_pluralised():
    one = language.why_it_surfaced({"scorer": "persistent_limitations",
                                    "component_scores": {"n_independent": 3, "timespan": 1}})
    two = language.why_it_surfaced({"scorer": "persistent_limitations",
                                    "component_scores": {"n_independent": 3, "timespan": 4}})
    assert "span 1 year." in one and "1 years" not in one
    assert "span 4 years." in two


def _libraries_with_problem_cards():
    """Built multi-domain libraries (the ones write_multi_domain_snapshot exports)."""
    reg = json.loads((REPO / "data" / "library_registry.json").read_text())["libraries"]
    return [l["slug"] for l in reg if l["status"] == "built" and not l.get("frozen")
            and (REPO / "data" / "domains" / l["slug"] / "prelabelled.json").exists()]


@pytest.mark.parametrize("slug", _libraries_with_problem_cards())
def test_every_repeated_problem_card_carries_the_count_caveat(slug, tmp_path):
    """Regression: export the library for real (into a temporary folder);
    every 'A problem several teams hit' card must carry the approved
    corpus-relative count caveat, with this library's own size."""
    write_multi_domain_snapshot(slug, tmp_path)
    lib = tmp_path / "library" / slug
    n = len(json.loads((REPO / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"])
    cards = [json.loads(f.read_text()) for f in sorted((lib / "opportunity").glob("*.json"))]
    problems = [c for c in cards if c["consumer"]["kind"] == "A problem several teams hit"]
    if not problems:
        pytest.skip(f"{slug}: no repeated-problem cards")
    for c in problems:
        texts = [f"{x['label']}. {x['text']}" for x in c["consumer"]["caveats"]]
        assert APPROVED.format(n=n) in texts, (slug, c["slug"], texts)
