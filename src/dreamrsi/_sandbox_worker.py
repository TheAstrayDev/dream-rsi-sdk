"""Private JSON-only entrypoint for one isolated interpreter decision."""

import asyncio
import json
import sys

from dreamrsi.models.policy import PolicyView
from dreamrsi.sandbox import PolicySandbox, SandboxConfig


def main():
    try:
        request = json.load(sys.stdin)
        sandbox = PolicySandbox(SandboxConfig.from_dict(request["config"]))
        decision = asyncio.run(
            sandbox.execute(
                request["code"],
                PolicyView.from_dict(request["view"]),
                request["timeout_s"],
            )
        )
        response = {"decision": decision.to_dict()}
    except Exception as exc:
        response = {"error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(response, allow_nan=False))


if __name__ == "__main__":
    main()
