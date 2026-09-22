import copy
import json
from dataclasses import asdict, replace

import pytest

from dreamrsi import DeveloperConfig, PolicyArtifact, PolicySandbox, SQLiteStore
from dreamrsi.appendix import (
    AppendixPolicyDeveloper,
    AppendixSourcePolicy,
    GridCampaign,
    GridPlan,
    GridPlanningContext,
    GridTrace,
    LLMDesignedMethod,
    Observation,
    OptimalPolicy,
    beta_sweep,
    finalize_result,
)
from dreamrsi.appendix.observation_signal import (
    branch_failed_hard,
    probe_improved_vs_parent,
    successful,
    trajectory_signal,
)
from dreamrsi.appendix.policy import choose_default_beta
from dreamrsi.errors import ConfigurationError, PolicyError, SandboxError

SOURCE = """
from see.policy.api import (
    LLMDesignedMethod, GridPlan, SimResult, _budget_done, _record_curve, finalize_result
)
from see.policy.observation_signal import successful
NAME = "OptimalPolicy"
class OptimalPolicy(LLMDesignedMethod):
    def __init__(self):
        self.beta = float(self.config.get("beta", 0.6))
    def _schedule(self, beta):
        return {"probes": 1 + int(3 * beta)}
    def plan_grid(self, context):
        width = min(context.fallback_branch_count, context.hard_max_branch_count)
        depth = min(context.fallback_refine_count, context.hard_max_refine_count)
        if context.trace_branch_count is not None:
            width = min(width, context.trace_branch_count)
        if context.trace_refine_count is not None:
            depth = min(depth, context.trace_refine_count)
        return GridPlan(branch_count=width, refine_count=depth, reason="Context bootstrap")
    def solve(self, question, budget=None):
        question.reset()
        res = SimResult()
        schedule = self._schedule(self.beta)
        while not _budget_done(question, budget):
            prefix = question.observed()
            remaining = schedule["probes"] - len(prefix)
            batch = question.legal_actions()[:min(question.max_parallelism, remaining)]
            if not batch or remaining <= 0:
                break
            question.probe_batch(batch, on_reveal=lambda obs: _record_curve(res, question))
        return finalize_result(question, res)
"""


def obs(branch, attempt, score=None, **kwargs):
    return Observation(
        branch,
        attempt,
        score,
        **{
            "evaluated": True,
            "valid": True,
            "fail_class": "ok",
            **kwargs,
        },
    )


def trace():
    return GridTrace(
        "fixture",
        0.0,
        (
            (obs(0, 0, 0.2), obs(0, 1, 1.0)),
            (obs(1, 0, 0.4), obs(1, 1, 0.8)),
        ),
        (("direction-a",), ("direction-b",)),
    )


def context(**kwargs):
    return GridPlanningContext(
        **{
            "fallback_branch_count": 2,
            "fallback_refine_count": 1,
            "max_parallelism": 2,
            **kwargs,
        }
    )


def test_observation_success_recovery_and_reopening():
    success = obs(0, 0, 2, valid=False, n_valid=0, n_total=5)
    assert successful(success)
    repair = obs(0, 1, fail_class="compile_other", error="compile failed", n_valid=0)
    assert not branch_failed_hard(repair)
    signal = trajectory_signal([success, repair])
    assert signal["anchor"] == 2
    assert signal["repairable"]
    hard = [obs(0, i, fail_class="dependency", error="unavailable") for i in (2, 3)]
    assert trajectory_signal([success, *hard])["hard_unrecoverable"]
    reopened = trajectory_signal([success, *hard, obs(0, 4, 3)])
    assert not reopened["hard_unrecoverable"]
    assert reopened["anchor"] == 3


def test_question_prefix_atomic_legality_deltas_and_callback_order():
    question = trace().question(GridPlan(2, 1, "test"), 2)
    assert question.observed() == {}
    assert question.legal_actions() == ["0:0", "1:0"]
    assert not hasattr(question.meta("0:1"), "score")
    for batch in (["0:0", "0:1"], ["0:0", "0:0"], ["0:0", "1:0", "0:1"]):
        with pytest.raises(PolicyError):
            question.probe_batch(batch)
        assert question.budget_spent == 0
    prefixes = []
    question.probe_batch(["0:0", "1:0"], on_reveal=lambda _: prefixes.append(question.observed()))
    assert [len(p) for p in prefixes] == [1, 2]
    question.probe_batch(["0:1"])
    child = question.observed()["0:1"]
    assert child.delta_vs_parent == pytest.approx(0.8)
    assert probe_improved_vs_parent(child)
    exposed = question.observed()
    exposed.clear()
    assert len(question.observed()) == 3
    with pytest.raises(PolicyError, match="reset"):
        question.reset()


