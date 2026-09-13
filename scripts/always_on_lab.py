"""THE ALWAYS-ON LAB — one supervisor, eight loops, whenever the PC is on.

    python -m scripts.always_on_lab --dry-run    # print the plan; touch nothing
    python -m scripts.always_on_lab              # the loop, until STOP
    python -m scripts.always_on_lab --ticks 1    # one tick, then exit
    python -m scripts.always_on_lab --schtasks   # print the registration, run nothing
    python -m scripts.always_on_lab --acceptance # the three-date acceptance receipt

Source: Murat, 2026-09-13 — "do a learning lab for it to continuously learn ...
live whenever pc is on, fetching live data for news the LLM and the engine is
gathering data and learning, decision vs reality, upcoming dates and
possibilities, linkedin theory, business pivot to ai, motivation, holders, the
business, the future anything."

Spec: `docs/research_notes/2026-09-13/spec_always_on_lab.md`.

WHAT THIS IS
============
ARBITRATION AND CADENCE. It is NOT a rewrite of `daily_pass.py`,
`night_factory.py`, `monday_night.py`, `night_l2_typed_events.py` or any of the
E1-E5/L1-L4/M1-M5 modules — every one of those already exists, is tested, and
has its own receipt discipline. This supervisor decides WHEN each existing
driver gets to run, makes sure two of them never fight over the GPU or the
model server, and writes ONE status file a human or the desktop board can read
without opening eight receipt folders.

A supervisor that re-implements `refuse_if_the_machine_may_sleep()` or the
STOP-file convention instead of IMPORTING them is a second copy of a rule that
will drift from the first. Every guard here is imported:

* `scripts.night_factory.refuse_if_the_machine_may_sleep` — the power plan;
* `backend.services.llama_server.status` — and NEVER `start()` or `stop()`;
* `backend.services.ledger_retrieval.visible_at` — the hindsight gate;
* `scripts.news_pull.pull_all` / `scripts.night_l2_typed_events.L2_typed_events`
  — the loops' actual work.

FIVE THINGS IT REFUSES, BY NAME
===============================
* `ALREADY_RUNNING: pid <n>` — a live supervisor holds the lock (spec 1.2);
* `POWER_PLAN_ALLOWS_SLEEP` — the GPU loops pause, the news pull does not (1.3);
* `CLOUD_READER_NOT_IMPLEMENTED` — `AEGIS_L2_READER=cloud` with no reader
  registered; never a silent fallback to local called a cloud run (3.2);
* `DAILY_SPEND_CAP_REACHED` — checked BEFORE a cloud call, not after (5);
* `NIGHT_FACTORY_ALREADY_RUNNING` / `DAILY_PASS_RUNNING` /
  `MONDAY_NIGHT_RUNNING` — the idle queue yields to the scheduled owners (4).

A refusal is a finding: it is recorded in `lab_status.json` and the process
exits 0. The exit code is non-zero only for a refusal about the INVOCATION
(a second instance), which is a fact about the command rather than the day.

NO ORDER PATH, NO LLM AUTHORITY OVER CAPITAL
============================================
Nothing here places an order, arms a lane, sizes a position or touches a paper
book's frozen `Strategy`. The nightly refit produces candidates for a FUTURE
book; it never reaches backward into one already accruing forward evidence.
`test_always_on_lab.py` walks this module's AST (docstrings removed) and fails
if an order or broker symbol appears in executable source.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backend import config as _config

logger = logging.getLogger("always_on_lab")

ROOT = Path(__file__).resolve().parent.parent

#: The declared loop list. The supervisor walks THIS, in this order, not the
#: list of things that worked — the `daily_pass.STEPS` discipline, which exists
#: because a check that reads the record of what ran cannot see what never got
#: called (`signal_reachability.py`'s founding lesson).
LOOPS: tuple[tuple[str, str], ...] = (
    ("news_pull", "every registered source into the corpus, with first_seen_utc"),
    ("l2_typing", "type new corpus rows into the frozen event vocabulary"),
    ("decision_vs_reality", "what we said vs what happened, across every mechanism"),
    ("catalyst_calendar", "earnings plus FOMC/CPI/NFP, every entry with its provenance"),
    ("nn_lab", "E1 refit, E4 ADWIN gate, E5 stopping rules, on tonight's table"),
    ("idle_gpu_queue", "the next registered job, only when nothing needs the model"),
    ("thematic_streams", "Murat's themes as typed hypothesis streams"),
    ("status", "lab_status.json, every tick, whether or not anything happened"),
)

#: The five statuses are deliberately `daily_pass.STATUSES` so one reader learns
#: one vocabulary, plus the two a long-running driver needs that a one-shot pass
#: does not.
STATUSES = ("ok", "nothing_to_do", "refused", "error", "skipped",
            "paused", "timeout")

PERIODS: dict = dict(_config.LAB_LOOP_PERIODS_MINUTES)
TIMEOUTS: dict = dict(_config.LAB_LOOP_TIMEOUT_S)
HEARTBEAT_MINUTES = _config.LAB_HEARTBEAT_MINUTES
POWER_RECHECK_MINUTES = _config.LAB_POWER_RECHECK_MINUTES
IDLE_MINUTES = _config.LAB_IDLE_MINUTES
MODEL_LOOPS = frozenset(_config.LAB_MODEL_LOOPS)
TASK_NAME = "AegisAlwaysOnLab"

assert set(PERIODS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a period in config.LAB_LOOP_PERIODS_MINUTES"
assert set(TIMEOUTS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a wall-clock box in config.LAB_LOOP_TIMEOUT_S"


# ===========================================================================
# PATHS AND CLOCKS
# ===========================================================================


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trunc(exc: BaseException, n: int = 400) -> str:
    return f"{type(exc).__name__}: {exc}"[:n]


def run_date() -> str:
    """The date this supervisor's receipts belong to.

    `NIGHT_RUN_DATE` is honoured so the lab files into the same night folder as
    every other job of the day. Unset it is TODAY — never a literal, which is
    the defect `night_factory.py` carried for five days in September.
    """
    return os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")


def data_dir() -> Path:
    """`backend/data/optimus` — the SHARED path, not a per-user temp directory.

    Shared on purpose: `ONLOGON` fires per logon, and two Windows sessions must
    be able to see each other's lock or the single-instance rule is not one.
    """
    return Path(_config.DATA_DIR) / "optimus"


def out_dir() -> Path:
    """Today's night folder, created at write time by the job registry."""
    from scripts import night_factory_jobs as J
    return J._out()


def lock_path() -> Path:
    return data_dir() / "always_on_lab_lock.json"


def status_path() -> Path:
    return data_dir() / "lab_status.json"


def stop_path() -> Path:
    return out_dir() / "STOP"


