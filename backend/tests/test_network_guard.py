"""The guard's own guard.

Written 2026-08-12 after discovering that the fast suite's network block had a
hole big enough to drive yfinance through.

`_block_network` patches `socket.socket.connect` and `socket.create_connection`.
That covers requests/urllib3/http.client. It does NOT cover `curl_cffi`, which
reaches libcurl through CFFI and never touches Python sockets — and **yfinance
1.1.0 uses curl_cffi**, so every yfinance call in the suite was unguarded.

The failure was not theoretical. During the LLM-SWARM-1 run a non-slow test
reached yfinance and hung under network contention while 24 workers saturated
the connection. `pytest-timeout` was declared in requirements but not installed
on that machine, so the second backstop was down at the same time.

These tests exist so the next transport change fails here instead of silently
reopening the hole. If a future library moves to yet another transport (aiohttp
on raw sockets is covered; a new CFFI/Rust binding would not be), add it to
`_block_network` AND add a probe here.
"""

import pytest


def test_the_socket_transport_is_blocked():
    """Control. If this ever fails the guard is off entirely."""
    import socket
    with pytest.raises(RuntimeError, match="BLOCKED"):
        socket.create_connection(("example.com", 80), timeout=5)


def test_the_curl_cffi_transport_is_blocked():
    """The regression. This test FAILED before 2026-08-12 — the request
    completed and reached example.com from inside the fast suite."""
    curl_requests = pytest.importorskip(
        "curl_cffi.requests",
        reason="curl_cffi absent — guard degrades to socket-only by design")
    with pytest.raises(RuntimeError, match="BLOCKED"):
        curl_requests.get("https://example.com", timeout=8)


def test_the_curl_cffi_session_object_is_blocked_too():
    """`requests.get` is a convenience wrapper; real callers (yfinance included)
    hold a pooled Session. Both funnel through Session.request, but assert it
    rather than trusting the funnel."""
    curl_requests = pytest.importorskip("curl_cffi.requests")
    with pytest.raises(RuntimeError, match="BLOCKED"):
        with curl_requests.Session() as s:
            s.get("https://example.com", timeout=8)


def test_loopback_still_works_over_curl_cffi():
    """The guard must not break TestClient-style local traffic. A connection
    refused (nothing listening) proves the guard let it THROUGH."""
    curl_requests = pytest.importorskip("curl_cffi.requests")
    try:
        curl_requests.get("http://127.0.0.1:9/", timeout=3)
    except RuntimeError as exc:                       # pragma: no cover
        if "BLOCKED" in str(exc):
            pytest.fail("guard blocked loopback — TestClient traffic would break")
    except Exception:
        pass  # connection refused / timeout: the guard allowed it through


def test_yfinance_actually_uses_the_transport_we_just_guarded():
    """Pins the reason this file exists. If yfinance stops using curl_cffi the
    comment above becomes wrong, and someone should notice here rather than
    from a hung suite."""
    yf = pytest.importorskip("yfinance")
    import inspect
    from yfinance import data as yf_data
    assert "curl_cffi" in inspect.getsource(yf_data), (
        f"yfinance {yf.__version__} no longer uses curl_cffi — re-check which "
        f"transport the fast-suite guard must cover")


# ── Protected LOCAL ports (2026-09-29) ─────────────────────────────────────
# The loopback allowance let two health() tests prove the instance against the
# owner's LIVE dedicated Chrome (CDP port) -- and the OpenClaw gateway was
# reachable the same way. Chrome crashed twice that afternoon soon after test
# traffic hit its port. Those ports are now refused for every test, both
# transports, while ephemeral local test servers keep working. Every probe
# below is refused BEFORE a connect is attempted, so none of them touches the
# live process even when it is up.

def _protected():
    from backend import config
    return {"cdp": int(config.OPENCLAW_DEDICATED_CDP_PORT),
            "gateway": int(config.OPENCLAW_GATEWAY_PORT)}


def test_protected_ports_are_read_from_config_not_a_second_copy():
    from backend.tests.conftest import protected_local_ports
    ports = protected_local_ports()
    assert set(ports) == set(_protected().values())
    assert set(ports.values()) == {"OPENCLAW_DEDICATED_CDP_PORT", "OPENCLAW_GATEWAY_PORT"}


@pytest.mark.parametrize("which", ["cdp", "gateway"])
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.1.2.3"])
def test_socket_connect_to_a_protected_port_is_refused(which, host):
    import socket
    from backend.tests.conftest import ProtectedLocalPortRefused
    port = _protected()[which]
    with pytest.raises(ProtectedLocalPortRefused, match="REFUSED loopback"):
        socket.create_connection((host, port), timeout=1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(ProtectedLocalPortRefused):
            s.connect(("127.0.0.1", port))
        with pytest.raises(ProtectedLocalPortRefused):
            s.connect_ex(("127.0.0.1", port))
    finally:
        s.close()


def test_a_refusal_reads_as_connection_refused_to_production_code():
    """Code that treats a refused connect as "service down" sees exactly that."""
    import socket
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", _protected()["cdp"]), timeout=1)


def test_urllib_to_the_cdp_endpoint_is_refused():
    """The real prover's path: urllib -> http.client -> socket."""
    import urllib.error
    import urllib.request
    url = f"http://127.0.0.1:{_protected()['cdp']}/json/version"
    with pytest.raises((urllib.error.URLError, ConnectionRefusedError)) as ei:
        urllib.request.urlopen(url, timeout=1)
    assert "REFUSED loopback" in str(ei.value)


@pytest.mark.parametrize("which", ["cdp", "gateway"])
def test_curl_cffi_to_a_protected_port_is_refused(which):
    curl_requests = pytest.importorskip("curl_cffi.requests")
    from backend.tests.conftest import ProtectedLocalPortRefused
    port = _protected()[which]
    for url in (f"http://127.0.0.1:{port}/json/version",
                f"http://localhost:{port}/"):
        with pytest.raises(ProtectedLocalPortRefused):
            curl_requests.get(url, timeout=1)
        with pytest.raises(ProtectedLocalPortRefused):
            with curl_requests.Session() as s:
                s.get(url, timeout=1)


@pytest.mark.slow
def test_protected_ports_are_refused_even_for_slow_tests():
    """Slow tests may reach the internet; they may not reach the owner's
    running browser. Offline and instant, so it costs nothing to run."""
    import socket
    from backend.tests.conftest import ProtectedLocalPortRefused
    with pytest.raises(ProtectedLocalPortRefused):
        socket.create_connection(("127.0.0.1", _protected()["cdp"]), timeout=1)


def test_an_ephemeral_local_test_server_still_works_over_both_transports():
    """The loopback allowance still exists for what it was for."""
    import http.server
    import threading
    import urllib.request

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                  # noqa: N802
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):                          # silence
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    assert port not in _protected().values()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert r.read() == b"ok"
        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            curl_requests = None
        if curl_requests is not None:
            r = curl_requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert r.status_code == 200 and r.content == b"ok"
    finally:
        srv.shutdown()
        srv.server_close()
