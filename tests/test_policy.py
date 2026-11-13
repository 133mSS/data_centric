
import sys
from pathlib import Path

import psycopg2
import pytest

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from policy import check_access
from db_config import get_db_config


@pytest.fixture(scope="module")
def db_conn():
    """Kết nối PostgreSQL app DB; skip rõ ràng nếu credentials chưa được nạp."""
    try:
        config = get_db_config()
    except RuntimeError as exc:
        pytest.skip(f"PostgreSQL app DB chưa được cấu hình trong môi trường test: {exc}")
    conn = psycopg2.connect(**config)
    try:
        yield conn
    finally:
        conn.close()


def get_user(conn, username):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT username, role, department
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()

    if row is None:
        raise ValueError(f"User not found: {username}")

    return {
        "username": row[0],
        "role": row[1],
        "department": row[2],
    }


def get_document(conn, document_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, classification, department
            FROM documents
            WHERE id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise ValueError(f"Document not found: {document_id}")

    return {
        "id": row[0],
        "title": row[1],
        "classification": row[2],
        "department": row[3],
    }


@pytest.mark.parametrize(
    "username, document_id, expected",
    [
        ("nv_dev", 6, "ALLOW"),
        ("mgr_tech", 3, "ALLOW"),
        ("mgr_sales", 3, "DENY"),
        ("mgr_sales", 5, "ALLOW"),
        ("mgr_tech", 5, "DENY"),
        ("nv_dev", 4, "DENY"),
        ("ceo_boss", 4, "ALLOW"),
        ("partner_01", 2, "DENY"),
    ],
    ids=[
        "employee-allowed",
        "tech-manager-allowed",
        "sales-manager-denied",
        "sales-manager-allowed",
        "tech-manager-denied",
        "employee-denied",
        "leadership-allowed",
        "partner-denied",
    ],
)
def test_check_access(db_conn, username, document_id, expected):
    user = get_user(db_conn, username)
    document = get_document(db_conn, document_id)

    actual = check_access(user, document)

    assert actual == expected, (
        f"user={username}, document_id={document_id}: "
        f"expected={expected}, actual={actual}"
    )
