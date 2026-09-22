"""Optional killable worker for the same bounded policy interpreter, without Docker."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

from dreamrsi.errors import SandboxError
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.sandbox import PolicySandbox


class ProcessPolicySandbox(PolicySandbox):
    """Start a fresh worker per decision; timeout includes worker startup.

    Keeps interpreter work off the caller's event loop and terminates the worker
    on timeout/cancellation. It does not grant arbitrary Python execution or
    provide an OS filesystem/network/memory security boundary.
    """

    def capabilities(self):
        return {**super().capabilities(), "execution": "fresh_process"}

    async def execute(self, code, policy_view, timeout_s=5.0):
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise SandboxError("A positive finite timeout is required")
        if type(code) is not str or len(code.encode()) > self.config.max_source_bytes:
            raise SandboxError("Policy source limit exceeded")
        payload = json.dumps(
            {
                "code": code,
                "view": policy_view.to_dict(),
                "config": self.config.to_dict(),
                "timeout_s": timeout_s,
            },
            allow_nan=False,
        ).encode()
        # -I prevents PYTHONPATH/user-site injection; load this exact SDK installation.
        bootstrap = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from dreamrsi._sandbox_worker import main; main()"
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            bootstrap,
            str(Path(__file__).resolve().parent.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            async with asyncio.timeout(timeout_s):
                stdout, stderr = await process.communicate(payload)
            if process.returncode != 0:
                raise SandboxError(
                    f"Policy worker exited with code {process.returncode}: "
                    f"{stderr.decode(errors='replace')[:1000]}"
                )
            result = json.loads(stdout)
            if "error" in result:
                raise SandboxError(result["error"])
            return PolicyDecision.from_dict(result["decision"])
        except TimeoutError as exc:
            raise SandboxError("Policy worker wall-time limit exceeded") from exc
        finally:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            # Drain pipes as well as reaping; wait() alone can stall on buffered output.
            await process.communicate()
