"""SQLAlchemy 2.x ORM tables mirroring the Pydantic schemas in models/.

pgvector column is defined lazily so the module can be imported (and
tables introspected) on machines without the pgvector Python extra
installed. Actual vector storage is only used from Phase 3 onward.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ResearchMap ORM tables."""


# --- Papers ---------------------------------------------------------------


class PaperRow(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    doi: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    venue: Mapped[str | None] = mapped_column(String, nullable=True)
    citations_out: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    citations_in_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    oa_fulltext_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fulltext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    claims = relationship("ClaimRow", back_populates="paper", cascade="all, delete-orphan")
    methodologies = relationship(
        "MethodologyRow", back_populates="paper", cascade="all, delete-orphan"
    )
    limitations = relationship(
        "LimitationRow", back_populates="paper", cascade="all, delete-orphan"
    )
    future_work = relationship(
        "FutureWorkRow", back_populates="paper", cascade="all, delete-orphan"
    )


# --- Claims & evidence ----------------------------------------------------


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    paper = relationship("PaperRow", back_populates="claims")
    evidence = relationship(
        "EvidenceRow", back_populates="claim", cascade="all, delete-orphan"
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        String, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)

    claim = relationship("ClaimRow", back_populates="evidence")


# --- Methodologies / limitations / future work ---------------------------


class MethodologyRow(Base):
    __tablename__ = "methodologies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    datasets: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    conditions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    paper = relationship("PaperRow", back_populates="methodologies")


class LimitationRow(Base):
    __tablename__ = "limitations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_category: Mapped[str] = mapped_column(String, nullable=False, index=True)

    paper = relationship("PaperRow", back_populates="limitations")


class FutureWorkRow(Base):
    __tablename__ = "future_work"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    addressed_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )

    paper = relationship("PaperRow", back_populates="future_work", foreign_keys=[paper_id])


# --- Relationship layer + opportunities ----------------------------------


class ClaimRelationshipRow(Base):
    __tablename__ = "claim_relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_claim_id: Mapped[str] = mapped_column(
        String, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_claim_id: Mapped[str] = mapped_column(
        String, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OpportunityRow(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    gap_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_paper_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    contradiction_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_trail: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "Base",
    "ClaimRelationshipRow",
    "ClaimRow",
    "EvidenceRow",
    "FutureWorkRow",
    "LimitationRow",
    "MethodologyRow",
    "OpportunityRow",
    "PaperRow",
]
