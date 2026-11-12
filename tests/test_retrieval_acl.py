"""Unit tests for ACL filtering in Hybrid exact-title and vector retrieval.
"""
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from benchmark_v1 import run_retrieval_benchmark as hybrid


class FakeCursor:
    def __init__(self, rows=(), result_sets=None):
        self.rows = list(rows)
        self.result_sets = [list(items) for items in result_sets] if result_sets is not None else None
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        if self.result_sets is not None:
            return self.result_sets.pop(0) if self.result_sets else []
        return self.rows


def row(chunk_id, document_id, title="Test hồ sơ 00002", content="safe content"):
    # Matches the SELECT tuple shape returned by both retrieval branches.
    return (chunk_id, document_id, title, "Công khai", "Kinh doanh", content, 0.9)


def test_hybrid_exact_title_excludes_denied_document_before_query(monkeypatch):
    """A matching title must not bypass ACL when its document is denied."""
    denied_doc_id = 200
    allowed_doc_id = 100
    # The exact-title query finds no permitted match; vector fill returns an allowed row.
    cursor = FakeCursor(result_sets=[[], [row(1001, allowed_doc_id, "Tài liệu khác")]])

    def fake_vector_search(cur, query_vector, top_k, candidate_ids, allowed_ids=None):
        # Hybrid must pass only the candidate/ACL intersection to vector search.
        assert set(candidate_ids) == {allowed_doc_id}
        assert set(allowed_ids) == {allowed_doc_id}
        return [row(1001, allowed_doc_id, "Tài liệu khác")]

    monkeypatch.setattr(hybrid, "vector_search", fake_vector_search)

    results = hybrid.hybrid_search(
        cursor,
        "Tìm hồ sơ 00002",
        [0.1, 0.2],
        top_k=2,
        candidate_ids=[denied_doc_id, allowed_doc_id],
        allowed_ids=[allowed_doc_id],
    )

    # Exact-title SQL must receive only permitted IDs; denied_doc_id is absent.
    exact_query, exact_params = cursor.queries[0]
    assert "c.document_id = ANY(%s)" in exact_query
    assert set(exact_params[1]) == {allowed_doc_id}
    assert denied_doc_id not in exact_params[1]
    assert all(result[1] != denied_doc_id for result in results)


def test_hybrid_returns_no_rows_when_all_exact_title_candidates_are_denied(monkeypatch):
    """If no candidate is allowed, retrieval exits before either branch queries."""
    cursor = FakeCursor()
    vector_called = False

    def fake_vector_search(*args, **kwargs):
        nonlocal vector_called
        vector_called = True
        return []

    monkeypatch.setattr(hybrid, "vector_search", fake_vector_search)

    results = hybrid.hybrid_search(
        cursor,
        "Tìm hồ sơ 00002",
        [0.1, 0.2],
        top_k=3,
        candidate_ids=[200],
        allowed_ids=[],
    )

    assert results == []
    assert cursor.queries == []
    assert vector_called is False


def test_vector_search_adds_acl_filter_before_ranking():
    """Vector SQL must constrain document IDs before ORDER BY/LIMIT."""
    allowed_doc_id = 100
    denied_doc_id = 200
    cursor = FakeCursor(rows=[row(1001, allowed_doc_id)])

    results = hybrid.vector_search(
        cursor,
        [0.1, 0.2],
        top_k=3,
        candidate_ids=[allowed_doc_id, denied_doc_id],
        allowed_ids=[allowed_doc_id],
    )

    assert len(cursor.queries) == 1
    query, params = cursor.queries[0]
    assert "AND c.document_id = ANY(%s)" in query
    assert "ORDER BY c.embedding <=> %s::vector" in query
    assert "LIMIT %s" in query
    # Parameter order: vector, candidate IDs, permitted IDs, vector, top_k.
    assert set(params[1]) == {allowed_doc_id, denied_doc_id}
    assert set(params[2]) == {allowed_doc_id}
    assert denied_doc_id not in params[2]
    assert params[4] == 3
    assert all(result[1] == allowed_doc_id for result in results)


def test_vector_search_returns_empty_without_sql_when_no_allowed_documents():
    cursor = FakeCursor()

    results = hybrid.vector_search(
        cursor,
        [0.1, 0.2],
        top_k=3,
        candidate_ids=[200],
        allowed_ids=[],
    )

    assert results == []
    assert cursor.queries == []
