"""The ONE wrapper every scheduled task's action points at (CH-05, wrapper PR "W").

    <venv>\\Scripts\\pythonw.exe -I <clone>\\scripts\\runtime_task.py [options] -m <module> [args...]
    <clone>\\scripts\\runtime_task.cmd [options] -m <module> [args...]      (a console; same logic)

Options (before the first `-m`):
    --pythonw            run the module under the venv's pythonw.exe (no stdout; today's default
                         for windowless tasks)
    --nn-lab             run under nn_lab's own venv (AEGIS_NN_LAB_VENV_DIR)
    --set NAME=VALUE     one per-task environment variable (allow-listed names only)
    --stop-file PATH     exit 0 without running when PATH exists (repeatable; relative = the clone)
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
   var alone is the split brain `runtime_preflight` fails on); or the clone's own
   `backend/data/optimus` does not resolve to `AEGIS_LIVE_OPTIMUS` (no junction = this task
   would write main's tracked copies inside the clone while every other task writes live data).
4. Builds the child environment: `AEGIS_DOTENV_PATH` (the task points at the keys file; nothing
   copies or prints it), `AEGIS_REPO_ROOT` = the clone (a stale inherited value cannot point a
   task back at the WIP checkout), `AEGIS_RUNTIME_CLONE`, no `PYTHONPATH`/`PYTHONHOME`.
5. `cd` into the clone and runs `<venv>\\Scripts\\python[w].exe -m <module> <args>`.
6. Returns the module's exit code UNCHANGED, and appends a start and an end row (pid, commit,
   rc, seconds) to `<AEGIS_LIVE_OPTIMUS>/runtime_switch/runtime_task_runs.jsonl` (the shared
   data dir, so a refusal in a clone without its junction does not dirty that clone).

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
    "AEGIS_LIVE_ROOT", "AEGIS_LIVE_OPTIMUS", "AEGIS_DOTENV_PATH", "AEGIS_VENV_DIR",
    "AEGIS_NN_LAB_VENV_DIR", "AEGIS_RUNTIME_ROOT", "AEGIS_PUBLICATION_ROOT",
)
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

_FLAG_NO_VALUE = {"--pythonw": "pythonw", "--nn-lab": "nn_lab", "--print-plan": "print_plan"}


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


def child_env(clone: Path, cfg: Mapping[str, str], opt: Options, environ: Mapping[str, str],
              *, logged: bool) -> dict[str, str]:
    env = {k: v for k, v in environ.items() if k not in CLEARED}
    env["AEGIS_DOTENV_PATH"] = cfg["AEGIS_DOTENV_PATH"]
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


def run_plan(plan: dict, *, popen=subprocess.Popen) -> int:
    clone, log = Path(plan["clone"]), plan.get("run_log")
    base = {"wrapper_pid": os.getpid(), "clone": str(clone), "head": clone_head(clone)}
    for sf in plan["stop_files"]:
        if Path(sf).exists():
            _run_row(log, {**base, "utc": _utc(), "event": "stopped", "stop_file": sf, "rc": 0})
            _say(f"runtime_task: STOP file present ({sf}); nothing ran")
            return 0
    rc_final = 0
    for n, r in enumerate(plan["runs"]):
        flags = CREATE_NO_WINDOW if os.name == "nt" and (r["log"] or _windowless()) else 0
        t0 = time.time()
        fh = None
        try:
            if r["log"]:
                Path(r["log"]).parent.mkdir(parents=True, exist_ok=True)
                fh = open(r["log"], "ab")
            child = popen(r["argv"], cwd=plan["cwd"], env=r["env"], stdin=subprocess.DEVNULL,
                          stdout=fh, stderr=subprocess.STDOUT if fh else None,
                          creationflags=flags)
            _run_row(log, {**base, "utc": _utc(), "event": "start", "segment": n,
                             "argv": r["argv"][1:], "child_pid": child.pid, "log": r["log"]})
            rc = child.wait()
        finally:
            if fh is not None:
                fh.close()
        _run_row(log, {**base, "utc": _utc(), "event": "end", "segment": n,
                         "module": r["argv"][2], "rc": rc, "seconds": round(time.time() - t0, 1)})
        if rc != 0 and rc_final == 0:
            rc_final = rc
    return rc_final


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_plan(argv)
    except Refused as exc:
        try:
            live = read_config()["AEGIS_LIVE_OPTIMUS"]
        except Refused:
            live = None                              # no config: the exit code is the only record
        _run_row(str(Path(live) / RUN_LOG_REL) if live else None,
                 {"utc": _utc(), "event": "refused", "wrapper_pid": os.getpid(),
                  "clone": str(CLONE), "why": str(exc), "argv": argv, "rc": REFUSED_RC})
        _say(f"runtime_task REFUSED: {exc}")
        return REFUSED_RC
    if plan["print_plan"]:
        # only the names this wrapper decides; the rest of the inherited environment is not shown
        names = sorted({*SETTABLE, "AEGIS_DOTENV_PATH", "AEGIS_REPO_ROOT", "AEGIS_RUNTIME_CLONE",
                        "PYTHONUNBUFFERED"})
        shown = {**plan, "runs": [{**r, "env": {k: r["env"][k] for k in names if k in r["env"]}}
                                  for r in plan["runs"]]}
        if sys.stdout is not None:
            print(json.dumps(shown, indent=1))
        return 0
    return run_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
