"""Tests for the /api/preflight endpoint.

These exercise the plain-language / dev-mode split, cache behaviour,
and consumer-copy honesty (must NEVER promise the diagnostic is
validated; must NEVER say the button works). Network is not required
— the preflight cache is seeded with a fixture that mirrors OpenAlex's
response shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import app
from backend.app.coherence import preflight as PF


REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _preseed_cache(tmp_path, monkeypatch):
    """Point the preflight cache at a temp dir so tests never hit
    OpenAlex, and seed it with a fixture that mimics OpenAlex's shape
    for the query 'test subject'."""
    monkeypatch.setattr(PF, "CACHE_DIR", tmp_path)

    # A small, hand-crackable fixture: 3 papers, one review, one
    # normal, one with references pointing to another in the corpus.
    payload = {
        "query": "test subject",
        "credit_headers": {"credits_used": "0", "remaining": "100000"},
        "meta": {"count": 300},
        "results": [
            {
                "id": "https://openalex.org/W101",
                "display_name": "A survey of test-subject methods",
                "publication_year": 2022,
                "type": "review",
                "referenced_works": [
                    "https://openalex.org/W102",
                    "https://openalex.org/EXTERNAL",
                ],
                "primary_location": {"source": {"id": "V1"}},
                "cited_by_count": 100,
            },
            {
                "id": "https://openalex.org/W102",
                "display_name": "Test subject calibration under load",
                "publication_year": 2023,
                "type": "article",
                "referenced_works": ["https://openalex.org/W103"],
                "primary_location": {"source": {"id": "V1"}},
                "cited_by_count": 20,
            },
            {
                "id": "https://openalex.org/W103",
                "display_name": "Empirical evaluation of test-subject metrics",
                "publication_year": 2024,
                "type": "article",
                "referenced_works": [],
                "primary_location": {"source": {"id": "V2"}},
                "cited_by_count": 5,
            },
        ],
    }
    slug = PF._slugify("test subject")
    (tmp_path / f"{slug}.json").write_text(json.dumps(payload))
    return payload


# --------------------------------------------------------------------------
# API contract
# --------------------------------------------------------------------------

def test_preflight_returns_consumer_and_dev_shapes(client):
    r = client.get("/api/preflight?q=test subject")
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "test subject"
    assert body["n_openalex_matches"] == 300
    assert body["n_sampled"] == 3
    # Consumer shape
    c = body["consumer"]
    for k in ("headline", "coverage_line", "diagnostic_line",
              "diagnostic_confidence", "estimate_headline"):
        assert k in c and isinstance(c[k], str) and c[k].strip()
    # Dev shape
    d = body["dev"]
    assert set(d["features"]) >= {
        "n_papers", "intracorpus_reference_rate", "citation_reciprocity",
        "citation_modularity", "review_ratio", "temporal_churn",
        "venue_concentration", "term_vector_spread",
    }
    assert set(d["verdict"]) >= {
        "contested_score", "contested_band",
        "method_transfer_score", "method_transfer_band", "caveat",
    }
    assert "target_papers" in d["cost_projection"]


def test_preflight_400_on_empty_query(client):
    r = client.get("/api/preflight?q=")
    assert r.status_code == 400


# --------------------------------------------------------------------------
# Honesty invariants of the consumer copy
# --------------------------------------------------------------------------

def test_diagnostic_never_promises_it_is_validated(client):
    """Any diagnostic language that reaches the consumer view must
    include the hypothesis-not-guarantee caveat somewhere. If future
    edits forget this, the test fails and the finding-doc contract
    with the reader breaks."""
    r = client.get("/api/preflight?q=test subject")
    d = r.json()["consumer"]["diagnostic_line"].lower()
    assert "hypothesis" in d or "haven't validated" in d or "not a guarantee" in d


def test_dev_verdict_carries_the_n1_caveat(client):
    """Dev-mode verdict must still say n=1 / not validated."""
    r = client.get("/api/preflight?q=test subject")
    verd = r.json()["dev"]["verdict"]
    txt = verd["caveat"].lower()
    assert "not validated" in txt or "n=1" in txt


def test_cost_estimate_uses_corrected_pricing(client):
    """A ~300-match subject → target ~200 papers → est extraction ~$5."""
    r = client.get("/api/preflight?q=test subject")
    cost = r.json()["dev"]["cost_projection"]
    assert cost["target_papers"] == 200
    # 200 * (0.55*0.0336 + 0.45*0.0109) ≈ 200 * 0.0234 ≈ $4.68
    assert 4.5 < cost["est_extraction_usd"] < 5.0
    # Total < $10 at N=200 per the scaling study.
    assert cost["est_total_usd"] < 10


def test_consumer_never_says_the_button_works(client):
    """The build_library.not_yet copy already promises this, but the
    preflight response should not accidentally imply the button
    triggers a build."""
    r = client.get("/api/preflight?q=test subject")
    joined = " ".join(str(v).lower() for v in r.json()["consumer"].values())
    for verboten in ("click here to build", "starting the build",
                     "your library is being built"):
        assert verboten not in joined


# --------------------------------------------------------------------------
# Cache behaviour
# --------------------------------------------------------------------------

def test_repeat_query_hits_cache_no_network(client, monkeypatch):
    """A second identical query MUST NOT trigger a network fetch."""
    calls = []

    def _forbidden_fetch(*_a, **_kw):
        calls.append(1)
        raise AssertionError("preflight should not fetch on cache hit")

    monkeypatch.setattr(PF, "_fetch", _forbidden_fetch)
    r1 = client.get("/api/preflight?q=test subject")
    r2 = client.get("/api/preflight?q=test subject")
    assert r1.status_code == 200 and r2.status_code == 200
    assert calls == []


def test_slugify_normalises_trivial_variants():
    """'Test Subject', 'test subject', 'test  subject' → same slug so
    cache hits survive case + whitespace differences."""
    a = PF._slugify("Test Subject")
    b = PF._slugify("test subject")
    c = PF._slugify("test  subject")
    assert a == b == c
