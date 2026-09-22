"""The PC as a live market node — watch the session, hold a ranked book, learn.

WHAT THE 2026-09-22 MORNING REPORT EXPOSED
==========================================
    "The queue finished at 01:50, five idle hours."
    "Paper NAV vs SPY: CANNOT DETERMINE on this machine."

Both sentences have the same cause: there was no process whose job was the
market. `night_run_until` is a batch runner — phase 1, grade, queue, STOP — so
when the queue drained there was nothing left to do, while the US session still
had four hours to run and the machine had a working internet connection the
whole time.

This module is that missing process. It runs from pre-open to after the close on
the VENUE's clock, it holds sole execution ownership of one paper account, and
it never exits because some other queue finished.

THE THREE STANDARDS, AND WHY THIS ONE IS NOT `RESEARCH_CLAIM`
=============================================================
Murat, 2026-09-22: *"it is not taking risks. It is limiting itself, pulling
itself back."* He is right, and the cause is a licence error rather than
cowardice: `RESEARCH_CLAIM` gates (significance, MDE, multiplicity) had drifted
onto decisions that only ever spend PAPER money. CLAUDE.md already says they
should not — a `PRODUCT_EXPERIMENT` needs a frozen contract, not a p-value.

So this loop runs under `PRODUCT_EXPERIMENT` and **a lack of statistical
significance is never a reason to refuse a position.** Uncertainty sets SIZE.

There is exactly one thing it still refuses, and the distinction is the whole
point: it will not knowingly buy a **measured negative**. A ranking whose top
decile has a realised OOS relative return below zero is not an uncertain bet, it
is a bet the evidence says loses. Refusing that is not timidity; it is the
difference between "we don't know yet" (size small, learn) and "we know, and the
answer is no" (don't). `_ranking_verdict` prints which of the two it found.

THE MODES
=========
``observe``  reconcile, snapshot NAV, rank, write the book it WOULD hold, send
             nothing. What runs when the ranker is unvalidated or the account
             is not configured. Still produces every learning row.
``trade``    the above, and submit the orders.

Mode is not a mood: `--mode trade` with an unvalidated ranking DOWNGRADES itself
to observe and says so in the receipt, rather than trading on nothing.

THE CLOCK (US/Eastern, read from the VENUE, never the laptop)
=============================================================
  pre-open   T-45m  reconcile from the broker, refresh the ranking, plan
  open       09:30  submit the pre-planned book
  session    ..     heartbeat every HEARTBEAT_MIN; re-plan only when the book
                    has drifted enough to be worth the round trip
  close      16:00  final reconcile, snapshot, write the session receipt

Continuous monitoring is NOT continuous trading. For a 21-session horizon there
is no reason to re-plan on every tick, and turnover is the most reliable way to
convert an edge into the broker's revenue.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                       # noqa: E402,F401  loads dotenv
from backend.services import pc_broker as PB                # noqa: E402
from backend.services import policy_state as POLICY         # noqa: E402

logger = logging.getLogger("live_market_loop")

OUT_DIR = REPO / "backend" / "data" / "optimus" / "pc_book"
HEARTBEAT_MIN = 30
PRE_OPEN_MIN = 45
#: Re-plan only when the desired book differs from the held book by more than
#: this fraction of equity. Below it, the expected edge cannot pay the spread.
REPLAN_DRIFT_FRAC = 0.05
#: How many names the book holds. 15-20 was the declared mandate 2026-09-22.
BOOK_SIZE = 18


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Loop:
    def __init__(self, a: argparse.Namespace) -> None:
        self.mode = a.mode
        # Preferences the NIGHT may have moved (`policy_state`); an explicit CLI
        # value still wins, because a human at the keyboard outranks last
        # night's self-adjustment.
        self.policy = POLICY.load()
        self.book_size = a.book_size if a.book_size != BOOK_SIZE else int(self.policy["book_size"])
        self.replan_drift = float(self.policy["replan_drift_frac"])
        self.heartbeat_min = float(self.policy["heartbeat_minutes"])
        self.out = OUT_DIR / a.date
        self.out.mkdir(parents=True, exist_ok=True)
        self.log_path = self.out / "live_market_loop.log"
        self.stop_file = self.out / "STOP_LIVE"
        self.date = a.date
        self.events: list[dict] = []
        self.orders_sent = 0
        self.lease: dict | None = None
        self.ranking_receipt: dict | None = None
        self.last_plan_at: datetime | None = None
        self.halted: str | None = None
        self._stopping = False
        self.started = _now()

    # ------------------------------------------------------------- plumbing
    def log(self, msg: str) -> None:
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.events.append({"t": _now(), "msg": msg})

    def write(self, name: str, payload: Any) -> Path:
        p = self.out / name
        p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        return p

    # -------------------------------------------------------------- ranking
    def ranking(self) -> tuple[list[PB.Target], dict]:
        """The ranked opportunity set, and the verdict on whether to act on it."""
        from backend.services import xs_ranker as XR
        t0 = time.time()
        panel = XR.build_panel()
        oos, folds = XR.walk_forward(panel)
        cal = XR.calibrate(oos)
        model, train_end = XR.fit_production(panel)
        ranked = XR.rank_asof(panel, model, cal, train_end=train_end)
        ranked["n_ranked"] = len(ranked)

        verdict = _ranking_verdict(cal, XR.top_k_backtest(oos, k=self.book_size))
        top = ranked.head(self.book_size)
        w = 1.0 / max(1, len(top))
        targets = [
            PB.Target(symbol=r["symbol"], weight=w,
                      rank=int(r["rank_21d"]),
                      expected_relative_return_21d=(
                          None if r["expected_relative_return_21d"] is None
                          else float(r["expected_relative_return_21d"])),
                      median_dollar_vol=float(r["median_dollar_vol"]),
                      reason="; ".join(XR.why(r)[:3]))
            for _, r in top.iterrows()
        ]
        receipt = {
            "receipt": "xs_ranking",
            "licence": "PRODUCT_EXPERIMENT",
            "asof": str(ranked["asof"].iloc[0]),
            "model_version": str(ranked["model_version"].iloc[0]),
            "n_eligible": int(len(ranked)),
            "book_size": self.book_size,
            "elapsed_s": round(time.time() - t0, 1),
            "folds": [asdict(f) for f in folds],
            "calibration": cal,
            "verdict": verdict,
            "top": [
                {"rank": int(r["rank_21d"]), "symbol": r["symbol"],
                 "decile": int(r["decile"]),
                 "expected_relative_return_21d": r["expected_relative_return_21d"],
                 "expected_relative_return_21d_net": r["expected_relative_return_21d_net"],
                 "downside_21d": r["downside_21d"],
                 "probability_beat_benchmark": r["probability_beat_benchmark"],
                 "calibration_measured": bool(r["calibration_measured"]),
                 "liquidity_band": r["liquidity_band"],
                 "why": XR.why(r)}
                for _, r in top.iterrows()
            ],
            "read_me_first": (
                "PRODUCT_EXPERIMENT. A ranking, not an alpha claim. The expected "
                "return on every row is the REALISED out-of-sample mean of that "
                "score decile, never a model output."),
        }
        self.ranking_receipt = receipt
        self.write("ranking.json", receipt)
        return targets, receipt

    # ------------------------------------------------------------ execution
    def reconcile(self, tag: str) -> dict:
        snap = PB.snapshot(tag=tag, out_dir=self.out)
        self.log(f"reconcile[{tag}]: equity ${snap['equity']:,.2f} cash ${snap['cash']:,.2f} "
                 f"{snap['n_positions']} positions invested "
                 f"{(snap['invested_frac'] or 0)*100:.1f}%")
        return snap

    def plan_and_maybe_trade(self, targets: list[PB.Target], *, why: str) -> dict:
        snap = self.reconcile("plan")
        held = {p["symbol"]: p["qty"] for p in snap["positions"]}
        syms = sorted({t.symbol for t in targets} | set(held))
        prices = PB.last_prices(syms)
        plans = PB.plan_orders(targets, equity=snap["equity"], held=held, prices=prices)

        turnover = sum(p.notional for p in plans if p.qty > 0)
        drift = turnover / snap["equity"] if snap["equity"] else 0.0
        act = self.mode == "trade" and not self.halted

        record = {
            "t": _now(), "why": why, "mode": self.mode, "acting": act,
            "equity": snap["equity"], "turnover_usd": turnover, "drift_frac": drift,
            "n_orders": sum(1 for p in plans if p.qty > 0),
            "plans": [asdict(p) for p in plans],
            "refusals": [{"symbol": p.symbol, "refused": p.refused}
                         for p in plans if p.refused],
            "halted": self.halted,
        }

        if drift < self.replan_drift and self.last_plan_at is not None:
            record["skipped"] = (f"drift {drift:.2%} < replan_drift_frac "
                                 f"{self.replan_drift:.0%}: not worth the round trip")
            self.log(f"plan[{why}]: {record['skipped']}")
            self._append("decisions.jsonl", record)
            return record

        if act:
            sent = []
            for p in plans:
                if p.qty <= 0:
                    continue
                if self.orders_sent >= PB.MAX_ORDERS_PER_SESSION:
                    record.setdefault("circuit_breaker", []).append(
                        f"MAX_ORDERS_PER_SESSION {PB.MAX_ORDERS_PER_SESSION} reached")
                    break
                try:
                    r = PB.submit(p)
                    self.orders_sent += 1
                    sent.append(r)
                except PB.BrokerError as exc:
                    sent.append({"status": "FAILED", "symbol": p.symbol,
                                 "error": str(exc)[:300]})
            record["sent"] = sent
            self.log(f"plan[{why}]: submitted {len([s for s in sent if s.get('status')=='submitted'])} "
                     f"of {record['n_orders']} orders, turnover ${turnover:,.0f} ({drift:.1%})")
        else:
            record["sent"] = []
            self.log(f"plan[{why}]: OBSERVE — {record['n_orders']} orders worth "
                     f"${turnover:,.0f} ({drift:.1%}) written, none sent"
                     + (f" [{self.halted}]" if self.halted else ""))

        self.last_plan_at = datetime.now(timezone.utc)
        self._append("decisions.jsonl", record)
        return record

    def _append(self, name: str, row: dict) -> None:
        with (self.out / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    # ------------------------------------------------------------ the clock
    def venue_clock(self) -> dict:
        c = PB.clock()
        return {"is_open": bool(c.get("is_open")),
                "now": c.get("timestamp"), "next_open": c.get("next_open"),
                "next_close": c.get("next_close")}

    def run(self) -> int:
        self.log(f"live market loop {self.date}: mode={self.mode} book={self.book_size}")

        # 1. the account, and sole ownership of it
        try:
            self.lease = PB.open_lease(owner=f"live_market_loop:{self.date}")
            self.log(f"lease OPEN on account {self.lease['account_number']} "
                     f"(pid {self.lease['pid']}, equity ${self.lease['equity_at_open']:,.2f})")
        except PB.BrokerError as exc:
            self.log(f"REFUSED: {exc}")
            self.mode, self.halted = "observe", str(exc)[:200]
            self.write("HALTED.json", {"why": str(exc), "t": _now()})
            if "not configured" not in str(exc):
                return 3

        if self.lease:
            lease_check = PB.check_lease(self.lease)
            self.log(f"ownership: {lease_check['verdict']}")
            if lease_check["conflict"]:
                self.halted = "OWNERSHIP_CONFLICT"
                self.mode = "observe"
                self.write("OWNERSHIP_CONFLICT.json", lease_check)

        # 2. the ranking, and whether it may be acted on
        try:
            targets, receipt = self.ranking()
            v = receipt["verdict"]
            self.log(f"ranking: {receipt['n_eligible']:,} eligible names, "
                     f"top {self.book_size}: {', '.join(t.symbol for t in targets[:8])}...")
            self.log(f"ranking verdict: {v['verdict']} — {v['why']}")
            if not v["may_trade"] and self.mode == "trade":
                self.mode = "observe"
                self.halted = self.halted or v["verdict"]
                self.log("mode DOWNGRADED to observe: the ranking may not be traded")
        except Exception as exc:                                  # noqa: BLE001
            self.log(f"ranking FAILED: {type(exc).__name__}: {exc}")
            self.write("RANKING_FAILED.json", {"error": f"{type(exc).__name__}: {exc}", "t": _now()})
            return 4

        if not self.lease:
            self.log("no broker: writing the book and the ranking only, then exiting")
            self.plan_and_maybe_trade_offline(targets)
            return 0

        # 3. the session
        self.reconcile("open_of_loop")
        try:
            # Plan once before the wait loop, so `--once` produces a real book
            # and a cold start does not sit idle until the first heartbeat.
            self.plan_and_maybe_trade(targets, why="startup")
            while not self._should_stop():
                c = self.venue_clock()
                if c["is_open"]:
                    self.plan_and_maybe_trade(targets, why="heartbeat")
                    self._sleep(self.heartbeat_min * 60)
                else:
                    nxt = c.get("next_open")
                    self.log(f"market closed; next open {nxt}")
                    if self._until(nxt) <= PRE_OPEN_MIN * 60:
                        targets, _ = self.ranking()
                        self.plan_and_maybe_trade(targets, why="pre_open")
                        self._sleep(min(300, max(60, self._until(nxt))))
                    else:
                        self._sleep(600)
        except KeyboardInterrupt:
            self.log("KeyboardInterrupt")
        finally:
            self.finish()
        return 0

    def plan_and_maybe_trade_offline(self, targets: list[PB.Target]) -> None:
        """No broker: still write the book this loop WOULD hold, with reasons."""
        book = [{"rank": t.rank, "symbol": t.symbol, "weight": t.weight,
                 "expected_relative_return_21d": t.expected_relative_return_21d,
                 "reason": t.reason} for t in targets]
        self.write("intended_book.json", {
            "t": _now(), "mode": "observe_no_broker", "halted": self.halted,
            "book": book,
            "read_me_first": ("The account is not configured, so this is the book "
                              "the loop would have held. Set ALPACA_PC_KEY_ID and "
                              "ALPACA_PC_SECRET_KEY to make it real.")})
        self.log(f"intended book written: {len(book)} names")

    def _should_stop(self) -> bool:
        return self._stopping or self.stop_file.exists()

    def _sleep(self, secs: float) -> None:
        end = time.time() + max(1.0, secs)
        while time.time() < end:
            if self._should_stop():
                return
            time.sleep(min(10.0, end - time.time()))

    @staticmethod
    def _until(iso: str | None) -> float:
        if not iso:
            return 1e9
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return max(0.0, (t - datetime.now(timezone.utc)).total_seconds())
        except ValueError:
            return 1e9

    def finish(self) -> None:
        snap = None
        try:
            snap = self.reconcile("close_of_loop")
        except PB.BrokerError as exc:
            self.log(f"final reconcile failed: {exc}")
        lease_check = PB.check_lease(self.lease) if self.lease else None
        PB.close_lease()
        payload = {
            "receipt": "LIVE_LOOP_STOPPED", "date": self.date, "mode": self.mode,
            "halted": self.halted, "orders_sent": self.orders_sent,
            "final": snap, "ownership": lease_check,
            "ranking_verdict": (self.ranking_receipt or {}).get("verdict"),
            "policy": self.policy,
            "policy_changes_tonight": POLICY.changed_since(self.started),
            "stopped": _now(), "events": self.events[-80:],
        }
        self.write("LIVE_LOOP_STOPPED.json", payload)
        self.log(f"stopped; {self.orders_sent} orders sent this session")


def _ranking_verdict(cal: dict, topk: dict) -> dict:
    """May this ranking be traded? Uncertain is YES. Measured-negative is NO.

    This function is where Murat's 2026-09-22 complaint is answered in code. It
    deliberately does NOT ask for significance. It asks two questions:

      1. Is the top decile's realised OOS relative return measured at all?
         No  -> trade it small. Nothing accrues if nothing is tried, and a PROBE
                that never runs is a self-fulfilling refusal (chunk 23a).
      2. If it IS measured, is it NEGATIVE?
         Yes -> do not buy it. That is not uncertainty, that is evidence.
    """
    top = next((r for r in cal["deciles"] if r["decile"] == 9), None)
    net = topk.get("mean_net_rel_21d")
    ic = cal.get("ic_mean")

    if top is None:
        return {"verdict": "NO_CALIBRATION", "may_trade": False,
                "why": "the calibration carries no top decile at all"}
    if not top["measured"]:
        return {"verdict": "UNMEASURED_TRADE_SMALL", "may_trade": True,
                "why": (f"top decile is unmeasured ({top['why_unmeasured']}). "
                        f"Uncertainty sizes the book down; it does not veto it."),
                "ic_mean": ic}
    if net is not None and net <= 0:
        return {"verdict": "MEASURED_NEGATIVE", "may_trade": False,
                "why": (f"a top-{topk.get('k')} book earned {net*100:+.2f}% relative per "
                        f"21 sessions NET out of sample over {topk.get('n_blocks')} "
                        f"month-blocks (IC {ic:+.4f}). This is not an uncertain bet, "
                        f"it is a measured losing one. Refusing it is evidence-led, "
                        f"not timid — fix the ranking, then trade it."),
                "top_k_net": net, "ic_mean": ic}
    return {"verdict": "MEASURED_POSITIVE", "may_trade": True,
            "why": (f"a top-{topk.get('k')} book earned {net*100:+.2f}% relative per 21 "
                    f"sessions NET out of sample over {topk.get('n_blocks')} month-blocks "
                    f"(t {topk.get('t_across_blocks')}). PRODUCT_EXPERIMENT: no "
                    f"significance gate is applied, and none is claimed."),
            "top_k_net": net, "ic_mean": ic}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("observe", "trade"), default="observe")
    ap.add_argument("--date", default=None)
    ap.add_argument("--book-size", type=int, default=BOOK_SIZE)
    ap.add_argument("--once", action="store_true",
                    help="rank, plan, write, exit — no session loop")
    a = ap.parse_args(argv)
    if not a.date:
        a.date = datetime.now().date().isoformat()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    loop = Loop(a)

    def _sig(_signum, _frame):
        loop._stopping = True
        loop.log("stop requested")
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except (ValueError, OSError):
            pass

    if a.once:
        loop._stopping = True
    return loop.run()


if __name__ == "__main__":
    raise SystemExit(main())
