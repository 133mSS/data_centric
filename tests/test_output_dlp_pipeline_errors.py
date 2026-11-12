
from unittest.mock import patch
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from output_dlp import process_output_safely


SOURCE_DOCUMENTS = [
    {
        "document_id": 4,
        "text": (
            "Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất "
            "tháng 12/2026, mức định giá 45 triệu USD."
        ),
    }
]

RAW_ANSWER = (
    "Kế hoạch sáp nhập với công ty XYZ, "
    "định giá 45 triệu USD."
)


def assert_blocked_without_leak(result):
    """Ensure a processing failure never releases the raw answer."""
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert RAW_ANSWER not in str(result)


def test_extractor_failure_blocks_output():
    with patch(
        "output_dlp.extract_structured_facts",
        side_effect=RuntimeError("simulated extraction failure"),
    ):
        result = process_output_safely(
            RAW_ANSWER,
            SOURCE_DOCUMENTS,
            "SHARE_SUMMARY",
        )

    assert_blocked_without_leak(result)
    assert result["error"] == "RuntimeError"


def test_matcher_failure_blocks_output():
    with patch(
        "output_dlp.match_protected_facts",
        side_effect=RuntimeError("simulated matching failure"),
    ):
        result = process_output_safely(
            RAW_ANSWER,
            SOURCE_DOCUMENTS,
            "SHARE_SUMMARY",
        )

    assert_blocked_without_leak(result)
    assert result["error"] == "RuntimeError"


def test_redaction_failure_blocks_output():
    with patch(
        "output_dlp.apply_redaction",
        side_effect=RuntimeError("simulated redaction failure"),
    ):
        result = process_output_safely(
            RAW_ANSWER,
            SOURCE_DOCUMENTS,
            "SHARE_SUMMARY",
        )

    assert_blocked_without_leak(result)
    assert result["error"] == "RuntimeError"


if __name__ == "__main__":
    tests = [
        test_extractor_failure_blocks_output,
        test_matcher_failure_blocks_output,
        test_redaction_failure_blocks_output,
    ]

    for test in tests:
        test()

    print("ALL OUTPUT DLP PIPELINE ERROR TESTS PASSED")
