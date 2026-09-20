"""Discovery tree — the central data structure of Dream-RSI.

A discovery tree records every exploration decision an agent made during
one online rollout.  Each node is one generation→evaluation attempt.
The tree is later converted into a replay world for cheap offline
evaluation of alternative exploration policies.
"""

from __future__ import annotations

import copy
import math
import uuid
from collections.abc import Iterator
from typing import Any

from dreamrsi.errors import DreamRSIError
from dreamrsi.models.discovery import DiscoveryNode, NodeStatus


class TreeError(DreamRSIError):
    """Error related to discovery tree operations."""


class DiscoveryTree:
    """An in-memory discovery tree.

    Invariants enforced:
    - Each node has at most one parent.
    - The root has no parent.
    - A node belongs to exactly one tree.
    - Once committed, recorded nodes cannot be modified.
    - Write operations are transactional (complete or raise).
    """

    def __init__(self, tree_id: str | None = None) -> None:
        self.tree_id = tree_id or str(uuid.uuid4())
        self._nodes: dict[str, DiscoveryNode] = {}
        self._root_id: str | None = None
        self._committed = False
        self._next_order = 0

    # ── Properties ──────────────────────────────────────────────

    @property
    def root_id(self) -> str | None:
        return self._root_id

    @property
    def root(self) -> DiscoveryNode | None:
        if self._root_id is None:
            return None
        return self.get_node(self._root_id)

    @property
    def is_committed(self) -> bool:
        return self._committed

    @property
    def size(self) -> int:
        """Total number of nodes including root."""
        return len(self._nodes)

    @property
    def non_root_size(self) -> int:
        """Number of non-root nodes (= number of generation attempts)."""
        return max(0, len(self._nodes) - (1 if self._root_id else 0))

    # ── Core operations ────────────────────────────────────────

    def create_root(
        self,
        state: Any = None,
        node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DiscoveryNode:
        """Create and register the root node.  Must be called exactly once."""
        if self._committed:
            raise TreeError("Cannot modify a committed tree")
        if self._root_id is not None:
            raise TreeError("Root already exists")

        node = DiscoveryNode(
            id=node_id or str(uuid.uuid4()),
            tree_id=self.tree_id,
            parent_id=None,
            depth=0,
            state=state,
            status=NodeStatus.COMPLETED,
            creation_order=self._next_order,
            metadata=metadata or {},
        )
        self._next_order += 1
        self._nodes[node.id] = node
        self._root_id = node.id
        return node

    def add_node(
        self,
        parent_id: str,
        *,
        node_id: str | None = None,
        state: Any = None,
        proposal: Any = None,
        action: Any = None,
        observation: Any = None,
        score: float | None = None,
        status: NodeStatus = NodeStatus.COMPLETED,
        cost: float = 0.0,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> DiscoveryNode:
        """Add a child node to a parent.  Returns the new node."""
        if self._committed:
            raise TreeError("Cannot modify a committed tree")
        if parent_id not in self._nodes:
            raise TreeError(f"Parent node {parent_id!r} not found in tree")

        parent = self._nodes[parent_id]
        if not parent.is_root and parent.children_ids:
            raise TreeError("A non-root node can only be extended once")
        if score is not None and not math.isfinite(score):
            raise TreeError("Node score must be finite")
        nid = node_id or str(uuid.uuid4())

        if nid in self._nodes:
            raise TreeError(f"Node {nid!r} already exists in tree")

        node = DiscoveryNode(
            id=nid,
            tree_id=self.tree_id,
            parent_id=parent_id,
            depth=parent.depth + 1,
            state=state,
            proposal=proposal,
            action=action,
            observation=observation,
            score=score,
            status=status,
            cost=cost,
            latency_ms=latency_ms,
            creation_order=self._next_order,
            metadata=metadata or {},
        )
        self._next_order += 1
        parent.children_ids.append(nid)
        self._nodes[nid] = node
        return node

    def commit(self) -> None:
        """Make the tree immutable.  After this, no nodes can be added or modified."""
        if self._root_id is None:
            raise TreeError("Cannot commit a tree without a root")
        self._nodes = copy.deepcopy(self._nodes)
        self._committed = True

    # ── Query operations ───────────────────────────────────────

    def get_node(self, node_id: str) -> DiscoveryNode | None:
        node = self._nodes.get(node_id)
        return copy.deepcopy(node) if self._committed else node

    def get_children(self, node_id: str) -> list[DiscoveryNode]:
        """Return direct children of a node, ordered by creation_order."""
        node = self._nodes.get(node_id)
        if node is None:
            return []
        children = [self._nodes[cid] for cid in node.children_ids if cid in self._nodes]
        children.sort(key=lambda n: n.creation_order)
        return copy.deepcopy(children) if self._committed else children

    def get_leaves(self) -> list[DiscoveryNode]:
        """Return all leaf nodes (no children)."""
        return [
            copy.deepcopy(n) if self._committed else n
            for n in self._nodes.values()
            if n.is_leaf and not n.is_root
        ]

    def get_eligible(self) -> list[DiscoveryNode]:
        """Return nodes eligible for expansion: root + all leaves.

        This implements A(T) = {r} ∪ {v ∈ T : v is a leaf} from the paper.
        """
        result: list[DiscoveryNode] = []
        for node in self._nodes.values():
            if node.is_root or node.is_leaf:
                result.append(copy.deepcopy(node) if self._committed else node)
        return result

    def get_path_to_root(self, node_id: str) -> list[DiscoveryNode]:
        """Return the path from a node to the root (inclusive, node-first)."""
        path: list[DiscoveryNode] = []
        current = self._nodes.get(node_id)
        visited: set[str] = set()
        while current is not None:
            if current.id in visited:
                raise TreeError(f"Cycle detected at node {current.id!r}")
            visited.add(current.id)
            path.append(copy.deepcopy(current) if self._committed else current)
            if current.parent_id is None:
                break
            current = self._nodes.get(current.parent_id)
        return path

    def get_best_node(self) -> DiscoveryNode | None:
        """Return the node with the highest score, or None if no scored nodes."""
        best: DiscoveryNode | None = None
        for node in self._nodes.values():
            if node.score is not None and (
                best is None or (best.score is not None and node.score > best.score)
            ):
                best = node
        return copy.deepcopy(best) if self._committed else best

    def get_best_score(self) -> float | None:
        """Return the best score in the tree."""
        best = self.get_best_node()
        return best.score if best else None

    def get_max_depth(self) -> int:
        """Return the maximum depth in the tree."""
        if not self._nodes:
            return 0
        return max(n.depth for n in self._nodes.values())

    def get_root_children(self) -> list[DiscoveryNode]:
        """Return children of root, ordered by creation_order (= branches)."""
        if self._root_id is None:
            return []
        return self.get_children(self._root_id)

    def iter_nodes(self) -> Iterator[DiscoveryNode]:
        """Iterate all nodes in creation order."""
        nodes = sorted(self._nodes.values(), key=lambda n: n.creation_order)
        yield from (copy.deepcopy(nodes) if self._committed else nodes)

    def iter_nodes_bfs(self) -> Iterator[DiscoveryNode]:
        """Iterate nodes in breadth-first order starting from root."""
        if self._root_id is None:
            return
        queue = [self._root_id]
        visited: set[str] = set()
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            node = self._nodes.get(nid)
            if node is None:
                continue
            yield copy.deepcopy(node) if self._committed else node
            for cid in node.children_ids:
                if cid not in visited:
                    queue.append(cid)

    def total_cost(self) -> float:
        """Sum of all node costs."""
        return sum(n.cost for n in self._nodes.values())

    # ── Subtree extraction ─────────────────────────────────────

    def subtree_node_ids(self, node_id: str) -> set[str]:
        """Return all node IDs in the subtree rooted at node_id (inclusive)."""
        result: set[str] = set()
        stack = [node_id]
        while stack:
            nid = stack.pop()
            if nid in result:
                continue
            result.add(nid)
            node = self._nodes.get(nid)
            if node is not None:
                stack.extend(node.children_ids)
        return result

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "tree_id": self.tree_id,
            "root_id": self._root_id,
            "committed": self._committed,
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "_schema_version": "1",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryTree:
        tree = cls(tree_id=data["tree_id"])
        tree._committed = data.get("committed", False)
        tree._root_id = data.get("root_id")
        for nid, ndata in data.get("nodes", {}).items():
            tree._nodes[nid] = DiscoveryNode.from_dict(ndata)
        if tree._nodes:
            tree._next_order = max(n.creation_order for n in tree._nodes.values()) + 1
        roots = [n for n in tree._nodes.values() if n.parent_id is None]
        if len(roots) != 1 or roots[0].id != tree.root_id or roots[0].depth != 0:
            raise TreeError("Serialized tree must have exactly one valid root")
        for nid, node in tree._nodes.items():
            if node.id != nid or node.tree_id != tree.tree_id:
                raise TreeError("Node identity does not match serialized tree")
            if node.score is not None and not math.isfinite(node.score):
                raise TreeError("Node score must be finite")
            if len(set(node.children_ids)) != len(node.children_ids):
                raise TreeError("Duplicate children")
            if node.parent_id is not None:
                parent = tree._nodes.get(node.parent_id)
                if (
                    parent is None
                    or nid not in parent.children_ids
                    or node.depth != parent.depth + 1
                ):
                    raise TreeError("Invalid parent/depth relationship")
                if len(node.children_ids) > 1:
                    raise TreeError("Non-root branches must be linear")
            for cid in node.children_ids:
                if cid not in tree._nodes or tree._nodes[cid].parent_id != nid:
                    raise TreeError("Invalid child relationship")
        return tree

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes

    def __repr__(self) -> str:
        return (
            f"DiscoveryTree(id={self.tree_id!r}, "
            f"nodes={len(self._nodes)}, "
            f"committed={self._committed})"
        )


__all__ = ["NodeStatus", "DiscoveryNode", "DiscoveryTree", "TreeError"]
