"""Iterative source development on training replay feedback only."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from dreamrsi._invoke import invoke
from dreamrsi.artifacts import PolicyArtifact, SourcePolicy
from dreamrsi.errors import BudgetExceeded, ConfigurationError


@dataclass(frozen=True)
class DeveloperConfig:
    revisions: int = 5
    model_timeout_s: float = 120.0
    max_feedback_chars: int = 200000
    max_steps_per_world: int = 100
    recover_best: bool = True
    response_format: str = "json"
    policy_timeout_s: float = 5.0

    def __post_init__(self):
        for name in ("revisions", "max_feedback_chars", "max_steps_per_world"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_feedback_chars < 1024:
            raise ValueError("Feedback budget must be at least 1024 characters")
        for name in ("model_timeout_s", "policy_timeout_s"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        if type(self.recover_best) is not bool:
            raise ValueError("recover_best must be a boolean")
        if self.response_format not in ("json", "python"):
            raise ValueError("response_format must be json or python")


def _revision(response):
    if isinstance(response, str):
        text = response.strip()
        # Some local chat templates leave the explicit reasoning delimiter in content.
        # Keep the original response in history; only the final answer is executable.
        delimiters = list(re.finditer(r"(?m)^\s*</think>\s*$", text))
        if delimiters:
            text = text[delimiters[-1].end() :].strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if text.startswith("{"):
            response = json.loads(text)
        else:
            return text, "", ""
    if not isinstance(response, dict) or not isinstance(response.get("source"), str):
        raise TypeError("Return source text or {source, diagnosis, changes}")
    diagnosis, changes = response.get("diagnosis", ""), response.get("changes", "")
    if not isinstance(diagnosis, str) or not isinstance(changes, str):
        raise TypeError("diagnosis and changes must be strings")
    return response["source"], diagnosis, changes


class LLMPolicyDeveloper:
    """Supply an async or sync model callback: request dict -> Python source text.

    The SDK owns replay/feedback/revision. The caller chooses the fixed model,
    credentials and transport. No specific provider is required by the core.
    """

    supports_sessions = True

    def __init__(self, generate, sandbox=None, revisions=None, provenance=None, config=None):
        from dataclasses import replace

        self.config = config or DeveloperConfig()
        if revisions is not None:
            self.config = replace(self.config, revisions=revisions)
        self.generate_source = generate
        from dreamrsi.sandbox import PolicySandbox

        self.sandbox = sandbox if sandbox is not None else PolicySandbox()
        self.revisions = self.config.revisions
        self.provenance = provenance or {}
        self.history: list[dict[str, Any]] = []

    @classmethod
    def from_runnable(cls, model, usage_extract=None, **kwargs):
        """Connect a LangChain chat model/Runnable without embedding provider credentials."""

        async def generate(request):
            prompt = json.dumps(
                {k: v for k, v in request.items() if k not in ("report_usage", "usage")},
                allow_nan=False,
            )
            fn = getattr(model, "ainvoke", None) or model.invoke
            result = await invoke(fn, prompt)
            if usage_extract is not None and "report_usage" in request:
                request["report_usage"](usage_extract(result))
            source = getattr(result, "content", result)
            if not isinstance(source, str):
                raise TypeError("Developer model must return plain source text")
            return source

        return cls(generate, **kwargs)

    def feedback(self, trajectories):
        scores = [t.replay_score for t in trajectories]
        complete = bool(scores) and all(
            value is not None and math.isfinite(value) for value in scores
        )
        data = {
            "summary": {
                "world_count": len(trajectories),
                "all_worlds_scored": complete,
                "mean_score": sum(scores) / len(scores) if complete else None,
                "total_probes": sum(t.total_probes for t in trajectories),
                "total_rounds": sum(t.total_rounds for t in trajectories),
                "empty_rounds": sum(
                    not step.revealed_nodes for t in trajectories for step in t.steps
                ),
                "recorded_cost": sum(t.total_cost for t in trajectories),
            },
            "trajectories": [],
        }
        for trajectory in trajectories:
            item = trajectory.to_dict()
            item["outcome_source"] = item.pop("source")
            item.pop("elapsed_ms", None)
            item.pop("_schema_version", None)
            for observation in item["observations"].values():
                diagnostics = observation.get("diagnostics", {})
                diagnostics.pop("attempt_id", None)
                evaluation = diagnostics.get("evaluation")
                if isinstance(evaluation, dict):
                    for key in ("id", "created_at", "_schema_version"):
                        evaluation.pop(key, None)
            compact_steps = []
            previous_signature = None
            for step in item["steps"]:
                signature = {k: v for k, v in step.items() if k != "round_number"}
                if compact_steps and signature == previous_signature:
                    compact_steps[-1]["repeated_rounds"] += 1
                    compact_steps[-1]["last_round_number"] = step["round_number"]
                else:
                    compact_steps.append({**step, "repeated_rounds": 1})
                previous_signature = signature
            limit = self.config.max_steps_per_world
            item["steps_truncated"] = len(compact_steps) > limit
            # Retain early improvements as well as the final boundary/stop context.
            item["steps"] = (
                compact_steps[: (limit + 1) // 2] + compact_steps[-(limit // 2) :]
                if len(compact_steps) > limit and limit > 1
                else compact_steps[:limit]
            )
            data["trajectories"].append(item)

        def length():
            return len(json.dumps(data, allow_nan=False))

        if length() > self.config.max_feedback_chars:
            for item in data["trajectories"]:
                item["observations"] = {}
                item["observations_truncated"] = True
        if length() > self.config.max_feedback_chars:
            for item in data["trajectories"]:
                item["steps"] = []
                item["revealed_node_ids"] = []
                item["steps_truncated"] = True
        while length() > self.config.max_feedback_chars and data["trajectories"]:
            data["trajectories"].pop()
            data["world_details_truncated"] = True
        return data

    async def develop(
        self,
        incumbent,
        trajectories,
        evaluate,
        budget=None,
        charge=None,
        persist=None,
        session_id=None,
    ):
        source = getattr(getattr(incumbent, "artifact", None), "source", None)
        parent = getattr(getattr(incumbent, "artifact", None), "source_hash", None)
        feedback = self.feedback(trajectories)
        baseline_feedback = copy.deepcopy(feedback)
        baseline = feedback["summary"]["mean_score"]
        best_score, best_source, best_hash = baseline, source, parent
        evaluated_source = source
        candidates = []
        session_id = session_id or uuid.uuid4().hex
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "worlds": [
                        {k: v for k, v in t.to_dict().items() if k != "elapsed_ms"}
                        for t in trajectories
                    ],
                    "sandbox": self.sandbox.capabilities()
                    if hasattr(self.sandbox, "capabilities")
                    else type(self.sandbox).__name__,
                    "incumbent": parent,
                    "baseline": baseline,
                    "policy_timeout_s": self.config.policy_timeout_s,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        prior = [(i, r) for i, r in enumerate(self.history) if r.get("session_id") == session_id]
        pending = None
        for index, item in prior:
            if item.get("input_fingerprint") != fingerprint:
                raise ConfigurationError("Developer session world pool/incumbent changed")
            if item["status"] == "generating":
                raise ConfigurationError(
                    "An interrupted developer request has no recorded response. "
                    "Reconcile it before continuing, or explicitly use a new session ID."
                )
            if item["status"] == "generated":
                pending = (index, item)
                break
            artifact_data = item.get("artifact")
            if artifact_data:
                artifact = PolicyArtifact.from_dict(artifact_data)
                source, parent = artifact.source, artifact.source_hash
                evaluated_source = source
                if item["status"] == "scored":
                    candidates.append(
                        SourcePolicy(artifact, self.sandbox, self.config.policy_timeout_s)
                    )
                    score = item["evaluation"]["mean_score"]
                    if best_score is None or score > best_score:
                        best_score, best_source, best_hash = score, source, parent
                    if (
                        self.config.recover_best
                        and best_source is not None
                        and score != best_score
                    ):
                        source, parent = best_source, best_hash
            feedback = copy.deepcopy(item.get("feedback", feedback))
        next_revision = pending[1]["revision"] if pending else len(prior)
        for revision in range(next_revision, self.revisions):
            if feedback.get("error"):
                revision_goal = (
                    "Repair the reported source error; preserve the intended algorithm. "
                    "Return the entire corrected program."
                )
            elif feedback.get("summary", {}).get("empty_rounds", 0):
                revision_goal = (
                    f"Replay recorded {feedback['summary']['empty_rounds']} empty rounds. "
                    "Diagnose repeated decisions with no newly revealed evidence. "
                    "Use the last_round observation to redesign stopping or recovery logic, "
                    "while preserving attained quality. "
                    "Do not merely change comments or constants."
                )
            elif revision > 0:
                revision_goal = (
                    "Propose an algorithmically different candidate using measured feedback. "
                    "Changing comments, names or only a ranking coefficient is insufficient. "
                    "Compare which recorded actions improved quality and which wasted work; "
                    "change branching, batching or stopping logic accordingly. "
                    "The best prior program is retained, so a new hypothesis may be tested."
                )
            else:
                revision_goal = (
                    "Develop a complete policy from the baseline source and trajectories."
                )
            response_instruction = (
                "Return JSON {diagnosis: string, changes: string, source: string}. "
                "The source field contains the entire executable program, never a status label. "
                if self.config.response_format == "json"
                else "Return ONLY the complete Python policy source, "
                "optionally in a python code fence. "
                "Put a short diagnosis and explanation of changes in Python comments. "
                "Do not return JSON, a tuple, or prose outside the code. "
            )
            request = {
                "revision_goal": revision_goal,
                "instruction": (
                    "Revise only the exploration policy, never the discovery agent or evaluator. "
                    "Write and rewrite executable policy code, not built-in parameter values. "
                    + response_instruction
                    + "Define decide(view); use helper functions allowed by sandbox capabilities. "
                    "view and its nodes are DICTIONARIES: "
                    "use view['frontier'], NOT view.frontier. "
                    "Return a DICTIONARY, e.g. {'expand': [node['id']], 'stop': False}. "
                    "The legal choices are EXACTLY view['frontier']; all are expandable, "
                    "including COMPLETED nodes. Do not filter them by status/children_count. "
                    "At the start only the root exists with score None; "
                    "expand it to get feedback. "
                    "The root stays unscored forever: expanding it starts a NEW attempt; "
                    "expanding a non-root leaf REFINES that leaf's state. "
                    "A null score is not evidence of high quality. "
                    "Replay only reveals recorded children; a missing continuation reveals "
                    "nothing and consumes a round. Repeated empty rounds are counted. "
                    "IDs must be unique; parallelism, if provided, must be a positive integer. "
                    "Node scores can be null (especially the root); handle null before ranking. "
                    "Use only revealed observations/history. No files, network, environment, "
                    "subprocesses or hidden outcomes. Each decision starts fresh; history is in "
                    "view['history']. Improve measured replay quality/work/parallelism. "
                    "Failed revisions should be diagnosed and corrected from feedback."
                    " Optimize the measured mean replay score, not just the raw best score. "
                    "Use trajectories to identify wasted probes, premature stops, missed "
                    "refinement and serial batches. Make a concrete algorithmic change when "
                    "progress stalls; explain the evidence and expected effect. Never embed "
                    "recorded node IDs, task answers or absolute target scores in the code. "
                    "Keep code concise and use finite numeric values only."
                ),
                "response_format": self.config.response_format,
                "source": source,
                "best_source": best_source,
                "evaluated_source": evaluated_source,
                "baseline_score": baseline,
                "best_score": best_score,
                "policy_timeout_s": self.config.policy_timeout_s,
                "sandbox": self.sandbox.capabilities()
                if hasattr(self.sandbox, "capabilities")
                else {"language": "custom"},
                "incumbent_type": type(incumbent).__name__,
                "feedback": copy.deepcopy(feedback),
                "baseline_feedback": copy.deepcopy(baseline_feedback) if revision > 0 else None,
                "revision": revision,
                "last_response": self.history[-1].get("response", "")
                if self.history and self.history[-1].get("phase") == "parse"
                else None,
                "revision_history": [
                    {
                        "revision": item["revision"],
                        "status": item.get("status", "legacy"),
                        "diagnosis": item.get("diagnosis", "")[:1000],
                        "changes": item.get("changes", "")[:1000],
                        "score": item.get("evaluation", {}).get("mean_score"),
                        "error": item.get("error"),
                        "behavior_hash": item.get("behavior_hash"),
                    }
                    for item in self.history[-12:]
                ],
                "view_contract": {
                    "frontier": "legal nodes: id, parent_id, depth, score (number or null), "
                    "status, children_count (revealed children only)",
                    "observations": "revealed node ID -> observation and diagnostics",
                    "history": "all revealed node summaries, in creation order",
                    "best_score": "highest revealed score or null",
                    "calls_used": "revealed probes",
                    "rounds_used": "completed rounds",
                    "max_parallelism": "maximum number of simultaneous expansions",
                    "budget_remaining": (
                        "remaining limits; null fields mean unlimited/unavailable. Default replay "
                        "counts one logical model/evaluator call per revealed probe, not provider "
                        "billing; an empty boundary consumes a round only. Replay has its own "
                        "round limit. Custom replay engines may omit this object."
                    ),
                    "last_round": "null initially; otherwise previous executed batch, "
                    "revealed_nodes, best_score_before and best_score_after. "
                    "Contains past outcomes only; an empty revealed_nodes means no new evidence.",
                },
            }
            record: dict[str, Any] = {
                "revision": revision,
                "parent_hash": parent,
                "best_score_before": best_score,
                "status": "generating",
                "evaluation": {},
                "session_id": session_id,
                "input_fingerprint": fingerprint,
                "request": copy.deepcopy(request),
            }
            if pending is not None:
                record_index, record = pending
                self.history[record_index] = record
            else:
                record_index = len(self.history)
                self.history.append(record)
                if persist is not None:
                    await persist(copy.deepcopy(self.history))
            started = time.monotonic()
            phase = "generation"
            try:
                async with asyncio.timeout(self.config.model_timeout_s):
                    if pending is not None:
                        response = record["response"]
                        pending = None
                    elif charge is None:
                        response = await invoke(self.generate_source, request)
                    else:
                        response = await charge(
                            "developer", self.generate_source, request, context=request
                        )
                record["response"] = response
                record["status"] = "generated"
                if persist is not None:
                    phase = "persist"
                    await persist(copy.deepcopy(self.history))
                phase = "parse"
                source, diagnosis, changes = _revision(response)
                evaluated_source = source
                record.update({"diagnosis": diagnosis, "changes": changes})
                source_limit = getattr(self.sandbox, "max_source_bytes", None)
                if source_limit is not None and len(source.encode()) > source_limit:
                    raise ValueError("Generated source exceeds the configured sandbox limit")
                artifact = PolicyArtifact(source, parent, copy.deepcopy(self.provenance))
                candidate = SourcePolicy(artifact, self.sandbox, self.config.policy_timeout_s)
                record["artifact"] = artifact.to_dict()
                parent = artifact.source_hash
                phase = "validation"
                if callable(getattr(self.sandbox, "validate", None)):
                    record.update(self.sandbox.validate(source))
                phase = "replay"
                measured = await evaluate(candidate)
                if [t.world_id for t in measured] != [t.world_id for t in trajectories]:
                    raise ConfigurationError("Candidate evaluation must cover the same world pool")
                feedback = self.feedback(measured)
                score = feedback["summary"]["mean_score"]
                record["evaluation"] = copy.deepcopy(feedback["summary"])
                record["status"] = "scored" if score is not None else "unscored"
                record["behavior_hash"] = hashlib.sha256(
                    json.dumps(
                        [
                            {
                                "world": t.world_id,
                                "steps": [(s.batch, s.revealed_nodes) for s in t.steps],
                            }
                            for t in measured
                        ],
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                record["duplicate_behavior"] = any(
                    item.get("behavior_hash") == record["behavior_hash"]
                    for item in self.history[:record_index]
                    if item.get("session_id") == session_id
                )
                feedback["comparison"] = {
                    "baseline": baseline,
                    "best_before": best_score,
                    "delta_vs_best": score - best_score
                    if score is not None and best_score is not None
                    else None,
                    "identical_decisions_to_prior_revision": record["duplicate_behavior"],
                    "quality_delta_vs_baseline": [
                        {
                            "world": actual.world_id,
                            "baseline_quality": original.best_score,
                            "candidate_quality": actual.best_score,
                            "baseline_probes": original.total_probes,
                            "candidate_probes": actual.total_probes,
                        }
                        for original, actual in zip(trajectories, measured, strict=True)
                    ],
                }
                if score is not None and (best_score is None or score > best_score):
                    best_score, best_source, best_hash = score, source, artifact.source_hash
                record["feedback"] = feedback
                if score is not None:
                    candidates.append(candidate)
                if self.config.recover_best and best_source is not None and score != best_score:
                    source, parent = best_source, best_hash
            except BudgetExceeded as exc:
                record.update(status="budget_exhausted", error=str(exc), phase=phase)
                self.history[record_index] = copy.deepcopy(record)
                if persist is not None:
                    await persist(self.history)
                break
            except Exception as exc:
                if phase == "persist":
                    raise
                record.update(status="failed", phase=phase, error=f"{type(exc).__name__}: {exc}")
                record["evaluation"] = {}
                feedback = {
                    **feedback,
                    "previous_summary": feedback.get("summary"),
                    "summary": {"all_worlds_scored": False, "mean_score": None},
                    "trajectories_are_previous_context": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "error_phase": phase,
                }
                record["feedback"] = copy.deepcopy(feedback)
            record["elapsed_s"] = time.monotonic() - started
            self.history[record_index] = copy.deepcopy(record)
            if persist is not None:
                await persist(self.history)
        return candidates
