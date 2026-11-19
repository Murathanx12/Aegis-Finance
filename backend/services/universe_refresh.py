"""CH-59: one refresh of the opportunity funnel's candidate set AND the universe graph.

    python -m scripts.universe_refresh            (the daily task's command)

WHY THIS EXISTS
===============
`funnel_night10.json` is the candidate set every decision path ranks; the universe graph
is what event nodes propagate over. The funnel's only scheduled caller was
`sim_run.u_funnel`, and the sim session is dead; the graph had no scheduled caller at all
(built by hand on 2026-11-11). Twice the funnel passed its 10-day limit while its remedy
looked available (CLAUDE.md, "THE REAL BOTTLENECK WAS A STATIC FILE").

WHAT A STAGE DOES, IN ORDER
===========================
1. Reads the live answer's own stamp and size (`generated_at` + candidates; `built_utc` +
   nodes/edges). An undateable or future stamp is UNKNOWN and is rebuilt, never fresh.
2. SKIPPED_FRESH when the answer is younger than its configured age (unless `--force`).
3. Funnel only: waits a bounded time for DNS. No DNS = REFUSED(NO_NETWORK); a DNS failure
   is never reported as a credentials problem, and credentials are not tested here.
4. Runs the builder OUT OF PROCESS (`sys.executable -m ...`), with a timeout, its
   stdout+stderr in a log beside the receipt. This module imports neither builder.
5. The child never writes the live answer directly:
     funnel  builds into a staging file; the parent checks stamp and size, then promotes
             it (temp -> verify -> replace) and files the archive copy;
     graph   is built twice: a REHEARSAL into a staging folder (about 5 s), checked for
             stamp and size, and only then the real build into the live folder (the
             builder itself writes a new run folder and flips `latest.json` atomically).
             If the live build still came out smaller, `latest.json` is put back.
6. Re-reads the stamp FROM THE LIVE FILE. A stage is REFRESHED only when that stamp moved;
   rc 0 with an unmoved stamp is UNMOVED, a failure.

STATUSES: REFRESHED, SKIPPED_FRESH (both green); REFUSED(reason), UNMOVED, FAILED(reason)
(all red). Overall rc: 0 only when every stage is green; `UNIVERSE_REFRESH_RC_REFUSED`
when the worst stage is a refusal; `UNIVERSE_REFRESH_RC_FAILED` for FAILED / UNMOVED.

The receipt is `<out>/refresh_<utc>_<pid>.json`; an existing name is never overwritten.
No LLM call anywhere on this path (the funnel's news source is off by default and makes
none; the graph build reads local parquet only).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from backend import config as _cfg

SCHEMA = "universe_refresh/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]

REFRESHED, SKIPPED_FRESH, REFUSED, UNMOVED, FAILED = (
    "REFRESHED", "SKIPPED_FRESH", "REFUSED", "UNMOVED", "FAILED")
GREEN = frozenset({REFRESHED, SKIPPED_FRESH})
STAGES = ("funnel", "graph")

FUNNEL_MODULE = "backend.services.opportunity_funnel"
GRAPH_MODULE = "backend.services.universe_graph"


# ───────────────────────────────── small helpers ─────────────────────────────

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_stamp(v: Any) -> Optional[datetime]:
    """An ISO stamp as an aware UTC datetime; anything else is None (undateable)."""
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        t = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def freshness(stamp: Any, now: datetime, max_age_hours: float) -> dict:
    """FRESH / STALE / UNKNOWN for a live answer's own stamp. UNKNOWN is rebuilt."""
    t = parse_stamp(stamp)
    out: dict[str, Any] = {"stamp": stamp, "limit_hours": float(max_age_hours), "age_hours": None}
    if t is None:
        return {**out, "verdict": "UNKNOWN", "why": "no parseable stamp on the live answer"}
    age_h = (now - t).total_seconds() / 3600.0
    out["age_hours"] = round(age_h, 2)
    if age_h * 3600.0 < -float(_cfg.UNIVERSE_REFRESH_FUTURE_STAMP_TOLERANCE_S):
        return {**out, "verdict": "UNKNOWN", "why": "the stamp is in the future"}
    return {**out, "verdict": "FRESH" if age_h <= float(max_age_hours) else "STALE", "why": ""}


