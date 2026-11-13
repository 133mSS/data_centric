"""Read-only PostgreSQL integration tests for Hybrid/Vector ACL retrieval.

Run from the project root:
    python -m pytest tests/test_retrieval_postgres_integration.py -v

Uses the existing benchmark database only. The connection is put into
READ ONLY mode; these tests do not insert or update benchmark results.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from policy import check_access  # noqa: E402
from db_config import get_benchmark_db_config  # noqa: E402
from benchmark_v1.run_retrieval_benchmark import hybrid_search, vector_search  # noqa: E402


def _db_config():
    config = get_benchmark_db_config()
    config.update({
        "connect_timeout": 5,
        "application_name": "readonly_retrieval_acl_integration_tests",
    })
    return config

# IDs observed in the existing scale-10000 diagnostic cases.
DENIED_PARTNER_DOC_ID = 6002
ALLOWED_EMPLOYEE_DOC_ID = 6006
KNOWN_ALLOWED_DISTRACTOR_DOC_ID = 7573


@pytest.fixture()
def db_conn():
    try:
        config = _db_config()
    except RuntimeError as exc:
        pytest.skip(f"Benchmark PostgreSQL chưa được cấu hình trong môi trường test: {exc}")
    conn = psycopg2.connect(**config)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('transaction_read_only')")
            db_name, read_only = cur.fetchone()
        assert db_name == config["dbname"], (
            f"Connected to unexpected database {db_name!r}; expected {config['dbname']!r}"
        )
        assert read_only == "on", "PostgreSQL transaction is not read-only"
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _load_user(cur, username: str) -> dict:
    cur.execute(
        "SELECT id, username, role::text, department::text FROM users WHERE username = %s",
        (username,),
    )
    row = cur.fetchone()
    if row is None:
        pytest.fail(f"Required benchmark user not found: {username}")
    return {"id": row[0], "username": row[1], "role": row[2], "department": row[3]}


def _load_document(cur, document_id: int) -> dict:
    cur.execute(
        "SELECT id, title, classification::text, department::text "
        "FROM documents WHERE id = %s",
        (document_id,),
    )
    row = cur.fetchone()
    if row is None:
        pytest.fail(f"Required benchmark document not found: id={document_id}")
    return {"id": row[0], "title": row[1], "classification": row[2], "department": row[3]}


def _load_query_vector(cur, document_id: int) -> str:
    cur.execute(
        "SELECT embedding::text FROM chunks "
        "WHERE document_id = %s AND embedding IS NOT NULL "
        "ORDER BY id LIMIT 1",
        (document_id,),
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        pytest.fail(f"No non-null embedding found for document id={document_id}")
    return row[0]


def _assert_retrieval_rows_are_allowed(rows, allowed_ids: set[int]) -> None:
    assert all(row[1] in allowed_ids for row in rows), (
        f"Retrieval returned document IDs outside allowed set: "
        f"returned={[row[1] for row in rows]}, allowed={sorted(allowed_ids)}"
    )


def test_postgres_hybrid_exact_title_denied_partner_is_not_returned(db_conn):
    """A partner's exact-title query must not retrieve an Internal document."""
    with db_conn.cursor() as cur:
        user = _load_user(cur, "bench_partner")
        target = _load_document(cur, DENIED_PARTNER_DOC_ID)
        distractor = _load_document(cur, KNOWN_ALLOWED_DISTRACTOR_DOC_ID)
        assert check_access(user, target) == "DENY", (user, target)
        assert check_access(user, distractor) == "ALLOW", (user, distractor)

        query_vector = _load_query_vector(cur, target["id"])
        candidate_ids = [target["id"], distractor["id"]]
        allowed_ids = [distractor["id"]]
        suffix = target["title"][-5:]
        query = f"Tìm nội dung của {target['title']} hồ sơ {suffix}"

        rows = hybrid_search(
            cur, query, query_vector, top_k=3,
            candidate_ids=candidate_ids, allowed_ids=allowed_ids,
        )

    returned_ids = {row[1] for row in rows}
    assert target["id"] not in returned_ids
    _assert_retrieval_rows_are_allowed(rows, set(allowed_ids))


def test_postgres_hybrid_exact_title_allowed_employee_is_returned(db_conn):
    """An employee can retrieve an allowed Internal document in their department."""
    with db_conn.cursor() as cur:
        user = _load_user(cur, "bench_employee_tech")
        target = _load_document(cur, ALLOWED_EMPLOYEE_DOC_ID)
        distractor = _load_document(cur, KNOWN_ALLOWED_DISTRACTOR_DOC_ID)
        assert check_access(user, target) == "ALLOW", (user, target)
        assert check_access(user, distractor) == "ALLOW", (user, distractor)

        query_vector = _load_query_vector(cur, target["id"])
        candidate_ids = [target["id"], distractor["id"]]
        allowed_ids = list(candidate_ids)
        suffix = target["title"][-5:]
        query = f"Tìm nội dung của {target['title']} hồ sơ {suffix}"

        rows = hybrid_search(
            cur, query, query_vector, top_k=3,
            candidate_ids=candidate_ids, allowed_ids=allowed_ids,
        )

    returned_ids = {row[1] for row in rows}
    assert target["id"] in returned_ids, (
        f"Allowed exact-title target {target['id']} missing; returned={sorted(returned_ids)}"
    )
    _assert_retrieval_rows_are_allowed(rows, set(allowed_ids))


def test_postgres_vector_retrieval_excludes_denied_document_before_ranking(db_conn):
    """Vector SQL must return only allowed IDs when the target is denied."""
    with db_conn.cursor() as cur:
        user = _load_user(cur, "bench_partner")
        target = _load_document(cur, DENIED_PARTNER_DOC_ID)
        distractor = _load_document(cur, KNOWN_ALLOWED_DISTRACTOR_DOC_ID)
        assert check_access(user, target) == "DENY", (user, target)
        assert check_access(user, distractor) == "ALLOW", (user, distractor)

        query_vector = _load_query_vector(cur, target["id"])
        candidate_ids = [target["id"], distractor["id"]]
        allowed_ids = [distractor["id"]]
        rows = vector_search(
            cur, query_vector, top_k=3,
            candidate_ids=candidate_ids, allowed_ids=allowed_ids,
        )

    assert target["id"] not in {row[1] for row in rows}
    _assert_retrieval_rows_are_allowed(rows, set(allowed_ids))
