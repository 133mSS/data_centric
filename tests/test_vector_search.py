"""Unit tests for the controlled vector retrieval and shadow audit path."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

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
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [10])
    monkeypatch.setattr(vs, "create_query_embedding", lambda *_: make_embedding())
    monkeypatch.setattr(vs, "enforce_access", lambda *_: MagicMock(effect="ALLOW"))
    cursor.fetchall.side_effect = [
        [(99, 20, "Denied", "Nội bộ", "Kinh doanh")],
        [(1, 10, "Allowed doc", "Nội bộ", "Kỹ thuật", "content", 0.9, "GENERAL_INTERNAL")],
    ]
    allowed, denied = vs.vector_search_with_audit(conn, {"id": 1}, "test query", top_k=3)
    assert len(allowed) == 1
    assert denied == []
    semantic_sql = cursor.execute.call_args_list[-1].args[0]
    normalized_sql = " ".join(semantic_sql.split())
    assert "WHERE c.document_id = ANY(%s)" in normalized_sql
    assert normalized_sql.index("WHERE") < normalized_sql.index("ORDER BY") < normalized_sql.index("LIMIT")


def test_no_allowed_documents_skips_all_queries_and_embedding(monkeypatch):
    cursor = MagicMock()
    conn = make_connection(cursor)
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [])
    monkeypatch.setattr(vs, "create_query_embedding", lambda *_: pytest.fail("must not embed"))
    allowed, denied = vs.vector_search_with_audit(conn, {"id": 1}, "query", top_k=3)
    assert allowed == []
    assert denied == []
    cursor.execute.assert_not_called()


def test_invalid_embedding_dimension_raises_error(monkeypatch):
    monkeypatch.setattr(
        vs.requests, "post",
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
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [10])
    monkeypatch.setattr(vs, "create_query_embedding", lambda *_: make_embedding())
    monkeypatch.setattr(
        vs, "enforce_access",
        lambda user, doc: MagicMock(effect="DENY" if doc["id"] == 20 else "ALLOW"),
    )
    cursor.fetchall.side_effect = [
        [(99, 20, "Denied", "Mật", "Kinh doanh")],
        [(1, 10, "Allowed doc", "Nội bộ", "Kỹ thuật", "safe content", 0.9, "GENERAL_INTERNAL")],
    ]
    allowed, denied = vs.vector_search_with_audit(conn, {"id": 1}, "query", top_k=3)
    assert [row[0] for row in allowed] == [1]
    assert [item["chunk_id"] for item in denied] == [99]
    assert "content" not in denied[0]
    assert all(row[0] != 99 for row in allowed)


def test_failed_search_clears_stale_audit_metadata(monkeypatch):
    vs._audit_state.denied_shadow_chunks = [{"chunk_id": 99, "document_id": 20}]
    monkeypatch.setattr(
        vs, "vector_search_with_audit",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )
    with pytest.raises(RuntimeError, match="simulated failure"):
        vs.vector_search(None, {"id": 1}, "query")
    assert vs.get_last_denied_shadow_chunks() == []


def test_extract_zero_padded_dossier_ids():
    assert vs._extract_record_ids("Tìm hồ sơ 00006 và hồ sơ 00038") == ["00006", "00038"]


def test_exact_search_is_scoped_to_allowed_ids_and_precedes_semantic(monkeypatch):
    cursor = MagicMock()
    conn = make_connection(cursor)
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [38])
    monkeypatch.setattr(vs, "create_query_embedding", lambda *_: make_embedding())
    exact = (10, 38, "Core Platform — hồ sơ 00038", "Nội bộ", "Kỹ thuật",
             "Nội dung được phép", None, "GENERAL_INTERNAL")
    semantic = (11, 38, "Core Platform — hồ sơ 00038", "Nội bộ", "Kỹ thuật",
                "Đoạn semantic khác", 0.8, "GENERAL_INTERNAL")
    cursor.fetchall.side_effect = [[exact], [], [semantic]]
    rows = vs.vector_search(conn, {"role": "Nhân viên", "department": "Kỹ thuật"},
                            "Tìm thông tin hồ sơ 00038", top_k=3)
    assert rows[0] == exact
    assert all(row[1] == 38 for row in rows)
    exact_sql = cursor.execute.call_args_list[0].args[0]
    assert "d.id = ANY(%s)" in exact_sql
    assert cursor.execute.call_args_list[0].args[1][0] == [38]


def test_top_k_is_bounded(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [1])
    with pytest.raises(ValueError, match="top_k"):
        vs.vector_search(conn, {}, "query", top_k=100)
