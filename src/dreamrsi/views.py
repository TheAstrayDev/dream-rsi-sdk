"""The same prefix-visible information for online and replay policies."""

import copy

from dreamrsi.models.policy import NodeSummary


def revealed_context(tree, revealed):
    history, observations = [], {}
    for node in tree.iter_nodes():
        if node.id not in revealed:
            continue
        history.append(
            NodeSummary(
                node.id,
                node.parent_id,
                node.depth,
                node.score,
                node.status,
                sum(child in revealed for child in node.children_ids),
            )
        )
        observations[node.id] = copy.deepcopy(
            {
                "observation": node.observation,
                "diagnostics": node.metadata,
                "score": node.score,
                "status": node.status.value,
                "parent_id": node.parent_id,
                "depth": node.depth,
            }
        )
    return {"history": history, "observations": observations}
