"""L4 / L4b: Qwen3-30B is MEASURED, not assumed -- and every server is stopped.

Until 2026-09-27 L4 refused to start a model server at all, so the queue item
could never produce a number. It now starts a SECOND, NAMED server config on
its own port and stops it BY PID on every exit path. What these tests pin,
with no GPU and no model:

* a FAKE llama-server (a tiny Python HTTP server written to tmp) stands in for
  the binary through `OwnedServer(launcher=...)`; the PID, `/health`, the kill
  and the port are all real, so "stopped" means the OS says the PID is gone;
* every exit path stops it: a clean run, an exception inside the block, a
  /health timeout (LISTENING IS NOT READY), the night's STOP file, a mid-sweep
  exception inside `run_sweep`;
* the refusals: a server on the DEFAULT port is not this job's and is left
  running; the RAM floor; a RUNNING sim session holds the GPU;
* the job never calls the default server's `start`/`stop`/`ensure` and never
  reaches the shell except through `quiet_subprocess` (AST, not grep);
* L4b's decision rule on synthetic paired results, and an end-to-end L4b over
  two fake servers.

The protocol pins from the first version stay: R2's frozen prompts by hash, the
19-block (not 112) registration, the two-condition adoption rule, and the
wall-time arithmetic from R2's own measured tokens.
"""

from __future__ import annotations

import ast
import json
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import llama_server as LS                    # noqa: E402
from backend.services.portfolio_intelligence import r2_trial        # noqa: E402
from scripts import night_l4_qwen3_measure as l4                    # noqa: E402
from scripts import night_l4b_qwen3_extraction as l4b               # noqa: E402

DOC = REPO / "docs" / "TRIALS" / "TRIAL-R2-monthly-news-digest-read.md"

#: assembled rather than written out, so this file's own text does not trip the
#: scanners that look for these names in source
_SHELL = ("subprocess" + ".run", "subprocess" + ".Popen", "os" + "." + "system")

FAKE_SERVER = textwrap.dedent('''
    import argparse, json, sys, time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int)
    ap.add_argument("--fake-mode", default="ok")
    a, _ = ap.parse_known_args()
    T0 = time.time()
    REPLY = {"ticker": "AAPL", "event_type": "no_event", "direction": 0,
             "magnitude_bucket": "SMALL"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            healthy = a.fake_mode != "never_healthy" and time.time() - T0 > 0.3
            self._send(200 if healthy else 503, {"status": "ok" if healthy else "loading"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            mt = int(body.get("max_tokens") or 16)
            self._send(200, {
                "model": "fake-gguf",
                "choices": [{"message": {"content": json.dumps(REPLY)}}],
                "usage": {"prompt_tokens": 300, "completion_tokens": mt},
                "timings": {"prompt_n": 300, "prompt_per_second": 250.0,
                            "predicted_n": mt, "predicted_per_second": 30.0}})

    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
''')


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _alive(pid: int) -> bool:
    return LS.pid_alive(int(pid))


@pytest.fixture()
def fake(tmp_path: Path, monkeypatch):
    """The fake server script, an isolated owner note / stop ledger, and a
    machine that has room (RAM, no sim, no GPU contender, no STOP file)."""
    script = tmp_path / "fake_llama_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    monkeypatch.setattr(l4, "OWNER_NOTE", tmp_path / "owner_l4.json")
    monkeypatch.setenv("AEGIS_LLAMA_STOP_LEDGER", str(tmp_path / "stops.jsonl"))
    monkeypatch.setattr(LS, "LLAMA_HOME", tmp_path)
    monkeypatch.setattr(l4, "stop_file_reason", lambda: None)
    monkeypatch.setattr(l4, "sleep_refusal", lambda: None)    # never run powercfg in a test
    monkeypatch.setattr(l4, "vram_used_mib", lambda: None)
    monkeypatch.setattr(l4, "avail_ram_gb", lambda: 64.0)
    monkeypatch.setattr(l4, "night_folder", lambda: tmp_path / "night")
    from backend.services import disk_guard, sim_session
    monkeypatch.setattr(disk_guard, "require_free",
                        lambda gb, what, path=None, **k: {"free_gb": 999.0, "path": str(path)})
    monkeypatch.setattr(sim_session, "status", lambda: {"state": "IDLE", "pid_alive": False})
    return {"launcher": [sys.executable, str(script)], "dir": tmp_path}


def _cfg(port: int, name: str = "fake") -> l4.ServerConfig:
    return l4.ServerConfig(name=name, model="fake.gguf", port=port, n_cpu_moe=48)


