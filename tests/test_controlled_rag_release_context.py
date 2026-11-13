"""Regression tests for trusted role-based Output DLP context selection."""

import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from controlled_rag import release_context_for_user


def test_internal_roles_use_internal_assistant_context():
    assert release_context_for_user({
        "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"
    }) == "INTERNAL_ASSISTANT"
    assert release_context_for_user({
        "username": "mgr_tech", "role": "Manager", "department": "Kỹ thuật"
    }) == "INTERNAL_ASSISTANT"
    assert release_context_for_user({
        "username": "ceo_boss", "role": "Ban lãnh đạo", "department": "Toàn công ty"
    }) == "INTERNAL_ASSISTANT"


def test_partner_uses_restrictive_share_context():
    assert release_context_for_user({
        "username": "partner_01", "role": "Đối tác", "department": None
    }) == "SHARE_SUMMARY"


def test_unknown_role_fails_closed_to_share_context():
    assert release_context_for_user({"role": "Unknown"}) == "SHARE_SUMMARY"
    assert release_context_for_user({}) == "SHARE_SUMMARY"


def test_user_supplied_context_cannot_override_role_policy():
    # Extra fields resembling client input are ignored; only authenticated role
    # attributes loaded from the signed token are considered.
    assert release_context_for_user({
        "role": "Đối tác", "release_context": "INTERNAL_ASSISTANT"
    }) == "SHARE_SUMMARY"
