"""Prove the attached browser is the DEDICATED MuratClaw Chrome, or refuse.

Murat, 2026-09-28: "configure to only murat claw like as if its controlling my
pc". Twice before, a page opened in his MAIN Chrome account. The marker-tab rule
(`dowjones_pull.PARENT_MARKER`) was the defence while OpenClaw attached to the
WHOLE running Chrome; with a dedicated instance the question becomes "is the
browser behind this endpoint the dedicated one?", and it is answered from both
sides before any action:

1. CONFIG: `openclaw.json` points the dedicated profile at
   `http://127.0.0.1:<port>` with `attachOnly`, and no profile is an
   `existing-session` or `extension` driver (those reach the main Chrome), and
   `user` / `chrome` are redefined (else OpenClaw's built-ins apply).
2. ENDPOINT: `GET /json/version` answers on 127.0.0.1:<port> (loopback only).
3. CHROME'S WORD: `SystemInfo.getProcessInfo` over that endpoint's browser
   websocket names the BROWSER process id. (`Browser.getBrowserCommandLine` is
   refused without --enable-automation, measured 2026-09-28; this is not.)
4. THE OS'S WORD: that PID is chrome.exe and its command line carries
   `--user-data-dir=<dedicated dir>` AND `--remote-debugging-port=<port>`.
5. THE SOCKET: the listener on 127.0.0.1:<port> is that same PID.
6. THE TAB: a tab about to be acted on is listed by `/json/list` of THIS
   endpoint (a CDP target id is a random 128-bit id, unique to one browser).

Steps 3-5 cost a websocket round trip and two PowerShell calls, so they are
cached per browser websocket GUID (Chrome issues a new one at every start);
steps 1, 2 and 6 run on every call (a few milliseconds on loopback).

Nothing here kills or restarts the MAIN Chrome. `launch_attach()` starts the
dedicated folder with its port only when no process holds that folder; a
process holding it WITHOUT the port refuses by name (a second launch would hand
the flags to the running instance and they would be ignored).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend import config as _config

CREATE_NO_WINDOW = 0x08000000


class InstanceNotProven(RuntimeError):
    """The attached browser could not be proven to be the dedicated Chrome."""


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def port() -> int:
    return int(_cfg("OPENCLAW_DEDICATED_CDP_PORT", 18802))


def host() -> str:
    return str(_cfg("OPENCLAW_DEDICATED_CDP_HOST", "127.0.0.1"))


def user_data_dir() -> str:
    return str(_cfg("OPENCLAW_DEDICATED_USER_DATA_DIR", str(Path.home() / "ChromeMuratClaw")))


def cdp_base() -> str:
    return f"http://{host()}:{port()}"


_LOOPBACK = ("127.0.0.1", "localhost", "::1")


# ── default probes (replaced by fakes in tests) ──────────────────────────────

def _http_json(url: str, timeout: float = 3.0) -> Any:
    h = re.match(r"^https?://\[?([^\]/:]+)", url or "")
    if not h or h.group(1) not in _LOOPBACK:
        raise InstanceNotProven(f"REFUSED_NOT_LOOPBACK: {url!r} -- the instance probe talks "
                                f"to loopback only")
    with urllib.request.urlopen(url, timeout=timeout) as r:            # noqa: S310
        return json.loads(r.read().decode("utf-8", "replace"))


def _ws_browser_pid(ws_url: str, timeout: float = 5.0) -> int | None:
    import websocket  # websocket-client, in the venv
    if not re.match(r"^ws://(127\.0\.0\.1|localhost)[:/]", ws_url or ""):
        raise InstanceNotProven(f"REFUSED_NOT_LOOPBACK: {ws_url!r}")
    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "SystemInfo.getProcessInfo", "params": {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                for p in (msg.get("result") or {}).get("processInfo") or []:
                    if p.get("type") == "browser":
                        return int(p.get("id"))
                return None
    finally:
        ws.close()
    return None


def _powershell(cmd: str, timeout: float = 30.0) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, timeout=timeout, stdin=subprocess.DEVNULL, shell=False,
                       creationflags=CREATE_NO_WINDOW)
    return r.stdout or ""


def _ts(v: Any) -> str:
    """PowerShell's `/Date(<ms>)/` -> ISO local time; anything else as given."""
    m = re.search(r"/Date\((\d+)", str(v or ""))
    if not m:
        return str(v or "")
    from datetime import datetime
    return datetime.fromtimestamp(int(m.group(1)) / 1000.0).astimezone().isoformat(
        timespec="seconds")


