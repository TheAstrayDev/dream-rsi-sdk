"""Real model source revision against a fixed Appendix B beta-sweep evaluator."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict

from dreamrsi._invoke import invoke
from dreamrsi.accounting import Usage
from dreamrsi.appendix.policy import choose_default_beta
from dreamrsi.appendix.replay import beta_sweep
from dreamrsi.appendix.source import AppendixSourcePolicy
from dreamrsi.artifacts import PolicyArtifact
from dreamrsi.developer import DeveloperConfig, _revision

INSTRUCTION = """Develop complete executable Appendix B exploration policy code.
Return only Python source defining NAME = 'OptimalPolicy' and class
OptimalPolicy(LLMDesignedMethod), with solve(self, question, budget=None),
plan_grid(self, context), and optionally __init__(self). The fixed discovery agent
and evaluator cannot be edited. Rewrite algorithmic code from measured replay
feedback; do not merely tune constants or copy winning cell IDs or score targets.
Allowed virtual imports: from dreamrsi.appendix.api import LLMDesignedMethod,
GridPlan, SimResult, _budget_done, _record_curve, finalize_result; from
dreamrsi.appendix.observation_signal import branch_promising, branch_failed_hard,
probe_improved_vs_parent, probe_improved_vs_baseline, successful, trajectory_signal.
These are interpreter capabilities, not host imports. Use bounded Python syntax
(functions, if/for/while, lists/dicts, comprehensions, math, sorting key lambdas).
No exec, filesystem, network, arbitrary imports, super(), sets, decorators or exceptions.
self.config is provided before __init__; read beta once with
self.beta = float(self.config.get('beta', 0.6)). Honor a provided beta. Never change
beta/config in solve. Route behavior through one _schedule(beta) helper.
question.reset(), observed(), legal_actions(), legal_roots(), opened_branches(),
meta(cell_id), probe_batch(list, on_reveal=lambda obs: ...), baseline_score and
max_parallelism are available. No hidden trace or bookkeeping attributes are readable.
Observation fields: branch, attempt, score, evaluated, valid, fail_class, error,
delta_vs_baseline, delta_vs_parent, n_valid, n_total. Meta: branch, attempt, parent_id,
seq, tags. Records support field syntax or dictionary keys. Derive signals only
from prefix observations. Success is evaluated and error is None and fail_class
equals 'ok', even when valid is False. Preserve successful anchors across repairable
failures. compile_other and zero-valid alone do not justify permanent closure;
later success reopens a branch. Use complete trajectories, relative improvements
and deterministic ranking, never absolute score cutoffs or random sampling.
Build dynamic independent batches up to max_parallelism: successful refinement,
underexplored/new directions and at most one justified recovery, without starving
normal refinements. Consider all remaining roles before stopping. Budget can be None;
terminate on an empty batch and do not repeatedly probe revealed cells.
Return finalize_result(question, SimResult()) from solve. plan_grid must return
GridPlan(branch_count=..., refine_count=..., reason=...) on every path BEFORE an
episode exists. It can use only context.history of earlier completed live cycles,
fallback_branch_count/refine_count, hard_max_branch_count/refine_count,
max_parallelism and optional trace_branch_count/refine_count. Never inspect question
from plan_grid. Unsupported replay plans earn no reward. Use explicit conservative
bootstrap if evidence is insufficient. Width vs depth must follow past evidence.
Beta is fixed per episode, swept offline, and its next default uses paired prior
live manifests and sweep evidence. Legacy AUC objectives are not comparable.
The evaluator reports an explicitly SDK-versioned attainment/work AUC minus
parallel_weight * mean(effective_sequential_rounds / probes). Do not claim exact
numerical equivalence to unpublished research code. Make beta change real behavior.
"""


def policy_at_beta(policy, beta):
    if isinstance(policy, AppendixSourcePolicy):
        return AppendixSourcePolicy(
            policy.artifact,
            {**policy.config, "beta": beta},
            sandbox=policy.sandbox,
            timeout_s=policy.timeout_s,
        )
    candidate = copy.deepcopy(policy)
    candidate.config = {**candidate.config, "beta": beta}
    candidate.beta = beta
    return candidate


class AppendixPolicyDeveloper:
    """Same provider callback as LLMPolicyDeveloper; every revision runs a full sweep.

    History preserves raw source, failures and measured trajectories. This developer
    does not automatically resume external model calls or claim holdout promotion.
    """

    def __init__(self, generate, *, config=None, sandbox=None, sweep_settings=None):
        self.generate = generate
        self.config = config or DeveloperConfig(response_format="python")
        self.sandbox = sandbox
        self.sweep_settings = copy.deepcopy(sweep_settings or {})
        self.history = []

    async def develop(self, incumbent, traces, context):
        traces, context = copy.deepcopy(tuple(traces)), copy.deepcopy(context)
        best = incumbent
        baseline = await asyncio.to_thread(
            beta_sweep,
            lambda beta: policy_at_beta(incumbent, beta),
            traces,
            context,
            **self.sweep_settings,
        )
        best_score = baseline["pareto"]["reward"]
        feedback = baseline
        previous_source = getattr(getattr(incumbent, "artifact", None), "source", None)
        default_beta = choose_default_beta(context.history)
        for revision in range(self.config.revisions):
            usage = Usage()

            def report_usage(value):
                nonlocal usage
                usage = usage + value

            encoded = json.dumps(feedback, allow_nan=False)
            if len(encoded) > self.config.max_feedback_chars:
                feedback_value = {
                    "truncated": True,
                    "original_characters": len(encoded),
                    "prefix_json_text": encoded[: self.config.max_feedback_chars],
                }
            else:
                feedback_value = feedback
            request = {
                "instruction": INSTRUCTION,
                "response_format": "python",
                "revision": revision,
                "previous_source": previous_source,
                "best_source": getattr(getattr(best, "artifact", None), "source", None),
                "feedback": feedback_value,
                "planning_context": asdict(context),
                "recommended_default_beta": default_beta,
                "report_usage": report_usage,
            }
            record = {
                "revision": revision,
                "status": "generating",
                "score": None,
                "request": {k: v for k, v in request.items() if k != "report_usage"},
            }
            self.history.append(record)
            try:
                response = await asyncio.wait_for(
                    invoke(self.generate, request), self.config.model_timeout_s
                )
                record["response"] = response
                source, diagnosis, changes = _revision(response)
                parent = getattr(getattr(best, "artifact", None), "source_hash", None)
                artifact = PolicyArtifact(
                    source,
                    parent_hash=parent,
                    provenance={"developer": "appendix", "revision": revision},
                )
                record.update(artifact=artifact.to_dict(), diagnosis=diagnosis, changes=changes)
                previous_source = source
                candidate = AppendixSourcePolicy(
                    artifact, sandbox=self.sandbox, timeout_s=self.config.policy_timeout_s
                )
                report = await asyncio.to_thread(
                    beta_sweep,
                    lambda beta, candidate=candidate: policy_at_beta(candidate, beta),
                    traces,
                    context,
                    **self.sweep_settings,
                )
                record["evaluation"] = report
                score = report["pareto"]["reward"]
                record.update(status="scored" if score is not None else "failed", score=score)
                feedback = report
                if score is not None and (best_score is None or score > best_score):
                    best, best_score = candidate, score
            except Exception as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                feedback = {"status": "failed", "score": None, "error": record["error"]}
            finally:
                record["usage"] = asdict(usage)
        return best
