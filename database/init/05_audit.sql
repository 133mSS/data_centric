-- WP2 audit migration; safe to rerun.
ALTER TYPE decision_t ADD VALUE IF NOT EXISTS 'BLOCK';

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS request_id UUID,
    ADD COLUMN IF NOT EXISTS stage TEXT,
    ADD COLUMN IF NOT EXISTS rule_id TEXT,
    ADD COLUMN IF NOT EXISTS release_context TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'audit_log_stage_valid'
          AND conrelid = 'audit_log'::regclass
    ) THEN
        ALTER TABLE audit_log
            ADD CONSTRAINT audit_log_stage_valid
            CHECK (stage IS NULL OR stage IN ('retrieval', 'output_dlp'))
            NOT VALID;
    END IF;
END $$;
