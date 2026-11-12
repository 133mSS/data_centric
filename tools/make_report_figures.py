"""Generate monochrome report figures from the newest saved experiment artifacts.

The script does not run experiments and never fabricates data. It selects the
newest timestamped answer-leakage CSV, and the latest run ID recorded in the
final prompt-injection exports.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "figures"
OUT.mkdir(parents=True, exist_ok=True)

GROUP_LABELS = {
    "direct_override": "Direct override",
    "dlp_attack": "DLP attack",
    "forged_metadata": "Forged metadata",
    "identity_impersonation": "Identity impersonation",
    "indirect_injection": "Indirect injection",
    "multilingual": "Multilingual",
    "obfuscation": "Obfuscation",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def numeric_rate(value: str | None) -> float:
    try:
        result = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return result if np.isfinite(result) else 0.0


def latest_timestamped_case_csv() -> Path | None:
    candidates = list(RESULTS.rglob("answer_leakage_cases_*.csv"))
    return max(candidates, key=lambda item: item.stem) if candidates else None


def save_answer_leakage(path: Path) -> None:
    rows = read_csv(path)
    if not rows or not {"baseline_leak", "controlled_leak"}.issubset(rows[0]):
        raise ValueError(f"Unexpected answer leakage schema: {path}")

    baseline = sum(str(row["baseline_leak"]).strip().lower() in {"true", "1", "yes"} for row in rows)
    controlled = sum(str(row["controlled_leak"]).strip().lower() in {"true", "1", "yes"} for row in rows)
    total = len(rows)
    values = [baseline, controlled]

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    bars = ax.bar(
        ["Baseline", "Controlled"], values,
        facecolor="white", edgecolor="black", hatch="///", linewidth=1.1,
    )
    ax.set_title(f"Answer leakage (n={total}; source: {path.name})", fontsize=10)
    ax.set_ylabel("Cases flagged by exact-match detector")
    ax.set_ylim(0, max(2, total * 1.08))
    ax.grid(axis="y", linestyle=":", color="0.65")
    ax.set_axisbelow(True)
    for bar, count in zip(bars, values):
        ax.annotate(
            f"{count}/{total} ({count / total:.1%})",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(OUT / "wp8_answer_leakage.png", dpi=200, facecolor="white")
    plt.close(fig)


def save_prompt_injection_overall(runs_path: Path) -> str:
    runs = read_csv(runs_path)
    if not runs:
        raise ValueError(f"No prompt injection runs in {runs_path}")
    latest_run = max(row.get("run_id", "") for row in runs)
    selected = [row for row in runs if row.get("run_id") == latest_run]
    systems = [row.get("system", "") for row in selected]
    values = [numeric_rate(row.get("asr")) * 100 for row in selected]
    order = sorted(zip(systems, values, selected), key=lambda item: item[0])
    systems = [item[0].title() for item in order]
    values = [item[1] for item in order]
    selected = [item[2] for item in order]

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    bars = ax.bar(
        systems, values,
        facecolor="white", edgecolor="black", hatch="///", linewidth=1.1,
    )
    ax.set_title(f"Prompt injection ASR — run {latest_run}")
    ax.set_ylabel("Attack success rate (%)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle=":", color="0.65")
    ax.set_axisbelow(True)
    for bar, val, row in zip(bars, values, selected):
        low = row.get("wilson95_low")
        high = row.get("wilson95_high")
        if low not in (None, "") and high not in (None, ""):
            label = f"{val:.1f}%\n95% CI {numeric_rate(low) * 100:.1f}–{numeric_rate(high) * 100:.1f}%"
        else:
            label = f"{val:.1f}%"
        ax.annotate(
            label, (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(OUT / "wp8_prompt_injection_asr.png", dpi=200, facecolor="white")
    plt.close(fig)
    return latest_run


def save_prompt_injection_groups(groups_path: Path, latest_run: str) -> None:
    rows = [row for row in read_csv(groups_path) if row.get("run_id") == latest_run]
    groups = list(dict.fromkeys(row.get("group", "") for row in rows))
    if not rows or not groups:
        raise ValueError(f"No prompt injection group data for run {latest_run} in {groups_path}")

    systems = ["baseline", "controlled"]
    lookup = {
        (row.get("group", ""), row.get("system", "")): numeric_rate(row.get("asr")) * 100
        for row in rows
    }
    x = np.arange(len(groups))
    width = 0.36
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    bars1 = ax.bar(
        x - width / 2, [lookup.get((group, "baseline"), 0) for group in groups], width,
        label="Baseline", facecolor="white", edgecolor="black", hatch="///", linewidth=1.0,
    )
    bars2 = ax.bar(
        x + width / 2, [lookup.get((group, "controlled"), 0) for group in groups], width,
        label="Controlled", facecolor="0.78", edgecolor="black", linewidth=1.0,
    )
    labels = [GROUP_LABELS.get(group, group.replace("_", " ").title()) for group in groups]
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylabel("Attack success rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title(f"Prompt injection ASR by attack group — run {latest_run}")
    ax.grid(axis="y", linestyle=":", color="0.65")
    ax.set_axisbelow(True)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "wp8_prompt_injection_by_group.png", dpi=200, facecolor="white")
    plt.close(fig)


def main() -> None:
    written: list[str] = []
    answer_path = latest_timestamped_case_csv()
    if answer_path:
        save_answer_leakage(answer_path)
        written.append(f"wp8_answer_leakage.png <- {answer_path.relative_to(ROOT)}")

    runs_path = RESULTS / "final" / "wp8_prompt_injection_runs.csv"
    groups_path = RESULTS / "final" / "wp8_prompt_injection_by_group.csv"
    if runs_path.exists() and groups_path.exists():
        latest_run = save_prompt_injection_overall(runs_path)
        save_prompt_injection_groups(groups_path, latest_run)
        written.append(f"wp8_prompt_injection_asr.png <- {runs_path.relative_to(ROOT)} (run {latest_run})")
        written.append(f"wp8_prompt_injection_by_group.png <- {groups_path.relative_to(ROOT)} (run {latest_run})")

    if not written:
        raise SystemExit("No recognized result artifacts were found; no figures generated.")
    status = "Generated by tools/make_report_figures.py. This script visualizes saved artifacts; it does not run experiments.\n" + "\n".join(written) + "\n"
    (OUT / "GENERATION_STATUS.txt").write_text(status, encoding="utf-8")
    print(status, end="")


if __name__ == "__main__":
    main()
