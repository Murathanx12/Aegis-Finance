"""The night supervisor's DEPENDENCY repair: classify, probe, repair, bounded.

LANE O2, 2026-09-28. The night of 09-27 -> 09-28 the reader died at 02:17 HKT on
"Chrome MCP subprocess tree cleanup could not be verified". The reader refuses
to restart the gateway by design, and the supervisor did not know how either: it
relaunched the reader 20 times in 100 minutes, each launch failing in seconds
against the same jammed gateway, and gave up at 04:05. Reading time achieved:
44 minutes of a 6.5-hour window (handoff §5 R1, R2).

So the supervisor now tells a READER fault from a DEPENDENCY fault, and repairs
a dependency before it relaunches anything:

    classify_exit(log text)  -> READER_CRASH | GATEWAY_DOWN | GATEWAY_STUCK |
                                CHROME_DOWN | NOT_MURATCLAW | POLICY_STOP |
                                QUEUE_DONE | UNKNOWN
    probe()                  -> gateway port, the browser status of the
                                dedicated profile, the dedicated Chrome's port
    repair(kind)             -> the LIGHTEST step that works, re-probing after
                                each: launch the dedicated Chrome; `browser
                                stop` on the profile; end an orphaned
                                chrome-devtools-mcp node process BY PID;
                                `gateway start`; `gateway restart`; then wait
                                for the port (bounded) and ONE attach.

Bounds: `RepairBudget` allows at most `OPENCLAW_REPAIRS_PER_HOUR` (3) repairs
per rolling hour, with exponential backoff from `OPENCLAW_REPAIR_BACKOFF_S`;
the supervisor never relaunches the reader while `probe()` says the dependency
is down. Every probe and every repair step returns a row the supervisor writes
to its receipt.

`NOT_MURATCLAW` (something other than the dedicated Chrome is on its port, or
the config drifted) is NEVER auto-repaired: it is the one fault where "make it
work again" could mean "attach to the wrong browser". It stops the night.

Nothing here kills by image name. The only process this module ends is an
orphaned `chrome-devtools-mcp` node process, by the PID read from its command
line, and only when its parent process is gone.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend import config as _config

CREATE_NO_WINDOW = 0x08000000

# ── classification ───────────────────────────────────────────────────────────

#: Order matters: the first family that matches wins.
PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("NOT_MURATCLAW", re.compile(r"REFUSED_NOT_MURATCLAW_INSTANCE|REFUSED_INSTANCE_CONFIG\b|"
                                 r"REFUSED_INSTANCE_LISTENER|REFUSED_INSTANCE_PROCESS|"
                                 r"REFUSED_TAB_NOT_IN_INSTANCE|REFUSED_MAIN_CHROME_PROFILE")),
    ("GATEWAY_STUCK", re.compile(r"GATEWAY_NEEDS_RESTART|subprocess tree cleanup could not be "
                                 r"verified|lifecycle changed while work was pending", re.I)),
    ("CHROME_DOWN", re.compile(r"REFUSED_INSTANCE_DOWN|REFUSED_INSTANCE_NO_PORT|"
                               r"attachOnly is enabled and profile \"?\w+\"? is not running", re.I)),
    ("GATEWAY_DOWN", re.compile(r"REFUSED_GATEWAY_DOWN|gateway timeout|timeout after \d+\s*ms|"
                                r"gateway (?:closed|unreachable|not running|is not running)|"
                                r"ECONNREFUSED", re.I)),
    # every lane of a run failed to OPEN its tab (2026-09-28: a blocked
    # window.open). Not a crash to relaunch every tick: the supervisor backs off.
    ("READER_CANNOT_OPEN_TABS", re.compile(r"READER_CANNOT_OPEN_TABS")),
    ("POLICY_STOP", re.compile(r"REFUSED_ZERO_YIELD_LANE|REFUSED_NO_HANDOFF|REFUSED_THROTTLE_DAY|"
                               r"REFUSED_PAYMENT|REFUSED_MESSAGE|REFUSED_DISK|REFUSED_READER_BUSY|"
                               r"REFUSED_ARCHIVE_OFF")),
    ("QUEUE_DONE", re.compile(r"QUEUE_DONE|queue finished|nothing left to read|all lines done",
                              re.I)),
)
DEPENDENCY = frozenset({"GATEWAY_DOWN", "GATEWAY_STUCK", "CHROME_DOWN"})


def classify_exit(text: str) -> dict:
    """{kind, evidence} for the tail of a reader's log / receipt text."""
    t = text or ""
    for kind, rx in PATTERNS:
        m = None
        for m in rx.finditer(t):
            pass
        if m is not None:
            a = max(0, m.start() - 80)
            return {"kind": kind, "evidence": t[a:m.end() + 80].strip()[:240]}
    if re.search(r"Traceback|Error|REFUSED", t):
        return {"kind": "READER_CRASH", "evidence": t.strip()[-240:]}
    return {"kind": "UNKNOWN", "evidence": t.strip()[-240:]}