def stamp_moved(before: Any, after: Any, started: datetime) -> tuple[bool, str]:
    """Did the answer's own stamp move because of THIS run?"""
    a, b = parse_stamp(after), parse_stamp(before)
    if a is None:
        return False, f"the stamp after the run is not a date ({after!r})"
    if before is not None and str(before) == str(after):
        return False, f"the stamp is still {after}"
    if b is not None and a <= b:
        return False, f"the stamp after the run ({after}) is not newer than before ({before})"
    if (started - a).total_seconds() > 2.0:
        return False, f"the stamp after the run ({after}) predates this run's start ({iso(started)})"
    return True, ""


def shrink_reason(before: Optional[int], after: Optional[int], min_fraction: float, what: str
                  ) -> Optional[tuple[str, str]]:
    """(reason, detail) when the new answer is empty or too small to replace the old one."""
    if type(after) is not int:
        return "UNREADABLE_SIZE", f"the new answer does not state a count of {what} ({after!r})"
    if after <= 0:
        return "EMPTY", f"the new answer has 0 {what}"
    if type(before) is int and before > 0 and after < float(min_fraction) * before:
        return "SHRINK", (f"{after} {what} is below {min_fraction:.0%} of the previous {before}; "
                          f"the previous answer is kept")
    return None


def _status(kind: str, reason: str = "", detail: str = "") -> dict:
    return {"status": f"{kind}({reason})" if reason else kind, "status_kind": kind,
            "reason": reason, "detail": detail}


