"""In-memory storage backend for testing and lightweight use."""

from __future__ import annotations

import copy

from dreamrsi.discovery import DiscoveryNode
from dreamrsi.events import Event
from dreamrsi.models.base import Run
from dreamrsi.models.evaluation import Evaluation
from dreamrsi.models.policy import PolicyDeploymentStatus, PolicyVersion


class InMemoryStore:
    """Simple in-memory storage backend.

    Suitable for tests, examples, and short-lived sessions.
    All data is lost when the process exits.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._nodes: dict[str, DiscoveryNode] = {}
        self._policies: dict[str, PolicyVersion] = {}
        self._events: list[Event] = []
        self._evaluations: dict[str, Evaluation] = {}

    async def save_run(self, run: Run) -> None:
        self._runs[run.id] = copy.deepcopy(run)

    async def get_run(self, run_id: str) -> Run | None:
        return copy.deepcopy(self._runs.get(run_id))

    async def save_node(self, node: DiscoveryNode) -> None:
        self._nodes[node.id] = copy.deepcopy(node)

    async def get_node(self, node_id: str) -> DiscoveryNode | None:
        return copy.deepcopy(self._nodes.get(node_id))

    async def get_nodes_by_tree(self, tree_id: str) -> list[DiscoveryNode]:
        return copy.deepcopy([n for n in self._nodes.values() if n.tree_id == tree_id])

    async def save_policy(self, policy: PolicyVersion) -> None:
        self._policies[policy.id] = copy.deepcopy(policy)

    async def get_policy(self, policy_id: str) -> PolicyVersion | None:
        return copy.deepcopy(self._policies.get(policy_id))

    async def list_policies(self) -> list[PolicyVersion]:
        return copy.deepcopy(sorted(self._policies.values(), key=lambda p: p.created_at))

    async def get_champion(self) -> PolicyVersion | None:
        for p in self._policies.values():
            if p.deployment_status == PolicyDeploymentStatus.CHAMPION:
                return copy.deepcopy(p)
        return None

    async def save_event(self, event: Event) -> None:
        self._events.append(copy.deepcopy(event))

    async def get_events(self, run_id: str | None = None, limit: int = 100) -> list[Event]:
        events = self._events
        if run_id is not None:
            events = [e for e in events if e.run_id == run_id]
        return copy.deepcopy(events[-limit:]) if limit > 0 else []

    async def save_evaluation(self, evaluation: Evaluation) -> None:
        self._evaluations[evaluation.id] = copy.deepcopy(evaluation)

    async def close(self) -> None:
        pass
