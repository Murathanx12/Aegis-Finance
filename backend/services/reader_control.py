"""One ON/OFF switch for the web reader, inside the desktop app (CH-22b, 2026-11-11).

Owner, 2026-11-11: "join that controller in the desktop to the exe, no need for
multiple controllers." Until then the reader had a second desktop program,
`AegisReaderControl.exe` (tkinter, Codex era), whose attestation layer refused
with `SOURCE_PREFLIGHT / ACTION_SOURCE_DRIFT` on every run from about 11-08, so
it could no longer start the reader at all. This module is the switch that
replaces it, served by `/api/control/reader*` and the desktop "Reader" page. The
attestation, the logon-id grant and the native-handle code are NOT ported.

HOW THE READER REALLY RUNS (and so what this switch does)
=========================================================
* ON is `scripts.task_keeper.ensure_reader()` -- the same decision and the same
  launcher the scheduled keeper uses (`paused` / `alive` / `cannot_determine` /
  `launch` / `launch_failed`). The launch callable it is handed
  (`launch_from_app`) runs the keeper's own command; it only drops the
  desktop-only environment variables and adds a job-object breakaway flag
  (see `job_binding`).
* OFF writes `dowjones/SUPERVISOR_STOP` with this app's owner tag and kills
  nothing. The supervisor checks it at the top of every 60 s tick
  (`night_reader_supervisor.py` main loop), then asks the pool to finish the page
  in hand and close its tabs (`stop_pool_gracefully`, up to 180 s) and writes
  `state: stopped`. The pool also honours SUPERVISOR_STOP on its own
  (`reader_pool.STOP_FILES`). `READER_POOL_STOP` is NOT written: the supervisor
  uses it for its own repairs and unlinks it afterwards.
* A STOP marker this app did not write (and not the retired controller's exact
  token) is "held by someone else": it is shown, never removed.

WHY A JOB-OBJECT CHECK
======================
The desktop launcher puts the shell -- and so this backend, which runs in the
shell's process -- in a Windows job object with KILL_ON_JOB_CLOSE
(`desktop/launcher.py::_job_object`). A supervisor started from here would
inherit that job and be hard-killed, with its pool and tabs, the moment the
window closes. So ON breaks the child out of the job when the job allows it, and
REFUSES to launch (saying why and what to run instead) when it does not.

`status()` reads files only (no process scan, no PowerShell), so the page can
poll it every 10 s. Article URLs, titles and bodies never leave this module:
pages are reported by HOST only, and URLs inside error text are redacted.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from backend import config as _config

SUPERVISOR_STOP_NAME = "SUPERVISOR_STOP"
POOL_STOP_NAME = "READER_POOL_STOP"
#: the first line of a marker this app writes
OWN_HEADER = "AEGIS_DESKTOP_READER_OFF/1"
OWNER_TAG = "aegis-desktop"
#: the retired AegisReaderControl.exe wrote exactly `<header>\n<32 hex>\n`
LEGACY_HEADER = "AEGIS_READER_CONTROLLER_OFF/1"
#: what `night_reader_supervisor.stop_pool_gracefully` writes into READER_POOL_STOP
SUPERVISOR_REPAIR_TEXT = "stop for a repair or a recycle"

STATE_FILE_NAME = "reader_control_desktop.json"
AUDIT_LOG_NAME = "reader_control_desktop.jsonl"

#: supervisor states (night_reader_supervisor.READING ...) in plain words
STATE_WORDS = {
    "READING": "Reading pages.",
    "STARTING": "Starting: the first pages have not come back yet.",
    "REPAIRING": "Repairing the browser connection.",
    "STALLED": "Stalled: no page came back OK recently; the supervisor is escalating.",
    "WAITING_FOR_CAP": "Waiting: this hour's or today's page budget is spent.",
    "WAITING_FOR_RESOURCES": "Waiting for free memory before opening tabs.",
    "QUEUE_EMPTY": "Nothing left to read right now.",
    "REFILLING": "Refilling its reading queue.",
    "DOWN": "The reader process is down; the supervisor is deciding what to do.",
    "PAUSED": "Paused for the IIF quiet window (16:45-17:05 local).",
}
RUNNING_STATES = frozenset(STATE_WORDS) - {"DOWN"}

_URL = re.compile(r"https?://\S+")
_LOCK = threading.Lock()


# ----------------------------------------------------------------- paths

def dj_dir(root: Path | None = None) -> Path:
    """The reader's folder: `<OPTIMUS_LEDGER_DIR>/dowjones` (the same folder
    `task_keeper.DJ` and `night_reader_supervisor.DJ` resolve)."""
    return Path(root) if root is not None else Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones"


def _fresh_s() -> float:
    return float(getattr(_config, "READER_CONTROL_FRESH_S", 180.0))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def redact(text: object, limit: int = 300) -> Optional[str]:
    """URLs out, length bounded. `None` stays `None`."""
    if text is None:
        return None
    return _URL.sub("[URL_REDACTED]", str(text))[:limit]


def host_of(url: object) -> Optional[str]:
    try:
        h = urlparse(str(url)).hostname
    except ValueError:
        return None
    if not h:
        return None
    return h[4:] if h.startswith("www.") else h


# ----------------------------------------------------------- stamps / files

def stamp_age(raw: object, now: datetime | None = None) -> dict:
    """`{utc, age_s, freshness}` for one stamp. A missing, undateable (naive or
    unparsable) or future stamp is never FRESH."""
    now = now or _now()
    if raw in (None, ""):
        return {"utc": None, "age_s": None, "freshness": "MISSING"}
    try:
        t = datetime.fromisoformat(str(raw))
    except ValueError:
        return {"utc": None, "age_s": None, "freshness": "UNDATEABLE"}
    if t.tzinfo is None:
        return {"utc": None, "age_s": None, "freshness": "UNDATEABLE"}
    age = (now - t).total_seconds()
    out = {"utc": t.astimezone(timezone.utc).isoformat(timespec="seconds"),
           "age_s": round(age, 1)}
    if age < -5.0:
        out["freshness"] = "FUTURE"
    else:
        out["freshness"] = "FRESH" if age <= _fresh_s() else "STALE"
    return out


def _read_json(path: Path, max_bytes: int = 2 * 1024 * 1024) -> tuple[Optional[dict], Optional[str]]:
    try:
        with path.open("rb") as fh:
            raw = fh.read(max_bytes + 1)
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"unreadable: {type(exc).__name__}"
    if len(raw) > max_bytes:
        return None, "too large"
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, "not JSON"
    return (d, None) if isinstance(d, dict) else (None, "not an object")


def _tail_lines(path: Path, n_bytes: int) -> tuple[list[str], bool]:
    """The last `n_bytes` of a file as lines (a cut first line dropped)."""
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        off = max(0, size - n_bytes)
        fh.seek(off)
        lines = fh.read().decode("utf-8", "replace").splitlines()
    if off and lines:
        lines = lines[1:]
    return lines, bool(off)


# ------------------------------------------------------------------ markers

def _legacy_owner(root: Path) -> Optional[str]:
    """The retired controller's `stop_owner` from its `reader_control.json`."""
    d, _ = _read_json(root / "reader_control.json", 64 * 1024)
    owner = (d or {}).get("stop_owner")
    return owner if isinstance(owner, str) and re.fullmatch(r"[0-9a-f]{32}", owner) else None


