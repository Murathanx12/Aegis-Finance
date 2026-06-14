"""
Proves the offline-guard is actually wired (conftest._block_network).

If these pass, a non-slow (unit) test genuinely cannot reach the live network —
the fix for the 2.5h-hang bug class. A `slow`-marked test is exempt (it may fetch).
"""

import socket

import pytest


def test_create_connection_is_blocked_for_unit_tests():
    with pytest.raises(RuntimeError, match="BLOCKED"):
        socket.create_connection(("8.8.8.8", 53), timeout=2)


def test_raw_socket_connect_is_blocked_for_unit_tests():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="BLOCKED"):
            s.connect(("93.184.216.34", 80))  # example.com — must never be reached
    finally:
        s.close()


def test_loopback_is_allowed():
    # Loopback must stay permitted (TestClient / local sockets). Connecting to a
    # closed loopback port raises ConnectionRefused/OSError — NOT our RuntimeError.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 1))  # almost certainly closed
    except RuntimeError:
        pytest.fail("loopback must not be blocked by the network guard")
    except OSError:
        pass  # expected: refused/timeout, not blocked
    finally:
        s.close()


@pytest.mark.slow
def test_slow_marked_tests_are_exempt_from_block():
    # A slow test is allowed to reach the network: the guard must NOT be installed,
    # so our RuntimeError is never raised (a real OSError may occur offline — fine).
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
    except RuntimeError as e:
        if "BLOCKED" in str(e):
            pytest.fail("slow tests must be exempt from the network block")
    except OSError:
        pass  # real network result (refused/timeout/ok) — the point is it's not BLOCKED
