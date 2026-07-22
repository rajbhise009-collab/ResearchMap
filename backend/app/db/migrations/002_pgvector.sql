-- Adds pgvector-backed embedding columns used by the Phase 3 relationship
-- layer. Kept in a separate migration because embeddings are not needed
-- for Phase 0/1 to run.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE claims
    ADD COLUMN IF NOT EXISTS embedding vector(768);

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS abstract_embedding vector(768);

-- IVF indexes are added once the corpus is populated (>10k rows) so they
-- have realistic centroids; skipped here to keep the migration fast on
-- an empty schema.