def marker_info(path: Path, root: Path | None = None) -> dict:
    """Who holds one STOP marker.

    owner: `absent` | `this_app` | `retired_controller` | `supervisor_repair` | `other`.
    `this_app` and `retired_controller` are the only owners ON may remove.
    """
    root = dj_dir(root)
    out: dict[str, Any] = {"name": path.name, "present": False, "owner": "absent",
                           "content": None, "written_utc": None}
    try:
        with path.open("rb") as fh:
            raw = fh.read(4097)
        st = path.stat()
    except FileNotFoundError:
        return out
    except OSError as exc:
        out.update(present=True, owner="other", content=f"unreadable: {type(exc).__name__}")
        return out
    text = raw.decode("utf-8", "replace")
    out.update(present=True,
               written_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc)
               .isoformat(timespec="seconds"),
               content=redact("".join(c if c.isprintable() or c == "\n" else "?"
                                      for c in text), 300))
    lines = text.split("\n")
    if lines[0] == OWN_HEADER and any(ln == f"owner={OWNER_TAG}" for ln in lines[1:]):
        out["owner"] = "this_app"
    elif (len(lines) == 3 and lines[0] == LEGACY_HEADER and lines[2] == ""
          and re.fullmatch(r"[0-9a-f]{32}", lines[1])):
        out["owner"] = "retired_controller"
        legacy = _legacy_owner(root)
        out["owner_matches_retired_control_file"] = (legacy == lines[1]) if legacy else None
    elif text.strip() == SUPERVISOR_REPAIR_TEXT:
        out["owner"] = "supervisor_repair"
    else:
        out["owner"] = "other"
    return out


