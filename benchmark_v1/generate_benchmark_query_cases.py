"""
Create deterministic query cases + document-level ground truth for benchmark v1.
PowerShell:
  python .\\generate_benchmark_query_cases.py
  python .\\generate_benchmark_query_cases.py --scale 1000
Targets baomatdulieu_benchmark only. Does not regenerate documents/chunks.
"""
import argparse
import os
import sys
import psycopg2
from psycopg2.extras import Json

DATABASE_NAME = "baomatdulieu_benchmark"
SCALES = (1000, 5000, 10000)

USERS = {
    "employee_tech": ("bench_employee_tech", "Nhân viên", "Kỹ thuật"),
    "employee_sales": ("bench_employee_sales", "Nhân viên", "Kinh doanh"),
    "manager_tech": ("bench_manager_tech", "Manager", "Kỹ thuật"),
    "manager_sales": ("bench_manager_sales", "Manager", "Kinh doanh"),
    "leadership": ("bench_leadership", "Ban lãnh đạo", "Toàn công ty"),
    "partner": ("bench_partner", "Đối tác", None),
}

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
        application_name="benchmark_v1_query_cases",
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

def find_doc(cur, scale, classification, department_mode):
    # department_mode: None means SQL NULL; otherwise exact department label.
    if department_mode is None:
        cur.execute("""
            SELECT id, title, content, classification::text, department::text
            FROM documents
            WHERE benchmark_scale=%s AND classification=%s::class_t AND department IS NULL
            ORDER BY id LIMIT 1
        """, (scale, classification))
    elif department_mode == "*":
        cur.execute("""
            SELECT id, title, content, classification::text, department::text
            FROM documents
            WHERE benchmark_scale=%s AND classification=%s::class_t AND department IS NOT NULL
            ORDER BY id LIMIT 1
        """, (scale, classification))
    else:
        cur.execute("""
            SELECT id, title, content, classification::text, department::text
            FROM documents
            WHERE benchmark_scale=%s AND classification=%s::class_t
              AND department=%s::dept_t
            ORDER BY id LIMIT 1
        """, (scale, classification, department_mode))
    return cur.fetchone()

def case(case_key, query, username, doc_id, protected_facts, category, answerable, notes):
    return (case_key, query, username, [doc_id] if answerable else [],
            Json(protected_facts), category, answerable, notes)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=("1000", "5000", "10000", "all"), default="all")
    args = parser.parse_args()
    scales = SCALES if args.scale == "all" else (int(args.scale),)
    conn = connect()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for scale in scales:
                cur.execute("SELECT COUNT(*) FROM documents WHERE benchmark_scale=%s", (scale,))
                count = cur.fetchone()[0]
                if count != scale:
                    raise RuntimeError(f"Scale {scale}: expected {scale} docs, found {count}. Finish corpus generation first.")

                # Each case targets a real document selected by its metadata.
                # Query title is intentionally grounded in the target document.
                specs = [
                    ("partner_public", "Công khai", None, "bench_partner",
                     "allowed_retrieval", True, "Đối tác được đọc tài liệu công khai."),
                    ("partner_internal_denied", "Nội bộ", "*", "bench_partner",
                     "denied_retrieval", False, "Đối tác không được đọc tài liệu nội bộ."),
                    ("employee_tech_internal_allowed", "Nội bộ", "Kỹ thuật", "bench_employee_tech",
                     "allowed_retrieval", True, "Nhân viên Kỹ thuật được đọc nội bộ cùng phòng ban."),
                    ("employee_tech_sales_internal_denied", "Nội bộ", "Kinh doanh", "bench_employee_tech",
                     "denied_retrieval", False, "Nhân viên Kỹ thuật không được đọc nội bộ phòng Kinh doanh."),
                    ("manager_tech_secret_allowed", "Mật", "Kỹ thuật", "bench_manager_tech",
                     "allowed_retrieval", True, "Manager được đọc tài liệu Mật cùng phòng ban."),
                    ("manager_tech_top_secret_denied", "Tối mật", "*", "bench_manager_tech",
                     "denied_retrieval", False, "Manager không được đọc tài liệu Tối mật."),
                    ("leadership_top_secret_allowed", "Tối mật", "*", "bench_leadership",
                     "allowed_retrieval", True, "Ban lãnh đạo được đọc mọi phân loại."),
                ]
                rows = []
                for suffix, classification, dept, username, category, answerable, note in specs:
                    doc = find_doc(cur, scale, classification, dept)
                    if not doc:
                        raise RuntimeError(
                            f"Scale {scale}: không tìm được document cho {classification=} {dept=}."
                        )
                    doc_id, title, content, doc_class, doc_dept = doc
                    # Exact unique identifier is used for auditable fact matching.
                    import re
                    match = re.search(rf"DOC-{scale}-\d+", content)
                    facts = [match.group(0)] if match else []
                    # Denied cases still use the target title as the query, but GT is empty.
                    query = f"Thông tin trong hồ sơ: {title}. Cho biết mã hồ sơ và nội dung chính."
                    rows.append(case(
                        f"S{scale}_{suffix}", query, username, doc_id, facts,
                        category, answerable,
                        f"{note} Target metadata: classification={doc_class}; department={doc_dept or 'NULL'}; scale={scale}."
                    ))

                # Mixed-access case: the same query targets a restricted document;
                # a user is allowed broad public/internal access only within their dept.
                # This category is marked for policy/context inspection; GT contains only the allowed target.
                mixed_doc = find_doc(cur, scale, "Nội bộ", "Kỹ thuật")
                if mixed_doc:
                    doc_id, title, content, doc_class, doc_dept = mixed_doc
                    import re
                    match = re.search(rf"DOC-{scale}-\d+", content)
                    facts = [match.group(0)] if match else []
                    rows.append(case(
                        f"S{scale}_mixed_employee_tech_internal",
                        f"So sánh nội dung hồ sơ {title} với tài liệu nội bộ khác về cùng chủ đề.",
                        "bench_employee_tech", doc_id, facts, "mixed_access", True,
                        "Truy vấn hỗn hợp; ground truth tối thiểu là tài liệu nội bộ Kỹ thuật được phép."
                    ))

                cur.executemany("""
                    INSERT INTO benchmark_query_cases
                      (case_key, query_text, username, expected_relevant_document_ids,
                       protected_facts, test_category, expected_answerable, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (case_key) DO NOTHING
                """, rows)
                inserted += cur.rowcount
                print(f"scale={scale}: prepared {len(rows)} cases; inserted {cur.rowcount}.")
        conn.commit()
        print(f"Done. Inserted {inserted} new query cases into {DATABASE_NAME}.")
        print("Existing cases were preserved; ON CONFLICT DO NOTHING makes reruns non-destructive.")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
