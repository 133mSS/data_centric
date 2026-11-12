import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
    
from protection_profile import (
    DOCUMENT_PROFILES,
    get_document_profile,
    get_protection_profile,
    select_protected_facts,
)


# ============================================================
# 1. Document profile mapping
# ============================================================

assert set(DOCUMENT_PROFILES) == set(range(1, 9))
assert get_document_profile(6) == "TECHNICAL_SENSITIVE"
assert get_document_profile(4) == "CORPORATE_SECRET"


# ============================================================
# 2. Structured facts and CORPORATE_SECRET profile
# ============================================================

facts = [
    {
        "type": "money",
        "raw": "45 triệu USD",
        "canonical": "money:45:million:USD",
    },
    {
        "type": "money",
        "raw": "12 triệu USD",
        "canonical": "money:12:million:USD",
    },
    {
        "type": "date",
        "raw": "tháng 12/2026",
        "canonical": "date:2026-12",
    },
    {
        "type": "ratio",
        "raw": "12/20",
        "canonical": "ratio:12/20",
    },
]

source_text = (
    "Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất "
    "tháng 12/2026, mức định giá thương lượng là 45 triệu USD."
)

protected = select_protected_facts(
    "CORPORATE_SECRET",
    facts,
    source_text=source_text,
)

# Matching canonical values must be protected.
assert any(
    f.get("canonical") == "money:45:million:USD"
    for f in protected
)
assert any(
    f.get("canonical") == "date:2026-12"
    for f in protected
)

# Non-matching structured facts must not be protected.
assert not any(
    f.get("canonical") == "money:12:million:USD"
    for f in protected
)
assert not any(
    f["type"] == "ratio"
    for f in protected
)


# ============================================================
# 3. Phrase/entity must exist in source text
# ============================================================

assert any(
    f["type"] == "named_entity" and f["value"] == "XYZ"
    for f in protected
)

assert any(
    f["type"] == "sensitive_phrase"
    and f["value"] == "Kế hoạch sáp nhập"
    for f in protected
)

# If phrase/entity is absent from source, it must not be selected.
source_without_entity_phrase = (
    "Báo cáo tài chính quý 3/2026 "
    "có giá trị 45 triệu USD."
)

protected_without_entity_phrase = select_protected_facts(
    "CORPORATE_SECRET",
    facts,
    source_text=source_without_entity_phrase,
)

assert not any(
    f["type"] == "named_entity" and f["value"] == "XYZ"
    for f in protected_without_entity_phrase
)

assert not any(
    f["type"] == "sensitive_phrase"
    and f["value"] == "Kế hoạch sáp nhập"
    for f in protected_without_entity_phrase
)

# Structured facts are still selected according to the profile.
assert any(
    f.get("canonical") == "money:45:million:USD"
    for f in protected_without_entity_phrase
)


# ============================================================
# 4. PERFORMANCE_SENSITIVE profile
# ============================================================

performance_source = (
    "Bảng đánh giá có 12/20 nhân viên đạt mức Xuất sắc, "
    "2 nhân viên nằm trong danh sách cảnh báo hiệu suất thấp."
)

performance_facts = [
    {
        "type": "ratio",
        "raw": "12/20",
        "canonical": "ratio:12/20",
    },
    {
        "type": "quantity",
        "raw": "2 nhân viên",
        "canonical": "quantity:2:person",
    },
    {
        "type": "quantity",
        "raw": "20 nhân viên",
        "canonical": "quantity:20:person",
    },
]

performance = select_protected_facts(
    "PERFORMANCE_SENSITIVE",
    performance_facts,
    source_text=performance_source,
)

# Quantity uses exact raw matching until canonical format is confirmed.
assert any(
    f["type"] == "quantity" and f["value"] == "2 nhân viên"
    for f in performance
)
assert not any(
    f["type"] == "quantity" and f["value"] == "20 nhân viên"
    for f in performance
)

