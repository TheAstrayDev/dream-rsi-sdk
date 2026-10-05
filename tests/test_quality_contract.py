import math
from itertools import product

import pytest

from dreamrsi.models.discovery import NodeStatus
from dreamrsi.models.replay import ReplayStep, ReplayTrajectory
from dreamrsi.optimization import DeterministicPolicyOptimizer
from dreamrsi.policies import CertifiedPolicy, FixedParallelPolicy, PrefixPolicy
from dreamrsi.quality import (
    QualityContract,
    get_record_quality,
    quality_certificate,
    quality_of_record,
    select_best_record,
)
from dreamrsi.validation import HoldoutPipeline


def record(quality, *, score=..., depth=1, bound=None, contract_id="raw-v1"):
    metadata = {"id": contract_id, "raw_quality": quality}
    if depth == 0:
        metadata["upper_bound"] = bound
    return {
        "depth": depth,
        "score": quality if score is ... else score,
        "status": NodeStatus.COMPLETED.value,
        "observation": {"quality": quality},
        "diagnostics": {"quality_contract": metadata},
    }


def test_raw_selector_matches_returned_observation_not_composite_score():
    contract = QualityContract(id="raw-v1", metric=lambda record: record["observation"]["quality"])
    records = {
        "a": record(.95, score=.70),
        "b": record(.90, score=.80),
    }
    assert select_best_record(records, contract) == ("a", .95)
    assert select_best_record(records) == ("b", .80)


def test_valid_initial_incumbent_survives_invalid_model_observations():
    contract = QualityContract(id="raw-v1", metric=lambda record: record["observation"]["quality"])
    records = {
        "root": record(.94, score=.50, depth=0, bound=1.),
        "invalid": record(None, score=0.),
    }
    assert select_best_record(records, contract) == ("root", .94)
    assert not quality_certificate(records, contract.id)


def test_negative_quality_stable_ties_and_missing_values():
    assert select_best_record({"a": {"score": -4}, "b": {"score": -4}}) == ("a", -4.)
    assert select_best_record({"a": {"score": None}}) == (None, None)
    assert select_best_record({}) == (None, None)


@pytest.mark.parametrize("value", [True, "1", math.nan, math.inf, 10**400])
def test_invalid_raw_quality_never_becomes_a_selectable_zero(value):
    contract = QualityContract(id="raw-v1", metric=lambda record: value)
    assert quality_of_record({"score": 1.}, contract) is None
    assert select_best_record({"a": {"score": 1.}}, contract) == (None, None)


@pytest.mark.parametrize("status", [NodeStatus.FAILED.value, NodeStatus.SKIPPED.value, None])
def test_failed_record_never_authorizes_quality_even_with_constant_metric(status):
    contract = QualityContract(id="raw-v1", metric=lambda record: 1.)
    invalid = record(1., score=0., depth=0, bound=1.)
    invalid["status"] = status
    assert quality_of_record(invalid, contract) is None
    assert select_best_record({"root": invalid}, contract) == (None, None)
    assert not quality_certificate({"root": invalid}, contract.id)


def test_unscored_record_never_authorizes_quality_even_with_constant_metric():
    contract = QualityContract(id="raw-v1", metric=lambda record: 1.)
    invalid = record(1., score=None, depth=0, bound=1.)
    assert quality_of_record(invalid, contract) is None
    assert not quality_certificate({"root": invalid}, contract.id)


@pytest.mark.parametrize("status", [NodeStatus.COMPLETED, NodeStatus.COMPLETED.value])
def test_actual_node_status_allows_completed_score_and_certificate(status):
    contract = QualityContract(id="raw-v1", metric=lambda record: record["score"])
    completed = record(1., score=1., depth=0, bound=1.)
    completed["status"] = status
    assert quality_of_record(completed, contract) == 1.
    assert select_best_record({"root": completed}, contract) == ("root", 1.)
    assert quality_certificate({"root": completed}, contract.id)


@pytest.mark.parametrize("value", [True, "1", math.nan, math.inf, -math.inf])
def test_invalid_static_bounds_rejected(value):
    with pytest.raises(ValueError, match="upper_bound"):
        QualityContract(id="raw-v1", upper_bound=value)


@pytest.mark.parametrize("name", ["metric", "initial_candidate"])
def test_noncallable_hooks_rejected(name):
    with pytest.raises(ValueError, match=name):
        QualityContract(id="raw-v1", **{name: 1})