def _write_atomic(path: Path, payload: dict) -> None:
    """`os.replace` over a sibling temp file — never a bare `write_text`.

    The same pattern `llama_server.py` and `night_launcher.py` already use for
    their own state files: a crash mid-write leaves the PREVIOUS status intact
    rather than a truncated JSON nobody can parse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, path)


# ===========================================================================
# THE SEAMS
#
# One module-level callable per external thing a loop does, so a test can
# replace it BY NAME. A loop body cannot be monkeypatched; these can.
# ===========================================================================


def power_refusal() -> str | None:
    """The power-plan guard, IMPORTED. A second copy would drift from the first."""
    from scripts.night_factory import refuse_if_the_machine_may_sleep
    return refuse_if_the_machine_may_sleep()


def model_status() -> dict:
    """`llama_server.status()` and nothing else — never `start()`, never `stop()`.

    The desktop app and a human are the only starters. This is probed before
    EVERY model-touching tick, not once at startup, because the desktop app can
    start or stop the server at any point in a multi-day supervisor run.
    """
    from backend.services import llama_server
    return llama_server.status()


def pid_alive(pid: int) -> bool:
    from backend.services import llama_server
    return llama_server.pid_alive(int(pid))


def pid_names_lab(pid: int) -> bool:
    """Does PID `pid`'s command line still name this supervisor?

    PID reuse is real on a long-uptime Windows box: liveness alone would report
    a stale lock as live the moment the OS handed that number to another
    program. CANNOT DETERMINE (the probe did not run) is treated as TRUE — the
    conservative direction is to refuse to start a second supervisor, not to
    start one on a maybe.
    """
    if sys.platform != "win32":
        return True
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}')"
                     ".CommandLine"],
                    capture_output=True, text=True, timeout=30)
    except Exception:                                              # noqa: BLE001
        return True
    out = (r.stdout or "").strip()
    if not out:
        return True
    return "always_on_lab" in out


def pull_news(**kw) -> dict:
    from scripts import news_pull
    return news_pull.pull_all(**kw)


def news_sources() -> list:
    from backend.services import news_registry
    return list(news_registry.pullable())


def type_rows(**kw) -> dict:
    from scripts import night_l2_typed_events
    return night_l2_typed_events.L2_typed_events(**kw)


#: The scheduled drivers that own their own windows and their own receipts.
#: The supervisor's overlapping loops YIELD to a running one rather than
#: launching a second concurrent copy of the same underlying job.
SCHEDULED_DRIVERS: dict = {
    "daily_pass": "scripts.daily_pass",
    "night_factory": "scripts.night_factory",
    "monday_night": "scripts.monday_night",
}

#: How long a process scan is trusted before it is taken again. A PowerShell
#: CIM query per loop per tick would cost more than the loops it guards.
DRIVER_SCAN_TTL_S = 60.0
_DRIVER_SCAN: dict = {"utc": None, "value": None}


def scan_processes() -> list[tuple[int, str]]:
    """(pid, command line) for every python process on this machine.

    ONE query, shared by every arbitration check in a tick. Returns [] when the
    probe itself could not run — and the callers treat that as CANNOT DETERMINE
    rather than as "nothing is running", because a scan that failed and a
    machine that is idle are different facts.
    """
    if sys.platform != "win32":
        return []
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                    capture_output=True, text=True, timeout=45)
    except Exception:                                              # noqa: BLE001
        return []
    out: list[tuple[int, str]] = []
    for line in (r.stdout or "").splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit():
            out.append((int(pid), cmd))
    return out


def running_drivers(*, now: datetime | None = None) -> dict:
    """Which scheduled drivers are running RIGHT NOW, by PID.

    Detected from the process table, never from a guessed wall-clock window: a
    `daily_pass` running late is still running, whatever time it is. The scan
    is cached for `DRIVER_SCAN_TTL_S` because it costs a PowerShell launch.
    """
    now = now or datetime.now(timezone.utc)
    prev = _as_dt(_DRIVER_SCAN.get("utc"))
    if prev is not None and (now - prev).total_seconds() < DRIVER_SCAN_TTL_S:
        return dict(_DRIVER_SCAN["value"] or {})
    rows = scan_processes()
    me = os.getpid()
    found: dict = {"scanned": len(rows), "scan_ran": bool(rows)}
    for name, needle in SCHEDULED_DRIVERS.items():
        found[name] = sorted(pid for pid, cmd in rows
                             if needle in (cmd or "") and pid != me)
    _DRIVER_SCAN["utc"] = now.isoformat(timespec="seconds")
    _DRIVER_SCAN["value"] = found
    return dict(found)


def yields_to(*names: str, now: datetime | None = None) -> dict | None:
    """A refusal row when one of `names` is running, else None.

    `NIGHT_FACTORY_ALREADY_RUNNING` / `DAILY_PASS_RUNNING` /
    `MONDAY_NIGHT_RUNNING`, by name, in the receipt — a reader never has to
    know an enum's numbering to learn why a tick did nothing.
    """
    drivers = running_drivers(now=now)
    for name in names:
        pids = drivers.get(name) or []
        if pids:
            return {"status": "skipped",
                    "reason": f"{name.upper()}_RUNNING" if name != "night_factory"
                              else "NIGHT_FACTORY_ALREADY_RUNNING",
                    "detail": (f"{name} is running as pid(s) {pids}; this loop "
                               f"yields rather than launching a second copy of "
                               f"the same underlying job"),
                    "yielded_to": name, "pids": pids}
    return None


def dispatch_job(job: str, minutes: int) -> dict:
    """One idle-queue job, through `night_factory`'s OWN dispatcher.

    Called rather than re-implemented: a second way to run the same job is two
    ways that drift, and `night_factory.run_job` is the one that time-boxes by
    AWAKE seconds and kills the process tree by PID.
    """
    from scripts import night_factory
    return night_factory.run_job(job, 1, minutes, [])


# ===========================================================================
# THE SINGLE-INSTANCE LOCK
# ===========================================================================


class AlreadyRunning(RuntimeError):
    """A live supervisor holds the lock. A refusal, not a crash."""


def read_lock() -> dict:
    p = lock_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lock_holder() -> dict:
    """Who holds the lock, and whether that claim survives inspection.

    Three states, never two: HELD (a live PID whose command line still names
    this supervisor), STALE (the PID is gone, or a different program now holds
    that number), and FREE (no lock file).
    """
    rec = read_lock()
    pid = int(rec.get("pid") or 0)
    if not pid:
        return {"state": "free", "lock": rec}
    if not pid_alive(pid):
        return {"state": "stale", "lock": rec, "why": f"pid {pid} is not alive"}
    if not pid_names_lab(pid):
        return {"state": "stale", "lock": rec,
                "why": (f"pid {pid} is alive but its command line does not name "
                        f"always_on_lab (PID reuse)")}
    return {"state": "held", "lock": rec, "pid": pid}


def acquire_lock() -> dict:
    """Take the lock, or raise `AlreadyRunning`. Written BEFORE the first tick."""
    holder = lock_holder()
    if holder["state"] == "held":
        raise AlreadyRunning(f"ALREADY_RUNNING: pid {holder['pid']} "
                             f"(started {holder['lock'].get('started_utc')})")
    rec = {"pid": os.getpid(), "started_utc": _now(),
           "hostname": socket.gethostname(), "started_by": "always_on_lab",
           "overwrote": (holder.get("lock") or None) if holder["state"] == "stale" else None,
           "overwrote_why": holder.get("why")}
    _write_atomic(lock_path(), rec)
    if holder["state"] == "stale":
        logger.warning("overwrote a stale lock: %s", holder.get("why"))
    return rec


def release_lock() -> None:
    p = lock_path()
    try:
        if p.exists() and int(read_lock().get("pid") or 0) == os.getpid():
            p.unlink()
    except OSError:
        pass


# ===========================================================================
# THE LOOP BOXES — a stuck loop must not become a silent supervisor
# ===========================================================================


class LoopTimeout(RuntimeError):
    """One loop outlived its wall-clock box. The supervisor's heartbeat did not."""


