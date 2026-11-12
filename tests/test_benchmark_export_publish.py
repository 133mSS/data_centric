"""Local filesystem tests for safe publication of benchmark export files."""
from pathlib import Path
import os
from unittest.mock import patch

from benchmark_v1.export_benchmark_db import publish_export_set


def test_publish_export_set_replaces_only_named_files(tmp_path):
    out = tmp_path / "out"
    stage = tmp_path / "stage"
    out.mkdir()
    stage.mkdir()
    (out / "metrics.csv").write_text("old-metrics", encoding="utf-8")
    (out / "unrelated.txt").write_text("keep", encoding="utf-8")
    (stage / "metrics.csv").write_text("new-metrics", encoding="utf-8")
    (stage / "manifest.json").write_text("new-manifest", encoding="utf-8")

    publish_export_set(stage, out, ["metrics.csv", "manifest.json"])

    assert (out / "metrics.csv").read_text(encoding="utf-8") == "new-metrics"
    assert (out / "manifest.json").read_text(encoding="utf-8") == "new-manifest"
    assert (out / "unrelated.txt").read_text(encoding="utf-8") == "keep"


def test_publish_export_set_rolls_back_existing_outputs_if_replace_fails(tmp_path):
    out = tmp_path / "out"
    stage = tmp_path / "stage"
    out.mkdir()
    stage.mkdir()
    (out / "a.csv").write_text("old-a", encoding="utf-8")
    (out / "b.csv").write_text("old-b", encoding="utf-8")
    (stage / "a.csv").write_text("new-a", encoding="utf-8")
    (stage / "b.csv").write_text("new-b", encoding="utf-8")

    original_replace = os.replace
    calls = {"count": 0}
    def fail_second_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated replacement failure")
        return original_replace(src, dst)

    with patch("benchmark_v1.export_benchmark_db.os.replace", side_effect=fail_second_replace):
        try:
            publish_export_set(stage, out, ["a.csv", "b.csv"])
        except OSError as exc:
            assert "simulated" in str(exc)
        else:
            raise AssertionError("expected publication failure")

    assert (out / "a.csv").read_text(encoding="utf-8") == "old-a"
    assert (out / "b.csv").read_text(encoding="utf-8") == "old-b"