def _ledger(tmp: Path) -> list[dict]:
    p = tmp / "stops.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# =================================================================== lifecycle

def test_a_clean_run_waits_on_health_and_stops_by_pid(fake):
    port = _free_port()
    with l4.OwnedServer(_cfg(port), "L4_test", launcher=fake["launcher"],
                        health_wait_s=30, poll_s=0.2, bind=False) as srv:
        st = srv.start()
        assert st["ready"] and st["action"] == "started", st
        pid = srv.pid
        # the venv's python.exe is a redirector, so the LISTENER can be the
        # grandchild; `taskkill /PID /T` reaches it (a real llama-server is not
        # a redirector and listens as the PID itself)
        assert _alive(pid) and l4.listener_pid(port) is not None
        note = json.loads((fake["dir"] / "owner_l4.json").read_text(encoding="utf-8"))
        assert note["server_pid"] == pid and note["job"] == "L4_test"
        r = l4.chat(port, {"system": "s", "user": "u", "max_tokens": 8})
        assert r["prompt_tok_s"] == 250.0 and r["gen_n"] == 8
    stop = srv.stopped
    assert stop["ok"] and stop["pid"] == pid and not stop["pid_alive_after"]
    assert not _alive(pid), "the server outlived its block"
    assert l4.listener_pid(port) is None
    assert not (fake["dir"] / "owner_l4.json").exists(), "the owner note outlived the server"
    rows = _ledger(fake["dir"])
    assert rows and rows[-1]["pid"] == pid and rows[-1]["reason"] == "operator", (
        "a deliberate stop must be in the stop ledger, or the lab counts it as a death")


def test_an_exception_inside_the_block_still_stops_the_server(fake):
    port = _free_port()
    box = {}
    with pytest.raises(RuntimeError, match="mid-bench"):
        with l4.OwnedServer(_cfg(port), "L4_test", launcher=fake["launcher"],
                            health_wait_s=30, poll_s=0.2, bind=False) as srv:
            assert srv.start()["ready"]
            box["pid"] = srv.pid
            raise RuntimeError("mid-bench")
    assert srv.stopped["ok"] and "exception" in srv.stopped["reason"]
    assert not _alive(box["pid"]) and l4.listener_pid(port) is None


def test_listening_is_not_ready_and_a_health_timeout_stops_the_server(fake):
    """The fake binds its port at once and never answers /health 200: the job
    must NOT call it started, and must stop it by PID."""
    port = _free_port()
    launcher = fake["launcher"] + ["--fake-mode", "never_healthy"]
    with l4.OwnedServer(_cfg(port), "L4_test", launcher=launcher,
                        health_wait_s=3, poll_s=0.2, bind=False) as srv:
        st = srv.start()
        assert not st["ready"] and st["action"] == "timeout", st
        assert "listening is not ready" in st["reason"]
        pid = srv.pid
    assert srv.stopped["ok"] and not _alive(pid)


def test_the_stop_file_stops_a_server_that_is_still_loading(fake):
    port = _free_port()
    launcher = fake["launcher"] + ["--fake-mode", "never_healthy"]
    with l4.OwnedServer(_cfg(port), "L4_test", launcher=launcher, health_wait_s=60,
                        poll_s=0.2, bind=False,
                        should_stop=lambda: "STOP file present") as srv:
        st = srv.start()
        assert st["action"] == "stopped_before_ready" and st["reason"] == "STOP file present"
        pid = srv.pid
    assert srv.stopped["ok"] and not _alive(pid)


def test_measure_setting_measures_and_the_card_is_checked_after(fake, monkeypatch):
    reads = iter([500, 4200, 4200, 520])
    monkeypatch.setattr(l4, "vram_used_mib", lambda: next(reads, 520))
    port = _free_port()
    row = l4.measure_setting(48, l4.bench_prompts(), job="L4_test", launcher=fake["launcher"],
                             health_wait_s=30, cfg=_cfg(port))
    assert row["status"] == "MEASURED", row
    assert row["prompt_eval_tok_s_r2_median"] == 250.0
    assert row["generation_tok_s"] == 30.0 and row["generation_tokens_measured"] == l4.GEN_TOKENS
    assert row["vram_loaded_mib"] == 4200
    assert row["stop"]["ok"] and not _alive(row["server_pid"])
    assert row["vram_after"]["returned_to_baseline"] and row["vram_after"]["after_mib"] == 520


