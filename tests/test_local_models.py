import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from dreamrsi import LlamaCppPolicyModel, OllamaPolicyModel


@asynccontextmanager
async def server(response, *, chunked=False, status=200):
    requests = []

    async def handle(reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head.decode().split("\r\n")
            size = next(
                int(x.split(":", 1)[1]) for x in lines if x.lower().startswith("content-length:")
            )
            body = await reader.readexactly(size)
            requests.append((lines[0], json.loads(body) if body else None))
            data = json.dumps(response).encode()
            framing = "Transfer-Encoding: chunked" if chunked else f"Content-Length: {len(data)}"
            writer.write(f"HTTP/1.1 {status} Test\r\n{framing}\r\n\r\n".encode())
            if chunked:
                writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n0\r\n\r\n")
            else:
                writer.write(data)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    instance = await asyncio.start_server(handle, "127.0.0.1", 0)
    async with instance:
        yield f"http://127.0.0.1:{instance.sockets[0].getsockname()[1]}", requests


@pytest.mark.parametrize("chunked", [False, True])
async def test_llamacpp_wire_contract_and_accounting(chunked):
    response = {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"source":"code"}'}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }
    async with server(response, chunked=chunked) as (url, requests):
        reports = []
        result = await LlamaCppPolicyModel(url)(
            {"instruction": "rewrite", "feedback": {"score": 1}, "report_usage": reports.append}
        )
        assert result == '{"source":"code"}'
        assert reports[0].tokens == 18
        assert reports[0].provider_calls == 1
        route, payload = requests[0]
        assert route == "POST /v1/chat/completions HTTP/1.1"
        assert payload["response_format"]["schema"]["required"] == [
            "source",
            "diagnosis",
            "changes",
        ]
        assert json.loads(payload["messages"][1]["content"])["feedback"] == {"score": 1}


async def test_truncation_is_rejected_but_usage_retained():
    response = {
        "choices": [{"finish_reason": "length", "message": {"content": "partial"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }
    async with server(response) as (url, _):
        reports = []
        with pytest.raises(RuntimeError, match="Incomplete"):
            await LlamaCppPolicyModel(url)(
                {"instruction": "rewrite", "report_usage": reports.append}
            )
        assert reports[0].tokens == 8


async def test_http_error_and_response_cap():
    async with server({"error": "unavailable"}, status=503) as (url, _):
        with pytest.raises(RuntimeError, match="503"):
            await LlamaCppPolicyModel(url).health()
    async with server({"large": "x" * 2000}, chunked=True) as (url, _):
        with pytest.raises(ValueError, match="limit"):
            await LlamaCppPolicyModel(url, max_response_bytes=1024).health()


async def test_ollama_uses_shared_transport():
    response = {
        "done": True,
        "message": {"content": "code"},
        "prompt_eval_count": 4,
        "eval_count": 2,
    }
    async with server(response) as (url, requests):
        reports = []
        assert (
            await OllamaPolicyModel("fixture", url)(
                {"instruction": "rewrite", "report_usage": reports.append}
            )
            == "code"
        )
        assert requests[0][0] == "POST /api/chat HTTP/1.1"
        assert reports[0].tokens == 6
