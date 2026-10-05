"""Independent holdouts remain single-use across concurrent memory writers."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from dreamrsi.errors import ConfigurationError, PolicyError
from dreamrsi.policy_memory import AdaptivePolicyMemory
from dreamrsi.storage import InMemoryStore, SQLiteStore
from dreamrsi.validation import HoldoutPipeline, task_key


def memory(store):
    return AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: "family",
        raw_quality=lambda task, result: 1.,
        minimum_quality=lambda task: 1.,
    )


class AsyncCustomStore:
    """Old custom store API with genuine I/O scheduling points; no atomic CAS."""

    def __init__(self):
        self.storage = InMemoryStore()

    async def get_checkpoint(self, key):
        value = await self.storage.get_checkpoint(key)
        await asyncio.sleep(0)
        return value

    async def save_checkpoint(self, key, data):
        await asyncio.sleep(0)
        await self.storage.save_checkpoint(key, data)


class BarrierAtomicStore(InMemoryStore):
    """Force two memory instances to read the same previous reservation."""

    def __init__(self):
        super().__init__()
        self.reads = 0
        self.barrier = asyncio.Event()

    async def get_checkpoint(self, key):
        value = await super().get_checkpoint(key)
        if key.endswith(":reserved-holdouts") and self.reads < 2:
            self.reads += 1
            if self.reads == 2:
                self.barrier.set()
            await self.barrier.wait()
        return value


async def test_old_async_custom_store_serializes_one_memory_instance():
    store = AsyncCustomStore()
    shared = memory(store)
    outcomes = await asyncio.gather(
        shared._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}])),
        shared._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}])),
        return_exceptions=True,
    )
    assert sum(value is None for value in outcomes) == 1
    assert sum(isinstance(value, ConfigurationError) for value in outcomes) == 1
    saved = await store.get_checkpoint(shared._holdout_key("family"))
    assert saved["task_keys"] == [task_key({"seed": 1})]


async def test_two_memory_instances_cannot_reserve_same_world_on_atomic_store():
    store = BarrierAtomicStore()
    first, second = memory(store), memory(store)
    outcomes = await asyncio.wait_for(asyncio.gather(
        first._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}])),
        second._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}])),
        return_exceptions=True,
    ), timeout=2)
    assert sum(value is None for value in outcomes) == 1
    assert sum(isinstance(value, ConfigurationError) for value in outcomes) == 1
    saved = await store.get_checkpoint(first._holdout_key("family"))
    assert saved["task_keys"] == [task_key({"seed": 1})]


async def test_concurrent_distinct_holdouts_do_not_lose_prior_reservations():
    store = BarrierAtomicStore()
    first, second = memory(store), memory(store)
    await asyncio.wait_for(asyncio.gather(
        first._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}])),
        second._reserve_holdouts("family", HoldoutPipeline([{"seed": 2}])),
    ), timeout=2)
    saved = await store.get_checkpoint(first._holdout_key("family"))
    assert set(saved["task_keys"]) == {task_key({"seed": 1}), task_key({"seed": 2})}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_compare_and_swap_rejects_stale_expected_without_writing(backend, tmp_path):
    store = InMemoryStore() if backend == "memory" else SQLiteStore(tmp_path / "memory.db")
    try:
        assert await store.compare_and_swap_checkpoint("key", None, {"worlds": [1]})
        assert not await store.compare_and_swap_checkpoint("key", None, {"worlds": [2]})
        assert await store.get_checkpoint("key") == {"worlds": [1]}
        assert await store.compare_and_swap_checkpoint("key", {"worlds": [1]}, {"worlds": [1, 2]})
    finally:
        await store.close()


def test_independent_sqlite_connections_atomically_reject_one_concurrent_writer(tmp_path):
    path = tmp_path / "shared.db"
    initial = SQLiteStore(path)
    asyncio.run(initial.close())
    barrier = threading.Barrier(2)

    def writer(seed):
        async def reserve():
            store = SQLiteStore(path)
            try:
                expected = await store.get_checkpoint("same-holdout")
                barrier.wait(timeout=5)
                return await store.compare_and_swap_checkpoint(
                    "same-holdout", expected, {"reserved_by": seed},
                )
            finally:
                await store.close()

        return asyncio.run(reserve())

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, [1, 2]))
    assert sorted(outcomes) == [False, True]
    final = SQLiteStore(path)
    try:
        saved = asyncio.run(final.get_checkpoint("same-holdout"))
        assert saved in ({"reserved_by": 1}, {"reserved_by": 2})
        assert not final.connection.in_transaction
    finally:
        asyncio.run(final.close())


async def test_incompatible_existing_reservation_remains_rejected():
    store = InMemoryStore()
    shared = memory(store)
    await store.save_checkpoint(shared._holdout_key("family"), {"schema": 999})
    with pytest.raises(PolicyError, match="Incompatible holdout"):
        await shared._reserve_holdouts("family", HoldoutPipeline([{"seed": 1}]))
    assert await store.get_checkpoint(shared._holdout_key("family")) == {"schema": 999}
