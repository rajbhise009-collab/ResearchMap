-- 004_paper_extractions.sql
--
-- Persistence + per-item provenance for Phase 2 extraction.
--
-- Adds:
--   * paper_extractions        — metadata for each extraction run
--   * extraction_id FKs on:    claims, evidence, limitations,
--                              methodologies, future_work
--
-- Every child row records the extraction that produced it, so a
-- future reader can always answer "which prompt version emitted this
-- Claim?". FKs are ON DELETE SET NULL so purging an extraction
-- doesn't cascade into the entity records — the records survive as
-- unlinked history.

CREATE TABLE IF NOT EXISTS paper_extractions (
    id            TEXT PRIMARY KEY,
    paper_id      TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    extractor     TEXT NOT NULL,
    prompt_hash   TEXT NOT NULL,
    extracted_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS paper_extractions_paper_idx
    ON paper_extractions(paper_id);
CREATE INDEX IF NOT EXISTS paper_extractions_prompt_hash_idx
    ON paper_extractions(prompt_hash);

ALTER TABLE claims
    ADD COLUMN IF NOT EXISTS extraction_id TEXT
    REFERENCES paper_extractions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS claims_extraction_idx
    ON claims(extraction_id);

ALTER TABLE evidence
    ADD COLUMN IF NOT EXISTS extraction_id TEXT
    REFERENCES paper_extractions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS evidence_extraction_idx
    ON evidence(extraction_id);

ALTER TABLE limitations
    ADD COLUMN IF NOT EXISTS extraction_id TEXT
    REFERENCES paper_extractions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS limitations_extraction_idx
    ON limitations(extraction_id);

ALTER TABLE methodologies
    ADD COLUMN IF NOT EXISTS extraction_id TEXT
    REFERENCES paper_extractions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS methodologies_extraction_idx
    ON methodologies(extraction_id);

ALTER TABLE future_work
    ADD COLUMN IF NOT EXISTS extraction_id TEXT
    REFERENCES paper_extractions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS future_work_extraction_idx
    ON future_work(extraction_id);
