#!/usr/bin/env python3
"""Deterministic numerical optimization — zero-dependency Dream-RSI example.

This demonstrates the full Dream-RSI loop (online explore → build tree →
replay → dream → improve policy → redeploy) without any API keys,
internet access, or external dependencies.

The "agent" is a simple numerical optimizer that tries to minimize f(x) = x²
by proposing random perturbations.  The "evaluator" scores candidates by
their closeness to zero.  Dream-RSI improves the exploration policy —
how many parallel branches to open, how deep to refine, etc. — across
successive rounds.

Run::

    python examples/01_toy_optimization.py

Reports measured scores. Online improvement is not guaranteed.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys

# Ensure the src directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dreamrsi import Budget, DreamRSI, DreamRSIConfig, FunctionalAgentAdapter

# ── The "agent": proposes candidate x values ──────────────────

class ToyOptimizer:
    """Generates candidate solutions for minimizing f(x) = x².

    Each call proposes a perturbation from the parent's x value.
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    async def __call__(self, state, context=None):
        """Propose a candidate x value."""
        parent_x = state["x"] if isinstance(state, dict) else self._rng.uniform(-10, 10)

        # Random perturbation with decreasing step size
        step = self._rng.gauss(0, max(abs(parent_x) * 0.5, 0.1))
        new_x = parent_x + step
        return {"x": new_x, "f_x": new_x ** 2}


# ── The "evaluator": scores candidates ────────────────────────

class MinimizationEvaluator:
    """Scores candidates by closeness to the optimum f(x) = 0.

    Score = -f(x) = -x² so that higher is better.
    """

    async def evaluate(self, candidate, context=None):
        if isinstance(candidate, dict):
            f_x = candidate.get("f_x", candidate.get("x", 0) ** 2)
        else:
            f_x = float(candidate) ** 2

        # Return a simple object with a .score attribute
        return type("Eval", (), {"score": -f_x})()


# ── Main ──────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Dream-RSI: Toy Optimization Example")
    print("=" * 60)
    print()
    print("Task: Minimize f(x) = x²")
    print("Agent: Random perturbation optimizer")
    print("Policy: Adapts exploration strategy across rounds")
    print()

    agent = ToyOptimizer(seed=42)
    evaluator = MinimizationEvaluator()

    config = DreamRSIConfig(
        default_batch_size=3,
        optimizer_variants=4,
        replay_max_rounds=50,
        replay_max_parallelism=8,
    )

    budget = Budget(
        max_nodes=30,
        max_rounds=10,
        max_depth=5,
    )

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(agent),
        evaluator=evaluator,
        config=config,
        budget=budget,
    )

    # Track progress

    def on_event(event):
        if event.type.value == "policy_promoted":
            d = event.data
            print(
                f"  🔄 Policy improved: {d.get('incumbent_score', 0):.4f} "
                f"→ {d.get('challenger_score', 0):.4f}"
            )

    rsi.on_event(on_event)

    # Run Dream-RSI improvement loop
    print("Running Dream-RSI with 5 recursive improvement rounds...")
    print()

    result = await rsi.improve(task={"x": 8.0}, rounds=5)

    # Report results
    print()
    print("─" * 60)
    print("Results:")
    print(f"  Best score:           {result.best_score:.6f}")
    if result.best and isinstance(result.best, dict):
        best_x = result.best.get("x", "?")
        if isinstance(best_x, float):
            print(f"  Best x:               {best_x:.6f}")
            print(f"  Best f(x) = x²:       {best_x**2:.6f}")
    print(f"  Total worlds:         {result.metrics.get('total_worlds', 0)}")
    print(f"  Policy promotions:    {result.metrics.get('policy_promotions', 0)}")
    print(f"  Agent calls:          {result.costs.model_calls:.0f}")
    print(f"  Evaluator calls:      {result.costs.evaluator_calls:.0f}")
    print(f"  Replay compute:       {result.costs.replay_compute_ms:.1f} ms")
    print()

    if result.champion_policy:
        print(f"  Champion policy:      {type(result.champion_policy).__name__}")
    else:
        print(f"  Policy:               {type(result.policy).__name__} (no promotion occurred)")

    print()
    print("✅ Dream-RSI completed successfully!")
    print()
    print("This demonstrates the core loop:")
    print("  1. Online exploration → builds discovery trees")
    print("  2. Trees become replay worlds (free simulators)")
    print("  3. Challenger policies evaluated via replay (no agent calls)")
    print("  4. Best policy promoted → redeployed online")
    print("  5. Repeat — selection improves replay score on fixed history only")


if __name__ == "__main__":
    asyncio.run(main())
