"""A deterministic reference portfolio controller, not the authors' unpublished policy."""

from __future__ import annotations

import hashlib
import math

from dreamrsi.appendix.api import GridPlan, LLMDesignedMethod, finalize_result
from dreamrsi.appendix.observation_signal import trajectory_signal


def choose_default_beta(history):
    """Use paired live + current-objective sweep evidence, never replay ceilings alone."""
    recent = list(history)[-3:]
    if len(recent) < 2:
        return 0.6
    if any(
        row.get("best_score") is None
        or row.get("beta_sweep", {}).get("objective_version") != "appendix-pareto-v1"
        or row.get("beta_sweep", {}).get("pareto", {}).get("reward") is None
        for row in recent
    ):
        return 0.6
    prior = float(recent[-1]["beta"])
    points = recent[-1]["beta_sweep"].get("frontier", [])
    current = min(points, key=lambda p: abs(p["beta"] - prior), default=None)
    if current is None:
        return 0.6
    improving = recent[-1]["best_score"] > recent[-2]["best_score"]
    nearby = [p for p in points if 0 < abs(p["beta"] - prior) <= 0.21]
    useful = [
        p
        for p in nearby
        if p["attainment"] > current["attainment"]
        and p["work"] <= current["work"] + 0.2
        and p["parallel_penalty"] <= current["parallel_penalty"] + 0.1
    ]
    if useful:
        chosen = max(useful, key=lambda p: (p["attainment"], -p["work"]))
        return round(max(0, min(1, prior + math.copysign(0.1, chosen["beta"] - prior))), 10)
    if not improving and prior >= 0.7 and recent[-2]["beta"] >= 0.7:
        cheaper = [
            p
            for p in nearby
            if p["beta"] < prior
            and p["attainment"] >= current["attainment"]
            and p["work"] < current["work"]
        ]
        if cheaper:
            return round(max(0, prior - 0.1), 10)
    return prior


class OptimalPolicy(LLMDesignedMethod):
    """Relative trajectory ranking, beta-controlled patience, dynamic batched recovery."""

    def _schedule(self, beta):
        return {
            "patience": 2 + int(4 * beta),
            "minimum_evidence": 2 + int(2 * beta),
            "root_fraction": 0.25 + 0.75 * beta,
            "prune_fraction": 0.6 * (1 - beta),
        }

    def plan_grid(self, context):
        width = min(context.fallback_branch_count, context.hard_max_branch_count)
        depth = min(context.fallback_refine_count, context.hard_max_refine_count)
        reason = "Insufficient earlier live evidence; conservative context bootstrap"
        history = context.history[-3:]
        if len(history) >= 2:
            wide = sum(row.get("root_improvements", 0) for row in history)
            deep = sum(row.get("refinement_improvements", 0) for row in history)
            hard = sum(row.get("hard_failure_branches", 0) for row in history)
            if hard > 0 and wide == deep == 0:
                width, depth = max(1, width - 1), max(0, depth - 1)
                reason = "Repeated hard failures without measured gains; reduce exposure"
            elif deep > wide and deep > 0:
                depth = min(depth + 1, context.hard_max_refine_count)
                reason = "Earlier live refinement improvements exceeded root improvements"
            elif wide > deep and wide > 0:
                width = min(width + 1, context.hard_max_branch_count)
                reason = "Earlier live root improvements exceeded refinement improvements"
        return GridPlan(width, depth, reason)

    def solve(self, question, budget=None):
        question.reset()
        schedule = self._schedule(self.beta)
        root_limit = max(1, math.ceil(len(question.legal_roots()) * schedule["root_fraction"]))
        while True:
            prefix = question.observed()
            by_branch = {}
            for obs in prefix.values():
                by_branch.setdefault(obs.branch, []).append(obs)
            signals = {branch: trajectory_signal(rows) for branch, rows in by_branch.items()}
            anchors = [s["anchor"] for s in signals.values() if s["anchor"] is not None]
            low, high = (min(anchors), max(anchors)) if anchors else (0, 0)
            normal, recovery, exploration, roots = [], [], [], []
            observed_tags = {tag for cid in prefix for tag in question.meta(cid).tags}
            for cid in question.legal_actions():
                meta = question.meta(cid)
                if meta.attempt == 0:
                    if len(by_branch) < root_limit:
                        novelty = len(set(meta.tags) - observed_tags)
                        # Stable direction-derived tie-break, not smallest branch id.
                        tie = int(hashlib.sha256(repr(meta.tags).encode()).hexdigest(), 16)
                        roots.append(((novelty, 0, tie), cid))
                    continue
                signal = signals[meta.branch]
                if signal["hard_unrecoverable"]:
                    continue
                anchor = signal["anchor"]
                relative = (
                    (anchor - low) / (high - low) if anchor is not None and high > low else 0
                )
                score = (relative, signal["gain"] or 0, -meta.seq)
                if signal["repairable"]:
                    if signal["failure_run"] <= schedule["patience"]:
                        recovery.append((score, cid))
                elif signal["successful_count"] < schedule["minimum_evidence"]:
                    exploration.append((score, cid))
                elif relative >= schedule["prune_fraction"] and (
                    signal["gain"] is None
                    or signal["gain"] > 0
                    or signal["attempts"] < schedule["patience"]
                ):
                    normal.append((score, cid))
            roots.sort(key=lambda item: item[0], reverse=True)
            exploration.extend(roots[: max(0, root_limit - len(by_branch))])
            # Role-local ranks avoid comparing direction metadata with score tuples.
            queues = [
                sorted(q, key=lambda item: item[0], reverse=True)
                for q in (normal, exploration, recovery)
            ]
            workers = question.max_parallelism
            if budget is not None:
                workers = min(workers, max(0, budget - question.budget_spent))
            batch = []
            # A strong successful refinement keeps representation when recovery competes.
            order = [0, 1, 2] if queues[0] else [1, 2]
            for index in order:
                if queues[index] and len(batch) < workers:
                    batch.append(queues[index].pop(0)[1])
            remaining = sorted(queues[0] + queues[1], key=lambda row: row[0][0], reverse=True)
            batch.extend(cid for _, cid in remaining[: max(0, workers - len(batch))])
            if not batch:
                break
            question.probe_batch(batch)
        return finalize_result(question)
