"""Phone transport checks use a fake spectator; no emulator or saves."""

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from pokemon_red_completion.phone_dashboard import PhoneDashboard

TOKEN = "a" * 43
RUN = "phone-view-test"


@contextmanager
def upstream(*, run_id=RUN, controls=0, redirect=False, oversized=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            requests.append(self.path)
            if redirect:
                self.send_response(302)
                self.send_header("Location", "/private-file")
                self.end_headers()
                return
            if self.path == "/api/status":
                body = json.dumps(dict(run=dict(id=run_id), controller_endpoints=controls,
                                       dashboard=dict(view_only=True))).encode()
                kind = "application/json"
            elif self.path == "/frame.png":
                body, kind = b"\x89PNG\r\n\x1a\nframe", "image/png"
            else:
                body, kind = b"<html>Actual spectator</html>", "text/html"
            if oversized:
                body = b"x" * (4 * 1024 * 1024 + 1)
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


def request(viewer, path="/watch", *, method="GET", token=TOKEN):
    url = urlsplit(viewer.url)
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
    headers = {} if token is None else {"Cookie": f"pokemon_spectator={token}"}
    connection.request(method, path, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_private_link_redirects_and_cookie_serves_existing_page_frame_and_status():
    with upstream() as (port, requests), PhoneDashboard(
        host="127.0.0.1", port=0, upstream_port=port, token=TOKEN, run_id=RUN
    ) as viewer:
        code, headers, body = request(viewer, f"/watch?access={TOKEN}", token=None)
        assert code == 303 and headers["Location"] == "/watch" and not body
        assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Lax" in headers["Set-Cookie"]
        assert headers["Referrer-Policy"] == "no-referrer" and requests == []
        assert request(viewer)[2] == b"<html>Actual spectator</html>"
        assert request(viewer, "/frame.png?v=42")[2].startswith(b"\x89PNG")
        assert json.loads(request(viewer, "/api/status")[2])["run"]["id"] == RUN
        assert request(viewer, method="HEAD")[2] == b""
        assert set(requests) <= {"/api/status", "/watch", "/frame.png"}


@pytest.mark.parametrize("path,token,code", [
    ("/watch", None, 403), ("/frame.png", "wrong", 403),
    ("/api/status?access=" + TOKEN, None, 403),
    ("/watch?access=wrong", None, 403),
    ("/watch?access=" + TOKEN + "&access=" + TOKEN, None, 403),
    ("/../../private", TOKEN, 404), ("/controller", TOKEN, 404),
    ("http://example.com/watch", TOKEN, 404),
])
def test_invalid_access_and_paths_never_reach_upstream(path, token, code):
    with upstream() as (port, requests), PhoneDashboard(
        host="127.0.0.1", port=0, upstream_port=port, token=TOKEN, run_id=RUN
    ) as viewer:
        assert request(viewer, path, token=token)[0] == code
        assert not requests


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_write_methods_are_rejected_without_forwarding(method):
    with upstream() as (port, requests), PhoneDashboard(
        host="127.0.0.1", port=0, upstream_port=port, token=TOKEN, run_id=RUN
    ) as viewer:
        assert request(viewer, method=method)[0] == 405
        assert not requests


@pytest.mark.parametrize("options", [dict(run_id="another-run"), dict(controls=1),
                                     dict(redirect=True), dict(oversized=True)])
def test_wrong_viewer_redirects_or_large_replies_fail_closed(options):
    with upstream(**options) as (port, requests), PhoneDashboard(
        host="127.0.0.1", port=0, upstream_port=port, token=TOKEN, run_id=RUN
    ) as viewer:
        assert request(viewer, "/frame.png")[0] == 502
        assert requests == ["/api/status"]


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "::1", "example.com"])
def test_public_wildcard_and_nonliteral_binds_are_rejected(host):
    with pytest.raises(ValueError):
        PhoneDashboard(host=host, port=0, upstream_port=8768, token=TOKEN, run_id=RUN)
