"""Context diagnostics for remaining Output DLP over-redaction candidates.

Cases:
- maintenance time range: 22:00-23:30
- corporate month/year: December 2026
- corporate money amount: USD 45 million

These tests only report current behavior. They do not change production code and do
not assume that matching in an unrelated context is automatically a security bug.

Run from the project root:
    python -m pytest -v -s tests/test_output_dlp_remaining_context_diagnostic.py
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
        {
            "answer": (
                "Lịch bảo trì phòng họp dự kiến từ 22:00 đến 23:30 "
                "vào tối thứ Sáu."
            ),
            "marker": "22:00",
            "catalog_item": "MAINTENANCE_NOTICE time range",
            "relevant_document": {
                "document_id": 7,
                "text": (
                    "Thông báo bảo trì hệ thống từ 22:00 đến 23:30 "
                    "ngày 15/10/2026."
                ),
            },
        },
        id="ordinary-time-window",
    ),
    pytest.param(
        {
            "answer": (
                "Thông báo chung: dự kiến hoàn thành công việc "
                "vào tháng 12/2026."
            ),
            "marker": "12/2026",
            "catalog_item": "CORPORATE_SECRET month/year",
            "relevant_document": {
                "document_id": 4,
                "text": (
                    "Kế hoạch sáp nhập dự kiến hoàn tất vào tháng 12/2026."
                ),
            },
        },
        id="ordinary-month-year",
    ),
    pytest.param(
        {
            "answer": (
                "Bảng ví dụ tài chính minh họa khoản ngân sách 45 triệu USD."
            ),
            "marker": "45 triệu USD",
            "catalog_item": "CORPORATE_SECRET money amount",
            "relevant_document": {
                "document_id": 4,
                "text": (
                    "Kế hoạch sáp nhập dự kiến có ngân sách 45 triệu USD."
                ),
            },
        },
        id="generic-financial-example",
    ),
]


UNRELATED_SOURCE = {
    "document_id": 2,  # GENERAL_INTERNAL
    "text": "Quy trình nội bộ về đào tạo và bàn giao công việc.",
}


def _run(answer, source_document):
    return process_output_safely(
        answer=answer,
        source_documents=[source_document],
        release_context="SHARE_SUMMARY",
    )


@pytest.mark.parametrize("case", CASES)
def test_report_context_behavior_for_remaining_structured_values(case):
    answer = case["answer"]
    marker = case["marker"]

    relevant_result = _run(answer, case["relevant_document"])
    unrelated_result = _run(answer, UNRELATED_SOURCE)

    relevant_output = relevant_result.get("answer") or ""
    unrelated_output = unrelated_result.get("answer") or ""

    print(
        "\nREMAINING CONTEXT DIAGNOSTIC"
        f"\n  Catalog item: {case['catalog_item']}"
        "\n  Relevant source profile:"
        f"\n    document_id={case['relevant_document']['document_id']}"
        f"\n    decision={relevant_result.get('decision')}"
        f"\n    matched_count={relevant_result.get('matched_count')}"
        f"\n    marker_removed={marker.casefold() not in relevant_output.casefold()}"
        f"\n    output={relevant_output!r}"
        "\n  Unrelated source profile:"
        f"\n    document_id={UNRELATED_SOURCE['document_id']}"
        f"\n    decision={unrelated_result.get('decision')}"
        f"\n    matched_count={unrelated_result.get('matched_count')}"
        f"\n    marker_removed={marker.casefold() not in unrelated_output.casefold()}"
        f"\n    output={unrelated_output!r}"
    )

    # Diagnostic invariants only: both executions should return a recognized
    # decision and a non-negative match count. Whether redaction is appropriate
    # must be decided separately from the observed result.
    for result in (relevant_result, unrelated_result):
        assert result.get("decision") in {"ALLOW", "REDACT", "BLOCK"}
        assert result.get("matched_count", 0) >= 0
