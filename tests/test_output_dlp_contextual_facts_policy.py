"""Regression suite for approved Output DLP contextual-fact policy (CTX-01..CTX-13)."""
import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from output_dlp import process_output_safely

GENERAL_SOURCE = {
    "document_id": 2,
    "text": "Quy trình nội bộ về đào tạo và bàn giao công việc.",
}
CORPORATE_SOURCE = {
    "document_id": 4,
    "text": "Kế hoạch sáp nhập dự kiến hoàn tất vào tháng 12/2026 với ngân sách 45 triệu USD.",
}
MAINTENANCE_SOURCE = {
    "document_id": 7,
    "text": "Thông báo bảo trì hệ thống từ 22:00 đến 23:30 ngày 15/10/2026.",
}


def run(answer, source=GENERAL_SOURCE, context="SHARE_SUMMARY"):
    return process_output_safely(answer, [source], context)


def test_ctx_01_sensitive_time_is_redacted_for_maintenance_profile():
    result = run("Hệ thống bảo trì từ 22:00 đến 23:30.", MAINTENANCE_SOURCE)
    assert result["decision"] == "REDACT"
    assert "22:00" not in result["answer"]


def test_ctx_02_sensitive_month_year_is_redacted_for_corporate_profile():
    result = run("Kế hoạch sáp nhập hoàn tất tháng 12/2026.", CORPORATE_SOURCE)
    assert result["decision"] == "REDACT"
    assert "12/2026" not in result["answer"]


def test_ctx_03_sensitive_money_is_redacted_for_corporate_profile():
    result = run("Kế hoạch sáp nhập có giá trị 45 triệu USD.", CORPORATE_SOURCE)
    assert result["decision"] == "REDACT"
    assert "45 triệu USD" not in result["answer"]


def test_ctx_04_benign_time_context_is_allowed():
    answer = "Lịch bảo trì phòng họp dự kiến từ 22:00 đến 23:30 vào tối thứ Sáu."
    result = run(answer)
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["contextual_classifications"][0]["status"] == "BENIGN"


def test_ctx_05_benign_month_year_context_is_allowed():
    answer = "Thông báo chung: dự kiến hoàn thành công việc vào tháng 12/2026."
    result = run(answer)
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["contextual_classifications"][0]["status"] == "BENIGN"


def test_ctx_06_benign_financial_example_is_allowed():
    answer = "Bảng ví dụ tài chính minh họa khoản ngân sách 45 triệu USD."
    result = run(answer)
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["contextual_classifications"][0]["status"] == "BENIGN"


def test_ctx_07_uncertain_share_summary_is_blocked_without_answer():
    result = run("Thông tin liên quan 45 triệu USD.")
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert result["uncertain_count"] == 1


def test_ctx_08_unretrieved_known_secret_with_specific_signal_is_not_released():
    answer = "Dự án XYZ dự kiến hoàn tất tháng 12/2026 với giá trị 45 triệu USD."
    result = run(answer)
    assert result["decision"] == "REDACT"
    for secret in ("XYZ", "12/2026", "45 triệu USD"):
        assert secret.casefold() not in result["answer"].casefold()


def test_ctx_09_larger_identifier_does_not_trigger_xyz_secret_rule():
    answer = "Mã dự án XYZABC đã được ghi nhận trong biên bản."
    result = run(answer)
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["matched_count"] == 0


def test_ctx_10_internal_assistant_preserves_answer_even_when_uncertain():
    answer = "Thông tin liên quan 45 triệu USD."
    result = run(answer, context="INTERNAL_ASSISTANT")
    assert result["decision"] == "ALLOW"
    assert result["answer"] == answer
    assert result["uncertain_count"] == 1


def test_ctx_11_sensitive_signal_wins_over_benign_signal():
    answer = "Ví dụ tài chính về kế hoạch sáp nhập có giá trị 45 triệu USD."
    result = run(answer)
    assert result["decision"] == "REDACT"
    assert "45 triệu USD" not in result["answer"]
    assert result["contextual_classifications"][0]["status"] == "SENSITIVE"


def test_ctx_12_processing_error_fails_closed_without_raw_answer():
    result = process_output_safely(
        answer="45 triệu USD",
        source_documents=[{"document_id": 999, "text": "nguồn hợp lệ"}],
        release_context="SHARE_SUMMARY",
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
    assert "45 triệu USD" not in str(result)


def test_ctx_13_unknown_context_fails_closed():
    result = process_output_safely(
        answer="Thông báo chung: hoàn thành công việc vào tháng 12/2026.",
        source_documents=[GENERAL_SOURCE],
        release_context="UNTRUSTED_CONTEXT",
    )
    assert result["decision"] == "BLOCK"
    assert result["answer"] is None
