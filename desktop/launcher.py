"""AEGIS LAUNCHER -- the .exe updates the checkout, then runs the checkout's code.

WHAT THIS REPLACES, AND WHY (roadmap O1)
========================================
Until 2026-09-11 PyInstaller froze the whole backend: `backend/`, `scripts/`,
`learner/` and their data, 1.1 GB of it. Two consequences, and both were paid
for:

1. **The app could not update itself.** Every change needed a rebuild, and the
   .exe on the desktop was whatever the last build happened to contain.
2. **A path that resolves differently when frozen** became a defect FAMILY --
   six instances by 09-11 (empty database inside the bundle, dropped vendored
   schema, ownership note written where nothing could read it, `AEGIS_DATA_DIR`
   one level too deep, the `-m` spawn, and `.env` invisible to `config.py`).
   From source every path was right, so nothing failed; the frozen build changed
   `__file__` underneath code that never mentions it.

So the .exe is now a LAUNCHER and nothing else. It finds the checkout, updates
it, and starts `python -m desktop.aegis_desktop` **under the checkout's own
interpreter**. Nothing is frozen but this file, `desktop/_interp.py` and
pywebview. The frozen-path family cannot recur in code that is not frozen.

WHAT IT DOES, IN ORDER, EACH WITH A LOG LINE AND A RECEIPT FIELD
===============================================================
1. **find the checkout** -- `AEGIS_REPO_ROOT`, then the .exe's own parents, then
   `%LOCALAPPDATA%\\Aegis\\repo_path` written on the first success. If none of
   those work it opens a window that NAMES what it looked for, rather than
   exiting silently on a double-click.
2. **`git status --porcelain`** -- a dirty tree SKIPS the pull and says so. It
   never stashes and never resets: an update mechanism that discards work is
   worse than one that does nothing.
3. **`pip install -r requirements.txt`** -- only when the file's sha256 differs
   from the one in the last receipt. Otherwise a 40-second dependency resolve
   sits between a double-click and a window every single launch.
4. **`npx next build`** -- only when `git diff <last_export_head> HEAD --
   frontend/` is non-empty, or when `frontend/out` is missing. No Node: say so
   and serve the export that is there.
5. **spawn the shell** and wait for it. On Windows the child is put in a JOB
   OBJECT with `KILL_ON_JOB_CLOSE`, the same mechanism `llama_server.bind_lifetime`
   uses, so closing the launcher kills the shell and the shell kills the model
   server. Every shutdown hook runs user code and `TerminateProcess` runs none:
   measured on 2026-09-10, a force-kill left 5,095 MiB of weights mapped.

The child's **stderr is redirected into `aegis_desktop.log`**. A `console=False`
build has nowhere for a traceback to go, and the 09-11 failure of the old bundle
(backend thread dead, no listener, 242 s timeout, an empty log) is a ten-second
read with this in place and a forensic dig without it.

A step that did nothing SAYS SO, with its reason. "Skipped, because the
requirements hash is unchanged" and "skipped, because nothing ran" are different
facts and the receipt distinguishes them (invariant 15).

USAGE
    AegisDesktop.exe                 # update, then open the window
    AegisDesktop.exe --headless      # update, start the shell serving, probe
                                     #   /api/health, print the receipt, stop
    AegisDesktop.exe --no-update     # skip steps 2-4 entirely
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from desktop._interp import resolve as resolve_interpreter   # noqa: E402

#: Everything a checkout must have for this to be the right directory. Checking
#: for `.git` alone would accept any clone; checking for `backend` alone would
#: accept the bundle, which is how `_internal` became a plausible repo root.
MARKERS = ("backend", "scripts", "desktop", ".git")

#: Written on the first successful find, read when the .exe is moved somewhere
#: with no repo above it (a Start Menu shortcut's target, say).
def pointer_file() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Aegis" / "repo_path"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _looks_like_checkout(p: Path) -> bool:
    try:
        return all((p / m).exists() for m in MARKERS)
    except OSError:
        return False


# --------------------------------------------------------------- step 1: find

def find_checkout(env: dict | None = None,
                  exe: Path | None = None,
                  frozen: bool | None = None) -> dict:
    """`{"ok", "root", "how", "looked_in": [...]}`. Never guesses."""
    env = os.environ if env is None else env
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    looked: list[str] = []

    cand = env.get("AEGIS_REPO_ROOT")
    if cand:
        looked.append(f"AEGIS_REPO_ROOT={cand}")
        if _looks_like_checkout(Path(cand)):
            return {"ok": True, "root": str(Path(cand).resolve()),
                    "how": "AEGIS_REPO_ROOT", "looked_in": looked}

    if not frozen:
        # `python -m desktop.launcher` -- the checkout is the parent of this
        # file and `sys.executable` is a system interpreter whose parents are
        # not repositories. Only true when NOT frozen: inside the bundle this
        # path is `_internal/desktop`, which is the whole defect family.
        looked.append(f"{HERE.parent} (this file's parent, source run)")
        if _looks_like_checkout(HERE.parent):
            return {"ok": True, "root": str(HERE.parent), "how": "the source tree",
                    "looked_in": looked}

    exe = Path(exe or sys.executable).resolve()
    for parent in exe.parents:
        looked.append(str(parent))
        if _looks_like_checkout(parent):
            return {"ok": True, "root": str(parent), "how": "a parent of the .exe",
                    "looked_in": looked}

    pf = pointer_file()
    looked.append(str(pf))
    try:
        p = Path(pf.read_text(encoding="utf-8").strip())
        if _looks_like_checkout(p):
            return {"ok": True, "root": str(p.resolve()),
                    "how": f"the pointer file {pf}", "looked_in": looked}
    except OSError:
        pass

    return {"ok": False, "root": None, "how": None, "looked_in": looked,
            "markers": list(MARKERS)}


def remember_checkout(root: Path) -> dict:
    pf = pointer_file()
    try:
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(str(root), encoding="utf-8")
        return {"ok": True, "path": str(pf)}
    except OSError as exc:
        return {"ok": False, "path": str(pf), "reason": f"{type(exc).__name__}: {exc}"}


# ----------------------------------------------------------- steps 2-4: update

def _run(cmd: list[str], cwd: Path, timeout: float = 900.0) -> dict:
    """One subprocess, fully recorded. Never raises."""
    t0 = time.time()
    try:
        out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                             timeout=timeout)
        # stdout is NOT stripped. `git status --porcelain` encodes the state in
        # the first two COLUMNS (" M" is modified-not-staged, "M " is staged),
        # so a leading strip silently rewrites the answer.
        return {"cmd": cmd, "returncode": out.returncode,
                "stdout": (out.stdout or "")[-4000:],
                "stderr": (out.stderr or "").strip()[-4000:],
                "seconds": round(time.time() - t0, 2)}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"cmd": cmd, "returncode": None,
                "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.time() - t0, 2)}


def git_head(root: Path) -> str | None:
    r = _run(["git", "rev-parse", "HEAD"], root, timeout=30)
    return r["stdout"].strip() if r.get("returncode") == 0 else None


def update_checkout(root: Path) -> dict:
    """Step 2. A dirty tree is left alone, and the receipt says why."""
    step: dict = {"step": "git", "utc": _now()}
    st = _run(["git", "status", "--porcelain"], root, timeout=60)
    step["status_returncode"] = st.get("returncode")
    if st.get("returncode") != 0:
        return step | {"updated": False,
                       "reason": f"`git status` failed: {st.get('stderr') or st.get('error')}"}
    dirty = bool(st["stdout"].strip())
    step["dirty"] = dirty
    step["head_before"] = git_head(root)
    if dirty:
        step["dirty_files"] = st["stdout"].rstrip("\n").splitlines()[:20]
        return step | {"updated": False, "reason": "local changes present",
                       "head_after": step["head_before"]}
    pull = _run(["git", "pull", "--ff-only"], root, timeout=300)
    step["pull"] = {k: pull.get(k) for k in ("returncode", "stdout", "stderr", "error")}
    step["head_after"] = git_head(root)
    if pull.get("returncode") != 0:
        # A failed pull is RECORDED AND NOT FATAL. No network on an aeroplane is
        # not a reason to refuse to open the app.
        return step | {"updated": False,
                       "reason": f"`git pull --ff-only` failed: "
                                 f"{(pull.get('stderr') or pull.get('error') or '').splitlines()[:1]}"}
    return step | {"updated": step["head_before"] != step["head_after"],
                   "reason": ("pulled" if step["head_before"] != step["head_after"]
                              else "already up to date")}


def requirements_path(root: Path) -> Path:
    return root / "requirements.txt"


def maybe_pip(root: Path, interp: str | None, last: dict) -> dict:
    """Step 3. Install only when `requirements.txt` actually changed."""
    req = requirements_path(root)
    sha = _sha256_file(req)
    step = {"step": "pip", "utc": _now(), "requirements": str(req.name),
            "sha256": sha, "sha256_last": (last or {}).get("sha256")}
    if sha is None:
        return step | {"ran": False, "reason": f"no {req}"}
    if interp is None:
        return step | {"ran": False, "reason": "no interpreter resolved"}
    if sha == step["sha256_last"]:
        return step | {"ran": False, "reason": "requirements.txt unchanged since the last launch"}
    r = _run([interp, "-m", "pip", "install", "-r", str(req)], root, timeout=1800)
    return step | {"ran": True, "returncode": r.get("returncode"),
                   "seconds": r.get("seconds"),
                   "tail": (r.get("stdout") or r.get("error") or "")[-600:],
                   "reason": ("installed" if r.get("returncode") == 0
                              else "pip failed; the app still starts on what is installed")}


def frontend_changed(root: Path, since: str | None) -> tuple[bool, str]:
    if not since:
        return True, "no recorded export head"
    r = _run(["git", "diff", "--quiet", since, "HEAD", "--", "frontend/"], root, timeout=60)
    if r.get("returncode") == 0:
        return False, f"frontend/ unchanged since {since[:9]}"
    if r.get("returncode") == 1:
        return True, f"frontend/ changed since {since[:9]}"
    return True, f"`git diff` could not compare against {since[:9]}"


def maybe_frontend(root: Path, last: dict) -> dict:
    """Step 4. Rebuild the static export only when `frontend/` moved."""
    out_dir = root / "frontend" / "out"
    head = git_head(root)
    changed, why = frontend_changed(root, (last or {}).get("export_head"))
    step = {"step": "frontend", "utc": _now(), "out_exists": out_dir.is_dir(),
            "export_head_last": (last or {}).get("export_head"), "why": why}
    if out_dir.is_dir() and not changed:
        return step | {"ran": False, "reason": why, "export_head": (last or {}).get("export_head") or head}
    import shutil
    npx = shutil.which("npx")
    if not npx:
        # Serving a stale export is a far better outcome than refusing to open.
        return step | {"ran": False, "reason": "Node/npx is not installed; serving the last export",
                       "export_head": (last or {}).get("export_head")}
    env = dict(os.environ, AEGIS_DESKTOP_BUILD="1")
    t0 = time.time()
    try:
        r = subprocess.run([npx, "next", "build"], cwd=str(root / "frontend"),
                           capture_output=True, text=True, timeout=1800, env=env)
        ok = r.returncode == 0
        return step | {"ran": True, "returncode": r.returncode,
                       "seconds": round(time.time() - t0, 2),
                       "tail": (r.stdout or r.stderr or "").strip()[-800:],
                       "export_head": head if ok else (last or {}).get("export_head"),
                       "reason": "rebuilt" if ok else "next build failed; serving the last export"}
    except (OSError, subprocess.SubprocessError) as exc:
        return step | {"ran": True, "returncode": None,
                       "error": f"{type(exc).__name__}: {exc}",
                       "export_head": (last or {}).get("export_head"),
                       "reason": "next build could not run; serving the last export"}


# ------------------------------------------------------------ step 5: the child

def _job_object():
    """A Windows job object with KILL_ON_JOB_CLOSE, or None off Windows.

    The same mechanism as `llama_server.bind_lifetime`, for the same reason: it
    is the only promise the OS keeps when the process is force-killed. `atexit`,
    `finally` and `closing` all run user code; `TerminateProcess` runs none.
    """
    if sys.platform != "win32":
        return None, {"bound": False, "reason": "not Windows"}
    try:
        import ctypes
        from ctypes import wintypes

        class _BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _IO(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                        ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64),
                        ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64),
                        ("OtherTransferCount", ctypes.c_uint64)]

        class _EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _BASIC),
                        ("IoInfo", _IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.CreateJobObjectW(None, None)
        if not h:
            return None, {"bound": False, "reason": "CreateJobObject failed"}
        info = _EXT()
        info.BasicLimitInformation.LimitFlags = 0x2000   # KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(h, 9, ctypes.byref(info),
                                           ctypes.sizeof(info)):
            return None, {"bound": False, "reason": "SetInformationJobObject failed"}
        return h, {"bound": True, "flag": "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE"}
    except Exception as exc:                                     # noqa: BLE001
        return None, {"bound": False, "reason": f"{type(exc).__name__}: {exc}"}


def _assign(handle, pid: int) -> dict:
    if handle is None:
        return {"bound": False, "reason": "no job object"}
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ph = k32.OpenProcess(0x001F0FFF, False, int(pid))     # PROCESS_ALL_ACCESS
        if not ph:
            return {"bound": False, "reason": "OpenProcess failed"}
        try:
            ok = k32.AssignProcessToJobObject(handle, ph)
            return {"bound": bool(ok),
                    "reason": None if ok else "AssignProcessToJobObject failed"}
        finally:
            k32.CloseHandle(ph)
    except Exception as exc:                                     # noqa: BLE001
        return {"bound": False, "reason": f"{type(exc).__name__}: {exc}"}


def shell_argv(interp: str, page: str = "/desktop", extra: list[str] | None = None) -> list[str]:
    return [interp, "-m", "desktop.aegis_desktop", "--page", page, *(extra or [])]


def log_path(root: Path) -> Path:
    return root / "backend" / "data" / "optimus" / "aegis_desktop.log"


def receipt_path(root: Path) -> Path:
    return root / "backend" / "data" / "optimus" / "launch_receipt.json"


def read_last_receipt(root: Path) -> dict:
    try:
        return json.loads(receipt_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_receipt(root: Path, receipt: dict) -> Path | None:
    p = receipt_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        return p
    except OSError:
        return None


def log_line(root: Path, msg: str) -> None:
    try:
        p = log_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{_now()} LAUNCHER {msg}\n")
    except OSError:
        pass


def spawn_shell(root: Path, argv: list[str]) -> dict:
    """Start the shell, own it at the kernel, and return `(proc, record)`."""
    handle, jrec = _job_object()
    env = dict(os.environ)
    env["AEGIS_REPO_ROOT"] = str(root)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    p = log_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = p.open("a", encoding="utf-8", errors="replace", newline="\n")
    fh.write(f"{_now()} LAUNCHER child stderr follows\n")
    fh.flush()
    creation = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW
    proc = subprocess.Popen(argv, cwd=str(root), env=env,
                            stdout=subprocess.PIPE, stderr=fh, text=True,
                            creationflags=creation)
    bound = _assign(handle, proc.pid)
    return {"proc": proc, "job_handle": handle, "log": fh,
            "record": {"step": "shell", "utc": _now(), "argv": argv,
                       "pid": proc.pid, "job_object": jrec, "bound": bound,
                       "stderr_to": str(p)}}


# ------------------------------------------------------------------ the refusal

def refuse_window(found: dict) -> None:
    """A double-click that finds nothing must SAY SO, not vanish."""
    looked = "".join(f"<li><code>{x}</code></li>" for x in found.get("looked_in", []))
    html = ("<body style='background:#0b0d10;color:#e6e8ea;font:14px system-ui;padding:32px'>"
            "<h2>Aegis could not find its checkout.</h2>"
            "<p>This launcher runs the code in your repository; it does not carry a copy. "
            "A directory counts as the checkout when it contains all of "
            f"<code>{', '.join(MARKERS)}</code>.</p><p>It looked in:</p><ul>"
            f"{looked}</ul>"
            "<p>Fix it by setting <code>AEGIS_REPO_ROOT</code> to the repository, or by "
            f"writing its path into <code>{pointer_file()}</code>.</p></body>")
    try:
        import webview
        webview.create_window("Aegis", html=html, width=900, height=620,
                              background_color="#0b0d10")
        webview.start()
    except Exception:                                            # noqa: BLE001
        print(html, file=sys.stderr)


# ------------------------------------------------------------------------ main

def probe_health(port: int, timeout_s: float = 240.0) -> dict:
    t0 = time.time()
    url = f"http://127.0.0.1:{port}/api/health"
    last = None
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2) as fh:   # noqa: S310 localhost
                if fh.status == 200:
                    return {"ok": True, "seconds": round(time.time() - t0, 2),
                            "payload": json.loads(fh.read().decode("utf-8"))}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    return {"ok": False, "seconds": round(time.time() - t0, 2), "last_error": last}


def shell_report_path(root: Path) -> Path:
    return root / "backend" / "data" / "optimus" / "aegis_desktop_report.json"


def wait_for_shell_report(root: Path, timeout_s: float = 60.0) -> dict:
    """The shell's own report, once it is FINISHED rather than half-written.

    The shell writes the report twice: early (port, pid, llama) so that a crash
    during startup still leaves something to read, and again after its health
    probe with `health_ok`, `llm_providers` and any `backend_error`. Reading it
    the moment our own probe succeeds gets the early copy and reports
    `llm_providers: null` -- which looks exactly like the defect the acceptance
    test is checking for.
    """
    t0 = time.time()
    last: dict = {}
    while time.time() - t0 < timeout_s:
        try:
            last = json.loads(shell_report_path(root).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            last = {}
        if "health_ok" in last:
            return last
        time.sleep(0.2)
    return last | {"incomplete": f"no health_ok in the shell report after {timeout_s}s"}


def free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aegis Desktop launcher")
    ap.add_argument("--no-update", action="store_true",
                    help="skip git / pip / frontend and start the shell as it is")
    ap.add_argument("--headless", action="store_true",
                    help="start the shell serving, probe /api/health, print the receipt, stop")
    ap.add_argument("--page", default="/desktop")
    ap.add_argument("--port", type=int, default=0)
    a, passthrough = ap.parse_known_args(argv)

    t0 = time.time()
    receipt: dict = {"job": "aegis_launcher", "utc": _now(),
                     "frozen": bool(getattr(sys, "frozen", False)),
                     "exe": sys.executable, "steps": []}

    found = find_checkout()
    receipt["steps"].append({"step": "find_checkout", "utc": _now(), **found})
    if not found["ok"]:
        receipt["status"] = "REFUSED"
        receipt["headline"] = "no checkout found"
        print(json.dumps(receipt, indent=1, default=str), file=sys.stderr)
        refuse_window(found)
        return 2
    root = Path(found["root"])
    receipt["root"] = str(root)
    log_line(root, f"start exe={sys.executable} root={root} how={found['how']}")
    receipt["steps"].append({"step": "remember_checkout", "utc": _now(),
                             **remember_checkout(root)})

    last = read_last_receipt(root)
    last_pip = next((s for s in last.get("steps", []) if s.get("step") == "pip"), {})
    last_fe = next((s for s in last.get("steps", []) if s.get("step") == "frontend"), {})

    interp, why = resolve_interpreter(root)
    receipt["steps"].append({"step": "interpreter", "utc": _now(),
                             "interpreter": interp, "why": why})
    log_line(root, f"interpreter {interp} ({why})")
    if interp is None:
        receipt["status"] = "REFUSED"
        receipt["headline"] = "no interpreter"
        write_receipt(root, receipt)
        refuse_window({"looked_in": [why]})
        return 2

    if a.no_update:
        for name in ("git", "pip", "frontend"):
            receipt["steps"].append({"step": name, "utc": _now(), "ran": False,
                                     "reason": "--no-update"})
    else:
        g = update_checkout(root)
        receipt["steps"].append(g)
        log_line(root, f"git updated={g.get('updated')} reason={g.get('reason')}")
        pi = maybe_pip(root, interp, last_pip)
        receipt["steps"].append(pi)
        log_line(root, f"pip ran={pi.get('ran')} reason={pi.get('reason')}")
        fe = maybe_frontend(root, last_fe)
        receipt["steps"].append(fe)
        log_line(root, f"frontend ran={fe.get('ran')} reason={fe.get('reason')}")

    extra = list(passthrough)
    port = a.port
    if a.headless:
        port = port or free_port()
        extra += ["--serve", "--no-llama", "--port", str(port)]
    elif port:
        extra += ["--port", str(port)]

    spawned = spawn_shell(root, shell_argv(interp, a.page, extra))
    proc, fh = spawned["proc"], spawned["log"]
    receipt["steps"].append(spawned["record"])
    receipt["shell_report"] = str(shell_report_path(root))
    log_line(root, f"shell pid={proc.pid} bound={spawned['record']['bound']}")
    write_receipt(root, receipt)

    try:
        if a.headless:
            health = probe_health(port)
            receipt["steps"].append({"step": "health", "utc": _now(), "port": port, **health})
            receipt["shell"] = wait_for_shell_report(root)
            receipt["status"] = "OK" if health["ok"] else "SHELL_DID_NOT_ANSWER"
            receipt["total_s"] = round(time.time() - t0, 2)
            write_receipt(root, receipt)
            print(json.dumps(receipt, indent=1, default=str), flush=True)
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 0 if health["ok"] else 1
        code = proc.wait()
        receipt["status"] = "OK" if code == 0 else "SHELL_EXITED_NONZERO"
        receipt["shell_returncode"] = code
        receipt["total_s"] = round(time.time() - t0, 2)
        write_receipt(root, receipt)
        log_line(root, f"shell exited {code} after {receipt['total_s']}s")
        return int(code)
    finally:
        try:
            fh.close()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
