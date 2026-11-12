"""Diagnose WP6 T35/T37 vector ranking without changing production behavior.

Run from project root:
    python experiments/diagnose_t35_t37_retrieval.py

Copy this file to <project-root>/experiments/ before running it.
Requires the same POSTGRES_* environment variables as app/db_config.py and
an available Ollama model `nomic-embed-text`.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import psycopg2
from db_config import get_db_config
from retrieval import get_allowed_document_ids
from vector_search import create_query_embedding, get_user

CASES = [
    {
        "case_id": "T35",
        "username": "nv_dev",
        "query": "Có thể xem tóm tắt chính sách nghỉ phép không?",
        "target_document_id": 2,
    },
    {
        "case_id": "T37",
        "username": "nv_dev",
        "query": "Mô tả công việc kỹ sư dữ liệu gồm những gì?",
        "target_document_id": 8,
    },
]
TOP_K = 3


def show_results(label: str, rows: list[tuple], target_document_id: int) -> None:
    print(f"\n{label} (top_k={TOP_K}):")
    if not rows:
        print("  <no rows>")
        return
    target_rank = None
    for rank, row in enumerate(rows, start=1):
        # row: chunk_id, document_id, title, classification, department, distance
        chunk_id, document_id, title, classification, department, distance = row
        marker = "  <-- TARGET" if document_id == target_document_id else ""
        if document_id == target_document_id and target_rank is None:
            target_rank = rank
        print(
            f"  rank={rank} chunk_id={chunk_id} doc_id={document_id} "
            f"distance={distance:.6f} similarity={1.0-distance:.6f} "
            f"classification={classification!r} department={department!r} "
            f"title={title!r}{marker}"
        )
    if target_rank is None:
        print(f"  Target doc {target_document_id}: NOT IN TOP {TOP_K}")
    else:
        print(f"  Target doc {target_document_id}: rank {target_rank}")


def main() -> int:
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            database_name, database_user = cur.fetchone()
        print(f"Database: {database_name}; DB user: {database_user}")

        for case in CASES:
            print("\n" + "=" * 76)
            print(f"{case['case_id']} | user={case['username']} | target_doc={case['target_document_id']}")
            print(f"Query: {case['query']}")

            user = get_user(conn, case["username"])
            print(f"Resolved user: role={user.get('role')!r}, department={user.get('department')!r}")
            allowed_ids = get_allowed_document_ids(conn, user)
            print(f"Allowed document count: {len(allowed_ids)}; target allowed: {case['target_document_id'] in allowed_ids}")

            embedding = create_query_embedding(case["query"])
            query_vector = "[" + ",".join(str(value) for value in embedding) + "]"
            print(f"Query embedding dimensions: {len(embedding)}")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), COUNT(embedding), MIN(vector_dims(embedding)),
                           MAX(vector_dims(embedding))
                    FROM chunks
                    """
                )
                total_chunks, embedded_chunks, min_dims, max_dims = cur.fetchone()
            print(
                f"DB chunks: total={total_chunks}, embedded={embedded_chunks}, "
                f"embedding_dims_range={min_dims}..{max_dims}"
            )

            sql = """
                SELECT c.id, c.document_id, d.title, d.classification, d.department,
                       c.embedding <=> %s::vector AS distance
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (query_vector, query_vector, TOP_K))
                baseline_rows = cur.fetchall()
            show_results("BASELINE / all embedded chunks", baseline_rows, case["target_document_id"])

            if not allowed_ids:
                controlled_rows = []
            else:
                controlled_sql = """
                    SELECT c.id, c.document_id, d.title, d.classification, d.department,
                           c.embedding <=> %s::vector AS distance
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.embedding IS NOT NULL
                      AND c.document_id = ANY(%s)
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                """
                with conn.cursor() as cur:
                    cur.execute(controlled_sql, (query_vector, allowed_ids, query_vector, TOP_K))
                    controlled_rows = cur.fetchall()
            show_results("CONTROLLED / ACL-filtered before top-k", controlled_rows, case["target_document_id"])

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, classification, department FROM documents WHERE id = %s",
                    (case["target_document_id"],),
                )
                target = cur.fetchone()
            print(f"Target metadata: {target!r}")

    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
