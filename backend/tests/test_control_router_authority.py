"""The control plane's authority, pinned by test (roadmap 2026-09-08 section 10.7).

`backend/routers/control.py` exists so a non-programmer can click a button and
run a night job. That makes it the one router in this repo that spawns
subprocesses, so three properties are pinned here rather than trusted:

1. it cannot reach a broker or an order path;
2. it cannot run anything that is not in the night queue's own whitelist, and it
   never builds a shell command from a request parameter;
3. it cannot kill a process by image name -- only a PID it wrote down itself --
   which is the 2026-09-06 lesson (`taskkill /F /IM python.exe` killed two other
   agents' jobs, a test suite and 1,676 already-billed extractions).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers import control

SOURCE = Path(control.__file__).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _imported_names() -> set[str]:
    out: set[str] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
            out.update(f"{node.module or ''}.{a.name}" for a in node.names)
    return out


def test_the_router_imports_no_broker():
    """No order path, at any depth, by any name."""
    forbidden = ("alpaca", "broker", "alpha.broker", "order", "trade_api", "tradeapi")
    names = " ".join(sorted(_imported_names())).lower()
    hits = [f for f in forbidden if f in names]
    assert not hits, f"the control router imports an order-capable module: {hits}"


def test_no_shell_true_anywhere():
    """A request parameter must never reach a shell."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call):
            for kw in node.keywords or []:
                if kw.arg == "shell":
                    assert isinstance(kw.value, ast.Constant) and kw.value.value is False, (
                        "subprocess in the control router must pass shell=False explicitly")


#: the ONLY function whose return value may stand in for an argv list literal.
#: It exists because the packaged .exe cannot run `-m` (see `child_argv`), and
#: it is allowlisted BY NAME so that a future `subprocess.Popen(build_cmd(...))`
#: whose builder joins a string is still caught.
ARGV_BUILDERS = {"child_argv"}


def test_every_spawn_passes_a_list_beginning_with_the_interpreter():
    """`Popen`/`run` argv is a list, never a joined string.

    A call is accepted only when it is one of `ARGV_BUILDERS`, and the companion
    test below proves that builder returns a list -- so the guard keeps its
    teeth rather than being widened to "any call" the first time an indirection
    appears.
    """
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"Popen", "run"} and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Call):
                name = getattr(arg.func, "id", None) or getattr(arg.func, "attr", None)
                assert name in ARGV_BUILDERS, (
                    f"a subprocess argv may come from a list literal, a name, or one of "
                    f"{sorted(ARGV_BUILDERS)} -- not from {name!r}")
                continue
            assert isinstance(arg, (ast.List, ast.Name)), (
                "the first argument of a subprocess call must be an argv list, not a string")


def test_the_argv_builder_returns_a_list_and_never_a_string():
    """`child_argv` is trusted by the test above; this is what earns that."""
    from backend.routers.control import child_argv

    for args in (["-m", "scripts.night_factory", "--job", "X"], ["other.py", "--x"]):
        argv = child_argv(args)
        assert isinstance(argv, list) and all(isinstance(x, str) for x in argv)
        assert len(argv) == len(args) + 1        # exactly one interpreter prepended


def _executable_strings() -> list[str]:
    """Every string constant the module can actually RUN -- docstrings excluded.

    The first version of this test grepped the raw source and failed on the
    docstring that explains why kill-by-image-name is banned. A gate that fires
    on its own rationale teaches the reader to delete the rationale, so it reads
    the AST and skips the docstring of the module and of every def/class.
    """
    doc_nodes = set()
    for n in ast.walk(TREE):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_nodes.add(id(body[0].value))
    return [n.value for n in ast.walk(TREE)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_nodes]


def test_no_kill_by_image_name():
    """`taskkill /IM` and `pkill -f` are how one agent killed three others' work."""
    runnable = [s.lower() for s in _executable_strings()]
    bad = [s for s in runnable if s.strip() in {"/im", "pkill", "killall"} or s.strip().startswith("pkill")]
    assert not bad, f"kill-by-image-name reachable from the control router: {bad}"
    assert any(s.strip() == "/pid" for s in runnable), (
        "the router should kill by PID and does not appear to pass /PID anywhere")


