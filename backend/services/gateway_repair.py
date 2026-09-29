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
    #: need_gb -> result; frees memory the reader owns (2026-09-29)
    reclaim: Callable[[float], dict] = None                # type: ignore[assignment]

    def __post_init__(self) -> None:
        from backend.services import muratclaw_instance as MI
        if self.chrome_status is None:
            self.chrome_status = MI.status
        if self.chrome_launch is None:
            self.chrome_launch = MI.launch_attach
        if self.reclaim is None:
            self.reclaim = lambda need: reclaim_memory(need_gb=need)


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
            # 2026-09-29: this used to RETURN here -- a floor the repair itself
            # could never clear, so a browser holding the memory blocked the
            # gateway forever. Now: reclaim what the reader owns (hung tabs,
            # idle tabs, a graceful restart of the dedicated Chrome), then go on
            # -- below the floor too, with the bounded port wait after it.
            rec = step("reclaim_memory", lambda: d.reclaim(min_free_gb()))
            if rec["healthy"]:
                return done(rec, "reclaim_memory")
            after = rec
            free2 = d.free_gb()
            if free2 is not None and free2 < min_free_gb():
                say(event="repair_below_floor", fault=fault, free_gb=free2,
                    floor_gb=min_free_gb(), why="reclaimed what the reader owns; proceeding")
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


# ── a HUNG TAB jams every attach (2026-09-29 00:59 HKT) ──────────────────────
#
# From 00:59 to 02:15 HKT every browser action failed with
# `browserType.connectOverCDP: Timeout 9000ms exceeded` (the gateway's own log,
# 343 times) while `probe()` said healthy: the gateway port answered, Chrome's
# /json answered, the profile was "running". Two page targets of the dedicated
# Chrome did not answer a one-line `Runtime.evaluate` in 4 s (a wsj.com tab and
# an x.com tab left open by an earlier job), and Playwright's connectOverCDP
# waits for EVERY page to initialise, so one hung renderer fails every attach.
# The pool kept opening tabs (plain /json calls) and read nothing: 98 BLANK
# pages in 75 minutes. A gateway restart does not help (the browser is external
# to the gateway); closing the hung target does.

def _loopback_ws(url: str) -> bool:
    return bool(re.match(r"^ws://(127\.0\.0\.1|localhost)[:/]", url or ""))


def _cdp_call(ws_url: str, method: str, params: dict | None = None,
              timeout: float = 4.0) -> dict:
    """One CDP command on a LOOPBACK websocket; raises on timeout."""
    import websocket  # websocket-client, in the venv
    if not _loopback_ws(ws_url):
        raise ValueError(f"REFUSED_NOT_LOOPBACK: {ws_url!r}")
    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return msg
        raise TimeoutError(f"{method}: no reply in {timeout} s")
    finally:
        ws.close()


def _page_targets() -> list[dict]:
    from backend.services import muratclaw_instance as MI
    rows = MI._http_json(f"{MI.cdp_base()}/json/list")
    return [t for t in rows or [] if isinstance(t, dict) and t.get("type") == "page"]


def _page_responsive(target: dict, timeout: float) -> bool:
    try:
        r = _cdp_call(str(target.get("webSocketDebuggerUrl") or ""), "Runtime.evaluate",
                      {"expression": "1", "returnByValue": True}, timeout=timeout)
        return "result" in r
    except Exception:                                               # noqa: BLE001
        return False


def _close_target(target_id: str) -> bool:
    """`Target.closeTarget` on the dedicated Chrome's BROWSER websocket (the
    browser process closes the tab even when its renderer is hung)."""
    from backend.services import muratclaw_instance as MI
    ver = MI._http_json(f"{MI.cdp_base()}/json/version")
    r = _cdp_call(str(ver.get("webSocketDebuggerUrl") or ""), "Target.closeTarget",
                  {"targetId": str(target_id)}, timeout=10.0)
    return bool((r.get("result") or {}).get("success", "error" not in r))


def _prove_dedicated() -> dict:
    from backend.services import muratclaw_instance as MI
    return MI.prove()


