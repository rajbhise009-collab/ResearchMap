-- Phase 3 two-stage future-work matcher: structured "addressed" verdicts
-- with full provenance, mirroring claim_relationships. The LLM sets label/
-- justification (perception); similarity + cites_source are deterministic.
-- Additive only.

CREATE TABLE IF NOT EXISTS future_work_addressals (
    id                 text PRIMARY KEY,
    future_work_id     text NOT NULL REFERENCES future_work(id) ON DELETE CASCADE,
    from_paper_id      text NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    to_paper_id        text NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    label              text NOT NULL,
    justification      text,
    addressing_element text,
    similarity         double precision NOT NULL,
    cites_source       boolean NOT NULL DEFAULT false,
    detector_model     text,
    prompt_hash        text
);

CREATE INDEX IF NOT EXISTS ix_fwa_future_work ON future_work_addressals(future_work_id);
CREATE INDEX IF NOT EXISTS ix_fwa_from_paper  ON future_work_addressals(from_paper_id);
CREATE INDEX IF NOT EXISTS ix_fwa_to_paper    ON future_work_addressals(to_paper_id);
CREATE INDEX IF NOT EXISTS ix_fwa_label       ON future_work_addressals(label);
CREATE INDEX IF NOT EXISTS ix_fwa_model       ON future_work_addressals(detector_model);
CREATE INDEX IF NOT EXISTS ix_fwa_prompt      ON future_work_addressals(prompt_hash);
