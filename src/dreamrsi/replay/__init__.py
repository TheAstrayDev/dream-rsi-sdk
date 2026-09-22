"""Strict replay — deterministic offline evaluation of exploration policies.

StrictReplay faithfully implements the offline evaluation procedure from
the Dream-RSI paper (§3, "Offline evaluation").  It works exclusively
with recorded transitions from committed discovery trees.

Key properties:
- **Deterministic**: same world + policy + seed → same trajectory
- **Reproducible**: independent of external state
- **Side-effect free**: never calls agent or evaluator
- **Cheap**: in-memory traversal, no LLM calls

An unrecorded continuation reveals nothing and consumes a round. Replay never fabricates,
interpolate, or approximate outcomes.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import replace
from typing import Any

from dreamrsi._invoke import invoke
from dreamrsi._policy import fresh_policy, validate_batch
from dreamrsi.discovery import DiscoveryNode, DiscoveryTree
from dreamrsi.errors import ReplayError
from dreamrsi.models.policy import NodeSummary, PolicyDecision, PolicyView
from dreamrsi.models.replay import ReplayStep, ReplayTrajectory
from dreamrsi.views import revealed_context


class ReplayWorld:
    """A committed discovery tree wrapped as a replayable simulator.

    The world is read-only.  It supports the Child(v; T, T_revealed)
    operation from the paper exactly:
    - For non-root leaf v: return v's unique recorded child (if any).
    - For root: return the earliest-created child of root not yet revealed.
    """

    def __init__(self, tree: DiscoveryTree, world_id: str | None = None) -> None:
        if not tree.is_committed:
            raise ReplayError("Cannot create a replay world from an uncommitted tree")
        self.tree = copy.deepcopy(tree)
        self.world_id = world_id or tree.tree_id

    def get_child(
        self,
        node_id: str,
        revealed: set[str],
    ) -> DiscoveryNode | None:
        """Return the next child to reveal, following paper semantics.

        For v ≠ root: the unique recorded child of v that is not in revealed.
            (In a tree, a leaf extended once has one child per attempt.)
        For v = root: the earliest-created child of root outside revealed.

        Returns None when no recorded continuation exists (replay boundary).
        """
        node = self.tree.get_node(node_id)
        if node is None:
            return None

        children = self.tree.get_children(node_id)  # sorted by creation_order
        for child in children:
            if child.id not in revealed:
                return child
        return None

    def all_node_ids(self) -> set[str]:
        """Return all node IDs in this world."""
        return set(n.id for n in self.tree.iter_nodes())


class StrictReplay:
    """Execute a policy against a replay world using only recorded transitions.

    This implements the offline evaluation from Dream-RSI §3:
    1. Start with T_revealed = {root}.
    2. At each round, build PolicyView from revealed nodes.
    3. Policy selects a batch C ⊆ A(T_revealed, W).
    4. For each v ∈ C, reveal Child(v) from the recorded tree.
    5. Repeat until policy stops, round limit, or all nodes revealed.

    Parameters
    ----------
    max_rounds : int
        Maximum decision rounds (K₂ in the paper). Default 1000.
    max_parallelism : int
        Maximum batch size (W workers). Default 32.
    """

    def __init__(
        self,
        max_rounds: int = 1000,
        max_parallelism: int = 32,
        beta1: float = 0.01,
        beta2: float = 0.005,
    ) -> None:
        if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 0:
            raise ValueError("max_rounds must be a nonnegative integer")
        if (
            not isinstance(max_parallelism, int)
            or isinstance(max_parallelism, bool)
            or max_parallelism < 1
        ):
            raise ValueError("max_parallelism must be a positive integer")
        if any(not math.isfinite(v) or v < 0 for v in (beta1, beta2)):
            raise ValueError("Replay coefficients must be finite and nonnegative")
        self.beta1, self.beta2 = beta1, beta2
        self.max_rounds = max_rounds
        self.max_parallelism = max_parallelism

    def checkpoint_config(self):
        """JSON configuration identifying replay semantics for campaign recovery."""
        return {
            "max_rounds": self.max_rounds,
            "max_parallelism": self.max_parallelism,
            "beta1": self.beta1,
            "beta2": self.beta2,
        }

    async def replay(
        self,
        world: ReplayWorld,
        policy: Any,  # ExplorationPolicy (duck-typed to avoid circular import)
        policy_id: str = "unknown",
    ) -> ReplayTrajectory:
        """Run one complete replay evaluation.

        Parameters
        ----------
        world : ReplayWorld
            The frozen discovery tree to replay against.
        policy : ExplorationPolicy
            Must implement ``async def decide(self, view: PolicyView) -> PolicyDecision``.
        policy_id : str
            Identifier for this policy version (for tracking).

        Returns
        -------
        ReplayTrajectory
            Complete record of the replay, including all revealed nodes,
            scores, and the computed replay score.
        """
        policy = fresh_policy(policy)
        t0 = time.monotonic()
        tree = world.tree

        if tree.root_id is None:
            raise ReplayError("Replay world has no root node")

        # T_revealed starts as {root}
        revealed: set[str] = {tree.root_id}
        trajectory = ReplayTrajectory(
            world_id=world.world_id,
            policy_id=policy_id,
        )

        # Track best score
        root = tree.get_node(tree.root_id)
        best_score: float | None = root.score if root else None
        probes = 0
        last_round = None

        all_ids = world.all_node_ids()
        for round_num in range(1, self.max_rounds + 1):
            if revealed >= all_ids:
                trajectory.completed = True
                break
            # Build the policy view from revealed nodes
            view = self._build_view(
                tree=tree,
                revealed=revealed,
                best_score=best_score,
                probes=probes,
                round_num=round_num,
                world=world,
            )
            view = replace(view, last_round=copy.deepcopy(last_round))

            # Ask policy for a decision
            decision: PolicyDecision = await invoke(policy.decide, view)

            # Check for stop
            if decision.stop or not decision.expand:
                trajectory.completed = True
                break

            # Validate batch
            batch = validate_batch(decision, view, self.max_parallelism)
            revealed_this_round: list[str] = []

            for node_id in batch:
                # Get the child to reveal
                child = world.get_child(node_id, revealed)
                if child is None:
                    # Replay boundary — no more recorded transitions
                    continue

                revealed.add(child.id)
                revealed_this_round.append(child.id)
                probes += 1

                # Update best score
                if child.score is not None and (best_score is None or child.score > best_score):
                    best_score = child.score

            step = ReplayStep(
                round_number=round_num,
                batch=batch,
                revealed_nodes=revealed_this_round,
                best_score_so_far=best_score,
                probes_so_far=probes,
                frontier=[n.to_dict() for n in view.frontier],
            )
            trajectory.steps.append(step)
            last_round = {
                "batch": list(batch),
                "revealed_nodes": list(revealed_this_round),
                "best_score_before": view.best_score,
                "best_score_after": best_score,
            }
            trajectory.revealed_node_ids.extend(revealed_this_round)

            # Check if all nodes revealed
            if revealed >= all_ids:
                trajectory.completed = True
                break

        trajectory.best_score = best_score
        trajectory.total_probes = probes
        trajectory.total_rounds = len(trajectory.steps)
        trajectory.elapsed_ms = (time.monotonic() - t0) * 1000

        # Compute replay objective from the paper
        trajectory.total_cost = sum(n.cost for n in tree.iter_nodes() if n.id in revealed)
        trajectory.observations = revealed_context(tree, revealed)["observations"]
        trajectory.replay_score = self._compute_replay_score(
            best_score=best_score,
            probes=probes,
            rounds=len(trajectory.steps),
            beta1=self.beta1,
            beta2=self.beta2,
        )
        trajectory.objective = {
            "formula": "best_score - beta1 * probes + beta2 * probes / max(1, rounds)",
            "direction": "maximize",
            "beta1": self.beta1,
            "beta2": self.beta2,
            "quality": best_score,
            "probe_penalty": self.beta1 * probes,
            "parallelism_bonus": self.beta2 * probes / max(1, len(trajectory.steps)),
            "max_rounds": self.max_rounds,
            "max_parallelism": self.max_parallelism,
        }

        return trajectory

    def _build_view(
        self,
        tree: DiscoveryTree,
        revealed: set[str],
        best_score: float | None,
        probes: int,
        round_num: int,
        world: ReplayWorld,
    ) -> PolicyView:
        """Build the policy's observation from the currently revealed subtree."""
        frontier: list[NodeSummary] = []

        for node in tree.iter_nodes():
            if node.id not in revealed:
                continue
            is_leaf = not any(cid in revealed for cid in node.children_ids)
            if node.is_root or is_leaf:
                frontier.append(
                    NodeSummary(
                        id=node.id,
                        parent_id=node.parent_id,
                        depth=node.depth,
                        score=node.score,
                        status=node.status,
                        children_count=sum(cid in revealed for cid in node.children_ids),
                    )
                )

        return PolicyView(
            **revealed_context(tree, revealed),
            frontier=frontier,
            best_score=best_score,
            total_nodes=len(revealed),
            calls_used=probes,
            cost_used=sum(n.cost for n in tree.iter_nodes() if n.id in revealed),
            rounds_used=round_num - 1,
            tree_id=tree.tree_id,
            round_number=round_num,
            max_parallelism=self.max_parallelism,
        )

    @staticmethod
    def _compute_replay_score(
        best_score: float | None,
        probes: int,
        rounds: int,
        beta1: float = 0.01,
        beta2: float = 0.005,
    ) -> float | None:
        """Compute the replay objective from the paper.

        V = max_score - β₁·N + β₂·(N/K)

        Where:
        - max_score = best score attained during replay
        - N = number of revealed non-root nodes (probes)
        - K = number of decision rounds
        - β₁ penalizes total attempts
        - β₂ rewards parallelism (higher probes per round = better batching)
        """
        if best_score is None:
            return None
        if probes == 0:
            return best_score

        parallelism_bonus = (probes / max(rounds, 1)) if rounds > 0 else 0.0
        return best_score - beta1 * probes + beta2 * parallelism_bonus


__all__ = [
    "NodeSummary",
    "PolicyDecision",
    "PolicyView",
    "ReplayStep",
    "ReplayTrajectory",
    "ReplayWorld",
    "StrictReplay",
]
