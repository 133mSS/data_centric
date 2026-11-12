import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "export" / "export_results.py"
SPEC = importlib.util.spec_from_file_location("wp8_export_results", SCRIPT)
wp8 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(wp8)


def test_wilson_interval_for_zero_successes_is_not_zero_width():
    low, high = wp8.wilson_interval(0, 20)
    assert low == 0.0
    assert 0 < high < 0.2


def test_wilson_interval_for_all_successes_is_bounded():
    low, high = wp8.wilson_interval(20, 20)
    assert 0.8 < low < 1.0
    assert high == 1.0


def test_wilson_interval_empty_sample_is_undefined():
    assert wp8.wilson_interval(0, 0) == (None, None)


def test_wp7_collector_uses_summary_files_only():
    assert callable(wp8.collect_wp7)
    assert callable(wp8.collect_answer_leakage)


def test_limitations_omit_stale_wp7_warning_when_three_runs_exist():
    limitations = wp8.build_limitations(3)
    assert not any("WP7 has" in item for item in limitations)
    assert any("4-way ablation was measured across all four configurations" in item for item in limitations)


def test_limitations_report_wp7_repeat_gap_when_target_not_met():
    assert any("WP7 has 2 distinct run(s)" in item for item in wp8.build_limitations(2))
    assert any("WP7 has 6 distinct run(s)" in item for item in wp8.build_limitations(6))
