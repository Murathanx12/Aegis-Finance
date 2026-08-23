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

THE HOLE THAT EXISTED UNTIL 2026-08-12, AND WHY IT MATTERED
-----------------------------------------------------------
Net (2) patched `socket.socket.connect` and `socket.create_connection`, which
catches anything built on Python's socket module — `requests`, `urllib3`,
`http.client`. **It did not catch `curl_cffi`**, which reaches libcurl through
CFFI and never touches Python sockets at all.

That is not a hypothetical gap: **yfinance 1.1.0 uses curl_cffi**, so every
yfinance call in the entire fast suite was unguarded. Proven empirically rather
than argued — see `test_network_guard.py`, where the socket control is blocked
and the curl_cffi probe reached example.com from a non-slow test.

Both backstops were down at once on this machine: `pytest-timeout` is declared
in requirements but was not installed locally, so the pytest.ini `timeout` was
inert too. The observable symptom was the LLM-SWARM-1 run — a non-slow test
hung under network contention while 24 workers saturated the connection, and
nothing stopped it.

The docstring's "un-hangable" claim was therefore false for the single most
common external dependency in this repo. It is true again now, and
`test_network_guard.py` exists so that the next transport change fails a test
rather than silently reopening the hole.
"""

import socket

import pytest

_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}

_BLOCK_MESSAGE = (
    "BLOCKED live network connect to {target!r} in a non-slow test. "
    "Unit tests must be offline — mark it @pytest.mark.slow (or .network) "
    "or mock the fetch. (This is the 2.5h-hang bug class.)"
)


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
def _fresh_fmp_budget():
    """Reset the FMP daily-quota ledger around every test (2026-07-17).

    The ledger is process-global on purpose (prod), but in the suite a test
    that mocks an FMP 402 marks the ledger exhausted and silently starves
    every later FMP-touching test in the same process — exactly the
    cross-test state leak the ledger is meant to create in prod, and
    exactly wrong for isolated unit tests.
    """
    try:
        from backend.services import fmp_budget
        fmp_budget._reset_for_tests()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _sandbox_telemetry_to_tmp(tmp_path_factory, monkeypatch):
    """Keep the suite's stub LLM calls out of the tracked sandbox ledger.

    FOUND 2026-08-15 BY LOOKING AT `git status` AFTER A TEST RUN.
    `investigator_night.SANDBOX_TELEMETRY` points at
    `backend/data/optimus/llm_calls_sandbox.jsonl`, which is TRACKED — it holds
    the five-arm rehearsal's record. Every full run of the fast suite was
    appending ~624 stub rows to it: 3.9 MB accumulated, ~400 KB per run, and a
    dirty working tree after every `pytest`.

    The separation from the real ledger is correct and deliberate (stub rows
    priced at $0.00 must never sit beside the rows the funding rule reads).
    What was missing is that the SUITE needs its own file too, for the same
    reason: exhaust from tests that never called a vendor should not accumulate
    in an artifact whose job is to record that a rehearsal happened.

    The same applies to `SANDBOX_RECEIPTS_DIR`, whose 2026-08-15 rehearsal
    receipt the suite was silently rewriting on every run — the file recording
    what the rehearsal did, overwritten by tests that did nothing.
    """
    try:
        from backend.services import investigator_night as _in
        d = tmp_path_factory.mktemp("sandbox_tele")
        monkeypatch.setattr(_in, "SANDBOX_TELEMETRY",
                            d / "llm_calls_sandbox.jsonl", raising=False)
        monkeypatch.setattr(_in, "SANDBOX_RECEIPTS_DIR", d / "nights",
                            raising=False)
    except Exception:                                            # noqa: BLE001
        pass
    yield


@pytest.fixture(autouse=True)
def _execution_ledger_to_tmp(tmp_path_factory, monkeypatch):
    """Keep the suite's fake broker orders out of the real execution ledger.

    FOUND THE SAME WAY AS THE ONE ABOVE — by reading `git status` after a run.
    `test_paper_broker_targets` drives `sync_alpaca_mirror` against a fake
    Alpaca, and the sync now records every submitted order. With no isolation
    those rows landed in `backend/data/optimus/execution/lane_mirror.jsonl`:
    PENDING orders for AAPL and MSFT that no broker will ever resolve, in the
    file a real reconciliation reads.

    That is worse than untidy. Those rows age past `UNRESOLVED_AFTER_DAYS` and
    then reconcile as NEVER_FILLED — so a suite that never touched a market
    would have written permanent evidence of failed executions into the ledger
    whose entire job is to measure execution.
    """
    try:
        from backend.services.portfolio_intelligence import execution_ledger
        d = tmp_path_factory.mktemp("exec_ledger")
        monkeypatch.setattr(execution_ledger, "ROOT", d, raising=False)
    except Exception:                                            # noqa: BLE001
        pass
    yield


@pytest.fixture(scope="session", autouse=True)
def _disk_cache_to_tmp(tmp_path_factory):
    """Give the suite its own disk cache instead of the repo's live one.

    FOUND 2026-08-17, AND FOUND THE EMBARRASSING WAY. `backend/cache.py` keeps
    a diskcache at `<repo>/.cache`, shared by the running app and by pytest.
    Verifying `/api/risk-layer/exposure` by hand wrote a real 200 response into
    it, and `test_an_unpriceable_book_is_422...` — which patches the price
    fetch to raise — then got a cache HIT and its 200 back. The refusal test
    had been passing only because nobody had exercised the endpoint first.

    That is the same family as the wall-clock fixture repaired this morning: a
    test whose verdict depends on something outside the code under test reports
    a defect on a CIRCUMSTANCE rather than on a change. Here the circumstance is
    whether a human happened to call the endpoint, which is worse, because
    exercising the thing you just built is exactly what we tell ourselves to do.

    Session-scoped and switched at the module attribute, so nothing in the
    production cache path changes and no test can reach the tracked directory.
    """
    try:
        from backend import cache as _c
        d = tmp_path_factory.mktemp("diskcache")
        _c._CACHE_DIR = d
        _c._disk_cache = None          # force a lazy re-init against the tmp dir
        yield
        _c._disk_cache = None
    except Exception:                                            # noqa: BLE001
        yield


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

    # curl_cffi bypasses Python sockets entirely (libcurl via CFFI), so the two
    # patches above cannot see it — and yfinance 1.1.0 uses exactly that
    # transport. Patch its Session.request, which every curl_cffi entry point
    # (`requests.get`, `Session.get`, yfinance's pooled session) funnels through.
    # Wrapped in its own try/except ImportError because curl_cffi is a
    # transitive dependency: if a future yfinance drops it, the guard must
    # degrade to "socket-only" rather than erroring every test in the suite.
    _curl_patched = []
    try:
        from curl_cffi import requests as _curl_requests

        _real_curl_request = _curl_requests.Session.request

        def _guard_curl(self, method, url, *args, **kwargs):
            host = str(url).split("//")[-1].split("/")[0].split(":")[0]
            if host in _LOOPBACK:
                return _real_curl_request(self, method, url, *args, **kwargs)
            raise RuntimeError(_BLOCK_MESSAGE.format(target=url))

        _curl_requests.Session.request = _guard_curl
        _curl_patched.append((_curl_requests, _real_curl_request))
    except ImportError:
        pass

    try:
        yield
    finally:
        socket.socket.connect = _REAL_CONNECT
        socket.create_connection = _REAL_CREATE_CONNECTION
        for mod, real in _curl_patched:
            mod.Session.request = real
