"""The simulation loop — cycles, checkpoints, and a stop that never loses work.

Started by `sim_session.start()` (the button), never by hand in normal use:

    python -m scripts.sim_run --session <id>

WHAT A CYCLE DOES, AND WHY IT IS SHAPED THIS WAY
================================================
One cycle is a fixed sequence of UNITS, each of which is small, idempotent and
writes its own receipt:

    reconcile   the broker's own view of the book -> pc_book/<date>/nav.jsonl
    funnel      refresh the candidate set when it is stale (once a session)
    analyst     the nightly analyst pull (once a day)
    rank        the cross-sectional ranker over the survivorship-free panel
    forecast    investigator rows at h=1 and h=5, once per UTC day (zero = red)
    review      pre-open review of every held name, 2-sigma patience rule
    plan        the book it would hold, and in paper_profit mode the orders
    grade       whatever reality has resolved since the last cycle
    learn       ONE queued research unit

Until 2026-09-23 this list was a LIE: `plan` was documented and never written,
so the loop ran reconcile/rank/grade/learn and no ranking could ever become a
decision. A 144-cycle session produced zero orders for two independent reasons
and only one of them was reported. A docstring that describes a step the code
does not take is worse than no docstring -- it is a guarantee nobody checks.

The unit boundary is the only place the loop checks whether to stop. That is the
whole safety design: `sim_session.should_continue()` is consulted BETWEEN units,
so a stop always lands somewhere the state on disk is complete. Nothing is ever
killed part-way through a fit or a broker write.

Murat, 2026-09-22: *"it should stop at a safe time save everything and maybe
continue not terminate or leave it on the middle."*

WHY CYCLES AND NOT ONE LONG JOB
===============================
`night_g3_evolve_v2` held a five-hour run in memory and wrote one receipt at
exit. When the PC died at 3.1 hours the receipt said `exited with no receipt`
and the work was gone. A cycle that checkpoints is worth more than a cycle that
is fast: at any moment the most that can be lost is the current unit.

The market is not always open, and that is fine. `rank` and `learn` are useful
at any hour; `reconcile` reads the broker whenever it answers; `plan` in trade
mode defers to the venue clock. A simulation started at 14:00 HKT spends its
first seven hours on research and its last five on a live session, and the cycle
log says which was which.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                      # noqa: E402,F401
from backend.services import sim_session as SS             # noqa: E402

logger = logging.getLogger("sim_run")

#: A unit that overruns this is reported, not killed. The loop's promise is that
#: it stops at boundaries; enforcing a timeout by killing would break exactly
#: the promise the design exists to keep.
SLOW_UNIT_S = 1800

#: A cycle is paced to at least this period. Once `u_rank` learned to skip an
#: unchanged panel, a cycle fell from 198s to 4s -- and an 8-hour session would
#: have spun ~800 near-empty cycles, each writing a receipt, none of them
#: learning anything the previous one had not. The loop should WAIT for the
#: world to change, not re-ask an unchanged question. Bars refresh daily and the
#: broker moves on a 5-minute scale, so that is the natural period.
MIN_CYCLE_PERIOD_S = 300

#: How often to beat while WAITING between cycles. Must be comfortably below
#: `sim_session.STALE_AFTER_S` (300) or a healthy idle reads as a dead process:
#: the two constants are equal, so a beat only at the cycle boundary is exactly
#: stale when the next cycle starts.
IDLE_BEAT_S = 60

#: Names the plan unit holds. 15-20 was the declared mandate 2026-09-22.
BOOK_SIZE = 18


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Cycle:
    """One pass of the units, with per-unit receipts and error containment."""

    def __init__(self, n: int, mode: str, out: Path) -> None:
        self.n = n
        self.mode = mode
        self.out = out
        self.units: dict[str, Any] = {}
        self.errors: list[dict] = []

    def unit(self, name: str, fn: Callable[[], Any]) -> Any:
        """Run one unit. An exception is RECORDED and the cycle continues.

        A failing unit must not end the session: a broker that 401s for ten
        minutes should cost those cycles' reconciles, not the night's research.
        The error travels in the receipt so the morning can see it.
        """
        t0 = time.time()
        # HEARTBEAT BEFORE EVERY UNIT, not only at the cycle boundary.
        #
        # `sim_session` DERIVES UNCLEAN from a heartbeat older than
        # STALE_AFTER_S (300s), which is the right rule -- a vanished process
        # leaves a stale beat and no stop receipt. But a beat written only when
        # a CYCLE starts says nothing about a cycle containing a legitimately
        # long unit. On 2026-09-24 the analyst pull took 67 minutes inside cycle
        # 1 and the session read UNCLEAN for the whole of it while the process
        # was healthy and its child was visibly working.
        #
        # A heartbeat means "this process is alive". It is alive during a unit.
        try:
            SS.heartbeat(cycle=self.n, note=f"cycle {self.n}: {name}")
        except Exception:                                          # noqa: BLE001
            # Never let the liveness signal kill the work it is reporting on.
            logger.debug("heartbeat before %s failed", name, exc_info=True)

        # AND KEEP BEATING WHILE IT RUNS.
        #
        # Beating only BEFORE a unit fixes a cycle made long by several short
        # units. It does nothing for a single unit that is legitimately long:
        # on 2026-09-25 the day rolled over, `u_analyst` correctly began its
        # nightly 3,214-ticker pull, and the session read UNCLEAN for the 67
        # minutes that took -- with the process alive and its child visibly
        # working the whole time.
        #
        # A daemon thread, so it can never hold the process open, and every
        # exception swallowed: a liveness signal must not be able to kill the
        # work it reports on.
        stop_beat = threading.Event()

        def _beat() -> None:
            waited = 0
            while not stop_beat.wait(IDLE_BEAT_S):
                waited += IDLE_BEAT_S
                try:
                    SS.heartbeat(cycle=self.n,
                                 note=f"cycle {self.n}: {name} ({waited}s)")
                except Exception:                                  # noqa: BLE001
                    logger.debug("beat during %s failed", name, exc_info=True)

        beater = threading.Thread(target=_beat, daemon=True,
                                  name=f"beat-{self.n}-{name}")
        beater.start()
        try:
            res = fn()
            dt = time.time() - t0
            stop_beat.set()
            self.units[name] = {"ok": True, "elapsed_s": round(dt, 1),
                                "result": _summarise(res)}
            if dt > SLOW_UNIT_S:
                self.units[name]["slow"] = (
                    f"{dt:.0f}s exceeds SLOW_UNIT_S {SLOW_UNIT_S}s; reported, "
                    f"not killed — the loop stops at boundaries by design")
            return res
        except Exception as exc:                                   # noqa: BLE001
            stop_beat.set()
            dt = time.time() - t0
            err = {"unit": name, "error": f"{type(exc).__name__}: {exc}"[:400],
                   "elapsed_s": round(dt, 1),
                   "where": traceback.format_exc(limit=3)[-600:]}
            self.errors.append(err)
            self.units[name] = {"ok": False, "elapsed_s": round(dt, 1),
                                "error": err["error"]}
            logger.warning("cycle %d unit %s failed: %s", self.n, name, err["error"])
            return None

    def payload(self, elapsed: float) -> dict:
        return {"cycle": self.n, "at": _now(), "mode": self.mode,
                "elapsed_s": round(elapsed, 1), "units": self.units,
                "errors": self.errors}


def _summarise(res: Any) -> Any:
    """Receipts stay readable: a cycle log is not a place for a 3,000-row frame."""
    if res is None or isinstance(res, (int, float, str, bool)):
        return res
    if isinstance(res, dict):
        return {k: v for k, v in res.items()
                if isinstance(v, (int, float, str, bool, type(None)))}
    if isinstance(res, (list, tuple)):
        return {"n": len(res)}
    return str(type(res).__name__)


# ────────────────────────────────── units ───────────────────────────────────

def u_reconcile(out: Path) -> dict:
    from backend.services import pc_broker as PB
    snap = PB.snapshot(tag="sim", out_dir=out)
    return {"equity": snap["equity"], "cash": snap["cash"],
            "n_positions": snap["n_positions"],
            "invested_frac": snap.get("invested_frac")}


def _bars_fingerprint() -> str:
    """What the ranking actually depends on: the bar files' size and mtime."""
    from backend.services import xs_ranker as XR
    parts = []
    for p in XR.survivorship_free_paths():
        try:
            s = p.stat()
            parts.append(f"{p.name}:{s.st_size}:{int(s.st_mtime)}")
        except OSError:
            parts.append(f"{p.name}:absent")
    return "|".join(parts)


