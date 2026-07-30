-- Phase 3 relationship layer: provenance on claim_relationships, and a
-- claim_embeddings table that records input_source for mixed-fidelity
-- correction. Additive only (extends the schema; nothing dropped).

-- Relationship provenance: no orphan conclusions — every relationship
-- traces to both source papers, the detector model, and the prompt.
ALTER TABLE claim_relationships
    ADD COLUMN IF NOT EXISTS from_paper_id  text REFERENCES papers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS to_paper_id    text REFERENCES papers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS detector_model text,
    ADD COLUMN IF NOT EXISTS prompt_hash    text,
    ADD COLUMN IF NOT EXISTS similarity     double precision;

CREATE INDEX IF NOT EXISTS ix_claim_relationships_from_paper ON claim_relationships(from_paper_id);
CREATE INDEX IF NOT EXISTS ix_claim_relationships_to_paper   ON claim_relationships(to_paper_id);
CREATE INDEX IF NOT EXISTS ix_claim_relationships_model      ON claim_relationships(detector_model);
CREATE INDEX IF NOT EXISTS ix_claim_relationships_prompt     ON claim_relationships(prompt_hash);

-- Claim embeddings (pgvector). input_source recorded per embedding so a
-- downstream scorer can weight abstract vs full-text extractions.
CREATE TABLE IF NOT EXISTS claim_embeddings (
    claim_id     text PRIMARY KEY REFERENCES claims(id) ON DELETE CASCADE,
    paper_id     text NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    input_source text NOT NULL,
    model        text NOT NULL,
    dim          integer NOT NULL,
    embedding    vector(768) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_claim_embeddings_paper  ON claim_embeddings(paper_id);
CREATE INDEX IF NOT EXISTS ix_claim_embeddings_source ON claim_embeddings(input_source);
CREATE INDEX IF NOT EXISTS ix_claim_embeddings_model  ON claim_embeddings(model);
