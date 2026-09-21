import pytest

from dreamrsi import Budget, DreamRSI
from dreamrsi.errors import ConfigurationError
from dreamrsi.models.objectives import ObjectiveResult
from dreamrsi.models.replay import ReplayTrajectory
from dreamrsi.policies import BalancedPolicy, DepthFirstPolicy
from dreamrsi.replay import ReplayWorld


class RecordedEngine:
    def __init__(self):
        self.calls = []
        self.cached = ReplayTrajectory(world_id="fixture", policy_id="fixture", replay_score=99)

    async def replay(self, world, policy, policy_id=""):
        self.calls.append((world.world_id, policy_id))
        self.cached.total_probes = 1 if isinstance(policy, DepthFirstPolicy) else 4
        return self.cached


class FewerProbes:
    def score(self, trajectory, context=None):
        return ObjectiveResult(score=-trajectory.total_probes)


class OneChallenger:
    async def generate(self, incumbent, evidence, budget=None):
        assert evidence[0].replay_score == -4
        return [DepthFirstPolicy()]


def runtime(**kwargs):
    return DreamRSI(agent=lambda x: x, evaluator=lambda x: x,
                    budget=Budget(model_calls=1), **kwargs)


async def test_engine_and_objective_used_by_replay_comparison_and_promotion():
    engine = RecordedEngine()
    rsi = runtime(replay=engine, objective=FewerProbes(),
                  policy=BalancedPolicy(), policy_optimizer=OneChallenger())
    result = await rsi.run(1)
    world = ReplayWorld(result.tree)
    trajectory = await rsi.replay(world, BalancedPolicy())
    assert trajectory.replay_score == -4
    assert engine.cached.replay_score == 99
    scores = await rsi.compare_policies([BalancedPolicy(), DepthFirstPolicy()], [world])
    assert scores == {0: -4, 1: -1}
    improved = await rsi.improve(1, rounds=1)
    assert isinstance(improved.champion_policy, DepthFirstPolicy)
    assert improved.metrics["policy_promotions"] == 1
    assert len(engine.calls) == 5
    assert [call[1] for call in engine.calls[-2:]] == ["incumbent", "challenger"]


async def test_custom_method_replaces_outer_loop_including_campaign():
    class OnlineOnly:
        def __init__(self):
            self.calls = []

        async def improve(self, runtime, task, rounds=5):
            self.calls.append((task, rounds))
            return await runtime.run(task)

    method = OnlineOnly()
    rsi = runtime(method=method)
    assert (await rsi.improve(2, rounds=3)).best_score == 2
    campaign = await rsi.run_campaign([3, 4], rounds=2)
    assert campaign.best_score == 4
    assert method.calls == [(2, 3), (3, 2), (4, 2)]
    assert campaign.worlds == []


def test_custom_method_sync_entrypoint():
    class OnlineOnly:
        async def improve(self, runtime, task, rounds=5):
            return await runtime.run(task)

    assert runtime(method=OnlineOnly()).improve_sync(7).best_score == 7


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
async def test_nonfinite_objective_cannot_reach_selection(value):
    class InvalidObjective:
        async def score(self, trajectory, context=None):
            return ObjectiveResult(score=value)

    rsi = runtime(objective=InvalidObjective())
    with pytest.raises(ConfigurationError, match="finite"):
        await rsi.improve(1, rounds=1)


@pytest.mark.parametrize("name", ["replay", "objective", "method"])
def test_invalid_extension_rejected_at_construction(name):
    with pytest.raises(ConfigurationError, match="implement"):
        runtime(**{name: object()})
