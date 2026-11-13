"""Create baomatdulieu_demo and copy the verified benchmark corpus into it.

Copies only documents, chunks and real embeddings. Benchmark users, MFA secrets,
audit rows, query cases and experiment measurements are deliberately excluded.
This script never drops or truncates a database.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from db_config import (  # noqa: E402
    DEMO_DATABASE_NAME,
    BENCHMARK_DATABASE_NAME,
    get_benchmark_db_config,
    get_demo_db_config,
)

EXPECTED_DOCUMENTS = 16000
EXPECTED_CHUNKS = 48000
BATCH_SIZE = 500
SCHEMA_FILES = (
    ROOT / "database" / "init" / "01_extensions.sql",
    ROOT / "database" / "init" / "02_schema.sql",
    ROOT / "database" / "init" / "05_audit.sql",
)


def connect(config, application_name):
    return psycopg2.connect(
        connect_timeout=15,
        application_name=application_name,
        **config,
    )


def benchmark_inventory(source_conn):
    with source_conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        if cur.fetchone()[0] != BENCHMARK_DATABASE_NAME:
            raise RuntimeError("Safety stop: source is not the benchmark database.")
        cur.execute("SELECT COUNT(*) FROM documents")
        documents = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE embedding IS NULL),
                   COUNT(*) FILTER (WHERE vector_kind IS DISTINCT FROM 'real')
            FROM chunks
            """
        )
        chunks, missing_embeddings, non_real_embeddings = map(int, cur.fetchone())
    if documents != EXPECTED_DOCUMENTS or chunks != EXPECTED_CHUNKS:
        raise RuntimeError(
            f"Benchmark corpus incomplete: expected {EXPECTED_DOCUMENTS:,} documents/"
            f"{EXPECTED_CHUNKS:,} chunks, found {documents:,}/{chunks:,}."
        )
    if missing_embeddings or non_real_embeddings:
        raise RuntimeError(
            "Benchmark chunks must all have real embeddings before copying; "
            f"missing={missing_embeddings:,}, synthetic_or_unknown={non_real_embeddings:,}."
        )
    return documents, chunks


def database_exists(maintenance_conn, database_name):
    with maintenance_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
        return cur.fetchone() is not None


def create_target_database(demo_config):
    maintenance_name = os.getenv("PG_MAINTENANCE_DB", "postgres")
    if maintenance_name in {DEMO_DATABASE_NAME, BENCHMARK_DATABASE_NAME}:
        raise RuntimeError("PG_MAINTENANCE_DB must be a maintenance database such as 'postgres'.")
    maintenance_config = dict(demo_config)
    maintenance_config["dbname"] = maintenance_name
    conn = connect(maintenance_config, "demo_database_provisioner")
    try:
        # CREATE DATABASE is not allowed inside a PostgreSQL transaction.
        conn.autocommit = True
        exists = database_exists(conn, DEMO_DATABASE_NAME)
        if not exists:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DEMO_DATABASE_NAME))
                )
            print(f"Created database: {DEMO_DATABASE_NAME}")
        else:
            print(f"Database already exists: {DEMO_DATABASE_NAME}")
        return not exists
    finally:
        conn.close()


def target_state(demo_conn):
    with demo_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        table_count = int(cur.fetchone()[0])
        if table_count == 0:
            return "empty"
        cur.execute(
            """
            SELECT to_regclass('public.documents'),
                   to_regclass('public.chunks'),
                   to_regclass('public.users'),
                   to_regclass('public.audit_log')
            """
        )
        tables = cur.fetchone()
        if any(value is None for value in tables):
            return "partial"
        cur.execute("SELECT COUNT(*) FROM documents")
        documents = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE embedding IS NOT NULL) FROM chunks"
        )
        chunks, embedded = map(int, cur.fetchone())
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'audit_log'
              AND column_name IN ('request_id', 'stage', 'rule_id', 'release_context')
            """
        )
        audit_columns = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'idx_demo_chunks_embedding_hnsw'
            )
            """
        )
        has_vector_index = bool(cur.fetchone()[0])
    if (
        documents == EXPECTED_DOCUMENTS
        and chunks == EXPECTED_CHUNKS
        and embedded == EXPECTED_CHUNKS
        and audit_columns == 4
        and has_vector_index
    ):
        return "complete"
    return "partial"


def initialize_schema(demo_conn):
    with demo_conn:
        with demo_conn.cursor() as cur:
            for path in SCHEMA_FILES:
                if not path.is_file():
                    raise FileNotFoundError(f"Required schema file not found: {path}")
                cur.execute(path.read_text(encoding="utf-8"))


