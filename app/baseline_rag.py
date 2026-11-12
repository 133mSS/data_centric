
"""Public baseline RAG entry point. Baseline intentionally has no ACL."""
from uuid import uuid4

import psycopg2

from db_config import get_db_config
from baseline_vector_search import baseline_vector_search
from llm import generate_answer


def baseline_answer(query: str, top_k: int = 3) -> dict:
    request_id = str(uuid4())

    if not isinstance(query, str) or not query.strip():
        return {
            "answer": "Truy vấn không hợp lệ.",
            "decision": "BLOCK",
            "retrieved_doc_ids": [],
            "request_id": request_id,
        }

    try:
        with psycopg2.connect(**get_db_config()) as conn:
            chunks = baseline_vector_search(conn, query, top_k=top_k)
            document_ids = sorted({int(row[1]) for row in chunks})

            if not chunks:
                answer = "Không có đủ thông tin để trả lời."
            else:
                answer = generate_answer(query, chunks)

        return {
            "answer": answer,
            "decision": "ALLOW" if document_ids else "BLOCK",
            "retrieved_doc_ids": document_ids,
            "request_id": request_id,
        }
    except Exception:
        # Do not expose DB errors, internal details, or secrets.
        return {
            "answer": "Không thể xử lý truy vấn baseline.",
            "decision": "BLOCK",
            "retrieved_doc_ids": [],
            "request_id": request_id,
        }
