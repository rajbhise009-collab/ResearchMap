"""File-backed persistence for the relationship layer, serialized FROM
the Pydantic/SQLAlchemy models (never a parallel hand-written format).

Chosen over live Postgres because at ~1k claims numpy cosine is
milliseconds and pgvector's ANN indexes buy nothing (see
docs/relationship-layer.md, "Why file-backed"). The on-disk records mirror
the SQLAlchemy tables field-for-field; `schema_columns()` derives the
column set from the ORM so the schema-drift test can prove the file
format and the migration DDL cannot silently diverge. The DB path
(`write_to_db` / `load_relationships_from_db`) works whenever a
DATABASE_URL engine is provided.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.config import REPO_ROOT
from backend.app.db.tables import (
    ClaimEmbeddingRow, ClaimRelationshipRow, FutureWorkAddressalRow,
)
from backend.app.models import (
    ClaimEmbedding, ClaimRelationship, FutureWorkAddressal,
)

DEFAULT_ROOT = REPO_ROOT / "data" / "relationships"


def schema_columns(row_cls) -> set[str]:
    """Column names of a SQLAlchemy table — the source of truth the file
    format and migration DDL must both match."""
    return {c.name for c in row_cls.__table__.columns}


class RelationshipStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths ---
    @property
    def _emb_meta(self) -> Path:
        return self.root / "claim_embeddings.jsonl"

    @property
    def _emb_vecs(self) -> Path:
        return self.root / "claim_embeddings.npy"

    @property
    def _rels(self) -> Path:
        return self.root / "claim_relationships.jsonl"

    # --- embeddings ---
    def save_embeddings(self, embs: list[ClaimEmbedding]) -> None:
        import numpy as np

        # Metadata (every model field except the vector) -> jsonl, in the
        # SAME order as the vector matrix rows.
        with self._emb_meta.open("w", encoding="utf-8") as fh:
            for e in embs:
                d = e.model_dump()
                d.pop("embedding")
                fh.write(json.dumps(d) + "\n")
        vecs = np.array([e.embedding for e in embs], dtype=np.float32) if embs \
            else np.zeros((0, 0), dtype=np.float32)
        np.save(self._emb_vecs, vecs)

    def load_embeddings(self) -> list[ClaimEmbedding]:
        import numpy as np

        if not self._emb_meta.exists():
            return []
        metas = [json.loads(line) for line in
                 self._emb_meta.read_text().splitlines() if line.strip()]
        vecs = np.load(self._emb_vecs)
        out = []
        for i, meta in enumerate(metas):
            out.append(ClaimEmbedding(embedding=vecs[i].tolist(), **meta))
        return out

    def load_vectors(self):
        """Return (claim_ids, ndarray[n,dim]) for fast shortlisting."""
        import numpy as np

        if not self._emb_meta.exists():
            return [], np.zeros((0, 0), dtype=np.float32)
        ids = [json.loads(line)["claim_id"] for line in
               self._emb_meta.read_text().splitlines() if line.strip()]
        return ids, np.load(self._emb_vecs)

    # --- relationships ---
    def save_relationships(self, rels: list[ClaimRelationship]) -> None:
        with self._rels.open("w", encoding="utf-8") as fh:
            for r in rels:
                fh.write(json.dumps(r.model_dump()) + "\n")

    def load_relationships(self) -> list[ClaimRelationship]:
        if not self._rels.exists():
            return []
        return [ClaimRelationship(**json.loads(line)) for line in
                self._rels.read_text().splitlines() if line.strip()]

    # --- future-work addressals (two-stage matcher) ---
    @property
    def _fwa(self) -> Path:
        return self.root / "future_work_addressals.jsonl"

    def save_addressals(self, rows: list[FutureWorkAddressal]) -> None:
        with self._fwa.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r.model_dump()) + "\n")

    def load_addressals(self) -> list[FutureWorkAddressal]:
        if not self._fwa.exists():
            return []
        return [FutureWorkAddressal(**json.loads(line)) for line in
                self._fwa.read_text().splitlines() if line.strip()]

    # --- DATABASE_URL path (used when Postgres is provisioned) ---
    def write_to_db(
        self, session: Session, *,
        embeddings: list[ClaimEmbedding] | None = None,
        relationships: list[ClaimRelationship] | None = None,
        addressals: list[FutureWorkAddressal] | None = None,
    ) -> None:
        """Persist to the real tables via SQLAlchemy. Rows are built
        directly from the Pydantic models (field names match columns), so
        there is no hand-maintained mapping to drift."""
        for e in embeddings or []:
            session.merge(ClaimEmbeddingRow(**e.model_dump()))
        for r in relationships or []:
            session.merge(ClaimRelationshipRow(**r.model_dump()))
        for a in addressals or []:
            session.merge(FutureWorkAddressalRow(**a.model_dump()))
        session.commit()

    def load_relationships_from_db(self, session: Session) -> list[ClaimRelationship]:
        cols = schema_columns(ClaimRelationshipRow)
        out = []
        for row in session.query(ClaimRelationshipRow).all():
            out.append(ClaimRelationship(**{c: getattr(row, c) for c in cols}))
        return out


__all__ = ["RelationshipStore", "schema_columns", "DEFAULT_ROOT"]