def test_whitelist_is_derived_from_the_queue_not_retyped():
    """A gate that derives its inputs: adding a job to the queue adds the button."""
    from scripts.night_factory import QUEUE

    wl = set(control.whitelist())
    assert {j for j, _ in QUEUE} <= wl
    assert set(control.EXTRA_JOBS) <= wl


@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(control.router)
    return TestClient(app)


def test_reads_work_while_writes_refuse_when_disabled(client):
    r = client.get("/api/control/jobs")
    assert r.status_code == 200 and r.json()["whitelist"]
    for path in ("/api/control/run/D1_reaction_book", "/api/control/night"):
        assert client.post(path).status_code == 403, f"{path} must refuse while the control plane is off"


def test_an_unknown_job_is_refused_even_when_enabled(client, monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = client.post("/api/control/run/rm%20-rf")
    assert r.status_code in (400, 404)
    r = client.post("/api/control/run/not_a_job")
    assert r.status_code == 400 and "whitelisted" in r.json()["detail"]


def test_stop_refuses_a_pid_it_did_not_start(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(control, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(control, "NIGHT_DIR", tmp_path / "night")
    r = client.post("/api/control/stop/999999")
    assert r.status_code == 404 and "registry" in r.json()["detail"]
    assert not (tmp_path / "night" / "STOP").exists(), "a refused stop must not touch the STOP file"


def test_services_reports_without_a_night_directory(monkeypatch, tmp_path):
    """A read must degrade to a report, never to an exception."""
    from fastapi import FastAPI

    monkeypatch.setattr(control, "NIGHT_DIR", tmp_path / "absent")
    monkeypatch.setattr(control, "RUNS_DIR", tmp_path / "absent_runs")
    app = FastAPI()
    app.include_router(control.router)
    body = TestClient(app).get("/api/control/services").json()
    assert body["runs"] == [] and body["stop_file_present"] is False
    assert "local_gguf" in body and "reachable" in body["local_gguf"]


# ===========================================================================
# THE BOARD'S READ-ONLY ROUTES (O4) AND THE UNCAPPED UNIVERSE (O8)
# ===========================================================================
#
# The board added a FILE VIEWER to a router that answers on localhost to a page
# in a browser. That is a new kind of authority in this module -- not "run a
# job" but "read anything" -- so it gets the same treatment as the spawn path:
# the properties are pinned, not trusted.


def _board_paths() -> set[str]:
    """The route paths the board added, read off the router itself."""
    return {r.path for r in control.router.routes
            if getattr(r, "path", "").split("/")[-1]
            in {"tree", "file", "app-log", "ledger", "universe"}}


def test_every_board_route_is_a_get():
    """A board card reads. None of these may ever accept a write -- and this
    reads the ROUTER, so adding `methods=["POST"]` to one fails here."""
    expected = {"/api/control/tree", "/api/control/file", "/api/control/app-log",
                "/api/control/ledger", "/api/control/universe"}
    got = _board_paths()
    assert expected <= got, f"missing board routes: {sorted(expected - got)}"
    for r in control.router.routes:
        if getattr(r, "path", "") in expected:
            assert set(getattr(r, "methods", set())) <= {"GET", "HEAD"}, (
                f"{r.path} accepts {sorted(r.methods)}; the board only reads")


def test_the_board_routes_do_not_write():
    """No `open(..., 'w')`, no `write_text`, no `mkdir` inside the five board
    handlers. Read with the AST, and only INSIDE those functions -- the router
    legitimately writes elsewhere (the run registry, the paper cache), so a
    module-wide grep would either fail forever or be silenced."""
    import ast as _ast

    names = {"tree", "file", "app_log", "ledger", "universe",
             "_resolve_in_checkout", "_tree_root_of", "_books_by_symbol",
             "_analyst_snapshots", "_review_index", "_graded_within"}
    # `replace` and `rename` are NOT here: `str.replace` is the same attribute
    # name as `os.replace`, and a guard that cannot tell a string method from a
    # filesystem call is a broken guard -- it failed on `raw.replace("\\", "/")`
    # the first time it ran. Those two are checked by QUALIFIED name below.
    banned_attrs = {"write_text", "write_bytes", "mkdir", "unlink", "rmtree", "touch"}
    banned_qualified = {("os", "replace"), ("os", "rename"), ("os", "remove"),
                        ("shutil", "rmtree"), ("shutil", "move")}
    for node in _ast.walk(TREE):
        if not isinstance(node, _ast.FunctionDef) or node.name not in names:
            continue
        for sub in _ast.walk(node):
            if not isinstance(sub, _ast.Call):
                continue
            fn = sub.func
            attr = getattr(fn, "attr", None)
            ident = fn.id if isinstance(fn, _ast.Name) else None
            assert attr not in banned_attrs, f"{node.name} calls .{attr}()"
            base = getattr(getattr(fn, "value", None), "id", None)
            assert (base, attr) not in banned_qualified, (
                f"{node.name} calls {base}.{attr}()")
            if ident == "open":
                mode = ""
                for a in list(sub.args[1:]) + [k.value for k in sub.keywords
                                               if k.arg == "mode"]:
                    if isinstance(a, _ast.Constant) and isinstance(a.value, str):
                        mode = a.value
                assert "w" not in mode and "a" not in mode, (
                    f"{node.name} opens a file for writing")


def test_a_traversal_or_absolute_path_outside_the_checkout_is_403_naming_the_path(client):
    """The refusal NAMES the path. A bare 403 from a file viewer sends the
    reader to the network tab to find out what they asked for."""
    for bad in ("../../../../etc/passwd", "..", "../../..",
                "C:/Windows/System32/drivers/etc/hosts", "/etc/passwd"):
        r = client.get("/api/control/file", params={"path": bad})
        assert r.status_code == 403, (bad, r.status_code, r.text[:200])
        detail = r.json()["detail"]
        assert "refused" in detail
        # The path the CALLER asked for, verbatim, is in the refusal.
        assert bad.split("/")[-1] in detail or bad in detail, detail


def test_a_secret_is_refused_by_name_before_the_sandbox_is_consulted(client):
    """`.env` IS inside the checkout, so the sandbox alone would serve it. A
    viewer that hands back DEEPSEEK_API_KEY over localhost is not read-only in
    any sense that matters."""
    for secret in (".env", "backend/../.env", ".env.local", "x/credentials.json",
                   "deploy/id_rsa", "certs/server.pem"):
        r = client.get("/api/control/file", params={"path": secret})
        assert r.status_code == 403, (secret, r.status_code)
        assert "never-served" in r.json()["detail"], secret


def test_a_file_inside_a_declared_root_is_served_with_its_commits(client):
    r = client.get("/api/control/file", params={"path": "backend/services/belief_state.py"})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["path"] == "backend/services/belief_state.py"
    assert body["root"] == "backend/services"
    assert body["lines"] > 100 and body["text"].strip()
    # Either commits, or a NAMED reason there are none. Never an empty list
    # with no explanation -- a caller cannot tell "no history" from "no git".
    assert body["commits"] or body["git_note"]


def test_a_binary_and_an_oversized_file_are_refused_by_type_and_size(client, tmp_path, monkeypatch):
    """A 40 MB parquet read as text is a hung browser, not a file view."""
    big = control.REPO / "scripts" / "__board_test_big__.py"
    r = client.get("/api/control/file", params={"path": "backend/data/aegis_pi.db"})
    assert r.status_code in (403, 404, 415), r.status_code
    monkeypatch.setattr(control, "FILE_MAX_BYTES", 10)
    try:
        big.write_text("# " + "x" * 200, encoding="utf-8")
        r = client.get("/api/control/file", params={"path": "scripts/__board_test_big__.py"})
        assert r.status_code == 413 and "cap" in r.json()["detail"]
    finally:
        big.unlink(missing_ok=True)


def test_the_tree_lists_only_declared_roots(client):
    r = client.get("/api/control/tree", params={"root": "scripts"})
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] and body["n_files"] > 0
    assert all(f["path"].startswith("scripts/") for f in body["files"])
    assert not any("__pycache__" in f["path"] for f in body["files"])
    bad = client.get("/api/control/tree", params={"root": "backend/data"})
    assert bad.status_code == 404 and "Declared roots" in bad.json()["detail"]


def test_the_app_log_reports_rather_than_raising_when_absent(client, monkeypatch, tmp_path):
    monkeypatch.setattr(control, "REPO", tmp_path)
    body = client.get("/api/control/app-log").json()
    assert body["exists"] is False and body["lines"] == [] and body["note"]


def test_the_ledger_card_reports_rather_than_raising(client):
    body = client.get("/api/control/ledger").json()
    assert body["available"] in (True, False)
    if body["available"]:
        # Each leg degrades to a report; none of them may be missing entirely,
        # because an absent key reads as zero to a card that cannot tell.
        assert "health" in body and "calibration_by_model" in body
        assert "n_open" in body and "graded_last_24h" in body


# ----------------------------------------------------------- the universe (O8)

def test_the_universe_total_equals_the_file_row_count(client):
    """The page prints `rows shown / rows in universe` and this is the check
    that keeps the denominator honest: it is counted from the FILE, not from
    whatever the route managed to build."""
    import json as _json

    body = client.get("/api/control/universe", params={"limit": 5}).json()
    if not body.get("available"):
        pytest.skip(f"no universe file in this checkout: {body.get('error')}")
    src = control.REPO / body["universe_source"]
    assert src.exists(), src
    rows = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # One header row plus one scorecard per symbol.
    scorecards = [ln for ln in rows if "symbol" in _json.loads(ln)]
    assert body["universe_rows"] == len(scorecards), (
        f"the route reports {body['universe_rows']} rows and {src.name} holds "
        f"{len(scorecards)} scorecards")
    assert body["n_matched"] == body["universe_rows"], "an unfiltered read drops nothing"
    assert body["rows_shown"] == len(body["rows"]) == 5


def test_a_symbol_not_in_the_universe_is_zero_rows_and_not_an_error(client):
    r = client.get("/api/control/universe", params={"q": "ZZZZNOTATICKER"})
    assert r.status_code == 200
    body = r.json()
    if not body.get("available"):
        pytest.skip("no universe file in this checkout")
    assert body["n_matched"] == 0 and body["rows"] == []
    # The denominator survives an empty result -- otherwise the page would say
    # "0 of 0" and look correct while the universe was still there.
    assert body["universe_rows"] > 0


def test_an_unknown_sort_is_422_and_never_a_silent_insertion_order(client):
    r = client.get("/api/control/universe", params={"sort": "whatever"})
    assert r.status_code == 422 and "unknown sort" in r.json()["detail"]


def test_the_universe_row_names_the_scale_of_every_consensus_it_prints(client):
    """The tracker's consensus runs 5 = STRONG BUY and the local Yahoo snapshot
    runs 1 = STRONG BUY. A page that prints 1.3 beside 4.2 without saying which
    way is up has published two numbers and no fact."""
    body = client.get("/api/control/universe", params={"limit": 50}).json()
    if not body.get("available"):
        pytest.skip("no universe file in this checkout")
    for row in body["rows"]:
        assert "STRONG BUY" in row["consensus_scale"]
        if row["analyst_snapshot"]:
            assert "STRONG BUY" in row["analyst_snapshot"]["scale"]
            assert row["analyst_snapshot"]["scale"] != row["consensus_scale"]


def test_the_board_joins_declare_what_they_could_not_answer(client):
    """`last_event` has no source until lane L2 lands. It is declared absent
    rather than omitted: an absent key reads as "nothing to report"."""
    body = client.get("/api/control/universe", params={"limit": 1}).json()
    if not body.get("available"):
        pytest.skip("no universe file in this checkout")
    joins = body["joins"]
    assert joins["last_event"]["source"] is None and joins["last_event"]["note"]
    assert set(joins) == {"books", "analyst_snapshot", "last_review", "last_event"}
