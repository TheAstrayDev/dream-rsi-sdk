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
from dreamrsi.accounting import Usage, UsageLedger, UsageReporter
from dreamrsi.adapters import CallableAgentAdapter
from dreamrsi.discovery import DiscoveryTree, NodeStatus
from dreamrsi.errors import (
    BudgetExceeded,
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
from dreamrsi.views import revealed_context

logger = logging.getLogger("dreamrsi")


# ── Config ─────────────────────────────────────────────────────


@dataclass
class DreamRSIConfig:
    """Optional configuration for DreamRSI."""

    replay_max_rounds: int = 1000
    replay_max_parallelism: int | None = None
    replay_beta1: float = 0.01
    replay_beta2: float = 0.005
    optimizer_variants: int = 5
    promotion_min_improvement: float = 0.0
    default_batch_size: int = 4
    random_seed: int | None = None

    def __post_init__(self):
        for name in (
            "replay_max_rounds",
            "optimizer_variants",
            "default_batch_size",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigurationError(f"{name} must be a positive integer")
        value = self.replay_max_parallelism
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ConfigurationError("replay_max_parallelism must be a positive integer or None")
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
    replay : ReplayEngine, optional
        Offline evaluation engine. Defaults to StrictReplay.
    objective : Objective, optional
        Overrides trajectory scoring consistently across replay and selection.
    method : Method, optional
        Owns the complete outer loop. Defaults to DefaultMethod.
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
        replay: Any | None = None,
        objective: Any | None = None,
        method: Any | None = None,
        experiment_version: str = "1",
        validation: Any | None = None,
        policy_codec: Any | None = None,
        campaign_budget: Budget | None = None,
        usage_limits: dict[str, Usage] | None = None,
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
        self.usage = UsageLedger(campaign_budget)
        self._usage_limits = usage_limits or {}
        if campaign_budget is not None and any(
            getattr(campaign_budget, field) is not None
            for field in ("max_nodes", "max_depth", "max_parallelism", "max_rounds")
        ):
            raise ConfigurationError(
                "Campaign limits support calls, tokens, USD and wall time; "
                "put tree/round/parallelism limits in the per-run budget"
            )
        self.experiment_version = experiment_version
        self._improving = False
        self._campaign_id = None
        self.validation = validation
        from dreamrsi.artifacts import PolicyCodec

        self.policy_codec = policy_codec or PolicyCodec(
            getattr(policy_optimizer, "sandbox", None) or getattr(policy, "sandbox", None)
        )
        self._replay_engine = replay
        self._objective = objective
        self._method = method
        for component, operation in (
            (replay, "replay"),
            (objective, "score"),
            (method, "improve"),
        ):
            if component is not None and not callable(getattr(component, operation, None)):
                raise ConfigurationError(f"Component must implement {operation}")
        if budget is not None and budget.max_nodes == 0:
            raise ConfigurationError("max_nodes includes the root; use at least 1")
        for limits in (budget, campaign_budget):
            if limits is not None and (limits.usd is not None or limits.tokens is not None):  # noqa: SIM102
                if not all(
                    stage in self._usage_limits for stage in ("agent", "evaluator", "developer")
                ):
                    raise ConfigurationError(
                        "USD/token budgets require explicit usage ceilings for all stages"
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

    async def record_world(self, task: Any, result: RunResult) -> ReplayWorld:
        """Add a completed run to training replay without making another agent call.

        The caller remains responsible for accounting for runs acquired outside
        this runtime. A run made by this runtime is already in ``usage``.
        """
        if self._improving:
            raise ConfigurationError("Cannot add training worlds during improvement")
        if not isinstance(result, RunResult) or result.tree is None:
            raise ConfigurationError("record_world requires a completed RunResult with a tree")
        if not result.tree.is_committed or result.tree.root_id is None:
            raise ConfigurationError("Only committed discovery trees can become replay worlds")
        if self.validation is not None:
            from dreamrsi.validation import task_key

            fingerprint = task_key(task)
            if fingerprint in {task_key(t) for t in self.validation.tasks}:
                raise ConfigurationError("Training task overlaps the validation partition")
            stored_run = await self._store.get_run(result.run_id)
            if (
                stored_run is None
                or stored_run.status != RunStatus.COMPLETED
                or stored_run.tree_id != result.tree.tree_id
                or stored_run.metadata.get("task_key") != fingerprint
            ):
                raise ConfigurationError("Recorded run does not belong to the supplied task")
        for world in self._worlds:
            if world.tree.tree_id == result.tree.tree_id:
                return world
        world = ReplayWorld(result.tree)
        self._worlds.append(world)
        await self._emit(
            EventType.WORLD_CREATED,
            data={"world_id": world.world_id, "tree_size": world.tree.size},
        )
        return world

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
        from dreamrsi.promotion import CostQualityGate

        self._promotion = CostQualityGate(
            min_quality_improvement=self._config.promotion_min_improvement
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
        run_usage = UsageLedger(self._budget)
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
        if self.validation is not None:
            from dreamrsi.validation import task_key

            record.metadata["task_key"] = task_key(task)
        await self._store.save_run(record)
        await self._emit(EventType.RUN_STARTED, run_id=run_id)

        cancellation_status = {}

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
                "attempt_id": uuid.uuid4().hex,
            }
            evaluation = None
            try:
                state = await invoke(clone, parent.state)

                async def agent_attempt():
                    await self._emit(
                        EventType.ATTEMPT_STARTED,
                        run_id=run_id,
                        data={
                            "attempt_id": context["attempt_id"],
                            "parent_id": parent.id,
                        },
                    )
                    proposal = await invoke(self._adapter.propose, state, context)
                    execution = await invoke(self._adapter.execute, proposal, state, context)
                    observation = await invoke(self._adapter.observe, execution, state)
                    return proposal, execution, observation

                proposal, execution, observation = await self._charge(
                    "agent", agent_attempt, context=context, local=run_usage, costs=costs
                )
                evaluation = await self._charge(
                    "evaluator",
                    self._evaluator.evaluate,
                    observation,
                    context,
                    context=context,
                    local=run_usage,
                    costs=costs,
                )
                next_state = await invoke(self._adapter.next_state, observation, state)
                return dict(
                    state=next_state,
                    proposal=proposal,
                    action=execution,
                    observation=observation,
                    score=evaluation.score,
                    cost=sum(u["usd"] for u in context.get("usage", {}).values()),
                    metadata={
                        "attempt_id": context["attempt_id"],
                        "usage": context.get("usage", {}),
                        "evaluation": evaluation.to_dict(),
                    },
                    status=NodeStatus.COMPLETED,
                ), evaluation
            except asyncio.CancelledError:
                cancel = getattr(self._adapter, "cancel", None)
                confirmed = False
                if callable(cancel):
                    try:
                        confirmed = bool(
                            await asyncio.wait_for(
                                invoke(cancel, context["attempt_id"]), timeout=5
                            )
                        )
                    except Exception:
                        confirmed = False
                cancellation_status[parent.id] = confirmed
                raise
            except BudgetExceeded:
                return dict(
                    state=state,
                    status=NodeStatus.SKIPPED,
                    metadata={"error": "Campaign budget exhausted"},
                ), evaluation
            except Exception as exc:
                return dict(
                    state=state,
                    status=NodeStatus.FAILED,
                    cost=sum(u["usd"] for u in context.get("usage", {}).values()),
                    metadata={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "usage": context.get("usage", {}),
                    },
                ), evaluation

        async def collect():
            nonlocal rounds_done, stop_reason
            initial = await invoke(self._adapter.initial_state, task)
            tree.create_root(state=initial)
            last_round = None
            for round_num in range(1, max_rounds + 1):
                if self.usage.breached or run_usage.breached:
                    stop_reason = "budget"
                    break
                slots = min(workers, max(0, max_nodes - tree.size))
                for name, used in (
                    ("model_calls", costs.model_calls),
                    ("evaluator_calls", costs.evaluator_calls),
                ):
                    cap = getattr(budget, name)
                    if cap is not None:
                        slots = min(slots, max(0, cap - used))
                for ledger in (run_usage, self.usage):
                    cap = getattr(ledger.budget, "total_llm_calls", None)
                    if cap is not None:
                        available = cap - ledger.spent["total_llm_calls"]
                        available -= ledger.held["total_llm_calls"]
                        slots = min(slots, max(0, available))
                if slots <= 0:
                    stop_reason = "budget"
                    break
                view = self._build_policy_view(tree, round_num, workers)
                view = replace(
                    view,
                    frontier=[n for n in view.frontier if n.depth < max_depth],
                    calls_used=costs.model_calls,
                    last_round=copy.deepcopy(last_round),
                    budget_remaining=replace(
                        budget, max_nodes=max_nodes, max_depth=max_depth,
                        max_parallelism=workers, max_rounds=max_rounds,
                    ).remaining(
                        Budget(
                            model_calls=costs.model_calls,
                            evaluator_calls=costs.evaluator_calls,
                            total_llm_calls=costs.model_calls,
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
                                metadata={
                                    "error": "Attempt cancelled before completion",
                                    "external_cancellation_confirmed": cancellation_status.get(
                                        batch[index], False
                                    ),
                                },
                            ),
                            None,
                        )
                        for index, task in enumerate(tasks)
                    ]
                revealed_this_round = []
                for parent_id, (fields, evaluation) in zip(batch, results, strict=True):
                    node = tree.add_node(parent_id=parent_id, **fields)
                    revealed_this_round.append(node.id)
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
                last_round = {
                    "batch": list(batch),
                    "revealed_nodes": revealed_this_round,
                    "best_score_before": view.best_score,
                    "best_score_after": tree.get_best_score(),
                }
                rounds_done += 1
                if not cancelled and all(
                    fields.get("status") == NodeStatus.SKIPPED for fields, _ in results
                ):
                    stop_reason = "budget"
                    break
                if cancelled:
                    raise asyncio.CancelledError
                await self._emit(
                    EventType.ROUND_COMPLETED,
                    run_id=run_id,
                    round_number=round_num,
                    data={"tree_size": tree.size, "best_score": tree.get_best_score()},
                )

        time_limits = [v for v in (budget.wall_time_s, self.usage.remaining_time) if v is not None]
        timeout = asyncio.timeout(min(time_limits) if time_limits else None)
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

    async def _charge(self, stage, fn, *args, context=None, local=None, costs=None):
        ceiling = self._usage_limits.get(stage, Usage())
        reservation = self.usage.reserve(stage, ceiling)
        local_reservation = None
        reporter = UsageReporter()
        if context is not None:
            context["report_usage"] = reporter
        try:
            if local is not None:
                local_reservation = local.reserve(stage, ceiling)
        except BaseException:
            # Local admission failed before dispatch: release the global reservation.
            self.usage.release(reservation)
            raise
        try:
            if self._campaign_id:
                await self._store.save_checkpoint(
                    self._campaign_id + ":usage", self.usage.to_dict()
                )
        except BaseException:
            self.usage.release(reservation)
            if local_reservation is not None and local is not None:
                local.release(local_reservation)
            raise
        completed = False
        if costs is not None:
            if stage == "agent":
                costs.model_calls += 1
            elif stage == "evaluator":
                costs.evaluator_calls += 1
        try:
            async with asyncio.timeout(self.usage.remaining_time):
                result = await invoke(fn, *args)
            completed = True
            return result
        finally:
            # Cancelled/failed external work may still incur cost: retain its ceiling.
            measured = reporter.usage if reporter.reported else None
            if measured is not None and not completed:
                from dataclasses import asdict

                measured = Usage(
                    **{k: max(v, asdict(ceiling)[k]) for k, v in asdict(measured).items()}
                )
            self.usage.settle(reservation, measured, estimated=not completed)
            if local_reservation is not None and local is not None:
                local.settle(local_reservation, measured, estimated=not completed)
            if self._campaign_id:
                await self._store.save_checkpoint(
                    self._campaign_id + ":usage", self.usage.to_dict()
                )
            charged = measured if measured is not None else ceiling
            if context is not None:
                from dataclasses import asdict

                context.setdefault("usage", {})[stage] = {
                    **asdict(charged),
                    "estimated": measured is None or not completed,
                }
            if costs is not None:
                field = {
                    "agent": "online_agent_cost",
                    "evaluator": "online_evaluator_cost",
                    "developer": "policy_generation_cost",
                }[stage]
                setattr(costs, field, getattr(costs, field) + charged.usd)
                costs.input_tokens += charged.input_tokens
                costs.output_tokens += charged.output_tokens
                costs.provider_calls += charged.provider_calls

    async def improve(self, task: Any, rounds: int = 5) -> RunResult:
        """Delegate the complete outer loop to the configured Method."""
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ConfigurationError("rounds must be a positive integer")
        if self._method is None:
            from dreamrsi.methods import DefaultMethod

            self._method = DefaultMethod()
        if self._improving:
            raise ConfigurationError("One runtime cannot run concurrent improvement campaigns")
        self._improving = True
        try:
            async with asyncio.timeout(self.usage.remaining_time):
                return await invoke(self._method.improve, self, task, rounds=rounds)
        finally:
            self._improving = False

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

    def _get_replay(self):
        if self._replay_engine is None:
            budget = self._budget or Budget()
            workers = budget.max_parallelism
            if workers is None:
                workers = self._config.default_batch_size
            self._replay_engine = StrictReplay(
                max_rounds=self._config.replay_max_rounds,
                max_parallelism=self._config.replay_max_parallelism or max(1, workers),
                beta1=self._config.replay_beta1,
                beta2=self._config.replay_beta2,
                budget=Budget(
                    model_calls=budget.model_calls,
                    evaluator_calls=budget.evaluator_calls,
                    max_nodes=500 if budget.max_nodes is None else budget.max_nodes,
                    max_depth=20 if budget.max_depth is None else budget.max_depth,
                    max_parallelism=workers,
                ),
            )
        return self._replay_engine

    async def replay(
        self,
        world: ReplayWorld,
        policy: Any,
        policy_id: str = "",
    ) -> ReplayTrajectory:
        """Evaluate through the injected engine and optional global objective.

        The objective changes policy selection, not the fixed task evaluator.
        Only the resulting trajectory is exposed; hidden world outcomes are not.
        """
        trajectory = await invoke(self._get_replay().replay, world, policy, policy_id=policy_id)
        # Do not mutate an engine's cached trajectory when applying an objective.
        trajectory = copy.deepcopy(trajectory)
        if self._objective is not None:
            result = await invoke(self._objective.score, copy.deepcopy(trajectory))
            if not math.isfinite(result.score):
                raise ConfigurationError("Objective score must be finite")
            trajectory.replay_score = result.score
            trajectory.objective = {
                "type": type(self._objective).__name__,
                "direction": "maximize",
                "score": result.score,
                "components": copy.deepcopy(result.components),
                "metadata": copy.deepcopy(result.metadata),
            }
        if trajectory.replay_score is not None and not math.isfinite(trajectory.replay_score):
            raise ConfigurationError("Replay score must be finite")
        return trajectory

    async def compare_policies(
        self,
        policies: list[Any],
        worlds: list[ReplayWorld],
    ) -> dict[int, float]:
        """Compare multiple policies across worlds.

        Returns dict mapping policy index to average replay score.
        """
        results: dict[int, float] = {}

        for i, policy in enumerate(policies):
            scores: list[float] = []
            for world in worlds:
                traj = await self.replay(world, policy, policy_id=f"policy_{i}")
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

    def _policy_version(self, policy):
        artifact = getattr(policy, "artifact", None)
        return PolicyVersion(
            source=artifact.source if artifact else "builtin",
            source_hash=artifact.source_hash if artifact else "",
            metadata={"artifact": artifact.to_dict()} if artifact else {},
            name=type(policy).__name__,
            creation_method="source_code" if artifact else "manual",
        )

    async def _save_policy(self, policy, version=None):
        previous = await self._store.get_champion()
        version = version or self._policy_version(policy)
        if previous is not None and previous.id != version.id:
            previous.deployment_status = PolicyDeploymentStatus.RETIRED
            await self._store.save_policy(previous)
        version.parent_id = previous.id if previous else None
        version.deployment_status = PolicyDeploymentStatus.CHAMPION
        await self._store.save_policy(version)
        return version

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
                **result.costs.to_dict(),
                # Keep the original export aliases for existing consumers.
                "online_agent": result.costs.online_agent_cost,
                "online_evaluator": result.costs.online_evaluator_cost,
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
            **revealed_context(tree, {n.id for n in tree.iter_nodes()}),
            frontier=frontier,
            best_score=tree.get_best_score(),
            total_nodes=tree.size,
            calls_used=tree.non_root_size,
            cost_used=tree.total_cost(),
            rounds_used=round_num - 1,
            tree_id=tree.tree_id,
            round_number=round_num,
            max_parallelism=parallelism,
        )


__all__ = ["Budget", "CostRecord", "RunResult", "CampaignResult", "DreamRSI", "DreamRSIConfig"]
