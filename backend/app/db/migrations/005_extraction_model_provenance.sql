-- 005_extraction_model_provenance.sql
--
-- Adds the MODEL to extraction provenance.
--
-- The model that produced an extraction is part of what produced the
-- output — as much as the prompt version is. Without it recorded, a
-- later cross-model comparison (or the planned abstract-vs-fulltext
-- comparison) cannot tell which model any given record came from, and
-- the cache could silently serve an old model's extraction for a new
-- model's request.
--
-- The paper_extractions.id itself now encodes the model
-- (<paper_id>#<model>#<prompt_hash>), so this column is a denormalized
-- convenience for indexed lookups / filtering by model.
--
-- Backfill: existing rows (if any) get 'unknown' — there are none in
-- practice since no live extraction had persisted before this migration.

ALTER TABLE paper_extractions
    ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS paper_extractions_model_idx
    ON paper_extractions(model);

-- Drop the default now that the column exists; future inserts must
-- supply the model explicitly.
ALTER TABLE paper_extractions
    ALTER COLUMN model DROP DEFAULT;
