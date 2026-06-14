"""
Pytest configuration for backend tests.

Two safety nets keep the fast suite (`-m "not slow"`) fast, offline, and
un-hangable — fixing the silent-fragility bug class that wedged a grind session
for 2.5h (a non-slow test made a live yfinance/FRED call with no timeout):

  1. `pytest.ini` sets a hard per-test `timeout` backstop.
  2. `_block_network` (below) blocks outbound sockets for any test NOT marked
     `slow`/`network`, so a unit test that reaches for the network fails FAST and
     LOUD instead of hanging. The rule is explicit: **a network call in a unit
     test is a bug** — mark it `@pytest.mark.slow` or mock the fetch.
"""

import socket

import pytest

_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


def pytest_configure(config):
    # Belt-and-suspenders marker registration (pytest.ini also declares these).
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (require network/data fetching)"
    )
    config.addinivalue_line(
        "markers", "network: marks tests that intentionally hit the live network"
    )


def _host_of(address):
    if isinstance(address, (tuple, list)) and address:
        return address[0]
    return address


@pytest.fixture(autouse=True)
def _block_network(request):
    """Block non-loopback sockets for non-slow/non-network tests (fail fast, loud)."""
    marker = request.node.get_closest_marker("slow") or request.node.get_closest_marker("network")
    if marker is not None:
        yield  # slow/network tests are allowed to reach the network
        return

    def _guard_connect(self, address):
        host = _host_of(address)
        if host in _LOOPBACK:
            return _REAL_CONNECT(self, address)
        raise RuntimeError(
            f"BLOCKED live network connect to {address!r} in a non-slow test. "
            "Unit tests must be offline — mark it @pytest.mark.slow (or .network) "
            "or mock the fetch. (This is the 2.5h-hang bug class.)"
        )

    def _guard_create_connection(address, *args, **kwargs):
        host = _host_of(address)
        if host in _LOOPBACK:
            return _REAL_CREATE_CONNECTION(address, *args, **kwargs)
        raise RuntimeError(
            f"BLOCKED live network connect to {address!r} in a non-slow test. "
            "Unit tests must be offline — mark it @pytest.mark.slow (or .network) "
            "or mock the fetch. (This is the 2.5h-hang bug class.)"
        )

    socket.socket.connect = _guard_connect
    socket.create_connection = _guard_create_connection
    try:
        yield
    finally:
        socket.socket.connect = _REAL_CONNECT
        socket.create_connection = _REAL_CREATE_CONNECTION