def own_marker_text(now: datetime | None = None) -> str:
    now = now or _now()
    return (f"{OWN_HEADER}\nowner={OWNER_TAG}\nutc={now.isoformat(timespec='seconds')}\n"
            f"pid={os.getpid()}\n")


def _write_exclusive(path: Path, text: str) -> bool:
    """Create `path` only if absent; False when it already existed."""
    try:
        with path.open("xb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except FileExistsError:
        return False


def _remove_if_owned(path: Path, root: Path) -> dict:
    """Remove a marker only while it is still ours: rename it aside (atomic),
    re-read the renamed copy, and put it back if it is not ours after all."""
    before = marker_info(path, root)
    if before["owner"] not in ("this_app", "retired_controller"):
        return {"name": path.name, "removed": False, "owner": before["owner"]}
    aside = path.with_name(f"{path.name}.{uuid.uuid4().hex}.releasing")
    try:
        os.rename(path, aside)
    except FileNotFoundError:
        return {"name": path.name, "removed": False, "owner": "absent"}
    except OSError as exc:
        return {"name": path.name, "removed": False, "owner": before["owner"],
                "error": f"{type(exc).__name__}: {exc}"[:200]}
    after = marker_info(aside, root)
    if after["owner"] not in ("this_app", "retired_controller"):
        # replaced between the read and the rename: it is someone else's now
        try:
            os.rename(aside, path)
        except OSError:
            pass                       # a newer marker sits there; theirs stays
        return {"name": path.name, "removed": False, "owner": after["owner"]}
    try:
        aside.unlink()
    except OSError:
        pass
    return {"name": path.name, "removed": True, "owner": before["owner"]}


# ------------------------------------------------------------------ readings

def _supervisor_reading(root: Path, now: datetime) -> dict:
    d, err = _read_json(root / "reader_status.json")
    if d is None:
        return {"readable": False, "why": err, "freshness": "MISSING" if err == "missing"
                else "UNDATEABLE"}
    st = stamp_age(d.get("t"), now)
    classes = d.get("classes_60m") if isinstance(d.get("classes_60m"), dict) else {}
    hosts = {}
    for h, row in classes.items():
        if isinstance(row, dict):
            hosts[str(h)] = {str(k): int(v) for k, v in row.items()
                             if isinstance(v, (int, float)) and not isinstance(v, bool)}
    workers = d.get("current_url_by_worker") if isinstance(d.get("current_url_by_worker"), dict) else {}
    pool = d.get("pool") if isinstance(d.get("pool"), dict) else {}
    return {"readable": True, "state": d.get("state"), "stamp": st, "freshness": st["freshness"],
            "pages_ok_10m": d.get("pages_ok_10m"), "pages_ok_60m": d.get("pages_ok_60m"),
            "classes_60m_by_host": hosts,
            "current_hosts": sorted({h for h in (host_of(u) for u in workers.values()) if h}),
            "next_action": redact(d.get("next_action")),
            "last_error": redact(d.get("last_error")),
            "restarts": d.get("restarts"), "free_ram_gb": d.get("free_ram_gb"),
            "free_disk_gb_as_reported": d.get("free_disk_gb"), "mode": d.get("mode"),
            "pool_pid_as_reported": pool.get("pid") if isinstance(pool.get("pid"), int) else None}


def _pool_reading(root: Path, now: datetime) -> dict:
    out: dict[str, Any] = {}
    d, err = _read_json(root / "reader_pool_status.json", 8 * 1024 * 1024)
    if d is None:
        out["status"] = {"readable": False, "why": err, "freshness": "MISSING"}
    else:
        st = stamp_age(d.get("t"), now)
        out["status"] = {"readable": True, "stamp": st, "freshness": st["freshness"],
                         "pid_as_reported": d.get("pid") if isinstance(d.get("pid"), int) else None,
                         "state": redact(d.get("state"), 64),
                         "stop_reason": redact(d.get("stop_reason"))}
    d2, err2 = _read_json(root / "reader_pool_startup.json", 64 * 1024)
    if d2 is None:
        out["startup"] = {"readable": False, "why": err2, "freshness": "MISSING"}
    else:
        st2 = stamp_age(d2.get("observed_utc"), now)
        out["startup"] = {"readable": True, "stamp": st2, "freshness": st2["freshness"],
                          "pid_as_reported": d2.get("pid") if isinstance(d2.get("pid"), int) else None,
                          "state": redact(d2.get("state"), 64), "phase": redact(d2.get("phase"), 64)}
    return out


def _supervisor_log_reading(root: Path, now: datetime, n_bytes: int = 256 * 1024) -> dict:
    """The newest `start` event (the supervisor logs its own pid) and anything
    that ended that run after it (`stopping` / `end`)."""
    try:
        lines, _ = _tail_lines(root / "night_reader_supervisor.jsonl", n_bytes)
    except OSError:
        return {"readable": False}
    start, ended = None, None
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        ev = row.get("event")
        if ev == "start":
            start, ended = row, None
        elif ev in ("stopping", "end") and start is not None:
            ended = row
    out: dict[str, Any] = {"readable": True, "start_seen_in_tail": start is not None}
    if start is not None:
        out.update(supervisor_pid_as_logged=start.get("pid") if isinstance(start.get("pid"), int) else None,
                   started=stamp_age(start.get("t"), now), until=redact(start.get("until"), 40))
    if ended is not None:
        out.update(ended=stamp_age(ended.get("t"), now), ended_why=redact(ended.get("why")))
    return out


def page_feedback(root: Path, now: datetime, n_bytes: int | None = None) -> dict:
    """Bounded tail of page_log.jsonl: last OK page time, OK pages per HOST in
    the last 10 / 60 minutes. Never a URL, a title or a body."""
    n_bytes = int(n_bytes or getattr(_config, "READER_CONTROL_PAGE_TAIL_BYTES", 512 * 1024))
    try:
        lines, cut = _tail_lines(root / "page_log.jsonl", n_bytes)
    except OSError:
        return {"readable": False, "last_ok": stamp_age(None, now)}
    last_ok: Optional[datetime] = None
    ok10: dict[str, int] = {}
    ok60: dict[str, int] = {}
    invalid = 0
    for ln in lines:
        try:
            row = json.loads(ln)
            if not isinstance(row, dict):
                raise ValueError
            t = datetime.fromisoformat(str(row["t"]))
            if t.tzinfo is None:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            invalid += 1
            continue
        if row.get("class") != "OK":
            continue
        if t > now + timedelta(seconds=5):
            invalid += 1            # a future page is not evidence of a page
            continue
        last_ok = t if last_ok is None or t > last_ok else last_ok
        h = str(row.get("host") or host_of(row.get("url")) or "?")
        age = (now - t).total_seconds()
        if age <= 3600:
            ok60[h] = ok60.get(h, 0) + 1
            if age <= 600:
                ok10[h] = ok10.get(h, 0) + 1
    return {"readable": True, "last_ok": stamp_age(last_ok.isoformat() if last_ok else None, now),
            "ok_10m": sum(ok10.values()), "ok_60m": sum(ok60.values()),
            "ok_60m_by_host": dict(sorted(ok60.items(), key=lambda kv: -kv[1])),
            "invalid_rows": invalid, "tail_bytes": n_bytes, "tail_was_cut": cut,
            "evidence": "saved page log (bounded tail), not a heartbeat"}


def _port_answers(host: str, port: int) -> Optional[bool]:
    try:
        from backend.services import gateway_repair as GR
        return bool(GR._port_open(host, port, timeout=1.0))
    except Exception:  # noqa: BLE001 -- unknown, not "down"
        return None


def gateway_reading(port_check: Callable[[str, int], Optional[bool]] | None = None) -> dict:
    check = port_check or _port_answers
    host = str(getattr(_config, "OPENCLAW_GATEWAY_HOST", "127.0.0.1"))
    port = int(getattr(_config, "OPENCLAW_GATEWAY_PORT", 18789))
    out: dict[str, Any] = {"gateway": {"host": host, "port": port, "answers": check(host, port)}}
    try:
        from backend.services import muratclaw_instance as MI
        out["chrome"] = {"host": MI.host(), "port": MI.port(),
                         "answers": check(MI.host(), MI.port())}
    except Exception as exc:  # noqa: BLE001
        out["chrome"] = {"answers": None, "why": f"{type(exc).__name__}"}
    return out


def disk_reading(root: Path) -> dict:
    """Free disk where the reader writes, beside the floor the supervisor stops at."""
    try:
        from scripts import night_reader_supervisor as NRS
        floor: Optional[float] = float(NRS.DISK_FLOOR_GB)
    except Exception:  # noqa: BLE001
        floor = None
    try:
        probe = root if root.exists() else root.parent
        free = round(shutil.disk_usage(str(probe)).free / 1e9, 1)
    except OSError:
        free = None
    return {"free_gb": free, "floor_gb": floor,
            "below_floor": (free < floor) if (free is not None and floor is not None) else None}


def iif_quiet(now_local: datetime | None = None) -> Optional[bool]:
    """The existing IIF quiet window, reused: `task_keeper.reader_iif_quiet`
    where the keeper has it (the runtime's copy does), else the supervisor's own
    `night_reader_supervisor.reader_iif_quiet` (main). None = cannot tell."""
    fn = None
    for mod in ("scripts.task_keeper", "scripts.night_reader_supervisor"):
        try:
            fn = getattr(__import__(mod, fromlist=["reader_iif_quiet"]), "reader_iif_quiet", None)
        except Exception:  # noqa: BLE001
            fn = None
        if fn is not None:
            break
    if fn is None:
        return None
    return bool(fn(now_local or datetime.now()))


# ------------------------------------------------------------------ actual

def derive_actual(desired: str, sup: dict) -> tuple[str, str]:
    """PURE. (actual_state, plain words) from the desired state and the
    supervisor's own status reading."""
    if not sup.get("readable"):
        return "UNKNOWN", "No readable reader status file: the reader's state cannot be determined."
    state = str(sup.get("state") or "").upper()
    fresh = sup.get("freshness")
    age = (sup.get("stamp") or {}).get("age_s")
    if state == "STOPPED":
        why = sup.get("next_action") or ""
        return "STOPPED", f"Stopped{_ago(age)}. {why}".strip()
    if fresh in ("UNDATEABLE", "FUTURE", "MISSING"):
        return "UNKNOWN", f"The reader status carries a {str(fresh).lower()} stamp, so it is not trusted."
    if fresh != "FRESH":
        return ("NOT_REPORTING",
                f"The supervisor last reported{_ago(age)} (as {state or 'nothing'}): it is not "
                "running, or it is hung.")
    if desired == "OFF":
        return ("STOP_REQUESTED",
                "Stop requested. The supervisor stops at its next tick (within about a minute), "
                "lets the pool finish its page and close its tabs (up to 3 minutes), then exits.")
    return state or "UNKNOWN", STATE_WORDS.get(state, f"Reported state: {state or 'none'}.")


def _ago(age_s: object) -> str:
    if not isinstance(age_s, (int, float)):
        return ""
    a = max(0.0, float(age_s))
    if a < 90:
        return f" {a:.0f} s ago"
    if a < 5400:
        return f" {a / 60:.0f} min ago"
    return f" {a / 3600:.1f} h ago"


def what_will_happen(s: dict) -> str:
    """PURE. The sentence under the switch."""
    stop = s["stop_marker"]
    parts: list[str] = []
    if s["desired"] == "ON":
        if s["actual"] in RUNNING_STATES:
            parts.append("Switching OFF writes SUPERVISOR_STOP. The supervisor stops by itself within "
                         "about a minute, the pool finishes the page in hand and closes its tabs "
                         "(up to 3 minutes). This app kills nothing.")
        else:
            parts.append("The reader is meant to be ON but is not reporting as running. Press ON to "
                         "check for a live supervisor and start one only if none is alive.")
    elif stop["owner"] in ("this_app", "retired_controller"):
        parts.append("Switching ON removes this app's pause and starts the supervisor if none is "
                     "alive; it opens the dedicated Chrome through the OpenClaw gateway and reads.")
    else:
        parts.append("Paused by a SUPERVISOR_STOP this app did not write (shown below). It will not "
                     "be removed from here; delete the file by hand if that pause is over.")
    if s.get("handoff_present") is False:
        parts.append("HANDOFF_PC is absent, so a supervisor would exit at once.")
    if s.get("iif_quiet_now"):
        parts.append("Inside the IIF quiet window (16:45-17:05 local) ON starts nothing; press it "
                     "again after 17:05.")
    if (s.get("disk") or {}).get("below_floor"):
        parts.append("Free disk is under the supervisor's floor, so it would stop at once.")
    return " ".join(parts)


def status(root: Path | None = None, *, now: datetime | None = None,
           port_check: Callable[[str, int], Optional[bool]] | None = None,
           quiet: Optional[bool] = None) -> dict:
    """Everything the switch shows, from files only (no process scan)."""
    root = dj_dir(root)
    now = now or _now()
    stop = marker_info(root / SUPERVISOR_STOP_NAME, root)
    pool_stop = marker_info(root / POOL_STOP_NAME, root)
    desired = "OFF" if stop["present"] else "ON"
    sup = _supervisor_reading(root, now)
    actual, words = derive_actual(desired, sup)
    retired, _ = _read_json(root / "reader_controller_status.json", 256 * 1024)
    s: dict[str, Any] = {
        "utc": now.isoformat(timespec="seconds"),
        "desired": desired, "actual": actual, "actual_words": words,
        "stop_marker": stop, "pool_stop_marker": pool_stop,
        "supervisor": sup, "supervisor_log": _supervisor_log_reading(root, now),
        "pool": _pool_reading(root, now), "pages": page_feedback(root, now),
        "disk": disk_reading(root), **gateway_reading(port_check),
        "handoff_present": (root.parent / "HANDOFF_PC").exists(),
        "iif_quiet_now": iif_quiet() if quiet is None else quiet,
        "last_launch_by_this_app": _read_json(root / STATE_FILE_NAME, 64 * 1024)[0],
        "retired_controller": ({"actual_state": redact(retired.get("actual_state"), 64),
                                "observed": stamp_age(retired.get("observed_utc"), now),
                                "last_error": redact(retired.get("last_error"))}
                               if retired else None),
        "fresh_limit_s": _fresh_s(),
    }
    s["what_will_happen"] = what_will_happen(s)
    return s


# ------------------------------------------------------------------ actions

def _audit(root: Path, row: dict) -> None:
    try:
        with (root / AUDIT_LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _now().isoformat(timespec="seconds"), **row},
                                default=str) + "\n")
    except OSError:
        pass


