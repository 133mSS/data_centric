"""Edge-case tests for app/redaction.py.

Run from the project root:
    python -m pytest -v tests/test_redaction_edge_cases.py
"""

import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from redaction import apply_redaction, find_exact_matches, merge_matches


def test_exact_match_is_case_insensitive():
    answer = "Công ty xyz và công ty XYZ."
    facts = [{"type": "named_entity", "value": "XYZ"}]

    matches = find_exact_matches(answer, facts)

    assert len(matches) == 2
    assert [match["matched_raw"] for match in matches] == ["xyz", "XYZ"]


def test_exact_match_does_not_match_inside_larger_identifier():
    answer = "XYZ hoạt động cùng XYZABC và ABCXYZ."
    facts = [{"type": "named_entity", "value": "XYZ"}]

    matches = find_exact_matches(answer, facts)

    assert len(matches) == 1
    assert matches[0]["matched_raw"] == "XYZ"
    assert answer[matches[0]["start"]:matches[0]["end"]] == "XYZ"


def test_identical_spans_are_merged_once_and_keep_both_types():
    structured_matches = [{"type": "money", "start": 10, "end": 20}]
    exact_matches = [{"type": "named_entity", "start": 10, "end": 20}]

    merged = merge_matches(structured_matches, exact_matches)

    assert len(merged) == 1
    assert merged[0]["start"] == 10
    assert merged[0]["end"] == 20
    assert set(merged[0]["types"]) == {"money", "named_entity"}


def test_overlapping_spans_are_merged_and_redacted_once():
    answer = "abcdefghij"
    matches = [
        {"type": "fact_a", "start": 1, "end": 5},
        {"type": "fact_b", "start": 4, "end": 8},
    ]

    merged = merge_matches(matches, [])

    assert len(merged) == 1
    assert merged[0]["start"] == 1
    assert merged[0]["end"] == 8
    assert apply_redaction(answer, merged) == "a[REDACTED]ij"


def test_non_overlapping_spans_remain_separate():
    matches = [
        {"type": "fact_a", "start": 0, "end": 2},
        {"type": "fact_b", "start": 5, "end": 7},
    ]

    merged = merge_matches(matches, [])

    assert len(merged) == 2
    assert [(match["start"], match["end"]) for match in merged] == [
        (0, 2),
        (5, 7),
    ]


def test_redaction_handles_multiple_non_overlapping_spans():
    answer = "SECRET and TOKEN"
    matches = [
        {"type": "secret", "start": 0, "end": 6},
        {"type": "token", "start": 11, "end": 16},
    ]

    assert apply_redaction(answer, matches) == "[REDACTED] and [REDACTED]"


def test_overlap_components_preserve_original_span_coordinates():
    """Audit metadata should retain each match's original start/end coordinates."""
    matches = [
        {"type": "fact_a", "start": 1, "end": 5},
        {"type": "fact_b", "start": 4, "end": 8},
    ]

    merged = merge_matches(matches, [])

    assert len(merged) == 1
    assert merged[0]["start"] == 1
    assert merged[0]["end"] == 8
    assert [
        (component["start"], component["end"])
        for component in merged[0]["components"]
    ] == [(1, 5), (4, 8)]