def test_an_exception_mid_sweep_stops_the_server_and_leaves_a_receipt(fake, monkeypatch, tmp_path):
    """`run_sweep` re-raises -- the factory records the FAILED exit -- but the
    server it started is already gone and the receipt says what happened."""
    started = []

    class Spy(l4.OwnedServer):
        def start(self):
            st = super().start()
            started.append(self.pid)
            return st

    monkeypatch.setattr(l4, "OwnedServer", Spy)
    monkeypatch.setattr(l4, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(l4, "qwen3_config", lambda n, port=None: _cfg(_free_port()))
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())
    out = tmp_path / "L4.json"
    with pytest.raises(RuntimeError, match="boom"):
        l4.run_sweep(out=out, launcher=fake["launcher"], check_gpu=False, sweep=(48, 40),
                     health_wait_s=30, with_hash=False)
    assert started and all(not _alive(p) for p in started), "a server outlived the exception"
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["status"] == "FAILED" and "boom" in r["exception"]


def test_a_full_sweep_on_fakes_stops_every_server_and_names_the_best(fake, monkeypatch, tmp_path):
    monkeypatch.setattr(l4, "qwen3_config",
                        lambda n, port=None: l4.ServerConfig(name=f"fake{n}", model="f.gguf",
                                                             port=_free_port(), n_cpu_moe=n))
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())
    out = tmp_path / "L4.json"
    r = l4.run_sweep(out=out, launcher=fake["launcher"], check_gpu=False, sweep=(48, 40),
                     health_wait_s=30, with_hash=False)
    assert r["status"] == "MEASURED", r.get("verdict")
    assert [s["n_cpu_moe"] for s in r["settings"]] == [48, 40]
    assert r["all_servers_stopped"] and all(not _alive(s["pid"]) for s in r["servers_stopped_by_pid"])
    assert r["best_setting"]["n_cpu_moe"] in (48, 40)
    assert r["wall_time"]["qwen3_30b_a3b_at_the_IDLE_measured_rates"]["prompt_eval_tok_s"] == 250.0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "MEASURED"


# =================================================================== refusals

def test_a_server_on_the_default_port_is_a_refusal_and_is_left_running(fake, monkeypatch, tmp_path):
    """Not this job's server: refuse by name, start nothing, stop nothing."""
    port = _free_port()
    other = subprocess.Popen(fake["launcher"] + ["--port", str(port)])  # a "foreign" reader
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not l4.health_ok(port):
            time.sleep(0.2)
        monkeypatch.setattr(LS, "LLAMA_PORT", port)
        named = _free_port()
        monkeypatch.setattr(l4, "qwen3_config",
                            lambda n, port=None: l4.ServerConfig(name="x", model="f.gguf",
                                                                 port=named, n_cpu_moe=n))
        out = tmp_path / "L4.json"
        r = l4.run_sweep(out=out, launcher=fake["launcher"], check_gpu=False, sweep=(48,),
                         with_hash=False)
        codes = {x["code"] for x in r["preflight"]["refusals"]}
        assert "REFUSED_SERVER_UP" in codes and r["status"].startswith("REFUSED")
        assert r["settings"] == [] and l4.listener_pid(named) is None, "it started a server anyway"
        assert other.poll() is None and _alive(other.pid), "it stopped a server it does not own"
        assert json.loads(out.read_text(encoding="utf-8"))["verdict"].startswith("REFUSED")
    finally:
        from scripts import night_factory
        night_factory.kill_tree(other.pid)          # BY PID, with its redirected child
        other.wait(timeout=10)


def test_the_ram_floor_and_a_running_sim_are_refusals(fake, monkeypatch):
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())
    monkeypatch.setattr(l4, "avail_ram_gb", lambda: 3.0)
    from backend.services import sim_session
    monkeypatch.setattr(sim_session, "status", lambda: {"state": "RUNNING", "pid_alive": True})
    pre = l4.preflight("L4_test", check_gpu=False)
    codes = {x["code"] for x in pre["refusals"]}
    assert {"REFUSED_RAM", "REFUSED_GPU_LOCK_HELD"} <= codes and not pre["ok"]
    monkeypatch.setattr(l4, "avail_ram_gb", lambda: None)
    assert any(x["code"] == "REFUSED_RAM" and "unmeasurable" in x["detail"]
               for x in l4.preflight("L4_test", check_gpu=False)["refusals"]), (
        "an unmeasured RAM is not RAM with room")


