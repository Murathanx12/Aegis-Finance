"""Lifecycle for the on-box llama.cpp server, owned by PID and never by name.

Murat, 2026-09-10: "I find it hard to close the llama server so on the exe put a
button to close or auto close when I shut the exe."

He is right that it is hard, and the reason is on disk. `~/llama/llama-stop.cmd`
ends with

    taskkill /IM llama-server.exe /F

which is kill-by-image-name -- the gesture CLAUDE.md bans outright after
2026-09-06, when one agent used it to stop its own job and took down two other
agents' jobs, a running test suite, ~1,676 already-billed LLM extractions and
the Optimus MCP server for the rest of the session. It also needs a terminal,
which is the "hard" part.

So this module does three things and no more:

* **status()** -- is anything listening on the port, which PID owns it, how much
  VRAM is in use, and *did Aegis start it*. That last flag is the whole design.
* **start()** -- start a server ONLY if the port is free. An instance that is
  already up may be mid-job with 8 GB mapped; taking it over would be a data
  loss disguised as convenience.
* **stop()** -- terminate by PID, from a PID recorded when the process was
  started (or resolved from the listening socket), with a grace period before
  the hard kill. Never by image name.

Ownership is written to a small JSON file so the answer survives a backend
restart: if Aegis started the server, closing Aegis stops it; if the server was
already running, closing Aegis LEAVES IT ALONE and the UI has to ask.

Nothing here runs a model, places an order, or touches a book.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.services import quiet_subprocess as qsp

def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT` the way the control router does.

    2026-09-10, found the hard way. `Path(__file__).parents[2]` is `_internal`
    inside the frozen app, so the packaged build wrote its ownership note into
    the BUNDLE while every other process -- and every later run of the app --
    looked for it in the repo. The consequence was the exact failure this module
    exists to prevent: Murat closed the app and llama-server PID 8012 kept
    running with 5,495 MiB of VRAM mapped. Its parent process was the app, so it
    was unambiguously ours; without a readable owner file `status()` called it
    `foreign` and `stop_if_owned()` correctly, uselessly, left it alone.

    A guard that reads state from a path the writer cannot reach is not a guard.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


REPO = _repo_root()

try:                                            # config is the home for parameters
    from backend import config as _cfg
except Exception:                               # noqa: BLE001 - importable standalone
    _cfg = None


def _conf(name: str, default):
    v = getattr(_cfg, name, None) if _cfg is not None else None
    return default if v is None else v


#: where the model, the binary and the ownership note live. Parameters belong in
#: `backend/config.py` (CLAUDE.md), so these read through it with a fallback.
LLAMA_HOME = Path(os.getenv("AEGIS_LLAMA_HOME", str(_conf("LLAMA_HOME", Path.home() / "llama"))))
LLAMA_BIN = Path(os.getenv("AEGIS_LLAMA_BIN", str(_conf("LLAMA_BIN", LLAMA_HOME / "bin" / "llama-server.exe"))))
LLAMA_MODEL = Path(os.getenv("AEGIS_LLAMA_MODEL",
                             str(_conf("LLAMA_MODEL", LLAMA_HOME / "models" / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"))))
LLAMA_HOST = os.getenv("AEGIS_LLAMA_HOST", str(_conf("LLAMA_HOST", "127.0.0.1")))
LLAMA_PORT = int(os.getenv("AEGIS_LLAMA_PORT", str(_conf("LLAMA_PORT", 8080))))
LLAMA_CTX = int(os.getenv("AEGIS_LLAMA_CTX", str(_conf("LLAMA_CTX", 8192))))
LLAMA_NGL = int(os.getenv("AEGIS_LLAMA_NGL", str(_conf("LLAMA_NGL", 99))))
#: expert tensors on CPU: the knob that makes a 30B-A3B MoE fit 8 GB of VRAM.
#: 0 means "everything the -ngl budget allows on the GPU", which is right for a
#: dense 7B and wrong for a 30B MoE. See `docs/` note on the model swap.
LLAMA_N_CPU_MOE = int(os.getenv("AEGIS_LLAMA_N_CPU_MOE", str(_conf("LLAMA_N_CPU_MOE", 0))))
#: CONSERVATIVE BATCH DEFAULTS FOR UNATTENDED USE (2026-09-12).
#:
#: At 10:53 HKT the machine bugchecked 0x116 VIDEO_TDR_ERROR -- the display
#: driver did not recover from a GPU timeout -- while an unattended night job
#: read cells through this server, which held 5.3 GB of the card's 8 GB. A TDR
#: fires when one GPU command takes longer than the driver's watchdog allows,
#: and the size of a single llama.cpp submission is the batch. llama.cpp's own
#: defaults are 2048 logical / 512 physical; 512/128 makes each submission a
#: quarter of that, which is the cheap half of the mitigation and the only half
#: a session is allowed to do -- raising `TdrDelay` needs admin and a reboot and
#: belongs to Murat (docs/HANDOFF_2026-09-11_SESSION_CLOSE_ROOT_FIRST.md 3c).
#:
#: This costs prompt-processing throughput and nothing else: generation is one
#: token at a time either way. An attended, interactive session that wants the
#: speed back sets AEGIS_LLAMA_BATCH=2048 / AEGIS_LLAMA_UBATCH=512.
LLAMA_BATCH = int(os.getenv("AEGIS_LLAMA_BATCH", str(_conf("LLAMA_BATCH", 512))))
LLAMA_UBATCH = int(os.getenv("AEGIS_LLAMA_UBATCH", str(_conf("LLAMA_UBATCH", 128))))

OWNER_FILE = Path(os.getenv("AEGIS_LLAMA_OWNER_FILE",
                            str(REPO / "backend" / "data" / "optimus" / "llama_server_owner.json")))

#: how long a stop waits for a clean exit before escalating.
#: Measured 2026-09-10: llama-server.exe has no window and no message loop, so a
#: graceful `taskkill /PID` never reaches it and the escalation ALWAYS fires. The
#: grace is kept (a future build, or the Linux SIGTERM path, may honour it) but
#: short, because eight seconds of waiting on every stop is what makes a person
#: reach for the kill-by-name script this module exists to replace.
STOP_GRACE_S = float(os.getenv("AEGIS_LLAMA_STOP_GRACE_S", "3"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ ownership

def _read_owner() -> dict:
    try:
        return json.loads(OWNER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_owner(payload: dict) -> None:
    OWNER_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OWNER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(tmp, OWNER_FILE)


def _clear_owner() -> None:
    try:
        OWNER_FILE.unlink()
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ probing

def port_open(host: str = LLAMA_HOST, port: int = LLAMA_PORT, timeout: float = 0.6) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def health_ok(timeout: float = 2.0) -> bool:
    """`/health` is 200 only once the weights are resident.

    Measured 2026-09-10: llama-server BINDS the port immediately and finishes
    loading seconds later, so `start()` reported "ready" after 0.5 s while
    nvidia-smi still showed 1.1 GB of a ~4.8 GB model. A caller that trusted the
    open port would have sent its first request into a 503. The port answers
    "is anything there"; only /health answers "can it work".
    """
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{LLAMA_HOST}:{LLAMA_PORT}/health",  # noqa: S310 localhost
                                    timeout=timeout) as fh:
            return fh.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def pid_on_port(port: int = LLAMA_PORT) -> int | None:
    """The PID holding the listening socket, resolved from the OS.

    This is what lets a stop be by PID even when Aegis did not start the
    process: the socket table names the owner, so there is never a reason to
    fall back to matching on an image name.
    """
    try:
        import psutil                                        # optional dependency
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.status == "LISTEN" and c.laddr and c.laddr.port == port and c.pid:
                    return int(c.pid)
        except (PermissionError, OSError):
            pass
    if sys.platform == "win32":
        try:
            out = qsp.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                          text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "TCP" and parts[3].upper() == "LISTENING" \
                    and parts[1].endswith(f":{port}"):
                try:
                    return int(parts[4])
                except ValueError:
                    return None
    return None


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = qsp.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                          capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return str(int(pid)) in out
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def vram() -> dict | None:
    """`nvidia-smi` used/total in MiB, or None when there is no NVIDIA GPU.

    Absence is reported as None, never as zero: a zero would read on the page as
    "no VRAM in use", which is a different claim from "we could not measure".
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = qsp.run([exe, "--query-gpu=memory.used,memory.total,name",
                       "--format=csv,noheader,nounits"],
                      capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    line = out.splitlines()[0] if out else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None
    try:
        return {"used_mib": int(parts[0]), "total_mib": int(parts[1]), "gpu": parts[2]}
    except ValueError:
        return None


# ------------------------------------------------------------------ status

@dataclass
class Status:
    url: str
    listening: bool
    #: the port is bound AND /health is 200. `listening and not ready` means the
    #: weights are still loading -- a real state the UI must not render as "up".
    ready: bool
    pid: int | None
    started_by_aegis: bool
    #: True when something is listening that Aegis did NOT start. The UI must
    #: not offer a one-click stop for this case without saying so: the process
    #: may be several GB into a job that belongs to somebody else.
    foreign: bool
    model: str | None
    model_present: bool
    binary_present: bool
    started_utc: str | None
    vram: dict | None
    detail: str


def status() -> dict:
    listening = port_open()
    owner = _read_owner()
    owned_pid = int(owner.get("pid") or 0)
    pid = pid_on_port() if listening else None
    # ownership only counts if the recorded PID is the one actually listening:
    # a stale owner file from a previous crash must not license a kill
    started_by_aegis = bool(listening and owned_pid and pid and owned_pid == pid and pid_alive(pid))
    if owned_pid and not pid_alive(owned_pid):
        _clear_owner()
    ready = health_ok() if listening else False
    st = Status(
        url=f"http://{LLAMA_HOST}:{LLAMA_PORT}",
        listening=listening,
        ready=ready,
        pid=pid,
        started_by_aegis=started_by_aegis,
        foreign=bool(listening and not started_by_aegis),
        model=owner.get("model") or (LLAMA_MODEL.name if LLAMA_MODEL.exists() else None),
        model_present=LLAMA_MODEL.exists(),
        binary_present=LLAMA_BIN.exists(),
        started_utc=owner.get("started_utc") if started_by_aegis else None,
        vram=vram(),
        detail=("not running" if not listening else
                ("bound but still loading the model (/health is not 200 yet)" if not ready else
                 (f"ready as PID {pid}, started by Aegis" if started_by_aegis else
                  f"ready as PID {pid}, started OUTSIDE Aegis -- it may be mid-job"))),
    )
    return {**asdict(st), "utc": _now(),
            "model_path": str(LLAMA_MODEL), "binary_path": str(LLAMA_BIN),
            "n_cpu_moe": LLAMA_N_CPU_MOE,
            "batch_size": LLAMA_BATCH, "ubatch_size": LLAMA_UBATCH}


# ------------------------------------------------------------------ start/stop

# ------------------------------------------------------------ lifetime binding

#: The Windows job object that ties the model server's life to ours. Held at
#: module scope so the handle stays open for the life of the process -- closing
#: it is what triggers the kill, so a local variable would kill the server the
#: moment `start()` returned.
_JOB_HANDLE = None


def bind_lifetime(pid: int) -> dict:
    """Make the OS kill `pid` when THIS process dies, however it dies.

    2026-09-10, measured after the first fix was not enough. The app registers a
    shutdown on the window's `closing` event, on `atexit`, and on the return
    from the window loop -- and NONE of them run when the process is terminated
    rather than closed. Tested: `Stop-Process` on the packaged app left
    llama-server up with 5,095 MiB still mapped, because `TerminateProcess`
    executes no user code at all. A promise kept only on the tidy path is not
    the promise that was asked for.

    A job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` moves the guarantee
    into the kernel: when the last handle to the job closes -- which happens
    when this process exits for ANY reason, including a hard kill, a crash, or
    the power going -- Windows terminates every process in it.

    Returns a dict rather than raising: failing to bind is worth reporting and
    is not worth refusing to start a model server over. On POSIX this is a
    no-op and says so.
    """
    global _JOB_HANDLE
    if sys.platform != "win32":
        return {"bound": False, "reason": "not Windows; the app stops it on exit instead"}
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # ctypes defaults every restype to c_int, which TRUNCATES a 64-bit
        # HANDLE. It happened to work here because the handles were small
        # (348, 368), and that is exactly the kind of latent bug that only
        # appears on a busier machine. Declared explicitly instead.
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                wintypes.LPVOID, wintypes.DWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

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

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9
        PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001

        if _JOB_HANDLE is None:
            h = k32.CreateJobObjectW(None, None)
            if not h:
                return {"bound": False, "reason": f"CreateJobObject failed ({ctypes.get_last_error()})"}
            info = _EXT()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(
                    h, JobObjectExtendedLimitInformation,
                    ctypes.byref(info), ctypes.sizeof(info)):
                return {"bound": False,
                        "reason": f"SetInformationJobObject failed ({ctypes.get_last_error()})"}
            _JOB_HANDLE = h

        ph = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
        if not ph:
            return {"bound": False, "reason": f"OpenProcess({pid}) failed ({ctypes.get_last_error()})"}
        try:
            ok = k32.AssignProcessToJobObject(_JOB_HANDLE, ph)
            if not ok:
                return {"bound": False,
                        "reason": f"AssignProcessToJobObject failed ({ctypes.get_last_error()})"}
        finally:
            k32.CloseHandle(ph)
        return {"bound": True,
                "note": ("the OS will terminate the model server when this process exits, "
                         "including on a hard kill -- no user code has to run")}
    except Exception as exc:  # noqa: BLE001
        return {"bound": False, "reason": f"{type(exc).__name__}: {exc}"}


def start(wait_s: float = 90.0, bind: bool = True) -> dict:
    """Start the server, but only when the port is free.

    Refusing to start a second copy is not politeness: two servers means two
    copies of the weights resident, which on 8 GB of VRAM means neither works.
    """
    if port_open():
        return {"ok": True, "action": "none", "reason": "already listening",
                "note": ("Aegis did not start this one and will not adopt it; a running server may "
                         "hold several GB and be mid-job." if not _read_owner().get("pid") else
                         "already started by Aegis"),
                "status": status()}
    if not LLAMA_BIN.exists():
        return {"ok": False, "action": "refused", "reason": f"binary not found at {LLAMA_BIN}",
                "status": status()}
    if not LLAMA_MODEL.exists():
        return {"ok": False, "action": "refused", "reason": f"model not found at {LLAMA_MODEL}",
                "status": status()}
    cmd = [str(LLAMA_BIN), "-m", str(LLAMA_MODEL),
           "--host", LLAMA_HOST, "--port", str(LLAMA_PORT),
           "-ngl", str(LLAMA_NGL), "-c", str(LLAMA_CTX), "--no-webui",
           "--batch-size", str(LLAMA_BATCH), "--ubatch-size", str(LLAMA_UBATCH)]
    if LLAMA_N_CPU_MOE > 0:
        # keep this many MoE expert layers on the CPU; the attention stack stays
        # on the GPU. Without it a 30B-A3B at Q4 (~18.6 GB) cannot start at all
        # on an 8 GB card, and with it only the ~3B active experts cost compute.
        cmd += ["--n-cpu-moe", str(LLAMA_N_CPU_MOE)]
    log = LLAMA_HOME / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        # its OWN process group, so a stop reaches the server and not this backend
        proc = qsp.popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=qsp.NEW_PROCESS_GROUP, cwd=str(LLAMA_HOME))
    bound = bind_lifetime(proc.pid) if bind else {"bound": False, "reason": "bind=False"}
    # `owner_pid` is THIS process, not the server's. The note lives in the
    # checkout, so before this line every Aegis instance in the same checkout
    # read it and believed the server was its own -- and on 2026-09-11 a second,
    # headless instance started for diagnosis called `stop_if_owned()` on exit
    # and killed the model server (PID 53112) that Murat's running .exe had
    # started. Ownership is per PROCESS; the file is merely where it is written.
    _write_owner({"pid": proc.pid, "started_utc": _now(), "model": LLAMA_MODEL.name,
                  "cmd": cmd, "port": LLAMA_PORT, "lifetime_bound": bound,
                  "owner_pid": os.getpid(), "owner_started_utc": _now()})
    if wait_s <= 0:
        # the desktop shell starts it and gets on with opening the window; a
        # multi-GB model loads while the splash is up. "starting" is a state,
        # and calling it "timeout" -- which the first build did -- reads as a
        # failure of a process that is loading perfectly well.
        return {"ok": True, "action": "starting", "pid": proc.pid, "ready": False,
                "lifetime_bound": bound,
                "note": "not waited on; poll /api/control/llama until ready is true",
                "status": status()}
    deadline = time.time() + wait_s
    t_start = time.time()
    while time.time() < deadline:
        # /health, not the open port: the port binds instantly and the weights
        # land seconds later. "started" must mean "will answer a request".
        if health_ok():
            return {"ok": True, "action": "started", "pid": proc.pid,
                    "waited_s": round(time.time() - t_start, 1),
                    "ready": True, "status": status()}
        if proc.poll() is not None:
            _clear_owner()
            return {"ok": False, "action": "died", "exit_code": proc.returncode,
                    "log": str(log), "status": status()}
        time.sleep(1.0)
    return {"ok": False, "action": "timeout",
            "reason": (f"/health did not return 200 within {wait_s}s. The process is still alive as "
                       f"PID {proc.pid} and a multi-GB model can take longer -- a 30B-A3B at Q4 is "
                       f"~18.6 GB and loads from disk. Poll status() rather than assuming it failed."),
            "listening": port_open(), "pid": proc.pid, "status": status()}


