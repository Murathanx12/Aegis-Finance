"""One probe per long-running or scheduled subsystem, each verdict DERIVED.

WHY THIS EXISTS (review 2026-09-26, `docs/reviews/REVIEW_2026-09-26_SYSTEMS_ATTACK_AND_HEALTH_PROBES.md`)
======================================================================================================
The review censused 29 things that are supposed to run and found three silent
stalls in one sitting -- the bars panel five sessions old with no refresher,
the Railway backend asleep with every lane NAV eight days old, the Telegram
agent dead for three and a half days -- each of them reading healthy on the
surface that existed. They are the `funnel_night10.json` failure again: a
file, or a process, that nothing compared to the clock.

So each probe here answers from EVIDENCE the producer itself wrote -- a stamp
inside a receipt, a pid that answers with the right module in its command
line, an HTTP body field, a row count that moved since the previous probe --
and never from a filesystem timestamp or a lock file alone. A lock says a
process started; it does not say the process lives.

Verdicts
--------
* ``ALIVE``   -- evidence inside the probe's declared cadence (+ grace).
* ``STALE``   -- evidence exists and is older than the cadence, or a process
                 answers but writes nothing.
* ``DEAD``    -- a process or endpoint is GONE (the pid does not answer, the
                 port does not answer). Only process/endpoint probes say DEAD.
* ``UNKNOWN`` -- the evidence that would decide does not exist; ``detail``
                 says why. Missing evidence is never ALIVE, and a probe that
                 raises is UNKNOWN with the exception class.
* ``STOPPED_BY_OPERATOR`` -- the process is gone AND its own stop record says a
                 human stopped it on purpose (the lab's STOP file). Not ALIVE
                 (nothing runs) and not DEAD (nothing crashed). Read from the
                 record the process wrote on its way out, never inferred from
                 the STOP file's presence alone.
* ``REFUSED`` -- nothing runs because the process's OWNER decided not to start
                 it, and its own fresh receipt names why (2026-10-06: the sim
                 owner's `sim/owner.jsonl`). Not DEAD (nothing crashed, the
                 owner fired) and not ALIVE (nothing runs). Exit code 2.
* ``ALIVE_OBSERVE_ONLY`` -- the process runs but CANNOT trade (a sim in
                 `observe` mode): a running loop is not a trading account
                 (review C2 F6). Exit code 0; the detail says why.

A probe that cannot go red is a broken probe: every probe has a test in
``test_system_health.py`` where its evidence is missing or old and the verdict
must not be ALIVE.

Surfaces: ``python -m scripts.health_probe`` (the table + a receipt under
``backend/data/optimus/health/``), ``/api/health/full`` -> ``subsystems``, the
morning report and the Telegram brief (non-ALIVE rows first).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Union

Verdict = Literal["ALIVE", "STALE", "DEAD", "UNKNOWN", "STOPPED_BY_OPERATOR", "REFUSED",
                  "ALIVE_OBSERVE_ONLY"]
VERDICT_ORDER = {"DEAD": 0, "STALE": 1, "REFUSED": 2, "UNKNOWN": 3,
                 "STOPPED_BY_OPERATOR": 4, "ALIVE_OBSERVE_ONLY": 5, "ALIVE": 6}

#: ALIVE tolerates this fraction of the cadence beyond it (a 5-minute
#: heartbeat written at 5m40s is not a stall).
GRACE = 0.25
#: A health receipt older than this is not used to fill rows it cannot compute.
RECEIPT_MAX_AGE_S = 2 * 3600
#: A US session is treated as CLOSED this long after 16:00 ET (the free SIP
#: feed serves with a 15-minute delay). Same constant as the bars refresher.
SESSION_CLOSED_AFTER_ET = dtime(16, 20)
#: `forecast_grader`: a due row waiting on a bar longer than this is STALE.
NO_BAR_STALE_DAYS = 21
#: `llama_server`: typing units waiting on a model longer than this is STALE.
PENDING_MODEL_STALE_S = 3600

REPO = Path(__file__).resolve().parents[2]
FLEET_SERVICES = ("aat-loop-hack1", "aat-loop-hack2", "aat-loop-hack4",
                  "aat-loop-hack5", "aat-loop-hack6", "seal-authority")


# ════════════════════════════════════════════════════════════════ contract

@dataclass
class ProbeResult:
    verdict: Verdict
    evidence_utc: Optional[str]
    age_s: Optional[float]
    detail: str
    delta: Optional[int] = None
    proof: str = ""
    #: the fine state beside the coarse verdict (C8, 2026-10-07): ALIVE_PROGRESSING /
    #: ALIVE_IDLE_EXPECTED / DEGRADED / ... (task_receipts.STATES). None = same as verdict.
    state: Optional[str] = None


@dataclass
class ProbeCtx:
    """Everything a probe may read. Injectable so tests never touch the machine."""
    optimus_dir: Path
    now: datetime
    repo: Path = REPO
    allow_proc: bool = True
    prev_state: dict = field(default_factory=dict)
    new_state: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)
    run: Optional[Callable[[list, float], tuple]] = None
    http_json: Optional[Callable[[str, float], tuple]] = None
    pid_cmdline: Optional[Callable[[int], Optional[str]]] = None
    railway_url: str = ""
    cache: dict = field(default_factory=dict)
    #: `shutil.disk_usage`-shaped reader for `disk_free`; None = not measured
    #: (UNKNOWN). `make_ctx` supplies the real one; tests inject a fake.
    disk_usage: Optional[Callable[[str], Any]] = None

    def path(self, key: str, default: Path) -> Path:
        return Path(self.paths.get(key, default))


ProbeOut = Union[ProbeResult, dict]


@dataclass(frozen=True)
class Probe:
    name: str
    where: Literal["pc", "railway", "external"]
    cadence: timedelta
    evidence: str
    fn: Callable[[ProbeCtx], ProbeOut]
    needs_proc: bool = False     # shells out / opens a socket: not run on an API request


# ════════════════════════════════════════════════════════════════ helpers

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts(v: Any) -> Optional[datetime]:
    """An aware UTC datetime from an ISO stamp or a date, else None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    s = str(v).strip().lstrip("\ufeff")
    try:
        if len(s) == 10:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") if dt else None


def _age(dt: Optional[datetime], now: datetime) -> Optional[float]:
    return None if dt is None else round((now - dt).total_seconds(), 1)


def _fmt_age(s: Optional[float]) -> str:
    if s is None:
        return "age unknown"
    s = max(0.0, s)              # a stamp written after the probe's clock read
    if s < 120:
        return f"{s:.0f}s"
    if s < 7200:
        return f"{s/60:.0f}m"
    if s < 172800:
        return f"{s/3600:.1f}h"
    return f"{s/86400:.1f}d"


def _read_json(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _tail_lines(p: Path, nbytes: int = 65536) -> list[str]:
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = data.splitlines()
    if size > nbytes and lines:
        lines = lines[1:]                     # the first line is probably cut
    return [l for l in lines if l.strip()]


def _last_json_row(p: Path) -> Optional[dict]:
    for line in reversed(_tail_lines(p)):
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                return row
        except ValueError:
            continue
    return None


def _by_age(dt: Optional[datetime], cadence: timedelta, now: datetime) -> Verdict:
    age = _age(dt, now)
    if age is None:
        return "UNKNOWN"
    return "ALIVE" if age <= cadence.total_seconds() * (1 + GRACE) else "STALE"


def _newest_named(folder: Path, pattern: str) -> Optional[Path]:
    """The newest file by NAME (the producer's own stamp), never by mtime."""
    try:
        files = sorted(folder.glob(pattern))
    except OSError:
        return None
    return files[-1] if files else None


def _unknown(detail: str, **kw) -> ProbeResult:
    return ProbeResult("UNKNOWN", kw.pop("evidence_utc", None), kw.pop("age_s", None),
                       detail, **kw)


# ─────────────────────────────────────────────── calendar (XNYS, else weekdays)

def _sessions(lo: date, hi: date) -> tuple[list[date], str]:
    try:
        import exchange_calendars as xc                             # noqa: PLC0415
        cal = xc.get_calendar("XNYS", start="2015-01-01", end="2035-12-31")
        return [s.date() for s in cal.sessions_in_range(lo.isoformat(), hi.isoformat())], "XNYS"
    except Exception:                                               # noqa: BLE001
        out, d = [], lo
        while d <= hi:
            if d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
        return out, "WEEKDAY_APPROX"


def _et(now: datetime) -> datetime:
    from zoneinfo import ZoneInfo                                   # noqa: PLC0415
    return now.astimezone(ZoneInfo("America/New_York"))


def last_closed_session(now: datetime) -> date:
    """The most recent XNYS session whose close has passed (a Monday is not
    stale because Sunday had no bar)."""
    et = _et(now)
    today = et.date()
    days, _ = _sessions(today - timedelta(days=14), today)
    if days and days[-1] == today and et.time() < SESSION_CLOSED_AFTER_ET:
        days = days[:-1]
    return days[-1] if days else today - timedelta(days=1)


def sessions_behind(newest: date, last: date) -> int:
    if newest >= last:
        return 0
    days, _ = _sessions(newest + timedelta(days=1), last)
    return len(days)


def in_session_hours(now: datetime) -> bool:
    et = _et(now)
    days, _ = _sessions(et.date(), et.date())
    return bool(days) and dtime(9, 30) <= et.time() <= dtime(16, 0)


def _bars_limit() -> int:
    try:
        from backend import config as C                             # noqa: PLC0415
        return int(getattr(C, "BARS_MAX_AGE_SESSIONS", 2))
    except Exception:                                               # noqa: BLE001
        return 2


# ─────────────────────────────────────────────── default machine adapters

def _default_run(argv: list, timeout: float) -> tuple:
    """(rc, text). rc None = could not run at all (binary absent, timeout).

    A `.cmd`/`.bat` shim (npm-installed CLIs on Windows) needs the shell; a
    real executable does not get one.
    """
    import shutil                                                   # noqa: PLC0415
    argv = [str(a) for a in argv]
    exe = shutil.which(argv[0]) or argv[0]
    shell = os.name == "nt" and exe.lower().endswith((".cmd", ".bat"))
    try:
        r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           shell=shell)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _default_http_json(url: str, timeout: float) -> tuple:
    """(body|None, elapsed_s, error|None)."""
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:     # noqa: S310
            return json.loads(r.read().decode("utf-8")), round(time.time() - t0, 2), None
    except Exception as exc:                                        # noqa: BLE001
        return None, round(time.time() - t0, 2), f"{type(exc).__name__}: {exc}"[:200]