def test_the_disk_floor_the_gpu_guard_and_a_sleeping_power_plan_are_refusals(fake, monkeypatch):
    """Each refuses BY NAME, and the preflight still reports every other reason."""
    from backend.services import disk_guard
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())

    def full(gb, what, path=None, **k):
        raise disk_guard.DiskTooFull(f"{what}: REFUSED -- 3.00 GB free (< {gb:g} GB required)")

    monkeypatch.setattr(disk_guard, "require_free", full)
    import scripts.gpu_guard as gg
    monkeypatch.setattr(gg, "contention", lambda *a, **k: {
        "contended": True, "reason": "5,900 MiB in use by pid 4242 (> 3072)",
        "state": {"card": "RTX 5060"}})
    monkeypatch.setattr(l4, "sleep_refusal",
                        lambda: "REFUSED: the active power plan sleeps after 900s on AC")
    pre = l4.preflight("L4_test", check_gpu=True, check_binary=False)
    codes = {x["code"] for x in pre["refusals"]}
    assert {"REFUSED_DISK", "REFUSED_GPU_CONTENDED", "REFUSED_MAY_SLEEP"} <= codes, codes
    assert not pre["ok"] and pre["seen"]["power_plan"]["may_sleep"] is True
    assert any("3.00 GB free" in x["detail"] for x in pre["refusals"] if x["code"] == "REFUSED_DISK")


def test_the_sleep_refusal_is_the_night_factorys_own_guard(monkeypatch):
    from scripts import night_factory
    monkeypatch.setattr(night_factory, "refuse_if_the_machine_may_sleep",
                        lambda: "REFUSED: the active power plan sleeps\n after 900s")
    assert l4.sleep_refusal() == "REFUSED: the active power plan sleeps after 900s"
    monkeypatch.setattr(night_factory, "refuse_if_the_machine_may_sleep", lambda: None)
    assert l4.sleep_refusal() is None


def test_a_refusal_writes_a_named_atomic_receipt_and_starts_nothing(fake, monkeypatch, tmp_path):
    """The live proof's shape, on fakes: RAM under the floor and a RUNNING sim
    -> a REFUSED receipt with a run id, written through the atomic writer, in a
    `<job>_runNN.json` that does not overwrite an earlier run."""
    from backend.services import disk_guard, sim_session
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())
    monkeypatch.setattr(l4, "avail_ram_gb", lambda: 5.0)
    monkeypatch.setattr(sim_session, "status", lambda: {"state": "RUNNING", "pid_alive": True})
    night = tmp_path / "night"
    night.mkdir()
    (night / "L4_qwen3_measure_run01.json").write_text('{"verdict": "older run"}', encoding="utf-8")
    writes = []
    real = disk_guard.atomic_write_json
    monkeypatch.setattr(disk_guard, "atomic_write_json",
                        lambda p, o, **k: (writes.append(Path(p)), real(p, o, **k))[1])
    started = []
    monkeypatch.setattr(l4.OwnedServer, "start", lambda self: started.append(1) or {})
    r = l4.run_sweep(launcher=fake["launcher"], check_gpu=False, with_hash=False)
    assert started == [], "a refused run started a server"
    assert r["status"].startswith("REFUSED") and r["verdict"].startswith("REFUSED")
    codes = {x["code"] for x in r["preflight"]["refusals"]}
    assert {"REFUSED_RAM", "REFUSED_GPU_LOCK_HELD"} <= codes
    assert writes and writes[-1].name == "L4_qwen3_measure_run02.json", writes
    older = json.loads((night / "L4_qwen3_measure_run01.json").read_text(encoding="utf-8"))
    assert older["verdict"] == "older run", "a second run overwrote the first's receipt"
    on_disk = json.loads(writes[-1].read_text(encoding="utf-8"))
    assert on_disk["run_id"] and on_disk["model"] == l4.GGUF_FILE
    assert on_disk["n_cpu_moe_sweep"] == list(l4.N_CPU_MOE_SWEEP)
    assert on_disk["receipt_path"].endswith("L4_qwen3_measure_run02.json")


def test_the_budget_counts_awake_seconds_not_the_night():
    t = {"now": 1000.0}
    b = l4.AwakeBudget(1.0, gap_s=300, clock=lambda: t["now"])      # a 60 s budget
    t["now"] += 20
    assert round(b.remaining()) == 40
    t["now"] += 8 * 3600                                           # Modern Standby
    assert not b.exhausted(), "a sleeping machine spent the job's budget"
    t["now"] += 41
    assert b.exhausted()
    v = b.view()
    assert v["slept_s"] >= 8 * 3600 and 60 <= v["awake_s"] < 62


