"""Hybrid exact/semantic retrieval for the controlled RAG application."""
from __future__ import annotations

import re
import threading

import requests
import psycopg2

from pep import enforce_access
from retrieval import get_allowed_document_ids
from db_config import get_db_config

OLLAMA_URL = "http://localhost:11434/api/embeddings"
_audit_state = threading.local()


def get_last_denied_shadow_chunks():
    return getattr(_audit_state, "denied_shadow_chunks", [])


def create_query_embedding(query):
    response = requests.post(
        OLLAMA_URL,
        json={"model": "nomic-embed-text", "prompt": query},
        timeout=120,
    )
    response.raise_for_status()
    embedding = response.json()["embedding"]
    if len(embedding) != 768:
        raise ValueError(f"Invalid embedding dimension: {len(embedding)}")
    return embedding


def _extract_record_ids(query: str) -> list[str]:
    """Recognize explicit zero-padded dossier numbers without changing them."""
    values = re.findall(r"(?i)(?:hồ\s*sơ|ho\s*so)\s*#?\s*(\d{3,12})", query)
    if not values:
        values = re.findall(r"(?<!\d)#(\d{3,12})(?!\d)", query)
    return list(dict.fromkeys(values))


def vector_search_with_audit(conn, user, query, top_k=3):
    """Return authorized chunks and metadata-only denied shadow candidates."""
    _audit_state.denied_shadow_chunks = []
    if not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")

    allowed_ids = get_allowed_document_ids(conn, user)
    if not allowed_ids:
        return [], []

    record_ids = _extract_record_ids(query)
    embedding = create_query_embedding(query)
    query_vector = "[" + ",".join(str(float(v)) for v in embedding) + "]"

    with conn.cursor() as cur:
        exact_rows = []
        if record_ids:
            # Exact matching happens only inside the ABAC-authorized ID set.
            cur.execute(
                """
                SELECT c.id, c.document_id, d.title, d.classification,
                       d.department, c.content,
                       NULL::float AS similarity, d.protection_profile
                FROM documents d
                JOIN chunks c ON c.document_id = d.id
                WHERE d.id = ANY(%s)
                  AND EXISTS (
                    SELECT 1 FROM unnest(%s::text[]) AS rid(value)
                    WHERE d.title ILIKE ('%%' || rid.value || '%%')
                  )
                ORDER BY d.id, c.id
                LIMIT %s
                """,
                (allowed_ids, record_ids, top_k),
            )
            exact_rows = cur.fetchall()

        # Shadow baseline reads metadata only and is used exclusively for audit.
        cur.execute(
            """
            SELECT c.id, c.document_id, d.title, d.classification, d.department
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, max(top_k, 10)),
        )
        shadow_rows = cur.fetchall()

        # Semantic search filters ABAC before ranking and LIMIT.
        cur.execute(
            """
            SELECT c.id, c.document_id, d.title, d.classification,
                   d.department, c.content,
                   1 - (c.embedding <=> %s::vector) AS similarity,
                   d.protection_profile
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = ANY(%s)
              AND c.embedding IS NOT NULL
              AND NOT (c.id = ANY(%s))
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                query_vector, allowed_ids,
                [row[0] for row in exact_rows] or [-1],
                query_vector, top_k,
            ),
        )
        semantic_rows = cur.fetchall()

    denied = []
    for row in shadow_rows:
        document = {"id": row[1], "classification": row[3], "department": row[4]}
        if enforce_access(user, document).effect != "ALLOW":
            denied.append({
                "chunk_id": row[0],
                "document_id": row[1],
                "classification": row[3],
                "department": row[4],
            })

    # Exact hits have precedence; semantic hits fill remaining slots.
    merged, seen = [], set()
    for row in [*exact_rows, *semantic_rows]:
        if row[0] not in seen:
            merged.append(row)
            seen.add(row[0])
        if len(merged) >= top_k:
            break
    return merged, denied


def vector_search(conn, user, query, top_k=3):
    _audit_state.denied_shadow_chunks = []
    authorized, denied = vector_search_with_audit(conn, user, query, top_k)
    _audit_state.denied_shadow_chunks = denied
    return authorized


def get_user(conn, username):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, role, department FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"User not found: {username}")
    return {"id": row[0], "username": row[1], "role": row[2], "department": row[3]}


if __name__ == "__main__":
    import psycopg2
    from db_config import get_db_config

    conn = psycopg2.connect(**get_db_config())
    try:
        user = get_user(conn, "nv_dev")
        for row in vector_search(conn, user, "Tìm thông tin hồ sơ 00006", top_k=5):
            print(f"Doc #{row[1]} | {row[2]} | {row[3]} | similarity={row[6]}")
    finally:
        conn.close()
