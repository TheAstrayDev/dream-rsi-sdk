"""Dependency-free async Ollama transport for real local policy development."""

from __future__ import annotations

import json

from dreamrsi._http import LocalHTTPTransport
from dreamrsi.accounting import Usage

_SCHEMA = {
    "type": "object",
    "required": ["source", "diagnosis", "changes"],
    "properties": {key: {"type": "string"} for key in ("source", "diagnosis", "changes")},
    "additionalProperties": False,
}


class OllamaPolicyModel(LocalHTTPTransport):
    """Use your local model; downloading models is never an SDK side effect.

    Closing the request on cancellation signals disconnection. Server-side compute
    termination still depends on Ollama; interrupted work is conservatively accounted.
    USD is zero provider billing, not a claim about electricity or hardware costs.
    """

    def __init__(
        self,
        model,
        base_url="http://127.0.0.1:11434",
        options=None,
        timeout_s=180,
        max_response_bytes=2_000_000,
        think=None,
    ):
        super().__init__(base_url, timeout_s, max_response_bytes)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.options = options or {"temperature": 0.3, "num_predict": 2048}
        self.timeout_s, self.max_response_bytes = timeout_s, max_response_bytes
        self.think = think

    async def models(self):
        return await self._request("/api/tags")

    async def __call__(self, request):
        content = {k: v for k, v in request.items() if k not in ("report_usage", "usage")}
        payload = {
            "model": self.model,
            "stream": False,
            "format": _SCHEMA,
            "options": self.options,
            "messages": [
                {"role": "system", "content": request["instruction"]},
                {"role": "user", "content": json.dumps(content, allow_nan=False)},
            ],
        }
        if self.think is not None:
            payload["think"] = self.think
        result = await self._request("/api/chat", payload)
        if "report_usage" in request:
            request["report_usage"](
                Usage(
                    input_tokens=result.get("prompt_eval_count", 0),
                    output_tokens=result.get("eval_count", 0),
                    provider_calls=1,
                    usd=0,
                )
            )
        if not result.get("done", False):
            raise RuntimeError("Ollama returned an incomplete generation")
        return result["message"]["content"]
