"""Inspect the local Demo's ACL-filtered exact/hybrid retrieval without generating an answer.

This diagnostic deliberately targets baomatdulieu_demo, the same database used by
Demo UI / answer_internal_query(). It never connects to the application or
benchmark database and never prints chunk contents, tokens or credentials.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="nv_dev")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    if not args.query.strip():
        parser.error("--query cannot be empty")
    if args.top_k < 1 or args.top_k > 20:
        parser.error("--top-k must be between 1 and 20")

    import psycopg2
    from db_config import DEMO_DATABASE_NAME, get_demo_db_config, require_database
    from retrieval import get_allowed_document_ids
    from vector_search import get_user, vector_search

    config = get_demo_db_config()
    if config.get("dbname") != DEMO_DATABASE_NAME:
        raise SystemExit(
            f"Safety stop: Demo diagnostic must use {DEMO_DATABASE_NAME!r}."
        )

    conn = psycopg2.connect(connect_timeout=5, application_name="demo_rag_diagnostic", **config)
    try:
        actual_database = require_database(
            conn, DEMO_DATABASE_NAME, operation="Demo retrieval diagnostic"
        )
        user = get_user(conn, args.username)
        allowed_ids = set(get_allowed_document_ids(conn, user))
        query = args.query.strip()
        rows = vector_search(conn, user, query, top_k=args.top_k)

        full_codes = re.findall(
            r"(?<![A-Z0-9])DOC-\d{4,}-\d{5,}(?!\d)", query, flags=re.IGNORECASE
        )
        record_ids = re.findall(r"(?<!\d)\d{5,}(?!\d)", query)
        mode = "EXACT_RECORD" if full_codes or record_ids else "HYBRID_SEMANTIC"

        print(f"Database: {actual_database}")
        print(f"User: {user['username']} | role={user['role']} | department={user['department']}")
        print(f"Retrieval mode: {mode}")
        if full_codes:
            print(f"Exact document code(s): {', '.join(full_codes)}")
        elif record_ids:
            print(f"Exact record number(s): {', '.join(record_ids)}")
        print(f"Allowed document IDs: {len(allowed_ids)}")
        print(f"Query: {query}")
        print(f"Returned authorized chunks: {len(rows)}")
        print("\nRANK | DOC_ID | CLASSIFICATION | DEPARTMENT | SIMILARITY | TITLE")
        print("-" * 140)

        for rank, row in enumerate(rows, start=1):
            document_id = row[1]
            title = str(row[2]).replace("\n", " ")
            classification = row[3]
            department = row[4] or "Không gán"
            similarity = float(row[6]) if row[6] is not None else 0.0
            print(
                f"{rank:>4} | {document_id:>6} | {str(classification):<14} | "
                f"{str(department):<12} | {similarity:>10.4f} | {title}"
            )

        if mode == "EXACT_RECORD":
            if rows:
                returned_doc_ids = sorted({int(row[1]) for row in rows})
                print(f"\nEXACT_LOOKUP: MATCH | authorized document id(s)={returned_doc_ids}")
                if len(returned_doc_ids) > 1:
                    print("NOTE: Multiple allowed documents share this short record number; review titles to distinguish them.")
            else:
                print("\nEXACT_LOOKUP: NO_RESULT | no matching record exists inside this user's ABAC allow-list.")
                print("The retrieval layer must not substitute a semantically similar record.")
        elif rows:
            print("\nHYBRID_LOOKUP: candidates returned from the ABAC-filtered semantic/title ranking.")
        else:
            print("\nHYBRID_LOOKUP: NO_RESULT | no matching chunk found inside this user's ABAC allow-list.")

        print("\nDiagnostic is read-only: no audit rows, documents, chunks or embeddings were modified.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
