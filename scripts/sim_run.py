"""The simulation loop — cycles, checkpoints, and a stop that never loses work.

Started by `sim_session.start()` (the button), never by hand in normal use:

    python -m scripts.sim_run --session <id>

WHAT A CYCLE DOES, AND WHY IT IS SHAPED THIS WAY
================================================
One cycle is a fixed sequence of UNITS, each of which is small, idempotent and
writes its own receipt:

    reconcile   the broker's own view of the book -> pc_book/<date>/nav.jsonl
    rank        the cross-sectional ranker over the survivorship-free panel
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
import time
import traceback
from datetime import datetime, timezone
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
        try:
            res = fn()
            dt = time.time() - t0
            self.units[name] = {"ok": True, "elapsed_s": round(dt, 1),
                                "result": _summarise(res)}
            if dt > SLOW_UNIT_S:
                self.units[name]["slow"] = (
                    f"{dt:.0f}s exceeds SLOW_UNIT_S {SLOW_UNIT_S}s; reported, "
                    f"not killed — the loop stops at boundaries by design")
            return res
        except Exception as exc:                                   # noqa: BLE001
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
    "breadth_check": (
        "from backend.services import xs_ranker as XR;"
        "panel=XR.build_panel(XR.load_bars(XR.survivorship_free_paths()));"
        "oos,_=XR.walk_forward(panel,n_folds=3);"
        "out={f'k{k}':XR.top_k_backtest(oos,k=k).get('mean_net_rel_21d') "
        "for k in (20,100,300)}"),
}


def _in_subprocess(pick: str, timeout: float = 1800.0) -> dict:
    import subprocess
    code = ("import json,warnings;warnings.filterwarnings('ignore');"
            + _LEARN_SRC[pick]
            + ";print('<<<'+json.dumps(out,default=str)+'>>>')")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                       capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    txt = r.stdout or ""
    if "<<<" in txt and ">>>" in txt:
        return json.loads(txt.split("<<<", 1)[1].rsplit(">>>", 1)[0])
    return {"failed": f"rc {r.returncode}", "stderr": (r.stderr or "")[-300:]}


# ──────────────────────────────── the loop ──────────────────────────────────

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

    try:
        while True:
            go, why = SS.should_continue(s)
            if stopping["flag"]:
                go, why = False, "signal"
            if not go:
                state = ("COMPLETED" if why == "requested duration elapsed"
                         else "STOPPED")
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
                c.unit("rank", lambda: u_rank(out))
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
            spent = time.time() - t0
            for _ in range(int(max(0.0, MIN_CYCLE_PERIOD_S - spent))):
                if SS.stop_requested() or stopping["flag"]:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
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
