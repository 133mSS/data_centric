"""Independent, hand-written ABAC ground truth for WP6 (G8)."""
import itertools

ROLES = {
    "Đối tác": (0, None),
    "Nhân viên_Kỹ thuật": (1, "Kỹ thuật"),
    "Nhân viên_Kinh doanh": (1, "Kinh doanh"),
    "Manager_Kỹ thuật": (2, "Kỹ thuật"),
    "Manager_Kinh doanh": (2, "Kinh doanh"),
    "Ban lãnh đạo": (3, "Toàn công ty"),
}
LEVELS = {"Công khai": 0, "Nội bộ": 1, "Mật": 2, "Tối mật": 3}


def expected_from_written_truth_table(user_key, classification, document_department):
    """Expected policy written independently from app.pdp/app.policy."""
    clearance, user_department = ROLES[user_key]
    if LEVELS[classification] > clearance:
        return False
    if document_department is None or document_department == "Toàn công ty":
        return True
    if user_department == "Toàn công ty":
        return True
    return user_department == document_department


def test_ground_truth_has_all_user_classification_department_combinations():
    classifications = ("Công khai", "Nội bộ", "Mật", "Tối mật")
    departments = (None, "Toàn công ty", "Kỹ thuật", "Kinh doanh")
    rows = [
        (user, classification, department,
         expected_from_written_truth_table(user, classification, department))
        for user, classification, department in itertools.product(
            ROLES, classifications, departments
        )
    ]
    assert len(rows) == 6 * 4 * 4
    assert any(not expected for _, _, _, expected in rows)
    assert any(expected for _, _, _, expected in rows)


def test_internal_company_wide_is_allowed_to_employee_and_manager():
    for user in ("Nhân viên_Kỹ thuật", "Manager_Kỹ thuật",
                 "Nhân viên_Kinh doanh", "Manager_Kinh doanh"):
        assert expected_from_written_truth_table(user, "Nội bộ", "Toàn công ty")


def test_unknown_values_are_not_silently_allowed_by_ground_truth():
    # Unknown labels/roles are intentionally outside the positive table and
    # must be handled fail-closed by the implementation tests.
    assert expected_from_written_truth_table("Đối tác", "Tối mật", "Kỹ thuật") is False
