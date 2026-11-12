"""
Generate deterministic synthetic corpora for benchmark v1.

Target database: baomatdulieu_benchmark ONLY.
Does not connect to or modify the application database.
Requires: psycopg2-binary, numpy.

Examples (PowerShell):
  python .\\generate_synthetic_dataset.py --scale 1000
  python .\\generate_synthetic_dataset.py --scale all

The script is intentionally non-destructive by default. It refuses to add a
scale that already contains documents; use --reset-scale only when you
explicitly want to replace that scale's synthetic corpus.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from typing import Iterable

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

DATABASE_NAME = "baomatdulieu_benchmark"
SCALES = (1000, 5000, 10000)
BASE_SEED = 20261010
VECTOR_DIMENSION = 768
CHUNKS_PER_DOCUMENT = 3
BATCH_SIZE = 250

DEPARTMENTS = ("Kỹ thuật", "Kinh doanh")
CLASSIFICATIONS = ("Công khai", "Nội bộ", "Mật", "Tối mật")

TOPICS = (
    ("nền tảng dữ liệu", "pipeline ETL", "chất lượng dữ liệu"),
    ("hệ thống RAG", "vector search", "kiểm soát truy cập"),
    ("hạ tầng cloud", "giám sát dịch vụ", "quản lý sự cố"),
    ("phát triển phần mềm", "quy trình review", "quản lý phiên bản"),
    ("an toàn thông tin", "quản lý phân quyền", "ghi nhật ký kiểm toán"),
    ("phân tích kinh doanh", "báo cáo vận hành", "dự báo nhu cầu"),
    ("hệ thống nhân sự", "quy trình nội bộ", "quản lý tài khoản"),
    ("dịch vụ khách hàng", "quản lý SLA", "theo dõi chất lượng"),
)
SYSTEMS = (
    "DataHub", "RAG Gateway", "Core Platform", "Insight Portal",
    "Access Service", "Ops Console", "Customer API", "Analytics Hub",
)
STATUSES = ("đang lập kế hoạch", "đang triển khai", "đang rà soát", "đã hoàn thành")
TEAMS = ("nền tảng", "dữ liệu", "an toàn thông tin", "vận hành", "sản phẩm")


def connect():
    """Connect only to the isolated benchmark database using shared env credentials."""
    user = os.getenv("BENCHMARK_DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("BENCHMARK_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Set POSTGRES_USER/POSTGRES_PASSWORD in the environment (or override "
            "with BENCHMARK_DB_USER/BENCHMARK_DB_PASSWORD)."
        )
    conn = psycopg2.connect(
        host=os.getenv("BENCHMARK_DB_HOST", os.getenv("POSTGRES_HOST", "localhost")),
        port=int(os.getenv("BENCHMARK_DB_PORT", os.getenv("POSTGRES_PORT", "5432"))),
        dbname=os.getenv("BENCHMARK_DB_NAME", DATABASE_NAME),
        user=user,
        password=password,
        connect_timeout=10,
        application_name="benchmark_v1_synthetic_generator",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
    actual_db = row[0] if row else None
    if actual_db != DATABASE_NAME:
        conn.close()
        raise RuntimeError(
            f"Safety stop: connected to {actual_db!r}, expected {DATABASE_NAME!r}."
        )
    conn.rollback()  # End the identity-check transaction before callers configure/use the session.
    return conn


def make_document(rng: random.Random, scale: int, doc_number: int):
    classification = CLASSIFICATIONS[(doc_number - 1) % len(CLASSIFICATIONS)]
    topic_group = rng.choice(TOPICS)
    topic = rng.choice(topic_group)
    system = rng.choice(SYSTEMS)
    team = rng.choice(TEAMS)
    status = rng.choice(STATUSES)
    quarter = rng.choice(("Q1", "Q2", "Q3", "Q4"))
    year = rng.choice((2025, 2026, 2027))

    if classification == "Công khai":
        department = None
        sensitivity_note = "Thông tin đã được xác định có thể công bố rộng rãi."
    elif classification == "Nội bộ":
        department = rng.choice((None, *DEPARTMENTS, "Toàn công ty"))
        sensitivity_note = "Chỉ phục vụ hoạt động và phối hợp nội bộ."
    elif classification == "Mật":
        department = rng.choice(DEPARTMENTS)
        sensitivity_note = "Chỉ người có thẩm quyền trong phạm vi phù hợp được truy cập."
    else:
        # Keep company-wide top-secret documents consistent with the approved
        # policy semantics; department-specific top-secret documents also occur.
        department = rng.choice(("Toàn công ty", *DEPARTMENTS))
        sensitivity_note = "Thông tin chiến lược có phạm vi truy cập hạn chế."

    title = f"{system} — {topic.capitalize()} — hồ sơ {doc_number:05d}"
    content = (
        f"Hồ sơ benchmark {doc_number:05d} của {system} đề cập đến {topic}. "
        f"Nhóm phụ trách: {team}. Trạng thái: {status}. Kỳ kế hoạch: {quarter}/{year}. "
        f"Mục tiêu là theo dõi tiến độ, chất lượng và trách nhiệm xử lý của nhóm. "
        f"{sensitivity_note} Mã hồ sơ: DOC-{scale}-{doc_number:05d}."
    )
    chunks = (
        f"Hồ sơ DOC-{scale}-{doc_number:05d}: {system} đang xử lý nội dung về {topic}. "
        f"Nhóm phụ trách là {team}; trạng thái hiện tại: {status}.",
        f"Kế hoạch {quarter}/{year} của {system} tập trung vào {topic_group[1]} "
        f"và {topic_group[2]}. Mọi thay đổi cần được ghi nhận theo quy trình.",
        f"Phân loại tài liệu: {classification}. Phạm vi phòng ban: "
        f"{department if department is not None else 'không giới hạn theo phòng ban'}. "
        f"Mã tham chiếu DOC-{scale}-{doc_number:05d}.",
    )
    return title, content, classification, department, chunks


def vector_literal(vector: np.ndarray) -> str:
    # pgvector accepts the standard textual format: [x1,x2,...].
    return "[" + ",".join(f"{float(x):.7f}" for x in vector) + "]"


def seed_benchmark_users(cur):
    """Insert fixed benchmark identities without changing existing identities."""
    users = (
        ("bench_employee_tech", "Nhân viên", "Kỹ thuật"),
        ("bench_employee_sales", "Nhân viên", "Kinh doanh"),
        ("bench_manager_tech", "Manager", "Kỹ thuật"),
        ("bench_manager_sales", "Manager", "Kinh doanh"),
        ("bench_leadership", "Ban lãnh đạo", "Toàn công ty"),
        ("bench_partner", "Đối tác", None),
    )
    for username, role, department in users:
        cur.execute(
            """
            INSERT INTO users (username, role, department)
            VALUES (%s, %s::role_t, %s::dept_t)
            ON CONFLICT (username) DO NOTHING
            """,
            (username, role, department),
        )


def generate_scale(cur, scale: int, base_seed: int):
    cur.execute("SELECT COUNT(*) FROM documents WHERE benchmark_scale = %s", (scale,))
    existing_count = cur.fetchone()[0]
    if existing_count:
        raise RuntimeError(
            f"Scale {scale} đã có {existing_count} documents. "
            "Không ghi đè tự động; dùng --reset-scale nếu thật sự muốn thay thế."
        )

    seed = base_seed + scale
    py_rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    docs_batch = []
    docs_chunks_batch = []
    total_docs = 0
    total_chunks = 0

    def flush_batch():
        nonlocal total_docs, total_chunks, docs_batch, docs_chunks_batch
        if not docs_batch:
            return
        returned = execute_values(
            cur,
            """
            INSERT INTO documents
                (title, content, classification, department, protection_profile,
                 benchmark_scale, generation_seed)
            VALUES %s
            RETURNING id
            """,
            docs_batch,
            page_size=len(docs_batch),
            fetch=True,
        )
        # INSERT ... RETURNING preserves insertion order for this single VALUES statement.
        chunk_rows = []
        for (doc_id,), (_title, _content, _classification, _department, chunks) in zip(
            returned, docs_chunks_batch
        ):
            for chunk_no, chunk_text in enumerate(chunks, start=1):
                vector = np_rng.standard_normal(VECTOR_DIMENSION).astype(np.float32)
                norm = float(np.linalg.norm(vector))
                vector /= norm
                chunk_rows.append(
                    (doc_id, chunk_text, vector_literal(vector), chunk_no, "synthetic")
                )
        execute_values(
            cur,
            """
            INSERT INTO chunks
                (document_id, content, embedding, chunk_no, vector_kind)
            VALUES %s
            """,
            chunk_rows,
            template="(%s, %s, %s::vector, %s, %s)",
            page_size=min(750, len(chunk_rows)),
        )
        total_docs += len(docs_batch)
        total_chunks += len(chunk_rows)
        docs_batch = []
        docs_chunks_batch = []

    for doc_number in range(1, scale + 1):
        title, content, classification, department, chunks = make_document(
            py_rng, scale, doc_number
        )
        docs_batch.append(
            (title, content, classification, department, "GENERAL_INTERNAL", scale, seed)
        )
        docs_chunks_batch.append(
            (title, content, classification, department, chunks)
        )
        if len(docs_batch) >= BATCH_SIZE:
            flush_batch()
            print(
                f"  scale={scale}: {total_docs:,}/{scale:,} documents; "
                f"{total_chunks:,}/{scale * CHUNKS_PER_DOCUMENT:,} chunks",
                flush=True,
            )
    flush_batch()
    return total_docs, total_chunks, seed


def reset_scale(cur, scale: int):
    """Reset one synthetic corpus without leaving stale case ground truth.

    Query cases store target document IDs in an INTEGER[] rather than a foreign
    key. Case-level retrieval results and scale-level performance results are
    immutable evidence. Refuse reset if either kind of history exists; use a
    separate benchmark database for a new corpus version.
    """
    prefix = f"S{scale}"
    cur.execute(
        "SELECT to_regclass('public.benchmark_query_cases'), "
        "to_regclass('public.benchmark_case_results'), "
        "to_regclass('public.benchmark_runs'), "
        "to_regclass('public.benchmark_performance_results')"
    )
    query_table, case_results_table, runs_table, performance_table = cur.fetchone()

    if query_table:
        cur.execute(
            "SELECT id FROM benchmark_query_cases "
            "WHERE split_part(case_key, '_', 1) = %s",
            (prefix,),
        )
        case_ids = [row[0] for row in cur.fetchall()]
        historical_case_results = 0
        if case_ids and case_results_table:
            cur.execute(
                "SELECT COUNT(*) FROM benchmark_case_results "
                "WHERE query_case_id = ANY(%s)",
                (case_ids,),
            )
            historical_case_results = cur.fetchone()[0]

        historical_performance_results = 0
        if performance_table and runs_table:
            # Older schemas stored timing by run/repetition without query_case_id.
            # Protect any saved timing for this scale rather than orphaning its context.
            cur.execute(
                "SELECT COUNT(*) FROM benchmark_performance_results p "
                "JOIN benchmark_runs r ON r.id = p.run_id "
                "WHERE r.dataset_scale = %s",
                (scale,),
            )
            historical_performance_results = cur.fetchone()[0]

        if historical_case_results or historical_performance_results:
            raise RuntimeError(
                f"Không thể reset scale={scale}: phát hiện {historical_case_results} "
                f"bản ghi benchmark_case_results và {historical_performance_results} "
                "bản ghi benchmark_performance_results trong lịch sử. "
                "Để giữ tính toàn vẹn, hãy tạo database benchmark mới thay vì thay đổi corpus cũ."
            )
        if case_ids:
            cur.execute(
                "DELETE FROM benchmark_query_cases "
                "WHERE split_part(case_key, '_', 1) = %s",
                (prefix,),
            )

    # Chỉ xóa corpus của scale đã chỉ định; chunks có thể được xóa riêng
    # để không phụ thuộc vào việc schema đã khai báo ON DELETE CASCADE hay chưa.
    cur.execute(
        "DELETE FROM chunks WHERE document_id IN "
        "(SELECT id FROM documents WHERE benchmark_scale = %s)",
        (scale,),
    )
    cur.execute("DELETE FROM documents WHERE benchmark_scale = %s", (scale,))


def main():
    parser = argparse.ArgumentParser(description="Sinh synthetic corpus cho benchmark v1.")
    parser.add_argument(
        "--scale", choices=("1000", "5000", "10000", "all"), default="1000",
        help="Quy mô cần sinh (mặc định: 1000). 'all' sinh cả ba corpus độc lập."
    )
    parser.add_argument("--seed", type=int, default=BASE_SEED, help="Seed gốc để tái lập dữ liệu.")
    parser.add_argument(
        "--reset-scale", action="store_true",
        help="Xóa và sinh lại documents/chunks của scale đã chọn; không xóa runs/results."
    )
    args = parser.parse_args()

    scales = list(SCALES) if args.scale == "all" else [int(args.scale)]
    if args.reset_scale and args.scale == "all":
        parser.error("--reset-scale không dùng cùng --scale all; chọn một scale cụ thể.")

    conn = None
    try:
        conn = connect()
        conn.autocommit = False
        with conn.cursor() as cur:
            # Fail fast if the expected schema isn't present.
            cur.execute("SELECT to_regclass('public.documents'), to_regclass('public.chunks')")
            if cur.fetchone() != ("documents", "chunks"):
                raise RuntimeError("Không tìm thấy bảng documents/chunks trong benchmark database.")

            seed_benchmark_users(cur)
            for scale in scales:
                if args.reset_scale:
                    reset_scale(cur, scale)
                docs, chunks, used_seed = generate_scale(cur, scale, args.seed)
                print(
                    f"Hoàn tất scale={scale}: documents={docs:,}, chunks={chunks:,}, "
                    f"seed={used_seed}",
                    flush=True,
                )
        conn.commit()
        print(f"\nĐã commit dữ liệu vào {DATABASE_NAME}.")
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
