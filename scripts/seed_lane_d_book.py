"""T4 — lane D's day-trading book (D1), created through the route.

MURAT, 2026-09-12, VERBATIM (roadmap §10b)
==========================================
> "If we can make 1% return every day in a day-trading part of the project with
> our live data and analysis, relying on future outcomes and dates, that would
> be a winner. Dedicate a paper account; check for signals in the market,
> monitor them, find the small details, make the engine and NN train on it. I
> will leave the PC open on Monday nights to let it test on the device."

That sentence is the book's `origin_text`. The arithmetic that answers it is on
the row, not in a slide: 1%/day compounds to **+1,127%/yr**, above Medallion's
gross. At the TAQ effective spread on liquid names (1.08 bp one-way) a 2x-daily
turnover book pays ~4.3 bp/day and needs ~1.04%/day gross; at the retail 25
bp/side assumption the same book pays **100 bp/day — the entire target** — and
needs 2.0%/day gross. Which regime applies is decided by fill quality on Alpaca
paper, and **that has not been measured**. It is D2's receipt, and until it
exists this book's cost model is labelled `retail_paper_pending_D2` on every
row so no number from it can be read as net-of-anything-measured.

WHAT IS GENUINELY UNTESTED, AND WHY THE SIGNAL IS A PLACEHOLDER
===============================================================
`FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` already measured the overnight /
intraday split at daily resolution (t 8.71, n 3,019 days) and buy-and-hold beat
overnight-only at zero cost; the daily reaction lane is closed in every form
(RW2). What nobody has tested is **the first hour after a natively-stamped
headline, by typed event**. L2's typed-event vocabulary is not built and the
roadmap says do not wait for it, so the signal here is the observable half of
that statement: `native_stamped_headline_in_first_hour` — a headline whose
stamp is the venue's own (`pit_grade: native_stamp`) and whose `first_seen_utc`
falls inside 09:30-10:30 ET. When L2 lands, the TYPE is added to the gate; the
window and the PIT grade do not move, and that is an amendment to the input,
not a new book.

THE BOOK IS MARKED AT DAILY CLOSE AND SAYS SO
=============================================
Minute bars do not exist on this machine. `book_cadence` marks a `30m` book
from the daily close with `granularity="daily_close"` and
`intraday_bars_available=False` on every row. A 30-minute book graded from
daily closes is not a 30-minute book's result, and the row is what stops
someone reading it as one.

    python -m scripts.seed_lane_d_book
    python -m scripts.seed_lane_d_book --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.strategy.contract import (Benchmark, Construction, CostModel,
                                       HoldRule, Licence, LossBudget, Objective,
                                       Signal, Sizing, Strategy, Universe,
                                       loss_budget_worst_case)

logger = logging.getLogger("seed_lane_d_book")

LANE = "D"
FLOOR_USD = 3_000_000.0
MIN_PRICE = 5.0

#: The interim cost ruler, named so it cannot be read as measured. D2's fill
#: receipt replaces it; chunk 5c's TAQ curve replaces that.
COST_CURVE = "retail_paper_pending_D2"

#: Murat's sentence, verbatim from roadmap §10b. It is the `origin_text`, and
#: it is quoted rather than paraphrased because a book's origin is a fact about
#: a human, not a summary of one.
ORIGIN_TEXT = (
    "Murat, 2026-09-12: \"If we can make 1% return every day in a day-trading "
    "part of the project with our live data and analysis, relying on future "
    "outcomes and dates, that would be a winner. Dedicate a paper account; "
    "check for signals in the market, monitor them, find the small details, "
    "make the engine and NN train on it. I will leave the PC open on Monday "
    "nights to let it test on the device.\" "
    "| The declared target is 1%/day and the result is MEASURED, not asserted: "
    "1%/day compounds to +1,127%/yr, above Medallion's gross. At TAQ spreads "
    "(1.08bp one-way) a 2x-turnover book needs ~1.04%/day gross; at the retail "
    "25bp/side assumption it needs 2.0%/day because turnover alone costs the "
    "whole 1%. Which regime applies is D2's unwritten fill receipt. "
    "The population prior is in the contract: <1% of Taiwanese day traders "
    "profitable net (Barber-Lee-Liu-Odean), 97% of persisting Brazilian "
    "futures day traders lose (Chague et al. 2020)."
)


def receipt_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "lane_d" / "seed_receipt.json"


def lane_d_book() -> Strategy:
    return Strategy(
        strategy_id="first_hour_event_intraday_v1",
        title=("First hour after a natively-stamped headline, k=12 EW, flat at "
               "the close (lane D, D1)"),
        universe=Universe(
            name="lane_d_liquid_universe",
            source=("local daily bars above the dollar-volume floor; the "
                    "headline gate reads news_corpus/alpaca_benzinga_news"),
            floor_dollar_vol_usd=FLOOR_USD, min_price_usd=MIN_PRICE,
            max_names=None,
            note=("the TAQ effective-spread panel covers 4,224 name-days and is "
                  "what chunk 5c's curve is calibrated on; this floor is the "
                  "repo's declared TRADABLE_DOLLAR_VOL and is not that panel"),
        ),
        signal=Signal(
            name="native_stamped_headline_in_first_hour",
            column="first_hour_native_headlines", direction=1,
            source=("news_corpus/alpaca_benzinga_news: pit_grade == "
                    "native_stamp AND first_seen_utc in 09:30-10:30 ET"),
            warmup_periods=0,
            note=("PLACEHOLDER for L2's typed event, which is not built (gate "
                  "order N-C -> N-D -> N-F -> L2). This is the OBSERVABLE half "
                  "of the same statement; when L2 lands the TYPE joins the gate "
                  "and the window and the PIT grade do not move. "
                  "`first_seen_utc` is when WE could first have seen it, which "
                  "is what an intraday book may use; `published_utc` is the "
                  "venue's claim about itself. On a BACKFILLED corpus day "
                  "`first_seen_utc` is the pull time, so the gate is empty by "
                  "construction and the book abstains — which the receipt says."),
        ),
        construction=Construction(
            rule="top_k", k=12, weighting="ew", max_single_name=0.0834,
            gross_cap=1.0,
            note=("k=12 EW. `max_single_name` is 1/12 rounded up, so the "
                  "binding constraint is gross_cap/k and the worst-case print "
                  "below is not quoting a gross the book cannot reach."),
        ),
        hold=HoldRule(
            horizon_periods=1, min_hold_periods=0, scheduled_review_periods=1,
            stop_loss=-0.02, roi_ladder={},
            exit_priority=("THESIS_INVALIDATED", "EXPLICIT_EVENT_STRATEGY_EXIT",
                           "STOP", "ROI_LADDER", "TRAILING_STOP", "DEADLINE",
                           "REBALANCE"),
            note=("FORCED FLAT AT THE CLOSE. The hold rule is `session_end`, "
                  "carried in engine_params because `HoldRule` counts periods "
                  "and a session boundary is not a period count. "
                  "`horizon_periods=1` is one 30-minute bar; the session-end "
                  "flat is what actually ends every position."),
        ),
        sizing=Sizing(
            rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0,
            params={"daily_loss_limit_pct": 0.02,
                    "daily_loss_limit_arithmetic":
                        "12 names x 8.33% notional x 2% stop = 2.00% of equity "
                        "per session, gross 1.00x"},
            note=("the daily loss limit is the worst case PRINTED, not a "
                  "sentiment: session protocol rule 4 asks for n x notional% x "
                  "stop% and for the gross line beside it, because on 28 Aug a "
                  "widened stop on uncapped gross turned -9% into -24%"),
        ),
        costs=CostModel(
            transaction_cost_bps=25.0, slippage_bps=0.0,
            note=(f"{COST_CURVE}: a FLAT 25 bps per side, the retail assumption, "
                  "chosen as the harsher of the two regimes because D2's fill "
                  "receipt does not exist. At 2x daily turnover this is 100 "
                  "bp/day — the entire 1%/day target — so a book that clears "
                  "the target under THIS curve has cleared it under the "
                  "pessimistic one. The optimistic TAQ regime (1.08 bp one-way) "
                  "is reported beside it and is never the headline."),
        ),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=False,
                            is_own_universe_average=False),
        objective=Objective(
            name="terminal_wealth_at_drawdown_budget",
            periods_per_year=252, drawdown_budget=-0.20,
            utility="risk_adjusted",
            note=("periods_per_year RECALIBRATED to 252: the contract's default "
                  "of 12 assumes a monthly book and would understate this "
                  "book's annualised everything by a factor of 21"),
        ),
        loss_budget=LossBudget(
            positions_judged=60, expected_losers=33,
            note=("the population prior is the loss budget: fewer than 1% of "
                  "Taiwanese day traders earn a positive abnormal return net "
                  "of fees, 97% of persisting Brazilian futures day traders "
                  "lose, and US 1998-99 profitability tracked Nasdaq beta "
                  "rather than skill. A majority of judged positions are "
                  "expected to lose and the book is not retired for that."),
        ),
        licence=Licence.PRODUCT_EXPERIMENT, engine="series",
        engine_params={
            "lane": LANE, "item": "D1",
            "intraday": {"hold_rule": "session_end",
                         "forced_flat_at_close": True,
                         "entry_window_et": ["09:30", "10:30"],
                         "bar_minutes": 30},
            "cost_curve": COST_CURVE,
            "declared_target": {"per_day": 0.01, "compounded_per_year": 11.27,
                                "source": "roadmap §10b, arithmetic stated once"},
            "sessions_to_a_first_read": {
                "at_book_sd_1.2pct_per_day": 12,
                "at_universe_sd_2.93pct_per_day": 71,
                "note": ("n = (t*sd/mean)^2 at t 2.8 against a true 1%/day. The "
                         "statistics are cheap; finding a surviving 1%/day "
                         "gross mechanism is the entire problem."),
            },
            "twins": ["random_universe (= random entry at the same clock and "
                      "size)", "overnight_only (holds through the open, nothing "
                      "intraday — the systems check against a KNOWN answer, "
                      "FINDING_2026-08-23, not a new question)"],
            "no_order_path": True,
        },
        note=("PRODUCT_EXPERIMENT, paper only, no order path. Respects "
              "FINDING_2026-08-23_OVERNIGHT_INTRADAY (the overnight/intraday "
              "split is already measured at daily resolution and buy-and-hold "
              "beat overnight-only at zero cost) and the closed daily reaction "
              "lane (RW2): neither is re-asked. The untested slice is the FIRST "
              "HOUR after a native-stamped headline."),
    )


def worst_case_print(strategy: Strategy) -> dict:
    """Session protocol rule 4, printed BEFORE the book exists."""
    k = int(strategy.construction.k)
    per_name = min(float(strategy.construction.max_single_name),
                   float(strategy.construction.gross_cap) / k)
    out = loss_budget_worst_case(strategy, n_names=k, notional_pct=per_name,
                                 equity_usd=float(strategy.sizing.notional_usd))
    out["daily_loss_limit"] = (
        f"{k} names x {per_name:.2%} notional x "
        f"{abs(strategy.hold.stop_loss):.0%} stop = "
        f"{k * per_name * abs(strategy.hold.stop_loss):.2%} of equity in one "
        f"session; gross {k * per_name:.2f}x against a "
        f"{strategy.sizing.gross_cap:.2f}x cap")
    return out


def seed(*, dry_run: bool = False, write_receipt: bool = True, conn=None) -> dict:
    from backend.services import paper_books as PB
    from scripts.seed_first_books import control_client

    s = lane_d_book()
    bid = PB.book_id_for(s)
    receipt: dict = {
        "job": "seed_lane_d_book", "lane": LANE, "item": "D1",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "PRODUCT_EXPERIMENT", "dry_run": bool(dry_run),
        "strategy_id": s.strategy_id, "book_id": bid,
        "cadence": "30m", "origin": "night_job", "origin_text": ORIGIN_TEXT,
        "cost_curve": COST_CURVE,
        "worst_case": worst_case_print(s),
        "marking_caveat": (
            "minute bars do not exist on this machine, so `book_cadence` marks "
            "this book at granularity='daily_close' with "
            "intraday_bars_available=false on every row. A 30-minute book "
            "graded from daily closes is not a 30-minute book's result."),
    }
    have = {b.book_id for b in PB.list_books(conn=conn)}
    receipt["already_present"] = bid in have
    if dry_run or bid in have:
        receipt["created"] = False
        if bid in have:
            receipt["reason"] = ("the fingerprint is already in `paper_books`; "
                                 "a second create would rewrite the row and "
                                 "re-draw nothing")
            # The twins are listed even on a no-op run. This receipt OVERWRITES
            # the one the creating run wrote, so a receipt that only said
            # "already present" would erase the only record of what was made.
            existing = PB.get(bid, conn=conn)
            if existing is not None:
                receipt["twins"] = [
                    {"book_id": tid,
                     "kind": (PB.get(tid, conn=conn).strategy.engine_params
                              .get("twin", {}).get("kind")
                              if PB.get(tid, conn=conn) else None)}
                    for tid in existing.control_twin_ids]
                receipt["created_utc"] = existing.created_utc
        return _finish(receipt, write_receipt)

    prev = os.environ.get("AEGIS_CONTROL_ENABLED")
    os.environ["AEGIS_CONTROL_ENABLED"] = "1"
    try:
        resp = control_client().post(
            "/api/control/books/create-from-contract",
            json={"strategy": s.as_dict(), "cadence": "30m",
                  "origin": "night_job", "origin_text": ORIGIN_TEXT})
    finally:
        if prev is None:
            os.environ.pop("AEGIS_CONTROL_ENABLED", None)
        else:
            os.environ["AEGIS_CONTROL_ENABLED"] = prev
    if resp.status_code != 200:
        receipt["created"] = False
        receipt["http_status"] = resp.status_code
        receipt["refused"] = resp.text[:600]
        return _finish(receipt, write_receipt)
    body = resp.json()
    receipt["created"] = True
    receipt["twins"] = [{"book_id": t["book_id"],
                         "kind": t["strategy_id"].rsplit("::", 1)[-1]}
                        for t in body["twins"]]
    receipt["route_worst_case"] = body.get("worst_case")
    return _finish(receipt, write_receipt)


def _finish(receipt: dict, write_receipt: bool) -> dict:
    if write_receipt:
        p = receipt_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        receipt["receipt_path"] = str(p)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(seed(dry_run=a.dry_run), indent=2, default=str))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
