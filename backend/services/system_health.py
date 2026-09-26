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
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Union

Verdict = Literal["ALIVE", "STALE", "DEAD", "UNKNOWN"]
VERDICT_ORDER = {"DEAD": 0, "STALE": 1, "UNKNOWN": 2, "ALIVE": 3}

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


def p_always_on_lab(ctx: ProbeCtx) -> ProbeResult:
    d = _lab_status(ctx)
    if d is None:
        return _unknown("no readable lab_status.json")
    hb = float(d.get("heartbeat_minutes") or 5)
    return _process_verdict(ctx, pid=d.get("pid"), module="always_on_lab",
                            stamp=_ts(d.get("utc")), cadence=timedelta(minutes=hb),
                            what="always_on_lab")


def p_lab_loops(ctx: ProbeCtx) -> ProbeOut:
    d = _lab_status(ctx)
    if d is None or not isinstance(d.get("loops"), dict):
        return _unknown("no lab_status.json loops block")
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


def p_sim_session(ctx: ProbeCtx) -> ProbeResult:
    s = _read_json(ctx.optimus_dir / "sim" / "session.json")
    if not isinstance(s, dict):
        last = _last_json_row(ctx.optimus_dir / "sim" / "sessions.jsonl")
        s = last if isinstance(last, dict) else None
    if not s:
        return _unknown("no sim/session.json and no sim/sessions.jsonl row")
    state = str(s.get("state", "?"))
    hb = _ts(s.get("heartbeat"))
    trading_now = in_session_hours(ctx.now)
    if state in ("RUNNING", "STOPPING"):
        r = _process_verdict(ctx, pid=s.get("pid"), module="sim_run", stamp=hb,
                             cadence=timedelta(minutes=10), what=f"sim {s.get('id')} {state}")
        if r.verdict == "DEAD":
            r.detail += " -- UNCLEAN: no stop receipt was written"
        return r
    ended = _ts(s.get("ended")) or hb
    if trading_now:
        return ProbeResult("DEAD", _iso(ended), _age(ended, ctx.now),
                           f"US session is open and no sim is running (last session "
                           f"{s.get('id')} {state}, ended {_fmt_age(_age(ended, ctx.now))} ago); "
                           f"no scheduler starts one",
                           proof=f"sim/session.json state={state}")
    return ProbeResult("ALIVE", _iso(ended), _age(ended, ctx.now),
                       f"idle outside US hours: last session {s.get('id')} {state} "
                       f"({s.get('end_reason') or '-'}); nothing schedules the next one",
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


def p_u_forecast(ctx: ProbeCtx) -> ProbeResult:
    L = _ledger_scan(ctx)
    if not L or not L["newest_made"]:
        return _unknown("no forecast ledger, or no row carries a `made_at`")
    newest = _ts(L["newest_made"])
    last = last_closed_session(ctx.now)
    v: Verdict = "ALIVE" if newest and newest.date() >= last else "STALE"
    return ProbeResult(v, _iso(newest), _age(newest, ctx.now),
                       f"newest forecast made {_fmt_age(_age(newest, ctx.now))} ago; "
                       f"{L['made_today']} made today (UTC); last session {last}",
                       delta=L["made_today"], proof="predictions.jsonl max(made_at)")


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
    detail = f"{newest.name} written {_fmt_age(_age(dt, ctx.now))} ago"
    try:
        from backend.services import accrual_canary as AC           # noqa: PLC0415
        nc = AC.n_considered_row(folder, ctx.path("funnel", ctx.optimus_dir.parent / "funnel_night10.json"))
        detail += f"; {nc.get('reason') or nc.get('line') or nc.get('status')}"
        if nc.get("status") == "DEGRADED":
            v = "STALE"
    except Exception as exc:                                        # noqa: BLE001
        detail += f"; n_considered row unavailable ({type(exc).__name__})"
    return ProbeResult(v, _iso(dt), _age(dt, ctx.now), detail,
                       proof=f"decisions/{newest.name} written_utc")


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


def p_book_grader(ctx: ProbeCtx) -> ProbeResult:
    _, dp = _newest_daily_pass(ctx)
    last = last_closed_session(ctx.now)
    lb = _newest_named(ctx.optimus_dir / "strategy_library", "leaderboard_*T*Z.json")
    lb_s = ""
    if lb:
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)", lb.name)
        if m:
            lbt = datetime.strptime(m.group(1), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            lb_s = f"; newest leaderboard {lb.name} ({_fmt_age(_age(lbt, ctx.now))} old)"
    nvs = ((dp or {}).get("scoreboard") or {}).get("nav_vs_spy") or {}
    ld = _ts((nvs.get("window") or {}).get("last_date"))
    if ld is None:
        return _unknown("no daily_pass scoreboard.nav_vs_spy.window.last_date" + lb_s)
    n = sessions_behind(ld.date(), last)
    return ProbeResult("ALIVE" if n == 0 else "STALE", _iso(ld), _age(ld, ctx.now),
                       f"books graded through {ld.date()}, {n} session(s) behind {last}" + lb_s,
                       proof="daily_pass scoreboard.nav_vs_spy.window.last_date")


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
        return ProbeResult("STALE", _iso(ctx.now), 0.0,
                           f"gateway up but degraded capability: {cap}",
                           proof="openclaw gateway status: Capability")
    return ProbeResult("ALIVE", _iso(ctx.now), 0.0,
                       f"gateway running, probe ok, capability {cap or 'not printed'}",
                       proof="openclaw gateway status: Connectivity probe: ok")


def p_openclaw_api_bridge(ctx: ProbeCtx) -> ProbeResult:
    return _unknown("openclaw_api_bridge writes no heartbeat or receipt; nothing derivable")


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
                       + ("" if v == "ALIVE" else " -- tools/refresh_aegis.py has no scheduled caller"),
                       proof="aegis-health-latest.md `generated` stamp")


