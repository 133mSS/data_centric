"""Regression tests for English representations of protected structured facts."""
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from entity_normalizer import normalize_date, normalize_money
from output_dlp import process_output
from structured_fact_extractor import extract_structured_facts


def _facts_by_type(text, fact_type):
    return [fact for fact in extract_structured_facts(text) if fact["type"] == fact_type]


def test_money_normalizer_supports_currency_first_and_amount_first():
    expected = "money:45:million:USD"
    assert normalize_money("45 triệu USD") == expected
    assert normalize_money("45 million USD") == expected
    assert normalize_money("USD 45 million") == expected
    assert normalize_money("US dollars 45 million") == expected
    assert normalize_money("bốn mươi lăm triệu USD") == expected


def test_date_normalizer_supports_english_month_names():
    expected = "date:2026-12"
    assert normalize_date("December 2026") == expected
    assert normalize_date("Dec 2026") == expected
    assert normalize_date("DEC. 2026") == expected
    assert normalize_date("tháng 12/2026") == expected


def test_extractor_detects_english_money_and_month_year():
    text = "The deal closes in December 2026 with a valuation of USD 45 million."
    dates = _facts_by_type(text, "date")
    money = _facts_by_type(text, "money")

    assert any(f["raw"] == "December 2026" and f["canonical"] == "date:2026-12" for f in dates)
    assert any(f["raw"] == "USD 45 million" and f["canonical"] == "money:45:million:USD" for f in money)


def test_share_summary_redacts_english_forms_of_protected_facts():
    source_documents = [{
        "document_id": 4,
        "text": (
            "Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất "
            "tháng 12/2026, mức định giá là 45 triệu USD."
        ),
    }]
    answer = "The deal closes in December 2026 with a valuation of USD 45 million."

    result = process_output(
        answer=answer,
        source_documents=source_documents,
        release_context="SHARE_SUMMARY",
    )

    assert result["decision"] == "REDACT"
    assert result["matched_count"] >= 2
    assert "December 2026" not in result["answer"]
    assert "USD 45 million" not in result["answer"]
    assert "[REDACTED]" in result["answer"]