def set_sequence(cur, table_name):
    # table_name is an internal constant, never user input.
    cur.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{table_name}', 'id'),
            GREATEST(COALESCE(MAX(id), 1), 1),
            COUNT(*) > 0
        )
        FROM {table_name}
        """
    )


def copy_corpus(source_conn, demo_conn):
    # Destination remains one transaction: incomplete copies are rolled back.
    with demo_conn:
        with demo_conn.cursor() as dst:
            with source_conn.cursor(name="demo_document_export") as src:
                src.itersize = BATCH_SIZE
                src.execute(
                    """
                    SELECT id, title, content, classification::text,
                           department::text, protection_profile
                    FROM documents
                    ORDER BY id
                    """
                )
                while True:
                    rows = src.fetchmany(BATCH_SIZE)
                    if not rows:
                        break
                    execute_values(
                        dst,
                        """
                        INSERT INTO documents
                            (id, title, content, classification, department, protection_profile)
                        VALUES %s
                        """,
                        rows,
                        template="(%s, %s, %s, %s::class_t, %s::dept_t, %s)",
                        page_size=BATCH_SIZE,
                    )

            with source_conn.cursor(name="demo_chunk_export") as src:
                src.itersize = BATCH_SIZE
                src.execute(
                    """
                    SELECT id, document_id, content, embedding::text
                    FROM chunks
                    WHERE embedding IS NOT NULL AND vector_kind = 'real'
                    ORDER BY id
                    """
                )
                while True:
                    rows = src.fetchmany(BATCH_SIZE)
                    if not rows:
                        break
                    execute_values(
                        dst,
                        "INSERT INTO chunks (id, document_id, content, embedding) VALUES %s",
                        rows,
                        template="(%s, %s, %s, %s::vector)",
                        page_size=BATCH_SIZE,
                    )

            set_sequence(dst, "documents")
            set_sequence(dst, "chunks")
            dst.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_demo_chunks_embedding_hnsw
                ON chunks USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
                """
            )
            dst.execute("ANALYZE documents")
            dst.execute("ANALYZE chunks")


def verify_target(demo_conn):
    with demo_conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        database = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM documents")
        documents = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE embedding IS NOT NULL) FROM chunks"
        )
        chunks, embedded = map(int, cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM users")
        users = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM audit_log")
        audit_rows = int(cur.fetchone()[0])
    if (
        database != DEMO_DATABASE_NAME
        or documents != EXPECTED_DOCUMENTS
        or chunks != EXPECTED_CHUNKS
        or embedded != EXPECTED_CHUNKS
    ):
        raise RuntimeError(
            "Demo database verification failed: "
            f"database={database}, documents={documents}, chunks={chunks}, embeddings={embedded}."
        )
    return documents, chunks, users, audit_rows


def main():
    demo_config = get_demo_db_config()
    source_config = get_benchmark_db_config()
    if demo_config["dbname"] == source_config["dbname"]:
        raise RuntimeError("Source and destination databases must be different.")

    source_conn = connect(source_config, "demo_benchmark_source_readonly")
    try:
        source_conn.set_session(readonly=True, autocommit=False)
        benchmark_inventory(source_conn)
        create_target_database(demo_config)

        # Do not nest psycopg2 connection context managers. Schema/copy helpers
        # each own their transaction on this explicitly managed connection.
        demo_conn = connect(demo_config, "demo_database_import")
        try:
            state = target_state(demo_conn)
            if state == "complete":
                verified = verify_target(demo_conn)
                print(
                    f"Already provisioned: {verified[0]:,} documents, "
                    f"{verified[1]:,} chunks, {verified[2]:,} users, "
                    f"{verified[3]:,} audit rows."
                )
                return 0
            if state != "empty":
                raise RuntimeError(
                    f"{DEMO_DATABASE_NAME} exists but is not empty or fully provisioned. "
                    "No tables or data were dropped. Inspect it manually before retrying."
                )
            initialize_schema(demo_conn)
            copy_corpus(source_conn, demo_conn)
            verified = verify_target(demo_conn)
        finally:
            demo_conn.close()
    finally:
        source_conn.close()

    print(f"Provisioned database: {DEMO_DATABASE_NAME}")
    print(f"Copied documents: {verified[0]:,}")
    print(f"Copied chunks with real embeddings: {verified[1]:,}")
    print("Users copied: 0 (Demo users and MFA are provisioned separately).")
    print("Audit rows copied: 0 (Demo audit starts clean).")
    print("Vector index: idx_demo_chunks_embedding_hnsw")
    print("Source benchmark database was read-only and was not modified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
