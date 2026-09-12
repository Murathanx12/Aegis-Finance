"""T2 — the first four `origin=night_job` PaperBooks, created THROUGH THE ROUTE.

WHY THROUGH THE ROUTE AND NOT THROUGH `paper_books.create`
==========================================================
`POST /api/control/books/create-from-contract` is the surface the roadmap says
a night job seeds books through, and it carries three refusals a direct call
would bypass: `origin="human_text"` is rejected (B2's human hold step is a
click, not a route), the contract is rebuilt from JSON by the strict loader
that refuses an unknown field, and the router's AST test keeps the whole module
broker-free. Seeding past it would make the route decorative on the one code
path it exists for.

The call is made IN PROCESS with a `TestClient` and `AEGIS_CONTROL_ENABLED=1`,
so no port is opened and no network is touched.

IDEMPOTENT, AND WHY THAT IS NOT A CONVENIENCE
=============================================
A book's id IS its contract's fingerprint (`book:<16 hex>`). Two runs of this
script with the same contracts therefore address the same rows — but a second
`create()` would re-`INSERT OR REPLACE` the book and re-draw nothing, while
still logging as if it had created something. This script LOOKS FIRST: it
computes each fingerprint, asks the database, and creates only what is absent.
A second run reports `existing` for all four and writes a receipt saying so.
That is the property that lets the night job call it unconditionally.

WHAT IS SEEDED, AND WHAT EACH BOOK CAN ACTUALLY DO ON THE LOCAL BARS
====================================================================
All four books are MARKED by `book_cadence` from the first pass. Whether each
can DECIDE depends on whether its panel reaches the bar vintage, and the
honest answer differs per book:

  A  short interest x turnover  -- MARKS, does not decide forward. The panel is
     CRSP-permno-keyed and ends 2024-12-31; the bars are ticker-keyed 2025-26.
     Its evidence comes from the replay job, in permno space.
  B  insider cluster length     -- MARKS AND DECIDES. The Form-4 tape runs to
     2026q2 and carries `symbol`, so it is the one of the four whose signal
     reaches the forward bars.
  C  disposition overhang       -- MARKS, does not decide forward. Grinblatt-Han
     weights past prices by turnover and turnover needs shares outstanding,
     which ticker bars do not carry.
  D  abstention                 -- MARKS AND DECIDES. Bars-only.

Those refusals are NAMED on every cadence receipt by `book_signals`. A book
that silently held nothing would be indistinguishable from a book that decided
to hold nothing, which is the distinction the whole lane is for.

    python -m scripts.seed_first_books
    python -m scripts.seed_first_books --dry-run
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
                                       Signal, Sizing, Strategy, Universe)

logger = logging.getLogger("seed_first_books")

#: The ONE multiplicity family the four books share (spec §0D). Four primary
#: tests, one budget, Holm at export.
FAMILY = "NIGHT_JOB_BOOKS_2026_09"

#: The execution floor this repository already declares.
FLOOR_USD = 3_000_000.0
MIN_PRICE = 5.0


def receipt_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "seed_receipt.json"


# --------------------------------------------------------------------------
# the four contracts, exactly as `spec_first_books.md` writes them
#
# Deviations from the spec's literal blocks are NAMED here rather than absorbed:
#
#  * `cadence="monthly"` everywhere, not the spec's interim `"quarterly"`. The
#    spec §0C recommended adding `monthly` to the enum before any of these is
#    held and said to use quarterly-plus-a-note until then. Chunk 5 added it.
#  * Book D uses `Construction(rule="threshold_coverage")` with
#    `engine_params["abstain"]`, not the spec's synthetic-`CASH_OR_SPY`
#    workaround. Chunk 5 added the rule; §D.3 says the workaround is no longer
#    required once it exists.
#  * Book D's confidence is the v1 trigger (composite extremity), not v0's R2
#    digest. §D.2: "whichever the builder wires up first, do not block on L2."
#  * Signal NAMES match `book_signals.REGISTRY` keys rather than the spec's
#    prose names, because the registry key IS the dispatch and two spellings of
#    one signal is how a book ends up marked by a ranking nobody declared.


def book_a() -> Strategy:
    return Strategy(
        strategy_id="si_low_turnover_high_v1",
        title="Low short interest, high turnover, long-only (Boehmer-Huszar-Jordan 2010)",
        universe=Universe(
            name="si_low_turnover_high_universe",
            source=("CRSP common stock + WRDS comp.sec_shortint (built panel, "
                    "PIT on observed_at = datadate + 14d) + computed 21-session turnover"),
            floor_dollar_vol_usd=FLOOR_USD, min_price_usd=MIN_PRICE, max_names=None,
            note=("report pre- and post-floor name counts every period; re-measure "
                  "the SAME double sort at a $10M floor too (TRIAL-H5 lesson: a "
                  "corner-dependent control must be re-measured at every corner)"),
        ),
        signal=Signal(
            name="short_interest_low_x_turnover_high",
            column="si_turnover_z", direction=1,
            source="computed: CRSP vol/shrout + WRDS Compustat short interest",
            warmup_periods=20,
            note=("z(turnover_21d_w) - z(si_ratio) within the month's cross-section: "
                  "the double sort collapsed to one composite so Construction.top_k "
                  "applies; the raw quintile x quintile table is reported beside it. "
                  "Turnover is NOT adjusted for Nasdaq double-counting (Anderson-Dyl "
                  "2005, UNRESOLVED) and the panel row says so."),
        ),
        construction=Construction(
            rule="top_k", k=50, weighting="ew", max_single_name=0.05, gross_cap=1.0,
            note="k=50 approximates BHJ's top double-sort cell; sensitivity at k=30,100 reported",
        ),
        hold=HoldRule(
            horizon_periods=6, min_hold_periods=1, scheduled_review_periods=1,
            stop_loss=-0.20, roi_ladder={},
            note="BHJ's own robustness runs to a 6-month hold with no documented decay inside it",
        ),
        sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
        costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
        objective=Objective(name="alpha_intercept", periods_per_year=12,
                            utility="risk_adjusted"),
        loss_budget=LossBudget(positions_judged=50, expected_losers=24,
                               note=("modest documented tilt, not a high-conviction "
                                     "picker; ~55% historical name-level hit rate assumed")),
        licence=Licence.PRODUCT_EXPERIMENT, engine="series",
        engine_params={"family": FAMILY, "prereg": "TRIAL-DRAFT-A-si-low-turnover-high-v1",
                       "prereg_status": "UNSIGNED"},
        note=("respects NEGATIVE_RESULTS §24: si_chg_low is a CHANGE signal with dead net "
              "turnover; dtc_low/high is a LEVEL of days-to-cover, the SHORT leg. This book "
              "is the SI-LEVEL x TURNOVER-LEVEL long-only cell, never tested here before."),
    )


def book_b() -> Strategy:
    return Strategy(
        strategy_id="insider_cluster_length_v1",
        title=("Insider cluster buys, 4-5 day clusters, long-only "
               "(Kang-Kim-Wang / Alldredge-Blank)"),
        universe=Universe(
            name="insider_cluster_universe",
            source="SEC Form-4 bulk (insider_events_v1.parquet) + CRSP link",
            floor_dollar_vol_usd=FLOOR_USD, min_price_usd=MIN_PRICE, max_names=None,
            note=("insider buys concentrate in small/micro caps — report pre- and "
                  "post-floor name counts every period; expect heavy attrition"),
        ),
        signal=Signal(
            name="insider_cluster_len", column="cluster_length_days", direction=1,
            source="computed: insider_events_v1.parquet transaction-date clustering",
            warmup_periods=0,
            note=("eligibility gate, not a continuous rank: a name enters only in the "
                  "month its 4-5-day cluster's LATEST filing_date lands"),
        ),
        construction=Construction(
            rule="passthrough", k=40, weighting="ew", max_single_name=0.10,
            gross_cap=1.0,
            note=("event count varies month to month; passthrough (not top_k) is "
                  "correct here. k is the cap the selector applies when the month's "
                  "event count exceeds it, and is reported beside the raw count."),
        ),
        hold=HoldRule(
            horizon_periods=4, min_hold_periods=1, scheduled_review_periods=1,
            stop_loss=-0.25, roi_ladder={},
            note=("BHAR(22,90) is measured from day 22, not day 0, but the book enters at "
                  "filing (T+1 open) since waiting 22 days forfeits the disclosure-day pop"),
        ),
        sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
        costs=CostModel(
            transaction_cost_bps=20.0, slippage_bps=5.0,
            note=("micro-cap spreads: NEGATIVE_RESULTS §25 measured 41.7-49.2bps "
                  "one-way (Corwin-Schultz) vs 11.6-13.1bps (Kyle-linear) in exactly "
                  "this segment, a 3.4-4.2x disagreement; the harsher estimate is "
                  "primary and the 5bps repo default is reported as an optimistic bound")),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
        objective=Objective(name="alpha_intercept", periods_per_year=12,
                            utility="risk_adjusted"),
        loss_budget=LossBudget(positions_judged=40, expected_losers=18,
                               note="rarer events than Book A; smaller expected sample"),
        licence=Licence.PRODUCT_EXPERIMENT, engine="series",
        engine_params={"family": FAMILY,
                       "prereg": "TRIAL-DRAFT-B-insider-cluster-length-v1",
                       "prereg_status": "UNSIGNED",
                       "cluster": {"spans": [4, 5], "min_insiders": 2,
                                   "window_days": 31}},
        note=("respects NEGATIVE_RESULTS §46/N1: the insider return does NOT accrue "
              "before disclosure on 5 filing days, so filing-date PIT entry is not "
              "pre-empted. The 13D/13G family stays NO CONCLUSION and is untouched. "
              "Cluster SALES are not shorted (KKW: uninformative)."),
    )


def book_b_falsifier() -> Strategy:
    """The same-day arm. KKW predicts it LOSES; if it wins, B is falsified.

    A separate `PaperBook` rather than a field on B, because an arm that is only
    a diagnostic column never gets marked, never gets a NAV and never gets a
    forecast row — and this one has to be all three for the falsifier to be
    checkable at the family read rather than asserted at it.
    """
    b = book_b()
    return b.with_(
        strategy_id="insider_cluster_same_day_v1",
        title="Insider SAME-DAY clusters — the falsifier arm for insider_cluster_length_v1",
        signal=Signal(
            name="insider_cluster_len", column="cluster_length_days", direction=1,
            source="computed: insider_events_v1.parquet transaction-date clustering",
            warmup_periods=0,
            note=("the SAME-DAY bucket (span 0). Theory says this arm underperforms "
                  "non-cluster purchases by ~0.72% BHAR(22,90); if it instead WINS, "
                  "the length-conditioning claim is falsified before the family read."),
        ),
        engine_params={"family": FAMILY,
                       "prereg": "TRIAL-DRAFT-B-insider-cluster-length-v1",
                       "prereg_status": "UNSIGNED",
                       "role": "falsifier_arm_of:insider_cluster_length_v1",
                       "cluster": {"spans": [0], "min_insiders": 2,
                                   "window_days": 31}},
        parents=("insider_cluster_length_v1",),
    )


def book_c() -> Strategy:
    return Strategy(
        strategy_id="disposition_overhang_conditioner_v0",
        title=("Good-news names in the top overhang tercile, long-only "
               "(Frazzini 2006 / Grinblatt-Han 2005)"),
        universe=Universe(
            name="disposition_overhang_universe",
            source=("CRSP price/volume (computed Grinblatt-Han CGO) + IBES revision "
                    "sign (v0) / L2 typed events (v1)"),
            floor_dollar_vol_usd=FLOOR_USD, min_price_usd=MIN_PRICE, max_names=None,
            note=("re-measure at the $10M corner too — S49/TRIAL-H5: the documented "
                  "effect concentrates in exactly the illiquid names most likely to "
                  "fail a floor"),
        ),
        signal=Signal(
            name="overhang_conditioned_reaction",
            column="overhang_rank_within_good_news", direction=1,
            source="computed CGO (Grinblatt-Han) x IBES revision sign (v0)",
            warmup_periods=252,
            note=("the eligible set is gated on event sign FIRST, then ranked on "
                  "overhang within it — this is the conditioner, not a two-factor blend"),
        ),
        construction=Construction(rule="top_k", k=30, weighting="ew",
                                  max_single_name=0.08, gross_cap=1.0),
        hold=HoldRule(horizon_periods=3, min_hold_periods=1,
                      scheduled_review_periods=1, stop_loss=-0.20, roi_ladder={},
                      note=("post-event drift horizon per Frazzini; re-checked against "
                            "the closed H5 book's own 5-session horizon for comparability")),
        sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
        costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
        objective=Objective(name="alpha_intercept", periods_per_year=12,
                            utility="risk_adjusted"),
        loss_budget=LossBudget(positions_judged=36, expected_losers=17),
        licence=Licence.PRODUCT_EXPERIMENT, engine="series",
        engine_params={"family": FAMILY,
                       "prereg": "TRIAL-DRAFT-C-disposition-overhang-conditioner-v0",
                       "prereg_status": "UNSIGNED",
                       "overhang": {"lookback_sessions": 1260, "tercile": 0.6667,
                                    "event_sign": "ibes_consensus_revision_1m"},
                       "primary_control": "unconditioned_reaction_book_rerun_fresh"},
        note=("respects TRIAL-H5/RW2: the pooled reaction lane is CLOSED (t 1.14, RW2 "
              "44-46% window pass rate); this book re-slices that SAME closed population "
              "by overhang tercile and may not restate the pooled claim as its own"),
    )


def book_c_control() -> Strategy:
    """The UNCONDITIONED reaction book, run fresh — Book C's PRIMARY comparator.

    Spec §C.4: this is the only comparator that makes "does the conditional
    question the closed verdict never asked" falsifiable rather than rhetorical.
    It is a book, not a number quoted from H5's closed receipt, because a
    comparator read off an old receipt was measured under an old cost model, an
    old universe and an old calendar.
    """
    c = book_c()
    return c.with_(
        strategy_id="unconditioned_reaction_book_v0",
        title="The UNCONDITIONED reaction book — Book C's primary comparator, run fresh",
        signal=Signal(
            name="overhang_conditioned_reaction",
            column="event_sign_only", direction=1,
            source="computed: IBES revision sign, with NO overhang conditioning",
            warmup_periods=252,
            note=("the identical event-sign universe and hold WITHOUT the overhang "
                  "tercile gate. This is the control Book C's primary metric "
                  "subtracts, and it is marked and graded by the same machinery.")),
        engine_params={"family": FAMILY,
                       "prereg": "TRIAL-DRAFT-C-disposition-overhang-conditioner-v0",
                       "prereg_status": "UNSIGNED",
                       "role": "primary_control_of:disposition_overhang_conditioner_v0",
                       "overhang": {"tercile": None,
                                    "event_sign": "ibes_consensus_revision_1m"}},
        parents=("disposition_overhang_conditioner_v0",),
    )


def book_d() -> Strategy:
    return Strategy(
        strategy_id="abstention_book_v0",
        title="Cash/index by default; deviate only above a confidence threshold",
        universe=Universe(
            name="abstention_universe",
            source=("arena composite extremity (v1: the signed cross-sectional z of "
                    "mom_12_1, which IS the composite for 99.5% of names) over the "
                    "local daily bars, with SPY as the declared fallback"),
            floor_dollar_vol_usd=FLOOR_USD, min_price_usd=MIN_PRICE, max_names=None),
        signal=Signal(
            name="abstention_confidence_z", column="composite_z", direction=1,
            source="computed from the local bars: cross-sectional z of mom_12_1",
            warmup_periods=253,
            note=("SIGNED, not absolute. An abstention book deviating into a name "
                  "because its momentum was extremely NEGATIVE would be buying the "
                  "worst names in the market with high confidence.")),
        construction=Construction(
            rule="threshold_coverage", k=5, weighting="ew", max_single_name=0.30,
            gross_cap=1.0,
            note=("coverage IS the decision; k is only what happens once coverage is "
                  "non-empty. The spec's synthetic CASH_OR_SPY workaround is no "
                  "longer needed — chunk 5 added the rule.")),
        hold=HoldRule(horizon_periods=1, min_hold_periods=1,
                      scheduled_review_periods=1, stop_loss=None, roi_ladder={},
                      note="monthly, matching R2's own cadence"),
        sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0,
                      overlays=("abstention_gate",),
                      params={"confidence_threshold": 1.5, "default_asset": "SPY"}),
        costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0,
                        note="turnover occurs only on regime switches; expected low"),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=False,
                            is_own_universe_average=False),
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            periods_per_year=12, drawdown_budget=-0.20,
                            utility="risk_adjusted"),
        loss_budget=LossBudget(positions_judged=24, expected_losers=10,
                               note=("must be BELOW the always-invested twin's own "
                                     "historical loser-month rate to be worth anything")),
        licence=Licence.PRODUCT_EXPERIMENT, engine="series",
        engine_params={"family": FAMILY, "prereg": "TRIAL-DRAFT-D-abstention-book-v0",
                       "prereg_status": "UNSIGNED",
                       "abstain": {"min_signal": 1.5, "min_names": 3,
                                   "fallback": "SPY"}},
        note=("respects NEGATIVE_RESULTS §1: the existing timing strategy lost to "
              "buy-and-hold (+28.3% vs +114.8%, Sharpe 0.432 vs 0.837); this book must "
              "beat that receipt directly, printed on the same axes, not merely exist "
              "as a different construction"),
    )


def book_d_always_invested() -> Strategy:
    """The ALWAYS-INVESTED twin — Book D's primary comparator, per §D.4.

    `make_twins` gives every book a random-universe and a beta-matched twin;
    neither of them is the control this idea's own falsifying observation
    names. The always-invested arm is the identical selector with the gate
    DISABLED (`top_k`, no threshold), so the only difference between the two
    NAV series is the abstention.
    """
    d = book_d()
    return d.with_(
        strategy_id="abstention_always_invested_twin_v0",
        title="Always invested — Book D's primary comparator (the gate disabled)",
        construction=Construction(rule="top_k", k=5, weighting="ew",
                                  max_single_name=0.30, gross_cap=1.0,
                                  note=("the SAME selector with coverage forced to "
                                        "100%: it always holds its top-5 real names "
                                        "and never falls back to SPY")),
        engine_params={"family": FAMILY, "prereg": "TRIAL-DRAFT-D-abstention-book-v0",
                       "prereg_status": "UNSIGNED",
                       "role": "primary_control_of:abstention_book_v0"},
        parents=("abstention_book_v0",),
    )


#: (strategy factory, origin_text). `origin_text` is what a reader sees on the
#: board beside the book, so it names the mechanism, the prereg and the
#: multiplicity family rather than restating the title.
BOOKS: tuple = (
    (book_a, ("Night job, 2026-09-12. Boehmer-Huszar-Jordan (JFE 2010): the "
              "informative side of short interest is the side nobody trades. "
              "Low SI x high turnover, long-only, monthly rebalance with a "
              "six-month maximum hold. Pre-registration TRIAL-DRAFT-A "
              "(UNSIGNED); multiplicity family NIGHT_JOB_BOOKS_2026_09, four "
              "primary tests under one budget. Decay past 2005 is UNVERIFIED "
              "and the prior is 'materially decayed', not '+1%/month'.")),
    (book_b, ("Night job, 2026-09-12. Kang-Kim-Wang: insider purchase clusters "
              "spread over 4-5 days are followed by >5% higher BHAR(22,90) "
              "than non-cluster purchases; same-day clusters are 0.72% worse. "
              "Entered at the LATEST filing date in the cluster. "
              "Pre-registration TRIAL-DRAFT-B (UNSIGNED), family "
              "NIGHT_JOB_BOOKS_2026_09. The power check says this design is "
              "UNDERPOWERED for its own prior (MDE 7.17% vs a published 5%), "
              "so a null here is not evidence of absence.")),
    (book_b_falsifier,
     ("Night job, 2026-09-12. The SAME-DAY arm of the insider-cluster book, "
      "created at the same time as its parent so the falsifier is a marked, "
      "graded NAV series rather than a claim made at the read. Theory says it "
      "LOSES; if it wins, insider_cluster_length_v1 is falsified.")),
    (book_c, ("Night job, 2026-09-12. Frazzini (JF 2006) / Grinblatt-Han (JFE "
              "2005): post-event drift is worst where holders sit on unrealised "
              "gains. TRIAL-H5 and RW2 closed the POOLED reaction lane; this "
              "book asks the CONDITIONAL question that closure never asked, on "
              "the same population, as a re-slice. Pre-registration "
              "TRIAL-DRAFT-C (UNSIGNED), family NIGHT_JOB_BOOKS_2026_09.")),
    (book_c_control,
     ("Night job, 2026-09-12. The UNCONDITIONED reaction book, run fresh — "
      "Book C's PRIMARY comparator. A scope-aware verdict needs a live "
      "comparator, not a number quoted from a closed receipt measured under an "
      "old cost model.")),
    (book_d, ("Night job, 2026-09-12. Cash/index by default; deviate into a name "
              "only when its confidence clears a frozen threshold. Abstention is "
              "timing with a stricter trigger and must beat NEGATIVE_RESULTS §1's "
              "receipt directly (+28.3% vs +114.8%, Sharpe 0.432 vs 0.837), not "
              "merely exist. Pre-registration TRIAL-DRAFT-D (UNSIGNED), family "
              "NIGHT_JOB_BOOKS_2026_09. Cannot be read before 24 monthly blocks.")),
    (book_d_always_invested,
     ("Night job, 2026-09-12. The ALWAYS-INVESTED arm of the abstention book — "
      "the identical selector with coverage forced to 100%. This is the control "
      "the idea's own falsifying observation names, and it is created with the "
      "book, before either has a number.")),
)


# --------------------------------------------------------------------------
# the seeding


def control_client():
    """An in-process TestClient with the control plane enabled.

    `AEGIS_CONTROL_ENABLED` is set here and restored afterwards. The router
    reads it per request (`_require_enabled`), so nothing is cached and no
    module is reloaded — `backend.config` is never re-imported, which is the
    house rule this would otherwise break.
    """
    from fastapi.testclient import TestClient

    from backend.main import app
    return TestClient(app)


def existing_ids(conn=None) -> set:
    from backend.services import paper_books as PB
    return {b.book_id for b in PB.list_books(conn=conn)}


def seed(*, dry_run: bool = False, write_receipt: bool = True,
         conn=None) -> dict:
    """Create whatever is missing; report what already existed."""
    from backend.services import paper_books as PB

    receipt: dict = {
        "job": "seed_first_books",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "dry_run": bool(dry_run), "books": [], "created": 0, "existing": 0,
        "note": ("created through POST /api/control/books/create-from-contract, "
                 "in process, so the route's refusals are the ones that fire"),
    }
    have = existing_ids(conn=conn)
    planned = []
    for factory, origin_text in BOOKS:
        s = factory()
        planned.append((s, origin_text, PB.book_id_for(s)))
    receipt["planned"] = [{"strategy_id": s.strategy_id, "book_id": bid,
                           "already_present": bid in have}
                          for s, _, bid in planned]
    if dry_run:
        return _finish(receipt, write_receipt)

    prev = os.environ.get("AEGIS_CONTROL_ENABLED")
    os.environ["AEGIS_CONTROL_ENABLED"] = "1"
    try:
        client = control_client()
        for s, origin_text, bid in planned:
            if bid in have:
                receipt["existing"] += 1
                receipt["books"].append({
                    "strategy_id": s.strategy_id, "book_id": bid,
                    "created": False,
                    "reason": ("the fingerprint is already in `paper_books`; a "
                               "second create would rewrite the row and re-draw "
                               "nothing while logging as if it had created "
                               "something")})
                continue
            resp = client.post("/api/control/books/create-from-contract", json={
                "strategy": s.as_dict(), "cadence": "monthly",
                "origin": "night_job", "origin_text": origin_text})
            if resp.status_code != 200:
                receipt["books"].append({
                    "strategy_id": s.strategy_id, "book_id": bid,
                    "created": False, "http_status": resp.status_code,
                    "refused": resp.json().get("detail") if resp.headers.get(
                        "content-type", "").startswith("application/json")
                        else resp.text[:400]})
                continue
            body = resp.json()
            receipt["created"] += 1
            receipt["books"].append({
                "strategy_id": s.strategy_id,
                "book_id": body["book"]["book_id"],
                "created": True,
                "cadence": body["book"]["cadence"],
                "origin": body["book"]["origin"],
                "twins": [{"book_id": t["book_id"],
                           "kind": t["strategy_id"].rsplit("::", 1)[-1]}
                          for t in body["twins"]],
                "worst_case": body.get("worst_case"),
                "licence": body["book"]["licence"],
                "round_trip_bps": body["book"].get("round_trip_bps"),
            })
    finally:
        if prev is None:
            os.environ.pop("AEGIS_CONTROL_ENABLED", None)
        else:
            os.environ["AEGIS_CONTROL_ENABLED"] = prev
    return _finish(receipt, write_receipt)


def _finish(receipt: dict, write_receipt: bool) -> dict:
    receipt["n_books"] = len(receipt.get("books") or receipt.get("planned") or [])
    if write_receipt:
        p = receipt_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        receipt["receipt_path"] = str(p)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the fingerprints and what would be created")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(seed(dry_run=a.dry_run), indent=2, default=str))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