@dataclass
class TabDeps:
    """Side effects of the hung-tab check, injectable."""
    prove: Callable[[], dict] = _prove_dedicated
    page_targets: Callable[[], list[dict]] = _page_targets
    responsive: Callable[[dict, float], bool] = _page_responsive
    close_target: Callable[[str], bool] = _close_target
    clock: Callable[[], float] = time.monotonic


def hung_page_targets(deps: TabDeps | None = None, *, timeout_s: float | None = None
                      ) -> dict:
    """Which page targets of the dedicated Chrome do not answer a one-line
    evaluate within `timeout_s`. Proves the instance first; never raises."""
    d = deps or TabDeps()
    to = float(getattr(_config, "READER_HUNG_TAB_TIMEOUT_S", 4.0)) if timeout_s is None \
        else timeout_s
    t0 = d.clock()
    try:
        d.prove()
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "refused": f"{type(exc).__name__}: {str(exc)[:200]}",
                "hung": [], "n_pages": None}
    try:
        pages = d.page_targets()
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "refused": f"list failed: {exc}"[:200], "hung": [], "n_pages": None}
    hung = [{"id": str(p.get("id")), "url": str(p.get("url") or "")[:160]}
            for p in pages if not d.responsive(p, to)]
    return {"ok": True, "n_pages": len(pages), "hung": hung,
            "seconds": round(d.clock() - t0, 2)}


def close_hung_tabs(deps: TabDeps | None = None, *, timeout_s: float | None = None,
                    log: Callable[..., None] | None = None) -> dict:
    """Find the hung page targets and close each one (by target id, on the
    PROVEN dedicated Chrome). Returns `{n_pages, hung, closed, failed}`."""
    d = deps or TabDeps()
    say = log or (lambda **k: None)
    h = hung_page_targets(d, timeout_s=timeout_s)
    out = {**h, "closed": [], "failed": []}
    if not h.get("ok"):
        say(event="hung_tabs_check_refused", why=h.get("refused"))
        return out
    for t in h["hung"]:
        try:
            ok = d.close_target(t["id"])
        except Exception:                                           # noqa: BLE001
            ok = False
        (out["closed"] if ok else out["failed"]).append(t)
    if h["hung"]:
        say(event="hung_tabs_closed", n_pages=h["n_pages"], closed=out["closed"],
            failed=out["failed"])
    return out



# ── the dedicated Chrome's memory: measure, reclaim, recycle ────────────────
#
# 2026-09-29: the dedicated Chrome, hours old and holding tabs an earlier job
# left open, was the largest single holder of memory on the machine while a
# long paper sim ran beside it (the machine's figures live under local_pc/,
# not here). A long-lived browser grows; the repair's free-memory floor could
# then block a gateway restart for as long as that browser held the memory. So the repair
# RECLAIMS what the reader owns (hung tabs, idle tabs, then the dedicated Chrome
# itself, gracefully) and then proceeds -- it never waits on the floor forever.

