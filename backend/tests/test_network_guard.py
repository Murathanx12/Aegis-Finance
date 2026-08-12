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
