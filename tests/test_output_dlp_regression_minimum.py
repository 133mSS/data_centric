"""Minimal regression tests for Output DLP detection gaps.

These tests intentionally express the expected security behavior. A failing
case means the current implementation does not yet meet that expectation.
Run from this directory with: python -m pytest -q test_output_dlp_regression_minimum.py
"""

from output_dlp import process_output
from output_dlp_policy import ReleaseContext
from protection_profile import get_protection_profile, select_protected_facts
from structured_fact_extractor import extract_structured_facts


def _selected(profile_name: str, source_text: str):
    facts = extract_structured_facts(source_text)
    return select_protected_facts(profile_name, facts, source_text=source_text)


def test_canonical_consistency_corporate_secret_money_and_date():
    source = "Kế hoạch sáp nhập: định giá 45 triệu USD vào tháng 12/2026."
    protected = _selected("CORPORATE_SECRET", source)
    actual = {(fact["type"], fact.get("canonical")) for fact in protected}
    assert ("money", "money:45:million:USD") in actual
    assert ("date", "date:2026-12") in actual


def test_canonical_consistency_commercial_secret_quantity_year():
    source = "Dự kiến năm 2027 triển khai 5.000 máy chủ."
    protected = _selected("COMMERCIAL_SECRET", source)
    actual = {(fact["type"], fact.get("canonical")) for fact in protected}
    assert ("year", "year:2027") in actual
    assert ("quantity", "quantity:5000:máy chủ") in actual


def test_year_detection_is_case_insensitive_at_sentence_start():
    facts = extract_structured_facts("Năm 2027 sẽ triển khai kế hoạch.")
    assert any(f["type"] == "year" and f["canonical"] == "year:2027" for f in facts)


def test_performance_profile_selects_quantity_two_employees():
    source = "Báo cáo ghi nhận 2 nhân viên cần được theo dõi."
    protected = _selected("PERFORMANCE_SENSITIVE", source)
    assert any(f["type"] == "quantity" and f["value"].casefold() == "2 nhân viên" for f in protected)


def test_output_dlp_redacts_spelled_out_protected_money():
    source = {
        "document_id": 4,
        "text": "Kế hoạch sáp nhập định giá 45 triệu USD; thông tin này được bảo vệ.",
    }
    answer = "Khoản định giá tương đương bốn mươi lăm triệu USD."
    result = process_output(answer, [source], ReleaseContext.SHARE_SUMMARY.value)
    assert result["decision"] == "REDACT"
    assert "bốn mươi lăm triệu USD" not in result["answer"]


def test_output_dlp_redacts_english_spelling_of_protected_money():
    source = {
        "document_id": 4,
        "text": "Kế hoạch sáp nhập định giá 45 triệu USD; thông tin này được bảo vệ.",
    }
    answer = "The valuation is 45 million US dollars."
    result = process_output(answer, [source], ReleaseContext.SHARE_SUMMARY.value)
    assert result["decision"] == "REDACT"
    assert "45 million US dollars" not in result["answer"]

def test_output_dlp_redacts_protected_quantity_end_to_end():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from output_dlp import process_output

    # Dùng Unicode escape để tránh lỗi mã hóa tiếng Việt trên PowerShell.
    source = (
        "B\u00e1o c\u00e1o ghi nh\u1eadn "
        "2 nh\u00e2n vi\u00ean c\u1ea7n "
        "\u0111\u01b0\u1ee3c theo d\u00f5i."
    )

    result = process_output(
        answer=source,
        source_documents=[
            {"document_id": 3, "text": source}
        ],
        release_context="SHARE_SUMMARY",
    )

    assert result["decision"] == "REDACT"
    assert result["matched_count"] == 1
    assert "[REDACTED]" in result["answer"]
    assert "2 nh\u00e2n vi\u00ean" not in result["answer"]

