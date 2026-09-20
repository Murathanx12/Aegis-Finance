"""THE DAILY PASS — the board self-updates without a click (chunk 12, T1).

    python -m scripts.daily_pass --dry-run     # print the plan, run nothing
    python -m scripts.daily_pass               # the real pass, once per date
    python -m scripts.daily_pass --force       # a second pass on the same date
    python -m scripts.daily_pass --schtasks    # print the registration, run nothing

WHAT THIS IS, AND WHAT IT IS NOT
================================
It is ONE idempotent driver that walks a declared list of steps in order, each
behind its own try/except, and writes ONE receipt with a row per step. It is the
DATA-ACCUMULATION half of the day: the news corpus, the analyst snapshot, the
E1 append, the books' own cadence, the coverage card.

It is NOT `backend/services/morning.py`. The Morning is what the OPERATOR
clicks: it builds a digest, marks lanes, writes forecast rows and hands the Ask
page a brief, and its own `news_pull` step is the dashboard fetch, not the
corpus writer. The two are complementary and deliberately separate — a driver a
scheduled task runs unattended must not depend on a page being open, and a
button a human presses must not wait on a full multi-source pull.

It places no order, arms no lane, and **never calls the model server**. Nothing
here asks an LLM for anything: `test_daily_pass.py` walks this module's AST and
fails if a model-server or LLM symbol appears in its executable source.

A REFUSAL IS A FINDING, SO THE EXIT CODE IS 0
=============================================
Every step returns one of five statuses (the Morning's own five, deliberately,
so one reader learns one vocabulary):

* ``ok``            — it ran and the counts are in the row;
* ``nothing_to_do`` — it ran correctly and there was nothing. NOT a failure and
  NOT an ``ok`` with zeros: a card cannot tell those apart from a bare 0;
* ``refused``       — a precondition was absent and the row NAMES it;
* ``error``         — it raised; the type and message are in the row, truncated;
* ``skipped``       — the pass asked for it not to run (a 30m book outside RTH);
* ``timeout``       — it outlived its wall-clock box and its thread was
  abandoned. Added 2026-09-18, see below.

EVERY STEP IS BOXED, AND A STUCK PASS CANNOT TAKE THE WEEK
==========================================================
MEASURED. The `AegisDailyPass` firing of 2026-09-14 06:30 entered its analyst
snapshot, checkpointed 1,500 of 2,362 symbols at 00:52:52Z, and never returned.
It stayed alive for FOUR DAYS. Every later scheduled firing died at Windows
result 0x80070420 — "an instance of this task is already running" — so no daily
pass ran on 09-15, 09-16, 09-17 or 09-18 and there is no receipt for any of
those dates. The always-on lab's news loop yielded to it (`DAILY_PASS_RUNNING`)
the whole time.

Every yfinance property read in that sweep was ALREADY boxed at 25 s, which is
the lesson: a per-call box does not bound a step. So

* every step now runs under `config.DAILY_PASS_STEP_BOX_S[step]` through
  `news_pull.call_with_timeout` — imported, not re-implemented — and a step that
  outlives its box is a `timeout` row and the pass CONTINUES. Exit code 0;
* at startup, another `scripts.daily_pass` process older than
  `config.DAILY_PASS_STALE_SIBLING_H` hours is killed BY PID (never by image
  name) and recorded as `stale_sibling_killed` in the receipt. A YOUNGER one
  still refuses by name: two passes minutes apart is a human being deliberate.

The process exits 0 whenever the receipt was written, whatever the rows say. A
scheduled task that goes red because a source refused teaches its reader to
ignore red; the evidence is the receipt, not the exit code. The exit code is
non-zero only when the pass REFUSED TO RUN AT ALL (a second pass on the same
date without ``--force``), because that one is a fact about the invocation
rather than about the day.

ONCE PER DATE
=============
The receipt is ``night_factory_<NIGHT_RUN_DATE>/daily_pass_<date>.json`` — the
same night folder every other job of the day writes into, so a reader who opens
one folder has the whole day. A second run on the same date is REFUSED unless
``--force``; with ``--force`` the earlier receipt is kept and the second lands
at ``daily_pass_<date>_run02.json``, because two passes on one day is a fact
about the day and the first receipt is the only evidence of what it saw.

30-MINUTE BOOKS ONLY DURING US REGULAR TRADING HOURS
====================================================
A 30m book marked at 03:00 HKT on a Sunday is a mark against a stale daily bar
wearing an intraday name. The cadence step runs every OTHER cadence always, and
runs `30m` only when the US market is inside 09:30-16:00 ET on an XNYS session
— skipping it with the reason IN the row, never omitting the row.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("daily_pass")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

#: The step list. The runner walks THIS, not whatever happened to succeed — a
#: check that reads the record of what ran cannot see what never got called
#: (`signal_reachability.py`'s founding lesson). Adding a row here without a
#: handler is an AssertionError at import time, which is the point.
#:
#: THE CONTRACT RUNS SECOND, BEFORE THE SWEEP (2026-09-20). It used to be
#: fifth, after the 2,362-symbol analyst snapshot, and the consequence was
#: measured rather than feared: `step_decision_contract` has NEVER executed in
#: a pass. The only firing that carried it — 09-14 06:30 — wedged inside the
#: snapshot four steps earlier and was killed four days later, so the append-only
#: ledger `backend/data/optimus/decisions/ledger.jsonl` did not exist at all and
#: `record_decided` had never been called once.
#:
#: It may move because it does not depend on anything the snapshot writes. The
#: builder reads `config.IC_FUNNEL_PATH` (a committed artefact), the agency's IPS
#: store and `paper_books.load_bars()` (a static parquet); it never opens
#: `backend/data/analyst_snapshot/<date>.parquet`, and no step of this pass
#: refreshes the bars it does read. Twelve seconds of work was standing behind
#: 2.5 hours of network for no reason at all.
STEPS: tuple[tuple[str, str], ...] = (
    ("news_pull", "every registered news source, into the corpus"),
    ("decision_contract", "what the engine would buy today, at what size, and "
                          "what would make it wrong — plus a REFUSED row per "
                          "candidate that did not clear"),
    ("analyst_snapshot", "today's consensus rows per symbol"),
    ("e1_append", "the text-and-return panel append, PIT re-verified"),
    ("book_cadence", "every paper book due today (30m only inside US RTH)"),
    # 2026-09-20. It is AFTER the cadence pass because the books write their
    # own forecast rows there, and a grader that ran first would leave today's
    # rows for tomorrow for no reason.
    ("grade_forecasts", "every forecast whose window has closed, resolved from "
                        "the local bars — with a NAMED reason per record that "
                        "did not"),
    ("coverage", "the per-source coverage card, derived from disk"),
)

#: `timeout` joined the five on 2026-09-18. It is deliberately the SAME word
#: `always_on_lab.STATUSES` uses for the same thing, so one reader learns one
#: vocabulary: the step outlived its wall-clock box, its thread was abandoned,
#: and the pass went on to the next step.
STATUSES = ("ok", "nothing_to_do", "refused", "error", "skipped", "timeout")

#: Per-step wall-clock bound, read from config at import so a step declared
#: without a box is an AssertionError HERE rather than an unbounded step three
#: months from now. The numbers live in `backend/config.py` (CLAUDE.md).
_STEP_BOXES: dict = dict(_config.DAILY_PASS_STEP_BOX_S)
assert set(_STEP_BOXES) == {s for s, _ in STEPS},     "every declared step needs a wall-clock box in config.DAILY_PASS_STEP_BOX_S"

#: Which cadence buckets are intraday. The full bucket list is
#: `backend.services.paper_books.CADENCES`, read at call time so the two cannot
#: drift; this is the intraday SET only.
INTRADAY_CADENCES = frozenset({"30m"})

#: US regular trading hours, in the exchange's own clock. The DATE is checked
#: against the XNYS calendar rather than against a weekday rule, because a
#: weekday rule happily trades on Thanksgiving (`market_sessions.py`).
RTH_OPEN_ET = dtime(9, 30)
RTH_CLOSE_ET = dtime(16, 0)

#: The local wall-clock time the scheduled task would fire. Printed by
#: `--schtasks`; registering it is a decision this file does not take.
SCHEDULED_LOCAL_TIME = "06:30"
TASK_NAME = "AegisDailyPass"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trunc(exc: BaseException, n: int = 400) -> str:
    return f"{type(exc).__name__}: {exc}"[:n]


def run_date() -> str:
    """The date this pass belongs to.

    `NIGHT_RUN_DATE` is honoured so a daily pass files into the same night
    folder as every other job of the day. Unset, it is TODAY — the default that
    was a literal `2026-09-08` in `night_factory.py` for five days and put two
    real receipts five days in the past before anyone noticed.
    """
    return os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")


def out_dir() -> Path:
    """The night folder for this date, created at WRITE time by the registry."""
    from scripts import night_factory_jobs as J
    return J._out()


def receipt_path(day: str, run: int = 1) -> Path:
    name = (f"daily_pass_{day}.json" if run <= 1
            else f"daily_pass_{day}_run{run:02d}.json")
    return out_dir() / name


def existing_receipts(day: str) -> list[Path]:
    """Every daily-pass receipt already on disk for `day`, oldest first."""
    d = out_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(f"daily_pass_{day}*.json") if p.is_file())


def git_head() -> str:
    """The commit this pass ran on, or a reason. Never raises."""
    try:
        r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable ({type(exc).__name__})"
    return r.stdout.strip() or f"unavailable (git exited {r.returncode})"


# ===========================================================================
# US REGULAR TRADING HOURS
# ===========================================================================


def us_rth_state(now: datetime | None = None) -> dict:
    """Is the US market open right now? `{"inside": bool, "why": str, ...}`.

    CANNOT DETERMINE is a THIRD answer and it is not "inside". If the exchange
    calendar cannot be loaded, the intraday bucket is skipped and the row says
    the calendar was missing — a 30m mark taken on a guess is not a 30m mark.
    """
    from zoneinfo import ZoneInfo

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(ZoneInfo("America/New_York"))
    try:
        from backend.services import market_sessions
        session = bool(market_sessions.is_session(et.date()))
        basis = "exchange_calendars XNYS"
    except Exception as exc:                                       # noqa: BLE001
        return {"inside": False, "session": None,
                "et": et.isoformat(timespec="seconds"),
                "basis": "CANNOT DETERMINE",
                "why": (f"the XNYS calendar could not be read "
                        f"({_trunc(exc, 120)}), so whether {et.date()} is a "
                        f"session is unknown")}
    inside = bool(session and RTH_OPEN_ET <= et.time() < RTH_CLOSE_ET)
    if inside:
        why = "inside US regular trading hours"
    elif session:
        why = (f"{et.date()} is an XNYS session but "
               f"{et.time().isoformat('minutes')} ET is outside "
               f"{RTH_OPEN_ET.isoformat('minutes')}-"
               f"{RTH_CLOSE_ET.isoformat('minutes')}")
    else:
        why = f"{et.date()} is not an XNYS session"
    return {"inside": inside, "session": session, "basis": basis,
            "et": et.isoformat(timespec="seconds"),
            "rth_et": f"{RTH_OPEN_ET.isoformat()}-{RTH_CLOSE_ET.isoformat()}",
            "why": why}


# ===========================================================================
# THE SEAMS
#
# One module-level callable per external thing a step does, so a test can
# replace it BY NAME. A step body cannot be monkeypatched; these can — the same
# reason `backend/services/morning.py` holds its fetches behind names.
# ===========================================================================


def pull_all_news(**kw) -> dict:
    from scripts import news_pull
    return news_pull.pull_all(**kw)


def run_analyst_snapshot(**kw) -> dict:
    from scripts import analyst_snapshot
    return analyst_snapshot.snapshot(**kw)


def run_e1_append(**kw) -> dict:
    """The append, dispatched THROUGH the job registry rather than imported.

    A daily job that reached past `JOBS` would be a second way to run the same
    work, and the two would drift the first time the registry gained a wrapper.
    """
    from scripts.night_factory_jobs import JOBS
    return JOBS["E1_append"](**kw)


def build_decision_contracts(**kw) -> list[dict]:
    """The chunk-18 contract builder, behind a name like every other seam."""
    from backend.services import decision_contract
    return decision_contract.build_daily_contracts(**kw)


def record_decided(rows: list[dict], day: str) -> dict:
    from backend.services import decision_ledger
    return decision_ledger.record_many(
        [r["decision_id"] for r in rows], "DECIDED", by="daily_pass",
        asof=day, detail={"step": "decision_contract"})


def grade_forecasts(**kw) -> dict:
    """The forecast grader, behind a name like every other seam."""
    from backend.services import forecast_grader
    return forecast_grader.grade_due(**kw)


def cadence_list() -> tuple[str, ...]:
    from backend.services.paper_books import CADENCES
    return tuple(CADENCES)


def run_cadence_pass(cadence: str, **kw) -> dict:
    from backend.services import book_cadence
    return book_cadence.run_pass(cadence, **kw)


def call_boxed(fn: Callable[[], dict], timeout_s: float, what: str) -> dict:
    """Run `fn()` under a hard wall-clock bound. IMPORTED, not re-implemented.

    `news_pull.call_with_timeout` is the daemon-thread box this repo already
    uses everywhere a third-party library can hold a socket open for ever. A
    second copy of it here would be a second thing to keep in step with the
    first, and the one that would drift is this one.

    The hung thread is NOT killed -- Python cannot -- which is why it is a
    daemon: it cannot hold the process open at exit, and the pass moves to the
    next step instead of waiting on it for ever. That is the whole of the
    2026-09-14 fix: the analyst sweep wedged and the process stayed alive for
    four days, so four scheduled firings reported 0x80070420 and no receipt was
    written for any of them.
    """
    from scripts.news_pull import call_with_timeout
    return call_with_timeout(fn, timeout_s, what)


def step_box_s(step: str) -> float:
    """This step's wall-clock bound, from config. A step with no declared box is
    an AssertionError at import, not an unbounded step."""
    return float(_STEP_BOXES[step])


def scan_daily_passes() -> list[dict]:
    """Every OTHER `scripts.daily_pass` python process, with its creation time.

    The shape is `always_on_lab.scan_processes`'s -- one `Get-CimInstance
    Win32_Process` query, matched on the COMMAND LINE, never on the image name.
    `CreationDate` comes back from CIM so the caller can tell a sibling that
    started four minutes ago from one that started four days ago.

    Returns [] when the probe itself could not run, and the caller treats that
    as CANNOT DETERMINE rather than as "nothing is running": a scan that failed
    and a machine that is idle are different facts, and the conservative
    direction here is to kill nothing.
    """
    if sys.platform != "win32":
        return []
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "ForEach-Object { \"$($_.ProcessId)`t"
                     "$($_.CreationDate.ToUniversalTime().ToString('o'))`t"
                     "$($_.CommandLine)\" }"],
                    capture_output=True, text=True, timeout=45)
    except Exception:                                              # noqa: BLE001
        return []
    return parse_process_table(r.stdout or "")


