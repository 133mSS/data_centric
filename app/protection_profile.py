"""
Document protection profiles for Output DLP.

ABAC classification decides whether a user may retrieve a document.
A protection profile selects specific facts that Output DLP must protect
when content is released in a restricted release context.

This module does not perform retrieval, matching, release decisions, or masking.
"""

from copy import deepcopy


PROTECTION_PROFILES = {
    "PUBLIC": {
        "protected_facts": [],
        "protected_phrases": [],
        "contextual_phrases": [],
        "protected_entities": [],
    },
    "GENERAL_INTERNAL": {
        "protected_facts": [],
        "protected_phrases": [],
        "contextual_phrases": [],
        "protected_entities": [],
    },
    "PERFORMANCE_SENSITIVE": {
        "protected_facts": [
            {"type": "ratio", "canonical": "ratio:12/20"},
            # Canonical format for quantity should be confirmed against the
            # project's entity_normalizer before enabling paraphrase matching.
            {"type": "quantity", "raw": "2 nhân viên"},
        ],
        # Contextual phrases are protected when their source profile applies,
        # but are not treated as globally sensitive values.
        "protected_phrases": ["cảnh báo hiệu suất thấp"],
        "contextual_phrases": ["Xuất sắc"],
        "protected_entities": [],
    },
    "CORPORATE_SECRET": {
        "protected_facts": [
            {"type": "money", "canonical": "money:45:million:USD", "contextual": True},
            {"type": "date", "canonical": "date:2026-12", "contextual": True},
        ],
        "protected_phrases": ["Kế hoạch sáp nhập"],
        "contextual_phrases": [],
        "protected_entities": ["XYZ"],
    },
    "COMMERCIAL_SECRET": {
        "protected_facts": [
            # Confirm the quantity canonical format with entity_normalizer
            # before adding a canonical selector for the server count.
            {"type": "quantity", "canonical": "quantity:5000:máy chủ"},
            {"type": "year", "canonical": "year:2027"},
            {"type": "money", "canonical": "money:2.8:million:USD"},
        ],
        "protected_phrases": [],
        "contextual_phrases": [],
        "protected_entities": ["Nhà cung cấp A"],
    },
    "TECHNICAL_SENSITIVE": {
        "protected_facts": [],
        "protected_phrases": [],
        "contextual_phrases": ["policy_engine.py"],
        "protected_entities": [],
    },
    "MAINTENANCE_NOTICE": {
        "protected_facts": [
            {"type": "time_range", "canonical": "time:22:00-23:30", "contextual": True},
            {"type": "date", "canonical": "date:2026-10-15"},
        ],
        "protected_phrases": [],
        "contextual_phrases": [],
        "protected_entities": [],
    },
    "PUBLIC_RECRUITMENT": {
        "protected_facts": [],
        "protected_phrases": [],
        "contextual_phrases": [],
        "protected_entities": [],
    },
}


# Values that are meaningful only when interpreted with explicit context.
# Signals are deliberately narrow and configured per canonical value. A sensitive
# signal takes precedence over a benign signal; absence of both means UNCERTAIN.
CONTEXTUAL_FACT_RULES = {
    "time:22:00-23:30": {
        "type": "time_range",
        "sensitive_profiles": ["MAINTENANCE_NOTICE"],
        "sensitive_signals": ["bảo trì hệ thống", "thông báo bảo trì hệ thống"],
        "benign_signals": ["lịch bảo trì phòng họp", "vào tối thứ sáu"],
    },
    "date:2026-12": {
        "type": "date",
        "sensitive_profiles": ["CORPORATE_SECRET"],
        "sensitive_signals": ["kế hoạch sáp nhập", "xyz"],
        "benign_signals": ["thông báo chung", "dự kiến hoàn thành công việc"],
    },
    "money:45:million:USD": {
        "type": "money",
        "sensitive_profiles": ["CORPORATE_SECRET"],
        "sensitive_signals": ["kế hoạch sáp nhập", "xyz"],
        "benign_signals": ["bảng ví dụ tài chính", "minh họa khoản ngân sách"],
    },
}

# Explicit mapping for the eight Phase 1 sample documents.
# This is a prototype mapping; scalable storage can later move to document metadata.
DOCUMENT_PROFILES = {
    1: "PUBLIC",
    2: "GENERAL_INTERNAL",
    3: "PERFORMANCE_SENSITIVE",
    4: "CORPORATE_SECRET",
    5: "COMMERCIAL_SECRET",
    6: "TECHNICAL_SENSITIVE",
    7: "MAINTENANCE_NOTICE",
    8: "PUBLIC_RECRUITMENT",
}


def get_protection_profile(profile_name: str) -> dict:
    """Return a copy so callers cannot mutate the global policy."""
    profile = PROTECTION_PROFILES.get(profile_name)
    if profile is None:
        raise ValueError(f"Unknown protection profile: {profile_name}")
    return deepcopy(profile)


def get_document_profile(document_id: int, metadata_profile: str | None = None) -> str:
    """Resolve profile from trusted document metadata, with legacy ID fallback.

    Metadata is authoritative for newly generated benchmark documents. The
    ID mapping remains only for the original eight seed documents during
    migration. Unknown IDs without valid metadata are rejected (fail-closed).
    """
    if metadata_profile is not None:
        if metadata_profile not in PROTECTION_PROFILES:
            raise ValueError("Unknown protection profile in document metadata")
        return metadata_profile
    try:
        return DOCUMENT_PROFILES[document_id]
    except KeyError as exc:
        raise ValueError(
            f"No protection profile configured for document_id={document_id}"
        ) from exc


def _fact_matches_selector(fact: dict, selector: dict) -> bool:
    if fact.get("type") != selector.get("type"):
        return False
    if "canonical" in selector:
        return fact.get("canonical") == selector["canonical"]
    if "raw" in selector:
        return fact.get("raw", "").casefold() == selector["raw"].casefold()
    return False


def select_protected_facts(
    profile_name: str,
    detected_facts: list[dict],
    source_text: str = "",
) -> list[dict]:
    """
    Select only facts explicitly configured in the profile.

    Structured fact input items are expected to contain type, raw and,
    when available, canonical. A selector matches by canonical value when
    configured; otherwise it matches the raw value exactly (case-insensitive).
    """
    profile = get_protection_profile(profile_name)
    protected = []

    for fact in detected_facts:
        for selector in profile["protected_facts"]:
            if _fact_matches_selector(fact, selector):
                protected.append({
                    "type": fact["type"],
                    "value": fact.get("raw", ""),
                    "canonical": fact.get("canonical"),
                    "protected": True,
                    "profile": profile_name,
                })
                break

    

    source_text_normalized = source_text.casefold()

    for entity in profile["protected_entities"]:
        if entity.casefold() in source_text_normalized:
            protected.append({
                "type": "named_entity",
                "value": entity,
                "protected": True,
                "profile": profile_name,
            })

    for phrase in profile["protected_phrases"]:
        if phrase.casefold() in source_text_normalized:
            protected.append({
                "type": "sensitive_phrase",
                "value": phrase,
                "protected": True,
                "profile": profile_name,
            })

    # Contextual phrases are selected only from the source's own profile.
    # They are deliberately excluded from the global protection catalog.
    for phrase in profile.get("contextual_phrases", []):
        if phrase.casefold() in source_text_normalized:
            protected.append({
                "type": "sensitive_phrase",
                "value": phrase,
                "protected": True,
                "profile": profile_name,
            })

    return protected