def _process(pid: int) -> dict | None:
    out = _powershell(f"Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\" | "
                      f"Select-Object ProcessId,Name,CommandLine,CreationDate | "
                      f"ConvertTo-Json -Compress")
    try:
        d = json.loads(out) if out.strip() else None
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    return {"pid": int(d.get("ProcessId") or 0), "name": d.get("Name") or "",
            "cmdline": d.get("CommandLine") or "", "created": _ts(d.get("CreationDate"))}


def _listener(p: int) -> int | None:
    out = _powershell(f"(Get-NetTCPConnection -State Listen -LocalPort {int(p)} "
                      f"-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess")
    s = out.strip()
    return int(s) if s.isdigit() else None


def _chrome_browser_processes() -> list[dict]:
    """Every chrome.exe BROWSER process (no --type=): pid, created, cmdline."""
    out = _powershell("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                      "Where-Object { $_.CommandLine -notmatch '--type=' } | "
                      "Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress")
    try:
        d = json.loads(out) if out.strip() else []
    except ValueError:
        return []
    rows = d if isinstance(d, list) else [d]
    return [{"pid": int(r.get("ProcessId") or 0), "cmdline": r.get("CommandLine") or "",
             "created": _ts(r.get("CreationDate"))} for r in rows if isinstance(r, dict)]


def _read_openclaw_config() -> dict:
    p = Path(_cfg("OPENCLAW_CONFIG_PATH", Path.home() / ".openclaw" / "openclaw.json"))
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class Probes:
    """Every side effect the prover has, injectable. Tests pass fakes."""
    http_json: Callable[[str], Any] = _http_json
    ws_browser_pid: Callable[[str], int | None] = _ws_browser_pid
    process: Callable[[int], dict | None] = _process
    listener: Callable[[int], int | None] = _listener
    read_config: Callable[[], dict] = _read_openclaw_config
    chrome_processes: Callable[[], list[dict]] = _chrome_browser_processes


PROBES = Probes()


# ── the proof ────────────────────────────────────────────────────────────────

def _norm_dir(s: str) -> str:
    return str(s or "").strip().strip('"').rstrip("\\/").replace("/", "\\").lower()


def cmdline_user_data_dir(cmdline: str) -> str | None:
    m = re.search(r'--user-data-dir=("([^"]+)"|(\S+))', cmdline or "")
    return (m.group(2) or m.group(3)) if m else None


def cmdline_port(cmdline: str) -> int | None:
    m = re.search(r"--remote-debugging-port=(\d+)", cmdline or "")
    return int(m.group(1)) if m else None


def is_dedicated_cmdline(cmdline: str, *, want_port: int | None = None) -> bool:
    d = cmdline_user_data_dir(cmdline)
    if d is None or _norm_dir(d) != _norm_dir(user_data_dir()):
        return False
    return want_port is None or cmdline_port(cmdline) == int(want_port)


def config_problems(cfg: dict, *, profile: str = "muratclaw") -> list[str]:
    """What in `openclaw.json` would let a browser verb reach anything but the
    dedicated Chrome. Empty list = the config is confined."""
    out: list[str] = []
    b = (cfg or {}).get("browser") or {}
    profs = b.get("profiles") or {}
    want = f"http://{host()}:{port()}"
    mine = profs.get(profile) or {}
    if str(mine.get("cdpUrl") or "").rstrip("/") != want:
        out.append(f"profiles.{profile}.cdpUrl is {mine.get('cdpUrl')!r}, not {want!r}")
    if mine.get("attachOnly") is not True:
        out.append(f"profiles.{profile}.attachOnly is not true (OpenClaw could launch its own)")
    if mine.get("driver") not in (None, "openclaw"):
        out.append(f"profiles.{profile}.driver is {mine.get('driver')!r}")
    for name, p in profs.items():
        if isinstance(p, dict) and p.get("driver") in ("existing-session", "extension"):
            out.append(f"profiles.{name} uses driver {p.get('driver')!r}, which attaches "
                       f"to a running Chrome (the main one)")
        if name != profile and isinstance(p, dict) \
                and str(p.get("cdpUrl") or "").rstrip("/") == want:
            out.append(f"profiles.{name} also points at the dedicated endpoint")
    for builtin in ("user", "chrome"):
        if builtin not in profs:
            out.append(f"profiles.{builtin} is not redefined, so OpenClaw's built-in "
                       f"{'existing-session' if builtin == 'user' else 'extension'} "
                       f"profile applies")
    if b.get("defaultProfile") not in (None, profile):
        out.append(f"browser.defaultProfile is {b.get('defaultProfile')!r}, not {profile!r}")
    return out


