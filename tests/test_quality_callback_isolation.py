"""Quality callbacks cannot mutate answers or invalidate saved source profiles."""

import copy

import pytest

from dreamrsi import Budget, DreamRSI, QualityContract, checkpoints
from dreamrsi.artifacts import PolicyArtifact, PolicyCodec, SourcePolicy
from dreamrsi.policies import CertifiedPolicy, FixedParallelPolicy, PrefixPolicy
from dreamrsi.process_sandbox import ProcessPolicySandbox
from dreamrsi.quality import get_record_quality
from dreamrsi.sandbox import PolicySandbox
from dreamrsi.storage import InMemoryStore


def completed_record():
    return {
        "score": .9,
        "status": "completed",
        "observation": {"quality": .9, "answer": [1, 2, 3]},
        "diagnostics": {"quality_contract": {"id": "snapshot-v1", "upper_bound": 1.}},
    }


def popping_metric(record):
    return record["observation"].pop("quality", None)


def test_mutating_metric_gets_a_fresh_snapshot_on_every_extraction():
    record = completed_record()
    original = copy.deepcopy(record)
    assert get_record_quality(record, popping_metric) == .9
    assert get_record_quality(record, popping_metric) == .9
    assert record == original


def test_callback_cannot_change_certificate_or_nested_answer():
    record = completed_record()
    original = copy.deepcopy(record)

    def metric(snapshot):
        snapshot["diagnostics"]["quality_contract"]["upper_bound"] = .9
        snapshot["observation"]["answer"].clear()
        snapshot["score"] = 0
        return .9

    assert get_record_quality(record, metric) == .9
    assert record == original


def test_raising_callback_cannot_leave_partial_mutations():
    record = completed_record()
    original = copy.deepcopy(record)

    def metric(snapshot):
        snapshot["observation"].clear()
        raise ValueError("bad extractor")

    assert get_record_quality(record, metric) is None
    assert record == original


def test_unsnapshotable_record_fails_open_without_calling_metric():
    class CannotSnapshot:
        def __deepcopy__(self, memo):
            raise TypeError("external handle")

    record = {"score": .9, "observation": CannotSnapshot()}

    def metric(snapshot):
        raise AssertionError("A metric must not receive an unisolated record")

    assert get_record_quality(record, metric) is None
    assert get_record_quality(record) == .9


@pytest.mark.parametrize("quality", [.9, 1.])
async def test_mutating_metric_preserves_returned_answer_and_bound(quality):
    rsi = DreamRSI(
        agent=lambda task: {"quality": quality, "answer": "valid"},
        evaluator=lambda candidate: candidate["quality"],
        policy=FixedParallelPolicy(1, 2),
        budget=Budget(model_calls=2, max_parallelism=1),
        quality=QualityContract(id="snapshot-v1", metric=popping_metric, upper_bound=1.),
    )
    result = await rsi.run({})
    assert result.best == {"quality": quality, "answer": "valid"}
    assert result.metrics["raw_quality"] == quality
    assert result.costs.model_calls == (1 if quality == 1. else 2)
    assert all(
        node.observation["quality"] == quality
        for node in result.tree.iter_nodes() if node.observation is not None
    )


def nested_source(sandbox):
    source = SourcePolicy(
        PolicyArtifact("def decide(view):\n    return {'expand': [], 'stop': True}"), sandbox,
    )
    return CertifiedPolicy(PrefixPolicy(source, 5), "nested-v1")


async def test_wrapped_process_source_can_restore_its_own_campaign():
    sandbox = ProcessPolicySandbox()
    policy = nested_source(sandbox)
    rsi = DreamRSI(
        agent=lambda task: 1, evaluator=lambda candidate: 1,
        policy=policy, store=InMemoryStore(),
    )
    assert rsi.policy_codec.sandbox is sandbox
    await checkpoints.save(rsi, "nested-source", {}, 0)
    assert await checkpoints.restore(rsi, "nested-source", {}) == (0, "ready")
    assert rsi._get_policy().policy.policy.sandbox is sandbox


def test_explicit_codec_retains_priority_over_nested_source_sandbox():
    class FalseyCodec(PolicyCodec):
        def __bool__(self):
            return False

    codec = FalseyCodec(PolicySandbox())
    rsi = DreamRSI(
        agent=lambda task: 1, evaluator=lambda candidate: 1,
        policy=nested_source(ProcessPolicySandbox()), policy_codec=codec,
    )
    assert rsi.policy_codec is codec


def test_developer_sandbox_retains_priority_when_codec_is_inferred():
    class Developer:
        sandbox = PolicySandbox()

    rsi = DreamRSI(
        agent=lambda task: 1, evaluator=lambda candidate: 1,
        policy=nested_source(ProcessPolicySandbox()), policy_optimizer=Developer(),
    )
    assert rsi.policy_codec.sandbox is Developer.sandbox
