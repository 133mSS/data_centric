"""Static contract checks for the offline benchmark schema and query runner."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_case_category_column_matches_schema_and_generator():
    schema = (ROOT / "benchmark_v1/sql/00_benchmark_schema.sql").read_text(encoding="utf-8")
    generator = (ROOT / "benchmark_v1/generate_benchmark_query_cases.py").read_text(encoding="utf-8")
    runner = (ROOT / "benchmark_v1/run_retrieval_benchmark.py").read_text(encoding="utf-8")
    exporter = (ROOT / "benchmark_v1/export_benchmark_db.py").read_text(encoding="utf-8")

    table_match = re.search(
        r"CREATE TABLE benchmark_query_cases\s*\((.*?)\n\);",
        schema,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table_match, "benchmark_query_cases table definition is missing"
    table_body = table_match.group(1)
    assert re.search(r"^\s*test_category\s+TEXT\s+NOT NULL", table_body, re.MULTILINE)
    assert "test_category" in generator
    assert "test_category" in exporter

    load_cases_match = re.search(
        r"def load_cases\(cur\):(?P<body>.*?)(?:\n\ndef |\n\nclass )",
        runner,
        flags=re.DOTALL,
    )
    assert load_cases_match, "load_cases() implementation is missing"
    assert re.search(r"\btest_category\b", load_cases_match.group("body"))
    assert not re.search(r"\bcategory\s*,\s*expected_answerable", load_cases_match.group("body")), (
        "Runner must select the schema column test_category, not a nonexistent category column"
    )


def test_reset_scale_guards_historical_ground_truth():
    source = (ROOT / "benchmark_v1/generate_synthetic_dataset.py").read_text(encoding="utf-8")
    body_match = re.search(
        r"def reset_scale\(cur, scale: int\):(?P<body>.*?)(?:\n\ndef |\n\nif __name__)",
        source,
        flags=re.DOTALL,
    )
    assert body_match, "reset_scale() implementation is missing"
    body = body_match.group("body")
    assert "benchmark_query_cases" in body
    assert "benchmark_case_results" in body
    assert "benchmark_performance_results" in body
    assert "historical_performance_results" in body
    assert "Không thể reset" in body
    assert "DELETE FROM benchmark_query_cases" in body


def test_benchmark_exporter_is_pinned_to_isolated_database():
    source = (ROOT / "benchmark_v1/export_benchmark_db.py").read_text(encoding="utf-8")
    assert 'EXPECTED_DATABASE = "baomatdulieu_benchmark"' in source
    assert "exporting other databases is disabled" in source


def test_performance_result_schema_matches_runner_and_exporter():
    schema = (ROOT / "benchmark_v1/sql/00_benchmark_schema.sql").read_text(encoding="utf-8")
    runner = (ROOT / "benchmark_v1/run_retrieval_benchmark.py").read_text(encoding="utf-8")
    exporter = (ROOT / "benchmark_v1/export_benchmark_db.py").read_text(encoding="utf-8")
    migration = (ROOT / "benchmark_v1/sql/03_performance_case_key_migration.sql").read_text(encoding="utf-8")

    table_match = re.search(
        r"CREATE TABLE benchmark_performance_results\s*\((.*?)\n\);",
        schema,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert table_match, "benchmark_performance_results table definition is missing"
    table_body = table_match.group(1)
    assert re.search(r"^\s*query_case_id\s+BIGINT NOT NULL", table_body, re.MULTILINE)
    assert re.search(
        r"UNIQUE\s*\(run_id,\s*query_case_id,\s*repetition_no,\s*warmup\)",
        table_body,
        re.IGNORECASE,
    )
    assert "query_case_id, repetition_no, warmup" in runner
    assert "p.query_case_id, q.case_key" in exporter
    assert "LEFT JOIN benchmark_query_cases q ON q.id = p.query_case_id" in exporter
    assert "ADD COLUMN IF NOT EXISTS query_case_id" in migration
    assert "benchmark_performance_results_run_id_repetition_no_warmup_key" in migration


def test_fresh_benchmark_schema_enforces_known_protection_profiles():
    schema = (ROOT / "benchmark_v1/sql/00_benchmark_schema.sql").read_text(encoding="utf-8")
    migration = (ROOT / "benchmark_v1/sql/01_protection_profile_migration.sql").read_text(encoding="utf-8")
    profiles = (
        "PUBLIC", "GENERAL_INTERNAL", "PERFORMANCE_SENSITIVE", "CORPORATE_SECRET",
        "COMMERCIAL_SECRET", "TECHNICAL_SENSITIVE", "MAINTENANCE_NOTICE", "PUBLIC_RECRUITMENT",
    )
    assert "CONSTRAINT doc_protection_profile_valid CHECK" in schema
    for profile in profiles:
        assert profile in schema
        assert profile in migration


def test_benchmark_writers_use_isolated_config_and_verify_actual_database():
    runner = (ROOT / "benchmark_v1/run_retrieval_benchmark.py").read_text(encoding="utf-8")
    synthetic = (ROOT / "benchmark_v1/generate_synthetic_dataset.py").read_text(encoding="utf-8")
    cases = (ROOT / "benchmark_v1/generate_benchmark_query_cases.py").read_text(encoding="utf-8")
    reembed = (ROOT / "experiments/diagnostics/reembed_benchmark_chunks.py").read_text(encoding="utf-8")
    hybrid = (ROOT / "experiments/diagnostics/run_retrieval_benchmark_hybrid_diagnostic.py").read_text(encoding="utf-8")

    assert "get_benchmark_db_config()" in runner
    assert "get_benchmark_db_config()" in hybrid
    assert "get_db_config()" not in hybrid
    for source in (synthetic, cases, reembed, runner, hybrid):
        assert "SELECT current_database()" in source
        assert "get_dsn_parameters()" not in source
        connect_body = source[source.index("def connect():"):]
        connect_body = connect_body.split("\ndef ", 1)[0]
        assert "conn.rollback()" in connect_body