# ── the budget ───────────────────────────────────────────────────────────────

@dataclass
class RepairBudget:
    """At most `per_hour` repairs in any rolling hour; after each, the next
    one waits `backoff_s * 2**(n-1)` where n counts repairs in the window."""
    per_hour: int = field(default_factory=lambda: int(getattr(_config,
                                                              "OPENCLAW_REPAIRS_PER_HOUR", 3)))
    backoff_s: float = field(default_factory=lambda: float(getattr(
        _config, "OPENCLAW_REPAIR_BACKOFF_S", 60.0)))
    stamps: list[float] = field(default_factory=list)

    def _window(self, now: float) -> list[float]:
        self.stamps = [t for t in self.stamps if now - t < 3600.0]
        return self.stamps

    def next_allowed_at(self, now: float) -> float:
        w = self._window(now)
        if len(w) >= self.per_hour:
            return w[0] + 3600.0
        if not w:
            return now
        return max(now, w[-1] + self.backoff_s * (2 ** (len(w) - 1)))

    def allow(self, now: float) -> tuple[bool, float]:
        at = self.next_allowed_at(now)
        return at <= now, max(0.0, at - now)

    def spend(self, now: float) -> None:
        self._window(now)
        self.stamps.append(now)


# ── probes (injectable) ──────────────────────────────────────────────────────

def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _openclaw(args: list[str], timeout: float = 120.0) -> dict:
    """One CLI call through `openclaw_client._run` (no shell, ledger kept)."""
    from backend.services import openclaw_client as OC
    t0 = time.monotonic()
    try:
        r = OC._run(list(args), timeout=timeout)
        return {"rc": r.returncode, "out": ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-400:],
                "seconds": round(time.monotonic() - t0, 2)}
    except subprocess.TimeoutExpired:
        return {"rc": None, "out": f"timeout after {timeout:.0f} s",
                "seconds": round(time.monotonic() - t0, 2)}


def _browser_status_http(profile: str) -> dict:
    """The dedicated profile's status over `POST /tools/invoke` (0.4-0.7 s,
    measured 2026-09-28) -- a probe that does not itself start a node process."""
    from backend.services import openclaw_http as OH
    t0 = time.monotonic()
    try:
        r = OH.HttpTransport().run(["browser", "--browser-profile", profile, "--json", "status"],
                                   timeout=20.0)
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "timeout", "seconds": round(time.monotonic() - t0, 2)}
    if r is None:
        return {"ok": False, "detail": "not served", "seconds": 0.0}
    out = {"ok": r.returncode == 0, "seconds": round(time.monotonic() - t0, 2)}
    if r.returncode == 0:
        try:
            d = json.loads(r.stdout)
            out.update(running=bool(d.get("running")), cdpUrl=d.get("cdpUrl"))
        except ValueError:
            out["detail"] = (r.stdout or "")[:160]
    else:
        out["detail"] = (r.stderr or r.stdout or "")[:240]
    return out


