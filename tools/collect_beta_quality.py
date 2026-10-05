"""Reproduce finite deterministic SDK quality invariants without model/API requests.

Run: python -I tools/collect_beta_quality.py --output temp/beta-quality.json
Only aggregate logical dispatch and local evaluator counts are written.
"""

import argparse
import asyncio
import json
import platform
import sys
from collections import Counter
from dataclasses import replace
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter, QualityContract  # noqa: E402
from dreamrsi.policies import FixedParallelPolicy  # noqa: E402


def step(state, context):
    index = state.get("index", 0)
    return {**state, "index": index + 1, "quality": state["values"][index]}


def build(contract):
    return DreamRSI(
        adapter=FunctionalAgentAdapter(step), evaluator=lambda item: item["quality"],
        policy=FixedParallelPolicy(branches=1, max_depth=4),
        budget=Budget(model_calls=4, evaluator_calls=5, max_parallelism=1), quality=contract,
    )


def summarize(rows):
    group = {
        "cases": len(rows), "quality_mismatches": sum(row[1] != 0 for row in rows),
        "early_stops": sum(row[3] < row[2] for row in rows),
    }
    for arm, dispatch, evaluation in (("reference", 2, 4), ("certified", 3, 5)):
        total = sum(row[dispatch] for row in rows)
        group[f"{arm}_logical_agent_dispatches_total"] = total
        group[f"{arm}_logical_agent_dispatches_mean"] = total / len(rows)
        group[f"{arm}_local_evaluator_calls_total"] = sum(row[evaluation] for row in rows)
        group[f"{arm}_initial_local_evaluator_calls_total"] = len(rows)
    return group


async def collect():
    contract = QualityContract(
        id="deterministic-unit-interval-v1",
        metric=lambda record: record["observation"]["quality"],
        upper_bound=1.0, initial_candidate=lambda state, task: {"quality": task["initial"]},
    )
    rows = []
    for values in product((0.0, 0.5, 1.0), repeat=5):
        initial, *future = values
        task = {"initial": initial, "values": future}
        reference = await build(replace(contract, certified_stopping=False)).run(task)
        certified = await build(contract).run(task)
        for result in (reference, certified):
            assert result.metrics["raw_quality"] == result.best["quality"] == max(values)
            assert result.costs.evaluator_calls == result.costs.model_calls + 1
            assert result.tree.root.metadata["initial_evaluator_calls"] == 1
        assert reference.costs.model_calls == 4
        expected_used = 0 if initial == 1 else next(
            (i + 1 for i, quality in enumerate(future) if quality == 1), 4,
        )
        assert certified.costs.model_calls == expected_used
        assert reference.tree.root.metadata["quality_contract"] == (
            certified.tree.root.metadata["quality_contract"]
        )
        assert [node.observation for node in certified.tree.iter_nodes()] == (
            [node.observation for node in reference.tree.iter_nodes()][:certified.tree.size]
        )
        rows.append((initial, certified.metrics["raw_quality"] - reference.metrics["raw_quality"],
                     reference.costs.model_calls, certified.costs.model_calls,
                     reference.costs.evaluator_calls, certified.costs.evaluator_calls))
    result = {
        "schema_version": 1, "evidence_type": "exhaustive_deterministic_sdk_runtime_invariant",
        "title": "Certified stopping preserves raw quality on all 243 finite test trajectories",
        "provenance": {
            "python_version": platform.python_version(),
            "report_type": "deterministic engineering verification",
            "implementation": "DreamRSI.run with FunctionalAgentAdapter and QualityContract",
            "contract_semantics": "docs/quality-contract.md",
            "enumeration_reference": "tests/test_quality_contract.py::"
                                     "test_exact_prefix_optimality_on_every_bounded_finite_trajectory",
            "trajectory_values": [0.0, 0.5, 1.0], "initial_qualities": [0.0, 0.5, 1.0],
            "future_steps": 4, "upper_bound": 1.0,
            "baseline_certified_stopping": False, "certified_certified_stopping": True,
            "policy": "FixedParallelPolicy(branches=1, max_depth=4)",
            "shared_budget": {"model_calls": 4, "evaluator_calls": 5, "max_parallelism": 1},
            "shared_initial_evaluator_calls_per_case_per_arm": 1, "external_model_api_calls": 0,
            "interpretation": "Logical deterministic agent dispatches, not measured provider "
                              "calls, tokens, dollars, or real-model performance.",
        },
        **summarize(rows),
        "raw_quality_difference_distribution": [
            {"difference": value, "cases": count}
            for value, count in sorted(Counter(row[1] for row in rows).items())
        ],
        "certified_logical_agent_dispatches_distribution": [
            {"logical_agent_dispatches": value, "cases": count}
            for value, count in sorted(Counter(row[3] for row in rows).items())
        ],
        "groups_by_initial_quality": [],
    }
    for initial in (0.0, 0.5, 1.0):
        group = {"initial_quality": initial, **summarize([r for r in rows if r[0] == initial])}
        group = {key: value for key, value in group.items() if "evaluator_calls" not in key}
        result["groups_by_initial_quality"].append(group)
    assert (result["cases"], result["quality_mismatches"], result["early_stops"]) == (243, 0, 195)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("temp/beta-quality.json"))
    args = parser.parse_args()
    evidence = asyncio.run(collect())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {evidence['cases']} cases; aggregate evidence: {args.output}")


if __name__ == "__main__":
    main()
