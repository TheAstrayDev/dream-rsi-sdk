"""Small, honest run reports. A run alone is not an all-in ROI experiment."""

from __future__ import annotations

from typing import Any


def run_report(result: Any) -> str:
    nodes = list(result.tree.iter_nodes()) if result.tree is not None else []
    agents = [node.metadata.get("usage", {}).get("agent") for node in nodes if not node.is_root]
    measured = [
        record
        for node in nodes
        for stage, record in node.metadata.get("usage", {}).items()
        if stage == "agent"
        or record.get("provider_calls", 0) > 0
        or record.get("input_tokens", 0) + record.get("output_tokens", 0) > 0
        or record.get("usd", 0) > 0
    ]
    known = (
        len(agents) == result.costs.model_calls
        and all(agents)
        and result.costs.developer_calls == 0
        and bool(measured)
        and all(record and not record.get("estimated", True) for record in measured)
    )
    tokens_known = known and all(
        record["input_tokens"] + record["output_tokens"] > 0 for record in measured
    )
    usd_known = known and all(record["usd"] > 0 for record in measured)
    return "\n".join(
        [
            f"Dream-RSI run {result.run_id}",
            f"Best evaluator score: {result.best_score}",
            f"Raw quality: {result.metrics.get('raw_quality', 'unknown')}",
            f"Agent dispatches: {result.costs.model_calls}",
            f"Evaluator dispatches: {result.costs.evaluator_calls}",
            f"Reported provider calls: {result.costs.provider_calls}",
            (
                f"Reported tokens: {result.costs.input_tokens + result.costs.output_tokens}"
                if tokens_known
                else "Tokens: unknown"
            ),
            f"Reported USD: {result.costs.total:.6f}" if usd_known else "USD: unknown",
            f"Stop: {result.metrics.get('stop_reason', 'unknown')}",
            "Scope: this run only; baseline quality and all-in ROI are not established.",
        ]
    )