def u_funnel(out: Path) -> dict:
    """Refresh the candidate set ONLY when it is stale, at most once a session.

    THE POINT OF THIS UNIT
    ----------------------
    `funnel_night10.json` is what `investment_committee` and every decision
    contract rank. On 2026-09-22 it was found to be a static file dated
    2026-08-11 -- forty tickers, `n_considered: 2` -- and the reason it went 44
    days without a refresh is that NOTHING CALLED THE REFRESH. There was no
    scheduled caller, and the command printed to operators
    (`python -m backend.services.opportunity_funnel`) had no `__main__` and
    exited 0 in silence. Both are fixed; this unit is the scheduled caller, so
    the staleness line stops being the only thing standing between a fresh
    decision and a month-old one.

    It is gated the same way `u_rank` is gated, and for the same reason: the
    funnel costs ~310s, ~25 batch price calls and 80 per-ticker calls, and
    running it every cycle of an 8-hour session would spend the night rebuilding
    one answer and burn the finnhub budget by cycle 4. The gate here is the
    snapshot's own AGE rather than a fingerprint, because the input (the live
    market) always differs and only the answer's shelf life matters.

    A failure is a SKIP, never a raised error: the existing snapshot is still
    the best candidate set on disk, and killing a cycle -- and with it the
    grade and learn units -- because a symbol list 503'd would trade a whole
    night for a data refresh. The reason is recorded on the cycle payload.
    """
    from backend.services import investment_committee as IC
    path = Path(_config.IC_FUNNEL_PATH)
    stamp = out / "funnel_refreshed.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = payload.get("generated_at")
        n_before = len(payload.get("candidates") or [])
    except (OSError, ValueError) as e:
        generated_at, n_before = None, 0
        logger.warning("funnel unreadable (%s); refreshing", e)

    stale = IC.funnel_staleness(generated_at)
    if not stale:
        return {"skipped": "candidate set is fresh",
                "generated_at": generated_at,
                "age_days": round(IC._funnel_age_days(generated_at) or 0.0, 2),
                "n_candidates": n_before}
    # Once per session. A snapshot that is still stale after a successful
    # rebuild means the rebuild wrote an old stamp, which is a bug to see once
    # rather than a retry loop to run 120 times.
    if stale and stamp.exists():
        return {"skipped": "already attempted this session",
                "why_it_was_stale": stale[:120]}

    res = _in_subprocess("funnel")
    # `main()` returns 2 on a REFUSED rebuild (a stage failed and the previous
    # snapshot was deliberately left alone). The subprocess still exits 0, so
    # the non-zero rc has to be read here or a refusal reads as a success.
    if not res.get("failed") and res.get("rc") not in (0, None):
        res = {"failed": f"opportunity_funnel refused (rc {res['rc']})"}
    stamp.write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "was": generated_at, "result": res}, indent=1, default=str),
        encoding="utf-8")
    if res.get("failed"):
        # Not raised. See the docstring.
        return {"refresh_failed": str(res["failed"])[:200],
                "kept": generated_at, "n_candidates": n_before,
                "note": "the previous snapshot is untouched and still ranks"}
    try:
        after = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"refresh_failed": f"snapshot unreadable after refresh: {e}"}
    now_stamp = after.get("generated_at")
    if now_stamp == generated_at:
        # The subprocess said rc 0 and the snapshot's stamp did not move. That
        # is not a refresh; it is the whole 2026-09-22 failure in miniature --
        # a remedy that reports success and changes nothing. Verify the
        # persistence claim, do not take the exit code's word for it.
        return {"refresh_failed": "rc 0 but `generated_at` did not move",
                "kept": generated_at, "n_candidates": n_before,
                "note": "check that opportunity_funnel wrote to IC_FUNNEL_PATH"}
    return {"refreshed": True, "was": generated_at, "now": now_stamp,
            "n_candidates": len(after.get("candidates") or []),
            "n_before": n_before}


def u_analyst(out: Path) -> dict:
    """Pull analyst targets and revisions, once a session.

    WHY THIS RUNS EVERY NIGHT AND NOT ON DEMAND
    -------------------------------------------
    `target_revisions` is historical and would be the same tomorrow. But
    `target_snapshots` has NO history at the vendor: the consensus target is a
    snapshot of today, and the only way it ever becomes point-in-time usable is
    if we write one row per night and let the series accrue. A month of nightly
    pulls is a month of revision data we can difference ourselves; skipping
    nights leaves holes that cannot be backfilled from anywhere.

    So the cost of missing a night is permanent, which is why this is a unit and
    not a script someone remembers to run.

    Out of process and once per session: ~1.0s a ticker over ~3,000 names is
    about 50 minutes, and running it every cycle of an 8-hour session would do
    nothing but exhaust the vendor's patience.
    """
    # ONCE A DAY, not once a session. The vendor's data changes daily, and the
    # first version of this gate keyed on a per-session stamp -- so starting a
    # second session on the same day re-ran a 67-minute pull that had already
    # completed, inside cycle 1, for nothing. Observed on 2026-09-24.
    #
    # The day's own receipt is the honest test of "already done": it is written
    # by the puller itself, so the gate reads the work rather than a note about
    # the work.
    day = date.today().isoformat()
    receipt = (Path(_config.OPTIMUS_LEDGER_DIR) / "analyst"
               / f"analyst_pull_{day}.json")
    if receipt.exists():
        try:
            r = json.loads(receipt.read_text(encoding="utf-8"))
            return {"skipped": f"already pulled today ({day})",
                    "n_snapshots": r.get("n_snapshots"),
                    "n_revision_rows": r.get("n_revision_rows")}
        except (OSError, ValueError):
            pass            # an unreadable receipt is not proof of a good pull
    stamp = out / "analyst_pulled.json"
    if stamp.exists():
        return {"skipped": "already attempted this session"}
    res = _in_subprocess("analyst", timeout=5400.0)
    stamp.write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "result": res}, indent=1, default=str), encoding="utf-8")
    if res.get("failed"):
        # A SKIP, not a raise. The night's ranking and grading do not depend on
        # this, and losing them to a vendor timeout would be a bad trade.
        return {"pull_failed": str(res["failed"])[:200],
                "note": "the existing analyst parquet is untouched"}
    return {"pulled": True, **{k: v for k, v in res.items() if k != "failed"}}


def u_rank(out: Path) -> dict:
    """Re-rank ONLY when the bars moved.

    `build_panel` reads ~7M rows, costs ~100s and peaks around 3 GB. Daily bars
    change once a day, so re-ranking every cycle of an 8-hour session would
    spend the whole night re-deriving one answer and leave the learn unit no
    room. The fingerprint is the bar files' size and mtime -- the thing the
    ranking actually depends on -- so a refreshed panel still re-ranks at once.
    """
    from backend.services import xs_ranker as XR
    fp = _bars_fingerprint()
    prior = out / "ranking.json"
    if prior.exists():
        try:
            old = json.loads(prior.read_text(encoding="utf-8"))
            if old.get("bars_fingerprint") == fp:
                return {"skipped": "bars unchanged since the last rank",
                        "asof": old.get("asof"),
                        "n_eligible": old.get("n_eligible"),
                        "top1": (old.get("top") or [{}])[0].get("symbol")}
        except (OSError, ValueError):
            pass
    res = _rank_in_subprocess(str(out))
    if res.get("failed"):
        raise RuntimeError(f"rank subprocess: {res['failed']} {res.get('stderr','')[:200]}")
    # stamp the fingerprint so the next cycle can skip
    prior_p = out / "ranking.json"
    try:
        payload = json.loads(prior_p.read_text(encoding="utf-8"))
        payload["bars_fingerprint"] = fp
        prior_p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return res


#: The ranker, out-of-process. `build_panel` peaks around 3 GB on 7M rows and
#: pandas keeps those pages for the life of the interpreter; over a 12-hour
#: session that is the difference between a bounded worker and an OOM. The
#: subprocess writes `ranking.json` itself and returns only the summary.
_RANK_SRC = """
import json, warnings, sys
warnings.filterwarnings('ignore')
from backend.services import xs_ranker as XR
from pathlib import Path
out = Path(sys.argv[1])
panel = XR.build_panel(XR.load_bars(XR.survivorship_free_paths()))
oos, folds = XR.walk_forward(panel)
cal = XR.calibrate(oos)
model, train_end = XR.fit_production(panel)
ranked = XR.rank_asof(panel, model, cal, train_end=train_end)
topk = XR.top_k_backtest(oos, k=20)
payload = {
    'receipt': 'sim_ranking',
    'asof': str(ranked['asof'].iloc[0]),
    'n_eligible': int(len(ranked)),
    'model_version': str(ranked['model_version'].iloc[0]),
    'ic_mean': cal.get('ic_mean'), 'ic_t': cal.get('ic_t'),
    'top20_net_rel_21d': topk.get('mean_net_rel_21d'),
    'top': [{'rank': int(r['rank_21d']), 'symbol': r['symbol'],
             'decile': int(r['decile']),
             'expected_relative_return_21d_net': r['expected_relative_return_21d_net'],
             'calibration_measured': bool(r['calibration_measured'])}
            for _, r in ranked.head(25).iterrows()],
}
(out / 'ranking.json').write_text(json.dumps(payload, indent=1, default=str), encoding='utf-8')
summary = {'n_eligible': payload['n_eligible'], 'ic_mean': payload['ic_mean'],
           'top20_net_rel_21d': payload['top20_net_rel_21d'],
           'top1': payload['top'][0]['symbol'] if payload['top'] else None}
print('<<<' + json.dumps(summary, default=str) + '>>>')
"""