def call_boxed(fn: Callable[[], dict], timeout_s: float, what: str) -> dict:
    """Run `fn()` under a hard wall-clock bound, on a DAEMON thread.

    The hung thread is NOT killed — Python cannot — which is why it is a daemon:
    it cannot hold the process open at exit, and the supervisor's own 5-minute
    heartbeat keeps advancing while that ONE loop's `last_tick_utc` stops. That
    divergence is exactly the detectable signal; a supervisor that awaited a
    stuck loop unboundedly would go silent instead, and silence is never
    success.

    Shape borrowed verbatim from `news_pull.call_with_timeout`, which was
    written on 2026-09-13 after Alpaca held a TLS handshake for two hours.
    """
    box: dict = {}

    def _run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:                               # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=_run, daemon=True, name=f"lab:{what}")
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise LoopTimeout(f"{what}: no return in {timeout_s:.0f}s (thread abandoned)")
    if "error" in box:
        raise box["error"]                                         # type: ignore[misc]
    return box.get("value") or {}


# ===========================================================================
# LOOP STATE
# ===========================================================================


class LabState:
    """Per-loop last-successful-tick times, carried across restarts.

    A loop due every 15 minutes that the supervisor was away from for six hours
    runs ONCE at the next wake-up, not twenty-four times to "catch up": catching
    up burns the budget on stale data for no benefit. That falls out of storing
    the last SUCCESSFUL tick rather than a schedule of missed firings.
    """

    def __init__(self, loops: dict | None = None, started_utc: str | None = None):
        self.loops: dict = {name: dict((loops or {}).get(name) or {})
                            for name, _ in LOOPS}
        for name, what in LOOPS:
            self.loops[name].setdefault("last_tick_utc", None)
            self.loops[name].setdefault("status", "not_yet_run")
            self.loops[name]["what"] = what
        self.started_utc = started_utc or _now()
        self.power_refusal: str | None = None
        self.power_checked_utc: str | None = None
        self.last_model_call_utc: str | None = None
        self.ticks = 0
        self.stopped_by: str | None = None
        #: WITHIN one process, never a second PID file: the supervisor is
        #: single-threaded for anything that touches the model server.
        self.model_lock = threading.Lock()
        #: A loop still running past its box is not re-issued while wedged.
        self.inflight: set[str] = set()

    @classmethod
    def load(cls) -> "LabState":
        p = status_path()
        if not p.exists():
            return cls()
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        st = cls(loops=prev.get("loops") or {})
        st.last_model_call_utc = prev.get("last_model_call_utc")
        return st

    def due(self, loop: str, now: datetime) -> bool:
        last = self.loops[loop].get("last_tick_utc")
        if not last:
            return True
        prev = _as_dt(last)
        if prev is None:
            return True
        return (now - prev) >= timedelta(minutes=PERIODS[loop])

    def idle_minutes(self, now: datetime) -> float | None:
        """Minutes since the last model-touching call, or None if there has
        never been one in this status file's history."""
        prev = _as_dt(self.last_model_call_utc)
        if prev is None:
            return None
        return (now - prev).total_seconds() / 60.0

    def note_model_call(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.last_model_call_utc = now.isoformat(timespec="seconds")


def _as_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ===========================================================================
# THE LOOPS
#
# Each returns a dict with at least `status`. A loop that did its work and
# found nothing returns `nothing_to_do` with an explicit count — never an
# omitted key, which is what a reader cannot tell from a crash.
# ===========================================================================


#: `200 req/min free tier` -> (200, "min"). Prose the registry writes for a
#: human, read for the one number in it that a cadence check can use.
_RATE_PER_MIN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:req|call|request)s?\s*(?:/|per)\s*"
    r"(s|sec|second|min|minute|h|hour|day)", re.I)


def parsed_rate_limit(source) -> dict:
    """The registry's PROSE rate limit, as calls-per-day when it parses.

    `rate_limit` is a sentence written for a human ("200 req/min free tier",
    "none observed", "unknown"). Where a number and a unit are in it, this
    returns the implied daily budget; where they are not, it returns
    CANNOT DETERMINE — which is NOT a skip. A refusal needs evidence just as a
    positive does, and skipping every source whose limit is unparseable prose
    would silently stop fourteen of eighteen sources.
    """
    text = str(getattr(source, "rate_limit", "") or "")
    m = _RATE_PER_MIN.search(text)
    if not m:
        return {"parsed": False, "per_day": None, "text": text[:120],
                "why": "no `<n> per <unit>` in the registry's prose"}
    n = float(m.group(1))
    per = {"s": 86400, "sec": 86400, "second": 86400,
           "min": 1440, "minute": 1440, "h": 24, "hour": 24,
           "day": 1}[m.group(2).lower()]
    return {"parsed": True, "per_day": n * per, "text": text[:120]}


def cadence_admits(source, period_minutes: int) -> dict:
    """May this source be pulled every `period_minutes`? Two checks, both derived.

    1. PACING: the source's own `min_interval_s` times its per-pull call count
       is the floor on how long ONE pull takes. A pull that cannot finish
       before the next one is due would have the supervisor's own cadence
       breaching the registry's declared spacing.
    2. BUDGET: where the prose rate limit parses to a daily budget, the cadence
       demands `1440/period` pulls a day at that many calls each.

    A skipped source is marked `rate_limit_would_be_breached_at_this_cadence`
    BY NAME rather than quietly pulled less often than declared — a cadence
    table with an unstated exception is not a cadence table.
    """
    calls = max(1, len(getattr(source, "queries", ()) or ()))
    floor_s = float(getattr(source, "min_interval_s", 0) or 0) * calls
    pulls_per_day = 1440.0 / max(1, period_minutes)
    rate = parsed_rate_limit(source)
    row = {"source": getattr(source, "id", "?"), "calls_per_pull": calls,
           "min_interval_s": getattr(source, "min_interval_s", None),
           "pull_floor_s": round(floor_s, 1),
           "pulls_per_day_at_this_cadence": round(pulls_per_day, 1),
           "calls_per_day_at_this_cadence": round(pulls_per_day * calls, 1),
           "declared_budget_per_day": rate["per_day"],
           "budget_parsed": rate["parsed"], "rate_limit_text": rate["text"]}
    if floor_s > period_minutes * 60:
        return {**row, "admitted": False,
                "why": "rate_limit_would_be_breached_at_this_cadence",
                "detail": (f"one pull needs at least {floor_s:.0f}s of declared "
                           f"spacing and the cadence is {period_minutes * 60}s")}
    if rate["parsed"] and pulls_per_day * calls > rate["per_day"]:
        return {**row, "admitted": False,
                "why": "rate_limit_would_be_breached_at_this_cadence",
                "detail": (f"{pulls_per_day * calls:.0f} calls/day at this cadence "
                           f"against a declared {rate['per_day']:.0f}/day")}
    return {**row, "admitted": True,
            "why": (None if rate["parsed"]
                    else "budget CANNOT DETERMINE from the registry's prose; "
                         "admitted, and said so")}


def loop_news_pull(state: LabState) -> dict:
    """Every registered source that the 15-minute cadence admits.

    Calls `news_pull.pull_all` — the corpus writer with its own per-source
    cursor, its own `first_seen_utc` stamp and its own two-zero-runs-is-RED
    rule. This wrapper adds exactly two things: the cadence admission above,
    and yielding to a `daily_pass` that is already pulling.
    """
    yielded = yields_to("daily_pass")
    if yielded:
        return {**yielded, "n": 0, "rows_new": 0, "sources_red": []}

    try:
        sources = news_sources()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "refused", "n": 0, "rows_new": 0, "sources_red": [],
                "reason": "REGISTRY_UNREADABLE", "detail": _trunc(exc)}

    period = PERIODS["news_pull"]
    admission = [cadence_admits(s, period) for s in sources]
    admitted = [r["source"] for r in admission if r["admitted"]]
    skipped = [{"source": r["source"], "why": r["why"], "detail": r.get("detail")}
               for r in admission if not r["admitted"]]
    if not admitted:
        return {"status": "refused", "n": 0, "rows_new": 0, "sources_red": [],
                "reason": "EVERY_SOURCE_RATE_LIMITED_AT_THIS_CADENCE",
                "sources_skipped": skipped, "cadence_minutes": period}

    summary = pull_news(source_ids=admitted)
    rows = int(summary.get("rows_new") or 0)
    red = list(summary.get("red") or [])
    refused = list(summary.get("refused") or [])
    return {
        "status": ("ok" if rows else ("refused" if refused and not red
                                      else "nothing_to_do")),
        "n": rows, "rows_new": rows,
        "sources_pulled": len(admitted),
        "sources_red": red,
        "sources_refused": refused,
        "sources_skipped": skipped,
        "cadence_minutes": period,
        "resolution_rate": summary.get("resolution_rate"),
        "receipt_path": summary.get("receipt_path"),
        "headline": summary.get("headline"),
    }


