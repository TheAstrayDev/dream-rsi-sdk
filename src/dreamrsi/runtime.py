"""DreamRSI runtime — the main entry point for the library.

This module implements the DreamRSI class which coordinates all
subsystems: online exploration, discovery tree construction,
replay evaluation, policy optimization, promotion, and the
recursive self-improvement loop.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any

from dreamrsi._invoke import invoke
from dreamrsi._policy import fresh_policy, validate_batch
from dreamrsi.adapters import CallableAgentAdapter
from dreamrsi.discovery import DiscoveryTree, NodeStatus
from dreamrsi.errors import (
    ConfigurationError,
)
from dreamrsi.evaluation import CallableEvaluator
from dreamrsi.events import Callback, Event, EventEmitter, EventType
from dreamrsi.models.base import CostRecord, Run, RunStatus
from dreamrsi.models.budget import Budget
from dreamrsi.models.policy import PolicyDeploymentStatus, PolicyVersion
from dreamrsi.models.results import CampaignResult, RunResult
from dreamrsi.replay import (
    NodeSummary,
    PolicyView,
    ReplayTrajectory,
    ReplayWorld,
    StrictReplay,
)
from dreamrsi.storage import InMemoryStore

logger = logging.getLogger("dreamrsi")


# ── Config ─────────────────────────────────────────────────────


@dataclass
class DreamRSIConfig:
    """Optional configuration for DreamRSI."""

    replay_max_rounds: int = 1000
    replay_max_parallelism: int = 32
    replay_beta1: float = 0.01
    replay_beta2: float = 0.005
    optimizer_variants: int = 5
    promotion_min_improvement: float = 0.0
    default_batch_size: int = 4
    random_seed: int | None = None

    def __post_init__(self):
        for name in (
            "replay_max_rounds",
            "replay_max_parallelism",
            "optimizer_variants",
            "default_batch_size",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigurationError(f"{name} must be a positive integer")
        for name in ("replay_beta1", "replay_beta2", "promotion_min_improvement"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ConfigurationError(f"{name} must be finite and nonnegative")


# ── Main Runtime ───────────────────────────────────────────────


class DreamRSI:
    """Embeddable runtime for Dream-RSI recursive self-improvement.

    The simplest usage::

        rsi = DreamRSI(agent=my_agent, evaluator=my_evaluator)
        result = await rsi.run(task)

    For full Dream-RSI with recursive improvement::

        result = await rsi.improve(task, rounds=5)

    Parameters
    ----------
    agent : callable or AgentAdapter, optional
        A callable or object implementing the AgentAdapter protocol.
    adapter : AgentAdapter, optional
        Native adapter for full Dream-RSI control.  Takes precedence
        over ``agent``.
    evaluator : Evaluator
        Scoring function or object with ``async evaluate(candidate, context)``.
    policy : ExplorationPolicy, optional
        Initial exploration policy.  Defaults to BalancedPolicy.
    policy_optimizer : PolicyOptimizer, optional
        Generates challenger policies.  Defaults to DeterministicPolicyOptimizer.
    promotion : PromotionGate, optional
        Decides whether to promote challengers.  Defaults to ReplayOnlyGate.
    store : Store, optional
        Storage backend.  Defaults to InMemoryStore.
    budget : Budget, optional
        Resource constraints.
    config : DreamRSIConfig, optional
        Fine-tuning parameters.
    callbacks : list[Callback], optional
        Lifecycle callback objects.
    """

    def __init__(
        self,
        agent: Any | None = None,
        adapter: Any | None = None,
        evaluator: Any | None = None,
        policy: Any | None = None,
        policy_optimizer: Any | None = None,
        promotion: Any | None = None,
        store: Any | None = None,
        budget: Budget | None = None,
        config: DreamRSIConfig | None = None,
        callbacks: list[Callback] | None = None,
    ) -> None:
        # Resolve adapter
        if adapter is not None:
            self._adapter = adapter
        elif agent is not None:
            if all(
                callable(getattr(agent, name, None))
                for name in ("initial_state", "propose", "execute", "observe", "next_state")
            ):
                self._adapter = agent
            elif callable(agent):
                self._adapter = CallableAgentAdapter(agent)
            else:
                self._adapter = agent
        else:
            raise ConfigurationError("Must provide either 'agent' or 'adapter'")

        if evaluator is None:
            raise ConfigurationError("Must provide 'evaluator'")
        self._evaluator = CallableEvaluator(getattr(evaluator, "evaluate", evaluator))

        self._config = config or DreamRSIConfig()
        self._budget = budget
        if budget is not None and budget.max_nodes == 0:
            raise ConfigurationError("max_nodes includes the root; use at least 1")
        if budget is not None and budget.usd is not None:
            raise ConfigurationError(
                "USD budgets require provider pricing; use model_calls/evaluator_calls for now"
            )
        for name in ("initial_state", "propose", "execute", "observe", "next_state"):
            if not callable(getattr(self._adapter, name, None)):
                raise ConfigurationError(f"Adapter must implement {name}")

        # Lazy imports to avoid circular deps — will be resolved at first use
        self._policy = policy
        self._optimizer = policy_optimizer
        self._promotion = promotion
        self._store = store if store is not None else InMemoryStore()

        # Events
        self._emitter = EventEmitter()
        if callbacks:
            for cb in callbacks:
                self._emitter.add_callback(cb)

        # State
        self._champion_policy: Any = None
        self._policy_history: list[Any] = []
        self._worlds: list[ReplayWorld] = []
        self._frozen = False

    def _get_policy(self) -> Any:
        """Resolve the default policy lazily."""
        if self._policy is not None:
            return self._policy
        # Import here to avoid circular dependency
        from dreamrsi.policies import BalancedPolicy

        self._policy = BalancedPolicy(batch_size=self._config.default_batch_size)
        return self._policy

    def _get_optimizer(self) -> Any:
        """Resolve the default optimizer lazily."""
        if self._optimizer is not None:
            return self._optimizer
        from dreamrsi.optimization import DeterministicPolicyOptimizer

        self._optimizer = DeterministicPolicyOptimizer(
            num_variants=self._config.optimizer_variants,
            seed=self._config.random_seed,
        )
        return self._optimizer

    def _get_promotion(self) -> Any:
        """Resolve the default promotion gate lazily."""
        if self._promotion is not None:
            return self._promotion
        from dreamrsi.promotion import ReplayOnlyGate

        self._promotion = ReplayOnlyGate(
            min_improvement=self._config.promotion_min_improvement,
        )
        return self._promotion

    # ── Events ─────────────────────────────────────────────────

    def on_event(self, callback: Any) -> None:
        """Register an event listener."""
        self._emitter.on(callback)

    async def _emit(self, event_type: EventType, **kwargs: Any) -> None:
        event = Event(type=event_type, **kwargs)
        await self._store.save_event(event)
        await self._emitter.emit(event)

    # ── Core API ───────────────────────────────────────────────

    async def run(self, task: Any) -> RunResult:
        """Explore once. Budgets apply per run, including each run in improve().

        Sync integrations run in worker threads. Cancelling a thread await cannot
        stop external work already in progress; adapters own external cancellation.
        """
        run_id = str(uuid.uuid4())
        tree = DiscoveryTree()
        costs = CostRecord()
        policy = self._champion_policy or self._get_policy()
        episode_policy = fresh_policy(policy)
        budget = self._budget or Budget()

        def limit(name, default):
            value = getattr(budget, name)
            return default if value is None else value

        max_rounds = limit("max_rounds", 100)
        max_nodes = limit("max_nodes", 500)
        max_depth = limit("max_depth", 20)
        workers = limit("max_parallelism", self._config.default_batch_size)
        rounds_done = 0
        stop_reason = "round_limit"
        started = time.monotonic()
        record = Run(
            id=run_id,
            task_id=str(getattr(task, "id", run_id)),
            tree_id=tree.tree_id,
            policy_id=type(policy).__name__,
            status=RunStatus.RUNNING,
            started_at=time.time(),
        )
        await self._store.save_run(record)
        await self._emit(EventType.RUN_STARTED, run_id=run_id)

        async def expand(parent, round_num):
            # Each branch owns its state. Adapter may provide custom snapshot logic.
            clone = getattr(self._adapter, "clone_state", copy.deepcopy)
            state = parent.state
            context = {
                "task": task,
                "round": round_num,
                "tree_size": tree.size,
                "parent_id": parent.id,
                "parent_score": parent.score,
            }
            evaluation = None
            try:
                state = await invoke(clone, parent.state)
                costs.model_calls += 1
                proposal = await invoke(self._adapter.propose, state, context)
                execution = await invoke(self._adapter.execute, proposal, state, context)
                observation = await invoke(self._adapter.observe, execution, state)
                costs.evaluator_calls += 1
                evaluation = await self._evaluator.evaluate(observation, context)
                next_state = await invoke(self._adapter.next_state, observation, state)
                return dict(
                    state=next_state,
                    proposal=proposal,
                    action=execution,
                    observation=observation,
                    score=evaluation.score,
                    status=NodeStatus.COMPLETED,
                ), evaluation
            except Exception as exc:
                return dict(
                    state=state,
                    status=NodeStatus.FAILED,
                    metadata={"error": str(exc), "error_type": type(exc).__name__},
                ), evaluation

        async def collect():
            nonlocal rounds_done, stop_reason
            initial = await invoke(self._adapter.initial_state, task)
            tree.create_root(state=initial)
            for round_num in range(1, max_rounds + 1):
                slots = min(workers, max(0, max_nodes - tree.size))
                for name, used in (
                    ("model_calls", costs.model_calls),
                    ("evaluator_calls", costs.evaluator_calls),
                ):
                    cap = getattr(budget, name)
                    if cap is not None:
                        slots = min(slots, max(0, cap - used))
                if slots <= 0:
                    stop_reason = "budget"
                    break
                view = self._build_policy_view(tree, round_num, workers)
                view = replace(
                    view,
                    frontier=[n for n in view.frontier if n.depth < max_depth],
                    calls_used=costs.model_calls,
                    budget_remaining=budget.remaining(
                        Budget(
                            model_calls=costs.model_calls,
                            evaluator_calls=costs.evaluator_calls,
                            max_nodes=tree.size,
                            max_rounds=rounds_done,
                            wall_time_s=time.monotonic() - started,
                        )
                    ),
                )
                if not view.frontier:
                    stop_reason = "frontier_exhausted"
                    break
                decision = await invoke(episode_policy.decide, view)
                batch = validate_batch(decision, view, workers)[:slots]
                if not batch:
                    stop_reason = "policy"
                    break
                # Gather preserves decision order even when attempts finish out of order.
                tasks = [
                    asyncio.create_task(expand(tree.get_node(nid), round_num)) for nid in batch
                ]
                cancelled = False
                results: list[tuple[dict[str, Any], Any]]
                try:
                    results = await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    cancelled = True
                    results = [
                        task.result()
                        if not task.cancelled()
                        else (
                            dict(
                                status=NodeStatus.SKIPPED,
                                metadata={"error": "Attempt cancelled before completion"},
                            ),
                            None,
                        )
                        for task in tasks
                    ]
                for parent_id, (fields, evaluation) in zip(batch, results, strict=True):
                    node = tree.add_node(parent_id=parent_id, **fields)
                    if evaluation is not None:
                        await self._store.save_evaluation(evaluation)
                    await self._emit(
                        EventType.NODE_CREATED,
                        run_id=run_id,
                        data={"node_id": node.id, "score": node.score},
                    )
                    await self._emit(
                        EventType.NODE_EVALUATED if node.score is not None else EventType.ERROR,
                        run_id=run_id,
                        data={"node_id": node.id, "score": node.score, **node.metadata},
                    )
                rounds_done += 1
                if cancelled:
                    raise asyncio.CancelledError
                await self._emit(
                    EventType.ROUND_COMPLETED,
                    run_id=run_id,
                    round_number=round_num,
                    data={"tree_size": tree.size, "best_score": tree.get_best_score()},
                )

        timeout = asyncio.timeout(budget.wall_time_s)
        try:
            async with timeout:
                await collect()
        except TimeoutError:
            if not timeout.expired():
                record.status = RunStatus.FAILED
                record.completed_at = time.time()
                await self._store.save_run(record)
                raise
            stop_reason = "wall_time"
        except BaseException:
            record.status = RunStatus.FAILED
            record.completed_at = time.time()
            await self._store.save_run(record)
            raise
        if tree.root_id is None:
            tree.create_root()
        tree.commit()
        for node in tree.iter_nodes():
            await self._store.save_node(node)
        record.status = RunStatus.COMPLETED
        record.completed_at = time.time()
        record.round_number = rounds_done
        record.metadata["stop_reason"] = stop_reason
        await self._store.save_run(record)
        if stop_reason in ("budget", "wall_time", "round_limit"):
            await self._emit(
                EventType.BUDGET_EXHAUSTED, run_id=run_id, data={"reason": stop_reason}
            )
        best_node = tree.get_best_node()
        result = RunResult(
            run_id=run_id,
            best=best_node.observation if best_node else None,
            best_score=best_node.score if best_node else None,
            best_node_id=best_node.id if best_node else None,
            tree=tree,
            policy=policy,
            champion_policy=self._champion_policy,
            rounds=rounds_done,
            costs=costs,
            metrics={
                "stop_reason": stop_reason,
                "failed_nodes": sum(n.status == NodeStatus.FAILED for n in tree.iter_nodes()),
            },
        )
        await self._emit(EventType.RUN_COMPLETED, run_id=run_id)
        return result

    async def improve(
        self,
        task: Any,
        rounds: int = 5,
    ) -> RunResult:
        """Run the full Dream-RSI recursive improvement loop.

        This is the main entry point for Dream-RSI.  It alternates between:
        1. Online exploration (building discovery trees)
        2. Offline dreaming (replay + policy improvement)

        Parameters
        ----------
        task : Any
            The task to solve.
        rounds : int
            Number of outer RSI iterations.  Each iteration:
            - Deploys current policy online → collects a new tree
            - Converts tree to replay world
            - Generates challenger policies
            - Evaluates challengers via replay
            - Promotes the best if it improves

        Returns
        -------
        RunResult
            Contains the best solution found, champion policy,
            all worlds, policy history, and cost accounting.
        """
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ConfigurationError("rounds must be a positive integer")
        campaign_id = str(uuid.uuid4())
        await self._emit(EventType.CAMPAIGN_STARTED, data={"campaign_id": campaign_id})

        all_costs = CostRecord()
        best_overall_score: float | None = None
        best_overall_result: Any = None
        best_node_id: str | None = None
        best_tree = None

        for t in range(1, rounds + 1):
            logger.info("Dream-RSI round %d/%d", t, rounds)

            # ── Phase 1: Online exploration ──
            run_result = await self.run(task)

            # Accumulate costs
            all_costs.model_calls += run_result.costs.model_calls
            all_costs.online_agent_cost += run_result.costs.online_agent_cost
            all_costs.evaluator_calls += run_result.costs.evaluator_calls
            all_costs.online_evaluator_cost += run_result.costs.online_evaluator_cost

            if run_result.best_score is not None and (
                best_overall_score is None or run_result.best_score > best_overall_score
            ):
                best_overall_score = run_result.best_score
                best_overall_result = run_result.best
                best_node_id = run_result.best_node_id
                best_tree = run_result.tree

            # ── Phase 2: Convert tree to replay world ──
            if run_result.tree is not None:
                world = ReplayWorld(run_result.tree)
                self._worlds.append(world)
                await self._emit(
                    EventType.WORLD_CREATED,
                    data={"world_id": world.world_id, "tree_size": run_result.tree.size},
                )

            # ── Phase 3: Dreaming — policy improvement ──
            if self._frozen or len(self._worlds) < 1:
                continue

            await self._emit(EventType.DREAM_STARTED, data={"round": t})

            current_policy = self._champion_policy or self._get_policy()
            optimizer = self._get_optimizer()
            replay = StrictReplay(
                max_rounds=self._config.replay_max_rounds,
                max_parallelism=self._config.replay_max_parallelism,
                beta1=self._config.replay_beta1,
                beta2=self._config.replay_beta2,
            )

            # Replay current policy across all worlds to get baseline scores
            incumbent_scores: list[float] = []
            incumbent_trajectories: list[ReplayTrajectory] = []
            for world in self._worlds:
                traj = await replay.replay(world, current_policy, policy_id="incumbent")
                incumbent_trajectories.append(traj)
                if traj.replay_score is not None:
                    incumbent_scores.append(traj.replay_score)
                all_costs.replay_compute_ms += traj.elapsed_ms

            if len(incumbent_scores) != len(self._worlds):
                await self._emit(
                    EventType.DREAM_COMPLETED, data={"round": t, "reason": "unscored_world"}
                )
                continue

            incumbent_avg = (
                sum(incumbent_scores) / len(incumbent_scores)
                if incumbent_scores
                else float("-inf")
            )

            # Generate challenger policies
            challengers = await optimizer.generate(
                current_policy, incumbent_trajectories, self._budget
            )

            # Evaluate each challenger via replay
            best_challenger = None
            best_challenger_avg = incumbent_avg

            for challenger in challengers:
                challenger_scores: list[float] = []
                for world in self._worlds:
                    traj = await replay.replay(world, challenger, policy_id="challenger")
                    if traj.replay_score is not None:
                        challenger_scores.append(traj.replay_score)
                    all_costs.replay_compute_ms += traj.elapsed_ms

                if challenger_scores and len(challenger_scores) == len(self._worlds):
                    avg = sum(challenger_scores) / len(challenger_scores)
                    if avg > best_challenger_avg:
                        best_challenger_avg = avg
                        best_challenger = challenger

            # ── Phase 4: Promotion ──
            if best_challenger is not None and best_challenger_avg > incumbent_avg:
                promotion = self._get_promotion()

                from dreamrsi.models.policy import PolicyVersion

                inc_version = PolicyVersion(name="incumbent")
                chl_version = PolicyVersion(name="challenger")

                evidence = {
                    "incumbent_avg_score": incumbent_avg,
                    "challenger_avg_score": best_challenger_avg,
                    "num_worlds": len(self._worlds),
                }

                decision = await promotion.evaluate(inc_version, chl_version, evidence)

                from dreamrsi.models.promotion import PromotionOutcome

                if decision.outcome == PromotionOutcome.PROMOTED:
                    await self._save_policy(best_challenger)
                    self._champion_policy = best_challenger
                    self._policy_history.append(best_challenger)
                    await self._emit(
                        EventType.POLICY_PROMOTED,
                        data={
                            "round": t,
                            "incumbent_score": incumbent_avg,
                            "challenger_score": best_challenger_avg,
                        },
                    )
                    logger.info(
                        "Policy promoted: %.4f → %.4f",
                        incumbent_avg,
                        best_challenger_avg,
                    )
                else:
                    await self._emit(
                        EventType.POLICY_REJECTED,
                        data={"round": t, "reason": decision.reason},
                    )

            await self._emit(EventType.DREAM_COMPLETED, data={"round": t})

        await self._emit(EventType.CAMPAIGN_COMPLETED, data={"campaign_id": campaign_id})

        return RunResult(
            run_id=campaign_id,
            best=best_overall_result,
            best_score=best_overall_score,
            best_node_id=best_node_id,
            tree=best_tree,
            policy=self._get_policy(),
            champion_policy=self._champion_policy,
            rounds=rounds,
            costs=all_costs,
            metrics={
                "total_worlds": len(self._worlds),
                "policy_promotions": len(self._policy_history),
            },
            policy_history=list(self._policy_history),
            worlds=list(self._worlds),
        )

    def run_sync(self, task: Any) -> RunResult:
        """Synchronous wrapper around ``run()``."""
        self._check_sync_context()
        return asyncio.run(self.run(task))

    def improve_sync(self, task: Any, rounds: int = 5) -> RunResult:
        """Synchronous wrapper around ``improve()``."""
        self._check_sync_context()
        return asyncio.run(self.improve(task, rounds))

    @staticmethod
    def _check_sync_context():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise ConfigurationError("An event loop is running; use await run()/improve()")

    async def run_campaign(
        self,
        tasks: list[Any],
        rounds: int = 5,
    ) -> CampaignResult:
        """Run Dream-RSI improvement across multiple tasks."""
        campaign_id = str(uuid.uuid4())
        results: list[RunResult] = []

        for task in tasks:
            result = await self.improve(task, rounds=rounds)
            results.append(result)

        best_score = max(
            (r.best_score for r in results if r.best_score is not None),
            default=None,
        )

        return CampaignResult(
            campaign_id=campaign_id,
            best_score=best_score,
            champion=self._champion_policy,
            task_results=results,
            policy_history=list(self._policy_history),
            worlds=list(self._worlds),
        )

    # ── Observability API ──────────────────────────────────────

    async def get_tree(self, run_id: str) -> DiscoveryTree | None:
        """Get the discovery tree for a run (if stored)."""
        run = await self._store.get_run(run_id)
        if run is None:
            return None
        nodes = await self._store.get_nodes_by_tree(run.tree_id)
        if not nodes:
            return None
        return DiscoveryTree.from_dict(
            {
                "tree_id": run.tree_id,
                "root_id": next(n.id for n in nodes if n.is_root),
                "committed": True,
                "nodes": {n.id: n.to_dict() for n in nodes},
            }
        )

    async def list_policies(self) -> list[Any]:
        """List all known policy versions."""
        return await self._store.list_policies()

    async def get_champion(self) -> Any:
        """Get the current champion policy."""
        return self._champion_policy

    # ── Replay API ─────────────────────────────────────────────

    async def replay(
        self,
        world: ReplayWorld,
        policy: Any,
    ) -> ReplayTrajectory:
        """Replay a policy against a world."""
        r = StrictReplay(
            max_rounds=self._config.replay_max_rounds,
            max_parallelism=self._config.replay_max_parallelism,
            beta1=self._config.replay_beta1,
            beta2=self._config.replay_beta2,
        )
        return await r.replay(world, policy)

    async def compare_policies(
        self,
        policies: list[Any],
        worlds: list[ReplayWorld],
    ) -> dict[int, float]:
        """Compare multiple policies across worlds.

        Returns dict mapping policy index to average replay score.
        """
        r = StrictReplay(
            max_rounds=self._config.replay_max_rounds,
            max_parallelism=self._config.replay_max_parallelism,
            beta1=self._config.replay_beta1,
            beta2=self._config.replay_beta2,
        )
        results: dict[int, float] = {}

        for i, policy in enumerate(policies):
            scores: list[float] = []
            for world in worlds:
                traj = await r.replay(world, policy, policy_id=f"policy_{i}")
                if traj.replay_score is not None:
                    scores.append(traj.replay_score)
            if scores and len(scores) == len(worlds):
                results[i] = sum(scores) / len(scores)

        return results

    # ── Policy management ──────────────────────────────────────

    async def promote(self, policy: Any) -> None:
        """Manually promote a policy to champion."""
        await self._save_policy(policy)
        self._champion_policy = policy
        self._policy_history.append(policy)
        await self._emit(EventType.POLICY_PROMOTED, data={"manual": True})

    async def _save_policy(self, policy):
        previous = await self._store.get_champion()
        if previous is not None:
            previous.deployment_status = PolicyDeploymentStatus.RETIRED
            await self._store.save_policy(previous)
        version = PolicyVersion(
            name=type(policy).__name__,
            parent_id=previous.id if previous else None,
            deployment_status=PolicyDeploymentStatus.CHAMPION,
        )
        await self._store.save_policy(version)

    async def freeze_policy(self) -> None:
        """Freeze the current policy — no more improvements."""
        self._frozen = True

    async def unfreeze_policy(self) -> None:
        """Unfreeze — allow policy improvement again."""
        self._frozen = False

    # ── Export ──────────────────────────────────────────────────

    async def export_run(
        self,
        result: RunResult,
        path: str,
        fmt: str = "json",
    ) -> None:
        """Export a run result to file."""
        import json

        data: dict[str, Any] = {
            "run_id": result.run_id,
            "best_score": result.best_score,
            "rounds": result.rounds,
            "costs": {
                "model_calls": result.costs.model_calls,
                "evaluator_calls": result.costs.evaluator_calls,
                "online_agent": result.costs.online_agent_cost,
                "online_evaluator": result.costs.online_evaluator_cost,
                "replay_compute_ms": result.costs.replay_compute_ms,
            },
            "metrics": result.metrics,
            "tree": result.tree.to_dict() if result.tree else None,
        }

        if fmt != "json":
            raise ConfigurationError("Only JSON export is supported")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)

    # ── Internal helpers ───────────────────────────────────────

    def _build_policy_view(
        self,
        tree: DiscoveryTree,
        round_num: int,
        parallelism: int,
    ) -> PolicyView:
        """Build a PolicyView from the current tree state for online exploration."""
        eligible = tree.get_eligible()
        frontier: list[NodeSummary] = []

        for node in eligible:
            frontier.append(
                NodeSummary(
                    id=node.id,
                    parent_id=node.parent_id,
                    depth=node.depth,
                    score=node.score,
                    status=node.status,
                    children_count=len(node.children_ids),
                )
            )

        return PolicyView(
            frontier=frontier,
            best_score=tree.get_best_score(),
            total_nodes=tree.size,
            calls_used=tree.non_root_size,
            cost_used=tree.total_cost(),
            rounds_used=round_num - 1,
            tree_id=tree.tree_id,
            round_number=round_num,
        )


__all__ = ["Budget", "CostRecord", "RunResult", "CampaignResult", "DreamRSI", "DreamRSIConfig"]
