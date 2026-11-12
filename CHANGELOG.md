# Changelog — review candidate

## 2026-10-29

- Fixed benchmark query loading to select `test_category`, matching `benchmark_v1/sql/00_benchmark_schema.sql`, the query-case generator, and export schema.
- Fixed the benchmark performance-result schema contract: added `query_case_id`, changed the uniqueness key to run/case/repetition/warm-up, added migration `03_performance_case_key_migration.sql` for older benchmark databases, and exported case keys alongside timing rows. The fresh benchmark schema now also enforces the same eight allowed `protection_profile` values as the existing migration and application schema.
- Hardened `--reset-scale`: refuses to reset a scale when case-level results or scale-level performance history exists; removes stale case definitions only when no related history exists.
- Standardized benchmark database connection overrides (`BENCHMARK_DB_HOST`, `BENCHMARK_DB_PORT`, `BENCHMARK_DB_USER`, `BENCHMARK_DB_PASSWORD`) while preserving a fixed `baomatdulieu_benchmark` safety boundary. Benchmark writers now verify `SELECT current_database()` instead of trusting client-supplied DSN metadata; the older hybrid diagnostic now also uses the isolated benchmark configuration.
- Updated ACL retrieval-matrix diagnostics to use the benchmark-specific connection configuration.
- Made benchmark export publication staged and rollback-aware: all files are generated in a temporary directory first, only the allow-listed export set is replaced, and existing outputs are restored if a replacement fails.
- Removed hard-coded `admin/admin` database defaults from policy/retrieval checks and migrated database check utilities and seed scripts to the shared environment-based configuration. Corrected the semantic-review diagnostic invocation path.
- Added offline schema-contract regression tests and a benchmark connection-override test.
- Added `.env.example` with placeholders and `README.md` with setup, test, isolated benchmark lifecycle, and reset safety instructions.
- Refreshed the answer-leakage and prompt-injection charts from explicitly identified saved artifacts; corrected the answer-leakage figure source to the October 26 case CSV and made the grouped attack chart readable.
- Excluded the original secret-bearing `.env`, Python bytecode/cache, stale `pytest-results.txt`, and superseded `.bak` file from the review bundle. Historical result artifacts are retained.

## Scope note

This is a reviewed candidate, not a production-ready or fully integration-verified release. PostgreSQL, Ollama, and the real `psycopg2` driver were unavailable in the review environment; see `TEST_RESULTS.md` for exact validation limits and local follow-up steps.