def _default_pid_cmdline(pid: int) -> Optional[str]:
    """The command line of a live pid; None when no such process.

    '' means the process exists but its command line is unreadable.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if os.name == "nt":
        rc, out = _default_run(
            ["powershell", "-NoProfile", "-Command",
             f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
             f"if($p){{'FOUND:'+$p.CommandLine}}"], 30)
        if rc is None:
            return None
        for line in out.splitlines():
            if line.startswith("FOUND:"):
                return line[6:].strip()
        return None
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return None


def _cmdline(ctx: ProbeCtx, pid: Any) -> Optional[str]:
    key = f"cmdline:{pid}"
    if key not in ctx.cache:
        fn = ctx.pid_cmdline or _default_pid_cmdline
        ctx.cache[key] = fn(pid) if pid else None
    return ctx.cache[key]


def _run(ctx: ProbeCtx, argv: list, timeout: float = 60) -> tuple:
    return (ctx.run or _default_run)(argv, timeout)


def _pid_from_file(p: Path) -> Optional[int]:
    try:
        txt = Path(p).read_text(encoding="utf-8-sig", errors="replace").strip().lstrip("\ufeff")
        return int(re.findall(r"\d+", txt)[0])
    except (OSError, IndexError, ValueError):
        return None


# ════════════════════════════════════════════════════════════════ probes

def p_bars_panel(ctx: ProbeCtx) -> ProbeResult:
    p = ctx.optimus_dir / "prices_2025_26" / "bars.parquet"
    if not p.exists():
        return _unknown(f"no bars panel at {p}")
    try:
        import pyarrow.parquet as pq                                # noqa: PLC0415
        f = pq.ParquetFile(p)
        i = f.schema_arrow.get_field_index("date")
        best = None
        for g in range(f.metadata.num_row_groups):
            st = f.metadata.row_group(g).column(i).statistics
            if st is None or not st.has_min_max:
                best = None
                break
            best = st.max if best is None or st.max > best else best
        if best is None:
            import pyarrow.compute as pc                            # noqa: PLC0415
            best = pc.max(pq.read_table(p, columns=["date"])["date"]).as_py()
    except Exception as exc:                                        # noqa: BLE001
        return _unknown(f"bars panel unreadable ({type(exc).__name__}: {str(exc)[:100]})")
    if best is None:
        return _unknown("bars panel carries no readable `date`")
    newest = best.date() if hasattr(best, "date") else date.fromisoformat(str(best)[:10])
    last = last_closed_session(ctx.now)
    n = sessions_behind(newest, last)
    limit = _bars_limit()
    dt = _ts(newest)
    v: Verdict = "STALE" if n > limit else "ALIVE"
    return ProbeResult(v, _iso(dt), _age(dt, ctx.now),
                       f"newest bar {newest}, {n} session(s) behind the last closed "
                       f"session {last} (limit BARS_MAX_AGE_SESSIONS={limit})",
                       proof=f"bars.parquet max(date)={newest}")


def _bars_newest(ctx: ProbeCtx) -> Optional[date]:
    if "bars_newest" not in ctx.cache:
        r = p_bars_panel(ctx)
        ctx.cache["bars_newest"] = _ts(r.evidence_utc).date() if r.evidence_utc else None
    return ctx.cache["bars_newest"]


def _newest_pc_book(ctx: ProbeCtx) -> Optional[Path]:
    d = ctx.optimus_dir / "pc_book"
    try:
        days = sorted(x for x in d.iterdir() if x.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x.name))
    except OSError:
        return None
    return days[-1] if days else None


def p_ranking(ctx: ProbeCtx) -> ProbeResult:
    day = _newest_pc_book(ctx)
    r = _read_json(day / "ranking.json") if day else None
    if not isinstance(r, dict) or not r.get("asof"):
        return _unknown("no pc_book/<day>/ranking.json with an `asof`")
    asof = _ts(r["asof"])
    if asof is None:
        return _unknown(f"ranking asof {r['asof']!r} is undateable")
    last = last_closed_session(ctx.now)
    n = sessions_behind(asof.date(), last)
    limit = _bars_limit()
    return ProbeResult("STALE" if n > limit else "ALIVE", _iso(asof), _age(asof, ctx.now),
                       f"ranking in {day.name} is as of {asof.date()}, {n} session(s) "
                       f"behind {last} (limit {limit})",
                       proof=f"{day.name}/ranking.json asof={r['asof']}")


def p_u_funnel(ctx: ProbeCtx) -> ProbeResult:
    try:
        from backend import config as C                             # noqa: PLC0415
        default = Path(C.IC_FUNNEL_PATH)
    except Exception:                                               # noqa: BLE001
        default = ctx.optimus_dir.parent / "funnel_night10.json"
    p = ctx.path("funnel", default)
    d = _read_json(p)
    if not isinstance(d, dict):
        return _unknown(f"no readable funnel snapshot at {p}")
    from backend.services.investment_committee import (             # noqa: PLC0415
        FUNNEL_STALE_DAYS, funnel_staleness)
    line = funnel_staleness(d.get("generated_at"), now=ctx.now)
    dt = _ts(d.get("generated_at"))
    if dt is None:
        return _unknown(line or "funnel snapshot is undateable")
    n = len(d.get("candidates") or d.get("shortlist") or [])
    return ProbeResult("STALE" if line else "ALIVE", _iso(dt), _age(dt, ctx.now),
                       line or f"funnel generated {_fmt_age(_age(dt, ctx.now))} ago "
                               f"(limit {FUNNEL_STALE_DAYS} d), {n} candidate(s)",
                       proof=f"funnel_night10.json generated_at={d.get('generated_at')}")


def _lab_status(ctx: ProbeCtx) -> Optional[dict]:
    if "lab" not in ctx.cache:
        ctx.cache["lab"] = _read_json(ctx.optimus_dir / "lab_status.json")
    d = ctx.cache["lab"]
    return d if isinstance(d, dict) else None


def _process_verdict(ctx: ProbeCtx, *, pid: Any, module: str, stamp: Optional[datetime],
                     cadence: timedelta, what: str) -> ProbeResult:
    """Shared rule: the pid must answer with `module` in its command line AND
    the stamp must be inside cadence. A dead pid is DEAD whatever the stamp says."""
    cl = _cmdline(ctx, pid) if pid else None
    age = _age(stamp, ctx.now)
    stamp_s = _iso(stamp)
    if not pid:
        return _unknown(f"{what}: no pid recorded, so liveness cannot be derived",
                        evidence_utc=stamp_s, age_s=age)
    if cl is None:
        return ProbeResult("DEAD", stamp_s, age,
                           f"{what}: pid {pid} is not running (last evidence "
                           f"{_fmt_age(age)} old)", proof=f"pid {pid} not in the process table")
    if cl == "":
        return _unknown(f"{what}: pid {pid} exists but its command line is unreadable, so it "
                        f"cannot be confirmed as {module}", evidence_utc=stamp_s, age_s=age)
    if module not in cl.replace("\\", "/").replace("/", "."):
        return ProbeResult("DEAD", stamp_s, age,
                           f"{what}: pid {pid} was reused by another program "
                           f"({cl[:80]!r}); {module} is not running",
                           proof=f"pid {pid} cmdline lacks {module}")
    if stamp is None:
        return _unknown(f"{what}: pid {pid} answers but no dated heartbeat exists")
    if _by_age(stamp, cadence, ctx.now) == "ALIVE":
        return ProbeResult("ALIVE", stamp_s, age, f"{what}: heartbeat {_fmt_age(age)} old",
                           proof=f"pid {pid} cmdline contains {module}")
    return ProbeResult("STALE", stamp_s, age,
                       f"{what}: pid {pid} answers but its heartbeat is {_fmt_age(age)} old "
                       f"(cadence {_fmt_age(cadence.total_seconds())})",
                       proof=f"pid {pid} cmdline contains {module}")


#: The lab's own name for a deliberate stop (`always_on_lab.EXIT_REASONS`).
LAB_OPERATOR_STOP_REASONS = ("STOP_file",)


def _lab_stop_record(ctx: ProbeCtx, d: dict) -> Optional[dict]:
    """The lab's record of a DELIBERATE stop, or None.

    Two places the lab writes it on the way out, both for the SAME pid:
    `lab_status.json` (`running: false`, `stopped_by`) and the lock's
    `exit_reason`. A STOP file on disk is NOT a record: it can be left behind,
    or written after a crash."""
    if d.get("running") is False and str(d.get("stopped_by")) in LAB_OPERATOR_STOP_REASONS:
        return {"source": "lab_status.json", "reason": d.get("stopped_by"),
                "utc": d.get("utc"), "pid": d.get("pid")}
    lock = _read_json(ctx.optimus_dir / "always_on_lab_lock.json")
    if (isinstance(lock, dict) and str(lock.get("exit_reason")) in LAB_OPERATOR_STOP_REASONS
            and str(lock.get("pid")) == str(d.get("pid"))):
        return {"source": "always_on_lab_lock.json", "reason": lock.get("exit_reason"),
                "utc": lock.get("exit_utc"), "pid": lock.get("pid")}
    return None


def p_always_on_lab(ctx: ProbeCtx) -> ProbeResult:
    d = _lab_status(ctx)
    from backend import config as C                                 # noqa: PLC0415
    marker = ctx.optimus_dir / str(getattr(C, "ALWAYS_ON_LAB_OFF_MARKER", "always_on_lab_OFF"))
    if marker.exists():
        # 2026-10-02: OFF is a persistent marker every launcher honours. A lab
        # process alive while it exists is a VIOLATION (DEAD verdict: the
        # guardrail failed), not a healthy lab.
        # dated by the stamp WRITTEN IN the marker, never its mtime (protocol 7)
        try:
            m = re.search(r"\d{4}-\d{2}-\d{2}T[0-9:+\-Z.]+",
                          marker.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            m = None
        mt = _ts(m.group(0)) if m else None
        if d is not None:
            r = _process_verdict(ctx, pid=d.get("pid"), module="always_on_lab",
                                 stamp=_ts(d.get("utc")),
                                 cadence=timedelta(minutes=float(d.get("heartbeat_minutes") or 5)),
                                 what="always_on_lab")
            if r.verdict == "ALIVE":
                return ProbeResult("DEAD", r.evidence_utc, r.age_s,
                                   f"always_on_lab: OFF marker present since {_iso(mt)} but the "
                                   f"lab is RUNNING (pid {d.get('pid')}) -- a launcher ignored it",
                                   proof=f"{marker.name} exists AND {r.proof}")
        return ProbeResult("STOPPED_BY_OPERATOR", _iso(mt), _age(mt, ctx.now),
                           f"always_on_lab: OFF (marker {marker.name}, since {_iso(mt) or 'an undated write'}); "
                           f"no launcher starts it until the marker is deleted",
                           proof=f"{marker} exists")
    if d is None:
        return _unknown("no readable lab_status.json")
    hb = float(d.get("heartbeat_minutes") or 5)
    r = _process_verdict(ctx, pid=d.get("pid"), module="always_on_lab",
                         stamp=_ts(d.get("utc")), cadence=timedelta(minutes=hb),
                         what="always_on_lab")
    if r.verdict != "DEAD":
        return r
    stop = _lab_stop_record(ctx, d)
    if stop is None:
        return r
    t = _ts(stop.get("utc"))
    return ProbeResult("STOPPED_BY_OPERATOR", _iso(t), _age(t, ctx.now),
                       f"always_on_lab: stopped on purpose ({stop['reason']}) "
                       f"{_fmt_age(_age(t, ctx.now))} ago, pid {stop.get('pid')}; "
                       f"nothing restarts it until a human does",
                       proof=f"{stop['source']} records {stop['reason']} for pid {stop.get('pid')}")


def p_lab_loops(ctx: ProbeCtx) -> ProbeOut:
    d = _lab_status(ctx)
    if d is None or not isinstance(d.get("loops"), dict):
        return _unknown("no lab_status.json loops block")
    lab = p_always_on_lab(ctx)
    if lab.verdict == "STOPPED_BY_OPERATOR":
        # the loops of a lab a human stopped are not stalled, they are off
        return {name: ProbeResult("STOPPED_BY_OPERATOR", lab.evidence_utc, lab.age_s,
                                  f"loop {name}: the lab was stopped on purpose",
                                  proof=lab.proof)
                for name, row in d["loops"].items() if isinstance(row, dict)}             or _unknown("lab_status.json has an empty loops block")
    periods = d.get("periods_minutes") or {}
    out: dict[str, ProbeResult] = {}
    for name, row in d["loops"].items():
        if not isinstance(row, dict):
            continue
        stamp = _ts(row.get("tick_utc") or row.get("last_tick_utc"))
        per = periods.get(name) or row.get("cadence_minutes")
        if stamp is None or not per:
            out[name] = _unknown(f"loop {name}: no dated tick or no declared period")
            continue
        age = _age(stamp, ctx.now)
        st = str(row.get("status"))
        within = age <= float(per) * 60 * 2
        bad = st in ("error", "timeout")
        v: Verdict = "ALIVE" if within and not bad else "STALE"
        why = (f"status {st}" + (f" ({row.get('reason')})" if row.get("reason") else "")
               + f", last tick {_fmt_age(age)} ago (period {per} min)")
        out[name] = ProbeResult(v, _iso(stamp), age, why,
                                proof=f"lab_status.loops.{name}.last_tick_utc")
    return out or _unknown("lab_status.json has an empty loops block")


def _sim_owner_row(ctx: ProbeCtx) -> tuple[Optional[dict], Optional[float]]:
    """The sim owner's newest receipt row and its age in seconds (by its stamp)."""
    row = _last_json_row(ctx.optimus_dir / "sim" / "owner.jsonl")
    if not isinstance(row, dict):
        return None, None
    return row, _age(_ts(row.get("utc")), ctx.now)


def _plan_census(ctx: ProbeCtx) -> str:
    """Plans written and orders SENT in the newest pc_book day (review C2 F6):
    a heartbeat says the loop lives, not that the account trades."""
    try:
        days = sorted(p for p in (ctx.optimus_dir / "pc_book").glob("20??-??-??")
                      if (p / "decisions.jsonl").is_file())
    except OSError:
        days = []
    if not days:
        return "plans today: none written"
    n_plans = n_sent = 0
    last = None
    for line in _tail_lines(days[-1] / "decisions.jsonl", 8 * 1024 * 1024):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        n_plans += 1
        last = _ts(rec.get("t")) or last
        n_sent += sum(1 for x in rec.get("sent") or []
                      if isinstance(x, dict) and str(x.get("status")) not in ("skipped", "FAILED"))
    return (f"plans {days[-1].name}: {n_plans}, last {_fmt_age(_age(last, ctx.now))} ago, "
            f"orders sent {n_sent}")


def _owner_max_age_s() -> float:
    try:
        from backend import config as C                             # noqa: PLC0415
        return float(getattr(C, "SIM_OWNER_RECEIPT_MAX_AGE_MIN", 75)) * 60.0
    except Exception:                                               # noqa: BLE001
        return 75 * 60.0


def p_sim_session(ctx: ProbeCtx) -> ProbeResult:
    """The sim session, and -- when none runs in US hours -- its OWNER's word.

    Until 2026-10-06 nothing scheduled a session, so "no sim in US hours" was
    always DEAD. The owner (`task_keeper sim`, task AegisSimOwner) now writes a
    row on every firing: a fresh refusal is REFUSED with its reason, the
    owner's pause is STOPPED_BY_OPERATOR, a start whose session is gone and a
    silent owner are DEAD.
    """
    s = _read_json(ctx.optimus_dir / "sim" / "session.json")
    if not isinstance(s, dict):
        last = _last_json_row(ctx.optimus_dir / "sim" / "sessions.jsonl")
        s = last if isinstance(last, dict) else None
    if not s:
        return _unknown("no sim/session.json and no sim/sessions.jsonl row")
    state = str(s.get("state", "?"))
    hb = _ts(s.get("heartbeat"))
    trading_now = in_session_hours(ctx.now)
    owner, owner_age = _sim_owner_row(ctx)
    if state in ("RUNNING", "STOPPING"):
        r = _process_verdict(ctx, pid=s.get("pid"), module="sim_run", stamp=hb,
                             cadence=timedelta(minutes=10), what=f"sim {s.get('id')} {state}")
        if r.verdict == "DEAD":
            r.detail += " -- UNCLEAN: no stop receipt was written"
        r.detail += f" (mode {s.get('mode')}); {_plan_census(ctx)}"
        if r.verdict == "ALIVE" and str(s.get("mode")) != "paper_profit":
            r = ProbeResult("ALIVE_OBSERVE_ONLY", r.evidence_utc, r.age_s,
                            r.detail + " -- the session cannot place orders", proof=r.proof)
        if owner and owner.get("session") == s.get("id") and owner.get("trade_refused"):
            r.detail += f"; trading refused by the owner: {owner['trade_refused']}"
        return r
    ended = _ts(s.get("ended")) or hb
    last = f"last session {s.get('id')} {state}, ended {_fmt_age(_age(ended, ctx.now))} ago"
    if trading_now:
        fresh = owner is not None and owner_age is not None and owner_age <= _owner_max_age_s()
        if not fresh:
            return ProbeResult("DEAD", _iso(ended), _age(ended, ctx.now),
                               f"US session is open and no sim is running ({last}); the sim "
                               f"owner (task AegisSimOwner) has "
                               + ("never written a receipt" if owner is None else
                                  f"not written a receipt for {_fmt_age(owner_age)}"),
                               proof=f"sim/session.json state={state}; sim/owner.jsonl")
        act = str(owner.get("action"))
        why = str(owner.get("why") or "")
        stamp = _ts(owner.get("utc"))
        proof = f"sim/owner.jsonl run {owner.get('run_id')} action={act}"
        if act in ("paused", "stopped_by_operator"):
            return ProbeResult("STOPPED_BY_OPERATOR", _iso(stamp), owner_age,
                               f"no sim in US hours, on purpose: {why} ({last})", proof=proof)
        if act in ("refused", "outside_window"):
            return ProbeResult("REFUSED", _iso(stamp), owner_age,
                               f"no sim in US hours: the owner REFUSED {_fmt_age(owner_age)} "
                               f"ago -- {why} ({last})", proof=proof)
        return ProbeResult("DEAD", _iso(ended), _age(ended, ctx.now),
                           f"US session is open and no sim is running ({last}); the owner's "
                           f"last row ({act}, {_fmt_age(owner_age)} ago, session "
                           f"{owner.get('session')}) says it should be", proof=proof)
    nxt = ("the sim owner (AegisSimOwner) starts the next one in its US/Eastern window"
           if owner is not None else "the sim owner has never fired (register AegisSimOwner)")
    return ProbeResult("ALIVE", _iso(ended), _age(ended, ctx.now),
                       f"idle outside US hours: {last} ({s.get('end_reason') or '-'}); {nxt}",
                       proof=f"sim/session.json state={state}")


