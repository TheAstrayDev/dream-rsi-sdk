"""Dream-RSI SDK — Embeddable recursive self-improvement for AI agents.

Independent alpha implementation inspired by Dream-RSI (Zheng et al., 2026, arXiv:2609.14858):
a framework for recursively improving exploration policies using recorded
discovery trees as replay simulators.

Quickstart::

    from dreamrsi import DreamRSI

    # Simple mode — just a callable + evaluator
    rsi = DreamRSI(agent=my_agent, evaluator=my_evaluator)
    result = await rsi.run(task)

    # Full Dream-RSI loop with recursive improvement
    result = await rsi.improve(task, rounds=5)

    # Synchronous
    result = rsi.run_sync(task)

Paper: https://arxiv.org/abs/2609.14858
SDK: https://github.com/TheAstrayDev/dream-rsi-sdk
Research project: https://dream-rsi.com
Not affiliated with Google or Google DeepMind.
"""

from __future__ import annotations

from dreamrsi.adapters import CallableAgentAdapter, FunctionalAgentAdapter
from dreamrsi.errors import (
    BudgetExceeded,
    ConfigurationError,
    DreamRSIError,
    EvaluationError,
    MissingTransition,
    PolicyError,
    PromotionError,
    ReplayError,
    SandboxError,
    StorageError,
)
from dreamrsi.runtime import (
    Budget,
    CampaignResult,
    CostRecord,
    DreamRSI,
    DreamRSIConfig,
    RunResult,
)

__version__ = "0.1.0a1"

__all__ = [
    "CallableAgentAdapter",
    "FunctionalAgentAdapter",
    # Core
    "DreamRSI",
    "DreamRSIConfig",
    "Budget",
    "RunResult",
    "CampaignResult",
    "CostRecord",
    # Errors
    "DreamRSIError",
    "ConfigurationError",
    "EvaluationError",
    "ReplayError",
    "MissingTransition",
    "PolicyError",
    "BudgetExceeded",
    "StorageError",
    "PromotionError",
    "SandboxError",
]