def stop(*, allow_foreign: bool = False, grace_s: float = STOP_GRACE_S) -> dict:
    """Terminate the server by PID.

    `allow_foreign` is the consent gate for a server Aegis did not start. The
    button in the app passes it only after the user has been told what they are
    stopping, because that process may be several GB into somebody else's job.
    """
    st = status()
    if not st["listening"]:
        _clear_owner()
        return {"ok": True, "action": "none", "reason": "nothing listening", "status": st}
    pid = st["pid"]
    if not pid:
        return {"ok": False, "action": "refused",
                "reason": (f"something is listening on {LLAMA_PORT} but the owning PID could not be "
                           f"resolved from the socket table. Refusing rather than falling back to a "
                           f"kill by image name, which is what took out three other jobs on 2026-09-06."),
                "status": st}
    if st["foreign"] and not allow_foreign:
        return {"ok": False, "action": "refused", "reason": "started outside Aegis",
                "needs_confirmation": True,
                "detail": (f"PID {pid} is serving on {LLAMA_PORT} but Aegis did not start it. It may be "
                           f"mid-job with several GB mapped. Re-send with allow_foreign=true to stop it."),
                "status": st}
    # terminate, then verify; escalate only if it is still there
    escalated = False
    try:
        if sys.platform == "win32":
            qsp.run(["taskkill", "/PID", str(int(pid))], capture_output=True,
                    text=True, timeout=15)
        else:
            os.kill(int(pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "action": "error", "reason": f"{type(exc).__name__}: {exc}", "status": status()}
    deadline = time.time() + grace_s
    while time.time() < deadline and pid_alive(int(pid)):
        time.sleep(0.4)
    if pid_alive(int(pid)):
        escalated = True
        try:
            if sys.platform == "win32":
                qsp.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True,
                        text=True, timeout=15)
            else:
                os.kill(int(pid), signal.SIGKILL)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "action": "error", "reason": f"{type(exc).__name__}: {exc}",
                    "status": status()}
        time.sleep(1.0)
    _clear_owner()
    after = status()
    return {"ok": not after["listening"], "action": "stopped", "pid": pid,
            "escalated_to_force": escalated,
            "note": "terminated by PID; never by image name", "status": after}


