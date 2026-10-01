"""Tests for the weekly-refresh module. No live API calls — uses the
`_FixtureClient` canned-response client."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from backend.app.refresh.weekly_candidates import (
    Candidate, _dedupe_candidates, _drop_known_to_library,
    _normalise_title_key, _window, _FixtureClient,
    query_cites_both_recent, query_cites_recent,
    render_issue_body, run,
)


def test_window_computes_inclusive_range():
    today = datetime.date(2026, 10, 1)
    fd, td = _window(today, 10)
    assert fd == "2026-09-21"
    assert td == "2026-10-01"


def test_normalise_title_key_strips_punct():
    assert (_normalise_title_key("Red meat & stroke: a 2026 update")
            == "red meat stroke a 2026 update")


def test_dedupe_candidates_removes_same_wid_doi_and_title():
    c = Candidate
    cands = [
        c("W1", "Red meat and stroke in middle-aged adults",
          2026, "10.1/a", None, "r1", "diet-and-mortality"),
        c("W1", "Red meat and stroke in middle-aged adults",  # dup wid
          2026, "10.1/a", None, "r2", "diet-and-mortality"),
        c("W2", "Red meat and stroke in middle-aged adults",  # dup DOI
          2026, "10.1/a", None, "r3", "diet-and-mortality"),
        c("W3", "Red meat and stroke in middle-aged adults",  # dup title+year
          2026, None, None, "r4", "diet-and-mortality"),
        c("W4", "Red meat and stroke in middle-aged adults",  # same title, diff year — pass 4 collapses
          2025, None, None, "r5", "diet-and-mortality"),
        c("W5", "Processed meat and cancer in cohort x",
          2026, "10.1/b", None, "r6", "diet-and-mortality"),
    ]
    out = _dedupe_candidates(cands)
    assert [k.wid for k in out] == ["W1", "W5"]


def test_drop_known_to_library(tmp_path):
    papers_json = tmp_path / "papers.json"
    papers_json.write_text(json.dumps({"items": [
        {"wid": "W100", "doi": "10.5/x", "title": "Something known"},
    ]}))
    cands = [
        Candidate("W100", "Something known", 2024, "10.5/x", None, "r", "l"),
        Candidate("W101", "Something new",   2026, None,     None, "r", "l"),
    ]
    out = _drop_known_to_library(cands, papers_json)
    assert [c.wid for c in out] == ["W101"]


def test_query_cites_both_recent_uses_AND_filter_and_window():
    captured = {}
    class Cap:
        def get(self, path, params):
            captured["path"] = path
            captured["filter"] = params["filter"]
            return {"results": [
                {"id": "https://openalex.org/W999",
                 "display_name": "Later synthesis", "publication_year": 2026,
                 "doi": "https://doi.org/10.9/z",
                 "primary_location": {"source": {"homepage_url": "x"}}},
            ], "meta": {"count": 1}}
    out = query_cites_both_recent(
        Cap(), "openalex:W100", "openalex:W200",
        ref_date=datetime.date(2026, 10, 1), lookback_days=7,
    )
    assert "cites:W100,cites:W200" in captured["filter"]
    assert "from_publication_date:2026-09-24" in captured["filter"]
    assert "to_publication_date:2026-10-01" in captured["filter"]
    assert out[0]["id"].endswith("W999")


def test_query_cites_recent_excludes_the_source_itself():
    class Cap:
        def get(self, path, params):
            return {"results": [
                {"id": "https://openalex.org/W100",      # self — must be excluded
                 "display_name": "self", "publication_year": 2026},
                {"id": "https://openalex.org/W300",
                 "display_name": "a citer", "publication_year": 2026},
            ], "meta": {"count": 2}}
    out = query_cites_recent(Cap(), "openalex:W100",
                              ref_date=datetime.date(2026, 10, 1))
    assert [w["id"].split("/")[-1] for w in out] == ["W300"]


def test_fixture_client_matches_by_filter_substring():
    fixture = [
        {"match": "cites:W1,cites:W2",
         "response": {"results": [{"id": "W999",
                                     "display_name": "match",
                                     "publication_year": 2026}],
                       "meta": {"count": 1}}},
    ]
    c = _FixtureClient(fixture)
    body = c.get("/works", {"filter": "cites:W1,cites:W2,from_publication_date:x"})
    assert body["results"][0]["display_name"] == "match"
    # Non-matching filter — empty response, not an error.
    assert c.get("/works", {"filter": "cites:W99"}) == {"results": [], "meta": {"count": 0}}


def _tiny_repo(tmp_path: Path) -> Path:
    """Synth a minimal snapshot tree for the module to walk."""
    (tmp_path / "frontend" / "public" / "data" / "library"
     / "diet-and-mortality").mkdir(parents=True)
    (tmp_path / "frontend" / "public" / "data" / "library"
     / "diet-and-mortality" / "papers.json").write_text(
        json.dumps({"items": [{"wid": "W_EXISTING", "doi": "10.1/kept"}]}))
    (tmp_path / "frontend" / "public" / "data" / "library"
     / "diet-and-mortality" / "opportunities.json").write_text(
        json.dumps({"items": []}))
    (tmp_path / "data" / "domains" / "diet-and-mortality"
     / "reasoning").mkdir(parents=True)
    (tmp_path / "data" / "domains" / "diet-and-mortality"
     / "reasoning" / "contradiction_audit.json").write_text(
        json.dumps({"verdicts": [
            {"verdict": "genuine", "topic": "red meat / stroke",
             "a_paper_id": "openalex:W_A", "b_paper_id": "openalex:W_B"},
        ]}))
    return tmp_path


def test_run_end_to_end_against_fixture(tmp_path):
    repo = _tiny_repo(tmp_path)
    fixture = [
        {"match": "cites:W_A,cites:W_B",
         "response": {"results": [
             {"id": "https://openalex.org/W_NEW",
              "display_name": "A new synthesis",
              "publication_year": 2026,
              "doi": "https://doi.org/10.2/new"},
             {"id": "https://openalex.org/W_EXISTING",  # already in library
              "display_name": "Already there",
              "publication_year": 2024},
         ], "meta": {"count": 2}}},
    ]
    result = run(_FixtureClient(fixture), slugs=["diet-and-mortality"],
                 repo_root=repo, ref_date=datetime.date(2026, 10, 1))
    cands = result.libraries["diet-and-mortality"]
    # W_EXISTING is dropped by _drop_known_to_library.
    assert [c.wid for c in cands] == ["W_NEW"]
    assert cands[0].reason.startswith("cites both sides of 'red meat / stroke'")
    assert result.credits_used == 1


def test_run_renders_markdown_and_states_flagged_not_confirmed(tmp_path):
    repo = _tiny_repo(tmp_path)
    fixture = [
        {"match": "cites:W_A,cites:W_B",
         "response": {"results": [
             {"id": "https://openalex.org/W_NEW",
              "display_name": "A new synthesis",
              "publication_year": 2026},
         ], "meta": {"count": 1}}},
    ]
    result = run(_FixtureClient(fixture), slugs=["diet-and-mortality"],
                 repo_root=repo, ref_date=datetime.date(2026, 10, 1))
    body = render_issue_body(result, lookback_days=10)
    assert "Flagged DOES NOT mean confirmed" in body
    assert "credits used: **1**" in body
    assert "W_NEW" in body
    assert "A new synthesis" in body
    assert "diet-and-mortality" in body


def test_render_honest_zero_body(tmp_path):
    repo = _tiny_repo(tmp_path)
    fixture = [
        {"match": "cites:W_A,cites:W_B",
         "response": {"results": [], "meta": {"count": 0}}},
    ]
    result = run(_FixtureClient(fixture), slugs=["diet-and-mortality"],
                 repo_root=repo, ref_date=datetime.date(2026, 10, 1))
    body = render_issue_body(result, lookback_days=10)
    assert "No candidates" in body
    assert "Honest zero" in body