def _rank_in_subprocess(out_dir: str, timeout: float = 2400.0) -> dict:
    import subprocess
    r = subprocess.run([sys.executable, "-c", _RANK_SRC, out_dir], cwd=str(REPO),
                       capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    txt = r.stdout or ""
    if "<<<" in txt and ">>>" in txt:
        return json.loads(txt.split("<<<", 1)[1].rsplit(">>>", 1)[0])
    return {"failed": f"rc {r.returncode}", "stderr": (r.stderr or "")[-400:]}


#: A unit that failed in its subprocess is retried at most this many times per
#: session: a deterministic crash must not become a 5-minute retry loop.
DAILY_UNIT_MAX_ATTEMPTS = 3


def _attempts(out: Path, name: str, day: str) -> int:
    p = out / f"{name}_attempts_{day}.json"
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("n", 0))
    except (OSError, ValueError):
        return 0


def _bump_attempts(out: Path, name: str, day: str, res: Any) -> None:
    p = out / f"{name}_attempts_{day}.json"
    p.write_text(json.dumps({"n": _attempts(out, name, day) + 1, "last": res},
                            indent=1, default=str), encoding="utf-8")


def u_forecast(out: Path) -> dict:
    """Investigator forecasts, h=1 AND h=5, once per UTC day. ZERO IS RED.

    Murat, 2026-09-25: "continue making forecasts and decisions everyday with
    every nightly sim ... so we can review them later." From 2026-09-11 to
    2026-09-24 the ledger gained no investigator row at all, because the only
    forecaster with measured skill (§64) was a script somebody had to remember.
    This unit is the scheduled caller.

    Idempotent through the day receipt `forecasts/day_<date>.json`, which the
    worker writes at START and after every name: a DONE / REFUSED_CAP /
    DEGRADED receipt ends the day, a RUNNING one (a crash) resumes where it
    stopped rather than re-paying for names already written. The dollar cap is
    read by the worker from the same telemetry ledger its OpenClaw calls write.
    Out of process: the evidence packets need the bars panel (~3 GB peak).
    """
    day = datetime.now(timezone.utc).date().isoformat()
    receipt = Path(_config.OPTIMUS_LEDGER_DIR) / "forecasts" / f"day_{day}.json"
    if receipt.exists():
        try:
            r = json.loads(receipt.read_text(encoding="utf-8"))
            if r.get("state") in ("DONE", "REFUSED_CAP", "DEGRADED"):
                return {"skipped": f"already ran today ({day})",
                        "state": r["state"],
                        "n_rows_written": r.get("n_rows_written"),
                        "status": ("DEGRADED" if not r.get("n_rows_written")
                                   else "ok")}
        except (OSError, ValueError):
            pass
    if _attempts(out, "forecast", day) >= DAILY_UNIT_MAX_ATTEMPTS:
        return {"skipped": f"{DAILY_UNIT_MAX_ATTEMPTS} failed attempts today",
                "status": "DEGRADED"}
    import subprocess
    try:
        res = _in_subprocess("forecast",
                             timeout=float(_config.FORECAST_UNIT_TIMEOUT_S))
    except subprocess.TimeoutExpired as exc:
        # A timeout is an ATTEMPT: uncounted, a worker that always hangs would
        # be relaunched for two hours every cycle. The RUNNING day receipt
        # keeps what it wrote, so the next attempt resumes.
        res = {"failed": f"timeout after {exc.timeout}s"}
    if res.get("failed") or res.get("state") == "RUNNING":
        _bump_attempts(out, "forecast", day, res)
    n = int(res.get("n_rows_written") or 0)
    return {**{k: v for k, v in res.items()
               if isinstance(v, (int, float, str, bool, type(None)))},
            "status": "ok" if n > 0 else "DEGRADED"}


#: The review runs pre-open, on the US venue's clock.
REVIEW_AFTER_ET = (8, 0)
MARKET_OPEN_ET = (9, 30)
MARKET_CLOSE_ET = (16, 0)


def _now_et() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))


def u_review(out: Path, *, now_et: datetime | None = None) -> dict:
    """The daily review of every held name, with the 2-sigma patience rule.

    First cycle after 08:00 ET on a weekday: `daily_review.run_daily` over
    Murat's book, PC-PAPER and every frozen llm_portfolio book, writing
    `review/review_<date>.json` + `morning_<date>.md` and one graded h=5 row
    per decisive label. Then, during the session, a held name that moves more
    than 2 sigma_63 intraday triggers ONE re-review for that name that day
    (`review_<date>_intraday_<HHMM>.json`; mints nothing).

    Weekends are skipped: the patience rule means "decide next SESSION", and a
    Saturday review would spend Friday's WATCH on a day nothing can trade.
    """
    from backend.services import daily_review as DR
    now = now_et or _now_et()
    day = now.date().isoformat()
    if now.weekday() >= 5:
        return {"skipped": "weekend: no session to review for"}
    if (now.hour, now.minute) < REVIEW_AFTER_ET:
        return {"skipped": f"before {REVIEW_AFTER_ET[0]:02d}:{REVIEW_AFTER_ET[1]:02d} ET"}
    jpath, _ = DR.review_paths(day)
    if not jpath.exists():
        if _attempts(out, "review", day) >= DAILY_UNIT_MAX_ATTEMPTS:
            return {"skipped": f"{DAILY_UNIT_MAX_ATTEMPTS} failed attempts today",
                    "status": "DEGRADED"}
        res = _in_subprocess("review", timeout=1800.0,
                             args=[json.dumps({"asof": day})])
        if res.get("failed"):
            _bump_attempts(out, "review", day, res)
        return {"morning": True, **{k: v for k, v in res.items()
                                    if isinstance(v, (int, float, str, bool,
                                                      type(None)))}}

    # INTRADAY: only while the venue is open, only for names not yet re-reviewed.
    if not (MARKET_OPEN_ET <= (now.hour, now.minute) < MARKET_CLOSE_ET):
        return {"skipped": "morning review done; market closed",
                "review": str(jpath)}
    table = DR.held_sigma_table(jpath)
    stamp = jpath.parent / f"intraday_{day}.json"
    try:
        already = json.loads(stamp.read_text(encoding="utf-8")).get("tickers", [])
    except (OSError, ValueError):
        already = []
    try:
        from backend.services import pc_broker as PB
        live = PB.last_prices(sorted(table))
    except Exception as exc:                                       # noqa: BLE001
        return {"intraday": "no live prices", "why": f"{type(exc).__name__}: {exc}"[:160]}
    trig = DR.intraday_triggers(table, live, already=already)
    if not trig:
        return {"intraday": "no held name beyond 2 sigma", "n_watched": len(table)}
    tag = now.strftime("%H%M")
    res = _in_subprocess("review", timeout=1800.0, args=[json.dumps(
        {"asof": day, "live_prices": {t["ticker"]: t["price"] for t in trig},
         "intraday_tag": tag})])
    stamp.write_text(json.dumps({"tickers": sorted(set(already) | {t["ticker"] for t in trig})},
                                indent=1), encoding="utf-8")
    return {"intraday": tag, "triggered": [f"{t['ticker']} {t['z']:+.1f}σ" for t in trig][:10],
            **{k: v for k, v in res.items()
               if isinstance(v, (int, float, str, bool, type(None)))}}


#: Where `u_plan`'s PROBE decisions are written as contract-shaped rows. A
#: SUBFOLDER of the decision contract's folder, not a file in it: the top-level
#: `decisions/<date>.json` is written whole by `decision_contract`, and rows
#: appended there by a second writer would be lost on its next run. The grader
#: (`decision_ledger._open_contract_rows`) and `scripts/decision_autopsy.py`
#: both read this subfolder as well, so the rows are graded like the rest.
PC_PLAN_SUBDIR = "pc_plan"
PROBE_POLICY_ID = "sim_run.u_plan.probe"
PROBE_POLICY_VERSION = "c3-v0"


def _asof_et() -> str:
    """The US session date the plan is for (orders only go while it is open)."""
    return _now_et().date().isoformat()


