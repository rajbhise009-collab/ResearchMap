"""Phase 6 — read-only API. Runs with no DATABASE_URL, file-backed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import app
from backend.app.ranking.schema import SCHEMA_VERSION

client = TestClient(app)


def test_runs_without_database_url(monkeypatch):
    # The whole API must work with no DB configured.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert client.get("/api").json()["schema_version"] == SCHEMA_VERSION
    assert client.get("/api/corpus/stats").status_code == 200


def test_opportunities_list_and_pagination():
    r = client.get("/api/opportunities?limit=5&offset=0").json()
    assert r["schema_version"] == SCHEMA_VERSION
    assert r["total"] >= 1 and len(r["items"]) <= 5
    # trust-ordered
    trusts = [c["trust"] for c in r["items"]]
    assert trusts == sorted(trusts, reverse=True)
    p2 = client.get("/api/opportunities?limit=5&offset=5").json()
    assert p2["items"] and p2["items"][0]["id"] != r["items"][0]["id"]


def test_opportunities_filters():
    tier = client.get("/api/opportunities?tier=low").json()
    assert all(c["confidence_tier"] == "low" for c in tier["items"])
    mc = client.get("/api/opportunities?min_confidence=0.6").json()
    assert all(c["confidence"] >= 0.6 for c in mc["items"])
    gt = client.get("/api/opportunities?gap_type=unfollowed_future_work").json()
    assert all(c["gap_type"] == "unfollowed_future_work" for c in gt["items"])


def test_opportunity_detail_and_404():
    first = client.get("/api/opportunities?limit=1").json()["items"][0]
    d = client.get(f"/api/opportunities/{first['id']}").json()
    assert d["id"] == first["id"] and d["evidence_trail"] and d["supporting_papers"]
    assert client.get("/api/opportunities/does-not-exist").status_code == 404


def test_honest_presentation_invariants():
    """Every card exposes tier + gap_type; orphans carry the corpus-relative
    caveat; structural holes carry a confirm status; none lacks an evidence
    trail. The API cannot hide the caveats."""
    for c in client.get("/api/opportunities?limit=500").json()["items"]:
        assert c["gap_type"] and c["confidence_tier"]
        assert c["evidence_trail"], f"{c['id']} has no evidence trail"
        codes = {cv["code"] for cv in c["caveats"]}
        if c["scorer"] == "orphaned_future_work":
            assert "corpus_relative" in codes
        if c["scorer"] == "structural_holes":
            assert c["confirm_status"] in ("substantive", "trivial", "not_addressing", "unconfirmed")
            assert "semantic_lead" in codes


def test_papers_list_filters_and_detail():
    allp = client.get("/api/papers").json()
    assert allp["total"] >= 1
    ft = client.get("/api/papers?input_source=fulltext").json()
    assert all(p["input_source"] == "fulltext" for p in ft["items"])
    ab = client.get("/api/papers?input_source=abstract").json()
    assert all(p["abstract_only"] for p in ab["items"])
    pid = allp["items"][0]["paper_id"]
    d = client.get(f"/api/papers/{pid}").json()
    assert d["paper_id"] == pid
    assert set(["claims", "limitations", "future_work", "methodologies",
                "cites", "cited_by", "abstract_only"]).issubset(d.keys())
    assert client.get("/api/papers/nope").status_code == 404


def test_relationships_and_stats():
    rel = client.get("/api/relationships").json()
    assert "items" in rel and rel["total"] == len(rel["items"])
    s = client.get("/api/corpus/stats").json()
    assert s["papers"] == s["full_text"] + s["abstract_only"]
    assert s["core"] + s["peripheral"] == s["papers"]
    assert "scorer_yields" in s and "spend_to_date_usd" in s and "manifest_hash" in s


def test_findings():
    items = client.get("/api/findings").json()["items"]
    assert items and "markdown" not in items[0]  # list is metadata-only
    slug = items[0]["slug"]
    f = client.get(f"/api/findings/{slug}").json()
    assert f["markdown"].startswith("#")
    assert client.get("/api/findings/nope").status_code == 404


def test_openapi_available():
    assert client.get("/openapi.json").status_code == 200
