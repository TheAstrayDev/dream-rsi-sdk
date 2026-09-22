import pytest

from dreamrsi import Budget, DefaultMethod, DreamRSI, HoldoutPipeline, SQLiteStore
from dreamrsi.errors import ConfigurationError
from dreamrsi.replay import StrictReplay


async def test_export_preserves_per_run_usage_after_runtime_reuse(tmp_path):
    import json

    from dreamrsi import FunctionalAgentAdapter, Usage

    def step(state, context):
        context["report_usage"](Usage(input_tokens=3, output_tokens=4, provider_calls=1))
        return state

    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(step), evaluator=float, budget=Budget(model_calls=1)
    )
    await runtime.run(1)
    result = await runtime.run(2)
    assert result.costs.input_tokens == 3
    assert result.costs.output_tokens == 4
    assert result.costs.provider_calls == 1
    assert runtime.usage.spent["tokens"] == 14
    output = tmp_path / "run.json"
    await runtime.export_run(result, str(output))
    costs = json.loads(output.read_text(encoding="utf-8"))["costs"]
    for key, value in result.costs.to_dict().items():
        assert costs[key] == value


async def test_changed_replay_coefficients_rejected_on_sqlite_resume(tmp_path):
    store = SQLiteStore(tmp_path / "campaign.db")
    first = DreamRSI(
        agent=lambda x: x,
        evaluator=float,
        store=store,
        replay=StrictReplay(beta1=0.01),
        budget=Budget(model_calls=1),
        method=DefaultMethod("coefficients"),
    )
    await first.improve(1, rounds=1)
    await store.close()
    reopened = SQLiteStore(tmp_path / "campaign.db")
    second = DreamRSI(
        agent=lambda x: x,
        evaluator=float,
        store=reopened,
        replay=StrictReplay(beta1=0.9),
        budget=Budget(model_calls=1),
        method=DefaultMethod("coefficients", resume=True),
    )
    with pytest.raises(ConfigurationError, match="configuration changed"):
        await second.improve(1, rounds=2)
    await reopened.close()


async def test_validation_failure_is_evidence_and_consumes_batch():
    from dreamrsi.policies import BalancedPolicy

    class BrokenPolicy:
        async def decide(self, view):
            raise ValueError("candidate failure")

    pipeline = HoldoutPipeline([9])
    runtime = DreamRSI(
        agent=lambda x: x, evaluator=float, budget=Budget(model_calls=1), validation=pipeline
    )
    await pipeline.prepare(runtime, 1)
    evidence = await pipeline.evaluate(runtime, BalancedPolicy(), BrokenPolicy())
    assert evidence["validation_status"] == "insufficient_evidence"
    assert evidence["validation_scores"] == {}
    assert evidence["validation_reports"][1]["error"] == "candidate failure"
    assert evidence["validation_reports"][0]["score"] is not None
    assert pipeline.used == 1
    exhausted = await pipeline.evaluate(runtime, BalancedPolicy(), BrokenPolicy())
    assert exhausted["validation_status"] == "exhausted"


async def test_ambiguous_validation_cannot_repeat_external_work(tmp_path):
    class FailingStore(SQLiteStore):
        async def save_checkpoint(self, key, data):
            if key.endswith(":validation") and data["worlds"]:
                raise OSError("crash after external validation task")
            await super().save_checkpoint(key, data)

    calls = []

    def agent(task):
        calls.append(task)
        return task

    store = FailingStore(tmp_path / "validation.db")
    first = DreamRSI(
        agent=agent,
        evaluator=float,
        store=store,
        validation=HoldoutPipeline([9]),
        budget=Budget(model_calls=1),
        method=DefaultMethod("validation"),
    )
    with pytest.raises(OSError, match="crash"):
        await first.improve(1, rounds=1)
    assert calls == [9]
    await store.close()

    reopened = SQLiteStore(tmp_path / "validation.db")
    second = DreamRSI(
        agent=agent,
        evaluator=float,
        store=reopened,
        validation=HoldoutPipeline([9]),
        budget=Budget(model_calls=1),
        method=DefaultMethod("validation", resume=True),
    )
    with pytest.raises(ConfigurationError, match="validation collection"):
        await second.improve(1, rounds=1)
    assert calls == [9]
    third = DreamRSI(
        agent=agent,
        evaluator=float,
        store=reopened,
        validation=HoldoutPipeline([9], abandon_inflight=True),
        budget=Budget(model_calls=1),
        method=DefaultMethod("validation", resume=True),
    )
    result = await third.improve(1, rounds=1)
    assert calls == [9, 1]
    assert result.costs.model_calls == 2
    assert third.validation.prepared
    assert third.validation.worlds == []
    assert third.validation.next_task_index == 1
    await reopened.close()
