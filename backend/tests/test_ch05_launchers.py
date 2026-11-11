"""CH-05 (2026-11-11): the reader launchers start THIS checkout's code, never a
data-dir `.cmd`, and the process scan still recognises a supervisor or a reader
started the old way, so a mixed period (old checkout + release clone) cannot
start a second one.

Fake popen everywhere except two Windows-only real-process checks that run a
`python -c` probe in a temp dir (no reader, no browser, no network)."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts import night_reader_supervisor as S
from scripts import task_keeper as K

REPO = Path(__file__).resolve().parents[2]

# The live command lines at 2026-11-11 13:38 local (read-only Win32_Process scan): the brain's
# `task_keeper reader` started the OLD data-dir chain, cmd.exe -> venv python -> base python.
OLD_SUPERVISOR = [
    {"pid": 78820, "cmdline": r"C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe  "
                              r"-m scripts.night_reader_supervisor --until continuous "},
    {"pid": 135816, "cmdline": r'"C:\Users\mrthn\AppData\Local\Programs\Python\Python312\python.exe" '
                               r"-m scripts.night_reader_supervisor --until continuous "},
]
OLD_POOL = [
    r"C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe  -m scripts.reader_pool --handoff "
    r"--profile muratclaw --max-tabs 6 ",
    r'"C:\Users\mrthn\AppData\Local\Programs\Python\Python312\python.exe" -m scripts.reader_pool '
    r"--handoff --profile muratclaw --max-tabs 6 ",
]
CLONE_PY = r"C:\Users\mrthn\aegis-runtime\runtime-20261115\.venv\Scripts\python.exe"


class FakePopen:
    calls: list[dict] = []

    def __init__(self, argv, **kw):
        FakePopen.calls.append({"argv": list(argv), **kw})
        self.pid = 4242


@pytest.fixture(autouse=True)
def _reset():
    FakePopen.calls = []


# ───────────────────────────── the keeper: what it starts ─────────────────────────────

def test_the_keeper_starts_the_supervisor_module_from_its_own_checkout(tmp_path):
    log = tmp_path / "dj" / "supervisor_2026-11-11_1338.log"
    stdin = tmp_path / "empty_stdin.txt"
    pid = K.spawn_logged(K.supervisor_argv("continuous"), log, stdin_path=stdin, popen=FakePopen)
    assert pid == 4242
    (c,) = FakePopen.calls
    assert c["argv"][1:] == ["-m", "scripts.night_reader_supervisor", "--until", "continuous"]
    assert c["argv"][0] == K._child_python()
    assert Path(c["cwd"]) == K.REPO                     # THIS checkout, not a `cd /d` in a file
    assert not any(str(a).lower().endswith(".cmd") or a == "cmd.exe" for a in c["argv"])
    assert c["stdin"].name == str(stdin) and stdin.is_file() and stdin.stat().st_size == 0
    assert c["stdout"].name == str(log) and c["stdout"].mode == "ab"
    assert c["stderr"] is subprocess.STDOUT                        # `>> log 2>&1`
    if sys.platform == "win32":
        assert c["creationflags"] & 0x08000000                        # CREATE_NO_WINDOW
        assert not c["creationflags"] & 0x00000008                    # not DETACHED_PROCESS


def test_the_new_command_line_is_the_one_the_scan_already_matches():
    argv = K.supervisor_argv("continuous", py=CLONE_PY)
    row = {"pid": 1, "cmdline": subprocess.list2cmdline(argv)}
    assert [r["pid"] for r in K.supervisor_rows([row])] == [1]
    # a one-shot probe from the clone is still not "a supervisor"
    probe = {"pid": 2, "cmdline": subprocess.list2cmdline([CLONE_PY, "-m", K.SUPERVISOR_MODULE,
                                                           "--probe"])}
    assert K.supervisor_rows([probe]) == []


@pytest.mark.parametrize("rows", [
    OLD_SUPERVISOR,                                                    # old chain only
    [{"pid": 9, "cmdline": subprocess.list2cmdline(K.supervisor_argv("continuous", py=CLONE_PY))}],
    OLD_SUPERVISOR + [{"pid": 9, "cmdline": "x -m scripts.night_reader_supervisor --until 08:00"}],
], ids=["old-checkout", "release-clone", "both"])
def test_mixed_period_a_supervisor_started_either_way_blocks_a_second(tmp_path, rows):
    out = K.ensure_reader(scan=lambda: rows,
                          launch=lambda *a: pytest.fail("a second supervisor was launched"),
                          stop_path=tmp_path / "STOP", now_local=datetime(2026, 11, 11, 21, 0),
                          log_path=tmp_path / "k.jsonl")
    assert out["action"] == "alive" and out["pids"] == [r["pid"] for r in rows]


def test_a_launch_row_names_the_code_root(tmp_path):
    out = K.ensure_reader(scan=lambda: [], launch=lambda u, p: 31,
                          stop_path=tmp_path / "STOP", now_local=datetime(2026, 11, 11, 21, 0),
                          log_path=tmp_path / "k.jsonl")
    assert out["launched_pid"] == 31 and out["code_root"] == str(K.REPO)
    assert out["until"] == "continuous"


@pytest.mark.parametrize("hhmm,action", [("16:44", "launch"), ("16:45", "paused"),
                                         ("17:04", "paused"), ("17:05", "launch")])
def test_the_keeper_does_not_launch_in_the_iif_quiet_window(tmp_path, hhmm, action):
    h, m = map(int, hhmm.split(":"))
    launched = []
    out = K.ensure_reader(scan=lambda: [], launch=lambda u, p: launched.append(u) or 5,
                          stop_path=tmp_path / "STOP", now_local=datetime(2026, 11, 11, h, m),
                          log_path=tmp_path / "k.jsonl")
    assert (out["action"] == "launch") is (action == "launch")
    assert bool(launched) is (action == "launch")
    if action == "paused":
        assert "16:45-17:05" in out["why"]


def test_the_keeper_and_the_supervisor_agree_on_the_quiet_window():
    for minute in range(24 * 60):
        t = datetime(2026, 11, 11, minute // 60, minute % 60)
        assert K.reader_iif_quiet(t) is S.reader_iif_quiet(t), t


# ─────────────────────────── the supervisor: what it starts ───────────────────────────

def test_the_pool_is_a_launch_of_this_checkout_with_the_old_arguments_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EMPTY_STDIN", tmp_path / "empty_stdin.txt")
    monkeypatch.setattr(S, "LAUNCH_RECORD", tmp_path / "reader_launch.json")
    spec = S.pool_launch(until="continuous", day="2026-11-11", max_tabs=6)
    assert spec.module == "scripts.reader_pool"
    assert spec.args[:5] == ("--handoff", "--profile", "muratclaw", "--max-tabs", spec.args[4])
    assert "--until" not in spec.args
    assert spec.out == S.DJ / "reader_pool_2026-11-11.log"
    assert spec.err == S.DJ / "reader_pool_2026-11-11.log.err"
    spec = S.Launch(spec.module, spec.args, tmp_path / "p.log", tmp_path / "p.log.err")
    assert S.launch(spec, popen=FakePopen) == 4242
    (c,) = FakePopen.calls
    assert c["argv"] == [S.PY, "-m", "scripts.reader_pool", *spec.args]
    assert Path(c["cwd"]) == S.REPO
    assert c["stdin"].name == str(tmp_path / "empty_stdin.txt")       # a regular file, not NUL
    assert c["stdout"].name == str(tmp_path / "p.log")
    assert c["stderr"].name == str(tmp_path / "p.log.err")
    rec = json.loads((tmp_path / "reader_launch.json").read_text(encoding="utf-8"))
    assert rec["pid"] == 4242 and rec["cwd"] == str(S.REPO) and rec["argv"] == c["argv"]
    # the scan the supervisor uses finds a pool started this way and the old way
    pat = re.compile(S.READER_CMDLINE.strip("'"))
    assert pat.search(subprocess.list2cmdline(c["argv"]))
    assert all(pat.search(line) for line in OLD_POOL)


def test_the_queue_launch_is_what_queue_run_cmd_ran(tmp_path):
    spec = S.queue_launch(S.DEFAULT_QUEUE)
    assert spec.module == "scripts.dowjones_pull"
    assert spec.args == ("--queue", str(S.DEFAULT_QUEUE), "--handoff", "--profile", "muratclaw",
                         "--workers", "3")
    assert spec.out == S.DJ / "queue_run_2026-09-28b.log"
    assert spec.err == S.DJ / "queue_run_2026-09-28b.log.err"
    assert S.queue_of(spec) == S.DEFAULT_QUEUE
    assert S.queue_logs(spec) == [spec.out, spec.err]


def test_a_cmd_path_is_refused_by_launch_and_by_the_cli(tmp_path):
    with pytest.raises(TypeError, match="retired"):
        S.launch(tmp_path / "reader_pool_run.cmd", popen=FakePopen)
    assert FakePopen.calls == []
    with pytest.raises(SystemExit) as e:
        S.main(["--queue-cmd", str(tmp_path / "queue_run.cmd")])
    assert e.value.code == 2                                          # a red exit, not a fallback


def test_a_locked_log_falls_back_to_a_per_launch_sibling(tmp_path, monkeypatch):
    real = Path.open
    target = tmp_path / "pool.log"

    def locked(self, *a, **k):
        if self == target:
            raise PermissionError("held by a cmd >> redirection")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "open", locked)
    fh, used = S._open_append(target)
    fh.close()
    assert used != target and used.parent == tmp_path and used.name.startswith("pool_")


# ────────────────────── no data-dir launcher on any path main executes ─────────────────

def _code_strings(path: Path) -> list[str]:
    """String constants in calls other than print/ap.error, docstrings excluded
    (CLAUDE.md item 10: a guard must not match the sentence explaining the ban)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name in ("print", "error"):
            continue
        for arg in list(n.args) + [k.value for k in n.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return out


@pytest.mark.parametrize("rel", ["scripts/task_keeper.py", "scripts/night_reader_supervisor.py",
                                 "scripts/always_on_lab.py"])
def test_no_launcher_file_is_executed(rel):
    src = (REPO / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"SUPERVISOR_CMD", "POOL_CMD"}, "the data-dir launcher constants are retired"
    for s in _code_strings(REPO / rel):
        assert s.lower() != "cmd.exe", f"{rel} starts cmd.exe"
        assert not re.search(r"(supervisor_run|queue_run|queue_run_rolling|reader_pool_run|"
                             r"always_on_lab)\.cmd", s), f"{rel} names a data-dir launcher: {s!r}"


# ──────────────────────────── real processes (Windows only) ────────────────────────────

PROBE = ("import ctypes, json, os, sys; h = ctypes.windll.kernel32.GetConsoleWindow(); "
         "print(json.dumps({'cwd': os.getcwd(), 'isatty': sys.stdin.isatty(), 'hwnd': h})); "
         "print('to-stderr', file=sys.stderr)")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console semantics")
def test_a_real_child_is_windowless_reads_a_regular_file_and_appends_both_streams(tmp_path):
    log = tmp_path / "child.log"
    log.write_bytes(b"earlier line\n")
    pid = K.spawn_logged([sys.executable, "-c", PROBE], log, stdin_path=tmp_path / "empty.txt",
                         cwd=tmp_path)
    assert pid > 0
    deadline = datetime.now().timestamp() + 30
    while datetime.now().timestamp() < deadline:
        txt = log.read_text(encoding="utf-8", errors="replace")
        if "to-stderr" in txt:
            break
        __import__("time").sleep(0.2)
    txt = log.read_text(encoding="utf-8", errors="replace")
    assert txt.startswith("earlier line\n"), "the log is appended, never truncated"
    row = json.loads(next(ln for ln in txt.splitlines() if ln.startswith("{")))
    assert Path(row["cwd"]) == tmp_path
    assert row["isatty"] is False, "stdin must be a regular file, not NUL (a character device)"
    assert row["hwnd"] == 0, "the child must not get a console window"
    assert "to-stderr" in txt                                          # 2>&1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console semantics")
def test_a_real_reader_launch_writes_both_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EMPTY_STDIN", tmp_path / "empty_stdin.txt")
    monkeypatch.setattr(S, "LAUNCH_RECORD", tmp_path / "reader_launch.json")
    monkeypatch.setattr(S, "PY", sys.executable)
    probe = tmp_path / "probe_mod.py"
    probe.write_text(PROBE.replace("; ", "\n"), encoding="utf-8")
    spec = S.Launch("probe_mod", (), tmp_path / "out.log", tmp_path / "out.log.err")
    real = subprocess.Popen

    def popen(argv, **kw):                       # run the probe module from tmp_path
        kw["cwd"] = str(tmp_path)
        return real(argv, **kw)
    pid = S.launch(spec, popen=popen)
    assert pid > 0
    deadline = datetime.now().timestamp() + 30
    while datetime.now().timestamp() < deadline and not (
            (tmp_path / "out.log.err").exists() and "to-stderr" in
            (tmp_path / "out.log.err").read_text(encoding="utf-8", errors="replace")):
        __import__("time").sleep(0.2)
    row = json.loads((tmp_path / "out.log").read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["isatty"] is False and row["hwnd"] == 0
    assert "to-stderr" in (tmp_path / "out.log.err").read_text(encoding="utf-8")