@pytest.mark.parametrize("value", [None, "", " ", 1])
def test_contract_requires_semantic_identity(value):
    with pytest.raises(ValueError, match="id"):
        QualityContract(id=value)


def test_failing_hooks_do_not_authorize_stopping_or_zero_quality():
    def fail(*args):
        raise ValueError("Uncertified task")

    contract = QualityContract(id="raw-v1", metric=fail, upper_bound=fail)
    assert contract.bound({}) is None
    assert contract.quality({"observation": {}, "score": 1.}) is None
    assert quality_of_record({"observation": {}, "score": 1.}, contract) is None


@pytest.mark.parametrize("value", [None, True, "1", math.nan, math.inf])
def test_invalid_dynamic_bounds_leave_stopping_open(value):
    contract = QualityContract(id="raw-v1", upper_bound=lambda task: value)
    assert contract.bound({}) is None


def test_initial_candidate_is_local_data_not_trusted_quality():
    contract = QualityContract(
        id="raw-v1", initial_candidate=lambda state, task: state["candidate"],
    )
    candidate = contract.initial_candidate({"candidate": {"answer": 42}}, {})
    assert candidate == {"answer": 42}
    assert contract.quality({"observation": candidate}) is None
    assert contract.quality({"observation": candidate, "score": .8}) == .8


def test_checkpoint_describes_contract_and_callback_identity():
    default = QualityContract(id="raw-v1", upper_bound=1.)
    assert default.checkpoint_config() == {
        "id": "raw-v1", "upper_bound": 1., "metric": "score", "initial_candidate": False,
        "preserve_policy": True,
        "certified_stopping": True,
    }
    dynamic = QualityContract(
        id="raw-v2", metric=lambda record: 1., upper_bound=lambda task: 1.,
        initial_candidate=lambda state, task: {},
    )
    assert dynamic.checkpoint_config() == {
        "id": "raw-v2", "upper_bound": "callable", "metric": "callable",
        "initial_candidate": True,
        "preserve_policy": True,
        "certified_stopping": True,
    }


@pytest.mark.parametrize("value", [1, 0, "false", None])
def test_policy_preservation_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="preserve_policy"):
        QualityContract(id="raw-v1", preserve_policy=value)


def test_empirical_policy_changes_require_explicit_opt_out_and_fingerprint():
    contract = QualityContract(id="raw-v1", preserve_policy=False)
    assert contract.checkpoint_config()["preserve_policy"] is False


@pytest.mark.parametrize("value", [1, 0, "false", None])
def test_certified_stopping_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="certified_stopping"):
        QualityContract(id="raw-v1", certified_stopping=value)


def test_full_reference_stopping_flag_has_distinct_checkpoint_semantics():
    reference = QualityContract(id="raw-v1", certified_stopping=False)
    protected = QualityContract(id="raw-v1")
    assert reference.id == protected.id
    assert reference.checkpoint_config()["certified_stopping"] is False
    assert reference.checkpoint_config() != protected.checkpoint_config()


def test_record_metric_receives_same_context_as_validation():
    value = record(.8, score=.5, depth=2)
    def metric(context):
        assert context["depth"] == 2
        assert context["diagnostics"]["quality_contract"]["id"] == "raw-v1"
        return context["observation"]["quality"]
    assert get_record_quality(value, metric) == .8


def test_certificate_requires_exact_attained_bound_and_consistent_metadata():
    records = {"root": record(.4, depth=0, bound=1.), "a": record(1.)}
    assert quality_certificate(records, "raw-v1")
    assert not quality_certificate(records, "another-contract")
    records["a"]["diagnostics"]["quality_contract"]["raw_quality"] = 1.01
    assert not quality_certificate(records, "raw-v1")  # contradictory bound
    records["a"]["diagnostics"]["quality_contract"]["raw_quality"] = .99999999999999
    assert not quality_certificate(records, "raw-v1")  # no hidden tolerance
    records["a"].pop("diagnostics")
    assert not quality_certificate(records, "raw-v1")


def test_negative_bound_and_invalid_candidate_can_coexist_with_certificate():
    records = {
        "root": record(-4., depth=0, bound=-1.),
        "invalid": record(None),
        "best": record(-1.),
    }
    assert quality_certificate(records, "raw-v1")


