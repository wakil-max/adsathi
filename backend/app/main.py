"""Local / Docker entrypoint: a zero-dependency stdlib HTTP server.

Run with:  python3 -m app.main      (from the backend/ directory)
No pip install required for demo mode.
"""
from __future__ import annotations
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

from .router import dispatch


def _parse_cookies(raw: str) -> dict:
    jar = SimpleCookie()
    try:
        jar.load(raw or "")
    except Exception:
        pass
    return {k: m.value for k, m in jar.items()}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self, method: str):
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        cookies = _parse_cookies(self.headers.get("Cookie", ""))
        hdrs = {k.lower(): v for k, v in self.headers.items()}
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        status, headers, payload = dispatch(method, parsed.path, query, cookies, hdrs, body)
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def log_message(self, *args):
        pass  # quiet


def run():
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"AdSathi running on http://{host}:{port}  (DRY_RUN={os.getenv('DRY_RUN','true')})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    run()
