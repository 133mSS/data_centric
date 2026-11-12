"""Regression tests for context-dependent protected phrases.

Run from project root:
    python -m pytest -v tests/test_output_dlp_context_regression.py
"""

import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest
from output_dlp import process_output_safely


CASES = [
    pytest.param(
        "Báo cáo đánh giá ghi nhận kết quả Xuất sắc của nhân viên.",
        {
            "document_id": 3,
            "text": "Báo cáo hiệu suất có ghi nhận mức đánh giá Xuất sắc của nhân viên.",
        },
        {
            "document_id": 2,
            "text": "Quy trình nội bộ về đào tạo và bàn giao công việc.",
        },
        "Xuất sắc",
        id="ordinary-phrase-xuat-sac",
    ),
    pytest.param(
        "Tài liệu hướng dẫn cấu hình policy_engine.py trong môi trường thử nghiệm.",
        {
            "document_id": 6,
            "text": "Tài liệu kỹ thuật nội bộ đề cập tên file policy_engine.py.",
        },
        {
            "document_id": 2,
            "text": "Hướng dẫn chung về cấu hình ứng dụng trong môi trường thử nghiệm.",
        },
        "policy_engine.py",
        id="filename-policy-engine",
    ),
]


@pytest.mark.parametrize(
    "answer,relevant_source,unrelated_source,protected_value", CASES
)
def test_contextual_phrase_is_redacted_only_for_relevant_source_profile(
    answer, relevant_source, unrelated_source, protected_value
):
    relevant_result = process_output_safely(
        answer=answer,
        source_documents=[relevant_source],
        release_context="SHARE_SUMMARY",
    )
    unrelated_result = process_output_safely(
        answer=answer,
        source_documents=[unrelated_source],
        release_context="SHARE_SUMMARY",
    )

    # The matching sensitive profile must still protect its contextual phrase.
    assert relevant_result["decision"] == "REDACT"
    assert protected_value.casefold() not in relevant_result["answer"].casefold()

    # An unrelated source profile must not trigger global phrase over-redaction.
    assert unrelated_result["decision"] == "ALLOW"
    assert unrelated_result["answer"] == answer
    assert unrelated_result["matched_count"] == 0
