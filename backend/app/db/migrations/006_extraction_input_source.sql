-- 006_extraction_input_source.sql
--
-- Adds the INPUT SOURCE (abstract vs fulltext) to extraction provenance.
--
-- The same paper, model, and prompt produce different extractions from
-- the abstract than from the full text. For the controlled
-- abstract-vs-fulltext comparison (Phase 1.5) both must coexist without
-- colliding. input_source is part of the extraction identity, alongside
-- model and prompt_hash.
--
-- The paper_extractions.id now encodes it
-- (<paper_id>#<model>#<input_source>#<prompt_hash>); this column is a
-- denormalized convenience for filtering.

ALTER TABLE paper_extractions
    ADD COLUMN IF NOT EXISTS input_source TEXT NOT NULL DEFAULT 'abstract';

ALTER TABLE paper_extractions
    DROP CONSTRAINT IF EXISTS paper_extractions_input_source_check;
ALTER TABLE paper_extractions
    ADD CONSTRAINT paper_extractions_input_source_check
    CHECK (input_source IN ('abstract', 'fulltext'));

CREATE INDEX IF NOT EXISTS paper_extractions_input_source_idx
    ON paper_extractions(input_source);

-- Drop the default now that the column exists; future inserts supply it.
ALTER TABLE paper_extractions
    ALTER COLUMN input_source DROP DEFAULT;
