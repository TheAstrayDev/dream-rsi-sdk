"""Render the published summary of the exploratory GPT-6 Luna discovery run."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402, I001

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "docs" / "experiments" / "luna-xhigh-discovery-v1.json"
OUTPUT = ROOT / "assets" / "luna-xhigh-discovery-v1"


def main():
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    categories = data["categories"]
    preparation = sum(data["preparation"].values())
    baseline = data["heldout"]["baseline_model_calls"]
    deployment = data["heldout"]["dream_model_calls"]
    assert (preparation, baseline, deployment) == (94, 24, 6)
    assert len(categories) == 3
    assert [row["name"] for row in categories] == [
        "low_autocorrelation", "circle_packing", "lasso_tuning"
    ]
    assert all(row["baseline_calls"] == 8 and row["dream_calls"] == 2 for row in categories)

    fig, (total_ax, task_ax) = plt.subplots(
        1, 2, figsize=(11.2, 4.8), gridspec_kw={"width_ratios": [0.85, 1.15]}
    )
    background = "#faf9f6"
    slate, teal, sand = "#8295a9", "#287f69", "#dfb56e"
    fig.patch.set_facecolor(background)
    fig.subplots_adjust(left=0.075, right=0.97, top=0.78, bottom=0.22, wspace=0.31)
    for ax in (total_ax, task_ax):
        ax.set_facecolor(background)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)

    total_ax.bar(0, baseline, width=0.52, color=slate)
    total_ax.bar(1, deployment, width=0.52, color=teal)
    total_ax.bar(1, preparation, bottom=deployment, width=0.52, color=sand, hatch="///")
    total_ax.set_xticks([0, 1], ["Fixed baseline", "Dream-RSI path"])
    total_ax.set_ylim(0, 115)
    total_ax.set_ylabel("Model requests")
    total_ax.set_title("Full six-task experiment")
    total_ax.text(0, baseline + 3, str(baseline), ha="center", weight="bold")
    total_ax.text(1, preparation + deployment + 3, "100", ha="center", weight="bold")
    total_ax.text(1, deployment + preparation / 2, "94 prep", ha="center", va="center")
    total_ax.text(1, deployment / 2, "6", ha="center", va="center", color="white")

    labels = ["Autocorrelation", "Circle packing", "Lasso tuning"]
    positions = list(range(len(categories)))
    task_ax.bar([x - 0.18 for x in positions], [8] * 3, width=0.34, color=slate, label="Baseline")
    task_ax.bar([x + 0.18 for x in positions], [2] * 3, width=0.34, color=teal, label="Dream-RSI")
    task_ax.set_xticks(positions, labels)
    task_ax.set_ylim(0, 9.5)
    task_ax.set_ylabel("Model requests for two test tasks")
    task_ax.set_title("Deployment: 4 → 1 call per task")
    task_ax.legend(frameon=False, loc="upper right", ncol=2)
    for x in positions:
        task_ax.text(x - 0.18, 8.13, "8", ha="center", weight="bold")
        task_ax.text(x + 0.18, 2.13, "2", ha="center", weight="bold")

    fig.suptitle(
        "GPT-6 Luna xhigh · learned policies, expensive preparation",
        fontsize=14,
        weight="bold",
    )
    fig.text(
        0.075,
        0.07,
        "Reported mean task score: 72.607% baseline → 72.293% Dream-RSI. "
        "The reduction in deployment calls is not an all-in win.",
        fontsize=9,
        color="#4f5964",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT.with_suffix(".png"), dpi=180)
    fig.savefig(OUTPUT.with_suffix(".svg"))
    plt.close(fig)


if __name__ == "__main__":
    main()