#: Tasks whose outcome another probe judges from the job's own receipt; their
#: schtasks row is not repeated (Last Result is cmd's rc, not the job's).
_TASK_RECEIPT = {"AegisDailyPass": "daily_pass", "AegisIIF1NightLauncher": "iif1_night",
                 "AegisTelegramAgent": "telegram_agent"}


def p_scheduled_tasks(ctx: ProbeCtx) -> ProbeOut:
    tasks = _schtasks(ctx)
    if tasks is None:
        return _unknown("`schtasks /query /fo CSV /v` could not be read")
    out = {}
    for name, row in tasks.items():
        lr = f"Last Run {row.get('Last Run Time')}, Last Result {row.get('Last Result')}"
        if row.get("Scheduled Task State") == "Disabled":
            continue
        if name in _TASK_RECEIPT:
            continue
        if row.get("Next Run Time") in ("N/A", "") and "One Time" in str(row.get("Schedule Type")):
            out[name] = _unknown(f"one-shot task, {lr}; retired -- delete it")
        else:
            out[name] = _unknown(f"{lr}; Last Result is cmd's rc, not the job's, and no receipt "
                                 f"is mapped for this task")
    return out or _unknown("no Aegis* scheduled tasks found")


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
    Probe("u_forecast", "pc", D1, "predictions.jsonl: max(made_at), rows made today", p_u_forecast),
    Probe("forecast_ledger", "pc", D1, "predictions.jsonl: new_rows_since_last_run", p_forecast_ledger),
    Probe("u_review", "pc", D1, "review/review_<last_session>.json: generated_utc", p_u_review),
    Probe("u_plan", "pc", D1, "pc_book/<d>/intended_book.json: t, asof, invested_frac", p_u_plan),
    Probe("decision_contract", "pc", D1, "decisions/<d>.json: written_utc + n_considered run", p_decision_contract),
    Probe("forecast_grader", "pc", D1, "predictions.jsonl: max(resolved_at) vs due rows; daily_pass 'wait on a bar'", p_forecast_grader),
    Probe("book_grader", "pc", D1, "daily_pass scoreboard.nav_vs_spy.window.last_date + leaderboard_<ts>.json", p_book_grader),
    Probe("learn_rota", "pc", D1, "pc_book/<d>/learn_*.json: status / skipped", p_learn_rota),
    Probe("daily_pass", "pc", D1, "night_factory_<d>/daily_pass_<d>.json: steps[*].utc/status (+ schtasks)", p_daily_pass),
    Probe("iif1_night", "pc", D1, "iif1_nights/<last weekday>.json: status, spend_usd", p_iif1_night),
    Probe("news_collectors", "pc", timedelta(minutes=15), "news_corpus/_receipts/<ts>_ALL.json + newest first_seen_utc per source", p_news_collectors),
    Probe("social", "pc", timedelta(hours=6), "lab_status.loops.social_pull.per_source", p_social_sources),
    Probe("dowjones_feeds", "pc", D1, "dowjones/feeds_<d>.json: generated_utc", p_dowjones_feeds),
    Probe("telegram_agent", "pc", timedelta(seconds=60), "telegram/heartbeat.json|update_offset.json + agent.pid cmdline", p_telegram_agent, True),
    Probe("openclaw_gateway", "pc", timedelta(minutes=5), "`openclaw gateway status`: Runtime, Connectivity probe, Capability", p_openclaw_gateway, True),
    Probe("openclaw_api_bridge", "pc", D1, "none written", p_openclaw_api_bridge),
    Probe("llama_server", "pc", D1, "GET :8080/health + owner note + lab l2_typing", p_llama_server, True),
    Probe("llama_reaper", "pc", timedelta(seconds=30), "llama_reaper.log.jsonl[-1]: t, action", p_llama_reaper),
    Probe("optimus_brain", "pc", timedelta(hours=24), "optimus aegis-health-latest.md: `generated` stamp", p_optimus_brain),
    Probe("task", "pc", D1, "schtasks /query /fo CSV /v (Last Run; never Last Result alone)", p_scheduled_tasks, True),
    Probe("railway_backend", "external", D1, "GET /api/health/full: deploy.uptime_seconds, scheduler.nav.all_fresh", p_railway_backend, True),
    Probe("railway_fleet", "external", D1, "`railway status` linked service (+ logs)", p_railway_fleet, True),
    Probe("ci", "external", D1, "gh run list --commit origin/main: conclusion", p_ci, True),
    Probe("git", "pc", D1, "git rev-list --count origin/main..HEAD", p_git, True),
    Probe("accrual_canary", "pc", D1, "accrual_canary.forecast_accrual + n_considered_row (PC paths)", p_accrual_canary),
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
    return {"name": name, "probe": p.name, "where": p.where,
            "cadence_s": p.cadence.total_seconds(), "evidence": p.evidence, **asdict(r)}


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