def parse_process_table(text: str, *, me: int | None = None,
                        parent: int | None = None) -> list[dict]:
    """The rows of a `pid<TAB>created<TAB>cmdline` table that are OTHER passes.

    "Other" excludes this process AND its parent. The parent matters on this
    machine: `.venv/Scripts/python.exe` is a REDIRECTOR that spawns the real
    interpreter as a child, and both carry `-m scripts.daily_pass` on their
    command line. On 2026-09-18 the first pass on the boxed code refused itself
    -- `another daily pass is running as pid(s) [24924]` was its own launcher,
    forty-five seconds old -- and a driver that cannot start is the 09-14
    stall with a better error message.
    """
    me = os.getpid() if me is None else int(me)
    parent = os.getppid() if parent is None else int(parent)
    out: list[dict] = []
    for line in text.splitlines():
        parts = line.split("	")
        if len(parts) < 3 or not parts[0].strip().isdigit():
            continue
        pid = int(parts[0])
        if pid in (me, parent) or "scripts.daily_pass" not in (parts[2] or ""):
            continue
        out.append({"pid": pid, "created_utc": parts[1].strip(),
                    "cmdline": (parts[2] or "")[:400]})
    return out


def kill_pid(pid: int) -> dict:
    """Terminate ONE process, BY PID, from a PID this run read off the process
    table. Never by image name.

    CLAUDE.md rule 6, and it is not hypothetical: on 2026-09-06 a
    kill-by-image-name took down two other agents' jobs, a running test suite,
    ~1,676 already-billed LLM extractions and the Optimus MCP server for the
    rest of the session.
    """
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                    capture_output=True, text=True, timeout=30)
    except Exception as exc:                                       # noqa: BLE001
        return {"killed": False, "pid": int(pid), "detail": _trunc(exc)}
    return {"killed": r.returncode == 0, "pid": int(pid),
            "returncode": r.returncode,
            "detail": ((r.stdout or "") + (r.stderr or "")).strip()[:300]}