def owning_instance(owner: dict | None = None) -> dict:
    """Which Aegis PROCESS owns the running server, and is it still alive?

    `{"owner_pid": int|None, "is_me": bool, "owner_alive": bool}`.
    """
    o = _read_owner() if owner is None else owner
    try:
        pid = int(o.get("owner_pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    return {"owner_pid": pid or None,
            "is_me": bool(pid) and pid == os.getpid(),
            "owner_alive": bool(pid) and pid_alive(pid)}


def stop_if_owned() -> dict:
    """What the desktop shell calls on exit.

    Murat asked for auto-close on shutdown. It applies to a server THIS PROCESS
    started; one that was already running is left alone, because closing a
    window is not consent to kill somebody else's 8 GB job.

    "THIS PROCESS", NOT "THIS CHECKOUT" -- the distinction cost a model server on
    2026-09-11. The ownership note is a file under `backend/data/optimus`, so a
    second instance running from the same checkout (a headless run started to
    diagnose the first) read the note, saw `started_by_aegis`, and killed the
    server the .exe in the foreground was using. `started_by_aegis` answers "did
    an Aegis start this?"; only `owner_pid` answers "did *I*?".

    An owner PID that is no longer alive is not a veto: the instance that
    started the server is gone, the server is orphaned, and `status()` has
    already checked that the recorded server PID is the one holding the socket.
    """
    st = status()
    if not st["listening"]:
        return {"ok": True, "action": "none", "reason": "nothing listening"}
    if not st["started_by_aegis"]:
        return {"ok": True, "action": "left_running",
                "reason": "the server was already running when Aegis started; not ours to stop",
                "pid": st["pid"]}
    inst = owning_instance()
    if inst["owner_pid"] and not inst["is_me"] and inst["owner_alive"]:
        return {"ok": True, "action": "left_alone",
                "reason": f"owned by another Aegis instance pid {inst['owner_pid']}",
                "pid": st["pid"], "owner_pid": inst["owner_pid"], "my_pid": os.getpid()}
    return stop(allow_foreign=False) | {"owner": inst}


# ------------------------------------------------------------ on demand (chunk G)
#
# 2026-09-26, Murat: "llama-server not permanently resident; idle shutdown".
# The machine had ~5 GB free that afternoon with the server resident at
# 9.5-12 GB, and fast suites had already been killed for low memory. So the
# server is now started by the CALLER that needs it -- `/ask`, `/research`,
# `/compare`, the factory's local pairing, the distillation -- through
# `ensure(reason)`, and stopped BY PID by the process that started it once no
# call has touched it for `MODEL_ROUTING_IDLE_SHUTDOWN_S`.
#
# WHY A WATCHDOG AND NOT A llama-server FLAG. Build 10645 (commit c5fc7e348) has
# `--sleep-idle-seconds` (checked with `--help`): it puts the server to SLEEP,
# the process stays, and what `/health` answers while asleep is unmeasured -- a
# `status()` reading "listening, not ready" forever would make every `ensure()`
# wait out its timeout. Stop-by-PID is the promise that was asked for, so the
# watchdog does that and the flag is not passed.
#
# WHO MAY IDLE-STOP. Only the process whose PID is `owner_pid` in the ownership
# note -- the per-PROCESS rule `stop_if_owned` paid for on 2026-09-11. Any
# process may `touch()` (record a use); only the starter stops.

import threading as _threading  # noqa: E402

IDLE_SHUTDOWN_S = float(os.getenv("AEGIS_LLAMA_IDLE_SHUTDOWN_S",
                                  str(_conf("MODEL_ROUTING_IDLE_SHUTDOWN_S", 900))))
WATCHDOG_TICK_S = float(_conf("MODEL_ROUTING_WATCHDOG_TICK_S", 30))
ENSURE_WAIT_S = float(_conf("MODEL_ROUTING_ENSURE_WAIT_S", 240.0))

_ENSURE_LOCK = _threading.Lock()
_WATCHDOG: "_threading.Thread | None" = None
_WATCHDOG_STOP = _threading.Event()


def hold_path() -> Path:
    """The operator hold the lab already honours (`LAB_MODEL_SERVER_HOLD_NAME`).

    `ensure()` honours it too: a suite run with the server held down must not be
    undone by a phone message asking a question.
    """
    return OWNER_FILE.parent / str(_conf("LAB_MODEL_SERVER_HOLD_NAME", "MODEL_SERVER_HOLD"))


def touch(reason: str | None = None, *, now: float | None = None) -> dict:
    """Record a use. Any process may call it; it never starts or stops anything."""
    owner = _read_owner()
    if not owner.get("pid"):
        return {"touched": False, "reason": "no ownership note (server not started by Aegis)"}
    owner["last_used_ts"] = float(now if now is not None else time.time())
    owner["last_used_for"] = reason or owner.get("last_used_for")
    owner["uses"] = int(owner.get("uses") or 0) + 1
    _write_owner(owner)
    return {"touched": True, "last_used_ts": owner["last_used_ts"]}


def busy(timeout: float = 2.0) -> bool:
    """Is a request mid-flight? `/slots` names it; unreadable means NOT busy.

    Only consulted once the idle clock has run out, so the cost of a wrong "not
    busy" is one interrupted generation after fifteen idle minutes.
    """
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{LLAMA_HOST}:{LLAMA_PORT}/slots",  # noqa: S310 localhost
                                    timeout=timeout) as fh:
            slots = json.loads(fh.read().decode() or "[]")
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return any(isinstance(s, dict) and s.get("is_processing") for s in (slots or []))


