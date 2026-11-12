# Test Results — review candidate

Date: 2026-10-29

## Summary

Static checks and an offline unit-test subset pass. The real database-backed and Ollama-backed benchmark lifecycle could not be run in this environment, so the bundle is intentionally identified as a review candidate rather than a fully verified final release.

## Checks executed

| Check | Result | Details |
|---|---|---|
| ZIP integrity | PASS | The uploaded ZIP was readable; `zipfile.testzip()` returned no corrupt entry. |
| Inventory | PASS | The input archive had 338 entries: 306 files and 32 directories, around 2.03 MB uncompressed. |
| Python syntax compilation | PASS | `python -m compileall -q app benchmark_v1 experiments scripts tests tools`. |
| JSON artifacts | PASS | All 20 JSON files in the source inventory parsed successfully. |
| CSV structure | PASS | All 28 CSV files parsed and rows had consistent field counts. |
| Docker Compose YAML parse | PASS | YAML parsed and declared the PostgreSQL service. This is not a Docker startup test. |
| Artifact consistency | PASS, limited | The October 26 answer-leakage summary and case CSV agreed on the reported 40-case metrics. This checks saved artifacts, not a newly executed experiment. |
| Chart regeneration | PASS | `python tools/make_report_figures.py` completed. Answer leakage now uses `results/answer_leakage_cases_20261026T142905Z.csv`; prompt injection figures are tied to run `20261018T072609Z`. |
| Offline schema-contract/export safety tests | PASS | Regression tests cover schema/runner `test_category` agreement, per-case performance-result schema compatibility, allowed protection-profile labels, reset protection, export DB isolation, and actual benchmark database identity checks, including clearing the read-only guard transaction before the connection is reused. |
| Unit-test subset | PASS with limitation | 498 tests passed when a temporary, out-of-project import stub for `psycopg2` was used and three database-oriented test modules were excluded: `tests/test_policy.py`, `tests/test_retrieval.py`, and `tests/test_retrieval_postgres_integration.py`. The stub only permits test modules that mock DB calls to import; it raises if a real connection is attempted. This is not equivalent to running with the actual driver. |
| Full pytest collection | BLOCKED | Direct `python -m pytest -q --maxfail=10` stopped during collection with five `ModuleNotFoundError: psycopg2` errors. |
| Dependency installation | BLOCKED | `pip install -r requirements-dev.txt` could not reach package indexes because network/DNS access was unavailable. `psycopg2`, `bcrypt`, and `pyotp` were not installed. |
| PostgreSQL integration | NOT RUN | Docker, `docker compose`, and `psql` were not available in this environment. |
| Ollama / actual embeddings | NOT RUN | No local Ollama service/models were available to execute the embedding lifecycle. |
| Full benchmark v1 | NOT RUN | No results are claimed for a new benchmark run. Existing CSV/JSON are historical artifacts, not proof that the modified benchmark code ran. |
| Report PDF layout | Reviewed with issue | Original PDF rendered to 31 pages and its contact sheet was reviewed. Pages 1–30 use A4-sized pages; page 31 uses Letter size. No report source DOCX was provided, so the source PDF was not silently rebuilt into an editable report. |

## Important findings addressed in source

1. `benchmark_v1/run_retrieval_benchmark.py` selected a nonexistent `category` column although the schema defines `test_category`; fixed to match the schema and added a regression test.
2. The runner inserted per-case timing rows into `benchmark_performance_results`, but its previous schema lacked `query_case_id` and had a uniqueness key that could not support multiple cases per run/repetition. The schema, old-database migration, exporter, and static contract test now agree on per-case timing rows.
3. `--reset-scale` could have left query-case ground truth with stale document IDs. It now deletes query cases only when no linked case-result history remains, and refuses the reset if either linked retrieval results or scale-level performance history exists.
4. Benchmark credentials and target database handling were aligned around the isolated `baomatdulieu_benchmark` database; the exporter is pinned to that database.
5. Removed hard-coded local `admin/admin` credentials from database-backed test/check scripts and moved them to the shared environment-based configuration. These DB tests still need a live local database and were not run here.
6. Figure generation was pointed to the latest saved answer-leakage case CSV rather than an older archived file, and the grouped prompt-injection chart labels were improved.

## Local Windows verification still required

Run in PowerShell from the project root, after installing Docker Desktop and Ollama and pulling the project's `qwen2.5:3b` and `nomic-embed-text` models:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env locally; never send or commit it.
.\scripts\load_lab_env.ps1
python -m pytest -q
docker compose up -d postgres
docker compose ps
ollama list
```

Then follow the isolated benchmark setup and full lifecycle in `README.md`. The runner currently validates all three scales, so generate the corpus and test cases with `--scale all`. Before testing `hybrid`, apply `benchmark_v1/sql/02_add_hybrid_variant.sql` to the benchmark database. Do not paste secrets or the contents of `.env` into logs or messages.
