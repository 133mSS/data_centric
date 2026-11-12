import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from output_dlp_policy import decide_release


protected_matches = [
    {
        "type": "money",
        "canonical": "money:45:million:USD",
    }
]


def test_internal_assistant_allows_protected_matches():
    result = decide_release(
        "INTERNAL_ASSISTANT",
        protected_matches,
    )
    assert result["decision"] == "ALLOW"


def test_internal_assistant_allows_without_matches():
    result = decide_release(
        "INTERNAL_ASSISTANT",
        [],
    )
    assert result["decision"] == "ALLOW"


def test_share_summary_redacts_protected_matches():
    result = decide_release(
        "SHARE_SUMMARY",
        protected_matches,
    )
    assert result["decision"] == "REDACT"


def test_share_summary_allows_without_matches():
    result = decide_release(
        "SHARE_SUMMARY",
        [],
    )
    assert result["decision"] == "ALLOW"


def test_unknown_context_is_rejected():
    try:
        decide_release("UNKNOWN_CONTEXT", [])
        raise AssertionError(
            "Unsupported context must be rejected"
        )
    except ValueError:
        pass


def test_empty_context_is_rejected():
    try:
        decide_release("", [])
        raise AssertionError(
            "Empty context must be rejected"
        )
    except ValueError:
        pass


def test_none_context_is_rejected():
    try:
        decide_release(None, [])
        raise AssertionError(
            "None context must be rejected"
        )
    except (ValueError, TypeError):
        pass


if __name__ == "__main__":
    tests = [
        test_internal_assistant_allows_protected_matches,
        test_internal_assistant_allows_without_matches,
        test_share_summary_redacts_protected_matches,
        test_share_summary_allows_without_matches,
        test_unknown_context_is_rejected,
        test_empty_context_is_rejected,
        test_none_context_is_rejected,
    ]

    for test in tests:
        test()

    print("ALL OUTPUT DLP POLICY TESTS PASSED")
