"""CH-59: one refresh of the opportunity funnel's candidate set AND the universe graph.

    python -m scripts.universe_refresh            (the scheduled task's command)

WHY THIS EXISTS
===============
`funnel_night10.json` is the candidate set every decision path ranks; the universe graph
is what event nodes propagate over. The funnel's only scheduled caller was
`sim_run.u_funnel`, and the sim session is dead; the graph had no scheduled caller at all
(built by hand on 2026-11-11). Twice the funnel passed its 10-day limit while its remedy
looked available (CLAUDE.md, "THE REAL BOTTLENECK WAS A STATIC FILE").

WHAT A RUN DOES, IN ORDER
=========================
0. Takes `<out>/universe_refresh.lock` (pid + start). A live holder means REFUSED(LOCKED)
   for every stage, nothing started; a stale lock (pid not alive, or older than the
   longest possible run) is taken over and the receipt records whose it was. The receipt
   is claimed at once and rewritten (temp -> replace) as each stage starts and ends, so a
   run killed by Task Scheduler still leaves a receipt naming the stage it was in.

WHAT A STAGE DOES, IN ORDER
===========================
1. Reads the live answer's own stamp, size and CONTENT. A live answer that does not exist
   is REFUSED(LIVE_FILE_ABSENT) unless `--allow-create`: a scheduled refresh never makes
   the first copy, because a typo'd or moved data root would otherwise be filled silently.
2. SKIPPED_FRESH only when the stamp is younger than its limit AND the live answer passes
   the same content check a new build must pass (`funnel_problems` / `graph_problems`).
   An undateable or future stamp is UNKNOWN; a fresh stamp over bad content is UNFIT;
   both are rebuilt.
3. Funnel only: waits a bounded time for DNS. No DNS = REFUSED(NO_NETWORK); a DNS failure
   is never reported as a credentials problem, and credentials are not tested here.
4. Runs the builder OUT OF PROCESS (`sys.executable -m ...`), with a timeout, its
   stdout+stderr in a log beside the receipt. This module imports neither builder.
5. The child never writes the live answer directly:
     funnel  builds into a staging file; the parent checks stamp, size and content, then
             promotes it (temp -> verify -> replace, retried while a reader holds the
             file) and files the archive copy;
     graph   is built twice: a REHEARSAL into a staging folder (about 5 s), checked for
             stamp, size and content, and only then the real build into the live folder
             (the builder writes a new run folder and flips `latest.json` atomically). Any
             non-green outcome after the live build started puts `latest.json` back.
   Content (B1/S1): a funnel whose builder recorded failed price batches or enrichment
   calls beyond the configured limits, whose candidates are null or miss required fields,
   or whose screened universe / stage-1 pool shrank, is REFUSED(DEGRADED_BUILD: ...). A
   graph's exit 3 is accepted only when its own receipt names exactly the known-benign
   degradation (the event-check weights MISSING); any other degraded input, an exit code
   that contradicts the receipt, a missing build file, or a structural edge kind that fell
   below its fraction of the previous graph is REFUSED(DEGRADED_BUILD: ...).
6. Re-reads the stamp FROM THE LIVE FILE. A stage is REFRESHED only when that stamp moved;
   rc 0 with an unmoved stamp is UNMOVED, a failure.

STATUSES: REFRESHED, SKIPPED_FRESH (both green); REFUSED(reason), UNMOVED, FAILED(reason)
(all red); RUNNING only inside an unfinished receipt. Overall rc: 0 only when every stage
is green; `UNIVERSE_REFRESH_RC_REFUSED` when the worst stage is a refusal;
`UNIVERSE_REFRESH_RC_FAILED` for FAILED / UNMOVED.

The receipt is `<out>/refresh_<utc>_<pid>.json`; an existing name is never overwritten.
No LLM call anywhere on this path (the funnel's news source is off by default and makes
none; the graph build reads local parquet only). Safe to run repeatedly: after a success
every later run inside the age limit is a cheap SKIPPED_FRESH that starts no child.
"""

from __future__ import annotations

import json
import os
import re
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

REFRESHED, SKIPPED_FRESH, REFUSED, UNMOVED, FAILED, RUNNING = (
    "REFRESHED", "SKIPPED_FRESH", "REFUSED", "UNMOVED", "FAILED", "RUNNING")
GREEN = frozenset({REFRESHED, SKIPPED_FRESH})
STAGES = ("funnel", "graph")

FUNNEL_MODULE = "backend.services.opportunity_funnel"
GRAPH_MODULE = "backend.services.universe_graph"

#: indirection so a test can make the live file "busy" without patching `os` itself
_os_replace = os.replace


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


def _judge_fresh(fresh: dict, live_problems: Sequence[str]) -> dict:
    """A FRESH stamp over content that fails the check is UNFIT, and is rebuilt."""
    if fresh["verdict"] == "FRESH" and live_problems:
        return {**fresh, "verdict": "UNFIT",
                "why": "fresh stamp, but the live content fails the check: " + "; ".join(live_problems)[:300]}
    return fresh


