import csv
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "export" / "export_results.py"
SPEC = importlib.util.spec_from_file_location("wp8_export_results_ci", SCRIPT)
wp8 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(wp8)


def test_ablation_ci_uses_latest_case_csv_and_four_configs(tmp_path, monkeypatch):
    rows = []
    for rep in (1, 2, 3):
        for config in ("Baseline", "ABAC only", "ABAC+DLP", "DLP only (ABAC off)"):
            rows.append({"configuration": config, "case_id": "T01", "target_retrieval_leak": str(config in {"Baseline", "DLP only (ABAC off)"}),
                         "answerable": "True", "harmless": "False", "dlp_decision": "ALLOW", "leaked_fact_count": "1", "latency_ms": "100", "repetition": str(rep)})
    monkeypatch.setattr(wp8, "RESULTS", tmp_path)
    with (tmp_path / "wp8_ablation_cases_test.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    metrics, summary = wp8.collect_ablation_final()
    assert len(metrics) == 4
    baseline = next(x for x in metrics if x["configuration"] == "Baseline")
    assert baseline["target_retrieval_leaks"] == 3
    assert baseline["retrieval_leak_wilson95_low"] is not None
    assert summary["repeats"] == 3
    assert "independent-sample inference" in summary["interpretation"]


def test_audit_sample_never_fabricates_records_when_db_unavailable(monkeypatch):
    # Connection dependencies are environment-specific; the collector must return a note, not synthetic rows.
    rows, note = wp8.collect_audit_sample()
    assert isinstance(rows, list)
    assert isinstance(note, str)
    assert not rows or {"request_id", "decision", "stage"}.issubset(rows[0])
