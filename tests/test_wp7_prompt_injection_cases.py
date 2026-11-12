"""Offline structural tests for the WP7 prompt-injection case matrix."""
import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "prompt_injection" / "prompt_injection_test.py"
NS = runpy.run_path(str(SCRIPT))
CASES = NS["CASES"]


def test_wp7_has_at_least_20_unique_cases():
    ids = [case["id"] for case in CASES]
    assert len(CASES) >= 20
    assert len(ids) == len(set(ids))


def test_wp7_has_all_required_attack_groups():
    groups = {case["group"] for case in CASES}
    assert groups == {
        "direct_override",
        "identity_impersonation",
        "multilingual",
        "obfuscation",
        "indirect_injection",
        "forged_metadata",
        "dlp_attack",
    }


def test_each_case_has_required_fields_and_valid_targets():
    for case in CASES:
        assert case["id"] and case["group"] and case["user"] and case["query"]
        assert isinstance(case["targets"], list)
        assert isinstance(case["facts"], tuple)
        assert all(isinstance(fact, str) and fact for fact in case["facts"])


def test_indirect_injection_cases_are_explicitly_marked():
    indirect = [case for case in CASES if case["group"] == "indirect_injection"]
    assert len(indirect) >= 2
    assert all(case.get("indirect") is True for case in indirect)


def test_dlp_cases_exercise_answer_detection_without_target_retrieval():
    dlp = [case for case in CASES if case["group"] == "dlp_attack"]
    assert len(dlp) >= 2
    assert all(not case["targets"] for case in dlp)
    assert all(case["facts"] for case in dlp)
