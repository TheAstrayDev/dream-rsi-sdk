"""Render the curated English follow-up figure; no model requests or private logs.

python tools/render_bonsai_structural_followup.py
Only the development environment needs matplotlib. The SDK has no new dependency.
"""

from __future__ import annotations

import json
from fractions import Fraction
from itertools import accumulate
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/verification/bonsai-structural-dream-2026-10-05.json"
BG, PANEL, TEXT = "#101c25", "#172832", "#f2f5f5"
MUTED, GRID = "#acc0ca", "#334854"
MINT, BLUE, AMBER, GRAY = "#75e0be", "#82b9e5", "#eebc73", "#a9b4bf"


def validate(data):
    cases, costs = data["cases"], data["costs"]
    assert len(cases) == data["protocol"]["application_tasks"] == 8
    assert all(Fraction(c["dream_gap"]) <= Fraction(c["baseline_gap"]) for c in cases)
    assert sum(c["dream_calls"] for c in cases) == costs["dream_application_calls"]
    assert sum(c["baseline_calls"] for c in cases) == costs["baseline_matched_calls"]
    assert (
        costs["dream_preparation_calls"] + costs["dream_application_calls"]
        == costs["dream_all_in_calls"]
    )
    assert (
        costs["baseline_matched_calls"] + costs["control_overhead_calls"]
        == costs["all_actual_control_calls"]
    )
    assert (
        costs["dream_all_in_calls"] + costs["all_actual_control_calls"]
        == costs["full_experiment_calls"]
    )
    assert (
        costs["dream_all_in_calls"] + costs["earlier_research_calls"]
        == costs["dream_including_earlier_research_calls"]
    )
    for arm in ("baseline", "dream"):
        assert (
            sum(Fraction(c[f"{arm}_gap"]) == 0 for c in cases)
            == data["quality"][f"{arm}_exact_optima"]
        )
    assert not data["protocol"]["original_protocol_success"]


def style(ax, axis="x"):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0, pad=8)
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=GRID, alpha=0.7, linewidth=0.8)


