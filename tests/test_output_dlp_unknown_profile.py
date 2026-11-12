import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from output_dlp import process_output, process_output_safely
from protection_profile import get_document_profile


def test_unknown_document_id_raises_error():
    try:
        get_document_profile(999)
        raise AssertionError(
            "Unknown document ID must not receive a default profile"
        )
    except ValueError as exc:
        assert "No protection profile configured" in str(exc)


def test_unknown_document_id_blocks_output():
    raw_answer = "CONFIDENTIAL-RAW-ANSWER"

    source_documents = [
        {
            "document_id": 999,
            "text": "Tài liệu không có Protection Profile.",
        }
    ]

    result = process_output_safely(
        answer=raw_answer,
        source_documents=source_documents,
        release_context="SHARE_SUMMARY",
    )

    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert raw_answer not in str(result)


def test_direct_processing_raises_error():
    try:
        process_output(
            answer="Báo cáo tổng hợp.",
            source_documents=[
                {
                    "document_id": 999,
                    "text": "Tài liệu không có Protection Profile.",
                }
            ],
            release_context="SHARE_SUMMARY",
        )
        raise AssertionError(
            "Direct processing must reject an unknown document ID"
        )
    except ValueError as exc:
        assert "No protection profile configured" in str(exc)


if __name__ == "__main__":
    test_unknown_document_id_raises_error()
    test_unknown_document_id_blocks_output()
    test_direct_processing_raises_error()

    print("ALL UNKNOWN PROFILE TESTS PASSED")
