import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from entity_normalizer import (
    normalize_money,
    normalize_date,
    normalize_year,
    normalize_quantity,
    normalize_ratio,
    normalize_time_range,
)


def test_money():
    assert normalize_money("45 triệu USD") == "money:45:million:USD"
    assert normalize_money("45 triệu đô la Mỹ") == "money:45:million:USD"
    assert normalize_money("12 triệu USD") != "money:45:million:USD"


def test_date():
    assert normalize_date("15/10/2026") == "date:2026-10-15"
    assert normalize_date("12/2026") == "date:2026-12"
    assert normalize_date("tháng 12/2026") == "date:2026-12"
    assert normalize_date("tháng 12 năm 2026") == "date:2026-12"

    assert normalize_date("11/2026") != "date:2026-12"


def test_year():
    assert normalize_year("năm 2027") == "year:2027"
    assert normalize_year("2027") == "year:2027"


def test_quantity():
    assert normalize_quantity("5.000 máy chủ") == "quantity:5000:máy chủ"
    assert normalize_quantity("5000 máy chủ") == "quantity:5000:máy chủ"


def test_ratio():
    assert normalize_ratio("12/20") == "ratio:12/20"


def test_time_range():
    assert normalize_time_range("22:00–23:30") == "time:22:00-23:30"
    assert normalize_time_range("22:00 đến 23:30") == "time:22:00-23:30"


if __name__ == "__main__":
    test_money()
    test_date()
    test_year()
    test_quantity()
    test_ratio()
    test_time_range()

    print("ALL ENTITY NORMALIZER TESTS PASS")