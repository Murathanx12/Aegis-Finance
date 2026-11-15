"""Job-starting and lane-changing routes are not public (S70, 2026-11-15).

The hosted backend answered ANYONE on `POST /api/optimus/run_job/{job_id}` (the
allow-listed `pi_daily_check` ends in the Alpaca PAPER mirror sync),
`POST /api/pi/trigger-check`, `POST /api/pi/replay/{lane_id}/refresh`, and
`GET /api/pi/reference/{lane_id}/state` ran a full rebalance check on a read.
The review round added four journal/PM writes no page calls.

(a) hosted settings, no token configured -> every gated route is a plain 404;
(b) a wrong, missing, too-short or non-ASCII token -> the same 404, the supplied
    value is neither echoed nor logged;
(c) the right token -> the handler is reached (every job is a stub: no broker,
    no LLM, no network);
(d) the desktop app's own same-machine page is unchanged, and a foreign origin
    or a network peer on the desktop gets no free pass;
(e) the reference GETs serve what exists and write NOTHING without the token;
(f) structure. Two guards, and only the first is complete:
    1. ROUTE TABLE: every POST/PUT/PATCH/DELETE route of the running app is
       control-plane gated, trigger-token gated, or on a reviewed list, and
       nothing in the table is a Mount/WebSocket the walk cannot see.
    2. HANDLER AST (every method, because a GET did this): DIRECT reach of the
       scheduler, the reference engine, `services.morning` or the lane/replay
       writers of `backend.db` needs the gate or an `if trigger_authorized(...)`
       branch around it. "Direct" means: names and imports, attribute chains,
       `import_module`/`__import__`, and ONE level of helpers from the
       handler's own module. It does NOT see a helper's helper, reach through
       another service module, or `getattr` with a computed name
       (`test_what_the_reach_walk_does_not_see` pins that limit).
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
MORNING_MODULE = "backend.services.morning"
DB_MODULE = "backend.db"
#: every name of these three counts as reach unless READ_ONLY_NAMES lists it
FULL_WATCH: tuple[str, ...] = (SCHEDULER_MODULE, ENGINE_MODULE, MORNING_MODULE)
WATCHED: tuple[str, ...] = FULL_WATCH + (DB_MODULE,)
#: of `backend.db`, only the writers of paper-lane / replay state count
DB_WRITERS: frozenset[str] = frozenset({"invalidate_replay_cache", "insert_rebalance_event",
                                        "insert_audit_log", "insert_nav"})
#: an attribute chain on a root the walk cannot resolve still counts when it
#: passes through one of these names (`anything.scheduler.x`)
HEURISTIC_SEGMENTS: dict[str, str] = {"scheduler": SCHEDULER_MODULE,
                                      "reference_engine": ENGINE_MODULE}
DYNAMIC_IMPORT = "<dynamic import of a computed name>"

trigger_authorized = CR.trigger_authorized     # the synthetic handlers below call it by name

#: (method, path) of every route that must carry `require_trigger_token`.
GATED_WRITES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/optimus/run_job/{job_id}"),
    ("POST", "/api/pi/trigger-check"),
    ("POST", "/api/pi/replay/{lane_id}/refresh"),
    # review round 2026-11-15: journal / PM writes with no browser caller
    ("POST", "/api/pm/journal/record"),
    ("POST", "/api/pm/snapshot"),
    ("POST", "/api/journal/resolve"),
    ("POST", "/api/journal/terminal-state/sync"),
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
#: the review-round routes: (url, json body or None)
JOURNAL_GATED: tuple[tuple[str, dict | None], ...] = (
    ("/api/pm/journal/record", None),
    ("/api/pm/snapshot", None),
    ("/api/pm/snapshot?tickers=AAA,BBB", None),
    ("/api/journal/resolve", {"as_of": "2031-01-01", "reflect": True}),
    ("/api/journal/terminal-state/sync", None),
)

#: REVIEWED 2026-11-15. Every POST/PUT/PATCH/DELETE route that is deliberately
#: reachable without the control-plane gate or the trigger token. A NEW unsafe
#: route fails `test_every_write_route_is_gated_or_reviewed` until someone reads
#: its handler and either gates it or adds it here with the reason.
#:   compute  = takes the caller's own inputs, returns a calculation, stores nothing
#:   llm      = spends provider budget per call (rate limits live in the handler)
#:   journal  = appends to the owner's journal / decision log. PUBLIC WRITE, left
#:              open pending the owner's decision. `conviction/decision` is called
#:              by the website's conviction page; `journal/thesis` has no fetch
#:              caller in `frontend/` (the journal page only names it in text).
#:              Both take the server's clock and capped lists from an anonymous
#:              caller. Not judged safe here; reported as an open item.
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
    ("POST", "/api/journal/thesis"): "journal",
}

#: Names a handler may take from a fully watched module WITHOUT the gate: status
#: readers and the read-only lane readers. Nothing here writes.
READ_ONLY_NAMES: dict[str, frozenset[str]] = {
    SCHEDULER_MODULE: frozenset({"lppls_status", "overlay_status", "scheduler_health",
                                 "nav_freshness"}),
    ENGINE_MODULE: frozenset({"read_reference_state", "open_lane_readonly"}),
    MORNING_MODULE: frozenset(),
}

#: Everything in the route table that is NOT an API route, by path. All four are
#: FastAPI's own documentation pages (GET/HEAD only).
KNOWN_NON_API_ROUTES: frozenset[str] = frozenset({"/openapi.json", "/docs",
                                                  "/docs/oauth2-redirect", "/redoc"})

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


def _in_watched_tree(name: str) -> bool:
    """A watched module, or a package one of them lives in."""
    return name in WATCHED or any(w.startswith(name + ".") for w in WATCHED)


def _local_bindings(tree: ast.AST) -> dict[str, tuple]:
    """Names an in-function import binds to the watched tree."""
    out: dict[str, tuple] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                full, local = f"{node.module}.{a.name}", a.asname or a.name
                if _in_watched_tree(full):
                    out[local] = ("module", full)
                elif node.module in WATCHED:
                    out[local] = ("object", node.module, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                bound, target = (a.asname, a.name) if a.asname else (a.name.split(".")[0],) * 2
                if _in_watched_tree(target):
                    out[bound] = ("module", target)
    return out


def _resolve(name: str, local: dict[str, tuple], fn) -> tuple | None:
    if name in local:
        return local[name]
    obj = getattr(fn, "__globals__", {}).get(name)
    if isinstance(obj, types.ModuleType):
        return ("module", obj.__name__) if _in_watched_tree(obj.__name__) else None
    module = getattr(obj, "__module__", None)
    if module in WATCHED and getattr(obj, "__name__", None):
        return ("object", module, obj.__name__)
    if inspect.isfunction(obj) and module == fn.__module__ and obj is not fn:
        return ("helper", obj)
    return None


def _site_of(binding: tuple, attrs: list[str]) -> str | None:
    """`module.name` reached by a resolved root followed by an attribute chain."""
    if binding[0] == "object":
        return f"{binding[1]}.{binding[2]}"
    cur = binding[1]
    for attr in attrs:
        nxt = f"{cur}.{attr}"
        if _in_watched_tree(nxt):
            cur = nxt
        elif cur in WATCHED:
            return f"{cur}.{attr}"
        else:
            return None                                  # walked out of the watched tree
    return f"{cur}.*" if cur in WATCHED else None


def _is_auth_call(node: ast.AST, fn) -> bool:
    """A CALL of `control.trigger_authorized` (by name, or as `<control>.trigger_authorized`)."""
    if not isinstance(node, ast.Call):
        return False
    g = getattr(fn, "__globals__", {})
    f = node.func
    if isinstance(f, ast.Name):
        return g.get(f.id) is CR.trigger_authorized
    return (isinstance(f, ast.Attribute) and f.attr == "trigger_authorized"
            and isinstance(f.value, ast.Name) and g.get(f.value.id) is CR)


def _is_dynamic_import(node: ast.Call) -> bool:
    f = node.func
    return ((isinstance(f, ast.Name) and f.id in ("__import__", "import_module"))
            or (isinstance(f, ast.Attribute) and f.attr == "import_module"))


def _reach_sites(fn, _depth: int = 0) -> list[tuple[str, bool]]:
    """(`module.name`, guarded) for every USE of the watched tree in the handler.

    `guarded` is True only inside the TRUE branch of an `if` (or `x if c else y`)
    whose test is a call of `trigger_authorized`, or a name assigned from one.
    An import statement alone is not a use; the name it binds is, where it is
    loaded. One level of same-module helpers is followed (a helper's sites count
    at the place the helper is named)."""
    tree = _handler_tree(fn)
    local = _local_bindings(tree)
    auth_names = {t.id for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and _is_auth_call(n.value, fn)
                  for t in n.targets if isinstance(t, ast.Name)}
    sites: list[tuple[str, bool]] = []

    def add(binding: tuple, attrs: list[str], guarded: bool) -> None:
        if binding[0] == "helper":
            if _depth == 0:
                sites.extend((s, guarded or g) for s, g in _reach_sites(binding[1], 1))
            return
        site = _site_of(binding, attrs)
        if site:
            sites.append((site, guarded))

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return
        if isinstance(node, (ast.If, ast.IfExp)):
            visit(node.test, guarded)
            authorised = _is_auth_call(node.test, fn) or (
                isinstance(node.test, ast.Name) and node.test.id in auth_names)
            for child in (node.body if isinstance(node.body, list) else [node.body]):
                visit(child, guarded or authorised)
            for child in (node.orelse if isinstance(node.orelse, list) else [node.orelse]):
                visit(child, guarded)
            return
        if isinstance(node, ast.Call) and _is_dynamic_import(node):
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                hit = next((m for m in WATCHED
                            if arg.value == m or arg.value.startswith(m + ".")), None)
                if hit:
                    sites.append((f"{hit}.*", guarded))
            else:
                sites.append((DYNAMIC_IMPORT, guarded))
        if isinstance(node, ast.Attribute):
            root, attrs = node, []
            while isinstance(root, ast.Attribute):
                attrs.append(root.attr)
                root = root.value
            attrs.reverse()
            binding = _resolve(root.id, local, fn) if isinstance(root, ast.Name) else None
            if binding is not None:
                add(binding, attrs, guarded)
                return
            segment = next((a for a in attrs if a in HEURISTIC_SEGMENTS), None)
            if segment:
                sites.append((f"{HEURISTIC_SEGMENTS[segment]}.*", guarded))
            if not isinstance(root, ast.Name):
                visit(root, guarded)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            binding = _resolve(node.id, local, fn)
            if binding is not None:
                add(binding, [], guarded)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(tree, False)
    return sites


def _counts(site: str) -> bool:
    """Is this site something a public handler must not reach ungated?"""
    if site == DYNAMIC_IMPORT:
        return True
    module = next(m for m in WATCHED if site.startswith(m + "."))
    name = site[len(module) + 1:]
    if name == "*":
        return True
    if module == DB_MODULE:
        return name in DB_WRITERS
    return name not in READ_ONLY_NAMES[module]


def _unreviewed_reach(fn) -> set[str]:
    return {s for s, _ in _reach_sites(fn) if _counts(s)}


def _unguarded_reach(fn) -> set[str]:
    """The reach that is NOT inside an `if trigger_authorized(...)` true branch."""
    return {s for s, guarded in _reach_sites(fn) if _counts(s) and not guarded}


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

    # review round: the journal / PM writes. Every service call is a recorder.
    from backend.routers import journal as J
    from backend.routers import pm as PM

    def _rec(name: str, value):
        def _stub(*a, **k):
            reached.append(name if not a or not isinstance(a[0], str) else f"{name}:{a[0]}")
            return value
        return _stub

    monkeypatch.setattr(PM, "daily", _rec("pm.daily", {"stub": True}))
    monkeypatch.setattr(PM.pm_journal, "record_brief", _rec("pm_journal.record_brief", {"ok": 1}))
    monkeypatch.setattr(PM.pm_engine, "load_book", _rec(
        "pm_engine.load_book", types.SimpleNamespace(positions=[], watchlist=[])))
    monkeypatch.setattr(PM.pm_engine, "enrich", _rec("pm_engine.enrich",
                                                     {"market_data_status": "stub"}))
    monkeypatch.setattr(PM.analyst_ledger, "snapshot_if_new", _rec("snapshot_if_new", None))
    monkeypatch.setattr(PM.analyst_ledger, "coverage", _rec("coverage", {}))
    monkeypatch.setattr(J.dl, "load_decisions", _rec("dl.load_decisions", []))
    monkeypatch.setattr(J.dl, "load_grades", _rec("dl.load_grades", []))
    monkeypatch.setattr(J.dl, "record_grade", _rec("dl.record_grade", None))
    monkeypatch.setattr(J.dl, "reflect", _rec("dl.reflect", {}))
    monkeypatch.setattr(J.tsr, "sync", _rec("tsr.sync", {"copied": 0, "artefacts": []}))
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


@pytest.mark.parametrize("value", ["t\u00f6ken-" + "x" * 30, "\u2713" * 30, "tok\u00e9n" * 8])
def test_a_non_ascii_configured_token_is_not_a_token(hosted, stubs, monkeypatch, value):
    """A header arrives latin-1 decoded, so such a value could never match. It
    counts as unset (fail closed) however the caller encodes its guess."""
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, value)
    assert CR.trigger_token_status() == "non_ascii"
    assert CR._configured_trigger_token() is None
    c = TestClient(app)
    for url in GATED_URLS:
        assert c.post(url).status_code == 404
        for raw in (value.encode("utf-8"), value.encode("utf-8", "ignore").decode("latin-1")
                    .encode("latin-1", "ignore")):
            assert c.post(url, headers={HEADER.encode(): raw}).status_code == 404, url
    assert stubs == [], stubs


@pytest.mark.parametrize("value,status,level", [
    (None, "unset", logging.INFO), ("", "unset", logging.INFO),
    ("short-value", "too_short", logging.WARNING),
    ("t\u00f6ken-" + "x" * 30, "non_ascii", logging.WARNING),
    (TOKEN, "configured", logging.INFO)])
def test_the_startup_line_names_the_variable_and_never_the_value(monkeypatch, caplog, value,
                                                                 status, level):
    if value is None:
        monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, value)
    with caplog.at_level(logging.DEBUG, logger=CR.__name__):
        assert CR.log_trigger_token_status() == status
    lines = [r for r in caplog.records if r.name == CR.__name__]
    assert len(lines) == 1 and lines[0].levelno == level, [r.getMessage() for r in lines]
    text = lines[0].getMessage()
    assert C.TRIGGER_TOKEN_ENV in text
    if value:
        assert value not in text and value[:8] not in text


def test_the_startup_line_is_called_from_the_lifespan():
    """From the AST of `main.lifespan`, not from its text."""
    import backend.main as M
    calls = [n for n in ast.walk(_handler_tree(M.lifespan)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "log_trigger_token_status"]
    assert len(calls) == 1 and M.control.log_trigger_token_status is CR.log_trigger_token_status


# --------------------------------------------- the review round: journal / PM


@pytest.mark.parametrize("url,body", JOURNAL_GATED)
def test_journal_writes_are_404_without_the_token(hosted, stubs, monkeypatch, url, body):
    never = TestClient(app).post("/api/pm/__never_written__")
    kw = {"json": body} if body is not None else {}
    for client in (TestClient(app), local_client(app)):
        assert client.post(url, **kw).content == never.content        # token not configured
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    for headers in ({}, {HEADER: WRONG}, {HEADER: TOKEN[:-1]}):
        r = TestClient(app).post(url, headers=headers, **kw)
        assert r.status_code == 404 and r.content == never.content, (url, r.text[:200])
    assert stubs == [], stubs


@pytest.mark.parametrize("url,body", JOURNAL_GATED)
def test_journal_writes_reach_the_handler_with_the_token_or_on_the_desktop(
        stubs, monkeypatch, url, body):
    kw = {"json": body} if body is not None else {}
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    r = TestClient(app).post(url, headers={HEADER: TOKEN}, **kw)
    assert r.status_code == 200 and stubs, (url, r.status_code, r.text[:300])
    n = len(stubs)
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = local_client(app).post(url, **kw)
    assert r.status_code == 200 and len(stubs) > n, (url, r.status_code, r.text[:300])


def test_pm_snapshot_caps_a_supplied_ticker_list(stubs, monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    c = TestClient(app, headers={HEADER: TOKEN})
    cap = C.PM_SNAPSHOT_MAX_TICKERS
    over = ",".join(f"T{i}" for i in range(cap + 1))
    r = c.post("/api/pm/snapshot", params={"tickers": over})
    assert r.status_code == 422 and "PM_SNAPSHOT_MAX_TICKERS" in r.text
    assert stubs == [], "the cap must refuse before any fetch"
    at = ",".join(f"T{i}" for i in range(cap))
    assert c.post("/api/pm/snapshot", params={"tickers": at}).status_code == 200
    assert sum(1 for s in stubs if s.startswith("pm_engine.enrich")) == cap


def test_the_open_conviction_write_caps_its_lists(hosted, monkeypatch):
    """Still open (owner's decision pending); an anonymous caller's lists are capped.
    Refused by validation, so nothing is written and nothing needs stubbing."""
    cap = C.PUBLIC_WRITE_MAX_LIST_ITEMS
    base = {"ticker": "AAA", "action": "enter", "shares_delta": 1, "price": 1.0,
            "rationale": "x" * 60, "conviction": 3}
    c = TestClient(app)
    for field in ("thesis_tags", "catalyst_dates"):
        r = c.post("/api/pi/conviction/decision", json={**base, field: ["2031-01-01"] * (cap + 1)})
        assert r.status_code == 422 and field in r.text, (field, r.status_code, r.text[:200])
    fields = PI.ConvictionDecisionRequest.model_fields
    for field in ("thesis_tags", "catalyst_dates"):
        caps = [m.max_length for m in fields[field].metadata if hasattr(m, "max_length")]
        assert caps == [cap], (field, caps)
    PI.ConvictionDecisionRequest(**base, thesis_tags=["t"] * cap)       # at the cap: accepted


def test_the_conviction_write_takes_no_timestamp_from_the_caller():
    """`personal_decisions.timestamp` is the server's clock for everyone: the model
    has no field a caller could set it with, and the handler passes its own."""
    assert not {"timestamp", "ts", "created_at", "as_of", "stated_at_utc"} & set(
        PI.ConvictionDecisionRequest.model_fields)


@pytest.fixture
def thesis_calls(monkeypatch) -> list[dict]:
    from backend.routers import journal as J

    seen: list[dict] = []

    def _build(**kw):
        seen.append(kw)
        return types.SimpleNamespace(stated_at_utc=kw.get("stated_at_utc"))

    monkeypatch.setattr(J.ht, "build", _build)
    monkeypatch.setattr(J.ht, "record", lambda t, decision_id=None: {"sealed": True})
    monkeypatch.setattr(J.ht, "export_for_seal", lambda t: {})
    monkeypatch.setattr(J.dl, "from_thesis", lambda t, **k: {"row": True})
    monkeypatch.setattr(J.dl, "record_decision", lambda row: {"decision_id": 1})
    return seen


THESIS = {"symbol": "AAA", "direction": "up", "catalyst": "synthetic catalyst",
          "catalyst_at_utc": "2031-01-01T00:00:00+00:00", "reason": "a synthetic reason",
          "falsifier": "a synthetic falsifier text", "expected_move": 0.05}
BACKDATE = "2020-01-01T00:00:00+00:00"


def test_an_anonymous_thesis_cannot_choose_when_it_was_stated(hosted, thesis_calls, monkeypatch):
    c = TestClient(app)
    r = c.post("/api/journal/thesis", json={**THESIS, "stated_at_utc": BACKDATE})
    assert r.status_code == 200, r.text[:300]
    assert thesis_calls[-1]["stated_at_utc"] is None            # -> the service's own now()
    assert "ignored" in r.json()["stated_at_source"] and BACKDATE not in r.text
    r = c.post("/api/journal/thesis", json=THESIS)              # the ordinary page-shaped call
    assert r.status_code == 200 and r.json()["stated_at_source"] == "server clock"
    # a wrong token is an anonymous caller
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    c.post("/api/journal/thesis", json={**THESIS, "stated_at_utc": BACKDATE},
           headers={HEADER: WRONG})
    assert thesis_calls[-1]["stated_at_utc"] is None


def test_the_token_holder_and_the_desktop_keep_stated_at(thesis_calls, monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
    r = TestClient(app).post("/api/journal/thesis", json={**THESIS, "stated_at_utc": BACKDATE},
                             headers={HEADER: TOKEN})
    assert r.status_code == 200 and thesis_calls[-1]["stated_at_utc"] == BACKDATE
    assert r.json()["stated_at_source"] == "caller"
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = local_client(app).post("/api/journal/thesis", json={**THESIS, "stated_at_utc": BACKDATE})
    assert r.status_code == 200 and thesis_calls[-1]["stated_at_utc"] == BACKDATE


def test_the_gated_routes_are_not_in_the_public_schema(hosted):
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    listed = [(m, p) for m, p in GATED_WRITES if m.lower() in paths.get(p, {})]
    assert not listed, listed
    assert "post" in paths["/api/journal/thesis"] and "post" in paths["/api/pi/conviction/decision"]


# ------------------------------------------- the in-process peer literal (item 7)


def _scope(peer: str, extensions: dict | None) -> dict:
    scope = {"type": "http", "method": "POST", "path": "/api/pi/trigger-check",
             "headers": [(b"host", b"127.0.0.1:8000"), (b"content-type", b"application/json")],
             "client": (peer, 40000), "server": ("127.0.0.1", 8000), "query_string": b""}
    if extensions is not None:
        scope["extensions"] = extensions
    return scope


def test_the_testclient_peer_name_counts_only_on_an_in_process_scope(monkeypatch):
    """Behind a proxy uvicorn trusts, `X-Forwarded-For: testclient` becomes the
    peer. A socket server's scope has no TestClient marker, so the name alone
    opens nothing: not the control plane, not the trigger routes."""
    from starlette.requests import Request

    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    for extensions in (None, {}, {"http.response.trailers": {}}):       # what a server sends
        req = Request(_scope(CR.IN_PROCESS_CLIENT, extensions))
        assert CR._client_is_loopback(req) is False
        assert CR.trigger_authorized(req) is False
        with pytest.raises(Exception) as exc:
            CR.control_plane_gate(req)
        assert getattr(exc.value, "status_code", None) == 403
    in_process = Request(_scope(CR.IN_PROCESS_CLIENT, {CR.IN_PROCESS_SCOPE_MARKER: {}}))
    assert CR._client_is_loopback(in_process) and CR.trigger_authorized(in_process)
    # a real loopback socket needs no marker
    assert CR._client_is_loopback(Request(_scope("127.0.0.1", None)))


def test_the_real_testclient_still_carries_the_marker(monkeypatch):
    """If Starlette drops the extension, every in-process caller is refused. This
    is the test that says so first, by name."""
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    assert local_client(app).get("/api/control/jobs").status_code == 200


def test_the_container_pins_the_forwarded_allow_list():
    """`backend/Dockerfile` starts uvicorn; its last CMD must trust only loopback
    for forwarded headers, whatever FORWARDED_ALLOW_IPS says."""
    import shlex
    from pathlib import Path

    lines = (Path(CR.__file__).resolve().parents[1] / "Dockerfile").read_text(
        encoding="utf-8").splitlines()
    cmds = [ln for ln in lines if ln.strip().startswith("CMD ")]
    assert cmds, "no CMD in backend/Dockerfile"
    argv = shlex.split(cmds[-1].strip()[4:])
    assert argv[0] == "uvicorn", argv
    assert argv.count("--forwarded-allow-ips") == 1
    assert argv[argv.index("--forwarded-allow-ips") + 1] == "127.0.0.1", argv


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


HISTORY_URL = f"/api/pi/reference/{LANE}/history"
EXPLAIN_URL = f"/api/pi/reference/{LANE}/explain"


@pytest.fixture
def no_seed(monkeypatch) -> list[str]:
    """Every way a read could create a lane, replaced by a recorder that raises."""
    from backend import db as DB
    from backend.services.portfolio_intelligence import reference_engine as RE

    called: list[str] = []

    def _writer(name: str):
        def _stub(*_a, **_k):
            called.append(name)
            raise AssertionError(f"{name} was called on a read")
        return _stub

    for name in ("_ensure_lane_initialized", "initialize_lane", "insert_audit_log",
                 "insert_rebalance_event"):
        monkeypatch.setattr(RE, name, _writer(name))
    monkeypatch.setattr(DB, "init_db", _writer("init_db"))
    return called


@pytest.mark.parametrize("mode", ["anonymous", "token", "desktop"])
def test_history_and_explain_never_seed_a_lane(tmp_path, monkeypatch, no_seed, mode):
    """A lane with NO ROW: the empty shape for everyone, and no row afterwards.
    No page calls these two routes (the frontend helpers have no caller), so
    nobody keeps the old seed-on-read behaviour, token or not."""
    from backend import db as DB

    path = tmp_path / "pi.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE paper_portfolios (id TEXT PRIMARY KEY, inception_date TEXT, "
        "inception_value REAL, config_version TEXT);"
        "CREATE TABLE rebalance_events (id INTEGER PRIMARY KEY, portfolio_id TEXT, "
        "triggered_at TEXT, trigger_reason TEXT, crash_prob_3m REAL, explanation TEXT, "
        "post_weights TEXT);")
    conn.commit()
    conn.close()
    monkeypatch.setattr(DB, "DB_PATH", path)
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    monkeypatch.delenv(C.TRIGGER_TOKEN_ENV, raising=False)
    client, headers = TestClient(app), {}
    if mode == "token":
        monkeypatch.setenv(C.TRIGGER_TOKEN_ENV, TOKEN)
        headers = {HEADER: TOKEN}
    elif mode == "desktop":
        monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
        client = local_client(app)
    before = _fingerprint(path)

    r = client.get(HISTORY_URL, headers=headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["portfolio_id"] == LANE and body["period"] == "1Y"
    assert body["equity_curve"] == [] and body["rebalance_log"] == []
    assert body["has_nav_data"] is False and body["has_rebalance_events"] is False
    assert body["inception_date"] is None and body["inception_value"] is None

    r = client.get(EXPLAIN_URL, headers=headers)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["has_rebalance_events"] is False and r.json()["last_rebalance_date"] is None

    assert no_seed == [], no_seed
    assert _fingerprint(path) == before
    assert before[1]["paper_portfolios"] == 0


def test_history_and_explain_do_not_create_a_missing_database(tmp_path, monkeypatch, hosted,
                                                              no_seed):
    from backend import db as DB

    missing = tmp_path / "absent.db"
    monkeypatch.setattr(DB, "DB_PATH", missing)
    c = TestClient(app)
    assert c.get(HISTORY_URL).json()["has_nav_data"] is False
    assert c.get(EXPLAIN_URL).json()["has_rebalance_events"] is False
    assert not missing.exists() and list(tmp_path.iterdir()) == [] and no_seed == []


def test_history_and_explain_still_serve_a_lane_that_exists(lane_db, hosted, no_seed):
    """The real schema with a seeded lane: the same data as before, read-only."""
    from backend import db as DB

    conn = DB.get_connection(lane_db.path)
    try:
        DB.insert_rebalance_event(conn, LANE, "2026-11-10T00:00:00", "scheduled", {}, {"AAA": 1.0},
                                  0.1, "calm", "synthetic explanation", config_version="test")
        DB.insert_nav(conn, LANE, "2026-11-10", 100500.0, "test", "2026-11-10T21:00:00")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    before = _fingerprint(lane_db.path)
    c = TestClient(app)
    h = c.get(HISTORY_URL, params={"period": "ALL"}).json()
    assert h["inception_date"] == "2026-01-02" and h["inception_value"] == 100000.0
    assert [p["value"] for p in h["equity_curve"]] == [100500.0] and h["has_nav_data"] is True
    assert [e["reason"] for e in h["rebalance_log"]] == ["scheduled"]
    e = c.get(EXPLAIN_URL).json()
    assert e["explanation"] == "synthetic explanation" and e["last_rebalance_date"] == "2026-11-10"
    assert _fingerprint(lane_db.path) == before and no_seed == []


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


def test_nothing_in_the_route_table_is_invisible():
    """`_api_routes` keeps what has a `dependant`. A Mount, a WebSocket route or a
    plain Starlette route has none and would hide a whole sub-application from
    every test here. So: each entry of `app.routes`, and each leaf, is an
    `APIRoute`, FastAPI's included-router wrapper, or one of the four docs pages."""
    from fastapi.routing import APIRoute
    from starlette.routing import Mount, Route, WebSocketRoute

    def _doc_page(route) -> bool:
        return (type(route) is Route and route.path in KNOWN_NON_API_ROUTES
                and set(route.methods or ()) <= {"GET", "HEAD"})

    strangers = []
    for r in app.routes:
        if isinstance(r, (Mount, WebSocketRoute)):
            strangers.append(("top", type(r).__name__, getattr(r, "path", None)))
        elif not (isinstance(r, APIRoute) or _doc_page(r)
                  or type(r).__name__ == "_IncludedRouter"):
            strangers.append(("top", type(r).__name__, getattr(r, "path", None)))
    seen_docs = set()
    for leaf in _leaf_routes(app):
        route = getattr(leaf, "original_route", leaf)
        if isinstance(route, APIRoute):
            assert getattr(leaf, "dependant", None) is not None, leaf.path
        elif _doc_page(route):
            seen_docs.add(route.path)
        else:
            strangers.append(("leaf", type(route).__name__, getattr(route, "path", None)))
    assert not strangers, (
        f"route-table entries no test here can see into: {strangers}. A Mount or WebSocket "
        "must be reviewed and named in KNOWN_NON_API_ROUTES (with its own gate test).")
    assert seen_docs == set(KNOWN_NON_API_ROUTES), seen_docs ^ set(KNOWN_NON_API_ROUTES)
    n_api = sum(1 for leaf in _leaf_routes(app)
                if isinstance(getattr(leaf, "original_route", leaf), APIRoute))
    assert n_api == len(_api_routes()), (n_api, len(_api_routes()))


def test_the_invisible_route_check_catches_a_mount_and_a_websocket():
    """The detector on a synthetic app: it must name both."""
    from fastapi import FastAPI
    from starlette.routing import Mount, WebSocketRoute

    synthetic = FastAPI()
    synthetic.mount("/static", FastAPI())

    @synthetic.websocket("/ws")
    async def _ws(websocket) -> None:                      # pragma: no cover - never connected
        return None

    kinds = {type(getattr(leaf, "original_route", leaf)).__name__
             for leaf in _leaf_routes(synthetic)} | {type(r).__name__ for r in synthetic.routes}
    assert any(isinstance(r, Mount) for r in synthetic.routes), kinds
    assert any(isinstance(r, WebSocketRoute) or "WebSocket" in type(r).__name__
               for r in synthetic.routes), kinds


def test_the_named_routes_carry_the_dependency_first():
    by_key = {(m, r.path): r for r in _api_routes() for m in (r.methods or set())}
    for key in GATED_WRITES:
        route = by_key[key]
        assert _gate_of(route) == "trigger-token", key
        first = route.dependant.dependencies[0].call if route.dependant.dependencies else None
        assert first is CR.require_trigger_token, (key, first)


def test_every_write_route_is_gated_or_reviewed():
    """THE test a new write route lands on. Add a POST/PUT/PATCH/DELETE anywhere
    in the app and it fails here until the route is gated or reviewed. This is
    the complete guard; the AST walk below is the incomplete one."""
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
    """Every method (a GET did this until 2026-11-15). DIRECT reach, as defined in
    the module docstring, needs `require_trigger_token`, the control-plane gate,
    or to sit inside the true branch of `if trigger_authorized(...)`."""
    offenders, seen = [], 0
    for r in _api_routes():
        fn = r.dependant.call
        if not _unreviewed_reach(fn):
            continue
        seen += 1
        if _gate_of(r) == "none" and _unguarded_reach(fn):
            offenders.append((sorted(r.methods or []), r.path, sorted(_unguarded_reach(fn))))
    assert not offenders, offenders
    assert seen >= 4, f"the reach walk matched {seen} handlers; it has gone blind"


def test_the_walk_sees_the_real_handlers_it_should():
    from backend.routers import optimus_ledger as OL

    assert _unreviewed_reach(OL.run_job_now) >= {
        f"{SCHEDULER_MODULE}._daily_check", f"{SCHEDULER_MODULE}._arena_daily_pass"}
    assert _unreviewed_reach(PI.trigger_check) == {f"{SCHEDULER_MODULE}.manual_trigger"}
    assert f"{DB_MODULE}.invalidate_replay_cache" in _unreviewed_reach(PI.refresh_replay)
    assert _unreviewed_reach(PI.get_reference_state) == {f"{ENGINE_MODULE}.run_reference_check"}
    assert _unguarded_reach(PI.get_reference_state) == set()
    # the two reads that used to seed a lane now take only a reviewed reader
    assert _unreviewed_reach(PI.get_reference_history) == set()
    assert _unreviewed_reach(PI.get_reference_explain) == set()
    assert "_ensure_lane_initialized" not in READ_ONLY_NAMES[ENGINE_MODULE]


# The synthetic handlers. Never called: only their AST and globals are read.


def _helper_that_reaches():
    from backend.services.portfolio_intelligence import scheduler as s
    return s.manual_trigger


def _helper_of_a_helper():
    return _helper_that_reaches()


async def _h_imports_the_module():
    from backend.services.portfolio_intelligence import scheduler as s
    return s


async def _h_imports_a_job():
    from backend.services.portfolio_intelligence.scheduler import manual_trigger
    return manual_trigger


async def _h_imports_a_writer():
    from backend.services.portfolio_intelligence.reference_engine import run_all_lanes
    return run_all_lanes()


async def _h_via_one_helper():
    return _helper_that_reaches()


async def _h_import_module():
    import importlib
    return importlib.import_module("backend.services.portfolio_intelligence.scheduler")


async def _h_dunder_import():
    return __import__("backend.services.portfolio_intelligence.reference_engine")


async def _h_import_module_computed(name: str):
    from importlib import import_module
    return import_module("backend.services." + name)


async def _h_import_module_of_the_package():
    import importlib
    return importlib.import_module("backend.services.portfolio_intelligence").scheduler._daily_check


async def _h_other_service():
    from backend.services import morning
    return morning.run_all_lanes()


async def _h_other_service_by_name():
    from backend.services.morning import run_all_lanes
    return run_all_lanes()


async def _h_db_writer_by_name():
    from backend.db import invalidate_replay_cache
    return invalidate_replay_cache("conservative")


async def _h_db_writer_by_module():
    from backend import db as DB
    conn = DB.get_connection()
    return DB.insert_nav(conn, "conservative", "2026-01-01", 1.0)


async def _h_db_reader_only():
    from backend import db as DB
    from backend.db import get_nav_series
    return get_nav_series(DB.get_connection(), "conservative")


async def _h_package_alias_import():
    import backend.services.portfolio_intelligence as p
    return p.scheduler.manual_trigger


async def _h_package_from_import():
    from backend.services import portfolio_intelligence as p
    return p.reference_engine.run_all_lanes


async def _h_dotted_import():
    import backend.services.portfolio_intelligence.scheduler
    return backend.services.portfolio_intelligence.scheduler._daily_check


async def _h_unresolvable_root(anything):
    return anything.scheduler.manual_trigger


async def _h_reads_status_only():
    from backend.services.portfolio_intelligence.scheduler import scheduler_health
    from backend.services.portfolio_intelligence.reference_engine import read_reference_state
    return scheduler_health, read_reference_state


async def _h_docstring_only():
    """Mentions scheduler.manual_trigger, run_reference_check and trigger_authorized in prose."""
    return "backend.services.portfolio_intelligence.scheduler"


async def _h_import_never_used():
    from backend.services.portfolio_intelligence.scheduler import manual_trigger  # noqa: F401
    return None


REACH_SHAPES = [
    (_h_imports_the_module, {f"{SCHEDULER_MODULE}.*"}),
    (_h_imports_a_job, {f"{SCHEDULER_MODULE}.manual_trigger"}),
    (_h_imports_a_writer, {f"{ENGINE_MODULE}.run_all_lanes"}),
    (_h_via_one_helper, {f"{SCHEDULER_MODULE}.manual_trigger"}),
    (_h_import_module, {f"{SCHEDULER_MODULE}.*"}),
    (_h_dunder_import, {f"{ENGINE_MODULE}.*"}),
    (_h_import_module_computed, {DYNAMIC_IMPORT}),
    (_h_import_module_of_the_package, {f"{SCHEDULER_MODULE}.*"}),
    (_h_other_service, {f"{MORNING_MODULE}.run_all_lanes"}),
    (_h_other_service_by_name, {f"{MORNING_MODULE}.run_all_lanes"}),
    (_h_db_writer_by_name, {f"{DB_MODULE}.invalidate_replay_cache"}),
    (_h_db_writer_by_module, {f"{DB_MODULE}.insert_nav"}),
    (_h_package_alias_import, {f"{SCHEDULER_MODULE}.manual_trigger"}),
    (_h_package_from_import, {f"{ENGINE_MODULE}.run_all_lanes"}),
    (_h_dotted_import, {f"{SCHEDULER_MODULE}._daily_check"}),
    (_h_unresolvable_root, {f"{SCHEDULER_MODULE}.*"}),
]


@pytest.mark.parametrize("handler,expected", REACH_SHAPES, ids=lambda v: getattr(v, "__name__", ""))
def test_the_reach_walk_catches_each_shape(handler, expected):
    """One negative per shape: each of these, as a public handler, must be an
    offender. A refactor that blinds one shape fails here by name."""
    assert _unreviewed_reach(handler) == expected
    assert _unguarded_reach(handler) == expected


@pytest.mark.parametrize("handler", [_h_reads_status_only, _h_docstring_only, _h_db_reader_only,
                                     _h_import_never_used], ids=lambda f: f.__name__)
def test_the_reach_walk_does_not_cry_wolf(handler):
    assert _unreviewed_reach(handler) == set()


async def _h_two_levels():
    return _helper_of_a_helper()


async def _h_computed_getattr(name: str):
    import backend.config as anything_else
    return getattr(anything_else, name)


def test_what_the_reach_walk_does_not_see():
    """THE LIMIT, pinned so nobody reads the walk as complete. Two helper levels
    and a computed `getattr` are invisible to it; for POST/PUT/PATCH/DELETE the
    route-table test still catches the route, for a GET nothing does."""
    assert _unreviewed_reach(_h_two_levels) == set()
    assert _unreviewed_reach(_h_computed_getattr) == set()


# The inline branch (item 2): a CALL of trigger_authorized as an `if` test, with
# the reach inside the true branch. Anything less is an offender.


async def _b_proper(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if trigger_authorized(request):
        return run_reference_check("conservative")
    return None


async def _b_assigned_name(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    allowed = trigger_authorized(request)
    if allowed:
        return run_reference_check("conservative")
    return None


async def _b_conditional_expression(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    return run_reference_check("conservative") if trigger_authorized(request) else None


async def _b_helper_in_branch(request):
    if trigger_authorized(request):
        return _helper_that_reaches()
    return None


async def _b_bare_mention(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    _ = trigger_authorized
    return run_reference_check("conservative")


async def _b_called_but_not_branched_on(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    trigger_authorized(request)
    return run_reference_check("conservative")


async def _b_reach_in_the_else(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if trigger_authorized(request):
        return None
    else:
        return run_reference_check("conservative")


async def _b_reach_after_the_if(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if trigger_authorized(request):
        pass
    return run_reference_check("conservative")


async def _b_negated(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if not trigger_authorized(request):
        return run_reference_check("conservative")
    return None


async def _b_uncalled_as_the_test(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if trigger_authorized:                               # always true: the function object
        return run_reference_check("conservative")
    return None


async def _b_some_other_test(request):
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check
    if request is not None:
        return run_reference_check("conservative")
    return None


async def _b_helper_outside_branch(request):
    if trigger_authorized(request):
        pass
    return _helper_that_reaches()


@pytest.mark.parametrize("handler", [_b_proper, _b_assigned_name, _b_conditional_expression,
                                     _b_helper_in_branch], ids=lambda f: f.__name__)
def test_a_real_branch_on_trigger_authorized_is_accepted(handler):
    assert _unreviewed_reach(handler), "the walk must still see the reach"
    assert _unguarded_reach(handler) == set()


@pytest.mark.parametrize("handler", [
    _b_bare_mention, _b_called_but_not_branched_on, _b_reach_in_the_else, _b_reach_after_the_if,
    _b_negated, _b_uncalled_as_the_test, _b_some_other_test, _b_helper_outside_branch,
], ids=lambda f: f.__name__)
def test_anything_less_than_a_real_branch_is_an_offender(handler):
    assert _unguarded_reach(handler), f"{handler.__name__} passed the inline check"


def test_the_gate_is_one_function_beside_the_control_plane_gate():
    """One shared dependency, not a copy per router."""
    from backend.routers import journal as J
    from backend.routers import optimus_ledger as OL
    from backend.routers import pm as PM
    for mod in (OL, PI, PM, J):
        assert mod.require_trigger_token is CR.require_trigger_token, mod.__name__
    assert PI.trigger_authorized is CR.trigger_authorized
    assert J.trigger_authorized is CR.trigger_authorized
    tree = ast.parse(textwrap.dedent(inspect.getsource(CR.trigger_authorized)))
    compares = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "compare_digest"]
    assert len(compares) == 1, "the token must be compared with hmac.compare_digest, once"
    equality = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)
                and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in n.ops)]
    assert not equality, "no ==/!= on the token path"