#: ws GUID -> the cached OS-side proof (steps 3-5).
_PID_PROOF: dict[str, dict] = {}
#: How long a cached OS-side proof is trusted even with an unchanged GUID.
PID_PROOF_TTL_S = 600.0
_clock = time.monotonic


def reset_cache() -> None:
    _PID_PROOF.clear()


def _refuse(code: str, msg: str) -> InstanceNotProven:
    return InstanceNotProven(f"{code}: {msg}")


def prove(*, target_id: str | None = None, profile: str = "muratclaw",
          probes: Probes | None = None) -> dict:
    """The six-step proof (module docstring). Returns the proof dict; raises
    `InstanceNotProven` with a named code on the first step that fails."""
    pr = probes or PROBES
    t0 = time.monotonic()
    try:
        cfg = pr.read_config()
    except (OSError, ValueError) as exc:
        raise _refuse("REFUSED_INSTANCE_CONFIG_UNREADABLE", f"{type(exc).__name__}: {exc}")
    probs = config_problems(cfg, profile=profile)
    if probs:
        raise _refuse("REFUSED_INSTANCE_CONFIG", "; ".join(probs))
    try:
        ver = pr.http_json(f"{cdp_base()}/json/version")
    except InstanceNotProven:
        raise
    except Exception as exc:                                        # noqa: BLE001
        raise _refuse("REFUSED_INSTANCE_DOWN",
                      f"{cdp_base()}/json/version did not answer ({type(exc).__name__}: "
                      f"{str(exc)[:120]}); the dedicated Chrome is not running with its port")
    ws = str((ver or {}).get("webSocketDebuggerUrl") or "")
    m = re.match(r"^ws://(127\.0\.0\.1|localhost):(\d+)/devtools/browser/([0-9a-f-]{36})$", ws)
    if not m or int(m.group(2)) != port():
        raise _refuse("REFUSED_INSTANCE_ENDPOINT", f"webSocketDebuggerUrl {ws!r} is not a "
                                                   f"loopback browser endpoint on {port()}")
    guid = m.group(3)
    hit = _PID_PROOF.get(guid)
    if hit is None or _clock() - hit["at"] >= PID_PROOF_TTL_S:
        try:
            pid = pr.ws_browser_pid(ws)
        except InstanceNotProven:
            raise
        except Exception as exc:                                    # noqa: BLE001
            raise _refuse("REFUSED_INSTANCE_PID", f"SystemInfo.getProcessInfo failed "
                                                  f"({type(exc).__name__}: {str(exc)[:120]})")
        if not pid:
            raise _refuse("REFUSED_INSTANCE_PID", "Chrome named no browser process")
        proc = pr.process(pid)
        if not proc or str(proc.get("name") or "").lower() != "chrome.exe":
            raise _refuse("REFUSED_INSTANCE_PROCESS", f"browser pid {pid} is "
                                                      f"{(proc or {}).get('name')!r}, not chrome.exe")
        if not is_dedicated_cmdline(proc.get("cmdline") or "", want_port=port()):
            raise _refuse("REFUSED_NOT_MURATCLAW_INSTANCE",
                          f"browser pid {pid}'s command line does not carry "
                          f"--user-data-dir={user_data_dir()} and --remote-debugging-port="
                          f"{port()}: this endpoint is NOT the dedicated Chrome")
        lpid = pr.listener(port())
        if lpid != pid:
            raise _refuse("REFUSED_INSTANCE_LISTENER", f"port {port()} is held by pid {lpid}, "
                                                       f"Chrome says its browser is pid {pid}")
        hit = {"at": _clock(), "pid": pid, "created": proc.get("created"), "guid": guid}
        _PID_PROOF.clear()                     # one browser at a time: a new GUID replaces
        _PID_PROOF[guid] = hit
        cached = False
    else:
        cached = True
    out = {"ok": True, "endpoint": cdp_base(), "guid": guid, "pid": hit["pid"],
           "created": hit.get("created"), "user_data_dir": user_data_dir(),
           "pid_proof": "cached" if cached else "checked", "target_id": target_id}
    if target_id:
        try:
            listed = pr.http_json(f"{cdp_base()}/json/list")
        except Exception as exc:                                    # noqa: BLE001
            raise _refuse("REFUSED_INSTANCE_DOWN", f"/json/list did not answer ({exc})")
        ids = {str(t.get("id") or "") for t in (listed or []) if isinstance(t, dict)}
        if str(target_id) not in ids:
            raise _refuse("REFUSED_TAB_NOT_IN_INSTANCE",
                          f"tab {target_id!r} is not a target of the dedicated Chrome at "
                          f"{cdp_base()} ({len(ids)} targets there)")
        out["tab_in_instance"] = True
    out["seconds"] = round(time.monotonic() - t0, 4)
    return out