def stamp_moved(before: Any, after: Any, started: datetime, *, trust_before: bool = True) -> tuple[bool, str]:
    """Did the answer's own stamp move because of THIS run? When the stamp before was judged
    UNKNOWN (future), `trust_before=False`: the new stamp need not be later than it (N1)."""
    a, b = parse_stamp(after), parse_stamp(before)
    if a is None:
        return False, f"the stamp after the run is not a date ({after!r})"
    if before is not None and str(before) == str(after):
        return False, f"the stamp is still {after}"
    if trust_before and b is not None and a <= b:
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


def _status(kind: str, reason: str = "", detail: str = "", label: str = "") -> dict:
    shown = label or reason
    return {"status": f"{kind}({shown})" if shown else kind, "status_kind": kind,
            "reason": reason, "detail": detail}


def _degraded(problems: Sequence[str], where: str, suffix: str = "") -> dict:
    return _status(REFUSED, "DEGRADED_BUILD" + suffix,
                   f"{where}: " + "; ".join(problems) + "; the previous answer is kept",
                   label=f"DEGRADED_BUILD{suffix}: {problems[0][:100]}")


def _read_json(path: Path) -> tuple[Any, Optional[str]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "absent"
    except (OSError, ValueError) as exc:
        return None, f"unreadable ({type(exc).__name__})"


def replace_with_retry(src: Path, dst: Path, fn: Optional[Callable[[Any, Any], None]] = None) -> None:
    """`os.replace`, retried while another process holds `dst` open (Windows: WinError 5).
    The last PermissionError is raised; nothing else is retried."""
    fn = fn or _os_replace
    tries = max(1, int(_cfg.UNIVERSE_REFRESH_REPLACE_RETRIES))
    for i in range(tries):
        try:
            fn(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(float(_cfg.UNIVERSE_REFRESH_REPLACE_RETRY_S))


def replace_verified(blob: bytes, dst: Path, verify: Callable[[bytes], None], tag: str, *,
                     make_parent: bool = False) -> None:
    """temp -> verify (re-read from disk) -> replace. Raises before `dst` is touched. The
    parent folder is created only when `make_parent` (never for a live answer by default)."""
    dst = Path(dst)
    if make_parent:
        dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.{tag}.tmp")
    try:
        tmp.write_bytes(blob)
        verify(tmp.read_bytes())
        replace_with_retry(tmp, dst)
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


def rewrite_json(path: Path, obj: Any) -> None:
    """Replace a receipt this run already claimed (temp -> replace)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(json.dumps(obj, indent=1, default=str).encode("utf-8"))
        replace_with_retry(tmp, path, fn=os.replace)
    finally:
        tmp.unlink(missing_ok=True)


# ───────────────────────────────── content checks ────────────────────────────

_BATCHES_RE = re.compile(r"^\s*(\d+)\s+batch")
_STAGE3_RE = re.compile(r"^\s*(\d+)\s+of\s+(\d+)\s")


def _int_at(d: Any, *keys: str) -> Any:
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def funnel_problems(d: Any, prev: Optional[Mapping[str, Any]] = None) -> list[str]:
    """What is wrong with a funnel snapshot's CONTENT ([] = nothing). `prev` is the previous
    live answer's `read_funnel` row, for the shrink fractions; None checks the floors only.
    Thresholds: the `UNIVERSE_REFRESH_FUNNEL_*` block in config."""
    if not isinstance(d, dict):
        return ["the snapshot is not a JSON object"]
    out: list[str] = []
    cands = d.get("candidates")
    if not isinstance(cands, list):
        out.append(f"candidates is not a list ({type(cands).__name__})")
        cands = []
    fails = d.get("failures")
    benign = set(_cfg.UNIVERSE_REFRESH_FUNNEL_BENIGN_FAILURES)
    if not isinstance(fails, dict):
        out.append("the snapshot carries no failures block, so its stage health cannot be judged")
    else:
        for k, v in sorted(fails.items()):
            if k in benign:
                continue
            txt = str(v)
            if k == "stage1_batches":
                m = _BATCHES_RE.match(txt)
                if m and int(m.group(1)) <= int(_cfg.UNIVERSE_REFRESH_FUNNEL_MAX_FAILED_BATCHES):
                    continue
            elif k == "stage3":
                m = _STAGE3_RE.match(txt)
                if m and int(m.group(2)) > 0 and (int(m.group(1)) / int(m.group(2))
                                                  <= float(_cfg.UNIVERSE_REFRESH_FUNNEL_MAX_STAGE3_FAILED_SHARE)):
                    continue
            out.append(f"failures.{k}: {txt[:160]}")
    req = tuple(_cfg.UNIVERSE_REFRESH_FUNNEL_REQUIRED_FIELDS)
    invalid: list[str] = []
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            invalid.append(f"#{i} is not a dict ({c!r})"[:60])
            continue
        miss = [f for f in req if c.get(f) is None
                or (f == "ticker" and not (isinstance(c.get(f), str) and c[f].strip()))]
        if miss:
            invalid.append(f"#{i} {c.get('ticker')!r} has no {'/'.join(miss)}")
    if cands and len(invalid) > float(_cfg.UNIVERSE_REFRESH_FUNNEL_MAX_INVALID_SHARE) * len(cands):
        out.append(f"{len(invalid)} of {len(cands)} candidates are invalid ({'; '.join(invalid[:3])})")
    frac = float(_cfg.UNIVERSE_REFRESH_FUNNEL_MIN_FRACTION)
    for name, keys, floor in (("universe.screened", ("universe", "screened"), _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_SCREENED),
                              ("stages.stage1_eligible", ("stages", "stage1_eligible"),
                               _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_STAGE1_ELIGIBLE)):
        v = _int_at(d, *keys)
        p = (prev or {}).get(name)
        if type(v) is not int:
            out.append(f"{name} is not a count ({v!r})")
        elif v < int(floor):
            out.append(f"{name} {v} is below the floor {floor}")
        elif type(p) is int and p > 0 and v < frac * p:
            out.append(f"{name} {v} is below {frac:.0%} of the previous {p}")
    s4 = _int_at(d, "stages", "stage4_candidates")
    if type(s4) is int and s4 != len(cands):
        out.append(f"stages.stage4_candidates {s4} != {len(cands)} candidates written")
    return out


def graph_problems(g: Mapping[str, Any], prev: Optional[Mapping[str, Any]] = None,
                   rc: Optional[int] = None) -> list[str]:
    """What is wrong with a graph build's CONTENT ([] = nothing), from its own receipt.
    `prev` is the previous live graph's `read_graph` row (per-kind edge fractions); `rc` the
    builder's exit code, which must agree with what the receipt says was degraded."""
    if g.get("error"):
        return [str(g["error"])]
    out: list[str] = []
    if g.get("missing_files"):
        out.append(f"build {g.get('build_id')} lacks {g['missing_files']}")
    degraded, inputs = g.get("degraded_inputs"), g.get("inputs")
    benign: Mapping[str, Sequence[str]] = dict(_cfg.UNIVERSE_REFRESH_GRAPH_BENIGN_DEGRADED)
    if not isinstance(degraded, list):
        out.append(f"the receipt has no degraded_inputs list ({degraded!r})")
        degraded = []
    rows = ({str(r.get("input")): r.get("status") for r in inputs if isinstance(r, dict)}
            if isinstance(inputs, list) else None)
    for name in degraded:
        allowed = benign.get(str(name))
        if allowed is None:
            out.append(f"degraded input {name!r} is not the known-benign degradation")
        elif rows is None:
            out.append(f"degraded input {name!r} cannot be identified: the receipt carries no inputs rows")
        elif rows.get(str(name)) not in tuple(allowed):
            out.append(f"degraded input {name!r} has status {rows.get(str(name))!r}; accepted only {tuple(allowed)}")
    if rows is not None:
        unlisted = sorted(k for k, s in rows.items() if s not in ("OK", "NOT_USED") and k not in map(str, degraded))
        if unlisted:
            out.append(f"inputs {unlisted} are not OK but are missing from degraded_inputs")
    if rc == 3 and not degraded:
        out.append("exit 3 (degraded) but the receipt names no degraded input")
    if rc == 0 and degraded:
        out.append(f"exit 0 but the receipt names degraded inputs {degraded}")
    prev_k = (prev or {}).get("edges_by_kind")
    if isinstance(prev_k, dict) and prev_k:
        new_k = g.get("edges_by_kind")
        frac = float(_cfg.UNIVERSE_REFRESH_GRAPH_MIN_KIND_FRACTION)
        if not isinstance(new_k, dict):
            out.append("the receipt carries no per-kind edge counts (counts.edges)")
        else:
            for k, n0 in sorted(prev_k.items()):
                if type(n0) is int and n0 > 0:
                    n1 = new_k.get(k, 0)
                    if type(n1) is not int or n1 < frac * n0:
                        out.append(f"edge kind {k}: {n0} -> {n1} (below {frac:.0%} of the previous graph)")
    return out


# ───────────────────────────────── live readers ──────────────────────────────

def read_funnel(path: Path) -> dict:
    """The funnel snapshot's own stamp, candidate count, stage health and content problems."""
    d, err = _read_json(path)
    if not isinstance(d, dict):
        return {"path": str(path), "exists": err != "absent", "stamp": None, "count": None,
                "error": err or "not a JSON object", "problems": [err or "not a JSON object"]}
    cands = d.get("candidates")
    fails = d.get("failures")
    return {"path": str(path), "exists": True, "stamp": d.get("generated_at"),
            "count": len(cands) if isinstance(cands, list) else None,
            "universe.screened": _int_at(d, "universe", "screened"),
            "stages.stage1_eligible": _int_at(d, "stages", "stage1_eligible"),
            "stages": d.get("stages"),
            "failures": dict(fails) if isinstance(fails, dict) else fails,     # the text, not only the keys
            "problems": funnel_problems(d), "error": None}


def read_graph(graph_dir: Path) -> dict:
    """`latest.json`'s `built_utc` and the node/edge counts and inputs of the build it names."""
    graph_dir = Path(graph_dir)
    lp = graph_dir / "latest.json"
    latest, err = _read_json(lp)
    out: dict[str, Any] = {"path": str(lp), "exists": err != "absent", "stamp": None, "count": None,
                           "n_edges": None, "build_id": None, "error": err}
    if not isinstance(latest, dict):
        out["error"] = err or "latest.json is not a JSON object"
        return out
    out.update(stamp=latest.get("built_utc"), build_id=latest.get("build_id"), error=None)
    build_dir = graph_dir / str(latest.get("build_id"))
    rec, rerr = _read_json(build_dir / "receipt.json")
    if not isinstance(rec, dict):
        out["error"] = f"receipt.json of {latest.get('build_id')}: {rerr or 'not a JSON object'}"
        return out
    counts = rec.get("counts") if isinstance(rec.get("counts"), dict) else {}
    out.update(count=counts.get("n_nodes"), n_edges=counts.get("n_edges"), edges_by_kind=counts.get("edges"),
               build_status=rec.get("status"), degraded_inputs=rec.get("degraded_inputs"),
               inputs=[{"input": r.get("input"), "status": r.get("status")} for r in rec["inputs"]
                       if isinstance(r, dict)] if isinstance(rec.get("inputs"), list) else None,
               panel_last_session=rec.get("panel_last_session"), as_of=rec.get("as_of"),
               missing_files=[f for f in _cfg.UNIVERSE_REFRESH_GRAPH_BUILD_FILES if not (build_dir / f).exists()])
    if rec.get("built_utc") != latest.get("built_utc"):
        out["error"] = (f"latest.json built_utc {latest.get('built_utc')} != receipt.json "
                        f"{rec.get('built_utc')}")
    return out


def _graph_live_problems(g: Mapping[str, Any]) -> list[str]:
    """The check a fresh live graph must pass before it may be skipped (S2)."""
    probs = graph_problems(g)
    if not g.get("error"):
        for what, v in (("nodes", g.get("count")), ("edges", g.get("n_edges"))):
            if type(v) is not int or v <= 0:
                probs.append(f"the live graph states {v!r} {what}")
    return probs


def _funnel_live_problems(f: Mapping[str, Any]) -> list[str]:
    probs = list(f.get("problems") or [])
    if not f.get("error") and (type(f.get("count")) is not int or f["count"] <= 0):
        probs.append(f"the live funnel holds {f.get('count')!r} candidates")
    return probs


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


# ───────────────────────────────── one instance at a time ────────────────────

def pid_alive(pid: Any) -> bool:
    """Is `pid` a running process? Reads only; never signals (on Windows `os.kill(pid, 0)`
    would SEND a CTRL_C_EVENT, so it is not used there)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return k32.GetLastError() == 5                   # ACCESS_DENIED: it exists
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == 259                         # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_stale(held: Any, now: datetime, alive: Callable[[Any], bool]) -> Optional[str]:
    """Why a held lock is stale, or None when its holder is alive and inside the longest run."""
    if not isinstance(held, dict):
        return "the lock file is not a readable JSON object"
    t = parse_stamp(held.get("started_utc"))
    if t is None:
        return "the lock carries no start time"
    age = (now - t).total_seconds()
    if age > float(_cfg.UNIVERSE_REFRESH_LOCK_MAX_AGE_S):
        return f"the lock is {age:.0f} s old, older than the longest run ({_cfg.UNIVERSE_REFRESH_LOCK_MAX_AGE_S} s)"
    if not alive(held.get("pid")):
        return f"pid {held.get('pid')} is not alive"
    return None


def acquire_lock(path: Path, run_id: str, now: datetime, *,
                 alive: Optional[Callable[[Any], bool]] = None) -> dict:
    """Exclusive-create `path`. A live, young holder: not acquired. A stale one: taken over
    and recorded. Nothing is ever killed."""
    alive = alive or pid_alive
    path = Path(path)
    mine = {"pid": os.getpid(), "started_utc": iso(now), "run_id": run_id}
    blob = json.dumps(mine).encode("utf-8")
    row: dict[str, Any] = {"path": str(path), "acquired": False, "held_by": None, "taken_over": None, "why": ""}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        held, _ = _read_json(path)
        why = _lock_stale(held, now, alive)
        if why is None:
            return {**row, "held_by": held,
                    "why": f"run {held.get('run_id')} (pid {held.get('pid')}) holds the lock since {held.get('started_utc')}"}
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_bytes(blob)
            replace_with_retry(tmp, path, fn=os.replace)
        finally:
            tmp.unlink(missing_ok=True)
        got, _ = _read_json(path)
        if not isinstance(got, dict) or got.get("run_id") != run_id:
            return {**row, "held_by": got, "why": "another run took over the stale lock first"}
        return {**row, "acquired": True, "taken_over": held, "why": why}
    with os.fdopen(fd, "wb") as fh:
        fh.write(blob)
    return {**row, "acquired": True}


def release_lock(path: Path, run_id: str) -> None:
    """Remove the lock only while it is still this run's."""
    held, _ = _read_json(path)
    if isinstance(held, dict) and held.get("run_id") == run_id:
        try:
            Path(path).unlink()
        except OSError:
            pass


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


def archive_path(history_dir: Path, stamp: str) -> Path:
    """`funnel_<date>.json`, the builder's own archive name; when that day already holds an
    archive, `funnel_<date>_<HHMMSS>Z.json`, so an earlier snapshot of the same day is kept
    (decision contracts cite a snapshot by its `generated_at`; readers glob `funnel_*.json`
    and sort by name, and the suffixed name sorts after the plain one)."""
    day = Path(history_dir) / f"funnel_{stamp[:10]}.json"
    t = parse_stamp(stamp)
    if not day.exists() or t is None:
        return day
    return Path(history_dir) / f"funnel_{stamp[:10]}_{t.strftime('%H%M%S')}Z.json"


# ───────────────────────────────── the two stages ────────────────────────────

Runner = Callable[[Sequence[str], Path, float], ChildResult]


def _base(before: dict, fresh: dict, cmd: Sequence[str], log_path: Path) -> dict:
    return {"live_path": before.get("path"), "stamp_before": before.get("stamp"), "stamp_after": before.get("stamp"),
            "count_before": before.get("count"), "count_after": before.get("count"),
            "read_error_before": before.get("error"), "freshness": fresh,
            "seconds": 0.0, "child_rc": None, "child_cmd": [str(c) for c in cmd], "log": str(log_path)}


def _absent(what: str, path: Any) -> dict:
    return _status(REFUSED, "LIVE_FILE_ABSENT", (
        f"no live {what} at {path}; a scheduled refresh never creates the first copy (a wrong or "
        f"moved data root would be filled silently). Check the path, or pass --allow-create"))


def refresh_funnel(*, live_path: Path, work_dir: Path, log_path: Path, now: datetime, force: bool,
                   run_id: str, command: Callable[[Path], list[str]] = funnel_command,
                   runner: Runner = run_child,
                   network: Callable[[], tuple[bool, dict]] = wait_for_dns,
                   allow_create: bool = False) -> dict:
    live_path = Path(live_path)
    staged = Path(work_dir) / "funnel" / live_path.name
    cmd = command(staged)
    before = read_funnel(live_path)
    fresh = _judge_fresh(freshness(before["stamp"], now, _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS),
                         _funnel_live_problems(before))
    st = {**_base(before, fresh, cmd, log_path), "count_unit": "candidates", "staged_path": str(staged)}
    if not before["exists"] and not allow_create:
        return {**st, **_absent("funnel", live_path)}
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
    st["staged"] = {k: new.get(k) for k in ("stamp", "count", "universe.screened", "stages.stage1_eligible",
                                            "stages", "failures", "error")}
    if new["error"]:
        return {**st, **_status(UNMOVED, detail=f"rc 0 but the builder wrote no readable snapshot ({new['error']})")}
    moved, why = stamp_moved(before["stamp"], new["stamp"], started, trust_before=fresh["verdict"] != "UNKNOWN")
    if not moved:
        return {**st, **_status(UNMOVED, detail=f"rc 0 but {why}")}
    small = shrink_reason(before["count"], new["count"], _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_FRACTION, "candidates")
    if small:
        return {**st, **_status(REFUSED, small[0], small[1] + f"; the rejected snapshot stays at {staged}")}
    probs = funnel_problems(_read_json(staged)[0], before if before["error"] is None else None)
    st["staged"]["problems"] = probs
    if probs:
        return {**st, **_degraded(probs, f"the new snapshot (kept at {staged})")}

    def verify(blob: bytes) -> None:
        got = json.loads(blob.decode("utf-8-sig"))
        if got.get("generated_at") != new["stamp"] or len(got.get("candidates") or []) != new["count"]:
            raise ValueError("the temp copy does not match the staged snapshot")

    blob = staged.read_bytes()
    try:
        replace_verified(blob, live_path, verify, run_id, make_parent=allow_create)
    except PermissionError as exc:
        return {**st, **_status(REFUSED, "LIVE_FILE_BUSY", (
            f"{type(exc).__name__}: {exc}; tried {_cfg.UNIVERSE_REFRESH_REPLACE_RETRIES} times "
            f"{_cfg.UNIVERSE_REFRESH_REPLACE_RETRY_S} s apart while another process held the live file; "
            f"the live file is unchanged, no archive was written, the build stays at {staged}"))}
    except (OSError, ValueError) as exc:
        after = read_funnel(live_path)
        st.update(stamp_after=after["stamp"], count_after=after["count"])
        return {**st, **_status(FAILED, "PROMOTE_FAILED", f"{type(exc).__name__}: {exc}")}
    try:
        archive = archive_path(live_path.parent / "funnel_history", str(new["stamp"]))
        replace_verified(blob, archive, verify, run_id, make_parent=True)
        st["archive"] = str(archive)
    except (OSError, ValueError) as exc:
        after = read_funnel(live_path)
        st.update(stamp_after=after["stamp"], count_after=after["count"])
        return {**st, **_status(FAILED, "PROMOTE_FAILED", f"archive copy: {type(exc).__name__}: {exc}")}
    after = read_funnel(live_path)                      # the claim is read back from the live file
    st.update(stamp_after=after["stamp"], count_after=after["count"])
    if after["stamp"] != new["stamp"]:
        return {**st, **_status(UNMOVED, detail=f"promoted, but the live file reads {after['stamp']!r}")}
    shutil.rmtree(staged.parent, ignore_errors=True)
    return {**st, **_status(REFRESHED)}


def refresh_graph(*, graph_dir: Path, data_root: Path, work_dir: Path, log_path: Path, now: datetime,
                  force: bool, run_id: str,
                  command: Callable[[Path, Path], list[str]] = graph_command,
                  runner: Runner = run_child, allow_create: bool = False) -> dict:
    graph_dir = Path(graph_dir)
    rehearsal_dir = Path(work_dir) / "graph_rehearsal"
    cmd = command(Path(data_root), graph_dir)
    before = read_graph(graph_dir)
    fresh = _judge_fresh(freshness(before["stamp"], now, _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS),
                         _graph_live_problems(before))
    trust = fresh["verdict"] != "UNKNOWN"
    prev = before if before["error"] is None else None
    st = {**_base(before, fresh, cmd, log_path), "count_unit": "nodes", "edges_before": before.get("n_edges"),
          "edges_after": before.get("n_edges"), "build_id_before": before.get("build_id"),
          "build_id_after": before.get("build_id"), "rehearsal_dir": str(rehearsal_dir), "rehearsal_rc": None,
          "panel_last_session_before": before.get("panel_last_session")}
    if not before["exists"] and not allow_create:
        return {**st, **_absent("graph (latest.json)", graph_dir / "latest.json")}
    if fresh["verdict"] == "FRESH" and not force:
        return {**st, **_status(SKIPPED_FRESH, detail=f"{fresh['age_hours']} h old, limit {fresh['limit_hours']} h")}
    ok_rcs = tuple(_cfg.UNIVERSE_REFRESH_GRAPH_WRITTEN_RCS)
    timeout_s = float(_cfg.UNIVERSE_REFRESH_GRAPH_TIMEOUT_S)
    frac = float(_cfg.UNIVERSE_REFRESH_GRAPH_MIN_FRACTION)

    def too_small(g: dict) -> Optional[tuple[str, str]]:
        return (shrink_reason(before["count"], g["count"], frac, "nodes")
                or shrink_reason(before["n_edges"], g["n_edges"], frac, "edges"))

    # 1. rehearsal: the same build into a staging folder, so a small, empty or degraded answer
    #    is seen before the live `latest.json` can be flipped to it
    rehearsal_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    res = runner(command(Path(data_root), rehearsal_dir), log_path, timeout_s)
    st.update(seconds=res.seconds, rehearsal_rc=res.rc)
    bad = _child_failure(res, ok_rcs, log_path, timeout_s)
    if bad:
        return {**st, **bad, "detail": f"rehearsal build: {bad['detail']}"}
    reh = read_graph(rehearsal_dir)
    st["rehearsal"] = {k: reh.get(k) for k in ("stamp", "count", "n_edges", "edges_by_kind", "build_id",
                                               "build_status", "degraded_inputs", "error")}
    if reh["error"]:
        return {**st, **_status(UNMOVED, detail=f"rehearsal rc {res.rc} but no readable graph ({reh['error']})")}
    moved, why = stamp_moved(before["stamp"], reh["stamp"], started, trust_before=trust)
    if not moved:
        return {**st, **_status(UNMOVED, detail=f"rehearsal rc {res.rc} but {why}")}
    small = too_small(reh)
    if small:
        return {**st, **_status(REFUSED, small[0], small[1] + f"; the rejected build stays at {rehearsal_dir}")}
    probs = graph_problems(reh, prev, rc=res.rc)
    st["rehearsal"]["problems"] = probs
    if probs:
        return {**st, **_degraded(probs, f"rehearsal build rc {res.rc} (kept at {rehearsal_dir})")}

    # 2. the live build; from here on, any outcome but REFRESHED puts `latest.json` back (N3)
    latest = graph_dir / "latest.json"
    latest_before = latest.read_bytes() if latest.exists() else None
    started = utc_now()
    res2 = runner(cmd, log_path, timeout_s)
    st.update(seconds=round(res.seconds + res2.seconds, 1), child_rc=res2.rc)
    after = read_graph(graph_dir)                       # the claim is read back from the live file
    st.update(stamp_after=after["stamp"], count_after=after["count"], edges_after=after["n_edges"],
              build_id_after=after["build_id"], build_status=after.get("build_status"),
              degraded_inputs=after.get("degraded_inputs"), panel_last_session=after.get("panel_last_session"))
    outcome = _child_failure(res2, ok_rcs, log_path, timeout_s)
    if outcome is None and after["error"]:
        outcome = _status(UNMOVED, detail=f"rc {res2.rc} but the live graph is not readable ({after['error']})")
    if outcome is None:
        moved, why = stamp_moved(before["stamp"], after["stamp"], started, trust_before=trust)
        if not moved:
            outcome = _status(UNMOVED, detail=f"rc {res2.rc} but {why}")
    if outcome is None:
        small = too_small(after)
        if small:                         # the rehearsal passed and the live build did not
            outcome = _status(REFUSED, small[0] + "_AFTER_WRITE",
                              small[1] + f"; the rejected build stays at {graph_dir / str(after['build_id'])}")
    if outcome is None:
        probs = graph_problems(after, prev, rc=res2.rc)
        if probs:
            outcome = _degraded(probs, f"live build rc {res2.rc} ({after['build_id']})", suffix="_AFTER_WRITE")
    if outcome is None:
        if st["panel_last_session"] == st["panel_last_session_before"]:
            st["note"] = f"the bars panel did not advance (panel_last_session {st['panel_last_session']})"
        shutil.rmtree(rehearsal_dir, ignore_errors=True)
        return {**st, **_status(REFRESHED)}
    now_bytes = latest.read_bytes() if latest.exists() else None
    if latest_before is not None and now_bytes != latest_before:
        try:
            replace_verified(latest_before, latest, lambda b: json.loads(b.decode("utf-8-sig")), run_id)
            back = read_graph(graph_dir)
            st.update(stamp_after=back["stamp"], count_after=back["count"], edges_after=back["n_edges"],
                      build_id_after=back["build_id"], rolled_back_from=after["build_id"])
            outcome = {**outcome, "detail": outcome["detail"] + "; latest.json was put back"}
        except (OSError, ValueError) as exc:
            outcome = {**outcome, "detail": outcome["detail"] + (
                f"; latest.json could NOT be put back ({type(exc).__name__}: {exc})")}
    return {**st, **outcome}


# ───────────────────────────────── the run ───────────────────────────────────

def overall_rc(stages: Mapping[str, Mapping[str, Any]]) -> int:
    kinds = {str(s.get("status_kind")) for s in stages.values()}
    if not stages or kinds - GREEN - {REFUSED}:
        return int(_cfg.UNIVERSE_REFRESH_RC_FAILED)      # FAILED, UNMOVED, an unknown status, no stage
    if REFUSED in kinds:
        return int(_cfg.UNIVERSE_REFRESH_RC_REFUSED)
    return 0


def _overall_status(rc: int) -> str:
    return "OK" if rc == 0 else ("REFUSED" if rc == int(_cfg.UNIVERSE_REFRESH_RC_REFUSED) else "FAILED")


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
         now: Optional[datetime] = None, force: bool = False, only: Sequence[str] = STAGES,
         allow_create: bool = False) -> dict:
    """What a run would do, from the live stamps and content alone. Starts nothing, writes nothing."""
    p = default_paths(data_root)
    now = now or utc_now()
    fp, gd = Path(funnel_path or p["funnel_path"]), Path(graph_dir or p["graph_dir"])
    out_dir = Path(out or p["out"])
    f, g = read_funnel(fp), read_graph(gd)
    ff = _judge_fresh(freshness(f["stamp"], now, _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS),
                      _funnel_live_problems(f))
    gf = _judge_fresh(freshness(g["stamp"], now, _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS),
                      _graph_live_problems(g))
    work = out_dir / "work" / "<run id>"

    def would(row: dict, fr: dict) -> Any:
        if not row["exists"] and not allow_create:
            return "no: REFUSED(LIVE_FILE_ABSENT)"
        return force or fr["verdict"] != "FRESH"

    rows = {
        "funnel": {"live_path": str(fp), "live_exists": f["exists"], "stamp": f["stamp"], "count": f["count"],
                   "freshness": ff, "would_run": would(f, ff),
                   "child_cmds": [funnel_command(work / "funnel" / fp.name)],
                   "then": "check stamp, size and content, promote into live_path (temp -> verify -> replace), "
                           "archive"},
        "graph": {"live_path": str(gd / "latest.json"), "live_exists": g["exists"], "stamp": g["stamp"],
                  "count": g["count"], "n_edges": g["n_edges"], "freshness": gf, "would_run": would(g, gf),
                  "child_cmds": [graph_command(p["data_root"], work / "graph_rehearsal"),
                                 graph_command(p["data_root"], gd)],
                  "then": "rehearsal first; the live build only when the rehearsal passes size and content"}}
    return {"schema": SCHEMA + "/plan", "now_utc": iso(now), "force": force, "out": str(out_dir),
            "lock": str(out_dir / _cfg.UNIVERSE_REFRESH_LOCK_NAME),
            "cwd": str(REPO_ROOT), "stages": {k: v for k, v in rows.items() if k in only},
            "writes": "nothing (plan only)"}


def _limits() -> dict:
    return {"funnel_max_age_hours": _cfg.UNIVERSE_REFRESH_FUNNEL_MAX_AGE_HOURS,
            "graph_max_age_hours": _cfg.UNIVERSE_REFRESH_GRAPH_MAX_AGE_HOURS,
            "funnel_min_fraction": _cfg.UNIVERSE_REFRESH_FUNNEL_MIN_FRACTION,
            "graph_min_fraction": _cfg.UNIVERSE_REFRESH_GRAPH_MIN_FRACTION,
            "graph_min_kind_fraction": _cfg.UNIVERSE_REFRESH_GRAPH_MIN_KIND_FRACTION,
            "funnel_timeout_s": _cfg.UNIVERSE_REFRESH_FUNNEL_TIMEOUT_S,
            "graph_timeout_s": _cfg.UNIVERSE_REFRESH_GRAPH_TIMEOUT_S,
            "network_wait_s": _cfg.UNIVERSE_REFRESH_NETWORK_WAIT_S,
            "max_run_s": _cfg.UNIVERSE_REFRESH_MAX_RUN_S}


def refresh(*, data_root: Optional[Path] = None, out: Optional[Path] = None,
            funnel_path: Optional[Path] = None, graph_dir: Optional[Path] = None,
            force: bool = False, only: Sequence[str] = STAGES, argv: Optional[Sequence[str]] = None,
            commands: Optional[Mapping[str, Callable[..., list[str]]]] = None,
            runner: Runner = run_child,
            network: Callable[[], tuple[bool, dict]] = wait_for_dns,
            now: Optional[datetime] = None, allow_create: bool = False) -> dict:
    """Take the lock, run the stages in `only`, keep the receipt current, return it (with
    `receipt_path`).

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
    log_path = out_dir / f"refresh_{run_id}.log"
    wanted = [s for s in STAGES if s in only]
    receipt: dict[str, Any] = {
        "schema": SCHEMA, "run_id": run_id, "started_utc": iso(started), "updated_utc": iso(utc_now()),
        "finished_utc": None, "argv": list(argv) if argv is not None else None, "force": bool(force),
        "allow_create": bool(allow_create), "only": list(only),
        "overall_rc": None, "overall_status": RUNNING, "in_progress": None, "stages": {},
        "paths": {"data_root": str(p["data_root"]), "out": str(out_dir), "log": str(log_path),
                  "cwd": str(REPO_ROOT)},
        "limits": _limits(), "producer_ids": {}, "llm_spend_usd": 0.0}
    lock_path = out_dir / str(_cfg.UNIVERSE_REFRESH_LOCK_NAME)
    lock = acquire_lock(lock_path, run_id, started)
    receipt["lock"] = lock
    if not lock["acquired"]:
        receipt["stages"] = {s: {**_status(REFUSED, "LOCKED", f"another refresh is running: {lock['why']}; "
                                                         f"nothing was started"), "seconds": 0.0, "child_rc": None}
                             for s in wanted}
        rc = overall_rc(receipt["stages"])
        receipt.update(overall_rc=rc, overall_status=_overall_status(rc), finished_utc=iso(utc_now()),
                       updated_utc=iso(utc_now()))
        path = write_new_json(out_dir, f"refresh_{run_id}", receipt)
        return {**receipt, "receipt_path": str(path)}
    try:
        path = write_new_json(out_dir, f"refresh_{run_id}", receipt)   # claimed now; rewritten as we go

        def save() -> None:
            receipt["updated_utc"] = iso(utc_now())
            try:
                rewrite_json(path, receipt)
            except OSError as exc:                      # a progress write must not cost the stage
                receipt.setdefault("receipt_write_errors", []).append(f"{type(exc).__name__}: {exc}"[:200])

        work.mkdir(parents=True)
        commands = dict(commands or {})
        stages: dict[str, dict] = receipt["stages"]
        for name in wanted:
            t0 = time.monotonic()
            receipt["in_progress"] = name
            stages[name] = {"status": RUNNING, "status_kind": RUNNING, "started_utc": iso(utc_now())}
            save()
            try:
                if name == "funnel":
                    stages[name] = refresh_funnel(
                        live_path=Path(funnel_path or p["funnel_path"]), work_dir=work, log_path=log_path,
                        now=started, force=force, run_id=run_id,
                        command=commands.get("funnel", funnel_command), runner=runner, network=network,
                        allow_create=allow_create)
                else:
                    stages[name] = refresh_graph(
                        graph_dir=Path(graph_dir or p["graph_dir"]), data_root=p["data_root"], work_dir=work,
                        log_path=log_path, now=started, force=force, run_id=run_id,
                        command=commands.get("graph", graph_command), runner=runner, allow_create=allow_create)
            except Exception as exc:                     # noqa: BLE001 - one stage must not cost the other
                stages[name] = {**_status(FAILED, "STAGE_RAISED", f"{type(exc).__name__}: {str(exc)[:300]}"),
                                "seconds": round(time.monotonic() - t0, 1), "child_rc": None}
            receipt["in_progress"] = None
            save()
        try:
            if not any(work.iterdir()):
                work.rmdir()
                if not any(work.parent.iterdir()):
                    work.parent.rmdir()
        except OSError:
            pass
        rc = overall_rc(stages)
        receipt.update(overall_rc=rc, overall_status=_overall_status(rc), finished_utc=iso(utc_now()),
                       producer_ids={"funnel": (stages.get("funnel") or {}).get("stamp_after"),
                                     "graph": (stages.get("graph") or {}).get("build_id_after")})
        receipt["updated_utc"] = iso(utc_now())
        rewrite_json(path, receipt)
        return {**receipt, "receipt_path": str(path)}
    finally:
        release_lock(lock_path, run_id)


def summary_lines(receipt: Mapping[str, Any]) -> list[str]:
    lines = []
    lock = receipt.get("lock") or {}
    if lock.get("taken_over"):
        lines.append(f"lock   taken over from run {lock['taken_over'].get('run_id')!r}: {lock.get('why')}")
    for name, s in (receipt.get("stages") or {}).items():
        lines.append(f"{name:6s} {s.get('status')}: {s.get('count_unit', 'rows')} {s.get('count_before')} -> "
                     f"{s.get('count_after')}, stamp {s.get('stamp_before')} -> {s.get('stamp_after')}, "
                     f"child rc {s.get('child_rc')}, {s.get('seconds')} s"
                     + (f" [{s.get('detail')}]" if s.get("detail") else "")
                     + (f" [{s.get('note')}]" if s.get("note") else ""))
    lines.append(f"overall rc {receipt.get('overall_rc')} ({receipt.get('overall_status')}); "
                 f"receipt {receipt.get('receipt_path')}")
    return lines
