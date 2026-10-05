"""Render public engineering figures; needs matplotlib, not a runtime dependency.

Run from any directory: python tools/render_beta_figures.py
Reads only the curated, credential-free engineering evidence. No model requests.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BG, PANEL = "#111d25", "#172730"
TEXT, MUTED, GRID = "#f3f0e6", "#acc0c7", "#32454e"
MINT, AMBER, BLUE, GRAY = "#75e0be", "#eebc73", "#82b9e5", "#a7b0b6"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "figure.facecolor": BG, "axes.facecolor": PANEL, "savefig.facecolor": BG,
    "text.color": TEXT, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": TEXT, "axes.edgecolor": GRID, "svg.fonttype": "none",
})


def figure(title, subtitle, *, width=12.8, height=7.4):
    fig = plt.figure(figsize=(width, height))
    fig.text(.07, .948, "DREAM-RSI SDK  /  0.3.0b1", color=MINT, fontsize=10,
             weight="bold", va="top")
    fig.text(.07, .898, title, fontsize=24, weight="bold", va="top")
    fig.text(.07, .843, subtitle, fontsize=11, color=MUTED, va="top")
    return fig


def style(ax):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0, pad=10)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=.8, alpha=.65)


def save(fig, name, footer):
    fig.text(.07, .065, footer, fontsize=10, color=MUTED, va="top", linespacing=1.5)
    output = ROOT / "assets"
    fig.savefig(output / f"{name}.png", dpi=180)
    svg_path = output / f"{name}.svg"
    fig.savefig(svg_path, metadata={"Date": None})
    # Matplotlib emits insignificant trailing spaces in multiline SVG paths.
    svg_path.write_text("\n".join(
        line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()
    ) + "\n", encoding="utf-8")
    plt.close(fig)


def sandbox_chart(data):
    fig = figure("Same policy. Less interpreter work.",
                 "Measured local timings  |  validated-code cache on vs off  |  lower is better")
    ax = fig.add_axes((.20, .20, .63, .54))
    cases = data["cases"]
    labels = ["One frontier node", "Eight frontier nodes", "Empty frontier"]
    for index, key in enumerate(("one_node", "eight_nodes", "terminal")):
        case = cases[key]
        for offset, field, color in ((-.17, "0", GRAY), (.17, "16", MINT)):
            samples = case["runs"][field]
            median = float(np.median(samples))
            y = index + offset
            ax.barh(y, median, height=.27, color=color, alpha=.88)
            ax.scatter(samples, [y] * len(samples), s=18, facecolors=BG,
                       edgecolors=TEXT, linewidth=.7, zorder=4)
            ax.text(max(samples) + .018, y, f"{median:.3f} s", va="center", fontsize=11)
        ax.text(1.065, index, f"{case['speedup']:.2f}x", color=MINT, weight="bold",
                fontsize=17, va="center", ha="left")
    ax.set_yticks(range(3), labels)
    ax.set_xlim(0, 1.24)
    ax.set_xticks((0, .25, .5, .75, 1), ("0", "0.25", "0.50", "0.75", "1.00"))
    ax.set_ylim(2.65, -.7)
    ax.set_xlabel("Seconds per 1,000 decisions  ·  dots show all seven samples", labelpad=15)
    style(ax)
    ax.scatter([], [], color=GRAY, marker="s", label="Cache disabled")
    ax.scatter([], [], color=MINT, marker="s", label="Cache enabled (16 entries)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.035), ncol=2, frameon=False,
              fontsize=11, labelcolor=TEXT)
    save(fig, "beta-sandbox-performance",
         "Existing balanced_source policy; identical decisions and fresh state in both modes.\n"
         "Seven alternating paired samples on one local machine. "
         "Interpreter timing, not LLM savings.")


def economy_chart(data):
    fig = figure("Stop preparation that cannot pay back.",
                 "Exact accounting example  |  fixed six-task horizon  |  not a model benchmark")
    left = fig.add_axes((.09, .30, .33, .45))
    right = fig.add_axes((.53, .30, .39, .45))
    old, new = data["static_additional_calls"], data["dynamic_additional_calls"]
    left.barh((0, 1), (old, new), color=(GRAY, MINT), height=.45)
    left.set_yticks((0, 1), ("Static", "Dynamic"))
    left.set_xlim(0, 18)
    left.set_ylim(1.6, -.6)
    left.set_xticks((0, 5, 10, 15))
    left.set_title("Further preparation allowed", fontsize=14, loc="left", pad=18)
    left.set_xlabel("Additional calls", labelpad=13)
    for y, value in enumerate((old, new)):
        left.text(value + .45, y, str(value), va="center", weight="bold", fontsize=19)
    style(left)
    parts = (
        ("Preparation spent", (data["preparation_calls"],) * 2, AMBER),
        ("Deployment spent", (data["deployment_calls"],) * 2, BLUE),
        ("Further preparation", (old, new), MINT),
        ("Unfinished task floor", (data["unfinished_floor_calls"],) * 2, GRAY),
    )
    start = np.zeros(2)
    for label, values, color in parts:
        right.barh((0, 1), values, left=start, height=.45, color=color, label=label)
        for y, value in enumerate(values):
            right.text(start[y] + value / 2, y, str(value), color=BG, ha="center",
                       va="center", weight="bold", fontsize=11)
        start += values
    cap = data["strict_total_call_cap"]
    right.axvline(cap, color=TEXT, linestyle="--", linewidth=1.4)
    right.text(cap + .25, -.54, f"Strict cap: {cap}", fontsize=10, va="bottom")
    right.set_yticks((0, 1), ("Static", "Dynamic"))
    right.set_ylim(1.6, -.6)
    right.set_xlim(0, 33)
    right.set_title("Optimistic final total", fontsize=14, loc="left", pad=18)
    right.set_xlabel("Spent + allowance + remaining floor", labelpad=13)
    right.legend(loc="upper left", bbox_to_anchor=(0, -.25), frameon=False,
                 ncol=2, fontsize=9, labelcolor=TEXT)
    style(right)
    fig.text(.095, .14, "6 unaffordable calls blocked", color=MINT,
             fontsize=14, weight="bold")
    save(fig, "beta-preparation-headroom",
         "Baseline: 4 calls/task × 6 tasks = 24. "
         "Spent: preparation 2, deployment 8 on 2 tasks.\n"
         "Four unfinished tasks reserve one call each. "
         "An optimistic floor does not prove future savings.")


def quality_chart(data):
    fig = figure("Preserve quality. Stop only with a certificate.",
                 "Exhaustive SDK check  |  243 deterministic cases  |  no model requests")
    left = fig.add_axes((.10, .31, .34, .43))
    right = fig.add_axes((.56, .31, .36, .43))
    groups = data["groups_by_initial_quality"]
    x = np.arange(len(groups))
    equal = data["cases"] - data["quality_mismatches"]
    assert data["quality_mismatches"] == 0
    counts = (equal, 0, 0)
    left.barh(range(3), counts, height=.4, color=(MINT, AMBER, BLUE))
    left.set_yticks(range(3), ("Equal", "Worse", "Better"))
    left.set_xlim(0, 280)
    left.set_ylim(2.7, -.7)
    left.set_xticks((0, 80, 160, 240))
    left.set_title("Returned quality vs full reference", fontsize=14, loc="left", pad=18)
    left.set_xlabel("Cases  ·  all 243 returned the same quality", labelpad=12)
    for y, value in enumerate(counts):
        left.text(value + 7, y, str(value), va="center", fontsize=17, weight="bold")
    style(left)
    for offset, field, color in (
        (-.17, "reference_logical_agent_dispatches_mean", GRAY),
        (.17, "certified_logical_agent_dispatches_mean", MINT),
    ):
        values = [group[field] for group in groups]
        right.bar(x + offset, values, width=.3, color=color)
        for position, value in zip(x + offset, values, strict=True):
            right.text(position, value + .12, f"{value:.2f}", ha="center", fontsize=11)
    right.set_xticks(x, [str(group["initial_quality"]) for group in groups])
    right.set_xlabel("Initial candidate quality  ·  81 cases each", labelpad=12)
    right.set_ylabel("Mean logical agent calls")
    right.set_ylim(0, 4.75)
    right.set_yticks((0, 1, 2, 3, 4))
    right.set_title("Fewer calls after certification", fontsize=14, loc="left", pad=18)
    style(right)
    right.grid(axis="x", visible=False)
    right.grid(axis="y", color=GRID, alpha=.65)
    right.scatter([], [], color=GRAY, marker="s", label="Full reference")
    right.scatter([], [], color=MINT, marker="s", label="Certified stopping")
    right.legend(loc="upper left", bbox_to_anchor=(0, -.27), ncol=2, frameon=False,
                 fontsize=10, labelcolor=TEXT)
    fig.text(.10, .14, "0 quality losses  /  195 early stops", color=MINT,
             fontsize=14, weight="bold")
    save(fig, "beta-quality-preservation",
         "Four responses from {0, 0.5, 1}; initial quality {0, 0.5, 1}; proven bound U = 1.\n"
         "Both arms charge an initial local evaluation. "
         "Logical callback calls are not paid LLM requests.")


def main():
    data = json.loads((ROOT / "docs/verification/0.3.0b1.json").read_text(encoding="utf-8"))
    sandbox_chart(data["sandbox"])
    economy_chart(data["economy"])
    quality_chart(data["quality"])
    print("Rendered three English figures as PNG and SVG; no model requests.")


if __name__ == "__main__":
    main()
