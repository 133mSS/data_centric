-- Run against baomatdulieu_benchmark before running the hybrid benchmark.
-- Existing baseline/controlled rows are preserved. This only expands allowed labels.
BEGIN;

ALTER TABLE benchmark_runs
    DROP CONSTRAINT IF EXISTS benchmark_runs_system_variant_check;

ALTER TABLE benchmark_runs
    ADD CONSTRAINT benchmark_runs_system_variant_check
    CHECK (system_variant IN ('baseline', 'controlled', 'hybrid'));

COMMIT;
