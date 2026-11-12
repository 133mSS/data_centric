"""Policy Decision Point: Bell-LaPadula + ABAC."""
from dataclasses import dataclass
from typing import Any, Mapping

LEVEL = {"Công khai": 0, "Nội bộ": 1, "Mật": 2, "Tối mật": 3}
CLEARANCE = {"Đối tác": 0, "Nhân viên": 1, "Manager": 2, "Ban lãnh đạo": 3}
DEPARTMENT_WHOLE_ORG = "Toàn công ty"


@dataclass(frozen=True)
class Decision:
    effect: str
    reason: str
    rule_id: str


def decide(subject: Mapping[str, Any], resource: Mapping[str, Any], action: str = "read") -> Decision:
    """Return a fail-closed access decision.

    The documented legacy leadership override is retained. For otherwise valid
    inputs, existing policy semantics are unchanged.
    """
    # Reject malformed top-level inputs instead of raising AttributeError.
    if not isinstance(subject, Mapping) or not isinstance(resource, Mapping):
        return Decision("DENY", "invalid_subject_or_resource", "DEFAULT-DENY")

    if action != "read":
        return Decision("DENY", "unsupported_action", "DEFAULT-DENY")

    role = subject.get("role")
    classification = resource.get("classification")

    # Intentionally preserved: leadership bypasses classification/department checks.
    if role == "Ban lãnh đạo":
        return Decision("ALLOW", "leadership_override", "LEGACY-LEADERSHIP")

    clearance = CLEARANCE.get(role)
    level = LEVEL.get(classification)
    if clearance is None or level is None:
        return Decision("DENY", "unknown_role_or_classification", "DEFAULT-DENY")
    if clearance < level:
        return Decision("DENY", "no-read-up", "BLP-1")

    resource_department = resource.get("department")
    subject_department = subject.get("department")
    if (
        resource_department in (None, DEPARTMENT_WHOLE_ORG)
        or subject_department in (resource_department, DEPARTMENT_WHOLE_ORG)
    ):
        return Decision("ALLOW", "clearance+department ok", "ABAC-2")
    return Decision("DENY", "department mismatch", "ABAC-2")
