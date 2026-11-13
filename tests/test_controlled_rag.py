
import contextlib
import io
import runpy
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
class TestControlledRAG(unittest.TestCase):

    def run_controlled_rag(self, retrieved_chunks, dlp_result=None, use_real_dlp=False):
        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1,
            "mgr_tech",
            "manager",
            "tech",
        )

        fake_modules = {}

        # Patch the functions used by controlled_rag.py.
        dlp_patch = (
            patch("output_dlp.process_output_safely", return_value=dlp_result)
            if not use_real_dlp
            else contextlib.nullcontext()
        )

        with (
            patch.dict("os.environ", {
                "RAG_ACCESS_TOKEN": "test-valid-token",
                "RAG_QUERY": "Đánh giá hiệu suất phòng Kỹ thuật như thế nào?",
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_password",
            }),
            patch(
                "auth.user_from_token",
                return_value={"id": 1, "username": "mgr_tech", "role": "manager", "department": "tech"},
            ),
            patch("psycopg2.connect", return_value=fake_conn),
            patch(
                "vector_search.vector_search",
                return_value=retrieved_chunks,
            ) as mock_search,
            patch(
                "llm.generate_answer",
                return_value="RAW-CONFIDENTIAL-ANSWER",
            ) as mock_llm,
            dlp_patch as mock_dlp,
        ):
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                try:
                    runpy.run_module(
                        "controlled_rag",
                        run_name="__main__",
                    )
                except SystemExit as exc:
                    if exc.code != 0:
                        raise

        return (
            output.getvalue(),
            mock_search,
            mock_llm,
            mock_dlp,
        )

    def test_empty_retrieval_does_not_call_llm(self):
        output, mock_search, mock_llm, mock_dlp = (
            self.run_controlled_rag(
                retrieved_chunks=[],
                dlp_result={
                    "decision": "BLOCK",
                    "answer": None,
                },
            )
        )

        self.assertIn(
            "Không có tài liệu được phép để trả lời.",
            output,
        )
        mock_search.assert_called_once()
        mock_llm.assert_not_called()
        mock_dlp.assert_not_called()
        self.assertNotIn("RAW-CONFIDENTIAL-ANSWER", output)

    def test_blocked_answer_is_never_printed(self):
        retrieved_chunks = [
            (
                1,
                4,
                "Corporate Secret",
                "Synthetic preview",
                0.95,
                "Nội dung tài liệu nội bộ.",
            )
        ]

        output, mock_search, mock_llm, mock_dlp = (
            self.run_controlled_rag(
                retrieved_chunks=retrieved_chunks,
                dlp_result={
                    "decision": "BLOCK",
                    "answer": None,
                    "matches": [],
                    "matched_count": 0,
                },
            )
        )

        mock_search.assert_called_once()
        mock_llm.assert_called_once()
        mock_dlp.assert_called_once()

        # The CLI prints the safe BLOCK message, not a separate decision label.
        self.assertIn(
            "Không thể phát hành câu trả lời do kiểm soát bảo mật thất bại.",
            output,
        )
        self.assertNotIn("RAW-CONFIDENTIAL-ANSWER", output)

    def test_dlp_pipeline_error_blocks_and_never_prints_raw_answer(self):
        retrieved_chunks = [
            (
                1,
                4,
                "Corporate Secret",
                "Synthetic preview",
                0.95,
                "Kế hoạch sáp nhập với công ty XYZ, định giá 45 triệu USD.",
            )
        ]

        with (
            patch(
                "output_dlp.extract_structured_facts",
                side_effect=RuntimeError("simulated extraction failure"),
            ),
            patch("audit.log_decision") as mock_audit,
        ):
            output, mock_search, mock_llm, mock_dlp = self.run_controlled_rag(
                retrieved_chunks=retrieved_chunks,
                use_real_dlp=True,
            )

        mock_search.assert_called_once()
        mock_llm.assert_called_once_with(
            "Đánh giá hiệu suất phòng Kỹ thuật như thế nào?",
            retrieved_chunks,
        )
        # Real process_output_safely is exercised; the injected extractor
        # failure must be converted into BLOCK by the fail-closed wrapper.
        # The CLI prints the safe BLOCK message, not a separate decision label.
        self.assertIn(
            "Không thể phát hành câu trả lời do kiểm soát bảo mật thất bại.",
            output,
        )
        self.assertNotIn("RAW-CONFIDENTIAL-ANSWER", output)
        self.assertNotIn("Kế hoạch sáp nhập với công ty XYZ", output)

        # Verify the fail-closed decision is also sent to the audit logger.
        block_audit_events = [
            call.kwargs
            for call in mock_audit.call_args_list
            if call.kwargs.get("stage") == "output_dlp"
            and call.kwargs.get("decision") == "BLOCK"
        ]
        self.assertTrue(
            block_audit_events,
            "DLP failure must create an output_dlp BLOCK audit event",
        )
        self.assertEqual(block_audit_events[-1].get("reason"), "processing_error")
        self.assertEqual(block_audit_events[-1].get("rule_id"), "dlp_fail_closed")

    def test_redacted_answer_is_printed_instead_of_raw_answer(self):
        retrieved_chunks = [
            (
                1,
                4,
                "Corporate Secret",
                "Synthetic preview",
                0.95,
                "Nội dung tài liệu nội bộ.",
            )
        ]

        output, _, mock_llm, mock_dlp = self.run_controlled_rag(
            retrieved_chunks=retrieved_chunks,
            dlp_result={
                "decision": "REDACT",
                "answer": "Thông tin đã [REDACTED].",
                "matches": [],
                "matched_count": 1,
            },
        )

        mock_llm.assert_called_once()
        mock_dlp.assert_called_once()

        self.assertIn("Thông tin đã [REDACTED].", output)
        self.assertNotIn("RAW-CONFIDENTIAL-ANSWER", output)
    
    def test_shadow_denied_chunk_is_audited_but_never_sent_to_llm(self):
        allowed_chunk = (
            101,
            10,
            "Internal",
            "Allowed preview",
            0.95,
            "Allowed content",
        )
        denied_shadow_chunk = {
            "chunk_id": 202,
            "document_id": 20,
            "classification": "Confidential",
            "department": "finance",
        }

        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1,
            "mgr_tech",
            "manager",
            "tech",
        )

        with (
            patch.dict("os.environ", {
                "RAG_ACCESS_TOKEN": "test-valid-token",
                "RAG_QUERY": "Đánh giá hiệu suất phòng Kỹ thuật như thế nào?",
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_password",
            }),
            patch(
                "auth.user_from_token",
                return_value={"id": 1, "username": "mgr_tech", "role": "manager", "department": "tech"},
            ),
            patch("psycopg2.connect", return_value=fake_conn),
            patch(
                "vector_search.vector_search",
                return_value=[allowed_chunk],
            ),
            patch(
                "vector_search.get_last_denied_shadow_chunks",
                return_value=[denied_shadow_chunk],
            ),
            patch("audit.log_decision") as mock_audit,
            patch(
                "llm.generate_answer",
                return_value="A safe answer",
            ) as mock_llm,
            patch(
                "source_documents.chunks_to_source_documents",
                return_value=[],
            ),
            patch(
                "output_dlp.process_output_safely",
                return_value={
                    "decision": "ALLOW",
                    "answer": "A safe answer",
                    "matches": [],
                    "matched_count": 0,
                },
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                runpy.run_module("controlled_rag", run_name="__main__")
            except SystemExit as exc:
                if exc.code != 0:
                    raise

        # LLM chỉ nhận chunk được phép.
        mock_llm.assert_called_once()
        self.assertEqual(mock_llm.call_args.args[1], [allowed_chunk])
        self.assertNotIn(denied_shadow_chunk, mock_llm.call_args.args[1])

        # Audit phải ghi nhận cả ALLOW và DENY.
        audit_calls = [
            call.kwargs
            for call in mock_audit.call_args_list
        ]

        self.assertTrue(any(
            call.get("decision") == "ALLOW"
            and call.get("document_id") == 10
            and call.get("chunk_id") == 101
            and call.get("stage") == "retrieval"
            for call in audit_calls
        ))

        self.assertTrue(any(
            call.get("decision") == "DENY"
            and call.get("document_id") == 20
            and call.get("chunk_id") == 202
            and call.get("stage") == "retrieval"
            and call.get("rule_id") == "acl_policy"
            for call in audit_calls
        ))

        fake_conn.commit.assert_called_once()
        fake_conn.close.assert_called_once()


    def test_internal_user_context_is_passed_to_output_dlp(self):
        from controlled_rag import _answer_query_with_connection

        fake_conn = MagicMock()
        chunks = [
            (10, 6, "Mã nguồn hệ thống RAG", "Nội bộ", "Kỹ thuật",
             "Module policy_engine.py kiểm tra quyền truy cập.", 0.91, "TECHNICAL_SENSITIVE")
        ]
        user = {"id": 1, "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"}
        dlp_result = {
            "decision": "ALLOW",
            "answer": "Module policy_engine.py kiểm tra quyền truy cập.",
            "matches": [],
            "matched_count": 0,
        }
        with (
            patch("controlled_rag.user_from_token", return_value=user),
            patch("controlled_rag.vector_search", return_value=chunks),
            patch("controlled_rag.get_last_denied_shadow_chunks", return_value=[]),
            patch("controlled_rag.generate_answer", return_value=dlp_result["answer"]),
            patch("controlled_rag.chunks_to_source_documents", return_value=[
                {"document_id": 6, "text": chunks[0][5], "protection_profile": "TECHNICAL_SENSITIVE"}
            ]),
            patch("controlled_rag.process_output_safely", return_value=dlp_result) as dlp,
            patch("controlled_rag.log_decision") as audit,
        ):
            result = _answer_query_with_connection(fake_conn, "signed-token", "Mã nguồn hệ thống RAG")

        assert result["decision"] == "ALLOW"
        assert result["release_context"] == "INTERNAL_ASSISTANT"
        assert result["output_dlp_executed"] is True
        dlp.assert_called_once()
        assert dlp.call_args.kwargs["release_context"] == "INTERNAL_ASSISTANT"
        assert all(call.kwargs.get("release_context") == "INTERNAL_ASSISTANT" for call in audit.call_args_list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
