"""CH-05 wrapper (`scripts/runtime_task.py` + `.cmd`): plan, refusals, exit codes.

Everything runs in a temp "clone"; nothing touches the live data or a scheduled task. The
real-process tests (Windows only) launch a stdlib probe module through the wrapper and check
that its exit code, cwd and environment arrive unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import runtime_task as RT

REPO = Path(__file__).resolve().parents[2]
WIN = sys.platform == "win32"


def _venv_root() -> Path:
    """The interpreter running this test, as a venv root (`<root>/Scripts/python.exe`)."""
    exe = Path(sys.executable)
    return exe.parent.parent


def make_pi_db(path: Path, rows: int = 1) -> Path:
    """A real SQLite file with a paper_nav table (the live store's shape, minimal)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE paper_nav (portfolio_id TEXT, computed_at TEXT, nav REAL)")
    con.executemany("INSERT INTO paper_nav VALUES (?, ?, ?)",
                    [(f"book{i}", "2026-11-10T23:58:02+00:00", 1.0) for i in range(rows)])
    con.commit()
    con.close()
    return path


def make_clone(tmp_path: Path, *, junction_ok: bool = True) -> tuple[Path, Path, dict]:
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    own = clone / "backend" / "data" / "optimus"
    own.mkdir(parents=True)
    # the clone's code honours the paper_nav override (the wrapper checks for the markers)
    (clone / "backend" / "config.py").write_text('PI = "AEGIS_PI_DB_PATH"\n', encoding="utf-8")
    (clone / "backend" / "db.py").write_text("DB_PATH = PI_DB_PATH\n", encoding="utf-8")
    live = own if junction_ok else (tmp_path / "live" / "optimus")
    live.mkdir(parents=True, exist_ok=True)
    keys = tmp_path / "keys.env"
    keys.write_text("", encoding="utf-8")
    pi_db = make_pi_db(tmp_path / "live" / "backend" / "data" / "aegis_pi.db")
    cfg = {"AEGIS_LIVE_ROOT": str(tmp_path / "live"), "AEGIS_LIVE_OPTIMUS": str(live),
           "AEGIS_LIVE_PI_DB": str(pi_db),
           "AEGIS_DOTENV_PATH": str(keys), "AEGIS_VENV_DIR": str(_venv_root()),
           "AEGIS_NN_LAB_VENV_DIR": str(tmp_path / "nnvenv"),
           "AEGIS_PUBLICATION_ROOT": str(tmp_path / "pub")}
    conf = clone / "scripts" / "runtime_task.config"
    conf.write_text("# test\n" + "".join(f"{k}={v}\n" for k, v in cfg.items()), encoding="utf-8")
    shutil.copy2(REPO / "scripts" / "runtime_task.py", clone / "scripts" / "runtime_task.py")
    shutil.copy2(REPO / "scripts" / "runtime_task.cmd", clone / "scripts" / "runtime_task.cmd")
    return clone, conf, cfg


CLEAN_ENV = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}


# ───────────────────────────────────────────────────────────── config

def test_the_committed_config_names_every_key_and_nothing_else():
    cfg = RT.read_config(REPO / "scripts" / "runtime_task.config", environ={})
    assert set(cfg) == set(RT.CONFIG_KEYS)
    assert cfg["AEGIS_DOTENV_PATH"].endswith(".env")
    assert cfg["AEGIS_LIVE_OPTIMUS"].replace("/", "\\").endswith(r"backend\data\optimus")


def test_environment_wins_over_the_file(tmp_path):
    _clone, conf, _cfg = make_clone(tmp_path)
    got = RT.read_config(conf, environ={"AEGIS_VENV_DIR": r"D:\other\venv"})
    assert got["AEGIS_VENV_DIR"] == r"D:\other\venv"


def test_unknown_or_missing_keys_refuse(tmp_path):
    p = tmp_path / "c.config"
    p.write_text("AEGIS_LIVE_ROOT=x\nAEGIS_TYPO=y\n", encoding="utf-8")
    with pytest.raises(RT.Refused, match="unknown"):
        RT.read_config(p, environ={})
    p.write_text("AEGIS_LIVE_ROOT=x\n", encoding="utf-8")
    with pytest.raises(RT.Refused, match="missing"):
        RT.read_config(p, environ={})


