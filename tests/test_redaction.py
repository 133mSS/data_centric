import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from redaction import redact_answer

answer = (
    "Kế hoạch sáp nhập với công ty XYZ "
    "dự kiến hoàn tất vào tháng 12/2026, "
    "với mức định giá 45 triệu USD."
)

sensitive_facts = [
    {
        "type": "sensitive_phrase",
        "value": "Kế hoạch sáp nhập",
    },
    {
        "type": "named_entity",
        "value": "công ty XYZ",
    },
    {
        "type": "date",
        "value": "12/2026",
    },
    {
        "type": "money",
        "value": "45 triệu USD",
    },
]

redacted = redact_answer(answer, sensitive_facts)

print("===== RAW ANSWER =====")
print(answer)

print("\n===== REDACTED ANSWER =====")
print(redacted)