def read_coverage() -> dict:
    """N-F's coverage card, computed by the route's own function.

    Called rather than re-implemented: a second implementation of a coverage
    count is a second answer, and the board shows the route's.
    """
    from backend.routers.control import coverage
    return coverage()


# ===========================================================================
# THE STEPS
# ===========================================================================


def _row(step: str, status: str, **fields) -> dict:
    if status not in STATUSES:
        raise ValueError(f"{status!r} is not one of {STATUSES}")
    row = {"step": step, "status": status, "utc": _now(),
           "rows": fields.pop("rows", None),
           "seconds": fields.pop("seconds", None),
           "refusals": [str(r)[:300] for r in (fields.pop("refusals", None) or [])]}
    row.update(fields)
    return row


def step_news_pull(ctx: dict) -> dict:
    """Every registered source, in registry order, each with its own receipt."""
    t0 = time.time()
    summary = pull_all_news()
    refusals = list(summary.get("refused") or [])
    refusals += [f"RED: {s}" for s in (summary.get("red") or [])]
    rows = int(summary.get("rows_new") or 0)
    status = ("ok" if rows
              else ("refused" if summary.get("refused") else "nothing_to_do"))
    return _row("news_pull", status, rows=rows,
                seconds=round(time.time() - t0, 2), refusals=refusals,
                sources=summary.get("sources"),
                resolution_rate=summary.get("resolution_rate"),
                receipt_path=summary.get("receipt_path"),
                headline=summary.get("headline"))


