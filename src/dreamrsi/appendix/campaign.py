"""Persistent earlier-live history and explicit pre-grid planning for Appendix B."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict, replace

from dreamrsi._invoke import invoke
from dreamrsi.appendix.api import CellMeta, GridQuestion, Observation, cell_id, finalize_result
from dreamrsi.appendix.observation_signal import successful, trajectory_signal
from dreamrsi.appendix.replay import GridTrace, beta_sweep
from dreamrsi.errors import ConfigurationError
from dreamrsi.storage import InMemoryStore


class GridCampaign:
    """Separate Appendix B orchestration; SQLiteStore provides durable checkpoints.

    evaluate(meta, parent_observation, direction) is a fixed caller-owned discovery
    agent/evaluator integration. It must return Observation and report actual failure
    classes. Sync or async callbacks are supported. No live action is retried on resume.
    """

    def __init__(self, campaign_id, context, *, store=None, baseline_score=0.0):
        if not isinstance(campaign_id, str) or not campaign_id:
            raise ValueError("campaign_id is required")
        self.campaign_id = "appendix:" + campaign_id
        self.context = copy.deepcopy(context)
        self.store = store or InMemoryStore()
        self.baseline_score = baseline_score
        self._lock = asyncio.Lock()

    async def _load(self):
        configuration = {"context": asdict(self.context), "baseline_score": self.baseline_score}
        # Normalize tuples through the same JSON contract used by SQLiteStore.
        import json

        configuration = json.loads(json.dumps(configuration, allow_nan=False))
        state = await self.store.get_checkpoint(self.campaign_id)
        if state is None:
            return {
                "schema": "appendix-campaign-v1",
                "configuration": configuration,
                "history": [],
                "traces": [],
                "in_flight": None,
            }
        if (
            state.get("schema") != "appendix-campaign-v1"
            or state["configuration"] != configuration
        ):
            raise ConfigurationError("Appendix campaign configuration changed")
        return state

    async def planning_context(self):
        state = await self._load()
        return replace(self.context, history=tuple(self.context.history) + tuple(state["history"]))

    async def traces(self):
        return [GridTrace.from_dict(row) for row in (await self._load())["traces"]]

    async def run_cycle(self, policy, evaluate, *, direction_provider=None, budget=None):
        async with self._lock:
            state = await self._load()
            if state["in_flight"] is not None:
                raise ConfigurationError(
                    "Unreconciled live cycle; external calls will not be retried"
                )
            context = replace(
                self.context,
                history=tuple(self.context.history) + tuple(state["history"]),
                trace_branch_count=None,
                trace_refine_count=None,
            )
            # Validate the plan before calling the direction provider or discovery backend.
            plan = context.validate(await invoke(policy.plan_grid, copy.deepcopy(context)))
            cycle_id = len(state["history"])
            state["in_flight"] = {"cycle": cycle_id, "plan": asdict(plan), "beta": policy.beta}
            await self.store.save_checkpoint(self.campaign_id, state)
            directions = []
            for branch in range(plan.branch_count):
                tags = await invoke(direction_provider, branch) if direction_provider else ()
                if not isinstance(tags, (list, tuple)) or any(
                    type(tag) is not str for tag in tags
                ):
                    raise ValueError("Direction provider returns a list/tuple of semantic tags")
                directions.append(tuple(tags))
            cells = {}
            for branch in range(plan.branch_count):
                for attempt in range(plan.refine_count + 1):
                    cells[cell_id(branch, attempt)] = CellMeta(
                        branch,
                        attempt,
                        cell_id(branch, attempt - 1) if attempt else None,
                        len(cells),
                        directions[branch],
                    )
            loop = asyncio.get_running_loop()
            resolved = {}

            def resolve(cid):
                meta = cells[cid]
                parent = resolved.get(meta.parent_id)
                future = asyncio.run_coroutine_threadsafe(
                    invoke(evaluate, meta, parent, directions[meta.branch]),
                    loop,
                )
                obs = future.result()
                if not isinstance(obs, Observation):
                    raise TypeError("Discovery callback must return Observation")
                resolved[cid] = obs
                return obs

            question = GridQuestion(
                cells,
                resolve,
                baseline_score=self.baseline_score,
                max_parallelism=context.max_parallelism,
                live=True,
                probe_budget=budget,
            )
            # Cancellation leaves the journal in-flight; backend reconciliation is explicit.
            await invoke(policy.solve, question, budget)
            result = finalize_result(question)
            rows = question.observed()
            branch_rows = tuple(
                tuple(
                    obs
                    for _, obs in sorted(rows.items(), key=lambda item: item[1].attempt)
                    if obs.branch == branch
                )
                for branch in range(plan.branch_count)
            )
            manifest = {
                "cycle": cycle_id,
                "status": "completed",
                "phase": "live",
                "planned_grid": asdict(plan),
                "effective_grid": asdict(plan),
                "opened_width": len(question.opened_branches()),
                "opened_depth": max((obs.attempt for obs in rows.values()), default=0),
                "total_probes": result.total_probes,
                "decision_rounds": result.decision_rounds,
                "best_score": result.best_score,
                "beta": policy.beta,
                "root_improvements": sum(
                    successful(obs) and obs.score is not None and obs.score > self.baseline_score
                    for obs in rows.values()
                    if obs.attempt == 0
                ),
                "refinement_improvements": sum(
                    successful(obs) and obs.delta_vs_parent is not None and obs.delta_vs_parent > 0
                    for obs in rows.values()
                    if obs.attempt > 0
                ),
                "hard_failure_branches": sum(
                    trajectory_signal(branch)["hard_unrecoverable"] for branch in branch_rows
                ),
                "result": asdict(result),
            }
            if callable(getattr(policy, "to_dict", None)):
                manifest["policy"] = policy.to_dict()
            state["history"].append(manifest)
            if rows:
                state["traces"].append(
                    GridTrace(
                        f"{self.campaign_id}:{cycle_id}",
                        self.baseline_score,
                        branch_rows,
                        tuple(directions),
                        planning_history=context.history,
                    ).to_dict()
                )
            state["in_flight"] = None
            await self.store.save_checkpoint(self.campaign_id, state)
            return copy.deepcopy(manifest)

    async def evaluate_sweep(self, policy_factory, **settings):
        async with self._lock:
            state = await self._load()
            if state["in_flight"] is not None or not state["history"]:
                raise ConfigurationError("Sweep requires a completed live cycle")
            # Only earlier cycles are exposed to planning the replayed current cycle.
            context = replace(
                self.context, history=tuple(self.context.history) + tuple(state["history"][:-1])
            )
            report = await asyncio.to_thread(
                beta_sweep,
                policy_factory,
                [GridTrace.from_dict(row) for row in state["traces"]],
                context,
                **settings,
            )
            state["history"][-1]["beta_sweep"] = report
            await self.store.save_checkpoint(self.campaign_id, state)
            return report
