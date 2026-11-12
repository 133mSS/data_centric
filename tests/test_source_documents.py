from pathlib import Path
import sys
import unittest

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from source_documents import chunks_to_source_documents
from output_dlp import process_output_safely


class TestChunksToSourceDocuments(unittest.TestCase):
    def test_chunks_from_same_document_are_combined_in_order(self):
        chunks = [
            (10, 4, "Title", "Mật", 0.9, "Đợt triển khai diễn ra tháng 12/"),
            (11, 4, "Title", "Mật", 0.8, "2026."),
            (12, 5, "Other", "Nội bộ", 0.7, "Tài liệu khác."),
        ]

        self.assertEqual(
            chunks_to_source_documents(chunks),
            [
                {"document_id": 4, "text": "Đợt triển khai diễn ra tháng 12/2026."},
                {"document_id": 5, "text": "Tài liệu khác."},
            ],
        )

    def test_sensitive_date_split_across_chunks_is_still_redacted(self):
        chunks = [
            (10, 4, "Title", "Mật", 0.9, "Thời điểm dự kiến là tháng 12/"),
            (11, 4, "Title", "Mật", 0.8, "2026."),
        ]
        source_documents = chunks_to_source_documents(chunks)

        result = process_output_safely(
            answer="Thời điểm dự kiến là tháng 12/2026.",
            source_documents=source_documents,
            release_context="SHARE_SUMMARY",
        )

        self.assertEqual(result["decision"], "REDACT")
        self.assertNotIn("12/2026", result["answer"])
        self.assertIn("[REDACTED]", result["answer"])

    def test_invalid_chunk_fails_validation(self):
        with self.assertRaises(ValueError):
            chunks_to_source_documents([(1, 4, "Title", "Mật", 0.9, " ")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