def p_live_market_loop(ctx: ProbeCtx) -> ProbeResult:
    newest = None
    try:
        for nav in sorted((ctx.optimus_dir / "pc_book").glob("*/nav.jsonl")):
            for line in _tail_lines(nav, 4 * 1024 * 1024):
                if '"open_of_loop"' in line or '"close_of_loop"' in line:
                    try:
                        t = _ts(json.loads(line).get("t"))
                    except ValueError:
                        continue
                    if t and (newest is None or t > newest):
                        newest = t
    except OSError:
        pass
    if newest is None:
        if not (ctx.optimus_dir / "pc_book").exists():
            return _unknown("no pc_book folder")
        return ProbeResult("STALE", None, None,
                           "no NAV row tagged open_of_loop/close_of_loop in any "
                           "pc_book/*/nav.jsonl -- live_market_loop has never run end-to-end "
                           "(its role is done by sim_run)", proof="0 tagged rows")
    last = last_closed_session(ctx.now)
    v: Verdict = "ALIVE" if newest.date() >= last else "STALE"
    return ProbeResult(v, _iso(newest), _age(newest, ctx.now),
                       f"newest loop-tagged NAV row {newest.date()} (last session {last})",
                       proof="pc_book/*/nav.jsonl tag open_of_loop")


_RA = re.compile(r'"resolves_after":\s*"([^"]+)"')
_RS = re.compile(r'"resolved_at":\s*(?:null|"([^"]*)")')
_MA = re.compile(r'"made_at":\s*"([^"]+)"')


def _ledger_scan(ctx: ProbeCtx) -> Optional[dict]:
    if "ledger" in ctx.cache:
        return ctx.cache["ledger"]
    p = ctx.optimus_dir / "predictions.jsonl"
    out: Optional[dict] = None
    if p.exists():
        today = ctx.now.date().isoformat()
        rows = made_today = due_unresolved = 0
        newest_made = newest_resolved = None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rows += 1
                    m = _MA.search(line)
                    if m:
                        if newest_made is None or m.group(1) > newest_made:
                            newest_made = m.group(1)
                        if m.group(1)[:10] == today:
                            made_today += 1
                    r = _RS.search(line)
                    if r and r.group(1):
                        if newest_resolved is None or r.group(1) > newest_resolved:
                            newest_resolved = r.group(1)
                    else:
                        a = _RA.search(line)
                        if a and a.group(1)[:10] < today:
                            due_unresolved += 1
            out = {"rows": rows, "made_today": made_today, "due_unresolved": due_unresolved,
                   "newest_made": newest_made, "newest_resolved": newest_resolved}
        except OSError:
            out = None
    ctx.cache["ledger"] = out
    return out


_SP = re.compile(r'"specialist":\s*"([^"]*)"')


def _writer_scan(ctx: ProbeCtx, writers: dict, since: str) -> Optional[dict]:
    """Rows per registered forecast WRITER with made_at >= `since` (ISO, UTC)."""
    key = ("writers", since)
    if key in ctx.cache:
        return ctx.cache[key]
    p = ctx.optimus_dir / "predictions.jsonl"
    out: Optional[dict] = None
    if p.exists():
        counts = {w: 0 for w in writers}
        newest = {w: None for w in writers}
        other = 0
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = _MA.search(line)
                    if not m:
                        continue
                    s = _SP.search(line)
                    spec = s.group(1) if s else ""
                    w = next((k for k, d in writers.items()
                              if spec.startswith(str(d.get("prefix") or "\0"))), None)
                    if w is not None and (newest[w] is None or m.group(1) > newest[w]):
                        newest[w] = m.group(1)
                    # `since` is a UTC midnight, so the date prefix decides
                    if m.group(1)[:10] < since[:10]:
                        continue
                    if w is None:
                        other += 1
                    else:
                        counts[w] += 1
            out = {"counts": counts, "newest": newest, "unregistered": other}
        except OSError:
            out = None
    ctx.cache[key] = out
    return out


def p_u_forecast(ctx: ProbeCtx) -> ProbeResult:
    """PER WRITER, not per ledger (2026-09-28).

    It read `max(made_at)` over every specialist, so on 2026-09-27 167
    thesis-card and source rows printed `u_forecast ALIVE` while the unit it is
    named after (`investigator:evidence_v3`) wrote 0 -- 2026-08-27 -> 09-25's
    dead ledger in a new shape. Now: for each writer in
    `config.FORECAST_WRITERS`, `new_rows_since_last_session` (a `utc_day`
    writer's last session is the previous UTC day, so the window opens at its
    00:00Z). A SCHEDULED writer with zero is DEGRADED by name, and so is one
    whose day receipt today carries a refusal. Unscheduled writers are
    reported and never graded -- they cannot make the probe green.
    """
    from backend import config as C                                 # noqa: PLC0415
    writers = dict(getattr(C, "FORECAST_WRITERS", None) or {})
    if not writers:
        return _unknown("config.FORECAST_WRITERS is empty: no writer to count")
    today = ctx.now.astimezone(timezone.utc).date()
    since = datetime.combine(today - timedelta(days=1), dtime(0, 0), tzinfo=timezone.utc)
    W = _writer_scan(ctx, writers, _iso(since))
    if W is None:
        return _unknown("no forecast ledger (predictions.jsonl) to count writers in")
    bad, parts, n_sched = [], [], 0
    for w, d in writers.items():
        n = W["counts"].get(w, 0)
        if not d.get("scheduled"):
            parts.append(f"{w} {n} (unscheduled, reported only)")
            continue
        n_sched += n
        why = []
        if n == 0:
            why.append(f"0 rows since {since:%Y-%m-%dT%H:%MZ}")
        rel = str(d.get("receipt") or "")
        if rel:
            rc = _read_json(ctx.optimus_dir / rel.format(day=today.isoformat()))
            st = rc.get("state") if isinstance(rc, dict) else None
            if st and (str(st).startswith("REFUSED") or st == "DEGRADED"):
                why.append(f"today's receipt {st}: {str(rc.get('why') or '')[:90]}")
        if why:
            bad.append(w)
            parts.append(f"{w} DEGRADED ({d.get('prefix')}): " + "; ".join(why)
                         + f"; newest {W['newest'].get(w) or 'never'}")
        else:
            parts.append(f"{w} {n} since {since:%Y-%m-%d}")
    newest_sched = [_ts(W["newest"][w]) for w, d in writers.items()
                    if d.get("scheduled") and W["newest"].get(w)]
    ev = max([t for t in newest_sched if t], default=None)
    v: Verdict = "STALE" if bad else "ALIVE"
    return ProbeResult(v, _iso(ev), _age(ev, ctx.now) if ev else None,
                       ("DEGRADED: " + ", ".join(bad) + " | " if bad else "")
                       + "; ".join(parts)
                       + f"; unregistered writers {W['unregistered']}",
                       delta=n_sched,
                       proof="predictions.jsonl per config.FORECAST_WRITERS prefix, "
                             "made_at >= previous UTC day + forecasts/day_<today>.json")


def p_forecast_ledger(ctx: ProbeCtx) -> ProbeResult:
    L = _ledger_scan(ctx)
    if not L:
        return _unknown("no forecast ledger")
    prev = ctx.prev_state.get("ledger") or {}
    ctx.new_state["ledger"] = {"rows": L["rows"], "utc": _iso(ctx.now)}
    prev_at = _ts(prev.get("utc"))
    if prev_at is None or prev.get("rows") is None:
        return _unknown(f"{L['rows']} rows; no previous probe run to diff against, so "
                        f"new_rows_since_last_run cannot be computed yet")
    delta = L["rows"] - int(prev["rows"])
    since = _age(prev_at, ctx.now)
    if delta > 0:
        return ProbeResult("ALIVE", _iso(ctx.now), 0.0,
                           f"{delta} new row(s) since the previous probe {_fmt_age(since)} ago",
                           delta=delta, proof="predictions.jsonl line count delta")
    # a zero delta is a finding only once the producer was due
    if since is not None and since >= 86400:
        return ProbeResult("STALE", _iso(prev_at), since,
                           f"DEGRADED: new_rows_since_last_run = {delta} over "
                           f"{_fmt_age(since)} -- a scoreboard over a dead ledger is green forever",
                           delta=delta, proof="predictions.jsonl line count delta")
    nm = _ts(L["newest_made"])
    v = "ALIVE" if nm and nm.date() >= last_closed_session(ctx.now) else "STALE"
    return ProbeResult(v, _iso(nm), _age(nm, ctx.now),
                       f"new_rows_since_last_run = {delta} over {_fmt_age(since)} "
                       f"(not yet a day); newest made_at {_iso(nm)}",
                       delta=delta, proof="predictions.jsonl line count delta")


def p_u_review(ctx: ProbeCtx) -> ProbeResult:
    last = last_closed_session(ctx.now)
    folder = ctx.optimus_dir / "review"
    p = folder / f"review_{last.isoformat()}.json"
    d = _read_json(p)
    if isinstance(d, dict):
        dt = _ts(d.get("generated_utc")) or _ts(d.get("asof"))
        return ProbeResult("ALIVE", _iso(dt), _age(dt, ctx.now),
                           f"review for {last} written ({d.get('n_rows', '?')} rows)",
                           proof=f"review/{p.name} generated_utc")
    newest = None
    try:
        names = sorted(x.name for x in folder.glob("review_20??-??-??.json"))
        newest = names[-1] if names else None
    except OSError:
        pass
    if newest is None:
        return _unknown(f"no review receipts in {folder}")
    nd = _ts(newest[7:17])
    return ProbeResult("STALE", _iso(nd), _age(nd, ctx.now),
                       f"no review for the last session {last}; newest is {newest}",
                       proof=f"review/{newest}")


def p_u_plan(ctx: ProbeCtx) -> ProbeResult:
    day = _newest_pc_book(ctx)
    d = _read_json(day / "intended_book.json") if day else None
    if not isinstance(d, dict):
        return _unknown("no pc_book/<day>/intended_book.json")
    t = _ts(d.get("t"))
    asof = _ts(d.get("asof"))
    if t is None or asof is None:
        return _unknown("intended_book.json lacks a `t` or `asof` stamp")
    last = last_closed_session(ctx.now)
    fresh = asof.date() >= last
    notes = [f"plan t={_iso(t)} asof {asof.date()} (last session {last}), acting={d.get('acting')}, "
             f"n_to_send={d.get('n_to_send', '?')}"]
    v: Verdict = "ALIVE" if fresh else "STALE"
    inv = d.get("invested_frac")
    try:
        from backend import config as C                             # noqa: PLC0415
        cap = float(getattr(C, "PROBE_GROSS_CAP", 0.20))
    except Exception:                                               # noqa: BLE001
        cap = 0.20
    if inv is not None:
        try:
            if float(inv) > cap + 0.05:
                v = "STALE"
                notes.append(f"holdings exceed cap: invested_frac {float(inv):.2f} > "
                             f"PROBE_GROSS_CAP {cap:.2f}")
        except (TypeError, ValueError):
            pass
    else:
        notes.append("invested_frac not in the receipt, cap check not possible")
    ranking = _read_json(day / "ranking.json") if day else None
    if isinstance(ranking, dict) and ranking.get("asof"):
        ra = _ts(ranking["asof"])
        n = sessions_behind(ra.date(), last) if ra else None
        notes.append(f"acting on a ranking as of {ranking['asof']} ({n} session(s) old)")
        if n is not None and n > _bars_limit() and d.get("acting"):
            v = "STALE"
    return ProbeResult(v, _iso(t), _age(t, ctx.now), "; ".join(notes),
                       proof=f"{day.name}/intended_book.json")


#: `policy_state` is STALE when no plan in this many sessions READ it.
POLICY_STATE_READ_SESSIONS = 2


