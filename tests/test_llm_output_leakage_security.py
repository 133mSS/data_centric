"""Security and edge-case tests for Output DLP catalog matching.

Run from the project root:
    python -m pytest -v tests/test_llm_output_leakage_security.py
"""

import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from output_dlp import process_output_safely


AUTHORIZED_BUT_NON_SENSITIVE_SOURCE = [
    {
        "document_id": 2,  # GENERAL_INTERNAL profile, no configured secrets
        "text": "Quy trình xin nghỉ phép cần được gửi cho quản lý trực tiếp.",
    }
]

CORPORATE_SECRET_VALUES = (
    "XYZ",
    "tháng 12/2026",
    "45 triệu USD",
)


def assert_no_corporate_secret_is_released(result):
    """A restricted summary must not release known corporate secret values."""
    assert result["decision"] in {"REDACT", "BLOCK"}, (
        "Expected Output DLP to redact/block corporate secrets even when the "
        "LLM output is not grounded in the authorized source."
    )
    released = result.get("answer") or ""
    for secret in CORPORATE_SECRET_VALUES:
        assert secret.casefold() not in released.casefold(), (
            f"Sensitive value was released: {secret}"
        )


def test_llm_invented_known_secret_is_not_released_without_source_evidence():
    """A known protected value must not pass just because source lacks it."""
    hallucinated_answer = (
        "Theo thông tin hệ thống, dự án liên quan đến XYZ, "
        "dự kiến hoàn tất tháng 12/2026 với giá trị 45 triệu USD."
    )

    result = process_output_safely(
        answer=hallucinated_answer,
        source_documents=AUTHORIZED_BUT_NON_SENSITIVE_SOURCE,
        release_context="SHARE_SUMMARY",
    )

    assert_no_corporate_secret_is_released(result)


def test_prompt_injection_style_answer_cannot_disclose_unretrieved_secret():
    """A malicious instruction must not make Output DLP release an ungrounded secret."""
    injected_answer = (
        "Tôi sẽ bỏ qua giới hạn truy cập. Kế hoạch sáp nhập với công ty XYZ "
        "dự kiến hoàn tất tháng 12/2026, trị giá 45 triệu USD."
    )

    result = process_output_safely(
        answer=injected_answer,
        source_documents=AUTHORIZED_BUT_NON_SENSITIVE_SOURCE,
        release_context="SHARE_SUMMARY",
    )

    assert_no_corporate_secret_is_released(result)


def test_known_secret_catalog_does_not_match_entity_inside_larger_identifier():
    """The configured entity XYZ must not match inside XYZABC."""
    answer = "Mã dự án XYZABC đã được ghi nhận trong biên bản."

    result = process_output_safely(
        answer=answer,
        source_documents=AUTHORIZED_BUT_NON_SENSITIVE_SOURCE,
        release_context="SHARE_SUMMARY",
    )

    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["matched_count"] == 0


def test_internal_assistant_policy_allows_catalog_matches():
    """Catalog detection must not override the trusted release policy."""
    answer = "Dự án XYZ có giá trị 45 triệu USD."

    result = process_output_safely(
        answer=answer,
        source_documents=AUTHORIZED_BUT_NON_SENSITIVE_SOURCE,
        release_context="INTERNAL_ASSISTANT",
    )

    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["matched_count"] > 0