# ───────────────────────────────────────────────────────────── argv

def test_parse_options_and_segments():
    opt, segs = RT.parse_argv(["--set", "AEGIS_PERSONAL_MODE=0", "--stop-file", "a\\STOP",
                               "--log", "x.log", "-m", "scripts.contest_desk", "--date", "today",
                               "--then", "-m", "scripts.contest_rehearsal", "daily", "--mode", "contest"])
    assert opt.sets == {"AEGIS_PERSONAL_MODE": "0"} and opt.stop_files == ["a\\STOP"]
    assert [(s.module, s.args, s.log) for s in segs] == [
        ("scripts.contest_desk", ["--date", "today"], "x.log"),
        ("scripts.contest_rehearsal", ["daily", "--mode", "contest"], None)]


@pytest.mark.parametrize("argv,why", [
    ([], "nothing to run"),
    (["--set", "AEGIS_DATA_DIR=x", "-m", "a"], "not allowed"),
    (["--set", "OPENAI_API_KEY=x", "-m", "a"], "not allowed"),
    (["--pythonw", "--log", "x.log", "-m", "a"], "no stdout"),
    (["--bogus", "-m", "a"], "unknown wrapper option"),
    (["-m", "a;rm"], "not a dotted module"),
    (["-m", "a", "--then"], "--then must be followed"),
    (["--log"], "needs a path"),
])
def test_parse_refusals(argv, why):
    with pytest.raises(RT.Refused, match=why):
        RT.parse_argv(argv)


# ───────────────────────────────────────────────────────────── plan