def test_missing_multiple_roots_and_invalid_metadata_leave_stopping_open():
    assert not quality_certificate({}, "raw-v1")
    assert not quality_certificate({"a": record(1.)}, "raw-v1")
    assert not quality_certificate({"root": record(None, depth=0, bound=1.)}, "raw-v1")
    assert not quality_certificate({
        "root": record(1., depth=0, bound=1.),
        "second-root": record(1., depth=0, bound=1.),
    }, "raw-v1")
    assert not quality_certificate({"root": record(1., depth=0, bound=None)}, "raw-v1")
    assert not quality_certificate({"root": record(True, depth=0, bound=1.)}, "raw-v1")


def test_exact_prefix_optimality_on_every_bounded_finite_trajectory():
    cases, early_stops = 0, 0
    for values in product((0., .5, 1.), repeat=5):
        initial, *future = values
        records = {"root": record(initial, depth=0, bound=1.)}
        used = 0
        while used < len(future) and not quality_certificate(records, "raw-v1"):
            records[str(used)] = record(future[used])
            used += 1
        seen = [r["diagnostics"]["quality_contract"]["raw_quality"] for r in records.values()]
        assert max(seen) == max(values)
        assert used <= len(future)
        early_stops += used < len(future)
        cases += 1
    assert cases == 243
    assert early_stops == 195


def test_plateau_does_not_prove_a_future_bound():
    # Two possible worlds have the same visible prefix. A stop based on that
    # prefix alone cannot distinguish a plateau from a later improvement.
    records = {"root": record(.5, depth=0, bound=1.), "a": record(.5)}
    assert not quality_certificate(records, "raw-v1")
    assert max((.5, .5)) < max((.5, .5, .9))


def test_all_in_break_even_counts_preparation_and_has_strict_boundary():
    preparation, baseline_per_task, deployment_per_task = 8, 4, 1
    assert preparation + 2 * deployment_per_task > 2 * baseline_per_task
    assert preparation + 3 * deployment_per_task < 3 * baseline_per_task
    assert not 2 * (baseline_per_task - deployment_per_task) > 6


def test_unscored_and_failed_records_cannot_inflate_validation_or_derive_zero_prefix():
    root = record(1., score=None, depth=0, bound=1.)
    failed = record(1., score=.1)
    failed["status"] = NodeStatus.FAILED.value
    trajectory = ReplayTrajectory(
        "world", "incumbent", total_rounds=4, best_score=.8,
        observations={
            "root": root,
            "failed": failed,
            "winner": record(.7, score=.2),
            "later": record(.6, score=.8),
        },
        steps=[
            ReplayStep(1, ["root"], ["failed"], .1, 1),
            ReplayStep(2, ["root"], ["winner"], .2, 2),
            ReplayStep(3, ["winner"], ["later"], .8, 3),
            ReplayStep(4, ["later"], [], .8, 3),
        ],
    )
    def metric(value):
        return value["observation"]["quality"]
    raw_pipeline = HoldoutPipeline([1], quality_metric=metric, quality_metric_id="raw-v1")
    assert raw_pipeline.quality_from_trajectory(trajectory) == .7
    optimizer = DeterministicPolicyOptimizer(quality_metric=metric)
    assert optimizer._prefix_round_limit([trajectory]) == 2
    assert HoldoutPipeline([1]).quality_from_trajectory(trajectory) == .8
    assert DeterministicPolicyOptimizer()._prefix_round_limit([trajectory]) == 3


def test_invalid_only_replay_has_unknown_quality_instead_of_zero_prefix():
    trajectory = ReplayTrajectory(
        "world", "incumbent", best_score=0., total_rounds=4,
        observations={"root": record(1., score=None, depth=0, bound=1.)},
    )
    pipeline = HoldoutPipeline(
        [1], quality_metric=lambda record: 1., quality_metric_id="raw-v1",
    )
    assert pipeline.quality_from_trajectory(trajectory) is None
    assert DeterministicPolicyOptimizer(
        quality_metric=lambda record: 1.,
    )._prefix_round_limit([trajectory]) is None


async def test_certified_builtin_uses_existing_parameter_search_after_unwrapping():
    incumbent = CertifiedPolicy(PrefixPolicy(FixedParallelPolicy(branches=2), 4), "raw-v1")
    variants = await DeterministicPolicyOptimizer(num_variants=5).generate(incumbent, [])
    assert len(variants) == 5
    assert isinstance(variants[-1], FixedParallelPolicy)
