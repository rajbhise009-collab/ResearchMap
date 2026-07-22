"""Tests for the schema pressure-test fields:
   Limitation.source_scope + Claim.source_sentence_id."""

from __future__ import annotations

import pytest

from backend.app.models import (
    Claim,
    ClaimType,
    Limitation,
    LimitationScope,
)


# --- Limitation.source_scope ------------------------------------------


def test_limitation_defaults_to_this_work_scope():
    """Backwards-compat: any pre-existing extraction that didn't set
    the field lands as this_work (the persistent-limitations scorer's
    safer interpretation)."""
    lim = Limitation(
        id="L1", paper_id="p1", text="Sample size is small",
        normalized_category="statistical-power",
    )
    assert lim.source_scope == LimitationScope.THIS_WORK.value


def test_limitation_accepts_prior_work_scope():
    lim = Limitation(
        id="L1", paper_id="p1",
        text="Existing methods are overconfident",
        normalized_category="calibration",
        source_scope=LimitationScope.PRIOR_WORK,
    )
    assert lim.source_scope == LimitationScope.PRIOR_WORK.value


def test_limitation_rejects_unknown_scope():
    with pytest.raises(Exception):
        Limitation(
            id="L1", paper_id="p1", text="X", normalized_category="c",
            source_scope="future_work",  # not a valid enum value
        )


# --- Claim.source_sentence_id -----------------------------------------


def test_claim_source_sentence_id_defaults_to_none():
    c = Claim(
        id="c1", paper_id="p1",
        text="LLMs are miscalibrated at horizon 336.",
        type=ClaimType.FINDING, confidence=0.8,
    )
    assert c.source_sentence_id is None


def test_claim_source_sentence_id_records_split_parent():
    """When a compound is split by the parser, each atom's
    source_sentence_id points at the parent Claim.id."""
    parent = Claim(
        id="c1", paper_id="p1",
        text="X is true, and Y is also true.",
        type=ClaimType.FINDING, confidence=0.7,
    )
    atom = Claim(
        id="c1:s1", paper_id="p1",
        text="X is true",
        type=ClaimType.FINDING, confidence=0.7,
        source_sentence_id=parent.id,
    )
    assert atom.source_sentence_id == "c1"
