from entity_normalizer import (
    normalize_money,
    normalize_date,
    normalize_year,
    normalize_quantity,
    normalize_ratio,
    normalize_time_range,
)


NORMALIZERS = {
    "money": normalize_money,
    "date": normalize_date,
    "year": normalize_year,
    "quantity": normalize_quantity,
    "ratio": normalize_ratio,
    "time_range": normalize_time_range,
}


def normalize_protected_fact(fact):
    """
    Chuẩn hóa một protected fact về canonical representation.

    Fact đầu vào tối thiểu:
    {
        "type": "...",
        "value": "..."
    }

    Các metadata khác như protection_profile/protected
    không được matcher sử dụng để quyết định policy.
    """

    fact_type = fact["type"]
    value = fact["value"]

    normalizer = NORMALIZERS.get(fact_type)

    if normalizer is None:
        return None

    return normalizer(value)


def match_protected_facts(protected_facts, answer_facts):
    """
    Tìm các protected facts xuất hiện trong answer.

    Matcher chỉ thực hiện DETECTION/MATCHING.
    Nó KHÔNG quyết định ALLOW hay REDACT.

    protected_facts:
        Các fact đã được protection profile xác định là cần bảo vệ.

    answer_facts:
        Structured facts được extract từ câu trả lời của LLM.
    """

    matches = []

    for protected_fact in protected_facts:
        protected_type = protected_fact["type"]

        protected_canonical = normalize_protected_fact(
            protected_fact
        )

        if protected_canonical is None:
            continue

        for answer_fact in answer_facts:

            if answer_fact["type"] != protected_type:
                continue

            if answer_fact["canonical"] != protected_canonical:
                continue

            matches.append({
                "type": protected_type,
                "protected_value": protected_fact["value"],
                "matched_raw": answer_fact["raw"],
                "canonical": answer_fact["canonical"],
                "start": answer_fact["start"],
                "end": answer_fact["end"],
            })

    return matches


# Backward-compatible alias trong giai đoạn chuyển đổi.
# Code cũ vẫn có thể gọi match_sensitive_facts().
def match_sensitive_facts(sensitive_facts, answer_facts):
    return match_protected_facts(sensitive_facts, answer_facts)
