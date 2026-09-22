"""Conservative Appendix B signals; classification is evidence, not automatic closure."""

from __future__ import annotations


def successful(obs):
    return obs.evaluated and obs.error is None and obs.fail_class == "ok"


def branch_promising(obs):
    return successful(obs) and (probe_improved_vs_parent(obs) or probe_improved_vs_baseline(obs))


def branch_failed_hard(obs):
    return not successful(obs) and obs.fail_class in {
        "environment",
        "dependency",
        "environment_unavailable",
        "dependency_unavailable",
        "hard_unrecoverable",
    }


def probe_improved_vs_parent(obs):
    return successful(obs) and obs.delta_vs_parent is not None and obs.delta_vs_parent > 0


def probe_improved_vs_baseline(obs):
    return successful(obs) and obs.delta_vs_baseline is not None and obs.delta_vs_baseline > 0


def trajectory_signal(trajectory):
    """Keep successful anchors across repairable episodes; later success reopens a branch."""
    ordered = sorted(trajectory, key=lambda obs: obs.attempt)
    anchors = [obs.score for obs in ordered if successful(obs) and obs.score is not None]
    failure_run = []
    for obs in reversed(ordered):
        if successful(obs):
            break
        failure_run.append(obs)
    hard = len(failure_run) >= 2 and all(branch_failed_hard(obs) for obs in failure_run)
    return {
        "anchor": max(anchors) if anchors else None,
        "successful_count": len(anchors),
        "gain": anchors[-1] - anchors[-2] if len(anchors) > 1 else None,
        "failure_run": len(failure_run),
        "hard_unrecoverable": hard,
        "repairable": bool(failure_run) and not hard,
        "attempts": len(ordered),
    }