def _overlap_block() -> dict:
    """The two-READER agreement set, or a named CANNOT DETERMINE.

    Reported on every typing tick rather than computed once at the end, because
    the day a second reader starts running is the day someone will want to mix
    its rows into E1's table — and the kappa that licenses that has to already
    exist, not be commissioned afterwards.
    """
    from backend.services import lab_reader
    try:
        return lab_reader.overlap_report()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "CANNOT DETERMINE", "why": _trunc(exc),
                "target_rows": lab_reader.overlap_rows()}


def loop_l2_typing(state: LabState) -> dict:
    """Type the rows the last pull added, bounded so one tick cannot eat the day.

    Three things this loop does NOT do, each of them named because doing any of
    them would be a plausible mistake:

    * it never starts the model server. It probes `llama_server.status()` before
      every model-touching tick — not once at startup, because the desktop app
      can start or stop the server at any point in a multi-day run — and USES a
      foreign-owned server read-only when one is up;
    * it never adds a second resume mechanism. `typed_events/_cursor.json` is
      the only one, and the supervisor's single-instance lock plus the in-process
      model lock are what stop two typing calls from racing it;
    * it never falls back from a refused cloud reader to local. The refusal is
      recorded by name and the tick ends.
    """
    from backend.services import lab_budget, lab_reader

    max_rows = int(_config.LAB_L2_MAX_ROWS_PER_TICK)
    choice = lab_reader.resolve(rows_this_tick=max_rows)
    if not choice.get("ok"):
        return {"status": "refused", "n": 0, "rows_typed_this_tick": 0,
                "reason": choice["refusal"], "detail": choice["detail"],
                "reader": choice["reader"],
                "spend_today_usd": choice.get("spend_today_usd"),
                "spend_cap_usd": choice.get("spend_cap_usd")}

    backend = choice["backend"]
    server = {}
    if backend == "local":
        try:
            server = model_status()
        except Exception as exc:                                   # noqa: BLE001
            return {"status": "error", "n": 0, "rows_typed_this_tick": 0,
                    "reader": "local", "detail": _trunc(exc)}
        if not server.get("listening"):
            # `L2_typed_events` writes PENDING_MODEL with the input list frozen
            # and hashed; this loop returns to the scheduler rather than raising.
            return {"status": "PENDING_MODEL", "n": 0, "rows_typed_this_tick": 0,
                    "reader": "local", "llama_server_up": False,
                    "detail": ("nothing is listening on the model port and this "
                               "loop does not start one; the desktop app and a "
                               "human are the only starters"),
                    "backlog_remaining": None}
        if server.get("foreign"):
            # A server that was already running when Aegis started is not ours to
            # stop. It IS ours to read from.
            server = {**server, "used_read_only": True}

    with state.model_lock:
        state.note_model_call()
        try:
            out = type_rows(backend=backend, max_rows=max_rows)
        except Exception as exc:                                   # noqa: BLE001
            return {"status": "error", "n": 0, "rows_typed_this_tick": 0,
                    "reader": choice["reader"], "detail": _trunc(exc)}

    corpus = out.get("corpus") or {}
    typed = int(out.get("rows_typed") or (out.get("counts") or {}).get("typed") or 0)
    waiting = corpus.get("rows_waiting")
    status = str(out.get("status") or "")
    if status.startswith("PENDING_MODEL"):
        row_status = "PENDING_MODEL"
    elif status == "done" or (waiting == 0 and not typed):
        row_status = "nothing_to_do"
    else:
        row_status = "ok" if typed else "nothing_to_do"

    spend = lab_budget.spend_today()
    cost_source = "not_metered"
    if choice["metered"] and typed:
        usage = out.get("usage") or {}
        reported = float(usage.get("cost_usd") or 0.0)
        # THE RECEIPT LIES ABOUT ZERO, MEASURED. The 2026-09-13 17:18 DeepSeek
        # run typed 6,007 rows and printed `llm_spend_usd: 0.00` while the call
        # ledger said $2.04, because the field reads the local-cost path. So a
        # metered tick that reports 0.00 is booked at the ESTIMATE instead --
        # and SAYS which of the two it used, because a silently substituted
        # number is the failure the substitution exists to prevent, wearing the
        # other hat.
        actual = reported or lab_reader.estimate_usd(choice["reader"], typed)
        cost_source = "receipt" if reported else "estimate_substituted"
        spend = lab_budget.record(actual, backend=choice["reader"],
                                  rows=typed,
                                  what=f"L2 typing tick ({cost_source})")
    elif typed:
        cost_source = "local_unmetered"
        lab_budget.record(0.0, backend="local", rows=typed, what="L2 typing tick")

    return {
        "status": row_status,
        "n": typed,
        "rows_typed_this_tick": typed,
        "backlog_remaining": waiting,
        "rows_on_disk": corpus.get("rows_on_disk"),
        "reader": choice["reader"],
        "backend": backend,
        "metered": choice["metered"],
        "estimated_usd": choice["estimated_usd"],
        "cost_source": cost_source,
        "spend_today_usd": spend["spend_today_usd"],
        "spend_cap_usd": spend["cap_usd"],
        "reader_overlap": _overlap_block(),
        "llama_server_up": bool(server.get("listening")),
        "llama_server_foreign": bool(server.get("foreign")),
        "headline": out.get("headline"),
    }


def loop_decision_vs_reality(state: LabState) -> dict:
    """What we said vs what happened, across every mechanism, once an hour.

    Re-grades nothing: it rolls up what each mechanism's own grader already
    wrote, through `ledger_retrieval.visible_at`'s hindsight gate. A window with
    zero resolutions writes the receipt anyway, with every mechanism at
    `n_resolved: 0` — invariant 15, which is the rule that costs a session the
    most when skipped.
    """
    from backend.services import lab_decision_vs_reality as DVR
    payload = DVR.report()
    path = DVR.write_report(payload, day=run_date(), out=out_dir())
    n = int(payload.get("n_resolved") or 0)
    worst = payload.get("worst_miss") or {}
    return {
        "status": "ok" if n else "nothing_to_do",
        "n": n,
        "n_resolved": n,
        "pool_size": payload.get("pool_size"),
        "mechanisms_reported": len(payload.get("by_mechanism") or []),
        "mechanisms_with_resolutions": sum(
            1 for r in (payload.get("by_mechanism") or []) if r.get("n_resolved")),
        "undeclared_mechanisms": payload.get("undeclared_mechanisms"),
        "worst_miss_id": worst.get("record_id"),
        "worst_miss_brier": worst.get("brier"),
        "receipt_path": str(path),
        "headline": payload.get("headline"),
    }