def test_the_server_is_bound_to_a_job_object_by_pid(fake, monkeypatch):
    """`bind=True` (the default) hands the server's PID to
    `llama_server.bind_lifetime` -- the Windows job object with
    KILL_ON_JOB_CLOSE -- and records the outcome in the owner note."""
    bound = []
    monkeypatch.setattr(LS, "bind_lifetime", lambda pid: bound.append(pid) or
                        {"bound": True, "note": "spy"})
    port = _free_port()
    with l4.OwnedServer(_cfg(port), "L4_test", launcher=fake["launcher"],
                        health_wait_s=30, poll_s=0.2) as srv:
        st = srv.start()
        assert st["ready"] and st["lifetime_bound"] == {"bound": True, "note": "spy"}
        note = json.loads((fake["dir"] / "owner_l4.json").read_text(encoding="utf-8"))
        assert note["lifetime_bound"]["bound"] is True
    assert bound == [srv.pid]
    assert l4.OwnedServer(_cfg(port), "x").bind is True, "binding must be the default"


_KILL_CHILD = textwrap.dedent("""
    import json, sys, time
    from pathlib import Path
    repo, tmp, script, base, port = sys.argv[1:6]
    sys.path.insert(0, repo)
    from backend.services import llama_server as LS
    from scripts import night_l4_qwen3_measure as l4
    l4.OWNER_NOTE = Path(tmp) / "owner_kill.json"
    LS.LLAMA_HOME = Path(tmp)
    cfg = l4.ServerConfig(name="kill", model="f.gguf", port=int(port), n_cpu_moe=48)
    srv = l4.OwnedServer(cfg, "L4_killtest", launcher=[base, script], health_wait_s=30,
                         poll_s=0.2)
    st = srv.start()
    print(json.dumps({"pid": srv.pid, "ready": st.get("ready"),
                      "bound": (st.get("lifetime_bound") or {}).get("bound")}), flush=True)
    time.sleep(600)
""")


