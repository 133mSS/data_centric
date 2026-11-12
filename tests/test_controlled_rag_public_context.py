"""Regression tests for the public controlled-RAG release context."""
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

    def test_public_entry_point_always_uses_share_summary(self):
        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1, "user", "manager", "tech"
        )
        retrieved_chunks = [(1, 7, "title", "content", 0.9)]

        with (
            patch.object(controlled_rag.psycopg2, "connect") as connect,
            patch.object(controlled_rag, "get_db_config", return_value={}),
            patch.object(controlled_rag, "user_from_token", return_value={"id": 1}),
            patch.object(controlled_rag, "vector_search", return_value=retrieved_chunks),
            patch.object(controlled_rag, "get_last_denied_shadow_chunks", return_value=[]),
            patch.object(controlled_rag, "generate_answer", return_value="safe candidate"),
            patch.object(controlled_rag, "chunks_to_source_documents", return_value=[]),
            patch.object(
                controlled_rag, "process_output_safely",
                return_value={"decision": "ALLOW", "answer": "safe answer", "matches": []},
            ) as process_output,
            patch.object(controlled_rag, "log_decision"),
        ):
            connect.return_value.__enter__.return_value = fake_conn
            result = controlled_rag.answer_query("valid-token", "test query")

        self.assertEqual(result["decision"], "ALLOW")
        self.assertEqual(result["answer"], "safe answer")
        process_output.assert_called_once_with(
            "safe candidate", [], release_context="SHARE_SUMMARY"
        )


if __name__ == "__main__":
    unittest.main()
