"""Diagnostic tests for possible global-catalog false positives.

Run from project root:
    python -m pytest -v -s tests/test_output_dlp_false_positive_diagnostic.py

These tests intentionally record the current behavior; they do not modify production code.
"""

import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest
from output_dlp import process_output_safely

NON_SENSITIVE_SOURCE = [
    {
        "document_id": 2,  # GENERAL_INTERNAL: no protected facts/phrases
        "text": "Quy trình nội bộ về đào tạo và bàn giao công việc.",
    }
]

# Each answer is intentionally unrelated to the corresponding secret's original context.
# If a generic phrase/value from another profile is still redacted, that is a candidate
# false positive caused by global catalog matching and should be reviewed by policy owners.
CASES = [
    pytest.param(
        "Báo cáo tổng kết ghi nhận nhân viên hoàn thành công việc xuất sắc.",
        "Xuất sắc",
        "PERFORMANCE_SENSITIVE phrase",
        id="generic-performance-praise",
    ),
    pytest.param(
        "Tài liệu kỹ thuật hướng dẫn cách cấu hình policy_engine.py trong môi trường thử nghiệm.",
        "policy_engine.py",
        "TECHNICAL_SENSITIVE phrase",
        id="technical-filename-in-general-guide",
    ),
    pytest.param(
        "Lịch bảo trì phòng họp dự kiến từ 22:00 đến 23:30 vào tối thứ Sáu.",
        "22:00",
        "MAINTENANCE_NOTICE time range",
        id="ordinary-time-window",
    ),
    pytest.param(
        "Thông báo chung: dự kiến hoàn thành công việc vào tháng 12/2026.",
        "12/2026",
        "CORPORATE_SECRET date",
        id="ordinary-month-year",
    ),
    pytest.param(
        "Bảng ví dụ tài chính minh họa khoản ngân sách 45 triệu USD.",
        "45 triệu USD",
        "CORPORATE_SECRET money amount",
        id="generic-financial-example",
    ),
]


@pytest.mark.parametrize("answer,marker,catalog_item", CASES)
def test_report_global_catalog_behavior_for_unrelated_context(answer, marker, catalog_item):
    result = process_output_safely(
        answer=answer,
        source_documents=NON_SENSITIVE_SOURCE,
        release_context="SHARE_SUMMARY",
    )

    redacted = result.get("answer") or ""
    marker_was_removed = marker.casefold() not in redacted.casefold()
    print(
        "\nFALSE-POSITIVE DIAGNOSTIC"
        f"\n  Catalog item: {catalog_item}"
        f"\n  Decision: {result.get('decision')}"
        f"\n  Matched count: {result.get('matched_count')}"
        f"\n  Marker removed: {marker_was_removed}"
        f"\n  Output: {redacted!r}"
    )

    # Safety/behavior invariant only: diagnostic should not crash or fail closed.
    # Whether marker removal is truly a false positive requires semantic/policy review.
    assert result.get("decision") in {"ALLOW", "REDACT", "BLOCK"}
    assert result.get("matched_count", 0) >= 0