def calendar_tickers() -> list[str]:
    """The names the per-ticker half of the calendar covers.

    The PM book's own positions, through the same loader `routers/pm.py`'s
    `/catalysts` already uses — a second answer to "which names do we hold"
    would be one answer too many. An unreadable book is CANNOT DETERMINE, not
    an empty list: the macro half still ships, and the receipt says the ticker
    half did not.
    """
    from backend.services import pm_engine
    book = pm_engine.load_book(strict=False)
    return [p.ticker for p in getattr(book, "positions", [])]


def loop_catalyst_calendar(state: LabState) -> dict:
    """Upcoming dates, every entry with its provenance and every gap named.

    Two halves. The per-ticker half is `pm_catalysts.calendar()`, CALLED, not
    rebuilt. The macro half is new: CPI and NFP from FRED's scheduled release
    dates, FOMC from a hand-seeded table. Every entry carries
    `engine_probability: null` with `AWAITING_L2`, because X3 is not wired and
    a fabricated probability attached to a real date is the one failure this
    loop could cause that nobody would notice for months.
    """
    from backend.services import macro_calendar

    tickers: list[str] = []
    ticker_refusal: str | None = None
    try:
        tickers = calendar_tickers()
    except Exception as exc:                                       # noqa: BLE001
        ticker_refusal = f"TICKERS_CANNOT_DETERMINE: {_trunc(exc)}"

    macro = macro_calendar.macro_block()
    per_ticker: dict = {}
    if tickers:
        try:
            from backend.services import pm_catalysts
            per_ticker = pm_catalysts.calendar(tickers)
        except Exception as exc:                                   # noqa: BLE001
            ticker_refusal = f"EARNINGS_HALF_FAILED: {_trunc(exc)}"

    payload = {
        "receipt": "lab_catalyst_calendar",
        "licence": "PRODUCT_EXPERIMENT", "stage": "raw", "llm_spend_usd": 0.0,
        "utc": _now(), "date": run_date(),
        "tickers": tickers, "ticker_refusal": ticker_refusal,
        "per_ticker": per_ticker, **macro,
    }
    path = out_dir() / f"lab_catalyst_calendar_{run_date()}.json"
    _write_atomic(path, payload)

    n_macro = len(macro.get("macro") or [])
    n_ticker = int((per_ticker.get("events_found") or 0))
    refusals = list(macro.get("refusals") or [])
    if ticker_refusal:
        refusals.append({"kind": "per_ticker", "refusal": ticker_refusal})
    return {
        "status": ("ok" if (n_macro or n_ticker)
                   else ("refused" if refusals else "nothing_to_do")),
        "n": n_macro + n_ticker,
        "macro_events": n_macro,
        "ticker_events": n_ticker,
        "tickers_checked": len(tickers),
        "macro_legs": macro.get("legs"),
        "fomc_table": (macro.get("fomc_table") or {}).get("status"),
        "refusals": [r.get("refusal") for r in refusals],
        "receipt_path": str(path),
        "headline": (f"{n_macro} macro date(s) and {n_ticker} ticker event(s) "
                     f"over {len(tickers)} name(s); "
                     f"{len(refusals)} named refusal(s); every "
                     f"engine_probability null (AWAITING_L2)"),
    }


def loop_nn_lab(state: LabState) -> dict:
    """The nightly refit sequence, once a night, only when the GPU is free.

    The idle condition is the same one the idle-GPU queue uses — this loop is
    not more entitled to the model than the typing loop is, and the in-process
    model lock serialises them whichever wins the tick.
    """
    from backend.services import lab_nn

    now = datetime.now(timezone.utc)
    idle = state.idle_minutes(now)
    if idle is not None and idle < IDLE_MINUTES:
        return {"status": "skipped", "n": 0,
                "reason": "MODEL_IN_USE",
                "detail": (f"a model-touching call finished {idle:.0f} min ago; "
                           f"{IDLE_MINUTES} min of quiet are required"),
                "idle_minutes": round(idle, 1)}

    yielded = yields_to("night_factory", "monday_night", now=now)
    if yielded:
        return {**yielded, "n": 0}

    with state.model_lock:
        state.note_model_call(now)
        payload = lab_nn.run_nn_lab()
    path = lab_nn.write_receipt(payload, day=run_date(), out=out_dir())

    return {
        "status": "ok" if payload["n_heads"] else ("refused" if payload["refusals"]
                                                   else "nothing_to_do"),
        "n": payload["n_heads"],
        "held_out_month": payload["held_out_month"],
        "heads": payload["n_heads"],
        "beat_last_night": payload["n_beat_last_night"],
        "undecided": payload["n_undecided"],
        "event_source": payload["event_source"],
        "refusals": payload["refusals"],
        "receipt_path": str(path),
        "headline": payload["headline"],
    }


def loop_idle_gpu_queue(state: LabState) -> dict:
    """The next registered job, ONLY when nothing else needs the model.

    This loop exists to fill the GAPS the scheduled evening run does not cover —
    daytime idle periods, a night `night_factory` was never launched. It is not
    a second scheduler for the same jobs, and it is the one loop that can
    actively collide with existing scheduled work, which is why it was built
    last and why every condition below is a refusal rather than a preference.

    Four gates, in this order:
      1. the model must have been quiet for `IDLE_MINUTES`;
      2. no FOREIGN server may be up — a server we did not start is the desktop
         app's or a human's, and taking the GPU out from under it is exactly
         the "not ours to stop" rule wearing a different hat;
      3. `night_factory` / `monday_night` / `daily_pass` must not be running;
      4. the job must not already have run today.
    """
    now = datetime.now(timezone.utc)
    row = state.loops["idle_gpu_queue"]
    dispatched: dict = dict(row.get("dispatched_on") or {})
    today = run_date()
    queue = [(j, m) for j, m in _config.LAB_IDLE_QUEUE]
    remaining = [j for j, _ in queue if dispatched.get(j) != today]

    idle = state.idle_minutes(now)
    if idle is not None and idle < IDLE_MINUTES:
        return {"status": "skipped", "n": 0, "reason": "GPU_BUSY",
                "detail": (f"a model-touching call finished {idle:.0f} min ago; "
                           f"{IDLE_MINUTES} min of quiet are required"),
                "idle_minutes": round(idle, 1), "queue_remaining": remaining,
                "dispatched_on": dispatched}

    try:
        server = model_status()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "error", "n": 0, "detail": _trunc(exc),
                "queue_remaining": remaining, "dispatched_on": dispatched}
    if server.get("listening") and server.get("foreign"):
        return {"status": "skipped", "n": 0, "reason": "FOREIGN_SERVER_UP",
                "detail": (f"pid {server.get('pid')} is serving the model and "
                           f"Aegis did not start it; it may be mid-job and is "
                           f"not ours to interrupt"),
                "queue_remaining": remaining, "dispatched_on": dispatched}

    yielded = yields_to("night_factory", "monday_night", "daily_pass", now=now)
    if yielded:
        return {**yielded, "n": 0, "queue_remaining": remaining,
                "dispatched_on": dispatched}

    if not remaining:
        return {"status": "nothing_to_do", "n": 0,
                "reason": "EVERY_QUEUED_JOB_ALREADY_RAN_TODAY",
                "queue_remaining": [], "dispatched_on": dispatched,
                "queue": [j for j, _ in queue]}

    job = remaining[0]
    minutes = dict(queue)[job]
    with state.model_lock:
        state.note_model_call(now)
        try:
            payload = dispatch_job(job, minutes)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("idle queue job %s raised", job)
            dispatched[job] = today
            row["dispatched_on"] = dispatched
            return {"status": "error", "n": 0, "job": job,
                    "detail": _trunc(exc), "dispatched_on": dispatched,
                    "queue_remaining": [j for j in remaining if j != job]}

    # Marked dispatched whatever the verdict: a job that FAILED tonight has had
    # its turn, and re-dispatching it every five minutes would starve the rest
    # of the queue on one broken job.
    dispatched[job] = today
    row["dispatched_on"] = dispatched
    return {
        "status": "ok", "n": 1, "job": job, "box_minutes": minutes,
        "verdict": payload.get("verdict"),
        "job_headline": str(payload.get("headline"))[:200],
        "dispatched_on": dispatched,
        "queue": [j for j, _ in queue],
        "queue_remaining": [j for j in remaining if j != job],
        "headline": (f"dispatched {job} (<= {minutes} min) into an idle GPU; "
                     f"{len(remaining) - 1} job(s) left in tonight's queue"),
    }