def test_source_class_executes_solve_planning_and_portable_roundtrip():
    policy = AppendixSourcePolicy(PolicyArtifact(SOURCE), {"beta": 1})
    plan = policy.plan_grid(context())
    result = policy.solve(trace().question(plan, 2))
    assert result.total_probes == 4
    assert result.decision_rounds == 2
    assert result.best_score == 1
    restored = AppendixSourcePolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
    assert asdict(restored.solve(trace().question(plan, 2))) == asdict(result)
    assert policy.solve(trace().question(plan, 2), budget=0).total_probes == 0
    custom_default = AppendixSourcePolicy(
        PolicyArtifact(SOURCE.replace('"beta", 0.6', '"beta", 0.8'))
    )
    assert custom_default.beta == 0.8


def test_sweep_has_hand_computable_auc_penalty_and_all_beta_world_pairs():
    report = beta_sweep(
        lambda beta: AppendixSourcePolicy(PolicyArtifact(SOURCE), {"beta": beta}),
        [trace()],
        context(),
        betas=(0, 1),
        parallel_weight=0.1,
    )
    assert not report["errors"]
    assert report["pareto"]["auc"] == pytest.approx(0.15)
    assert report["pareto"]["parallel_penalty"] == pytest.approx(0.75)
    assert report["pareto"]["reward"] == pytest.approx(0.075)
    assert report["non_degenerate"]
    assert [e["result"]["total_probes"] for e in report["episodes"]] == [1, 4]
    assert all(not e["result"]["execution_trace"][0]["prefix"] for e in report["episodes"])


def test_unsupported_plan_gets_no_reward_and_never_executes():
    class Unsupported(LLMDesignedMethod):
        def plan_grid(self, context):
            return GridPlan(3, 1, "Exceeds trace support")

        def solve(self, question, budget=None):
            raise AssertionError("Must reject before solve")

    report = beta_sweep(lambda beta: Unsupported(), [trace()], context(), betas=(0, 1))
    assert report["pareto"]["reward"] is None
    assert len(report["errors"]) == 2
    assert report["episodes"] == []


@pytest.mark.parametrize(
    "expression",
    [
        "question._resolve",
        "question.best_so_far",
        "question.budget_spent",
        "question.__class__",
    ],
)
def test_source_cannot_read_hidden_or_bookkeeping_objects(expression):
    source = SOURCE.replace(
        "question.reset()", f"forbidden = {expression}\n        question.reset()"
    )
    policy = AppendixSourcePolicy(PolicyArtifact(source))
    with pytest.raises(SandboxError):
        policy.solve(trace().question(GridPlan(2, 1, "test"), 2))


def test_source_imports_beta_mutation_and_infinite_loop_are_rejected():
    with pytest.raises(SandboxError):
        AppendixSourcePolicy(PolicyArtifact("import os\n" + SOURCE))
    with pytest.raises(SandboxError, match="fixed"):
        AppendixSourcePolicy(PolicyArtifact(SOURCE.replace("question.reset()", "self.beta = 1")))
    loop = SOURCE.replace("question.reset()", "while True:\n            pass")
    policy = AppendixSourcePolicy(PolicyArtifact(loop), sandbox=PolicySandbox(max_steps=1000))
    with pytest.raises(SandboxError, match="limit"):
        policy.solve(trace().question(GridPlan(2, 1, "test"), 2))


