-- Repair older benchmark DBs where performance rows were keyed only by run/repetition.
-- Run only against baomatdulieu_benchmark. Fresh databases from 00_benchmark_schema.sql
-- already include query_case_id; this migration remains safe to re-run.
BEGIN;

ALTER TABLE benchmark_performance_results
    ADD COLUMN IF NOT EXISTS query_case_id BIGINT
    REFERENCES benchmark_query_cases(id) ON DELETE CASCADE;

-- Older schema allowed only one row per run/repetition/warmup, which conflicts with
-- per-case metrics. Historical rows retain NULL query_case_id because their original
-- case cannot be reconstructed reliably. New benchmark rows must provide query_case_id.
ALTER TABLE benchmark_performance_results
    DROP CONSTRAINT IF EXISTS benchmark_performance_results_run_id_repetition_no_warmup_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_benchmark_perf_run_case_rep_warmup
    ON benchmark_performance_results (run_id, query_case_id, repetition_no, warmup)
    WHERE query_case_id IS NOT NULL;

COMMIT;
