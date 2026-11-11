"""The ONE wrapper every scheduled task's action points at (CH-05, wrapper PR "W").

    <venv>\\Scripts\\pythonw.exe -I <clone>\\scripts\\runtime_task.py [options] -m <module> [args...]
    <clone>\\scripts\\runtime_task.cmd [options] -m <module> [args...]      (a console; same logic)

Options (before the first `-m`):
    --pythonw            run the module under the venv's pythonw.exe (no stdout; today's default
                         for windowless tasks)
    --nn-lab             run under nn_lab's own venv (AEGIS_NN_LAB_VENV_DIR)
    --set NAME=VALUE     one per-task environment variable (allow-listed names only)
    --stop-file PATH     exit 0 without running when PATH exists (repeatable; relative = the clone)
    --allow-breakaway    processes the module STARTS may outlive the task (see KILL SEMANTICS);
                         only for a task whose job is to start something long-lived
    --print-plan         print what would run (JSON) and exit 0; runs nothing
Segments:
    [--log PATH] -m <module> [args...] [--then [--log PATH] -m <module> [args...]]...
    --log appends the module's stdout+stderr to PATH (relative = the clone, i.e. through the data
    junction) and runs it under python.exe with no console window. Segments run in order, all of
    them; the exit code is the first non-zero segment's, else 0.

WHAT IT DOES, IN ORDER
======================
1. Finds its clone from its OWN location (`<clone>\\scripts\\runtime_task.py`), never from cwd.
2. Reads `scripts/runtime_task.config`; an environment variable of the same name wins.
3. REFUSES (exit 90, a red exit, one line to the run log) when: a config key is missing; the
   interpreter is absent; `AEGIS_DOTENV_PATH` names no file; `AEGIS_DATA_DIR` is set (the env
   var alone is the split brain `runtime_preflight` fails on); the clone's own
   `backend/data/optimus` does not resolve to `AEGIS_LIVE_OPTIMUS` (no junction = this task
   would write main's tracked copies inside the clone while every other task writes live data);
   or the paper_nav database the child would open is not the live one (B1, below).
4. Builds the child environment: `AEGIS_DOTENV_PATH` (the task points at the keys file; nothing
   copies or prints it), `AEGIS_PI_DB_PATH` (the live paper_nav database), `AEGIS_REPO_ROOT` =
   the clone (a stale inherited value cannot point a task back at the WIP checkout),
   `AEGIS_RUNTIME_CLONE`, `AEGIS_PUBLICATION_ROOT`, no `PYTHONPATH`/`PYTHONHOME`.
5. `cd` into the clone and runs `<venv>\\Scripts\\python[w].exe -m <module> <args>` inside a
   Windows Job Object (KILL SEMANTICS, below).
6. Returns the module's exit code UNCHANGED (a crash code >= 2**31 is passed as the signed
   value Windows stores, so LastTaskResult shows 0xC0000005 rather than -1), and appends a
   start and an end row (pid, commit, rc, seconds) to
   `<AEGIS_LIVE_OPTIMUS>/runtime_switch/runtime_task_runs.jsonl` (the shared data dir, so a
   refusal in a clone without its junction does not dirty that clone). A launch that fails
   writes a `launch_failed` row and exits 90.

THE PAPER_NAV DATABASE (review 5, B1)
=====================================
`backend/data/aegis_pi.db` is gitignored and outside the optimus junction; a clone has no
such file, and `sqlite3.connect` would create an EMPTY one there. So the wrapper exports
`AEGIS_PI_DB_PATH = AEGIS_LIVE_PI_DB` (honoured by `config.PI_DB_PATH` -> `backend.db`) and
refuses when: that file is missing, empty or not SQLite; it resolves inside the clone; the
clone already holds its OWN `backend/data/aegis_pi.db` (something opened the default path:
a split brain); or the clone's code predates the override (the child would open the clone's
path whatever the wrapper exported). `runtime_preflight --expect-pi-db` is the stronger check
(the child's resolved `DB_PATH`, and `paper_nav` must hold rows).

KILL SEMANTICS (review 5, M1; measured 2026-11-11)
==================================================
The venv's `python[w].exe` is a launcher: it runs the real interpreter in its own kill-on-close
job, which ALSO permits silent breakaway. A process the wrapper starts therefore broke away
from the job Task Scheduler's time limit kills, and a hung module outlived its task. Now:
  default (tree)     the wrapper puts ITSELF into a new job with
                     JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and no breakaway, before it starts
                     anything. Everything the module starts, at any depth, is in that job, and
                     when the wrapper exits -- normally, by TerminateProcess, by the scheduler's
                     time limit or End -- the kernel kills all of it. Nothing is orphaned.
  --allow-breakaway  the CHILD (the venv launcher) is put into a kill-on-close job that permits
                     silent breakaway, right after it starts. Killing the wrapper still kills
                     the module (the launcher dies with the job, the interpreter with the
                     launcher's own job), but what the module deliberately STARTS survives the
                     task -- exactly the venv launcher's behaviour before the switch. For tasks
                     whose job is to start a long-lived process: `task_keeper reader` (the
                     reader supervisor) and `task_keeper sim` (the detached sim session). In
                     tree mode those would be killed the moment the task returned.
If the job cannot be created or joined the wrapper REFUSES (90) before starting anything: a
task whose time limit would no longer kill it is the failure being fixed.

WHY A PYTHON CORE AND NOT ONLY A .cmd (measured 2026-11-11)
===========================================================
Every task runs with LogonType InteractiveToken, so a task whose action is a `.cmd` opens a
console window for as long as it runs (the "console windows flashing" complaint of 09-11), and
`conhost.exe --headless cmd /c "exit 7"` returned 0 here: it hides the window and EATS the exit
code. So task actions run THIS file under the venv's `pythonw.exe` (no window, exit code kept)
and the `.cmd` is the console entry for a human. One file holds the logic; both entries use it.

Stdlib only, imports nothing from the repository: it runs with `-I` before anything else is
trusted, and its own failure must not depend on the code it is about to launch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

CLONE = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).resolve().with_name("runtime_task.config")

#: The wrapper itself refused (configuration, interpreter, split brain). Distinct from any
#: module's own codes, which pass through unchanged.
REFUSED_RC = 90

CONFIG_KEYS: tuple[str, ...] = (
    "AEGIS_LIVE_ROOT", "AEGIS_LIVE_OPTIMUS", "AEGIS_LIVE_PI_DB", "AEGIS_DOTENV_PATH",
    "AEGIS_VENV_DIR", "AEGIS_NN_LAB_VENV_DIR", "AEGIS_PUBLICATION_ROOT",
)
#: Release clones live BESIDE the live checkout (review 5, B2): `<parent>\\aegis-runtime-<tag>`,
#: so `REPO.parent` -- which code uses to find aegis-alpha-terminal, optimus, `Aegis module`
#: and the publication checkout -- is the same directory it is for the live checkout.
CLONE_PREFIX = "aegis-runtime-"
#: The first 16 bytes of every SQLite 3 database file.
SQLITE_MAGIC = b"SQLite format 3\x00"
#: The names `--set` may carry. Keys and paths that decide WHICH code or data runs are not
#: settable per task: they come from the config file (one place) or the wrapper itself.
SETTABLE: frozenset[str] = frozenset({
    "AEGIS_PERSONAL_MODE", "AEGIS_IGNORE_DOTENV", "AEGIS_PUBLIC_RECEIPTS_DIR",
    "AEGIS_PUBLICATION_ROOT", "AEGIS_TELEGRAM_AGENT_MODE",
})
#: Inherited variables that would make the child import or read something other than the clone.
CLEARED: tuple[str, ...] = ("PYTHONPATH", "PYTHONHOME")
#: Under AEGIS_LIVE_OPTIMUS (the shared data, not the clone): a refusal in a clone that has no
#: junction yet must not dirty it, and every clone's rows land in one file.
RUN_LOG_REL = Path("runtime_switch") / "runtime_task_runs.jsonl"
CREATE_NO_WINDOW = 0x08000000


class Refused(RuntimeError):
    """The wrapper will not launch. Always a red exit (REFUSED_RC), never a silent 0."""


@dataclass
class Segment:
    module: str
    args: list[str] = field(default_factory=list)
    log: Optional[str] = None


@dataclass
class Options:
    pythonw: bool = False
    nn_lab: bool = False
    sets: dict[str, str] = field(default_factory=dict)
    stop_files: list[str] = field(default_factory=list)
    print_plan: bool = False
    allow_breakaway: bool = False


# ───────────────────────────────────────────────────────────── config

def read_config(path: Path = CONFIG_PATH, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """`KEY=VALUE` lines; an environment variable of the same name (non-empty) wins.
    An unknown key or a missing one REFUSES: a typo must not become a silent default."""
    environ = os.environ if environ is None else environ
    vals: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise Refused(f"config {path} unreadable ({type(exc).__name__})") from None
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in CONFIG_KEYS:
            raise Refused(f"config {Path(path).name} line {n}: unknown or malformed entry {key!r}")
        vals[key] = value
    for key in CONFIG_KEYS:
        env = (environ.get(key) or "").strip()
        if env:
            vals[key] = env
    missing = [k for k in CONFIG_KEYS if not vals.get(k)]
    if missing:
        raise Refused(f"config is missing {', '.join(missing)}")
    return vals


# ───────────────────────────────────────────────────────────── argv

_FLAG_NO_VALUE = {"--pythonw": "pythonw", "--nn-lab": "nn_lab", "--print-plan": "print_plan",
                  "--allow-breakaway": "allow_breakaway"}


def parse_argv(argv: Sequence[str]) -> tuple[Options, list[Segment]]:
    """Options, then one or more `[--log P] -m module args...` segments joined by `--then`."""
    a = list(argv)
    opt = Options()
    i = 0
    while i < len(a) and a[i] not in ("-m", "--log"):
        tok = a[i]
        if tok in _FLAG_NO_VALUE:
            setattr(opt, _FLAG_NO_VALUE[tok], True)
            i += 1
            continue
        if tok in ("--set", "--stop-file"):
            if i + 1 >= len(a):
                raise Refused(f"{tok} needs a value")
            val = a[i + 1]
            if tok == "--set":
                name, sep, value = val.partition("=")
                if not sep or name not in SETTABLE:
                    raise Refused(f"--set {name!r} is not allowed (allowed: {', '.join(sorted(SETTABLE))})")
                opt.sets[name] = value
            else:
                opt.stop_files.append(val)
            i += 2
            continue
        raise Refused(f"unknown wrapper option {tok!r} (options come before the first -m)")
    segments: list[Segment] = []
    while i < len(a):
        log = None
        if a[i] == "--log":
            if i + 1 >= len(a):
                raise Refused("--log needs a path")
            log, i = a[i + 1], i + 2
        if i >= len(a) or a[i] != "-m" or i + 1 >= len(a):
            raise Refused("each segment is `[--log PATH] -m <module> [args...]`")
        module, i = a[i + 1], i + 2
        if not module.replace(".", "").replace("_", "").isalnum():
            raise Refused(f"{module!r} is not a dotted module name")
        args: list[str] = []
        while i < len(a) and a[i] != "--then":
            args.append(a[i])
            i += 1
        if i < len(a):          # skip "--then"
            i += 1
            if i >= len(a):
                raise Refused("--then must be followed by a segment")
        segments.append(Segment(module, args, log))
    if not segments:
        raise Refused("nothing to run: give `-m <module> [args...]`")
    if opt.pythonw and any(s.log for s in segments):
        raise Refused("--pythonw has no stdout to log; drop --pythonw (a logged segment runs "
                      "python.exe with no console window)")
    return opt, segments


# ───────────────────────────────────────────────────────────── plan

def _resolve(p: Path) -> Path:
    try:
        return Path(os.path.realpath(p))
    except OSError:
        return Path(p)


def _in_clone(p: str, clone: Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else clone / q


def interpreter(cfg: Mapping[str, str], opt: Options, *, logged: bool) -> Path:
    venv = Path(cfg["AEGIS_NN_LAB_VENV_DIR"] if opt.nn_lab else cfg["AEGIS_VENV_DIR"])
    exe = "pythonw.exe" if (opt.pythonw and not logged) else "python.exe"
    if os.name != "nt":                       # tests on a non-Windows CI runner
        exe = "python"
    return venv / ("Scripts" if os.name == "nt" else "bin") / exe


def check_runtime(clone: Path, cfg: Mapping[str, str], environ: Mapping[str, str]) -> None:
    """The refusals that keep a task from running in a split brain or keyless."""
    if (environ.get("AEGIS_DATA_DIR") or "").strip():
        raise Refused("AEGIS_DATA_DIR is set: with a data junction it is redundant, without one it "
                      "is the split brain runtime_preflight fails on; unset it")
    if not Path(cfg["AEGIS_DOTENV_PATH"]).is_file():
        raise Refused("AEGIS_DOTENV_PATH names no file (the keys file is pointed at, never copied)")
    own = clone / "backend" / "data" / "optimus"
    live = Path(cfg["AEGIS_LIVE_OPTIMUS"])
    if not live.is_dir():
        raise Refused(f"AEGIS_LIVE_OPTIMUS {live} is not a directory")
    if _resolve(own) != _resolve(live):
        raise Refused(f"{own} does not resolve to the live data {live}: create the junction "
                      "(scripts/runtime_release.py) before pointing a task here")
    check_pi_db(clone, Path(cfg["AEGIS_LIVE_PI_DB"]))


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(_resolve(a))) == os.path.normcase(str(_resolve(b)))


def _inside(child: Path, parent: Path) -> bool:
    c = os.path.normcase(str(_resolve(child)))
    p = os.path.normcase(str(_resolve(parent)))
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


#: The text the clone's own code must contain for AEGIS_PI_DB_PATH to be honoured. A
#: presence check, necessary and not sufficient: runtime_preflight imports backend.db and
#: compares the resolved DB_PATH itself.
_DB_OVERRIDE_MARKERS = ((Path("backend") / "config.py", "AEGIS_PI_DB_PATH"),
                        (Path("backend") / "db.py", "PI_DB_PATH"))


def check_pi_db(clone: Path, live_db: Path) -> None:
    """B1: the child must open the LIVE paper_nav database, never a new one in the clone."""
    try:
        with open(live_db, "rb") as fh:
            head = fh.read(len(SQLITE_MAGIC))
    except OSError as exc:
        raise Refused(f"AEGIS_LIVE_PI_DB {live_db} cannot be read ({type(exc).__name__}): the "
                      "paper_nav store must exist before a task may write it") from None
    if head != SQLITE_MAGIC:
        raise Refused(f"AEGIS_LIVE_PI_DB {live_db} is empty or not a SQLite database")
    if _inside(live_db, clone):
        raise Refused(f"AEGIS_LIVE_PI_DB {live_db} is inside the clone {clone}; it must be the "
                      "live checkout's file")
    own = clone / "backend" / "data" / "aegis_pi.db"
    if os.path.lexists(own) and not _same(own, live_db):
        raise Refused(f"{own} exists and is not the live database: something opened the default "
                      "path in this clone (a split brain). Move it aside (never delete paper_nav "
                      "rows) and find the writer before pointing a task here")
    for rel, marker in _DB_OVERRIDE_MARKERS:
        try:
            text = (clone / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if marker not in text:
            raise Refused(f"{clone / rel} does not mention {marker}: this tag predates the "
                          "paper_nav override, so the child would open the clone's own "
                          "backend/data/aegis_pi.db; release a newer tag")


def child_env(clone: Path, cfg: Mapping[str, str], opt: Options, environ: Mapping[str, str],
              *, logged: bool) -> dict[str, str]:
    env = {k: v for k, v in environ.items() if k not in CLEARED}
    env["AEGIS_DOTENV_PATH"] = cfg["AEGIS_DOTENV_PATH"]
    env["AEGIS_PI_DB_PATH"] = cfg["AEGIS_LIVE_PI_DB"]
    env["AEGIS_PUBLICATION_ROOT"] = cfg["AEGIS_PUBLICATION_ROOT"]
    env["AEGIS_REPO_ROOT"] = str(clone)
    env["AEGIS_RUNTIME_CLONE"] = str(clone)
    env.update(opt.sets)
    if logged:
        env["PYTHONUNBUFFERED"] = "1"
    return env


def build_plan(argv: Sequence[str], *, clone: Path = CLONE, config_path: Path = CONFIG_PATH,
               environ: Mapping[str, str] | None = None, check: bool = True) -> dict:
    """Everything `main` will do, as data. Raises Refused; runs nothing."""
    environ = dict(os.environ if environ is None else environ)
    opt, segments = parse_argv(argv)
    cfg = read_config(config_path, environ)
    if check:
        check_runtime(clone, cfg, environ)
    runs = []
    for s in segments:
        logged = s.log is not None
        exe = interpreter(cfg, opt, logged=logged)
        if check and not exe.is_file():
            raise Refused(f"interpreter {exe} does not exist")
        runs.append({"argv": [str(exe), "-m", s.module, *s.args],
                     "log": str(_in_clone(s.log, clone)) if logged else None,
                     "env": child_env(clone, cfg, opt, environ, logged=logged)})
    return {"clone": str(clone), "cwd": str(clone),
            "run_log": str(Path(cfg["AEGIS_LIVE_OPTIMUS"]) / RUN_LOG_REL),
            "stop_files": [str(_in_clone(p, clone)) for p in opt.stop_files],
            "job": "breakaway" if opt.allow_breakaway else "tree",
            "print_plan": opt.print_plan, "runs": runs}


# ───────────────────────────────────────────────────────────── run

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clone_head(clone: Path) -> Optional[str]:
    """The commit this clone is at, read from `.git/HEAD` (no git process in a task's path)."""
    try:
        head = (clone / ".git" / "HEAD").read_text(encoding="ascii").strip()
        if head.startswith("ref: "):
            ref = clone / ".git" / head[5:]
            return ref.read_text(encoding="ascii").strip() if ref.is_file() else head
        return head
    except OSError:
        return None


def _run_row(run_log: Optional[str], row: dict) -> None:
    """Append one row; a failure to log never changes the task's exit code."""
    if not run_log:
        return
    try:
        p = Path(run_log)
        if not p.parent.parent.is_dir():          # the live data dir itself must already exist
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def _say(msg: str) -> None:
    if sys.stderr is not None:                      # pythonw has no stderr
        try:
            print(msg, file=sys.stderr)
        except OSError:
            pass


def _windowless() -> bool:
    return sys.stdout is None or Path(sys.executable).name.lower() == "pythonw.exe"


# ───────────────────────────────────────────────────────────── job object (M1)

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
_JOB_EXTENDED_LIMIT_INFORMATION = 9


class KillOnCloseJob:
    """A Windows Job Object that kills its processes when its last handle closes.

    The handle is held on this object for the life of the wrapper and NEVER closed by
    code: closing it is the kill, and in tree mode the wrapper itself is a member. The
    kernel closes it when the wrapper exits for any reason, including TerminateProcess,
    which runs no user code. Stdlib ctypes only (the same structures as
    `llama_server.bind_lifetime`, with HANDLE restypes declared: ctypes' default c_int
    truncates a 64-bit handle).
    """

    def __init__(self, *, breakaway: bool) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                wintypes.LPVOID, wintypes.DWORD]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        self._k32 = k32

        class _BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class _EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.breakaway = breakaway
        h = k32.CreateJobObjectW(None, None)
        if not h:
            raise Refused(f"CreateJobObject failed (winerror {ctypes.get_last_error()})")
        info = _EXT()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | (JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK if breakaway else 0))
        if not k32.SetInformationJobObject(h, _JOB_EXTENDED_LIMIT_INFORMATION,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            raise Refused(f"SetInformationJobObject failed (winerror {ctypes.get_last_error()})")
        self.handle = h

    def _assign(self, process_handle, what: str) -> None:
        if not self._k32.AssignProcessToJobObject(self.handle, process_handle):
            raise Refused(f"AssignProcessToJobObject({what}) failed "
                          f"(winerror {self._ctypes.get_last_error()}): this task would not be "
                          "killed with its wrapper")

    def adopt_self(self) -> None:
        """Tree mode: the wrapper joins the job BEFORE it starts anything, so every
        descendant is born inside it (no race with a child that spawns fast)."""
        self._assign(self._k32.GetCurrentProcess(), "the wrapper")

    def adopt(self, popen_child) -> None:
        """Breakaway mode: the child joins right after it starts."""
        self._assign(int(popen_child._handle), f"child pid {popen_child.pid}")


def make_job(mode: str):
    """The job for `plan['job']`, or None off Windows. Raises Refused."""
    if os.name != "nt":
        return None
    job = KillOnCloseJob(breakaway=(mode == "breakaway"))
    if mode == "tree":
        job.adopt_self()
    return job


#: Exit codes are 32-bit on Windows. Python turns SystemExit(n >= 2**31) into -1, so an
#: access violation (0xC0000005 = 3221225477) reached Task Scheduler as -1. Pass the signed
#: value instead; Windows stores the same 32 bits.
def windows_exit_code(rc: int) -> int:
    rc = int(rc)
    if os.name == "nt" and 2 ** 31 <= rc < 2 ** 32:
        return rc - 2 ** 32
    return rc


def run_plan(plan: dict, *, popen=subprocess.Popen, job_factory=None) -> int:
    """Run every segment. `job_factory(mode)` makes the Job Object; the default is the real
    one only with the real Popen on Windows (an in-process test must never put the test
    runner into a kill-on-close job)."""
    clone, log = Path(plan["clone"]), plan.get("run_log")
    base = {"wrapper_pid": os.getpid(), "clone": str(clone), "head": clone_head(clone)}
    for sf in plan["stop_files"]:
        if Path(sf).exists():
            _run_row(log, {**base, "utc": _utc(), "event": "stopped", "stop_file": sf, "rc": 0})
            _say(f"runtime_task: STOP file present ({sf}); nothing ran")
            return 0
    mode = plan.get("job", "tree")
    if job_factory is None:
        job_factory = make_job if popen is subprocess.Popen else (lambda _m: None)
    job = job_factory(mode)                 # raises Refused before anything starts
    rc_final = 0
    for n, r in enumerate(plan["runs"]):
        flags = CREATE_NO_WINDOW if os.name == "nt" and (r["log"] or _windowless()) else 0
        t0 = time.time()
        fh = None
        try:
            if r["log"]:
                Path(r["log"]).parent.mkdir(parents=True, exist_ok=True)
                fh = open(r["log"], "ab")
            # stdin is a pipe closed at once (EOF), NOT the null device: the Windows CRT's
            # `_isatty()` is True for ANY character device, NUL included, and
            # `run_night_launcher --scheduled` marks a firing with isatty() True as
            # `contradicted` (run_night_launcher.py:372-400, measured 2026-08-19). A pipe
            # is not a character device, needs no console and no file on disk.
            # With no --log and no handles of our own (Task Scheduler starts pythonw with
            # none), stdout/stderr must be the null device, never None: because stdin is
            # a pipe, subprocess would otherwise hand the child a stdout pipe nobody reads,
            # and its first print raises (AegisStraddleForward exited 120 in 2 s on the
            # first real repoint, 2026-11-11). A console entry keeps inheriting.
            quiet = fh is None and _windowless()
            child = popen(r["argv"], cwd=plan["cwd"], env=r["env"], stdin=subprocess.PIPE,
                          stdout=fh if fh else (subprocess.DEVNULL if quiet else None),
                          stderr=(subprocess.STDOUT if fh else
                                  (subprocess.DEVNULL if quiet else None)),
                          creationflags=flags)
            if getattr(child, "stdin", None) is not None:
                child.stdin.close()
        except OSError as exc:
            if fh is not None:
                fh.close()
            _run_row(log, {**base, "utc": _utc(), "event": "launch_failed", "segment": n,
                             "argv": r["argv"][1:], "why": f"{type(exc).__name__}: {exc}",
                             "rc": REFUSED_RC})
            _say(f"runtime_task: launch failed: {type(exc).__name__}: {exc}")
            return REFUSED_RC
        try:
            if job is not None and mode == "breakaway":
                job.adopt(child)
            _run_row(log, {**base, "utc": _utc(), "event": "start", "segment": n,
                             "argv": r["argv"][1:], "child_pid": child.pid, "log": r["log"],
                             "job": mode if job is not None else "none"})
            rc = child.wait()
        except Refused:
            child.kill()                    # it joined no job: it must not run unguarded
            child.wait()
            raise
        finally:
            if fh is not None:
                fh.close()
        _run_row(log, {**base, "utc": _utc(), "event": "end", "segment": n,
                         "module": r["argv"][2], "rc": rc, "seconds": round(time.time() - t0, 1)})
        if rc != 0 and rc_final == 0:
            rc_final = rc
    return rc_final


def _refused(argv: Sequence[str], exc: Exception) -> int:
    try:
        live = read_config()["AEGIS_LIVE_OPTIMUS"]
    except Refused:
        live = None                                  # no config: the exit code is the only record
    _run_row(str(Path(live) / RUN_LOG_REL) if live else None,
             {"utc": _utc(), "event": "refused", "wrapper_pid": os.getpid(),
              "clone": str(CLONE), "why": str(exc), "argv": list(argv), "rc": REFUSED_RC})
    _say(f"runtime_task REFUSED: {exc}")
    return REFUSED_RC


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_plan(argv)
    except Refused as exc:
        return _refused(argv, exc)
    if plan["print_plan"]:
        # only the names this wrapper decides; the rest of the inherited environment is not shown
        names = sorted({*SETTABLE, "AEGIS_DOTENV_PATH", "AEGIS_PI_DB_PATH", "AEGIS_REPO_ROOT",
                        "AEGIS_RUNTIME_CLONE", "PYTHONUNBUFFERED"})
        shown = {**plan, "runs": [{**r, "env": {k: r["env"][k] for k in names if k in r["env"]}}
                                  for r in plan["runs"]]}
        if sys.stdout is not None:
            print(json.dumps(shown, indent=1))
        return 0
    try:
        return run_plan(plan)
    except Refused as exc:                           # the job object could not be made or joined
        return _refused(argv, exc)


if __name__ == "__main__":
    raise SystemExit(windows_exit_code(main()))