def step_analyst_snapshot(ctx: dict) -> dict:
    """Today's consensus rows. The name table is updated by the same sweep."""
    t0 = time.time()
    # THE TRADABLE BAND, NOT THE WHOLE POTENTIAL UNIVERSE (chunk 15b). The
    # 3,056-name sweep is 3.4 h of a 3.9 h pass at the measured 4.45 s/symbol,
    # and a quarter of it is names no book here can hold. `analyst_snapshot`
    # reads the band from `night_f_seasonality_export.load_universe` -- the one
    # place the floor is defined -- and REFUSES rather than falling back to the
    # larger list, so a pass that quietly grew by 700 names cannot happen
    # silently. The CLI default stays `all` for the one-off name-table sweep.
    #
    # AND IT STOPS ITSELF (2026-09-20). The step box abandons a wedged thread
    # and leaves no receipt of its own; the sweep's own budget flushes, writes
    # a receipt that NAMES the shortfall, and returns. At 4.45 s/symbol the
    # 2,362-name band needs ~2.9 h, so this truncates most days — visibly, in
    # `symbols_not_reached`, rather than by a `timeout` row every morning.
    rec = run_analyst_snapshot(
        universe="tradable", budget_s=float(_config.DAILY_PASS_ANALYST_BUDGET_S))
    by_status = rec.get("by_status") or {}
    rows = int(rec.get("rows") or 0)
    errs = int(by_status.get("error") or 0)
    refusals = []
    if rec.get("refused"):
        refusals.append(rec["refused"])
    if rec.get("truncated"):
        refusals.append(str(rec.get("truncation_reason")
                            or "the sweep reached its own budget"))
    if errs:
        refusals.append(f"{errs} symbol(s) errored")
    status = ("refused" if rec.get("refused")
              else ("ok" if rows else "nothing_to_do"))
    return _row("analyst_snapshot", status, rows=rows,
                seconds=round(time.time() - t0, 2), refusals=refusals,
                by_status=by_status, coverage_rate=rec.get("coverage_rate"),
                path=rec.get("path"),
                budget_s=rec.get("budget_s"), truncated=rec.get("truncated"),
                symbols_not_reached=rec.get("symbols_not_reached"),
                name_table_update=rec.get("name_table_update"),
                headline=rec.get("headline"))


def step_e1_append(ctx: dict) -> dict:
    """The panel append. It re-verifies PIT itself and refuses the WHOLE append
    on a single violation; this step reports that refusal, it does not soften
    it into a partial success."""
    t0 = time.time()
    rec = run_e1_append()
    rows = int(rec.get("rows_appended") or 0)
    verdict = str(rec.get("verdict") or "")
    refused = verdict.upper().startswith("REFUSED")
    return _row("e1_append", ("refused" if refused
                              else ("ok" if rows else "nothing_to_do")),
                rows=rows, seconds=round(time.time() - t0, 2),
                refusals=([rec.get("headline") or verdict] if refused else []),
                verdict=verdict or None, funnel=rec.get("funnel"),
                headline=rec.get("headline"))


