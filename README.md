# Data-Centric Security for RAG — Lab Project

This project demonstrates a controlled Retrieval-Augmented Generation (RAG) flow with ABAC/PDP/PEP checks before retrieval, output DLP, audit events, synthetic data, and security experiments. It is a lab, not a production security certification.

## 1. Prepare the environment

1. Install Python 3.11+; the current source was syntax-checked in Python 3.13. The ZIP also contained compiled cache files from another Python version; those caches are excluded from this package.
2. Install Docker Desktop and start Docker.
3. Install Ollama, then pull `qwen2.5:3b` and `nomic-embed-text` for the application and experiment scripts.
4. Copy `.env.example` to `.env`. Replace `POSTGRES_PASSWORD` and `SECRET_KEY` with local values. Do not commit or share `.env`.
5. In PowerShell, load the environment in the same terminal before running Python scripts:

   ```powershell
   .\scripts\load_lab_env.ps1
   ```

   The loader asks for `SEED_DEMO_PASSWORD` without echoing it. Python does not load `.env` automatically; Docker Compose reads it automatically for the compose service.
6. Install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-dev.txt
   ```

## 2. Start the application database

```powershell
docker compose up -d postgres
docker compose ps
```

The initialization SQL in `database/init/` is applied when the PostgreSQL data volume is initialized for the first time. If the volume already exists, the init scripts are not automatically replayed.

## 3. Run tests

```powershell
python -m pytest -q
```

Tests in `tests/test_retrieval_postgres_integration.py`, `tests/check_benchmark_schema.py`, and `tests/check_benchmark_users.py` require a running PostgreSQL instance with the expected schema. The benchmark scripts also require a separate database named `baomatdulieu_benchmark`; do not run benchmark DDL or generation scripts against the application database.

## 4. Benchmark v1 lifecycle

All benchmark v1 data generation, embedding, query-case creation, retrieval execution, and export are intended for the isolated `baomatdulieu_benchmark` database. The scripts refuse connections to an unexpected database name; the exporter is pinned to this database. Keep `BENCHMARK_DB_NAME` at its default.

1. Create an isolated database named `baomatdulieu_benchmark` on the PostgreSQL server. From PowerShell, after loading `.env` in the current shell, run:

   ```powershell
   docker compose exec postgres psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -c "CREATE DATABASE baomatdulieu_benchmark;"
   ```

   If the benchmark database already exists, do not recreate it; verify that it is the isolated benchmark database.
2. Apply `benchmark_v1/sql/00_benchmark_schema.sql` to that database only. Use `docker compose cp` and `psql -f` to preserve the SQL file's UTF-8 bytes because the schema contains Vietnamese labels:

   ```powershell
   docker compose cp .\benchmark_v1\sql\00_benchmark_schema.sql postgres:/tmp/00_benchmark_schema.sql
   docker compose exec postgres psql -U $env:POSTGRES_USER -d baomatdulieu_benchmark -f /tmp/00_benchmark_schema.sql
   ```
3. For an existing benchmark database from an older schema, apply migration `01_protection_profile_migration.sql` only if the protection-profile column is missing, and apply `03_performance_case_key_migration.sql` to repair the older per-case performance-result schema. Fresh databases created from the current `00_benchmark_schema.sql` do not need migration 03. Copy a migration into the container and execute it against the benchmark database only. For example, before running the `hybrid` variant, apply migration 02 (the base schema initially allows only `baseline` and `controlled`):

   ```powershell
   docker compose cp .\benchmark_v1\sql\02_add_hybrid_variant.sql postgres:/tmp/02_add_hybrid_variant.sql
   docker compose exec postgres psql -U $env:POSTGRES_USER -d baomatdulieu_benchmark -f /tmp/02_add_hybrid_variant.sql
   ```

   Do not apply benchmark migrations to the application database.
4. Generate all three required scales. The current benchmark runner validates all scales (1,000, 5,000 and 10,000 documents), even when a limited set of case keys is selected, so generating only one scale will not pass its precheck:

   ```powershell
   python benchmark_v1/generate_synthetic_dataset.py --scale all
   ```

   This generates 16,000 documents and 48,000 chunks. Synthetic vectors are normalized and marked `vector_kind='synthetic'`.
5. Generate query cases for all generated scales:

   ```powershell
   python benchmark_v1/generate_benchmark_query_cases.py --scale all
   ```
6. Replace synthetic vectors with `nomic-embed-text` embeddings. This calls the local Ollama embedding API for all chunks and may take substantial time. The command without `--apply` is dry-run only:

   ```powershell
   python experiments/diagnostics/reembed_benchmark_chunks.py
   python experiments/diagnostics/reembed_benchmark_chunks.py --apply
   ```

   Confirm the validator reports zero missing/synthetic embeddings and that every chunk is marked real before invoking the retrieval benchmark.
7. Validate without writing benchmark measurements:

   ```powershell
   python benchmark_v1/run_retrieval_benchmark.py --variant controlled --dry-run
   ```
8. Run the chosen variant after checking the environment and database state:

   ```powershell
   python benchmark_v1/run_retrieval_benchmark.py --variant baseline
   python benchmark_v1/run_retrieval_benchmark.py --variant controlled
   python benchmark_v1/run_retrieval_benchmark.py --variant hybrid
   ```

   The runner requires exactly 30 measured repetitions per case and five warm-ups. Repeated calls create new run records. Use `--variant hybrid` only after applying migration 02.
9. Export allow-listed metadata and metrics:

   ```powershell
   python benchmark_v1/export_benchmark_db.py
   ```

### Reset safety

`--reset-scale` is destructive for the selected synthetic corpus. If query cases for that scale have saved retrieval results, or if any saved performance rows exist for the scale (including rows from the older schema without a case key), the generator refuses the reset so ground truth and saved results are not silently detached. Use a fresh benchmark database for a new corpus version when preserving old results matters.

## 5. Security and privacy notes

- Do not include `.env` in a shared archive. This package intentionally includes only `.env.example`.
- The audit layer may persist `query_text`; never use real sensitive queries in this lab without changing the audit data-minimization policy.
- Exact-substring and structured-fact matching can miss paraphrase, semantic disclosure, and obfuscation. Zero observed matches in finite tests does not establish zero real-world leakage.
- The leadership override is an explicit business-policy exception in this project and is not strict Bell–LaPadula enforcement for every role.
- Keep `results/archive/` as historical evidence; do not mix results from different test cases/configurations without identifying their run IDs.

## Demo DLP release contexts

The local chat demo derives its Output DLP release context on the backend from the role loaded through the verified authentication token:
- `Nhân viên`, `Manager`, and `Ban lãnh đạo` use `INTERNAL_ASSISTANT` for internal Q&A.
- `Đối tác` and unknown roles use `SHARE_SUMMARY` (fail-closed default).
- The browser cannot choose or override the release context.
- ABAC/PDP remains the authorization boundary for document retrieval. `INTERNAL_ASSISTANT` does not expand the user's document permissions; it only changes the post-generation release policy for content that was already retrieved after ABAC filtering.
- `SHARE_SUMMARY` continues to redact confirmed protected matches and block uncertain configured summaries.

Run `python -m pytest -q` after pulling the demo branch. The regression tests cover role-to-context routing, technical filename redaction in share context, internal release, and no-result handling.


## 5. Local Demo database (separate from benchmark)

The interactive Demo uses a third database, baomatdulieu_demo. It is deliberately isolated from both the original application database and the benchmark database.

- baomatdulieu remains unchanged and is still used by existing application-policy tests/tools.
- baomatdulieu_benchmark remains the source of benchmark data and results.
- baomatdulieu_demo receives a copy of documents, chunks and real embeddings only. It has separate users, MFA secrets and audit rows.

After the benchmark corpus has 16,000 documents, 48,000 chunks and 48,000 real embeddings, run:

~~~powershell
. .\scripts\load_demo_env.ps1
python .\scripts\setup_demo_database.py
python .\scripts\seed_demo_users.py
~~~

The database creation script requires CREATEDB permission. It creates baomatdulieu_demo if absent, applies the application schema and audit migration, copies the corpus in batches, creates a cosine HNSW index and verifies row counts. It does not copy benchmark users/MFA, audit data, query cases or benchmark measurements. It never drops or truncates a database; an incomplete pre-existing Demo database is refused for manual inspection.

The user-provisioning script prompts for a shared Demo password, creates nv_dev, mgr_tech, mgr_sales, ceo_boss and partner_01, and prints fresh TOTP secrets/URIs once. Save each TOTP secret in an Authenticator app. It refuses to rotate existing credentials unless --rotate is explicitly requested.

Start the local UI with:

~~~powershell
.\scripts\start_demo.ps1
~~~

Open http://127.0.0.1:8765. The Demo server and interactive Controlled RAG are pinned to baomatdulieu_demo; POSTGRES_DB stays baomatdulieu and BENCHMARK_DB_NAME stays baomatdulieu_benchmark.

See README_DEMO.md for the complete Demo checklist, account roles, troubleshooting and test instructions.
