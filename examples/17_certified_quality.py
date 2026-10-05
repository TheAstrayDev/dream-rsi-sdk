"""Quality-preserving mechanics demo; deterministic agent, not an LLM benchmark."""

import asyncio
import json
from dataclasses import replace

from dreamrsi import Budget, DreamRSI, EconomyPlan, FunctionalAgentAdapter, QualityContract
from dreamrsi.policies import FixedParallelPolicy


def step(state, context):
    return {**state, "number": state.get("number", 0) + 1}


def score(candidate):
    return float(candidate["number"] == candidate["target"])


async def main():
    tasks = [{"target": number} for number in (2, 3, 4)]
    plan = EconomyPlan(baseline_calls_per_task=8, horizon=len(tasks))

    def runtime(quality=None):
        return DreamRSI(
            adapter=FunctionalAgentAdapter(step), evaluator=score,
            policy=FixedParallelPolicy(1, 8), budget=Budget(model_calls=8, max_parallelism=1),
            quality=quality, economy=plan,
        )

    quality = QualityContract(id="exact-match-v1", upper_bound=1)
    reference = runtime(replace(quality, certified_stopping=False))
    protected = runtime(quality)
    for task in tasks:
        baseline = await reference.run(task)
        result = await protected.run(task)
        assert baseline.best_score == result.best_score == 1
        print(f"Target {task['target']}: baseline={baseline.costs.model_calls}, "
              f"certified={result.costs.model_calls}, quality={result.metrics['raw_quality']}")
    report = plan.report(
        preparation_calls=protected.usage.calls_for("preparation"),
        deployment_calls=protected.usage.calls_for("deployment"),
        tasks_completed=len(tasks),
    )
    print("Deterministic mechanics only; counts are logical adapter calls, not paid requests.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
