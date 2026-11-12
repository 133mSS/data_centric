import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from redaction import redact_answer


def test_money_paraphrase():

    answer = (
        "Kế hoạch sáp nhập có mức định giá "
        "45 triệu đô la Mỹ."
    )

    sensitive_facts = [
        {
            "type": "money",
            "value": "45 triệu USD",
        }
    ]

    result = redact_answer(
        answer,
        sensitive_facts,
    )

    assert "45 triệu đô la Mỹ" not in result
    assert "[REDACTED]" in result


def test_different_money_not_redacted():

    answer = (
        "Kế hoạch có mức định giá "
        "12 triệu USD."
    )

    sensitive_facts = [
        {
            "type": "money",
            "value": "45 triệu USD",
        }
    ]

    result = redact_answer(
        answer,
        sensitive_facts,
    )

    assert "12 triệu USD" in result
    assert "[REDACTED]" not in result


def test_month_year_paraphrase():

    answer = (
        "Kế hoạch dự kiến hoàn tất "
        "vào tháng 12 năm 2026."
    )

    sensitive_facts = [
        {
            "type": "date",
            "value": "12/2026",
        }
    ]

    result = redact_answer(
        answer,
        sensitive_facts,
    )

    assert "tháng 12 năm 2026" not in result
    assert "[REDACTED]" in result


def test_exact_named_entity():

    answer = (
        "Kế hoạch sáp nhập với công ty XYZ "
        "đang được xem xét."
    )

    sensitive_facts = [
        {
            "type": "named_entity",
            "value": "công ty XYZ",
        }
    ]

    result = redact_answer(
        answer,
        sensitive_facts,
    )

    assert "công ty XYZ" not in result
    assert "[REDACTED]" in result


def test_multiple_sensitive_facts():

    answer = (
        "Kế hoạch sáp nhập với công ty XYZ "
        "dự kiến hoàn tất tháng 12 năm 2026, "
        "với mức định giá 45 triệu đô la Mỹ."
    )

    sensitive_facts = [
        {
            "type": "named_entity",
            "value": "công ty XYZ",
        },
        {
            "type": "date",
            "value": "12/2026",
        },
        {
            "type": "money",
            "value": "45 triệu USD",
        },
    ]

    result = redact_answer(
        answer,
        sensitive_facts,
    )

    assert "công ty XYZ" not in result
    assert "tháng 12 năm 2026" not in result
    assert "45 triệu đô la Mỹ" not in result

    assert result.count("[REDACTED]") == 3


if __name__ == "__main__":
    test_money_paraphrase()
    test_different_money_not_redacted()
    test_month_year_paraphrase()
    test_exact_named_entity()
    test_multiple_sensitive_facts()

    print("ALL HYBRID REDACTION TESTS PASS")

def test_money_hyphen_variant():
    answer = "Mức định giá là 45 triệu-USD."
    sensitive_facts = [{"type": "money", "value": "45 triệu USD"}]

    result = redact_answer(answer, sensitive_facts)

    assert "45 triệu-USD" not in result
    assert "[REDACTED]" in result


def test_month_year_comma_variant():
    answer = "Kế hoạch hoàn tất vào tháng 12, năm 2026."
    sensitive_facts = [{"type": "date", "value": "12/2026"}]

    result = redact_answer(answer, sensitive_facts)

    assert "tháng 12, năm 2026" not in result
    assert "[REDACTED]" in result


def test_exact_entity_does_not_match_inside_larger_identifier():
    answer = "Đối tác là công ty XYZCorp."
    sensitive_facts = [{"type": "named_entity", "value": "công ty XYZ"}]

    result = redact_answer(answer, sensitive_facts)

    assert result == answer
    assert "[REDACTED]" not in result


def test_exact_entity_still_matches_with_punctuation():
    answer = "Đối tác (công ty XYZ), đang được xem xét."
    sensitive_facts = [{"type": "named_entity", "value": "công ty XYZ"}]

    result = redact_answer(answer, sensitive_facts)

    assert "công ty XYZ" not in result
    assert "[REDACTED]" in result
