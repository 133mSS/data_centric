-- ============================================================
-- 02_schema.sql
-- Project: Data-Centric Access Control for RAG
-- Phase 2: Database Design
-- ============================================================

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

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


-- ============================================================
-- 2. USERS
-- ============================================================

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          role_t NOT NULL,
    department    dept_t,
    mfa_secret    TEXT,

    CONSTRAINT user_dept_rule CHECK (
        (role = 'Đối tác' AND department IS NULL)
        OR
        (role = 'Ban lãnh đạo' AND department = 'Toàn công ty')
        OR
        (
            role IN ('Nhân viên', 'Manager')
            AND department IN ('Kỹ thuật', 'Kinh doanh')
        )
    )
);


-- ============================================================
-- 3. DOCUMENTS
-- ============================================================

CREATE TABLE documents (
    id             SERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    content        TEXT NOT NULL,
    classification class_t NOT NULL,
    department     dept_t,
    protection_profile TEXT NOT NULL DEFAULT 'GENERAL_INTERNAL',

    CONSTRAINT doc_protection_profile_valid CHECK (protection_profile IN (
        'PUBLIC', 'GENERAL_INTERNAL', 'PERFORMANCE_SENSITIVE',
        'CORPORATE_SECRET', 'COMMERCIAL_SECRET', 'TECHNICAL_SENSITIVE',
        'MAINTENANCE_NOTICE', 'PUBLIC_RECRUITMENT'
    )),
    CONSTRAINT doc_dept_rule CHECK (
        -- Công khai: không thuộc phòng ban cụ thể
        (classification = 'Công khai' AND department IS NULL)

        OR

        -- Nội bộ: có thể là toàn công ty hoặc thuộc một phòng ban
        (classification = 'Nội bộ')

        OR

        -- Mật / Tối mật: bắt buộc phải xác định phạm vi phòng ban
        (classification IN ('Mật', 'Tối mật')
         AND department IS NOT NULL)
    )
);


-- ============================================================
-- 4. CHUNKS
-- ============================================================

CREATE TABLE chunks (
    id          SERIAL PRIMARY KEY,
    document_id INT NOT NULL
                REFERENCES documents(id)
                ON DELETE CASCADE,

    content     TEXT NOT NULL,

    -- 768 chiều tương ứng với embedding model
    -- đang được lựa chọn trong D003.
    embedding   vector(768)
);


-- ============================================================
-- 5. AUDIT LOG
-- ============================================================

CREATE TABLE audit_log (
    id             BIGSERIAL PRIMARY KEY,

    user_id        INT
                   REFERENCES users(id),

    document_id    INT
                   REFERENCES documents(id),

    chunk_id       INT
                   REFERENCES chunks(id),

    decision       decision_t NOT NULL,

    reason         TEXT,

    -- Phiên bản policy-as-code đã tạo ra quyết định
    policy_version TEXT,

    -- Query của người dùng để phục vụ audit
    query_text     TEXT,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);