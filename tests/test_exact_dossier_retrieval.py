"""Regression tests for ACL-safe exact dossier retrieval."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import vector_search as vs


def _embedding(_query):
    return [0.01] * 768


def test_extract_zero_padded_dossier_ids():
    assert vs._extract_record_ids("Tìm hồ sơ 00006 và hồ sơ 00038") == ["00006", "00038"]


def test_exact_search_is_scoped_to_allowed_ids_and_precedes_semantic(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [38])
    monkeypatch.setattr(vs, "create_query_embedding", _embedding)

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


def test_no_allowed_documents_returns_empty_without_embedding(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [])
    monkeypatch.setattr(vs, "create_query_embedding",
                        lambda *_: pytest.fail("embedding must not be requested"))
    assert vs.vector_search(conn, {}, "Hồ sơ 00038") == []


def test_top_k_is_bounded(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(vs, "get_allowed_document_ids", lambda *_: [1])
    with pytest.raises(ValueError, match="top_k"):
        vs.vector_search(conn, {}, "query", top_k=100)