def _powershell_json(cmd: str, timeout: float = 30.0) -> Any:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, timeout=timeout, stdin=subprocess.DEVNULL, shell=False,
                       creationflags=CREATE_NO_WINDOW)
    try:
        d = json.loads(r.stdout) if (r.stdout or "").strip() else []
    except ValueError:
        return []
    return d if isinstance(d, list) else [d]


def _orphan_mcp_pids() -> list[dict]:
    """`chrome-devtools-mcp` node processes whose PARENT process is gone."""
    rows = _powershell_json(
        "$all = Get-CimInstance Win32_Process; $ids = $all | ForEach-Object { $_.ProcessId }; "
        "$all | Where-Object { $_.CommandLine -match 'chrome-devtools-mcp' } | "
        "Select-Object ProcessId,ParentProcessId,Name,@{n='parent_alive';e={$ids -contains "
        "$_.ParentProcessId}} | ConvertTo-Json -Compress")
    return [{"pid": int(r.get("ProcessId") or 0), "ppid": int(r.get("ParentProcessId") or 0),
             "name": r.get("Name"), "parent_alive": bool(r.get("parent_alive"))}
            for r in rows if isinstance(r, dict)]


def _kill_pid(pid: int) -> bool:
    """By PID only -- never by image name (CLAUDE.md protocol 6)."""
    r = subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True,
                       text=True, stdin=subprocess.DEVNULL, shell=False,
                       creationflags=CREATE_NO_WINDOW)
    return r.returncode == 0


def _gateway_listener_pid() -> int | None:
    rows = _powershell_json(f"Get-NetTCPConnection -State Listen -LocalPort "
                            f"{_gw_port()} -ErrorAction SilentlyContinue | Select-Object "
                            f"-First 1 OwningProcess | ConvertTo-Json -Compress")
    for r in rows:
        if isinstance(r, dict) and r.get("OwningProcess"):
            return int(r["OwningProcess"])
    return None


