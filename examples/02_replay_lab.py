"""Record once, compare policies without additional agent/evaluator calls.

Toy mechanics demo, not an LLM performance benchmark. Run from the checkout.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter  # noqa: E402
from dreamrsi.policies import BalancedPolicy, BreadthFirstPolicy, DepthFirstPolicy  # noqa: E402
from dreamrsi.replay import ReplayWorld  # noqa: E402


async def main():
    calls = {"agent": 0, "evaluator": 0}

    async def step(state):
        calls["agent"] += 1
        return state / 2

    async def evaluate(candidate):
        calls["evaluator"] += 1
        return -candidate ** 2

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(step), evaluator=evaluate,
        budget=Budget(model_calls=8, max_rounds=8, max_parallelism=2),
    )
    result = await rsi.run(8.0)
    world = ReplayWorld(result.tree)
    before = calls.copy()
    print("Toy recorded-tree replay; results do not establish online improvement.")
    print(f"Recorded calls: {calls}")
    print(f"{'Policy':24} {'Best score':>12} {'Probes':>8} {'Rounds':>8} {'Objective':>12}")
    for policy in (BalancedPolicy(), BreadthFirstPolicy(), DepthFirstPolicy()):
        trajectory = await rsi.replay(world, policy)
        print(f"{type(policy).__name__:24} {str(trajectory.best_score):>12} "
              f"{trajectory.total_probes:8} {trajectory.total_rounds:8} "
              f"{str(trajectory.replay_score):>12}")
    for label, key in (("agent", "agent"), ("evaluator", "evaluator")):
        delta = calls[key] - before[key]
        print(f"Additional {label} calls during replay: {delta}")
        assert delta == 0, "Replay unexpectedly invoked online work"


if __name__ == "__main__":
    asyncio.run(main())
