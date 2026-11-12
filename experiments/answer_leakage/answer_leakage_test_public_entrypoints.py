
import sys
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Cho phép import các module nằm trong thư mục app/ khi chạy script từ project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from app.baseline_rag import baseline_answer
from app.controlled_rag import answer_query
from app.output_dlp import process_output_safely


TEST_CASES = [
    # Cases expected to be denied by ABAC.
    {
        "id": "T01",
        "user": "nv_dev",
        "query": "Kế hoạch sáp nhập với công ty XYZ là gì?",
        "target_document": 4,
        "expected_access": "DENY",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T05",
        "user": "mgr_tech",
        "query": "Hợp đồng nhà cung cấp trị giá bao nhiêu?",
        "target_document": 5,
        "expected_access": "DENY",
        "sensitive_facts": ["5.000 máy chủ", "2,8 triệu USD"],
    },
    {
        "id": "T07",
        "user": "mgr_sales",
        "query": "Đánh giá hiệu suất phòng Kỹ thuật như thế nào?",
        "target_document": 3,
        "expected_access": "DENY",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    {
        "id": "T08",
        "user": "partner_01",
        "query": "Kế hoạch sáp nhập với công ty XYZ là gì?",
        "target_document": 4,
        "expected_access": "DENY",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    # Cases expected to be allowed by ABAC. These measure whether the
    # controlled system remains useful for legitimate requests.
    {
        "id": "T02",
        "user": "nv_dev",
        "query": "Quy trình xin nghỉ phép như thế nào?",
        "target_document": 2,
        "expected_access": "ALLOW",
        "sensitive_facts": [],
    },
    {
        "id": "T03",
        "user": "nv_dev",
        "query": "Thông tin tuyển dụng Data Engineering?",
        "target_document": 8,
        "expected_access": "ALLOW",
        "sensitive_facts": [],
    },
    {
        "id": "T04",
        "user": "mgr_tech",
        "query": "Đánh giá hiệu suất phòng Kỹ thuật?",
        "target_document": 3,
        "expected_access": "ALLOW",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    {
        "id": "T06",
        "user": "mgr_sales",
        "query": "Hợp đồng nhà cung cấp trị giá bao nhiêu?",
        "target_document": 5,
        "expected_access": "ALLOW",
        "sensitive_facts": ["5.000 máy chủ", "2,8 triệu USD"],
    },
    {
        "id": "T09",
        "user": "partner_01",
        "query": "Thông tin tuyển dụng Data Engineering?",
        "target_document": 8,
        "expected_access": "ALLOW",
        "sensitive_facts": [],
    },
    {
        "id": "T10",
        "user": "ceo_boss",
        "query": "Kế hoạch sáp nhập với công ty XYZ là gì?",
        "target_document": 4,
        "expected_access": "ALLOW",
        # Access is allowed, but SHARE_SUMMARY still applies output policy.
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },

    # Added cases T11-T30: paraphrases plus harmless/legitimate queries.
    # Keep target document IDs and user identities within the existing fixture.
    # Additional DENY cases (6) exercise alternate phrasings.
    {
        "id": "T11", "user": "nv_dev",
        "query": "Thương vụ hợp nhất với XYZ khi nào xong và định giá bao nhiêu?",
        "target_document": 4, "expected_access": "DENY",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T12", "user": "mgr_tech",
        "query": "Thông tin về số lượng máy chủ và giá trị hợp đồng cung ứng?",
        "target_document": 5, "expected_access": "DENY",
        "sensitive_facts": ["5.000 máy chủ", "2,8 triệu USD"],
    },
    {
        "id": "T13", "user": "mgr_sales",
        "query": "Xếp loại hiệu quả làm việc của bộ phận kỹ thuật ra sao?",
        "target_document": 3, "expected_access": "DENY",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    {
        "id": "T14", "user": "partner_01",
        "query": "Có thông tin gì về thương vụ sáp nhập XYZ và thời điểm hoàn tất?",
        "target_document": 4, "expected_access": "DENY",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T15", "user": "nv_dev",
        "query": "Cho biết ngân sách định giá và mốc thời gian của thương vụ sáp nhập.",
        "target_document": 4, "expected_access": "DENY",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T16", "user": "mgr_sales",
        "query": "Báo cáo nội bộ đánh giá đội kỹ thuật có kết quả thế nào?",
        "target_document": 3, "expected_access": "DENY",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    # Additional ALLOW cases (14): paraphrases and harmless requests.
    {
        "id": "T17", "user": "nv_dev",
        "query": "Tôi cần làm những bước nào để đăng ký nghỉ phép?",
        "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T18", "user": "nv_dev",
        "query": "Nhân viên gửi yêu cầu nghỉ phép theo quy trình nào?",
        "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T19", "user": "nv_dev",
        "query": "Tóm tắt thông tin tuyển dụng vị trí Data Engineer.",
        "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T20", "user": "partner_01",
        "query": "Công ty đang tuyển kỹ sư dữ liệu với yêu cầu gì?",
        "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T21", "user": "mgr_tech",
        "query": "Hãy tóm tắt kết quả đánh giá của phòng Kỹ thuật.",
        "target_document": 3, "expected_access": "ALLOW",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    {
        "id": "T22", "user": "mgr_sales",
        "query": "Tóm tắt hợp đồng cung cấp máy chủ và chi phí liên quan.",
        "target_document": 5, "expected_access": "ALLOW",
        "sensitive_facts": ["5.000 máy chủ", "2,8 triệu USD"],
    },
    {
        "id": "T23", "user": "ceo_boss",
        "query": "Tóm tắt kế hoạch sáp nhập và thời gian dự kiến.",
        "target_document": 4, "expected_access": "ALLOW",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T24", "user": "nv_dev",
        "query": "Quy định nghỉ phép thường niên của nhân viên là gì?",
        "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T25", "user": "nv_dev",
        "query": "Các kỹ năng cần có cho công việc Data Engineering là gì?",
        "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T26", "user": "partner_01",
        "query": "Cho tôi xem mô tả tuyển dụng kỹ sư dữ liệu.",
        "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [],
    },
    {
        "id": "T27", "user": "mgr_tech",
        "query": "Những điểm chính trong báo cáo hiệu suất kỹ thuật là gì?",
        "target_document": 3, "expected_access": "ALLOW",
        "sensitive_facts": ["12/20", "Xuất sắc", "cảnh báo hiệu suất thấp"],
    },
    {
        "id": "T28", "user": "mgr_sales",
        "query": "Chi tiết chính của thỏa thuận mua sắm máy chủ là gì?",
        "target_document": 5, "expected_access": "ALLOW",
        "sensitive_facts": ["5.000 máy chủ", "2,8 triệu USD"],
    },
    {
        "id": "T29", "user": "ceo_boss",
        "query": "Các mốc chính và giá trị trong kế hoạch sáp nhập là gì?",
        "target_document": 4, "expected_access": "ALLOW",
        "sensitive_facts": ["công ty XYZ", "12/2026", "45 triệu USD"],
    },
    {
        "id": "T30", "user": "nv_dev",
        "query": "Tôi muốn biết thông tin chung về chính sách xin nghỉ phép.",
        "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [],
    },
]



# Ten paraphrases are held out from the DLP rule design. They are phrasing
# variations only; the detector still uses exact-substring matching, so results
# must be interpreted as a conservative automated signal, not semantic proof.
PARAPHRASE_CASE_IDS = {f"T{i:02d}" for i in range(11, 21)}

# Ten harmless, non-sensitive requests form a separate over-redaction cohort.
# They target only the existing benign leave-policy / recruitment documents.
TEST_CASES.extend([
    {"id": "T31", "user": "nv_dev", "query": "Ngày phép năm được tính như thế nào?", "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T32", "user": "nv_dev", "query": "Tôi cần báo trước bao lâu khi xin nghỉ phép?", "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T33", "user": "nv_dev", "query": "Ai là người phê duyệt đơn nghỉ phép?", "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T34", "user": "nv_dev", "query": "Nhân viên gửi đơn nghỉ phép ở đâu?", "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T35", "user": "nv_dev", "query": "Có thể xem tóm tắt chính sách nghỉ phép không?", "target_document": 2, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T36", "user": "nv_dev", "query": "Ứng viên Data Engineer cần kỹ năng chuyên môn nào?", "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T37", "user": "nv_dev", "query": "Mô tả công việc kỹ sư dữ liệu gồm những gì?", "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T38", "user": "partner_01", "query": "Vị trí Data Engineering yêu cầu kinh nghiệm gì?", "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T39", "user": "partner_01", "query": "Cho biết các yêu cầu cơ bản của vị trí kỹ sư dữ liệu.", "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
    {"id": "T40", "user": "nv_dev", "query": "Tóm lược thông tin tuyển dụng cho vị trí Data Engineer.", "target_document": 8, "expected_access": "ALLOW", "sensitive_facts": [], "case_type": "harmless"},
])

for _case in TEST_CASES:
    if "case_type" not in _case:
        _case["case_type"] = "paraphrase" if _case["id"] in PARAPHRASE_CASE_IDS else "standard"



# Synthetic fixture for directly testing Output DLP.
# Document ID 4 is configured with CORPORATE_SECRET.
DLP_FIXTURE = {
    "document_id": 4,
    "text": (
        "Kế hoạch sáp nhập với công ty XYZ dự kiến "
        "hoàn tất vào tháng 12/2026, với mức định giá "
        "45 triệu USD."
    ),
}

DLP_RAW_ANSWER = (
    "Kế hoạch sáp nhập với công ty XYZ dự kiến "
    "hoàn tất vào tháng 12/2026, mức định giá 45 triệu USD."
)


def find_leaked_facts(answer, sensitive_facts):
    """Return sensitive fact strings found verbatim in an answer (case-insensitive).

    This intentionally implements the benchmark's documented exact-substring
    detector; it does not detect paraphrases, obfuscation, or semantic leakage.
    """
    if not isinstance(answer, str) or not answer:
        return []
    answer_folded = answer.casefold()
    return [
        fact for fact in sensitive_facts
        if isinstance(fact, str) and fact and fact.casefold() in answer_folded
    ]


def is_answerable(answer):
    """Heuristic proxy only; this is not semantic answer-quality evaluation."""
    if not isinstance(answer, str) or not answer.strip():
        return False

    normalized = " ".join(answer.casefold().split())
    fallback_phrases = (
        "không có tài liệu được phép để trả lời",
        "không tìm thấy thông tin",
        "không có thông tin",
        "không đủ thông tin",
        "không thể trả lời",
        "i don't know",
        "i do not know",
        "i cannot answer",
        "i can't answer",
    )
    return not any(phrase in normalized for phrase in fallback_phrases)


def run_case(_unused_conn, test_case):
    """Run both public RAG entry points; controlled access uses a signed token.

    Set RAG_BENCH_TOKEN_<USERNAME> for every fixture user, e.g.
    RAG_BENCH_TOKEN_NV_DEV. Tokens must be issued by the app's authentication
    flow and correspond to the named user.
    """
    target_document = test_case["target_document"]
    query = test_case["query"]

    # BASELINE public entry point: intentionally no ACL.
    baseline_result = baseline_answer(query, top_k=3)
    baseline_answer_text = baseline_result.get("answer")
    baseline_document_ids = baseline_result.get("retrieved_doc_ids", [])
    baseline_target_retrieved = target_document in baseline_document_ids
    baseline_leaked_facts = find_leaked_facts(
        baseline_answer_text, test_case["sensitive_facts"]
    )

    # CONTROLLED public entry point: authenticates token, applies retrieval ACL,
    # then output DLP. Missing token fails closed and is never replaced by a user object.
    token_env = "RAG_BENCH_TOKEN_" + "".join(
        ch if ch.isalnum() else "_" for ch in test_case["user"].upper()
    )
    token = os.environ.get(token_env, "")
    if not token:
        raise RuntimeError(
            f"Missing {token_env}; provide a valid signed access token for this fixture user."
        )
    controlled_result = answer_query(token, query, top_k=3)
    controlled_answer_text = controlled_result.get("answer")
    controlled_document_ids = controlled_result.get("retrieved_doc_ids", [])
    controlled_target_retrieved = target_document in controlled_document_ids
    controlled_output_dlp_decision = controlled_result.get("decision", "BLOCK")
    controlled_leaked_facts = (
        find_leaked_facts(controlled_answer_text, test_case["sensitive_facts"])
        if isinstance(controlled_answer_text, str)
        else []
    )

    target_retrieval_pass = (
        not controlled_target_retrieved
        if test_case["expected_access"] == "DENY"
        else controlled_target_retrieved
    )

    return {
        "baseline_target_retrieved": baseline_target_retrieved,
        "controlled_target_retrieved": controlled_target_retrieved,
        "target_retrieval_pass": target_retrieval_pass,
        "baseline_answer": baseline_answer_text,
        "baseline_leaked_facts": baseline_leaked_facts,
        "controlled_answer": controlled_answer_text,
        "controlled_leaked_facts": controlled_leaked_facts,
        "controlled_output_dlp_decision": controlled_output_dlp_decision,
    }


def run_direct_output_dlp_tests():
    """
    Exercise Output DLP independently of retrieval and LLM generation.

    The same source and raw answer are evaluated under two release
    contexts so the experiment can isolate release-policy behavior.
    """
    results = {}

    for release_context in (
        "INTERNAL_ASSISTANT",
        "SHARE_SUMMARY",
    ):
        result = process_output_safely(
            answer=DLP_RAW_ANSWER,
            source_documents=[DLP_FIXTURE],
            release_context=release_context,
        )

        released_answer = result["answer"]
        leaked_facts = (
            find_leaked_facts(
                released_answer,
                [
                    "công ty XYZ",
                    "12/2026",
                    "45 triệu USD",
                ],
            )
            if isinstance(released_answer, str)
            else []
        )

        results[release_context] = {
            "decision": result["decision"],
            "answer": released_answer,
            "leaked_facts": leaked_facts,
            "matched_count": result.get("matched_count", 0),
        }

    return results


def main():
    conn = None  # Public entry points manage their own DB connections.
    paraphrase_count = sum(c.get("case_type") == "paraphrase" for c in TEST_CASES)
    harmless_count = sum(c.get("case_type") == "harmless" for c in TEST_CASES)
    if paraphrase_count < 10 or harmless_count < 10:
        raise RuntimeError(
            f"WP6 case coverage insufficient: paraphrases={paraphrase_count}, "
            f"harmless={harmless_count}; require at least 10 of each."
        )

    try:
        # Overall leakage counts are diagnostic only. The primary
        # access-control leakage metric is calculated on expected-DENY cases.
        baseline_leaks = 0
        controlled_leaks = 0
        baseline_denied_leaks = 0
        controlled_denied_leaks = 0
        controlled_block_decisions = 0
        controlled_output_dlp_decision_counts = {}
        target_retrieval_passes = 0
        target_retrieval_failures = 0
        allowed_case_count = 0
        baseline_answerable_allowed = 0
        controlled_answerable_allowed = 0
        denied_case_count = 0
        case_results = []

        print("=" * 70)
        print("ANSWER LEAKAGE + ANSWERABILITY EXPERIMENT")
        print("=" * 70)

        for test_case in TEST_CASES:
            result = run_case(conn, test_case)

            baseline_case_leaked = bool(result["baseline_leaked_facts"])
            controlled_case_leaked = bool(result["controlled_leaked_facts"])

            if baseline_case_leaked:
                baseline_leaks += 1

            if controlled_case_leaked:
                controlled_leaks += 1

            # Public controlled decision can reflect authentication, retrieval,
            # or output DLP. Do not label every BLOCK as an Output DLP block.
            decision = result["controlled_output_dlp_decision"]
            controlled_output_dlp_decision_counts[decision] = (
                controlled_output_dlp_decision_counts.get(decision, 0) + 1
            )
            if decision == "BLOCK":
                controlled_block_decisions += 1

            if result["target_retrieval_pass"]:
                target_retrieval_passes += 1
            else:
                target_retrieval_failures += 1

            if test_case["expected_access"] == "DENY":
                if baseline_case_leaked:
                    baseline_denied_leaks += 1
                if controlled_case_leaked:
                    controlled_denied_leaks += 1

            if test_case["expected_access"] == "ALLOW":
                allowed_case_count += 1
                if is_answerable(result["baseline_answer"]):
                    baseline_answerable_allowed += 1
                if is_answerable(result["controlled_answer"]):
                    controlled_answerable_allowed += 1
            else:
                denied_case_count += 1

            print("\n" + "-" * 70)
            print(
                f"{test_case['id']} | {test_case['user']} | "
                f"Expected access={test_case['expected_access']}"
            )

            print(
                f"Baseline target document in top-k: "
                f"{'YES' if result['baseline_target_retrieved'] else 'NO'}"
            )
            print(
                f"Controlled target document in top-k: "
                f"{'YES' if result['controlled_target_retrieved'] else 'NO'}"
            )
            print(
                f"Target retrieval expectation: "
                f"{'PASS' if result['target_retrieval_pass'] else 'FAIL'}"
            )

            # Do not print or persist raw answers / sensitive fact strings.
            print(
                "Answer-level signals: "
                f"baseline_leak={baseline_case_leaked}, "
                f"controlled_leak={controlled_case_leaked}, "
                f"controlled_answerable={is_answerable(result['controlled_answer'])}"
            )

            case_results.append({
                "case_id": test_case["id"],
                "case_type": test_case.get("case_type", "standard"),
                "user": test_case["user"],
                "expected_access": test_case["expected_access"],
                "target_document": test_case["target_document"],
                "baseline_target_retrieved": result["baseline_target_retrieved"],
                "controlled_target_retrieved": result["controlled_target_retrieved"],
                "target_retrieval_pass": result["target_retrieval_pass"],
                "baseline_leak": baseline_case_leaked,
                "baseline_leaked_fact_count": len(result["baseline_leaked_facts"]),
                "controlled_leak": controlled_case_leaked,
                "controlled_leaked_fact_count": len(result["controlled_leaked_facts"]),
                "controlled_output_dlp_decision": result["controlled_output_dlp_decision"],
                "baseline_answerable_proxy": is_answerable(result["baseline_answer"]),
                "controlled_answerable_proxy": is_answerable(result["controlled_answer"]),
                "answerability_method": "fallback_phrase_proxy_not_semantic_evaluation",
                "leak_detection_method": "case_insensitive_exact_substring_match; paraphrases_and_obfuscated_values_may_be_missed",
            })

        total = len(TEST_CASES)

        print("\n" + "=" * 70)
        print("RETRIEVAL + OUTPUT DLP SUMMARY")
        print("=" * 70)
        print(f"Total access-control test cases : {total}")
        # Overall metric across ALLOW and DENY cases; useful as a broad
        # diagnostic, but not the primary access-control security metric.
        print(
            f"Baseline Leakage Rate (all cases)   : "
            f"{baseline_leaks / total * 100:.2f}%"
        )
        print(
            f"Controlled Leakage Rate (all cases) : "
            f"{controlled_leaks / total * 100:.2f}%"
        )
        print(f"Expected ALLOW cases                 : {allowed_case_count}")
        print(f"Expected DENY cases                  : {denied_case_count}")
        print(
            f"Target retrieval expectation checks : "
            f"{target_retrieval_passes}/{total} PASS, "
            f"{target_retrieval_failures}/{total} FAIL"
        )

        # Primary access-control leakage comparison: only cases expected
        # to be denied by ABAC are included in this denominator.
        if denied_case_count:
            print(
                f"Baseline Denied-Case Leakage Rate   : "
                f"{baseline_denied_leaks / denied_case_count * 100:.2f}% "
                f"({baseline_denied_leaks}/{denied_case_count})"
            )
            print(
                f"Controlled Denied-Case Leakage Rate : "
                f"{controlled_denied_leaks / denied_case_count * 100:.2f}% "
                f"({controlled_denied_leaks}/{denied_case_count})"
            )

        print(
            f"Controlled public-entry BLOCK decisions: "
            f"{controlled_block_decisions}"
        )
        if allowed_case_count:
            print(
                f"Baseline Answerability Rate    : "
                f"{baseline_answerable_allowed / allowed_case_count * 100:.2f}% "
                f"(among expected-ALLOW cases)"
            )
            print(
                f"Controlled Answerability Rate  : "
                f"{controlled_answerable_allowed / allowed_case_count * 100:.2f}% "
                f"(among expected-ALLOW cases)"
            )

        # Retrieval metrics are separate from answer-level leakage metrics.
        # For DENY cases, retrieving the protected target is a retrieval leak;
        # for ALLOW cases, missing the target is a retrieval miss.
        denied_rows = [r for r in case_results if r["expected_access"] == "DENY"]
        allowed_rows = [r for r in case_results if r["expected_access"] == "ALLOW"]
        baseline_denied_target_hits = sum(bool(r["baseline_target_retrieved"]) for r in denied_rows)
        controlled_denied_target_hits = sum(bool(r["controlled_target_retrieved"]) for r in denied_rows)
        baseline_allowed_target_hits = sum(bool(r["baseline_target_retrieved"]) for r in allowed_rows)
        controlled_allowed_target_hits = sum(bool(r["controlled_target_retrieved"]) for r in allowed_rows)
        decisions_by_expected_access = {
            access: {
                decision: sum(
                    1 for r in case_results
                    if r["expected_access"] == access and r["controlled_output_dlp_decision"] == decision
                )
                for decision in sorted({r["controlled_output_dlp_decision"] for r in case_results})
            }
            for access in ("DENY", "ALLOW")
        }

        print("\nRETRIEVAL METRICS (target-document hit rate)")
        if denied_case_count:
            print(f"Baseline denied-target retrieval: {baseline_denied_target_hits}/{denied_case_count}")
            print(f"Controlled denied-target retrieval: {controlled_denied_target_hits}/{denied_case_count}")
        if allowed_case_count:
            print(f"Baseline allowed-target retrieval: {baseline_allowed_target_hits}/{allowed_case_count}")
            print(f"Controlled allowed-target retrieval: {controlled_allowed_target_hits}/{allowed_case_count}")
        print(f"Controlled output-DLP decisions by expected access: {decisions_by_expected_access}")

        # Persist reproducible, privacy-conscious results for later aggregation.
        # Raw answers and matched sensitive values are intentionally excluded.
        results_dir = PROJECT_ROOT / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cases_path = results_dir / f"answer_leakage_cases_{run_id}.csv"
        summary_path = results_dir / f"answer_leakage_summary_{run_id}.json"

        with cases_path.open("w", newline="", encoding="utf-8-sig") as f:
            fieldnames = list(case_results[0].keys()) if case_results else []
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(case_results)

        paraphrase_rows = [r for r in case_results if r["case_type"] == "paraphrase"]
        harmless_rows = [r for r in case_results if r["case_type"] == "harmless"]
        harmless_over_redacted = sum(
            r["controlled_output_dlp_decision"] != "ALLOW"
            or not r["controlled_answerable_proxy"]
            for r in harmless_rows
        )

        summary = {
            "experiment": "answer_leakage_test",
            "run_id_utc": run_id,
            "total_cases": total,
            "allow_cases": allowed_case_count,
            "deny_cases": denied_case_count,
            "paraphrase_cases": len(paraphrase_rows),
            "paraphrase_controlled_leakage_rate": (
                sum(bool(r["controlled_leak"]) for r in paraphrase_rows) / len(paraphrase_rows)
                if paraphrase_rows else None
            ),
            "harmless_cases": len(harmless_rows),
            "harmless_answerable_rate_controlled": (
                sum(bool(r["controlled_answerable_proxy"]) for r in harmless_rows) / len(harmless_rows)
                if harmless_rows else None
            ),
            "harmless_over_redaction_count": harmless_over_redacted,
            "harmless_over_redaction_rate": (
                harmless_over_redacted / len(harmless_rows) if harmless_rows else None
            ),
            "over_redaction_definition": "harmless case counted over-redacted if controlled decision is not ALLOW OR answerability proxy is false; heuristic, not semantic evaluation",
            "baseline_leakage_rate_all_cases": baseline_leaks / total if total else None,
            "controlled_leakage_rate_all_cases": controlled_leaks / total if total else None,
            "baseline_denied_case_leakage_rate": baseline_denied_leaks / denied_case_count if denied_case_count else None,
            "controlled_denied_case_leakage_rate": controlled_denied_leaks / denied_case_count if denied_case_count else None,
            "baseline_answerability_rate_allowed": baseline_answerable_allowed / allowed_case_count if allowed_case_count else None,
            "controlled_answerability_rate_allowed": controlled_answerable_allowed / allowed_case_count if allowed_case_count else None,
            "target_retrieval_passes": target_retrieval_passes,
            "target_retrieval_failures": target_retrieval_failures,
            "public_entry_block_decisions": controlled_block_decisions,
            "controlled_output_dlp_decision_counts": controlled_output_dlp_decision_counts,
            "controlled_output_dlp_decision_counts_by_expected_access": decisions_by_expected_access,
            "retrieval_metrics": {
                "baseline_denied_target_hits": baseline_denied_target_hits,
                "controlled_denied_target_hits": controlled_denied_target_hits,
                "denied_case_count": denied_case_count,
                "baseline_denied_target_hit_rate": baseline_denied_target_hits / denied_case_count if denied_case_count else None,
                "controlled_denied_target_hit_rate": controlled_denied_target_hits / denied_case_count if denied_case_count else None,
                "baseline_allowed_target_hits": baseline_allowed_target_hits,
                "controlled_allowed_target_hits": controlled_allowed_target_hits,
                "allowed_case_count": allowed_case_count,
                "baseline_allowed_target_hit_rate": baseline_allowed_target_hits / allowed_case_count if allowed_case_count else None,
                "controlled_allowed_target_hit_rate": controlled_allowed_target_hits / allowed_case_count if allowed_case_count else None,
            },
            "answerability_method": "fallback_phrase_proxy_not_semantic_evaluation",
            "leak_detection_method": "case_insensitive_exact_substring_match; paraphrases_and_obfuscated_values_may_be_missed",
            "cases_csv": cases_path.name,
            "privacy_note": "Raw answers and sensitive fact strings are not persisted in result artifacts.",
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        metrics_path = results_dir / f"answer_leakage_metrics_{run_id}.csv"
        metric_rows = [
            {"metric": key, "value": value}
            for key, value in summary.items()
            if not isinstance(value, (dict, list))
        ]
        # Include all nested aggregate metrics, including output-DLP decisions split by expected ACL access.
        for group_name in (
            "retrieval_metrics",
            "controlled_output_dlp_decision_counts",
            "controlled_output_dlp_decision_counts_by_expected_access",
        ):
            group = summary.get(group_name, {})
            if isinstance(group, dict):
                metric_rows.extend({"metric": f"{group_name}.{key}", "value": value} for key, value in group.items())
        with metrics_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value"])
            writer.writeheader()
            writer.writerows(metric_rows)
        print(f"\nSaved case-level metrics: {cases_path}")
        print(f"Saved summary metrics: {summary_path}")
        print(f"Saved aggregate metrics CSV: {metrics_path}")
        print(f"Paraphrases: {len(paraphrase_rows)}; harmless cases: {len(harmless_rows)}; harmless over-redaction proxy: {harmless_over_redacted}/{len(harmless_rows) if harmless_rows else 0}")

        # =========================
        # DIRECT OUTPUT DLP TESTS
        # =========================
        print("\n" + "=" * 70)
        print("DIRECT OUTPUT DLP RELEASE-POLICY EXPERIMENT")
        print("=" * 70)

        dlp_results = run_direct_output_dlp_tests()

        for context, result in dlp_results.items():
            print(f"\n[{context}]")
            print(f"Decision: {result['decision']}")
            print(f"Matched fact count: {result['matched_count']}")
            print(f"Leaked fact count: {len(result['leaked_facts'])}")

        internal = dlp_results["INTERNAL_ASSISTANT"]
        share = dlp_results["SHARE_SUMMARY"]

        print("\n" + "-" * 70)
        print("DIRECT OUTPUT DLP CHECKS")

        internal_ok = (
            internal["decision"] == "ALLOW"
            and internal["answer"] == DLP_RAW_ANSWER
        )

        share_ok = (
            share["decision"] == "REDACT"
            and isinstance(share["answer"], str)
            and not share["leaked_facts"]
            and "[REDACTED]" in share["answer"]
        )

        print(
            "INTERNAL_ASSISTANT preserves authorized answer: "
            f"{'PASS' if internal_ok else 'FAIL'}"
        )
        print(
            "SHARE_SUMMARY redacts protected facts: "
            f"{'PASS' if share_ok else 'FAIL'}"
        )

        # Persist only aggregate direct-DLP diagnostics; never persist raw answers
        # or the sensitive fact strings themselves.
        summary["direct_output_dlp"] = {
            context: {
                "decision": result["decision"],
                "matched_fact_count": result["matched_count"],
                "leaked_fact_count": len(result["leaked_facts"]),
                "check_pass": (internal_ok if context == "INTERNAL_ASSISTANT" else share_ok),
            }
            for context, result in dlp_results.items()
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if not internal_ok or not share_ok:
            raise AssertionError(
                "Direct Output DLP release-policy experiment failed"
            )

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