def _chrome_memory() -> dict:
    """Working set of every process whose command line names the dedicated
    user-data-dir (never the main Chrome)."""
    from backend.services import muratclaw_instance as MI
    udd = MI.user_data_dir().replace("'", "''")
    rows = _powershell_json(
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { "
        "$_.CommandLine -and $_.CommandLine.ToLower().Contains('" + udd.lower() + "') } | "
        "ForEach-Object { $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
        "if ($p) { [pscustomobject]@{pid=$_.ProcessId; ws=$p.WorkingSet64; "
        "pv=$p.PrivateMemorySize64} } } | ConvertTo-Json -Compress")
    procs = [r for r in rows if isinstance(r, dict)]
    # `total_gb` is PRIVATE bytes: summed working sets count shared pages once
    # per process and overstate a many-process browser
    return {"n_procs": len(procs),
            "total_gb": round(sum(float(r.get("pv") or 0) for r in procs) / 2 ** 30, 2),
            "working_set_gb": round(sum(float(r.get("ws") or 0) for r in procs) / 2 ** 30, 2)}


def _open_blank() -> str | None:
    """Open one about:blank page so closing every other tab never closes the
    last window (which would end the browser)."""
    from backend.services import muratclaw_instance as MI
    ver = MI._http_json(f"{MI.cdp_base()}/json/version")
    r = _cdp_call(str(ver.get("webSocketDebuggerUrl") or ""), "Target.createTarget",
                  {"url": "about:blank"}, timeout=10.0)
    return (r.get("result") or {}).get("targetId")


def _browser_close() -> bool:
    """`Browser.close` on the PROVEN dedicated Chrome: a graceful exit that
    lets it write its profile (cookies / sign-ins survive)."""
    from backend.services import muratclaw_instance as MI
    ver = MI._http_json(f"{MI.cdp_base()}/json/version")
    try:
        _cdp_call(str(ver.get("webSocketDebuggerUrl") or ""), "Browser.close", {}, timeout=10.0)
    except Exception:                                               # noqa: BLE001
        pass                     # the socket closes as the browser exits: expected
    return True


def _pid_alive(pid: int) -> bool:
    rows = _powershell_json(f"Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue | "
                            f"Select-Object Id | ConvertTo-Json -Compress")
    return any(isinstance(r, dict) and r.get("Id") for r in rows)


@dataclass
class ChromeDeps:
    """Side effects of reclaim / recycle, injectable (tests pass fakes)."""
    prove: Callable[[], dict] = _prove_dedicated
    page_targets: Callable[[], list[dict]] = _page_targets
    close_target: Callable[[str], bool] = _close_target
    open_blank: Callable[[], str | None] = _open_blank
    browser_close: Callable[[], bool] = _browser_close
    pid_alive: Callable[[int], bool] = _pid_alive
    kill_pid: Callable[[int], bool] = _kill_pid
    launch: Callable[[], dict] = None                      # type: ignore[assignment]
    chrome_memory: Callable[[], dict] = _chrome_memory
    free_gb: Callable[[], float | None] = _free_gb
    responsive: Callable[[dict, float], bool] = _page_responsive
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        from backend.services import muratclaw_instance as MI
        if self.launch is None:
            self.launch = MI.launch_attach

    def tabs(self) -> TabDeps:
        return TabDeps(prove=self.prove, page_targets=self.page_targets,
                       responsive=self.responsive, close_target=self.close_target,
                       clock=self.clock)


def close_idle_tabs(own_tab_ids: list[str] | None = None, *, deps: ChromeDeps | None = None,
                    keep_one: bool = True) -> dict:
    """Close the reader's OWN tabs first (`own_tab_ids`), then every other
    page of the dedicated Chrome (called only when no reader runs, so every
    remaining page is idle). With `keep_one`, one about:blank is opened first
    so the browser keeps a window. Proves the instance first; never raises."""
    d = deps or ChromeDeps()
    try:
        d.prove()
        pages = d.page_targets()
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "refused": f"{type(exc).__name__}: {str(exc)[:200]}",
                "closed": [], "order": []}
    own = [str(t) for t in (own_tab_ids or [])]
    ids = [str(p.get("id")) for p in pages]
    order = [t for t in own if t in ids] + [t for t in ids if t not in own]
    blank = None
    if keep_one and order:
        try:
            blank = d.open_blank()
        except Exception:                                           # noqa: BLE001
            blank = None
    closed, failed = [], []
    for t in order:
        if t == blank:
            continue
        try:
            (closed if d.close_target(t) else failed).append(t)
        except Exception:                                           # noqa: BLE001
            failed.append(t)
    return {"ok": True, "closed": closed, "failed": failed, "order": order,
            "own_first": [t for t in own if t in ids], "blank": blank}


