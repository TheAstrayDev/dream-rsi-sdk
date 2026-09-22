"""SQLite store with atomic JSON checkpoints; no executable deserialization."""

from __future__ import annotations

import json
import sqlite3
import uuid

from dreamrsi.discovery import DiscoveryNode
from dreamrsi.events import Event, EventType
from dreamrsi.models.base import Run
from dreamrsi.models.policy import PolicyDeploymentStatus, PolicyVersion


class SQLiteStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS records "
            "(kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id))"
        )
        self.connection.commit()

    def _save(self, kind, key, value):
        payload = json.dumps(value, allow_nan=False, ensure_ascii=False)
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO records VALUES (?,?,?)", (kind, key, payload)
            )

    def _get(self, kind, key):
        row = self.connection.execute(
            "SELECT data FROM records WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _all(self, kind):
        return [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,)
            )
        ]

    async def save_run(self, run):
        self._save("run", run.id, run.to_dict())

    async def get_run(self, run_id):
        data = self._get("run", run_id)
        return Run.from_dict(data) if data else None

    async def save_node(self, node):
        self._save("node", node.id, node.to_dict())

    async def get_node(self, node_id):
        data = self._get("node", node_id)
        return DiscoveryNode.from_dict(data) if data else None

    async def get_nodes_by_tree(self, tree_id):
        nodes = [DiscoveryNode.from_dict(n) for n in self._all("node") if n["tree_id"] == tree_id]
        return sorted(nodes, key=lambda node: node.creation_order)

    async def save_policy(self, policy):
        self._save("policy", policy.id, policy.to_dict())

    async def get_policy(self, policy_id):
        data = self._get("policy", policy_id)
        return PolicyVersion.from_dict(data) if data else None

    async def list_policies(self):
        return sorted(
            [PolicyVersion.from_dict(p) for p in self._all("policy")], key=lambda p: p.created_at
        )

    async def get_champion(self):
        return next(
            (
                p
                for p in reversed(await self.list_policies())
                if p.deployment_status == PolicyDeploymentStatus.CHAMPION
            ),
            None,
        )

    async def save_event(self, event):
        self._save("event", uuid.uuid4().hex, event.to_dict())

    async def get_events(self, run_id=None, limit=100):
        events = [
            Event(**{**e, "type": EventType(e["type"])})
            for e in self._all("event")
            if run_id is None or e["run_id"] == run_id
        ]
        return events[-limit:] if limit > 0 else []

    async def save_evaluation(self, evaluation):
        self._save("evaluation", evaluation.id, evaluation.to_dict())

    async def save_checkpoint(self, campaign_id, data):
        self._save("checkpoint", campaign_id, data)

    async def get_checkpoint(self, campaign_id):
        return self._get("checkpoint", campaign_id)

    async def close(self):
        self.connection.close()
