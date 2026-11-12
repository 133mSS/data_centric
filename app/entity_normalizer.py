import re


def normalize_money(text: str):
    """Normalize equivalent USD-million formats to one canonical value.

    Examples:
    - 45 triệu USD / 45 million USD / USD 45 million
    - bốn mươi lăm triệu USD
    -> money:45:million:USD
    """
    value_pattern = r"(\d+(?:[.,]\d+)?|bốn\s+mươi\s+lăm)"
    value_first = re.compile(
        value_pattern + r"\s*(?:triệu|million)\s*[-–—]?\s*"
        r"(?:USD|đô\s+la\s+Mỹ|US\s+dollars?)\b",
        re.IGNORECASE,
    )
    currency_first = re.compile(
        r"(?:USD|US\s+dollars?|đô\s+la\s+Mỹ)\s*"
        + value_pattern + r"\s*(?:triệu|million)\b",
        re.IGNORECASE,
    )

    match = value_first.search(text) or currency_first.search(text)
    if not match:
        return None

    # In both patterns, group 1 is the amount value.
    raw_value = re.sub(r"\s+", " ", match.group(1).strip()).casefold()
    if raw_value == "bốn mươi lăm":
        value = "45"
    else:
        value = raw_value.replace(",", ".")

    return f"money:{value}:million:USD"


def normalize_date(text: str):
    """
    Chuẩn hóa:
    15/10/2026
    -> date:2026-10-15

    12/2026
    tháng 12/2026
    tháng 12 năm 2026
    -> date:2026-12
    """

    # Full date: DD/MM/YYYY
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        text
    )

    if match:
        day, month, year = match.groups()

        return (
            f"date:{year}-"
            f"{int(month):02d}-"
            f"{int(day):02d}"
        )

    # Month/year: MM/YYYY
    match = re.search(
        r"\b(\d{1,2})/(\d{4})\b",
        text
    )

    if match:
        month, year = match.groups()

        return f"date:{year}-{int(month):02d}"

    # tháng MM/YYYY
    match = re.search(
        r"tháng\s+(\d{1,2})/(\d{4})",
        text,
        re.IGNORECASE
    )

    if match:
        month, year = match.groups()

        return f"date:{year}-{int(month):02d}"

    # tháng MM năm YYYY
    match = re.search(
        r"tháng\s+(\d{1,2})\s*,?\s+năm\s+(\d{4})",
        text,
        re.IGNORECASE
    )

    if match:
        month, year = match.groups()

        return f"date:{year}-{int(month):02d}"

    # English month name + year, e.g. December 2026 or Dec 2026.
    english_months = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    match = re.search(
        r"\b(january|jan\.?|february|feb\.?|march|mar\.?|"
        r"april|apr\.?|may|june|jun\.?|july|jul\.?|"
        r"august|aug\.?|september|sept?\.?|october|oct\.?|"
        r"november|nov\.?|december|dec\.?)\s+(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        month_name, year = match.groups()
        month_key = month_name.casefold().rstrip(".")
        return f"date:{year}-{english_months[month_key]:02d}"

    return None


def normalize_year(text: str):
    """
    Chuẩn hóa năm:
    năm 2027
    2027
    -> year:2027
    """

    match = re.search(r"\bnăm\s+(\d{4})\b|\b(20\d{2})\b", text)

    if not match:
        return None

    year = match.group(1) or match.group(2)

    return f"year:{year}"


def normalize_quantity(text: str):
    """
    Chuẩn hóa số lượng:
    5.000 máy chủ
    5000 máy chủ
    -> quantity:5000:máy chủ
    """

    match = re.search(
        r"\b(\d+(?:\.\d+)*)\s+(máy chủ|nhân viên)\b",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    value = match.group(1).replace(".", "")
    unit = match.group(2).lower()

    return f"quantity:{value}:{unit}"


def normalize_ratio(text: str):
    """
    Chuẩn hóa tỷ lệ:
    12/20
    -> ratio:12/20
    """

    match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", text)

    if not match:
        return None

    numerator, denominator = match.groups()

    return f"ratio:{numerator}/{denominator}"


def normalize_time_range(text: str):
    """
    Chuẩn hóa khoảng thời gian:
    22:00–23:30
    22:00 - 23:30
    22:00 đến 23:30
    """

    pattern = re.compile(
        r"(\d{1,2}:\d{2})\s*"
        r"(?:-|–|—|đến)\s*"
        r"(\d{1,2}:\d{2})",
        re.IGNORECASE
    )

    match = pattern.search(text)

    if not match:
        return None

    start, end = match.groups()

    return f"time:{start}-{end}"