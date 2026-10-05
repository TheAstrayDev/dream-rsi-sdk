import itertools
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

import dreamrsi.policies as policies
from dreamrsi.models.policy import PolicyDeploymentStatus, PolicyVersion
from dreamrsi.quality import get_record_quality


class DeterministicPolicyOptimizer:
    """Distil replay prefixes, then try a bounded portfolio without model calls.

    ``prefix_search=False`` retains the parameter-only portfolio. Synthesized
    prefixes still pass the runtime's raw-quality and independent holdout gates.
    """

    def __init__(
        self, num_variants: int = 5, seed: int | None = None,
        *, quality_metric=None, prefix_search: bool = True,
    ):
        self._num_variants = num_variants
        self._seed = seed
        if quality_metric is not None and not callable(quality_metric):
            raise ValueError("quality_metric must be callable")
        self._quality_metric = quality_metric
        if type(prefix_search) is not bool:
            raise ValueError("prefix_search must be boolean")
        self._prefix_search = prefix_search

    def _prefix_round_limit(self, trajectories):
        """Smallest constant cap preserving each recorded incumbent raw quality."""
        if not isinstance(trajectories, (list, tuple)) or not trajectories:
            return None
        caps = []
        for trajectory in trajectories:
            values = {}
            for node_id, observation in trajectory.observations.items():
                value = get_record_quality(observation, self._quality_metric)
                if value is not None:
                    values[node_id] = value
            target = max(values.values()) if values else None
            reached = {
                node_id for node_id, value in values.items()
                if value == target
            }
            roots = {
                node_id for node_id, observation in trajectory.observations.items()
                if isinstance(observation, Mapping)
                and type(observation.get("depth")) is int
                and observation["depth"] == 0
            }
            first = 0 if reached & roots else next(
                (
                    step.round_number for step in trajectory.steps
                    if reached.intersection(step.revealed_nodes)
                ),
                None,
            )
            if target is None or first is None:
                return None
            caps.append(first)
        cap = max(caps)
        return cap if any(cap < t.total_rounds for t in trajectories) else None

    async def generate(
        self, incumbent: Any, evidence: Any, budget: Any | None = None
    ) -> list[Any]:
        supported = {getattr(policies, name) for name in policies.__all__}
        cap = self._prefix_round_limit(evidence) if self._prefix_search else None
        if type(incumbent) not in supported and cap is None:
            from dreamrsi.errors import ConfigurationError

            raise ConfigurationError("Custom policies require an explicit optimizer/developer")
        # The previous search only increased BalancedPolicy's batch size and
        # exploration coefficient. It could not represent stopping after one
        # good branch, even when replay proved that this saved calls at equal
        # quality. Keep the configured evaluation count, but spend its first
        # slots on distinct branching/stopping behaviours.
        variants = [
            policies.FixedParallelPolicy(branches=1, max_depth=1),
            policies.FixedParallelPolicy(branches=1, max_depth=2),
            policies.FixedParallelPolicy(branches=2, max_depth=2),
            policies.BalancedPolicy(batch_size=1),
        ]
        if cap is not None:
            # Keep the established one-probe candidate first when another slot
            # remains. A one-candidate budget must retain the derived prefix.
            position = 1 if cap == 1 and self._num_variants > 1 else 0
            variants.insert(position, policies.PrefixPolicy(incumbent, cap))
        variants = variants[: max(0, self._num_variants)]
        if type(incumbent) not in supported:
            return variants
        while isinstance(incumbent, (policies.PrefixPolicy, policies.CertifiedPolicy)):
            incumbent = incumbent.policy
        if type(incumbent) not in supported:
            return variants
        incumbent_type = type(incumbent).__name__

        for i in range(max(0, self._num_variants - len(variants))):
            if incumbent_type == "BalancedPolicy":
                # tweak exploration_coeff and batch_size
                coeff = getattr(incumbent, "_exploration_coeff", 1.41) + ((i + 1) * 0.1)
                bs = getattr(incumbent, "_batch_size", 4) + i
                variants.append(policies.BalancedPolicy(exploration_coeff=coeff, batch_size=bs))
            elif incumbent_type == "EpsilonGreedyPolicy":
                # tweak epsilon
                eps = max(0.01, getattr(incumbent, "_epsilon", 0.1) - (i * 0.02))
                variants.append(policies.EpsilonGreedyPolicy(epsilon=eps, seed=self._seed))
            elif incumbent_type == "FixedParallelPolicy":
                # tweak branches and depth
                b = getattr(incumbent, "_branches", 3) + (i % 2)
                d = getattr(incumbent, "_max_depth", 2) + (i // 2)
                variants.append(policies.FixedParallelPolicy(branches=b, max_depth=d))
            elif incumbent_type == "GreedyPolicy":
                # generate EpsilonGreedy variants
                variants.append(
                    policies.EpsilonGreedyPolicy(epsilon=(i + 1) * 0.05, seed=self._seed)
                )
            elif type(incumbent) in (
                policies.DepthFirstPolicy,
                policies.BreadthFirstPolicy,
                policies.RandomPolicy,
            ):
                variants.append(policies.BalancedPolicy(batch_size=i + 1))
            else:
                from dreamrsi.errors import ConfigurationError

                raise ConfigurationError(
                    "This policy needs LLMPolicyDeveloper or an explicit custom optimizer"
                )

        return variants


class ParameterSearchOptimizer:
    """Grid search over a parameter space for policy generation."""

    def __init__(self, policy_factory: Callable[..., Any], param_grid: dict[str, list[Any]]):
        self._policy_factory = policy_factory
        self._param_grid = param_grid

    async def generate(
        self, incumbent: Any, evidence: Any, budget: Any | None = None
    ) -> list[Any]:
        keys = list(self._param_grid.keys())
        values = list(self._param_grid.values())
        variants = []
        for combination in itertools.product(*values):
            params = dict(zip(keys, combination, strict=False))
            variants.append(self._policy_factory(**params))
        return variants


class PolicyVersionManager:
    """Tracks policy versions and their lineage."""

    def __init__(self):
        self._versions: dict[str, PolicyVersion] = {}
        self._champion_id: str | None = None

    def register(
        self,
        policy: Any,
        parent_id: str | None = None,
        name: str = "",
        source: str = "builtin",
        creation_method: str = "manual",
    ) -> PolicyVersion:
        policy_id = str(uuid.uuid4())
        version = PolicyVersion(
            id=policy_id,
            parent_id=parent_id,
            name=name,
            source=source,
            creation_method=creation_method,
            deployment_status=PolicyDeploymentStatus.CANDIDATE,
            created_at=time.time(),
            metadata={"policy_type": type(policy).__name__},
        )
        self._versions[policy_id] = version
        return version

    def promote(self, policy_id: str) -> None:
        if policy_id not in self._versions:
            raise ValueError(f"Policy {policy_id} not found")
        if self._champion_id and self._champion_id in self._versions:
            old_champion = self._versions[self._champion_id]
            old_champion.deployment_status = PolicyDeploymentStatus.RETIRED

        new_champion = self._versions[policy_id]
        new_champion.deployment_status = PolicyDeploymentStatus.CHAMPION
        self._champion_id = policy_id

    def reject(self, policy_id: str) -> None:
        if policy_id in self._versions:
            ver = self._versions[policy_id]
            ver.deployment_status = PolicyDeploymentStatus.REJECTED

    def rollback(self, to_policy_id: str) -> None:
        self.promote(to_policy_id)

    def get_champion(self) -> PolicyVersion | None:
        if self._champion_id:
            return self._versions.get(self._champion_id)
        return None

    def get_version(self, policy_id: str) -> PolicyVersion | None:
        return self._versions.get(policy_id)

    def list_versions(self) -> list[PolicyVersion]:
        return list(self._versions.values())

    def get_lineage(self, policy_id: str) -> list[PolicyVersion]:
        lineage = []
        current_id = policy_id
        visited = set()
        while current_id and current_id in self._versions and current_id not in visited:
            visited.add(current_id)
            ver = self._versions[current_id]
            lineage.append(ver)
            current_id = ver.parent_id
        return lineage
