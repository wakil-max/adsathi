"""Vercel serverless entry (Python runtime) — WSGI app wrapping the same router."""
import os
import sys
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.router import dispatch  # noqa: E402


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    query = {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
    jar = SimpleCookie(); jar.load(environ.get("HTTP_COOKIE", "") or "")
    cookies = {k: m.value for k, m in jar.items()}
    headers = {}
    for k, v in environ.items():
        if k.startswith("HTTP_"):
            headers[k[5:].replace("_", "-").lower()] = v
    try:
        length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    except ValueError:
        length = 0
    body = environ["wsgi.input"].read(length) if length else b""

    status, resp_headers, payload = dispatch(method, path, query, cookies, headers, body)
    reason = {200: "OK", 302: "Found", 400: "Bad Request", 401: "Unauthorized",
              402: "Payment Required", 404: "Not Found", 502: "Bad Gateway"}.get(status, "OK")
    start_response(f"{status} {reason}",
                   list(resp_headers) + [("Content-Length", str(len(payload)))])
    return [payload]
