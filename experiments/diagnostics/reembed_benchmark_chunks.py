"""Replace synthetic benchmark vectors with nomic-embed-text embeddings.

SAFE DEFAULT: dry-run only. Pass --apply to write to baomatdulieu_benchmark.
Requires: psycopg2-binary, requests, and a running local Ollama with
nomic-embed-text pulled. Uses Ollama's batch /api/embed endpoint.

The script does not regenerate documents, chunks, users, or query cases.
It updates only chunks whose vector_kind is 'synthetic' or whose embedding is NULL.
Completed batches are committed, so rerunning resumes unfinished chunks.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import psycopg2
import requests
from psycopg2.extras import execute_values

EXPECTED_DB = "baomatdulieu_benchmark"
MODEL = "nomic-embed-text"
DIMENSION = 768
BATCH_SIZE_DEFAULT = 32
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def connect():
    user = os.getenv("BENCHMARK_DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("BENCHMARK_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Set POSTGRES_USER/POSTGRES_PASSWORD in the environment (or override "
            "with BENCHMARK_DB_USER/BENCHMARK_DB_PASSWORD)."
        )
    conn = psycopg2.connect(
        host=os.getenv("BENCHMARK_DB_HOST", os.getenv("POSTGRES_HOST", "localhost")),
        port=int(os.getenv("BENCHMARK_DB_PORT", os.getenv("POSTGRES_PORT", "5432"))),
        dbname=os.getenv("BENCHMARK_DB_NAME", EXPECTED_DB),
        user=user,
        password=password,
        connect_timeout=10,
        application_name="reembed_benchmark_chunks",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
    actual_db = row[0] if row else None
    if actual_db != EXPECTED_DB:
        conn.close()
        raise RuntimeError(
            f"Safety stop: connected to {actual_db!r}, expected {EXPECTED_DB!r}. "
            "No data was changed."
        )
    conn.rollback()  # End the identity-check transaction before callers configure/use the session.
    return conn


def get_embeddings(texts: list[str], session: requests.Session) -> list[list[float]]:
    response = session.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": MODEL, "input": texts, "truncate": False},
        timeout=300,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError(
            "Ollama returned an unexpected batch response. "
            "Expected one embedding per input text; no current batch was written."
        )
    for i, vector in enumerate(embeddings):
        if not isinstance(vector, list) or len(vector) != DIMENSION:
            actual = len(vector) if isinstance(vector, list) else type(vector).__name__
            raise RuntimeError(
                f"Invalid embedding dimension/type at batch item {i}: {actual}; "
                f"expected a list of {DIMENSION} floats. No current batch was written."
            )
    return embeddings


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in vector) + "]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually update embeddings. Without this flag, performs a dry run.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
        help=f"Texts per Ollama request (default: {BATCH_SIZE_DEFAULT}).",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Optional maximum chunks to process; 0 means all remaining chunks.",
    )
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 128:
        parser.error("--batch-size must be between 1 and 128")
    if args.limit < 0:
        parser.error("--limit must be >= 0")

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            total_chunks = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM documents")
            total_documents = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*)
                FROM chunks
                WHERE vector_kind = 'synthetic' OR embedding IS NULL
            """)
            pending = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*)
                FROM chunks
                WHERE vector_kind = 'real' AND embedding IS NOT NULL
            """)
            already_done = cur.fetchone()[0]

        print(f"Database: {EXPECTED_DB}")
        print(f"Documents: {total_documents:,}; chunks: {total_chunks:,}")
        print(f"Chunks already marked real: {already_done:,}")
        print(f"Chunks to process: {pending:,}")
        print(f"Model: {MODEL}; expected dimension: {DIMENSION}")

        if not args.apply:
            print("DRY RUN: no data changed. Add --apply to replace embeddings.")
            return 0
        if pending == 0:
            print("Nothing to do: no synthetic or missing embeddings found.")
            return 0

        session = requests.Session()
        # Verify model availability before starting any writes.
        tags = session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=15)
        tags.raise_for_status()
        model_names = [item.get("name", "") for item in tags.json().get("models", [])]
        if not any(name == MODEL or name.startswith(MODEL + ":") for name in model_names):
            raise RuntimeError(
                f"Ollama model {MODEL!r} is not installed. Run `ollama pull {MODEL}` first. "
                "No data was changed."
            )

        processed = 0
        started = time.time()
        while True:
            with conn.cursor() as cur:
                sql = """
                    SELECT id, content
                    FROM chunks
                    WHERE vector_kind = 'synthetic' OR embedding IS NULL
                    ORDER BY id
                    LIMIT %s
                """
                limit = args.batch_size
                if args.limit:
                    remaining_limit = args.limit - processed
                    if remaining_limit <= 0:
                        break
                    limit = min(limit, remaining_limit)
                cur.execute(sql, (limit,))
                rows = cur.fetchall()

            if not rows:
                break

            ids = [row[0] for row in rows]
            texts = [row[1] for row in rows]
            embeddings = get_embeddings(texts, session)
            updates = [
                (vector_literal(vector), "real", chunk_id)
                for chunk_id, vector in zip(ids, embeddings)
            ]

            # Each batch is atomic. If a batch fails, it is rolled back.
            try:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        UPDATE chunks AS c
                        SET embedding = v.embedding::vector,
                            vector_kind = v.vector_kind
                        FROM (VALUES %s) AS v(embedding, vector_kind, id)
                        WHERE c.id = v.id
                        """,
                        updates,
                        template="(%s, %s, %s)",
                        page_size=len(updates),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

            processed += len(rows)
            elapsed = max(time.time() - started, 0.001)
            print(
                f"[PASS] updated {processed:,} chunks; "
                f"rate={processed / elapsed:.1f} chunks/s"
            )

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_chunks,
                    COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_chunks,
                    COUNT(*) FILTER (WHERE embedding IS NULL) AS missing_embeddings,
                    COUNT(*) FILTER (WHERE vector_kind = 'synthetic') AS synthetic_remaining,
                    COUNT(*) FILTER (WHERE vector_kind = 'real') AS real_model_chunks
                FROM chunks
            """)
            result = cur.fetchone()
        conn.commit()
        print("\nValidation:")
        print(f"total_chunks={result[0]:,}")
        print(f"embedded_chunks={result[1]:,}")
        print(f"missing_embeddings={result[2]:,}")
        print(f"synthetic_remaining={result[3]:,}")
        print(f"{MODEL}_chunks={result[4]:,}")

        if result[2] != 0 or result[3] != 0 or result[4] != result[0]:
            print("VALIDATION FAILED: some chunks remain unfinished; rerun to resume.")
            return 2
        print("VALIDATION PASSED: all chunks use real nomic-embed-text embeddings.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"ERROR: Ollama request failed: {exc}", file=sys.stderr)
        print("No partially returned batch is written. Completed earlier batches remain committed.", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