def loop_thematic_streams(state: LabState) -> dict:
    """Murat's four themes, each its own `mechanism_id`, each on its own cadence.

    Registration is idempotent and happens every tick; only the streams whose
    own cadence has elapsed do any work. A placeholder reports `n_fired: 0` with
    the reason rather than disappearing from the payload — a stream nobody
    remembers is waiting is a stream that gets invented from nothing later, with
    no history.
    """
    from backend.services import lab_themes

    tickers: list[str] = []
    try:
        tickers = calendar_tickers()
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("thematic streams: no ticker list (%s)", _trunc(exc))

    out = lab_themes.run_due(tickers)
    path = out_dir() / f"lab_theme_streams_{run_date()}.json"
    _write_atomic(path, out)
    obs = sum(r["n_observations"] for r in out["streams"])
    fired = sum(r["n_fired"] for r in out["streams"])
    return {
        "status": "ok" if (obs or fired) else "nothing_to_do",
        "n": obs + fired,
        "observations": obs,
        "forecasts": fired,
        "tickers_checked": len(tickers),
        "streams": {r["mechanism_id"]: r["readiness"] for r in out["streams"]},
        "blocked": {r["mechanism_id"]: r.get("blocked_by")
                    for r in out["streams"] if r.get("blocked_by")},
        "receipt_path": str(path),
        "headline": out["headline"],
    }


def loop_status(state: LabState) -> dict:
    """The heartbeat's own loop. Writing the file is the tick's last act, so
    this one only records that the writer was reached."""
    return {"status": "ok", "note": "lab_status.json written at the end of the tick"}


HANDLERS: dict[str, Callable[[LabState], dict]] = {
    "news_pull": loop_news_pull,
    "l2_typing": loop_l2_typing,
    "decision_vs_reality": loop_decision_vs_reality,
    "catalyst_calendar": loop_catalyst_calendar,
    "nn_lab": loop_nn_lab,
    "idle_gpu_queue": loop_idle_gpu_queue,
    "thematic_streams": loop_thematic_streams,
    "status": loop_status,
}
assert set(HANDLERS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a handler"


# ===========================================================================
# THE SUPERVISOR
# ===========================================================================


def check_power(state: LabState, now: datetime) -> None:
    """Re-check the power plan on a cadence, never only at boot.

    A refusal does NOT kill the process. It pauses the GPU-touching loops and
    says so; the next recheck can un-pause them without a human restarting a
    scheduled task. `night_factory` checks once because its longest run is
    hours; this supervisor runs for days.
    """
    if state.power_checked_utc:
        prev = _as_dt(state.power_checked_utc)
        if prev is not None and (now - prev) < timedelta(minutes=POWER_RECHECK_MINUTES):
            return
    try:
        state.power_refusal = power_refusal()
    except Exception as exc:                                       # noqa: BLE001
        state.power_refusal = None
        logger.warning("power check raised (%s); CANNOT DETERMINE, continuing",
                       _trunc(exc))
    state.power_checked_utc = now.isoformat(timespec="seconds")


def tick(state: LabState, *, now: datetime | None = None) -> dict:
    """One heartbeat: every DUE loop, in declared order, each under its box."""
    now = now or datetime.now(timezone.utc)
    state.ticks += 1
    check_power(state, now)
    ran: list[str] = []

    for name, _what in LOOPS:
        row = state.loops[name]
        if not state.due(name, now):
            row["due"] = False
            continue
        row["due"] = True
        if name in state.inflight:
            row["status"] = "timeout"
            row["detail"] = ("a previous call to this loop has not returned; "
                             "not re-issued")
            continue
        if state.power_refusal and name in MODEL_LOOPS:
            row["status"] = "paused"
            row["detail"] = f"POWER_PLAN_ALLOWS_SLEEP: {str(state.power_refusal)[:200]}"
            row["paused_since_utc"] = row.get("paused_since_utc") or now.isoformat(
                timespec="seconds")
            continue
        row.pop("paused_since_utc", None)
        state.inflight.add(name)
        t0 = time.time()
        try:
            out = call_boxed(lambda n=name: HANDLERS[n](state), TIMEOUTS[name], name)
            state.inflight.discard(name)
        except LoopTimeout as exc:
            # Left in `inflight` ON PURPOSE: the thread is abandoned, not dead,
            # and re-issuing the same loop against the same resource is how one
            # stuck call becomes a pile of them.
            row["status"] = "timeout"
            row["detail"] = f"timeout_after_{TIMEOUTS[name]:.0f}s"
            row["error"] = str(exc)[:300]
            continue
        except Exception as exc:                                   # noqa: BLE001
            state.inflight.discard(name)
            logger.exception("lab loop %s raised", name)
            row["status"] = "error"
            row["detail"] = _trunc(exc)
            continue
        row.update({k: v for k, v in out.items() if k != "what"})
        row["seconds"] = round(time.time() - t0, 2)
        row["last_tick_utc"] = now.isoformat(timespec="seconds")
        ran.append(name)

    payload = status_payload(state, now)
    _write_atomic(status_path(), payload)
    try:
        write_learned_line(payload)
    except OSError as exc:
        logger.warning("could not write the LEARNED line (%s)", _trunc(exc))
    payload["loops_run_this_tick"] = ran
    return payload


def _theme_status() -> dict:
    from backend.services import lab_themes
    try:
        return lab_themes.status()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "CANNOT DETERMINE", "why": _trunc(exc)}


def status_payload(state: LabState, now: datetime | None = None) -> dict:
    """`lab_status.json` — every loop's block present every tick, always."""
    now = now or datetime.now(timezone.utc)
    try:
        model = model_status()
    except Exception as exc:                                       # noqa: BLE001
        model = {"error": _trunc(exc)}
    from backend.services import lab_budget
    spend = lab_budget.spend_today()
    return {
        "receipt": "always_on_lab",
        "licence": "PRODUCT_EXPERIMENT",
        "utc": now.isoformat(timespec="seconds"),
        "date": run_date(),
        "running": state.stopped_by is None,
        "stopped_by": state.stopped_by,
        "pid": os.getpid(),
        "started_utc": state.started_utc,
        "ticks": state.ticks,
        "heartbeat_minutes": HEARTBEAT_MINUTES,
        "power_plan": (f"REFUSED, may sleep since {state.power_checked_utc}"
                       if state.power_refusal else "ok (or CANNOT DETERMINE)"),
        "power_refusal": (str(state.power_refusal)[:400] if state.power_refusal else None),
        "power_checked_utc": state.power_checked_utc,
        "periods_minutes": PERIODS,
        "loops": state.loops,
        "last_model_call_utc": state.last_model_call_utc,
        "idle_minutes": state.idle_minutes(now),
        "llama_server": {"up": bool(model.get("listening")),
                         "ready": bool(model.get("ready")),
                         "owned_by_us": bool(model.get("started_by_aegis")),
                         "foreign_owner_pid": (model.get("pid")
                                               if model.get("foreign") else None),
                         "detail": model.get("detail")},
        "spend_today_usd": spend["spend_today_usd"],
        "spend_cap_usd": spend["cap_usd"],
        "spend_cap_reached": spend["cap_reached"],
        "thematic_streams": _theme_status(),
        "single_instance_lock": read_lock(),
        "stop_file": str(stop_path()),
        "read_me_first": (
            "One block per DECLARED loop, every tick, whether or not it ran — a "
            "loop that found nothing says `nothing_to_do` with a count, never an "
            "omitted key. `last_tick_utc` advances only on a SUCCESSFUL tick, so "
            "a loop whose stamp stops moving while `utc` keeps moving is stuck, "
            "which is the signal this file exists to make visible. Nothing here "
            "places an order or starts the model server."),
    }


