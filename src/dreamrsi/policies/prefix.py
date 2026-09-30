"""Compose a policy with a fixed stopping round; preserve complete prior batches."""

from dreamrsi._invoke import invoke
from dreamrsi.models.policy import PolicyDecision, PolicyView


class PrefixPolicy:
    """Delegate unchanged until ``max_rounds`` complete rounds, then stop.

    A replay-derived cap preserves quality on the checked history only.
    Independent validation is still required to assess transfer to new tasks.
    The runtime isolates the nested policy's state for every rollout.
    """

    def __init__(self, policy, max_rounds: int):
        if not callable(getattr(policy, "decide", None)):
            raise ValueError("policy must implement decide(view)")
        if type(max_rounds) is not int or max_rounds < 0:
            raise ValueError("max_rounds must be a nonnegative integer")
        self.policy = policy
        self.max_rounds = max_rounds

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if view.rounds_used >= self.max_rounds:
            return PolicyDecision(expand=[], stop=True)
        return await invoke(self.policy.decide, view)
