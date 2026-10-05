"""Measure local sandbox cache timing; no model/API calls. Timings vary by host.

Run: python -I tools/measure_beta_sandbox.py --output temp/beta-sandbox.json
"""

import argparse
import asyncio
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from balanced_source import BALANCED_SOURCE  # noqa: E402

from dreamrsi.models.discovery import NodeStatus  # noqa: E402
from dreamrsi.models.policy import NodeSummary, PolicyView  # noqa: E402
from dreamrsi.sandbox import PolicySandbox  # noqa: E402


async def measure():
    views = {
        "terminal": PolicyView([], None, 0, 0, 0, 0),
        "one_node": PolicyView(
            [NodeSummary("root", None, 0, None, NodeStatus.COMPLETED, 0)],
            None, 1, 0, 0, 0,
        ),
        "eight_nodes": PolicyView(
            [NodeSummary(str(i), None, 0, i / 8, NodeStatus.COMPLETED, i) for i in range(8)],
            0.875, 8, 0, 0, 0,
        ),
    }
    report = {
        "method": "same balanced_source; seven alternating pairs, 1000 decisions per sample",
        "provider_calls": 0,
        "provenance": {
            "report_type": "local deterministic sandbox timing",
            "python_version": platform.python_version(), "platform": platform.platform(),
            "source": "examples/balanced_source.py::BALANCED_SOURCE",
            "source_sha256": hashlib.sha256(BALANCED_SOURCE.encode("utf-8")).hexdigest(),
            "timer": "time.perf_counter wall-clock seconds",
            "samples_per_capacity_per_case": 7, "decisions_per_sample": 1000,
            "cache_capacities": [0, 16], "fresh_sandbox_per_sample": True,
        },
        "cases": {},
    }
    for name, view in views.items():
        samples = {0: [], 16: []}
        expected = None
        for repeat in range(7):
            for capacity in ((0, 16) if repeat % 2 == 0 else (16, 0)):
                sandbox = PolicySandbox(cache_size=capacity)
                started = time.perf_counter()
                for _ in range(1000):
                    decision = await sandbox.execute(BALANCED_SOURCE, view)
                    if expected is None:
                        expected = decision
                    assert decision == expected
                samples[capacity].append(time.perf_counter() - started)
        uncached, cached = (statistics.median(samples[capacity]) for capacity in (0, 16))
        report["cases"][name] = {
            "uncached_s": uncached, "cached_s": cached,
            "speedup": uncached / cached, "runs": samples,
        }
    report["decisions_checked"] = 42000
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("temp/beta-sandbox.json"))
    args = parser.parse_args()
    report = asyncio.run(measure())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {report['decisions_checked']} decisions; timing report: {args.output}")


if __name__ == "__main__":
    main()
