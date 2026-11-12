from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark_v1"
if str(BENCH) not in sys.path: sys.path.insert(0, str(BENCH))

from run_retrieval_benchmark import evaluate


def fake_row(chunk_id, doc_id, content):
    # Cấu trúc tương ứng với kết quả SELECT trong vector_search:
    # chunk_id, document_id, title, classification, department, content, similarity
    return (chunk_id, doc_id, "Test document", "Mật", "Kỹ thuật", content, 0.9)


user = {"username": "bench_employee_tech", "role": "Nhân viên",
        "department": "Kỹ thuật"}

documents = {
    1: {"id": 1, "classification": "Mật", "department": "Kỹ thuật"},
    2: {"id": 2, "classification": "Nội bộ", "department": "Kỹ thuật"},
}

fact = ["DOC-1000-00004"]


def test_denied_fact_found():
    result = evaluate(
        [fake_row(101, 1, "Mã hồ sơ DOC-1000-00004")],
        [], fact, user, documents, "denied_retrieval"
    )
    assert result["protected_facts_leaked_exact"] == 1
    assert result["unauthorized_context_count"] == 1


def test_denied_fact_not_found():
    result = evaluate(
        [fake_row(102, 1, "Nội dung khác")],
        [], fact, user, documents, "denied_retrieval"
    )
    assert result["protected_facts_leaked_exact"] == 0


def test_allowed_fact_not_counted_as_leakage():
    result = evaluate(
        [fake_row(103, 2, "Mã hồ sơ DOC-1000-00004")],
        [2], fact, user, documents, "allowed_retrieval"
    )
    assert result["protected_facts_leaked_exact"] == 0
    assert result["unauthorized_context_count"] == 0

print("PASS: cả 3 kiểm thử evaluate() đều đạt.")
