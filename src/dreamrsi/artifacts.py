"""Portable, integrity-checked policy source; loading never executes code."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from dreamrsi.errors import PolicyError


@dataclass(frozen=True)
class PolicyArtifact:
    source: str
    parent_hash: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1 or not isinstance(self.source, str):
            raise PolicyError("Unsupported policy artifact")

    @property
    def source_hash(self):
        return hashlib.sha256(self.source.encode()).hexdigest()

    def to_dict(self):
        return {**asdict(self), "source_hash": self.source_hash}

    @classmethod
    def from_dict(cls, data):
        values = dict(data)
        digest = values.pop("source_hash")
        artifact = cls(**values)
        if artifact.source_hash != digest:
            raise PolicyError("Policy source integrity mismatch")
        return artifact


class SourcePolicy:
    """Stateless decide(view-dict) source evaluated only by an explicit sandbox."""

    def __init__(self, artifact: PolicyArtifact, sandbox, timeout_s: float = 5):
        self.artifact = artifact
        self.sandbox = sandbox
        self.timeout_s = timeout_s

    def __deepcopy__(self, memo):
        # Executor is infrastructure; each decision runs in a fresh isolation boundary.
        return SourcePolicy(
            PolicyArtifact.from_dict(self.artifact.to_dict()), self.sandbox, self.timeout_s
        )

    async def decide(self, view):
        return await self.sandbox.execute(self.artifact.source, view, self.timeout_s)


class PolicyCodec:
    """Explicit allowlist for portable policies. Register custom policy codecs."""

    def __init__(self, sandbox=None):
        from dreamrsi.sandbox import PolicySandbox

        self.sandbox = sandbox if sandbox is not None else PolicySandbox()
        self.custom = {}

    def register(self, name, policy_type, encode, decode):
        if name in self.custom:
            raise ValueError("Codec already registered")
        self.custom[name] = (policy_type, encode, decode)

    def encode(self, policy):
        import random

        from dreamrsi import policies

        if isinstance(policy, SourcePolicy):
            return {
                "kind": "source",
                "artifact": policy.artifact.to_dict(),
                "timeout_s": policy.timeout_s,
                "sandbox": policy.sandbox.capabilities()
                if hasattr(policy.sandbox, "capabilities")
                else None,
            }
        for name, (kind, encode, _) in self.custom.items():
            if type(policy) is kind:
                return {"kind": "custom", "name": name, "state": encode(policy)}
        allowed = {getattr(policies, name) for name in policies.__all__}
        if type(policy) not in allowed:
            raise PolicyError("Register a codec before checkpointing a custom policy")
        state = {}
        for key, value in vars(policy).items():
            state[key] = (
                {"random_state": value.getstate()} if isinstance(value, random.Random) else value
            )
        return {"kind": "builtin", "name": type(policy).__name__, "state": state}

    def decode(self, data):
        import random

        from dreamrsi import policies

        if data["kind"] == "source":
            capabilities = (
                self.sandbox.capabilities() if hasattr(self.sandbox, "capabilities") else None
            )
            if data.get("sandbox") != capabilities:
                raise PolicyError("Source policy requires the same sandbox profile")
            return SourcePolicy(
                PolicyArtifact.from_dict(data["artifact"]), self.sandbox, data.get("timeout_s", 5)
            )
        if data["kind"] == "custom":
            return self.custom[data["name"]][2](data["state"])
        if data["kind"] != "builtin" or data["name"] not in policies.__all__:
            raise PolicyError("Unknown policy codec")
        policy = getattr(policies, data["name"])()
        if set(data["state"]) != set(vars(policy)):
            raise PolicyError("Invalid built-in policy state")

        def tuples(value):
            return tuple(tuples(v) for v in value) if isinstance(value, list) else value

        for key, value in data["state"].items():
            if key == "_rng":
                rng = random.Random()
                rng.setstate(tuples(value["random_state"]))
                value = rng
            setattr(policy, key, value)
        return policy
