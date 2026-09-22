"""Replaceable outer exploration / dreaming orchestration.

DefaultMethod follows the research phase order. Custom methods can use the
runtime's public run, replay, compare_policies and promote operations.
"""

from __future__ import annotations

import logging
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

    def __init__(self, campaign_id=None, resume=False, abandon_inflight=False):
        self.campaign_id = campaign_id
        self.resume = resume
        self.abandon_inflight = abandon_inflight

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

        for t in range(completed + 1, rounds + 1):
            logger.info("Dream-RSI round %d/%d", t, rounds)

            if phase != "dream":
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

            # Generate challenger policies
            async def evaluate_candidate(candidate):
                return [await runtime.replay(w, candidate) for w in runtime._worlds]

            async def persist_developer(history):
                if self.campaign_id:
                    await runtime._store.save_checkpoint(
                        campaign_id + ":developer",
                        {
                            "history": history,
                        },
                    )

            if callable(getattr(optimizer, "develop", None)):
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
            else:
                challengers = await optimizer.generate(
                    current_policy, incumbent_trajectories, runtime._budget
                )

            # Evaluate each challenger via replay
            best_challenger = None
            best_challenger_avg = incumbent_avg
            best_world_scores = {}

            for challenger in challengers:
                challenger_scores: list[float] = []
                for world in runtime._worlds:
                    traj = await runtime.replay(world, challenger, policy_id="challenger")
                    if traj.replay_score is not None:
                        challenger_scores.append(traj.replay_score)
                    all_costs.replay_compute_ms += traj.elapsed_ms

                if challenger_scores and len(challenger_scores) == len(runtime._worlds):
                    avg = sum(challenger_scores) / len(challenger_scores)
                    if avg > best_challenger_avg:
                        best_challenger_avg = avg
                        best_challenger = challenger
                        best_world_scores = dict(
                            zip(
                                (w.world_id for w in runtime._worlds),
                                challenger_scores,
                                strict=True,
                            )
                        )

            # ── Phase 4: Promotion ──
            if best_challenger is not None and best_challenger_avg > incumbent_avg:
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
            rounds=rounds,
            costs=all_costs,
            metrics={
                "usage_scope": "runtime_lifetime_including_validation",
                "total_worlds": len(runtime._worlds),
                "policy_promotions": len(runtime._policy_history),
            },
            policy_history=list(runtime._policy_history),
            worlds=list(runtime._worlds),
        )
