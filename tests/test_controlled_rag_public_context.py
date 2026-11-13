"""Regression tests for the separation of benchmark and internal-demo contexts."""
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import controlled_rag


def _mock_controlled_query(user, expected_context):
    fake_conn = MagicMock()
    retrieved_chunks = [
        (1, 6 if user["role"] == "Nhân viên" else 1,
         "A title", "Nội bộ" if user["role"] == "Nhân viên" else "Công khai",
         user.get("department"), "Authorized content", 0.9,
         "TECHNICAL_SENSITIVE" if user["role"] == "Nhân viên" else "PUBLIC")
    ]
    with (
        patch.object(controlled_rag.psycopg2, "connect") as connect,
        patch.object(controlled_rag, "get_db_config", return_value={}),
        patch.object(controlled_rag, "user_from_token", return_value=user),
        patch.object(controlled_rag, "vector_search", return_value=retrieved_chunks),
        patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
        patch.object(controlled_rag, "generate_answer", return_value="Authorized content"),
        patch.object(controlled_rag, "chunks_to_source_documents", return_value=[
            {"document_id": retrieved_chunks[0][1], "text": "Authorized content",
             "protection_profile": retrieved_chunks[0][7]}
        ]),
        patch.object(
            controlled_rag, "process_output_safely",
            return_value={"decision": "ALLOW", "answer": "Authorized content",
                          "matches": [], "matched_count": 0},
        ) as process_output,
        patch.object(controlled_rag, "log_decision"),
    ):
        connect.return_value.__enter__.return_value = fake_conn
        result = controlled_rag.answer_query("valid-token", "test query")
    return result, process_output


class TestControlledRAGPublicContext(unittest.TestCase):
    def test_public_entry_point_does_not_accept_release_context(self):
        parameters = inspect.signature(controlled_rag.answer_query).parameters
        self.assertNotIn("release_context", parameters)
        with self.assertRaises(TypeError):
            controlled_rag.answer_query(
                "valid-token", "test query", release_context="INTERNAL_ASSISTANT"
            )

    def test_public_benchmark_entry_point_remains_share_summary_for_employee(self):
        user = {"id": 1, "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"}
        result, process_output = _mock_controlled_query(user, "SHARE_SUMMARY")
        self.assertEqual(result["release_context"], "SHARE_SUMMARY")
        self.assertEqual(process_output.call_args.kwargs["release_context"], "SHARE_SUMMARY")

    def test_public_benchmark_entry_point_remains_share_summary_for_partner(self):
        user = {"id": 2, "username": "partner_01", "role": "Đối tác", "department": None}
        result, process_output = _mock_controlled_query(user, "SHARE_SUMMARY")
        self.assertEqual(result["release_context"], "SHARE_SUMMARY")
        self.assertEqual(process_output.call_args.kwargs["release_context"], "SHARE_SUMMARY")


if __name__ == "__main__":
    unittest.main()