def main():
    data = json.loads(DATA.read_text())
    validate(data)
    costs = data["costs"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "figure.facecolor": BG,
            "axes.facecolor": PANEL,
            "savefig.facecolor": BG,
            "text.color": TEXT,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": TEXT,
            "axes.edgecolor": GRID,
            "svg.fonttype": "none",
        }
    )
    fig = plt.figure(figsize=(14.5, 10))
    fig.text(
        0.06,
        0.962,
        "DREAM-RSI SDK / LOCAL EXPERIMENT / 05 OCT 2026",
        color=MINT,
        fontsize=10,
        weight="bold",
    )
    fig.text(0.06, 0.909, "Fewer calls. No measured quality loss.", fontsize=27, weight="bold")
    fig.text(
        0.06,
        0.870,
        "Bonsai-27B Q2 | 8 new Lasso tasks | empty memory | recovered control comparison",
        color=MUTED,
        fontsize=12,
    )

    calls = fig.add_axes((0.14, 0.56, 0.34, 0.22))
    style(calls)
    calls.set_title("01 / Fresh campaign calls", loc="left", pad=28, weight="bold")
    calls.barh(1, costs["baseline_matched_calls"], height=0.38, color=BLUE)
    calls.barh(0, costs["dream_preparation_calls"], height=0.38, color=AMBER, label="Preparation")
    calls.barh(
        0,
        costs["dream_application_calls"],
        left=costs["dream_preparation_calls"],
        height=0.38,
        color=MINT,
        label="Application",
    )
    calls.text(
        costs["baseline_matched_calls"] + 0.45,
        1,
        str(costs["baseline_matched_calls"]),
        va="center",
        weight="bold",
        fontsize=17,
    )
    calls.text(
        costs["dream_all_in_calls"] + 0.45,
        0,
        str(costs["dream_all_in_calls"]),
        va="center",
        weight="bold",
        fontsize=17,
    )
    calls.text(
        costs["dream_preparation_calls"] / 2,
        0,
        str(costs["dream_preparation_calls"]),
        color=BG,
        weight="bold",
        ha="center",
        va="center",
    )
    calls.text(
        costs["dream_preparation_calls"] + costs["dream_application_calls"] / 2,
        0,
        str(costs["dream_application_calls"]),
        color=BG,
        weight="bold",
        ha="center",
        va="center",
    )
    calls.set_yticks([1, 0], ["Baseline", "Dream"])
    calls.set_xticks([0, 4, 8, 12, 16])
    calls.set_xlim(0, 18)
    calls.set_ylim(-0.65, 1.65)
    calls.set_xlabel("Real model requests (preparation included)", fontsize=10)
    calls.legend(
        loc="upper left",
        bbox_to_anchor=(0, 1.02),
        ncol=2,
        frameon=False,
        fontsize=10,
        handlelength=1.1,
    )
    saving = 1 - costs["dream_all_in_calls"] / costs["baseline_matched_calls"]
    fig.text(
        0.14,
        0.492,
        f"{saving:.1%} fewer calls in the fresh campaign",
        color=MINT,
        fontsize=13,
        weight="bold",
    )

    quality = fig.add_axes((0.64, 0.56, 0.30, 0.22))
    style(quality)
    quality.set_title("02 / Answer quality", loc="left", pad=28, weight="bold")
    for y, arm, color in ((1, "baseline", BLUE), (0, "dream", MINT)):
        n = data["quality"][f"{arm}_exact_optima"]
        quality.barh(y, n, color=color, height=0.38)
        quality.text(n + 0.25, y, f"{n} / 8", va="center", weight="bold", fontsize=17)
    quality.set_yticks([1, 0], ["Baseline", "Dream"])
    quality.set_xticks([0, 2, 4, 6, 8])
    quality.set_xlim(0, 9.1)
    quality.set_ylim(-0.65, 1.65)
    quality.set_xlabel("Exact global optima (higher is better)", fontsize=10)
    fig.text(
        0.64,
        0.492,
        "Raw quality equal or better in all 8 pairs",
        color=MINT,
        fontsize=12,
        weight="bold",
    )
    fig.text(0.64, 0.468, "2 Dream answers still remain nonoptimal", color=MUTED, fontsize=10)

    cumulative = fig.add_axes((0.14, 0.175, 0.80, 0.22))
    style(cumulative, "y")
    cumulative.set_title(
        "03 / Payback: fresh campaign vs historical research", loc="left", pad=20, weight="bold"
    )
    x = list(range(9))
    baseline = [0, *accumulate(c["baseline_calls"] for c in data["cases"])]
    dream = [costs["dream_preparation_calls"]]
    dream += list(accumulate((c["dream_calls"] for c in data["cases"]), initial=dream[0]))[1:]
    historical = [v + costs["earlier_research_calls"] for v in dream]
    cumulative.plot(
        x, baseline, color=BLUE, linewidth=2.5, marker="o", markersize=4, label="Baseline"
    )
    cumulative.plot(
        x,
        dream,
        color=MINT,
        linewidth=2.5,
        marker="o",
        markersize=4,
        label="Dream: fresh campaign",
    )
    cumulative.plot(
        x,
        historical,
        color=GRAY,
        linewidth=1.8,
        linestyle="--",
        label="Dream + 12 earlier research calls",
    )
    cumulative.set_xticks(x)
    cumulative.set_yticks([0, 4, 8, 12, 16, 20, 24])
    cumulative.set_ylim(0, 25)
    cumulative.set_xlim(-0.15, 9.2)
    cumulative.set_xlabel("Completed application tasks (6 deployment + 2 frozen confirmation)")
    cumulative.set_ylabel("Cumulative model calls", fontsize=10)
    cumulative.legend(loc="upper left", frameon=False, fontsize=9.5, ncol=2)
    for values, color, label in (
        (baseline, BLUE, "16"),
        (dream, MINT, "10"),
        (historical, GRAY, "22"),
    ):
        cumulative.text(
            8.2, values[-1], label, color=color, va="center", weight="bold", fontsize=13
        )
    cumulative.annotate(
        "Break-even: task 2",
        xy=(2, 4),
        xytext=(2.2, 8.7),
        fontsize=10,
        color=AMBER,
        arrowprops={"arrowstyle": "->", "color": AMBER},
    )
    fig.text(
        0.06,
        0.073,
        "Transport failure: one control request timed out; its usage remains unknown. "
        "Separate control repeat: +2 calls.",
        color=MUTED,
        fontsize=10,
    )
    fig.text(
        0.06,
        0.047,
        "28 actual calls in this experiment. Original preregistered success: false. "
        "Recovered comparison: follow-up evidence.",
        color=MUTED,
        fontsize=10,
    )
    fig.text(
        0.06,
        0.021,
        "Earlier research has not paid back. Small Lasso prototype; "
        "no universal SDK or dollar-ROI claim.",
        color=MUTED,
        fontsize=10,
    )
    output = ROOT / "assets/bonsai-structural-dream-2026-10-05"
    fig.savefig(output.with_suffix(".png"), dpi=180)
    fig.savefig(output.with_suffix(".svg"), metadata={"Date": None})
    svg = output.with_suffix(".svg")
    svg.write_text(
        "\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n", encoding="utf-8"
    )
    plt.close(fig)
    print(output.with_suffix(".png"))


if __name__ == "__main__":
    main()
