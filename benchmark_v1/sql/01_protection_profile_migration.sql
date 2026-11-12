-- Run once against an existing benchmark_v1 database before using WP6/G10.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS protection_profile TEXT NOT NULL DEFAULT 'GENERAL_INTERNAL';

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS doc_protection_profile_valid;
ALTER TABLE documents
    ADD CONSTRAINT doc_protection_profile_valid CHECK (protection_profile IN (
        'PUBLIC', 'GENERAL_INTERNAL', 'PERFORMANCE_SENSITIVE',
        'CORPORATE_SECRET', 'COMMERCIAL_SECRET', 'TECHNICAL_SENSITIVE',
        'MAINTENANCE_NOTICE', 'PUBLIC_RECRUITMENT'
    ));
