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

REPO = Path(__file__).resolve().parents[2]

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
            "n_cpu_moe": LLAMA_N_CPU_MOE}


# ------------------------------------------------------------------ start/stop

def start(wait_s: float = 90.0) -> dict:
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
           "-ngl", str(LLAMA_NGL), "-c", str(LLAMA_CTX), "--no-webui"]
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
    _write_owner({"pid": proc.pid, "started_utc": _now(), "model": LLAMA_MODEL.name,
                  "cmd": cmd, "port": LLAMA_PORT})
    if wait_s <= 0:
        # the desktop shell starts it and gets on with opening the window; a
        # multi-GB model loads while the splash is up. "starting" is a state,
        # and calling it "timeout" -- which the first build did -- reads as a
        # failure of a process that is loading perfectly well.
        return {"ok": True, "action": "starting", "pid": proc.pid, "ready": False,
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


def stop_if_owned() -> dict:
    """What the desktop shell calls on exit.

    Murat asked for auto-close on shutdown. It applies to a server Aegis
    started; one that was already running is left alone, because closing a
    window is not consent to kill somebody else's 8 GB job.
    """
    st = status()
    if not st["listening"]:
        return {"ok": True, "action": "none", "reason": "nothing listening"}
    if not st["started_by_aegis"]:
        return {"ok": True, "action": "left_running",
                "reason": "the server was already running when Aegis started; not ours to stop",
                "pid": st["pid"]}
    return stop(allow_foreign=False)


def main() -> int:                                            # tiny CLI for the shell and for humans
    import argparse
    ap = argparse.ArgumentParser(description="local llama.cpp server: status / start / stop")
    ap.add_argument("action", choices=("status", "start", "stop", "stop-if-owned"))
    ap.add_argument("--allow-foreign", action="store_true",
                    help="stop a server Aegis did not start (it may be mid-job)")
    a = ap.parse_args()
    if a.action == "status":
        out = status()
    elif a.action == "start":
        out = start()
    elif a.action == "stop":
        out = stop(allow_foreign=a.allow_foreign)
    else:
        out = stop_if_owned()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
