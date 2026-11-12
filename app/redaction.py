from structured_fact_extractor import extract_structured_facts
from sensitive_fact_matcher import match_sensitive_facts
import re

STRUCTURED_TYPES = {
    "money",
    "date",
    "year",
    "quantity",
    "ratio",
    "time_range",
}



def find_exact_matches(answer, sensitive_facts):
    """
    Tìm textual facts bằng exact matching không phân biệt hoa/thường.
    Giữ nguyên vị trí span trong chuỗi answer gốc.
    """
    matches = []

    for fact in sensitive_facts:
        fact_type = fact["type"]

        if fact_type in STRUCTURED_TYPES:
            continue

        value = fact["value"]

        if not value:
            continue

        # Match complete textual values, not substrings inside larger identifiers.
        # Python's Unicode-aware \w boundary also supports Vietnamese text.
        pattern = re.compile(
            r"(?<!\w)" + re.escape(value) + r"(?!\w)",
            re.IGNORECASE,
        )

        for match in pattern.finditer(answer):
            start, end = match.span()

            matches.append({
                "type": fact_type,
                "sensitive_value": value,
                "matched_raw": match.group(0),
                "start": start,
                "end": end,
            })

    return matches



def merge_matches(structured_matches, exact_matches):
    all_matches = sorted(
        structured_matches + exact_matches,
        key=lambda item: (item["start"], item["end"]),
    )

    if not all_matches:
        return []

    merged = []

    for match in all_matches:
        current = dict(match)

        if not merged or current["start"] >= merged[-1]["end"]:
            current["types"] = [current["type"]]
            merged.append(current)
            continue

        previous = merged[-1]

        # Lưu span gốc trước khi cập nhật tọa độ span hợp nhất.
        previous.setdefault("components", [dict(previous)])
        previous["components"].append(dict(current))

        previous["end"] = max(previous["end"], current["end"])

        if current["type"] not in previous["types"]:
            previous["types"].append(current["type"])

    return merged



def apply_redaction(answer, matches):
    """
    Thay các span sensitive bằng [REDACTED].

    Xử lý từ phải sang trái để không làm
    thay đổi index của các span phía trước.
    """

    redacted_answer = answer

    sorted_matches = sorted(
        matches,
        key=lambda item: item["start"],
        reverse=True,
    )

    for match in sorted_matches:
        start = match["start"]
        end = match["end"]

        redacted_answer = (
            redacted_answer[:start]
            + "[REDACTED]"
            + redacted_answer[end:]
        )

    return redacted_answer


def redact_answer(answer, sensitive_facts):
    """
    Hybrid Dynamic Redaction.

    1. Structured matching
    2. Exact text matching
    3. Merge spans
    4. Redact
    """

    answer_facts = extract_structured_facts(answer)

    structured_matches = match_sensitive_facts(
        sensitive_facts,
        answer_facts,
    )

    exact_matches = find_exact_matches(
        answer,
        sensitive_facts,
    )

    matches = merge_matches(
        structured_matches,
        exact_matches,
    )

    redacted_answer = apply_redaction(
        answer,
        matches,
    )

    return redacted_answer