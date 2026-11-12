import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from output_dlp import process_output


# Synthetic source corresponding to document 4:
# CORPORATE_SECRET.
source_documents = [
    {
        "document_id": 4,
        "text": (
            "Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất "
            "tháng 12/2026, mức định giá thương lượng là 45 triệu USD."
        ),
    }
]

answer = (
    "Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất "
    "vào tháng 12/2026, với mức định giá 45 triệu USD."
)

# 1. INTERNAL_ASSISTANT must not redact.
internal_result = process_output(
    answer=answer,
    source_documents=source_documents,
    release_context="INTERNAL_ASSISTANT",
)

assert internal_result["decision"] == "ALLOW"
assert internal_result["answer"] == answer

# 2. SHARE_SUMMARY must redact matched protected facts.
share_result = process_output(
    answer=answer,
    source_documents=source_documents,
    release_context="SHARE_SUMMARY",
)

assert share_result["decision"] == "REDACT"
assert share_result["matched_count"] > 0
assert "[REDACTED]" in share_result["answer"]
assert "45 triệu USD" not in share_result["answer"]

# 3. An unrelated answer with no protected matches remains unchanged.
unrelated_answer = "Hôm nay nhóm tổ chức cuộc họp dự án."

unrelated_result = process_output(
    answer=unrelated_answer,
    source_documents=source_documents,
    release_context="SHARE_SUMMARY",
)

assert unrelated_result["decision"] == "ALLOW"
assert unrelated_result["answer"] == unrelated_answer

# 4. Invalid context must be rejected.
try:
    process_output(
        answer=answer,
        source_documents=source_documents,
        release_context="UNKNOWN_CONTEXT",
    )
    raise AssertionError("Unknown context must be rejected")
except ValueError:
    pass

# 5. Missing source documents must be rejected.
try:
    process_output(
        answer=answer,
        source_documents=[],
        release_context="INTERNAL_ASSISTANT",
    )
    raise AssertionError("Missing sources must be rejected")
except ValueError:
    pass

print("ALL OUTPUT DLP INTEGRATION TESTS PASSED")
