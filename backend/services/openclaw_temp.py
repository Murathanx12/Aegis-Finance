"""OpenClaw's `openclaw-plugin-build-*` folders: swept, and measured by a probe.

WHY THIS EXISTS (2026-09-27: C: at 0 bytes free for ~85 minutes)
=================================================================
About 2,400 folders named ``openclaw-plugin-build-XXXXXX`` of ~70 MB each sat in
``%LOCALAPPDATA%\\Temp`` -- roughly 170 GB. Where they come from, read from the
installed CLI (OpenClaw 2026.9.5,
``dist/plugin-generation-artifact-*.mjs::createPluginSourceCapture``):

* When a process loads a plugin that ships as a SOURCE package (here the
  npm-installed ``@openclaw/whatsapp`` channel plugin with ``baileys`` and the
  audio decoders -- ``package-0 .. package-76`` inside every folder), OpenClaw
  copies the plugin's package tree into
  ``fs.mkdtempSync(os.tmpdir() + "/openclaw-plugin-build-")`` so the loaded
  generation cannot change under it, and links the host install in with a
  JUNCTION (``node_modules/openclaw -> <npm>/node_modules/openclaw``).
* The copy is removed only by the plugin instance's ``onModuleDispose`` hook.
  A short-lived CLI process exits without disposing its plugin instances, so
  every process that loaded the plugin left one folder behind.
* There is no environment variable or config key for that directory: it is
  ``os.tmpdir()`` (TEMP/TMP) and nothing else.

The folders stopped appearing at 19:44:56 local on 2026-09-27, when the
WhatsApp plugin was disabled in ``~/.openclaw/openclaw.json``
(``plugins.entries.whatsapp.enabled = false``). A live ``gateway status`` call
through the client afterwards created none. So the source is closed by config;
this module is the guard for the next plugin that does the same.

WHY NOT A PRIVATE TEMP PER CALL
===============================
Pointing the child's TEMP/TMP at a per-call directory removed in ``finally``
would contain the leak, and it was considered and NOT done: OpenClaw keeps its
own temp root at ``os.tmpdir()/openclaw`` on Windows (the CLI's daily log,
``downloads/`` and ``session-archive-read-cache``) and node's compile cache at
``os.tmpdir()/node-compile-cache``. A private TEMP would delete a ``download``
or ``pdf`` result the moment the call returned, and the CLI's own log with it.

WHAT IS HERE
============
* ``sweep_plugin_builds`` -- deletes ONLY directories directly inside the temp
  dir whose name starts with ``openclaw-plugin-build-`` and whose mtime is older
  than the limit. It never follows a symlink or a junction (a top-level link is
  skipped; a link inside a folder is unlinked, its target untouched -- the
  junction to the OpenClaw install is exactly such a link), keeps a folder
  created within ``OPENCLAW_TEMP_PROTECT_WINDOW_S`` after a live OpenClaw node
  process started (the gateway's own loaded plugin copy), tolerates a folder
  that vanishes or is locked, stops at a wall-clock budget, and appends one
  receipt line per sweep.
* ``after_cli_call`` -- what the client calls after every CLI round trip: at
  most one sweep per ``OPENCLAW_TEMP_SWEEP_INTERVAL_S``, on a daemon thread, and
  never raising. ``finally`` does not run on a force-kill, which is why a sweep
  must exist at all.
* ``p_openclaw_temp_builds`` -- the ``system_health`` probe: count always,
  size sampled inside a time box, DEGRADED (verdict STALE) above either
  threshold, UNKNOWN when the temp dir cannot be read.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Union

from backend import config as _config

logger = logging.getLogger(__name__)

PREFIX = "openclaw-plugin-build-"
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

Now = Union[None, float, datetime]


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def receipt_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "openclaw_temp_sweeps.jsonl"


def default_temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def _epoch(now: Now) -> float:
    if now is None:
        return time.time()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.timestamp()
    return float(now)


def _is_link(st: os.stat_result) -> bool:
    """A symlink, a junction, or any other reparse point: never traversed."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE)


def _birth(st: os.stat_result) -> float:
    return float(getattr(st, "st_birthtime", None) or st.st_ctime)


def _unlink_link(path: str) -> None:
    """Remove the link itself (never its target)."""
    try:
        os.unlink(path)
    except (IsADirectoryError, PermissionError):
        os.rmdir(path)            # a junction / directory symlink


