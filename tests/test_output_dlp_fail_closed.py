import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from unittest.mock import patch

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

ANSWER = (
    "Kế hoạch sáp nhập với công ty XYZ, "
    "định giá 45 triệu USD."
)


# 1. Normal processing should return a valid decision.
def test_normal_processing():
    result = process_output_safely(
        ANSWER,
        SOURCE_DOCUMENTS,
        "SHARE_SUMMARY",
    )

    assert result["decision"] == "REDACT"
    assert result["answer"] is not None

# 2. Profile failure must block output.
def test_profile_failure_blocks_output():
    with patch(
        "output_dlp.get_document_profile",
        side_effect=RuntimeError("simulated profile failure"),
    ):
        result = process_output_safely(
            ANSWER,
            SOURCE_DOCUMENTS,
            "SHARE_SUMMARY",
        )

    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert result["error"] == "RuntimeError"

# 3. Policy failure must block output.
def test_policy_failure_blocks_output():
    with patch(
        "output_dlp.decide_release",
        side_effect=RuntimeError("simulated policy failure"),
    ):
        result = process_output_safely(
            ANSWER,
            SOURCE_DOCUMENTS,
            "INTERNAL_ASSISTANT",
        )

    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert result["error"] == "RuntimeError"

# 4. Invalid release context must not release the answer.
def test_invalid_context_blocks_output():
    result = process_output_safely(
        ANSWER,
        SOURCE_DOCUMENTS,
        "UNKNOWN_CONTEXT",
    )

    assert result["decision"] == "BLOCK"
    assert result["answer"] is None

    print("ALL OUTPUT DLP FAIL-CLOSED TESTS PASSED")
