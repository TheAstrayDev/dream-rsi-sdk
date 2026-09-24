"""Shared online/replay policy lifecycle and action validation."""

from __future__ import annotations

import copy

from dreamrsi.errors import PolicyError


def fresh_policy(policy):
    """A prototype never receives per-rollout mutations."""
    try:
        return copy.deepcopy(policy)
    except Exception as exc:
        raise PolicyError("Policy must support deepcopy for isolated rollouts") from exc


def validate_batch(decision, view, max_parallelism):
    if decision.stop:
        return []
    batch = list(decision.expand)
    eligible = {node.id for node in view.frontier}
    if any(not isinstance(nid, str) or nid not in eligible for nid in batch):
        raise PolicyError(
            "Policy selected a node outside the observed frontier; return an ID "
            "from the current view['frontier'], never a literal root ID"
        )
    if len(set(batch)) != len(batch):
        raise PolicyError("Policy batch contains duplicate node IDs")
    workers = decision.parallelism
    if workers is not None:
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise PolicyError("Decision parallelism must be a positive integer")
        max_parallelism = min(max_parallelism, workers)
    return batch[:max_parallelism]
