"""Regression tests for the role-based release context used by the demo wrapper."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, APP_DIR)

import controlled_rag


def test_internal_roles_map_to_internal_assistant_for_demo():
    assert controlled_rag.release_context_for_user({
        "role": "Nhân viên", "department": "Kỹ thuật"
    }) == "INTERNAL_ASSISTANT"
    assert controlled_rag.release_context_for_user({
        "role": "Manager", "department": "Kỹ thuật"
    }) == "INTERNAL_ASSISTANT"
    assert controlled_rag.release_context_for_user({
        "role": "Ban lãnh đạo", "department": "Toàn công ty"
    }) == "INTERNAL_ASSISTANT"


def test_partner_and_unknown_role_keep_share_summary():
    assert controlled_rag.release_context_for_user({
        "role": "Đối tác", "department": None
    }) == "SHARE_SUMMARY"
    assert controlled_rag.release_context_for_user({"role": "Unknown"}) == "SHARE_SUMMARY"
    assert controlled_rag.release_context_for_user({}) == "SHARE_SUMMARY"


def test_browser_supplied_context_field_is_ignored():
    assert controlled_rag.release_context_for_user({
        "role": "Đối tác",
        "release_context": "INTERNAL_ASSISTANT",
    }) == "SHARE_SUMMARY"


def test_demo_wrapper_selects_internal_context_after_loading_signed_user():
    fake_conn = MagicMock()
    user = {"id": 1, "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"}
    chunks = [
        (1, 6, "Mã nguồn hệ thống RAG", "Nội bộ", "Kỹ thuật",
         "Module policy_engine.py", 0.9, "TECHNICAL_SENSITIVE")
    ]
    with (
        patch.object(controlled_rag.psycopg2, "connect") as connect,
        patch.object(controlled_rag, "get_db_config", return_value={}),
        patch.object(controlled_rag, "user_from_token", return_value=user),
        patch.object(controlled_rag, "vector_search", return_value=chunks),
        patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
        patch.object(controlled_rag, "generate_answer", return_value="Module policy_engine.py"),
        patch.object(controlled_rag, "chunks_to_source_documents", return_value=[
            {"document_id": 6, "text": "Module policy_engine.py",
             "protection_profile": "TECHNICAL_SENSITIVE"}
        ]),
        patch.object(
            controlled_rag, "process_output_safely",
            return_value={"decision": "ALLOW", "answer": "Module policy_engine.py",
                          "matches": [], "matched_count": 0},
        ) as dlp,
        patch.object(controlled_rag, "log_decision"),
    ):
        connect.return_value.__enter__.return_value = fake_conn
        result = controlled_rag.answer_internal_query("signed-token", "Mã nguồn hệ thống RAG")

    assert result["release_context"] == "INTERNAL_ASSISTANT"
    assert result["answer"] == "Module policy_engine.py"
    assert dlp.call_args.kwargs["release_context"] == "INTERNAL_ASSISTANT"


def test_demo_wrapper_keeps_partner_on_share_summary():
    fake_conn = MagicMock()
    user = {"id": 2, "username": "partner_01", "role": "Đối tác", "department": None}
    chunks = [
        (1, 1, "Thông tin công khai", "Công khai", None,
         "Thông tin công khai", 0.9, "PUBLIC")
    ]
    with (
        patch.object(controlled_rag.psycopg2, "connect") as connect,
        patch.object(controlled_rag, "get_db_config", return_value={}),
        patch.object(controlled_rag, "user_from_token", return_value=user),
        patch.object(controlled_rag, "vector_search", return_value=chunks),
        patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
        patch.object(controlled_rag, "generate_answer", return_value="Thông tin công khai"),
        patch.object(controlled_rag, "chunks_to_source_documents", return_value=[
            {"document_id": 1, "text": "Thông tin công khai", "protection_profile": "PUBLIC"}
        ]),
        patch.object(
            controlled_rag, "process_output_safely",
            return_value={"decision": "ALLOW", "answer": "Thông tin công khai",
                          "matches": [], "matched_count": 0},
        ) as dlp,
        patch.object(controlled_rag, "log_decision"),
    ):
        connect.return_value.__enter__.return_value = fake_conn
        result = controlled_rag.answer_internal_query("signed-token", "Thông tin công khai")

    assert result["release_context"] == "SHARE_SUMMARY"
    assert dlp.call_args.kwargs["release_context"] == "SHARE_SUMMARY"
