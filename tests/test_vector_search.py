"""Unit tests for the controlled vector retrieval and shadow audit path."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import vector_search as vs  # noqa: E402


def make_connection(cursor):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def make_embedding():
    return [0.1] * 768


def test_controlled_query_filters_acl_before_limit(monkeypatch):
    cursor = MagicMock()
    conn = make_connection(cursor)

    monkeypatch.setattr(
        vs, "get_allowed_document_ids", lambda conn, user: [10]
    )
    monkeypatch.setattr(
        vs, "create_query_embedding", lambda query: make_embedding()
    )
    monkeypatch.setattr(
        vs,
        "enforce_access",
        lambda user, doc: MagicMock(effect="ALLOW"),
    )

    cursor.fetchall.side_effect = [
        [],  # Shadow baseline
        [(1, 10, "Allowed doc", "INTERNAL", "IT", "content", 0.9)],
    ]

    allowed, denied = vs.vector_search_with_audit(
        conn, {"id": 1}, "test query", top_k=3
    )

    assert len(allowed) == 1
    assert denied == []

    controlled_sql = cursor.execute.call_args_list[1].args[0]
    normalized_sql = " ".join(controlled_sql.split())

    assert "WHERE c.document_id = ANY(%s)" in normalized_sql
    assert normalized_sql.index("WHERE") < normalized_sql.index("ORDER BY")
    assert normalized_sql.index("ORDER BY") < normalized_sql.index("LIMIT")


def test_no_allowed_documents_skips_controlled_query(monkeypatch):
    cursor = MagicMock()
    conn = make_connection(cursor)

    monkeypatch.setattr(
        vs, "get_allowed_document_ids", lambda conn, user: []
    )
    monkeypatch.setattr(
        vs, "create_query_embedding", lambda query: make_embedding()
    )
    monkeypatch.setattr(
        vs,
        "enforce_access",
        lambda user, doc: MagicMock(effect="DENY"),
    )

    cursor.fetchall.return_value = [(99, 20, "CONFIDENTIAL", "Finance")]

    allowed, denied = vs.vector_search_with_audit(
        conn, {"id": 1}, "test query", top_k=3
    )

    assert allowed == []
    assert len(denied) == 1
    assert denied[0]["chunk_id"] == 99
    assert "content" not in denied[0]
    assert cursor.execute.call_count == 1


def test_invalid_embedding_dimension_raises_error(monkeypatch):
    monkeypatch.setattr(
        vs.requests,
        "post",
        lambda *args, **kwargs: MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"embedding": [0.1] * 10},
        ),
    )

    with pytest.raises(ValueError, match="Invalid embedding dimension"):
        vs.create_query_embedding("test query")


def test_denied_shadow_chunk_is_audit_only(monkeypatch):
    cursor = MagicMock()
    conn = make_connection(cursor)

    monkeypatch.setattr(
        vs, "get_allowed_document_ids", lambda conn, user: [10]
    )
    monkeypatch.setattr(
        vs, "create_query_embedding", lambda query: make_embedding()
    )
    monkeypatch.setattr(
        vs,
        "enforce_access",
        lambda user, doc: MagicMock(
            effect="DENY" if doc["id"] == 20 else "ALLOW"
        ),
    )

    # Baseline contains a denied chunk; controlled retrieval returns only ALLOW.
    cursor.fetchall.side_effect = [
        [(99, 20, "CONFIDENTIAL", "Finance")],
        [(1, 10, "Allowed doc", "INTERNAL", "IT", "safe content", 0.9)],
    ]

    allowed, denied = vs.vector_search_with_audit(
        conn, {"id": 1}, "test query", top_k=3
    )

    assert [row[0] for row in allowed] == [1]
    assert [item["chunk_id"] for item in denied] == [99]
    assert "content" not in denied[0]
    assert all(row[0] != 99 for row in allowed)


def test_failed_search_clears_stale_audit_metadata(monkeypatch):
    vs._audit_state.denied_shadow_chunks = [
        {"chunk_id": 99, "document_id": 20}
    ]

    def fail_search(*args, **kwargs):
        raise RuntimeError("simulated retrieval failure")

    monkeypatch.setattr(vs, "vector_search_with_audit", fail_search)

    with pytest.raises(RuntimeError, match="simulated retrieval failure"):
        vs.vector_search(None, {"id": 1}, "test query")

    assert vs.get_last_denied_shadow_chunks() == []