def step_book_cadence(ctx: dict) -> dict:
    """One pass per cadence bucket; the intraday bucket only inside US RTH."""
    t0 = time.time()
    rth = ctx.setdefault("rth", us_rth_state())
    per: list[dict] = []
    decisions = 0
    refusals: list[str] = []
    for cadence in cadence_list():
        if cadence in INTRADAY_CADENCES and not rth.get("inside"):
            per.append({"cadence": cadence, "status": "skipped",
                        "reason": f"outside US RTH — {rth.get('why')}"})
            continue
        try:
            rec = run_cadence_pass(cadence)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("daily pass: cadence %s raised", cadence)
            per.append({"cadence": cadence, "status": "error",
                        "reason": _trunc(exc)})
            refusals.append(f"{cadence}: {_trunc(exc, 160)}")
            continue
        n = len(rec.get("decisions") or [])
        decisions += n
        per.append({"cadence": cadence,
                    "status": ("nothing_to_do" if rec.get("nothing_to_do") else "ok"),
                    "books_considered": rec.get("books_considered"),
                    "decisions": n, "marked": len(rec.get("marked") or []),
                    "refused": rec.get("refused") or [],
                    "reason": rec.get("reason"), "bar_date": rec.get("bar_date")})
        for r in (rec.get("refused") or []):
            refusals.append(f"{cadence}: {str(r)[:160]}")
    ran = [p for p in per if p["status"] in ("ok", "nothing_to_do")]
    status = ("ok" if decisions
              else ("refused" if (refusals and not ran) else "nothing_to_do"))
    return _row("book_cadence", status, rows=decisions,
                seconds=round(time.time() - t0, 2), refusals=refusals,
                per_cadence=per, us_rth=rth)


def step_decision_contract(ctx: dict) -> dict:
    """The decision contract, on the UNATTENDED path (chunk 18).

    `backend/services/morning.py` has the same step, and both exist on purpose:
    the Morning is what the OPERATOR clicks and this pass is what runs whether
    or not anybody is at the machine. The gate for chunk 18 is Murat asking the
    local model "what would you buy today" and reading engine-sized rows — which
    requires the contract to exist without a click.

    Writing the same day twice is not a conflict: the file is keyed on the DATE
    and rewritten atomically from the same inputs, and the ledger's DECIDED row
    is idempotent per decision id, so the second writer records `duplicate`
    rather than a second row.

    IT RUNS SECOND. Measured by hand on 2026-09-20: 43 rows in 12 seconds. It
    stood behind a 2.5-hour network sweep for four weeks and therefore never
    ran once; see the note on `STEPS`.
    """
    t0 = time.time()
    from backend.services import decision_contract as DC

    try:
        rows = build_decision_contracts(asof=ctx["date_obj"])
    except DC.CostModelRefused as exc:
        return _row("decision_contract", "refused", rows=0,
                    seconds=round(time.time() - t0, 2), refusals=[_trunc(exc)])
    counts = {d: sum(1 for r in rows if r.get("direction") == d)
              for d in DC.DIRECTIONS}
    ledger = record_decided(rows, ctx["date"])
    blob = DC.latest(ctx["date"]) or {}
    actionable = counts.get("BUY", 0) + counts.get("WATCH", 0)
    return _row("decision_contract",
                ("ok" if actionable else "nothing_to_do"),
                rows=len(rows), seconds=round(time.time() - t0, 2),
                refusals=list(blob.get("notes") or []),
                count_by_direction=counts,
                count_by_refusal_class=blob.get("count_by_refusal_class"),
                count_by_terminal_state=blob.get("count_by_terminal_state"),
                worst_case_largest_admissible_book=blob.get(
                    "worst_case_largest_admissible_book"),
                licence=DC.LICENCE, ledger=ledger, receipt=blob.get("path"))


def step_grade_forecasts(ctx: dict) -> dict:
    """Resolve every forecast whose window has closed (chunk 18b).

    MEASURED 2026-09-20 on the live ledger: 24,839 records, and every single one
    carried `resolved_at: null`. 17,614 were past their resolution date, the
    oldest since 2026-08-11. `lab_decision_vs_reality` reported the number every
    hour and re-grades nothing by design; the graders it aggregates over simply
    had no caller on this machine, because the only production caller is a
    background thread inside a server process that does not run here.

    `nothing_to_do` when nothing was due, `ok` when a record resolved, and
    `refused` when the resolver itself refused (an unestablished population, an
    unreadable campaign ledger) — never an `ok` with zeros, which a card cannot
    tell from a day on which everything was already graded.
    """
    t0 = time.time()
    rec = grade_forecasts()
    totals = rec.get("totals") or {}
    newly = int(rec.get("newly_resolved") or 0)
    status_word = str(rec.get("resolver_status") or "ok").upper()
    refusals: list[str] = []
    if status_word in ("REFUSED", "ERROR"):
        refusals.append(str(rec.get("resolver_reason") or status_word))
    for bucket in ("RECORD_LACKS_TARGET", "MECHANISM_HAS_NO_GRADER",
                   "NO_BAR_FOR_RESOLUTION_DATE", "QUARANTINED"):
        n = int(totals.get(bucket) or 0)
        if n:
            refusals.append(f"{bucket}: {n:,} record(s)")
    if status_word in ("REFUSED", "ERROR"):
        status = "refused"
    elif newly:
        status = "ok"
    else:
        status = "nothing_to_do"
    return _row("grade_forecasts", status, rows=newly,
                seconds=round(time.time() - t0, 2), refusals=refusals,
                totals=totals, bars=rec.get("bars"),
                n_records=rec.get("n_records"),
                graded_after_this_run=rec.get("graded_after_this_run"),
                n_unpriceable_tickers=rec.get("n_unpriceable_tickers"),
                licence=rec.get("licence"), receipt=rec.get("path"),
                headline=rec.get("headline"))


