"""The simulation loop — cycles, checkpoints, and a stop that never loses work.

Started by `sim_session.start()` (the button), never by hand in normal use:

    python -m scripts.sim_run --session <id>

WHAT A CYCLE DOES, AND WHY IT IS SHAPED THIS WAY
================================================
One cycle is a fixed sequence of UNITS, each of which is small, idempotent and
writes its own receipt:

    reconcile   the broker's own view of the book -> pc_book/<date>/nav.jsonl
    rank        the cross-sectional ranker over the survivorship-free panel
    plan        the book it would hold, and (in trade mode) the orders
    grade       whatever reality has resolved since the last cycle
    learn       ONE queued research unit

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


def u_rank(out: Path) -> dict:
    from backend.services import xs_ranker as XR
    panel = XR.build_panel(XR.load_bars(XR.survivorship_free_paths()))
    oos, folds = XR.walk_forward(panel)
    cal = XR.calibrate(oos)
    model, train_end = XR.fit_production(panel)
    ranked = XR.rank_asof(panel, model, cal, train_end=train_end)
    topk = XR.top_k_backtest(oos, k=20)
    payload = {
        "receipt": "sim_ranking", "at": _now(),
        "asof": str(ranked["asof"].iloc[0]),
        "n_eligible": int(len(ranked)),
        "model_version": str(ranked["model_version"].iloc[0]),
        "ic_mean": cal.get("ic_mean"), "ic_t": cal.get("ic_t"),
        "top20_net_rel_21d": topk.get("mean_net_rel_21d"),
        "top": [{"rank": int(r["rank_21d"]), "symbol": r["symbol"],
                 "decile": int(r["decile"]),
                 "expected_relative_return_21d_net": r["expected_relative_return_21d_net"],
                 "calibration_measured": bool(r["calibration_measured"])}
                for _, r in ranked.head(25).iterrows()],
    }
    (out / "ranking.json").write_text(json.dumps(payload, indent=1, default=str),
                                      encoding="utf-8")
    return {"n_eligible": payload["n_eligible"], "ic_mean": payload["ic_mean"],
            "top20_net_rel_21d": payload["top20_net_rel_21d"],
            "top1": payload["top"][0]["symbol"] if payload["top"] else None}


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
    """One research unit per cycle, rotating, so a long session covers ground."""
    from backend.services import xs_ranker as XR
    rota = ("survivorship_audit", "breadth_check", "idle")
    pick = rota[cycle_n % len(rota)]
    if pick == "survivorship_audit":
        bars = XR.load_bars(XR.survivorship_free_paths())
        return {"unit": pick, **XR.survivorship_audit(bars)}
    if pick == "breadth_check":
        panel = XR.build_panel(XR.load_bars(XR.survivorship_free_paths()))
        oos, _ = XR.walk_forward(panel, n_folds=3)
        return {"unit": pick,
                **{f"k{k}": XR.top_k_backtest(oos, k=k).get("mean_net_rel_21d")
                   for k in (20, 100, 300)}}
    return {"unit": "idle", "why": "rota rest slot; the market loop owns the session"}


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
                c.unit("grade", u_grade)
                c.unit("learn", lambda: u_learn(n, out))

            payload = c.payload(time.time() - t0)
            (cycle_dir / f"cycle_{n:04d}.json").write_text(
                json.dumps(payload, indent=1, default=str), encoding="utf-8")
            SS.record_cycle(n, payload)
            logger.info("cycle %d done in %.0fs (%d error(s))",
                        n, payload["elapsed_s"], len(c.errors))

            # a short breather so a fast cycle cannot spin the machine
            for _ in range(6):
                if SS.stop_requested() or stopping["flag"]:
                    break
                time.sleep(5)
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
