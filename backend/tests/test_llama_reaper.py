"""The llama-server reaper (G-fix, adjudication row 7), tested on REAL processes.

No mocks of the OS: a real short-lived child process holds a real listening
socket on a free loopback port and plays the model server; a fake owner note
names it; the reaper runs as a real separate process with the same env vars
`llama_server.spawn_reaper` hands it. It must

* stop the idle server BY PID and exit once it is gone;
* leave a server that is in use alone;
* never touch a listener the owner note does not name (foreign);
* refuse to run twice (the exclusive lock), because on the first E-G1 run a
  `tasklist` timeout under memory pressure spawned ten reapers in four minutes.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REAPER = REPO / "scripts" / "llama_reaper.py"

pytestmark = pytest.mark.skipif(not REAPER.exists(), reason="reaper script missing")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


#: A venv's python.exe on Windows is a LAUNCHER that re-spawns the base
#: interpreter, so Popen's pid is not the pid holding the socket -- which the
#: reaper (correctly) calls foreign. The fake server runs the base interpreter.
BASE_PY = getattr(sys, "_base_executable", None) or sys.executable


def _fake_server(port: int) -> subprocess.Popen:
    # accepts and closes every connection: a listener that never accepts fills
    # its backlog after a few probes and then reads as "nothing listening"
    code = ("import socket,time\n"
            "s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            f"s.bind(('127.0.0.1',{port})); s.listen(16); s.settimeout(1.0)\n"
            "t0=time.time()\n"
            "while time.time()-t0<120:\n"
            "    try:\n"
            "        c,_=s.accept(); c.close()\n"
            "    except OSError:\n"
            "        pass\n")
    p = subprocess.Popen([BASE_PY, "-c", code])
    deadline = time.time() + 20
    while time.time() < deadline:
        with socket.socket() as c:
            c.settimeout(0.3)
            if c.connect_ex(("127.0.0.1", port)) == 0:
                return p
        time.sleep(0.2)
    p.kill()
    raise RuntimeError("fake server never listened")


def _env(tmp_path: Path, port: int) -> dict:
    env = dict(os.environ)
    env.update(AEGIS_LLAMA_OWNER_FILE=str(tmp_path / "owner.json"),
               AEGIS_LLAMA_REAPER_PID_FILE=str(tmp_path / "reaper.pid.json"),
               AEGIS_LLAMA_PORT=str(port), AEGIS_IGNORE_DOTENV="1",
               PYTHONPATH=str(REPO))
    return env


def _note(tmp_path: Path, pid: int, *, idle_s: float) -> None:
    (tmp_path / "owner.json").write_text(json.dumps({
        "pid": pid, "started_utc": "2026-09-26T00:00:00+00:00",
        "last_used_ts": time.time() - idle_s,
        "owner_pid": 999999, "started_for": "test"}), encoding="utf-8")


def _reap(tmp_path, port, *args, timeout=90):
    return subprocess.run([sys.executable, str(REAPER), *args], cwd=str(REPO),
                          env=_env(tmp_path, port), capture_output=True, text=True,
                          timeout=timeout)


def test_the_reaper_stops_an_IDLE_server_by_pid_and_exits(tmp_path):
    port = _free_port()
    srv = _fake_server(port)
    try:
        _note(tmp_path, srv.pid, idle_s=120)
        t0 = time.time()
        r = _reap(tmp_path, port, "--idle-s", "5", "--tick-s", "0.5")
        assert r.returncode == 0, r.stderr
        srv.wait(timeout=20)                         # it really died
        assert srv.returncode is not None
        assert not (tmp_path / "owner.json").exists()
        assert not (tmp_path / "reaper.pid.json").exists()   # the reaper cleaned up
        log = [json.loads(x) for x in
               (tmp_path / "llama_reaper.log.jsonl").read_text().splitlines()]
        stopped = [x for x in log if x.get("action") == "idle_stopped"]
        assert stopped and stopped[0]["pid"] == srv.pid
        assert stopped[0]["stop"]["action"] == "stopped"
        assert time.time() - t0 < 80
    finally:
        if srv.poll() is None:
            srv.kill()


def test_a_server_IN_USE_is_left_alone(tmp_path):
    port = _free_port()
    srv = _fake_server(port)
    try:
        _note(tmp_path, srv.pid, idle_s=1)
        r = _reap(tmp_path, port, "--once", "--idle-s", "3600")
        out = json.loads(r.stdout)
        assert out["action"] == "none" and out["reason"] == "in use", out
        assert srv.poll() is None
    finally:
        srv.kill()


def test_a_FOREIGN_listener_is_never_touched(tmp_path):
    port = _free_port()
    srv = _fake_server(port)
    other = subprocess.Popen([BASE_PY, "-c", "import time; time.sleep(60)"])
    try:
        _note(tmp_path, other.pid, idle_s=10_000)   # the note names a DIFFERENT pid
        r = _reap(tmp_path, port, "--once", "--idle-s", "5")
        out = json.loads(r.stdout)
        assert out["action"] == "exit" and "foreign" in out["reason"], out
        assert srv.poll() is None and other.poll() is None
    finally:
        srv.kill()
        other.kill()


def test_no_server_means_the_reaper_exits_at_once(tmp_path):
    port = _free_port()
    r = _reap(tmp_path, port, "--idle-s", "5", "--tick-s", "0.5", timeout=30)
    assert r.returncode == 0
    log = [json.loads(x) for x in (tmp_path / "llama_reaper.log.jsonl").read_text().splitlines()]
    assert log[0]["action"] == "exit" and "no owner note" in log[0]["reason"]


def test_a_second_reaper_cannot_live_while_one_holds_the_lock(tmp_path):
    port = _free_port()
    srv = _fake_server(port)
    first = None
    try:
        _note(tmp_path, srv.pid, idle_s=0)
        first = subprocess.Popen([sys.executable, str(REAPER), "--idle-s", "3600",
                                  "--tick-s", "0.5"], cwd=str(REPO), env=_env(tmp_path, port))
        deadline = time.time() + 30
        while time.time() < deadline and not (tmp_path / "reaper.pid.json").exists():
            time.sleep(0.2)
        assert (tmp_path / "reaper.pid.json").exists()
        second = _reap(tmp_path, port, "--idle-s", "3600", "--tick-s", "0.5", timeout=30)
        assert second.returncode == 0
        log = [json.loads(x) for x in (tmp_path / "llama_reaper.log.jsonl").read_text().splitlines()]
        exits = [x for x in log if "exit" in x]
        assert exits and exits[-1]["exit"]["last"]["reason"] == "another reaper holds the lock"
        assert first.poll() is None and srv.poll() is None
    finally:
        if first is not None:
            first.kill()
        srv.kill()


def test_ensure_spawns_a_reaper_and_starts_UNBOUND_when_one_is_available(tmp_path, monkeypatch):
    from backend.services import llama_server as LS
    monkeypatch.setattr(LS, "OWNER_FILE", tmp_path / "owner.json")
    monkeypatch.setattr(LS, "REAPER_PID_FILE", tmp_path / "reaper.pid.json")
    seen = {}

    def start(wait_s=90.0, bind=True):
        seen["bind"] = bind
        LS._write_owner({"pid": 4242, "started_utc": LS._now(), "owner_pid": os.getpid()})
        return {"ok": True, "action": "started", "pid": 4242, "status": {}}
    spawned = []
    monkeypatch.setattr(LS, "start", start)
    monkeypatch.setattr(LS, "status", lambda: {"listening": False, "ready": False,
                                               "started_by_aegis": False, "pid": None})
    monkeypatch.setattr(LS, "spawn_reaper", lambda **k: spawned.append(1) or {"spawned": True})
    monkeypatch.setattr(LS, "start_watchdog", lambda: True)
    out = LS.ensure("test", wait_s=0)
    assert out["ok"] and seen["bind"] is False and spawned == [1]


def test_spawn_is_throttled_by_the_stamp_even_when_liveness_reads_dead(tmp_path, monkeypatch):
    from backend.services import llama_server as LS
    monkeypatch.setattr(LS, "REAPER_PID_FILE", tmp_path / "reaper.pid.json")
    (tmp_path / "reaper.pid.json").write_text(json.dumps({"pid": 1}), encoding="utf-8")
    monkeypatch.setattr(LS, "pid_alive", lambda pid: False)      # a tasklist timeout
    out = LS.spawn_reaper()
    assert out["spawned"] is False and "stamped" in out["reason"]
