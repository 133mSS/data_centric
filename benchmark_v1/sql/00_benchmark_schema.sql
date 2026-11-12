-- ============================================================
-- Benchmark v1: schema initialization
-- Run this file ONLY after connecting to database:
--   baomatdulieu_benchmark
--
-- Prerequisite:
--   PostgreSQL 16 + pgvector installed on the PostgreSQL server.
--
-- This script creates benchmark-specific tables and the core
-- application tables needed by the existing retrieval/policy code.
-- It is intended for a NEW, EMPTY benchmark database.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- -------------------------
-- 1. ENUM TYPES
-- -------------------------
CREATE TYPE role_t AS ENUM (
    'Nhân viên',
    'Manager',
    'Ban lãnh đạo',
    'Đối tác'
);

CREATE TYPE dept_t AS ENUM (
    'Kỹ thuật',
    'Kinh doanh',
    'Toàn công ty'
);

CREATE TYPE class_t AS ENUM (
    'Công khai',
    'Nội bộ',
    'Mật',
    'Tối mật'
);

CREATE TYPE decision_t AS ENUM (
    'ALLOW',
    'DENY',
    'REDACT'
);

-- -------------------------
-- 2. CORE APPLICATION TABLES
-- Keep names/columns compatible with current project code.
-- -------------------------
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL DEFAULT 'benchmark-placeholder',
    role          role_t NOT NULL,
    department    dept_t,
    mfa_secret    TEXT,
    CONSTRAINT user_dept_rule CHECK (
        (role = 'Đối tác' AND department IS NULL)
        OR (role = 'Ban lãnh đạo' AND department = 'Toàn công ty')
        OR (
            role IN ('Nhân viên', 'Manager')
            AND department IN ('Kỹ thuật', 'Kinh doanh')
        )
    )
);

CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    classification  class_t NOT NULL,
    department      dept_t,
    protection_profile TEXT NOT NULL DEFAULT 'GENERAL_INTERNAL',
    benchmark_scale INTEGER,
    generation_seed BIGINT,
    CONSTRAINT doc_protection_profile_valid CHECK (protection_profile IN (
        'PUBLIC', 'GENERAL_INTERNAL', 'PERFORMANCE_SENSITIVE',
        'CORPORATE_SECRET', 'COMMERCIAL_SECRET', 'TECHNICAL_SENSITIVE',
        'MAINTENANCE_NOTICE', 'PUBLIC_RECRUITMENT'
    )),
    CONSTRAINT doc_dept_rule CHECK (
        (classification = 'Công khai' AND department IS NULL)
        OR (classification = 'Nội bộ')
        OR (
            classification IN ('Mật', 'Tối mật')
            AND department IS NOT NULL
        )
    ),
    CONSTRAINT document_scale_valid CHECK (
        benchmark_scale IS NULL
        OR benchmark_scale IN (1000, 5000, 10000)
    )
);

CREATE INDEX idx_documents_benchmark_scale
    ON documents (benchmark_scale, id);

CREATE TABLE chunks (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL
                REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    embedding   vector(768),
    chunk_no    SMALLINT,
    vector_kind TEXT,
    CONSTRAINT chunk_no_valid CHECK (
        chunk_no IS NULL OR chunk_no BETWEEN 1 AND 3
    ),
    CONSTRAINT vector_kind_valid CHECK (
        vector_kind IS NULL
        OR vector_kind IN ('synthetic', 'real')
    )
);

CREATE INDEX idx_chunks_document_id ON chunks (document_id);