@pytest.mark.skipif(sys.platform != "win32", reason="the job object is Windows-only")
def test_a_hard_kill_of_the_job_takes_its_server_with_it(fake, tmp_path):
    """TerminateProcess on the JOB runs no user code -- no __exit__, no
    finally. The kernel's KILL_ON_JOB_CLOSE is what stops the server, so a
    force-kill cannot leave 17 GiB mapped. Both processes are the BASE
    interpreter (the venv's python.exe is a redirector whose kill would not
    reach the real job), and every kill here is by a PID this test started."""
    import os
    base = getattr(sys, "_base_executable", sys.executable)
    child_py = tmp_path / "kill_child.py"
    child_py.write_text(_KILL_CHILD, encoding="utf-8")
    port = _free_port()
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
           "AEGIS_LLAMA_STOP_LEDGER": str(tmp_path / "stops.jsonl"),
           "AEGIS_IGNORE_DOTENV": "1"}
    job = subprocess.Popen([base, str(child_py), str(REPO), str(tmp_path),
                            str(tmp_path / "fake_llama_server.py"), base, str(port)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    server_pid = None
    try:
        info = json.loads(job.stdout.readline())
        server_pid = int(info["pid"])
        assert info["ready"] and info["bound"] is True, info
        assert _alive(server_pid) and l4.health_ok(port)
        job.kill()                                   # TerminateProcess, by our own handle
        job.wait(timeout=20)
        deadline = time.time() + 20
        while time.time() < deadline and _alive(server_pid):
            time.sleep(0.2)
        assert not _alive(server_pid), "the server outlived a hard kill of its job"
        assert l4.listener_pid(port) is None
    finally:
        if job.poll() is None:
            job.kill()
        if server_pid and _alive(server_pid):
            from scripts import night_factory
            night_factory.kill_tree(server_pid)


def test_the_job_never_touches_the_default_server_or_the_shell():
    """AST, not grep: the docstrings explain the banned gestures."""
    for mod in (l4, l4b):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f, parts = node.func, []
                while isinstance(f, ast.Attribute):
                    parts.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    parts.append(f.id)
                calls.add(".".join(reversed(parts)))
        banned = {f"{m}.{fn}" for m in ("LS", "llama_server")
                  for fn in ("start", "stop", "ensure", "stop_if_owned")}
        assert not (calls & banned), f"{mod.__name__} touches the default server: {calls & banned}"
        assert not (calls & set(_SHELL)), f"{mod.__name__} reaches the shell directly"
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert "/IM" not in literals and "/im" not in literals


def test_the_named_port_is_not_the_default_port():
    assert l4.PORT != LS.LLAMA_PORT, "the 30B must never answer on the default reader's port"
    assert l4.qwen3_config(48).model.endswith(l4.GGUF_FILE)
    assert l4.incumbent_config().model.endswith(l4.INCUMBENT_FILE)
    assert "--n-cpu-moe" in l4.qwen3_config(48).argv()
    assert "--n-cpu-moe" not in l4.incumbent_config().argv()


# =================================================================== L4b's rule

def _rows(arm: str, correct: list[int], graded: int = 3) -> list[dict]:
    out = []
    for i, c in enumerate(correct):
        g = {"ticker": c >= 1, "event_type": c >= 2, "direction": (c >= 3) if graded == 3 else None}
        out.append({"arm": arm, "item_id": f"I{i:03d}", "grade": g})
    return out


def test_the_paired_difference_is_the_pooled_e_g1_metric():
    a = _rows("local_7b", [1, 2, 2, 1] * 30)
    b = _rows("local_30b", [2, 2, 3, 1] * 30)
    p = l4b.paired_field_accuracy(a, b)
    assert p["n"] == 120
    assert p["acc_a"] == pytest.approx(180 / 360, abs=1e-4)
    assert p["acc_b"] == pytest.approx(240 / 360, abs=1e-4)
    assert p["diff_pts"] == pytest.approx(100 * 60 / 360, abs=0.01)
    assert p["t"] > 2 and p["n_b_better"] == 60 and p["n_tied"] == 60


def test_replace_needs_all_three_conditions():
    good = {"n": 240, "diff_pts": 4.0, "t": 2.5}
    d = l4b.decide(good, 3.0, n_expected=240, n_a=240, n_b=240)
    assert d["decision"] == "REPLACE_7B_FOR_L2"
    for paired, hours, why in (({"n": 240, "diff_pts": 2.9, "t": 5.0}, 1.0, "gain"),
                               ({"n": 240, "diff_pts": 6.0, "t": 1.9}, 1.0, "paired t"),
                               ({"n": 240, "diff_pts": 6.0, "t": None}, 1.0, "undefined"),
                               (good, 9.5, "projected nightly typing"),
                               (good, None, "not projectable")):
        d = l4b.decide(paired, hours, n_expected=240, n_a=240, n_b=240)
        assert d["decision"] == "KEEP_7B", (paired, hours)
        assert why in d["why"] and "archive" in d["archive_candidate"]


def test_an_unfinished_comparison_decides_nothing():
    d = l4b.decide({"n": 200, "diff_pts": 9.0, "t": 9.0}, 1.0, n_expected=240, n_a=240, n_b=200)
    assert d["decision"] == "INCOMPLETE"


def test_the_rule_is_on_the_receipt_before_the_first_item(fake, monkeypatch, tmp_path):
    """End to end over two fake servers: the receipt's first flush carries the
    decision rule and no rows; both servers are stopped by PID; identical
    readers decide KEEP_7B (t undefined), never REPLACE."""
    items = [{"item_id": f"E-G1-{i:03d}", "document_date": "2026-09-01", "source": "s",
              "title": f"t{i}", "body": "b", "tickers": ["AAPL"],
              "gold": {"stratum": "unmatched", "direction": None}} for i in range(6)]
    frozen = {"ok": True, "items": items, "sha256": "x" * 64, "path": "mem"}
    monkeypatch.setattr(LS, "LLAMA_PORT", _free_port())
    monkeypatch.setattr(l4b, "nightly_typing_rows",
                        lambda: {"rows_per_night": 1000, "source": "MEASURED"})
    monkeypatch.setattr(l4b, "l4_best_n_cpu_moe", lambda: {"n_cpu_moe": 40, "source": "test"})
    flushes = []
    real_write = __import__("backend.services.disk_guard", fromlist=["x"]).atomic_write_json

    def spy(path, obj, **kw):
        flushes.append(json.loads(json.dumps(obj, default=str)))
        return real_write(path, obj, **kw)

    monkeypatch.setattr("backend.services.disk_guard.atomic_write_json", spy)
    cfgs = {a: l4.ServerConfig(name=a, model="f.gguf", port=_free_port()) for a in l4b.ARMS}
    r = l4b.run_comparison(out=tmp_path / "L4b.json", launcher=fake["launcher"],
                           check_gpu=False, frozen=frozen, configs=cfgs, health_wait_s=30)
    first_with_rule = next(f for f in flushes if f.get("preflight"))
    assert first_with_rule["decision_rule"]["min_gain_pts"] == l4b.MIN_GAIN_PTS
    assert first_with_rule["rows"] == [] and first_with_rule["decision"] is None
    assert r["summary"]["local_7b"]["n"] == 6 and r["summary"]["local_30b"]["n"] == 6
    assert r["decision"]["decision"] == "KEEP_7B"
    assert all(s["stopped_ok"] and not _alive(s["pid"]) for s in r["servers_stopped_by_pid"])
    # the receipt names the run, the model per arm and the knob, and carries the peaks
    assert r["run_id"] and r["model"] == {"local_7b": "f.gguf", "local_30b": "f.gguf"}
    assert all({"model", "n_cpu_moe", "vram_peak_mib", "server_rss_peak_mib",
                "ram_available_min_gib", "generation_tok_s_median"} <= set(s)
               for s in r["servers_stopped_by_pid"])
    assert r["budget"]["awake_s"] >= 0 and "slept_s" in r["budget"]


def test_the_frozen_inputs_refuse_a_tampered_file(tmp_path):
    p = tmp_path / "frozen.json"
    p.write_text(json.dumps({"items": [{"a": 1}], "items_sha256": "0" * 64}), encoding="utf-8")
    r = l4b.freeze_items(out=p)
    assert not r["ok"] and "tampered" in r["reason"]


@pytest.mark.parametrize("job,mod,fn", [("L4_qwen3_measure", "l4", "run_sweep"),
                                         ("L4b_qwen3_extraction", "l4b", "run_comparison")])
def test_the_factory_forwards_its_out_so_the_flushes_land_in_its_receipt(job, mod, fn, monkeypatch,
                                                                          tmp_path):
    from scripts import night_factory_jobs as NFJ
    seen = {}

    def spy(**kw):
        seen.update(kw)
        return {"verdict": "REFUSED (REFUSED_RAM): test", "headline": "test"}

    monkeypatch.setattr({"l4": l4, "l4b": l4b}[mod], fn, spy)
    out = tmp_path / f"{job}_run03.json"
    assert NFJ.main([job, "--out", str(out), "--run", "3"]) == 0
    assert seen["out"] == out and seen["run_no"] == 3
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"].startswith("REFUSED")


def test_l4b_is_queued_after_l4_and_owns_the_gpu():
    from backend import config as C
    from scripts.night_factory_jobs import JOB_STAGES, JOBS
    q = [j for j, _ in C.LAB_IDLE_QUEUE]
    assert q.index("L4b_qwen3_extraction") == q.index("L4_qwen3_measure") + 1
    assert {"L4_qwen3_measure", "L4b_qwen3_extraction"} <= set(C.LAB_IDLE_JOBS_OWN_THE_GPU)
    assert "L4b_qwen3_extraction" in JOBS and JOB_STAGES["L4b_qwen3_extraction"] == "raw"


# =================================================================== the protocol

def test_the_reader_state_is_read_not_changed():
    st = l4.reader_state()
    for k in ("listening", "ready", "pid", "vram", "detail"):
        assert k in st
    assert "never started" in st["this_job_never_touches_the_default_server"]


def test_the_file_check_reports_absence_as_absence():
    fc = l4.file_check(with_hash=False)
    assert fc["expected_file"] == l4.GGUF_FILE
    assert fc["license"] == "apache-2.0"
    assert isinstance(fc["present"], bool)
    if not fc["present"]:
        assert fc["sha256"] is None and fc["status"].startswith("ABSENT")
    else:
        assert fc["bytes"] > 0 and fc["gibibytes"] > 0
        assert "17.28" in fc["size_note"], (
            "GB and GiB must be reconciled in the receipt -- otherwise a later reader sees "
            "18.56 against the handoff's 17.28 and concludes the file changed")


def test_the_protocol_uses_r2s_frozen_prompts_by_hash():
    p = l4.protocol()
    fp = p["frozen_prompts"]
    assert fp["system_sha256"] == r2_trial.SYSTEM_SHA256
    assert fp["prompt_sha256"] == r2_trial.PROMPT_SHA256
    assert fp["digest_spec_sha256"] == r2_trial.DIGEST_SPEC_SHA256
    assert p["bench_prompts_sha256"] == l4.bench_sha256()
    assert all(b["system"] == r2_trial.SYSTEM for b in l4.bench_prompts())


def test_the_sweep_is_the_roadmaps_own_and_has_a_stop_condition():
    p = l4.protocol()["step_2_sweep"]
    assert p["n_cpu_moe"] == [48, 40, 32, 24]
    assert "--n-cpu-moe" in p["flag"]
    assert "never taskkill /IM" in p["between_settings"]
    assert "6866" in p["stop_condition"] or "6,866" in p["stop_condition"]
    assert "prompt-eval" in p["decisive_number"]
    assert "/health" in p["ready_means"]


def test_the_block_count_is_panel_bs_nineteen_and_says_it_is_not_112():
    reg = l4.protocol()["step_4_registration"]
    assert "19 monthly blocks" in reg["block_count"]
    assert "112" in reg["block_count"] and "PANEL-A" in reg["block_count"]


def test_the_refusal_definition_reuses_the_language_pin():
    step = l4.protocol()["step_3_refusal_rate"]
    assert step["n_digests"] == 200
    assert any("llm_language.refuse" in s for s in step["a_refusal_is"])
    assert "PLAIN Instruct" in step["build"]
    assert "not to" in step["compared_to"] and "zero" in step["compared_to"]


def test_adoption_needs_the_lookahead_condition_too():
    rule = l4.protocol()["step_5_decision_rule"]
    assert len(rule["adopt_only_if"]) == 2
    assert any("Lookahead" in s for s in rule["adopt_only_if"])
    assert rule["a_pass_on_the_first_alone_is"].startswith("CONDITIONAL_ON_LAP")


def test_the_wall_time_comes_from_r2s_own_measured_tokens():
    wt = l4.wall_time()
    assert wt["mean_prompt_tokens"] == pytest.approx(330.4, abs=0.2)
    assert wt["mean_completion_tokens"] == pytest.approx(14.0, abs=0.2)
    assert wt["panelB_calls_arm_plus_control"] == 37002
    assert wt["incumbent_qwen2_5_7b"]["panelB_hours"] == pytest.approx(3.9, abs=0.1)
    slow = wt["qwen3_30b_a3b_at_the_CONTENDED_rates"]
    assert slow["panelB_days"] > 10, (
        "the contended arithmetic no longer says this arm is impractical, which is the whole "
        "reason the idle re-measurement is the first step")
    assert "Not guessed" in wt["source"]
    idle = l4.wall_time(330.4, 14.0)["qwen3_30b_a3b_at_the_IDLE_measured_rates"]
    assert idle["seconds_per_call"] == pytest.approx(2.0, abs=0.01)


# ---------------------------------------------------------------------------
# the registration
# ---------------------------------------------------------------------------
def _doc() -> str:
    if not DOC.is_file():
        pytest.skip(f"trial doc absent on this machine: {DOC}")
    return DOC.read_text(encoding="utf-8", errors="replace")


def test_the_addendum_registers_a_new_arm_and_says_it_is_unsigned():
    d = _doc()
    assert "ADDENDUM (UNSIGNED)" in d
    assert "`R2-Qwen3`, a NEW ARM beside R2" in d
    assert "no Qwen3 digest has been read" in d
    assert "19 monthly blocks" in d and "not 112" in d
    assert "CONDITIONAL_ON_LAP" in d


def test_the_addendum_carries_the_models_sha256_and_leaves_the_incumbents_alone():
    d = _doc()
    fc = l4.file_check(with_hash=False)
    if fc["present"]:
        assert "6c997b8af17debdfb01d890214400ccbab00db6acc0ba8da5de1cc906c4774d0" in d
    assert r2_trial.MODEL_IDENTITY["sha256"] in d, (
        "the incumbent's model hash left the document -- a new arm must be registered BESIDE "
        "R2, never on top of it")
    assert "apache-2.0" in d


def test_the_receipt_refuses_by_name_when_the_reader_is_down():
    night = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-13"
    path = night / "L4_qwen3_measure_run01.json"
    if not path.is_file():
        pytest.skip("L4 has not run on this checkout")
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r["status"] in ("PENDING_MODEL", "REFUSED")
    assert r["arm"] == "R2-Qwen3"
    assert r["stage"] == "raw"
    assert r["llm_spend_usd"] == 0.0, "L4 must not have spent a cent -- it made no model call"
    assert r["reader"]["ready"] is False or r["status"] == "REFUSED"
    assert r["protocol"]["frozen_prompts"]["prompt_sha256"] == r2_trial.PROMPT_SHA256
    assert r["next_test"]
