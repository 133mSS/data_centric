import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "ablation" / "run_wp8_ablation.py"
SPEC = importlib.util.spec_from_file_location("wp8_ablation_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


def test_four_ablation_arms_are_isolated_and_complete():
    assert runner.CONFIGS == {
        "Baseline": {"abac": False, "dlp": False},
        "ABAC only": {"abac": True, "dlp": False},
        "ABAC+DLP": {"abac": True, "dlp": True},
        "DLP only (ABAC off)": {"abac": False, "dlp": True},
    }


def test_runner_has_denied_allowed_and_harmless_controls():
    assert any(c["expected_access"] == "DENY" for c in runner.CASES)
    assert any(c["expected_access"] == "ALLOW" for c in runner.CASES)
    assert any(c["harmless"] for c in runner.CASES)
    assert len({c["case_id"] for c in runner.CASES}) == len(runner.CASES)


def test_aggregate_reports_all_four_configurations():
    rows = []
    for name in runner.CONFIGS:
        rows.append({
            "configuration": name, "case_id": "T01", "target_retrieval_leak": True,
            "leaked_fact_count": 2, "dlp_decision": "NOT_APPLIED", "over_redaction": False,
            "answerable": True, "latency_ms": 100.0, "harmless": False,
        })
    result = runner._aggregate(rows, 3)
    assert [row["configuration"] for row in result] == list(runner.CONFIGS)
    assert all(row["cases"] == 1 for row in result)
    assert all(row["target_retrieval_leaks"] == 1 for row in result)


def test_exporter_keeps_ablation_unmeasured_until_real_summary_exists(tmp_path, monkeypatch):
    export_script = ROOT / "experiments" / "export" / "export_results.py"
    spec = importlib.util.spec_from_file_location("wp8_export_for_ablation_test", export_script)
    exporter = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(exporter)
    monkeypatch.setattr(exporter, "RESULTS", tmp_path)
    rows, status = exporter.collect_ablation_final()
    assert rows == []
    assert status["status"] == "NOT_MEASURED"