def p_policy_state(ctx: ProbeCtx) -> ProbeResult:
    """Was the night's learning READ by a plan? (review 2026-09-26 item 7)

    `policy_state.json` is refreshed every night; for a month nothing on the
    paper path read it. ALIVE only when some `u_plan` receipt
    (`pc_book/<day>/decisions.jsonl`) whose `asof` is within the last
    `POLICY_STATE_READ_SESSIONS` sessions carries `policy_state_used`.
    Otherwise STALE -- including when the newest plan says
    `policy_state_ignored` (the reason is printed) and when the state was
    written but no plan ran: write-only learning is the failure this row exists
    to show. No state file and no plan at all is UNKNOWN (no evidence).
    """
    book = ctx.optimus_dir / "pc_book"
    st = _read_json(book / "policy_state.json")
    refreshed = _ts(st.get("refreshed_utc") or st.get("updated")) if isinstance(st, dict) else None
    last = last_closed_session(ctx.now)
    try:
        days = sorted((x for x in book.iterdir()
                       if x.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x.name)),
                      reverse=True)[:7]
    except OSError:
        days = []
    newest_used, newest_plan = None, None
    for day in days:
        for line in reversed(_tail_lines(day / "decisions.jsonl", 1 << 20)):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or "verdict" not in row or not row.get("asof"):
                continue
            a = _ts(row["asof"])
            if a is None or sessions_behind(a.date(), last) > POLICY_STATE_READ_SESSIONS:
                continue
            newest_plan = newest_plan or (day.name, row)
            if isinstance(row.get("policy_state_used"), dict):
                newest_used = (day.name, row)
                break
        if newest_used:
            break
    ref = (f"policy_state.json refreshed {_iso(refreshed)}" if refreshed
           else "policy_state.json missing or undated")
    if newest_used:
        day, row = newest_used
        t = _ts(row.get("t"))
        u = row["policy_state_used"]
        return ProbeResult("ALIVE", _iso(t), _age(t, ctx.now),
                           f"plan asof {row['asof']} read it: age {u.get('age_sessions')} "
                           f"session(s), order: {str(u.get('order_source'))[:90]}, "
                           f"weighting {u.get('probe_weighting')}; {ref}",
                           proof=f"pc_book/{day}/decisions.jsonl policy_state_used")
    if newest_plan:
        day, row = newest_plan
        t = _ts(row.get("t"))
        why = ((row.get("policy_state_ignored") or {}).get("reason")
               or (f"the plan was {row.get('verdict')} before reaching the reader"
                   if str(row.get("verdict", "")).startswith("REFUSED") else
                   "the plan predates the reader (no policy_state_used / _ignored field)"))
        return ProbeResult("STALE", _iso(t), _age(t, ctx.now),
                           f"WRITE-ONLY: the newest plan (asof {row['asof']}) did not read "
                           f"policy_state: {why}; {ref}",
                           proof=f"pc_book/{day}/decisions.jsonl")
    if refreshed is None:
        return _unknown(f"no dated pc_book/policy_state.json and no plan in the last "
                        f"{POLICY_STATE_READ_SESSIONS} session(s)")
    return ProbeResult("STALE", _iso(refreshed), _age(refreshed, ctx.now),
                       f"WRITE-ONLY: no plan in the last {POLICY_STATE_READ_SESSIONS} "
                       f"session(s) (to {last}) read policy_state; {ref}",
                       proof="pc_book/<day>/decisions.jsonl")


def p_decision_contract(ctx: ProbeCtx) -> ProbeResult:
    folder = ctx.optimus_dir / "decisions"
    newest = _newest_named(folder, "20??-??-??.json")
    d = _read_json(newest) if newest else None
    if not isinstance(d, dict):
        return _unknown(f"no dated decision contract in {folder}")
    dt = _ts(d.get("written_utc"))
    if dt is None:
        return _unknown(f"{newest.name} carries no written_utc")
    v = _by_age(dt, timedelta(days=1), ctx.now)
    state: Optional[str] = None
    detail = f"{newest.name} written {_fmt_age(_age(dt, ctx.now))} ago"
    try:
        from backend.services import accrual_canary as AC           # noqa: PLC0415
        nc = AC.n_considered_row(folder, ctx.path("funnel", ctx.optimus_dir.parent / "funnel_night10.json"))
        detail += f"; {nc.get('reason') or nc.get('line') or nc.get('status')}"
        if nc.get("status") == "DEGRADED":
            v = "STALE"
            # C8 (2026-10-07): say WHICH cause. After C2 refreshed the funnel the
            # number is static because the eligibility gate passes the same few
            # names, not because the candidate file is old.
            cause = _n_considered_cause(d)
            detail += "; CAUSE: " + cause
            if cause.startswith("NOT a stale file"):
                state = "DEGRADED"
    except Exception as exc:                                        # noqa: BLE001
        detail += f"; n_considered row unavailable ({type(exc).__name__})"
    return ProbeResult(v, _iso(dt), _age(dt, ctx.now), detail,
                       proof=f"decisions/{newest.name} written_utc",
                       state=state if v == "STALE" else None)


def _n_considered_cause(contract: dict) -> str:
    """Why n_considered is not moving, from the contract's own candidate_set."""
    cs = contract.get("candidate_set") or {}
    n_c, n_k = cs.get("n_candidates"), cs.get("n_considered")
    age = cs.get("candidates_age_days")
    try:
        from backend.services import investment_committee as IC     # noqa: PLC0415
        limit = float(IC.FUNNEL_STALE_DAYS)
    except Exception:                                               # noqa: BLE001
        limit = 10.0
    if n_c is None or age is None:
        return "the contract carries no candidate_set, so stale-file vs eligibility cannot be told apart"
    if float(age) > limit:
        return (f"a STALE candidate file: {n_c} candidates generated {float(age):.1f} d ago "
                f"(limit {limit:g} d)")
    ex = cs.get("excluded_by_gate") or {}
    ex_txt = ", ".join(f"{v} {k}" for k, v in sorted(ex.items(), key=lambda kv: -kv[1])) or "not itemised"
    return (f"NOT a stale file -- the candidate set is fresh ({n_c} candidates, {float(age):.1f} d old); "
            f"only {n_k} of {n_c} pass the eligibility gate (excluded: {ex_txt})")


def _daily_pass_receipt(ctx: ProbeCtx, day: date) -> Optional[dict]:
    d = _read_json(ctx.optimus_dir / f"night_factory_{day}" / f"daily_pass_{day}.json")
    return d if isinstance(d, dict) else None


def _newest_daily_pass(ctx: ProbeCtx, back: int = 7) -> tuple[Optional[date], Optional[dict]]:
    for i in range(back + 1):
        day = ctx.now.date() - timedelta(days=i)
        d = _daily_pass_receipt(ctx, day)
        if d:
            return day, d
    return None, None


def _step(receipt: dict, name: str) -> Optional[dict]:
    for s in receipt.get("steps") or []:
        if isinstance(s, dict) and s.get("step") == name:
            return s
    return None


def p_forecast_grader(ctx: ProbeCtx) -> ProbeResult:
    L = _ledger_scan(ctx)
    if not L:
        return _unknown("no forecast ledger")
    newest = _ts(L["newest_resolved"])
    notes = [f"{L['due_unresolved']} due-but-unresolved row(s); newest resolved_at "
             f"{L['newest_resolved']}"]
    _, dp = _newest_daily_pass(ctx)
    wait = None
    if dp:
        st = _step(dp, "grade_forecasts") or {}
        m = re.search(r"([\d,]+) wait on a bar", str(st.get("headline", "")))
        if m:
            wait = int(m.group(1).replace(",", ""))
            notes.append(f"{wait} wait on a bar (daily_pass)")
    prev = ctx.prev_state.get("no_bar") or {}
    first_seen = _ts(prev.get("since")) if prev.get("count") else None
    if wait:
        first_seen = first_seen or ctx.now
        ctx.new_state["no_bar"] = {"count": wait, "since": _iso(first_seen)}
    if newest is None:
        if L["due_unresolved"]:
            return ProbeResult("STALE", None, None,
                               "; ".join(notes) + " -- no row has EVER resolved while due rows exist",
                               proof="predictions.jsonl resolved_at")
        return _unknown("no resolved row and nothing due; the grader has not been exercised")
    age = _age(newest, ctx.now)
    v: Verdict = "ALIVE"
    if L["due_unresolved"] and age > 86400 * (1 + GRACE) + 86400:
        v = "STALE"
        notes.append("resolved_at has not moved while due rows exist")
    if wait and first_seen and (ctx.now - first_seen).days > NO_BAR_STALE_DAYS:
        v = "STALE"
        notes.append(f"rows have waited on a bar for > {NO_BAR_STALE_DAYS} d")
    return ProbeResult(v, _iso(newest), age, "; ".join(notes),
                       proof="predictions.jsonl max(resolved_at) vs due rows")


#: The daily pass's book-grading steps (2026-09-27). A row of theirs that is
#: refused / error / timeout makes `book_grader` non-ALIVE: the step never fails
#: the pass, so this probe is where its failure turns a row red.
BOOK_GRADE_STEPS = ("grade_books", "paper_accounts", "bridge_report")
#: The llm_portfolio leaderboard is STALE when its `bars_through` is MORE than
#: this many closed sessions behind the last one (one missed pass is tolerated).
LLM_BOARD_MAX_SESSIONS_BEHIND = 1


def _llm_books(ctx: ProbeCtx) -> tuple[list[dict], set]:
    """(non-void book records, void ids) from `llm_portfolio/books.jsonl`."""
    books, voids = [], set()
    try:
        text = (ctx.optimus_dir / "llm_portfolio" / "books.jsonl").read_text(encoding="utf-8")
    except OSError:
        return [], set()
    for line in text.splitlines():
        try:
            x = json.loads(line)
        except ValueError:
            continue
        if not isinstance(x, dict):
            continue
        if x.get("schema") == "llm_portfolio/void":
            voids.add(x.get("book_id"))
        elif x.get("book_id"):
            books.append(x)
    return [b for b in books if b.get("book_id") not in voids], voids


def _book_steps(ctx: ProbeCtx) -> tuple[Optional[list], str]:
    """The book-grading step rows: the CURRENT pass's (the daily pass hands its
    rows in as `ctx.cache["daily_pass_rows"]`, because its own receipt is
    written after this probe runs), else the newest receipt on disk."""
    rows = ctx.cache.get("daily_pass_rows")
    if rows is not None:
        return list(rows), "this daily pass"
    for i in range(-1, 8):
        day = ctx.now.date() - timedelta(days=i)
        d = _daily_pass_receipt(ctx, day)
        if d:
            return list(d.get("steps") or []), f"daily_pass_{day}.json"
    return None, "no daily_pass receipt"


