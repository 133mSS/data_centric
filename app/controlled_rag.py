import os
import psycopg2
from uuid import uuid4
from auth import user_from_token, AuthenticationError
from output_dlp import process_output_safely
from vector_search import vector_search, get_last_denied_shadow_chunks
from audit import log_decision
from llm import generate_answer
from source_documents import chunks_to_source_documents
from db_config import get_db_config


INTERNAL_RELEASE_ROLES = {"Nhân viên", "Manager", "Ban lãnh đạo"}
EXTERNAL_RELEASE_ROLES = {"Đối tác"}
DEFAULT_RELEASE_CONTEXT = "SHARE_SUMMARY"


def release_context_for_user(user: dict) -> str:
    """Resolve release policy from authenticated backend identity, never browser input.

    Internal employees/managers/leadership ask questions within their ABAC-
    authorized workspace. Partner-facing sessions retain the restrictive
    SHARE_SUMMARY policy. Unknown roles fail closed to SHARE_SUMMARY.
    """
    role = user.get("role") if isinstance(user, dict) else None
    if role in INTERNAL_RELEASE_ROLES:
        return "INTERNAL_ASSISTANT"
    if role in EXTERNAL_RELEASE_ROLES:
        return "SHARE_SUMMARY"
    return DEFAULT_RELEASE_CONTEXT


def _answer_query_with_connection(conn, token, query, top_k=3):
    """Run controlled RAG using a verified token, never a caller-supplied user."""
    request_id = str(uuid4())
    try:
        user = user_from_token(conn, token)
    except (AuthenticationError, RuntimeError):
        return {
            "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
            "decision": "BLOCK", "retrieved_doc_ids": [], "request_id": request_id,
            "release_context": DEFAULT_RELEASE_CONTEXT,
        }

    release_context = release_context_for_user(user)

    try:
        retrieved_chunks = vector_search(conn, user, query, top_k=top_k)
        denied_shadow_chunks = get_last_denied_shadow_chunks()
        for chunk in retrieved_chunks:
            log_decision(
                conn, request_id=request_id, user_id=user["id"], stage="retrieval",
                decision="ALLOW", reason="allowed", document_id=chunk[1],
                chunk_id=chunk[0], rule_id="acl_policy", query_text=query,
                release_context=release_context,
            )
        for chunk in denied_shadow_chunks:
            log_decision(
                conn, request_id=request_id, user_id=user["id"], stage="retrieval",
                decision="DENY", reason="policy_violation",
                document_id=chunk["document_id"], chunk_id=chunk["chunk_id"],
                rule_id="acl_policy", query_text=query, release_context=release_context,
            )
        if not retrieved_chunks:
            conn.commit()
            return {
                "answer": "Không có tài liệu được phép để trả lời.",
                "decision": "BLOCK", "retrieved_doc_ids": [],
                "request_id": request_id, "release_context": release_context,
                "output_dlp_executed": False,
            }

        raw_answer = generate_answer(query, retrieved_chunks)
        source_documents = chunks_to_source_documents(retrieved_chunks)
        # process_output_safely is fail-closed and returns BLOCK on any DLP error.
        dlp_result = process_output_safely(
            raw_answer, source_documents, release_context=release_context,
        )

        decision = dlp_result.get("decision", "BLOCK")
        matches = dlp_result.get("matches") or []
        if decision in {"REDACT", "BLOCK"} and matches:
            for match in matches:
                safe_type = str(match.get("type", "sensitive_match"))[:80]
                log_decision(
                    conn, request_id=request_id, user_id=user["id"], stage="output_dlp",
                    decision=decision, reason="sensitive_match",
                    rule_id=f"match:{safe_type}:start={match.get('start')}:end={match.get('end')}",
                    query_text=query, release_context=release_context,
                )
        elif decision == "BLOCK":
            log_decision(
                conn, request_id=request_id, user_id=user["id"], stage="output_dlp",
                decision="BLOCK", reason="processing_error", rule_id="dlp_fail_closed",
                query_text=query, release_context=release_context,
            )
        conn.commit()
        safe_answer = (
            dlp_result.get("answer", "")
            if decision in {"ALLOW", "REDACT"}
            else "Không thể phát hành câu trả lời do kiểm soát bảo mật thất bại."
        )
        return {
            "answer": safe_answer,
            "decision": decision,
            "retrieved_doc_ids": sorted({int(chunk[1]) for chunk in retrieved_chunks}),
            "request_id": request_id,
            "release_context": release_context,
            "output_dlp_executed": True,
            "dlp_match_count": int(dlp_result.get("matched_count", len(matches)) or 0),
        }
    except Exception:
        conn.rollback()
        return {
            "answer": "Không thể xử lý yêu cầu một cách an toàn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": release_context,
            "output_dlp_executed": False,
        }


def answer_query(token: str, query: str, top_k: int = 3) -> dict:
    """Public controlled RAG entry point; authentication is mandatory."""
    request_id = str(uuid4())

    if not isinstance(token, str) or not token.strip():
        return {
            "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
        }
    if not isinstance(query, str) or not query.strip():
        return {
            "answer": "Truy vấn không hợp lệ.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
        }

    try:
        with psycopg2.connect(**get_db_config()) as conn:
            return _answer_query_with_connection(conn, token, query, top_k=top_k)
    except Exception:
        return {
            "answer": "Không thể xử lý yêu cầu một cách an toàn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
        }


if __name__ == "__main__":
    token = os.getenv("RAG_ACCESS_TOKEN", "")
    query = os.getenv("RAG_QUERY", "")
    if not token or not query:
        raise SystemExit(
            "Set RAG_ACCESS_TOKEN and RAG_QUERY; authenticate via app.auth.authenticate first."
        )
    conn = psycopg2.connect(**get_db_config())
    try:
        result = _answer_query_with_connection(conn, token, query)
        print(result["answer"])
    finally:
        conn.close()