# Sensitive phrases must exist in source text.
assert any(
    f["type"] == "sensitive_phrase" and f["value"] == "Xuất sắc"
    for f in performance
)
assert any(
    f["type"] == "sensitive_phrase"
    and f["value"] == "cảnh báo hiệu suất thấp"
    for f in performance
)


# ============================================================
# 5. Case-insensitive phrase/entity verification
# ============================================================

case_insensitive_source = (
    "kế HOẠCH SÁP NHẬP với công ty xyz."
)

case_insensitive = select_protected_facts(
    "CORPORATE_SECRET",
    [],
    source_text=case_insensitive_source,
)

assert any(
    f["type"] == "named_entity" and f["value"] == "XYZ"
    for f in case_insensitive
)

assert any(
    f["type"] == "sensitive_phrase"
    and f["value"] == "Kế hoạch sáp nhập"
    for f in case_insensitive
)


# ============================================================
# 6. PUBLIC profile
# ============================================================

assert select_protected_facts(
    "PUBLIC",
    facts,
    source_text=source_text,
) == []


# ============================================================
# 7. Fail closed for unknown profiles/documents
# ============================================================

for operation in (
    lambda: get_protection_profile("UNKNOWN"),
    lambda: get_document_profile(999),
):
    try:
        operation()
        raise AssertionError(
            "Unknown profile/document must fail"
        )
    except ValueError:
        pass


# ============================================================
# 8. Profile configuration must not be mutable externally
# ============================================================

profile = get_protection_profile("PUBLIC")
profile["protected_facts"].append(
    {"type": "money", "canonical": "anything"}
)

assert (
    get_protection_profile("PUBLIC")["protected_facts"] == []
)


# ============================================================
# 9. COMMERCIAL_SECRET canonical selectors
# ============================================================

commercial_facts = [
    {
        "type": "quantity",
        "raw": "5.000 máy chủ",
        "canonical": "quantity:5000:máy chủ",
    },
    {
        "type": "quantity",
        "raw": "6.000 máy chủ",
        "canonical": "quantity:6000:máy chủ",
    },
    {
        "type": "year",
        "raw": "năm 2027",
        "canonical": "year:2027",
    },
    {
        "type": "year",
        "raw": "năm 2028",
        "canonical": "year:2028",
    },
    {
        "type": "money",
        "raw": "2,8 triệu USD",
        "canonical": "money:2.8:million:USD",
    },
]

commercial = select_protected_facts(
    "COMMERCIAL_SECRET",
    commercial_facts,
    source_text=(
        "ABC Tech cung cấp 5.000 máy chủ "
        "trong năm 2027 với giá trị 2,8 triệu USD "
        "cho Nhà cung cấp A."
    ),
)

assert any(
    f.get("canonical") == "quantity:5000:máy chủ"
    for f in commercial
)
assert not any(
    f.get("canonical") == "quantity:6000:máy chủ"
    for f in commercial
)
assert any(
    f.get("canonical") == "year:2027"
    for f in commercial
)
assert not any(
    f.get("canonical") == "year:2028"
    for f in commercial
)
assert any(
    f.get("canonical") == "money:2.8:million:USD"
    for f in commercial
)
assert any(
    f["type"] == "named_entity"
    and f["value"] == "Nhà cung cấp A"
    for f in commercial
)


# ============================================================
# 10. MAINTENANCE_NOTICE canonical selectors
# ============================================================

maintenance_facts = [
    {
        "type": "time_range",
        "raw": "22:00 đến 23:30",
        "canonical": "time:22:00-23:30",
    },
    {
        "type": "time_range",
        "raw": "23:00 đến 23:30",
        "canonical": "time:23:00-23:30",
    },
]

maintenance = select_protected_facts(
    "MAINTENANCE_NOTICE",
    maintenance_facts,
    source_text=(
        "Hệ thống được bảo trì từ 22:00 đến 23:30 "
        "ngày 15/10/2026."
    ),
)

assert any(
    f.get("canonical") == "time:22:00-23:30"
    for f in maintenance
)
assert not any(
    f.get("canonical") == "time:23:00-23:30"
    for f in maintenance
)


print("ALL PROTECTION PROFILE TESTS PASSED")