CREATE TABLE audit_log (
    id             BIGSERIAL PRIMARY KEY,
    user_id        INTEGER REFERENCES users(id),
    document_id    INTEGER REFERENCES documents(id),
    chunk_id       INTEGER REFERENCES chunks(id),
    decision       decision_t NOT NULL,
    reason         TEXT,
    policy_version TEXT,
    query_text     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------
-- 3. BENCHMARK RUN METADATA
-- One row per experiment run/configuration.
-- -------------------------
CREATE TABLE benchmark_runs (
    id                  BIGSERIAL PRIMARY KEY,
    run_name            TEXT NOT NULL,
    system_variant      TEXT NOT NULL
                        CHECK (system_variant IN ('baseline', 'controlled')),
    experiment_type     TEXT NOT NULL
                        CHECK (experiment_type IN (
                            'performance_synthetic',
                            'retrieval_real_embedding',
                            'security_leakage'
                        )),
    dataset_scale       INTEGER NOT NULL
                        CHECK (dataset_scale IN (1000, 5000, 10000)),
    seed                BIGINT NOT NULL,
    top_k               INTEGER NOT NULL DEFAULT 3 CHECK (top_k > 0),
    vector_dimension    INTEGER NOT NULL DEFAULT 768
                        CHECK (vector_dimension = 768),
    distance_metric     TEXT NOT NULL DEFAULT 'cosine',
    index_description   TEXT NOT NULL DEFAULT 'record actual index configuration',
    postgres_version    TEXT,
    pgvector_version    TEXT,
    embedding_model     TEXT,
    hardware_description TEXT,
    warmup_count        INTEGER NOT NULL DEFAULT 5 CHECK (warmup_count >= 0),
    measurement_count   INTEGER NOT NULL DEFAULT 30
                        CHECK (measurement_count = 30),
    config_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_benchmark_runs_lookup
    ON benchmark_runs (dataset_scale, experiment_type, system_variant);

-- -------------------------
-- 4. QUERY CASES AND GROUND TRUTH
-- A query case is independent from an individual run.
-- -------------------------
CREATE TABLE benchmark_query_cases (
    id                  BIGSERIAL PRIMARY KEY,
    case_key            TEXT UNIQUE NOT NULL,
    query_text          TEXT NOT NULL,
    username            TEXT NOT NULL,
    expected_relevant_document_ids INTEGER[] NOT NULL DEFAULT '{}',
    protected_facts     JSONB NOT NULL DEFAULT '[]'::jsonb,
    test_category       TEXT NOT NULL
                        CHECK (test_category IN (
                            'allowed_retrieval',
                            'denied_retrieval',
                            'mixed_access',
                            'output_leakage'
                        )),
    expected_answerable BOOLEAN NOT NULL DEFAULT TRUE,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------
-- 5. PERFORMANCE RESULTS
-- Store raw timing per query case and repetition; derive P50/P95 afterwards.
-- All durations are milliseconds.
-- -------------------------
CREATE TABLE benchmark_performance_results (
    id                    BIGSERIAL PRIMARY KEY,
    run_id                BIGINT NOT NULL
                          REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    query_case_id         BIGINT NOT NULL
                          REFERENCES benchmark_query_cases(id) ON DELETE CASCADE,
    repetition_no         INTEGER NOT NULL CHECK (repetition_no > 0),
    warmup                BOOLEAN NOT NULL DEFAULT FALSE,
    policy_latency_ms     DOUBLE PRECISION,
    embedding_latency_ms  DOUBLE PRECISION,
    vector_search_ms      DOUBLE PRECISION,
    total_retrieval_ms    DOUBLE PRECISION NOT NULL
                          CHECK (total_retrieval_ms >= 0),
    returned_chunk_count  INTEGER NOT NULL DEFAULT 0
                          CHECK (returned_chunk_count >= 0),
    allowed_document_count INTEGER NOT NULL DEFAULT 0
                          CHECK (allowed_document_count >= 0),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_benchmark_perf_run_case_rep_warmup
        UNIQUE (run_id, query_case_id, repetition_no, warmup),
    CHECK (policy_latency_ms IS NULL OR policy_latency_ms >= 0),
    CHECK (embedding_latency_ms IS NULL OR embedding_latency_ms >= 0),
    CHECK (vector_search_ms IS NULL OR vector_search_ms >= 0)
);

-- -------------------------
-- 6. RETRIEVAL / SECURITY RESULTS
-- Keep policy correctness and retrieval relevance separate.
-- -------------------------
CREATE TABLE benchmark_case_results (
    id                    BIGSERIAL PRIMARY KEY,
    run_id                BIGINT NOT NULL
                          REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    query_case_id         BIGINT NOT NULL
                          REFERENCES benchmark_query_cases(id),
    repetition_no         INTEGER NOT NULL DEFAULT 1 CHECK (repetition_no > 0),
    returned_document_ids INTEGER[] NOT NULL DEFAULT '{}',
    returned_chunk_ids    INTEGER[] NOT NULL DEFAULT '{}',
    unauthorized_chunk_ids INTEGER[] NOT NULL DEFAULT '{}',
    recall_at_k           DOUBLE PRECISION,
    unauthorized_context_count INTEGER NOT NULL DEFAULT 0
                          CHECK (unauthorized_context_count >= 0),
    protected_facts_leaked_exact INTEGER NOT NULL DEFAULT 0
                          CHECK (protected_facts_leaked_exact >= 0),
    semantic_review_required BOOLEAN NOT NULL DEFAULT FALSE,
    semantic_review_result TEXT
                          CHECK (semantic_review_result IS NULL OR
                                 semantic_review_result IN (
                                     'leak', 'no_leak', 'inconclusive', 'not_reviewed'
                                 )),
    output_text           TEXT,
    notes                 TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, query_case_id, repetition_no),
    CHECK (recall_at_k IS NULL OR (recall_at_k >= 0 AND recall_at_k <= 1))
);

CREATE INDEX idx_case_results_run
    ON benchmark_case_results (run_id, query_case_id);

-- -------------------------
-- 7. DATASET VALIDATION SNAPSHOTS
-- Record expected/actual row counts before each benchmark phase.
-- -------------------------
CREATE TABLE benchmark_validation_results (
    id                  BIGSERIAL PRIMARY KEY,
    dataset_scale       INTEGER NOT NULL
                        CHECK (dataset_scale IN (1000, 5000, 10000)),
    seed                BIGINT NOT NULL,
    documents_expected  INTEGER NOT NULL,
    documents_actual    INTEGER NOT NULL,
    chunks_expected     INTEGER NOT NULL,
    chunks_actual       INTEGER NOT NULL,
    chunks_missing_embedding INTEGER NOT NULL,
    invalid_dimension_count INTEGER NOT NULL DEFAULT 0,
    allowed_document_ratio DOUBLE PRECISION,
    validation_passed   BOOLEAN NOT NULL,
    validation_details  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------
-- 8. HELPFUL VALIDATION VIEW
-- -------------------------
CREATE VIEW benchmark_dataset_counts AS
SELECT
    d.benchmark_scale AS dataset_scale,
    COUNT(DISTINCT d.id) AS document_count,
    COUNT(c.id) AS chunk_count,
    COUNT(c.id) FILTER (WHERE c.embedding IS NOT NULL) AS chunks_with_embedding,
    COUNT(c.id) FILTER (WHERE c.embedding IS NULL) AS chunks_without_embedding,
    COUNT(DISTINCT d.id) FILTER (
        WHERE d.classification = 'Công khai'
    ) AS public_documents,
    COUNT(DISTINCT d.id) FILTER (
        WHERE d.classification = 'Nội bộ'
    ) AS internal_documents,
    COUNT(DISTINCT d.id) FILTER (
        WHERE d.classification = 'Mật'
    ) AS secret_documents,
    COUNT(DISTINCT d.id) FILTER (
        WHERE d.classification = 'Tối mật'
    ) AS top_secret_documents
FROM documents d
LEFT JOIN chunks c ON c.document_id = d.id
GROUP BY d.benchmark_scale;