def _wait_ready(wait_s: float) -> bool:
    deadline = time.time() + max(0.0, wait_s)
    while True:
        if health_ok():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(1.0)


def ensure(reason: str, *, wait_s: float | None = None, bind: bool = True,
           watchdog: bool = True) -> dict:
    """Make the local model answer, starting it only if nothing is listening.

    Returns `status()` plus `ok`, `action` (`reused` | `started` | `refused` |
    `died` | `timeout`), `started_for` (the reason recorded when THIS server was
    started) and `requested_for` (this call's reason). A foreign server is
    USED, never adopted: it is not ours to stop, so no watchdog is armed for it.
    """
    wait = ENSURE_WAIT_S if wait_s is None else float(wait_s)
    with _ENSURE_LOCK:
        st = status()
        if st["listening"]:
            ready = bool(st["ready"]) or _wait_ready(wait)
            if st["started_by_aegis"]:
                touch(reason)
            owner = _read_owner()
            return {**status(), "ok": ready, "action": "reused",
                    "requested_for": reason,
                    "started_for": owner.get("started_for") if st["started_by_aegis"] else None,
                    "note": None if ready else f"listening but /health not 200 after {wait}s"}
        if hold_path().exists():
            return {**st, "ok": False, "action": "refused", "reason": "OPERATOR_HOLD",
                    "requested_for": reason,
                    "detail": f"{hold_path()} exists: an operator is holding the server down"}
        r = start(wait_s=wait, bind=bind)
        if r.get("ok") and r.get("pid"):
            owner = _read_owner()
            owner.update({"started_for": reason, "last_used_ts": time.time(),
                          "last_used_for": reason, "uses": 1,
                          "idle_shutdown_s": IDLE_SHUTDOWN_S})
            _write_owner(owner)
            if watchdog:
                start_watchdog()
        return {**(r.get("status") or status()), "ok": bool(r.get("ok")),
                "action": r.get("action"), "reason": r.get("reason"),
                "pid": r.get("pid"), "requested_for": reason,
                "started_for": reason if r.get("ok") else None,
                "idle_shutdown_s": IDLE_SHUTDOWN_S}


