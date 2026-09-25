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


def u_plan(out: Path, mode: str) -> dict:
    """Ranking -> a book. THE UNIT THAT DID NOT EXIST.

    The module docstring claimed a cycle was
    `reconcile -> rank -> plan -> grade -> learn` and the loop called four
    units. There was no code path from a ranking to a decision at all, so the
    2026-09-22 session's 144 cycles would have produced zero orders **even with
    a positive ranking**. Two independent causes of the same nothing, and only
    one of them was reported. Found by Murat's external review, 2026-09-23.

    What it does every cycle, in both modes:

    * reads the ranking on disk and the broker's actual holdings;
    * sizes an equal-weight book of the top `BOOK_SIZE` names, through
      `pc_broker.plan_orders` -- so the mandate limits (no leverage, no shorts,
      12% per name, 2% of ADV, $250 minimum) apply identically whether or not
      the orders are sent;
    * writes `intended_book.json` and appends every plan to `decisions.jsonl`.

    In `observe` it stops there. In `paper_profit` it submits, but only if the
    ranking's own verdict permits: a MEASURED_NEGATIVE ranking is refused here
    as well as in the live loop, because "we measured it and it loses" is not
    uncertainty and spending paper capital on it would teach the learner that
    losing is normal.
    """
    from backend.services import pc_broker as PB
    from scripts.live_market_loop import _ranking_verdict

    rank_path = out / "ranking.json"
    if not rank_path.exists():
        return {"planned": False, "why": "no ranking on disk yet"}
    r = json.loads(rank_path.read_text(encoding="utf-8"))
    top = (r.get("top") or [])[:BOOK_SIZE]
    if not top:
        return {"planned": False, "why": "the ranking carries no names"}

    snap = PB.snapshot(tag="plan", out_dir=out)
    held = {p["symbol"]: p["qty"] for p in snap["positions"]}
    w = 1.0 / len(top)
    targets = [PB.Target(symbol=x["symbol"], weight=w, rank=x.get("rank"),
                         expected_relative_return_21d=x.get("expected_relative_return_21d_net"),
                         median_dollar_vol=None,
                         reason=f"rank {x.get('rank')} decile {x.get('decile')}")
               for x in top]
    prices = PB.last_prices([t.symbol for t in targets] + list(held))
    plans = PB.plan_orders(targets, equity=snap["equity"], held=held, prices=prices)

    # The same gate the live loop applies, read from the ranking's own receipt.
    net = r.get("top20_net_rel_21d")
    verdict = ("MEASURED_NEGATIVE" if (net is not None and net <= 0)
               else "MEASURED_POSITIVE" if net is not None
               else "UNMEASURED_TRADE_SMALL")
    may_trade = verdict != "MEASURED_NEGATIVE"
    acting = (mode == "paper_profit") and may_trade

    record = {"t": _now(), "mode": mode, "verdict": verdict, "acting": acting,
              "equity": snap["equity"], "n_targets": len(targets),
              "n_orders": sum(1 for p in plans if p.qty > 0),
              "turnover_usd": sum(p.notional for p in plans if p.qty > 0),
              "refusals": [{"symbol": p.symbol, "refused": p.refused}
                           for p in plans if p.refused][:10],
              "book": [{"rank": t.rank, "symbol": t.symbol, "weight": t.weight,
                        "expected_relative_return_21d": t.expected_relative_return_21d}
                       for t in targets]}

    if acting:
        sent = []
        for p in plans:
            if p.qty <= 0:
                continue
            try:
                sent.append(PB.submit(p))
            except PB.BrokerError as exc:
                sent.append({"status": "FAILED", "symbol": p.symbol,
                             "error": str(exc)[:200]})
        record["sent"] = sent
    else:
        record["sent"] = []
        record["why_not"] = (
            f"mode={mode}" if mode != "paper_profit"
            else f"ranking verdict {verdict}: refusing to buy a measured negative")

    (out / "intended_book.json").write_text(
        json.dumps(record, indent=1, default=str), encoding="utf-8")
    with (out / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")

    return {"planned": True, "verdict": verdict, "acting": acting,
            "n_orders": record["n_orders"], "turnover_usd": record["turnover_usd"],
            "top1": targets[0].symbol}


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
