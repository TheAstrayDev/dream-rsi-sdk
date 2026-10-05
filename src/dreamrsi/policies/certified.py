"""Stop an unchanged policy only when its evaluator proves optimal quality."""

from dreamrsi._invoke import invoke
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.quality import quality_certificate


class CertifiedPolicy:
    """Keep complete incumbent batches; missing certificates retain its search.

    The bound and measured quality must come from a matching QualityContract.
    Training plateaus are not certificates. No model call is made by this policy.
    """

    def __init__(self, policy, contract_id: str):
        if not callable(getattr(policy, "decide", None)):
            raise ValueError("policy must implement decide")
        if not isinstance(contract_id, str) or not contract_id.strip():
            raise ValueError("contract_id must be a nonempty string")
        self.policy = policy
        self.contract_id = contract_id

    async def decide(self, view):
        if quality_certificate(view.observations, self.contract_id):
            return PolicyDecision(expand=[], stop=True)
        return await invoke(self.policy.decide, view)