def step_coverage(ctx: dict) -> dict:
    """The card, from disk. A card that cannot be computed says so."""
    t0 = time.time()
    cov = read_coverage()
    if cov.get("available") is False:
        return _row("coverage", "refused", rows=0,
                    seconds=round(time.time() - t0, 2),
                    refusals=[cov.get("error")])
    sources = cov.get("sources") or []
    bad = [s.get("id") for s in sources
           if s.get("status") in ("RED", "STALE", "REFUSED", "NEVER_PULLED")]
    return _row("coverage", ("ok" if sources else "nothing_to_do"),
                rows=sum(int(s.get("rows_today") or 0) for s in sources),
                seconds=round(time.time() - t0, 2), refusals=bad,
                sources=len(sources),
                regions=[{"region": r.get("region"),
                          "rows_today": r.get("rows_today")}
                         for r in (cov.get("regions") or [])],
                totals=cov.get("totals"))


_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "news_pull": step_news_pull,
    "analyst_snapshot": step_analyst_snapshot,
    "e1_append": step_e1_append,
    "book_cadence": step_book_cadence,
    "decision_contract": step_decision_contract,
    "grade_forecasts": step_grade_forecasts,
    "coverage": step_coverage,
}
assert set(_HANDLERS) == {s for s, _ in STEPS}, "every declared step needs a handler"


# ===========================================================================
# THE RUNNER
# ===========================================================================


class SamePassAlreadyRan(RuntimeError):
    """A daily pass for this date is on disk and `--force` was not given."""


def _age_h(created_utc: str, now: datetime | None = None) -> float | None:
    """Hours since `created_utc`, or None when it cannot be parsed.

    None is CANNOT DETERMINE and it is NOT "old enough": a sibling whose age we
    could not read is left alone.
    """
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(created_utc).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600.0


def stale_siblings(*, now: datetime | None = None,
                   siblings: list[dict] | None = None) -> dict:
    """Which other daily passes are running, and which of them are STALE.

    MEASURED, 2026-09-14. The 06:30 pass wedged inside its analyst snapshot and
    stayed alive for four days. Every later scheduled firing died at Windows
    result 0x80070420 -- "an instance of this task is already running" -- so no
    pass ran on 09-15, 09-16, 09-17 or 09-18 and no receipt exists for any of
    them. One stuck process took a week.

    A sibling older than `DAILY_PASS_STALE_SIBLING_H` is killed BY PID and this
    pass takes the day. A younger one still REFUSES by name, because two passes
    launched minutes apart is a human doing something deliberate.
    """
    rows = scan_daily_passes() if siblings is None else list(siblings)
    limit = float(_config.DAILY_PASS_STALE_SIBLING_H)
    out = []
    for row in rows:
        age = _age_h(row.get("created_utc"), now)
        out.append({**row, "age_h": (None if age is None else round(age, 2)),
                    "stale": bool(age is not None and age >= limit)})
    return {"siblings": out, "stale_h": limit,
            "stale": [r for r in out if r["stale"]],
            "young": [r for r in out if not r["stale"]],
            "probe_ran": bool(rows) or siblings == [] or rows == []}


def clear_stale_siblings(*, now: datetime | None = None,
                         siblings: list[dict] | None = None) -> dict:
    """Kill every STALE sibling by PID; return what happened, for the receipt.

    Never by image name (CLAUDE.md rule 6). A young sibling is reported and NOT
    killed -- the caller turns that into the same `ALREADY_RUNNING` refusal the
    pass has always had.
    """
    found = stale_siblings(now=now, siblings=siblings)
    killed = []
    for row in found["stale"]:
        result = kill_pid(int(row["pid"]))
        killed.append({"pid": int(row["pid"]), "age_h": row["age_h"],
                       "killed": bool(result.get("killed")),
                       "detail": result.get("detail"),
                       "cmdline": row.get("cmdline")})
        logger.warning("killed a stale daily pass: pid %s, %s h old (%s)",
                       row["pid"], row["age_h"],
                       "ok" if result.get("killed") else "FAILED")
    return {**found, "killed": killed}


class SiblingPassRunning(RuntimeError):
    """Another daily pass is running and it is NOT old enough to be stale."""


