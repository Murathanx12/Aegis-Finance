"""A_published_anomaly -- one published anomaly a week, on OUR tape, preregistered.

Modelled on Fidetolabs Notes (research note 2026-09-11): pick one published
quant-finance paper, preregister the plan BEFORE loading data, test it from
scratch on real market data, and publish the code, the charts and the result
INCLUDING the negative ones. Roadmap section 11a.

WHY A CADENCE AND NOT A BATCH
=============================
Eight anomalies run at once is one afternoon's work and eight numbers nobody
reads. One a week, each with its own pre-registration committed before its
first cell is graded, is eight tamper-evident replications and a ratio --
published over replicated -- that is itself the finding. The order below is
CHEAPEST DATA FIRST, so week 1 does not block on a data build: a cadence whose
first week waits for a pull is a cadence that never starts.

WHAT THIS JOB REFUSES
=====================
It refuses to run the PRIMARY of a week whose pre-registration is not SIGNED.
A replication that grades its primary before its plan is signed is a
replication with a free parameter in it -- the plan -- and the whole point of
the cadence is that the plan is fixed first. `--smoke` is allowed against an
unsigned prereg and its verdict field is forced to `SMOKE_NOT_A_VERDICT`; it
is a plumbing check, and the receipt says so in the field a reader looks at.

THE CONTROL IS DRIFT-ONLY
=========================
Every anomaly book is graded against a book that holds the same NUMBER of the
same KIND of names, rebalanced on the same calendar, at the same costs,
selected by `oldest_listing` -- a sort with no economic claim in it. The
difference is then about the SORT and not about being in the market, which is
what a raw Sharpe would mostly measure.

    python -m scripts.night_anomaly_adjudicate --week 1 --smoke
    python -m scripts.night_factory_jobs A_published_anomaly --run 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_farm import farm as FARM              # noqa: E402
from backend.services.portfolio_farm.panel import (PanelUnavailable,   # noqa: E402
                                                   load_panel)
from backend.services.portfolio_farm.policy import Policy              # noqa: E402

NIGHTS = REPO / "backend" / "data" / "optimus"
TRIALS = REPO / "docs" / "TRIALS"

#: The family every week's evidence row is filed under, so M2's distillation
#: can pair an anomaly week's era split exactly like any other mechanism.
FAMILY = "PUBLISHED_ANOMALIES_2026"

#: The control. Declared here once rather than per week: a control chosen per
#: anomaly is a control chosen after seeing the anomaly.
DRIFT_ONLY_CONTROL = "oldest_listing"

#: The eras, frozen. 2 of 3 with the same sign is `evidence_memory`'s own bar.
ERAS = (("1990-2001", 1990, 2001), ("2002-2012", 2002, 2012),
        ("2013-2024", 2013, 2024))

#: THE EIGHT, in cadence order, cheapest data requirement first. `signal` is
#: the engine's EXISTING signal where one already implements the published
#: sort; `None` means the factor has still to be built and the week is not
#: runnable yet, which the receipt says by name rather than by returning
#: nothing.
ANOMALIES: tuple[dict, ...] = (
    {"week": 1, "name": "short_term_reversal", "signal": "reversal_1m",
     "citation": ("Jegadeesh (1990), 'Evidence of Predictable Behavior of "
                  "Security Returns', Journal of Finance 45(3)"),
     "data_need": "monthly returns only -- already on the tape",
     "prereg": "PREREG_ANOMALY_SHORT_TERM_REVERSAL_1.md",
     "published_direction": "last month's losers outperform last month's winners"},
    {"week": 2, "name": "earnings_momentum_pead", "signal": None,
     "citation": ("Ball & Brown (1968); Bernard & Thomas (1989/1990), "
                  "post-earnings-announcement drift"),
     "data_need": "SUE from quarterly EPS -- ingested for the insider/revisions work",
     "prereg": None,
     "published_direction": "high-SUE names drift up for ~60 sessions"},
    {"week": 3, "name": "fifty_two_week_high", "signal": None,
     "citation": ("George & Hwang (2004), 'The 52-Week High and Momentum "
                  "Investing', Journal of Finance 59(5)"),
     "data_need": "252-session rolling high -- trivial from the price panel",
     "prereg": None,
     "published_direction": "names near their 52-week high outperform"},
    {"week": 4, "name": "gross_profitability", "signal": None,
     "citation": ("Novy-Marx (2013), 'The Other Side of Value: The Gross "
                  "Profitability Premium', Journal of Financial Economics 108(1)"),
     "data_need": "(revenue - COGS) / assets -- fundamentals panel",
     "prereg": None,
     "published_direction": "high gross profitability outperforms"},
    {"week": 5, "name": "asset_growth", "signal": None,
     "citation": ("Cooper, Gulen & Schill (2008), 'Asset Growth and the "
                  "Cross-Section of Stock Returns', Journal of Finance 63(4)"),
     "data_need": "total assets YoY -- fundamentals panel",
     "prereg": None,
     "published_direction": "low asset growth outperforms high"},
    {"week": 6, "name": "net_stock_issuance", "signal": None,
     "citation": ("Pontiff & Woodgate (2008), 'Share Issuance and "
                  "Cross-Sectional Returns', Journal of Finance 63(2); "
                  "Daniel & Titman (2006)"),
     "data_need": "shares outstanding change -- fundamentals panel",
     "prereg": None,
     "published_direction": "share repurchasers outperform issuers"},
    {"week": 7, "name": "accruals", "signal": None,
     "citation": ("Sloan (1996), 'Do Stock Prices Fully Reflect Information "
                  "in Accruals and Cash Flows about Future Earnings?', "
                  "The Accounting Review 71(3)"),
     "data_need": "(net income - operating cash flow) / assets",
     "prereg": None,
     "published_direction": "low-accrual names outperform high-accrual ones"},
    {"week": 8, "name": "low_volatility", "signal": "low_vol",
     "citation": ("Ang, Hodrick, Xing & Zhang (2006), 'The Cross-Section of "
                  "Volatility and Expected Returns', Journal of Finance 61(1); "
                  "Baker, Bradley & Wurgler (2011)"),
     "data_need": "trailing realised vol -- already computed for sizing",
     "prereg": None,
     "published_direction": "low-volatility names earn higher risk-adjusted returns"},
)

#: The primary cost ruler, and the two flat rates reported beside it. Never
#: one number: a result that exists only at 6 bps is a result about 6 bps.
COST_CELLS = (
    {"curve": "taq_empirical"},
    {"curve": "flat", "transaction_cost_bps": 5.0, "slippage_bps": 1.0},
    {"curve": "flat", "transaction_cost_bps": 25.0, "slippage_bps": 5.0},
)
PRIMARY_COST = "taq_empirical"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def anomaly_of(week: int | None = None, name: str | None = None) -> dict:
    for row in ANOMALIES:
        if (week is not None and row["week"] == week) or (
                name is not None and row["name"] == name):
            return row
    raise SystemExit(f"REFUSED: no anomaly at week={week} name={name}; "
                     f"declared: {[a['name'] for a in ANOMALIES]}")


def prereg_state(anomaly: dict) -> dict:
    """Is this week's plan on disk, and is it SIGNED?

    Read from the file rather than tracked in a flag: the pre-registration IS
    the commitment and a second place recording its status is a second place
    that can disagree with it.
    """
    name = anomaly.get("prereg")
    if not name:
        return {"present": False, "signed": False, "path": None,
                "why": f"no pre-registration is written for week {anomaly['week']}"}
    p = TRIALS / name
    if not p.is_file():
        return {"present": False, "signed": False, "path": str(p),
                "why": f"{name} is not on this checkout"}
    text = p.read_text(encoding="utf-8", errors="replace")
    signed = ("SIGNED-BY:" in text
              or "**Status: SIGNED" in text
              or "Status: SIGNED" in text)
    return {"present": True, "signed": bool(signed), "path": str(p),
            "why": ("signed" if signed else
                    "present and UNSIGNED -- the primary may not be graded "
                    "until Murat signs it; a smoke run is allowed and its "
                    "verdict is forced to SMOKE_NOT_A_VERDICT")}


def _cell_label(cost: dict) -> str:
    if cost.get("curve", "flat") != "flat":
        return str(cost["curve"])
    return f"flat_{cost['transaction_cost_bps']:.0f}+{cost['slippage_bps']:.0f}bps"


def era_cells(anomaly: dict, eras=ERAS, *, top_k: int = 50,
              universe_n: int = 500, holding_days: int = 21,
              costs=COST_CELLS) -> list[dict]:
    """One (era, cost) cell per row, each with its book and its drift control."""
    out = []
    for label, lo, hi in eras:
        for cost in costs:
            out.append({"era": label, "start": lo, "end": hi,
                        "cost_cell": _cell_label(cost),
                        "book": Policy(signal=anomaly["signal"],
                                       holding_days=holding_days, top_k=top_k,
                                       universe_n=universe_n, **cost),
                        "control": Policy(signal=DRIFT_ONLY_CONTROL,
                                          holding_days=holding_days,
                                          top_k=top_k, universe_n=universe_n,
                                          **cost)})
    return out


def _pair_row(cell: dict, book, control) -> dict:
    bm, cm = book.metrics or {}, control.metrics or {}
    sb, sc = bm.get("sharpe"), cm.get("sharpe")
    return {
        "era": cell["era"], "cost_cell": cell["cost_cell"],
        "book_policy_id": cell["book"].policy_id,
        "control_policy_id": cell["control"].policy_id,
        "book_sharpe": sb, "control_sharpe": sc,
        "sharpe_advantage": (None if (sb is None or sc is None)
                             else round(sb - sc, 4)),
        "book_cagr_pct": bm.get("cagr_pct"), "control_cagr_pct": cm.get("cagr_pct"),
        "cagr_advantage_pp": (
            None if (bm.get("cagr_pct") is None or cm.get("cagr_pct") is None)
            else round(bm["cagr_pct"] - cm["cagr_pct"], 3)),
        "book_turnover_annual": bm.get("turnover_annual"),
        "control_turnover_annual": cm.get("turnover_annual"),
        "book_max_drawdown_pct": bm.get("max_drawdown_pct"),
        "book_total_cost_usd": bm.get("total_cost_usd"),
    }


def adjudicate(rows: list[dict], *, primary_cost: str = PRIMARY_COST) -> dict:
    """The decision rule, applied to the primary cost cell only.

    Written as a function of the ROWS so the same rule can be re-applied to an
    archived receipt without re-running the replay -- and so the rule is
    testable without a panel.
    """
    primary = [r for r in rows if r["cost_cell"] == primary_cost
               and r["sharpe_advantage"] is not None]
    if len(primary) < 2:
        return {"verdict": "CANNOT_DETERMINE", "n_eras_graded": len(primary),
                "reason": (f"{len(primary)} era(s) graded at the primary cost "
                           f"ruler {primary_cost}; the decision rule needs 2 of "
                           f"3 and a rule that decided on one era would be "
                           f"deciding on whichever era loaded")}
    wins = [r for r in primary if r["sharpe_advantage"] > 0]
    gross = [r for r in rows if r["cost_cell"] != primary_cost
             and (r["sharpe_advantage"] or 0) > 0]
    if len(wins) >= 2:
        verdict = "REPLICATES"
        reason = (f"{len(wins)}/{len(primary)} eras show a positive net Sharpe "
                  f"advantage over the drift-only control at {primary_cost}")
    elif len(gross) >= 2:
        verdict = "REPLICATES_GROSS_ONLY"
        reason = (f"only {len(wins)}/{len(primary)} eras clear at "
                  f"{primary_cost}, but {len(gross)} cheaper-cost cells do -- "
                  f"the cost is what killed it, and the rate is named")
    else:
        verdict = "DOES_NOT_REPLICATE"
        reason = (f"{len(wins)}/{len(primary)} eras show a positive net Sharpe "
                  f"advantage over the drift-only control at {primary_cost}")
    return {"verdict": verdict, "reason": reason, "n_eras_graded": len(primary),
            "n_eras_positive": len(wins),
            "median_sharpe_advantage": round(
                sorted(r["sharpe_advantage"] for r in primary)[len(primary) // 2], 4)}


def A_published_anomaly(smoke: bool = False, run: int = 1, *,
                        week: int = 1, name: str | None = None,
                        out_dir: Path | None = None) -> dict:
    t0 = time.time()
    anomaly = anomaly_of(None if name else week, name)
    prereg = prereg_state(anomaly)
    base = {
        "job": "A_published_anomaly", "licence": "RESEARCH_CLAIM",
        "llm_spend_usd": 0.0, "family_id": f"anomaly_{anomaly['name']}",
        "cadence_family": FAMILY,
        "week": anomaly["week"], "anomaly": anomaly["name"],
        "citation": anomaly["citation"],
        "published_direction": anomaly["published_direction"],
        "data_need": anomaly["data_need"],
        "prereg": prereg,
        "control": {"signal": DRIFT_ONLY_CONTROL,
                    "why": ("a book with the same number of the same kind of "
                            "names on the same calendar at the same costs, "
                            "sorted by something with no economic claim in "
                            "it, so the difference is about the SORT")},
        "eras": [e[0] for e in ERAS],
        "cost_cells": [_cell_label(c) for c in COST_CELLS],
        "primary_cost_cell": PRIMARY_COST,
        "smoke": bool(smoke),
        "written_utc": _now(),
    }

    if anomaly["signal"] is None:
        return {**base, "available": False,
                "headline": (f"week {anomaly['week']} ({anomaly['name']}) has no "
                             f"factor on this engine yet: {anomaly['data_need']}"),
                "verdict": ("NOT_RUNNABLE_YET: the factor this week needs is not "
                            "built. Named in the cadence table so it cannot be "
                            "quietly dropped."),
                "elapsed_s": round(time.time() - t0, 1)}

    if not prereg["present"]:
        return {**base, "available": False,
                "headline": f"week {anomaly['week']}: {prereg['why']}",
                "verdict": ("REFUSED: no pre-registration. A replication whose "
                            "plan is written after the data is loaded has a "
                            "free parameter in it -- the plan."),
                "elapsed_s": round(time.time() - t0, 1)}

    if not prereg["signed"] and not smoke:
        return {**base, "available": False,
                "headline": (f"week {anomaly['week']}: pre-registration present "
                             f"and UNSIGNED; the primary was NOT graded"),
                "verdict": ("REFUSED_PREREG_UNSIGNED: the plan exists and is "
                            "not signed. Run --smoke for the plumbing check, "
                            "whose verdict is not a verdict, or get the "
                            "signature."),
                "elapsed_s": round(time.time() - t0, 1)}

    eras = (("2013-2016", 2013, 2016),) if smoke else ERAS
    cells = era_cells(anomaly, eras)
    rows: list[dict] = []
    absent: list[str] = []
    for era in {(c["era"], c["start"], c["end"]) for c in cells}:
        label, lo, hi = era
        try:
            panel = load_panel(lo, hi, reduce_for_universe_n=500)
        except PanelUnavailable as exc:
            # AN ABSENT ERA IS REPORTED, NEVER SKIPPED. Deciding on the eras
            # that happened to load is deciding on the loader.
            absent.append(f"{label}: {exc}")
            continue
        mine = [c for c in cells if c["era"] == label]
        policies = [c["book"] for c in mine] + [c["control"] for c in mine]
        results = FARM.run_many(panel, policies, progress=False)
        by_id = {r.policy.policy_id: r for r in results}
        for c in mine:
            b, ctrl = by_id.get(c["book"].policy_id), by_id.get(c["control"].policy_id)
            if b is None or ctrl is None:
                continue
            rows.append(_pair_row(c, b, ctrl))

    decided = adjudicate(rows)
    if smoke:
        decided = {"verdict": "SMOKE_NOT_A_VERDICT",
                   "reason": ("a plumbing check on one short window against an "
                              "UNSIGNED pre-registration; it grades nothing and "
                              "is excluded from the trial's evidence"),
                   "smoke_would_have_said": decided}
    if absent:
        decided = {"verdict": "CANNOT_DETERMINE",
                   "reason": (f"{len(absent)} era(s) could not be loaded; a "
                              f"verdict on the rest would be a verdict on the "
                              f"loader. Absent: {absent}"),
                   "partial": decided}
    head = (f"week {anomaly['week']} {anomaly['name']}: {len(rows)} (era x cost) "
            f"cells vs the drift-only control; {decided['verdict']}")
    return {**base, "available": True, "rows": rows,
            "eras_absent": absent, **decided,
            "headline": head, "elapsed_s": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--anomaly", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = A_published_anomaly(smoke=a.smoke, run=a.run, week=a.week,
                                  name=a.anomaly)
    dest = (Path(a.out) if a.out else
            NIGHTS / f"night_factory_{datetime.now(timezone.utc):%Y-%m-%d}"
            / f"A_published_anomaly_w{payload['week']:02d}_run{a.run:02d}"
              f"{'_smoke' if a.smoke else ''}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"A_published_anomaly: {payload['headline']}\n"
          f"  verdict: {payload['verdict']}\n  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
