"""A throwaway static file server on 127.0.0.1 for a web build (fetch() needs http://, not file://)."""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class StaticServer:
    def __init__(self, root: Path, port: int = 0) -> None:
        handler = functools.partial(_Quiet, directory=str(root))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
