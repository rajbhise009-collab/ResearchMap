-- ResearchMap initial schema.
-- Runs on plain local Postgres. pgvector is optional here; the vector
-- column is introduced in migration 002 when the relationship layer
-- (Phase 3) starts producing embeddings.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
    id                    TEXT PRIMARY KEY,
    source                TEXT NOT NULL,
    source_id             TEXT NOT NULL,
    doi                   TEXT,
    title                 TEXT NOT NULL,
    abstract              TEXT,
    year                  INTEGER,
    authors               TEXT[] NOT NULL DEFAULT '{}',
    venue                 TEXT,
    citations_out         TEXT[] NOT NULL DEFAULT '{}',
    citations_in_count    INTEGER NOT NULL DEFAULT 0,
    oa_fulltext_available BOOLEAN NOT NULL DEFAULT FALSE,
    fulltext              TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS papers_doi_idx    ON papers(doi);
CREATE INDEX IF NOT EXISTS papers_source_idx ON papers(source);
CREATE INDEX IF NOT EXISTS papers_year_idx   ON papers(year);

CREATE TABLE IF NOT EXISTS claims (
    id         TEXT PRIMARY KEY,
    paper_id   TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    type       TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS claims_paper_idx ON claims(paper_id);
CREATE INDEX IF NOT EXISTS claims_type_idx  ON claims(type);

CREATE TABLE IF NOT EXISTS evidence (
    id          TEXT PRIMARY KEY,
    claim_id    TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    strength    DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS evidence_claim_idx ON evidence(claim_id);

CREATE TABLE IF NOT EXISTS methodologies (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    datasets    TEXT[] NOT NULL DEFAULT '{}',
    conditions  TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS methodologies_paper_idx ON methodologies(paper_id);

CREATE TABLE IF NOT EXISTS limitations (
    id                  TEXT PRIMARY KEY,
    paper_id            TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    text                TEXT NOT NULL,
    normalized_category TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS limitations_paper_idx    ON limitations(paper_id);
CREATE INDEX IF NOT EXISTS limitations_category_idx ON limitations(normalized_category);

CREATE TABLE IF NOT EXISTS future_work (
    id           TEXT PRIMARY KEY,
    paper_id     TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    text         TEXT NOT NULL,
    addressed_by TEXT REFERENCES papers(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS future_work_paper_idx ON future_work(paper_id);

CREATE TABLE IF NOT EXISTS claim_relationships (
    id            TEXT PRIMARY KEY,
    from_claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    to_claim_id   TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    weight        DOUBLE PRECISION NOT NULL,
    evidence_note TEXT,
    CHECK (from_claim_id <> to_claim_id)
);
CREATE INDEX IF NOT EXISTS claim_rel_from_idx ON claim_relationships(from_claim_id);
CREATE INDEX IF NOT EXISTS claim_rel_to_idx   ON claim_relationships(to_claim_id);
CREATE INDEX IF NOT EXISTS claim_rel_type_idx ON claim_relationships(type);

CREATE TABLE IF NOT EXISTS opportunities (
    id                   TEXT PRIMARY KEY,
    gap_type             TEXT NOT NULL,
    title                TEXT NOT NULL,
    score                DOUBLE PRECISION NOT NULL,
    component_scores     JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation          TEXT NOT NULL,
    supporting_paper_ids TEXT[] NOT NULL DEFAULT '{}',
    contradiction_ids    TEXT[] NOT NULL DEFAULT '{}',
    confidence           DOUBLE PRECISION NOT NULL,
    evidence_trail       TEXT[] NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS opportunities_gap_type_idx ON opportunities(gap_type);
CREATE INDEX IF NOT EXISTS opportunities_score_idx    ON opportunities(score DESC);