def p_book_grader(ctx: ProbeCtx) -> ProbeResult:
    """Every graded book, from the evidence each grader wrote.

    Three parts, the worst wins; a part with no evidence is NAMED, never ALIVE:
    (1) the paper-book scoreboard (`daily_pass scoreboard.nav_vs_spy`), 0
    sessions behind or STALE; (2) the llm_portfolio leaderboard: STALE when its
    `bars_through` is more than `LLM_BOARD_MAX_SESSIONS_BEHIND` session(s)
    behind the last closed session, or when a book past its entry is on no
    board (UNGRADED); its PENDING / UNGRADED / REFUSED counts are printed;
    (3) the daily pass's `grade_books` / `paper_accounts` / `bridge_report`
    rows: any refused / error / timeout is STALE by name."""
    last = last_closed_session(ctx.now)
    verdicts: list[Verdict] = []
    notes: list[str] = []
    evidence: Optional[datetime] = None

    # (1) the paper-book scoreboard, as before
    _, dp = _newest_daily_pass(ctx)
    lb = _newest_named(ctx.optimus_dir / "strategy_library", "leaderboard_*T*Z.json")
    lb_s = ""
    if lb:
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)", lb.name)
        if m:
            lbt = datetime.strptime(m.group(1), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            lb_s = f"; newest library leaderboard {lb.name} ({_fmt_age(_age(lbt, ctx.now))} old)"
    nvs = ((dp or {}).get("scoreboard") or {}).get("nav_vs_spy") or {}
    ld = _ts((nvs.get("window") or {}).get("last_date"))
    if ld is None:
        notes.append("paper books: no daily_pass scoreboard.nav_vs_spy.window.last_date")
    else:
        n = sessions_behind(ld.date(), last)
        verdicts.append("ALIVE" if n == 0 else "STALE")
        notes.append(f"paper books graded through {ld.date()}, {n} session(s) behind {last}")
        evidence = ld

    # (2) the llm_portfolio leaderboard
    books, _voids = _llm_books(ctx)
    board_p = _newest_named(ctx.optimus_dir / "llm_portfolio", "leaderboard_*.json")
    board = _read_json(board_p) if board_p else None
    past_entry = [b for b in books if (_ts(b.get("asof")) is not None
                                       and _ts(b.get("asof")).date() < last)]
    if isinstance(board, dict):
        graded_ids = {r.get("book_id") for r in board.get("books") or []}
        ungraded = [b for b in past_entry if b.get("book_id") not in graded_ids]
        sc = dict(board.get("status_counts") or {})
        if not sc:                        # a board written before status_counts existed
            for r in board.get("books") or []:
                sc[str(r.get("status"))] = sc.get(str(r.get("status")), 0) + 1
        refused = sum(v for k, v in sc.items() if str(k).startswith("REFUSED"))
        counts = (f"PENDING {sc.get('PENDING', 0)}, UNGRADED {len(ungraded)}, "
                  f"REFUSED {refused}, OK {sc.get('OK', 0)}")
        bt = _ts(board.get("bars_through"))
        if bt is None:
            verdicts.append("STALE")
            notes.append(f"llm books: {board_p.name} carries no bars_through ({counts})")
        else:
            n = sessions_behind(bt.date(), last)
            bad = n > LLM_BOARD_MAX_SESSIONS_BEHIND or bool(ungraded)
            verdicts.append("STALE" if bad else "ALIVE")
            notes.append(f"llm books: {board_p.name} bars through {bt.date()}, {n} session(s) "
                         f"behind {last} (limit {LLM_BOARD_MAX_SESSIONS_BEHIND}); {counts}"
                         + (f"; ungraded past entry: {[b.get('name') for b in ungraded[:5]]}"
                            if ungraded else ""))
        gt = _ts(board.get("graded_utc"))
        if gt and (evidence is None or gt > evidence):
            evidence = gt
    elif past_entry:
        verdicts.append("STALE")
        notes.append(f"llm books: no llm_portfolio leaderboard while {len(past_entry)} book(s) "
                     f"are past their entry: UNGRADED {len(past_entry)}")
    elif books:
        notes.append(f"llm books: {len(books)} book(s), none past entry yet, no leaderboard")
    else:
        notes.append("llm books: no llm_portfolio/books.jsonl")

    # (3) the daily pass's book-grading steps
    steps, src = _book_steps(ctx)
    if steps is not None:
        mine = {s_.get("step"): s_ for s_ in steps if isinstance(s_, dict)
                and s_.get("step") in BOOK_GRADE_STEPS}
        failed = [f"{k}={v.get('status')}" for k, v in mine.items()
                  if v.get("status") in ("refused", "error", "timeout")]
        if failed:
            verdicts.append("STALE")
            notes.append(f"book-grading steps failed in {src}: {failed}")
        elif mine:
            notes.append(f"book-grading steps in {src}: "
                         + ", ".join(f"{k}={v.get('status')}" for k, v in mine.items()))

    detail = "; ".join(notes) + lb_s
    if not verdicts:
        return _unknown(detail)
    v: Verdict = "STALE" if "STALE" in verdicts else "ALIVE"
    return ProbeResult(v, _iso(evidence), _age(evidence, ctx.now), detail,
                       proof=("daily_pass scoreboard.nav_vs_spy.window.last_date + "
                              "llm_portfolio/leaderboard_<day>.json bars_through/status_counts + "
                              "daily_pass steps grade_books/paper_accounts/bridge_report"))


def _session_report_gaps(ctx: ProbeCtx) -> list[str]:
    """The finished sim session's learning report, judged from its own rows.

    2026-10-02: ad32603783de COMPLETED 2026-09-29T23:56Z, its exit-time report
    raised into a logger, and this row said ok for three days. Now: the newest
    finished session in `sim/session.json` must have an `ok` row in
    `learning_reports/report_runs.jsonl`, or its day's report must carry a
    `generated_utc` after the session ended; a newest row of FAILED is named."""
    out: list[str] = []
    s = _read_json(ctx.optimus_dir / "sim" / "session.json") or {}
    s = s.get("session") if isinstance(s.get("session"), dict) else s
    if not isinstance(s, dict) or s.get("state") not in ("COMPLETED", "STOPPED"):
        return out
    sid = s.get("id")
    end = _ts(s.get("finished_utc") or s.get("ended_utc") or s.get("planned_end"))
    rows = []
    rp = ctx.optimus_dir / "learning_reports" / "report_runs.jsonl"
    try:
        for ln in rp.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("session") == sid:
                rows.append(r)
    except OSError:
        pass
    if rows and rows[-1].get("status") != "ok":
        return [f"learning report for session {sid} FAILED: {str(rows[-1].get('error'))[:80]}"]
    if rows:
        return out
    if end is not None:
        rep = _read_json(ctx.optimus_dir / "learning_reports" / f"report_{end.date().isoformat()}.json") or {}
        g = _ts(rep.get("generated_utc"))
        if g is not None and g >= end:
            return out
    out.append(f"session {sid} {s.get('state')} with NO learning report (no ok row, "
               f"no report generated after it ended)")
    return out


def p_learn_rota(ctx: ProbeCtx) -> ProbeResult:
    day = _newest_pc_book(ctx)
    files = sorted(day.glob("learn_*.json")) if day else []
    if not files:
        return _unknown("no pc_book/<day>/learn_*.json receipts")
    notes, bad, newest = [], [], None
    bars_newest = _bars_newest(ctx)
    for f in files:
        d = _read_json(f) or {}
        unit = f.stem[6:]
        t = _ts(d.get("ran_utc") or d.get("utc") or d.get("generated_utc"))
        if t and (newest is None or t > newest):
            newest = t
        st = d.get("status")
        if d.get("skipped"):
            bad.append(f"{unit}=skipped ({str(d['skipped'])[:30]})")
        elif st is not None:
            (bad if ("DEGRADED" in str(st) or str(st) in ("error", "timeout")) else notes).append(
                f"{unit}={str(st)[:24]}")
        elif d.get("panel_last_session"):
            pls = _ts(d["panel_last_session"])
            if bars_newest and pls and pls.date() < bars_newest:
                bad.append(f"{unit} computed on bars through {pls.date()} while the panel "
                           f"reaches {bars_newest} (not re-run)")
            else:
                notes.append(f"{unit}=current")
        else:
            notes.append(f"{unit}=undated result")
    bad.extend(_session_report_gaps(ctx))
    v: Verdict = "STALE" if bad else _by_age(newest, timedelta(days=1), ctx.now)
    if v == "UNKNOWN":
        return _unknown(f"learn receipts in {day.name} carry no run stamp")
    return ProbeResult(v, _iso(newest), _age(newest, ctx.now),
                       (f"cannot run / degraded: {', '.join(bad)}; " if bad else "")
                       + f"ok: {', '.join(notes) or 'none'} ({day.name})",
                       proof=f"pc_book/{day.name}/learn_*.json")


def _schtasks(ctx: ProbeCtx) -> Optional[dict]:
    """{task name: row dict} from `schtasks /query /fo CSV /v`, or None."""
    if "schtasks" in ctx.cache:
        return ctx.cache["schtasks"]
    out = None
    if ctx.allow_proc:
        rc, txt = _run(ctx, ["schtasks", "/query", "/fo", "CSV", "/v"], 60)
        if rc == 0 and txt:
            out = {}
            rows = list(csv.reader(io.StringIO(txt)))
            header = None
            for r in rows:
                if r and r[0] == "HostName":
                    header = r
                    continue
                if header and len(r) == len(header):
                    row = dict(zip(header, r))
                    name = row.get("TaskName", "").lstrip("\\")
                    if name.startswith("Aegis"):
                        out[name] = row
    ctx.cache["schtasks"] = out
    return out


def p_daily_pass(ctx: ProbeCtx) -> ProbeResult:
    today = ctx.now.date()
    # the pass for local date D starts at 06:30 HKT = the previous UTC evening
    d = _daily_pass_receipt(ctx, today) or _daily_pass_receipt(ctx, today + timedelta(days=1))
    tasks = _schtasks(ctx) or {}
    task = tasks.get("AegisDailyPass") or {}
    ts_note = (f"; schtasks Last Run {task.get('Last Run Time')} Last Result "
               f"{task.get('Last Result')} (cmd's rc, not the job's)") if task else ""
    if not d:
        dday, old = _newest_daily_pass(ctx)
        if old:
            t = _ts(old.get("finished_utc") or old.get("started_utc"))
            return ProbeResult("STALE", _iso(t), _age(t, ctx.now),
                               f"no daily_pass receipt for {today}; newest is {dday}" + ts_note,
                               proof=f"night_factory_{dday}/daily_pass_{dday}.json")
        return _unknown(f"no daily_pass receipt for {today} or the week before" + ts_note)
    steps = [s for s in d.get("steps") or [] if isinstance(s, dict)]
    stamps = [t for t in (_ts(s.get("utc")) for s in steps) if t]
    newest = max(stamps) if stamps else _ts(d.get("finished_utc"))
    errs = [s.get("step") for s in steps if s.get("status") in ("error", "timeout")]
    v: Verdict = "STALE" if errs else _by_age(newest, timedelta(days=1), ctx.now)
    if v == "UNKNOWN":
        return _unknown("daily_pass receipt has no dated step" + ts_note)
    return ProbeResult(v, _iso(newest), _age(newest, ctx.now),
                       f"{d.get('headline', '?')}" + (f"; errored: {errs}" if errs else "") + ts_note,
                       proof=f"daily_pass_{d.get('date')}.json steps[*].utc")


def p_iif1_night(ctx: ProbeCtx) -> ProbeResult:
    folder = ctx.optimus_dir / "iif1_nights"
    lastwd = ctx.now.date()
    # the night for weekday D is launched 16:00 HKT = 08:00 UTC
    if ctx.now.hour < 9:
        lastwd -= timedelta(days=1)
    while lastwd.weekday() >= 5:
        lastwd -= timedelta(days=1)
    d = _read_json(folder / f"{lastwd}.json")
    if isinstance(d, dict):
        t = _ts(d.get("actual_start_utc")) or _ts(lastwd)
        ok = d.get("status") == "ok"
        return ProbeResult("ALIVE" if ok else "STALE", _iso(t), _age(t, ctx.now),
                           f"night {lastwd}: status {d.get('status')} "
                           f"{d.get('void_reason') or ''}, spend ${float(d.get('spend_usd') or 0):.2f}",
                           proof=f"iif1_nights/{lastwd}.json status")
    newest = _newest_named(folder, "20??-??-??.json")
    if newest is None:
        return _unknown(f"no IIF-1 night receipts in {folder}")
    t = _ts(newest.stem)
    return ProbeResult("STALE", _iso(t), _age(t, ctx.now),
                       f"no receipt for weekday {lastwd}; newest {newest.name}",
                       proof=f"iif1_nights/{newest.name}")


def p_news_collectors(ctx: ProbeCtx) -> ProbeOut:
    corpus = ctx.optimus_dir / "news_corpus"
    rec = _newest_named(corpus / "_receipts", "*_ALL.json")
    d = _read_json(rec) if rec else None
    if not isinstance(d, dict):
        return _unknown(f"no news_corpus/_receipts/*_ALL.json")
    t = _ts(d.get("written_utc"))
    red = list(d.get("red") or []) + list(d.get("refused") or [])
    v = _by_age(t, timedelta(minutes=30), ctx.now)
    if v == "ALIVE" and red:
        v = "STALE"
    # newest first_seen_utc per source, from each source's newest day file
    stale_src, n_src = [], 0
    try:
        for sd in sorted(x for x in corpus.iterdir() if x.is_dir() and not x.name.startswith("_")):
            f = _newest_named(sd, "20??-??-??.jsonl")
            if f is None:
                continue
            n_src += 1
            row = _last_json_row(f)
            fs = _ts((row or {}).get("first_seen_utc")) or _ts(f.stem)
            a = _age(fs, ctx.now)
            if a is None or a > 3 * 86400:
                stale_src.append(f"{sd.name} ({_fmt_age(a)})")
    except OSError:
        pass
    main = ProbeResult(v, _iso(t), _age(t, ctx.now),
                       f"{d.get('headline', '?')}; {n_src - len(stale_src)}/{n_src} sources "
                       f"wrote within 3 d" + (f"; quiet: {', '.join(stale_src[:8])}" if stale_src else "")
                       + (f"; RED/refused: {red}" if red else ""),
                       delta=d.get("rows_new"), proof=f"news_corpus/_receipts/{rec.name} written_utc")
    return main


def p_social_sources(ctx: ProbeCtx) -> ProbeOut:
    d = _lab_status(ctx)
    row = ((d or {}).get("loops") or {}).get("social_pull")
    if not isinstance(row, dict) or not row.get("per_source"):
        return _unknown("no lab_status.loops.social_pull.per_source")
    t = _ts(row.get("last_tick_utc"))
    per = float(row.get("cadence_minutes") or 360)
    out = {}
    for s in row["per_source"]:
        name = s.get("source", "?")
        st = str(s.get("status"))
        if s.get("refused"):
            out[name] = _unknown(f"{name}: {s['refused']} -- refused, not collected",
                                 evidence_utc=_iso(t), age_s=_age(t, ctx.now))
            continue
        v = _by_age(t, timedelta(minutes=per * 2), ctx.now)
        if st not in ("OK", "ok"):
            v = "STALE"
        out[name] = ProbeResult(v, _iso(t), _age(t, ctx.now),
                                f"{name}: {st}, {s.get('rows', '?')} row(s) on the last tick",
                                proof="lab_status.loops.social_pull.per_source")
    return out


def p_dowjones_feeds(ctx: ProbeCtx) -> ProbeResult:
    f = _newest_named(ctx.optimus_dir / "dowjones", "feeds_20??-??-??.json")
    d = _read_json(f) if f else None
    if not isinstance(d, dict):
        return _unknown("no dowjones/feeds_<date>.json receipt")
    t = _ts(d.get("generated_utc"))
    red = d.get("refused_or_red") or []
    v = _by_age(t, timedelta(days=1), ctx.now)
    if v == "ALIVE" and red:
        v = "STALE"
    return ProbeResult(v, _iso(t), _age(t, ctx.now),
                       f"{d.get('n_feeds', '?')} feeds, {d.get('items_new', '?')} new item(s)"
                       + (f"; red: {red[:4]}" if red else ""),
                       delta=d.get("items_new"), proof=f"dowjones/{f.name} generated_utc")


def p_telegram_agent(ctx: ProbeCtx) -> ProbeResult:
    tg = ctx.optimus_dir / "telegram"
    pid = _pid_from_file(tg / "agent.pid")
    hb = _read_json(tg / "heartbeat.json")
    off = _read_json(tg / "update_offset.json")
    hb_t = _ts((hb or {}).get("utc")) if isinstance(hb, dict) else None
    if isinstance(hb, dict) and hb.get("pid"):
        pid = hb.get("pid")
    off_t = _ts((off or {}).get("at")) if isinstance(off, dict) else None
    last_poll = f"last poll offset stamp {_iso(off_t)}"
    if pid is None and hb_t is None and off_t is None:
        return _unknown("no telegram/agent.pid, heartbeat.json or update_offset.json")
    if hb_t is None:
        cl = _cmdline(ctx, pid) if pid else None
        if not pid or cl is None:
            return ProbeResult("DEAD", _iso(off_t), _age(off_t, ctx.now),
                               f"agent pid {pid} not running; {last_poll} "
                               f"({_fmt_age(_age(off_t, ctx.now))})",
                               proof=f"pid {pid} not in the process table")
        if "telegram_agent" not in cl.replace("\\", "/").replace("/", "."):
            return ProbeResult("DEAD", _iso(off_t), _age(off_t, ctx.now),
                               f"agent.pid {pid} now belongs to another program; {last_poll}",
                               proof=f"pid {pid} cmdline lacks telegram_agent")
        return _unknown(f"pid {pid} answers as telegram_agent but the agent writes no "
                        f"heartbeat.json, so the poll loop's liveness cannot be derived; {last_poll}",
                        evidence_utc=_iso(off_t), age_s=_age(off_t, ctx.now))
    return _process_verdict(ctx, pid=pid, module="telegram_agent", stamp=hb_t,
                            cadence=timedelta(seconds=120), what="telegram_agent")


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _reader_evidence(ctx: ProbeCtx, *, max_age_min: float = 60.0) -> dict:
    """Did the reader load pages THROUGH the gateway recently? From its own
    `dowjones/reader_status.json` (`t`, `pages_ok_60m`); never a file mtime."""
    d = _read_json(ctx.optimus_dir / "dowjones" / "reader_status.json")
    if not isinstance(d, dict):
        return {"ok": False, "why": "no readable reader_status.json"}
    t = _ts(d.get("t"))
    n = int(d.get("pages_ok_60m") or 0)
    if t is None:
        return {"ok": False, "why": "reader_status.json carries no stamp"}
    age = _age(t, ctx.now)
    if age is None or age > max_age_min * 60:
        return {"ok": False, "why": f"reader status is {_fmt_age(age)} old"}
    if n <= 0:
        return {"ok": False, "why": "pages_ok_60m is 0"}
    return {"ok": True, "pages_ok_60m": n, "utc": _iso(t), "age_s": age}


def p_openclaw_gateway(ctx: ProbeCtx) -> ProbeResult:
    try:
        from backend.services import openclaw_client as OC          # noqa: PLC0415
        argv = [OC._bin(), "gateway", "status"]
    except Exception:                                               # noqa: BLE001
        argv = ["openclaw", "gateway", "status"]
    rc, txt = _run(ctx, argv, 90)
    if rc is None:
        return _unknown(f"`openclaw gateway status` could not run: {str(txt)[:120]}")
    txt = _ANSI.sub("", txt or "")
    running = "Runtime: running" in txt
    probe_ok = "Connectivity probe: ok" in txt
    m = re.search(r"Capability:\s*([^\r\n]+)", txt)
    cap = m.group(1).strip() if m else None
    lr = re.search(r"last run time\s+([0-9T:\-\.+Z]+)", txt)
    t = _ts(lr.group(1)) if lr else None
    if not running or not probe_ok:
        return ProbeResult("DEAD", _iso(t), _age(t, ctx.now),
                           f"gateway runtime running={running}, connectivity probe ok={probe_ok}",
                           proof="openclaw gateway status")
    if cap and "no-operator" in cap:
        # 2026-10-02: `connected-no-operator-scope` is the STATUS CLI's own probe
        # connection (it connects without an operator-scoped token, so the
        # deep status RPCs are unreadable); it is not what the gateway can
        # serve. The row said "degraded" for days while the reader read through
        # it. Capability is now taken from the reader's own evidence.
        ev = _reader_evidence(ctx)
        if ev.get("ok"):
            return ProbeResult("ALIVE", ev.get("utc") or _iso(ctx.now), ev.get("age_s") or 0.0,
                               f"gateway running, probe ok; the status CLI has no operator "
                               f"scope ({cap}), capability PROVEN by the reader: "
                               f"{ev['pages_ok_60m']} pages OK in 60 min (as of {ev.get('utc')})",
                               proof="openclaw gateway status + dowjones/reader_status.json")
        return ProbeResult("STALE", _iso(ctx.now), 0.0,
                           f"gateway running, probe ok, but capability UNPROVEN: the status "
                           f"CLI has no operator scope ({cap}) and the reader shows no OK page "
                           f"in the last hour ({ev.get('why')})",
                           proof="openclaw gateway status: Capability + dowjones/reader_status.json")
    return ProbeResult("ALIVE", _iso(ctx.now), 0.0,
                       f"gateway running, probe ok, capability {cap or 'not printed'}",
                       proof="openclaw gateway status: Connectivity probe: ok")


def p_openclaw_tool_scope(ctx: ProbeCtx) -> ProbeResult:
    """What an OpenClaw LLM turn may do (config) and did (transcripts, 24 h).
    2026-09-29: a thesis-card quest drove the signed-in Chrome through `exec`."""
    from backend.services import openclaw_tool_scope as OTS          # noqa: PLC0415
    return OTS.p_openclaw_tool_scope(ctx)


def p_openclaw_api_bridge(ctx: ProbeCtx) -> ProbeResult:
    """The read-only MCP bridge's own heartbeat (C8, 2026-10-07): rewritten on
    server start and on every tool call. The agent calls it ON DEMAND, so a quiet
    week is idle, not dead; a last call that ERRORED is DEGRADED. No heartbeat at
    all is UNKNOWN -- the bridge has not been called since it learned to write one."""
    from backend import config as C                                 # noqa: PLC0415
    hb_p = ctx.path("openclaw_bridge_hb", ctx.optimus_dir / "openclaw_api_bridge" / "heartbeat.json")
    hb = _read_json(hb_p)
    if not isinstance(hb, dict):
        return _unknown("no openclaw_api_bridge/heartbeat.json: the bridge has not started or been "
                        "called since its heartbeat landed (2026-10-07)")
    last = _ts(hb.get("last_call_utc"))
    started = _ts(hb.get("started_utc"))
    t = last or started
    if t is None:
        return _unknown("openclaw_api_bridge heartbeat carries no stamp")
    counts_txt = f"{hb.get('n_calls', 0)} call(s), {hb.get('n_errors', 0)} error(s) this server run"
    if last is not None and hb.get("last_error"):
        return ProbeResult("STALE", _iso(last), _age(last, ctx.now),
                           f"last call {hb.get('last_tool')} {hb.get('last_route')} ERRORED: "
                           f"{hb.get('last_error')}; {counts_txt}",
                           proof="openclaw_api_bridge/heartbeat.json last_error", state="DEGRADED")
    idle_s = float(C.OPENCLAW_BRIDGE_IDLE_DAYS) * 86400
    what = (f"last call {hb.get('last_tool')} {_fmt_age(_age(last, ctx.now))} ago" if last
            else f"server started {_fmt_age(_age(started, ctx.now))} ago, no call yet")
    state = "ALIVE_PROGRESSING" if (last and (_age(last, ctx.now) or 0) <= idle_s) else "ALIVE_IDLE_EXPECTED"
    return ProbeResult("ALIVE", _iso(t), _age(t, ctx.now),
                       f"{what}; {counts_txt}"
                       + ("" if state == "ALIVE_PROGRESSING" else
                          " (declared idle: the agent calls the bridge on demand)"),
                       proof="openclaw_api_bridge/heartbeat.json", state=state)


def p_llama_server(ctx: ProbeCtx) -> ProbeResult:
    try:
        from backend.services import llama_server as LS             # noqa: PLC0415
        owner_p, url = LS.OWNER_FILE, f"http://{LS.LLAMA_HOST}:{LS.LLAMA_PORT}/health"
    except Exception:                                               # noqa: BLE001
        owner_p, url = ctx.optimus_dir / "llama_server_owner.json", "http://127.0.0.1:8080/health"
    owner_p = ctx.path("llama_owner", owner_p)
    owner = _read_json(owner_p) if Path(owner_p).exists() else None
    body, _, err = (ctx.http_json or _default_http_json)(url, 3)
    up = body is not None
    lab = _lab_status(ctx)
    l2 = ((lab or {}).get("loops") or {}).get("l2_typing") or {}
    pending = str(l2.get("status")) == "PENDING_MODEL"
    prev = ctx.prev_state.get("pending_model_since")
    since = _ts(prev) if pending and prev else (ctx.now if pending else None)
    if pending:
        ctx.new_state["pending_model_since"] = _iso(since)
    if up:
        return ProbeResult("ALIVE", _iso(ctx.now), 0.0,
                           f"/health answers; owner note {'present' if owner else 'absent (foreign server?)'}",
                           proof=f"GET {url}")
    if owner:
        return ProbeResult("DEAD", _iso(_ts(owner.get("started_utc"))), None,
                           f"an Aegis owner note exists (pid {owner.get('pid')}) but /health does "
                           f"not answer ({err})", proof=f"GET {url} failed")
    if pending and since and (ctx.now - since).total_seconds() > PENDING_MODEL_STALE_S:
        return ProbeResult("STALE", _iso(since), _age(since, ctx.now),
                           f"server down and l2_typing has waited PENDING_MODEL for "
                           f"{_fmt_age(_age(since, ctx.now))} -- typing never happens unattended",
                           proof="lab_status.loops.l2_typing.status")
    if lab is None:
        return _unknown(f"server down ({err}) and no lab_status to say whether anything waits on it")
    return ProbeResult("ALIVE", _iso(ctx.now), 0.0,
                       "idle by design: not running and nothing has waited > 1 h"
                       + (" (l2_typing PENDING_MODEL, first seen this run)" if pending else ""),
                       proof=f"GET {url} refused; no owner note")


def p_llama_reaper(ctx: ProbeCtx) -> ProbeResult:
    row = None
    for line in reversed(_tail_lines(ctx.optimus_dir / "llama_reaper.log.jsonl")):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("action"):
            row = r
            break
    if row is None:
        return _unknown("no llama_reaper.log.jsonl row with an action")
    t = _ts(row.get("t"))
    if row.get("action") == "exit" and row.get("reason"):
        return ProbeResult("ALIVE", _iso(t), _age(t, ctx.now),
                           f"exited by design: {row['reason']}", proof="llama_reaper.log.jsonl[-1]")
    v = "ALIVE" if (_age(t, ctx.now) or 1e9) < 60 else "STALE"
    return ProbeResult(v, _iso(t), _age(t, ctx.now),
                       f"last action {row.get('action')} {_fmt_age(_age(t, ctx.now))} ago",
                       proof="llama_reaper.log.jsonl[-1].t")


def p_optimus_brain(ctx: ProbeCtx) -> ProbeResult:
    root = Path(os.getenv("OPTIMUS_ROOT", str(Path.home() / "optimus")))
    p = ctx.path("optimus_health", root / "brain" / "projects" / "aegis-health" / "aegis-health-latest.md")
    try:
        body = Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _unknown(f"no Optimus health page at {p}")
    m = re.search(r"generated (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC", body)
    if not m:
        return _unknown("Optimus health page carries no `generated ... UTC` stamp")
    t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    v = _by_age(t, timedelta(hours=24), ctx.now)
    return ProbeResult(v, _iso(t), _age(t, ctx.now),
                       f"brain health page generated {_fmt_age(_age(t, ctx.now))} ago"
                       + ("" if v == "ALIVE" else
                          " -- its caller is the AegisBrainRefresh task (`task_keeper brain`); "
                          "see the task:AegisBrainRefresh row for whether it ran or refused"),
                       proof="aegis-health-latest.md `generated` stamp")


def p_scheduled_tasks(ctx: ProbeCtx) -> ProbeOut:
    """One row per Aegis task, judged by the RECEIPT it must advance (C8, 2026-10-07).

    Never by schtasks' "Last Result": that is cmd's / pythonw's exit code, not the
    job's (17 rows read UNKNOWN on it every night). The scheduler is read only to
    know WHICH tasks exist, whether one is Disabled, and whether it has ever run.
    A task declared in `task_receipts.TASK_RECEIPT` but absent from the scheduler
    is a row too: nothing will write its next receipt."""
    from backend.services import task_receipts as TR                # noqa: PLC0415
    tasks = _schtasks(ctx)
    if tasks is None:
        return _unknown("`schtasks /query /fo CSV /v` could not be read, so which tasks exist "
                        "cannot be derived")
    out = {}
    for name in sorted(set(tasks) | set(TR.TASK_RECEIPT)):
        row = tasks.get(name)
        spec = TR.TASK_RECEIPT.get(name)
        if row is None and spec is not None and (spec.retired or spec.registered_only):
            continue                                  # retired/deleted, or never registered by design
        j = TR.judge(ctx, name, row, spec)
        out[name] = ProbeResult(j.verdict, _iso(j.stamp), _age(j.stamp, ctx.now), j.detail,
                                proof=j.proof or (spec.receipt if spec else ""), state=j.state)
    return out or _unknown("no Aegis* scheduled tasks found and none declared")


def p_railway_backend(ctx: ProbeCtx) -> ProbeResult:
    url = (ctx.railway_url or "").rstrip("/") + "/api/health/full"
    body, elapsed, err = (ctx.http_json or _default_http_json)(url, 45)
    if body is None:
        return ProbeResult("DEAD", None, None, f"GET {url} failed: {err}", proof="no HTTP body")
    dep = body.get("deploy") or {}
    nav = (body.get("scheduler") or {}).get("nav") or {}
    up = dep.get("uptime_seconds")
    fresh = nav.get("all_fresh")
    lanes = nav.get("lanes") or {}
    lastnav = sorted({str(v.get("last_nav_date")) for v in lanes.values() if isinstance(v, dict)})
    started = _ts(dep.get("started_at"))
    parts = [f"commit {str(dep.get('commit'))[:8]}", f"uptime {up}s", f"response {elapsed}s",
             f"all_fresh={fresh}", f"expected_nav_date {nav.get('expected_nav_date')}",
             f"lane last_nav_date {lastnav[:3]}"]
    asleep = isinstance(up, (int, float)) and up < 86400
    if asleep:
        parts.append("uptime < 1 day: the container was asleep/restarted and the in-process "
                     "scheduler did not run while it slept")
    if fresh is None or up is None:
        return _unknown("body lacks deploy.uptime_seconds or scheduler.nav.all_fresh; "
                        + "; ".join(parts))
    v: Verdict = "ALIVE" if (fresh and not asleep) else "STALE"
    return ProbeResult(v, _iso(started), _age(started, ctx.now), "; ".join(parts),
                       proof="GET /api/health/full deploy+scheduler.nav")


def p_railway_fleet(ctx: ProbeCtx) -> ProbeResult:
    rc, txt = _run(ctx, ["railway", "status"], 30)
    if rc is None or rc != 0:
        return _unknown(f"`railway status` did not answer ({str(txt)[:100]})")
    m = re.search(r"Linked service\s+(\S+)", txt or "")
    svc = m.group(1) if m else None
    if svc not in FLEET_SERVICES:
        return _unknown(f"CLI linked to {svc or 'no service'} (not a live fleet service), so the "
                        f"fleet's `cycle full exited rc=0` lines cannot be read read-only from here")
    return _unknown(f"CLI linked to {svc}; per-service log reads are not automated yet")


def p_ci(ctx: ProbeCtx) -> ProbeResult:
    rc, sha = _run(ctx, ["git", "-C", str(ctx.repo), "rev-parse", "origin/main"], 20)
    if rc != 0 or not sha:
        return _unknown(f"cannot resolve origin/main ({str(sha)[:80]})")
    sha = sha.strip().splitlines()[0]
    rc, txt = _run(ctx, ["gh", "run", "list", "--commit", sha, "--limit", "1", "--json",
                         "conclusion,status,createdAt,headSha,workflowName"], 45)
    if rc != 0:
        return _unknown(f"`gh run list` failed: {str(txt)[:100]}")
    try:
        runs = json.loads(txt)
    except ValueError:
        return _unknown(f"`gh run list` printed non-JSON: {str(txt)[:80]}")
    if not runs:
        return _unknown(f"no CI run for origin/main {sha[:8]}")
    r = runs[0]
    t = _ts(r.get("createdAt"))
    concl = r.get("conclusion") or r.get("status")
    v: Verdict = "ALIVE" if concl == "success" else ("UNKNOWN" if r.get("status") != "completed" else "STALE")
    return ProbeResult(v, _iso(t), _age(t, ctx.now),
                       f"CI {r.get('workflowName')} on origin/main {sha[:8]}: {concl}",
                       proof="gh run list --commit origin/main")


def p_git(ctx: ProbeCtx) -> ProbeResult:
    rc, txt = _run(ctx, ["git", "-C", str(ctx.repo), "rev-list", "--count", "origin/main..HEAD"], 20)
    if rc != 0:
        return _unknown(f"git rev-list failed: {str(txt)[:80]}")
    try:
        n = int(str(txt).strip().splitlines()[0])
    except (ValueError, IndexError):
        return _unknown(f"git printed {str(txt)[:40]!r}")
    return ProbeResult("ALIVE" if n == 0 else "STALE", _iso(ctx.now), 0.0,
                       f"{n} local commit(s) not on origin/main (local ref; not fetched)",
                       delta=n, proof="git rev-list --count origin/main..HEAD")


def p_accrual_canary(ctx: ProbeCtx) -> ProbeResult:
    from backend.services import accrual_canary as AC               # noqa: PLC0415
    today = ctx.now.date()
    rows = {}
    rows["forecast_accrual"] = AC.forecast_accrual(ctx.optimus_dir / "predictions.jsonl", today=today)
    rows["n_considered"] = AC.n_considered_row(
        ctx.optimus_dir / "decisions", ctx.path("funnel", ctx.optimus_dir.parent / "funnel_night10.json"))
    st = [r.get("status") for r in rows.values()]
    reasons = [f"{k}: {r.get('status')} {str(r.get('reason') or '')[:90]}" for k, r in rows.items()]
    if all(s == "UNKNOWN" for s in st):
        return _unknown("; ".join(reasons))
    v: Verdict = "STALE" if any(s in ("DEGRADED", "UNKNOWN") for s in st) else "ALIVE"
    fa = _ts(rows["forecast_accrual"].get("last_new_row_utc"))
    return ProbeResult(v, _iso(fa), _age(fa, ctx.now), "; ".join(reasons),
                       proof="accrual_canary.forecast_accrual + n_considered_row on the PC paths")


# ─────────────────────────────────────── disk (2026-09-27 disk-full incident)

#: Receipt-shaped names the zero-byte probe inspects. Logs (`*.log`, `*.err`)
#: are excluded on purpose: an empty stderr log is the NORMAL state of a clean
#: run, and counting them would make the probe red for ever.
_RECEIPT_SUFFIXES = (".md", ".csv", ".parquet")
_STAMP_DT = re.compile(r"(20\d{2})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z")
_STAMP_DASH_DT = re.compile(r"(20\d{2})-(\d{2})-(\d{2})[_T](\d{2})(\d{2})(\d{2})")
_STAMP_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def _name_stamp(name: str) -> tuple[Optional[datetime], bool]:
    """(stamp, date_only) from the producer's own stamp in a FILE NAME, never an
    mtime. `20260927T111250Z`, `2026-09-27_111242`, else `2026-09-27`."""
    for rx in (_STAMP_DT, _STAMP_DASH_DT):
        m = rx.search(name)
        if m:
            try:
                return datetime(*map(int, m.groups()), tzinfo=timezone.utc), False
            except ValueError:
                pass
    m = _STAMP_DATE.search(name)
    if m:
        try:
            return datetime(*map(int, m.groups()), tzinfo=timezone.utc), True
        except ValueError:
            pass
    return None, False


#: Never receipts, whatever else is in the name: an OS lock sidecar
#: (`disk_guard.file_lock` -> `<file>.lock`, e.g. `x.jsonl.lock`) is EMPTY by
#: design, and counting it read as a truncated receipt (2026-09-29).
_NOT_RECEIPT_SUFFIXES = (".lock",)


def _is_receipt_name(name: str) -> bool:
    if name.lower().endswith(_NOT_RECEIPT_SUFFIXES):
        return False
    return ".json" in name or name.endswith(_RECEIPT_SUFFIXES)


def p_disk_free(ctx: ProbeCtx) -> ProbeResult:
    """Free bytes on the volume holding the ledger dir (`shutil.disk_usage`).

    ALIVE >= DISK_FREE_STALE_GB, STALE below, DEAD < DISK_FREE_DEAD_GB. On
    2026-09-27 C: reached 0 bytes and 13 receipts were truncated to zero while
    every row here read healthy -- nothing measured the disk."""
    if ctx.disk_usage is None:
        return _unknown("no disk_usage reader on the probe context; free space not measured")
    from backend import config as C                                 # noqa: PLC0415
    from backend.services import disk_guard as DG                   # noqa: PLC0415
    try:
        m = DG.measure(ctx.optimus_dir, disk_usage=ctx.disk_usage)
    except DG.DiskTooFull as exc:
        return _unknown(str(exc)[:200])
    stale_gb, dead_gb = float(C.DISK_FREE_STALE_GB), float(C.DISK_FREE_DEAD_GB)
    free_gb = m["free_bytes"] / DG.GB
    v: Verdict = "DEAD" if free_gb < dead_gb else ("STALE" if free_gb < stale_gb else "ALIVE")
    return ProbeResult(v, _iso(ctx.now), 0.0,
                       f"disk free: {free_gb:.1f} GB on {m['volume']} of {m['total_gb']:.0f} GB "
                       f"(STALE < {stale_gb:g} GB, DEAD < {dead_gb:g} GB)",
                       delta=int(m["free_bytes"]),
                       proof=f"shutil.disk_usage({m['volume']}) for {ctx.optimus_dir.name}/")


def p_zero_byte_receipts(ctx: ProbeCtx) -> ProbeResult:
    """Zero-byte receipt-shaped files under the ledger dir, dated by the STAMP in
    their own name within the last 24 h. A file with no stamp is counted under
    `undated` and printed, but cannot turn the row red (it has no date)."""
    root = ctx.optimus_dir
    if not root.is_dir():
        return _unknown(f"ledger dir {root} does not exist")
    lo = ctx.now - timedelta(hours=24)
    hi = ctx.now + timedelta(hours=1)
    n_dated, empty_dated, empty_undated = 0, [], []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for fn in files:
            if not _is_receipt_name(fn):
                continue
            ts, date_only = _name_stamp(fn)
            if ts is None:
                try:
                    if os.path.getsize(os.path.join(dirpath, fn)) == 0:
                        empty_undated.append(os.path.relpath(os.path.join(dirpath, fn), root))
                except OSError:
                    pass
                continue
            in_window = (ts.date() >= lo.date() and ts.date() <= hi.date()) if date_only \
                else (lo <= ts <= hi)
            if not in_window:
                continue
            n_dated += 1
            try:
                if os.path.getsize(os.path.join(dirpath, fn)) == 0:
                    empty_dated.append(os.path.relpath(os.path.join(dirpath, fn), root))
            except OSError:
                pass
    und = (f"; undated zero-byte: {len(empty_undated)}"
           + (f" ({', '.join(sorted(empty_undated)[:5])})" if empty_undated else ""))
    if n_dated == 0:
        return _unknown(f"no receipt-stamped file dated in the last 24 h under {root.name}/ "
                        f"to inspect{und}", delta=len(empty_dated))
    names = ", ".join(sorted(empty_dated)[:5]).replace("\\", "/")
    v: Verdict = "STALE" if empty_dated else "ALIVE"
    return ProbeResult(v, _iso(ctx.now), 0.0,
                       f"{len(empty_dated)} zero-byte of {n_dated} receipt(s) stamped in the last 24 h"
                       + (f": {names}" if names else "") + und.replace("\\", "/"),
                       delta=len(empty_dated),
                       proof="os.walk + os.path.getsize; date = the stamp in the file name, never mtime")


# ════════════════════════════════════════════════════════════════ registry

D1 = timedelta(days=1)
PROBES: tuple[Probe, ...] = (
    Probe("bars_panel", "pc", D1, "prices_2025_26/bars.parquet: max(date) vs last closed XNYS session", p_bars_panel),
    Probe("ranking", "pc", D1, "pc_book/<d>/ranking.json: asof", p_ranking),
    Probe("u_funnel", "pc", timedelta(days=10), "funnel_night10.json: generated_at", p_u_funnel),
    Probe("always_on_lab", "pc", timedelta(minutes=5), "lab_status.json: utc + pid cmdline contains always_on_lab", p_always_on_lab, True),
    Probe("lab_loop", "pc", timedelta(minutes=5), "lab_status.json: loops[*].last_tick_utc + status", p_lab_loops),
    Probe("sim_session", "pc", D1, "sim/session.json: state, heartbeat, pid cmdline", p_sim_session, True),
    Probe("live_market_loop", "pc", D1, "pc_book/*/nav.jsonl: rows tagged open_of_loop/close_of_loop", p_live_market_loop),
    Probe("u_forecast", "pc", D1, "predictions.jsonl per writer (config.FORECAST_WRITERS): new_rows_since_last_session + today's day receipt", p_u_forecast),
    Probe("forecast_ledger", "pc", D1, "predictions.jsonl: new_rows_since_last_run", p_forecast_ledger),
    Probe("u_review", "pc", D1, "review/review_<last_session>.json: generated_utc", p_u_review),
    Probe("u_plan", "pc", D1, "pc_book/<d>/intended_book.json: t, asof, invested_frac", p_u_plan),
    Probe("policy_state", "pc", D1, "pc_book/<d>/decisions.jsonl: a plan within 2 sessions carrying policy_state_used", p_policy_state),
    Probe("decision_contract", "pc", D1, "decisions/<d>.json: written_utc + n_considered run", p_decision_contract),
    Probe("forecast_grader", "pc", D1, "predictions.jsonl: max(resolved_at) vs due rows; daily_pass 'wait on a bar'", p_forecast_grader),
    Probe("book_grader", "pc", D1, "daily_pass scoreboard.nav_vs_spy.window.last_date + llm_portfolio/leaderboard_<day>.json (bars_through, status_counts) + the pass's book-grading steps", p_book_grader),
    Probe("learn_rota", "pc", D1, "pc_book/<d>/learn_*.json: status / skipped", p_learn_rota),
    Probe("daily_pass", "pc", D1, "night_factory_<d>/daily_pass_<d>.json: steps[*].utc/status (+ schtasks)", p_daily_pass),
    Probe("iif1_night", "pc", D1, "iif1_nights/<last weekday>.json: status, spend_usd", p_iif1_night),
    Probe("news_collectors", "pc", timedelta(minutes=15), "news_corpus/_receipts/<ts>_ALL.json + newest first_seen_utc per source", p_news_collectors),
    Probe("social", "pc", timedelta(hours=6), "lab_status.loops.social_pull.per_source", p_social_sources),
    Probe("dowjones_feeds", "pc", D1, "dowjones/feeds_<d>.json: generated_utc", p_dowjones_feeds),
    Probe("telegram_agent", "pc", timedelta(seconds=60), "telegram/heartbeat.json|update_offset.json + agent.pid cmdline", p_telegram_agent, True),
    Probe("openclaw_gateway", "pc", timedelta(minutes=5), "`openclaw gateway status`: Runtime, Connectivity probe, Capability", p_openclaw_gateway, True),
    Probe("openclaw_api_bridge", "pc", D1, "openclaw_api_bridge/heartbeat.json: last_call_utc, last_error (written per call)", p_openclaw_api_bridge),
    Probe("openclaw_tool_scope", "pc", D1, "~/.openclaw/openclaw.json tool policy + agents/*/agent/openclaw-agent.sqlite tool calls (24 h, read-only)", p_openclaw_tool_scope),
    Probe("llama_server", "pc", D1, "GET :8080/health + owner note + lab l2_typing", p_llama_server, True),
    Probe("llama_reaper", "pc", timedelta(seconds=30), "llama_reaper.log.jsonl[-1]: t, action", p_llama_reaper),
    Probe("optimus_brain", "pc", timedelta(hours=24), "optimus aegis-health-latest.md: `generated` stamp", p_optimus_brain),
    Probe("task", "pc", D1, "each task's own receipt (task_receipts.TASK_RECEIPT); schtasks only says which tasks exist", p_scheduled_tasks, True),
    Probe("railway_backend", "external", D1, "GET /api/health/full: deploy.uptime_seconds, scheduler.nav.all_fresh", p_railway_backend, True),
    Probe("railway_fleet", "external", D1, "`railway status` linked service (+ logs)", p_railway_fleet, True),
    Probe("ci", "external", D1, "gh run list --commit origin/main: conclusion", p_ci, True),
    Probe("git", "pc", D1, "git rev-list --count origin/main..HEAD", p_git, True),
    Probe("accrual_canary", "pc", D1, "accrual_canary.forecast_accrual + n_considered_row (PC paths)", p_accrual_canary),
    Probe("disk_free", "pc", timedelta(minutes=5), "shutil.disk_usage on the ledger dir's volume vs DISK_FREE_STALE_GB / DISK_FREE_DEAD_GB", p_disk_free),
    Probe("zero_byte_receipts", "pc", D1, "zero-byte *.json*/.md/.csv/.parquet under the ledger dir, dated by the stamp in the name (last 24 h)", p_zero_byte_receipts),
    Probe("openclaw_temp_builds", "pc", timedelta(minutes=10), "count + time-boxed size of %TEMP%/openclaw-plugin-build-* vs OPENCLAW_TEMP_DEGRADED_COUNT / _GB", lambda ctx: __import__("backend.services.openclaw_temp", fromlist=["p_openclaw_temp_builds"]).p_openclaw_temp_builds(ctx), True),
    Probe("backtest_leaderboard", "pc", timedelta(days=7), "strategy_library/leaderboard_<run id>.json: run id in the name vs BACKTEST_LEADERBOARD_STALE_DAYS", lambda ctx: __import__("backend.services.backtest_staleness", fromlist=["p_backtest_leaderboard"]).p_backtest_leaderboard(ctx)),
)


# ════════════════════════════════════════════════════════════════ running

def health_dir(optimus_dir: Optional[Path] = None) -> Path:
    if optimus_dir is None:
        from backend import config as C                             # noqa: PLC0415
        optimus_dir = Path(C.OPTIMUS_LEDGER_DIR)
    return Path(optimus_dir) / "health"


def on_railway() -> bool:
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))


