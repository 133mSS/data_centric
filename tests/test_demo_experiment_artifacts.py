from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import demo_server


def test_experiment_summary_loads_timestamped_wp6_artifact(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    artifact = results / "wp6_retrieval_matrix_seed4206_20261113.csv"
    artifact.write_text(
        "pass,actual\nTrue,ALLOW\nTrue,DENY\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_server, "ROOT", tmp_path)

    summary = demo_server._experiment_summary()

    assert summary["wp6"] == {
        "checks": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 100.0,
        "allow": 1,
        "deny": 1,
    }
