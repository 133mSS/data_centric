import itertools
import pytest
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from pdp import decide
from pep import enforce_access
from policy import check_access

ROLES = ["Đối tác", "Nhân viên", "Manager", "Ban lãnh đạo"]
CLASSES = ["Công khai", "Nội bộ", "Mật", "Tối mật"]
DEPTS = ["Kỹ thuật", "Kinh doanh", "Toàn công ty", None]
# Bảng kỳ vọng viết tay, độc lập với implementation PDP.
EXPECTED = {
 "Đối tác": {"Công khai":"ALLOW", "Nội bộ":"DENY", "Mật":"DENY", "Tối mật":"DENY"},
 "Nhân viên": {"Công khai":"ALLOW", "Nội bộ":"ALLOW", "Mật":"DENY", "Tối mật":"DENY"},
 "Manager": {"Công khai":"ALLOW", "Nội bộ":"ALLOW", "Mật":"ALLOW", "Tối mật":"DENY"},
 "Ban lãnh đạo": {"Công khai":"ALLOW", "Nội bộ":"ALLOW", "Mật":"ALLOW", "Tối mật":"ALLOW"},
}

@pytest.mark.parametrize("role,classification,user_dept,doc_dept", list(itertools.product(ROLES, CLASSES, DEPTS, DEPTS)))
def test_full_policy_matrix(role, classification, user_dept, doc_dept):
    expected = EXPECTED[role][classification]
    if expected == "ALLOW" and role != "Ban lãnh đạo" and doc_dept not in (None, "Toàn công ty") and user_dept not in (doc_dept, "Toàn công ty"):
        expected = "DENY"
    subject = {"role": role, "department": user_dept}
    resource = {"classification": classification, "department": doc_dept}
    assert decide(subject, resource).effect == expected
    assert check_access(subject, resource) == expected
    assert enforce_access(subject, resource).effect == expected

@pytest.mark.parametrize("role", ["Nhân viên", "Manager"])
def test_internal_company_wide_document_allowed(role):
    assert decide({"role":role,"department":"Kỹ thuật"}, {"classification":"Nội bộ","department":"Toàn công ty"}).effect == "ALLOW"

@pytest.mark.parametrize("role", ["Unknown", None, ""])
def test_unknown_role_fails_closed(role):
    assert decide({"role":role,"department":"Kỹ thuật"}, {"classification":"Công khai","department":"Kỹ thuật"}).effect == "DENY"

def test_unknown_classification_fails_closed():
    assert decide({"role":"Manager","department":"Kỹ thuật"}, {"classification":"UNKNOWN","department":"Kỹ thuật"}).effect == "DENY"

def test_leadership_legacy_override():
    decision = decide({"role":"Ban lãnh đạo","department":"Kỹ thuật"}, {"classification":"Tối mật","department":"Kinh doanh"})
    assert decision.effect == "ALLOW"
    assert decision.rule_id == "LEGACY-LEADERSHIP"


def test_unsupported_action_is_denied_before_leadership_override():
    assert decide(
        {"role": "Ban lãnh đạo", "department": "Toàn công ty"},
        {"classification": "Tối mật", "department": "Toàn công ty"},
        action="write",
    ).effect == "DENY"