def _unlink_file(path: str) -> None:
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)   # read-only file
        os.unlink(path)


def _remove_tree(root: str, deadline: Optional[float] = None) -> int:
    """Delete `root` (a real directory) without following any link.

    Returns the bytes of regular files removed. Raises ``TimeoutError`` past `deadline`
    (the rest is deferred; caught before OSError, of which it is a subclass)
    and OSError on the first entry that cannot be removed."""
    freed = 0
    with os.scandir(root) as it:
        entries = list(it)
    for e in entries:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"sweep budget spent inside {root}")
        st = e.stat(follow_symlinks=False)
        if _is_link(st):
            _unlink_link(e.path)
        elif stat.S_ISDIR(st.st_mode):
            freed += _remove_tree(e.path, deadline)
        else:
            _unlink_file(e.path)
            freed += int(st.st_size)
    os.rmdir(root)
    return freed


def _tree_bytes(root: str, deadline: float) -> Optional[int]:
    """Bytes of regular files under `root` (links not followed), or None past
    the deadline -- a partial size is never reported as a size."""
    total = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if time.monotonic() > deadline:
                        return None
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if _is_link(st):
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(e.path)
                    else:
                        total += int(st.st_size)
        except OSError:
            continue
    return total


def _scan(temp_dir: Path) -> tuple[list[tuple[os.DirEntry, os.stat_result]], dict]:
    """Matching real directories directly inside `temp_dir` + skip counts.
    Raises OSError when `temp_dir` itself cannot be listed."""
    found: list = []
    skipped = {"skipped_files": 0, "skipped_links": 0, "vanished": 0}
    with os.scandir(temp_dir) as it:
        for e in it:
            if not e.name.startswith(PREFIX):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except FileNotFoundError:
                skipped["vanished"] += 1
                continue
            except OSError:
                skipped["skipped_files"] += 1
                continue
            if _is_link(st):
                skipped["skipped_links"] += 1
            elif not stat.S_ISDIR(st.st_mode):
                skipped["skipped_files"] += 1
            else:
                found.append((e, st))
    return found, skipped


# ─────────────────────────────────────────── live OpenClaw process starts

def openclaw_process_starts(timeout: float = 20.0) -> Optional[list[float]]:
    """Start times (epoch s) of live node processes whose command line names
    openclaw, or None when they cannot be listed (the caller then refuses to
    delete anything young enough to belong to one)."""
    if os.name != "nt":
        return None
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
          "Where-Object { $_.CommandLine -match 'openclaw' } | "
          "ForEach-Object { ([DateTimeOffset]$_.CreationDate).ToUnixTimeSeconds() }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=timeout, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out: list[float] = []
    for line in (r.stdout or "").split():
        try:
            out.append(float(line))
        except ValueError:
            return None
    return out


def _protected(birth: float, starts: list[float], window_s: float) -> bool:
    return any(s - 5.0 <= birth <= s + window_s for s in starts)


# ───────────────────────────────────────────────────────────────── sweep

