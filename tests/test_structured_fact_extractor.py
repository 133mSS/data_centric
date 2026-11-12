import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from structured_fact_extractor import extract_structured_facts


def types_and_raw(text):
    return [
        (fact["type"], fact["raw"], fact["canonical"])
        for fact in extract_structured_facts(text)
    ]


def test_full_date_is_not_misclassified_as_ratio():
    facts = types_and_raw(
        "Hệ thống được bảo trì từ 22:00 đến 23:30 ngày 15/10/2026."
    )

    assert ("date", "15/10/2026", "date:2026-10-15") in facts
    assert not any(fact_type == "ratio" and raw == "15/10"
                   for fact_type, raw, _ in facts)
    assert ("time_range", "22:00 đến 23:30", "time:22:00-23:30") in facts


def test_month_year_is_not_misclassified_as_ratio():
    facts = types_and_raw(
        "Kế hoạch dự kiến hoàn tất tháng 12/2026, định giá 45 triệu USD."
    )

    assert ("date", "tháng 12/2026", "date:2026-12") in facts
    assert not any(fact_type == "ratio" and raw == "12/2026"
                   for fact_type, raw, _ in facts)
    assert ("money", "45 triệu USD", "money:45:million:USD") in facts


def test_valid_ratio_is_recognized():
    facts = types_and_raw("12/20 nhân viên đạt mức Xuất sắc.")

    assert ("ratio", "12/20", "ratio:12/20") in facts


def test_quantity_and_year_are_recognized():
    facts = types_and_raw(
        "Hợp đồng cung cấp 5.000 máy chủ trong năm 2027."
    )

    assert ("quantity", "5.000 máy chủ", "quantity:5000:máy chủ") in facts
    assert ("year", "năm 2027", "year:2027") in facts


def test_facts_do_not_have_duplicate_spans():
    text = "Ngày 15/10/2026 và 12/20 nhân viên."
    facts = extract_structured_facts(text)
    spans = [(fact["start"], fact["end"]) for fact in facts]

    assert len(spans) == len(set(spans))


def test_money_is_extracted():
    facts = types_and_raw("45 triệu USD")

    assert ("money", "45 triệu USD", "money:45:million:USD") in facts


def test_month_year_is_extracted():
    facts = types_and_raw("tháng 12/2026")

    assert ("date", "tháng 12/2026", "date:2026-12") in facts


def test_year_is_extracted():
    facts = types_and_raw("năm 2027")

    assert ("year", "năm 2027", "year:2027") in facts


def test_quantity_is_extracted():
    facts = types_and_raw("5.000 máy chủ")

    assert ("quantity", "5.000 máy chủ", "quantity:5000:máy chủ") in facts


def test_ratio_is_extracted():
    facts = types_and_raw("12/20 nhân viên")

    assert ("ratio", "12/20", "ratio:12/20") in facts


def test_time_range_is_extracted():
    facts = types_and_raw("22:00 đến 23:30")

    assert ("time_range", "22:00 đến 23:30", "time:22:00-23:30") in facts
