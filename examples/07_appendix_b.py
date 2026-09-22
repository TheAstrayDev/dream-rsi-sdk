"""Run two live grid cycles and a beta sweep; optionally develop real model source.

python examples/07_appendix_b.py --output temp/appendix-demo.json
python examples/07_appendix_b.py --model-url http://127.0.0.1:8087 --revisions 3
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamrsi import DeveloperConfig, LlamaCppPolicyModel, PolicyArtifact  # noqa: E402
from dreamrsi.appendix import (  # noqa: E402
    AppendixPolicyDeveloper,
    AppendixSourcePolicy,
    GridCampaign,
    GridPlanningContext,
    Observation,
)


async def main(args):
    implementation_hashes = {
        str(path.relative_to(Path(__file__).parents[1])): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (Path(__file__).parents[1] / "src/dreamrsi/appendix").glob("*.py")
    }
    context = GridPlanningContext(
        fallback_branch_count=4,
        fallback_refine_count=3,
        hard_max_branch_count=8,
        hard_max_refine_count=6,
        max_parallelism=3,
    )
    source = Path(__file__).with_name("appendix_policy.py").read_text(encoding="utf-8")
    policy = AppendixSourcePolicy(PolicyArtifact(source), {"beta": 1})
    campaign = GridCampaign("appendix-example", context)
    calls = []

    def evaluate(meta, parent, direction):
        calls.append([meta.branch, meta.attempt])
        # Synthetic diagnostics: one repairable failure, one late improving direction,
        # and flat branches. This is plumbing evidence, not a research benchmark.
        if meta.branch == 1 and meta.attempt == 1:
            return Observation(
                meta.branch,
                meta.attempt,
                evaluated=True,
                fail_class="compile_other",
                error="repairable fixture",
            )
        values = (
            [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
            [0.1, 0.0, 0.6, 0.9, 0.95, 0.95, 0.95],
            [0.2, 0.35, 0.5, 0.7, 0.8, 0.9, 1.0],
            [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
        )
        return Observation(
            meta.branch,
            meta.attempt,
            values[meta.branch % 4][meta.attempt],
            evaluated=True,
            valid=False,
            fail_class="ok",
        )

    first = await campaign.run_cycle(
        policy, evaluate, direction_provider=lambda branch: [f"mechanism-{branch}"]
    )

    def source_factory(beta):
        return AppendixSourcePolicy(PolicyArtifact(source), {"beta": beta})

    sweep = await campaign.evaluate_sweep(source_factory)
    selected = policy
    history = []
    if args.model_url:
        model = LlamaCppPolicyModel(
            args.model_url,
            max_tokens=8192,
            timeout_s=300,
            temperature=0.7,
            seed=43,
            structured=False,
        )
        developer = AppendixPolicyDeveloper(
            model,
            config=DeveloperConfig(
                revisions=args.revisions,
                model_timeout_s=300,
                max_feedback_chars=30000,
                policy_timeout_s=10,
                response_format="python",
            ),
        )
        selected = await developer.develop(
            policy, await campaign.traces(), await campaign.planning_context()
        )
        history = developer.history
    restored = AppendixSourcePolicy.from_dict(json.loads(json.dumps(selected.to_dict())))
    second = await campaign.run_cycle(
        restored, evaluate, direction_provider=lambda branch: [f"mechanism-{branch}"]
    )
    report = {
        "experiment": "appendix-b-synthetic-v1",
        "model_url": args.model_url,
        "model_settings": {"seed": 43, "temperature": 0.7, "max_tokens": 8192},
        "context": {"workers": 3, "bootstrap_width": 4, "bootstrap_refinements": 3},
        "live_cycles": [first, second],
        "baseline_sweep": sweep,
        "revisions": history,
        "selected_policy": selected.to_dict(),
        "live_calls": len(calls),
        "checks": {
            "sweep_scored": sweep["pareto"]["reward"] is not None,
            "beta_changes_tradeoff": sweep["non_degenerate"],
            "history_available": len((await campaign.planning_context()).history) == 2,
            "selected_reloaded_and_executed": second["total_probes"] > 0,
        },
        "implementation_sha256": implementation_hashes,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "checks": report["checks"],
                "revisions": [
                    {"status": row["status"], "score": row["score"], "error": row.get("error")}
                    for row in history
                ],
                "report": str(output),
            },
            indent=2,
        )
    )
    if not all(report["checks"].values()):
        raise SystemExit("Appendix mechanics checks failed; inspect the saved report")
    if args.model_url and not any(row["status"] == "scored" for row in history):
        raise SystemExit("No model revision scored; inspect the saved report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-url")
    parser.add_argument("--revisions", type=int, default=3)
    parser.add_argument("--output", default="temp/appendix-demo.json")
    asyncio.run(main(parser.parse_args()))
