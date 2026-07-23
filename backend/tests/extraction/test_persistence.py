"""Persistence tests. Uses a stub in-memory session so we don't depend
on a live Postgres — the test verifies the shape of what would be
persisted, not the DB roundtrip itself."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.db.tables import (
    ClaimRow,
    EvidenceRow,
    FutureWorkRow,
    LimitationRow,
    MethodologyRow,
    PaperExtractionRow,
)
from backend.app.extraction.persistence import (
    extraction_id,
    persist_extraction,
)
from backend.app.models import (
    Claim,
    ClaimType,
    Evidence,
    FutureWork,
    Limitation,
    LimitationScope,
    Methodology,
    PaperExtraction,
)


class _StubSession:
    """Records every merge() call so tests can assert what would land."""

    def __init__(self):
        self.merges: list = []

    def merge(self, obj):
        self.merges.append(obj)
        return obj


def _sample_extraction() -> PaperExtraction:
    pid = "openalex:W1"
    return PaperExtraction(
        paper_id=pid,
        claims=[Claim(
            id=f"{pid}:c1", paper_id=pid,
            text="X reduces MSE by 12%.",
            type=ClaimType.FINDING, confidence=0.9,
        )],
        evidence=[Evidence(
            id=f"{pid}:e1", claim_id=f"{pid}:c1",
            description="Table 3.", strength=0.9,
        )],
        methodologies=[Methodology(
            id=f"{pid}:m1", paper_id=pid,
            name="X-Net", description="Sparse-attention model.",
            datasets=["ETTh1"], conditions=["horizon=336"],
        )],
        limitations=[Limitation(
            id=f"{pid}:l1", paper_id=pid,
            text="Single seed.",
            normalized_category="statistical-power",
            source_scope=LimitationScope.THIS_WORK,
        )],
        future_work=[FutureWork(
            id=f"{pid}:f1", paper_id=pid,
            text="Ablate seeds.",
        )],
        extractor="test",
        extracted_at=datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc),
    )


def test_extraction_id_is_deterministic():
    assert extraction_id("openalex:W1", "gemini:m", "abcdef012345") == (
        "openalex:W1#gemini:m#abcdef012345"
    )


def test_extraction_id_distinguishes_model():
    """Same paper + prompt hash, different model → different id."""
    a = extraction_id("openalex:W1", "gemini:model-A", "hh")
    b = extraction_id("openalex:W1", "gemini:model-B", "hh")
    assert a != b


def test_persist_writes_one_row_per_entity():
    session = _StubSession()
    ext = _sample_extraction()
    prompt_hash = "abcdef012345"

    xid = persist_extraction(session, ext, prompt_hash=prompt_hash)
    # model defaults to extraction.extractor ("test") when not passed.
    assert xid == extraction_id(ext.paper_id, "test", prompt_hash)
    assert session.merges[0].model == "test"

    # Row types produced.
    types = [type(m).__name__ for m in session.merges]
    assert types == [
        "PaperExtractionRow",
        "ClaimRow",
        "EvidenceRow",
        "MethodologyRow",
        "LimitationRow",
        "FutureWorkRow",
    ]


def test_persist_attaches_extraction_id_to_every_child_row():
    session = _StubSession()
    ext = _sample_extraction()
    xid = persist_extraction(session, ext, prompt_hash="hhhhhhhhhhhh")

    parent = session.merges[0]
    assert isinstance(parent, PaperExtractionRow)
    assert parent.id == xid
    assert parent.prompt_hash == "hhhhhhhhhhhh"
    assert parent.extractor == "test"

    for child in session.merges[1:]:
        assert getattr(child, "extraction_id", None) == xid, (
            f"{type(child).__name__} missing extraction_id"
        )


def test_persist_carries_source_scope_on_limitation():
    """Regression: the source_scope value must reach the row unchanged."""
    session = _StubSession()
    pid = "openalex:W2"
    ext = PaperExtraction(
        paper_id=pid,
        limitations=[
            Limitation(id=f"{pid}:l1", paper_id=pid,
                       text="Existing methods overconfident.",
                       normalized_category="calibration",
                       source_scope=LimitationScope.PRIOR_WORK),
            Limitation(id=f"{pid}:l2", paper_id=pid,
                       text="Single seed.",
                       normalized_category="statistical-power",
                       source_scope=LimitationScope.THIS_WORK),
        ],
        extractor="test",
    )
    persist_extraction(session, ext, prompt_hash="hhhhhhhhhhhh")

    lim_rows = [m for m in session.merges if isinstance(m, LimitationRow)]
    scopes = sorted(lim.source_scope for lim in lim_rows)
    assert scopes == ["prior_work", "this_work"]
