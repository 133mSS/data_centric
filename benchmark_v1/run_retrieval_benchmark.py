"""
Benchmark retrieval cho baomatdulieu_benchmark.
So sánh:
  - baseline: vector search trên cohort scale, không lọc quyền
  - controlled: áp dụng policy trước khi vector search
  - hybrid: ưu tiên khớp mã hồ sơ chính xác, sau đó bổ sung vector search; lọc quyền trước cả hai nhánh

Chạy từ thư mục gốc project:
    python benchmark_v1/run_retrieval_benchmark.py --variant controlled --dry-run
    python benchmark_v1/run_retrieval_benchmark.py --variant controlled

Yêu cầu:
  - Ollama đang chạy và có model nomic-embed-text
  - app/policy.py có hàm check_access(user, document)
  - database benchmark có users, documents, chunks, benchmark_query_cases,
    benchmark_runs, benchmark_case_results.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from policy import check_access

DATABASE_NAME = "baomatdulieu_benchmark"
MODEL = "nomic-embed-text"
DIMENSION = 768
DEFAULT_TOP_K = 3
DEFAULT_REPETITIONS = 30
WARMUP_COUNT = 5
SCALE_SEEDS = {1000: 20262010, 5000: 20266010, 10000: 20271010}
OLLAMA_URL = os.getenv("OLLAMA_EMBEDDINGS_URL", "http://localhost:11434/api/embeddings")

from db_config import get_benchmark_db_config


def connect():
    import psycopg2
    conn = psycopg2.connect(**get_benchmark_db_config())
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
    actual = row[0] if row else None
    if actual != DATABASE_NAME:
        conn.close()
        raise RuntimeError(
            f"Safety stop: connected to {actual!r}, expected {DATABASE_NAME!r}."
        )
    conn.rollback()  # End the identity-check transaction before callers configure/use the session.
    return conn


def embed_query(query):
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": query},
        timeout=120,
    )
    response.raise_for_status()
    vector = response.json().get("embedding")
    if not isinstance(vector, list) or len(vector) != DIMENSION:
        raise ValueError(
            f"Embedding không hợp lệ: expected {DIMENSION} dimensions."
        )
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


def load_cases(cur):
    cur.execute("""
        SELECT id, case_key, query_text, username,
               expected_relevant_document_ids, protected_facts,
               test_category, expected_answerable, notes
        FROM benchmark_query_cases
        ORDER BY id
    """)
    return cur.fetchall()


def load_user(cur, username):
    cur.execute("""
        SELECT username, role, department
        FROM users
        WHERE username = %s
    """, (username,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Không tìm thấy benchmark user: {username}")
    return {"username": row[0], "role": row[1], "department": row[2]}


def load_document_metadata(cur):
    cur.execute("""
        SELECT id, classification::text, department::text, benchmark_scale
        FROM documents
    """)
    return {
        row[0]: {
            "id": row[0], "classification": row[1],
            "department": row[2], "benchmark_scale": int(row[3]),
        }
        for row in cur.fetchall()
    }


def case_scale(case_key):
    match = re.match(r"^S(1000|5000|10000)_", case_key)
    if not match:
        raise RuntimeError(
            f"case_key không có prefix scale hợp lệ (S1000_/S5000_/S10000_): {case_key}"
        )
    return int(match.group(1))


def allowed_document_ids(user, documents):
    return [
        doc_id for doc_id, doc in documents.items()
        if check_access(user, doc) == "ALLOW"
    ]


def vector_search(cur, query_vector, top_k, candidate_ids, allowed_ids=None):
    """Search chỉ trong cohort scale; controlled còn lọc quyền trước ranking."""
    if not candidate_ids:
        return []
    if allowed_ids is not None:
        allowed_ids = list(set(candidate_ids).intersection(allowed_ids))
        if not allowed_ids:
            return []
        document_filter = "AND c.document_id = ANY(%s)"
        params = (query_vector, candidate_ids, allowed_ids, query_vector, top_k)
    else:
        document_filter = ""
        params = (query_vector, candidate_ids, query_vector, top_k)

    cur.execute(f"""
        SELECT c.id, c.document_id, d.title, d.classification::text,
               d.department::text, c.content,
               (1 - (c.embedding <=> %s::vector)) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
          AND c.document_id = ANY(%s)
          {document_filter}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """, params)
    return cur.fetchall()



def hybrid_search(cur, query, query_vector, top_k, candidate_ids, allowed_ids):
    """Hybrid retrieval với ACL áp dụng trước cả hai nhánh."""
    hybrid_start = time.perf_counter()
    exact_match_ms = 0.0
    vector_search_ms = 0.0

    permitted_ids = list(set(candidate_ids).intersection(allowed_ids))
    if not permitted_ids or top_k < 1:
        return []

    match = re.search(r"\bhồ sơ\s+(\d{5})\b", query, flags=re.IGNORECASE)
    exact_rows = []
    exact_doc_id = None

    if match:
        suffix = match.group(1)

        exact_start = time.perf_counter()
        cur.execute("""
            SELECT c.id, c.document_id, d.title, d.classification::text,
                   d.department::text, c.content,
                   (1 - (c.embedding <=> %s::vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND c.document_id = ANY(%s)
              AND d.title ILIKE %s
            ORDER BY c.embedding <=> %s::vector
            LIMIT 1
        """, (query_vector, permitted_ids, f"%hồ sơ {suffix}", query_vector))
        exact_rows = cur.fetchall()
        exact_match_ms = (time.perf_counter() - exact_start) * 1000

        if exact_rows:
            exact_doc_id = exact_rows[0][1]

    remaining_k = top_k - len(exact_rows)
    vector_rows = []

    if remaining_k > 0:
        fill_candidate_ids = [
            doc_id for doc_id in permitted_ids
            if doc_id != exact_doc_id
        ]

        vector_start = time.perf_counter()
        vector_rows = vector_search(
            cur, query_vector, remaining_k,
            fill_candidate_ids, allowed_ids=permitted_ids
        )
        vector_search_ms = (time.perf_counter() - vector_start) * 1000

    hybrid_total_ms = (time.perf_counter() - hybrid_start) * 1000



    return exact_rows + vector_rows




def explain_hybrid_case(cur, case_key, query, query_vector, candidate_ids, allowed_ids, top_k):
    """Print real PostgreSQL execution plans for one Hybrid case; writes no benchmark rows."""
    permitted_ids = list(set(candidate_ids).intersection(allowed_ids))
    print(f"\nEXPLAIN diagnostic: case_key={case_key}")
    print(f"candidate_documents={len(candidate_ids)}; permitted_documents={len(permitted_ids)}")
    if not permitted_ids:
        print("Không có document được phép trong cohort; không có truy vấn retrieval để explain.")
        return

    match = re.search(r"\bhồ sơ\s+(\d{5})\b", query, flags=re.IGNORECASE)
    exact_doc_id = None

    if match:
        suffix = match.group(1)
        exact_params = (
            query_vector, permitted_ids, f"%hồ sơ {suffix}", query_vector
        )
        exact_sql = """
            SELECT c.id, c.document_id, d.title, d.classification::text,
                   d.department::text, c.content,
                   (1 - (c.embedding <=> %s::vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND c.document_id = ANY(%s)
              AND d.title ILIKE %s
            ORDER BY c.embedding <=> %s::vector
            LIMIT 1
        """

        # Get the same exact-match result as Hybrid uses, to reproduce its vector fill set.
        cur.execute(exact_sql, exact_params)
        exact_rows = cur.fetchall()
        if exact_rows:
            exact_doc_id = exact_rows[0][1]
        print(f"\n--- EXACT-MATCH branch (suffix={suffix}; exact_doc_id={exact_doc_id}) ---")
        cur.execute(
            "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) " + exact_sql,
            exact_params,
        )
        for row in cur.fetchall():
            print(row[0])
    else:
        print("\n--- EXACT-MATCH branch skipped: query has no 'hồ sơ + 5 digits' pattern ---")

    remaining_k = max(0, top_k - (1 if exact_doc_id is not None else 0))
    if remaining_k < 1:
        print("\n--- VECTOR branch skipped: exact-match already fills top_k ---")
        return

    fill_candidate_ids = [doc_id for doc_id in permitted_ids if doc_id != exact_doc_id]
    if not fill_candidate_ids:
        print("\n--- VECTOR branch skipped: no remaining permitted candidates ---")
        return

    # Match vector_search(..., allowed_ids=permitted_ids), using its actual SQL and filters.
    vector_sql = """
        SELECT c.id, c.document_id, d.title, d.classification::text,
               d.department::text, c.content,
               (1 - (c.embedding <=> %s::vector)) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
          AND c.document_id = ANY(%s)
          AND c.document_id = ANY(%s)
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    vector_params = (
        query_vector, fill_candidate_ids, permitted_ids, query_vector, remaining_k
    )
    print(
        f"\n--- VECTOR-SEARCH branch "
        f"(candidate_documents={len(fill_candidate_ids)}; top_k={remaining_k}) ---"
    )
    cur.execute(
        "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) " + vector_sql,
        vector_params,
    )
    for row in cur.fetchall():
        print(row[0])


def normalize_facts(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []



def evaluate(rows, expected_doc_ids, protected_facts, user, documents, category):
    returned_doc_ids = list(dict.fromkeys(row[1] for row in rows))
    returned_chunk_ids = [row[0] for row in rows]

    unauthorized_chunk_ids = [
        row[0] for row in rows
        if check_access(user, documents[row[1]]) != "ALLOW"
    ]

    expected = set(expected_doc_ids or [])
    returned = set(returned_doc_ids)
    recall = (
        len(expected & returned) / len(expected)
        if expected else None
    )

    context = "\n".join(str(row[5]) for row in rows)

    # Chỉ đo exact fact exposure trên các case bị từ chối truy cập.
    # Đây là leakage trong retrieval context, không phải LLM answer leakage.
    leaked_facts = 0
    if category == "denied_retrieval":
        leaked_facts = sum(
            1
            for fact in protected_facts
            if isinstance(fact, str) and fact and fact in context
        )

    return {
        "returned_document_ids": returned_doc_ids,
        "returned_chunk_ids": returned_chunk_ids,
        "unauthorized_chunk_ids": unauthorized_chunk_ids,
        "recall_at_k": recall,
        "unauthorized_context_count": len(unauthorized_chunk_ids),
        "protected_facts_leaked_exact": leaked_facts,
        "output_text": context,
    }



def main():
    import psycopg2
    from psycopg2.extras import Json, execute_values
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--variant", choices=("baseline", "controlled", "hybrid"), required=True, help="Variant chạy trong invocation này.")
    parser.add_argument(
        "--explain-case-key",
        help="Chỉ in EXPLAIN ANALYZE cho một case Hybrid; không ghi benchmark rows.",
    )
    parser.add_argument(
        "--case-keys", nargs="+",
        help="Chỉ chạy các case_key được chỉ định; dùng để kiểm thử có giới hạn trước full benchmark.",
    )
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be >= 1")
    if args.repetitions != 30:
        parser.error("Schema benchmark_runs yêu cầu measurement_count=30; --repetitions phải bằng 30")

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM chunks
                WHERE embedding IS NOT NULL AND vector_kind = 'real'
            """)
            embedded = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM chunks")
            total_chunks = cur.fetchone()[0]
            if embedded != total_chunks or total_chunks == 0:
                raise RuntimeError(
                    f"Embedding precheck failed: real={embedded}, total={total_chunks}"
                )

            cases = load_cases(cur)
            if not cases:
                raise RuntimeError("benchmark_query_cases không có test case.")
            if args.case_keys:
                requested_keys = set(args.case_keys)
                available_keys = {row[1] for row in cases}
                missing_keys = requested_keys - available_keys
                if missing_keys:
                    raise RuntimeError(
                        f"Không tìm thấy case_key được yêu cầu: {sorted(missing_keys)}"
                    )
                cases = [row for row in cases if row[1] in requested_keys]
            documents = load_document_metadata(cur)

            docs_by_scale = {scale: [] for scale in SCALE_SEEDS}
            for doc_id, doc in documents.items():
                scale = doc["benchmark_scale"]
                if scale not in docs_by_scale:
                    raise RuntimeError(f"documents có benchmark_scale không hợp lệ: {scale}")
                docs_by_scale[scale].append(doc_id)
            for scale, ids in docs_by_scale.items():
                if len(ids) != scale:
                    raise RuntimeError(
                        f"Scale {scale}: mong đợi {scale:,} documents, thực tế {len(ids):,}."
                    )

            cases_by_scale = {scale: [] for scale in SCALE_SEEDS}
            for case_row in cases:
                scale = case_scale(case_row[1])
                if scale not in cases_by_scale:
                    raise RuntimeError(f"Scale không được hỗ trợ: {scale}")
                expected_ids = case_row[4] or []
                unknown_ids = set(expected_ids) - set(documents)
                if unknown_ids:
                    raise RuntimeError(
                        f"Case {case_row[1]} tham chiếu document không tồn tại: {sorted(unknown_ids)}"
                    )
                wrong_scale = [doc_id for doc_id in expected_ids
                               if documents[doc_id]["benchmark_scale"] != scale]
                if wrong_scale:
                    raise RuntimeError(
                        f"Case {case_row[1]} có expected document khác scale: {wrong_scale}"
                    )
                cases_by_scale[scale].append(case_row)
            for scale, scale_cases in cases_by_scale.items():
                if not scale_cases and not args.case_keys:
                    raise RuntimeError(f"Không có test case cho scale {scale}.")

            users = {}
            for case_row in cases:
                username = case_row[3]
                if username not in users:
                    users[username] = load_user(cur, username)

            if args.explain_case_key:
                selected = [row for row in cases if row[1] == args.explain_case_key]
                if not selected:
                    available = sorted(row[1] for row in load_cases(cur))
                    raise RuntimeError(
                        f"Không tìm thấy case_key {args.explain_case_key!r}. "
                        f"Ví dụ case hợp lệ: {available[:10]}"
                    )
                case_row = selected[0]
                case_key = case_row[1]
                scale = case_scale(case_key)
                candidate_ids = docs_by_scale[scale]
                user = users.get(case_row[3]) or load_user(cur, case_row[3])
                allowed_ids = allowed_document_ids(user, documents)
                query_vector = embed_query(case_row[2])
                print(f"Database: {DATABASE_NAME}")
                print(f"Diagnostic case: {case_key}; scale={scale}; user={user['username']}")
                explain_hybrid_case(
                    cur, case_key, case_row[2], query_vector, candidate_ids, allowed_ids, args.top_k
                )
                print("\nDiagnostic completed. No benchmark_runs or benchmark_case_results inserted.")
                return

            print(f"Database: {DATABASE_NAME}")
            print(f"Chunks with real embeddings: {embedded:,}/{total_chunks:,}")
            print(f"Test cases: {len(cases)}; scale distribution: " +
                  ", ".join(f"{scale}={len(rows)}" for scale, rows in cases_by_scale.items()))
            print(f"Top-k: {args.top_k}; measured repetitions/case/variant: {args.repetitions}")
            print(f"Warm-up repetitions/case/variant: {WARMUP_COUNT}")
            print(f"Users validated: {len(users)}")
            if args.dry_run:
                print("DRY RUN: validation only; no benchmark rows inserted and no retrieval executed.")
                return

            started = datetime.now(timezone.utc)
            run_ids = {}
            active_scales = [scale for scale in (1000, 5000, 10000) if cases_by_scale[scale]]
            for scale in active_scales:
                for variant in (args.variant,):
                    cur.execute("""
                        INSERT INTO benchmark_runs
                          (run_name, system_variant, experiment_type, dataset_scale,
                           seed, top_k, vector_dimension, distance_metric,
                           index_description, embedding_model, warmup_count,
                           measurement_count, started_at, config_json, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        f"retrieval-{variant}-s{scale}-{started.strftime('%Y%m%dT%H%M%SZ')}",
                        variant, "security_leakage", scale, SCALE_SEEDS[scale],
                        args.top_k, DIMENSION, "cosine",
                        "Existing chunks embedding index; verify actual PostgreSQL index separately",
                        MODEL, WARMUP_COUNT, args.repetitions, started,
                        Json({
                            "metric_scope": "retrieval_context",
                            "repetitions": args.repetitions,
                            "warmup_count": WARMUP_COUNT,
                            "scale_seed_semantics": "document generation seed for this scale cohort",
                            "cohort_filter": "documents.benchmark_scale",
                            "policy_applied_before_ranking": variant in ("controlled", "hybrid"),
                            "retrieval_strategy": {
                                "baseline": "vector_only_without_acl",
                                "controlled": "vector_only_with_acl_before_ranking",
                                "hybrid": "exact_title_suffix_then_vector_with_acl_before_both",
                            }[variant],
                        }),
                        "Retrieval-only security benchmark; no LLM generation. Exact fact metric checks retrieved context only; semantic review remains pending.",
                    ))
                    run_ids[(scale, variant)] = cur.fetchone()[0]
            conn.commit()

            result_rows = []
            performance_rows = []
            for scale in active_scales:
                # Ghi thời điểm bắt đầu thực tế của riêng run này.
                run_started = datetime.now(timezone.utc)
                run_id = run_ids[(scale, args.variant)]
                with conn.cursor() as timestamp_cur:
                    timestamp_cur.execute(
                        "UPDATE benchmark_runs SET started_at = %s, finished_at = NULL WHERE id = %s",
                        (run_started, run_id),
                    )
                conn.commit()

                candidate_ids = docs_by_scale[scale]
                for case_row in cases_by_scale[scale]:
                    (case_id, case_key, query, username, expected_ids, facts,
                     category, answerable, notes) = case_row
                    user = users[username]
                    facts = normalize_facts(facts)
                    allowed_ids = allowed_document_ids(user, documents)
                    query_vector = embed_query(query)
                    
                    # Không chạy truy vấn chẩn đoán trong benchmark đo latency.
                    # Khi cần xem execution plan/ranking, chạy riêng --explain-case-key.
                    # Warm-up cho biến thể đang chạy; không ghi vào measurement results.
                    for _ in range(WARMUP_COUNT):
                        for variant in (args.variant,):
                            if variant == "baseline":
                                vector_search(cur, query_vector, args.top_k, candidate_ids)
                            elif variant == "controlled":
                                vector_search(cur, query_vector, args.top_k, candidate_ids, allowed_ids)
                            else:
                                hybrid_search(cur, query, query_vector, args.top_k, candidate_ids, allowed_ids)

                    for repetition in range(1, args.repetitions + 1):
                        # Mỗi invocation chỉ đo một variant (--variant); so sánh giữa các run cần chuẩn hóa thứ tự chạy.
                        variants = (args.variant,)
                        for variant in variants:
                            start = time.perf_counter()
                            if variant == "baseline":
                                rows = vector_search(cur, query_vector, args.top_k, candidate_ids)
                            elif variant == "controlled":
                                rows = vector_search(cur, query_vector, args.top_k, candidate_ids, allowed_ids)
                            else:
                                rows = hybrid_search(cur, query, query_vector, args.top_k, candidate_ids, allowed_ids)
                            elapsed_ms = (time.perf_counter() - start) * 1000
                            metrics = evaluate(rows, expected_ids, facts, user, documents, category)
                            metrics["notes"] = (
                                f"scale={scale}; case={case_key}; category={category}; "
                                f"expected_answerable={answerable}; retrieval_ms={elapsed_ms:.3f}; "
                                f"base_notes={notes or ''}"
                            )
                            result_rows.append((
                                run_ids[(scale, variant)], case_id, repetition,
                                metrics["returned_document_ids"],
                                metrics["returned_chunk_ids"],
                                metrics["unauthorized_chunk_ids"],
                                metrics["recall_at_k"],
                                metrics["unauthorized_context_count"],
                                metrics["protected_facts_leaked_exact"],
                                True, "not_reviewed", metrics["output_text"], metrics["notes"],
                            ))
                            performance_rows.append((
                                run_ids[(scale, variant)], case_id, repetition, False,
                                None, None,
                                elapsed_ms if variant in ("baseline", "controlled") else None,
                                elapsed_ms,
                                len(rows),
                                len(set(candidate_ids).intersection(allowed_ids)),
                            ))
                        if len(result_rows) >= 200:
                            with conn.cursor() as insert_cur:
                                execute_values(insert_cur, """
                                    INSERT INTO benchmark_case_results
                                      (run_id, query_case_id, repetition_no,
                                       returned_document_ids, returned_chunk_ids,
                                       unauthorized_chunk_ids, recall_at_k,
                                       unauthorized_context_count,
                                       protected_facts_leaked_exact,
                                       semantic_review_required, semantic_review_result,
                                       output_text, notes)
                                    VALUES %s
                                """, result_rows)
                                execute_values(insert_cur, """
                                    INSERT INTO benchmark_performance_results
                                      (run_id, query_case_id, repetition_no, warmup,
                                       policy_latency_ms, embedding_latency_ms,
                                       vector_search_ms, total_retrieval_ms,
                                       returned_chunk_count, allowed_document_count)
                                    VALUES %s
                                """, performance_rows)
                            conn.commit()
                            result_rows.clear()
                            performance_rows.clear()
                    print(f"[PASS] scale={scale} {case_key}")

                # Flush phần còn lại của scale hiện tại trước khi đánh dấu run hoàn tất.
                if result_rows:
                    with conn.cursor() as insert_cur:
                        execute_values(insert_cur, """
                            INSERT INTO benchmark_case_results
                              (run_id, query_case_id, repetition_no,
                               returned_document_ids, returned_chunk_ids,
                               unauthorized_chunk_ids, recall_at_k,
                               unauthorized_context_count,
                               protected_facts_leaked_exact,
                               semantic_review_required, semantic_review_result,
                               output_text, notes)
                            VALUES %s
                        """, result_rows)
                        execute_values(insert_cur, """
                            INSERT INTO benchmark_performance_results
                              (run_id, query_case_id, repetition_no, warmup,
                               policy_latency_ms, embedding_latency_ms,
                               vector_search_ms, total_retrieval_ms,
                               returned_chunk_count, allowed_document_count)
                            VALUES %s
                        """, performance_rows)
                    conn.commit()
                    result_rows.clear()
                    performance_rows.clear()

                run_finished = datetime.now(timezone.utc)
                with conn.cursor() as  timestamp_cur:
                     timestamp_cur.execute(
                        "UPDATE benchmark_runs SET finished_at = %s WHERE id = %s",
                        (run_finished, run_id),
                    )
                conn.commit()

            if result_rows:
                with conn.cursor() as insert_cur:
                    execute_values(insert_cur, """
                        INSERT INTO benchmark_case_results
                          (run_id, query_case_id, repetition_no,
                           returned_document_ids, returned_chunk_ids,
                           unauthorized_chunk_ids, recall_at_k,
                           unauthorized_context_count,
                           protected_facts_leaked_exact,
                           semantic_review_required, semantic_review_result,
                           output_text, notes)
                        VALUES %s
                    """, result_rows)
                    execute_values(insert_cur, """
                        INSERT INTO benchmark_performance_results
                          (run_id, query_case_id, repetition_no, warmup,
                           policy_latency_ms, embedding_latency_ms,
                           vector_search_ms, total_retrieval_ms,
                           returned_chunk_count, allowed_document_count)
                        VALUES %s
                    """, performance_rows)
                conn.commit()

            print("\nBenchmark completed.")
            print("Run IDs by (scale, variant):")
            for key, run_id in run_ids.items():
                print(f"  {key}: {run_id}")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT r.dataset_scale, r.system_variant, cr.query_case_id,
                           COUNT(*) AS measurements,
                           COALESCE(SUM(cr.unauthorized_context_count), 0) AS unauthorized_chunks,
                           AVG(cr.recall_at_k) AS mean_recall_at_k,
                           AVG(cr.protected_facts_leaked_exact) AS mean_exact_fact_matches
                    FROM benchmark_runs r
                    JOIN benchmark_case_results cr ON cr.run_id = r.id
                    WHERE r.id = ANY(%s)
                    GROUP BY r.dataset_scale, r.system_variant, cr.query_case_id
                    ORDER BY r.dataset_scale, r.system_variant, cr.query_case_id
                """, (list(run_ids.values()),))
                summaries = cur.fetchall()
            print("\nSummary by scale / variant / test case:")
            for row in summaries:
                print(
                    f"scale={row[0]} variant={row[1]} case_id={row[2]} "
                    f"measurements={row[3]} unauthorized_chunks_sum={row[4]} "
                    f"mean_recall_at_k={row[5]} mean_exact_fact_matches={row[6]}"
                )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
