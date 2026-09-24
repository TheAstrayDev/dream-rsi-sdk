"""Plot the separately frozen diverse-signal Bonsai experiment."""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402, I001

ROOT = Path(__file__).resolve().parents[2]
REPORT = (
    ROOT
    / "docs"
    / "experiments"
    / "ternary-bonsai-diverse-2026-09-24"
    / "generation-and-audit.json"
)
OUTPUT = ROOT / "assets" / "ternary-bonsai-diverse-local"


def main():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "completed" and report["strict_win"]
    fresh = report["fresh"]
    assert len(fresh) == 64
    assert all(
        row["baseline"]["quality"] == row["champion"]["quality"] == 0.9
        for row in fresh
    )
    baseline = sum(row["baseline"]["calls"] for row in fresh)
    deployment = sum(row["champion"]["calls"] for row in fresh)
    preparation = report["development"]["preparation_calls"]
    assert (baseline, deployment, preparation) == (256, 224, 24)
    by_shift = defaultdict(list)
    for row in fresh:
        by_shift[row["task"]["signal_shift"]].append(row["champion"]["calls"])
    shifts = sorted(by_shift)
    means = [sum(by_shift[shift]) / len(by_shift[shift]) for shift in shifts]
    assert means == [3, 4, 3, 4]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.0), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor("#faf9f6")
    fig.subplots_adjust(left=0.08, right=0.96, top=0.82, bottom=0.23, wspace=0.33)
    left, right = axes
    for ax in axes:
        ax.set_facecolor("#faf9f6")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)

    left.bar([0, 1], [baseline, deployment], color=["#8295a9", "#287f69"], width=0.55)
    left.bar([1], [preparation], bottom=[deployment], color="#9cc9b4", width=0.55, hatch="///")
    left.set_xticks([0, 1], ["Fixed baseline", "Bonsai Q2 policy"])
    left.set_ylim(0, 285)
    left.set_ylabel("Logical calls across 64 fresh tasks")
    left.set_title("Counted operations: 3.125% fewer")
    left.text(0, baseline + 4, "256", ha="center", weight="bold")
    left.text(1, deployment + preparation + 4, "248", ha="center", weight="bold")
    left.text(1, deployment + preparation / 2, "24 prep", ha="center", va="center", fontsize=9)

    right.bar(range(len(shifts)), means, color="#287f69", width=0.63)
    right.set_xticks(range(len(shifts)), [str(shift) for shift in shifts])
    right.set_ylim(0, 4.5)
    right.set_ylabel("Average deployment calls per task")
    right.set_xlabel("Intermediate-score shift")
    right.set_title("16 fresh tasks at each shift")
    for index, value in enumerate(means):
        right.text(index, value + 0.07, str(value), ha="center")

    fig.suptitle("Bonsai policy on varied intermediate-score scales", fontsize=14, weight="bold")
    fig.text(
        0.08,
        0.06,
        "Raw quality 0.9 throughout. 8 developer attempts; the last exceeded local context.\n"
        "Deterministic branch fixture; not the published Dream-RSI benchmark.",
        color="#4f5964",
        fontsize=9,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT.with_suffix(".png"), dpi=180)
    fig.savefig(OUTPUT.with_suffix(".svg"))
    plt.close(fig)


if __name__ == "__main__":
    main()
