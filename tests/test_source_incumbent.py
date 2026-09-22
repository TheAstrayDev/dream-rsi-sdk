import importlib.util
from pathlib import Path

import pytest

from dreamrsi import PolicyArtifact, PolicySandbox, SourcePolicy
from dreamrsi.models.discovery import NodeStatus
from dreamrsi.models.policy import NodeSummary, PolicyView
from dreamrsi.policies import BalancedPolicy


@pytest.mark.parametrize(
    "scores", [[], [None], [None, -4, -2, -1], [None, 0, 0, 0, 0, 0], [None, 3, 1, 8, -2]]
)
async def test_source_incumbent_matches_builtin_on_null_negative_and_tied_scores(scores):
    path = Path(__file__).resolve().parents[1] / "examples" / "balanced_source.py"
    spec = importlib.util.spec_from_file_location("balanced_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frontier = [
        NodeSummary(str(i), None if i == 0 else "0", i, score, NodeStatus.COMPLETED, i % 3)
        for i, score in enumerate(scores)
    ]
    view = PolicyView(
        frontier,
        max((s for s in scores if s is not None), default=None),
        len(scores),
        len(scores),
        0,
        1,
    )
    source = SourcePolicy(PolicyArtifact(module.BALANCED_SOURCE), PolicySandbox())
    assert await source.decide(view) == await BalancedPolicy().decide(view)
