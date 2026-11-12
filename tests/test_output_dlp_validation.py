import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from output_dlp import process_output, process_output_safely


VALID_ANSWER = "Báo cáo tổng hợp."
VALID_DOCUMENTS = [
    {
        "document_id": 1,
        "text": "Tài liệu kiểm thử nội bộ.",
    }
]
VALID_CONTEXT = "SHARE_SUMMARY"


def test_invalid_answer_type():
    result = process_output_safely(
        123,
        VALID_DOCUMENTS,
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_empty_answer():
    result = process_output_safely(
        "   ",
        VALID_DOCUMENTS,
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_empty_source_documents():
    result = process_output_safely(
        VALID_ANSWER,
        [],
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_missing_document_text():
    result = process_output_safely(
        VALID_ANSWER,
        [{"document_id": 1}],
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_invalid_document_id():
    result = process_output_safely(
        VALID_ANSWER,
        [{"document_id": "1", "text": "Tài liệu kiểm thử."}],
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_empty_document_text():
    result = process_output_safely(
        VALID_ANSWER,
        [{"document_id": 1, "text": "   "}],
        VALID_CONTEXT,
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_invalid_release_context():
    result = process_output_safely(
        VALID_ANSWER,
        VALID_DOCUMENTS,
        "USER_SUPPLIED_CONTEXT",
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None


def test_no_raw_answer_in_error_result():
    raw_answer = "CONFIDENTIAL-RAW-ANSWER"

    result = process_output_safely(
        raw_answer,
        [{"document_id": 1}],
        VALID_CONTEXT,
    )

    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert raw_answer not in str(result)


if __name__ == "__main__":
    tests = [
        test_invalid_answer_type,
        test_empty_answer,
        test_empty_source_documents,
        test_missing_document_text,
        test_invalid_document_id,
        test_empty_document_text,
        test_invalid_release_context,
        test_no_raw_answer_in_error_result,
    ]

    for test in tests:
        test()

    print("ALL OUTPUT DLP VALIDATION TESTS PASSED")
