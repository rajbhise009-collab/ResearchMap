"""Store round-trips, the schema-drift guard, and the DATABASE_URL path.

These three tests exist because the file format is a serialization of the
DB schema: if the model, the ORM table, and the migration DDL ever
diverge, the file store silently rots. The drift test ties all three
together; the DB-path test proves the normally-unused Postgres loader
still works.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.config import REPO_ROOT
from backend.app.db.tables import ClaimEmbeddingRow, ClaimRelationshipRow
from backend.app.models import ClaimEmbedding, ClaimRelationship
from backend.app.relationships.embeddings import MockEmbeddingClient
from backend.app.relationships.store import RelationshipStore, schema_columns

MIGRATION = REPO_ROOT / "backend" / "app" / "db" / "migrations" / "007_relationship_provenance.sql"


def _emb(i: int) -> ClaimEmbedding:
    v = MockEmbeddingClient(dim=8).embed([f"claim {i}"])[0]
    return ClaimEmbedding(claim_id=f"c{i}", paper_id="p1", input_source="fulltext",
                          model="mock", dim=8, embedding=v)


def _rel() -> ClaimRelationship:
    return ClaimRelationship(
        id="rel:a__contradicts__b", from_claim_id="a", to_claim_id="b",
        type="contradicts", weight=0.7, evidence_note="opposite",
        from_paper_id="p1", to_paper_id="p2", detector_model="m",
        prompt_hash="h", similarity=0.83)


def test_embeddings_round_trip(tmp_path: Path):
    store = RelationshipStore(root=tmp_path)
    embs = [_emb(i) for i in range(3)]
    store.save_embeddings(embs)
    back = store.load_embeddings()
    assert [e.claim_id for e in back] == ["c0", "c1", "c2"]
    assert back[0].input_source == "fulltext"
    assert pytest.approx(back[0].embedding[0], abs=1e-6) == embs[0].embedding[0]


def test_relationships_round_trip(tmp_path: Path):
    store = RelationshipStore(root=tmp_path)
    store.save_relationships([_rel()])
    back = store.load_relationships()
    assert back[0].type == "contradicts"
    assert back[0].from_paper_id == "p1"
    assert back[0].similarity == 0.83


def test_pydantic_fields_match_orm_columns():
    """Model and table must have identical field/column sets — the file
    store serializes straight from the model into the row."""
    assert set(ClaimRelationship.model_fields) == schema_columns(ClaimRelationshipRow)
    assert set(ClaimEmbedding.model_fields) == schema_columns(ClaimEmbeddingRow)


def _ddl_columns(table: str) -> set[str]:
    """Column names for `table` from migration 007 — either its CREATE
    TABLE body or the ADD COLUMNs inside its own ALTER TABLE block. The
    migration is the deploy-time source of truth."""
    sql = MIGRATION.read_text()
    cols: set[str] = set()
    create = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\);", sql, re.DOTALL)
    if create:
        for line in create.group(1).splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY", "FOREIGN", "CONSTRAINT")):
                continue
            cols.add(line.split()[0])
    alter = re.search(rf"ALTER TABLE {table}\b(.*?);", sql, re.DOTALL)
    if alter:
        for add in re.finditer(r"ADD COLUMN IF NOT EXISTS (\w+)", alter.group(1)):
            cols.add(add.group(1))
    return cols


def test_migration_ddl_matches_orm():
    """The claim_embeddings DDL and the relationship-provenance ADD COLUMNs
    must match the ORM, so the on-disk schema can't drift from the DB."""
    emb_ddl = _ddl_columns("claim_embeddings")
    assert emb_ddl == schema_columns(ClaimEmbeddingRow), emb_ddl ^ schema_columns(ClaimEmbeddingRow)
    # Provenance columns added to claim_relationships must all exist on the ORM.
    provenance = {"from_paper_id", "to_paper_id", "detector_model", "prompt_hash", "similarity"}
    assert provenance <= schema_columns(ClaimRelationshipRow)
    added = _ddl_columns("claim_relationships")  # the ADD COLUMNs
    assert provenance <= added


def test_database_url_path_round_trips():
    """The DATABASE_URL loader path must keep working even though it is
    normally unused. SQLite stands in for Postgres here — the
    claim_relationships table is pure String/Float/Text, so it is
    engine-portable (the pgvector embedding table is not, and is
    exercised by the file store instead)."""
    engine = create_engine("sqlite://")
    ClaimRelationshipRow.__table__.create(engine)
    store = RelationshipStore()
    with Session(engine) as session:
        store.write_to_db(session, relationships=[_rel()])
        back = store.load_relationships_from_db(session)
    assert len(back) == 1
    assert back[0].type == "contradicts"
    assert back[0].detector_model == "m"
    assert back[0].similarity == 0.83