def idle_check(*, now: float | None = None) -> dict:
    """One watchdog tick: stop BY PID if THIS process started the server and
    nothing has used it for `IDLE_SHUTDOWN_S`. Returns what it decided."""
    owner = _read_owner()
    if not owner.get("pid"):
        return {"action": "none", "reason": "no ownership note"}
    inst = owning_instance(owner)
    if not inst["is_me"]:
        return {"action": "none", "reason": "not the starting process",
                "owner_pid": inst["owner_pid"]}
    t = float(now if now is not None else time.time())
    last = owner.get("last_used_ts")
    if last is None:
        try:
            last = datetime.fromisoformat(str(owner.get("started_utc"))).timestamp()
        except (TypeError, ValueError):
            last = t
    idle = t - float(last)
    if idle < IDLE_SHUTDOWN_S:
        return {"action": "none", "reason": "in use", "idle_s": round(idle, 1),
                "idle_shutdown_s": IDLE_SHUTDOWN_S}
    if busy():
        touch("watchdog:busy", now=t)
        return {"action": "none", "reason": "a request is mid-flight", "idle_s": round(idle, 1)}
    r = stop(allow_foreign=False)
    return {"action": "idle_stopped" if r.get("ok") else "stop_failed",
            "idle_s": round(idle, 1), "pid": r.get("pid"),
            "started_for": owner.get("started_for"),
            "stop": {k: r.get(k) for k in ("ok", "action", "reason", "pid")}}