def _default_railway_url() -> str:
    return os.getenv("AEGIS_PAPER_SOURCE_URL", "https://aegis-finance-production.up.railway.app")


def _row(p: Probe, name: str, r: ProbeResult) -> dict:
    d = {"name": name, "probe": p.name, "where": p.where,
         "cadence_s": p.cadence.total_seconds(), "evidence": p.evidence, **asdict(r)}
    d["state"] = r.state or r.verdict
    return d


def run_probes(ctx: ProbeCtx, *, only: Optional[set] = None,
               receipt: Optional[dict] = None) -> list[dict]:
    """Every probe, one or more rows each. Never raises."""
    rows: list[dict] = []
    rec_rows = {r["name"]: r for r in (receipt or {}).get("rows", [])}
    rec_age = _age(_ts((receipt or {}).get("generated_utc")), ctx.now)
    railway = on_railway()
    for p in PROBES:
        if only and p.name not in only:
            continue
        if (railway and p.where == "pc") or (p.needs_proc and not ctx.allow_proc):
            copied = [r for n, r in rec_rows.items() if r.get("probe") == p.name]
            if copied and rec_age is not None and rec_age <= RECEIPT_MAX_AGE_S:
                for r in copied:
                    rows.append({**r, "detail": f"(from the PC probe receipt, {_fmt_age(rec_age)} old) "
                                               + str(r.get("detail"))})
                continue
            why = ("runs on the PC" if railway and p.where == "pc"
                   else "not computed on a request (it shells out or opens a socket)")
            rows.append(_row(p, p.name, _unknown(
                f"{why}; last PC health receipt is "
                f"{_fmt_age(rec_age) if rec_age is not None else 'absent'} old")))
            continue
        try:
            out = p.fn(ctx)
        except Exception as exc:                                    # noqa: BLE001
            out = _unknown(f"probe raised {type(exc).__name__}: {str(exc)[:160]}")
        if isinstance(out, dict):
            for sub, r in out.items():
                rows.append(_row(p, f"{p.name}:{sub}", r))
        else:
            rows.append(_row(p, p.name, out))
    rows.sort(key=lambda r: (VERDICT_ORDER.get(r["verdict"], 9), r["name"]))
    return rows


