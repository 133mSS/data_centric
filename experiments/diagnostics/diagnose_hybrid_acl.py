from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import re
import sys

from benchmark_v1.run_retrieval_benchmark import (
    connect,
    load_cases,
    load_user,
    load_document_metadata,
    case_scale,
    allowed_document_ids,
    embed_query,
    hybrid_search,
    evaluate,
    SCALE_SEEDS,
)


def main():
    target_cases = {
        "S10000_partner_internal_denied": 6002,
        "S10000_employee_tech_internal_allowed": 6006,
    }

    conn = connect()

    try:
        with conn.cursor() as cur:
            cases = load_cases(cur)
            documents = load_document_metadata(cur)

            cases_by_key = {
                row[1]: row for row in cases
            }

            for case_key, target_doc_id in target_cases.items():
                if case_key not in cases_by_key:
                    print(f"\n[ERROR] Không tìm thấy case: {case_key}")
                    continue

                row = cases_by_key[case_key]
                (
                    case_id, _, query, username, expected_ids,
                    facts, category, answerable, notes
                ) = row

                scale = case_scale(case_key)
                candidate_ids = [
                    doc_id
                    for doc_id, doc in documents.items()
                    if doc["benchmark_scale"] == scale
                ]

                user = load_user(cur, username)
                allowed_ids = allowed_document_ids(user, documents)

                permitted_ids = set(candidate_ids) & set(allowed_ids)
                target = documents.get(target_doc_id)

                print("\n" + "=" * 65)
                print(f"CASE: {case_key}")
                print(f"User: {username}")
                print(f"Role: {user['role']}")
                print(f"Target document: {target_doc_id}")
                print(f"Target metadata: {target}")
                print(
                    "Target allowed in cohort:",
                    target_doc_id in permitted_ids,
                )

                query_vector = embed_query(query)

                rows = hybrid_search(
                    cur,
                    query,
                    query_vector,
                    3,
                    candidate_ids,
                    allowed_ids,
                )

                metrics = evaluate(
                    rows,
                    expected_ids,
                    facts,
                    user,
                    documents,
                    category,
                )

                returned_ids = metrics["returned_document_ids"]

                print("Returned document IDs:", returned_ids)
                print("Returned chunk IDs:", metrics["returned_chunk_ids"])
                print(
                    "Unauthorized chunk IDs:",
                    metrics["unauthorized_chunk_ids"],
                )
                print(
                    "Protected facts leaked:",
                    metrics["protected_facts_leaked_exact"],
                )
                print(
                    "Target returned:",
                    target_doc_id in returned_ids,
                )

                if category == "denied_retrieval":
                    passed = (
                        target_doc_id not in returned_ids
                        and not metrics["unauthorized_chunk_ids"]
                        and metrics["protected_facts_leaked_exact"] == 0
                    )
                else:
                    passed = (
                        target_doc_id in returned_ids
                        and not metrics["unauthorized_chunk_ids"]
                    )

                print("RESULT:", "PASS" if passed else "FAIL")

        print("\nDiagnostic hoàn tất. Không ghi benchmark results.")

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
