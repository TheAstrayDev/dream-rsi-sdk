"""Small cancellable HTTP transport shared by local model connectors."""

from __future__ import annotations

import asyncio
import json
import ssl
from urllib.parse import urlsplit


class LocalHTTPTransport:
    def __init__(self, base_url, timeout_s=180, max_response_bytes=2_000_000):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Provide an HTTP(S) URL without credentials/query")
        if timeout_s <= 0 or max_response_bytes < 1024:
            raise ValueError("Invalid transport limits")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_response_bytes = max_response_bytes

    async def _request(self, endpoint, payload=None):
        parsed = urlsplit(self.base_url)
        secure = parsed.scheme == "https"
        port = parsed.port or (443 if secure else 80)
        async with asyncio.timeout(self.timeout_s):
            reader, writer = await asyncio.open_connection(
                parsed.hostname, port, ssl=ssl.create_default_context() if secure else None
            )
            try:
                body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode()
                path = parsed.path.rstrip("/") + endpoint
                method = "GET" if payload is None else "POST"
                host = parsed.hostname
                assert host is not None
                if ":" in host:
                    host = "[" + host + "]"
                header = (
                    f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                    "Content-Type: application/json\r\nConnection: close\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                )
                if "\r" in path or "\n" in path:
                    raise ValueError("Invalid URL path")
                writer.write(header.encode() + body)
                await writer.drain()
                headers = await reader.readuntil(b"\r\n\r\n")
                lines = headers.decode("iso-8859-1").split("\r\n")
                status = int(lines[0].split()[1])
                fields = dict(line.lower().split(":", 1) for line in lines[1:] if ":" in line)
                output = bytearray()
                if "chunked" in fields.get("transfer-encoding", ""):
                    while True:
                        size = int((await reader.readline()).split(b";", 1)[0], 16)
                        if size == 0:
                            break
                        if size < 0 or len(output) + size > self.max_response_bytes:
                            raise ValueError("Model response limit exceeded")
                        output.extend(await reader.readexactly(size))
                        if await reader.readexactly(2) != b"\r\n":
                            raise ValueError("Invalid chunk framing")
                elif "content-length" in fields:
                    size = int(fields["content-length"])
                    if size < 0 or size > self.max_response_bytes:
                        raise ValueError("Model response limit exceeded")
                    output.extend(await reader.readexactly(size))
                else:
                    while chunk := await reader.read(4096):
                        output.extend(chunk)
                        if len(output) > self.max_response_bytes:
                            raise ValueError("Model response limit exceeded")
                if status != 200:
                    raise RuntimeError(
                        f"Model HTTP {status}: {output[:1000].decode(errors='replace')}"
                    )
                return json.loads(output)
            finally:
                writer.close()
                await writer.wait_closed()
