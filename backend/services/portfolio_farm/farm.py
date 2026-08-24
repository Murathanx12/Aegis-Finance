"""Run many policies over ONE panel, and rank what came back.

THE WHOLE POINT IS THE SHARED PANEL. Six hundred policies over fifteen years of
CRSP is six hundred replays and ONE load, ONE momentum grid, ONE volatility
grid. Recomputing the grids per policy is the difference between a coffee and
an overnight job, and it is also the difference between a farm you actually
search with and one you run twice and abandon.

WHAT THE LEADERBOARD IS ALLOWED TO SAY
======================================
It ranks. It does not conclude. Six hundred policies over one history is six
hundred draws, and the best of six hundred draws is high for the same reason
the tallest of six hundred people is tall. So:

  * every run includes the NULL policies (`random`, `equal`) at the SAME
    holding period, breadth, universe and costs, and `rank_report` prints the
    best null beside the best real signal. A winner that does not clear its own
    null is reported as not clearing it;
  * `n_policies` is on the receipt, because a top result is only interpretable
    against the number of tries that produced it;
  * nothing here computes a p-value, and nothing here may be quoted as alpha.
    A farm winner is a CANDIDATE for a frozen forward book (`CAPITAL_CANDIDATE`
    needs forward evidence; `RESEARCH_CLAIM` needs the full apparatus).

That is "explore dirty, promote clean" made mechanical: the dirt is allowed and
labelled, and the label travels with the number.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from backend.config import DATA_DIR
from backend.services.portfolio_farm import replay, signals as SIG
from backend.services.portfolio_farm.metrics import summarise, turnover_annual
from backend.services.portfolio_farm.panel import market_benchmark
from backend.services.portfolio_farm.policy import FarmResult, Policy

logger = logging.getLogger(__name__)

RESULTS_DIR = DATA_DIR / "optimus" / "portfolio_farm"


def run_many(panel, policies: list[Policy], *, progress: bool = True
             ) -> list[FarmResult]:
    """Replay every policy. Grids are computed once per DISTINCT signal."""
    t0 = time.perf_counter()
    # float32 everywhere the grid is only ever READ a row at a time. Halves the
    # resident set of a fifteen-year run; the row is widened at use.
    dolvol_ma = SIG._roll_mean(panel.dolvol.astype(np.float64), SIG.MONTH,
                               5).astype(np.float32)
    vol = SIG._vol_matrix(panel).astype(np.float32)
    grids: dict[tuple, np.ndarray] = {}
    for p in policies:
        key = (p.signal, p.signal_seed)
        if key not in grids:
            grids[key] = SIG.matrix(panel, p.signal,
                                    p.signal_seed).astype(np.float32)
    logger.info("portfolio_farm: %d grids for %d policies in %.1fs",
                len(grids), len(policies), time.perf_counter() - t0)

    bench = market_benchmark(panel.dates)
    out: list[FarmResult] = []
    for n, p in enumerate(policies, 1):
        res = replay.run(panel, p, sig=grids[(p.signal, p.signal_seed)],
                         dolvol_ma=dolvol_ma, vol=vol)
        nav = np.asarray(res.nav, dtype=float)
        w0 = len(panel.dates) - len(res.dates)
        res.metrics = summarise(res.dates, nav, panel, benchmark=bench[w0:])
        finite = nav[np.isfinite(nav)]
        res.metrics["turnover_annual"] = turnover_annual(
            res.diagnostics["traded_notional_usd"],
            float(finite.mean()) if finite.size else 0.0,
            res.metrics.get("years") or 0.0)
        res.metrics["total_cost_usd"] = round(
            res.diagnostics["total_cost_usd"], 2)
        res.metrics["is_null_control"] = p.signal in SIG.NULL_SIGNALS
        out.append(res)
        if progress and (n % 25 == 0 or n == len(policies)):
            logger.info("portfolio_farm: %d/%d (%.0fs)", n, len(policies),
                        time.perf_counter() - t0)
    return out


def rank_report(results: list[FarmResult], *, by: str = "terminal_usd",
                top: int = 25) -> dict:
    """The leaderboard, with its nulls attached rather than filtered out."""
    rows = [r.as_row() for r in results if r.metrics.get("status") == "ok"]
    rows.sort(key=lambda r: (r.get(by) is None, -(r.get(by) or 0)))
    reals = [r for r in rows if not r.get("is_null_control")]
    nulls = [r for r in rows if r.get("is_null_control")]
    best_real = reals[0] if reals else None
    best_null = nulls[0] if nulls else None
    bench = next((r.get("benchmark_terminal_usd") for r in rows
                  if r.get("benchmark_terminal_usd") is not None), None)
    null = null_distribution(nulls)
    pct = None
    if best_real and null["n"] >= 5:
        vals = np.asarray(null["terminals"], dtype=float)
        pct = round(100.0 * float((vals < best_real["terminal_usd"]).mean()), 1)
    return {
        "ranked_by": by,
        "n_policies": len(results),
        "n_ranked": len(rows),
        "benchmark_terminal_usd": bench,
        "best_real": best_real,
        "best_null": best_null,
        "null_distribution": null,
        #: Where the best REAL policy sits inside the null's own spread. This
        #: is the honest version of "beats_own_null": one random draw of twelve
        #: names has a terminal-wealth spread that routinely straddles any real
        #: signal, so beating ONE draw is a coin toss reported as a result.
        #: None when fewer than five null draws were run — and the absence is
        #: reported rather than defaulted, because a missing control is a
        #: finding about the run, not about the strategy.
        "best_real_percentile_in_null": pct,
        "beats_own_null": (
            None if not (best_real and best_null)
            else bool(best_real["terminal_usd"] > best_null["terminal_usd"])),
        "beats_market": (None if not (best_real and bench)
                         else bool(best_real["terminal_usd"] > bench)),
        "top": rows[:top],
        "all": rows,
    }


def null_distribution(null_rows: list[dict]) -> dict:
    """Terminal wealth across every null policy that ran.

    Reported as a SPREAD, never as a single number. `random` with one seed is
    one portfolio; the question a leaderboard has to answer is whether the best
    real signal sits outside what chance produces on the same universe, the
    same breadth, the same holding period and the same costs.
    """
    vals = sorted(float(r["terminal_usd"]) for r in null_rows
                  if r.get("terminal_usd") is not None)
    if not vals:
        return {"n": 0, "terminals": [],
                "note": "NO NULL RAN — nothing on this board has a control"}
    a = np.asarray(vals)
    return {
        "n": len(vals),
        "min": round(float(a.min()), 2),
        "p10": round(float(np.percentile(a, 10)), 2),
        "median": round(float(np.median(a)), 2),
        "p90": round(float(np.percentile(a, 90)), 2),
        "max": round(float(a.max()), 2),
        "terminals": [round(x, 2) for x in vals],
    }


def save(report: dict, name: str, *, dir_: Path | None = None) -> Path:
    d = dir_ or RESULTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return p


#: The axes that define "the same settings". A real policy is scored against
#: the nulls that share ALL of these; anything outside is a different game.
#:
#: THE DEFECT THIS REPLACED. The default used to be `("holding_days",)`, which
#: is right for the `holding` preset and wrong for every other one. The
#: `breadth` preset varies `top_k` from 3 to 50 and `sizing` across two values,
#: so all ten real policies were scored against one pooled null spanning every
#: breadth — and the printed table showed ten rows with IDENTICAL nullHi and
#: nullLo columns, which is what "not actually a comparison" looks like when
#: nothing raises. Grouping on the full tuple makes a mis-grouped run
#: impossible rather than merely unlikely.
GROUP_AXES = ("holding_days", "top_k", "sizing", "universe_n")


def compare_within_groups(results: list["FarmResult"], keys=GROUP_AXES,
                          ) -> list[dict]:
    """Score every real policy against the nulls THAT RAN AT ITS OWN SETTINGS.

    THE DEFECT THIS FIXES, MEASURED 2026-08-24. The first leaderboard pooled
    every null in the run into one distribution and compared the single best
    real policy to it. That is two errors at once:

      * a 1-session null pays ~45x/yr turnover in costs and a 252-session null
        pays almost none, so pooling them produces a "chance" distribution that
        is really a mixture of six different games. A real policy at h=1 was
        being scored against the easy half of that mixture;
      * comparing the MAX of the real policies to a percentile of the pooled
        nulls flatters the reals by exactly the multiple-comparison margin the
        percentile is supposed to measure.

    So the comparison is per GROUP — same holding period, same cost regime,
    same breadth — and every real policy gets its OWN percentile rather than
    the run getting one headline. The output is one row per real policy, which
    is also what makes the Micron question answerable: the h=1 row and the
    h=252 row are directly comparable because each is stated relative to its
    own chance baseline.
    """
    rows = [r.as_row() for r in results if r.metrics.get("status") == "ok"]

    def gkey(r):
        return tuple(r.get(k) for k in keys) + (bool(r.get("zero_cost_diagnostic")),)

    groups: dict[tuple, dict] = {}
    for r in rows:
        g = groups.setdefault(gkey(r), {"real": [], "null": []})
        g["null" if r.get("is_null_control") else "real"].append(r)

    def _pct(vals: np.ndarray, x: float):
        return (round(100.0 * float((vals < x).mean()), 1)
                if vals.size >= 5 else None)

    out = []
    for key, g in sorted(groups.items(), key=lambda kv: str(kv[0])):
        allnull = np.asarray([r["terminal_usd"] for r in g["null"]],
                             dtype=float)
        # THE TWO NULLS ARE NOT INTERCHANGEABLE AND ARE NOT POOLED.
        # `random` re-draws every formation date, so at a 1-session holding
        # period it re-ranks the whole universe daily and turns over ~492x/yr;
        # 12-1 momentum, whose ranks barely move day to day, turns over ~45x.
        # At 6 bps that is 29.5%/yr of cost for the null against 2.7% for the
        # strategy, and over 2013-2024 the churning null's median terminal
        # collapsed to $1,123 while momentum's was $36,623. Reported as
        # "momentum sits at the 100th percentile of chance", that comparison is
        # mostly a statement about turnover.
        # So `random_persistent` — one fixed random basket, near-zero turnover —
        # brackets the other end, and a real signal is asked to clear BOTH.
        hi = np.asarray([r["terminal_usd"] for r in g["null"]
                         if r["signal"] == "random"], dtype=float)
        lo = np.asarray([r["terminal_usd"] for r in g["null"]
                         if r["signal"] == "random_persistent"], dtype=float)
        for r in sorted(g["real"], key=lambda x: -x["terminal_usd"]):
            t = r["terminal_usd"]
            p_hi, p_lo = _pct(hi, t), _pct(lo, t)
            out.append({
                "group": dict(zip(list(keys) + ["zero_cost_diagnostic"], key)),
                "label": r["label"],
                "signal": r["signal"],
                "terminal_usd": t,
                "cagr_pct": r["cagr_pct"],
                "max_drawdown_pct": r["max_drawdown_pct"],
                "sharpe": r["sharpe"],
                "turnover_annual": r.get("turnover_annual"),
                "total_cost_usd": r.get("total_cost_usd"),
                "n_nulls": int(allnull.size),
                "null_median_usd": (round(float(np.median(allnull)), 2)
                                    if allnull.size else None),
                "null_p90_usd": (round(float(np.percentile(allnull, 90)), 2)
                                 if allnull.size else None),
                "null_hi_turnover_median_usd": (round(float(np.median(hi)), 2)
                                                if hi.size else None),
                "null_lo_turnover_median_usd": (round(float(np.median(lo)), 2)
                                                if lo.size else None),
                "percentile_vs_own_null": _pct(allnull, t),
                "percentile_vs_hi_turnover_null": p_hi,
                # The demanding one. Beating a null that pays almost no costs
                # means the SELECTION did something; beating only the churning
                # null can mean nothing more than trading less than it did.
                "percentile_vs_lo_turnover_null": p_lo,
                "clears_BOTH_nulls": (None if p_hi is None or p_lo is None
                                      else bool(p_hi >= 90 and p_lo >= 90)),
            })
    return out


def across_phases(results: list["FarmResult"]) -> list[dict]:
    """Collapse a phase sweep into one row per RULE, summarised by the median.

    A single phase is one draw from an arbitrary calendar alignment. Measured
    2013-2024 at k=12: 12-1 momentum returned $12,968 at a 21-session cycle and
    $38,817 at a 63-session one, and the difference is which sessions happened
    to be formation dates. Reporting one phase reports that coincidence.

    The median across every offset in the cycle is a property of the RULE. The
    spread (min..max) is reported beside it and is itself the finding — a rule
    whose phase spread is wider than its edge has not been shown to have one.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in results:
        if r.metrics.get("status") != "ok":
            continue
        row = r.as_row()
        key = (row["signal"], row["signal_seed"], row["holding_days"],
               row["top_k"], row["sizing"], row["universe_n"],
               bool(row["zero_cost_diagnostic"]))
        groups.setdefault(key, []).append(row)

    out = []
    for key, rows in groups.items():
        t = np.asarray([x["terminal_usd"] for x in rows], dtype=float)
        base = rows[0]
        out.append({
            "signal": key[0], "signal_seed": key[1], "holding_days": key[2],
            "top_k": key[3], "sizing": key[4], "universe_n": key[5],
            "zero_cost_diagnostic": key[6],
            "is_null_control": base.get("is_null_control"),
            "n_phases": len(rows),
            "terminal_median_usd": round(float(np.median(t)), 2),
            "terminal_min_usd": round(float(t.min()), 2),
            "terminal_max_usd": round(float(t.max()), 2),
            # How much of the answer is the calendar rather than the rule.
            "phase_spread_ratio": (round(float(t.max() / t.min()), 2)
                                   if t.min() > 0 else None),
            "turnover_annual": base.get("turnover_annual"),
            "label_phase0": base["label"],
        })
    out.sort(key=lambda r: (r["signal"], r["holding_days"], r["top_k"]))
    return out
