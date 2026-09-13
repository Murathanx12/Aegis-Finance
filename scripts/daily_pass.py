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
* ``skipped``       — the pass asked for it not to run (a 30m book outside RTH).

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

#: The step list. The runner walks THIS, not whatever happened to succeed — a
#: check that reads the record of what ran cannot see what never got called
#: (`signal_reachability.py`'s founding lesson). Adding a row here without a
#: handler is an AssertionError at import time, which is the point.
STEPS: tuple[tuple[str, str], ...] = (
    ("news_pull", "every registered news source, into the corpus"),
    ("analyst_snapshot", "today's consensus rows per symbol"),
    ("e1_append", "the text-and-return panel append, PIT re-verified"),
    ("book_cadence", "every paper book due today (30m only inside US RTH)"),
    ("coverage", "the per-source coverage card, derived from disk"),
)

STATUSES = ("ok", "nothing_to_do", "refused", "error", "skipped")

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


def cadence_list() -> tuple[str, ...]:
    from backend.services.paper_books import CADENCES
    return tuple(CADENCES)


def run_cadence_pass(cadence: str, **kw) -> dict:
    from backend.services import book_cadence
    return book_cadence.run_pass(cadence, **kw)


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
    rec = run_analyst_snapshot()
    by_status = rec.get("by_status") or {}
    rows = int(rec.get("rows") or 0)
    errs = int(by_status.get("error") or 0)
    refusals = []
    if rec.get("refused"):
        refusals.append(rec["refused"])
    if errs:
        refusals.append(f"{errs} symbol(s) errored")
    status = ("refused" if rec.get("refused")
              else ("ok" if rows else "nothing_to_do"))
    return _row("analyst_snapshot", status, rows=rows,
                seconds=round(time.time() - t0, 2), refusals=refusals,
                by_status=by_status, coverage_rate=rec.get("coverage_rate"),
                path=rec.get("path"),
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
    "coverage": step_coverage,
}
assert set(_HANDLERS) == {s for s, _ in STEPS}, "every declared step needs a handler"


# ===========================================================================
# THE RUNNER
# ===========================================================================


class SamePassAlreadyRan(RuntimeError):
    """A daily pass for this date is on disk and `--force` was not given."""


def run_daily_pass(*, day: str | None = None, force: bool = False,
                   write_receipt: bool = True) -> dict:
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
        try:
            row = _HANDLERS[step_id](ctx)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("daily pass step %s raised", step_id)
            row = _row(step_id, "error", refusals=[_trunc(exc)])
        row.setdefault("what", what)
        ctx["rows"].append(row)

    rows = ctx["rows"]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    receipt = {
        "receipt": "daily_pass",
        "roadmap_item": "chunk 12 T1",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "date": day, "run": run,
        "git_head": git_head(),
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": _now(),
        "elapsed_s": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "declared_steps": [s for s, _ in STEPS],
        "steps": rows,
        "step_status_counts": counts,
        "steps_that_did_not_run": [r["step"] for r in rows
                                   if r["status"] in ("refused", "error")],
        "us_rth": ctx.get("rth"),
        "forced": bool(force),
        "prior_receipts": [p.name for p in prior],
        "read_me_first": (
            "One row per DECLARED step, in order, always — the runner walks the "
            "step list, not the list of things that worked. `refused` NAMES the "
            "missing precondition and is a finding, not a failure; "
            "`nothing_to_do` means the step ran correctly and there was "
            "nothing, which is not the same as zero. Nothing here places an "
            "order, arms a lane, or asks a model for anything."),
        "headline": (
            f"{counts['ok']} ok / {counts['nothing_to_do']} nothing-to-do / "
            f"{counts['refused']} refused / {counts['error']} error / "
            f"{counts['skipped']} skipped over {len(STEPS)} steps"),
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
        "steps": [{"step": s, "what": w,
                   "note": (skip_note if s == "book_cadence" and not rth.get("inside")
                            else None)}
                  for s, w in STEPS],
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
    except SamePassAlreadyRan as exc:
        print(f"REFUSED: {exc}")
        return 2
    print_receipt(receipt)
    return 0


__all__ = ["INTRADAY_CADENCES", "STATUSES", "STEPS", "SamePassAlreadyRan",
           "cadence_list", "existing_receipts", "git_head", "main", "out_dir",
           "plan", "print_receipt", "pull_all_news", "read_coverage",
           "receipt_path", "run_analyst_snapshot", "run_cadence_pass",
           "run_daily_pass", "run_date", "run_e1_append", "us_rth_state"]


if __name__ == "__main__":
    raise SystemExit(main())
