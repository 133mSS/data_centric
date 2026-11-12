
"""
Output DLP release policy.

ABAC controls access to documents.
Output DLP controls whether protected facts can be released
in the current trusted release context.
"""

from enum import Enum


class ReleaseContext(str, Enum):
    INTERNAL_ASSISTANT = "INTERNAL_ASSISTANT"
    SHARE_SUMMARY = "SHARE_SUMMARY"


class ReleaseDecision(str, Enum):
    ALLOW = "ALLOW"
    REDACT = "REDACT"
    BLOCK = "BLOCK"


def decide_release(
    release_context: str,
    protected_matches: list[dict],
    uncertain_matches: list[dict] | None = None,
) -> dict:
    """
    Decide whether an answer may be released, redacted, or blocked.

    protected_matches contains confirmed sensitive values. uncertain_matches
    contains configured contextual values that lack sufficient evidence for a
    safe classification. SHARE_SUMMARY blocks on uncertainty; INTERNAL_ASSISTANT
    preserves the established ALLOW policy. Matching and redaction happen upstream.
    """

    try:
        context = ReleaseContext(release_context)
    except (ValueError, TypeError):
        raise ValueError(
            f"Unsupported release context: {release_context!r}"
        )

    uncertain_matches = uncertain_matches or []

    if context == ReleaseContext.INTERNAL_ASSISTANT:
        # Preserve the established internal release policy, including UNCERTAIN.
        decision = ReleaseDecision.ALLOW

    elif context == ReleaseContext.SHARE_SUMMARY:
        if uncertain_matches:
            decision = ReleaseDecision.BLOCK
        elif protected_matches:
            decision = ReleaseDecision.REDACT
        else:
            decision = ReleaseDecision.ALLOW

    else:
        # Defensive fallback; unsupported contexts must not be released.
        raise ValueError(
            f"Unsupported release context: {release_context!r}"
        )

    return {
        "release_context": context.value,
        "decision": decision.value,
        "matched_count": len(protected_matches),
        "uncertain_count": len(uncertain_matches),
    }