def exit_code(rows: list[dict]) -> int:
    """1 any DEAD · 2 any STALE · 3 all UNKNOWN · 0 otherwise."""
    c = counts(rows)
    if c["DEAD"]:
        return 1
    if c["STALE"]:
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
           "exit_code": exit_code(rows), "rows": rows,
           "read_me_first": ("Every verdict is derived from evidence the producer wrote (a stamp "
                             "inside a receipt, a pid answering with its module, an HTTP body "
                             "field, a row-count delta) -- never an mtime or a lock file alone. "
                             "UNKNOWN names why the evidence is missing; it is never ALIVE.")}
    if persist:
        hd.mkdir(parents=True, exist_ok=True)
        stamp = ctx.now.strftime("%Y%m%dT%H%M%SZ")
        p = hd / f"health_{stamp}.json"
        p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        (hd / "HEALTH.md").write_text(render_md(out), encoding="utf-8")
        with open(hd / "health_index.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": out["generated_utc"], "path": p.name,
                                "counts": out["counts"], "exit_code": out["exit_code"]}) + "\n")
        state = {**ctx.prev_state, **ctx.new_state, "generated_utc": out["generated_utc"]}
        if "pending_model_since" not in ctx.new_state:
            state.pop("pending_model_since", None)
        if "no_bar" not in ctx.new_state:
            state.pop("no_bar", None)
        (hd / "_state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
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
         f"{'verdict':<8} {'subsystem':<34} {'age':>7}  detail", "-" * width]
    for r in out["rows"]:
        L.append(f"{r['verdict']:<8} {r['name'][:34]:<34} {_fmt_age(r.get('age_s')):>7}  "
                 f"{str(r['detail'])[:width - 54]}")
    return "\n".join(L)


def render_md(out: dict) -> str:
    L = [f"# HEALTH — {out['generated_utc']}", "",
         f"counts {out['counts']} · exit code {out['exit_code']} · source {out['source']}", "",
         "| verdict | subsystem | evidence (UTC) | age | detail | proof |",
         "|---|---|---|---|---|---|"]
    for r in out["rows"]:
        L.append(f"| {r['verdict']} | {r['name']} | {r.get('evidence_utc') or '-'} | "
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
                 "counts": out["counts"], "exit_code": out["exit_code"],
                 "rows": [{k: r.get(k) for k in ("name", "verdict", "where", "evidence_utc",
                                                 "age_s", "detail", "delta", "proof")}
                          for r in out["rows"]]}
    except Exception as exc:                                        # noqa: BLE001
        block = {"generated_utc": _iso(_utcnow()), "source": "error", "counts": {},
                 "exit_code": None, "rows": [],
                 "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    _API_CACHE["v"] = (now, block)
    return block


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
        return [head] + [f"- {row_line(r)}" for r in bad[:limit]] + (
            [f"- ... {len(bad) - limit} more in backend/data/optimus/health/HEALTH.md"]
            if len(bad) > limit else [])
    except Exception as exc:                                        # noqa: BLE001
        return [f"_subsystems: CANNOT DETERMINE ({type(exc).__name__}: {str(exc)[:120]})_"]
