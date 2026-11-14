"""The desktop reader switch (CH-22b): one controller, inside the app.

Everything runs against a temp `dowjones` folder with fake scans and launchers.
Nothing here starts, stops or scans a real process.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from backend.tests.local_control import local_client
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import reader_control as RC
from scripts import task_keeper as TK

NOW = datetime.now(timezone.utc).replace(microsecond=0)
NO_PORTS = lambda h, p: None  # noqa: E731 -- never a socket in the unit suite


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _dj(tmp_path: Path) -> Path:
    d = tmp_path / "optimus" / "dowjones"
    d.mkdir(parents=True)
    (tmp_path / "optimus" / "HANDOFF_PC").write_text("pc\n", encoding="utf-8")
    return d


def _status_file(dj: Path, *, state: str = "READING", t: str | None = None, **extra) -> None:
    row = {"t": t if t is not None else _iso(NOW - timedelta(seconds=20)), "state": state,
           "current_url_by_worker": {"pool": "https://www.reuters.com/markets/secret-article-123/"},
           "pages_ok_10m": 4, "pages_ok_60m": 9,
           "classes_60m": {"reuters.com": {"OK": 3, "ROBOTS_DISALLOWED": 1}, "wsj.com": {"OK": 6}},
           "last_not_ok_page": {"url": "https://www.wsj.com/articles/private-title-here"},
           "last_error": "STALLED at https://www.ft.com/content/abc-def while reading",
           "next_action": "keep reading", "restarts": 1, "pool": {"pid": 4242}, **extra}
    (dj / "reader_status.json").write_text(json.dumps(row), encoding="utf-8")


def _page_log(dj: Path, rows: list[dict]) -> None:
    (dj / "page_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                       encoding="utf-8")


class FakeEnsure:
    """Stands in for `task_keeper.ensure_reader`; records how it was called."""

    def __init__(self, action: str = "launch", **row):
        self.calls: list[dict] = []
        self.action, self.row = action, row

    def __call__(self, **kw) -> dict:
        self.calls.append(kw)
        d = {"action": self.action, "why": f"fake {self.action}", "job": "reader", **self.row}
        if self.action == "launch" and not kw.get("dry_run"):
            d["launched_pid"] = 777
        return d


def _on(dj: Path, ensure: FakeEnsure, *, job: dict | None = None, quiet: bool = False) -> dict:
    return RC.turn_on(dj, ensure=ensure, job_probe=lambda: job or {"in_job": False},
                      quiet_fn=lambda: quiet, port_check=NO_PORTS)


# ------------------------------------------------------------------ status

def test_status_reports_reading_by_host_and_never_a_url(tmp_path):
    dj = _dj(tmp_path)
    _status_file(dj)
    _page_log(dj, [{"t": _iso(NOW - timedelta(minutes=2)), "host": "wsj.com", "class": "OK",
                    "url": "https://www.wsj.com/articles/private-title-here"},
                   {"t": _iso(NOW - timedelta(minutes=30)), "host": "reuters.com", "class": "OK",
                    "url": "https://www.reuters.com/x"},
                   {"t": _iso(NOW - timedelta(minutes=1)), "host": "ft.com", "class": "PAYWALL",
                    "url": "https://www.ft.com/y"}])
    s = RC.status(dj, now=NOW, port_check=NO_PORTS, quiet=False)
    assert s["desired"] == "ON" and s["actual"] == "READING"
    assert s["supervisor"]["freshness"] == "FRESH"
    assert s["pages"]["ok_10m"] == 1 and s["pages"]["ok_60m"] == 2
    assert s["pages"]["ok_60m_by_host"] == {"wsj.com": 1, "reuters.com": 1}
    assert s["supervisor"]["current_hosts"] == ["reuters.com"]
    assert s["supervisor"]["pool_pid_as_reported"] == 4242
    dumped = json.dumps(s)
    assert "secret-article" not in dumped and "private-title" not in dumped
    assert "https://" not in dumped and "[URL_REDACTED]" in s["supervisor"]["last_error"]
    assert "OFF writes SUPERVISOR_STOP" in s["what_will_happen"]


@pytest.mark.parametrize("stamp,actual,fresh", [
    (_iso(NOW - timedelta(minutes=30)), "NOT_REPORTING", "STALE"),
    ((NOW - timedelta(seconds=10)).replace(tzinfo=None).isoformat(), "UNKNOWN", "UNDATEABLE"),
    (_iso(NOW + timedelta(hours=2)), "UNKNOWN", "FUTURE"),
    ("not a date", "UNKNOWN", "UNDATEABLE"),
])
def test_a_stale_undateable_or_future_stamp_is_never_fresh(tmp_path, stamp, actual, fresh):
    dj = _dj(tmp_path)
    _status_file(dj, t=stamp)
    s = RC.status(dj, now=NOW, port_check=NO_PORTS, quiet=False)
    assert s["supervisor"]["freshness"] == fresh
    assert s["actual"] == actual


def test_missing_status_is_unknown_not_off(tmp_path):
    dj = _dj(tmp_path)
    s = RC.status(dj, now=NOW, port_check=NO_PORTS, quiet=False)
    assert s["desired"] == "ON" and s["actual"] == "UNKNOWN"
    assert s["pages"]["readable"] is False and s["pages"]["last_ok"]["freshness"] == "MISSING"


def test_a_future_page_is_not_a_last_successful_page(tmp_path):
    dj = _dj(tmp_path)
    _page_log(dj, [{"t": _iso(NOW + timedelta(hours=1)), "host": "a.com", "class": "OK"},
                   {"t": (NOW - timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
                    "host": "b.com", "class": "OK"}])
    p = RC.page_feedback(dj, NOW)
    assert p["last_ok"]["freshness"] == "MISSING" and p["invalid_rows"] == 2


def test_the_supervisors_stopped_write_reads_as_stopped(tmp_path):
    dj = _dj(tmp_path)
    _status_file(dj, state="stopped", next_action="none: STOP file",
                 t=_iso(NOW - timedelta(minutes=40)))
    s = RC.status(dj, now=NOW, port_check=NO_PORTS, quiet=False)
    assert s["actual"] == "STOPPED"
    assert "not reporting as running" in s["what_will_happen"]


def test_handoff_absent_is_named(tmp_path):
    dj = _dj(tmp_path)
    (tmp_path / "optimus" / "HANDOFF_PC").unlink()
    s = RC.status(dj, now=NOW, port_check=NO_PORTS, quiet=False)
    assert s["handoff_present"] is False and "HANDOFF_PC is absent" in s["what_will_happen"]


# ------------------------------------------------------------------ OFF

def test_off_writes_a_tagged_marker_and_kills_nothing(tmp_path):
    dj = _dj(tmp_path)
    _status_file(dj)
    out = RC.turn_off(dj, now=NOW, port_check=NO_PORTS)
    assert out["result"] == "STOP_REQUESTED" and out["wrote_marker"] is True
    text = (dj / "SUPERVISOR_STOP").read_text(encoding="utf-8")
    assert text.startswith(RC.OWN_HEADER + "\n") and f"owner={RC.OWNER_TAG}" in text
    assert not (dj / "READER_POOL_STOP").exists(), "the supervisor owns READER_POOL_STOP"
    assert out["status"]["desired"] == "OFF" and out["status"]["actual"] == "STOP_REQUESTED"
    again = RC.turn_off(dj, now=NOW, port_check=NO_PORTS)
    assert again["result"] == "STOP_REQUESTED" and again["wrote_marker"] is False


def test_off_reports_stopped_once_the_supervisor_says_so(tmp_path):
    dj = _dj(tmp_path)
    _status_file(dj, state="stopped", next_action="none: STOP file")
    assert RC.turn_off(dj, now=NOW, port_check=NO_PORTS)["result"] == "STOPPED"


def test_off_over_someone_elses_marker_writes_nothing(tmp_path):
    dj = _dj(tmp_path)
    (dj / "SUPERVISOR_STOP").write_text("brain pause until 18:00\n", encoding="utf-8")
    out = RC.turn_off(dj, now=NOW, port_check=NO_PORTS)
    assert out["result"] == "HELD_BY_OTHER" and out["wrote_marker"] is False
    assert (dj / "SUPERVISOR_STOP").read_text(encoding="utf-8") == "brain pause until 18:00\n"
    assert out["status"]["stop_marker"]["owner"] == "other"
    assert "brain pause" in out["status"]["stop_marker"]["content"]


# ------------------------------------------------------------------ ON

def test_on_refuses_someone_elses_marker_and_never_touches_it(tmp_path):
    dj = _dj(tmp_path)
    (dj / "SUPERVISOR_STOP").write_text("", encoding="utf-8")
    ens = FakeEnsure()
    out = _on(dj, ens)
    assert out["action"] == "held" and out["http"] == 409
    assert (dj / "SUPERVISOR_STOP").exists() and ens.calls == []


def test_on_removes_its_own_marker_and_reuses_the_keeper_launcher(tmp_path):
    dj = _dj(tmp_path)
    RC.turn_off(dj, now=NOW, port_check=NO_PORTS)
    ens = FakeEnsure("launch")
    out = _on(dj, ens)
    assert out["action"] == "launch" and out["http"] == 200
    assert not (dj / "SUPERVISOR_STOP").exists()
    launch = ens.calls[0]["launch"]
    assert len(ens.calls) == 1 and launch.func is RC.launch_from_app
    assert launch.keywords == {"breakaway": False}
    state = json.loads((dj / RC.STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state["pid"] == 777
    # a second ON inside the cooldown does not launch again
    out2 = _on(dj, ens)
    assert out2["action"] == "starting" and len(ens.calls) == 1


def test_on_with_a_live_supervisor_is_alive_not_a_second_launch(tmp_path):
    dj = _dj(tmp_path)
    ens = FakeEnsure("alive", pids=[1, 2])
    out = _on(dj, ens)
    assert out["action"] == "alive" and out["http"] == 200
    assert not (dj / RC.STATE_FILE_NAME).exists()


def test_on_removes_the_retired_controllers_exact_token_from_both_markers(tmp_path):
    dj = _dj(tmp_path)
    owner = "ab" * 16
    (dj / "reader_control.json").write_text(json.dumps({"stop_owner": owner}), encoding="utf-8")
    token = f"{RC.LEGACY_HEADER}\n{owner}\n"
    for name in ("SUPERVISOR_STOP", "READER_POOL_STOP"):
        (dj / name).write_text(token, encoding="utf-8", newline="")
    info = RC.marker_info(dj / "SUPERVISOR_STOP", dj)
    assert info["owner"] == "retired_controller" and info["owner_matches_retired_control_file"]
    out = _on(dj, FakeEnsure("launch"))
    assert out["action"] == "launch"
    assert not (dj / "SUPERVISOR_STOP").exists() and not (dj / "READER_POOL_STOP").exists()


def test_a_legacy_looking_marker_with_anything_extra_is_someone_elses(tmp_path):
    dj = _dj(tmp_path)
    (dj / "SUPERVISOR_STOP").write_text(f"{RC.LEGACY_HEADER}\n{'ab' * 16}\nmanual note\n",
                                        encoding="utf-8", newline="")
    out = _on(dj, FakeEnsure())
    assert out["action"] == "held" and (dj / "SUPERVISOR_STOP").exists()


def test_on_leaves_the_supervisors_own_repair_marker(tmp_path):
    dj = _dj(tmp_path)
    (dj / "READER_POOL_STOP").write_text(RC.SUPERVISOR_REPAIR_TEXT + "\n", encoding="utf-8")
    out = _on(dj, FakeEnsure("alive"))
    assert out["action"] == "alive" and (dj / "READER_POOL_STOP").exists()


def test_on_inside_the_iif_window_starts_nothing(tmp_path):
    dj = _dj(tmp_path)
    RC.turn_off(dj, now=NOW, port_check=NO_PORTS)
    ens = FakeEnsure()
    out = _on(dj, ens, quiet=True)
    assert out["action"] == "iif_quiet" and out["http"] == 200 and ens.calls == []
    assert not (dj / "SUPERVISOR_STOP").exists(), "the pause is lifted; the start waits"


def test_on_refuses_to_launch_into_a_job_that_kills_on_close(tmp_path):
    dj = _dj(tmp_path)
    ens = FakeEnsure("launch")
    out = _on(dj, ens, job={"in_job": True, "limit_flags": 0x2000, "kill_on_close": True,
                            "breakaway_ok": False, "silent_breakaway_ok": False})
    assert out["action"] == "refused_bound_to_app" and out["http"] == 409
    assert ens.calls == [{"dry_run": True}], "only a dry-run decision, never a launch"
    assert "python -m scripts.task_keeper reader" in out["detail"]


def test_on_breaks_away_when_the_job_allows_it(tmp_path):
    dj = _dj(tmp_path)
    ens = FakeEnsure("launch")
    out = _on(dj, ens, job={"in_job": True, "limit_flags": 0x2800, "kill_on_close": True,
                            "breakaway_ok": True, "silent_breakaway_ok": False})
    assert out["action"] == "launch"
    assert ens.calls[0]["launch"].keywords == {"breakaway": True}


def test_the_child_environment_drops_only_the_desktop_flags():
    base = {"AEGIS_DESKTOP": "1", "AEGIS_CONTROL_ENABLED": "1", "PATH": "x", "AEGIS_REPO_ROOT": "r"}
    assert RC.child_env(base) == {"PATH": "x", "AEGIS_REPO_ROOT": "r"}


def test_launch_from_app_runs_the_keepers_own_command(monkeypatch, tmp_path):
    seen = {}

    class P:
        pid = 31337

    def fake_popen(argv, **kw):
        seen.update(argv=argv, **kw)
        return P()

    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    monkeypatch.setattr(RC.subprocess, "Popen", fake_popen)
    pid = RC.launch_from_app("continuous", tmp_path / "s.log", breakaway=True)
    assert pid == 31337
    assert seen["argv"] == TK.supervisor_argv("continuous")
    assert (tmp_path / "s.log").exists()          # output appended to the keeper's log
    assert seen["cwd"] == str(TK.REPO) and "AEGIS_DESKTOP" not in seen["env"]
    assert seen["creationflags"] & RC.BREAKAWAY_FLAG or sys.platform != "win32"


def test_a_keeper_that_pauses_for_the_iif_window_reads_as_iif_quiet(tmp_path):
    dj = _dj(tmp_path)
    out = _on(dj, FakeEnsure("paused", why="IIF reader quiet window (16:45-17:05 local)"))
    assert out["action"] == "iif_quiet" and out["http"] == 200


def test_iif_window_is_the_existing_one():
    assert RC.iif_quiet(datetime(2026, 11, 11, 16, 50)) is True
    assert RC.iif_quiet(datetime(2026, 11, 11, 17, 5)) is False


@pytest.mark.parametrize("action,http", [("cannot_determine", 503), ("launch_failed", 500),
                                         ("paused", 409)])
def test_keeper_refusals_map_to_http_codes(tmp_path, action, http):
    dj = _dj(tmp_path)
    out = _on(dj, FakeEnsure(action))
    assert out["action"] == action and out["http"] == http and out["ok"] is False


@pytest.mark.parametrize("job,mode", [
    ({"in_job": False}, "plain"),
    ({"in_job": None, "how": "x"}, "refuse"),
    ({"in_job": True, "limit_flags": None}, "refuse"),
    ({"in_job": True, "limit_flags": 0x3000, "kill_on_close": True, "silent_breakaway_ok": True},
     "plain"),
    ({"in_job": True, "limit_flags": 0x2800, "kill_on_close": True, "breakaway_ok": True},
     "breakaway"),
    ({"in_job": True, "limit_flags": 0, "kill_on_close": False}, "plain"),
    ({"in_job": True, "limit_flags": 0x2000, "kill_on_close": True}, "refuse"),
])
def test_launch_mode_table(job, mode):
    assert RC.launch_mode(job)[0] == mode


def test_job_binding_answers_in_this_process():
    j = RC.job_binding()
    assert j["in_job"] in (True, False, None)


@pytest.mark.skipif(sys.platform != "win32", reason="job objects are a Windows mechanism")
def test_in_the_launchers_job_only_the_breakaway_child_survives_a_hard_kill(tmp_path):
    """The claim the switch rests on, measured with real processes: inside the
    desktop launcher's job (`launcher._job_object`), a plain child dies with the
    app, and a child started with `BREAKAWAY_FLAG` -- what `launch_from_app(breakaway=True)`
    passes -- survives it. `job_binding` must read the job the same way."""
    repo = Path(__file__).resolve().parents[2]
    ids_file = tmp_path / "ids.json"
    script = tmp_path / "parent.py"
    script.write_text(
        "import ctypes, json, subprocess, sys, time\n"
        f"sys.path.insert(0, r'{repo}')\n"
        "from desktop import launcher as L\n"
        "from backend.services import reader_control as RC\n"
        "h, rec = L._job_object()\n"
        "k32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "k32.GetCurrentProcess.restype = ctypes.c_void_p\n"
        "k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]\n"
        "ok = k32.AssignProcessToJobObject(h, k32.GetCurrentProcess())\n"
        "sleep = [sys.executable, '-c', 'import time; time.sleep(120)']\n"
        "plain = subprocess.Popen(sleep, creationflags=0x08000000)\n"
        "free = subprocess.Popen(sleep, creationflags=0x08000000 | RC.BREAKAWAY_FLAG)\n"
        f"open(r'{ids_file}', 'w').write(json.dumps({{'assigned': bool(ok), "
        "'plain': plain.pid, 'free': free.pid, 'job': RC.job_binding(), "
        "'mode': RC.launch_mode(RC.job_binding())[0]}))\n"
        "time.sleep(120)\n", encoding="utf-8")
    import signal
    import subprocess as sp
    import time

    from backend.services import llama_server as ls

    parent = sp.Popen([sys.executable, str(script)], creationflags=0x08000000)
    free_pid = None
    try:
        ids = None
        for _ in range(300):
            try:
                ids = json.loads(ids_file.read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        assert ids is not None and ids["assigned"], ids
        free_pid = int(ids["free"])
        assert ids["job"]["kill_on_close"] and ids["job"]["breakaway_ok"], ids["job"]
        assert ids["mode"] == "breakaway"
        parent.kill()                               # TerminateProcess: the window closing hard
        parent.wait(timeout=30)
        for _ in range(100):
            if not ls.pid_alive(int(ids["plain"])):
                break
            time.sleep(0.1)
        assert not ls.pid_alive(int(ids["plain"])), "a plain child must still die with the app"
        assert ls.pid_alive(free_pid), "the breakaway child (the reader) must outlive the app"
    finally:
        if parent.poll() is None:
            parent.kill()
        if free_pid and ls.pid_alive(free_pid):
            os.kill(free_pid, signal.SIGTERM)       # the PID this test started, nothing else


# ------------------------------------------------------------------ retire script

def test_retire_moves_only_the_reader_shortcut_and_never_overwrites(tmp_path):
    from scripts import retire_reader_control as R

    desk, dest = tmp_path / "Desktop", tmp_path / "evidence"
    desk.mkdir()
    lnk = desk / R.SHORTCUT_NAME
    lnk.write_bytes(b"lnk")
    exe = r"C:\Users\x\AppData\Local\Programs\AegisReaderControl\20261031\AegisReaderControl.exe"
    p = R.plan(desktop=desk, dest_dir=dest, target_of=lambda _: exe)
    assert p["action"] == "move" and lnk.exists(), "a plan changes nothing"
    out = R.apply(p)
    assert out["applied"] and not lnk.exists() and (dest / R.SHORTCUT_NAME).read_bytes() == b"lnk"
    lnk.write_bytes(b"new")
    p2 = R.plan(desktop=desk, dest_dir=dest, target_of=lambda _: exe)
    assert p2["action"] == "refuse" and "already exists" in p2["why"]
    p3 = R.plan(desktop=desk, dest_dir=tmp_path / "e2", target_of=lambda _: r"C:\x\Other.exe")
    assert p3["action"] == "refuse" and lnk.exists()
    assert R.plan(desktop=tmp_path / "empty", dest_dir=dest)["action"] == "nothing"


# ------------------------------------------------------------------ router

@pytest.fixture()
def client(monkeypatch, tmp_path):
    from backend.routers import control

    (tmp_path / "dowjones").mkdir()
    monkeypatch.setattr(RC._config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(RC, "_port_answers", NO_PORTS)
    monkeypatch.setattr(RC, "iif_quiet", lambda now_local=None: False)
    monkeypatch.setattr(RC, "job_binding", lambda: {"in_job": False})
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(control.router)
    return local_client(app)  # H1: loopback Host + JSON, like the desktop page


def test_router_reads_while_disabled_and_refuses_writes(client, tmp_path):
    r = client.get("/api/control/reader")
    assert r.status_code == 200 and r.json()["desired"] == "ON"
    for path in ("/api/control/reader/on", "/api/control/reader/off"):
        assert client.post(path).status_code == 403
    assert not (tmp_path / "dowjones" / "SUPERVISOR_STOP").exists()


def test_router_off_then_on(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = client.post("/api/control/reader/off")
    assert r.status_code == 200 and r.json()["result"] == "STOP_REQUESTED"
    assert (tmp_path / "dowjones" / "SUPERVISOR_STOP").exists()
    ens = FakeEnsure("launch")
    monkeypatch.setattr(TK, "ensure_reader", ens)
    r = client.post("/api/control/reader/on")
    assert r.status_code == 200 and r.json()["action"] == "launch"
    assert not (tmp_path / "dowjones" / "SUPERVISOR_STOP").exists()


def test_router_codes_for_held_and_cannot_determine(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    stop = tmp_path / "dowjones" / "SUPERVISOR_STOP"
    stop.write_text("someone\n", encoding="utf-8")
    r = client.post("/api/control/reader/on")
    assert r.status_code == 409 and r.json()["action"] == "held" and stop.exists()
    stop.unlink()
    monkeypatch.setattr(TK, "ensure_reader", FakeEnsure("cannot_determine"))
    r = client.post("/api/control/reader/on")
    assert r.status_code == 503 and r.json()["detail"]