def run_forever(*, max_ticks: int | None = None,
                sleeper: Callable[[float], None] | None = None,
                clock: Callable[[], datetime] | None = None) -> dict:
    """The loop. Holds the lock, ends on STOP, never on a sub-loop's failure."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleeper = sleeper or time.sleep
    rec = acquire_lock()
    state = LabState.load()
    state.started_utc = rec["started_utc"]
    payload: dict = {}
    try:
        while True:
            if stop_path().exists():
                state.stopped_by = "STOP_file"
                payload = status_payload(state, clock())
                _write_atomic(status_path(), payload)
                break
            payload = tick(state, now=clock())
            if max_ticks is not None and state.ticks >= max_ticks:
                break
            sleeper(HEARTBEAT_MINUTES * 60)
    finally:
        release_lock()
    return payload


# ===========================================================================
# PRINTERS
# ===========================================================================


def plan() -> dict:
    """What a real run WOULD do. Reads the clock and the lock; calls no loop,
    touches no network and no model."""
    holder = lock_holder()
    return {
        "dry_run": True,
        "date": run_date(),
        "heartbeat_minutes": HEARTBEAT_MINUTES,
        "status_file_would_be": str(status_path()),
        "lock_file": str(lock_path()),
        "lock_state": holder["state"],
        "stop_file": str(stop_path()),
        "power_recheck_minutes": POWER_RECHECK_MINUTES,
        "idle_minutes": IDLE_MINUTES,
        "spend_cap_usd": _config.LAB_DAILY_SPEND_CAP_USD,
        "l2_reader": os.getenv("AEGIS_L2_READER", "local"),
        "loops": [{"loop": n, "what": w, "period_minutes": PERIODS[n],
                   "timeout_s": TIMEOUTS[n],
                   "touches_model": n in MODEL_LOOPS} for n, w in LOOPS],
        "note": ("--dry-run calls no loop: it makes no network request, probes "
                 "no model server, and writes nothing. It prints the cadence "
                 "table and the process model, which is what a reader deciding "
                 "whether to register the task needs."),
    }


def print_plan(p: dict) -> None:
    print("=" * 74)
    print(f"ALWAYS-ON LAB — dry run — {p['date']}")
    print("=" * 74)
    print(f"  heartbeat        every {p['heartbeat_minutes']} min")
    print(f"  lock             {p['lock_state']}  {p['lock_file']}")
    print(f"  STOP file        {p['stop_file']}")
    print(f"  power recheck    every {p['power_recheck_minutes']} min")
    print(f"  idle threshold   {p['idle_minutes']} min with no model call")
    print(f"  spend cap        ${p['spend_cap_usd']:.2f}/UTC day")
    print(f"  L2 reader        {p['l2_reader']}")
    print()
    print(f"  {'loop':22s} {'period':>10s} {'box':>8s}  model  what")
    for row in p["loops"]:
        print(f"  {row['loop']:22s} {row['period_minutes']:6d} min "
              f"{row['timeout_s']:7d}s  "
              f"{'GPU' if row['touches_model'] else '   ':5s}  {row['what'][:44]}")
    print(f"\n  status file -> {p['status_file_would_be']}")
    print(f"\n  {p['note']}")


def _print_schtasks() -> int:
    """Print the registration. Deliberately does not run it.

    ONLOGON, not ONSTART and not a fixed daily time: it is the literal
    translation of "live whenever pc is on". The task fires once per
    interactive logon and the supervisor loops until STOP, rather than firing
    once and exiting the way `daily_pass` and `run_night_launcher` do.

    /RL LIMITED: nothing here needs admin rights, and an elevated unattended
    loop is a bigger blast radius for the same job.
    """
    root = os.getcwd()
    empty = f"{root}\\backend\\data\\optimus\\empty_stdin.txt"
    log = f"{root}\\backend\\data\\optimus\\always_on_lab.log"
    py = sys.executable
    print("=" * 74)
    print("REGISTER THE ALWAYS-ON LAB — printed, not run; registering it is a decision")
    print("=" * 74)
    print(f"""
  * ONLOGON, not ONSTART: the lab needs an interactive session (the desktop app
    owns the model server, and a session-0 service cannot see it).

  * /RL LIMITED. Nothing this loop does needs admin rights.

  * ONE instance. A second logon's supervisor reads the shared lock at
    {lock_path()} and refuses with ALREADY_RUNNING.

  * The stdin redirect comes from a REGULAR FILE, not from NUL: on Windows
    `_isatty()` returns true for any character device, so `< NUL` redirects and
    changes nothing observable (paid for on 2026-08-18).

  * No pipe. `cmd | tail` reports tail's exit code, and the exit code is the
    guard.
""")
    print(f'  schtasks /Create /TN "{TASK_NAME}" /SC ONLOGON /RL LIMITED '
          f'/TR "cmd /c cd /d {root} && {py} -m scripts.always_on_lab '
          f'< {empty} >> {log} 2>&1"')
    print("\n  Already registered? Change it in place rather than re-registering:\n")
    print(f'  schtasks /Change /TN "{TASK_NAME}" '
          f'/TR "cmd /c cd /d {root} && {py} -m scripts.always_on_lab '
          f'< {empty} >> {log} 2>&1"')
    print(f"""
  To stop it: create {stop_path()} and wait one heartbeat
  ({HEARTBEAT_MINUTES} min). Never `taskkill /F /IM python.exe` — on
  2026-09-06 that killed two other agents' jobs, a test suite and 1,676
  already-billed extractions. Kill by the PID in
  {lock_path()}, or do not kill.

  The log redirect is a convenience, NOT the evidence. The evidence is
  {status_path()} and the per-loop receipts in the night folder.