def _gateway_procs() -> list[dict]:
    """Every live `openclaw ... gateway --port` node process (supervisor or child)."""
    rows = _powershell_json(
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { "
        "$_.CommandLine -match 'openclaw' -and $_.CommandLine -match 'gateway --port' } | "
        "Select-Object ProcessId,ParentProcessId,CreationDate | ConvertTo-Json -Compress")
    return [{"pid": int(r.get("ProcessId") or 0), "ppid": int(r.get("ParentProcessId") or 0)}
            for r in rows if isinstance(r, dict)]


def _free_gb() -> float | None:
    rows = _powershell_json("Get-CimInstance Win32_OperatingSystem | Select-Object "
                            "FreePhysicalMemory | ConvertTo-Json -Compress")
    for r in rows:
        if isinstance(r, dict) and r.get("FreePhysicalMemory") is not None:
            return round(float(r["FreePhysicalMemory"]) / (1024 * 1024), 2)
    return None


def _gw_host() -> str:
    return str(getattr(_config, "OPENCLAW_GATEWAY_HOST", "127.0.0.1"))


def _gw_port() -> int:
    return int(getattr(_config, "OPENCLAW_GATEWAY_PORT", 18789))


def _profile() -> str:
    return str(getattr(_config, "OPENCLAW_DEDICATED_PROFILES", ("muratclaw",))[0])


@dataclass
class Deps:
    """Every side effect, injectable (tests pass fakes)."""
    port_open: Callable[[str, int], bool] = _port_open
    openclaw: Callable[..., dict] = _openclaw
    browser_status: Callable[[str], dict] = _browser_status_http
    chrome_status: Callable[[], dict] = None               # type: ignore[assignment]
    chrome_launch: Callable[[], dict] = None               # type: ignore[assignment]
    orphan_mcp: Callable[[], list[dict]] = _orphan_mcp_pids
    kill_pid: Callable[[int], bool] = _kill_pid
    gateway_procs: Callable[[], list[dict]] = _gateway_procs
    free_gb: Callable[[], float | None] = _free_gb
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        from backend.services import muratclaw_instance as MI
        if self.chrome_status is None:
            self.chrome_status = MI.status
        if self.chrome_launch is None:
            self.chrome_launch = MI.launch_attach


def probe(deps: Deps | None = None) -> dict:
    """The dependency's state, cheapest checks first. `healthy` means: the
    gateway port answers, the dedicated Chrome answers on its port, and the
    gateway reports the dedicated profile running (not latched)."""
    d = deps or Deps()
    t0 = d.clock()
    out: dict[str, Any] = {"gateway_port": d.port_open(_gw_host(), _gw_port())}
    try:
        cs = d.chrome_status()
    except Exception as exc:                                        # noqa: BLE001
        cs = {"running_with_port": False, "error": str(exc)[:160]}
    out["chrome_port"] = bool(cs.get("running_with_port"))
    if out["gateway_port"]:
        bs = d.browser_status(_profile())
        out["browser_status"] = bs
        detail = str(bs.get("detail") or "")
        out["latched"] = bool(PATTERNS[1][1].search(detail))
        out["profile_running"] = bool(bs.get("ok") and bs.get("running"))
    else:
        out["latched"], out["profile_running"] = False, False
    out["healthy"] = bool(out["gateway_port"] and out["chrome_port"] and out["profile_running"])
    if not out["gateway_port"]:
        out["fault"] = "GATEWAY_DOWN"
    elif out["latched"]:
        out["fault"] = "GATEWAY_STUCK"
    elif not out["chrome_port"]:
        out["fault"] = "CHROME_DOWN"
    elif not out["profile_running"]:
        out["fault"] = "PROFILE_DETACHED"
    else:
        out["fault"] = None
    out["seconds"] = round(d.clock() - t0, 2)
    return out


def wait_for_port(deps: Deps, *, wait_s: float | None = None, poll_s: float = 1.0) -> dict:
    wait_s = float(getattr(_config, "OPENCLAW_REPAIR_PORT_WAIT_S", 90.0)) if wait_s is None \
        else wait_s
    t0 = deps.clock()
    while deps.clock() - t0 < wait_s:
        if deps.port_open(_gw_host(), _gw_port()):
            return {"port": True, "seconds": round(deps.clock() - t0, 1)}
        deps.sleep(poll_s)
    return {"port": False, "seconds": round(deps.clock() - t0, 1)}


def min_free_gb() -> float:
    return float(getattr(_config, "OPENCLAW_REPAIR_MIN_FREE_GB", 1.5))


def repair(fault: str, *, deps: Deps | None = None, log: Callable[..., None] | None = None
           ) -> dict:
    """The lightest repair that clears `fault`, re-probing after each step.
    Returns `{fault, steps: [...], healthy, cleared_by, stopped_because}`;
    never raises.

    Two rules from the kill test of 2026-09-28 14:30 (see the lane-O note):
    * NO gateway (re)start below `OPENCLAW_REPAIR_MIN_FREE_GB` free RAM -- at
      0.5-0.8 GB a started gateway did not bind its port for 15+ minutes;
    * NEVER `gateway restart` while a gateway process is still coming up:
      `restart` ended the task's root and started a second tree beside the
      first, and two gateways then competed for one port."""
    d = deps or Deps()
    say = log or (lambda **k: None)
    steps: list[dict] = []
    t0 = d.clock()

    def step(name: str, fn: Callable[[], Any]) -> dict:
        s0 = d.clock()
        try:
            res = fn()
        except Exception as exc:                                    # noqa: BLE001
            res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        after = probe(d)
        row = {"step": name, "result": res, "seconds": round(d.clock() - s0, 2),
               "probe_after": {k: after.get(k) for k in ("healthy", "fault", "gateway_port",
                                                         "chrome_port", "latched",
                                                         "profile_running")}}
        steps.append(row)
        say(event="repair_step", fault=fault, **row)
        return after

    def done(after: dict, cleared: str | None, stopped: str | None = None) -> dict:
        return {"fault": fault, "steps": steps, "healthy": bool(after.get("healthy")),
                "cleared_by": cleared, "stopped_because": stopped,
                "seconds": round(d.clock() - t0, 2)}

    if fault == "NOT_MURATCLAW":
        out = done({"healthy": False}, None, "NOT_MURATCLAW is never auto-repaired: it could "
                                             "mean attaching to the wrong browser")
        out["refused"] = out["stopped_because"]
        return out
    prof = _profile()
    after = probe(d)
    if after["healthy"]:
        return done(after, "already_healthy")

    # 1. the dedicated Chrome
    if not after["chrome_port"]:
        after = step("launch_dedicated_chrome", d.chrome_launch)
        if after["healthy"]:
            return done(after, "launch_dedicated_chrome")

    # 2. a latched gateway: the light resets first
    if after.get("latched") or fault == "GATEWAY_STUCK":
        after = step("browser_stop", lambda: d.openclaw(["browser", "--browser-profile", prof,
                                                         "stop"], 90.0))
        if after["healthy"]:
            return done(after, "browser_stop")

        def kill_orphans() -> dict:
            orphans = [o for o in d.orphan_mcp() if not o.get("parent_alive")]
            return {"orphans": orphans, "killed": [o["pid"] for o in orphans
                                                   if d.kill_pid(o["pid"])]}
        after = step("kill_orphan_mcp_by_pid", kill_orphans)
        if after["healthy"]:
            return done(after, "kill_orphan_mcp_by_pid")

    # 3. the gateway itself: memory first, never two trees
    if not after["healthy"] and (not after["gateway_port"] or after.get("latched")
                                 or fault == "GATEWAY_STUCK"):
        free = d.free_gb()
        if free is not None and free < min_free_gb():
            say(event="repair_deferred", fault=fault, why="LOW_MEMORY", free_gb=free)
            return done(after, None, f"LOW_MEMORY: {free} GB free < {min_free_gb()} GB; a "
                                     f"gateway started now does not bind its port")
        if not after["gateway_port"]:
            procs = d.gateway_procs()
            if procs:
                # something is already starting: wait for it, do not start another
                after = step("wait_for_port_existing", lambda: wait_for_port(d))
                if after["healthy"] or after["gateway_port"]:
                    if not after["healthy"]:
                        after = step("attach_once", lambda: d.openclaw(
                            ["browser", "--browser-profile", prof, "start"], 90.0))
                    return done(after, "wait_for_port_existing" if after["healthy"] else None,
                                None if after["healthy"] else "attach failed after the port "
                                                              "came up")
                return done(after, None, f"GATEWAY_STARTING_SLOW: {len(procs)} gateway "
                                         f"process(es) alive, port closed; not starting "
                                         f"another")
            after = step("gateway_start", lambda: d.openclaw(["gateway", "start"], 120.0))
            if not after["gateway_port"]:
                after = step("wait_for_port", lambda: wait_for_port(d))
        else:
            after = step("gateway_restart", lambda: d.openclaw(["gateway", "restart"], 180.0))
            if not after["gateway_port"]:
                after = step("wait_for_port", lambda: wait_for_port(d))
        if after["healthy"]:
            return done(after, steps[-1]["step"])
        if not after["gateway_port"]:
            return done(after, None, "the gateway did not bind its port within the wait; "
                                     "not restarting a gateway that may still be starting")

    # 4. one attach
    after = step("attach_once", lambda: d.openclaw(["browser", "--browser-profile", prof,
                                                    "start"], 90.0))
    return done(after, "attach_once" if after["healthy"] else None,
                None if after["healthy"] else "still unhealthy after one attach")