def recycle_dedicated_chrome(own_tab_ids: list[str] | None = None, *,
                             deps: ChromeDeps | None = None, why: str = "",
                             exit_wait_s: float = 30.0) -> dict:
    """Restart the DEDICATED Chrome gracefully: prove it; close the reader's
    own tabs first, then the rest; `Browser.close`; wait for its browser PID to
    exit (by that PID only: `taskkill /PID /T` after `exit_wait_s`); launch it
    again with its port (`launch_attach`). Never touches another Chrome and
    never kills by image name. Never raises."""
    d = deps or ChromeDeps()
    out: dict[str, Any] = {"why": why, "steps": []}
    t0 = d.clock()
    try:
        proof = d.prove()
    except Exception as exc:                                        # noqa: BLE001
        out.update(ok=False, refused=f"{type(exc).__name__}: {str(exc)[:200]}")
        return out
    pid = int(proof.get("pid") or 0)
    out["pid_before"] = pid
    try:
        out["mem_before"] = d.chrome_memory()
    except Exception:                                               # noqa: BLE001
        out["mem_before"] = None
    tabs = close_idle_tabs(own_tab_ids, deps=d, keep_one=False)
    out["steps"].append({"step": "close_tabs", "closed": len(tabs.get("closed") or []),
                         "order": tabs.get("order"), "own_first": tabs.get("own_first"),
                         "failed": tabs.get("failed")})
    try:
        d.browser_close()
        out["steps"].append({"step": "browser_close"})
    except Exception as exc:                                        # noqa: BLE001
        out["steps"].append({"step": "browser_close", "error": str(exc)[:160]})
    w0 = d.clock()
    while pid and d.pid_alive(pid) and d.clock() - w0 < exit_wait_s:
        d.sleep(1.0)
    if pid and d.pid_alive(pid):
        out["steps"].append({"step": "kill_browser_pid", "pid": pid, "ok": d.kill_pid(pid)})
    else:
        out["steps"].append({"step": "exited", "seconds": round(d.clock() - w0, 1)})
    try:
        res = d.launch() or {}
        out["steps"].append({"step": "launch_attach", "result": {
            k: res.get(k) for k in ("launched", "why", "pid_started", "seconds_to_port")}})
        out["ok"] = True
    except Exception as exc:                                        # noqa: BLE001
        out["steps"].append({"step": "launch_attach", "error": str(exc)[:200]})
        out["ok"] = False
    out["seconds"] = round(d.clock() - t0, 1)
    return out


def reclaim_memory(*, need_gb: float, own_tab_ids: list[str] | None = None,
                   deps: ChromeDeps | None = None, log: Callable[..., None] | None = None
                   ) -> dict:
    """Free memory the READER owns until `need_gb` is free: hung tabs, then the
    idle tabs of the dedicated Chrome, then a graceful restart of that Chrome.
    Stops at the first step that clears the floor. Never raises, never waits
    beyond the recycle's own bounded exit wait."""
    d = deps or ChromeDeps()
    say = log or (lambda **k: None)
    steps: list[dict] = []

    def free() -> float | None:
        try:
            return d.free_gb()
        except Exception:                                           # noqa: BLE001
            return None

    f0 = free()
    if f0 is not None and f0 >= need_gb:
        return {"ok": True, "free_before": f0, "free_after": f0, "steps": steps}
    h = close_hung_tabs(d.tabs())
    steps.append({"step": "close_hung_tabs", "closed": len(h.get("closed") or []),
                  "free_gb": free()})
    if (steps[-1]["free_gb"] or 0.0) < need_gb:
        c = close_idle_tabs(own_tab_ids, deps=d)
        steps.append({"step": "close_idle_tabs", "closed": len(c.get("closed") or []),
                      "free_gb": free()})
    if (steps[-1]["free_gb"] or 0.0) < need_gb:
        r = recycle_dedicated_chrome(own_tab_ids, deps=d, why="reclaim memory for a repair")
        steps.append({"step": "recycle_dedicated_chrome", "ok": r.get("ok"),
                      "free_gb": free()})
    f1 = steps[-1]["free_gb"]
    out = {"ok": f1 is not None and f1 >= need_gb, "free_before": f0, "free_after": f1,
           "steps": steps}
    say(event="reclaim_memory", **out)
    return out


