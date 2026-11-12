import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from structured_fact_extractor import extract_structured_facts

samples = [
    "45 triệu USD",
    "tháng 12/2026",
    "năm 2027",
    "5.000 máy chủ",
    "12/20 nhân viên",
    "22:00 đến 23:30",
]

for sample in samples:
    print(f"\nINPUT: {sample}")
    for fact in extract_structured_facts(sample):
        print(fact)