def run_daily_pass(*, day: str | None = None, force: bool = False,
                   write_receipt: bool = True,
                   check_siblings: bool = True) -> dict:
    """Walk every declared step in order, write ONE receipt, return it.

    Never raises for a step's sake: a step that raises still produces its row,
    because half a day is still a day and the operator needs the receipt more
    than the traceback. It DOES raise `SamePassAlreadyRan` BEFORE any step runs
    when the date already has a receipt and `force` is not set — that refusal
    is about the invocation, not about the day, and it is the one thing this
    driver must not do silently: an unforced second pull re-hits every source's
    rate limit and appends rows nobody asked for.
    """
    day = day or run_date()
    # THE STALE-SIBLING RULE, BEFORE ANY STEP. One wedged pass cost 09-15
    # through 09-18: four scheduled firings, four 0x80070420s, four dates with
    # no receipt at all. A sibling older than the stale bound is killed BY PID;
    # a younger one still refuses.
    sibling_block: dict = {"checked": False}
    if check_siblings:
        sibling_block = clear_stale_siblings()
        sibling_block["checked"] = True
        if sibling_block["young"]:
            raise SiblingPassRunning(
                f"another daily pass is running as pid(s) "
                f"{[r['pid'] for r in sibling_block['young']]} and is younger "
                f"than {sibling_block['stale_h']} h. Two passes at once re-hit "
                f"every source's rate limit; this one refuses rather than "
                f"killing a run somebody started deliberately.")
    prior = existing_receipts(day)
    if prior and not force:
        raise SamePassAlreadyRan(
            f"{len(prior)} daily-pass receipt(s) already exist for {day} "
            f"({prior[-1].name}). The pass is idempotent per DATE by design. "
            f"Re-run with --force to take a second pass; the earlier receipt "
            f"is kept either way.")
    run = len(prior) + 1
    started = datetime.now(timezone.utc)
    ctx: dict[str, Any] = {"date": day, "date_obj": date.fromisoformat(day),
                           "run": run, "rows": []}
    for step_id, what in STEPS:
        box = step_box_s(step_id)
        t0 = time.time()
        try:
            row = call_boxed(lambda s=step_id: _HANDLERS[s](ctx), box, step_id)
        except Exception as exc:                                   # noqa: BLE001
            # `CallTimeout` is a `FetchError` is a `RuntimeError`; it is caught
            # HERE by name rather than by class so the row says `timeout` and
            # not `error`. The two are different findings: `error` means the
            # step raised and told us why, `timeout` means it never came back
            # and its thread was abandoned.
            from scripts.news_pull import CallTimeout
            if isinstance(exc, CallTimeout):
                logger.error("daily pass step %s outlived its %gs box",
                             step_id, box)
                row = _row(step_id, "timeout", seconds=round(time.time() - t0, 2),
                           refusals=[f"timeout_after_{box:g}s"],
                           box_s=box,
                           detail=("the step did not return inside its wall-clock "
                                   "box; its thread is abandoned (a daemon, so it "
                                   "cannot hold this process open) and the pass "
                                   "continued to the next step"))
            else:
                logger.exception("daily pass step %s raised", step_id)
                row = _row(step_id, "error", seconds=round(time.time() - t0, 2),
                           refusals=[_trunc(exc)])
        row.setdefault("what", what)
        row.setdefault("box_s", box)
        ctx["rows"].append(row)

    rows = ctx["rows"]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    receipt = {
        "receipt": "daily_pass",
        "roadmap_item": "chunk 12 T1",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        # THE STAGE CONTRACT (`docs/STAGE_CONTRACT.md`). A driver is not one
        # stage: its steps run from `raw` (the corpus pull, the snapshot)
        # through `normalized` (the E1 append) to `pnl` (the cadence pass marks
        # positions and a NAV). It is stamped at the LAST stage it reaches,
        # which is the conservative direction -- `pnl` may read anything and
        # nothing may read it, so a stamp of `pnl` can never license a forward
        # read. The per-step stages are in `step_stages` rather than averaged
        # into one number nobody can act on.
        "stage": "pnl",
        # `decision_contract` stays `pnl` even though it now runs SECOND, before
        # the cadence pass marks anything. It composes positions and sizes them
        # in dollars, which is the latest stage anything it touches can be, and
        # `pnl` may read anything while nothing may read `pnl` — so the stamp is
        # the conservative direction in both orders. What changed on 2026-09-20
        # is the ORDER, not the stage: the row is no longer derived from a NAV
        # this pass wrote, and it never was — `compose_book` is the committee's
        # composer, not the paper book's marker.
        # `grade_forecasts` is `pnl` and could not be anything else: an outcome
        # written onto a forecast is the thing that makes it evidence, and
        # nothing upstream may read it.
        "step_stages": {"news_pull": "raw", "analyst_snapshot": "raw",
                        "e1_append": "normalized", "book_cadence": "pnl",
                        "decision_contract": "pnl", "grade_forecasts": "pnl",
                        "coverage": "raw"},
        "date": day, "run": run,
        "git_head": git_head(),
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": _now(),
        "elapsed_s": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "declared_steps": [s for s, _ in STEPS],
        "step_boxes_s": dict(_STEP_BOXES),
        "stale_sibling_killed": (sibling_block.get("killed") or None),
        "siblings": sibling_block,
        "steps": rows,
        "step_status_counts": counts,
        "steps_that_did_not_run": [r["step"] for r in rows
                                   if r["status"] in ("refused", "error",
                                                      "timeout")],
        "us_rth": ctx.get("rth"),
        "forced": bool(force),
        "prior_receipts": [p.name for p in prior],
        "read_me_first": (
            "One row per DECLARED step, in order, always — the runner walks the "
            "step list, not the list of things that worked. `refused` NAMES the "
            "missing precondition and is a finding, not a failure; "
            "`nothing_to_do` means the step ran correctly and there was "
            "nothing, which is not the same as zero; `timeout` means the step "
            "outlived `box_s` and its thread was abandoned, and the pass went "
            "on — which is why one wedged step can no longer cost a week the "
            "way 2026-09-14's did. Nothing here places an order, arms a lane, "
            "or asks a model for anything."),
        "headline": (
            f"{counts['ok']} ok / {counts['nothing_to_do']} nothing-to-do / "
            f"{counts['refused']} refused / {counts['error']} error / "
            f"{counts['skipped']} skipped / {counts['timeout']} timed out "
            f"over {len(STEPS)} steps"),
    }
    if write_receipt:
        path = receipt_path(day, run)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        receipt["path"] = str(path)
    return receipt


