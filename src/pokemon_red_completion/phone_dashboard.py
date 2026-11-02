"""Authenticated GET-only LAN bridge to an already running spectator.

This module has no emulator, controller, save or model access. The loopback
dashboard remains unchanged; only its existing public projection is forwarded.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_PATHS = frozenset({"/", "/watch", "/api/status", "/frame.png", "/healthz"})
_COOKIE = "pokemon_spectator"
_MAX_RESPONSE = 4 * 1024 * 1024
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class PhoneDashboard:
    """Expose a fixed spectator on one private interface with a private link."""

    def __init__(self, *, host: str, port: int, upstream_port: int, token: str, run_id: str):
        address = ipaddress.ip_address(host)
        if address.version != 4 or not address.is_private or address.is_unspecified:
            raise ValueError("phone viewer requires a specific private IPv4 address")
        if any(
            type(value) is not int or not 0 <= value <= 65535
            for value in (port, upstream_port)
        ):
            raise ValueError("invalid viewer port")
        if not upstream_port or (port and port == upstream_port):
            raise ValueError("phone viewer and upstream ports must differ")
        if not _TOKEN.fullmatch(token) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", run_id):
            raise ValueError("invalid private token or run identity")
        self.token = token
        self.run_id = run_id
        self.origin = f"http://127.0.0.1:{upstream_port}"
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self._server = _BridgeHTTPServer((host, port), self._handler())
        self._thread = None

    @property
    def url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/watch"

    @property
    def private_url(self):
        return f"{self.url}?access={self.token}"

    def _read(self, path):
        with self._opener.open(self.origin + path, timeout=3) as response:
            payload = response.read(_MAX_RESPONSE + 1)
            content_type = response.headers.get("Content-Type", "application/octet-stream")
        if len(payload) > _MAX_RESPONSE:
            raise ValueError("viewer response exceeds limit")
        return payload, content_type

    def _status(self):
        payload, content_type = self._read("/api/status")
        status = json.loads(payload)
        if (
            status.get("controller_endpoints") != 0
            or status.get("dashboard", {}).get("view_only") is not True
            or status.get("run", {}).get("id") != self.run_id
        ):
            raise ValueError("spectator identity or read-only boundary differs")
        return payload, content_type

    def _handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, format, *args):
                # Private links must not appear in access logs.
                pass

            def send_body(
                self, status, payload=b"", content_type="text/plain; charset=utf-8", headers=()
            ):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
                )
                for key, value in headers:
                    self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            def authorized(self):
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get("Cookie", ""))
                    value = cookie[_COOKIE].value if _COOKIE in cookie else ""
                except CookieError:
                    return False
                return hmac.compare_digest(value.encode(), bridge.token.encode())

            def do_GET(self):  # noqa: N802
                try:
                    parsed = urllib.parse.urlsplit(self.path)
                    query = urllib.parse.parse_qs(parsed.query, max_num_fields=8)
                except ValueError:
                    self.send_body(400, b"Invalid viewer request.\n")
                    return
                if parsed.scheme or parsed.netloc or parsed.path not in _PATHS:
                    self.send_body(404, b"Not found.\n")
                    return
                tokens = query.get("access", [])
                if tokens:
                    if (
                        parsed.path not in {"/", "/watch"}
                        or len(tokens) != 1
                        or not hmac.compare_digest(tokens[0].encode(), bridge.token.encode())
                    ):
                        self.send_body(403, b"Open your private viewing link.\n")
                        return
                    self.send_body(303, headers=(
                        ("Location", parsed.path),
                        ("Set-Cookie", f"{_COOKIE}={bridge.token}; Path=/; HttpOnly; "
                         "SameSite=Lax; Max-Age=86400"),
                    ))
                    return
                if not self.authorized():
                    self.send_body(403, b"Open your private viewing link.\n")
                    return
                try:
                    status_payload = bridge._status()
                    payload, kind = (
                        status_payload if parsed.path == "/api/status"
                        else bridge._read(parsed.path)
                    )
                except (OSError, ValueError, TypeError, AttributeError):
                    self.send_body(502, b"This run's viewer is temporarily unavailable.\n")
                    return
                self.send_body(200, payload, kind)

            def do_HEAD(self):  # noqa: N802
                self.do_GET()

            def do_POST(self):  # noqa: N802
                self.send_body(405, b"Viewing only.\n", headers=(("Allow", "GET, HEAD"),))

            do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

        return Handler

    def start(self):
        if self._thread is not None:
            raise RuntimeError("phone viewer already started")
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self):
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