def _append_receipt(path: Path, row: dict) -> Optional[str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        return None
    except OSError as exc:
        return f"{type(exc).__name__}: {str(exc)[:120]}"


def _free_gb(temp_dir: Path) -> Optional[float]:
    try:
        from backend.services import disk_guard as DG                # noqa: PLC0415
        return DG.measure(temp_dir)["free_gb"]
    except Exception:                                               # noqa: BLE001
        return None


def sweep_plugin_builds(max_age_minutes: float = 15, temp_dir: Optional[Path] = None,
                        now: Now = None, *, max_seconds: Optional[float] = None,
                        process_starts: Union[list[float], None, str] = "scan",
                        receipt: Union[Path, None, bool] = True) -> dict:
    """Delete stale ``openclaw-plugin-build-*`` directories in `temp_dir`.

    `process_starts`: "scan" (default) lists live OpenClaw node processes;
    a list is used as given (tests); None means the scan failed. When it
    failed, only folders older than ``OPENCLAW_TEMP_UNSCANNED_MIN_AGE_H`` go.
    `receipt`: True = the default jsonl, a Path = that file, False/None = none.
    Never raises for a folder; raises nothing at all except for bad arguments --
    an unreadable temp dir comes back as ``ok: False``."""
    t0 = time.monotonic()
    now_s = _epoch(now)
    temp_dir = Path(temp_dir) if temp_dir is not None else default_temp_dir()
    budget = float(max_seconds if max_seconds is not None
                   else _cfg("OPENCLAW_TEMP_SWEEP_MAX_SECONDS", 30.0))
    deadline = t0 + budget
    out: dict[str, Any] = {
        "t": datetime.fromtimestamp(now_s, timezone.utc).isoformat(timespec="seconds"),
        "temp_dir": str(temp_dir), "max_age_minutes": max_age_minutes, "ok": True,
        "seen": 0, "deleted": 0, "bytes_freed": 0, "kept_recent": 0, "kept_protected": 0,
        "skipped_files": 0, "skipped_links": 0, "vanished": 0, "failed": 0,
        "deferred": 0, "errors": [], "process_scan": "not_needed"}
    try:
        found, skipped = _scan(temp_dir)
    except OSError as exc:
        out.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:160]}")
        found, skipped = [], {}
    out.update(skipped)
    out["seen"] = len(found)

    min_age_s = float(max_age_minutes) * 60.0
    candidates = []
    for e, st in found:
        if now_s - st.st_mtime < min_age_s:
            out["kept_recent"] += 1
        else:
            candidates.append((e, st))

    if candidates:
        starts = openclaw_process_starts() if process_starts == "scan" else process_starts
        if starts is None:
            out["process_scan"] = "failed"
            floor = float(_cfg("OPENCLAW_TEMP_UNSCANNED_MIN_AGE_H", 24)) * 3600.0
            keep = [c for c in candidates if now_s - c[1].st_mtime < floor]
            out["kept_protected"] += len(keep)
            candidates = [c for c in candidates if now_s - c[1].st_mtime >= floor]
        else:
            out["process_scan"] = f"{len(starts)} live openclaw process(es)"
            window = float(_cfg("OPENCLAW_TEMP_PROTECT_WINDOW_S", 300))
            kept = [c for c in candidates if _protected(_birth(c[1]), starts, window)]
            out["kept_protected"] += len(kept)
            candidates = [c for c in candidates if not _protected(_birth(c[1]), starts, window)]

    if candidates:
        out["free_gb_before"] = _free_gb(temp_dir)
    candidates.sort(key=lambda c: c[1].st_mtime)       # oldest first
    for i, (e, _st) in enumerate(candidates):
        if time.monotonic() >= deadline:
            out["deferred"] += len(candidates) - i
            break
        try:
            out["bytes_freed"] += _remove_tree(e.path, deadline)
            out["deleted"] += 1
        except TimeoutError:                # budget spent: before OSError
            out["deferred"] += len(candidates) - i
            break
        except FileNotFoundError:
            out["vanished"] += 1
        except OSError as exc:
            out["failed"] += 1
            if len(out["errors"]) < 5:
                out["errors"].append(f"{e.name}: {type(exc).__name__}: {str(exc)[:100]}")
    if "free_gb_before" in out:
        out["free_gb_after"] = _free_gb(temp_dir)
    out["seconds"] = round(time.monotonic() - t0, 3)

    rp = receipt_path() if receipt is True else (Path(receipt) if receipt else None)
    if rp is not None:
        err = _append_receipt(rp, out)
        if err:
            out["receipt_error"] = err
    return out


# ─────────────────────────────────────── the client's hook, rate-limited

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"last": None, "running": False, "last_result": None,
                          "last_error": None}


def hooks_enabled() -> bool:
    """False under pytest: a unit test's fake CLI call must never sweep the
    machine's real temp dir. Tests that exercise the hook patch this."""
    return "PYTEST_CURRENT_TEST" not in os.environ


