import os
import psycopg2
from uuid import uuid4
from auth import user_from_token, AuthenticationError
from output_dlp import process_output_safely
from vector_search import vector_search, get_last_denied_shadow_chunks
from audit import log_decision
from llm import generate_answer
from source_documents import chunks_to_source_documents
from db_config import get_db_config, get_demo_db_config


INTERNAL_RELEASE_ROLES = {"Nhân viên", "Manager", "Ban lãnh đạo"}
DEFAULT_RELEASE_CONTEXT = "SHARE_SUMMARY"


def release_context_for_user(user: dict) -> str:
    """Choose the demo's internal release context from verified backend identity."""
    role = user.get("role") if isinstance(user, dict) else None
    if role in INTERNAL_RELEASE_ROLES:
        return "INTERNAL_ASSISTANT"
    # Partners and unknown/malformed roles fail closed to the restrictive context.
    return DEFAULT_RELEASE_CONTEXT


def _verified_user_from_token(conn, token: str):
    """Load user attributes from a signed token, returning None on auth failure."""
    try:
        return user_from_token(conn, token)
    except (AuthenticationError, RuntimeError):
        return None

def _answer_query_with_connection(
    conn, token, query, top_k=3, *, release_context_override=None, verified_user=None
):
    """Run controlled RAG after verifying a signed token.

    release_context_override is a trusted server-side hook for the local demo.
    It is deliberately not accepted by the public answer_query() function.
    """
    request_id = str(uuid4())
    # The demo wrapper may pass the user it just verified in this same DB session;
    # public/benchmark callers omit it and are authenticated here as before.
    user = verified_user if verified_user is not None else _verified_user_from_token(conn, token)
    if user is None:
        return {
            "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
            "decision": "BLOCK", "retrieved_doc_ids": [], "request_id": request_id,
            "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }

    # The normal application/benchmark entrypoint preserves SHARE_SUMMARY.
    # Only the local authenticated demo server supplies a context selected by
    # release_context_for_user() after loading this user from the signed token.
    if release_context_override is None:
        release_context = DEFAULT_RELEASE_CONTEXT
    else:
        if release_context_override not in {"INTERNAL_ASSISTANT", "SHARE_SUMMARY"}:
            release_context = DEFAULT_RELEASE_CONTEXT
        else:
            release_context = release_context_override

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
                "decision": "NO_RESULT", "retrieved_doc_ids": [],
                "request_id": request_id, "release_context": release_context,
                "output_dlp_executed": False,
            }

        raw_answer = generate_answer(query, retrieved_chunks)
        source_documents = chunks_to_source_documents(retrieved_chunks)
        # DLP stays fail-closed: process_output_safely returns BLOCK if processing fails.
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
    """Public controlled RAG entrypoint used by benchmarks; remains SHARE_SUMMARY."""
    request_id = str(uuid4())
    if not isinstance(token, str) or not token.strip():
        return {
            "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }
    if not isinstance(query, str) or not query.strip():
        return {
            "answer": "Truy vấn không hợp lệ.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }
    try:
        with psycopg2.connect(**get_db_config()) as conn:
            return _answer_query_with_connection(
                conn, token, query, top_k=top_k,
                release_context_override=DEFAULT_RELEASE_CONTEXT,
            )
    except Exception:
        return {
            "answer": "Không thể xử lý yêu cầu một cách an toàn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }


def answer_internal_query(token: str, query: str, top_k: int = 3) -> dict:
    """Local demo entrypoint with backend-derived Output DLP context."""
    request_id = str(uuid4())
    if not isinstance(token, str) or not token.strip():
        return {
            "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }
    if not isinstance(query, str) or not query.strip():
        return {
            "answer": "Truy vấn không hợp lệ.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
        }

    try:
        # One DB session: resolve the signed identity once, then run the
        # retrieval and DLP pipeline for exactly that verified subject.
        with psycopg2.connect(**get_demo_db_config()) as conn:
            user = _verified_user_from_token(conn, token)
            if user is None:
                return {
                    "answer": "Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.",
                    "decision": "BLOCK", "retrieved_doc_ids": [],
                    "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
                    "output_dlp_executed": False,
                }
            context = release_context_for_user(user)
            return _answer_query_with_connection(
                conn, token, query, top_k=top_k,
                release_context_override=context, verified_user=user,
            )
    except Exception:
        return {
            "answer": "Không thể xử lý yêu cầu một cách an toàn.",
            "decision": "BLOCK", "retrieved_doc_ids": [],
            "request_id": request_id, "release_context": DEFAULT_RELEASE_CONTEXT,
            "output_dlp_executed": False,
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
        result = _answer_query_with_connection(
            conn, token, query, release_context_override=DEFAULT_RELEASE_CONTEXT
        )
        print(result["answer"])
    finally:
        conn.close()