def _probe_grade(ledger_path: Path | None = None) -> dict:
    """The SHORTLIST's own forward grade, from SCORED `decision_ledger` rows.

    Not `top20_net_rel_21d`: that number measures the ranker, and the shortlist
    is a different selector. Graded on the SHORTEST declared PROBE horizon, one
    decision day counted once (rows from one day are one observation, CANON
    §58). Below `PROBE_GRADE_MIN_SESSIONS` distinct days the verdict is
    UNMEASURED_TRADE_SMALL and the plan may trade at the probe cap.
    """
    from backend.services import decision_ledger as DL
    hid = str(_config.PROBE_SHORTLIST_HYPOTHESIS_ID)
    h = min(int(x) for x in _config.PROBE_HORIZONS_SESSIONS)
    by_day: dict[str, list[float]] = {}
    for r in DL.read(ledger_path):
        d = r.get("detail") or {}
        if str(r.get("state")) != "SCORED" or not isinstance(d, dict):
            continue
        # A PROBE row graded under the day's CONTRACT hypothesis (the ALLE
        # fix) keeps the shortlist's id in `shortlist_hypothesis_id`.
        if (hid not in (d.get("hypothesis_id"), d.get("shortlist_hypothesis_id"))
                or d.get("horizon_sessions") != h):
            continue
        ex = d.get("excess_return")
        if ex is None:
            continue
        by_day.setdefault(str(r.get("asof"))[:10], []).append(float(ex))
    need = int(_config.PROBE_GRADE_MIN_SESSIONS)
    n_days = len(by_day)
    day_means = [sum(v) / len(v) for v in by_day.values()]
    mean = (sum(day_means) / n_days) if n_days else None
    base = {"hypothesis_id": hid, "horizon_sessions": h, "n_days_scored": n_days,
            "min_days": need, "mean_excess_per_day": mean}
    if n_days < need:
        return {**base, "verdict": "UNMEASURED_TRADE_SMALL", "may_trade": True,
                "why": (f"{n_days} of {need} scored decision days at h={h}: "
                        f"unmeasured, so it trades at the probe cap")}
    if mean is not None and mean <= 0:
        return {**base, "verdict": "MEASURED_NEGATIVE", "may_trade": False,
                "why": (f"the shortlist's PROBE rows earned {mean*100:+.2f}% "
                        f"excess per decision day at h={h} over {n_days} days")}
    return {**base, "verdict": "MEASURED_POSITIVE", "may_trade": True,
            "why": (f"the shortlist's PROBE rows earned {mean*100:+.2f}% excess "
                    f"per decision day at h={h} over {n_days} days")}


def _blend_grade(ledger_path: Path | None = None) -> dict:
    """The E[r] BLEND's own forward grade (chunk 2), from SCORED ledger rows.

    A row counts when it carried `er_total` at `ER_BLEND_GRADE_HORIZON`: its
    score is `sign(er_total) * excess_return` -- what following the blend's
    direction on that row earned. One decision day counts once (CANON §58).
    Below `ER_BLEND_GRADE_MIN_SESSIONS` distinct days the blend is UNMEASURED
    and EXPLOIT refuses: nothing sized on E[r] trades before E[r] is graded.
    """
    from backend.services import decision_ledger as DL
    h = int(_config.ER_BLEND_GRADE_HORIZON)
    by_day: dict[str, list[float]] = {}
    for r in DL.read(ledger_path):
        d = r.get("detail") or {}
        if str(r.get("state")) != "SCORED" or not isinstance(d, dict):
            continue
        if d.get("er_total") is None or d.get("excess_return") is None:
            continue
        if int(d.get("er_horizon") or d.get("horizon_sessions") or 0) != h:
            continue
        er, ex = float(d["er_total"]), float(d["excess_return"])
        if er == 0:
            continue
        by_day.setdefault(str(r.get("asof"))[:10], []).append((1.0 if er > 0 else -1.0) * ex)
    need = int(_config.ER_BLEND_GRADE_MIN_SESSIONS)
    n_days = len(by_day)
    means = [sum(v) / len(v) for v in by_day.values()]
    mean = (sum(means) / n_days) if n_days else None
    base = {"horizon_sessions": h, "n_days_scored": n_days, "min_days": need,
            "mean_signed_excess_per_day": mean}
    if n_days < need:
        return {**base, "verdict": "UNMEASURED", "may_trade": False,
                "why": (f"the E[r] blend has {n_days} of {need} scored decision days at "
                        f"h={h}: EXPLOIT waits for its own grade")}
    if mean is not None and mean <= 0:
        return {**base, "verdict": "MEASURED_NEGATIVE", "may_trade": False,
                "why": f"the E[r] blend earned {mean*100:+.2f}%/day signed excess over {n_days} days"}
    return {**base, "verdict": "MEASURED_POSITIVE", "may_trade": True,
            "why": f"the E[r] blend earned {mean*100:+.2f}%/day signed excess over {n_days} days"}


def _daily_sigma(row: dict) -> float:
    v = row.get("vol_annual")
    if isinstance(v, (int, float)) and v > 0:
        return float(v) / (252 ** 0.5)
    return float(_config.PROBE_REF_DAILY_SIGMA)


def probe_worst_case(*, equity: float, n_names: int, weight: float,
                     daily_sigma: float, label: str) -> dict:
    """Session protocol item 4, in dollars: `n x notional% x stop_sigma_pct`
    and `sum|notional| / equity`.

    u_plan declares NO stop order, so two numbers are printed and neither is
    hidden: the k-sigma session (every name moves `PROBE_WORST_CASE_SIGMA`
    daily sigmas against the book at once) and the no-stop ceiling (the whole
    gross notional, since a long cash position can lose all of it).
    """
    k = float(_config.PROBE_WORST_CASE_SIGMA)
    stop_sigma_pct = k * float(daily_sigma)
    gross = float(n_names) * float(weight)
    k_sigma_usd = float(n_names) * float(weight) * stop_sigma_pct * float(equity)
    ceiling_usd = gross * float(equity)
    return {
        "label": label, "n_names": int(n_names), "notional_pct": float(weight),
        "stop_declared": False, "adverse_sigma": k,
        "daily_sigma": float(daily_sigma), "stop_sigma_pct": stop_sigma_pct,
        "gross_over_equity": gross, "equity_usd": float(equity),
        "worst_case_k_sigma_usd": -k_sigma_usd,
        "worst_case_no_stop_usd": -ceiling_usd,
        "line": (f"{label}: {int(n_names)} x {weight:.2%} x {stop_sigma_pct:.2%} "
                 f"({k:g} sigma of {daily_sigma:.2%}/day) = -${k_sigma_usd:,.0f} "
                 f"on ${equity:,.0f}; sum|notional|/equity = {gross:.2f}; "
                 f"no stop is declared, so the ceiling is -${ceiling_usd:,.0f}"),
    }


def _pc_plan_dir(contracts_dir: Path | None) -> Path:
    if contracts_dir is not None:
        return Path(contracts_dir)
    from backend.services import decision_contract as DC
    return Path(DC.DECISIONS_DIR) / PC_PLAN_SUBDIR


def _prior_probe_holdings(folder: Path, asof: str) -> set[str]:
    """Tickers an EARLIER plan was permitted to buy as PROBE. Their exits are
    PROBE exits: without this, a PROBE position whose name left the shortlist
    could only ever be sold by the EXPLOIT gate, which is refused."""
    out: set[str] = set()
    if not folder.is_dir():
        return out
    for p in folder.glob("20[0-9][0-9]-[01][0-9]-[0-3][0-9].json"):
        if p.stem >= asof:
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in blob.get("rows") or []:
            if r.get("direction") == "PROBE" and r.get("acting"):
                out.add(str(r.get("ticker")))
    return out


#: The day's decision contract REFUSED a name with one of these terminal
#: states: the contract MEASURED no positive expected value for it. PROBE must
#: not buy it the same day (the 2026-09-25 ALLE clash: the contract refused
#: ALLE on insider t 1.40 < 2.0 while PC-PAPER bought 131 shares off the same
#: shortlist). `EDGE_BELOW_BAR` is the refusal CLASS the contract writes beside
#: the terminal state `NEGATIVE_EV`; either one excludes. `DATA_MISSING` and
#: the rest do NOT: a missing input is not a measurement against the name.
CONTRACT_NEGATIVE_EV_STATES = frozenset({"NEGATIVE_EV", "EDGE_BELOW_BAR"})


