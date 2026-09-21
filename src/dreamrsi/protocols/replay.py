from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from dreamrsi.models.replay import ReplayTrajectory
from dreamrsi.replay import ReplayWorld


@runtime_checkable
class ReplayEngine(Protocol):
    """Offline engine; implementations must declare any changed replay semantics."""

    async def replay(
        self, world: ReplayWorld, policy: Any, policy_id: str = "",
    ) -> ReplayTrajectory: ...
