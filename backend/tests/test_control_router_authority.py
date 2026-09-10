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


def test_every_spawn_passes_a_list_beginning_with_the_interpreter():
    """`Popen`/`run` argv is a list literal, never a joined string."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"Popen", "run"} and node.args:
            assert isinstance(node.args[0], (ast.List, ast.Name)), (
                "the first argument of a subprocess call must be an argv list, not a string")


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
