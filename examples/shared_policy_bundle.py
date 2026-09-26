"""Transfer a real recorded toy tree and a policy between independent stores.

Run: python examples/shared_policy_bundle.py
No network, credentials, or model calls. This is an integration demo, not a benchmark.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from dreamrsi import (
    AdaptivePolicyMemory,
    Budget,
    DefaultMethod,
    DreamRSI,
    FunctionalAgentAdapter,
    HoldoutPipeline,
    PolicyMemorySettings,
    SQLiteStore,
)
from dreamrsi.policies import DepthFirstPolicy

FAMILY = "numeric-halving:v1"


def build_runtime(task, saved_policy):
    return DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state: {**state, "x": state["x"] / 2}),
        evaluator=lambda candidate: -(candidate["x"] ** 2),
        policy=saved_policy if saved_policy is not None else DepthFirstPolicy(),
        budget=Budget(model_calls=2, max_parallelism=1, max_depth=2),
        method=DefaultMethod(online=False),
        # Required by AdaptivePolicyMemory. Not collected in this reuse-only demo.
        validation=HoldoutPipeline([{"kind": FAMILY, "x": 32.0, "split": "validation"}]),
    )


def make_memory(store):
    return AdaptivePolicyMemory(
        store=store,
        runtime_factory=build_runtime,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, result: result.best_score,
        minimum_quality=lambda task: -4.0,
        settings=PolicyMemorySettings(
            accept_world=lambda current, recorded, world: current["kind"] == recorded["kind"],
            # Explicit reuse-only mode: report degradation without starting training.
            allow_training=lambda task, policy, quality, floor: False,
        ),
    )


async def main():
    with TemporaryDirectory(prefix="dreamrsi-sharing-") as directory:
        folder = Path(directory)
        sender_store = SQLiteStore(folder / "sender.sqlite3")
        receiver_store = SQLiteStore(folder / "receiver.sqlite3")
        try:
            sender = make_memory(sender_store)
            task = {"kind": FAMILY, "x": 8.0}
            # A supplied policy, not a learned or holdout-promoted champion.
            await sender.remember(task, DepthFirstPolicy(), origin="external")
            await sender.run(task)  # Records the actual toy agent's discovery tree.
            bundle = folder / "shared-policy.dreamrsi.json"
            exported = await sender.export_bundle(task, bundle)

            # A recipient needs only this JSON file, not the sender's database.
            receiver = make_memory(receiver_store)
            new_task = {"kind": FAMILY, "x": 6.0}
            imported = await receiver.import_bundle(bundle, task=new_task)
            assert (imported["policies"], imported["worlds"]) == (1, 1)
            assert isinstance(await receiver.load(FAMILY, task=new_task), DepthFirstPolicy)
            outcome = await receiver.run(new_task)
            assert outcome.reused_policy and not outcome.trained and not outcome.degraded
            assert outcome.result.best["x"] == 1.5
            assert outcome.result.costs.model_calls == 2
            received = await receiver.export_bundle(new_task, folder / "receiver.dreamrsi.json")
            assert received["worlds"] == 2  # Imported history plus the new task's tree.

            print(f"Transferred: {exported['policies']} policy, {exported['worlds']} tree")
            print(f"Reused policy: {outcome.reused_policy}; trained: {outcome.trained}")
            print(
                f"Raw quality: {outcome.raw_quality}; "
                f"agent calls: {outcome.result.costs.model_calls}"
            )
            print(f"Recipient now stores {received['worlds']} trees")
        finally:
            await sender_store.close()
            await receiver_store.close()


if __name__ == "__main__":
    asyncio.run(main())