def turn_off(root: Path | None = None, *, now: datetime | None = None,
             port_check: Callable[[str, int], Optional[bool]] | None = None) -> dict:
    """Write SUPERVISOR_STOP (this app's tag). Kills nothing.

    result: `STOP_REQUESTED` (written now, or ours already there and the
    supervisor still reporting) | `STOPPED` (the status already says stopped) |
    `HELD_BY_OTHER` (someone else's marker is there; nothing written).
    """
    root = dj_dir(root)
    stop = root / SUPERVISOR_STOP_NAME
    if not root.is_dir():
        return {"ok": False, "result": "CANNOT_DETERMINE", "http": 503,
                "detail": f"the reader folder {root} does not exist"}
    wrote = _write_exclusive(stop, own_marker_text(now))
    m = marker_info(stop, root)
    s = status(root, now=now, port_check=port_check)
    if m["owner"] in ("this_app", "retired_controller"):
        result = "STOPPED" if s["actual"] == "STOPPED" else "STOP_REQUESTED"
        detail = ("SUPERVISOR_STOP written. " if wrote else "This app's SUPERVISOR_STOP was already "
                  "there. ") + ("The status already says stopped." if result == "STOPPED" else
                                "The supervisor stops by itself; this page shows STOP_REQUESTED "
                                "until its status says stopped.")
    else:
        result = "HELD_BY_OTHER"
        detail = ("A SUPERVISOR_STOP that this app did not write is already there, so the reader "
                  "is already paused; nothing was written.")
    _audit(root, {"action": "off", "result": result, "wrote": wrote, "marker_owner": m["owner"]})
    return {"ok": True, "result": result, "wrote_marker": wrote, "detail": detail, "http": 200,
            "status": s}


