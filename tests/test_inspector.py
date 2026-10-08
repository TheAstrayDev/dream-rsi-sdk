"""Observer invariants, persistence, interruption and the real HTTP delivery path."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dreamrsi import (
    Budget,
    DreamRSI,
    EconomyPlan,
    FunctionalAgentAdapter,
    LiveInspector,
    QualityContract,
    Usage,
)
from dreamrsi.cli import main
from dreamrsi.inspector import InspectorServer
from dreamrsi.inspector.journal import InspectorReader, safe_value
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.policies import BreadthFirstPolicy, DepthFirstPolicy, GreedyPolicy
from dreamrsi.replay import ReplayWorld


async def execute(inspector=None, *, parallelism=1):
    contexts = []
    quality_calls = []

    def step(state, context):
        contexts.append(sorted(key for key in context if key != "report_usage"))
        return {"x": state["x"] / 2}

    def raw(record):
        quality_calls.append(record["score"])
        return record["score"]

    sdk = DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda answer: -(answer["x"] ** 2),
        policy=DepthFirstPolicy() if parallelism == 1 else GreedyPolicy(batch_size=3),
        budget=Budget(model_calls=4 if parallelism == 1 else 8, max_parallelism=parallelism),
        quality=QualityContract(id="observer-test", metric=raw, upper_bound=0),
        inspector=inspector,
    )
    result = await sdk.run({"x": 8})
    return sdk, result, contexts, quality_calls


@pytest.mark.parametrize("parallelism", [1, 3])
async def test_observer_preserves_answers_decisions_contexts_and_costs(tmp_path, parallelism):
    baseline = await execute(parallelism=parallelism)
    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        watched = await execute(observer, parallelism=parallelism)
        assert observer.flush()
        snapshot = InspectorReader(observer.path).snapshot()
    assert baseline[1].best == watched[1].best
    assert baseline[1].costs == watched[1].costs
    assert baseline[2:] == watched[2:]
    assert baseline[0].usage.spent == watched[0].usage.spent

    def shape(result):
        nodes = list(result.tree.iter_nodes())
        orders = {node.id: node.creation_order for node in nodes}
        return [
            (node.creation_order, orders.get(node.parent_id), node.state, node.score, node.status)
            for node in nodes
        ]

    assert shape(baseline[1]) == shape(watched[1])
    calls = watched[1].costs.model_calls
    assert len([e for e in snapshot["events"] if e["type"] == "node_snapshot"]) == calls + 1
    assert [
        e["data"]["round"] for e in snapshot["events"] if e["type"] == "policy_decision"
    ] == list(range(1, watched[1].rounds + 1))
    usage = [e["data"] for e in snapshot["events"] if e["type"] == "usage"][-1]
    assert usage["deployment"] == calls and usage["preparation"] == 0
    assert usage["tokens"] is None and usage["usd"] is None


async def test_live_root_pending_attempt_and_cancelled_outcome(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def agent(task):
        entered.set()
        await release.wait()
        return task

    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        sdk = DreamRSI(
            agent=agent, evaluator=float, budget=Budget(model_calls=1), inspector=observer
        )
        task = asyncio.create_task(sdk.run(1))
        await asyncio.wait_for(entered.wait(), 3)
        assert observer.flush()
        live = InspectorReader(observer.path).snapshot()
        assert any(e["type"] == "node_snapshot" for e in live["events"])
        assert any(e["type"] == "attempt_started" for e in live["events"])
        pending_usage = [e["data"] for e in live["events"] if e["type"] == "usage"][-1]
        assert pending_usage["run_held"]["total_llm_calls"] == 1
        assert pending_usage["deployment"] == 1
        assert not any(e["type"] == "run_result" for e in live["events"])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observer.flush()
        final = InspectorReader(observer.path).snapshot()
        assert any(e["type"] == "attempt_finished" for e in final["events"])
        assert any(e["type"] == "run_failed" for e in final["events"])
        assert sdk.usage.spent["model_calls"] == 1
    assert not InspectorReader(observer.path).snapshot()["writer_alive"]


async def test_failing_observer_cannot_fail_search():
    class Broken:
        def record(self, *args, **kwargs):
            raise RuntimeError("viewer failed")

        def on_event(self, event):
            raise RuntimeError("viewer failed")

    result = await execute(Broken())
    assert result[1].best == {"x": 0.5}


async def test_policy_reason_and_stopped_decision_are_recorded(tmp_path):
    class StopPolicy:
        def decide(self, view):
            return PolicyDecision(expand=[], stop=True, reason="Local feasibility check passed")

    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        sdk = DreamRSI(agent=lambda t: t, evaluator=float, policy=StopPolicy(), inspector=observer)
        result = await sdk.run(1)
        observer.flush()
        event = next(
            e
            for e in InspectorReader(observer.path).snapshot()["events"]
            if e["type"] == "policy_decision"
        )
    assert result.costs.model_calls == 0
    assert event["data"]["stop"]
    assert event["data"]["reason"] == "Local feasibility check passed"
    assert (
        PolicyDecision.from_dict(PolicyDecision([], reason="reason").to_dict()).reason == "reason"
    )
    assert PolicyDecision.from_dict({"expand": []}).reason is None


def test_projection_does_not_execute_objects_or_expose_known_credentials():
    class Hostile:
        def __repr__(self):
            raise AssertionError("repr executed")

    class HostileDict(dict):
        def items(self):
            raise AssertionError("custom items executed")

    class HostileList(list):
        def __getitem__(self, key):
            raise AssertionError("custom slice executed")

    assert safe_value(HostileDict()) == "[unsupported HostileDict]"
    assert safe_value(HostileList()) == "[unsupported HostileList]"

    original = {
        "api_key": "private",
        "message": "sk-" + "x" * 30,
        "value": Hostile(),
        "input_tokens": 10,
        "huge": 10**400,
        "nan": float("nan"),
    }
    projected = safe_value(original)
    assert projected["api_key"] == "[redacted]"
    assert projected["message"] == "[redacted]"
    assert projected["input_tokens"] == 10 and projected["nan"] is None
    assert projected["value"] == "[unsupported Hostile]"
    assert original["api_key"] == "private"
    assert (
        safe_value({"state": {"private": "content"}}, include_content=False)["state"]
        == "[content disabled]"
    )


def test_queue_overflow_is_visible_and_never_blocks_execution(tmp_path):
    with LiveInspector(tmp_path / "journal.sqlite3", queue_capacity=1) as observer:
        observer.record("run_opened", run_id="one", data={"policy": "test"})
        assert observer.flush()
        for index in range(2000):
            observer.record("round_completed", run_id="one", data={"index": index})
        assert observer.flush()
        assert observer.dropped_events > 0
        assert InspectorReader(observer.path).snapshot()["dropped"] > 0


async def test_session_history_is_not_mixed_between_runs(tmp_path):
    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        first = (await execute(observer))[1]
        observer.record("policy_review", data={"reason": "first only"})
        second = (await execute(observer))[1]
        observer.record("policy_review", data={"reason": "second only"})
        observer.flush()
        older = InspectorReader(observer.path).snapshot(first.run_id)
        newer = InspectorReader(observer.path).snapshot(second.run_id)
    assert [e["data"]["reason"] for e in older["events"] if e["type"] == "policy_review"] == [
        "first only"
    ]
    assert [e["data"]["reason"] for e in newer["events"] if e["type"] == "policy_review"] == [
        "second only"
    ]


async def test_real_replay_comparison_does_not_dispatch_agent(tmp_path):
    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        sdk, result, _, _ = await execute(observer)
        before = sdk.usage.to_dict()["spent"]
        reports = await observer.compare(
            sdk, ReplayWorld(result.tree), [DepthFirstPolicy(), GreedyPolicy(batch_size=1)]
        )
        observer.flush()
        assert sdk.usage.to_dict()["spent"] == before
        assert len(reports) == 2
        assert all(report["tree_id"] == result.tree.tree_id for report in reports)
        assert all(report["preserves_original"] for report in reports)
        assert reports[1]["requested_policy"] == "GreedyPolicy"
        assert reports[1]["policy"] == "CertifiedPolicy"
        assert any(
            e["type"] == "replay_comparison"
            for e in InspectorReader(observer.path).snapshot()["events"]
        )
        sdk.quality = replace(sdk.quality, preserve_policy=False, certified_stopping=False)
        extended = await observer.compare(
            sdk, ReplayWorld(result.tree), [BreadthFirstPolicy(batch_size=1), GreedyPolicy(1)]
        )
        observer.flush()
        captured = [
            e["data"]["reports"]
            for e in InspectorReader(observer.path).snapshot()["events"]
            if e["type"] == "replay_comparison"
        ][-1]
        assert extended[0]["rounds"] == 1000
        assert len(captured) == 2
        assert captured[1]["policy"] == "GreedyPolicy"


async def test_http_assets_security_and_self_contained_export(tmp_path):
    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        await execute(observer)
        observer.record("policy_review", data={"reason": "</script><script>alert(1)</script>"})
        observer.flush()
        with InspectorServer(observer.path) as server:
            with urlopen(server.url + "/api/state", timeout=3) as response:
                assert response.headers["X-Content-Type-Options"] == "nosniff"
                assert len(json.load(response)["runs"]) == 1
            with urlopen(server.url + "/app.js", timeout=3) as response:
                assert b"textContent" in response.read()
            with urlopen(server.url + "/api/export", timeout=3) as response:
                html = response.read().decode()
                assert 'id="offline-state"' in html
                assert 'src="/app.js"' not in html
                assert 'href="/style.css"' not in html
                assert "</script><script>alert(1)</script>" not in html
            for request in [
                Request(server.url, headers={"Host": "evil.example"}),
                Request(server.url, headers={"Origin": "https://evil.example"}),
                Request(server.url + "/../../pyproject.toml"),
            ]:
                with pytest.raises(HTTPError):
                    urlopen(request, timeout=3)


def test_cli_init_and_doctor_do_not_overwrite_or_make_model_calls(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    source = (tmp_path / "dreamrsi_app.py").read_text(encoding="utf-8")
    compile(source, "dreamrsi_app.py", "exec")
    assert main(["init"]) == 1
    assert (tmp_path / "dreamrsi_app.py").read_text(encoding="utf-8") == source
    assert main(["doctor"]) == 0
    assert "Model requests: none" in capsys.readouterr().out


def test_missing_reader_is_read_only_and_invalid_port_is_helpful(tmp_path):
    path = tmp_path / "missing.sqlite3"
    assert InspectorReader(path).snapshot()["runs"] == []
    assert not path.exists()
    assert main(["watch", "--port", "-1", "--no-browser"]) == 1


async def test_report_keeps_unknown_costs_unknown():
    result = (await execute())[1]
    report = result.report()
    assert "Agent dispatches: 4" in report
    assert "Tokens: unknown" in report
    assert "USD: unknown" in report
    assert "ROI are not established" in report


async def test_nested_usage_historical_costs_and_safe_export(tmp_path):
    def agent(state, context):
        context["report_usage"](Usage(provider_calls=2, input_tokens=7, usd=0.02))
        return state

    def evaluate(answer, context):
        context["report_usage"](Usage(provider_calls=1, output_tokens=3, usd=0.01))
        return float(answer)

    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        sdk = DreamRSI(
            adapter=FunctionalAgentAdapter(agent),
            evaluator=evaluate,
            budget=Budget(model_calls=1, total_llm_calls=3),
            economy=EconomyPlan(
                baseline_calls_per_task=4, horizon=6, historical_preparation_calls=4
            ),
            inspector=observer,
        )
        result = await sdk.run(1)
        observer.flush()
        usage = [
            e["data"]
            for e in InspectorReader(observer.path).snapshot()["events"]
            if e["type"] == "usage"
        ][-1]
        assert usage["historical"] == 4
        assert usage["spent"]["total_llm_calls"] == 3
        assert usage["deployment"] == 3
        assert usage["tokens"] == 10 and usage["usd"] == pytest.approx(0.03)
        assert "Reported tokens: 10" in result.report()
        assert "Reported USD: 0.030000" in result.report()
    report = tmp_path / "report.html"
    args = ["watch", "--journal", str(observer.path), "--export", str(report)]
    assert main(args) == 0
    content = report.read_text(encoding="utf-8")
    assert main(args) == 1
    assert report.read_text(encoding="utf-8") == content


async def test_zero_dispatch_run_retains_campaign_ledger(tmp_path):
    class Stop:
        def decide(self, view):
            return PolicyDecision([], stop=True)

    with LiveInspector(tmp_path / "journal.sqlite3") as observer:
        sdk, _, _, _ = await execute(observer)
        sdk._policy = Stop()
        result = await sdk.run({"x": 8})
        observer.flush()
        events = InspectorReader(observer.path).snapshot(result.run_id)["events"]
        usage = [event["data"] for event in events if event["type"] == "usage"][-1]
    assert result.costs.model_calls == 0
    assert usage["spent"]["total_llm_calls"] == 4
    assert usage["run_spent"]["model_calls"] == 0


def test_metadata_only_capture_keeps_private_diagnostics_out(tmp_path):
    with LiveInspector(tmp_path / "journal.sqlite3", include_content=False) as observer:
        observer.record("run_opened", run_id="one", data={})
        observer.record(
            "node_snapshot",
            run_id="one",
            data={
                "node": {
                    "id": "root",
                    "parent_id": None,
                    "raw_quality": 0.9,
                    "observation": "private answer",
                    "metadata": {"diagnostics": "private task"},
                }
            },
        )
        observer.flush()
        text = json.dumps(InspectorReader(observer.path).snapshot())
    assert "private answer" not in text and "private task" not in text
    assert "0.9" in text
    connection = sqlite3.connect(observer.path)
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()
