"""Replaceable outer exploration / dreaming orchestration.

DefaultMethod follows the research phase order. Custom methods can use the
runtime's public run, replay, compare_policies and promote operations.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import TYPE_CHECKING, Any

from dreamrsi import checkpoints
from dreamrsi.errors import ConfigurationError
from dreamrsi.events import EventType
from dreamrsi.models.base import CostRecord
from dreamrsi.models.results import RunResult
from dreamrsi.replay import ReplayTrajectory, ReplayWorld

if TYPE_CHECKING:
    from dreamrsi.runtime import DreamRSI

logger = logging.getLogger("dreamrsi")


class DefaultMethod:
    """Online rollout, freeze history, replay, generate, compare, promote."""

    def __init__(
        self,
        campaign_id=None,
        resume=False,
        abandon_inflight=False,
        *,
        online=True,
        force_developer=False,
    ):
        if type(online) is not bool:
            raise ConfigurationError("online must be boolean")
        if type(force_developer) is not bool:
            raise ConfigurationError("force_developer must be boolean")
        self.campaign_id = campaign_id
        self.resume = resume
        self.abandon_inflight = abandon_inflight
        self.online = online
        self.force_developer = force_developer

    async def improve(self, runtime: DreamRSI, task: Any, rounds: int = 5) -> RunResult:
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ConfigurationError("rounds must be a positive integer")
        campaign_id = self.campaign_id or str(uuid.uuid4())
        completed = 0
        phase = "ready"
        runtime._campaign_id = self.campaign_id
        if self.campaign_id:
            if self.resume:
                completed, phase = await checkpoints.restore(runtime, campaign_id, task)
                if phase == "online":
                    if not self.abandon_inflight:
                        raise ConfigurationError(
                            "Interrupted external run requires reconciliation. Confirm external "
                            "work is stopped, then resume with abandon_inflight=True to skip it; "
                            "reserved costs remain charged."
                        )
                    completed += 1
                    phase = "ready"
            elif await runtime._store.get_checkpoint(campaign_id) is not None:
                raise ConfigurationError("Campaign already exists; explicitly resume it")
        if not self.online and not runtime._worlds:
            raise ConfigurationError("Offline improvement requires a recorded training world")
        # Replaying the same frozen worlds in multiple outer rounds adds no
        # evidence. The developer's inner revision loop handles rewrites.
        effective_rounds = rounds if self.online else 1
        await runtime._emit(EventType.CAMPAIGN_STARTED, data={"campaign_id": campaign_id})

        if self.campaign_id and not self.resume:
            await checkpoints.save(runtime, campaign_id, task, completed)
        if runtime.validation is not None:
            await runtime.validation.prepare(runtime, task)

        all_costs = CostRecord()
        best_overall_score: float | None = None
        best_overall_result: Any = None
        best_node_id: str | None = None
        best_tree = None

        for world in runtime._worlds:
            node = world.tree.get_best_node()
            if (
                node
                and node.score is not None
                and (best_overall_score is None or node.score > best_overall_score)
            ):
                best_overall_score, best_overall_result = node.score, node.observation
                best_node_id, best_tree = node.id, world.tree

        if self.campaign_id and not self.resume:
            await checkpoints.save(runtime, campaign_id, task, completed)

        for t in range(completed + 1, effective_rounds + 1):
            logger.info("Dream-RSI round %d/%d", t, effective_rounds)

            if self.online and phase != "dream":
                if self.campaign_id:
                    await checkpoints.save(runtime, campaign_id, task, t - 1, phase="online")
                # ── Phase 1: Online exploration ──
                run_result = await runtime.run(task)

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
                    runtime._worlds.append(world)
                    await runtime._emit(
                        EventType.WORLD_CREATED,
                        data={"world_id": world.world_id, "tree_size": run_result.tree.size},
                    )
                if self.campaign_id:
                    await checkpoints.save(runtime, campaign_id, task, t - 1, phase="dream")
            phase = "ready"

            # ── Phase 3: Dreaming — policy improvement ──
            if runtime._frozen or len(runtime._worlds) < 1:
                if self.campaign_id:
                    await checkpoints.save(runtime, campaign_id, task, t)
                continue

            await runtime._emit(EventType.DREAM_STARTED, data={"round": t})

            current_policy = runtime._champion_policy or runtime._get_policy()
            optimizer = runtime._get_optimizer()

            # Replay current policy across all worlds to get baseline scores
            incumbent_scores: list[float] = []
            incumbent_trajectories: list[ReplayTrajectory] = []
            for world in runtime._worlds:
                traj = await runtime.replay(world, current_policy, policy_id="incumbent")
                incumbent_trajectories.append(traj)
                if traj.replay_score is not None:
                    incumbent_scores.append(traj.replay_score)
                all_costs.replay_compute_ms += traj.elapsed_ms

            if len(incumbent_scores) != len(runtime._worlds):
                await runtime._emit(
                    EventType.DREAM_COMPLETED, data={"round": t, "reason": "unscored_world"}
                )
                if self.campaign_id:
                    await checkpoints.save(runtime, campaign_id, task, t)
                continue

            incumbent_avg = (
                sum(incumbent_scores) / len(incumbent_scores)
                if incumbent_scores
                else float("-inf")
            )

            # Rank quality and work separately. The replay objective remains
            # recorded for research, but its fixed beta is not a quality gate.
            quality_metric = getattr(runtime.validation, "quality_from_trajectory", None)

            def raw_quality(
                trajectory,
                metric=quality_metric,
                has_validation=runtime.validation is not None,
            ):
                value = (
                    metric(trajectory)
                    if callable(metric)
                    else trajectory.best_score
                )
                # A custom replay engine may expose only its objective. Keep
                # such extensions usable when no raw metric was configured.
                if value is None and not has_validation:
                    value = trajectory.replay_score
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return None
                return float(value) if math.isfinite(value) else None

            incumbent_quality_raw = [raw_quality(traj) for traj in incumbent_trajectories]
            if any(value is None for value in incumbent_quality_raw):
                await runtime._emit(
                    EventType.DREAM_COMPLETED, data={"round": t, "reason": "unscored_quality"}
                )
                if self.campaign_id:
                    await checkpoints.save(runtime, campaign_id, task, t)
                continue
            incumbent_quality = [
                value for value in incumbent_quality_raw if value is not None
            ]

            # A developer may evaluate its own proposals. Cache those free
            # replay results rather than traversing the same worlds twice.
            replay_cache = {}

            async def evaluate_candidate(candidate, cache=replay_cache):
                key = id(candidate)
                if key not in cache:
                    trajectories = [
                        await runtime.replay(w, candidate, policy_id="challenger")
                        for w in runtime._worlds
                    ]
                    cache[key] = trajectories
                    all_costs.replay_compute_ms += sum(traj.elapsed_ms for traj in trajectories)
                return cache[key]

            async def persist_developer(history):
                if self.campaign_id:
                    await runtime._store.save_checkpoint(
                        campaign_id + ":developer",
                        {
                            "history": history,
                        },
                    )

            best_challenger = None
            best_challenger_avg = None
            best_challenger_trajectories = None
            best_challenger_qualities = None
            best_world_scores = {}
            incumbent_probes = sum(traj.total_probes for traj in incumbent_trajectories)

            async def select_challenger(
                challengers,
                baseline_quality=tuple(incumbent_quality),
                baseline_probes=incumbent_probes,
            ):
                nonlocal best_challenger, best_challenger_avg
                nonlocal best_challenger_trajectories, best_challenger_qualities
                nonlocal best_world_scores
                for challenger in challengers:
                    try:
                        trajectories = await evaluate_candidate(challenger)
                    except Exception:
                        logger.exception("Challenger replay failed")
                        continue
                    scores = [traj.replay_score for traj in trajectories]
                    raw_qualities = [raw_quality(traj) for traj in trajectories]
                    if (
                        len(trajectories) != len(runtime._worlds)
                        or any(score is None for score in scores)
                        or any(value is None for value in raw_qualities)
                    ):
                        continue
                    qualities = [value for value in raw_qualities if value is not None]
                    if any(
                        challenger_quality + 1e-9 < incumbent_value
                        for challenger_quality, incumbent_value in zip(
                            qualities, baseline_quality, strict=True
                        )
                    ):
                        continue
                    probes = sum(traj.total_probes for traj in trajectories)
                    if probes > baseline_probes:
                        continue
                    gain = sum(qualities) - sum(baseline_quality)
                    if probes == baseline_probes and gain <= 1e-9:
                        continue
                    if best_challenger_trajectories is not None:
                        previous_probes = sum(
                            traj.total_probes for traj in best_challenger_trajectories
                        )
                        previous_quality = sum(best_challenger_qualities or ())
                        if (probes, -sum(qualities)) >= (
                            previous_probes,
                            -previous_quality,
                        ):
                            continue
                    best_challenger = challenger
                    best_challenger_avg = sum(scores) / len(scores)
                    best_challenger_trajectories = trajectories
                    best_challenger_qualities = qualities
                    best_world_scores = dict(
                        zip((w.world_id for w in runtime._worlds), scores, strict=True)
                    )

            if callable(getattr(optimizer, "develop", None)):
                from dreamrsi.optimization import DeterministicPolicyOptimizer

                cheap = DeterministicPolicyOptimizer(
                    num_variants=runtime._config.optimizer_variants,
                    seed=runtime._config.random_seed,
                )
                try:
                    variants = await cheap.generate(
                        current_policy, incumbent_trajectories, runtime._budget
                    )
                except ConfigurationError:
                    # Generated source has no parameter grid. A tiny fixed
                    # portfolio still gives it a zero-LLM cost baseline.
                    from dreamrsi.policies import (
                        BalancedPolicy,
                        DepthFirstPolicy,
                        FixedParallelPolicy,
                        GreedyPolicy,
                    )

                    variants = [
                        FixedParallelPolicy(branches=1, max_depth=1),
                        GreedyPolicy(batch_size=1),
                        BalancedPolicy(batch_size=1),
                        DepthFirstPolicy(),
                    ][: runtime._config.optimizer_variants]
                await select_challenger(variants)
                if best_challenger is None or self.force_developer:
                    session_options = (
                        {"session_id": f"{campaign_id}:round:{t}"}
                        if getattr(optimizer, "supports_sessions", False)
                        else {}
                    )
                    challengers = await optimizer.develop(
                        current_policy,
                        incumbent_trajectories,
                        evaluate_candidate,
                        runtime._budget,
                        charge=runtime._charge,
                        persist=persist_developer,
                        **session_options,
                    )
                    await select_challenger(challengers)
            else:
                challengers = await optimizer.generate(
                    current_policy, incumbent_trajectories, runtime._budget
                )
                await select_challenger(challengers)

            # ── Phase 4: Promotion ──
            if best_challenger is not None:
                assert best_challenger_trajectories is not None
                promotion = runtime._get_promotion()

                from dreamrsi.models.policy import PolicyDeploymentStatus

                inc_version = await runtime._store.get_champion()
                if inc_version is None:
                    inc_version = await runtime._save_policy(current_policy)
                inc_version.replay_scores = {
                    w.world_id: score
                    for w, score in zip(runtime._worlds, incumbent_scores, strict=True)
                }
                await runtime._store.save_policy(inc_version)
                chl_version = runtime._policy_version(best_challenger)
                chl_version.parent_id = inc_version.id
                chl_version.replay_scores = best_world_scores

                evidence = {
                    "incumbent_avg_score": incumbent_avg,
                    "challenger_avg_score": best_challenger_avg,
                    "num_worlds": len(runtime._worlds),
                    "training_reports": [
                        {
                            "role": role,
                            "world_id": world.world_id,
                            "raw_quality": raw_quality(trajectory),
                            "probes": trajectory.total_probes,
                        }
                        for role, trajectories in (
                            ("incumbent", incumbent_trajectories),
                            ("challenger", best_challenger_trajectories),
                        )
                        for world, trajectory in zip(
                            runtime._worlds, trajectories, strict=True
                        )
                    ],
                }

                if runtime.validation is not None:
                    evidence.update(
                        await runtime.validation.evaluate(runtime, current_policy, best_challenger)
                    )

                decision = await promotion.evaluate(inc_version, chl_version, evidence)
                chl_version.validation_scores = evidence.get("validation_scores", {})
                chl_version.metadata["promotion"] = decision.to_dict()

                from dreamrsi.models.promotion import PromotionOutcome

                if decision.outcome == PromotionOutcome.PROMOTED:
                    await runtime._save_policy(best_challenger, chl_version)
                    runtime._champion_policy = best_challenger
                    runtime._policy_history.append(best_challenger)
                    await runtime._emit(
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
                    chl_version.deployment_status = PolicyDeploymentStatus.REJECTED
                    await runtime._store.save_policy(chl_version)
                    await runtime._emit(
                        EventType.POLICY_REJECTED,
                        data={"round": t, "reason": decision.reason},
                    )

            await runtime._emit(EventType.DREAM_COMPLETED, data={"round": t})
            if self.campaign_id:
                await checkpoints.save(runtime, campaign_id, task, t)

        await runtime._emit(EventType.CAMPAIGN_COMPLETED, data={"campaign_id": campaign_id})

        all_costs.model_calls = int(runtime.usage.spent["model_calls"])
        all_costs.evaluator_calls = int(runtime.usage.spent["evaluator_calls"])
        all_costs.developer_calls = int(runtime.usage.spent["developer_calls"])
        all_costs.online_agent_cost = 0.0
        all_costs.online_evaluator_cost = 0.0
        for record in runtime.usage.records:
            amount = record["usage"]
            all_costs.input_tokens += amount["input_tokens"]
            all_costs.output_tokens += amount["output_tokens"]
            all_costs.provider_calls += amount["provider_calls"]
            field = {
                "agent": "online_agent_cost",
                "evaluator": "online_evaluator_cost",
                "developer": "policy_generation_cost",
            }[record["stage"]]
            setattr(all_costs, field, getattr(all_costs, field) + amount["usd"])

        return RunResult(
            run_id=campaign_id,
            best=best_overall_result,
            best_score=best_overall_score,
            best_node_id=best_node_id,
            tree=best_tree,
            policy=runtime._get_policy(),
            champion_policy=runtime._champion_policy,
            rounds=effective_rounds,
            costs=all_costs,
            metrics={
                "usage_scope": "runtime_lifetime_including_validation",
                "total_worlds": len(runtime._worlds),
                "policy_promotions": len(runtime._policy_history),
            },
            policy_history=list(runtime._policy_history),
            worlds=list(runtime._worlds),
        )
