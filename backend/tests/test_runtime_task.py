"""CH-05 wrapper (`scripts/runtime_task.py` + `.cmd`): plan, refusals, exit codes.

Everything runs in a temp "clone"; nothing touches the live data or a scheduled task. The
real-process tests (Windows only) launch a stdlib probe module through the wrapper and check
that its exit code, cwd and environment arrive unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import runtime_task as RT

REPO = Path(__file__).resolve().parents[2]
WIN = sys.platform == "win32"


def _venv_root() -> Path:
    """The interpreter running this test, as a venv root (`<root>/Scripts/python.exe`)."""
    exe = Path(sys.executable)
    return exe.parent.parent


def make_clone(tmp_path: Path, *, junction_ok: bool = True) -> tuple[Path, Path, dict]:
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    own = clone / "backend" / "data" / "optimus"
    own.mkdir(parents=True)
    live = own if junction_ok else (tmp_path / "live" / "optimus")
    live.mkdir(parents=True, exist_ok=True)
    keys = tmp_path / "keys.env"
    keys.write_text("", encoding="utf-8")
    cfg = {"AEGIS_LIVE_ROOT": str(tmp_path / "live"), "AEGIS_LIVE_OPTIMUS": str(live),
           "AEGIS_DOTENV_PATH": str(keys), "AEGIS_VENV_DIR": str(_venv_root()),
           "AEGIS_NN_LAB_VENV_DIR": str(tmp_path / "nnvenv"),
           "AEGIS_RUNTIME_ROOT": str(tmp_path / "rt"), "AEGIS_PUBLICATION_ROOT": str(tmp_path / "pub")}
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