def _watchdog_loop() -> None:
    while not _WATCHDOG_STOP.wait(WATCHDOG_TICK_S):
        try:
            out = idle_check()
        except Exception:                          # noqa: BLE001 - a tick never kills the host
            continue
        if out.get("action") == "idle_stopped" or out.get("reason") in (
                "no ownership note", "not the starting process"):
            return


def start_watchdog() -> bool:
    """Arm the idle watchdog in THIS process (idempotent). A daemon thread: it
    never keeps a process alive, and a process that exits takes a bound server
    with it anyway (`bind_lifetime`)."""
    global _WATCHDOG
    if _WATCHDOG is not None and _WATCHDOG.is_alive():
        return False
    _WATCHDOG_STOP.clear()
    _WATCHDOG = _threading.Thread(target=_watchdog_loop, name="llama-idle-watchdog",
                                  daemon=True)
    _WATCHDOG.start()
    return True


def stop_watchdog() -> None:
    _WATCHDOG_STOP.set()


def main() -> int:                                            # tiny CLI for the shell and for humans
    import argparse
    ap = argparse.ArgumentParser(description="local llama.cpp server: status / start / stop")
    ap.add_argument("action", choices=("status", "start", "stop", "stop-if-owned",
                                       "ensure", "idle-check"))
    ap.add_argument("--allow-foreign", action="store_true",
                    help="stop a server Aegis did not start (it may be mid-job)")
    ap.add_argument("--reason", default="cli", help="ensure: what the model is started for")
    a = ap.parse_args()
    if a.action == "status":
        out = status()
    elif a.action == "start":
        out = start()
    elif a.action == "stop":
        out = stop(allow_foreign=a.allow_foreign)
    elif a.action == "ensure":
        # a CLI process exits at once, so no watchdog could outlive it: unbound,
        # and the note says so -- stop it with `stop` when done.
        out = ensure(a.reason, bind=False, watchdog=False)
    elif a.action == "idle-check":
        out = idle_check()
    else:
        out = stop_if_owned()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