def _contract_view(folder: Path, asof: str, contract_file: Path | None) -> dict:
    """What the day's top-level decision contract says about each ticker.

    Returns `{"status": "present"|"absent"|"unreadable", "path", "refused":
    {TICKER: reason}, "hypothesis": {TICKER: (hypothesis_id, basis)}}`.
    `refused` holds only REFUSED rows whose `terminal_state` or
    `refusal_class` is negative-EV. `hypothesis` prefers a PROBE row's id, else
    any row's, so the plan's PROBE rows are graded under the contract's
    hypothesis (one grade covers both writers).
    """
    if contract_file is None:
        contract_file = (folder.parent / f"{asof}.json"
                         if folder.name == PC_PLAN_SUBDIR else None)
    view: dict = {"status": "absent",
                  "path": str(contract_file) if contract_file else None,
                  "refused": {}, "hypothesis": {}}
    if contract_file is None or not Path(contract_file).is_file():
        return view
    try:
        blob = json.loads(Path(contract_file).read_text(encoding="utf-8"))
        rows = list(blob.get("rows") or [])
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        view["status"] = "unreadable"
        view["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return view
    view["status"] = "present"
    ranked: dict[str, tuple[int, str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = str(r.get("ticker") or "").upper()
        if not t:
            continue
        refused = r.get("direction") == "REFUSED" or r.get("authority") == "REFUSED"
        states = {str(r.get("terminal_state")), str(r.get("refusal_class"))}
        if refused and states & CONTRACT_NEGATIVE_EV_STATES:
            view["refused"].setdefault(t, (
                f"{r.get('terminal_state')}/{r.get('refusal_class')}: "
                f"{str(r.get('refusal_reason') or r.get('authority_basis') or '')[:160]}"))
        hid = r.get("hypothesis_id")
        if hid:
            pri = 0 if r.get("direction") == "PROBE" else 1
            if t not in ranked or pri < ranked[t][0]:
                ranked[t] = (pri, str(hid), r.get("hypothesis_id_basis"))
    view["hypothesis"] = {t: (h, b) for t, (_, h, b) in ranked.items()}
    return view


def _write_probe_decisions(rows: list[dict], *, asof: str, folder: Path,
                           ledger_path: Path | None) -> dict:
    """Merge today's PROBE rows into `pc_plan/<asof>.json` and write DECIDED.

    Idempotent per `decision_id` (policy, ticker, asof, horizon): the plan runs
    every cycle, and the FIRST decision of the day is the one graded. A later
    cycle neither rewrites it nor adds a second ledger row.
    """
    from backend.services import decision_ledger as DL
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{asof}.json"
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        blob = {"date": asof, "source": "sim_run.u_plan", "rows": []}
    have = {str(r.get("decision_id")) for r in blob.get("rows") or []}
    new = [r for r in rows if str(r["decision_id"]) not in have]
    if new:
        blob.setdefault("rows", []).extend(new)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(blob, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, path)
    recorded, refused = 0, []
    for r in new:
        try:
            DL.record(r["decision_id"], "DECIDED", by="sim_run.u_plan", asof=asof,
                      path=ledger_path,
                      detail={"state": "PROBE", "ticker": r["ticker"],
                              "horizon_sessions": r["horizon_sessions"],
                              "weight": r["position_budget"]["weight"],
                              "dollars": r["position_budget"]["dollars"],
                              "thesis_source": r["thesis_source"],
                              "hypothesis_id": r["hypothesis_id"],
                              "shortlist_hypothesis_id": r.get("shortlist_hypothesis_id"),
                              "hypothesis_id_basis": r.get("hypothesis_id_basis"),
                              "ranking_verdict": r["ranking_verdict"],
                              "probe_verdict": r["probe_verdict"],
                              "acting": r["acting"], "virtual": r["virtual"],
                              "contract_file": str(path),
                              **{k: r.get(k) for k in DL.ER_ROW_FIELDS}})
            recorded += 1
        except DL.DecisionLedgerError as exc:
            refused.append({"decision_id": r["decision_id"], "reason": str(exc)[:200]})
    return {"file": str(path), "new_rows": len(new), "ledger_decided": recorded,
            "ledger_refused": refused}


def _er_summary(view: dict | None, red: str | None) -> dict:
    """The plan receipt's E[r] block: which components woke, whose weights."""
    if not view:
        return {"present": False, "red": red}
    names = view.get("names") or {}
    awake: dict[str, int] = {}
    priced = 0
    for v in names.values():
        c = v.get("h21") or {}
        if c.get("er") is not None:
            priced += 1
        for k in c.get("components_awake") or []:
            awake[k] = awake.get(k, 0) + 1
    return {"present": True, "red": red, "path": view.get("path"),
            "weights_source": view.get("weights_source"), "regime": view.get("regime"),
            "n_names": len(names), "n_priced_h21": priced, "awake_h21": awake,
            "unavailable": view.get("unavailable"),
            "calibration_vintage": view.get("calibration_vintage")}


def u_plan(out: Path, mode: str, *, asof: str | None = None,
           funnel_path: Path | None = None, ledger_path: Path | None = None,
           contracts_dir: Path | None = None, er_sources: Any = None,
           er_dir: Path | None = None, contract_file: Path | None = None) -> dict:
    """Ranking + committee shortlist -> a book, under EXPLOIT and PROBE.

    THE UNIT THAT DID NOT EXIST (2026-09-23), and then the unit that could not
    act (2026-09-25). It read only `ranking.json` and refused whenever the
    ranker's own `top20_net_rel_21d <= 0` -- measured negative since §59 -- so
    PC-PAPER never placed an order and nothing it could have decided was ever
    graded. Murat, 2026-09-25: *"make sure the engine makes decisions that we
    can then later judge."*

    Two sources, two states, two gates (roadmap 2026-09-25 C3, §16.2):

    * EXPLOIT -- the ranker's top `BOOK_SIZE`. The old gate, EXACTLY: the
      ranking's `top20_net_rel_21d` <= 0 is MEASURED_NEGATIVE and refused.
    * PROBE -- the committee shortlist (`investment_committee.shortlist`), at
      most `PROBE_MAX_NAMES` names at `PROBE_MAX_WEIGHT` each, sum <=
      `PROBE_GROSS_CAP`. NOT gated on the ranker's number (that measures a
      different selector). Gated on the shortlist's own forward grade
      (`_probe_grade`) once `PROBE_GRADE_MIN_SESSIONS` decision days are
      scored; until then UNMEASURED_TRADE_SMALL, which acts at the cap only in
      `paper_profit`.

    Every PROBE name writes contract-shaped rows (one per
    `PROBE_HORIZONS_SESSIONS`) to `decisions/pc_plan/<asof>.json` and a
    `DECIDED` ledger row, so the grader and `decision_autopsy` score them.
    An empty or refused shortlist is a RED line on the receipt, never silence.
    Orders go only while the venue clock says open, and never for a symbol that
    already has an open order (a 5-minute loop would otherwise re-send a queued
    order every cycle until it fills).

    CHUNK 2 (2026-09-25): every candidate gets `E[r_h]` from
    `expected_return.build`, decomposed by component, and every decision row
    carries the decomposition (`decision_ledger.ER_ROW_FIELDS`). EXPLOIT names
    are the ranker's list ordered by `E[r_21]` (E > 0 only), sized in proportion
    to E[r] under `ER_EXPLOIT_MAX_WEIGHT` and shrunk (never lifted) by the
    magnitude and regime scales -- and EXPLOIT still refuses until the blend's
    OWN 21-session grade exists and is positive (`_blend_grade`), on top of the
    ranker's gate. PROBE is chunk 1's, unchanged. A caller that injects
    `ledger_path` gets sandbox E[r] sources (its ranking and its ledger only).

    THE ALLE CLASH (adjudication 2026-09-26 row 11): the day's decision
    contract (`decisions/<asof>.json`, or `contract_file`) is read first. A
    name it REFUSED as `NEGATIVE_EV`/`EDGE_BELOW_BAR` is removed from PROBE and
    named in `contract_clash`; a refusal for any other reason (DATA_MISSING...)
    does not exclude. PROBE rows take the contract's `hypothesis_id` for the
    same ticker where one exists (the shortlist id moves to
    `shortlist_hypothesis_id`), so one grade covers both writers. An absent
    contract does not stop PROBE: the receipt says `contract: absent`, red.
    """
    from backend.services import expected_return as ER
    from backend.services import pc_broker as PB
    from backend.services import investment_committee as IC
    from backend.services import decision_contract as DC

    asof = asof or _asof_et()
    folder = _pc_plan_dir(contracts_dir)

    # ---- the ranker (EXPLOIT) -------------------------------------------------
    rank_path = out / "ranking.json"
    r: dict = {}
    if rank_path.exists():
        try:
            r = json.loads(rank_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            r = {}
    pool = list(r.get("top") or [])
    top = pool[:BOOK_SIZE]
    net = r.get("top20_net_rel_21d")
    if not top:
        verdict = "NO_RANKING"
        may_trade = False
    else:
        verdict = ("MEASURED_NEGATIVE" if (net is not None and net <= 0)
                   else "MEASURED_POSITIVE" if net is not None
                   else "UNMEASURED_TRADE_SMALL")
        may_trade = verdict != "MEASURED_NEGATIVE"
    ranking_verdict = {"verdict": verdict, "top20_net_rel_21d": net,
                       "ranking_asof": r.get("asof"),
                       "model_version": r.get("model_version")}
    blend_grade = _blend_grade(ledger_path)

    # ---- the shortlist (PROBE) ------------------------------------------------
    shortlist_red = None
    try:
        sl = IC.shortlist(asof, funnel_path=funnel_path)
    except IC.ShortlistRefused as exc:
        sl, shortlist_red = [], f"shortlist: 0, REFUSED: {exc}"
    if not sl and shortlist_red is None:
        shortlist_red = ("shortlist: 0, reason: the funnel's candidate file is "
                         "fresh and EMPTY -- no PROBE decision can be made today")

    # ---- the day's decision contract: its negative-EV refusals bind PROBE ----
    contract = _contract_view(folder, asof, contract_file)
    contract_clash = sorted({str(x["ticker"]) for x in sl
                             if str(x["ticker"]).upper() in contract["refused"]})
    contract_red = None
    if contract["status"] != "present":
        contract_red = (f"contract: {contract['status']} ({contract['path']}) -- PROBE "
                        f"proceeds WITHOUT the contract's negative-EV refusals"
                        + (f"; {contract['error']}" if contract.get("error") else ""))
        logger.warning("u_plan RED: %s", contract_red)
    if contract_clash:
        sl = [x for x in sl if str(x["ticker"]) not in contract_clash]

    # ---- the expected-return layer (chunk 2) ----------------------------------
    er_view, er_red = None, None
    cand = [str(x.get("symbol")) for x in pool] + [str(x["ticker"]) for x in sl]
    sandbox = ledger_path is not None or er_sources is not None
    try:
        src = er_sources or (ER.Sources.sandbox(out=out, decision_ledger=ledger_path)
                             if ledger_path is not None else
                             ER.Sources.production(asof=asof, out=out))
        er_view = ER.build(asof, cand, src,
                           out_dir=(er_dir if er_dir is not None else
                                    (out / "expected_return") if sandbox else None))
    except Exception as exc:                                       # noqa: BLE001
        er_red = f"expected_return: REFUSED {type(exc).__name__}: {exc}"[:300]
        logger.warning("u_plan RED: %s", er_red)

    def _er(sym: str, h: int = 21) -> dict | None:
        return (((er_view or {}).get("names") or {}).get(str(sym).upper()) or {}).get(f"h{h}")

    def _scale(sym: str) -> float:
        return float((((er_view or {}).get("names") or {}).get(str(sym).upper()) or {})
                     .get("size_scale", 1.0))

    er_pool = [(x, (_er(x["symbol"]) or {}).get("er")) for x in pool]
    if er_view is not None and any(e is not None for _, e in er_pool):
        ex_pick = sorted([(x, e) for x, e in er_pool if e is not None and e > 0],
                         key=lambda z: -z[1])[:BOOK_SIZE]
        exploit_basis = "E[r_21] > 0, descending"
    else:
        ex_pick = [(x, None) for x in top]
        exploit_basis = "ranker order (no E[r] priced)"
    exploit_acting = ((mode == "paper_profit") and may_trade
                      and blend_grade["may_trade"] and bool(ex_pick))
    exploit_syms = [x["symbol"] for x, _ in ex_pick]
    probe_rows = [x for x in sl if not (exploit_acting and x["ticker"] in exploit_syms)]
    probe_rows = probe_rows[:int(_config.PROBE_MAX_NAMES)]
    n_probe = len(probe_rows)
    w_probe = (min(float(_config.PROBE_MAX_WEIGHT),
                   float(_config.PROBE_GROSS_CAP) / n_probe) if n_probe else 0.0)
    probe_gross = n_probe * w_probe
    grade = _probe_grade(ledger_path)
    probe_acting = (mode == "paper_profit") and grade["may_trade"] and n_probe > 0

    snap = PB.snapshot(tag="plan", out_dir=out)
    equity = float(snap["equity"])
    held = {p["symbol"]: p["qty"] for p in snap["positions"]}

    probe_syms = [x["ticker"] for x in probe_rows]
    ex_syms = [s for s in exploit_syms if s not in probe_syms]
    room = max(0.0, 1.0 - probe_gross)
    ex_er = {x["symbol"]: e for x, e in ex_pick if x["symbol"] in ex_syms}
    if ex_syms and all(ex_er.get(s) is not None for s in ex_syms):
        tot = sum(ex_er[s] for s in ex_syms)
        w_by = {s: min(float(_config.ER_EXPLOIT_MAX_WEIGHT), room * ex_er[s] / tot) * _scale(s)
                for s in ex_syms}
    else:
        w_ex = (room / len(ex_syms)) if ex_syms else 0.0
        w_by = {s: w_ex for s in ex_syms}
    targets = [PB.Target(symbol=x["symbol"], weight=w_by[x["symbol"]], rank=x.get("rank"),
                         expected_relative_return_21d=(ex_er.get(x["symbol"])
                                                       if ex_er.get(x["symbol"]) is not None
                                                       else x.get("expected_relative_return_21d_net")),
                         median_dollar_vol=None,
                         reason=(f"EXPLOIT rank {x.get('rank')} decile {x.get('decile')}"
                                 + (f" E[r_21] {ex_er[x['symbol']]*100:+.2f}%"
                                    if ex_er.get(x["symbol"]) is not None else "")))
               for x, _ in ex_pick if x["symbol"] in ex_syms]
    targets += [PB.Target(symbol=x["ticker"], weight=w_probe,
                          median_dollar_vol=x.get("median_dollar_vol"),
                          reason=f"PROBE shortlist score {x.get('score')} ({x['source']})")
                for x in probe_rows]
    syms = [t.symbol for t in targets] + list(held)
    prices = PB.last_prices(syms) if syms else {}
    plans = PB.plan_orders(targets, equity=equity, held=held, prices=prices) if syms else []

    prior_probe = _prior_probe_holdings(folder, asof)

    def _state(sym: str) -> str:
        if sym in probe_syms:
            return "PROBE"
        if sym in ex_syms:
            return "EXPLOIT"
        return "PROBE_EXIT" if sym in prior_probe else "EXIT"

    def _may_send(p) -> bool:
        st = _state(p.symbol)
        return p.qty > 0 and ((st in ("PROBE", "PROBE_EXIT") and probe_acting)
                              or (st in ("EXPLOIT", "EXIT") and exploit_acting))

    by_state: dict[str, int] = {}
    for p in plans:
        if p.qty > 0:
            by_state[_state(p.symbol)] = by_state.get(_state(p.symbol), 0) + 1

    # ---- the worst case, in dollars, on every receipt (protocol item 4) -------
    sig_all = [_daily_sigma(x) for x in sl] or [float(_config.PROBE_REF_DAILY_SIGMA)]
    n_max = int(_config.PROBE_MAX_NAMES)
    w_max = min(float(_config.PROBE_MAX_WEIGHT), float(_config.PROBE_GROSS_CAP) / n_max)
    wc_admissible = probe_worst_case(
        equity=equity, n_names=n_max, weight=w_max, daily_sigma=max(sig_all),
        label="largest admissible PROBE book")
    wc_planned = probe_worst_case(
        equity=equity, n_names=n_probe, weight=w_probe,
        daily_sigma=max([_daily_sigma(x) for x in probe_rows] or sig_all),
        label="planned PROBE book")
    wc_exploit = probe_worst_case(
        equity=equity, n_names=BOOK_SIZE, weight=1.0 / BOOK_SIZE,
        daily_sigma=float(_config.PROBE_REF_DAILY_SIGMA),
        label=(f"largest admissible EXPLOIT book (gross <= 1 - PROBE gross, "
               f"<= {float(_config.ER_EXPLOIT_MAX_WEIGHT):.0%}/name)"))
    book_gross = sum(t.weight for t in targets
                     if (t.symbol in probe_syms and probe_acting)
                     or (t.symbol in ex_syms and exploit_acting))

    # ---- the decisions, graded later ------------------------------------------
    by_sym = {p.symbol: p for p in plans}
    expiries = {int(h): DC.sessions_expiry(date.fromisoformat(asof), int(h))
                for h in _config.PROBE_HORIZONS_SESSIONS}
    hid = str(_config.PROBE_SHORTLIST_HYPOTHESIS_ID)
    rows: list[dict] = []
    for x in probe_rows:
        p = by_sym.get(x["ticker"])
        px = prices.get(x["ticker"])
        c_hid, c_basis = contract["hypothesis"].get(str(x["ticker"]).upper(), (None, None))
        row_hid = c_hid or hid
        hid_basis = (f"the day's decision contract ({contract['path']}) carries "
                     f"hypothesis {c_hid} for {x['ticker']}: one grade covers both "
                     f"writers. Contract basis: {c_basis}" if c_hid else
                     f"config.PROBE_SHORTLIST_HYPOTHESIS_ID (contract {contract['status']}"
                     f" or no contract hypothesis for {x['ticker']})")
        for h, (expiry, basis) in sorted(expiries.items()):
            row = {
                "decision_id": DC.decision_id(
                    policy_id=PROBE_POLICY_ID, policy_version=PROBE_POLICY_VERSION,
                    ticker=x["ticker"], asof=asof, horizon_sessions=h),
                "asof": asof, "policy_id": PROBE_POLICY_ID,
                "policy_version": PROBE_POLICY_VERSION,
                "information_cutoff_utc": x["source"].split("@", 1)[-1],
                "licence": "PRODUCT_EXPERIMENT", "ticker": x["ticker"],
                "source": "investment_committee",
                "thesis_source": x["source"],
                "reasons": list(x.get("reasons") or [])[:6],
                "shortlist_score": x.get("score"),
                "direction": "PROBE", "authority": "PROBE",
                "hypothesis_id": row_hid, "shortlist_hypothesis_id": hid,
                "hypothesis_id_basis": hid_basis, "horizon_sessions": h,
                "horizon": {"sessions": h, "basis": "config.PROBE_HORIZONS_SESSIONS"},
                "expiry_utc": expiry, "expiry_basis": basis,
                "mode": mode, "acting": probe_acting, "virtual": not probe_acting,
                "position_budget": {
                    "weight": w_probe, "dollars": w_probe * equity,
                    "shares": int(p.target_qty) if p else 0, "price": px,
                    "capital_usd": equity, "virtual": not probe_acting,
                    "basis": ("config.PROBE_MAX_WEIGHT / PROBE_GROSS_CAP; "
                              "orders only while the venue is open")},
                "ranking_verdict": ranking_verdict,
                "probe_verdict": {k: grade[k] for k in ("verdict", "n_days_scored", "min_days")},
                "maximum_loss": probe_worst_case(
                    equity=equity, n_names=1, weight=w_probe,
                    daily_sigma=_daily_sigma(x), label=f"PROBE {x['ticker']}"),
                "built_utc": _now(),
            }
            row.update(ER.row_fields(er_view, x["ticker"], h))
            row["artifact_sha256"] = DC.seal(row)
            rows.append(row)
    ledger = (_write_probe_decisions(rows, asof=asof, folder=folder,
                                     ledger_path=ledger_path)
              if rows else {"new_rows": 0, "ledger_decided": 0})

    # ---- send ------------------------------------------------------------------
    to_send = [p for p in plans if _may_send(p)]
    sent: list[dict] = []
    send_block = None
    if to_send:
        try:
            is_open = bool((PB.clock() or {}).get("is_open"))
        except PB.BrokerError as exc:
            is_open, send_block = False, f"venue clock unreadable: {str(exc)[:120]}"
        if not is_open:
            send_block = send_block or "venue closed: orders wait for the open"
        else:
            try:
                open_syms = {o.get("symbol") for o in PB.orders(status="open")}
            except PB.BrokerError as exc:
                open_syms, send_block = None, f"open orders unreadable: {str(exc)[:120]}"
            if open_syms is not None:
                for p in to_send:
                    if p.symbol in open_syms:
                        sent.append({"status": "skipped", "symbol": p.symbol,
                                     "why": "an order for this symbol is already open"})
                        continue
                    try:
                        res = PB.submit(p)
                        res["state"] = _state(p.symbol)
                        sent.append(res)
                    except PB.BrokerError as exc:
                        sent.append({"status": "FAILED", "symbol": p.symbol,
                                     "state": _state(p.symbol), "error": str(exc)[:200]})

    acting = exploit_acting or probe_acting
    record = {"t": _now(), "asof": asof, "mode": mode,
              "verdict": verdict, "acting": acting,
              "exploit_acting": exploit_acting,
              "probe_verdict": grade["verdict"], "probe_acting": probe_acting,
              "probe_grade": grade,
              "equity": equity, "n_targets": len(targets),
              "n_considered": len({str(x.get("symbol")) for x in pool} | {x["ticker"] for x in sl}),
              "blend_grade": blend_grade, "exploit_basis": exploit_basis,
              "er": _er_summary(er_view, er_red),
              "er_top": (ER.format_top(er_view, n=10).splitlines() if er_view else
                         [er_red or "expected_return: no view"]),
              "shortlist": len(sl), "shortlist_red": shortlist_red,
              "contract": contract["status"], "contract_path": contract["path"],
              "contract_red": contract_red,
              "contract_clash": contract_clash,
              "contract_refused_excluded": len(contract_clash),
              "contract_clash_reasons": {t: contract["refused"].get(t.upper())
                                         for t in contract_clash},
              "n_probe": n_probe, "probe_weight": w_probe, "probe_gross": probe_gross,
              "n_orders": sum(1 for p in plans if p.qty > 0),
              "orders_by_state": by_state,
              "sendable_by_state": {st: sum(1 for p in to_send if _state(p.symbol) == st)
                                    for st in ("PROBE", "PROBE_EXIT", "EXPLOIT", "EXIT")},
              "n_to_send": len(to_send), "send_block": send_block,
              "turnover_usd": sum(p.notional for p in plans if p.qty > 0),
              "worst_case": {"largest_admissible": wc_admissible,
                             "largest_admissible_exploit": wc_exploit,
                             "planned_probe": wc_planned,
                             "acting_book_gross_over_equity": book_gross},
              "worst_case_line": wc_admissible["line"],
              "decisions": ledger,
              "refusals": [{"symbol": p.symbol, "refused": p.refused}
                           for p in plans if p.refused][:10],
              "book": [{"rank": t.rank, "symbol": t.symbol, "weight": t.weight,
                        "state": _state(t.symbol),
                        "expected_relative_return_21d": t.expected_relative_return_21d}
                       for t in targets],
              "sent": sent}
    if not to_send:
        why = []
        if mode != "paper_profit":
            why.append(f"mode={mode}")
        else:
            if not exploit_acting:
                why.append(f"EXPLOIT: ranking verdict {verdict}: refusing to buy "
                           f"a measured negative" if verdict == "MEASURED_NEGATIVE"
                           else f"EXPLOIT: ranking verdict {verdict}; "
                                f"blend {blend_grade['verdict']}: {blend_grade['why']}"
                           if not blend_grade["may_trade"]
                           else f"EXPLOIT: ranking verdict {verdict}; no name with E[r_21] > 0")
            if not probe_acting:
                why.append(f"PROBE: {shortlist_red or grade['why']}")
        record["why_not"] = "; ".join(why) or "nothing to trade"
    if shortlist_red:
        logger.warning("u_plan RED: %s", shortlist_red[:200])

    (out / "intended_book.json").write_text(
        json.dumps(record, indent=1, default=str), encoding="utf-8")
    with (out / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")

    return {"planned": True, "verdict": verdict, "acting": acting,
            "exploit_acting": exploit_acting,
            "blend_verdict": blend_grade["verdict"],
            "er_present": er_view is not None, "er_red": er_red,
            "probe_verdict": grade["verdict"], "probe_acting": probe_acting,
            "shortlist": len(sl), "shortlist_red": shortlist_red,
            "contract": contract["status"], "contract_red": contract_red,
            "contract_clash": contract_clash,
            "contract_refused_excluded": len(contract_clash),
            "n_considered": record["n_considered"], "n_probe": n_probe,
            "n_orders": record["n_orders"],
            # PERMITTED to be sent (acting gate applied), not merely planned:
            # the would-be EXPLOIT book is still planned and printed when its
            # gate refuses it, as it always was.
            "n_probe_orders": sum(1 for p in to_send if _state(p.symbol) == "PROBE"),
            "n_exploit_orders": sum(1 for p in to_send if _state(p.symbol) == "EXPLOIT"),
            "n_sent": sum(1 for s in sent if s.get("status") == "submitted"),
            "send_block": send_block,
            "turnover_usd": record["turnover_usd"],
            "worst_case_line": wc_admissible["line"],
            "decisions_new": ledger.get("new_rows", 0),
            "top1": targets[0].symbol if targets else None}


def u_grade() -> dict:
    from backend.services import forecast_grader as FG, decision_ledger as DL
    out: dict[str, Any] = {}
    try:
        r = FG.grade_due()
        out["forecasts"] = r.get("status") or r.get("headline")
    except Exception as exc:                                       # noqa: BLE001
        out["forecasts"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    try:
        r = DL.score_due()
        out["decisions"] = r.get("status") or r.get("headline")
    except Exception as exc:                                       # noqa: BLE001
        out["decisions"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    # After the grader: the E[r] components re-grade on whatever just scored.
    try:
        from backend.services import expected_return as ER
        r = ER.refit()
        out["expected_return"] = {f"h{h}": r["oos"][f"h{h}"].get("licensed")
                                  for h in _config.ER_HORIZONS}
    except Exception as exc:                                       # noqa: BLE001
        out["expected_return"] = f"FAILED {type(exc).__name__}: {exc}"[:200]
    return out


def u_learn(cycle_n: int, out: Path) -> dict:
    """One research unit per cycle -- but only when its INPUT has changed.

    The first version rotated unconditionally, and every `breadth_check` rebuilt
    a 7-million-row panel. Measured on the live 12-hour run at cycle 19: the
    worker held **7.8 GB** with 3.6 GB free on the machine. pandas does not hand
    that memory back to the OS, so a 144-cycle session would have grown until
    something was OOM-killed -- and the 5-minute pacing made it worse by fitting
    in MORE cycles, each loading another panel.

    Two fixes, and the second is the one that actually bounds it:

    1. the same bars fingerprint `u_rank` uses, so an unchanged panel is not
       re-analysed; and
    2. the heavy units run in a SUBPROCESS, because releasing a Python
       reference is not the same as returning the pages. A process that exits
       returns everything, which is the only bound that holds over 12 hours.
    """
    rota = ("survivorship_audit", "breadth_check", "idle")
    pick = rota[cycle_n % len(rota)]
    if pick == "idle":
        return {"unit": "idle", "why": "rota rest slot; the market loop owns the session"}

    fp = _bars_fingerprint()
    cache = out / f"learn_{pick}.json"
    if cache.exists():
        try:
            old_res = json.loads(cache.read_text(encoding="utf-8"))
            if old_res.get("bars_fingerprint") == fp:
                return {"unit": pick, "skipped": "bars unchanged since this unit last ran",
                        **{k: v for k, v in old_res.items()
                           if isinstance(v, (int, float, str, bool, type(None)))}}
        except (OSError, ValueError):
            pass

    res = _in_subprocess(pick)
    res["bars_fingerprint"] = fp
    cache.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return {"unit": pick, **{k: v for k, v in res.items()
                             if isinstance(v, (int, float, str, bool, type(None)))}}


#: The heavy units, run out-of-process. Releasing a reference is not returning
#: the pages; only an exiting process does that reliably.
_LEARN_SRC = {
    "survivorship_audit": (
        "from backend.services import xs_ranker as XR;"
        "bars=XR.load_bars(XR.survivorship_free_paths());"
        "out=XR.survivorship_audit(bars)"),
    # The funnel runs OUT OF PROCESS like the other heavy units: it loads
    # yfinance, holds a 5,339-name universe and ~1,500 price histories, and a
    # released Python reference is not a returned page. The 12-hour run of
    # 2026-09-23 reached 7,835 MB in-process for exactly this reason.
    "funnel": (
        "from backend.services import opportunity_funnel as OF;"
        "rc=OF.main([]);"
        "out={'rc':rc}"),
    "analyst": (
        "from scripts import pull_analyst_targets as PA;"
        "rc=PA.main([]);"
        "out={'rc':rc}"),
    "breadth_check": (
        "from backend.services import xs_ranker as XR;"
        "panel=XR.build_panel(XR.load_bars(XR.survivorship_free_paths()));"
        "oos,_=XR.walk_forward(panel,n_folds=3);"
        "out={f'k{k}':XR.top_k_backtest(oos,k=k).get('mean_net_rel_21d') "
        "for k in (20,100,300)}"),
    # u_forecast: the worker writes its own day receipt after every name.
    "forecast": (
        "from scripts import night_investigator_forecast as NIF;"
        "out=NIF.daily_forecast()"),
    # u_review: params arrive as one JSON argv (asof, live_prices, intraday_tag).
    "review": (
        "import sys;from backend.services import daily_review as DR;"
        "kw=json.loads(sys.argv[1]) if len(sys.argv)>1 else {};"
        "out=DR.run_daily(**kw)"),
}


def _in_subprocess(pick: str, timeout: float = 1800.0,
                   args: list[str] | None = None) -> dict:
    import subprocess
    code = ("import json,warnings;warnings.filterwarnings('ignore');"
            + _LEARN_SRC[pick]
            + ";print('<<<'+json.dumps(out,default=str)+'>>>')")
    r = subprocess.run([sys.executable, "-c", code, *(args or [])], cwd=str(REPO),
                       capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    txt = r.stdout or ""
    if "<<<" in txt and ">>>" in txt:
        return json.loads(txt.split("<<<", 1)[1].rsplit(">>>", 1)[0])
    return {"failed": f"rc {r.returncode}", "stderr": (r.stderr or "")[-300:]}


# ──────────────────────────────── the loop ──────────────────────────────────

#: Windows `SetThreadExecutionState` flags. A long job is allowed to ask the
#: OS not to idle-sleep underneath it, and should.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool) -> str:
    """Ask Windows not to IDLE-sleep while a session runs. Returns what happened.

    WHY THIS IS HERE, 2026-09-25
    -----------------------------
    The machine suspended mid-session. The process was not killed -- it was
    frozen, resumed 17 minutes later with a stale heartbeat, and its in-flight
    analyst pull came back on a socket that no longer existed.

    WHAT THIS CAN AND CANNOT DO, stated because the difference matters:

      CAN     stop the OS from idle-sleeping while the loop runs.
      CANNOT  stop a lid close, a deliberate Start-menu sleep, or a battery
              running out. Nothing an application can call stops those, and a
              guard that claims otherwise would be worse than none.

    On this machine `STANDBYIDLE` is already 0 on AC (never) and 600s on
    battery, so the battery case is the one this actually covers -- and the
    call is cheap, declared, and released on exit either way.

    Non-Windows is a no-op that says so rather than pretending to have worked.
    """
    if sys.platform != "win32":
        return f"not applicable on {sys.platform}"
    try:
        import ctypes
        flags = (_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED) if on else _ES_CONTINUOUS
        prev = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        if prev == 0:
            return "REFUSED by the OS (SetThreadExecutionState returned 0)"
        return ("idle-sleep suppressed (a lid close or a manual sleep still "
                "suspends this process)" if on else "released")
    except Exception as exc:                                       # noqa: BLE001
        return f"unavailable: {type(exc).__name__}: {exc}"


def run(session_id: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    st = SS.status()
    s = st.get("session") or {}
    if s.get("id") != session_id:
        logger.error("session mismatch: asked for %s, on disk %s", session_id, s.get("id"))
        return 3

    mode = s.get("mode", "observe")
    day = datetime.now().date().isoformat()
    out = _config.OPTIMUS_LEDGER_DIR / "pc_book" / day
    out.mkdir(parents=True, exist_ok=True)
    cycle_dir = SS.STATE_DIR / session_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    stopping = {"flag": False}

    def _sig(_s, _f):
        # A signal asks for the SAME safe stop the button does. It does not
        # unwind the stack: the current unit finishes, then the loop exits.
        stopping["flag"] = True
        logger.info("signal received — will stop at the next unit boundary")
    for sg in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sg, _sig)
        except (ValueError, OSError):
            pass

    n = int(s.get("cycle", 0))
    logger.info("sim %s: mode=%s resuming at cycle %d, planned_end %s",
                session_id, mode, n, s.get("planned_end"))
    logger.info("keep-awake: %s", keep_awake(True))

    try:
        while True:
            go, why = SS.should_continue(s)
            if stopping["flag"]:
                go, why = False, "signal"
            if not go:
                state = ("COMPLETED" if why == "requested duration elapsed"
                         else "STOPPED")
                keep_awake(False)
                SS.finish(state, why, {"final_cycle": n})
                logger.info("sim %s: %s (%s) after %d cycles", session_id, state, why, n)
                return 0

            n += 1
            t0 = time.time()
            c = Cycle(n, mode, out)
            SS.heartbeat(cycle=n, note=f"cycle {n} started")
            logger.info("cycle %d start", n)

            c.unit("reconcile", lambda: u_reconcile(out))
            if SS.stop_requested():
                logger.info("stop seen after reconcile; finishing the cycle short")
            else:
                # BEFORE the rank, not after: a ranking computed over last
                # month's candidate set is the exact failure of 2026-09-22.
                c.unit("funnel", lambda: u_funnel(out))
                # After the funnel, before the rank: both are inputs the
                # decision reads, and neither should be a day older than it
                # has to be.
                c.unit("analyst", lambda: u_analyst(out))
                c.unit("rank", lambda: u_rank(out))
                # After the rank, before the plan: every sim day forecasts
                # (h=1 and h=5, zero is red) and reviews every held name
                # pre-open with the 2-sigma patience rule. Both are once per
                # day behind their own day receipts, so later cycles skip.
                c.unit("forecast", lambda: u_forecast(out))
                c.unit("review", lambda: u_review(out))
                c.unit("plan", lambda: u_plan(out, mode))
                c.unit("grade", u_grade)
                c.unit("learn", lambda: u_learn(n, out))

            payload = c.payload(time.time() - t0)
            (cycle_dir / f"cycle_{n:04d}.json").write_text(
                json.dumps(payload, indent=1, default=str), encoding="utf-8")
            SS.record_cycle(n, payload)
            logger.info("cycle %d done in %.0fs (%d error(s))",
                        n, payload["elapsed_s"], len(c.errors))

            # Pace to MIN_CYCLE_PERIOD_S measured from the cycle's START, so a
            # slow cycle costs no extra wait and a fast one does not spin.
            # The stop flag is checked every second: a stop should feel
            # immediate even when the loop is idling.
            #
            # AND BEAT WHILE IDLING. `MIN_CYCLE_PERIOD_S` (300) is exactly
            # `sim_session.STALE_AFTER_S` (300), so a beat written only at the
            # cycle's start is precisely stale at the moment the next cycle
            # begins -- the session would flap into UNCLEAN once per cycle,
            # forever, while perfectly healthy. Idling is not dying, and the
            # heartbeat has to say so.
            spent = time.time() - t0
            idle = int(max(0.0, MIN_CYCLE_PERIOD_S - spent))
            for i in range(idle):
                if SS.stop_requested() or stopping["flag"]:
                    break
                if i and i % IDLE_BEAT_S == 0:
                    try:
                        SS.heartbeat(cycle=n, note=f"idle {i}s of {idle}s")
                    except Exception:                              # noqa: BLE001
                        logger.debug("idle heartbeat failed", exc_info=True)
                time.sleep(1)
    except KeyboardInterrupt:
        keep_awake(False)
        SS.finish("STOPPED", "KeyboardInterrupt", {"final_cycle": n})
        return 130
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("sim loop crashed")
        SS.finish("UNCLEAN", f"{type(exc).__name__}: {exc}"[:300], {"final_cycle": n})
        return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    a = ap.parse_args(argv)
    return run(a.session)


if __name__ == "__main__":
    raise SystemExit(main())