def test_planning_never_gets_current_episode_or_future_trace_history():
    seen = []

    class Inspect(OptimalPolicy):
        def plan_grid(self, context):
            seen.append(copy.deepcopy(context.history))
            return GridPlan(2, 1, "Explicit")

    early = replace(trace(), planning_history=())
    later = replace(
        trace(),
        trace_id="later",
        planning_history=({"status": "completed", "phase": "live", "cycle": 0},),
    )
    report = beta_sweep(
        lambda beta: Inspect({"beta": beta}), [early, later], context(), betas=(0,)
    )
    assert not report["errors"]
    assert seen == [(), ({"status": "completed", "phase": "live", "cycle": 0},)]
    with pytest.raises(ValueError, match="completed earlier"):
        context(history=({"status": "running", "phase": "live"},))


async def test_campaign_plans_before_live_persists_history_and_reuses_sqlite(tmp_path):
    store = SQLiteStore(tmp_path / "appendix.sqlite")
    campaign = GridCampaign("test", context(), store=store)
    calls = []

    async def evaluate(meta, parent, direction):
        calls.append((meta.branch, meta.attempt))
        return obs(meta.branch, meta.attempt, 1 + meta.attempt)

    policy = AppendixSourcePolicy(PolicyArtifact(SOURCE), {"beta": 1})
    first = await campaign.run_cycle(policy, evaluate)
    assert first["total_probes"] == 4
    report = await campaign.evaluate_sweep(
        lambda beta: AppendixSourcePolicy(PolicyArtifact(SOURCE), {"beta": beta}), betas=(0, 1)
    )
    assert report["pareto"]["reward"] is not None
    assert len(calls) == 4  # Replay never invokes the discovery callback.
    restarted = GridCampaign("test", context(), store=store)
    history = (await restarted.planning_context()).history
    assert history[0]["beta_sweep"]["objective_version"] == "appendix-pareto-v1"
    assert history[0]["beta"] == 1
    await restarted.run_cycle(policy, evaluate)
    traces = await restarted.traces()
    assert traces[0].planning_history == ()
    assert len(traces[1].planning_history) == 1
    assert len(calls) == 8
    await store.close()


async def test_interrupted_live_cycle_is_not_silently_reexecuted():
    campaign = GridCampaign("failed", context())
    calls = []

    def broken(meta, parent, direction):
        calls.append(meta)
        raise RuntimeError("external uncertainty")

    policy = AppendixSourcePolicy(PolicyArtifact(SOURCE))
    with pytest.raises(SandboxError, match="external uncertainty"):
        await campaign.run_cycle(policy, broken)
    previous = len(calls)
    with pytest.raises(ConfigurationError, match="Unreconciled"):
        await campaign.run_cycle(policy, broken)
    assert len(calls) == previous


async def test_developer_repairs_code_from_feedback_and_retains_best():
    class Stop(OptimalPolicy):
        def solve(self, question, budget=None):
            question.reset()
            return finalize_result(question)

    requests = []

    async def generate(request):
        requests.append(copy.deepcopy({k: v for k, v in request.items() if k != "report_usage"}))
        return ["invalid code!", SOURCE, "invalid again!"][len(requests) - 1]

    developer = AppendixPolicyDeveloper(
        generate, config=DeveloperConfig(revisions=3), sweep_settings={"betas": (0, 1)}
    )
    selected = await developer.develop(Stop(), [trace()], context())
    assert isinstance(selected, AppendixSourcePolicy)
    assert [r["status"] for r in developer.history] == ["failed", "scored", "failed"]
    assert requests[1]["feedback"]["score"] is None
    assert "error" in requests[1]["feedback"]
    assert requests[2]["best_source"] == SOURCE.strip()
    assert developer.history[2]["score"] is None


def test_default_beta_requires_paired_live_sweep_evidence():
    assert choose_default_beta([]) == 0.6
    rows = [
        {
            "best_score": 1,
            "beta": 0.7,
            "beta_sweep": {
                "objective_version": "appendix-pareto-v1",
                "pareto": {"reward": 0.2},
                "frontier": [
                    {"beta": 0.7, "work": 0.5, "attainment": 0.5, "parallel_penalty": 0.5},
                    {"beta": 0.8, "work": 0.6, "attainment": 0.8, "parallel_penalty": 0.5},
                ],
            },
        }
        for _ in range(2)
    ]
    assert choose_default_beta(rows) == 0.8
    rows[-1]["beta_sweep"]["objective_version"] = "legacy-auc"
    assert choose_default_beta(rows) == 0.6
