"""Inspect ACL-filtered live retrieval ranking without generating an answer.

Prints only document metadata and cosine similarity. It does not write audit
records, modify PostgreSQL rows, or print chunk content/credentials.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
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
    from db_config import get_db_config
    from retrieval import get_allowed_document_ids
    from vector_search import get_user, vector_search

    config = get_db_config()
    if config.get("dbname") != "baomatdulieu":
        raise SystemExit(
            "Safety stop: diagnostics must use application database 'baomatdulieu', "
            "not the benchmark database."
        )

    conn = psycopg2.connect(connect_timeout=5, **config)
    try:
        user = get_user(conn, args.username)
        allowed_ids = set(get_allowed_document_ids(conn, user))
        rows = vector_search(conn, user, args.query.strip(), top_k=args.top_k)

        print(f"Database: {config['dbname']}")
        print(f"User: {user['username']} | role={user['role']} | department={user['department']}")
        print(f"Allowed document IDs: {len(allowed_ids)}")
        print(f"Query: {args.query.strip()}")
        print(f"Returned authorized chunks: {len(rows)}")
        print("\nRANK | DOC_ID | CLASSIFICATION | SIMILARITY | TITLE")
        print("-" * 100)
        for rank, row in enumerate(rows, start=1):
            document_id = row[1]
            title = str(row[2]).replace("\n", " ")
            classification = row[3]
            similarity = float(row[6])
            print(
                f"{rank:>4} | {document_id:>6} | {str(classification):<14} | "
                f"{similarity:>10.4f} | {title}"
            )

        expected_title = "Mã nguồn hệ thống RAG"
        title_hit = any(str(row[2]).casefold() == expected_title.casefold() for row in rows)
        print("\nExact target title in returned Top-K:", "YES" if title_hit else "NO")
        if not title_hit and expected_title.casefold() in args.query.casefold():
            print(
                "DIAGNOSIS: exact-title target is not in the ACL-filtered vector Top-K. "
                "Inspect embedding consistency/ranking before changing the LLM prompt."
            )
        elif title_hit:
            print(
                "DIAGNOSIS: target document is retrieved. If the answer still says "
                "there is insufficient information, inspect the generation prompt/context."
            )
        print("\nNo chunk text, credentials, tokens, or audit records were printed or changed.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
