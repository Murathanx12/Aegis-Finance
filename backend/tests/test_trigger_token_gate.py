"""Job-starting and lane-changing routes are not public (S70, 2026-11-15).

The hosted backend answered ANYONE on `POST /api/optimus/run_job/{job_id}` (the
allow-listed `pi_daily_check` ends in the Alpaca PAPER mirror sync),
`POST /api/pi/trigger-check`, `POST /api/pi/replay/{lane_id}/refresh`, and
`GET /api/pi/reference/{lane_id}/state` ran a full rebalance check on a read.

(a) hosted settings, no token configured -> every gated route is a plain 404;
(b) a wrong, missing or too-short token -> the same 404, the supplied value is
    neither echoed nor logged;
(c) the right token -> the handler is reached (every job is a stub: no broker,
    no LLM, no network);
(d) the desktop app's own same-machine page is unchanged, and a foreign origin
    or a network peer on the desktop gets no free pass;
(e) the GET serves the open book and writes NOTHING without the token;
(f) structure, from the running app's route table and the handlers' AST (no
    source grep): every unsafe-method route is control-plane gated, trigger-token
    gated, or on a reviewed list; a handler that reaches the scheduler or a
    reference-engine writer without the gate fails.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
import sqlite3
import sys
import textwrap
import types

import pytest
from fastapi.testclient import TestClient

from backend import config as C
from backend.main import app
from backend.routers import control as CR
from backend.routers import portfolio_intelligence as PI
from backend.tests.local_control import LOCAL_BASE, local_client

TOKEN = "t0k-" + "s70-synthetic-trigger-token-for-tests"   # not a real credential
WRONG = "w0k-" + "s70-synthetic-wrong-value-for-tests-x"
HEADER = C.TRIGGER_TOKEN_HEADER

SCHEDULER_MODULE = "backend.services.portfolio_intelligence.scheduler"
ENGINE_MODULE = "backend.services.portfolio_intelligence.reference_engine"

#: (method, path) of every route that must carry `require_trigger_token`.
GATED_WRITES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/optimus/run_job/{job_id}"),
    ("POST", "/api/pi/trigger-check"),
    ("POST", "/api/pi/replay/{lane_id}/refresh"),
)
#: the same routes with concrete values the stubs below answer.
GATED_URLS: tuple[str, ...] = (
    "/api/optimus/run_job/pi_daily_check",
    "/api/optimus/run_job/pi_ledger_resolve",
    "/api/optimus/run_job/pi_hourly_mtm",
    "/api/optimus/run_job/pi_arena_daily",
    "/api/pi/trigger-check",
    "/api/pi/trigger-check?lane_id=conservative",
    "/api/pi/replay/conservative/refresh",
)

#: REVIEWED 2026-11-15. Every POST/PUT/PATCH/DELETE route that is deliberately
#: reachable without the control-plane gate or the trigger token. A NEW unsafe
#: route fails `test_every_write_route_is_gated_or_reviewed` until someone reads
#: its handler and either gates it or adds it here with the reason.
#:   compute  = takes the caller's own inputs, returns a calculation, stores nothing
#:   llm      = spends provider budget per call (rate limits live in the handler)
#:   journal  = appends to the owner's journal / decision log. PUBLIC WRITE, left
#:              as found because the website's own pages call it from the browser;
#:              reported to the owner as an open item, not judged safe here.
UNGATED_WRITE_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/portfolio/questionnaire"): "compute",
    ("POST", "/api/portfolio/guidance"): "compute",
    ("POST", "/api/portfolio/analyze"): "compute",
    ("POST", "/api/portfolio/project"): "compute",
    ("POST", "/api/portfolio/build"): "compute",
    ("POST", "/api/portfolio/optimize"): "compute",
    ("POST", "/api/portfolio/attribution"): "compute",
    ("POST", "/api/portfolio/risk-contributions"): "compute",
    ("POST", "/api/portfolio/commentary"): "llm",
    ("POST", "/api/portfolio/factor-exposures"): "compute",
    ("POST", "/api/portfolio/copula-risk"): "compute",
    ("POST", "/api/portfolio/benchmark"): "compute",
    ("POST", "/api/portfolio/compare"): "compute",
    ("POST", "/api/portfolio/optimize-mpc"): "compute",
    ("POST", "/api/portfolio/tearsheet.html"): "compute",
    ("POST", "/api/portfolio/currency-exposure"): "compute",
    ("POST", "/api/portfolio/tearsheet.xlsx"): "compute",
    ("POST", "/api/savings/project"): "compute",
    ("POST", "/api/savings/simulate"): "compute",
    ("POST", "/api/savings/safe-rate"): "compute",
    ("POST", "/api/analytics/factors/pca-residuals"): "compute",
    ("POST", "/api/analytics/factors/portfolio"): "compute",
    ("POST", "/api/analytics/stress-test"): "compute",
    ("POST", "/api/analytics/stress-test/hypothetical"): "compute",
    ("POST", "/api/analytics/copula/portfolio"): "compute",
    ("POST", "/api/analytics/allocation-backtest"): "compute",
    ("POST", "/api/copilot/chat"): "llm",
    ("POST", "/api/bond/analytics"): "compute",
    ("POST", "/api/bond/key-rate-durations"): "compute",
    ("POST", "/api/bond/ladder"): "compute",
    ("POST", "/api/pi/real-portfolio/analyze"): "compute",
    ("POST", "/api/risk-layer/exposure"): "compute",
    ("POST", "/api/pi/conviction/decision"): "journal",
    ("POST", "/api/pm/journal/record"): "journal",
    ("POST", "/api/pm/snapshot"): "journal",
    ("POST", "/api/journal/thesis"): "journal",
    ("POST", "/api/journal/resolve"): "journal",
    ("POST", "/api/journal/terminal-state/sync"): "journal",
}

#: Names a handler may take from the scheduler / reference engine WITHOUT the
#: gate. The scheduler names are status readers. `_ensure_lane_initialized` is
#: NOT a pure read (it creates a missing lane row); it is listed because two
#: public GETs called it before this change and were left as found -- reported.
READ_ONLY_NAMES: dict[str, frozenset[str]] = {
    SCHEDULER_MODULE: frozenset({"lppls_status", "overlay_status", "scheduler_health",
                                 "nav_freshness"}),
    ENGINE_MODULE: frozenset({"read_reference_state", "_ensure_lane_initialized"}),
}

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# ------------------------------------------------------------------ plumbing


def _leaf_routes(application) -> list:
    """Same enumeration as `test_control_plane_gate` (FastAPI wraps included routers)."""
    import fastapi.routing as fr
    if hasattr(fr, "iter_route_contexts"):
        return list(fr.iter_route_contexts(application.routes))
    return list(application.routes)


def _api_routes() -> list:
    return [r for r in _leaf_routes(app) if getattr(r, "dependant", None) is not None]


def _calls(dependant) -> list:
    out = [dependant.call]
    for sub in dependant.dependencies:
        out += _calls(sub)
    return out


def _gate_of(route) -> str:
    calls = _calls(route.dependant)
    if CR.control_plane_gate in calls:
        return "control-plane"
    if CR.require_trigger_token in calls:
        return "trigger-token"
    return "none"


def _handler_tree(fn) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(fn)))


def _reaches(fn) -> set[str]:
    """`module.name` for everything the handler takes from the scheduler or the
    reference engine: in-function imports, and module-level names it refers to.
    The scheduler MODULE itself (any alias) is reported as `<module>.*`."""
    watched = (SCHEDULER_MODULE, ENGINE_MODULE)
    tree = _handler_tree(fn)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in watched:
                found |= {f"{node.module}.{a.name}" for a in node.names}
            for a in node.names:
                if f"{node.module}.{a.name}" in watched:
                    found.add(f"{node.module}.{a.name}.*")
        elif isinstance(node, ast.Import):
            found |= {f"{a.name}.*" for a in node.names if a.name in watched}
        elif isinstance(node, ast.Name):
            obj = getattr(fn, "__globals__", {}).get(node.id)
            if isinstance(obj, types.ModuleType) and obj.__name__ in watched:
                found.add(f"{obj.__name__}.*")
            elif getattr(obj, "__module__", None) in watched and hasattr(obj, "__name__"):
                found.add(f"{obj.__module__}.{obj.__name__}")
    return found


def _unreviewed_reach(fn) -> set[str]:
    out = set()
    for full in _reaches(fn):
        module = SCHEDULER_MODULE if full.startswith(SCHEDULER_MODULE + ".") else ENGINE_MODULE
        name = full[len(module) + 1:]
        if name not in READ_ONLY_NAMES[module]:
            out.add(full)
    return out


def _asks_trigger_authorized(fn) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "trigger_authorized"
               and fn.__globals__.get("trigger_authorized") is CR.trigger_authorized
               for n in ast.walk(_handler_tree(fn)))


@pytest.fixture
def hosted(monkeypatch):
    """The website deployment: no desktop flag, no token configured."""
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)


@pytest.fixture
def stubs(monkeypatch) -> list[str]:
    """Every job behind the gated routes replaced by a recorder. Nothing real runs."""
    from backend import db as DB
    from backend.services.portfolio_intelligence import scheduler as S

    reached: list[str] = []

    def _job(name: str):
        async def _stub(*_a, **_k) -> None:
            reached.append(name)
        return _stub

    for name in ("_ledger_resolve", "_hourly_mtm", "_daily_check", "_arena_daily_pass",
                 "_arena_daily"):
        monkeypatch.setattr(S, name, _job(name))

    async def _manual(lane_id: str | None = None) -> dict:
        reached.append(f"manual_trigger:{lane_id}")
        return {"stub": True}

    def _invalidate(lane_id: str, *_a, **_k) -> None:
        reached.append(f"invalidate_replay_cache:{lane_id}")

    def _replay(lane_id: str, *_a, **_k):
        reached.append(f"_cached_replay:{lane_id}")
        raise ValueError("stub replay reached")        # the handler turns this into 400

    monkeypatch.setattr(S, "manual_trigger", _manual)
    monkeypatch.setattr(DB, "invalidate_replay_cache", _invalidate)
    monkeypatch.setattr(PI, "_cached_replay", _replay)
    return reached


def _reached_status(url: str) -> int:
    return 400 if url.endswith("/refresh") else 200


# ------------------------------------------------------------------ the names


def test_the_names_live_in_config():
    assert C.TRIGGER_TOKEN_ENV == "AEGIS_TRIGGER_TOKEN"
    assert C.TRIGGER_TOKEN_HEADER == "X-Aegis-Trigger-Token"
    assert C.TRIGGER_TOKEN_MIN_LENGTH >= 16
    assert len(TOKEN) >= C.TRIGGER_TOKEN_MIN_LENGTH and len(WRONG) == len(TOKEN)


def test_no_module_holds_the_token_value(monkeypatch):
    """Read at request time only: nothing imported keeps a copy to leak or go stale."""
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    TestClient(app).post("/api/pi/trigger-check", headers={HEADER: WRONG})
    for mod in (C, CR, PI, sys.modules["backend.routers.optimus_ledger"]):
        holders = [k for k, v in vars(mod).items() if isinstance(v, str) and v == TOKEN]
        assert not holders, (mod.__name__, holders)


# ------------------------------------------------------- (a) hosted, no token


@pytest.mark.parametrize("url", GATED_URLS)
def test_unset_token_is_a_plain_404_for_everyone(hosted, stubs, url):
    never = TestClient(app).post("/api/pi/__never_written__")
    assert never.status_code == 404
    for client in (TestClient(app), local_client(app)):
        for headers in ({}, {HEADER: ""}, {HEADER: TOKEN}, {HEADER: WRONG}):
            r = client.post(url, headers=headers)
            assert r.status_code == 404, (url, headers.keys(), r.status_code, r.text[:200])
            assert r.content == never.content, r.text[:200]
    assert stubs == [], stubs


@pytest.mark.parametrize("value", ["", "   ", "short", "x" * 23])
def test_an_empty_or_short_configured_token_is_not_a_token(hosted, stubs, monkeypatch, value):
    """Fail closed: `AEGIS_TRIGGER_TOKEN=` (or a guessable one) must not open the
    routes to a caller who sends the same empty or short header."""
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, value)
    c = TestClient(app)
    for url in GATED_URLS:
        for supplied in (value, value.strip(), ""):
            assert c.post(url, headers={HEADER: supplied}).status_code == 404, (url, value)
        assert c.post(url).status_code == 404, url
    assert stubs == [], stubs


# ------------------------------------------------- (b) wrong or missing token


@pytest.mark.parametrize("url", GATED_URLS)
def test_wrong_or_missing_token_is_404_and_is_not_echoed_or_logged(hosted, stubs, monkeypatch,
                                                                    caplog, url):
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    c = TestClient(app)
    never = c.post("/api/pi/__never_written__")
    with caplog.at_level(logging.DEBUG):
        attempts = [c.post(url),
                    c.post(url, headers={HEADER: WRONG}),
                    c.post(url, headers={HEADER: TOKEN[:-1]}),
                    c.post(url, headers={HEADER: TOKEN + "x"}),
                    c.post(url, headers={HEADER: TOKEN.upper()}),
                    c.post(url, headers={"Authorization": f"Bearer {TOKEN}"}),
                    c.post(url + ("&" if "?" in url else "?") + f"token={TOKEN}")]
    for r in attempts:
        assert r.status_code == 404, (url, r.status_code, r.text[:200])
        assert r.content == never.content
        assert WRONG not in r.text and TOKEN not in r.text
        assert all(WRONG not in v and TOKEN not in v for v in r.headers.values())
    # `httpx` is the TEST CLIENT logging its own request line (it prints the URL it
    # was asked to call); every server-side logger is in scope.
    logged = "\n".join(rec.getMessage() for rec in caplog.records if rec.name != "httpx")
    assert WRONG not in logged and TOKEN not in logged and TOKEN[:-1] not in logged
    assert stubs == [], stubs


def test_a_non_ascii_header_is_a_404_not_a_500(hosted, stubs, monkeypatch):
    """`hmac.compare_digest` raises on non-ASCII str; the gate compares bytes."""
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    from starlette.requests import Request
    req = Request({"type": "http", "method": "POST", "path": "/api/pi/trigger-check",
                   "headers": [(HEADER.lower().encode(), "töken-é".encode("latin-1"))],
                   "client": ("203.0.113.9", 5), "server": ("0.0.0.0", 8000),
                   "query_string": b""})
    assert CR.trigger_authorized(req) is False
    assert stubs == []


# ------------------------------------------------------------ (c) right token


@pytest.mark.parametrize("url", GATED_URLS)
def test_the_right_token_reaches_the_handler(hosted, stubs, monkeypatch, url):
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    r = TestClient(app).post(url, headers={HEADER: TOKEN})
    assert r.status_code == _reached_status(url), (url, r.status_code, r.text[:200])
    assert len(stubs) >= 1, (url, stubs)
    assert TOKEN not in r.text


def test_run_job_runs_the_named_job_and_only_that_one(hosted, stubs, monkeypatch):
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    c = TestClient(app, headers={HEADER: TOKEN})
    assert c.post("/api/optimus/run_job/pi_daily_check").json()["ran"] is True
    assert stubs == ["_daily_check"]
    # the arena repair stays the DECISION half: it never submits orders
    assert c.post("/api/optimus/run_job/pi_arena_daily").status_code == 200
    assert stubs == ["_daily_check", "_arena_daily_pass"]
    # an unknown job is still the handler's own 404, reached only with the token
    r = c.post("/api/optimus/run_job/not_a_job")
    assert r.status_code == 404 and "non-triggerable" in r.text
    assert stubs == ["_daily_check", "_arena_daily_pass"]


def test_trigger_check_and_refresh_pass_their_arguments_through(hosted, stubs, monkeypatch):
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    c = TestClient(app, headers={HEADER: TOKEN})
    assert c.post("/api/pi/trigger-check?lane_id=balanced").json() == {"stub": True}
    r = c.post("/api/pi/replay/aggressive/refresh")
    assert r.status_code == 400 and "stub replay reached" in r.text
    assert stubs == ["manual_trigger:balanced", "invalidate_replay_cache:aggressive",
                     "_cached_replay:aggressive"]


# ---------------------------------------------------------------- (d) desktop


@pytest.mark.parametrize("configured", [None, TOKEN])
@pytest.mark.parametrize("url", GATED_URLS)
def test_the_desktop_page_is_unchanged_and_needs_no_token(stubs, monkeypatch, url, configured):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    if configured is None:
        monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, configured)
    r = local_client(app).post(url)
    assert r.status_code == _reached_status(url), (url, r.status_code, r.text[:200])
    assert len(stubs) >= 1


@pytest.mark.parametrize("url", GATED_URLS)
def test_on_the_desktop_a_foreign_caller_gets_no_free_pass(stubs, monkeypatch, url):
    """Desktop mode is not a bypass by itself: the SAME same-machine test the
    control plane uses must pass. Otherwise the token rule applies (here: unset)."""
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    hostile = (
        TestClient(app),                                                  # Host: testserver
        local_client(app, headers={"Origin": "https://evil.example"}),
        local_client(app, headers={"Sec-Fetch-Site": "cross-site"}),
        TestClient(app, base_url="http://evil.example:8000"),
        TestClient(app, base_url=LOCAL_BASE, client=("192.168.1.20", 40000),
                   headers={"Content-Type": "application/json"}),
        TestClient(app, base_url=LOCAL_BASE, headers={"Content-Type": "text/plain"}),
    )
    for client in hostile:
        r = client.post(url)
        assert r.status_code == 404, (url, r.status_code, r.text[:200])
    assert stubs == [], stubs


def test_on_the_desktop_a_remote_caller_with_the_token_still_works(stubs, monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    r = TestClient(app).post("/api/pi/trigger-check", headers={HEADER: TOKEN})
    assert r.status_code == 200 and stubs == ["manual_trigger:None"]


# ------------------------------------------------- (e) the GET that used to write


LANE = "conservative"
STATE_URL = f"/api/pi/reference/{LANE}/state"


@pytest.fixture
def lane_db(tmp_path, monkeypatch):
    """A real schema with one open book, in a temp file `backend.db.DB_PATH` points at."""
    from backend import db as DB
    from backend.services.portfolio_intelligence import reference_engine as RE

    path = tmp_path / "pi.db"
    DB.init_db(path)
    conn = DB.get_connection(path)
    try:
        conn.execute("INSERT OR IGNORE INTO paper_portfolios (id, inception_date, inception_value, "
                     "config_version) VALUES (?, '2026-01-02', 100000.0, 'test')", (LANE,))
        conn.execute("DELETE FROM paper_positions WHERE portfolio_id = ?", (LANE,))
        conn.executemany(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at, "
            "closed_at) VALUES (?, ?, ?, ?, '2026-01-02T00:00:00', ?)",
            [(LANE, "AAA", 10.0, 100.0, None), (LANE, "BBB", 30.0, 100.0, None),
             (LANE, "OLD", 99.0, 100.0, "2026-02-01T00:00:00")])
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    monkeypatch.setattr(DB, "DB_PATH", path)
    priced: list[list[str]] = []

    def _prices(tickers: list[str]) -> dict[str, float]:
        priced.append(sorted(tickers))
        return {"AAA": 300.0}                           # BBB falls back to cost basis

    monkeypatch.setattr(RE, "_get_current_prices", _prices)
    return types.SimpleNamespace(path=path, priced=priced)


def _fingerprint(path) -> tuple[str, dict[str, int]]:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    return hashlib.sha256(dump.encode("utf-8")).hexdigest(), counts


@pytest.fixture
def no_check(monkeypatch) -> list[str]:
    """`run_reference_check` and every writer it uses, replaced by recorders."""
    from backend.services.portfolio_intelligence import reference_engine as RE
    from backend.schemas.portfolio_intelligence import SnapshotResponse

    called: list[str] = []

    def _check(lane_id: str, *_a, **_k) -> SnapshotResponse:
        called.append(f"run_reference_check:{lane_id}")
        return SnapshotResponse(portfolio_id=lane_id, date="2026-11-15", weights={"CHK": 1.0})

    def _writer(name: str):
        def _stub(*_a, **_k):
            called.append(name)
            raise AssertionError(f"{name} was called on a read")
        return _stub

    monkeypatch.setattr(RE, "run_reference_check", _check)
    for name in ("insert_audit_log", "insert_rebalance_event", "_apply_rebalance_positions",
                 "_ensure_lane_initialized", "initialize_lane"):
        monkeypatch.setattr(RE, name, _writer(name))
    return called


@pytest.mark.parametrize("headers", [{}, {HEADER: WRONG}, {HEADER: ""}])
@pytest.mark.parametrize("configured", [None, TOKEN])
def test_the_get_serves_the_book_and_writes_nothing_without_the_token(
        hosted, lane_db, no_check, monkeypatch, headers, configured):
    if configured is not None:
        monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, configured)
    before = _fingerprint(lane_db.path)
    r = TestClient(app).get(STATE_URL, headers=headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["portfolio_id"] == LANE and body["latest_rebalance"] is None
    # AAA 10 x 300 = 3000 (live), BBB 30 x 100 = 3000 (cost basis); the closed row is out
    assert body["weights"] == {"AAA": 0.5, "BBB": 0.5}
    assert lane_db.priced == [["AAA", "BBB"]]
    assert no_check == [], no_check
    assert _fingerprint(lane_db.path) == before
    assert WRONG not in r.text


def test_the_read_path_cannot_write_even_if_it_tried(lane_db):
    """The connection the read uses is SQLite read-only: 'no write' is enforced,
    not merely observed."""
    from backend.services.portfolio_intelligence import reference_engine as RE

    opened: list[tuple[str, dict]] = []
    real = sqlite3.connect

    def _spy(database, *a, **k):
        opened.append((str(database), dict(k)))
        return real(database, *a, **k)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sqlite3, "connect", _spy)
        out = RE.read_reference_state(LANE)
    assert out.weights == {"AAA": 0.5, "BBB": 0.5}
    assert len(opened) == 1, opened
    database, kwargs = opened[0]
    assert database.startswith("file:") and database.endswith("?mode=ro"), database
    assert kwargs.get("uri") is True, kwargs
    probe = sqlite3.connect(f"{lane_db.path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            probe.execute("INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, "
                          "opened_at) VALUES ('conservative', 'ZZZ', 1, 1, 'x')")
    finally:
        probe.close()
    src = ast.parse(textwrap.dedent(inspect.getsource(RE.read_reference_state)))
    called = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
              for n in ast.walk(src) if isinstance(n, ast.Call)}
    assert not called & {"init_db", "initialize_lane", "_ensure_lane_initialized", "get_connection",
                         "insert_audit_log", "insert_rebalance_event", "commit"}, called


def test_the_read_does_not_create_a_missing_database_or_table(tmp_path, monkeypatch, hosted, no_check):
    from backend import db as DB
    from backend.services.portfolio_intelligence import reference_engine as RE

    monkeypatch.setattr(RE, "_get_current_prices", lambda t: {})
    missing = tmp_path / "absent.db"
    monkeypatch.setattr(DB, "DB_PATH", missing)
    r = TestClient(app).get(STATE_URL)
    assert r.status_code == 200 and r.json()["weights"] == {}
    assert not missing.exists() and list(tmp_path.iterdir()) == []

    bare = tmp_path / "bare.db"
    sqlite3.connect(str(bare)).close()
    bare.write_bytes(b"")                                # a database with no tables
    monkeypatch.setattr(DB, "DB_PATH", bare)
    r = TestClient(app).get(STATE_URL)
    assert r.status_code == 200 and r.json()["weights"] == {}
    assert bare.read_bytes() == b"" and no_check == []


def test_the_get_still_runs_the_check_for_the_token_holder_and_the_desktop(
        lane_db, no_check, monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    r = TestClient(app).get(STATE_URL, headers={HEADER: TOKEN})
    assert r.status_code == 200 and r.json()["weights"] == {"CHK": 1.0}
    assert no_check == [f"run_reference_check:{LANE}"]

    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = local_client(app).get(STATE_URL)
    assert r.status_code == 200 and r.json()["weights"] == {"CHK": 1.0}
    assert no_check == [f"run_reference_check:{LANE}"] * 2
    # desktop flag, but not this machine's page -> the read, not the check
    r = TestClient(app).get(STATE_URL)
    assert r.status_code == 200 and r.json()["weights"] == {"AAA": 0.5, "BBB": 0.5}
    assert no_check == [f"run_reference_check:{LANE}"] * 2


def test_an_unknown_lane_is_still_the_handlers_404(hosted):
    r = TestClient(app).get("/api/pi/reference/not_a_lane/state")
    assert r.status_code == 404 and "Unknown lane" in r.text


# -------------------------------------------------------------- (f) structure


def test_the_enumeration_sees_the_app():
    """A walk that found nothing would make every structural test vacuous."""
    paths = {(m, r.path) for r in _api_routes() for m in (r.methods or set())}
    for must in GATED_WRITES + (("GET", "/api/pi/reference/{lane_id}/state"),
                                ("POST", "/api/control/run/{job}"), ("GET", "/api/health/full")):
        assert must in paths, must
    assert len(paths) >= 200, len(paths)


def test_the_named_routes_carry_the_dependency_first():
    by_key = {(m, r.path): r for r in _api_routes() for m in (r.methods or set())}
    for key in GATED_WRITES:
        route = by_key[key]
        assert _gate_of(route) == "trigger-token", key
        first = route.dependant.dependencies[0].call if route.dependant.dependencies else None
        assert first is CR.require_trigger_token, (key, first)


def test_every_write_route_is_gated_or_reviewed():
    """THE test a new write route lands on. Add a POST/PUT/PATCH/DELETE anywhere
    in the app and it fails here until the route is gated or reviewed."""
    ungated = {(m, r.path) for r in _api_routes()
               for m in (r.methods or set()) & UNSAFE if _gate_of(r) == "none"}
    new = sorted(ungated - set(UNGATED_WRITE_ROUTES))
    assert not new, (
        f"unsafe-method routes with no gate and no review: {new}. Read the handler: if it "
        "starts a job, calls a broker or changes lane state, add "
        "`dependencies=[Depends(require_trigger_token)]`; otherwise add it to "
        "UNGATED_WRITE_ROUTES with the reason.")
    stale = sorted(set(UNGATED_WRITE_ROUTES) - ungated)
    assert not stale, f"reviewed entries that are gone or now gated (remove them): {stale}"
    trigger = {(m, r.path) for r in _api_routes()
               for m in (r.methods or set()) & UNSAFE if _gate_of(r) == "trigger-token"}
    assert trigger == set(GATED_WRITES), sorted(trigger ^ set(GATED_WRITES))


def test_no_handler_reaches_the_scheduler_or_a_lane_writer_without_the_gate():
    """From each handler's AST and globals, every method (a GET did this until
    2026-11-15): taking the scheduler module, a job from it, or a reference-engine
    writer requires `require_trigger_token`, the control-plane gate, or an inline
    `trigger_authorized` branch."""
    offenders, seen = [], 0
    for r in _api_routes():
        fn = r.dependant.call
        reach = _unreviewed_reach(fn)
        if not reach:
            continue
        seen += 1
        if _gate_of(r) == "none" and not _asks_trigger_authorized(fn):
            offenders.append((sorted(r.methods or []), r.path, sorted(reach)))
    assert not offenders, offenders
    assert seen >= 3, f"the reach walk matched {seen} handlers; it has gone blind"


def test_the_reach_walk_catches_each_shape_it_claims_to():
    """The detector on synthetic handlers, so a refactor cannot silently blind it."""
    from backend.services.portfolio_intelligence import scheduler as _sched_alias

    globals()["_sched_alias"] = _sched_alias

    async def imports_the_module():
        from backend.services.portfolio_intelligence import scheduler as s
        return s

    async def imports_a_job():
        from backend.services.portfolio_intelligence.scheduler import manual_trigger
        return manual_trigger

    async def imports_a_writer():
        from backend.services.portfolio_intelligence.reference_engine import run_all_lanes
        return run_all_lanes

    async def uses_a_module_level_alias():
        return _sched_alias._daily_check

    async def reads_status_only():
        from backend.services.portfolio_intelligence.scheduler import scheduler_health
        from backend.services.portfolio_intelligence.reference_engine import read_reference_state
        return scheduler_health, read_reference_state

    async def docstring_only():
        """Mentions scheduler.manual_trigger and run_reference_check in prose only."""
        return "backend.services.portfolio_intelligence.scheduler"

    try:
        assert _unreviewed_reach(imports_the_module) == {f"{SCHEDULER_MODULE}.*"}
        assert _unreviewed_reach(imports_a_job) == {f"{SCHEDULER_MODULE}.manual_trigger"}
        assert _unreviewed_reach(imports_a_writer) == {f"{ENGINE_MODULE}.run_all_lanes"}
        assert _unreviewed_reach(uses_a_module_level_alias) == {f"{SCHEDULER_MODULE}.*"}
        assert _unreviewed_reach(reads_status_only) == set()
        assert _unreviewed_reach(docstring_only) == set()
        assert not _asks_trigger_authorized(docstring_only)
    finally:
        globals().pop("_sched_alias", None)
    assert _asks_trigger_authorized(PI.get_reference_state)
    assert f"{ENGINE_MODULE}.run_reference_check" in _unreviewed_reach(PI.get_reference_state)


def test_the_gate_is_one_function_beside_the_control_plane_gate():
    """One shared dependency, not a copy per router."""
    from backend.routers import optimus_ledger as OL
    assert OL.require_trigger_token is CR.require_trigger_token
    assert PI.require_trigger_token is CR.require_trigger_token
    assert PI.trigger_authorized is CR.trigger_authorized
    tree = ast.parse(textwrap.dedent(inspect.getsource(CR.trigger_authorized)))
    compares = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "compare_digest"]
    assert len(compares) == 1, "the token must be compared with hmac.compare_digest, once"
    equality = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)
                and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in n.ops)]
    assert not equality, "no ==/!= on the token path"