def chrome_recycle_due(*, age_s: float | None, mem_gb: float | None,
                       free_gb: float | None = None) -> str | None:
    """PURE. Why the dedicated Chrome should be recycled now, or None:
    * older than `READER_CHROME_RECYCLE_S`;
    * holding more than `READER_CHROME_MAX_GB` (private bytes) whatever the
      machine's state;
    * holding more than `READER_CHROME_SOFT_GB` while free RAM is under
      `READER_CHROME_LOW_FREE_GB` (the browser is what squeezes the machine).
    A fresh browser with a full pool already holds several GB, so size alone
    at a low bar would recycle every quarter hour for nothing (measured on the
    first night of this rule)."""
    max_age = float(getattr(_config, "READER_CHROME_RECYCLE_S", 7200.0))
    max_gb = float(getattr(_config, "READER_CHROME_MAX_GB", 8.0))
    soft_gb = float(getattr(_config, "READER_CHROME_SOFT_GB", 4.0))
    low_free = float(getattr(_config, "READER_CHROME_LOW_FREE_GB", 3.0))
    if mem_gb is not None and mem_gb > max_gb:
        return f"MEMORY: the dedicated Chrome holds {mem_gb:.1f} GB > {max_gb:.1f} GB"
    if mem_gb is not None and free_gb is not None and mem_gb > soft_gb and free_gb < low_free:
        return (f"MEMORY_PRESSURE: the dedicated Chrome holds {mem_gb:.1f} GB > "
                f"{soft_gb:.1f} GB with {free_gb:.1f} GB free < {low_free:.1f} GB")
    if age_s is not None and age_s > max_age:
        return f"AGE: {age_s / 3600:.1f} h since the last recycle > {max_age / 3600:.1f} h"
    return None


# ── stale tabs: pages nobody has navigated for a long time (2026-09-29) ──────
#
# The attach launcher's start page stayed open, idle, for the browser's whole
# life; within 14 minutes of a relaunch it was the largest renderer, and an
# earlier job's tabs were left open for hours. The pool's tabs live a minute or
# two. So every few minutes the supervisor closes pages that have not been
# NAVIGATED (performance.timeOrigin) for READER_STALE_TAB_S, except those the
# pool names as its own and about:blank; a page that does not answer is hung
# and is closed too. One about:blank is opened first if nothing else would be
# left, so the browser keeps a window.

def _page_loaded_at(target: dict, timeout: float) -> float | None:
    """Epoch seconds when the page's current document began loading, or None
    when the page does not answer (hung)."""
    try:
        r = _cdp_call(str(target.get("webSocketDebuggerUrl") or ""), "Runtime.evaluate",
                      {"expression": "performance.timeOrigin", "returnByValue": True},
                      timeout=timeout)
        v = ((r.get("result") or {}).get("result") or {}).get("value")
        return float(v) / 1000.0 if v is not None else None
    except Exception:                                               # noqa: BLE001
        return None


def close_stale_tabs(*, keep_ids: list[str] | None = None, max_idle_s: float | None = None,
                     prove: Callable[[], dict] = _prove_dedicated,
                     page_targets: Callable[[], list[dict]] = _page_targets,
                     loaded_at: Callable[[dict, float], float | None] = _page_loaded_at,
                     close_target: Callable[[str], bool] = _close_target,
                     open_blank: Callable[[], str | None] | None = None,
                     now: Callable[[], float] = time.time,
                     timeout_s: float | None = None) -> dict:
    """Close the dedicated Chrome's pages not navigated for `max_idle_s` (and
    hung ones), sparing `keep_ids` and about:blank. Proves first; never raises."""
    idle = float(getattr(_config, "READER_STALE_TAB_S", 1800.0)) if max_idle_s is None \
        else max_idle_s
    to = float(getattr(_config, "READER_HUNG_TAB_TIMEOUT_S", 4.0)) if timeout_s is None \
        else timeout_s
    keep = {str(k) for k in (keep_ids or [])}
    try:
        prove()
        pages = page_targets()
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "refused": f"{type(exc).__name__}: {str(exc)[:200]}",
                "closed": []}
    t = now()
    stale = []
    for p in pages:
        pid, url = str(p.get("id")), str(p.get("url") or "")
        if pid in keep or url.startswith("about:blank"):
            continue
        at = loaded_at(p, to)
        if at is None or t - at >= idle:
            stale.append({"id": pid, "url": url[:160],
                          "idle_s": None if at is None else round(t - at)})
    if stale and len(stale) == len(pages):
        try:
            (open_blank or _open_blank)()
        except Exception:                                           # noqa: BLE001
            pass
    closed = []
    for s in stale:
        try:
            if close_target(s["id"]):
                closed.append(s)
        except Exception:                                           # noqa: BLE001
            pass
    return {"ok": True, "n_pages": len(pages), "closed": closed}
