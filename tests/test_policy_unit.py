"""Unit tests for app/policy.py; no database or external service required."""
import pytest
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from policy import check_access


ROLES = ("Ban lãnh đạo", "Đối tác", "Nhân viên", "Manager")
CLASSIFICATIONS = ("Công khai", "Nội bộ", "Mật", "Tối mật")


def expected_decision(role, classification, user_department, document_department):
    """Mirror the approved policy rules as an explicit test oracle."""
    if role == "Ban lãnh đạo":
        return "ALLOW"
    if role == "Đối tác":
        return "ALLOW" if classification == "Công khai" else "DENY"
    if role == "Nhân viên":
        allowed_classifications = ("Công khai", "Nội bộ")
    elif role == "Manager":
        allowed_classifications = ("Công khai", "Nội bộ", "Mật")
    else:
        return "DENY"

    if classification not in allowed_classifications:
        return "DENY"
    if document_department is not None and document_department != user_department:
        return "DENY"
    return "ALLOW"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_role_classification_matrix(role, classification):
    """Cover every role × classification pair for same-department documents."""
    user = {"role": role, "department": "Kỹ thuật"}
    document = {"classification": classification, "department": "Kỹ thuật"}
    assert check_access(user, document) == expected_decision(
        role, classification, "Kỹ thuật", "Kỹ thuật"
    )


@pytest.mark.parametrize("role", ("Nhân viên", "Manager"))
@pytest.mark.parametrize("classification", CLASSIFICATIONS)
@pytest.mark.parametrize("document_department", ("Kỹ thuật", "Kinh doanh", None))
def test_department_boundaries(role, classification, document_department):
    """Same dept allows eligible classifications; other dept denies; None follows approved rule."""
    user = {"role": role, "department": "Kỹ thuật"}
    document = {
        "classification": classification,
        "department": document_department,
    }
    assert check_access(user, document) == expected_decision(
        role, classification, "Kỹ thuật", document_department
    )


@pytest.mark.parametrize("role", ("Nhân viên", "Manager"))
def test_user_department_none_with_document_department_none(role):
    """A missing department on both sides follows the current equality semantics."""
    for classification in CLASSIFICATIONS:
        user = {"role": role, "department": None}
        document = {"classification": classification, "department": None}
        assert check_access(user, document) == expected_decision(
            role, classification, None, None
        )


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_leadership_can_access_all_classifications_even_other_department(classification):
    user = {"role": "Ban lãnh đạo", "department": "Kỹ thuật"}
    document = {"classification": classification, "department": "Kinh doanh"}
    assert check_access(user, document) == "ALLOW"


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_partner_only_accesses_public(classification):
    user = {"role": "Đối tác", "department": "Kỹ thuật"}
    document = {"classification": classification, "department": None}
    expected = "ALLOW" if classification == "Công khai" else "DENY"
    assert check_access(user, document) == expected


@pytest.mark.parametrize("role", ("", "Unknown", None))
def test_unknown_role_fails_closed(role):
    user = {"role": role, "department": "Kỹ thuật"}
    document = {"classification": "Công khai", "department": "Kỹ thuật"}
    assert check_access(user, document) == "DENY"


@pytest.mark.parametrize("role", ("Nhân viên", "Manager", "Đối tác"))
def test_unknown_classification_is_denied_for_non_leadership(role):
    user = {"role": role, "department": "Kỹ thuật"}
    document = {"classification": "UNKNOWN", "department": "Kỹ thuật"}
    assert check_access(user, document) == "DENY"
