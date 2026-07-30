"""Pydantic v2 schemas — the canonical shape of every ResearchMap object.

Every downstream artifact (extractions, relationships, opportunities) must
validate against these schemas. IDs are strings so they compose cleanly
across sources (openalex:W123, doi:10.x, seed:0001).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


# --- Shared primitives ----------------------------------------------------

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class Source(str, Enum):
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    EUROPE_PMC = "europe_pmc"
    SEED = "seed"


class ClaimType(str, Enum):
    FINDING = "finding"
    METHOD = "method"
    THEORETICAL = "theoretical"
    NEGATIVE = "negative"


class RelationshipType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    DEPENDS_ON = "depends_on"
    SIMILAR_TO = "similar_to"
    USES_METHOD = "uses_method"


class LimitationScope(str, Enum):
    """Whose limitation is this? See docs/schema-pressure-test.md
    decision #1.

    - `this_work`: a limitation of the paper's OWN method, benchmark, or
      empirical findings — including limitations of the subject the
      paper investigates (e.g. "we find LLMs are miscalibrated"). This
      is the evidence the persistent-limitations scorer counts.
    - `prior_work`: a limitation of PRIOR work cited by the paper as
      motivation ("existing methods X have Y problem, so we…"). Almost
      never attributable to the specific prior paper from an abstract
      alone; feeding it to the scorer causes prior-work-limitation
      misattribution (see opportunity-criteria.md).
    """

    THIS_WORK = "this_work"
    PRIOR_WORK = "prior_work"


class GapType(str, Enum):
    UNADDRESSED_LIMITATION = "unaddressed_limitation"
    UNRESOLVED_CONTRADICTION = "unresolved_contradiction"
    UNFOLLOWED_FUTURE_WORK = "unfollowed_future_work"
    METHOD_TRANSFER = "method_transfer"
    UNDER_REPLICATED_FINDING = "under_replicated_finding"


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
        validate_assignment=True,
    )


# --- Core objects ---------------------------------------------------------


class Paper(_Base):
    id: NonEmptyStr
    source: Source
    source_id: NonEmptyStr
    doi: str | None = None
    title: NonEmptyStr
    abstract: str | None = None
    year: int | None = Field(default=None, ge=1600, le=2100)
    authors: list[NonEmptyStr] = Field(default_factory=list)
    venue: str | None = None
    citations_out: list[NonEmptyStr] = Field(default_factory=list)
    citations_in_count: int = Field(default=0, ge=0)
    oa_fulltext_available: bool = False
    fulltext: str | None = None
    # IDs of records collapsed INTO this one by `deduplicate()`. Populated
    # by ingestion when a preprint/journal pair (or any two records for
    # the same work) merges. Never silently dropped — the collapse is
    # always traceable back to every OpenAlex/S2 record that fed it.
    merged_from: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("doi")
    @classmethod
    def _normalize_doi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if v.startswith(prefix):
                v = v[len(prefix):]
        return v or None


class Evidence(_Base):
    id: NonEmptyStr
    claim_id: NonEmptyStr
    description: NonEmptyStr
    strength: Confidence


class Claim(_Base):
    id: NonEmptyStr
    paper_id: NonEmptyStr
    text: NonEmptyStr
    type: ClaimType
    confidence: Confidence
    # If this claim was split out of a compound sentence during
    # extraction, `source_sentence_id` points at the parent Claim.id
    # from which it was derived. Populated by
    # `backend.app.extraction.parse.split_compound_claims`. See
    # docs/schema-pressure-test.md decision #2.
    source_sentence_id: str | None = None


class Methodology(_Base):
    id: NonEmptyStr
    paper_id: NonEmptyStr
    name: NonEmptyStr
    description: str | None = None
    datasets: list[NonEmptyStr] = Field(default_factory=list)
    conditions: list[NonEmptyStr] = Field(default_factory=list)


class Limitation(_Base):
    id: NonEmptyStr
    paper_id: NonEmptyStr
    text: NonEmptyStr
    normalized_category: NonEmptyStr
    # Whose limitation this is. Default `this_work` matches the
    # persistent-limitations scorer's usable-evidence class; extractors
    # must set `prior_work` explicitly when the limitation is being
    # cited from prior work rather than reported about this paper.
    source_scope: LimitationScope = LimitationScope.THIS_WORK


class FutureWork(_Base):
    id: NonEmptyStr
    paper_id: NonEmptyStr
    text: NonEmptyStr
    addressed_by: str | None = None


class ClaimRelationship(_Base):
    id: NonEmptyStr
    from_claim_id: NonEmptyStr
    to_claim_id: NonEmptyStr
    type: RelationshipType
    # `weight` is computed by DETERMINISTIC Python (see
    # relationships/weighting.py), never returned by an LLM. The LLM only
    # perceives the relationship *type* for a single pair; all numbers are
    # code. Must not read Claim.confidence (see docs/confidence-policy.md).
    weight: Confidence
    evidence_note: str | None = None
    # --- Provenance (Phase 3). No orphan conclusions: a relationship must
    # trace to both source papers, the detector model, and the prompt. ---
    from_paper_id: str | None = None
    to_paper_id: str | None = None
    detector_model: str | None = None
    prompt_hash: str | None = None
    # Cosine similarity of the two claim embeddings that shortlisted this
    # pair — a deterministic input to `weight`, recorded for audit.
    similarity: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("to_claim_id")
    @classmethod
    def _no_self_loop(cls, v: str, info) -> str:
        if v == info.data.get("from_claim_id"):
            raise ValueError("ClaimRelationship cannot point a claim at itself")
        return v


class FutureWorkLabel(str, Enum):
    ADDRESSED = "addressed"
    PARTIAL = "partial"
    NOT_ADDRESSED = "not_addressed"


class FutureWorkAddressal(_Base):
    """An LLM verdict on whether a LATER paper addresses an EARLIER paper's
    future-work item — the two-stage matcher's structured output (cosine
    shortlist → LLM classification), with the same provenance discipline as
    ClaimRelationship. The LLM sets `label`/`justification` (perception);
    every number/flag (`similarity`, `cites_source`) is deterministic code.
    """

    id: NonEmptyStr
    future_work_id: NonEmptyStr
    from_paper_id: NonEmptyStr        # paper that raised the future-work item
    to_paper_id: NonEmptyStr          # candidate later paper
    label: FutureWorkLabel
    justification: str | None = None
    addressing_element: str | None = None   # the claim/method that addresses it
    similarity: float = Field(ge=-1.0, le=1.0)   # FW <-> best claim cosine (deterministic)
    cites_source: bool = False        # citation prior (deterministic): to cites from
    detector_model: str | None = None
    prompt_hash: str | None = None

    @field_validator("to_paper_id")
    @classmethod
    def _no_self(cls, v: str, info) -> str:
        if v == info.data.get("from_paper_id"):
            raise ValueError("a paper cannot address its own future work")
        return v


class ClaimEmbedding(_Base):
    """A claim's embedding vector plus the provenance needed for
    mixed-fidelity correction. `input_source` (abstract | fulltext) is
    recorded because full-text and abstract extractions differ in yield
    and a downstream scorer must be able to weight by it."""

    claim_id: NonEmptyStr
    paper_id: NonEmptyStr
    input_source: str
    model: NonEmptyStr
    dim: int = Field(ge=1)
    # Named `embedding` to match ClaimEmbeddingRow.embedding so the model
    # round-trips to the DB row field-for-field (schema-drift guard).
    embedding: list[float] = Field(min_length=1)

    @field_validator("embedding")
    @classmethod
    def _dim_matches(cls, v: list[float], info) -> list[float]:
        dim = info.data.get("dim")
        if dim is not None and len(v) != dim:
            raise ValueError(f"embedding length {len(v)} != declared dim {dim}")
        return v


class Opportunity(_Base):
    id: NonEmptyStr
    gap_type: GapType
    title: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    component_scores: dict[str, float] = Field(default_factory=dict)
    explanation: NonEmptyStr
    supporting_paper_ids: list[NonEmptyStr] = Field(min_length=1)
    contradiction_ids: list[NonEmptyStr] = Field(default_factory=list)
    confidence: Confidence
    evidence_trail: list[NonEmptyStr] = Field(default_factory=list)


# --- Extraction bundle (what the LLM returns per paper) -------------------


class PaperExtraction(_Base):
    """The structured output an LLM produces for one paper.

    This is the ONLY thing an LLM ever writes into the pipeline.
    Everything else — relationships, scores, rankings, opportunities — is
    computed by deterministic Python.
    """

    paper_id: NonEmptyStr
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    methodologies: list[Methodology] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    future_work: list[FutureWork] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extractor: NonEmptyStr = "unknown"

    @field_validator("claims", "evidence", "methodologies", "limitations", "future_work")
    @classmethod
    def _ids_unique(cls, v: list) -> list:
        ids = [item.id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate IDs within extraction bundle")
        return v


__all__ = [
    "ClaimType",
    "ClaimRelationship",
    "ClaimEmbedding",
    "FutureWorkAddressal",
    "FutureWorkLabel",
    "Claim",
    "Confidence",
    "Evidence",
    "FutureWork",
    "GapType",
    "Limitation",
    "LimitationScope",
    "Methodology",
    "NonEmptyStr",
    "Opportunity",
    "Paper",
    "PaperExtraction",
    "RelationshipType",
    "Source",
]
