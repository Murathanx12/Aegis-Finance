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

from backend.tests import ledger_guard

_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}

_BLOCK_MESSAGE = (
    "BLOCKED live network connect to {target!r} in a non-slow test. "
    "Unit tests must be offline — mark it @pytest.mark.slow (or .network) "
    "or mock the fetch. (This is the 2.5h-hang bug class.)"
)


#: Filled by `pytest_sessionstart`, read by `pytest_sessionfinish`. A plain
#: module dict rather than a fixture because the check has to bracket the WHOLE
#: run, including collection errors and tests in modules that were never
#: imported -- a session-scoped fixture only brackets the tests that request it.
_LEDGER_AT_START: dict = {}


def pytest_sessionstart(session):
    _LEDGER_AT_START.clear()
    _LEDGER_AT_START.update(ledger_guard.fingerprint())


def pytest_sessionfinish(session, exitstatus):
    """Fail the RUN (not a test) if the suite appended to the evidence ledger.

    See `backend/tests/ledger_guard.py` for the defect. It is a session hook
    rather than a test because the offending write can come from any test in
    any module, and the run's verdict is what has to change -- a green suite
    that dirtied a tracked 65 MB append-only ledger is not a green suite.
    """
    diffs = ledger_guard.differences(_LEDGER_AT_START, ledger_guard.fingerprint())
    if not diffs:
        return
    print("")
    print(ledger_guard.FAILURE_HEADER)
    for line in diffs:
        print("  " + line)
    session.exitstatus = 1


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


@pytest.fixture(scope="session")
def _exec_ledger_dir(tmp_path_factory):
    """ONE directory for the whole run, not one per test.

    `mktemp` inside a function-scoped autouse fixture runs for every test in
    the suite — 5,570 directories, and measurably: the full fast suite went
    from 8:46 to 14:37 when this fixture was added per-test. Redirecting a
    module constant needs a fresh patch per test, but it does not need a fresh
    directory, and nothing here reads what another test wrote (every test
    passes its own `root=`).
    """
    return tmp_path_factory.mktemp("exec_ledger")


@pytest.fixture(autouse=True)
def _execution_ledger_to_tmp(_exec_ledger_dir, monkeypatch):
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
        monkeypatch.setattr(execution_ledger, "ROOT", _exec_ledger_dir,
                            raising=False)
    except Exception:                                            # noqa: BLE001
        pass
    yield


@pytest.fixture(scope="session")
def _book_cadence_receipt_dir(tmp_path_factory):
    """ONE directory for the whole run — same reasoning as `_exec_ledger_dir`."""
    return tmp_path_factory.mktemp("book_cadence")


@pytest.fixture(autouse=True)
def _book_cadence_receipts_to_tmp(_book_cadence_receipt_dir, request, monkeypatch):
    """Keep the suite's cadence passes out of the repo's receipt directory.

    FOUND THE SAME WAY AS THE TWO ABOVE, on 2026-09-12, by reading `git status`
    after a full run: the Morning's `mark_books` step now calls
    `book_cadence.run_all()` in-process, so every test that clicks the Morning
    wrote five dated receipts into
    `backend/data/optimus/book_cadence/` — a directory whose whole purpose is to
    record what the real scheduler did on this machine. Receipts from a suite
    run are indistinguishable from receipts from a real pass once they are in
    there, which makes the directory useless for the thing it exists for.

    The module constant is a FUNCTION (`receipt_dir()`), so it is patched
    rather than reassigned; tests that want to inspect their own receipts patch
    it again with their own `tmp_path` and win, because monkeypatch applies in
    order.
    """
    try:
        from backend.services import book_cadence
        monkeypatch.setattr(book_cadence, "receipt_dir",
                            lambda: _book_cadence_receipt_dir, raising=False)
    except Exception:                                            # noqa: BLE001
        pass
    # AND THE DATABASE, for the same reason one layer down. A cadence pass with
    # no `db_path` opens the repo's real `aegis_pi.db`, where the machine's own
    # paper books live. Before any book existed that was a harmless "nothing to
    # do"; the moment one exists, a suite run MARKS A REAL FORWARD BOOK and
    # writes a NAV row nobody decided to write. Tests that pass their own `conn`
    # or `db_path` are untouched -- only the default is redirected.
    #
    # PER TEST, not per session, and the file name is derived from the node id
    # rather than from `mktemp`: a session-scoped book database leaks BOOKS
    # between tests, and a book created by one test is then marked by the next
    # test that clicks the Morning -- which is how two forecast rows about a
    # book that exists nowhere landed in the tracked `predictions.jsonl` on
    # 2026-09-12. Deriving the name costs nothing; `mktemp` per test cost this
    # suite six minutes the last time it was tried (see `_exec_ledger_dir`).
    try:
        import hashlib

        from backend.services import paper_books
        _real_conn = paper_books._conn
        key = hashlib.sha1(str(request.node.nodeid).encode()).hexdigest()[:16]
        db = _book_cadence_receipt_dir / f"aegis_pi_{key}.db"
        monkeypatch.setattr(
            paper_books, "_conn",
            lambda db_path=None: _real_conn(db_path if db_path is not None else db),
            raising=False)
    except Exception:                                            # noqa: BLE001
        pass
    # AND the forecast writer's default destination. Belt and braces: a test
    # that both creates a book AND clicks the Morning would otherwise append
    # real-looking `PredictionRecord`s about a synthetic book to the tracked
    # ledger, where nothing later could tell them from forecasts the machine
    # actually made. Only THIS writer is redirected -- every test that reads the
    # real ledger still reads it.
    try:
        from backend.services import book_forecasts
        monkeypatch.setattr(book_forecasts, "DEFAULT_LEDGER",
                            _book_cadence_receipt_dir / "predictions.jsonl",
                            raising=False)
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
