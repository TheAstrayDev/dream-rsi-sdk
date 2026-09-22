"""Render measured policy-development results from the archived, hash-checked report."""

import gzip
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import ScalarFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/experiments/sandbox-v4-2026-09-22"
manifest = json.loads((ARCHIVE / "manifest.json").read_text(encoding="utf-8"))
entry = manifest["runs"][-1]
raw = gzip.decompress((ARCHIVE / entry["file"]).read_bytes())
assert hashlib.sha256(raw).hexdigest() == entry["uncompressed_sha256"]
report = json.loads(raw)
assert all(report["acceptance"].values())
records = report["revisions"]
selected_hash = report["deployment"]["artifact"]["artifact"]["source_hash"]
selected = next(r for r in records if r.get("artifact", {}).get("source_hash") == selected_hash)
scored = [r for r in records if r["status"] == "scored"]
failed = [r for r in records if r["status"] != "scored"]
baseline = records[0]["request"]["baseline_score"]
online = report["deployment"]["online_incumbent_then_loaded_champion"]
assert online[0]["model_calls"] == online[1]["model_calls"]
residuals = [-row["best_score"] for row in online]
reduction = 100 * (1 - residuals[1] / residuals[0])
for row in scored:
    assert row["evaluation"]["all_worlds_scored"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#bac4cd", "axes.labelcolor": "#344454",
    "xtick.color": "#344454", "ytick.color": "#344454",
    "svg.fonttype": "none",
})
blue, green, grey, red = "#276cb2", "#168568", "#8695a3", "#b94b50"
fig = plt.figure(figsize=(15, 9), facecolor="#ffffff")
grid = fig.add_gridspec(2, 2, left=.08, right=.965, bottom=.15, top=.82, hspace=.60, wspace=.30)
ax = fig.add_subplot(grid[0, :])
xs = [r["revision"] + 1 for r in scored]
scores = [r["evaluation"]["mean_score"] for r in scored]
ax.axhline(baseline, color=grey, linestyle="--", linewidth=1.3, label="Baseline")
ax.plot(xs, scores, "o-", color=blue, linewidth=2, markersize=6, label="Measured revision")
sx, sy = selected["revision"] + 1, selected["evaluation"]["mean_score"]
ax.scatter([sx], [sy], s=130, facecolor=green, edgecolor="white", linewidth=2,
           zorder=5, label="Selected and deployed")
for i, (x, y) in enumerate(zip(xs, scores, strict=True)):
    offset = -25 if i in (1, 4) else 13
    ax.annotate(f"{y:.6f}", (x, y), xytext=(0, offset), textcoords="offset points",
                ha="center", fontsize=10, color=green if x == sx else blue)
for row in failed:
    x = row["revision"] + 1
    ax.axvspan(x - .28, x + .28, color=red, alpha=.09)
    ax.text(x, .45, "FAILED\nNo score", transform=ax.get_xaxis_transform(),
            ha="center", va="center", color=red, fontsize=10, fontweight="bold")
ax.set(xlim=(.6, len(records) + .4), xticks=range(1, len(records) + 1),
       xlabel="LLM revision", ylabel="Replay objective\n(higher is better)")
span = max(scores) - min(scores)
ax.set_ylim(min(scores) - max(.008, span * .35), max(scores) + max(.008, span * .4))
ax.grid(axis="y", color="#edf0f3")
ax.set_title("A   Executable revisions evaluated on the same recorded world", loc="left",
             fontsize=12, fontweight="bold", pad=13)
ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=9)

work = fig.add_subplot(grid[1, 0])
rounds = [r["evaluation"]["total_rounds"] for r in scored]
probes = [r["evaluation"]["total_probes"] for r in scored]
work.bar(xs, rounds, width=.55, color=[green if x == sx else blue for x in xs], alpha=.88)
work.set_yscale("log")
work.set_ylim(.8, max(rounds) * 2.4)
work.set_yticks([1, 10, 100, 1000])
work.yaxis.set_major_formatter(ScalarFormatter())
work.set(xlim=(.5, len(records) + .5), xticks=range(1, len(records) + 1),
         ylabel="Decision rounds · log scale")
work.set_xticklabels([
    f"{r['revision'] + 1}\n{r['evaluation']['total_probes']} probes"
    if r["status"] == "scored" else f"{r['revision'] + 1}\nfailed"
    for r in records
], fontsize=9)
for x, value in zip(xs, rounds, strict=True):
    work.annotate(str(value), (x, value), xytext=(0, 5), textcoords="offset points",
                  ha="center", fontsize=10)
work.grid(axis="y", color="#edf0f3")
work.set_axisbelow(True)
work.set_title("B   Replay work per revision", loc="left", fontsize=12, fontweight="bold", pad=13)

quality = fig.add_subplot(grid[1, 1])
quality.bar([0, 1], residuals, width=.55, color=[grey, green])
quality.set(xticks=[0, 1], xticklabels=["Baseline", "Reloaded generated policy"],
            ylabel="Final residual |state| · lower is better", ylim=(0, max(residuals) * 1.3))
for x, value in enumerate(residuals):
    quality.annotate(f"{value:g}\n{online[x]['model_calls']} agent calls", (x, value),
                     xytext=(0, 7), textcoords="offset points", ha="center", fontsize=11)
quality.text(.97, .93, f"{reduction:g}% less residual", transform=quality.transAxes,
             ha="right", color=green, fontsize=12, fontweight="bold")
quality.grid(axis="y", color="#edf0f3")
quality.set_axisbelow(True)
quality.set_title("C   Fresh online task after source reload", loc="left",
                  fontsize=12, fontweight="bold", pad=13)

fig.text(.08, .94, "Bonsai-27B-Q1_0 · measured executable-policy development",
         fontsize=20, fontweight="bold", color="#20364a")
fig.text(.08, .895,
         f"Seed {report['generation']['seed']}  |  {len(records)} requested revisions  |  "
         f"{len(scored)} scored  |  {len(failed)} failed  |  "
         f"{len(report['distinct_behavior_hashes'])} distinct replay behaviors",
         fontsize=12, color="#526677")
held = report["heldout_scores_incumbent_then_champion"]
fig.text(.08, .084,
         f"Held-out mean replay score: {held['0']:.6f} → {held['1']:.6f} (3 worlds). "
         "Training task: 8; validation: 6/10/14; fresh online task: 12.", fontsize=10,
         color="#344454")
fig.text(.08, .049,
         "Synthetic halving task; fixed agent/evaluator. Failed revisions have no plotted score. "
         "One exploratory run, not a generalization benchmark.", fontsize=10, color="#526677")
fig.text(.08, .021, f"Source report SHA-256: {entry['uncompressed_sha256']}",
         fontsize=8, color="#687d8d")

destination = ROOT / "assets/bonsai-development-v4"
fig.savefig(destination.with_suffix(".png"), dpi=180, facecolor=fig.get_facecolor())
fig.savefig(
    destination.with_suffix(".svg"), facecolor=fig.get_facecolor(), metadata={"Date": None}
)
svg = destination.with_suffix(".svg")
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
data = {
    "report_sha256": entry["uncompressed_sha256"], "model": report["model"],
    "baseline_replay_score": baseline, "selected_revision": sx,
    "revisions": [{"revision": row["revision"] + 1, "status": row["status"],
                   "evaluation": row["evaluation"]} for row in records],
    "online_incumbent_then_loaded_champion": online,
    "heldout_scores": held,
}
destination.with_suffix(".json").write_text(json.dumps(data, indent=2), encoding="utf-8")
print(destination.with_suffix(".png"))
