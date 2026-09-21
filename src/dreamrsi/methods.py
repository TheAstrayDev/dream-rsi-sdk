"""Replaceable outer exploration / dreaming orchestration.

DefaultMethod follows the research phase order. Custom methods can use the
runtime's public run, replay, compare_policies and promote operations.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

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

    async def improve(self, runtime: DreamRSI, task: Any, rounds: int = 5) -> RunResult:
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ConfigurationError("rounds must be a positive integer")
        campaign_id = str(uuid.uuid4())
        await runtime._emit(EventType.CAMPAIGN_STARTED, data={"campaign_id": campaign_id})

        all_costs = CostRecord()
        best_overall_score: float | None = None
        best_overall_result: Any = None
        best_node_id: str | None = None
        best_tree = None

        for t in range(1, rounds + 1):
            logger.info("Dream-RSI round %d/%d", t, rounds)

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

            # ── Phase 3: Dreaming — policy improvement ──
            if runtime._frozen or len(runtime._worlds) < 1:
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
                continue

            incumbent_avg = (
                sum(incumbent_scores) / len(incumbent_scores)
                if incumbent_scores
                else float("-inf")
            )

            # Generate challenger policies
            challengers = await optimizer.generate(
                current_policy, incumbent_trajectories, runtime._budget
            )

            # Evaluate each challenger via replay
            best_challenger = None
            best_challenger_avg = incumbent_avg

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

            # ── Phase 4: Promotion ──
            if best_challenger is not None and best_challenger_avg > incumbent_avg:
                promotion = runtime._get_promotion()

                from dreamrsi.models.policy import PolicyVersion

                inc_version = PolicyVersion(name="incumbent")
                chl_version = PolicyVersion(name="challenger")

                evidence = {
                    "incumbent_avg_score": incumbent_avg,
                    "challenger_avg_score": best_challenger_avg,
                    "num_worlds": len(runtime._worlds),
                }

                decision = await promotion.evaluate(inc_version, chl_version, evidence)

                from dreamrsi.models.promotion import PromotionOutcome

                if decision.outcome == PromotionOutcome.PROMOTED:
                    await runtime._save_policy(best_challenger)
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
                    await runtime._emit(
                        EventType.POLICY_REJECTED,
                        data={"round": t, "reason": decision.reason},
                    )

            await runtime._emit(EventType.DREAM_COMPLETED, data={"round": t})

        await runtime._emit(EventType.CAMPAIGN_COMPLETED, data={"campaign_id": campaign_id})

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
                "total_worlds": len(runtime._worlds),
                "policy_promotions": len(runtime._policy_history),
            },
            policy_history=list(runtime._policy_history),
            worlds=list(runtime._worlds),
        )

