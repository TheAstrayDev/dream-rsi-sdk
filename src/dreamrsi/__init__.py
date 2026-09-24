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

from dreamrsi.accounting import Usage, UsageLedger
from dreamrsi.adapters import CallableAgentAdapter, FunctionalAgentAdapter
from dreamrsi.artifacts import PolicyArtifact, PolicyCodec, SourcePolicy
from dreamrsi.developer import DeveloperConfig, LLMPolicyDeveloper
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
from dreamrsi.llamacpp import LlamaCppPolicyModel
from dreamrsi.methods import DefaultMethod
from dreamrsi.ollama import OllamaPolicyModel
from dreamrsi.policy_memory import AdaptivePolicyMemory, AdaptiveRun, PolicyMemorySettings
from dreamrsi.process_sandbox import ProcessPolicySandbox
from dreamrsi.runtime import (
    Budget,
    CampaignResult,
    CostRecord,
    DreamRSI,
    DreamRSIConfig,
    RunResult,
)
from dreamrsi.sandbox import PolicySandbox, SandboxConfig
from dreamrsi.storage import SQLiteStore
from dreamrsi.validation import HoldoutPipeline, split_tasks

__version__ = "0.2.0a1"

__all__ = [
    "Usage",
    "UsageLedger",
    "PolicyArtifact",
    "PolicyCodec",
    "SourcePolicy",
    "LLMPolicyDeveloper",
    "DeveloperConfig",
    "OllamaPolicyModel",
    "LlamaCppPolicyModel",
    "PolicySandbox",
    "SandboxConfig",
    "ProcessPolicySandbox",
    "HoldoutPipeline",
    "split_tasks",
    "SQLiteStore",
    "AdaptivePolicyMemory",
    "PolicyMemorySettings",
    "AdaptiveRun",
    "CallableAgentAdapter",
    "FunctionalAgentAdapter",
    # Core
    "DreamRSI",
    "DefaultMethod",
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
