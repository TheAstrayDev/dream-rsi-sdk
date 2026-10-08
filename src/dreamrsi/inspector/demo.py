"""A real SDK execution with a deterministic local adapter, never an LLM benchmark."""

from __future__ import annotations

import asyncio
import threading

from .journal import LiveInspector


async def run_demo(inspector: LiveInspector, stop: threading.Event, *, once=False):
    from dreamrsi import Budget, DreamRSI, DreamRSIConfig, FunctionalAgentAdapter, QualityContract
    from dreamrsi.models.policy import PolicyDecision
    from dreamrsi.policies import BreadthFirstPolicy, GreedyPolicy

    class DemoPolicy:
        def decide(self, view):
            ranked = sorted(view.frontier, key=lambda n: (-(n.score or 0), n.depth))
            return PolicyDecision(
                expand=[n.id for n in ranked[:3]],
                reason="Expand the three highest-scoring available branches, including the root.",
            )

    iteration = 0
    while not stop.is_set():
        iteration += 1

        async def step(state, context):
            delay = 0.7 + context["round"] % 3 * 0.3
            await asyncio.sleep(delay)
            if stop.is_set():
                raise asyncio.CancelledError()
            if context["round"] == 3 and state["x"] > 4:
                raise ValueError("Candidate violates the configured stability constraint")
            factor = 0.45 if context["round"] % 2 else 0.65
            x = state["x"] * factor
            return {
                "x": round(x, 5),
                "loss": round(x * x, 5),
                "method": "Reduce the controller offset toward zero",
            }

        sdk = DreamRSI(
            adapter=FunctionalAgentAdapter(step),
            evaluator=lambda value: 1 / (1 + value["x"] ** 2),
            policy=DemoPolicy(),
            budget=Budget(model_calls=14, max_parallelism=3, max_rounds=7),
            config=DreamRSIConfig(replay_max_rounds=7),
            quality=QualityContract(
                id="quadratic-demo-v1",
                upper_bound=1,
                preserve_policy=False,
                certified_stopping=False,
            ),
            inspector=inspector,
        )
        try:
            result = await sdk.run(
                {"x": 6.0, "demo": True, "name": f"Controller calibration · run {iteration}"}
            )
            if result.tree is not None:
                from dreamrsi.replay import ReplayWorld

                await inspector.compare(
                    sdk,
                    ReplayWorld(result.tree),
                    [BreadthFirstPolicy(batch_size=1), GreedyPolicy(batch_size=1)],
                )
        except asyncio.CancelledError:
            break
        if once:
            break
        for _ in range(40):
            if stop.is_set():
                break
            await asyncio.sleep(0.1)
