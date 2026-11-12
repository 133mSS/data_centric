"""Context-comparison diagnostics for broad phrase/file-name catalog entries.

Run from project root:
    python -m pytest -v -s tests/test_output_dlp_context_diagnostic.py

These tests compare matching source profiles with unrelated source profiles.
They do not change production code or decide the final release policy.
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
        "PERFORMANCE_SENSITIVE",
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
        "TECHNICAL_SENSITIVE",
        id="filename-policy-engine",
    ),
]


@pytest.mark.parametrize(
    "answer,relevant_source,unrelated_source,marker,profile_name",
    CASES,
)
def test_compare_relevant_and_unrelated_source_context(
    answer, relevant_source, unrelated_source, marker, profile_name
):
    """Show whether source profile/context changes the DLP decision."""
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

    relevant_output = relevant_result.get("answer") or ""
    unrelated_output = unrelated_result.get("answer") or ""
    relevant_marker_removed = marker.casefold() not in relevant_output.casefold()
    unrelated_marker_removed = marker.casefold() not in unrelated_output.casefold()

    print(
        f"\nCONTEXT COMPARISON: {profile_name} / {marker!r}"
        f"\n  Relevant source profile: {relevant_source['document_id']}"
        f"\n    decision={relevant_result.get('decision')}"
        f", matched_count={relevant_result.get('matched_count')}"
        f", marker_removed={relevant_marker_removed}"
        f"\n    output={relevant_output!r}"
        f"\n  Unrelated source profile: {unrelated_source['document_id']}"
        f"\n    decision={unrelated_result.get('decision')}"
        f", matched_count={unrelated_result.get('matched_count')}"
        f", marker_removed={unrelated_marker_removed}"
        f"\n    output={unrelated_output!r}"
    )

    # Guard only against crashes / invalid decisions. The diagnostic deliberately
    # does not encode which context-sensitive behavior should become policy.
    assert relevant_result.get("decision") in {"ALLOW", "REDACT", "BLOCK"}
    assert unrelated_result.get("decision") in {"ALLOW", "REDACT", "BLOCK"}
    assert relevant_result.get("matched_count", 0) >= 0
    assert unrelated_result.get("matched_count", 0) >= 0
