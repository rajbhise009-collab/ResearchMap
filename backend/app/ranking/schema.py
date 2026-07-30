"""Evidence-card schema — the stable, versioned serialization the API and
frontend consume. Deterministic; assembled from scorer output + the corpus.

Design goals (Phase 5):
- gap_type and confidence TIER are first-class fields, not buried in
  component_scores.
- Every caveat that applies (corpus-relative, mixed-fidelity, construct-
  gated, semantic-lead-not-finding, generic-category, unconfirmed) is
  explicit and structured, so the UI can render it inline.
- The full traceable chain opportunity -> claims/limitations/relationships
  -> source papers is resolved, with no orphan references.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Bump on any breaking change to the shapes below. Served at /api and used
# by the frontend to guard against drift.
SCHEMA_VERSION = "1.0.0"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def tier_for(confidence: float) -> ConfidenceTier:
    """Deterministic tiering. Thresholds chosen so the corpus's actual
    confidences land sensibly: contradictions ~0.84 (high), orphans ~0.5
    (medium), structural-hole leads ~0.2 (low)."""
    if confidence >= 0.60:
        return ConfidenceTier.HIGH
    if confidence >= 0.35:
        return ConfidenceTier.MEDIUM
    return ConfidenceTier.LOW


class Caveat(_Base):
    code: str            # machine key, e.g. "corpus_relative"
    label: str           # short UI label
    detail: str          # one-sentence explanation


class SupportingPaper(_Base):
    paper_id: str
    title: str | None = None
    year: int | None = None
    input_source: str
    abstract_only: bool
    domain_centrality: str


class EvidenceItem(_Base):
    kind: str            # paper | claim | limitation | future_work | relationship | method
    id: str
    paper_id: str | None = None
    text: str | None = None


class EvidenceCard(_Base):
    schema_version: str = SCHEMA_VERSION
    id: str
    rank: int
    gap_type: str                       # first-class
    scorer: str
    title: str
    score: float
    confidence: float
    confidence_tier: ConfidenceTier     # first-class
    trust: float                        # score * confidence (ranking key)
    # For structural-hole leads: substantive | trivial | not_addressing | unconfirmed
    confirm_status: str | None = None
    component_scores: dict[str, float] = Field(default_factory=dict)
    explanation: str
    caveats: list[Caveat] = Field(default_factory=list)
    supporting_papers: list[SupportingPaper] = Field(default_factory=list)
    evidence_trail: list[EvidenceItem] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)


__all__ = [
    "SCHEMA_VERSION", "ConfidenceTier", "tier_for",
    "Caveat", "SupportingPaper", "EvidenceItem", "EvidenceCard",
]
