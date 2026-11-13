"""Regression tests for backend-derived Controlled RAG release contexts."""
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import controlled_rag


class TestControlledRAGPublicContext(unittest.TestCase):
    def test_public_entry_point_does_not_accept_release_context(self):
        parameters = inspect.signature(controlled_rag.answer_query).parameters
        self.assertNotIn("release_context", parameters)
        with self.assertRaises(TypeError):
            controlled_rag.answer_query(
                "valid-token", "test query", release_context="INTERNAL_ASSISTANT"
            )

    def test_authenticated_internal_employee_uses_internal_assistant(self):
        fake_conn = MagicMock()
        user = {"id": 1, "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"}
        retrieved_chunks = [
            (1, 6, "Mã nguồn hệ thống RAG", "Nội bộ", "Kỹ thuật",
             "Module policy_engine.py được dùng để kiểm tra quyền.", 0.9, "TECHNICAL_SENSITIVE")
        ]

        with (
            patch.object(controlled_rag.psycopg2, "connect") as connect,
            patch.object(controlled_rag, "get_db_config", return_value={}),
            patch.object(controlled_rag, "user_from_token", return_value=user),
            patch.object(controlled_rag, "vector_search", return_value=retrieved_chunks),
            patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
            patch.object(controlled_rag, "generate_answer", return_value="Module policy_engine.py được dùng để kiểm tra quyền."),
            patch.object(controlled_rag, "chunks_to_source_documents", return_value=[
                {"document_id": 6, "text": "Module policy_engine.py được dùng để kiểm tra quyền.", "protection_profile": "TECHNICAL_SENSITIVE"}
            ]),
            patch.object(
                controlled_rag, "process_output_safely",
                return_value={"decision": "ALLOW", "answer": "Module policy_engine.py được dùng để kiểm tra quyền.", "matches": [], "matched_count": 0},
            ) as process_output,
            patch.object(controlled_rag, "log_decision"),
        ):
            connect.return_value.__enter__.return_value = fake_conn
            result = controlled_rag.answer_query("valid-token", "Mã nguồn hệ thống RAG")

        self.assertEqual(result["decision"], "ALLOW")
        self.assertEqual(result["release_context"], "INTERNAL_ASSISTANT")
        self.assertEqual(result["answer"], "Module policy_engine.py được dùng để kiểm tra quyền.")
        process_output.assert_called_once()
        self.assertEqual(process_output.call_args.kwargs["release_context"], "INTERNAL_ASSISTANT")

    def test_authenticated_partner_retains_share_summary(self):
        fake_conn = MagicMock()
        user = {"id": 2, "username": "partner_01", "role": "Đối tác", "department": None}
        retrieved_chunks = [(1, 1, "Tài liệu công khai", "Công khai", None, "Thông tin công khai", 0.9, "PUBLIC")]

        with (
            patch.object(controlled_rag.psycopg2, "connect") as connect,
            patch.object(controlled_rag, "get_db_config", return_value={}),
            patch.object(controlled_rag, "user_from_token", return_value=user),
            patch.object(controlled_rag, "vector_search", return_value=retrieved_chunks),
            patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
            patch.object(controlled_rag, "generate_answer", return_value="Thông tin công khai."),
            patch.object(controlled_rag, "chunks_to_source_documents", return_value=[
                {"document_id": 1, "text": "Thông tin công khai.", "protection_profile": "PUBLIC"}
            ]),
            patch.object(
                controlled_rag, "process_output_safely",
                return_value={"decision": "ALLOW", "answer": "Thông tin công khai.", "matches": [], "matched_count": 0},
            ) as process_output,
            patch.object(controlled_rag, "log_decision"),
        ):
            connect.return_value.__enter__.return_value = fake_conn
            result = controlled_rag.answer_query("valid-token", "Thông tin công khai")

        self.assertEqual(result["release_context"], "SHARE_SUMMARY")
        self.assertEqual(process_output.call_args.kwargs["release_context"], "SHARE_SUMMARY")


if __name__ == "__main__":
    unittest.main()
