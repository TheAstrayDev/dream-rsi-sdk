"""Local llama.cpp server transport; no provider SDK or model download side effects."""

from __future__ import annotations

import json

from dreamrsi._http import LocalHTTPTransport
from dreamrsi.accounting import Usage
from dreamrsi.ollama import _SCHEMA


class LlamaCppPolicyModel(LocalHTTPTransport):
    """Generate policy revisions through llama-server's chat endpoint.

    Cancellation closes the connection. Actual compute cancellation depends on the
    server. Zero USD denotes provider billing, excluding local hardware costs.
    """

    def __init__(
        self,
        base_url="http://127.0.0.1:8080",
        *,
        model="local",
        temperature=0.3,
        max_tokens=2048,
        timeout_s=180,
        max_response_bytes=2_000_000,
        structured=True,
        reasoning_effort=None,
        seed=None,
        top_p=0.95,
        top_k=20,
    ):
        super().__init__(base_url, timeout_s, max_response_bytes)
        if max_tokens <= 0 or temperature < 0:
            raise ValueError("Invalid generation limits")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.structured = structured
        self.reasoning_effort = reasoning_effort
        self.seed = seed
        self.top_p, self.top_k = top_p, top_k

    async def health(self):
        return await self._request("/health")

    async def __call__(self, request):
        content = {
            k: v for k, v in request.items() if k not in ("report_usage", "usage", "instruction")
        }
        payload = {
            "model": self.model,
            "stream": False,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": request["instruction"]},
                {"role": "user", "content": json.dumps(content, allow_nan=False)},
            ],
        }
        if self.structured and request.get("response_format") != "python":
            payload["response_format"] = {
                "type": "json_schema",
                "schema": _SCHEMA,
            }
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.seed is not None:
            payload["seed"] = self.seed
        result = await self._request("/v1/chat/completions", payload)
        usage = result.get("usage", {})
        if "report_usage" in request:
            request["report_usage"](
                Usage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    provider_calls=1,
                )
            )
        choice = result["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise RuntimeError(f"Incomplete llama.cpp generation: {choice.get('finish_reason')}")
        source = choice["message"]["content"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError("llama.cpp returned no policy content")
        return source
