"""Schema-level invariants — the shape of every downstream artifact."""

from __future__ import annotations

import pytest

from backend.app.models import (
    Claim,
    ClaimRelationship,
    ClaimType,
    Evidence,
    FutureWork,
    GapType,
    Limitation,
    Methodology,
    Opportunity,
    Paper,
    PaperExtraction,
    RelationshipType,
    Source,
)


def _paper(**over):
    defaults = dict(
        id="seed:0001", source=Source.SEED, source_id="1", title="A",
        abstract="B", year=2024, authors=["X. Y"],
    )
    defaults.update(over)
    return Paper(**defaults)


def test_paper_normalizes_doi():
    p = _paper(doi="https://doi.org/10.1234/ABC.5")
    assert p.doi == "10.1234/abc.5"


def test_paper_rejects_impossible_year():
    with pytest.raises(Exception):
        _paper(year=1500)


def test_paper_forbids_extra_fields():
    with pytest.raises(Exception):
        Paper(
            id="seed:0001", source=Source.SEED, source_id="1", title="A",
            year=2024, mystery_field="oops",
        )


def test_confidence_must_be_within_zero_one():
    with pytest.raises(Exception):
        Claim(id="a", paper_id="p", text="t", type=ClaimType.FINDING, confidence=1.5)


def test_claim_relationship_forbids_self_loop():
    with pytest.raises(Exception):
        ClaimRelationship(
            id="r", from_claim_id="c1", to_claim_id="c1",
            type=RelationshipType.SUPPORTS, weight=0.5,
        )


def test_paper_extraction_rejects_duplicate_claim_ids():
    claims = [
        Claim(id="dup", paper_id="p", text="a", type=ClaimType.FINDING, confidence=0.5),
        Claim(id="dup", paper_id="p", text="b", type=ClaimType.METHOD, confidence=0.5),
    ]
    with pytest.raises(Exception):
        PaperExtraction(paper_id="p", claims=claims)


def test_opportunity_requires_supporting_paper_id():
    with pytest.raises(Exception):
        Opportunity(
            id="o1",
            gap_type=GapType.UNADDRESSED_LIMITATION,
            title="t",
            score=0.5,
            explanation="e",
            supporting_paper_ids=[],  # empty rejected
            confidence=0.5,
        )


def test_full_extraction_roundtrips_through_json():
    ext = PaperExtraction(
        paper_id="seed:0001",
        claims=[Claim(id="c1", paper_id="seed:0001", text="t",
                       type=ClaimType.FINDING, confidence=0.8)],
        evidence=[Evidence(id="e1", claim_id="c1", description="d", strength=0.7)],
        methodologies=[Methodology(id="m1", paper_id="seed:0001", name="Method")],
        limitations=[Limitation(id="l1", paper_id="seed:0001", text="lim",
                                normalized_category="statistical-power")],
        future_work=[FutureWork(id="f1", paper_id="seed:0001", text="fw")],
    )
    round_tripped = PaperExtraction.model_validate_json(ext.model_dump_json())
    assert round_tripped == ext