# ── is it running, and start it ──────────────────────────────────────────────

def status(*, probes: Probes | None = None) -> dict:
    """Running / port answering / which processes hold the dedicated folder.
    Never raises; `main_chrome` lists the OTHER Chrome browser processes (pid +
    start time) so a receipt can show they were not touched."""
    pr = probes or PROBES
    out: dict[str, Any] = {"endpoint": cdp_base(), "user_data_dir": user_data_dir()}
    try:
        ver = pr.http_json(f"{cdp_base()}/json/version")
        out["port_answers"] = True
        out["browser"] = (ver or {}).get("Browser")
    except Exception as exc:                                        # noqa: BLE001
        out["port_answers"] = False
        out["port_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    try:
        procs = pr.chrome_processes()
    except Exception as exc:                                        # noqa: BLE001
        procs = []
        out["process_error"] = str(exc)[:120]
    ded = [p for p in procs if is_dedicated_cmdline(p["cmdline"])]
    out["dedicated"] = [{"pid": p["pid"], "created": p["created"],
                         "port": cmdline_port(p["cmdline"])} for p in ded]
    out["main_chrome"] = [{"pid": p["pid"], "created": p["created"]} for p in procs
                          if p not in ded]
    out["running_with_port"] = any(d["port"] == port() for d in out["dedicated"]) \
        and out["port_answers"]
    return out


def attach_argv() -> list[str]:
    """Exactly `scripts/open_muratclaw_chrome_attach.cmd`, as an argv."""
    return [str(_cfg("OPENCLAW_CHROME_EXE",
                     r"C:\Program Files\Google\Chrome\Application\chrome.exe")),
            f"--user-data-dir={user_data_dir()}", f"--remote-debugging-port={port()}",
            f"--remote-debugging-address={host()}", "--no-first-run",
            "https://www.wsj.com/"]


def launch_attach(*, probes: Probes | None = None, popen: Callable[..., Any] | None = None,
                  wait_s: float = 30.0, sleep_fn: Callable[[float], None] = time.sleep,
                  clock: Callable[[], float] = time.monotonic) -> dict:
    """Start the dedicated Chrome WITH its port, if nothing holds the folder.

    * already running with the port -> `{"launched": False, "why": "running"}`;
    * a process holds the folder WITHOUT the port -> REFUSED_INSTANCE_NO_PORT
      (relaunching would hand the flags to it and they would be ignored; the
      owner closes that window or the caller closes it by PID);
    * otherwise start it (no shell, detached) and wait for the port."""
    pr = probes or PROBES
    st = status(probes=pr)
    if st["running_with_port"]:
        return {"launched": False, "why": "running", "status": st}
    if st["dedicated"] and not any(d["port"] == port() for d in st["dedicated"]):
        raise _refuse("REFUSED_INSTANCE_NO_PORT",
                      f"the dedicated folder is held by pid "
                      f"{[d['pid'] for d in st['dedicated']]} without --remote-debugging-port="
                      f"{port()}; close that window, then launch again")
    po = popen or subprocess.Popen
    proc = po(attach_argv(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, shell=False,
              creationflags=CREATE_NO_WINDOW | 0x00000008)          # DETACHED_PROCESS
    t0 = clock()
    while clock() - t0 < wait_s:
        try:
            pr.http_json(f"{cdp_base()}/json/version")
            return {"launched": True, "pid_started": getattr(proc, "pid", None),
                    "seconds_to_port": round(clock() - t0, 2)}
        except Exception:                                           # noqa: BLE001
            sleep_fn(0.3)
    raise _refuse("REFUSED_INSTANCE_DOWN", f"launched, but {cdp_base()} did not answer within "
                                           f"{wait_s:.0f} s")