def test_plan_sets_the_environment_and_clears_pythonpath(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    env = {**CLEAN_ENV, "PYTHONPATH": r"C:\Users\mrthn\aegis-finance", "AEGIS_REPO_ROOT": r"C:\old"}
    plan = RT.build_plan(["--set", "AEGIS_PERSONAL_MODE=0", "-m", "scripts.alert_pass"],
                         clone=clone, config_path=conf, environ=env, check=WIN)
    run = plan["runs"][0]
    assert run["argv"][1:] == ["-m", "scripts.alert_pass"]
    assert Path(run["argv"][0]).parent.parent == Path(cfg["AEGIS_VENV_DIR"])
    e = run["env"]
    assert e["AEGIS_DOTENV_PATH"] == cfg["AEGIS_DOTENV_PATH"]
    assert e["AEGIS_PI_DB_PATH"] == cfg["AEGIS_LIVE_PI_DB"]                 # B1
    assert e["AEGIS_PUBLICATION_ROOT"] == cfg["AEGIS_PUBLICATION_ROOT"]     # B2: exported now
    assert e["AEGIS_REPO_ROOT"] == str(clone) and e["AEGIS_RUNTIME_CLONE"] == str(clone)
    assert e["AEGIS_PERSONAL_MODE"] == "0"
    assert "PYTHONPATH" not in e
    assert plan["cwd"] == str(clone)
    assert plan["run_log"] == str(Path(cfg["AEGIS_LIVE_OPTIMUS"]) / "runtime_switch" / "runtime_task_runs.jsonl")


@pytest.mark.skipif(not WIN, reason="interpreter names are Windows paths")
def test_interpreter_choice(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    p = RT.build_plan(["--pythonw", "-m", "a"], clone=clone, config_path=conf, environ=CLEAN_ENV)
    assert Path(p["runs"][0]["argv"][0]).name == "pythonw.exe"
    p = RT.build_plan(["--log", "l.log", "-m", "a"], clone=clone, config_path=conf, environ=CLEAN_ENV)
    assert Path(p["runs"][0]["argv"][0]).name == "python.exe"
    assert p["runs"][0]["log"] == str(clone / "l.log")
    assert p["runs"][0]["env"]["PYTHONUNBUFFERED"] == "1"
    p = RT.build_plan(["--nn-lab", "-m", "nn_lab.nightly"], clone=clone, config_path=conf,
                      environ=CLEAN_ENV, check=False)
    assert Path(p["runs"][0]["argv"][0]).parent.parent == Path(cfg["AEGIS_NN_LAB_VENV_DIR"])


def test_refuses_a_clone_without_its_data_junction(tmp_path):
    clone, conf, _ = make_clone(tmp_path, junction_ok=False)
    with pytest.raises(RT.Refused, match="does not resolve to the live data"):
        RT.build_plan(["-m", "a"], clone=clone, config_path=conf, environ=CLEAN_ENV)


def test_refuses_aegis_data_dir_and_a_missing_keys_file(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    with pytest.raises(RT.Refused, match="AEGIS_DATA_DIR"):
        RT.build_plan(["-m", "a"], clone=clone, config_path=conf,
                      environ={**CLEAN_ENV, "AEGIS_DATA_DIR": str(tmp_path)})
    with pytest.raises(RT.Refused, match="AEGIS_DOTENV_PATH"):
        RT.build_plan(["-m", "a"], clone=clone, config_path=conf,
                      environ={**CLEAN_ENV, "AEGIS_DOTENV_PATH": str(tmp_path / "nope.env")})


def test_refuses_a_missing_interpreter(tmp_path):
    clone, conf, _ = make_clone(tmp_path)
    with pytest.raises(RT.Refused, match="interpreter"):
        RT.build_plan(["--nn-lab", "-m", "a"], clone=clone, config_path=conf, environ=CLEAN_ENV)


# ───────────────────────────────────────────────────────────── B1: the paper_nav database

def test_the_live_database_passes(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    RT.check_pi_db(clone, Path(cfg["AEGIS_LIVE_PI_DB"]))
    RT.check_runtime(clone, cfg, CLEAN_ENV)            # the whole runtime check, db included


@pytest.mark.parametrize("damage,why", [
    ("missing", "cannot be read"),
    ("zero_bytes", "empty or not a SQLite"),
    ("not_sqlite", "empty or not a SQLite"),
])
def test_a_live_database_that_is_not_there_refuses(tmp_path, damage, why):
    clone, conf, cfg = make_clone(tmp_path)
    db = Path(cfg["AEGIS_LIVE_PI_DB"])
    db.unlink()
    if damage == "zero_bytes":
        db.write_bytes(b"")                           # what sqlite3.connect leaves behind
    elif damage == "not_sqlite":
        db.write_text("not a database", encoding="utf-8")
    with pytest.raises(RT.Refused, match=why):
        RT.check_pi_db(clone, db)


def test_a_database_inside_the_clone_refuses(tmp_path):
    clone, conf, _ = make_clone(tmp_path)
    inner = make_pi_db(clone / "backend" / "data" / "aegis_pi.db")
    with pytest.raises(RT.Refused, match="inside the clone"):
        RT.check_pi_db(clone, inner)


def test_a_stray_database_in_the_clone_is_a_split_brain(tmp_path):
    """Something opened the default path in the clone: refuse, never pick one."""
    clone, conf, cfg = make_clone(tmp_path)
    make_pi_db(clone / "backend" / "data" / "aegis_pi.db", rows=0)
    with pytest.raises(RT.Refused, match="split brain"):
        RT.check_pi_db(clone, Path(cfg["AEGIS_LIVE_PI_DB"]))


def test_a_tag_that_predates_the_override_refuses(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    (clone / "backend" / "config.py").write_text("DATA_DIR = 1\n", encoding="utf-8")
    with pytest.raises(RT.Refused, match="predates the paper_nav override"):
        RT.check_pi_db(clone, Path(cfg["AEGIS_LIVE_PI_DB"]))


def test_the_database_path_is_not_settable_per_task():
    with pytest.raises(RT.Refused, match="not allowed"):
        RT.parse_argv(["--set", "AEGIS_PI_DB_PATH=x", "-m", "a"])


def test_config_honours_the_override_and_refuses_a_missing_file(tmp_path, monkeypatch):
    from backend import config as C
    from backend import db as D
    assert D.DB_PATH == C.PI_DB_PATH                    # every writer imports DB_PATH from db
    monkeypatch.delenv("AEGIS_PI_DB_PATH", raising=False)
    assert C._pi_db_path() == C.DATA_DIR / "aegis_pi.db"
    live = make_pi_db(tmp_path / "live.db")
    monkeypatch.setenv("AEGIS_PI_DB_PATH", str(live))
    assert C._pi_db_path() == live.resolve()
    monkeypatch.setenv("AEGIS_PI_DB_PATH", str(tmp_path / "absent.db"))
    with pytest.raises(RuntimeError, match="refusing"):
        C._pi_db_path()
    assert not (tmp_path / "absent.db").exists()        # never created


# ───────────────────────────────────────────────────────────── exit codes, launch failure

@pytest.mark.skipif(not WIN, reason="32-bit exit codes are a Windows matter")
def test_a_crash_code_keeps_its_32_bits():
    assert RT.windows_exit_code(3221225477) == 3221225477 - 2 ** 32      # 0xC0000005
    assert RT.windows_exit_code(7) == 7 and RT.windows_exit_code(-1) == -1


def test_a_launch_that_fails_writes_a_row_and_exits_90(tmp_path):
    plan, _ = _plan(tmp_path, ["-m", "a"])

    def boom(*_a, **_k):
        raise FileNotFoundError("interpreter vanished")

    assert RT.run_plan(plan, popen=boom) == RT.REFUSED_RC
    rows = _rows(plan)
    assert rows[-1]["event"] == "launch_failed" and "vanished" in rows[-1]["why"]


# ───────────────────────────────────────────────────────────── M1: the job object (fakes)

class FakeJob:
    def __init__(self, mode):
        self.mode, self.adopted = mode, []

    def adopt(self, child):
        self.adopted.append(child.pid)


def test_allow_breakaway_is_parsed_and_planned(tmp_path):
    opt, _ = RT.parse_argv(["--allow-breakaway", "--pythonw", "-m", "scripts.task_keeper", "reader"])
    assert opt.allow_breakaway and opt.pythonw
    plan, _ = _plan(tmp_path, ["--allow-breakaway", "-m", "a"])
    assert plan["job"] == "breakaway"
    plan, _ = _plan(tmp_path / "t", ["-m", "a"])
    assert plan["job"] == "tree"


@pytest.mark.parametrize("mode", ["tree", "breakaway"])
def test_the_job_is_made_before_any_launch_and_only_breakaway_adopts_the_child(tmp_path, mode):
    plan, _ = _plan(tmp_path, (["--allow-breakaway"] if mode == "breakaway" else []) + ["-m", "a"])
    jobs, order = [], []

    def factory(m):
        order.append("job")
        jobs.append(FakeJob(m))
        return jobs[-1]

    RT.run_plan(plan, popen=lambda argv, **kw: (order.append("popen"), FakeChild(0))[1], job_factory=factory)
    assert order == ["job", "popen"] and jobs[0].mode == mode
    assert jobs[0].adopted == ([4242] if mode == "breakaway" else [])   # tree: the wrapper joined itself
    assert _rows(plan)[0]["job"] == mode


def test_no_job_means_no_launch(tmp_path):
    plan, _ = _plan(tmp_path, ["-m", "a"])

    def factory(_m):
        raise RT.Refused("AssignProcessToJobObject(the wrapper) failed")

    with pytest.raises(RT.Refused):
        RT.run_plan(plan, popen=lambda *a, **k: pytest.fail("must not launch"), job_factory=factory)


def test_a_child_that_cannot_join_the_job_is_killed(tmp_path):
    plan, _ = _plan(tmp_path, ["--allow-breakaway", "-m", "a"])
    killed = []

    class Child(FakeChild):
        def kill(self):
            killed.append(self.pid)

    class BadJob:
        def adopt(self, child):
            raise RT.Refused("AssignProcessToJobObject(child) failed")

    with pytest.raises(RT.Refused):
        RT.run_plan(plan, popen=lambda *a, **k: Child(0), job_factory=lambda _m: BadJob())
    assert killed == [4242]


# ───────────────────────────────────────────────────────────── run (fake process)

class FakeChild:
    def __init__(self, rc):
        self.rc, self.pid = rc, 4242

    def wait(self):
        return self.rc


def _plan(tmp_path, argv):
    clone, conf, cfg = make_clone(tmp_path)
    return RT.build_plan(argv, clone=clone, config_path=conf, environ=CLEAN_ENV, check=False), cfg


def _rows(plan):
    p = Path(plan["run_log"])
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_exit_code_passes_through_unchanged(tmp_path):
    plan, _ = _plan(tmp_path, ["-m", "a"])
    seen = []
    rc = RT.run_plan(plan, popen=lambda argv, **kw: (seen.append((argv, kw["cwd"])), FakeChild(7))[1])
    assert rc == 7
    assert seen[0][1] == plan["cwd"]
    rows = _rows(plan)
    assert [r["event"] for r in rows] == ["start", "end"]
    assert rows[0]["child_pid"] == 4242 and rows[1]["rc"] == 7


def test_segments_all_run_and_the_first_failure_is_the_exit_code(tmp_path):
    plan, _ = _plan(tmp_path, ["-m", "a", "--then", "-m", "b", "--then", "-m", "c"])
    codes = iter([0, 3, 5])
    ran = []
    rc = RT.run_plan(plan, popen=lambda argv, **kw: (ran.append(argv[2]), FakeChild(next(codes)))[1])
    assert ran == ["a", "b", "c"] and rc == 3


def test_a_stop_file_runs_nothing_and_exits_zero(tmp_path):
    plan, _ = _plan(tmp_path, ["--stop-file", "STOP", "-m", "a"])
    Path(plan["clone"], "STOP").write_text("", encoding="utf-8")
    rc = RT.run_plan(plan, popen=lambda *a, **k: pytest.fail("must not launch"))
    assert rc == 0 and _rows(plan)[-1]["event"] == "stopped"


def test_a_logged_segment_writes_to_its_log_without_a_console(tmp_path):
    plan, _ = _plan(tmp_path, ["--log", os.path.join("logs", "x.log"), "-m", "a"])
    kws = []
    RT.run_plan(plan, popen=lambda argv, **kw: (kws.append(kw), FakeChild(0))[1])
    assert kws[0]["stdout"] is not None and kws[0]["stderr"] == subprocess.STDOUT
    assert kws[0]["stdin"] == subprocess.DEVNULL
    if WIN:
        assert kws[0]["creationflags"] & RT.CREATE_NO_WINDOW
    assert Path(plan["clone"], "logs", "x.log").exists()


# ───────────────────────────────────────────────────────────── real processes (Windows)

PROBE = """import json, os, sys
open(os.environ["RT_PROBE_OUT"], "w", encoding="utf-8").write(json.dumps({
    "cwd": os.getcwd(), "argv": sys.argv[1:], "exe": sys.executable,
    "repo_root": os.environ.get("AEGIS_REPO_ROOT"), "dotenv": os.environ.get("AEGIS_DOTENV_PATH"),
    "pythonpath": os.environ.get("PYTHONPATH")}))
print("probe-stdout")
raise SystemExit(int(sys.argv[1]))
"""


def _probe_clone(tmp_path):
    clone, conf, cfg = make_clone(tmp_path)
    (clone / "rtprobe.py").write_text(PROBE, encoding="utf-8")
    out = tmp_path / "probe.json"
    env = {**os.environ, "RT_PROBE_OUT": str(out), "PYTHONPATH": "C:\\nowhere"}
    for k in RT.CONFIG_KEYS:
        env.pop(k, None)
    env.pop("AEGIS_DATA_DIR", None)
    return clone, cfg, out, env


@pytest.mark.skipif(not WIN, reason="the wrapper runs scheduled tasks on Windows")
@pytest.mark.parametrize("entry", ["python", "pythonw", "cmd"])
def test_a_real_child_exit_code_cwd_and_env_arrive_unchanged(tmp_path, entry):
    clone, cfg, out, env = _probe_clone(tmp_path)
    venv = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts"
    script = clone / "scripts" / "runtime_task.py"
    if entry == "cmd":
        argv = ["cmd.exe", "/d", "/c", str(clone / "scripts" / "runtime_task.cmd"), "-m", "rtprobe", "7"]
    else:
        exe = venv / ("pythonw.exe" if entry == "pythonw" else "python.exe")
        flags = ["--pythonw"] if entry == "pythonw" else []
        argv = [str(exe), "-I", str(script), *flags, "-m", "rtprobe", "7"]
    r = subprocess.run(argv, env=env, cwd=str(tmp_path), capture_output=True, text=True, timeout=120)
    assert r.returncode == 7, (r.stdout, r.stderr)
    got = json.loads(out.read_text(encoding="utf-8"))
    assert Path(got["cwd"]) == clone
    assert got["repo_root"] == str(clone)
    assert got["dotenv"] == cfg["AEGIS_DOTENV_PATH"]
    assert got["pythonpath"] is None
    if entry == "pythonw":
        assert Path(got["exe"]).name.lower() == "pythonw.exe"
    rows = [json.loads(x) for x in (Path(cfg["AEGIS_LIVE_OPTIMUS"]) / RT.RUN_LOG_REL)
            .read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "end" and rows[-1]["rc"] == 7


@pytest.mark.skipif(not WIN, reason="the wrapper runs scheduled tasks on Windows")
def test_a_logged_real_child_goes_to_its_log(tmp_path):
    clone, cfg, out, env = _probe_clone(tmp_path)
    exe = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "pythonw.exe"
    r = subprocess.run([str(exe), "-I", str(clone / "scripts" / "runtime_task.py"),
                        "--log", r"backend\data\optimus\probe.log", "-m", "rtprobe", "0"],
                       env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert "probe-stdout" in (clone / "backend" / "data" / "optimus" / "probe.log").read_text(encoding="utf-8")


@pytest.mark.skipif(not WIN, reason="the wrapper runs scheduled tasks on Windows")
@pytest.mark.parametrize("entry", ["python", "cmd"])
def test_a_refusal_is_exit_90(tmp_path, entry):
    clone, cfg, out, env = _probe_clone(tmp_path)
    env["AEGIS_DATA_DIR"] = str(tmp_path)
    if entry == "cmd":
        argv = ["cmd.exe", "/d", "/c", str(clone / "scripts" / "runtime_task.cmd"), "-m", "rtprobe", "0"]
    else:
        argv = [str(Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"), "-I",
                str(clone / "scripts" / "runtime_task.py"), "-m", "rtprobe", "0"]
    r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == RT.REFUSED_RC, (r.stdout, r.stderr)
    assert "REFUSED" in r.stderr and not out.exists()


# ───────────────────────────────────────────────────────────── M1: real processes (Windows)
#
# Every PID below is one this test started or that a process it started recorded; each is
# killed BY THAT PID in a finally block if it is still alive. Never by image name.

SLEEPER = r"""import json, os, subprocess, sys, time
mode, out = sys.argv[1], os.environ["RT_PROBE_DIR"]
def mark(name, pid):
    open(os.path.join(out, name + ".pid"), "w", encoding="ascii").write(str(pid))
mark("module", os.getpid())
if mode == "sleep":
    time.sleep(90)
elif mode == "spawn":
    # what task_keeper reader / sim_session do: a DETACHED, new-group child meant to outlive us
    code = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(90)"
    flags = 0x00000008 | 0x00000200 | 0x08000000
    subprocess.Popen([sys.executable, "-c", code, os.path.join(out, "grandchild.pid")],
                     creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(200):
        if os.path.exists(os.path.join(out, "grandchild.pid")):
            break
        time.sleep(0.05)
elif mode == "crash":
    import ctypes
    ctypes.windll.kernel32.ExitProcess(0xC0000005)
"""


def _alive(pid: int, wait_s: float = 0.0) -> bool:
    """True while `pid` runs; waits up to `wait_s` for it to exit (SYNCHRONIZE handle)."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x00100000 | 0x1000, False, int(pid))
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), int(wait_s * 1000)) != 0
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def _read_pid(path: Path, timeout: float = 30.0) -> int:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            return int(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError(f"{path} never appeared")


def _kill(pid) -> None:
    if pid and _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)                      # TerminateProcess by PID
        except OSError:
            pass


def _sleeper_clone(tmp_path):
    clone, cfg, _out, env = _probe_clone(tmp_path)
    (clone / "rtsleep.py").write_text(SLEEPER, encoding="utf-8")
    pdir = tmp_path / "pids"
    pdir.mkdir()
    env["RT_PROBE_DIR"] = str(pdir)
    return clone, cfg, pdir, env


def _wrapper_pid(cfg) -> int:
    log = Path(cfg["AEGIS_LIVE_OPTIMUS"]) / RT.RUN_LOG_REL
    t0 = time.time()
    while time.time() - t0 < 30:
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("event") == "start":
                    return int(row["wrapper_pid"])
        time.sleep(0.1)
    raise AssertionError("the wrapper never wrote its start row")


def _launch(clone, cfg, env, *flags_and_args):
    exe = Path(cfg["AEGIS_VENV_DIR"]) / "Scripts" / "python.exe"
    return subprocess.Popen([str(exe), "-I", str(clone / "scripts" / "runtime_task.py"), *flags_and_args],
                            env=env, cwd=str(clone), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.mark.skipif(not WIN, reason="Windows Job Objects")
@pytest.mark.parametrize("mode", ["tree", "breakaway"])
def test_killing_the_wrapper_by_its_own_pid_kills_the_module(tmp_path, mode):
    """Review 5 M1, measured: before the job object the module ran to completion after the
    wrapper was TerminateProcess'd (what the scheduler's time limit and End do)."""
    clone, cfg, pdir, env = _sleeper_clone(tmp_path)
    flags = ["--allow-breakaway"] if mode == "breakaway" else []
    outer = _launch(clone, cfg, env, *flags, "-m", "rtsleep", "sleep")
    module = wrapper = None
    try:
        module = _read_pid(pdir / "module.pid")
        wrapper = _wrapper_pid(cfg)
        assert wrapper != module and _alive(module)
        os.kill(wrapper, signal.SIGTERM)                       # the wrapper, by ITS recorded pid
        assert not _alive(module, wait_s=15), f"module {module} outlived its wrapper ({mode})"
    finally:
        _kill(module)
        _kill(wrapper)
        outer.kill()
        outer.wait(timeout=30)


@pytest.mark.skipif(not WIN, reason="Windows Job Objects")
def test_tree_mode_kills_a_detached_grandchild_when_the_task_ends(tmp_path):
    clone, cfg, pdir, env = _sleeper_clone(tmp_path)
    outer = _launch(clone, cfg, env, "-m", "rtsleep", "spawn")
    grand = None
    try:
        assert outer.wait(timeout=60) == 0
        grand = _read_pid(pdir / "grandchild.pid")
        assert not _alive(grand, wait_s=15), "tree mode must leave nothing behind"
    finally:
        _kill(grand)


@pytest.mark.skipif(not WIN, reason="Windows Job Objects")
def test_allow_breakaway_lets_a_detached_grandchild_outlive_the_task(tmp_path):
    """`task_keeper reader` / `task_keeper sim` start a process that must survive the task."""
    clone, cfg, pdir, env = _sleeper_clone(tmp_path)
    outer = _launch(clone, cfg, env, "--allow-breakaway", "-m", "rtsleep", "spawn")
    grand = None
    try:
        assert outer.wait(timeout=60) == 0
        grand = _read_pid(pdir / "grandchild.pid")
        assert _alive(grand, wait_s=3) and _alive(grand), "the detached process must survive"
    finally:
        _kill(grand)


@pytest.mark.skipif(not WIN, reason="32-bit exit codes")
def test_a_real_crash_code_reaches_the_caller_intact(tmp_path):
    clone, cfg, pdir, env = _sleeper_clone(tmp_path)
    outer = _launch(clone, cfg, env, "-m", "rtsleep", "crash")
    assert outer.wait(timeout=60) == 0xC0000005                # was -1 before (review 5 m1)