def counts(rows: list[dict]) -> dict:
    c = {k: 0 for k in VERDICT_ORDER}
    for r in rows:
        c[r["verdict"]] = c.get(r["verdict"], 0) + 1
    return c


def state_counts(rows: list[dict]) -> dict:
    """The fine states (C8): ALIVE_PROGRESSING / ALIVE_IDLE_EXPECTED / DEGRADED ...
    A row without a fine state counts under its verdict."""
    c: dict = {}
    for r in rows:
        k = r.get("state") or r["verdict"]
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


def exit_code(rows: list[dict]) -> int:
    """1 any DEAD · 2 any STALE or REFUSED · 3 all UNKNOWN · 0 otherwise."""
    c = counts(rows)
    if c["DEAD"]:
        return 1
    if c["STALE"] or c.get("REFUSED"):
        return 2
    if rows and c["UNKNOWN"] == len(rows):
        return 3
    return 0


def _load_state(hd: Path) -> dict:
    d = _read_json(hd / "_state.json")
    return d if isinstance(d, dict) else {}


def newest_receipt(hd: Optional[Path] = None) -> Optional[dict]:
    hd = hd or health_dir()
    p = _newest_named(hd, "health_*T*Z.json")
    d = _read_json(p) if p else None
    return d if isinstance(d, dict) else None


