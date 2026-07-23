"""Persist a `PaperExtraction` to Postgres.

Given a SQLAlchemy session, writes one `paper_extractions` row plus
one row per Claim / Evidence / Limitation / Methodology / FutureWork,
each linked back to the `paper_extractions.id` for provenance.

The extraction's id is deterministic: `<paper_id>#<prompt_hash>`. Two
extractions of the same paper under the same prompt idempotently
overwrite; a prompt version bump lands a new row alongside.

This module deliberately makes no DB connection at import time. Call
`persist_extraction(session, extraction, prompt_hash)` from a caller
that has already opened one.
"""

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
from backend.app.models import PaperExtraction


def extraction_id(paper_id: str, model: str, prompt_hash: str) -> str:
    """Deterministic id for a (paper, model, prompt version) triple.

    The MODEL is part of the identity: two extractions of the same paper
    under the same prompt but a different model are DIFFERENT extractions
    and must not collide.
    """
    return f"{paper_id}#{model}#{prompt_hash}"


def persist_extraction(
    session,  # sqlalchemy.orm.Session — typed loosely to avoid a hard import
    extraction: PaperExtraction,
    prompt_hash: str,
    model: str | None = None,
) -> str:
    """Persist a `PaperExtraction` and its children under a shared
    extraction id. Returns the extraction id.

    `model` defaults to `extraction.extractor` (the client name, which is
    the model identity). Passed explicitly by callers that distinguish
    the two.

    Uses `session.merge()` on the parent row so re-running against the
    same (paper_id, model, prompt_hash) is idempotent.
    """
    model = model or extraction.extractor
    xid = extraction_id(extraction.paper_id, model, prompt_hash)

    parent = PaperExtractionRow(
        id=xid,
        paper_id=extraction.paper_id,
        extractor=extraction.extractor,
        model=model,
        prompt_hash=prompt_hash,
        extracted_at=extraction.extracted_at or datetime.now(timezone.utc),
    )
    session.merge(parent)

    for c in extraction.claims:
        session.merge(ClaimRow(
            id=c.id,
            paper_id=c.paper_id,
            text=c.text,
            type=c.type,
            confidence=c.confidence,
            source_sentence_id=c.source_sentence_id,
            extraction_id=xid,
        ))
    for e in extraction.evidence:
        session.merge(EvidenceRow(
            id=e.id,
            claim_id=e.claim_id,
            description=e.description,
            strength=e.strength,
            extraction_id=xid,
        ))
    for m in extraction.methodologies:
        session.merge(MethodologyRow(
            id=m.id,
            paper_id=m.paper_id,
            name=m.name,
            description=m.description,
            datasets=list(m.datasets),
            conditions=list(m.conditions),
            extraction_id=xid,
        ))
    for lim in extraction.limitations:
        session.merge(LimitationRow(
            id=lim.id,
            paper_id=lim.paper_id,
            text=lim.text,
            normalized_category=lim.normalized_category,
            source_scope=lim.source_scope,
            extraction_id=xid,
        ))
    for fw in extraction.future_work:
        session.merge(FutureWorkRow(
            id=fw.id,
            paper_id=fw.paper_id,
            text=fw.text,
            addressed_by=fw.addressed_by,
            extraction_id=xid,
        ))

    return xid


__all__ = ["extraction_id", "persist_extraction"]
