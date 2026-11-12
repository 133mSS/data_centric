"""WP6 retrieval ACL matrix: 6 users x 4 labels x up to 10 docs/cell.

Ground truth below is deliberately independent of app.policy/app.pdp.
Run after the benchmark corpus and users are seeded and embeddings exist.
"""
import csv
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import psycopg2
from db_config import get_benchmark_db_config
from retrieval import get_allowed_document_ids

DATABASE_NAME = "baomatdulieu_benchmark"
SEED = 4206
SAMPLE_PER_CELL = 10
USER_KEYS = (
    ("bench_partner", "Đối tác", None),
    ("bench_employee_tech", "Nhân viên", "Kỹ thuật"),
    ("bench_employee_sales", "Nhân viên", "Kinh doanh"),
    ("bench_manager_tech", "Manager", "Kỹ thuật"),
    ("bench_manager_sales", "Manager", "Kinh doanh"),
    ("bench_leadership", "Ban lãnh đạo", "Toàn công ty"),
)
LEVEL = {"Công khai": 0, "Nội bộ": 1, "Mật": 2, "Tối mật": 3}
CLEARANCE = {"Đối tác": 0, "Nhân viên": 1, "Manager": 2, "Ban lãnh đạo": 3}
CLASSIFICATIONS = ("Công khai", "Nội bộ", "Mật", "Tối mật")


def expected_allow(role, user_department, classification, document_department):
    # Hand-written oracle, not imported from the policy implementation.
    if CLEARANCE.get(role, -1) < LEVEL.get(classification, 99):
        return False
    if document_department is None or document_department == "Toàn công ty":
        return True
    if user_department == "Toàn công ty":
        return True
    return user_department == document_department


def main():
    rng = random.Random(SEED)
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    output = out_dir / f"wp6_retrieval_matrix_seed{SEED}.csv"
    rows = []
    # Keep the application's default database untouched. This experiment must
    # connect explicitly to the benchmark database, not the 8-document app DB.
    db_config = get_benchmark_db_config()
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            actual_database = cur.fetchone()[0]
            if actual_database != DATABASE_NAME:
                raise RuntimeError(
                    f"Safety stop: connected to {actual_database!r}, "
                    f"expected benchmark database {DATABASE_NAME!r}."
                )
            cur.execute("SELECT id, classification, department FROM documents")
            docs = cur.fetchall()
            by_label = {label: [row for row in docs if row[1] == label] for label in CLASSIFICATIONS}
            for label, candidates in by_label.items():
                if len(candidates) < SAMPLE_PER_CELL:
                    raise RuntimeError(
                        f"Nhãn {label!r} chỉ có {len(candidates)} tài liệu; "
                        f"cần ít nhất {SAMPLE_PER_CELL}. Hãy seed benchmark corpus trước."
                    )
            cur.execute("SELECT id, username, role, department FROM users WHERE username = ANY(%s)",
                        ([item[0] for item in USER_KEYS],))
            db_users = {row[1]: {"id": row[0], "username": row[1], "role": row[2], "department": row[3]}
                        for row in cur.fetchall()}
        missing = [name for name, _, _ in USER_KEYS if name not in db_users]
        if missing:
            raise RuntimeError(f"Thiếu benchmark users: {missing}")
        for username, role, department in USER_KEYS:
            user = db_users[username]
            actual_allowed = set(get_allowed_document_ids(conn, user))
            for label in CLASSIFICATIONS:
                sample = rng.sample(by_label[label], SAMPLE_PER_CELL)
                for doc_id, classification, doc_department in sample:
                    expected = expected_allow(role, department, classification, doc_department)
                    actual = doc_id in actual_allowed
                    rows.append({
                        "seed": SEED, "username": username, "role": role,
                        "user_department": department or "NULL", "document_id": doc_id,
                        "classification": classification,
                        "document_department": doc_department or "NULL",
                        "expected": "ALLOW" if expected else "DENY",
                        "actual": "ALLOW" if actual else "DENY",
                        "pass": expected == actual,
                    })
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    failures = [row for row in rows if not row["pass"]]
    print(f"Database: {DATABASE_NAME}")
    print(f"WP6 retrieval matrix: {len(rows)} checks; seed={SEED}; sample/cell={SAMPLE_PER_CELL}")
    print(f"PASS={len(rows)-len(failures)} FAIL={len(failures)}")
    print(f"CSV: {output}")
    if failures:
        for row in failures[:20]:
            print(row)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