def _read_json(path: Path) -> tuple[Any, Optional[str]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "absent"
    except (OSError, ValueError) as exc:
        return None, f"unreadable ({type(exc).__name__})"


def replace_verified(blob: bytes, dst: Path, verify: Callable[[bytes], None], tag: str) -> None:
    """temp -> verify (re-read from disk) -> replace. Raises before `dst` is touched."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.{tag}.tmp")
    try:
        tmp.write_bytes(blob)
        verify(tmp.read_bytes())
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_new_json(folder: Path, stem: str, obj: Any) -> Path:
    """Write `<stem>.json` under a name no earlier run holds; never overwrites one."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(obj, indent=1, default=str).encode("utf-8")
    tmp = folder / f".{stem}.{os.getpid()}.tmp"
    tmp.write_bytes(blob)
    try:
        json.loads(tmp.read_bytes().decode("utf-8"))
        for n in range(1000):
            final = folder / (f"{stem}.json" if n == 0 else f"{stem}_{n}.json")
            try:
                os.link(tmp, final)                      # fails when the name exists
                return final
            except FileExistsError:
                continue
            except OSError:                              # no hard links on this volume
                if not final.exists():
                    shutil.copyfile(tmp, final)
                    return final
        raise FileExistsError(f"no free receipt name for {stem} under {folder}")
    finally:
        tmp.unlink(missing_ok=True)


# ───────────────────────────────── live readers ──────────────────────────────

def read_funnel(path: Path) -> dict:
    """The funnel snapshot's own stamp and candidate count."""
    d, err = _read_json(path)
    if not isinstance(d, dict):
        return {"path": str(path), "exists": err != "absent", "stamp": None, "count": None,
                "error": err or "not a JSON object"}
    cands = d.get("candidates")
    return {"path": str(path), "exists": True, "stamp": d.get("generated_at"),
            "count": len(cands) if isinstance(cands, list) else None,
            "stages": d.get("stages"), "failures": sorted((d.get("failures") or {}).keys()),
            "error": None}


def read_graph(graph_dir: Path) -> dict:
    """`latest.json`'s `built_utc` and the node/edge counts of the build it names."""
    graph_dir = Path(graph_dir)
    lp = graph_dir / "latest.json"
    latest, err = _read_json(lp)
    out: dict[str, Any] = {"path": str(lp), "exists": err != "absent", "stamp": None, "count": None,
                           "n_edges": None, "build_id": None, "error": err}
    if not isinstance(latest, dict):
        out["error"] = err or "latest.json is not a JSON object"
        return out
    out.update(stamp=latest.get("built_utc"), build_id=latest.get("build_id"), error=None)
    rec, rerr = _read_json(graph_dir / str(latest.get("build_id")) / "receipt.json")
    if not isinstance(rec, dict):
        out["error"] = f"receipt.json of {latest.get('build_id')}: {rerr or 'not a JSON object'}"
        return out
    counts = rec.get("counts") if isinstance(rec.get("counts"), dict) else {}
    out.update(count=counts.get("n_nodes"), n_edges=counts.get("n_edges"),
               build_status=rec.get("status"), degraded_inputs=rec.get("degraded_inputs"),
               panel_last_session=rec.get("panel_last_session"), as_of=rec.get("as_of"))
    if rec.get("built_utc") != latest.get("built_utc"):
        out["error"] = (f"latest.json built_utc {latest.get('built_utc')} != receipt.json "
                        f"{rec.get('built_utc')}")
    return out


# ───────────────────────────────── network gate ──────────────────────────────

def _resolve(host: str) -> None:
    socket.getaddrinfo(host, 443)


def wait_for_dns(hosts: Optional[Sequence[str]] = None, *, wait_s: Optional[float] = None,
                 poll_s: Optional[float] = None, resolver: Callable[[str], Any] = _resolve,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> tuple[bool, dict]:
    """True once every host resolves; False after `wait_s`. DNS only: no request is sent."""
    hosts = tuple(_cfg.UNIVERSE_REFRESH_NETWORK_HOSTS if hosts is None else hosts)
    wait_s = float(_cfg.UNIVERSE_REFRESH_NETWORK_WAIT_S if wait_s is None else wait_s)
    poll_s = float(_cfg.UNIVERSE_REFRESH_NETWORK_POLL_S if poll_s is None else poll_s)
    t0 = clock()
    tries = 0
    while True:
        tries += 1
        failed = {}
        for h in hosts:
            try:
                resolver(h)
            except OSError as exc:
                failed[h] = type(exc).__name__
        waited = round(clock() - t0, 1)
        info = {"hosts": list(hosts), "unresolved": failed, "tries": tries, "waited_s": waited,
                "wait_limit_s": wait_s, "check": "DNS resolution only; credentials were not tested"}
        if not failed:
            return True, info
        if clock() - t0 + poll_s > wait_s:
            return False, info
        sleep(poll_s)


# ───────────────────────────────── children ──────────────────────────────────

@dataclass
class ChildResult:
    rc: Optional[int]
    seconds: float
    timed_out: bool = False
    error: str = ""


def run_child(cmd: Sequence[str], log_path: Path, timeout_s: float, *,
              cwd: Optional[Path] = None) -> ChildResult:
    """Run one builder out of process, its output appended to `log_path`, no console window.
    On timeout the child this call started is killed by its own handle."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    t0 = time.monotonic()
    with open(log_path, "ab") as log:
        log.write(f"\n=== {iso(utc_now())} $ {' '.join(map(str, cmd))}\n".encode("utf-8"))
        log.flush()
        try:
            p = subprocess.Popen([str(c) for c in cmd], cwd=str(cwd or REPO_ROOT), stdout=log,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=flags)
        except OSError as exc:
            return ChildResult(None, round(time.monotonic() - t0, 1),
                               error=f"could not start ({type(exc).__name__}: {exc})")
        try:
            rc = p.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return ChildResult(p.returncode, round(time.monotonic() - t0, 1), timed_out=True)
    return ChildResult(rc, round(time.monotonic() - t0, 1))


def child_python() -> str:
    """This interpreter; under `pythonw.exe` (a windowless task) its `python.exe` sibling,
    so the child's prints reach the log. `run_child` starts it with no console window."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def funnel_command(out_file: Path) -> list[str]:
    return [child_python(), "-m", FUNNEL_MODULE, "--out", str(out_file)]


def graph_command(data_root: Path, out_dir: Path) -> list[str]:
    return [child_python(), "-m", GRAPH_MODULE, "build", "--data-root", str(data_root),
            "--out", str(out_dir)]


def _log_tail(log_path: Path, needle: str = "REFUSED", nbytes: int = 4000) -> str:
    """The child's last line carrying `needle` (else its last line), for the receipt."""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - nbytes))
            lines = [ln.strip() for ln in fh.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    except OSError:
        return ""
    hit = [ln for ln in lines if needle in ln]
    return (hit[-1] if hit else (lines[-1] if lines else ""))[:300]


def _child_failure(res: ChildResult, ok_rcs: Sequence[int], log_path: Path, timeout_s: float
                   ) -> Optional[dict]:
    """None when the child's rc is one that means "written"; else the stage status."""
    if res.error:
        return _status(FAILED, "CHILD_NOT_STARTED", res.error)
    if res.timed_out:
        return _status(FAILED, "TIMEOUT", f"killed after {timeout_s:.0f} s")
    if res.rc in tuple(ok_rcs):
        return None
    if res.rc == 2:                      # both builders' documented refusal code
        return _status(REFUSED, "CHILD_REFUSED", _log_tail(log_path) or "the builder exited 2")
    return _status(FAILED, f"CHILD_RC_{res.rc}", _log_tail(log_path, "Error"))


# ───────────────────────────────── the two stages ────────────────────────────

Runner = Callable[[Sequence[str], Path, float], ChildResult]


def _base(before: dict, fresh: dict, cmd: Sequence[str], log_path: Path) -> dict:
    return {"live_path": before.get("path"), "stamp_before": before.get("stamp"), "stamp_after": before.get("stamp"),
            "count_before": before.get("count"), "count_after": before.get("count"),
            "read_error_before": before.get("error"), "freshness": fresh,
            "seconds": 0.0, "child_rc": None, "child_cmd": [str(c) for c in cmd], "log": str(log_path)}


def refresh_funnel(*, live_path: Path, work_dir: Path, log_path: Path, now: datetime, force: bool,
                   run_id: str, command: Callable[[Path], list[str]] = funnel_command,
                   runner: Runner = run_child,
                   network: Callable[[], tuple[bool, dict]] = wait_for_dns) -> dict:
    live_path = Path(live_path)
    staged = Path(work_dir) / "funnel" / live_path.name
    cmd = command(staged)
    before = read_funnel(live_path)
    fresh = freshness(before["stamp"], now, _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS)
    st = {**_base(before, fresh, cmd, log_path), "count_unit": "candidates", "staged_path": str(staged)}
    if fresh["verdict"] == "FRESH" and not force:
        return {**st, **_status(SKIPPED_FRESH, detail=f"{fresh['age_hours']} h old, limit {fresh['limit_hours']} h")}
    ok, net = network()
    st["network"] = net
    if not ok:
        return {**st, **_status(REFUSED, "NO_NETWORK", (
            f"DNS did not resolve {sorted(net.get('unresolved') or {})} within {net.get('waited_s')} s; "
            f"the builder was not started and no credential was tested"))}
    staged.parent.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    timeout_s = float(_cfg.UNIVERSE_REFRESH_FUNNEL_TIMEOUT_S)
    res = runner(cmd, log_path, timeout_s)
    st.update(seconds=res.seconds, child_rc=res.rc)
    bad = _child_failure(res, (0,), log_path, timeout_s)
    if bad:
        return {**st, **bad}
    new = read_funnel(staged)
    st["staged"] = {k: new.get(k) for k in ("stamp", "count", "stages", "failures", "error")}
    if new["error"]:
        return {**st, **_status(UNMOVED, detail=f"rc 0 but the builder wrote no readable snapshot ({new['error']})")}
    moved, why = stamp_moved(before["stamp"], new["stamp"], started)
    if not moved:
        return {**st, **_status(UNMOVED, detail=f"rc 0 but {why}")}
    small = shrink_reason(before["count"], new["count"], _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_FRACTION, "candidates")
    if small:
        return {**st, **_status(REFUSED, small[0], small[1] + f"; the rejected snapshot stays at {staged}")}

    def verify(blob: bytes) -> None:
        got = json.loads(blob.decode("utf-8-sig"))
        if got.get("generated_at") != new["stamp"] or len(got.get("candidates") or []) != new["count"]:
            raise ValueError("the temp copy does not match the staged snapshot")

    blob = staged.read_bytes()
    try:
        replace_verified(blob, live_path, verify, run_id)
        archive = live_path.parent / "funnel_history" / f"funnel_{str(new['stamp'])[:10]}.json"
        replace_verified(blob, archive, verify, run_id)
        st["archive"] = str(archive)
    except (OSError, ValueError) as exc:
        after = read_funnel(live_path)
        st.update(stamp_after=after["stamp"], count_after=after["count"])
        return {**st, **_status(FAILED, "PROMOTE_FAILED", f"{type(exc).__name__}: {exc}")}
    after = read_funnel(live_path)                      # the claim is read back from the live file
    st.update(stamp_after=after["stamp"], count_after=after["count"])
    if after["stamp"] != new["stamp"]:
        return {**st, **_status(UNMOVED, detail=f"promoted, but the live file reads {after['stamp']!r}")}
    shutil.rmtree(staged.parent, ignore_errors=True)
    return {**st, **_status(REFRESHED)}


def refresh_graph(*, graph_dir: Path, data_root: Path, work_dir: Path, log_path: Path, now: datetime,
                  force: bool, run_id: str,
                  command: Callable[[Path, Path], list[str]] = graph_command,
                  runner: Runner = run_child) -> dict:
    graph_dir = Path(graph_dir)
    rehearsal_dir = Path(work_dir) / "graph_rehearsal"
    cmd = command(Path(data_root), graph_dir)
    before = read_graph(graph_dir)
    fresh = freshness(before["stamp"], now, _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS)
    st = {**_base(before, fresh, cmd, log_path), "count_unit": "nodes", "edges_before": before.get("n_edges"),
          "edges_after": before.get("n_edges"), "build_id_before": before.get("build_id"),
          "build_id_after": before.get("build_id"), "rehearsal_dir": str(rehearsal_dir), "rehearsal_rc": None}
    if fresh["verdict"] == "FRESH" and not force:
        return {**st, **_status(SKIPPED_FRESH, detail=f"{fresh['age_hours']} h old, limit {fresh['limit_hours']} h")}
    ok_rcs = tuple(_cfg.UNIVERSE_REFRESH_GRAPH_WRITTEN_RCS)
    timeout_s = float(_cfg.UNIVERSE_REFRESH_GRAPH_TIMEOUT_S)
    frac = float(_cfg.UNIVERSE_REFRESH_GRAPH_MIN_FRACTION)

    def too_small(g: dict) -> Optional[tuple[str, str]]:
        return (shrink_reason(before["count"], g["count"], frac, "nodes")
                or shrink_reason(before["n_edges"], g["n_edges"], frac, "edges"))

    # 1. rehearsal: the same build into a staging folder, so a small or empty answer is
    #    seen before the live `latest.json` can be flipped to it
    rehearsal_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    res = runner(command(Path(data_root), rehearsal_dir), log_path, timeout_s)
    st.update(seconds=res.seconds, rehearsal_rc=res.rc)
    bad = _child_failure(res, ok_rcs, log_path, timeout_s)
    if bad:
        return {**st, **bad, "detail": f"rehearsal build: {bad['detail']}"}
    reh = read_graph(rehearsal_dir)
    st["rehearsal"] = {k: reh.get(k) for k in ("stamp", "count", "n_edges", "build_id", "build_status", "error")}
    if reh["error"]:
        return {**st, **_status(UNMOVED, detail=f"rehearsal rc {res.rc} but no readable graph ({reh['error']})")}
    moved, why = stamp_moved(before["stamp"], reh["stamp"], started)
    if not moved:
        return {**st, **_status(UNMOVED, detail=f"rehearsal rc {res.rc} but {why}")}
    small = too_small(reh)
    if small:
        return {**st, **_status(REFUSED, small[0], small[1] + f"; the rejected build stays at {rehearsal_dir}")}

    # 2. the live build
    latest = graph_dir / "latest.json"
    latest_before = latest.read_bytes() if latest.exists() else None
    started = utc_now()
    res2 = runner(cmd, log_path, timeout_s)
    st.update(seconds=round(res.seconds + res2.seconds, 1), child_rc=res2.rc)
    after = read_graph(graph_dir)                       # the claim is read back from the live file
    st.update(stamp_after=after["stamp"], count_after=after["count"], edges_after=after["n_edges"],
              build_id_after=after["build_id"], build_status=after.get("build_status"),
              degraded_inputs=after.get("degraded_inputs"), panel_last_session=after.get("panel_last_session"))
    bad = _child_failure(res2, ok_rcs, log_path, timeout_s)
    if bad:
        return {**st, **bad}
    if after["error"]:
        return {**st, **_status(UNMOVED, detail=f"rc {res2.rc} but the live graph is not readable ({after['error']})")}
    moved, why = stamp_moved(before["stamp"], after["stamp"], started)
    if not moved:
        return {**st, **_status(UNMOVED, detail=f"rc {res2.rc} but {why}")}
    small = too_small(after)
    if small:
        # the rehearsal passed and the live build did not (the inputs changed in between)
        detail = small[1] + f"; the rejected build stays at {graph_dir / str(after['build_id'])}"
        if latest_before is not None:
            replace_verified(latest_before, latest, lambda b: json.loads(b.decode("utf-8-sig")), run_id)
            back = read_graph(graph_dir)
            st.update(stamp_after=back["stamp"], count_after=back["count"], edges_after=back["n_edges"],
                      build_id_after=back["build_id"], rolled_back_from=after["build_id"])
            detail += "; latest.json was put back"
        return {**st, **_status(REFUSED, small[0] + "_AFTER_WRITE", detail)}
    shutil.rmtree(rehearsal_dir, ignore_errors=True)
    return {**st, **_status(REFRESHED)}


# ───────────────────────────────── the run ───────────────────────────────────

def overall_rc(stages: Mapping[str, Mapping[str, Any]]) -> int:
    kinds = {str(s.get("status_kind")) for s in stages.values()}
    if not stages or kinds - GREEN - {REFUSED}:
        return int(_cfg.UNIVERSE_REFRESH_RC_FAILED)      # FAILED, UNMOVED, an unknown status, no stage
    if REFUSED in kinds:
        return int(_cfg.UNIVERSE_REFRESH_RC_REFUSED)
    return 0


def default_paths(data_root: Optional[Path] = None) -> dict[str, Path]:
    """Where the live answers are. In a release clone `backend/data/optimus` is a junction to
    the live data while `backend/data/funnel_night10.json` beside it is the copy committed with
    the release, so the LIVE funnel is the sibling of the junction's target (the rule
    `scripts.system_status.live_data_dir` uses, CH-64)."""
    root = Path(data_root) if data_root else Path(_cfg.OPTIMUS_LEDGER_DIR)
    try:
        live_data = root.resolve().parent
    except OSError:
        live_data = root.parent
    return {"data_root": root,
            "funnel_path": live_data / Path(_cfg.IC_FUNNEL_PATH).name,
            "graph_dir": root / Path(_cfg.UNIVERSE_GRAPH_DIR).name,
            "out": root / str(_cfg.UNIVERSE_REFRESH_DIRNAME)}


def plan(*, data_root: Optional[Path] = None, out: Optional[Path] = None,
         funnel_path: Optional[Path] = None, graph_dir: Optional[Path] = None,
         now: Optional[datetime] = None, force: bool = False, only: Sequence[str] = STAGES) -> dict:
    """What a run would do, from the live stamps alone. Starts nothing, writes nothing."""
    p = default_paths(data_root)
    now = now or utc_now()
    fp, gd = Path(funnel_path or p["funnel_path"]), Path(graph_dir or p["graph_dir"])
    out_dir = Path(out or p["out"])
    f, g = read_funnel(fp), read_graph(gd)
    ff = freshness(f["stamp"], now, _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS)
    gf = freshness(g["stamp"], now, _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS)
    work = out_dir / "work" / "<run id>"
    rows = {
        "funnel": {"live_path": str(fp), "stamp": f["stamp"], "count": f["count"], "freshness": ff,
                   "would_run": force or ff["verdict"] != "FRESH",
                   "child_cmds": [funnel_command(work / "funnel" / fp.name)],
                   "then": "check stamp and size, promote into live_path (temp -> verify -> replace), archive"},
        "graph": {"live_path": str(gd / "latest.json"), "stamp": g["stamp"], "count": g["count"],
                  "n_edges": g["n_edges"], "freshness": gf, "would_run": force or gf["verdict"] != "FRESH",
                  "child_cmds": [graph_command(p["data_root"], work / "graph_rehearsal"),
                                 graph_command(p["data_root"], gd)],
                  "then": "rehearsal first; the live build only when the rehearsal is not smaller"}}
    return {"schema": SCHEMA + "/plan", "now_utc": iso(now), "force": force, "out": str(out_dir),
            "cwd": str(REPO_ROOT), "stages": {k: v for k, v in rows.items() if k in only},
            "writes": "nothing (plan only)"}


def refresh(*, data_root: Optional[Path] = None, out: Optional[Path] = None,
            funnel_path: Optional[Path] = None, graph_dir: Optional[Path] = None,
            force: bool = False, only: Sequence[str] = STAGES, argv: Optional[Sequence[str]] = None,
            commands: Optional[Mapping[str, Callable[..., list[str]]]] = None,
            runner: Runner = run_child,
            network: Callable[[], tuple[bool, dict]] = wait_for_dns,
            now: Optional[datetime] = None) -> dict:
    """Run the stages in `only`, write the receipt, return it (with `receipt_path`).

    `commands` maps a stage to the function that builds its child command; tests inject
    fake children there. Each stage runs whatever the other one did."""
    p = default_paths(data_root)
    started = now or utc_now()
    out_dir = Path(out or p["out"])
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}_{os.getpid()}"
    work = out_dir / "work" / run_id
    n = 0
    while work.exists():                                 # a second run in the same second, same pid
        n += 1
        work = out_dir / "work" / f"{run_id}_{n}"
    run_id = work.name
    work.mkdir(parents=True)
    log_path = out_dir / f"refresh_{run_id}.log"
    commands = dict(commands or {})
    stages: dict[str, dict] = {}
    for name in STAGES:
        if name not in only:
            continue
        t0 = time.monotonic()
        try:
            if name == "funnel":
                stages[name] = refresh_funnel(
                    live_path=Path(funnel_path or p["funnel_path"]), work_dir=work, log_path=log_path,
                    now=started, force=force, run_id=run_id,
                    command=commands.get("funnel", funnel_command), runner=runner, network=network)
            else:
                stages[name] = refresh_graph(
                    graph_dir=Path(graph_dir or p["graph_dir"]), data_root=p["data_root"], work_dir=work,
                    log_path=log_path, now=started, force=force, run_id=run_id,
                    command=commands.get("graph", graph_command), runner=runner)
        except Exception as exc:                         # noqa: BLE001 - one stage must not cost the other
            stages[name] = {**_status(FAILED, "STAGE_RAISED", f"{type(exc).__name__}: {str(exc)[:300]}"),
                            "seconds": round(time.monotonic() - t0, 1), "child_rc": None}
    try:
        if not any(work.iterdir()):
            work.rmdir()
            if not any(work.parent.iterdir()):
                work.parent.rmdir()
    except OSError:
        pass
    rc = overall_rc(stages)
    receipt = {
        "schema": SCHEMA, "run_id": run_id, "started_utc": iso(started), "finished_utc": iso(utc_now()),
        "argv": list(argv) if argv is not None else None, "force": bool(force), "only": list(only),
        "overall_rc": rc, "overall_status": "OK" if rc == 0 else (
            "REFUSED" if rc == int(_cfg.UNIVERSE_REFRESH_RC_REFUSED) else "FAILED"),
        "stages": stages,
        "paths": {"data_root": str(p["data_root"]), "out": str(out_dir), "log": str(log_path),
                  "cwd": str(REPO_ROOT)},
        "limits": {"funnel_max_age_hours": _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS,
                   "graph_max_age_hours": _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS,
                   "funnel_min_fraction": _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_FRACTION,
                   "graph_min_fraction": _cfg.UNIVERSE_REFRESH_GRAPH_MIN_FRACTION},
        "producer_ids": {"funnel": (stages.get("funnel") or {}).get("stamp_after"),
                         "graph": (stages.get("graph") or {}).get("build_id_after")},
        "llm_spend_usd": 0.0,
    }
    path = write_new_json(out_dir, f"refresh_{run_id}", receipt)
    return {**receipt, "receipt_path": str(path)}


def summary_lines(receipt: Mapping[str, Any]) -> list[str]:
    lines = []
    for name, s in (receipt.get("stages") or {}).items():
        lines.append(f"{name:6s} {s.get('status')}: {s.get('count_unit', 'rows')} {s.get('count_before')} -> "
                     f"{s.get('count_after')}, stamp {s.get('stamp_before')} -> {s.get('stamp_after')}, "
                     f"child rc {s.get('child_rc')}, {s.get('seconds')} s"
                     + (f" [{s.get('detail')}]" if s.get("detail") else ""))
    lines.append(f"overall rc {receipt.get('overall_rc')} ({receipt.get('overall_status')}); "
                 f"receipt {receipt.get('receipt_path')}")
    return lines
