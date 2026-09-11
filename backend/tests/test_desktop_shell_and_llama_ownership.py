"""Two defects found live on 2026-09-11, both in the shell, both silent.

**One.** A SECOND Aegis instance -- a headless run started from source to
diagnose the first -- called `llama_server.stop_if_owned()` on exit and killed
the model server (PID 53112) that Murat's running .exe had started. The
ownership note is a file under `backend/data/optimus`, so it is per CHECKOUT;
every instance in the same checkout read it and believed the server was its own.
`started_by_aegis` answers "did an Aegis start this?". Only `owner_pid` answers
"did *I*?".

**Two.** The frozen build's backend thread died and said nothing: no listener,
the window counting to 242 s, and `aegis_desktop.log` holding the start line and
nothing else. A daemon thread that raises in a `console=False` build writes its
traceback to a stderr that does not exist.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

from backend.services import llama_server as ls

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------- ownership

def test_the_owner_is_a_process_not_a_checkout():
    me = ls.owning_instance({"owner_pid": os.getpid()})
    assert me["is_me"] is True and me["owner_alive"] is True


def test_a_note_with_no_owner_pid_claims_nothing():
    """Notes written before 2026-09-11 have no `owner_pid`. They must not be
    read as "nobody owns it" NOR as "I own it" -- the caller decides, and the
    old behaviour (stop it) is preserved for them because there is no second
    instance in that world to protect."""
    assert ls.owning_instance({}) == {"owner_pid": None, "is_me": False,
                                      "owner_alive": False}
    assert ls.owning_instance({"owner_pid": "not a pid"})["owner_pid"] is None


def test_a_dead_owner_is_not_a_veto():
    """PID 1 is not an Aegis instance; a very high PID is almost certainly
    free. Either way, an owner that is gone leaves an ORPHANED server and the
    surviving instance may stop it -- `status()` has already checked that the
    recorded server PID is the one holding the socket."""
    inst = ls.owning_instance({"owner_pid": 4_000_000})
    assert inst["owner_alive"] is False and inst["is_me"] is False


def _fake_status(**kw):
    base = {"listening": True, "started_by_aegis": True, "pid": 53112}
    return base | kw


def test_a_second_instance_leaves_the_first_instances_server_alone(monkeypatch):
    """THE 2026-09-11 DEFECT, as a test. Two fake instances: the owner is alive
    and is not me."""
    monkeypatch.setattr(ls, "status", lambda: _fake_status())
    monkeypatch.setattr(ls, "_read_owner",
                        lambda: {"pid": 53112, "owner_pid": os.getpid() + 1})
    monkeypatch.setattr(ls, "pid_alive", lambda pid: True)
    stopped = []
    monkeypatch.setattr(ls, "stop", lambda **kw: stopped.append(kw) or {})

    out = ls.stop_if_owned()
    assert out["action"] == "left_alone"
    assert f"pid {os.getpid() + 1}" in out["reason"]
    assert out["my_pid"] == os.getpid()
    assert stopped == [], "it killed another instance's model server"


def test_my_own_server_is_stopped(monkeypatch):
    monkeypatch.setattr(ls, "status", lambda: _fake_status())
    monkeypatch.setattr(ls, "_read_owner",
                        lambda: {"pid": 53112, "owner_pid": os.getpid()})
    monkeypatch.setattr(ls, "pid_alive", lambda pid: True)
    monkeypatch.setattr(ls, "stop", lambda **kw: {"ok": True, "action": "stopped"})
    out = ls.stop_if_owned()
    assert out["action"] == "stopped"
    assert out["owner"]["is_me"] is True


def test_an_orphaned_server_is_stopped_by_whoever_is_left(monkeypatch):
    monkeypatch.setattr(ls, "status", lambda: _fake_status())
    monkeypatch.setattr(ls, "_read_owner",
                        lambda: {"pid": 53112, "owner_pid": 4_000_000})
    monkeypatch.setattr(ls, "pid_alive", lambda pid: pid == 53112)
    monkeypatch.setattr(ls, "stop", lambda **kw: {"ok": True, "action": "stopped"})
    assert ls.stop_if_owned()["action"] == "stopped"


def test_a_foreign_server_is_still_left_running(monkeypatch):
    monkeypatch.setattr(ls, "status", lambda: _fake_status(started_by_aegis=False))
    out = ls.stop_if_owned()
    assert out["action"] == "left_running"


def test_the_owner_pid_is_recorded_when_the_server_starts():
    """Read the AST rather than the text: the docstring above `_write_owner`'s
    call explains the defect and would satisfy a grep (protocol §10)."""
    src = (REPO / "backend" / "services" / "llama_server.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "start")
    keys = {k.value for n in ast.walk(fn) if isinstance(n, ast.Dict)
            for k in n.keys if isinstance(k, ast.Constant)}
    assert {"pid", "owner_pid", "owner_started_utc"} <= keys


# ------------------------------------------------------- the backend thread

@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_dead_backend_thread_writes_a_log_line_and_a_report(tmp_path, monkeypatch):
    """Monkeypatch the import so the thread body raises, then read the log.

    Without the wrapper this test hangs on nothing and passes on nothing: the
    thread dies, the exception goes to a stderr that does not exist in a
    `console=False` build, and the only symptom is a window that never loads.
    """
    import builtins
    import logging

    from desktop import aegis_desktop as ad

    monkeypatch.setattr(ad, "_log_path", lambda: tmp_path / "aegis_desktop.log")
    monkeypatch.setattr(ad, "repo_root", lambda: tmp_path)
    ad.BACKEND_ERROR.clear()

    # `import uvicorn` inside the thread body goes through `__import__`, so
    # that is what has to be replaced -- patching `importlib.import_module`
    # catches nothing here and the test would pass by never firing.
    real_builtin = builtins.__import__

    def _boom_builtin(name, *a, **k):
        if name == "uvicorn":
            raise ImportError("no uvicorn in this world")
        return real_builtin(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _boom_builtin)

    handler = logging.FileHandler(tmp_path / "aegis_desktop.log", encoding="utf-8")
    ad.log.addHandler(handler)
    ad.log.setLevel(logging.INFO)
    # `start_backend` sets AEGIS_DESKTOP / AEGIS_CONTROL_ENABLED / AEGIS_REPO_ROOT
    # / AEGIS_DATA_DIR on `os.environ` DIRECTLY -- correctly, because uvicorn and
    # every router read them -- and `monkeypatch` cannot undo what the code under
    # test wrote. The first version of this test left AEGIS_DATA_DIR pointing at
    # a tmp_path for the rest of the session, and six later tests in three other
    # files went DEGRADED because the ledger they health-check was suddenly
    # somewhere with no history in it. Snapshot and restore.
    before = dict(os.environ)
    try:
        th = ad.start_backend(0)
        th.join(timeout=20)
    finally:
        monkeypatch.undo()
        os.environ.clear()
        os.environ.update(before)
        ad.log.removeHandler(handler)
        handler.close()

    assert ad.BACKEND_ERROR.get("error", "").startswith("ImportError")
    text = (tmp_path / "aegis_desktop.log").read_text(encoding="utf-8")
    assert "backend thread died" in text
    assert "no uvicorn in this world" in text
    ad.BACKEND_ERROR.clear()


def test_the_thread_body_catches_base_exception_not_just_exception():
    """`SystemExit` from inside uvicorn's config is exactly as silent and
    exactly as fatal as an ImportError."""
    from desktop import aegis_desktop as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "start_backend")
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert any(isinstance(h.type, ast.Name) and h.type.id == "BaseException"
               for h in handlers), "the backend thread body is unwrapped again"


def test_the_shell_writes_a_report_file_beside_the_log(tmp_path, monkeypatch):
    from desktop import aegis_desktop as ad
    monkeypatch.setattr(ad, "_log_path", lambda: tmp_path / "aegis_desktop.log")
    p = ad.write_report({"utc": "now", "port": 1234})
    assert p == tmp_path / "aegis_desktop_report.json"
    assert json.loads(p.read_text(encoding="utf-8"))["port"] == 1234


# -------------------------------------------------- the laptop is not Railway

@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({"AEGIS_DESKTOP": "1"}, True),
    ({"AEGIS_DESKTOP": "1", "AEGIS_DESKTOP_SCHEDULER": "1"}, False),
    ({"AEGIS_DESKTOP_SCHEDULER": "1"}, False),
])
def test_desktop_mode_does_not_run_the_deployments_loops(env, expected, monkeypatch):
    """Until chunk 1 the packaged app could not read `.env`, so every keyed
    background job failed closed and nobody noticed the loops were registered.
    With the repo root fixed the laptop has Railway's keys -- and would have run
    Railway's schedule, `pi_daily_digest` and `pi_why_moved` included, on a paid
    DeepSeek key."""
    from backend.main import _desktop_background_off
    for k in ("AEGIS_DESKTOP", "AEGIS_DESKTOP_SCHEDULER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert _desktop_background_off() is expected


def test_health_reports_the_checkouts_head():
    """The launcher's acceptance test: the only way to see from OUTSIDE that
    the served code is the pulled code."""
    from backend.main import git_head
    head = git_head()
    assert head is None or (len(head) == 40 and all(c in "0123456789abcdef"
                                                    for c in head))


# ------------------------------------------- the windowless process has no stdout

def test_bind_std_streams_gives_a_windowless_process_a_stdout(tmp_path, monkeypatch):
    """`pythonw.exe` and a `console=False` build both set both streams to None."""
    from desktop import aegis_desktop as ad

    monkeypatch.setattr(ad, "_log_path", lambda: tmp_path / "aegis_desktop.log")
    monkeypatch.setattr(ad, "_STD_STREAM_FILE", None)
    real_out, real_err = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        rec = ad.bind_std_streams()
        assert rec["bound"] == ["stdout", "stderr"]
        assert sys.stdout is sys.stderr          # one handle, not two on one file
        assert sys.stdout.isatty() is False      # the call that used to raise
        sys.stdout.write("hello from a process with no console\n")
        again = ad.bind_std_streams()            # idempotent
        assert again["bound"] == []
    finally:
        try:
            if ad._STD_STREAM_FILE is not None:
                ad._STD_STREAM_FILE.close()
        finally:
            sys.stdout, sys.stderr = real_out, real_err
            ad._STD_STREAM_FILE = None
    assert "hello from a process with no console" in (
        tmp_path / "aegis_desktop.log").read_text(encoding="utf-8")


def test_uvicorn_configures_its_logging_when_stdout_is_none(tmp_path, monkeypatch):
    """The actual regression, run through uvicorn's own code.

    `uvicorn.Config(...).configure_logging()` is what raised
    `AttributeError: 'NoneType' object has no attribute 'isatty'` at
    `uvicorn/logging.py:44` -- BEFORE the socket was bound, which is why the
    splash timed out at 242 s with an empty log. Constructing the Config with
    the shell's own kwargs is the cheapest way to keep the fix honest against a
    future uvicorn.
    """
    import uvicorn

    from desktop import aegis_desktop as ad

    monkeypatch.setattr(ad, "_log_path", lambda: tmp_path / "aegis_desktop.log")
    monkeypatch.setattr(ad, "_STD_STREAM_FILE", None)
    real_out, real_err = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        ad.bind_std_streams()
        cfg = uvicorn.Config(app=lambda scope, receive, send: None,
                             port=0, **ad.UVICORN_KWARGS)
        cfg.configure_logging()                  # raised AttributeError before
    finally:
        try:
            if ad._STD_STREAM_FILE is not None:
                ad._STD_STREAM_FILE.close()
        finally:
            sys.stdout, sys.stderr = real_out, real_err
            ad._STD_STREAM_FILE = None


def test_the_shell_binds_the_streams_before_it_imports_uvicorn():
    """AST, not grep: the docstring above `bind_std_streams` names uvicorn too."""
    from desktop import aegis_desktop as ad
    fn = next(n for n in ast.walk(ast.parse(Path(ad.__file__).read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "start_backend")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    binds = [n for n in calls
             if isinstance(n.func, ast.Name) and n.func.id == "bind_std_streams"]
    assert binds, "start_backend no longer binds stdout/stderr"
    imports = [n for n in ast.walk(fn) if isinstance(n, ast.Import)
               for al in n.names if al.name == "uvicorn"]
    assert imports and binds[0].lineno < imports[0].lineno
    assert ad.UVICORN_KWARGS["use_colors"] is False, (
        "uvicorn asks sys.stdout.isatty() unless use_colors is True or False")


def test_the_launcher_sends_both_child_streams_to_the_log():
    from desktop import launcher
    fn = next(n for n in ast.walk(ast.parse(
        Path(launcher.__file__).read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "spawn_shell")
    popen = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "Popen")
    kw = {k.arg: k.value for k in popen.keywords}
    assert isinstance(kw["stdout"], ast.Name) and kw["stdout"].id == "fh", (
        "the child's stdout is not the log: a windowless parent gives it None")
    assert not (isinstance(kw["stdout"], ast.Attribute) and kw["stdout"].attr == "PIPE")


@pytest.mark.slow
def test_pythonw_starts_the_whole_shell_and_reaches_health(tmp_path):
    """The end-to-end proof, under the interpreter that has no console.

    Marked slow because it starts a real server in a real subprocess: it imports
    pandas, lightgbm and pyarrow and binds a port. Every FAST test above pins one
    link of the chain; this one pins that the chain holds.
    """
    import subprocess

    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pytest.skip(f"no pythonw beside {sys.executable}")
    report = REPO / "backend" / "data" / "optimus" / "aegis_desktop_report.json"
    before = report.read_text(encoding="utf-8") if report.exists() else None
    env = dict(os.environ, AEGIS_REPO_ROOT=str(REPO), PYTHONIOENCODING="utf-8")
    try:
        subprocess.run([str(pyw), "-m", "desktop.aegis_desktop", "--headless",
                        "--no-llama"], cwd=str(REPO), env=env, timeout=420,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload.get("health_ok") is True, payload.get("backend_error")
        assert payload.get("std_streams", {}).get("bound") == ["stdout", "stderr"]
    finally:
        if before is not None:
            report.write_text(before, encoding="utf-8")
