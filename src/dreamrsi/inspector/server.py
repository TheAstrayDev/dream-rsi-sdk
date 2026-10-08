"""Read-only loopback viewer and standalone HTML export; Python standard library."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .journal import DEFAULT_JOURNAL, InspectorReader


def export_html(snapshot: dict) -> str:
    assets = files("dreamrsi.inspector").joinpath("ui")
    html = assets.joinpath("index.html").read_text(encoding="utf-8")
    css = assets.joinpath("style.css").read_text(encoding="utf-8")
    script = assets.joinpath("app.js").read_text(encoding="utf-8")
    saved = {
        **snapshot,
        "runs": [
            run for run in snapshot.get("runs", []) if run["id"] == snapshot.get("selected_run")
        ],
    }
    data = json.dumps(saved, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    html = html.replace('<link rel="stylesheet" href="/style.css">', f"<style>{css}</style>")
    return html.replace(
        '<script src="/app.js" defer></script>',
        f'<script id="offline-state" type="application/json">{data}</script>'
        f"<script>{script}</script>",
    )


class InspectorServer:
    """Serve only bundled assets and projected journal records on 127.0.0.1."""

    def __init__(self, path: str | Path = DEFAULT_JOURNAL, *, port: int = 0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be an integer between 0 and 65535")
        reader = InspectorReader(path)
        assets = files("dreamrsi.inspector").joinpath("ui")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hostname = urlsplit("http://" + self.headers.get("Host", "")).hostname
                origin = self.headers.get("Origin")
                if hostname not in ("127.0.0.1", "localhost") or (
                    origin and origin != f"http://{self.headers.get('Host')}"
                ):
                    self._send(403, b"Local requests only", "text/plain")
                    return
                address = urlsplit(self.path)
                if address.path in ("/api/state", "/api/export"):
                    try:
                        query = parse_qs(address.query)
                        run_id = query.get("run", [None])[0]
                        snapshot = reader.snapshot(run_id)
                        if address.path == "/api/export":
                            self._send(
                                200,
                                export_html(snapshot).encode("utf-8"),
                                "text/html",
                                download=True,
                            )
                        else:
                            self._send(
                                200,
                                json.dumps(snapshot, allow_nan=False).encode("utf-8"),
                                "application/json",
                            )
                    except Exception:
                        payload = {
                            "error": "Cannot read this inspector journal. "
                            "Check the path or restart the writer."
                        }
                        self._send(503, json.dumps(payload).encode(), "application/json")
                    return
                name = {"/": "index.html", "/style.css": "style.css", "/app.js": "app.js"}
                if address.path not in name:
                    self._send(404, b"Not found", "text/plain")
                    return
                resource = name[address.path]
                content_type = {
                    "index.html": "text/html",
                    "style.css": "text/css",
                    "app.js": "application/javascript",
                }[resource]
                self._send(200, assets.joinpath(resource).read_bytes(), content_type)

            def _send(self, code, body, content_type, download=False):
                self.send_response(code)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                if not download:
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'self'; script-src 'self'; "
                        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        "connect-src 'self'; frame-ancestors 'none'",
                    )
                if download:
                    self.send_header(
                        "Content-Disposition", 'attachment; filename="dreamrsi-run.html"'
                    )
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread: threading.Thread | None = None

    def start(self) -> InspectorServer:
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="dreamrsi-viewer", daemon=True
        )
        self._thread.start()
        return self

    def close(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=3)
        self._server.server_close()

    def __enter__(self) -> InspectorServer:
        return self.start()

    def __exit__(self, *_):
        self.close()
