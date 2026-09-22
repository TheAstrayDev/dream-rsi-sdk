"""Editable Appendix B source: relative trajectories and a deterministic portfolio.

The inherited constructor reads the one fixed beta scalar. The SDK also interprets
this file as an AppendixSourcePolicy without importing or executing host Python.
"""

from dreamrsi.appendix.api import GridPlan, LLMDesignedMethod, finalize_result
from dreamrsi.appendix.observation_signal import trajectory_signal

NAME = "OptimalPolicy"


class OptimalPolicy(LLMDesignedMethod):
    def _schedule(self, beta):
        return {"patience": 2 + int(4 * beta), "root_fraction": 0.25 + 0.75 * beta}

    def plan_grid(self, context):
        width = min(context.fallback_branch_count, context.hard_max_branch_count)
        depth = min(context.fallback_refine_count, context.hard_max_refine_count)
        reason = "Insufficient history; conservative context bootstrap"
        if len(context.history) >= 2:
            recent = context.history[-2:]
            roots = sum(row.get("root_improvements", 0) for row in recent)
            refinements = sum(row.get("refinement_improvements", 0) for row in recent)
            if refinements > roots:
                depth = min(depth + 1, context.hard_max_refine_count)
                reason = "Prior live refinement gains favor additional depth"
            elif roots > refinements:
                width = min(width + 1, context.hard_max_branch_count)
                reason = "Prior live root gains favor additional width"
        if context.trace_branch_count is not None:
            width = min(width, context.trace_branch_count)
        if context.trace_refine_count is not None:
            depth = min(depth, context.trace_refine_count)
        return GridPlan(branch_count=width, refine_count=depth, reason=reason)

    def solve(self, question, budget=None):
        question.reset()
        schedule = self._schedule(self.beta)
        root_count = len(question.legal_roots())
        root_limit = max(1, int(root_count * schedule["root_fraction"] + 0.999))
        while True:
            prefix = question.observed()
            branches = {}
            for observation in prefix.values():
                branch = str(observation.branch)
                if branch not in branches:
                    branches[branch] = []
                branches[branch].append(observation)
            normal = []
            exploration = []
            roots = []
            recovery = []
            tags_seen = []
            for cid in prefix:
                tags_seen.extend(question.meta(cid).tags)
            for cid in question.legal_actions():
                meta = question.meta(cid)
                if meta.attempt == 0:
                    if len(branches) < root_limit:
                        novelty = sum(tag not in tags_seen for tag in meta.tags)
                        roots.append([novelty, cid])
                    continue
                signal = trajectory_signal(branches[str(meta.branch)])
                if signal["hard_unrecoverable"]:
                    continue
                anchor = signal["anchor"]
                priority = anchor - question.baseline_score if anchor is not None else 0
                if signal["repairable"]:
                    if signal["failure_run"] <= schedule["patience"]:
                        recovery.append([priority, cid])
                elif signal["successful_count"] < 2:
                    exploration.append([priority, cid])
                elif signal["gain"] > 0 or signal["attempts"] < schedule["patience"]:
                    normal.append([priority, cid])
            roots.sort(key=lambda row: row[0], reverse=True)
            exploration.extend(roots[: max(0, root_limit - len(branches))])
            normal.sort(key=lambda row: row[0], reverse=True)
            exploration.sort(key=lambda row: row[0], reverse=True)
            recovery.sort(key=lambda row: row[0], reverse=True)
            workers = question.max_parallelism
            if budget is not None:
                workers = min(workers, max(0, budget - len(prefix)))
            batch = []
            if normal and len(batch) < workers:
                batch.append(normal.pop(0)[1])
            if exploration and len(batch) < workers:
                batch.append(exploration.pop(0)[1])
            if recovery and len(batch) < workers:
                batch.append(recovery.pop(0)[1])
            remaining = sorted(normal + exploration, key=lambda row: row[0], reverse=True)
            batch.extend(row[1] for row in remaining[: max(0, workers - len(batch))])
            if not batch:
                break
            question.probe_batch(batch)
        return finalize_result(question)