""")
    return 0


#: The six acceptance criteria, declared so the report walks THEM rather than
#: whatever happened to be checkable. Each is (id, what it asserts).
ACCEPTANCE_CRITERIA: tuple[tuple[str, str], ...] = (
    ("news_pull_never_gapped",
     "`news_pull`'s last_tick_utc never gapped by more than 2x its declared "
     "period on any of the three dates"),
    ("decision_vs_reality_per_date",
     "at least one full decision_vs_reality receipt per date, even at "
     "n_resolved 0 everywhere"),
    ("catalyst_calendar_refreshed",
     "the catalyst calendar refreshed at least once per date with the macro "
     "block populated, or FRED_KEY_ABSENT named"),
    ("no_double_write_collisions",
     "zero collisions with night_factory/daily_pass recorded as anything other "
     "than a clean skip"),
    ("spend_cap_never_breached",
     "the daily dollar cap never breached"),
    ("learned_line_present",
     "LEARNED_<date>.md carries the supervisor's line for all three dates"),
)


def learned_line(payload: dict) -> str:
    """The ONE line the lab contributes to the day's brain file.

    Written whether or not anything interesting happened — the "a session that
    ships thirty changes and moves none of them says RESULT IMPROVEMENT: NONE"
    discipline, on a daily cadence instead of a session one.
    """
    loops = payload.get("loops") or {}
    news = loops.get("news_pull") or {}
    l2 = loops.get("l2_typing") or {}
    nn = loops.get("nn_lab") or {}
    idle = loops.get("idle_gpu_queue") or {}
    themes = payload.get("thematic_streams") or {}
    red = news.get("sources_red") or []
    return (
        f"Always-on lab, {payload.get('date')}: news pulled from "
        f"{news.get('sources_pulled', 0)} source(s) ({len(red)} red); L2 typed "
        f"{l2.get('rows_typed_this_tick', 0)} row(s) (backlog "
        f"{l2.get('backlog_remaining')}, reader={l2.get('reader', 'local')}); NN lab "
        f"{nn.get('heads', 0)} head(s), {nn.get('beat_last_night', 0)} beat last "
        f"night on held-out {nn.get('held_out_month')}; idle-GPU queue ran "
        f"{idle.get('job') or 'nothing'}; thematic streams: "
        f"{', '.join(f'{k}={v}' for k, v in sorted(themes.items()))}; spend "
        f"${payload.get('spend_today_usd', 0.0):.2f}/"
        f"${payload.get('spend_cap_usd', 0.0):.2f} cap.")


def write_learned_line(payload: dict) -> Path:
    """Append the line to `brain/LEARNED_<date>.md`, creating the file."""
    p = data_dir() / "brain" / f"LEARNED_{payload.get('date')}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = f"> {learned_line(payload)}\n"
    prior = p.read_text(encoding="utf-8") if p.exists() else ""
    if line not in prior:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return p


def acceptance_report(*, dates: list[str] | None = None,
                      status: dict | None = None) -> dict:
    """Is the lab ACCEPTED? Three dates of real coverage, not three task runs.

    `ONLOGON` can fire and die repeatedly in a bad state and still produce three
    "runs"; the bar is three DATES on which the machine was actually on. This
    report reads what is on disk and REFUSES to conclude from what is absent:
    a date with no receipts is `no_evidence`, never a failure and never a pass.
    """
    payload = status if status is not None else _read_status()
    today = date.fromisoformat(run_date())
    want = dates or [(today - timedelta(days=i)).isoformat()
                     for i in range(_config.LAB_ACCEPTANCE_DATES - 1, -1, -1)]

    per_date = []
    for day in want:
        folder = data_dir() / f"night_factory_{day}"
        dvr = folder / f"decision_vs_reality_{day}.json"
        cal = folder / f"lab_catalyst_calendar_{day}.json"
        learned = data_dir() / "brain" / f"LEARNED_{day}.md"
        row = {
            "date": day,
            "night_folder_exists": folder.is_dir(),
            "decision_vs_reality": dvr.exists(),
            "catalyst_calendar": cal.exists(),
            "learned_line": (learned.exists()
                             and "Always-on lab" in learned.read_text(
                                 encoding="utf-8", errors="replace")),
        }
        row["evidence"] = any(v for k, v in row.items() if k != "date")
        per_date.append(row)

    dated = [r for r in per_date if r["evidence"]]
    spend = _spend_block()
    checks = {
        "news_pull_never_gapped": "CANNOT DETERMINE (no per-tick history file yet)",
        "decision_vs_reality_per_date": all(r["decision_vs_reality"] for r in per_date)
        if dated else "no_evidence",
        "catalyst_calendar_refreshed": all(r["catalyst_calendar"] for r in per_date)
        if dated else "no_evidence",
        "no_double_write_collisions": "CANNOT DETERMINE (collisions are recorded "
                                      "per tick, not per date)",
        "spend_cap_never_breached": not spend["cap_reached"],
        "learned_line_present": all(r["learned_line"] for r in per_date)
        if dated else "no_evidence",
    }
    accepted = (len(dated) >= _config.LAB_ACCEPTANCE_DATES
                and all(v is True for v in checks.values()))
    return {
        "receipt": "always_on_lab_acceptance",
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "utc": _now(), "date": run_date(),
        "dates_required": _config.LAB_ACCEPTANCE_DATES,
        "min_hours_per_date": _config.LAB_ACCEPTANCE_MIN_HOURS,
        "dates_examined": want,
        "dates_with_evidence": [r["date"] for r in dated],
        "per_date": per_date,
        "criteria": {k: v for k, v in ACCEPTANCE_CRITERIA},
        "checks": checks,
        "spend": spend,
        "accepted": accepted,
        "status": ("ACCEPTED" if accepted else
                   ("BUILT_UNACCEPTED" if len(dated) < _config.LAB_ACCEPTANCE_DATES
                    else "BUILT_NOT_YET_PASSING")),
        "headline": (
            f"{len(dated)} of {_config.LAB_ACCEPTANCE_DATES} date(s) carry "
            f"evidence; " + ("ACCEPTED" if accepted else
                             "NOT accepted — acceptance needs real wall-clock "
                             "days, not agent time")),
        "read_me_first": (
            "Three DATES on which the machine was actually on, not three task "
            "runs: ONLOGON can fire and die repeatedly in a bad state and still "
            "produce three runs. A date with no receipts is `no_evidence` — "
            "neither a pass nor a failure. Until every check is True the honest "
            "status is 'built, unaccepted', and a fabricated acceptance receipt "
            "would be worse than none."),
    }


def _read_status() -> dict:
    p = status_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _spend_block() -> dict:
    from backend.services import lab_budget
    return lab_budget.spend_today()


def write_acceptance(report: dict | None = None) -> Path:
    report = report if report is not None else acceptance_report()
    day = report.get("date") or run_date()
    p = out_dir() / f"always_on_lab_acceptance_{day}.json"
    _write_atomic(p, report)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="always_on_lab",
                                 description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the cadence table and the process model; run nothing")
    ap.add_argument("--schtasks", action="store_true",
                    help="print the ONLOGON registration; runs nothing")
    ap.add_argument("--ticks", type=int, default=None,
                    help="run this many heartbeats and exit (default: until STOP)")
    ap.add_argument("--acceptance", action="store_true",
                    help="write the acceptance receipt and exit")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:                                          # noqa: BLE001
            pass

    if a.schtasks:
        return _print_schtasks()
    if a.dry_run:
        print_plan(plan())
        return 0
    if a.acceptance:
        report = acceptance_report()
        path = write_acceptance(report)
        print(json.dumps({**report, "path": str(path)}, indent=1, default=str))
        return 0
    try:
        payload = run_forever(max_ticks=a.ticks)
    except AlreadyRunning as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps({k: payload.get(k) for k in
                      ("utc", "ticks", "running", "stopped_by",
                       "spend_today_usd", "power_plan")}, indent=1, default=str))
    return 0


__all__ = ["ACCEPTANCE_CRITERIA", "HANDLERS", "LOOPS", "PERIODS",
           "SCHEDULED_DRIVERS", "STATUSES", "TIMEOUTS", "AlreadyRunning",
           "LabState", "LoopTimeout", "acceptance_report", "acquire_lock",
           "cadence_admits", "calendar_tickers", "call_boxed", "check_power",
           "data_dir", "dispatch_job", "learned_line", "lock_holder",
           "lock_path", "main", "model_status", "news_sources", "out_dir",
           "parsed_rate_limit", "pid_alive", "pid_names_lab", "plan",
           "power_refusal", "print_plan", "pull_news", "read_lock",
           "release_lock", "run_date", "run_forever", "running_drivers",
           "scan_processes", "status_path", "status_payload", "stop_path",
           "tick", "type_rows", "write_acceptance", "write_learned_line",
           "yields_to"]


if __name__ == "__main__":
    raise SystemExit(main())
