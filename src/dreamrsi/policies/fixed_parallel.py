"""Fixed parallel policy for Dream-RSI."""

from dreamrsi.replay import PolicyDecision, PolicyView


class FixedParallelPolicy:
    """Opens a fixed number of branches from root, then refines each to a fixed depth."""

    def __init__(self, branches: int = 4, max_depth: int = 5):
        self._branches = branches
        self._max_depth = max_depth

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        root_nodes = [n for n in view.frontier if n.depth == 0]
        non_root_nodes = [n for n in view.frontier if 0 < n.depth < self._max_depth]

        to_expand = []

        # Phase 2: Refine existing branches first (depth first like)
        # Sort non-root nodes by depth descending to reach max_depth quickly
        non_root_nodes.sort(key=lambda n: n.depth, reverse=True)

        # Add non-root nodes up to `branches` limit
        for n in non_root_nodes:
            if len(to_expand) < self._branches:
                to_expand.append(n.id)

        # Phase 1: Open more branches from root if we have capacity
        if (
            len(to_expand) < self._branches
            and root_nodes
            and root_nodes[0].children_count < self._branches
        ):
            to_expand.append(root_nodes[0].id)

        if not to_expand:
            return PolicyDecision(expand=[], stop=True)

        return PolicyDecision(expand=to_expand, stop=False)
