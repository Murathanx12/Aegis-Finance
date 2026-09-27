"""L4 -- Qwen3-30B-A3B is MEASURED, not assumed: this job starts and stops it.

    python -m scripts.night_l4_qwen3_measure                 # the registered sweep
    python -m scripts.night_l4_qwen3_measure --smoke         # one setting, one prompt, no sha256
    python -m scripts.night_l4_qwen3_measure --plan-only     # the protocol + refusals, no server

WHY THIS CHANGED (2026-09-27). Murat asked why the 30B is not used. The honest
answer was: nobody had measured it idle. The 2026-09-10 numbers (17.28 GiB,
`--n-cpu-moe 48` -> 1,854 MiB VRAM, 19.8 tok/s generation, 5.6 tok/s prompt
eval) were taken while PyInstaller saturated all 20 cores, and the first
version of this file refused to start a server at all -- with the 7B up it
said REFUSED, with it down it said PENDING_MODEL -- so the queue item could
never produce a number. A measurement job that cannot measure is the
"gate that cannot go green" failure.

So the job now OWNS its server, and the rules that made the old version refuse
become the rules it runs under:

* It starts a SECOND, NAMED server config (`ServerConfig`) with an explicit
  model path and `--n-cpu-moe`, on its OWN port (`config.L4_PORT`). The default
  serving config (`llama_server.LLAMA_MODEL` on `LLAMA_PORT`) is never started,
  stopped or re-pointed: no caller of the default reader can reach the 30B.
* It REFUSES while any llama-server is up on the default port (it is not this
  job's), while the GPU is held (`gpu_guard.contention`, a RUNNING sim session
  -- which "owns the GPU" -- or another live L4/L4b holder), when free RAM is
  under `L4_MIN_FREE_RAM_GB` or disk under `L4_MIN_FREE_DISK_GB`.
* It waits on `/health`, not the open port (LISTENING IS NOT READY).
* It stops the server BY PID after every setting -- taskkill /PID, escalated to
  /F, then the Popen handle's own TerminateProcess -- and verifies that the PID
  is gone and VRAM came back to the pre-start baseline. Every exit path goes
  through `OwnedServer.__exit__`: an exception, a /health timeout, the night's
  STOP file, the job's own budget. A hard kill of this process is covered by
  the Windows job object (`llama_server.bind_lifetime`) and by the factory's
  tree kill, which reaches the server as our child.

A MODEL SWAP IS STILL A NEW ARM (`TRIAL-R2-monthly-news-digest-read.md` s.6):
`R2-Qwen3` is registered beside R2, never as an upgrade. This job measures cost
and speed; `L4b_qwen3_extraction` measures accuracy and applies the decision.

Licence: PRODUCT_EXPERIMENT. $0 -- local model only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402

JOB = "L4_qwen3_measure"
LICENCE = "PRODUCT_EXPERIMENT"
ARM = "R2-Qwen3"

MODEL_REPO = "Qwen/Qwen3-30B-A3B-Instruct-2507"
GGUF_REPO = "bartowski/Qwen_Qwen3-30B-A3B-Instruct-2507-GGUF"
GGUF_FILE = str(getattr(_cfg, "L4_QWEN3_MODEL_FILE", "Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"))
INCUMBENT_FILE = str(getattr(_cfg, "L4_INCUMBENT_MODEL_FILE", "Qwen2.5-7B-Instruct-Q4_K_M.gguf"))
LICENSE = "apache-2.0"

#: the roadmap's own sweep, descending -- fewer MoE layers on the CPU as the
#: number falls, so more of the model sits on the card
N_CPU_MOE_SWEEP = tuple(int(x) for x in getattr(_cfg, "L4_N_CPU_MOE_SWEEP", (48, 40, 32, 24)))
PORT = int(getattr(_cfg, "L4_PORT", 8093))
MIN_FREE_RAM_GB = float(getattr(_cfg, "L4_MIN_FREE_RAM_GB", 20.0))
MIN_FREE_DISK_GB = float(getattr(_cfg, "L4_MIN_FREE_DISK_GB", 25.0))
HEALTH_WAIT_S = float(getattr(_cfg, "L4_HEALTH_WAIT_S", 600.0))
MAX_MINUTES = float(getattr(_cfg, "L4_MAX_MINUTES", 50.0))
VRAM_TOL_MIB = int(getattr(_cfg, "L4_VRAM_BASELINE_TOL_MIB", 300))
VRAM_SETTLE_S = float(getattr(_cfg, "L4_VRAM_SETTLE_S", 20.0))
GEN_TOKENS = int(getattr(_cfg, "L4_GEN_TOKENS", 128))

#: the 5060's usable budget and the OS/desktop floor implied by HANDOFF
#: 2026-09-10 section 3 (8,151 total - 6,866 free = 1,285 MiB resident)
CARD_TOTAL_MIB = 8151
DESKTOP_FLOOR_MIB = 1285
STOP_WITHIN_MIB = 500

#: HANDOFF 2026-09-10 section 3, taken while PyInstaller used all 20 cores
CONTENDED = {"file_gb": 17.28, "n_cpu_moe": 48, "vram_mib": 1854,
             "generation_tok_s": 19.8, "prompt_eval_tok_s": 5.6,
             "incumbent_generation_tok_s": 41.4,
             "note": "a LOWER BOUND -- all 20 cores were saturated by a PyInstaller build"}

REFUSAL_DIGESTS = 200

#: the note this job's server is recorded in -- NOT `llama_server.OWNER_FILE`,
#: which belongs to the default reader. Resolved at call time (tests redirect).
OWNER_NOTE: Path | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def owner_note() -> Path:
    if OWNER_NOTE is not None:
        return Path(OWNER_NOTE)
    from backend.services import llama_server
    return llama_server.OWNER_FILE.parent / "llama_server_owner_l4.json"


# =============================================================== the frozen bench

#: Eight anonymised news items, R2-shaped (`r2_trial.DIGEST_SPEC`: '- ' prefix,
#: <= 320 chars, '[co]' masking). Content does not move a tok/s number much;
#: what matters is that EVERY setting and every later run reads the same bytes,
#: which the sha256 in the receipt pins.
BENCH_ITEMS = (
    "[co] reported quarterly revenue of $4.2 billion, up 11% from a year earlier, as demand "
    "for its data-center products offset weaker consumer sales; gross margin narrowed by "
    "80 basis points on higher component costs.",
    "[co] said it will cut about 1,200 jobs, roughly 6% of its workforce, as part of a "
    "restructuring aimed at saving $300 million a year by the end of next fiscal year.",
    "An analyst at a large brokerage raised the price target on [co] to $185 from $160, "
    "citing stronger-than-expected order growth and a longer product cycle.",
    "[co] announced a $2 billion share repurchase program and raised its quarterly dividend "
    "by 8%, its fifth consecutive annual increase.",
    "Regulators opened an inquiry into [co]'s billing practices in two states; the company "
    "said it was cooperating and did not expect a material financial impact.",
    "[co] agreed to acquire a privately held software firm for $650 million in cash, "
    "expanding its security portfolio; the deal is expected to close next quarter.",
    "[co] cut its full-year earnings guidance, now expecting $3.10 to $3.25 a share versus "
    "$3.40 to $3.55 previously, blaming currency headwinds and slower European demand.",
    "[co]'s chief financial officer will step down at the end of the month; the company "
    "named its treasurer as interim CFO while it searches for a permanent replacement.",
)


def bench_prompts() -> list[dict]:
    """The frozen prompt set: four R2-shaped reads (the registered prompt, each
    digest a rotation of the eight items) and one LONG read (all eight items
    three times) that measures prompt-eval at a realistic batch. Generation is
    measured on the long read with `ignore_eos`, so its token count is exact."""
    from backend.services.portfolio_intelligence import r2_trial

    def digest(items) -> str:
        return "\n".join("- " + " ".join(t.split())[:320] for t in items)

    out = []
    for k in range(4):
        rot = BENCH_ITEMS[k * 2:] + BENCH_ITEMS[:k * 2]
        out.append({"id": f"r2_rot{k}", "system": r2_trial.SYSTEM,
                    "user": r2_trial.PROMPT.format(digest=digest(rot)),
                    "max_tokens": 48, "ignore_eos": False})
    out.append({"id": "long_gen", "system": r2_trial.SYSTEM,
                "user": r2_trial.PROMPT.format(digest=digest(BENCH_ITEMS * 3)),
                "max_tokens": GEN_TOKENS, "ignore_eos": True})
    return out


def bench_sha256() -> str:
    blob = json.dumps(bench_prompts(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# =============================================================== the named server

@dataclass(frozen=True)
class ServerConfig:
    """A second, NAMED llama-server config. Never the default serving model."""
    name: str
    model: str
    port: int = PORT
    n_cpu_moe: int = 0
    ngl: int = 99
    ctx: int = 8192
    batch: int = 512
    ubatch: int = 128
    host: str = "127.0.0.1"

    def argv(self) -> list[str]:
        cmd = ["-m", str(self.model), "--host", self.host, "--port", str(self.port),
               "-ngl", str(self.ngl), "-c", str(self.ctx), "--no-webui",
               "--batch-size", str(self.batch), "--ubatch-size", str(self.ubatch)]
        if self.n_cpu_moe > 0:
            cmd += ["--n-cpu-moe", str(self.n_cpu_moe)]
        return cmd


def qwen3_config(n_cpu_moe: int, *, port: int | None = None) -> ServerConfig:
    from backend.services import llama_server as LS
    return ServerConfig(name=f"qwen3_30b_moe{n_cpu_moe}",
                        model=str(LS.LLAMA_MODEL.parent / GGUF_FILE),
                        port=int(port or PORT), n_cpu_moe=int(n_cpu_moe),
                        ngl=LS.LLAMA_NGL, ctx=LS.LLAMA_CTX,
                        batch=LS.LLAMA_BATCH, ubatch=LS.LLAMA_UBATCH)


def incumbent_config(*, port: int | None = None) -> ServerConfig:
    """The 7B exactly as the default reader runs it -- but on OUR port, started
    by US, so both arms of L4b go through one client and one lifecycle."""
    from backend.services import llama_server as LS
    return ServerConfig(name="qwen25_7b", model=str(LS.LLAMA_MODEL.parent / INCUMBENT_FILE),
                        port=int(port or PORT), n_cpu_moe=0, ngl=LS.LLAMA_NGL,
                        ctx=LS.LLAMA_CTX, batch=LS.LLAMA_BATCH, ubatch=LS.LLAMA_UBATCH)


# --------------------------------------------------------------- machine probes

def http_json(port: int, path: str, payload: dict | None = None, *, timeout: float = 300.0,
              host: str = "127.0.0.1") -> tuple[int, dict | None]:
    """(status, json) from the named server. Never raises for an HTTP failure."""
    url = f"http://{host}:{port}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:     # noqa: S310 loopback
            body = fh.read().decode("utf-8", errors="replace")
            try:
                return fh.status, json.loads(body)
            except ValueError:
                return fh.status, None
    except urllib.error.HTTPError as e:
        return int(e.code), None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None


def health_ok(port: int, timeout: float = 2.0) -> bool:
    """/health is 200 only once the weights are resident. The port is not."""
    return http_json(port, "/health", timeout=timeout)[0] == 200


def listener_pid(port: int) -> int | None:
    """The PID listening on `port`, or None when nothing is."""
    from backend.services import llama_server as LS
    if not LS.port_open(port=port):
        return None
    return LS.pid_on_port(port) or -1          # -1: listening, owner unresolvable


def avail_ram_gb() -> float | None:
    """Physical RAM the OS can hand out now (free + standby), in GiB, or None."""
    if sys.platform == "win32":
        try:
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _MS()
            m.dwLength = ctypes.sizeof(_MS)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return None
            return round(m.ullAvailPhys / (1 << 30), 2)
        except Exception:                                          # noqa: BLE001
            return None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return round(int(line.split()[1]) / (1 << 20), 2)
    except (OSError, ValueError):
        return None
    return None


def proc_rss_mib(pid: int) -> int | None:
    """The server's working set in MiB (mmapped weights that are resident count)."""
    if not pid or pid <= 0:
        return None
    if sys.platform == "win32":
        from backend.services import quiet_subprocess as qsp
        try:
            out = qsp.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
                          capture_output=True, text=True, timeout=15).stdout
        except Exception:                                          # noqa: BLE001
            return None
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 5 and parts[1].strip('"') == str(int(pid)):
                digits = "".join(c for c in parts[4] if c.isdigit())
                return int(digits) // 1024 if digits else None
        return None
    try:
        for line in Path(f"/proc/{int(pid)}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        return None
    return None


def vram_used_mib() -> int | None:
    from backend.services import llama_server as LS
    v = LS.vram()
    return None if v is None else int(v["used_mib"])


def _pid_alive(pid: int) -> bool:
    from backend.services import llama_server as LS
    return LS.pid_alive(int(pid))


# ---------------------------------------------------------------- the owner note

def _read_note() -> dict:
    try:
        return json.loads(owner_note().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_note(payload: dict) -> None:
    p = owner_note()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _clear_note(server_pid: int | None = None) -> None:
    note = _read_note()
    if server_pid is not None and note and int(note.get("server_pid") or 0) != int(server_pid):
        return                                   # not ours to clear
    try:
        owner_note().unlink()
    except FileNotFoundError:
        pass


class OwnedServer:
    """One llama-server this job started, stopped by PID on EVERY exit path.

    `with OwnedServer(cfg, job) as srv:` -- `start()` returns a dict and never
    raises for a server that fails to come up; `__exit__` always runs `stop()`.
    `launcher` replaces the llama-server binary (a test passes a fake server
    script); everything else -- the PID, /health, the kill -- is real.
    """

    def __init__(self, cfg: ServerConfig, job: str, *, launcher: list[str] | None = None,
                 health_wait_s: float = HEALTH_WAIT_S, poll_s: float = 1.0,
                 should_stop: Callable[[], str | None] | None = None,
                 log_path: Path | None = None, bind: bool = True,
                 kill_grace_s: float = 3.0) -> None:
        self.cfg = cfg
        self.job = job
        self.launcher = launcher
        self.health_wait_s = float(health_wait_s)
        self.poll_s = float(poll_s)
        self.should_stop = should_stop or (lambda: None)
        self.log_path = log_path
        self.bind = bind
        self.kill_grace_s = float(kill_grace_s)
        self.proc = None
        self.pid: int | None = None
        self.stopped: dict | None = None
        self.started_ts: float | None = None

    # -------------------------------------------------------------- start
    def command(self) -> list[str]:
        from backend.services import llama_server as LS
        head = list(self.launcher) if self.launcher else [str(LS.LLAMA_BIN)]
        return head + self.cfg.argv()

    def start(self) -> dict:
        from backend.services import llama_server as LS
        from backend.services import quiet_subprocess as qsp

        if not self.launcher:
            if not LS.LLAMA_BIN.exists():
                return {"ready": False, "action": "refused",
                        "reason": f"binary not found at {LS.LLAMA_BIN}"}
            if not Path(self.cfg.model).is_file():
                return {"ready": False, "action": "refused",
                        "reason": f"model not found at {self.cfg.model}"}
        taken = listener_pid(self.cfg.port)
        if taken is not None:
            return {"ready": False, "action": "refused",
                    "reason": f"port {self.cfg.port} is already held by PID {taken}; not ours"}
        log = self.log_path or (LS.LLAMA_HOME / f"server_{self.cfg.name}.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.command()
        self.started_ts = time.time()
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n# {_now()} {self.job} starting {self.cfg.name}: {cmd}\n")
            fh.flush()
            self.proc = qsp.popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                  creationflags=qsp.NEW_PROCESS_GROUP,
                                  cwd=str(Path(self.cfg.model).parent if not self.launcher
                                          else REPO))
        self.pid = int(self.proc.pid)
        bound = LS.bind_lifetime(self.pid) if self.bind else {"bound": False, "reason": "bind=False"}
        _write_note({"job": self.job, "job_pid": os.getpid(), "server_pid": self.pid,
                     "config": asdict(self.cfg), "cmd": cmd, "started_utc": _now(),
                     "lifetime_bound": bound})
        deadline = time.time() + self.health_wait_s
        outcome = {"ready": False, "action": "timeout", "pid": self.pid, "lifetime_bound": bound,
                   "log": str(log), "cmd": cmd}
        while time.time() < deadline:
            if health_ok(self.cfg.port):
                outcome.update(ready=True, action="started")
                break
            if self.proc.poll() is not None:
                outcome.update(action="died", exit_code=self.proc.returncode)
                break
            why = self.should_stop()
            if why:
                outcome.update(action="stopped_before_ready", reason=why)
                break
            time.sleep(self.poll_s)
        outcome["load_seconds"] = round(time.time() - self.started_ts, 1)
        if outcome["action"] == "timeout":
            outcome["reason"] = (f"/health did not return 200 within {self.health_wait_s:.0f}s "
                                 "(listening is not ready)")
        return outcome

    # -------------------------------------------------------------- stop
    def _kill(self, force: bool) -> None:
        from backend.services import quiet_subprocess as qsp
        if sys.platform == "win32":
            argv = ["taskkill", "/PID", str(int(self.pid)), "/T"] + (["/F"] if force else [])
            try:
                qsp.run(argv, capture_output=True, text=True, timeout=15)
            except Exception:                                      # noqa: BLE001
                pass
        else:
            import signal
            try:
                os.kill(int(self.pid), signal.SIGKILL if force else signal.SIGTERM)
            except OSError:
                pass

    def _dead(self) -> bool:
        if self.proc is not None:
            # our own handle is authoritative for our child: an exit code means
            # the PID is gone (and cannot be reused while we hold the handle)
            return self.proc.poll() is not None
        return not _pid_alive(int(self.pid))

    def stop(self, reason: str = "done") -> dict:
        """Idempotent. By PID only -- never by image name, never the default server."""
        if self.stopped is not None:
            return self.stopped
        if self.pid is None:
            self.stopped = {"ok": True, "action": "none", "reason": "never started"}
            return self.stopped
        from backend.services import llama_server as LS
        steps = []
        if not self._dead():
            self._kill(force=False)
            steps.append("taskkill /PID /T")
            end = time.time() + self.kill_grace_s
            while time.time() < end and not self._dead():
                time.sleep(0.2)
        if not self._dead():
            self._kill(force=True)
            steps.append("taskkill /PID /T /F")
            end = time.time() + 10
            while time.time() < end and not self._dead():
                time.sleep(0.2)
        if not self._dead() and self.proc is not None:
            try:
                self.proc.kill()                 # TerminateProcess on OUR handle
                steps.append("Popen.kill")
                self.proc.wait(timeout=10)
            except Exception:                                      # noqa: BLE001
                pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except Exception:                                      # noqa: BLE001
                pass
        dead = self._dead()
        still_listening = listener_pid(self.cfg.port)
        if dead:
            _clear_note(self.pid)
            LS.record_stop(int(self.pid), "operator", stopped_by=f"{self.job}:pid{os.getpid()}",
                           started_for=f"{self.job}:{self.cfg.name}")
        self.stopped = {"ok": bool(dead and still_listening is None), "action": "stopped",
                        "pid": self.pid, "reason": reason, "steps": steps,
                        "pid_alive_after": not dead,
                        "port_listening_after": still_listening is not None,
                        "note": "terminated by PID; never by image name"}
        return self.stopped

    def __enter__(self) -> "OwnedServer":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.stop("exception: " + exc_type.__name__ if exc_type else "context exit")
        return False


def wait_vram_back(baseline: int | None, *, tol: int = VRAM_TOL_MIB,
                   settle_s: float = VRAM_SETTLE_S,
                   read: Callable[[], int | None] | None = None) -> dict:
    """Did the card come back to where it was before we started? Polls briefly:
    the driver frees the mapping a moment after the PID is gone."""
    read = read or vram_used_mib
    if baseline is None:
        return {"checked": False, "reason": "no NVIDIA GPU visible; VRAM not measurable"}
    end = time.time() + settle_s
    now = read()
    while now is not None and now > baseline + tol and time.time() < end:
        time.sleep(1.0)
        now = read()
    return {"checked": True, "baseline_mib": baseline, "after_mib": now, "tolerance_mib": tol,
            "returned_to_baseline": now is not None and now <= baseline + tol}


# =============================================================== the refusals

def night_folder() -> Path:
    """The night folder for a write made NOW (resolved at write time)."""
    from scripts import night_factory
    return night_factory.out_dir()


def stop_file_reason() -> str | None:
    from scripts import night_factory
    return "STOP file present" if night_factory.stop_path().exists() else None


def sleep_refusal() -> str | None:
    """The night factory's own power-plan guard, called rather than copied: a
    17 GiB load that the machine can suspend in the middle of measures the
    suspend, not the model. `AEGIS_NIGHT_ALLOW_SLEEP=1` overrides there."""
    from scripts import night_factory
    why = night_factory.refuse_if_the_machine_may_sleep()
    return " ".join(why.split()) if why else None


def new_run_id() -> str:
    """A run id that no second run can share: UTC stamp + this process's PID."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-p{os.getpid()}"


def free_receipt_path(folder: Path, job: str, run_no: int, smoke: bool = False) -> Path:
    """`<job>_runNN.json` at the first NN >= `run_no` that does not exist yet --
    the factory's run number when it launched us (its file is not written until
    we exit), never an older run's receipt. A second run cannot overwrite."""
    n = max(1, int(run_no))
    while True:
        p = Path(folder) / f"{job}_run{n:02d}{'_smoke' if smoke else ''}.json"
        if not p.exists():
            return p
        n += 1


class AwakeBudget:
    """A job budget that counts AWAKE seconds, like `night_factory.await_within_box`.

    Every `spent()` adds the time since the last look; a gap longer than
    `gap_s` means the MACHINE stopped (standby froze us), so it is recorded in
    `slept_s` and does not spend the budget. The factory's box stays the
    authority on killing the job; this only decides when the job stops
    descending and writes its receipt."""

    def __init__(self, minutes: float, *, gap_s: float | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        from scripts import night_factory
        self.budget_s = float(minutes) * 60.0
        self.gap_s = float(night_factory.SLEEP_GAP_S if gap_s is None else gap_s)
        self.clock = clock
        self._last = clock()
        self.awake_s = 0.0
        self.slept_s = 0.0

    def spent(self) -> float:
        now = self.clock()
        delta = max(now - self._last, 0.0)
        self._last = now
        if delta > self.gap_s:
            self.slept_s += delta
        else:
            self.awake_s += delta
        return self.awake_s

    def remaining(self) -> float:
        return self.budget_s - self.spent()

    def exhausted(self) -> bool:
        return self.remaining() <= 0

    def view(self) -> dict:
        self.spent()
        return {"budget_s": round(self.budget_s, 1), "awake_s": round(self.awake_s, 1),
                "slept_s": round(self.slept_s, 1), "sleep_gap_s": self.gap_s}


def preflight(job: str, *, ports: tuple[int, ...] = (PORT,),
              need_ram_gb: float = MIN_FREE_RAM_GB, need_disk_gb: float = MIN_FREE_DISK_GB,
              models: tuple[str, ...] = (), check_gpu: bool = True,
              check_binary: bool = True) -> dict:
    """Every reason not to start, by name. An empty `refusals` list means go.

    Nothing here stops anything: a server on the default port -- the lab's 7B
    or a human's -- is not this job's, so the job waits for it rather than
    taking the card out from under it.
    """
    from backend.services import llama_server as LS
    refusals: list[dict] = []
    seen: dict = {"utc": _now(), "job_pid": os.getpid()}

    if check_binary and not LS.LLAMA_BIN.exists():
        refusals.append({"code": "REFUSED_BINARY_ABSENT", "detail": str(LS.LLAMA_BIN)})
    for m in models:
        if not Path(m).is_file():
            refusals.append({"code": "REFUSED_MODEL_ABSENT", "detail": str(m)})

    default_pid = listener_pid(LS.LLAMA_PORT)
    seen["default_port"] = {"port": LS.LLAMA_PORT, "listener_pid": default_pid}
    if default_pid is not None:
        refusals.append({"code": "REFUSED_SERVER_UP", "detail": (
            f"a llama-server is up on the default port {LS.LLAMA_PORT} as PID {default_pid}; "
            "it is not this job's and this job does not stop it -- rerun once it is down")})

    note = _read_note()
    seen["owner_note"] = note or None
    for port in ports:
        pid = listener_pid(port)
        seen.setdefault("named_ports", {})[str(port)] = pid
        if pid is None:
            continue
        orphan = (note and int(note.get("server_pid") or 0) == pid
                  and not _pid_alive(int(note.get("job_pid") or 0)))
        if orphan:
            # our own note names it and the job that started it is dead: reap
            # it BY PID (the job object should have; this is the backstop)
            srv = OwnedServer(ServerConfig(**note["config"]), job)
            srv.pid = pid
            seen["reaped_orphan"] = srv.stop("orphan of a dead L4/L4b job")
            if listener_pid(port) is None:
                continue
        refusals.append({"code": "REFUSED_PORT_TAKEN", "detail": (
            f"port {port} is held by PID {pid}, which no live L4/L4b job owns")})

    holder = int(note.get("job_pid") or 0) if note else 0
    if holder and holder != os.getpid() and _pid_alive(holder):
        refusals.append({"code": "REFUSED_GPU_LOCK_HELD", "detail": (
            f"{note.get('job')} (pid {holder}) holds the named server's card")})
    try:
        from backend.services import sim_session
        sim = sim_session.status()
        seen["sim_session"] = {"state": sim.get("state"), "pid_alive": sim.get("pid_alive")}
        if sim.get("state") in ("RUNNING", "STOPPING") and sim.get("pid_alive"):
            refusals.append({"code": "REFUSED_GPU_LOCK_HELD", "detail": (
                "a sim session is RUNNING and 'one session owns the GPU and the broker lease' "
                "(sim_session.start); L4 waits for it")})
    except Exception as exc:                                       # noqa: BLE001
        seen["sim_session"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    if check_gpu:
        try:
            from scripts import gpu_guard
            c = gpu_guard.contention()
            seen["gpu"] = {"contended": c["contended"], "reason": c["reason"],
                           "card": c["state"].get("card")}
            if c["contended"]:
                refusals.append({"code": "REFUSED_GPU_CONTENDED", "detail": c["reason"]})
        except Exception as exc:                                   # noqa: BLE001
            seen["gpu"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    ram = avail_ram_gb()
    seen["ram_available_gib"] = ram
    if ram is None or ram < need_ram_gb:
        refusals.append({"code": "REFUSED_RAM", "detail": (
            f"{'unmeasurable' if ram is None else f'{ram:.1f} GiB'} free RAM < "
            f"{need_ram_gb:g} GiB; a 17 GiB mmapped model on a short machine pages "
            "the weights and measures the disk, not the model")})

    try:
        from backend.services import disk_guard
        seen["disk"] = disk_guard.require_free(need_disk_gb, job, path=night_folder())
    except OSError as exc:
        refusals.append({"code": "REFUSED_DISK", "detail": str(exc)[:300]})

    why = stop_file_reason()
    if why:
        refusals.append({"code": "REFUSED_STOP_FILE", "detail": why})
    try:
        slp = sleep_refusal()
    except Exception as exc:                                       # noqa: BLE001
        slp = None
        seen["power_plan"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    else:
        seen["power_plan"] = {"may_sleep": bool(slp)}
    if slp:
        refusals.append({"code": "REFUSED_MAY_SLEEP", "detail": slp[:400]})
    return {"ok": not refusals, "refusals": refusals, "seen": seen,
            "floors": {"ram_gib": need_ram_gb, "disk_gib": need_disk_gb}}


# =============================================================== the measurement

def chat(port: int, prompt: dict, *, cache_prompt: bool = False,
         timeout: float = 600.0) -> dict:
    """One chat turn against the named server, with llama-server's own timings."""
    payload = {"messages": [{"role": "system", "content": prompt["system"]},
                            {"role": "user", "content": prompt["user"]}],
               "max_tokens": int(prompt.get("max_tokens") or 48), "temperature": 0.0,
               "cache_prompt": bool(cache_prompt)}
    if prompt.get("ignore_eos"):
        payload["ignore_eos"] = True
    t0 = time.perf_counter()
    status, body = http_json(port, "/v1/chat/completions", payload, timeout=timeout)
    wall = time.perf_counter() - t0
    out = {"id": prompt.get("id"), "http": status, "wall_s": round(wall, 3)}
    if status != 200 or not body:
        out["error"] = f"HTTP {status}"
        return out
    try:
        out["text"] = body["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError):
        out["text"] = None
    out["served_model"] = body.get("model")
    usage = body.get("usage") or {}
    out["tokens_in"] = usage.get("prompt_tokens")
    out["tokens_out"] = usage.get("completion_tokens")
    t = body.get("timings") or {}
    if t:
        out["timings_source"] = "llama-server timings"
        out["prompt_n"] = t.get("prompt_n")
        out["prompt_tok_s"] = t.get("prompt_per_second")
        out["gen_n"] = t.get("predicted_n")
        out["gen_tok_s"] = t.get("predicted_per_second")
    else:
        out["timings_source"] = "wall clock (the server sent no timings)"
        out["prompt_n"] = out["tokens_in"]
        out["gen_n"] = out["tokens_out"]
        out["prompt_tok_s"] = None
        out["gen_tok_s"] = (round(out["tokens_out"] / wall, 2)
                            if out.get("tokens_out") and wall > 0 else None)
    return out


def _median(xs) -> float | None:
    v = [float(x) for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(v), 2) if v else None


def measure_setting(n_cpu_moe: int, prompts: list[dict], *, job: str = JOB,
                    launcher: list[str] | None = None, port: int | None = None,
                    health_wait_s: float = HEALTH_WAIT_S,
                    should_stop: Callable[[], str | None] | None = None,
                    cfg: ServerConfig | None = None) -> dict:
    """Start -> /health -> warm-up -> bench -> stop BY PID -> VRAM back. One row."""
    cfg = cfg or qwen3_config(n_cpu_moe, port=port)
    should_stop = should_stop or stop_file_reason
    row: dict = {"n_cpu_moe": n_cpu_moe, "model": Path(cfg.model).name, "config": asdict(cfg),
                 "vram_baseline_mib": vram_used_mib(), "ram_available_before_gib": avail_ram_gb()}
    peaks = {"vram": [], "rss": [], "ram_avail": []}

    def sample(pid) -> None:
        # peaks, not one snapshot: the KV cache and the MoE experts page in as
        # the long read runs, so the loaded-but-idle reading is the floor
        peaks["vram"].append(vram_used_mib())
        peaks["rss"].append(proc_rss_mib(pid))
        peaks["ram_avail"].append(avail_ram_gb())
    with OwnedServer(cfg, job, launcher=launcher, health_wait_s=health_wait_s,
                     should_stop=should_stop) as srv:
        st = srv.start()
        row["start"] = {k: st.get(k) for k in ("ready", "action", "pid", "reason", "exit_code",
                                               "load_seconds", "log", "lifetime_bound")}
        row["server_pid"] = st.get("pid")
        if st.get("ready"):
            row["load_seconds"] = st.get("load_seconds")
            row["vram_loaded_mib"] = vram_used_mib()
            row["server_rss_mib"] = proc_rss_mib(srv.pid)
            row["ram_available_loaded_gib"] = avail_ram_gb()
            peaks["vram"].append(row["vram_loaded_mib"])
            peaks["rss"].append(row["server_rss_mib"])
            peaks["ram_avail"].append(row["ram_available_loaded_gib"])
            row["warmup"] = chat(cfg.port, prompts[0])
            calls = []
            for p in prompts:
                why = should_stop()
                if why:
                    row["interrupted"] = why
                    break
                calls.append(chat(cfg.port, p))
                sample(srv.pid)
            row["calls"] = calls
            ok = [c for c in calls if not c.get("error")]
            short = [c for c in ok if c["id"] != "long_gen"]
            long_ = [c for c in ok if c["id"] == "long_gen"]
            row["prompt_eval_tok_s_r2_median"] = _median(c.get("prompt_tok_s") for c in short)
            row["prompt_eval_tok_s_long"] = _median(c.get("prompt_tok_s") for c in long_)
            row["generation_tok_s"] = _median(c.get("gen_tok_s") for c in long_) or \
                _median(c.get("gen_tok_s") for c in ok)
            row["generation_tokens_measured"] = (long_[0].get("gen_n") if long_ else None)
            row["seconds_per_r2_call_median"] = _median(c.get("wall_s") for c in short)
            row["n_calls_ok"] = len(ok)
            row["status"] = "MEASURED" if len(ok) == len(prompts) else "PARTIAL"
        else:
            row["status"] = {"died": "DIED_LOADING", "timeout": "HEALTH_TIMEOUT",
                             "refused": "REFUSED",
                             "stopped_before_ready": "STOPPED"}.get(st.get("action"), "FAILED")
    row["stop"] = srv.stopped
    row["vram_after"] = wait_vram_back(row["vram_baseline_mib"])
    row["ram_available_after_gib"] = avail_ram_gb()
    num = lambda xs: [x for x in xs if isinstance(x, (int, float))]      # noqa: E731
    row["vram_peak_mib"] = max(num(peaks["vram"]), default=None)
    row["server_rss_peak_mib"] = max(num(peaks["rss"]), default=None)
    row["ram_available_min_gib"] = min(num(peaks["ram_avail"]), default=None)
    row["n_samples"] = len(peaks["vram"])
    return row


# =============================================================== the protocol

def _sha256_file(p: Path, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_check(with_hash: bool = True) -> dict:
    """Present? How many bytes? Which sha256? The file IS the frozen identity."""
    from backend.services import llama_server

    path = llama_server.LLAMA_MODEL.parent / GGUF_FILE
    out = {"expected_file": GGUF_FILE, "searched_at": str(path), "present": path.is_file(),
           "gguf_repo": GGUF_REPO, "hub_repo": MODEL_REPO, "license": LICENSE,
           "quant": "Q4_K_M -- the same quant level the incumbent runs, for an "
                    "apples-to-apples file-size and VRAM comparison"}
    if not path.is_file():
        out["sha256"] = None
        out["status"] = ("ABSENT -- download it from the GGUF repo above and re-run; the "
                         "sha256 computed at that moment is what freezes this arm's identity")
        return out
    out["bytes"] = int(path.stat().st_size)
    out["gigabytes"] = round(out["bytes"] / 1e9, 3)
    out["gibibytes"] = round(out["bytes"] / (1 << 30), 2)
    out["size_note"] = ("HANDOFF 2026-09-10 section 3 says 17.28 GB; that is GiB. The same "
                        "18,556,686,752 bytes is 18.56 GB decimal and 17.28 GiB binary -- "
                        "one file, two units, and NOT evidence the file changed.")
    if with_hash:
        t0 = time.time()
        out["sha256"] = _sha256_file(path)
        out["sha256_seconds"] = round(time.time() - t0, 1)
    out["status"] = "PRESENT"
    return out


def reader_state() -> dict:
    """The DEFAULT reader, read and never changed: this job does not touch it."""
    from backend.services import llama_server

    st = llama_server.status()
    return {"listening": st["listening"], "ready": st["ready"], "pid": st["pid"],
            "foreign": st["foreign"], "model_loaded": st["model"], "vram": st["vram"],
            "detail": st["detail"],
            "this_job_never_touches_the_default_server": (
                "the default reader (llama_server.LLAMA_MODEL on LLAMA_PORT) is never started, "
                "stopped or re-pointed by L4; L4 refuses while it is up and runs its OWN named "
                "server on its own port, stopped by PID")}


def protocol() -> dict:
    """The exact run, frozen now so the run that happens asks this question."""
    from backend.services.portfolio_intelligence import r2_trial

    usable = CARD_TOTAL_MIB - DESKTOP_FLOOR_MIB
    return {
        "step_1_idle_precondition": {
            "gpu": "scripts/gpu_guard.contention() -- the SAME helper E2 uses",
            "refuse_above_mib": 3072,
            "refuse_if": ["any llama-server on the default port (not this job's)",
                          "the named port held by a PID no live L4/L4b owns",
                          "a RUNNING sim session (it owns the GPU) or another L4/L4b holder",
                          f"free RAM < {MIN_FREE_RAM_GB:g} GiB",
                          f"free disk < {MIN_FREE_DISK_GB:g} GiB (disk_guard.require_free)",
                          "the night's STOP file",
                          "a power plan that lets the machine sleep on AC "
                          "(night_factory.refuse_if_the_machine_may_sleep)"],
        },
        "step_2_sweep": {
            "n_cpu_moe": list(N_CPU_MOE_SWEEP),
            "flag": "--n-cpu-moe on a NAMED server config (ServerConfig), port "
                    f"{PORT}; the default serving config is not changed",
            "between_settings": ("stop() BY PID (taskkill /PID /T, then /F, then the Popen "
                                 "handle) then start() -- never taskkill /IM -- and VRAM must "
                                 f"return within {VRAM_TOL_MIB} MiB of the pre-start baseline"),
            "ready_means": "/health == 200, not an open port",
            "measure_at_each": ["vram_mib (llama_server.vram())", "server working set MiB",
                                "RAM available before/loaded/after", "load_seconds",
                                "prompt_eval_tok_s (llama-server timings, cache_prompt off)",
                                "generation_tok_s (128 tokens, ignore_eos)"],
            "benchmark_prompt": ("R2's OWN frozen system + prompt over four fixed anonymised "
                                 "digests, plus one long read for prompt-eval at batch and "
                                 "generation; sha256 in the receipt"),
            "stop_condition": (f"stop descending once VRAM is within {STOP_WITHIN_MIB} MiB of "
                               f"{CARD_TOTAL_MIB} - {DESKTOP_FLOOR_MIB} = {usable} MiB usable, "
                               "or a setting fails to load, or the job's budget runs out"),
            "decisive_number": ("prompt-eval tok/s. R2's digests are a month of news per name, "
                                "so generation speed is nearly irrelevant beside how fast the "
                                "reader can READ"),
        },
        "step_3_refusal_rate": {
            "n_digests": REFUSAL_DIGESTS,
            "drawn_from": "PANEL-B's per-name-month digests (18,501 cells over 19 blocks)",
            "build": "the PLAIN Instruct build -- abliterated only if refusals exceed the "
                     "incumbent's, and then as its own arm R2-Qwen3-abliterated, never a "
                     "silent swap-in",
            "a_refusal_is": ["a non-JSON / unparseable reply (night_r2_monthly_llm.parse "
                             "returns no direction)",
                             "the model declining to answer",
                             "backend.services.llm_language.refuse() firing on a >10% "
                             "non-Latin-script reply -- the language pin applies to a local "
                             "reader too; a model that code-switches is still a bad reader"],
            "compared_to": ("Qwen2.5-7B's own refusal rate on the SAME 200 prompts -- not to "
                            "an absolute zero, because the incumbent's rate is not zero either"),
            "where": "L4b_qwen3_extraction measures refusals on the E-G1 set; the PANEL-B "
                     "digest refusal test stays owed to the registered R2-Qwen3 read",
        },
        "frozen_prompts": r2_trial.fingerprint(),
        "bench_prompts_sha256": bench_sha256(),
        "step_4_registration": {
            "arm": ARM,
            "beside": "R2 (Qwen2.5-7B-Instruct-Q4_K_M)",
            "same": ["PANEL-B", "the shuffled-digest control (seed 20260909)",
                     "read_minus_shuffled_control", "Newey-West lag-2 t on monthly blocks",
                     "25 bps a side on realised turnover"],
            "block_count": ("19 monthly blocks -- PANEL-B's, confirmed from "
                            "R2_widened_panelB_run01.json ('18501 cells over 19 month "
                            "blocks'). NOT 112: that is PANEL-A's count and PANEL-A is a "
                            "different panel."),
            "pre_registered_before": "the first Qwen3 digest is read",
        },
        "step_5_decision_rule": {
            "adopt_only_if": [
                "R2-Qwen3's OWN read_minus_shuffled_control beats R2's own, on the SAME "
                "blocks, at the same significance bar R2 uses",
                "AND its Lookahead Propensity (lane X item L3) is NOT worse than R2's",
            ],
            "a_pass_on_the_first_alone_is": "CONDITIONAL_ON_LAP, never ADOPTED",
            "why": ("a bigger, differently-trained model reading the same anonymised digest "
                    "may simply have memorised more pre-cutoff fact; a win driven by that is "
                    "not a win"),
            "l2_typing_rule": "L4b_qwen3_extraction's receipt (a separate, narrower question)",
        },
    }


def wall_time(prompt_eval_tok_s: float | None = None,
              generation_tok_s: float | None = None) -> dict:
    """Is this arm practical to run nightly? From R2's OWN measured token counts,
    at the CONTENDED rates and -- once measured -- at the IDLE ones."""
    # PANEL-A, night_factory_2026-09-08/R2_monthly_llm_2015_2024_run01.json:
    # usage.tokens_in 5,098,607 and tokens_out 216,677 over 15,433 calls
    # (7,417 arm + 7,417 control + 299 + 300 canary), elapsed 5,854.2 s.
    calls_a, tin, tout, elapsed_a = 15433, 5_098_607, 216_677, 5854.2
    p_tok = tin / calls_a
    c_tok = tout / calls_a
    panelb_calls = 18_501 * 2                     # the arm and its shuffled control

    incumbent_s_per_call = elapsed_a / calls_a
    q3 = CONTENDED["prompt_eval_tok_s"], CONTENDED["generation_tok_s"]
    q3_s_per_call = p_tok / q3[0] + c_tok / q3[1]
    out = {
        "source": ("R2 PANEL-A's own usage block -- 5,098,607 tokens in and 216,677 out over "
                   "15,433 calls in 5,854.2s. Not guessed."),
        "mean_prompt_tokens": round(p_tok, 1),
        "mean_completion_tokens": round(c_tok, 1),
        "panelB_calls_arm_plus_control": panelb_calls,
        "incumbent_qwen2_5_7b": {
            "measured_seconds_per_call": round(incumbent_s_per_call, 3),
            "panelB_hours": round(panelb_calls * incumbent_s_per_call / 3600, 2),
        },
        "qwen3_30b_a3b_at_the_CONTENDED_rates": {
            "prompt_eval_tok_s": q3[0], "generation_tok_s": q3[1],
            "seconds_per_call": round(q3_s_per_call, 1),
            "panelB_hours": round(panelb_calls * q3_s_per_call / 3600, 1),
            "panelB_days": round(panelb_calls * q3_s_per_call / 86400, 1),
        },
        "what_this_decides": (
            "at the contended prompt-eval rate the PANEL-B read is a multi-WEEK job, so the "
            "idle re-measurement is not a tidiness exercise -- it is the difference between "
            "an arm that can be run and one that cannot. If idle prompt-eval does not come "
            "up by roughly an order of magnitude, R2-Qwen3 is not a nightly arm at any "
            "n_cpu_moe and the honest move is to say so rather than to start it."),
        "arithmetic": ("digests x (mean_prompt_tokens / prompt_eval_tok_s + "
                       "mean_completion_tokens / generation_tok_s)"),
    }
    if prompt_eval_tok_s and generation_tok_s:
        s = p_tok / float(prompt_eval_tok_s) + c_tok / float(generation_tok_s)
        out["qwen3_30b_a3b_at_the_IDLE_measured_rates"] = {
            "prompt_eval_tok_s": prompt_eval_tok_s, "generation_tok_s": generation_tok_s,
            "seconds_per_call": round(s, 2),
            "panelB_hours": round(panelb_calls * s / 3600, 1),
            "panelB_days": round(panelb_calls * s / 86400, 2),
        }
    return out


# =============================================================== the run

def best_setting(rows: list[dict]) -> dict | None:
    """The measured setting with the highest R2 prompt-eval tok/s (the decisive
    number), ties to the smaller VRAM footprint."""
    ok = [r for r in rows if r.get("status") in ("MEASURED", "PARTIAL")
          and r.get("prompt_eval_tok_s_r2_median")]
    if not ok:
        return None
    ok.sort(key=lambda r: (-float(r["prompt_eval_tok_s_r2_median"]),
                           int(r.get("vram_loaded_mib") or 1 << 30)))
    return ok[0]


def run_sweep(*, smoke: bool = False, run_no: int = 1, out: Path | None = None,
        max_minutes: float = MAX_MINUTES, launcher: list[str] | None = None,
        sweep: tuple[int, ...] | None = None, check_gpu: bool = True,
        need_ram_gb: float = MIN_FREE_RAM_GB, need_disk_gb: float = MIN_FREE_DISK_GB,
        health_wait_s: float = HEALTH_WAIT_S, plan_only: bool = False,
        with_hash: bool | None = None) -> dict:
    t0 = time.time()
    budget = AwakeBudget(max_minutes)
    sweep = tuple(sweep if sweep is not None else N_CPU_MOE_SWEEP)
    if smoke:
        sweep = sweep[:1]
    prompts = bench_prompts()
    if smoke:
        prompts = prompts[:1]
    out_path: dict = {"p": Path(out) if out else None}

    def write(receipt: dict) -> Path:
        # resolved at the FIRST write (the night folder of that moment) and then
        # kept, so one run's flushes never split across two folders
        if out_path["p"] is None:
            out_path["p"] = free_receipt_path(night_folder(), JOB, run_no, smoke)
        from backend.services import disk_guard
        receipt["receipt_path"] = str(out_path["p"])
        receipt["written_utc"] = _now()
        receipt["elapsed_s"] = round(time.time() - t0, 1)
        receipt["budget"] = budget.view()
        disk_guard.atomic_write_json(out_path["p"], receipt)
        return out_path["p"]

    model_path = str(qwen3_config(sweep[0] if sweep else 48).model)
    receipt: dict = {
        "job": JOB, "licence": LICENCE, "run": run_no, "run_id": new_run_id(),
        "smoke": bool(smoke), "model": GGUF_FILE, "port": PORT,
        "n_cpu_moe_sweep": list(sweep),
        "stage": "raw", "llm_spend_usd": 0.0, "arm": ARM,
        "question": ("Idle, not contended: what does Qwen3-30B-A3B-Instruct-2507 Q4_K_M cost "
                     "in VRAM and RAM and buy in prompt-eval and generation tok/s at each "
                     "--n-cpu-moe, measured on a server this job starts and stops by PID?"),
        "inputs": [GGUF_FILE],
        # size and presence now; the sha256 (a 17 GiB read) only once the run is
        # cleared to start -- a refusal must not spend a minute of disk on it
        "model_identity": file_check(with_hash=False),
        "reader": reader_state(),
        "contended_measurement_being_superseded": CONTENDED,
        "protocol": protocol(),
        "status": "running", "settings": [],
    }
    pre = preflight(JOB, need_ram_gb=need_ram_gb, need_disk_gb=need_disk_gb,
                    models=(() if launcher else (model_path,)), check_gpu=check_gpu,
                    check_binary=not launcher)
    receipt["preflight"] = pre
    if not pre["ok"] or plan_only:
        codes = sorted({r["code"] for r in pre["refusals"]})
        receipt["status"] = codes[0] if codes else "PLAN_ONLY"
        receipt["verdict"] = (
            (f"REFUSED ({', '.join(codes)}): " + "; ".join(r["detail"] for r in pre["refusals"]))
            if codes else "PLAN_ONLY: the protocol and the preflight, no server started")
        receipt["headline"] = (f"{ARM} not measured: {', '.join(codes)}" if codes
                               else f"{ARM} plan only; preflight clear")
        receipt["wall_time"] = wall_time()
        receipt["next_test"] = ("the lab re-dispatches L4 from its idle-GPU queue on a later "
                                "day; it runs once no server is up, the card is free and "
                                f">= {need_ram_gb:g} GiB RAM is available")
        write(receipt)
        return receipt

    if (not smoke) if with_hash is None else with_hash:
        receipt["model_identity"] = file_check(with_hash=True)
    write(receipt)                                   # the protocol is on disk before a load
    usable = CARD_TOTAL_MIB - DESKTOP_FLOOR_MIB
    stopped_early = None
    try:
        for n in sweep:
            why = stop_file_reason()
            if why:
                stopped_early = why
                break
            if budget.remaining() < min(health_wait_s, 300):
                stopped_early = f"budget: {max_minutes:g} awake min would be exceeded"
                break
            remaining = max(30.0, budget.remaining())
            row = measure_setting(n, prompts, launcher=launcher,
                                  health_wait_s=min(health_wait_s, remaining),
                                  should_stop=lambda: stop_file_reason() or (
                                      "budget" if budget.exhausted() else None))
            receipt["settings"].append(row)
            write(receipt)
            if row.get("status") not in ("MEASURED", "PARTIAL"):
                stopped_early = f"n_cpu_moe {n} did not load ({row.get('status')})"
                break
            if row.get("vram_loaded_mib") and row["vram_loaded_mib"] >= usable - STOP_WITHIN_MIB:
                stopped_early = (f"stop condition: {row['vram_loaded_mib']} MiB is within "
                                 f"{STOP_WITHIN_MIB} MiB of {usable} usable")
                break
            if row.get("interrupted"):
                stopped_early = row["interrupted"]
                break
    except BaseException as exc:                     # the server is already stopped by
        receipt["exception"] = f"{type(exc).__name__}: {exc}"[:400]   # OwnedServer.__exit__
        stopped_early = stopped_early or "exception"
        receipt["status"] = "FAILED"
        write(receipt)
        raise
    receipt["stopped_early"] = stopped_early
    rows = receipt["settings"]
    best = best_setting(rows)
    all_stopped = all((r.get("stop") or {}).get("ok", True) for r in rows)
    vram_back = all((r.get("vram_after") or {}).get("returned_to_baseline", True)
                    or not (r.get("vram_after") or {}).get("checked") for r in rows)
    receipt["servers_stopped_by_pid"] = [
        {"n_cpu_moe": r["n_cpu_moe"], "pid": r.get("server_pid"),
         "stopped_ok": (r.get("stop") or {}).get("ok"),
         "vram_after_mib": (r.get("vram_after") or {}).get("after_mib"),
         "vram_baseline_mib": (r.get("vram_after") or {}).get("baseline_mib")} for r in rows]
    receipt["all_servers_stopped"] = all_stopped
    receipt["vram_returned_to_baseline"] = vram_back
    # one line per setting: the model, the knob, the speeds and the peaks
    receipt["per_setting"] = [
        {k: r.get(k) for k in ("model", "n_cpu_moe", "status", "prompt_eval_tok_s_r2_median",
                               "prompt_eval_tok_s_long", "generation_tok_s", "vram_loaded_mib",
                               "vram_peak_mib", "server_rss_peak_mib", "ram_available_min_gib",
                               "load_seconds")} for r in rows]
    if best:
        receipt["best_setting"] = {k: best.get(k) for k in (
            "n_cpu_moe", "prompt_eval_tok_s_r2_median", "prompt_eval_tok_s_long",
            "generation_tok_s", "vram_loaded_mib", "server_rss_mib", "load_seconds",
            "seconds_per_r2_call_median", "vram_peak_mib", "server_rss_peak_mib",
            "ram_available_min_gib")}
        receipt["wall_time"] = wall_time(best.get("prompt_eval_tok_s_r2_median")
                                         or best.get("prompt_eval_tok_s_long"),
                                         best.get("generation_tok_s"))
        cells = "; ".join(
            f"moe{r['n_cpu_moe']}: pp {r.get('prompt_eval_tok_s_r2_median')}/"
            f"{r.get('prompt_eval_tok_s_long')} tok/s, tg {r.get('generation_tok_s')} tok/s, "
            f"VRAM {r.get('vram_loaded_mib')} MiB, RSS {r.get('server_rss_mib')} MiB"
            for r in rows if r.get("status") in ("MEASURED", "PARTIAL"))
        full = (len([r for r in rows if r.get("status") == "MEASURED"]) == len(sweep)
                or (stopped_early or "").startswith("stop condition"))
        receipt["status"] = "MEASURED" if full else "PARTIAL"
        receipt["verdict"] = (
            f"DESCRIPTIVE: {ARM} measured idle on a server this job started and stopped by "
            f"PID at {len(rows)} setting(s); best n_cpu_moe {best['n_cpu_moe']}. "
            + ("Every server was stopped and VRAM returned to baseline."
               if all_stopped and vram_back else
               "WARNING: a server stop or the VRAM return did not verify -- see "
               "servers_stopped_by_pid."))
        receipt["headline"] = f"{ARM} idle: {cells}" + (
            f" (stopped early: {stopped_early})" if stopped_early and not full else "")
    else:
        receipt["status"] = "FAILED"
        receipt["wall_time"] = wall_time()
        receipt["verdict"] = (f"FAILED: no setting produced a measurement ({stopped_early}); "
                              "every server this job started was stopped by PID"
                              if all_stopped else "FAILED: and a stop did not verify")
        receipt["headline"] = f"{ARM} not measured: {stopped_early}"
    receipt["next_test"] = ("L4b_qwen3_extraction: the E-G1 240-item extraction set, local 7B "
                            "vs local 30B at this receipt's best n_cpu_moe, with the decision "
                            "rule written before the first item")
    write(receipt)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L4 Qwen3-30B-A3B idle measurement")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="one setting, one prompt, no sha256")
    ap.add_argument("--plan-only", action="store_true", help="preflight + protocol, no server")
    ap.add_argument("--max-minutes", type=float, default=MAX_MINUTES)
    ap.add_argument("--stage", default="raw")
    args = ap.parse_args(argv)
    r = run_sweep(smoke=args.smoke, run_no=args.run, out=Path(args.out) if args.out else None,
            max_minutes=args.max_minutes, plan_only=args.plan_only)
    print(r.get("headline"))
    print(r.get("verdict"))
    return 0


def L4_qwen3_measure(smoke: bool = False, run: int = 1, out: str | Path | None = None) -> dict:
    """The night-factory entry point. `out` is the receipt path the factory
    resolved (`night_factory_jobs` forwards `--out`), so this run's atomic
    mid-sweep flushes land in the SAME file the factory reads back: a kill
    mid-sweep leaves the rows on disk, and no stray run number appears."""
    return run_sweep(smoke=smoke, run_no=run, out=Path(out) if out else None)


if __name__ == "__main__":
    raise SystemExit(main())