def plan(day: str | None = None) -> dict:
    """What a real run WOULD do. Reads the clock and the calendar; writes
    nothing and calls nothing."""
    day = day or run_date()
    prior = existing_receipts(day)
    rth = us_rth_state()
    skip_note = (f"the {sorted(INTRADAY_CADENCES)} bucket would be SKIPPED "
                 f"({rth.get('why')})")
    return {
        "dry_run": True, "date": day,
        "receipt_would_be": str(receipt_path(day, len(prior) + 1)),
        "prior_receipts": [p.name for p in prior],
        "would_refuse_without_force": bool(prior),
        "us_rth": rth,
        "steps": [{"step": s, "what": w, "box_s": step_box_s(s),
                   "note": (skip_note if s == "book_cadence" and not rth.get("inside")
                            else None)}
                  for s, w in STEPS],
        "stale_sibling_hours": float(_config.DAILY_PASS_STALE_SIBLING_H),
    }


def print_receipt(receipt: dict) -> None:
    print("=" * 74)
    print(f"DAILY PASS — {receipt['date']}  run {receipt['run']}")
    print("=" * 74)
    print(f"  git HEAD   {receipt['git_head']}")
    print(f"  elapsed    {receipt['elapsed_s']}s")
    print()
    for r in receipt["steps"]:
        secs = "--" if r.get("seconds") is None else f"{r['seconds']:.1f}s"
        rows = "--" if r.get("rows") is None else str(r["rows"])
        print(f"  {r['step']:18s} {r['status']:14s} rows {rows:>8s}  {secs:>8s}")
        for ref in r.get("refusals") or []:
            print(f"      ! {str(ref)[:100]}")
    print(f"\n  {receipt['headline']}")
    if receipt.get("path"):
        print(f"  receipt -> {receipt['path']}")


def _print_schtasks() -> int:
    """Print the registration. Deliberately does not run it.

    The shape is `scripts/run_night_launcher.py::_print_schtasks`'s, including
    the stdin redirect from an EMPTY REGULAR FILE — `< NUL` was registered on
    2026-08-18, does not work (the Windows CRT calls any character device a
    tty), and cost two wasted receipts before anyone measured it.
    """
    root = os.getcwd()
    empty = f"{root}\\backend\\data\\optimus\\empty_stdin.txt"
    log = f"{root}\\backend\\data\\optimus\\daily_pass.log"
    print("=" * 74)
    print("REGISTER THE DAILY PASS — printed, not run; registering it is a decision")
    print("=" * 74)
    print(f"""
  * {SCHEDULED_LOCAL_TIME} is WALL CLOCK on this machine. It is not tied to the
    opening bell and does not need to be: the pass re-derives US RTH at every
    firing from the XNYS calendar and SKIPS the intraday cadence bucket with a
    reason rather than marking a 30m book against a stale daily bar.

  * DAILY, not MON-FRI. The corpus, the snapshot and the coverage card are not
    session-bound, and a weekend row is a real row. The steps that ARE
    session-bound say so in their own rows.

  * The stdin redirect is load-bearing and must come from a REGULAR FILE, not
    from NUL: on Windows `_isatty()` returns true for any character device, so
    `< NUL` redirects and changes nothing observable.

  * No pipe. `cmd | tail` reports tail's exit code, and the exit code is the
    guard.
""")
    print(f'  schtasks /Create /TN "{TASK_NAME}" /SC DAILY /ST '
          f'{SCHEDULED_LOCAL_TIME} /TR "cmd /c cd /d {root} && '
          f'python -m scripts.daily_pass < {empty} >> {log} 2>&1"')
    print("\n  Already registered? Change it in place rather than re-registering:\n")
    print(f'  schtasks /Change /TN "{TASK_NAME}" /TR '
          f'"cmd /c cd /d {root} && '
          f'python -m scripts.daily_pass < {empty} >> {log} 2>&1"')
    print("""
  The log redirect is a convenience, NOT the evidence. The evidence is
  `night_factory_<date>/daily_pass_<date>.json`, which is written whether or
  not anything is watching stdout.
""")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="daily_pass",
                                 description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan; run nothing, write nothing")
    ap.add_argument("--force", action="store_true",
                    help="take a second pass on a date that already has one")
    ap.add_argument("--schtasks", action="store_true",
                    help="print the Windows registration command; runs nothing")
    ap.add_argument("--date", default=None,
                    help="the pass date (default: NIGHT_RUN_DATE, else today)")
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
        print(json.dumps(plan(a.date), indent=1, default=str))
        return 0
    try:
        receipt = run_daily_pass(day=a.date, force=a.force)
    except (SamePassAlreadyRan, SiblingPassRunning) as exc:
        print(f"REFUSED: {exc}")
        return 2
    print_receipt(receipt)
    return 0


__all__ = ["INTRADAY_CADENCES", "STATUSES", "STEPS", "SamePassAlreadyRan",
           "SiblingPassRunning", "cadence_list", "call_boxed",
           "clear_stale_siblings", "existing_receipts", "git_head",
           "grade_forecasts", "kill_pid", "parse_process_table",
           "main", "out_dir", "plan", "print_receipt", "pull_all_news",
           "read_coverage", "receipt_path", "run_analyst_snapshot",
           "run_cadence_pass", "run_daily_pass", "run_date", "run_e1_append",
           "scan_daily_passes", "stale_siblings", "step_box_s", "us_rth_state"]


if __name__ == "__main__":
    raise SystemExit(main())
