"""Run actual model-generated policy revisions against a local llama-server.

Start your server separately. Example:
python examples/05_local_llamacpp.py --url http://127.0.0.1:8080 --model Bonsai-27B-Q1_0
This small mechanics experiment is not a reproduction of published benchmarks.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from balanced_source import BALANCED_SOURCE  # noqa: E402

from dreamrsi import (  # noqa: E402
    Budget,
    DeveloperConfig,
    DreamRSI,
    FunctionalAgentAdapter,
    HoldoutPipeline,
    LlamaCppPolicyModel,
    LLMPolicyDeveloper,
    PolicyArtifact,
    PolicySandbox,
    SourcePolicy,
)
from dreamrsi.artifacts import PolicyCodec  # noqa: E402
from dreamrsi.policies import BalancedPolicy  # noqa: E402


async def main(args):
    implementation_hashes = {
        str(path.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (Path(__file__).resolve().parents[1] / "src" / "dreamrsi").rglob("*.py")
    }
    model = LlamaCppPolicyModel(
        args.url,
        model=args.model,
        timeout_s=args.timeout,
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
        seed=args.seed,
        temperature=args.temperature,
    )
    await model.health()
    requests = []

    async def generate(request):
        if request["revision"]:
            print(
                f"Previous feedback: {request['feedback'].get('summary')} "
                f"{request['feedback'].get('error', '')}",
                flush=True,
            )
        print(f"Generating revision {request['revision'] + 1}...", flush=True)
        requests.append(
            {key: value for key, value in request.items() if key not in ("report_usage", "usage")}
        )
        response = await model(request)
        print(f"Received {len(response)} characters", flush=True)
        return response

    developer = LLMPolicyDeveloper(
        generate,
        config=DeveloperConfig(
            revisions=args.revisions,
            model_timeout_s=args.timeout,
            max_feedback_chars=12_000,
            response_format=args.response_format,
        ),
        provenance={"backend": "llama.cpp", "model": args.model},
    )
    collector = (
        SourcePolicy(
            PolicyArtifact(
                BALANCED_SOURCE, provenance={"origin": "equivalent handwritten baseline"}
            ),
            PolicySandbox(),
        )
        if args.source_incumbent
        else BalancedPolicy()
    )
    validation = HoldoutPipeline([6, 10, 14], worlds_per_check=3)
    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state: state / 2),
        evaluator=lambda observation: -abs(observation),
        policy=collector,
        policy_optimizer=developer,
        validation=validation,
        budget=Budget(model_calls=6),
        campaign_budget=Budget(model_calls=30, developer_calls=args.revisions),
    )
    result = await runtime.improve(8, rounds=1)
    validation_scores = await runtime.compare_policies(
        [collector, result.champion_policy or collector], validation.worlds
    )
    # Serialize through JSON and load afresh: the deployed code must be portable,
    # and execute on observations which were never part of development feedback.
    deployment = None
    if result.champion_policy is not None:
        codec = PolicyCodec()
        encoded = json.loads(json.dumps(codec.encode(result.champion_policy)))
        loaded = codec.decode(encoded)
        online = []
        for policy in (collector, loaded):
            fresh = DreamRSI(
                adapter=FunctionalAgentAdapter(lambda state: state / 2),
                evaluator=lambda observation: -abs(observation),
                policy=policy,
                budget=Budget(model_calls=6),
            )
            run = await fresh.run(12)
            online.append({"best_score": run.best_score, "model_calls": run.costs.model_calls})
        deployment = {
            "artifact": encoded,
            "task": 12,
            "online_incumbent_then_loaded_champion": online,
            "source_hash_preserved": (
                loaded.artifact.source_hash == result.champion_policy.artifact.source_hash
            ),
        }
    scored = [entry for entry in developer.history if entry.get("status") == "scored"]
    report = {
        "model": args.model,
        "backend": "llama.cpp",
        "generation": {
            "max_tokens": args.max_tokens,
            "seed": args.seed,
            "reasoning_effort": args.reasoning_effort,
            "temperature": args.temperature,
            "top_p": model.top_p,
            "top_k": model.top_k,
            "response_format": args.response_format,
            "source_incumbent": args.source_incumbent,
        },
        "implementation_hashes": implementation_hashes,
        "experiment": "halve-toward-zero mechanics, independent validation tasks 6/10/14",
        "metrics": result.metrics,
        "usage": runtime.usage.to_dict(),
        "revisions": developer.history,
        "requests": requests,
        "deployment": deployment,
        "distinct_behavior_hashes": sorted({entry["behavior_hash"] for entry in scored}),
        "distinct_ast_hashes": sorted({entry["ast_hash"] for entry in scored}),
        "heldout_scores_incumbent_then_champion": validation_scores,
        "heldout_worlds": len(validation.worlds),
        "distinct_source_hashes": sorted({entry["artifact"]["source_hash"] for entry in scored}),
        "scored_revisions": len(scored),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Report: {output.resolve()}")
    print(f"Scored revisions: {report['scored_revisions']}/{len(developer.history)}")
    print(f"Distinct sources: {len(report['distinct_source_hashes'])}")
    print(f"Promotions: {result.metrics.get('policy_promotions', 0)}")
    gates = {
        "multiple_scored_revisions": len(scored) >= 2,
        "different_executable_structure": len(report["distinct_ast_hashes"]) >= 2,
        "different_replay_decisions": len(report["distinct_behavior_hashes"]) >= 2,
        "promoted": result.metrics.get("policy_promotions", 0) > 0,
        "loaded_and_executed": deployment is not None and deployment["source_hash_preserved"],
    }
    report["acceptance"] = gates
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if not all(gates.values()):
        raise SystemExit(f"Developer demonstration incomplete: {gates}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="Bonsai-27B-Q1_0")
    parser.add_argument("--revisions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source-incumbent", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--response-format", choices=["python", "json"], default="python")
    parser.add_argument("--output", default="temp/llamacpp-experiment.json")
    asyncio.run(main(parser.parse_args()))
