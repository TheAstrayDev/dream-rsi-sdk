"""Standard-library smoke gate: run with an installed wheel's Python using -I.

CI invokes this file outside the checkout, in a fresh virtual environment.
It deliberately has no pytest dependency and does not accept editable imports.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import site
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path


async def check_installed_wheel() -> None:
    import dreamrsi
    from dreamrsi import (
        Budget,
        DreamRSI,
        EconomyPlan,
        LiveInspector,
        PolicyArtifact,
        PolicyCodec,
        PolicySandbox,
        ProcessPolicySandbox,
        QualityContract,
        SandboxConfig,
        SourcePolicy,
    )
    from dreamrsi.models.discovery import NodeStatus
    from dreamrsi.models.policy import NodeSummary, PolicyView
    from dreamrsi.policies import CertifiedPolicy, PrefixPolicy
    from dreamrsi.protocols import PolicyDeveloper

    assert sys.flags.isolated, "Run this gate with python -I"
    checkout = Path(__file__).resolve().parents[1]
    installed = Path(dreamrsi.__file__).resolve()
    assert not installed.is_relative_to(checkout), "SDK was imported from the checkout"
    assert any(
        installed.is_relative_to(Path(directory).resolve())
        for directory in site.getsitepackages()
    ), "SDK must load from the virtual environment's site-packages"
    distribution = metadata.distribution("dreamrsi")
    assert distribution.version == dreamrsi.__version__, "Wheel and SDK versions differ"
    direct_url = distribution.read_text("direct_url.json")
    if direct_url:
        assert not json.loads(direct_url).get("dir_info", {}).get("editable", False)
    assert any(
        point.group == "console_scripts"
        and point.name == "dreamrsi"
        and point.value == "dreamrsi.cli:main"
        for point in distribution.entry_points
    )
    assert isinstance(dreamrsi.LLMPolicyDeveloper(lambda request: ""), PolicyDeveloper)

    from urllib.request import urlopen

    from dreamrsi.inspector import InspectorServer

    with (
        tempfile.TemporaryDirectory() as directory,
        LiveInspector(Path(directory) / "journal.sqlite3") as inspector,
    ):
        runtime = DreamRSI(agent=lambda task: task, evaluator=float,
                           budget=Budget(model_calls=1), inspector=inspector)
        observed = await runtime.run(1)
        assert "Agent dispatches: 1" in observed.report()
        assert inspector.flush()
        with InspectorServer(inspector.path) as server:
            with urlopen(server.url + "/api/state", timeout=3) as response:
                assert json.load(response)["selected_run"] == observed.run_id
            for name in ("app.js", "style.css", ""):
                with urlopen(server.url + "/" + name, timeout=3) as response:
                    assert response.status == 200 and response.read()

    with tempfile.TemporaryDirectory() as directory:
        profile = SandboxConfig.preset("small", max_steps=100_000)
        path = profile.save(Path(directory) / "sandbox.json")
        assert path.is_absolute() and SandboxConfig.load(path) == profile
        worker = ProcessPolicySandbox.from_file(path)
        inline = PolicySandbox.from_file(path, cache_size=2)
    source = PolicyArtifact(
        'def decide(view):\n'
        '    return {"expand": [view["frontier"][0]["id"]], "stop": False}'
    )
    policy = PrefixPolicy(PrefixPolicy(SourcePolicy(source, worker), 3), 2)
    codec = PolicyCodec(worker)
    encoded = json.loads(json.dumps(codec.encode(policy)))
    restored = codec.decode(encoded)
    assert codec.encode(restored) == encoded, "Recursive policy codec did not round-trip"
    view = PolicyView(
        frontier=[NodeSummary("root", None, 0, None, NodeStatus.COMPLETED, 0)],
        best_score=None,
        total_nodes=1,
        calls_used=0,
        cost_used=0,
        rounds_used=0,
    )
    decision = await restored.decide(view)
    assert decision.expand == ["root"] and not decision.stop
    for _ in range(2):
        assert (await inline.execute(source.source, view)).expand == ["root"]
    assert inline.cache_info()["entries"] == 1 and inline.cache_info()["hits"] == 1
    inline.clear_cache()
    assert inline.cache_info()["entries"] == 0
    assert (await restored.decide(dataclasses.replace(view, rounds_used=2))).stop

    contract = QualityContract(id="installed-wheel-quality-v1", upper_bound=1.0)
    assert contract.preserve_policy, "QualityContract must preserve policy by default"
    certified = CertifiedPolicy(restored, contract.id)
    certified_data = json.loads(json.dumps(codec.encode(certified)))
    loaded = codec.decode(certified_data)
    assert codec.encode(loaded) == certified_data
    # No certificate: delegation must still launch the installed worker.
    assert (await loaded.decide(view)).expand == ["root"]
    optimal_record = {
        "depth": 0,
        "score": 1.0,
        "status": NodeStatus.COMPLETED.value,
        "diagnostics": {"quality_contract": {
            "id": contract.id, "raw_quality": 1.0, "upper_bound": 1.0,
        }},
    }
    assert contract.quality(optimal_record) == contract.bound({}) == 1.0
    assert (await loaded.decide(dataclasses.replace(
        view, observations={"root": optimal_record},
    ))).stop
    plan = EconomyPlan(baseline_calls_per_task=4, horizon=6)
    assert plan.preparation_budget().total_llm_calls == 17
    assert plan.remaining_preparation_calls(2, 8, 2) == 9
    assert plan.report(8, 6, 6)["all_in_calls"] == 14

    # Exercise the installed console entry point as well as module execution.
    command = Path(sys.executable).parent / (
        "dreamrsi.exe" if sys.platform == "win32" else "dreamrsi"
    )
    for invocation in (
        [str(command), "--help"],
        [sys.executable, "-I", "-m", "dreamrsi", "--help"],
    ):
        result = subprocess.run(invocation, check=True, capture_output=True, text=True)
        assert all(name in result.stdout for name in ("publish", "install", "watch", "doctor"))
    print(
        f"Installed wheel {dreamrsi.__version__}: "
        "import, recursive codecs, quality, economy, worker, inspector and CLI passed"
    )


if __name__ == "__main__":
    asyncio.run(check_installed_wheel())
