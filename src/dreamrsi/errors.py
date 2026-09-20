# Dream-RSI SDK Errors
"""Exception hierarchy for the dreamrsi library.

All public exceptions inherit from DreamRSIError. User code should catch
specific subclasses rather than the base when fine-grained handling is needed.
"""

from __future__ import annotations


class DreamRSIError(Exception):
    """Base exception for all dreamrsi errors."""


class ConfigurationError(DreamRSIError):
    """Invalid or missing configuration."""


class AdapterError(DreamRSIError):
    """Error from an agent adapter."""


class EvaluationError(DreamRSIError):
    """Error during candidate evaluation."""


class ReplayError(DreamRSIError):
    """Error during replay execution."""


class MissingTransition(ReplayError):
    """Replay requested a transition that does not exist in the recorded tree.

    This is expected at replay boundaries — it means the policy tried to
    explore beyond what was recorded in the original online run.
    """

    def __init__(self, node_id: str, tree_id: str, message: str | None = None) -> None:
        self.node_id = node_id
        self.tree_id = tree_id
        msg = message or f"No recorded child for node {node_id!r} in tree {tree_id!r}"
        super().__init__(msg)


class PolicyError(DreamRSIError):
    """Error related to exploration policy execution or management."""


class SandboxError(DreamRSIError):
    """Error during sandboxed execution of generated policy code."""


class SandboxTimeoutError(SandboxError):
    """Sandboxed execution exceeded its time limit."""


class BudgetExceeded(DreamRSIError):
    """A budget constraint has been reached."""

    def __init__(self, constraint: str, limit: float, used: float) -> None:
        self.constraint = constraint
        self.limit = limit
        self.used = used
        super().__init__(f"Budget exceeded: {constraint} (limit={limit}, used={used})")


class StorageError(DreamRSIError):
    """Error from the storage backend."""


class PromotionError(DreamRSIError):
    """Error during policy promotion evaluation."""
