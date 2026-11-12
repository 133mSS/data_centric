import re

from entity_normalizer import (
    normalize_money,
    normalize_date,
    normalize_year,
    normalize_quantity,
    normalize_ratio,
    normalize_time_range,
)


def _overlaps(start, end, occupied):
    """Kiểm tra span có chồng lên fact đã phát hiện hay không."""
    return any(start < old_end and end > old_start
               for old_start, old_end in occupied)


def _append_matches(facts, occupied, text, pattern, fact_type, normalizer):
    """
    Thêm các structured facts, đồng thời loại bỏ span chồng lấn.

    Thứ tự extractor rất quan trọng:
    date phải được nhận diện trước ratio để '15/10/2026'
    không bị nhận nhầm thêm thành ratio '15/10'.
    """
    for match in pattern.finditer(text):
        start, end = match.span()

        if _overlaps(start, end, occupied):
            continue

        raw = match.group(0)
        canonical = normalizer(raw)

        if not canonical:
            continue

        facts.append({
            "type": fact_type,
            "raw": raw,
            "canonical": canonical,
            "start": start,
            "end": end,
        })
        occupied.append((start, end))


def extract_structured_facts(text: str):
    """
    Phát hiện structured facts trong text và chuẩn hóa chúng.

    Supported types:
    - money
    - date
    - year
    - quantity
    - ratio
    - time_range

    Quy tắc:
    - Mỗi span trong answer chỉ được gán cho một structured fact.
    - Date được ưu tiên trước ratio để tránh nhận nhầm DD/MM
      hoặc MM/YYYY thành ratio.
    """

    facts = []
    occupied = []

    # -------------------------
    # 1. MONEY
    # -------------------------
    # Support both amount-first (45 million USD) and currency-first
    # (USD 45 million) representations. Keep each complete amount in one span.
    money_pattern = re.compile(
        r"(?:\b(?:\d+(?:[.,]\d+)?|bốn\s+mươi\s+lăm)\s*"
        r"(?:triệu|million)\s*[-–—]?\s*"
        r"(?:USD|đô\s+la\s+Mỹ|US\s+dollars?)\b"
        r"|\b(?:USD|US\s+dollars?|đô\s+la\s+Mỹ)\s*"
        r"(?:\d+(?:[.,]\d+)?|bốn\s+mươi\s+lăm)\s*"
        r"(?:triệu|million)\b)",
        re.IGNORECASE,
    )

    _append_matches(
        facts, occupied, text,
        money_pattern, "money", normalize_money
    )

    # -------------------------
    # 2. DATE
    #    Full date trước, sau đó month/year.
    # -------------------------
    date_patterns = [
        # Ưu tiên biểu diễn đầy đủ và biểu diễn có từ "tháng"
        # trước pattern tổng quát MM/YYYY.
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
        re.compile(r"\btháng\s+\d{1,2}/\d{4}\b", re.IGNORECASE),
        re.compile(
            r"\btháng\s+\d{1,2}\s*,?\s+năm\s+\d{4}\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b\d{1,2}/\d{4}\b"),
        re.compile(
            r"\b(?:January|Jan\.?|February|Feb\.?|March|Mar\.?|"
            r"April|Apr\.?|May|June|Jun\.?|July|Jul\.?|"
            r"August|Aug\.?|September|Sept?\.?|October|Oct\.?|"
            r"November|Nov\.?|December|Dec\.?)\s+20\d{2}\b",
            re.IGNORECASE,
        ),
    ]

    for pattern in date_patterns:
        _append_matches(
            facts, occupied, text,
            pattern, "date", normalize_date
        )

    # -------------------------
    # 3. YEAR
    #    Giữ nguyên behavior cũ:
    #    chỉ nhận 'năm 2027', không tự nhận mọi số 4 chữ số.
    # -------------------------
    year_pattern = re.compile(r"\bnăm\s+20\d{2}\b", re.IGNORECASE)

    _append_matches(
        facts, occupied, text,
        year_pattern, "year", normalize_year
    )

    # -------------------------
    # 4. QUANTITY
    # -------------------------
    quantity_pattern = re.compile(
        r"(?<![/\d])\b\d+(?:\.\d+)*\s+(?:máy chủ|nhân viên)\b",
        re.IGNORECASE,
    )

    _append_matches(
        facts, occupied, text,
        quantity_pattern, "quantity", normalize_quantity
    )

    # -------------------------
    # 5. RATIO
    #    Chỉ nhận nếu span chưa thuộc date.
    # -------------------------
    ratio_pattern = re.compile(r"\b\d+\s*/\s*\d+\b")

    _append_matches(
        facts, occupied, text,
        ratio_pattern, "ratio", normalize_ratio
    )

    # -------------------------
    # 6. TIME RANGE
    # -------------------------
    time_pattern = re.compile(
        r"\b\d{1,2}:\d{2}\s*"
        r"(?:-|–|—|đến)\s*"
        r"\d{1,2}:\d{2}\b",
        re.IGNORECASE,
    )

    _append_matches(
        facts, occupied, text,
        time_pattern, "time_range", normalize_time_range
    )

    # Sort theo vị trí xuất hiện trong text để downstream
    # dễ xử lý deterministic.
    facts.sort(key=lambda item: item["start"])

    return facts
