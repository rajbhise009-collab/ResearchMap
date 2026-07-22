-- 003_schema_pressure_test.sql
--
-- Applies the two required schema changes from
-- docs/schema-pressure-test.md before Phase 2 extraction goes live:
--
--   1. Limitation.source_scope  — this_work | prior_work; default
--      this_work. Fixes the prior-work-limitation-misattribution
--      failure mode: without this field, the persistent-limitations
--      scorer would double-attribute Paper A's cited limitations to
--      Paper A itself.
--
--   2. Claim.source_sentence_id — nullable text. Populated by the
--      compound-splitting parser when a claim is derived from a
--      sentence that carried multiple assertions. Points at the
--      parent Claim.id from which it was split.
--
-- Both changes are additive; no data loss; safe to run on an empty
-- schema or on live-populated tables.

ALTER TABLE limitations
    ADD COLUMN IF NOT EXISTS source_scope TEXT NOT NULL DEFAULT 'this_work';

CREATE INDEX IF NOT EXISTS limitations_source_scope_idx
    ON limitations(source_scope);

-- Enforce enum values at the DB level.
ALTER TABLE limitations
    DROP CONSTRAINT IF EXISTS limitations_source_scope_check;
ALTER TABLE limitations
    ADD CONSTRAINT limitations_source_scope_check
    CHECK (source_scope IN ('this_work', 'prior_work'));

ALTER TABLE claims
    ADD COLUMN IF NOT EXISTS source_sentence_id TEXT;