def make_ctx(*, optimus_dir: Optional[Path] = None, now: Optional[datetime] = None,
             allow_proc: bool = True, **kw) -> ProbeCtx:
    if optimus_dir is None:
        from backend import config as C                             # noqa: PLC0415
        optimus_dir = Path(C.OPTIMUS_LEDGER_DIR)
    kw.setdefault("disk_usage", shutil.disk_usage)
    ctx = ProbeCtx(optimus_dir=Path(optimus_dir), now=now or _utcnow(), allow_proc=allow_proc,
                   railway_url=kw.pop("railway_url", None) or _default_railway_url(), **kw)
    ctx.prev_state = _load_state(health_dir(ctx.optimus_dir))
    return ctx


def run(*, ctx: Optional[ProbeCtx] = None, only: Optional[set] = None,
        persist: bool = False) -> dict:
    """The table as a receipt. `persist` writes the receipt, HEALTH.md, the index
    line and the delta state (the CLI does; an API request does not)."""
    ctx = ctx or make_ctx()
    hd = health_dir(ctx.optimus_dir)
    receipt = None if ctx.allow_proc and not on_railway() else newest_receipt(hd)
    rows = run_probes(ctx, only=only, receipt=receipt)
    out = {"receipt": "system_health", "generated_utc": _iso(ctx.now),
           "source": ("railway_local" if on_railway() else "pc"),
           "allow_proc": ctx.allow_proc, "counts": counts(rows),
           "state_counts": state_counts(rows),
           "exit_code": exit_code(rows), "rows": rows,
           "read_me_first": ("Every verdict is derived from evidence the producer wrote (a stamp "
                             "inside a receipt, a pid answering with its module, an HTTP body "
                             "field, a row-count delta) -- never an mtime or a lock file alone. "
                             "UNKNOWN names why the evidence is missing; it is never ALIVE.")}
    if persist:
        hd.mkdir(parents=True, exist_ok=True)
        stamp = ctx.now.strftime("%Y%m%dT%H%M%SZ")
        p = hd / f"health_{stamp}.json"
        # atomic (2026-09-27): a full disk leaves the OLD file, never a zero-byte one
        from backend.services.disk_guard import atomic_write_json, atomic_write_text  # noqa: PLC0415
        atomic_write_json(p, out, ensure_ascii=True)
        atomic_write_text(hd / "HEALTH.md", render_md(out))
        with open(hd / "health_index.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": out["generated_utc"], "path": p.name,
                                "counts": out["counts"], "exit_code": out["exit_code"]}) + "\n")
        state = {**ctx.prev_state, **ctx.new_state, "generated_utc": out["generated_utc"]}
        if "pending_model_since" not in ctx.new_state:
            state.pop("pending_model_since", None)
        if "no_bar" not in ctx.new_state:
            state.pop("no_bar", None)
        atomic_write_json(hd / "_state.json", state, ensure_ascii=True)
        out["path"] = str(p)
    return out


# ════════════════════════════════════════════════════════════════ rendering

def row_line(r: dict) -> str:
    """`DEAD telegram_agent -- <detail>; proof: <proof>`"""
    ev = r.get("evidence_utc")
    return (f"{r['verdict']} {r['name']} -- {r['detail']}"
            + (f" [evidence {ev[:16]}Z]" if ev else "")
            + (f"; proof: {r['proof']}" if r.get("proof") else ""))


def render_table(out: dict, width: int = 150) -> str:
    L = [f"system health {out['generated_utc']}  counts {out['counts']}  rc {out['exit_code']}",
         f"states {out.get('state_counts') or '-'}",
         f"{'verdict':<8} {'state':<19} {'subsystem':<34} {'age':>7}  detail", "-" * width]
    for r in out["rows"]:
        st = r.get("state") or r["verdict"]
        L.append(f"{r['verdict']:<8} {(st if st != r['verdict'] else ''):<19} {r['name'][:34]:<34} "
                 f"{_fmt_age(r.get('age_s')):>7}  {str(r['detail'])[:width - 74]}")
    return "\n".join(L)


def render_md(out: dict) -> str:
    L = [f"# HEALTH — {out['generated_utc']}", "",
         f"counts {out['counts']} · exit code {out['exit_code']} · source {out['source']}",
         f"states {out.get('state_counts') or '-'}", "",
         "| verdict | state | subsystem | evidence (UTC) | age | detail | proof |",
         "|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        L.append(f"| {r['verdict']} | {r.get('state') or r['verdict']} | {r['name']} | "
                 f"{r.get('evidence_utc') or '-'} | "
                 f"{_fmt_age(r.get('age_s'))} | {str(r['detail']).replace('|', '/')} | "
                 f"{str(r.get('proof') or '').replace('|', '/')} |")
    L += ["", out["read_me_first"], ""]
    return "\n".join(L)


_API_CACHE: dict = {}


def api_block(*, ttl_s: float = 60.0) -> dict:
    """`/api/health/full` -> `subsystems`. File-derived probes computed on the
    request; probes that shell out come from the newest PC receipt (<= 2 h) or
    are UNKNOWN saying so. Cached `ttl_s`. Never raises."""
    now = time.time()
    hit = _API_CACHE.get("v")
    if hit and now - hit[0] < ttl_s:
        return hit[1]
    try:
        out = run(ctx=make_ctx(allow_proc=False))
        block = {"generated_utc": out["generated_utc"],
                 "source": "railway_local" if on_railway() else "pc_request",
                 "counts": out["counts"], "state_counts": out.get("state_counts"),
                 "exit_code": out["exit_code"],
                 "rows": [{k: r.get(k) for k in ("name", "verdict", "state", "where", "evidence_utc",
                                                 "age_s", "detail", "delta", "proof")}
                          for r in out["rows"]]}
    except Exception as exc:                                        # noqa: BLE001
        block = {"generated_utc": _iso(_utcnow()), "source": "error", "counts": {},
                 "exit_code": None, "rows": [],
                 "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    _API_CACHE["v"] = (now, block)
    return block


def disk_status(*, optimus_dir: Optional[Path] = None,
                disk_usage: Optional[Callable[[str], Any]] = None) -> dict:
    """The `disk_free` probe measured NOW (it is cheap and must never come from
    a two-hour-old receipt): {verdict, line, free_gb}. Never raises."""
    try:
        ctx = make_ctx(optimus_dir=optimus_dir, allow_proc=False,
                       disk_usage=disk_usage or shutil.disk_usage)
        r = p_disk_free(ctx)
        free = r.delta / (1024 ** 3) if r.delta is not None else None
        return {"verdict": r.verdict, "free_gb": None if free is None else round(free, 2),
                "line": (r.detail if free is not None else f"disk free: UNKNOWN ({r.detail})")
                        if r.verdict == "ALIVE" else f"{r.verdict} {r.detail}",
                "detail": r.detail}
    except Exception as exc:                                        # noqa: BLE001
        return {"verdict": "UNKNOWN", "free_gb": None, "detail": type(exc).__name__,
                "line": f"disk free: CANNOT DETERMINE ({type(exc).__name__}: {str(exc)[:100]})"}


def non_alive_lines(*, limit: int = 12) -> list[str]:
    """DEAD/STALE rows first, one line each, for the morning report and the
    Telegram brief. Uses the newest probe receipt when it is <= 2 h old, else
    computes the file-derived probes now. Never raises."""
    try:
        rec = newest_receipt()
        age = _age(_ts((rec or {}).get("generated_utc")), _utcnow())
        if rec and age is not None and age <= RECEIPT_MAX_AGE_S:
            rows, src = rec["rows"], f"probe receipt {_fmt_age(age)} old"
        else:
            rows = run(ctx=make_ctx(allow_proc=False))["rows"]
            src = "computed now, file probes only (no probe receipt within 2 h)"
        bad = [r for r in rows if r["verdict"] in ("DEAD", "STALE")]
        unk = sum(1 for r in rows if r["verdict"] == "UNKNOWN")
        head = (f"_subsystems: {len(bad)} DEAD/STALE, {unk} UNKNOWN of {len(rows)} ({src})_")
        body = [f"- {row_line(r)}" for r in bad[:limit]
                if r.get("probe") != "disk_free" and r.get("name") != "disk_free"] + (
            [f"- ... {len(bad) - limit} more in backend/data/optimus/health/HEALTH.md"]
            if len(bad) > limit else [])
        # The disk is measured NOW, not read from the receipt, and LEADS the
        # block when it is STALE/DEAD (2026-09-27: C: at 0 bytes read healthy).
        d = disk_status()
        if d["verdict"] in ("DEAD", "STALE"):
            return [f"- {d['line']}", head] + body
        return [head] + body + [f"- {d['line']}"]
    except Exception as exc:                                        # noqa: BLE001
        return [f"_subsystems: CANNOT DETERMINE ({type(exc).__name__}: {str(exc)[:120]})_"]
