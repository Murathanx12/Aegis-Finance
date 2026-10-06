"""Count live python processes by command-line family; never kill anything.

WHY THIS EXISTS (C14, 2026-10-07)
=================================
At 03:30 HKT 590 python processes were alive: 294 Optimus MCP servers and 296
`scripts/openclaw_api_bridge.py`, 2.5 GB of working set, two GB free, a full
test-suite run and two agents' waits killed by memory pressure. Every one of
them was a stdio MCP server the OpenClaw gateway starts for an agent SESSION
(`~/.openclaw/openclaw.json` -> `mcp.servers.{optimus,aegis_api}`), one pair
per `openclaw_client.agent()` turn, and none was ever reaped:
`release_session` ARCHIVED the session, and in OpenClaw 2026.9.5 archiving
(`sessions.patch {archived: true}`) does not retire the session's bundle-MCP
runtime -- only `sessions.delete` / `sessions.abort` / the opt-in idle TTL
(`mcp.sessionIdleTtlMs`, default 0 = keep for the session's lifetime) do. The
release reported success and changed nothing, and no surface counted the
processes, so the first symptom was the machine running out of memory.

So this module counts. One census per probe, LOGICAL instances per family
(a Windows venv `python.exe` is a launcher shim that starts the real
interpreter as its child with the same command line -- that pair counts
once), against the caps in `config.PROCESS_CENSUS_FAMILIES`:

* ``ALIVE``             -- at or under the cap
* ``STALE`` / DEGRADED  -- over the cap
* ``DEAD``              -- over ``PROCESS_CENSUS_DEAD_MULT`` x the cap
* ``UNKNOWN``           -- the process table could not be read (never ALIVE)

Each row prints the parent breakdown (which process spawned them) and the
oldest creation time, which is what the 2026-10-07 diagnosis needed and had to
reconstruct by hand. The census is read-only: it never terminates a process
(CLAUDE.md protocol item 6 -- kill by a PID you recorded, or don't kill).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

#: name prefixes whose command lines the reader fetches (others: name only)
_CMDLINE_NAMES = ("python", "pythonw", "node")


def _cfg(name: str, default: Any) -> Any:
    try:
        from backend import config as C                             # noqa: PLC0415
        return getattr(C, name, default)
    except Exception:                                               # noqa: BLE001
        return default


def families() -> dict[str, tuple[str, int]]:
    return dict(_cfg("PROCESS_CENSUS_FAMILIES", {}))


# ═══════════════════════════════════════════════════════════════ reading

_PS = (
    "$ErrorActionPreference='Stop';"
    "$r=@(Get-CimInstance Win32_Process | ForEach-Object {"
    "$n=[string]$_.Name; $c=$null;"
    "if($n -match '^(python|pythonw|node)'){ $c=[string]$_.CommandLine };"
    "$t=$null; if($_.CreationDate){ $t=$_.CreationDate.ToUniversalTime().ToString('o') };"
    "[pscustomobject]@{pid=[int]$_.ProcessId; ppid=[int]$_.ParentProcessId; name=$n;"
    " created_utc=$t; cmd=$c} });"
    "ConvertTo-Json -InputObject $r -Compress -Depth 3"
)


def read_processes(timeout: Optional[float] = None) -> Optional[list[dict]]:
    """Every process as ``{pid, ppid, name, created_utc, cmd}`` (``cmd`` only
    for python/node). None when the table cannot be read -- the caller reports
    UNKNOWN, never an empty (healthy-looking) census."""
    timeout = float(timeout or _cfg("PROCESS_CENSUS_TIMEOUT_S", 45))
    if os.name != "nt":
        return _read_proc_fs()
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else None


def _read_proc_fs() -> Optional[list[dict]]:
    """Linux/macOS-with-/proc fallback; None where /proc does not exist."""
    root = "/proc"
    if not os.path.isdir(root):
        return None
    boot = None
    out: list[dict] = []
    for d in os.listdir(root):
        if not d.isdigit():
            continue
        try:
            with open(f"{root}/{d}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            with open(f"{root}/{d}/stat", "r", encoding="utf-8", errors="replace") as f:
                stat = f.read()
        except OSError:
            continue
        name = stat[stat.find("(") + 1:stat.rfind(")")]
        rest = stat[stat.rfind(")") + 2:].split()
        ppid = int(rest[1]) if len(rest) > 1 else 0
        created = None
        try:
            if boot is None:
                with open(f"{root}/stat", encoding="utf-8") as f:
                    boot = int(next(l for l in f if l.startswith("btime")).split()[1])
            ticks = int(rest[19])
            created = datetime.fromtimestamp(boot + ticks / os.sysconf("SC_CLK_TCK"),
                                             timezone.utc).isoformat()
        except (OSError, StopIteration, ValueError, IndexError, AttributeError):
            pass
        out.append({"pid": int(d), "ppid": ppid, "name": name, "created_utc": created,
                    "cmd": cmd if name.lower().startswith(_CMDLINE_NAMES) else None})
    return out


# ═══════════════════════════════════════════════════════════════ counting

def _family_of(cmd: Optional[str], fams: dict[str, tuple[str, int]]) -> Optional[str]:
    if not cmd:
        return None
    for fam, (rx, _cap) in fams.items():
        if re.search(rx, cmd, re.I):
            return fam
    return None


def _parent_label(row: Optional[dict]) -> str:
    if row is None:
        return "gone"
    name = str(row.get("name") or "?")
    cmd = str(row.get("cmd") or "").lower()
    if "openclaw" in cmd and " gateway" in cmd:
        return f"{name} (openclaw gateway)"
    if "openclaw" in cmd:
        return f"{name} (openclaw)"
    return name


def _ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        # .NET 'o' carries 7 fractional digits; fromisoformat takes at most 6
        s = re.sub(r"(\.\d{6})\d+", r"\1", s)
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def census(rows: list[dict], fams: Optional[dict[str, tuple[str, int]]] = None,
           *, dead_mult: Optional[float] = None) -> dict[str, dict]:
    """PURE. Per family: logical instances, raw OS processes, cap, verdict,
    oldest creation, parent breakdown.

    A process whose PARENT is in the same family (the venv shim -> interpreter
    pair) is not a second instance; it is counted under ``raw`` only."""
    fams = families() if fams is None else fams
    dead_mult = float(_cfg("PROCESS_CENSUS_DEAD_MULT", 2.0) if dead_mult is None else dead_mult)
    by_pid = {int(r.get("pid") or 0): r for r in rows}
    fam_of = {pid: _family_of(r.get("cmd"), fams) for pid, r in by_pid.items()}
    out: dict[str, dict] = {}
    for fam, (_rx, cap) in fams.items():
        members = [r for pid, r in by_pid.items() if fam_of.get(pid) == fam]
        roots = [r for r in members if fam_of.get(int(r.get("ppid") or 0)) != fam]
        parents: dict[int, int] = {}
        for r in roots:
            pp = int(r.get("ppid") or 0)
            parents[pp] = parents.get(pp, 0) + 1
        top = sorted(parents.items(), key=lambda kv: (-kv[1], kv[0]))
        created = [t for t in (_ts(r.get("created_utc")) for r in roots) if t is not None]
        n = len(roots)
        cap = int(cap)
        if n > dead_mult * cap:
            verdict, state = "DEAD", "DEAD"
        elif n > cap:
            verdict, state = "STALE", "DEGRADED"
        else:
            verdict, state = "ALIVE", None
        out[fam] = {"family": fam, "instances": n, "raw": len(members), "cap": cap,
                    "dead_above": dead_mult * cap, "verdict": verdict, "state": state,
                    "oldest_utc": min(created).isoformat(timespec="seconds") if created else None,
                    "newest_utc": max(created).isoformat(timespec="seconds") if created else None,
                    "parents": [{"ppid": pp, "count": c, "parent": _parent_label(by_pid.get(pp))}
                                for pp, c in top]}
    return out


def render(fam: dict) -> str:
    """One line per family: what a human reads in the health table."""
    head = (f"{fam['family']}: {fam['instances']} live instance(s) "
            f"({fam['raw']} OS process(es)), cap {fam['cap']}, DEAD above "
            f"{fam['dead_above']:g}")
    if fam["state"] == "DEGRADED":
        head = "DEGRADED: " + head
    elif fam["verdict"] == "DEAD":
        head = "DEAD: " + head
    if fam["instances"]:
        par = ", ".join(f"{p['count']} x parent pid {p['ppid']} [{p['parent']}]"
                        for p in fam["parents"][:3])
        head += f"; oldest created {fam['oldest_utc']}; parents: {par}"
    if fam["verdict"] != "ALIVE":
        head += ("; read-only: nothing was terminated -- see "
                 "docs/research_notes/2026-10-07/gateway_process_leak_2026-10-07.md")
    return head


# ═══════════════════════════════════════════════════════════════ the probe

def p_process_census(ctx: Any) -> Any:
    """`system_health` probe, one row per family. The process reader comes
    from ``ctx.process_rows``; a context without one (the unit-test context)
    is UNKNOWN, never a read of the real machine."""
    from backend.services.system_health import ProbeResult, _iso, _unknown  # noqa: PLC0415
    reader = getattr(ctx, "process_rows", None)
    if reader is None:
        return _unknown("no process reader on this context; python processes not counted")
    try:
        rows = reader()
    except Exception as exc:                                        # noqa: BLE001
        return _unknown(f"process reader raised {type(exc).__name__}: {str(exc)[:120]}")
    if rows is None:
        return _unknown("process table unreadable (Win32_Process query failed or timed out); "
                        "python processes not counted")
    fams = families()
    if not fams:
        return _unknown("config.PROCESS_CENSUS_FAMILIES is empty; nothing to count against")
    now = getattr(ctx, "now", None) or datetime.now(timezone.utc)
    c = census(rows, fams)
    proof = (f"Win32_Process (read-only), {len(rows)} process(es) read; logical instance = "
             f"a family member whose parent is not in the same family; caps "
             f"config.PROCESS_CENSUS_FAMILIES")
    out = {}
    for fam, d in c.items():
        out[fam] = ProbeResult(d["verdict"], _iso(now), 0.0, render(d), delta=d["instances"],
                               proof=proof, state=d["state"])
    return out


__all__ = ["census", "families", "p_process_census", "read_processes", "render"]
