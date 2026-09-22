"""Compare inline and worker execution with an explicit JSON sandbox profile."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamrsi import PolicySandbox, ProcessPolicySandbox, SandboxConfig  # noqa: E402
from dreamrsi.models.policy import PolicyView  # noqa: E402

SOURCE = '''def decide(view):
    if len(view["frontier"]) == 0:
        return {"expand": [], "stop": True}
    return {"expand": [view["frontier"][0]["id"]]}
'''


async def main():
    profile = SandboxConfig(allowed_builtins=("len",), max_steps=10_000)
    restored = SandboxConfig.from_dict(json.loads(json.dumps(profile.to_dict())))
    for backend in (PolicySandbox, ProcessPolicySandbox):
        sandbox = backend(restored)
        started = time.perf_counter()
        result = await sandbox.execute(SOURCE, PolicyView([], None, 0, 0, 0, 0))
        print(f"{backend.__name__}: {result.to_dict()}, {time.perf_counter() - started:.4f}s")
    print("Active profile:", json.dumps(profile.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