def job_binding() -> dict:
    """Is THIS process in a Windows job that kills its children when it closes,
    and may a child break away? Read with IsProcessInJob +
    QueryInformationJobObject(NULL) -- the immediate job of this process."""
    if sys.platform != "win32":
        return {"in_job": False, "how": "not Windows"}
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
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class _EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.BOOL)]
        k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                  wintypes.DWORD, ctypes.c_void_p]
        res = wintypes.BOOL()
        if not k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(res)):
            return {"in_job": None, "how": "IsProcessInJob failed"}
        if not res.value:
            return {"in_job": False, "how": "IsProcessInJob"}
        info = _EXT()
        if not k32.QueryInformationJobObject(None, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            return {"in_job": True, "limit_flags": None, "how": "QueryInformationJobObject failed"}
        f = int(info.BasicLimitInformation.LimitFlags)
        return {"in_job": True, "limit_flags": f, "kill_on_close": bool(f & 0x2000),
                "breakaway_ok": bool(f & 0x800), "silent_breakaway_ok": bool(f & 0x1000),
                "how": "QueryInformationJobObject"}
    except Exception as exc:  # noqa: BLE001
        return {"in_job": None, "how": f"{type(exc).__name__}: {exc}"[:200]}


#: CREATE_BREAKAWAY_FROM_JOB
BREAKAWAY_FLAG = 0x01000000


def launch_mode(job: dict) -> tuple[str, str]:
    """PURE. How ON may start a supervisor from this process:
    `plain` (task_keeper.launch_supervisor as is) / `breakaway` / `refuse`."""
    if job.get("in_job") is False:
        return "plain", "this process is in no job object"
    if job.get("in_job") is None or job.get("limit_flags") is None:
        return "refuse", f"cannot read this process's job object ({job.get('how')})"
    if job.get("silent_breakaway_ok"):
        return "plain", "the job lets every child break away silently"
    if job.get("breakaway_ok"):
        return "breakaway", "the job allows CREATE_BREAKAWAY_FROM_JOB"
    if not job.get("kill_on_close"):
        return "plain", "the job does not kill its children when it closes"
    return "refuse", ("this app runs inside a job object that kills its children when the window "
                      "closes and does not allow breakaway, so a reader started from here would be "
                      "hard-killed (pool and tabs included) when the app closes")


#: set by `desktop/aegis_desktop.start_backend` for THIS process only; the
#: reader must start with the environment the scheduled keeper gives it
DESKTOP_ONLY_ENV = ("AEGIS_DESKTOP", "AEGIS_CONTROL_ENABLED", "AEGIS_DESKTOP_BUILD",
                    "AEGIS_DESKTOP_SCHEDULER")


def child_env(base: dict | None = None) -> dict:
    """PURE. The environment a reader started from the app gets."""
    env = dict(os.environ if base is None else base)
    for k in DESKTOP_ONLY_ENV:
        env.pop(k, None)
    return env


def launch_from_app(until: str, log_path: Path, *, breakaway: bool = False) -> int:
    """`task_keeper.launch_supervisor` with two differences and no others:
    the desktop-only variables are dropped from the child's environment, and,
    when the app's job allows it, CREATE_BREAKAWAY_FROM_JOB so the reader
    outlives the window. Same argv (`TK.supervisor_argv`), same cwd, same log
    and stdin handling (`TK.spawn_logged`) -- it is the keeper's launcher, not
    a second one."""
    from scripts import task_keeper as TK

    def popen(argv, **kw):
        kw["env"] = child_env()
        if breakaway and sys.platform == "win32":
            kw["creationflags"] = int(kw.get("creationflags") or 0) | BREAKAWAY_FLAG
        return subprocess.Popen(argv, **kw)

    return TK.spawn_logged(TK.supervisor_argv(until), log_path, popen=popen)


#: decision -> HTTP status for the router
HTTP_FOR_ACTION = {"launch": 200, "alive": 200, "starting": 200, "iif_quiet": 200,
                   "held": 409, "busy": 409, "paused": 409, "refused_bound_to_app": 409,
                   "cannot_determine": 503, "launch_failed": 500}


def turn_on(root: Path | None = None, *, ensure: Callable[..., dict] | None = None,
            job_probe: Callable[[], dict] | None = None,
            quiet_fn: Callable[[], Optional[bool]] | None = None,
            now: datetime | None = None,
            port_check: Callable[[str, int], Optional[bool]] | None = None) -> dict:
    """Remove the pause this app (or the retired controller) owns, then
    `task_keeper.ensure_reader()`. Returns its decision row plus what was done."""
    root = dj_dir(root)
    if not _LOCK.acquire(timeout=5.0):
        return _on_result(root, "busy", "another ON is still running", {}, [], now, port_check)
    try:
        if not root.is_dir():
            return _on_result(root, "cannot_determine", f"the reader folder {root} does not exist",
                              {}, [], now, port_check)
        stop = marker_info(root / SUPERVISOR_STOP_NAME, root)
        if stop["owner"] not in ("absent", "this_app", "retired_controller"):
            return _on_result(root, "held", "SUPERVISOR_STOP is held by someone else; it was not "
                              "touched", {}, [], now, port_check)
        removed = [_remove_if_owned(root / SUPERVISOR_STOP_NAME, root)] if stop["present"] else []
        pool_stop = marker_info(root / POOL_STOP_NAME, root)
        if pool_stop["owner"] == "retired_controller":          # it wrote both markers
            removed.append(_remove_if_owned(root / POOL_STOP_NAME, root))
        if any(r.get("owner") not in ("this_app", "retired_controller", "absent") and not r["removed"]
               for r in removed):
            return _on_result(root, "held", "a STOP marker changed hands while ON ran; it was left",
                              {}, removed, now, port_check)
        q = (quiet_fn or iif_quiet)()
        if q:
            return _on_result(root, "iif_quiet", "inside the IIF quiet window (16:45-17:05 local) "
                              "nothing is started", {}, removed, now, port_check)
        last, _ = _read_json(root / STATE_FILE_NAME, 64 * 1024)
        cooldown = float(getattr(_config, "READER_CONTROL_LAUNCH_COOLDOWN_S", 120.0))
        when = stamp_age((last or {}).get("launched_utc"), now)
        if when["freshness"] in ("FRESH", "STALE") and (when["age_s"] or 0) < cooldown:
            return _on_result(root, "starting", f"this app started a supervisor {when['age_s']:.0f} s "
                              "ago; not launching a second one", {"launched_pid": last.get("pid")},
                              removed, now, port_check)
        from scripts import task_keeper as TK
        job = (job_probe or job_binding)()
        mode, why_mode = launch_mode(job)
        ensure = ensure or TK.ensure_reader
        if mode == "refuse":
            d = ensure(dry_run=True)
            if d.get("action") == "launch":
                d = {**d, "action": "refused_bound_to_app" if job.get("in_job") else "cannot_determine",
                     "why": why_mode + ". Start it outside the app: python -m scripts.task_keeper reader"}
        else:
            d = ensure(launch=functools.partial(launch_from_app, breakaway=mode == "breakaway"))
        if d.get("action") == "paused" and "IIF" in str(d.get("why") or ""):
            d = {**d, "action": "iif_quiet"}       # a keeper that checks the window itself
        d = {**d, "launch_mode": mode, "launch_mode_why": why_mode, "job_object": job}
        if d.get("action") == "launch" and d.get("launched_pid"):
            _write_state(root, {"launched_utc": _now().isoformat(timespec="seconds"),
                                "pid": d.get("launched_pid"), "mode": mode,
                                "supervisor_log": d.get("supervisor_log")})
        return _on_result(root, str(d.get("action")), str(d.get("why") or ""), d, removed, now,
                          port_check)
    finally:
        _LOCK.release()


def _write_state(root: Path, row: dict) -> None:
    p = root / STATE_FILE_NAME
    tmp = p.with_name(f"{p.name}.{uuid.uuid4().hex}.writing")
    try:
        tmp.write_text(json.dumps(row, default=str), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _on_result(root: Path, action: str, why: str, decision: dict, removed: list[dict],
               now: datetime | None, port_check) -> dict:
    http = HTTP_FOR_ACTION.get(action, 500)
    _audit(root, {"action": "on", "result": action, "why": why[:300],
                  "removed": [r.get("name") for r in removed if r.get("removed")],
                  "launched_pid": decision.get("launched_pid")})
    try:
        s = status(root, now=now, port_check=port_check) if root.is_dir() else None
    except Exception as exc:  # noqa: BLE001 -- the action's own answer still goes back
        s = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"ok": http == 200, "action": action, "http": http, "detail": why,
            "decision": decision, "markers_removed": removed, "status": s}
