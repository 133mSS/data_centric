import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from sensitive_fact_matcher import match_protected_facts
from structured_fact_extractor import extract_structured_facts


def match(source_fact, answer):
    answer_facts = extract_structured_facts(answer)
    return match_protected_facts([source_fact], answer_facts)


# 1. Money paraphrase -> MATCH
matches = match(
    {
        "type": "money",
        "value": "45 triệu USD",
        "protected": True,
    },
    "Mức định giá là 45 triệu đô la Mỹ."
)
assert len(matches) == 1
assert matches[0]["type"] == "money"
assert matches[0]["canonical"] == "money:45:million:USD"

# 2. Different money value -> NO MATCH
matches = match(
    {
        "type": "money",
        "value": "45 triệu USD",
        "protected": True,
    },
    "Mức định giá là 12 triệu USD."
)
assert matches == []

# 3. Date paraphrase -> MATCH
matches = match(
    {
        "type": "date",
        "value": "12/2026",
        "protected": True,
    },
    "Kế hoạch hoàn tất vào tháng 12 năm 2026."
)
assert len(matches) == 1
assert matches[0]["canonical"] == "date:2026-12"

# 4. Ratio -> MATCH
matches = match(
    {
        "type": "ratio",
        "value": "12/20",
        "protected": True,
    },
    "Có 12/20 nhân viên đạt mức Xuất sắc."
)
assert len(matches) == 1
assert matches[0]["canonical"] == "ratio:12/20"

# 5. Non-structured fact type is skipped here.
# Textual exact matching remains the responsibility of redaction.py.
matches = match(
    {
        "type": "sensitive_phrase",
        "value": "Xuất sắc",
        "protected": True,
    },
    "12/20 nhân viên đạt mức Xuất sắc."
)
assert matches == []

# 6. Metadata does not affect matching.
# protected=False is intentionally ignored here because this module
# only performs matching; protection_profile/output_dlp_policy decides
# whether a fact is protected/released.
matches = match(
    {
        "type": "money",
        "value": "45 triệu USD",
        "protected": False,
    },
    "Mức định giá là 45 triệu đô la Mỹ."
)
assert len(matches) == 1

print("ALL PROTECTED FACT MATCHER TESTS PASSED")