def _run_sweep() -> None:
    try:
        _STATE["last_result"] = sweep_plugin_builds(
            _cfg("OPENCLAW_TEMP_SWEEP_MAX_AGE_MIN", 15))
        _STATE["last_error"] = None
    except Exception as exc:                                        # noqa: BLE001
        _STATE["last_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        logger.warning("openclaw temp sweep failed: %s", _STATE["last_error"])
    finally:
        _STATE["running"] = False


def after_cli_call(*, now: Now = None, inline: bool = False) -> str:
    """At most one sweep per interval; on a daemon thread unless `inline`.
    Returns what it did ("started" | "ran" | "rate_limited" | "running" |
    "disabled" | "error: ..."). Never raises."""
    try:
        if not hooks_enabled():
            return "disabled"
        now_s = _epoch(now)
        interval = float(_cfg("OPENCLAW_TEMP_SWEEP_INTERVAL_S", 600))
        with _LOCK:
            if _STATE["running"]:
                return "running"
            last = _STATE["last"]
            if last is not None and now_s - last < interval:
                return "rate_limited"
            _STATE["last"] = now_s          # a failing sweep still waits its turn
            _STATE["running"] = True
        if inline:
            _run_sweep()
            return "ran"
        threading.Thread(target=_run_sweep, name="openclaw-temp-sweep",
                         daemon=True).start()
        return "started"
    except Exception as exc:                                        # noqa: BLE001
        _STATE["running"] = False
        return f"error: {type(exc).__name__}"


def sweep_state() -> dict:
    return json.loads(json.dumps(_STATE, default=str))


# ─────────────────────────────────────────────────────────────── probe

def measure_builds(temp_dir: Path, *, budget_s: Optional[float] = None,
                   clock: Callable[[], float] = time.monotonic) -> dict:
    """Count every matching folder; size as many as fit in the budget and
    extrapolate. Raises OSError when `temp_dir` cannot be listed."""
    t0 = clock()
    budget = float(budget_s if budget_s is not None
                   else _cfg("OPENCLAW_TEMP_PROBE_BUDGET_S", 1.5))
    found, skipped = _scan(Path(temp_dir))
    n = len(found)
    sized, sized_bytes = 0, 0
    oldest = min((st.st_mtime for _e, st in found), default=None)
    for e, _st in sorted(found, key=lambda c: c[1].st_mtime, reverse=True):
        remaining = t0 + budget - clock()
        if remaining <= 0:
            break
        b = _tree_bytes(e.path, time.monotonic() + remaining)
        if b is None:
            break
        sized += 1
        sized_bytes += b
    est = (sized_bytes / sized * n) if sized else (0 if n == 0 else None)
    return {"count": n, "sized": sized, "sized_bytes": sized_bytes,
            "est_bytes": None if est is None else int(est),
            "size_exact": sized == n, "oldest_mtime": oldest,
            "seconds": round(clock() - t0, 3), **skipped}


def p_openclaw_temp_builds(ctx: Any) -> Any:
    """`system_health` probe. The temp dir comes from
    ``ctx.paths["openclaw_temp_dir"]``; a context without it that does not
    measure the machine either (no ``disk_usage`` reader -- the unit-test
    context) is UNKNOWN rather than a read of the real temp dir."""
    from backend.services.system_health import ProbeResult, _iso, _unknown  # noqa: PLC0415
    td = (getattr(ctx, "paths", None) or {}).get("openclaw_temp_dir")
    if td is None:
        if getattr(ctx, "disk_usage", None) is None:
            return _unknown("temp dir not measured on this context "
                            "(no paths['openclaw_temp_dir'] and no disk reader)")
        td = default_temp_dir()
    try:
        m = measure_builds(Path(td))
    except OSError as exc:
        return _unknown(f"cannot list {td}: {type(exc).__name__}: {str(exc)[:120]}")
    max_n = int(_cfg("OPENCLAW_TEMP_DEGRADED_COUNT", 50))
    max_gb = float(_cfg("OPENCLAW_TEMP_DEGRADED_GB", 5.0))
    gb = None if m["est_bytes"] is None else m["est_bytes"] / 1024 ** 3
    if gb is None:
        size_txt = "size not sampled in the time box"
    elif m["size_exact"]:
        size_txt = f"{gb:.1f} GB"
    else:
        size_txt = f"~{gb:.1f} GB (sized {m['sized']} of {m['count']})"
    base = f"{m['count']} {PREFIX}* folder(s) in {td}, {size_txt}"
    over = m["count"] > max_n or (gb is not None and gb > max_gb)
    now = getattr(ctx, "now", None) or datetime.now(timezone.utc)
    proof = f"scandir {td} ({m['seconds']}s); thresholds {max_n} folders / {max_gb:g} GB"
    if over:
        return ProbeResult("STALE", _iso(now), 0.0,
                           f"DEGRADED: {base} > {max_n} folders or {max_gb:g} GB; "
                           f"sweep: openclaw_temp.sweep_plugin_builds()", proof=proof)
    return ProbeResult("ALIVE", _iso(now), 0.0, base, proof=proof)


__all__ = ["PREFIX", "after_cli_call", "measure_builds", "openclaw_process_starts",
           "p_openclaw_temp_builds", "sweep_plugin_builds", "sweep_state"]
