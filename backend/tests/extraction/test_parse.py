"""Compound-splitting parser — the contract from schema-pressure-test #2."""

from __future__ import annotations

from backend.app.extraction.parse import (
    enforce_compound_splitting,
    is_compound,
    split_compound_claims,
)
from backend.app.models import Claim, ClaimType, PaperExtraction


def _c(cid: str, text: str) -> Claim:
    return Claim(
        id=cid, paper_id="p1", text=text,
        type=ClaimType.FINDING, confidence=0.8,
    )


# --- Detection --------------------------------------------------------


def test_atomic_claim_not_split():
    """A fluent single-clause claim must NOT be split, even if it has
    multiple sentences of surrounding context."""
    text = ("Our method reduces MSE on the ETTh1 benchmark. Ablations "
            "confirm the effect is robust to seed choice.")
    assert not is_compound(text)
    assert split_compound_claims([_c("c1", text)]) == [_c("c1", text)]


def test_numeric_enumeration_split():
    """1) X, 2) Y, 3) Z — three atomic claims, correctly split."""
    text = ("Our contributions are 1) a novel calibration objective, "
            "2) a benchmark with 200 items, 3) a state-of-the-art result "
            "on ETTh1.")
    assert is_compound(text)
    out = split_compound_claims([_c("c1", text)])
    assert len(out) == 3
    for i, atom in enumerate(out, start=1):
        assert atom.id == f"c1:s{i}"
        assert atom.source_sentence_id == "c1"
        assert atom.paper_id == "p1"
        assert atom.type == ClaimType.FINDING.value
        assert atom.confidence == 0.8


def test_semicolon_split_when_both_halves_have_verbs():
    text = ("The proposed method achieves state-of-the-art MSE; the "
            "ablations show that the improvement is not driven by "
            "training-data size.")
    assert is_compound(text)
    out = split_compound_claims([_c("c1", text)])
    assert len(out) == 2
    assert all(a.source_sentence_id == "c1" for a in out)


def test_semicolon_not_split_when_second_half_is_just_a_list():
    """A trailing list after a semicolon is NOT a compound."""
    text = ("Three benchmarks were used; ETTh1, ETTh2, and Weather.")
    assert not is_compound(text)


def test_short_fragments_not_split():
    """Enum-looking text with tiny fragments (1) X 2) Y stays atomic
    if the fragments aren't long enough to be independent claims."""
    text = "See table 1) col 2) for details."
    assert not is_compound(text)


def test_splitter_is_idempotent():
    """Running the splitter twice on already-atomic claims doesn't
    over-split or reassign source_sentence_ids."""
    text = "Our method reduces MSE by 12% on ETTh1."
    once = split_compound_claims([_c("c1", text)])
    twice = split_compound_claims(once)
    assert once == twice


# --- Bundle-level -----------------------------------------------------


def test_enforce_compound_splitting_no_op_on_atomic_bundle():
    ext = PaperExtraction(
        paper_id="p1",
        claims=[_c("c1", "MSE is reduced by 12% on ETTh1.")],
        extractor="test",
    )
    out = enforce_compound_splitting(ext)
    assert out.claims == ext.claims


def test_enforce_compound_splitting_rewrites_when_needed():
    ext = PaperExtraction(
        paper_id="p1",
        claims=[
            _c("c1", "Our method achieves the following: "
                     "1) 12% lower MSE than DLinear, "
                     "2) 3x faster inference, "
                     "3) robustness to seed choice."),
            _c("c2", "Ablations confirm the effect."),
        ],
        extractor="test",
    )
    out = enforce_compound_splitting(ext)
    ids = [c.id for c in out.claims]
    # c1 split into 3, c2 stays atomic — total 4 claims.
    assert len(out.claims) == 4
    assert "c1:s1" in ids and "c1:s2" in ids and "c1:s3" in ids
    assert "c2" in ids
    # Every split atom carries source_sentence_id back to c1.
    for c in out.claims:
        if c.id.startswith("c1:"):
            assert c.source_sentence_id == "c1"
