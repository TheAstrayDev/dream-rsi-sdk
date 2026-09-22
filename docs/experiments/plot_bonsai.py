"""Rebuild the figure from archived evidence; requires matplotlib only for plotting."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

root = Path(__file__).resolve().parents[2]
report = json.loads(gzip.decompress(
    (Path(__file__).parent / "bonsai-2026-09-22/bonsai-matrix-seed-43.json.gz").read_bytes()
))
comparison = report["deployment"]["online_incumbent_then_loaded_champion"]
values = [-run["best_score"] for run in comparison]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "svg.hashsalt": "dreamrsi-bonsai-2026-09-22"})
fig, ax = plt.subplots(figsize=(9, 3.5), facecolor="#101d27")
ax.set_facecolor("#101d27")
ax.barh([1, 0], values, height=0.42, color=["#eebc73", "#75e0be"])
ax.set_yticks([1, 0], ["Balanced baseline", "Generated policy\n(reloaded)"])
ax.tick_params(axis="both", colors="#c3d0d4", length=0, pad=10)
ax.set_xlim(0, 1.85)
ax.set_xticks([0, 0.5, 1, 1.5])
ax.set_xlabel("Final absolute state · lower is better", color="#c3d0d4", labelpad=8)
for y, value in zip([1, 0], values, strict=True):
    ax.text(value + 0.035, y, f"{value:.4f}", va="center", color="white", weight="bold")
for spine in ax.spines.values():
    spine.set_visible(False)
fig.text(0.06, 0.92, "Bonsai-27B-Q1_0 · local policy development", color="white",
         fontsize=16, weight="bold")
fig.text(0.06, 0.83, "Fresh toy task · seed 43 · 6 agent calls per policy",
         color="#c3d0d4", fontsize=11)
fig.text(0.06, 0.035,
         "87.5% less residual error  |  1 of 3 matrix seeds promoted  |  Not a general benchmark",
         color="#c3d0d4", fontsize=9)
fig.subplots_adjust(left=0.25, right=0.95, top=0.74, bottom=0.25)
fig.savefig(root / "assets/bonsai-result.svg", metadata={"Date": None})
fig.savefig(root / "assets/bonsai-result.png", dpi=160)
svg = root / "assets/bonsai-result.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
