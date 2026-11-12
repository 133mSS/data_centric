"""Contextual structured-value behavior across trusted release contexts."""
import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest
from output_dlp import process_output_safely

UNRELATED_SOURCE = [{
    "document_id": 2,
    "text": "Quy trình nội bộ về đào tạo và bàn giao công việc.",
}]

BENIGN_CASES = [
    pytest.param(
        "Lịch bảo trì phòng họp dự kiến từ 22:00 đến 23:30 vào tối thứ Sáu.",
        "22:00", id="ordinary-time-window",
    ),
    pytest.param(
        "Thông báo chung: dự kiến hoàn thành công việc vào tháng 12/2026.",
        "12/2026", id="ordinary-month-year",
    ),
    pytest.param(
        "Bảng ví dụ tài chính minh họa khoản ngân sách 45 triệu USD.",
        "45 triệu USD", id="generic-financial-example",
    ),
]


@pytest.mark.parametrize("answer,value", BENIGN_CASES)
def test_share_summary_allows_configured_benign_context(answer, value):
    result = process_output_safely(answer, UNRELATED_SOURCE, "SHARE_SUMMARY")
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert value.casefold() in result["answer"].casefold()


@pytest.mark.parametrize("answer,value", BENIGN_CASES)
def test_internal_assistant_keeps_answer_unchanged(answer, value):
    result = process_output_safely(answer, UNRELATED_SOURCE, "INTERNAL_ASSISTANT")
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
