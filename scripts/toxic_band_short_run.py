"""TOXIC BAND SHORT -- can the toxic_ge_5 exclusion be monetised on the SHORT side?

THE QUESTION, STATED SO IT CAN LOSE
===================================
`toxic_ge_5` (analyst target/price ratio >= 5, after the $2/coverage-2 hygiene
gate) is the ONLY band effect that survives BH-FDR in the S36 self-attack
(`band_horizon_20260903.json`): excess_vw about -37%/yr with block t -6.25 at
one month, stable at every horizon, and MORE negative in 2022-2024. Today the
engine uses it as an exclusion rule -- "don't buy". A reliable
negative-expected-return population is economically bigger than a filter, IF a
short book survives the frictions that long books never meet:

* borrow cost -- we hold NO borrow-rate data, so borrow is modelled as
  EXPLICIT COST TIERS (0/2/5/10/20/50 %/yr) and every construction reports its
  BREAKEVEN borrow rate instead of pretending to know the realised one.
  Hard-to-borrow small-caps routinely sit at 20-100%+/yr;
* share availability -- many of these names are small, illiquid, and heavily
  shorted already. The receipt quantifies what fraction of the population is
  sub-$2 (unborrowable, and already excluded by the band's own hygiene gate),
  sub-$3 and below the $3m/day dollar-volume floor where a short is fictional;
* the distribution's own violence -- a short position's loss is unbounded.
  Worst period and worst name-months are first-class outputs, and a phase
  chain that passes through -100% is reported as RUIN, not as a smooth number.

THE BENCHMARK IS SHORT-THE-MARKET, NOT CASH
===========================================
A short book's alternative is shorting the index (SPY / VW market), not
sitting in cash. Every construction is therefore reported (i) against zero and
(ii) PAIRED against `-mkt_vw` over the same months. Note the identity: the
unit-hedged construction (short toxic + long $1 VW market) IS the paired
difference vs short-the-market -- the same object seen twice, stated so nobody
counts it as two findings.

SHORT ACCOUNTING CONVENTION (declared, and pinned by test)
==========================================================
$1 of short notional, fully collateralised; no leverage. Per holding period of
h months:

    gross     = -(equal-weighted cohort forward return)
    hedged    = gross + k * mkt_vw       k = 1 (unit) or cohort mean beta_pre
    trading   = sum|dw| x bps/side, old short weights DRIFTED by their realised
                short-leg return (1 - fwd), floored at zero (a name that more
                than doubles has consumed its short equity)
    borrow    = tier_annual x h/12, charged on the $1 short notional
    net(tier) = gross_or_hedged - trading - hedge_trading - borrow

Short rebate / collateral interest is NOT credited (rf ~ 0 convention of the
parent study); that makes every net number slightly conservative in the
2022-2024 rate era and says so here rather than quietly flattering the short.

WHOSE RULES
===========
Licence: PRODUCT_EXPERIMENT (post-hoc exploration allowed; PIT discipline,
leakage rules, explicit costs and receipts never relax). Nothing here trades,
sizes, seals or orders. Same PIT panel, investability definition, beta panel,
contamination clause and statistics (block t on date blocks, canon 58) as
`scripts/band_horizon_run.py` -- imported from it, not re-derived.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import benchmark as BM                              # noqa: E402
from learner import beta as B                                   # noqa: E402
from learner import dataset as D                                # noqa: E402
from scripts.band_horizon_run import (                          # noqa: E402
    ERAS, annualise, block_t, cohort_frame, contamination_months,
    max_drawdown, panel_ew_benchmark, series_stats,
)

RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
           / "toxic_band_short_20260905.json")
#: The receipt this one REPLACES.
SUPERSEDES = "toxic_band_short_20260904.json"

BAND = "toxic_ge_5"
#: Reg-T INITIAL margin. A short book's capital base is NOT its short notional.
#: Regulation T requires 50% equity against the long leg and 50% against the
#: short leg, so $1 short hedged with $k long needs 0.5 x (1 + k) of equity.
#: Dividing a hedged P&L by $1 (the old receipt's "hedged gross") both flatters
#: the return AND hides that the long leg was earning the equity premium.
REGT_INITIAL_LONG = 0.50
REGT_INITIAL_SHORT = 0.50
#: FINRA maintenance minima, reported as a sensitivity only. Running a book at
#: maintenance margin is running it one tick from a forced close, so it is a
#: BOUND on leverage, never a plan.
MAINT_LONG = 0.25
MAINT_SHORT = 0.30
#: The price floor the toxic cell MUST be reported at (VERIFICATION SS4).
PRICE_FLOORS = (0.0, 2.0, 5.0, 10.0)
HORIZONS = (1, 3, 6, 12)
#: Annual borrow-fee tiers, %/yr. There is NO borrow data in this repo; these
#: are explicit assumptions, and the breakeven rate is the headline instead.
BORROW_TIERS_PCT = (0.0, 2.0, 5.0, 10.0, 20.0, 50.0)
TRADE_COST_BPS = 10.0            # per side, the parent study's primary
TRADE_COST_BPS_SENS = 25.0       # per side, sensitivity
HEDGE_COST_BPS = 1.0             # per side on the index hedge leg (SPY-like)
LIQ_FLOOR_USD = 3_000_000.0      # $/day; the S29 universe floor
N_WORST_NAME_MONTHS = 10


# ----------------------------------------------------------- pure mechanics
# Kept as small pure functions so backend/tests/test_toxic_band_short.py can
# pin them offline without touching the panel.

def borrow_cost_per_period(rate_annual_pct: float, h: int) -> float:
    """Borrow fee for one h-month holding period, on $1 of short notional.
    Linear in time: fee quotes are ACT/360-ish simple rates, not compounded."""
    return (rate_annual_pct / 100.0) * h / 12.0


def breakeven_borrow_rate_pct(mean_net_of_trading_per_period: float, h: int) -> float:
    """The annual borrow rate (%/yr) at which the mean per-period return, net
    of trading costs but gross of borrow, is exactly consumed."""
    return float(mean_net_of_trading_per_period * 12.0 / h * 100.0)


def drifted_short_weights(w_old: pd.Series, fwd_old: pd.Series) -> pd.Series:
    """Old short weights drifted by their realised SHORT-leg return.

    A short position's equity moves with (1 - fwd); a name that more than
    doubled has consumed its short equity, so the drifted weight floors at 0.
    Re-normalised to sum to 1 (the book re-margins to $1 short notional)."""
    drifted = (w_old * (1.0 - fwd_old.reindex(w_old.index))).clip(lower=0.0)
    tot = drifted.sum()
    if tot <= 0:
        return pd.Series(0.0, index=w_old.index)
    return drifted / tot


def short_turnover(w_new: pd.Series, w_old_drifted: pd.Series) -> float:
    """sum|dw| between the drifted old short weights and the new ones. Counts
    the cover leg and the new-short leg, so one multiplication by bps-per-side
    is the whole round trip -- same convention as the parent study."""
    allp = w_new.index.union(w_old_drifted.index)
    return float(np.abs(w_new.reindex(allp).fillna(0.0)
                        - w_old_drifted.reindex(allp).fillna(0.0)).sum())


def regt_capital(short_notional: float, long_notional: float,
                 maintenance: bool = False) -> float:
    """Equity a Reg-T account must hold for this pair. The DENOMINATOR.

    The old receipt reported the beta-hedged construction as "+76.6%/yr hedged
    gross" -- a P&L per $1 of SHORT notional, with a 1.48x long market leg
    financed out of thin air. Two things were wrong at once: about +27%/yr of it
    was the equity premium the long leg earned (which `beta_matched` prices), and
    the capital that leg requires never appeared in the denominator. This
    function is the second half of that repair; `-resid` is the first.
    """
    fl, fs = (MAINT_LONG, MAINT_SHORT) if maintenance else (REGT_INITIAL_LONG,
                                                            REGT_INITIAL_SHORT)
    cap = fs * abs(short_notional) + fl * abs(long_notional)
    return float(max(cap, 1e-9))


def hedge_return(mkt: float, k: float) -> float:
    """Return of the long hedge leg: k dollars of VW market per $1 short."""
    return k * mkt


def chain_wealth(net: np.ndarray) -> tuple[np.ndarray, bool]:
    """Compound $1 through a sequence of per-period net returns. A factor
    <= 0 is RUIN: wealth goes to 0 and STAYS there -- a wiped account does not
    keep compounding."""
    w, ruined, out = 1.0, False, []
    for r in net:
        if not ruined:
            w = w * (1.0 + r)
            if w <= 0.0:
                w, ruined = 0.0, True
        out.append(w)
    return np.asarray(out), ruined


# ------------------------------------------------------- book construction

def short_book(c: pd.DataFrame, h: int, trade_cost_bps: float = TRADE_COST_BPS,
               hedge: str | None = None,
               hedge_cost_bps: float = HEDGE_COST_BPS) -> pd.DataFrame:
    """Monthly-formed equal-weighted SHORT book of the cohort, held h months.

    One row per formation month: gross short return, hedged return where
    requested, trading cost, and the components needed for the receipt.
    `hedge` is None (naive), 'unit' ($1 market per $1 short) or 'beta'
    (cohort mean beta_pre dollars of market per $1 short).
    """
    if hedge not in (None, "unit", "beta"):
        raise ValueError(f"unknown hedge {hedge!r}")
    months = sorted(c["month"].unique())
    holdings = {m: g for m, g in c.groupby("month")}
    rows = []
    for i, m in enumerate(months):
        g = holdings[m]
        n = len(g)
        if n == 0:
            continue
        long_ret = float(g["fwd"].mean())
        mkt = float(g["mkt_vw"].mean())
        beta_mean = float(g["beta_pre"].mean())
        k = 0.0 if hedge is None else (1.0 if hedge == "unit" else beta_mean)
        # THE HEADLINE OBJECT. `resid` is computed per name in cohort_frame as
        # fwd - beta_pre x mkt_vw, so -resid IS the short's return with the
        # equity premium its own beta bought already removed -- per name, not at
        # the cohort mean. This is what the receipt reports; "hedged gross" is a
        # decomposition line and never a headline.
        resid_mean = float(g["resid"].mean())
        rec = {
            "month": m, "n_names": n,
            "long_ret": long_ret, "mkt_vw": mkt, "beta_mean": beta_mean,
            "gross_short": -long_ret,
            "hedge_k": k,
            "gross": -long_ret + hedge_return(mkt, k),
            "minus_resid": -resid_mean,
            # what the leverage ALONE earns: beta x market + (1-beta) x rf, with
            # rf = 0.0 DECLARED (the parent study's convention). Quoted beside
            # every short number so nobody re-books the equity premium as alpha.
            "beta_matched_leg": beta_mean * mkt,
        }
        if i - h >= 0:
            pg = holdings[months[i - h]]
            w_old = pd.Series(1.0 / len(pg), index=pg["permno"].to_numpy())
            fwd_old = pd.Series(pg["fwd"].to_numpy(), index=pg["permno"].to_numpy())
            w_new = pd.Series(1.0 / n, index=g["permno"].to_numpy())
            rec["turnover"] = short_turnover(
                w_new, drifted_short_weights(w_old, fwd_old))
        else:
            rec["turnover"] = np.nan
        rows.append(rec)
    bk = pd.DataFrame(rows).set_index("month")
    med = (float(np.nanmedian(bk["turnover"]))
           if len(bk) and bk["turnover"].notna().any() else 0.0)
    bk["trade_cost"] = bk["turnover"].fillna(med) * (trade_cost_bps / 10_000.0)
    # Hedge leg cost: an UPPER BOUND of full replacement every period at
    # hedge_cost_bps per side. On a $|k| index position that is 2 x k x 1bp;
    # ~0.02%/period, quoted rather than omitted.
    bk["hedge_cost"] = np.abs(bk["hedge_k"]) * 2.0 * (hedge_cost_bps / 10_000.0)
    bk["net_of_trading"] = bk["gross"] - bk["trade_cost"] - bk["hedge_cost"]
    # THE REPORTED SERIES: -resid, netted for trading and the hedge leg, then
    # divided by the Reg-T equity the pair actually ties up. A short leg of $1
    # against a long leg of beta dollars needs 0.5 x (1 + beta) of equity.
    bk["minus_resid_net_of_trading"] = (
        bk["minus_resid"] - bk["trade_cost"] - bk["hedge_cost"])
    bk["regt_capital"] = [regt_capital(1.0, b) for b in bk["beta_mean"]]
    bk["maint_capital"] = [regt_capital(1.0, b, maintenance=True)
                           for b in bk["beta_mean"]]
    bk["minus_resid_net_on_regt"] = (
        bk["minus_resid_net_of_trading"] / bk["regt_capital"])
    bk["minus_resid_net_on_maint"] = (
        bk["minus_resid_net_of_trading"] / bk["maint_capital"])
    bk.attrs["median_turnover"] = med
    return bk


def net_series(bk: pd.DataFrame, tier_pct: float, h: int) -> pd.Series:
    """Per-period net return at one borrow tier: trading-netted return minus
    the borrow fee on the $1 short leg (the hedge leg pays no borrow)."""
    return bk["net_of_trading"] - borrow_cost_per_period(tier_pct, h)


def resid_net_on_capital(bk: pd.DataFrame, tier_pct: float, h: int,
                         maintenance: bool = False) -> pd.Series:
    """`-resid`, net of trading AND borrow, ON REG-T CAPITAL. The headline.

    The borrow fee is charged on the $1 short notional and then divided by the
    same capital base as the P&L -- charging it on capital instead would quietly
    shrink it by the leverage factor.
    """
    cap = bk["maint_capital"] if maintenance else bk["regt_capital"]
    return (bk["minus_resid_net_of_trading"]
            - borrow_cost_per_period(tier_pct, h)) / cap


def phase_chains_short(bk: pd.DataFrame, h: int, col_or_series, tier_pct: float | None = None) -> dict:
    """Terminal wealth / max drawdown / ruin per non-overlapping phase chain."""
    s_all = bk[col_or_series] if isinstance(col_or_series, str) else col_or_series
    out = []
    for p in range(h):
        s = s_all.iloc[p::h].dropna()
        if len(s) < 2:
            continue
        w, ruined = chain_wealth(s.to_numpy())
        out.append({"phase": p, "n_rebalances": int(len(s)),
                    "terminal_wealth": round(float(w[-1]), 4),
                    "max_drawdown": round(max_drawdown(w[w > 0]) if (w > 0).any() else -1.0, 4),
                    "ruined": bool(ruined)})
    if not out:
        return {"phases": []}
    tw = [o["terminal_wealth"] for o in out]
    return {"phases": out,
            "terminal_wealth_median": round(float(np.median(tw)), 4),
            "terminal_wealth_min": round(float(np.min(tw)), 4),
            "terminal_wealth_max": round(float(np.max(tw)), 4),
            "max_drawdown_worst": round(float(np.min([o["max_drawdown"] for o in out])), 4),
            "n_ruined_phases": int(sum(o["ruined"] for o in out)),
            "n_phases": len(out)}


# ------------------------------------------------------------ the analysis

def _era_block(x: pd.Series, h: int) -> dict:
    yr = pd.Series([int(m[:4]) for m in x.index], index=x.index)
    out = {}
    for name, (lo, hi) in ERAS.items():
        st = series_stats(x.loc[(yr >= lo) & (yr <= hi)], h, name)
        out[name] = {"n_months": st.get("n_months"),
                     "annualised_pct": st.get("annualised_pct"),
                     "t_block": st.get("t_block")}
    return out


def analyse_construction(bk: pd.DataFrame, h: int, label: str) -> dict:
    """Everything the receipt reports for one (construction, horizon)."""
    gross = bk["gross"].dropna()
    paired_vs_short_mkt = (bk["gross_short"] - (-bk["mkt_vw"])).dropna()
    net_of_trading = bk["net_of_trading"].dropna()
    mean_not = float(net_of_trading.mean())

    tiers = {}
    for tier in BORROW_TIERS_PCT:
        ns = net_series(bk, tier, h).dropna()
        st = series_stats(ns, h, f"net@{tier:g}%")
        ch = phase_chains_short(bk, h, ns, tier)
        tiers[f"{tier:g}"] = {
            "annualised_pct": st.get("annualised_pct"),
            "t_block": st.get("t_block"),
            "terminal_wealth_median": ch.get("terminal_wealth_median"),
            "terminal_wealth_min": ch.get("terminal_wealth_min"),
            "max_drawdown_worst": ch.get("max_drawdown_worst"),
            "n_ruined_phases": ch.get("n_ruined_phases"),
        }

    # THE HEADLINE: -resid on Reg-T capital, by borrow tier.
    resid_tiers = {}
    for tier in BORROW_TIERS_PCT:
        rs = resid_net_on_capital(bk, tier, h).dropna()
        st = series_stats(rs, h, f"minus_resid_on_regt@{tier:g}%")
        ch = phase_chains_short(bk, h, rs, tier)
        resid_tiers[f"{tier:g}"] = {
            "annualised_pct": st.get("annualised_pct"),
            "t_block": st.get("t_block"),
            "n_effective_date_blocks": st.get("n_effective_date_blocks"),
            "terminal_wealth_median": ch.get("terminal_wealth_median"),
            "terminal_wealth_min": ch.get("terminal_wealth_min"),
            "max_drawdown_worst": ch.get("max_drawdown_worst"),
            "n_ruined_phases": ch.get("n_ruined_phases"),
        }
    resid_maint = {}
    for tier in (0.0, 20.0):
        rs = resid_net_on_capital(bk, tier, h, maintenance=True).dropna()
        st = series_stats(rs, h, f"minus_resid_on_maint@{tier:g}%")
        resid_maint[f"{tier:g}"] = {"annualised_pct": st.get("annualised_pct"),
                                    "t_block": st.get("t_block")}
    mr_net = bk["minus_resid_net_of_trading"].dropna()

    worst_i = net_of_trading.idxmin()
    best_i = net_of_trading.idxmax()
    return {
        "label": label,
        # ---------------- what this receipt REPORTS ----------------
        "HEADLINE_minus_resid_on_regt_capital": {
            "definition": ("-mean(resid) per formation month, where resid = fwd - "
                           "beta_pre x mkt_vw PER NAME; netted for trading and the hedge "
                           "leg; divided by the Reg-T equity the pair ties up, "
                           f"{REGT_INITIAL_SHORT:g} x $1 short + {REGT_INITIAL_LONG:g} x "
                           "$beta long."),
            "mean_regt_capital_per_dollar_short": round(float(bk["regt_capital"].mean()), 4),
            "on_regt_capital_by_borrow_tier_pct": resid_tiers,
            "on_maintenance_margin_SENSITIVITY_ONLY": resid_maint,
            "breakeven_borrow_rate_pct_on_notional": round(
                breakeven_borrow_rate_pct(float(mr_net.mean()), h), 2),
            "minus_resid_net_of_trading_on_NOTIONAL_decomposition_only":
                series_stats(mr_net, h, "minus_resid_net_notional"),
        },
        "beta_matched_benchmark": {
            "what_it_is": ("beta x market + (1 - beta) x rf with rf = 0.0 DECLARED "
                           "(learner.benchmark.beta_matched). This is what the long hedge "
                           "leg earns for holding leverage and NOTHING else."),
            "leg_annualised_pct": series_stats(
                bk["beta_matched_leg"].dropna(), h, "beta_matched_leg").get("annualised_pct"),
            "leg_t_block": series_stats(
                bk["beta_matched_leg"].dropna(), h, "beta_matched_leg").get("t_block"),
            "mean_beta": round(float(bk["beta_mean"].mean()), 4),
            "why_it_is_here": ("the superseded receipt reported this construction as "
                               "'+76.6%/yr hedged gross'. That number embedded this leg "
                               "(about +27%/yr of equity premium on a ~1.48x long market "
                               "position) and divided by $1 instead of by the capital the "
                               "pair requires. -resid removes the leg; Reg-T capital fixes "
                               "the denominator. NEVER report hedged gross."),
        },
        "hedged_gross_DECOMPOSITION_ONLY_NEVER_A_HEADLINE": {
            "status": "DO NOT QUOTE",
            "why": ("a P&L per $1 of SHORT notional with an unfunded long market leg. It "
                    "is retained only so the arithmetic path from the void receipt to this "
                    "one is visible."),
        },
        "n_periods": int(len(gross)),
        "median_names_per_month": int(bk["n_names"].median()),
        "mean_beta_pre": round(float(bk["beta_mean"].mean()), 4),
        "mean_hedge_k": round(float(bk["hedge_k"].mean()), 4),
        "turnover_sum_abs_dw_median": round(bk.attrs["median_turnover"], 4),
        "trade_cost_annualised_pct": round(
            100.0 * float(bk["trade_cost"].mean()) * 12.0 / h, 3),
        "gross": series_stats(gross, h, "gross"),
        "vs_short_market_paired": series_stats(paired_vs_short_mkt, h, "paired"),
        "net_of_trading_10bps": series_stats(net_of_trading, h, "net_of_trading"),
        "net_by_borrow_tier_pct": tiers,
        "breakeven_borrow_rate_pct_after_10bps_trading":
            round(breakeven_borrow_rate_pct(mean_not, h), 2),
        "worst_period": {"month": str(worst_i),
                         "net_of_trading_pct": round(100.0 * float(net_of_trading.min()), 2)},
        "best_period": {"month": str(best_i),
                        "net_of_trading_pct": round(100.0 * float(net_of_trading.max()), 2)},
        "terminal_wealth_gross": phase_chains_short(bk, h, "gross"),
        "era_splits_net_of_trading": _era_block(net_of_trading, h),
        "era_breakeven_borrow_rate_pct": {
            name: round(breakeven_borrow_rate_pct(float(sub.mean()), h), 2)
            for name, sub in (
                (nm, net_of_trading.loc[
                    (pd.Series([int(m[:4]) for m in net_of_trading.index],
                               index=net_of_trading.index) >= lo)
                    & (pd.Series([int(m[:4]) for m in net_of_trading.index],
                                 index=net_of_trading.index) <= hi)])
                for nm, (lo, hi) in ERAS.items())
            if len(sub) >= 3},
    }


def realism_fractions(df: pd.DataFrame) -> dict:
    """How much of the toxic population could actually be borrowed and shorted.

    Two populations, because they are different objects:
      * the RAW ratio>=5 population, hygiene ignored -- the distribution the
        toxicity claim is ABOUT;
      * the BAND cohort (band == toxic_ge_5, split-free, matured 1m target) --
        the rows a book could actually form on. Hygiene already bars close<$2,
        so the sub-$2 fraction HERE is structurally 0; the interesting
        fractions are price bands just above $2 and the liquidity floor.
    """
    dv = np.expm1(df["log_dollar_vol_20d"])
    raw = df[df["ratio"] >= 5.0]
    raw_dv = dv.loc[raw.index]
    band = df[(df["band"] == BAND) & (~df["split_prior_year"].astype(bool))
              & df["fwd_1m"].notna()]
    band_dv = dv.loc[band.index]

    def frac(mask) -> float:
        return round(float(mask.mean()), 4) if len(mask) else float("nan")

    return {
        "note": ("borrow availability is NOT observed in this repo; these are "
                 "structural proxies. Sub-$2 names are widely unborrowable; "
                 "sub-$3m/day dollar volume is the S29 universe floor below "
                 "which the panel's own edge band was declared UNOBSERVED and "
                 "a short of size is fictional."),
        "raw_ratio_ge_5_population": {
            "name_months": int(len(raw)),
            "share_close_below_2": frac(raw["close"] < 2.0),
            "share_close_below_3": frac(raw["close"] < 3.0),
            "share_close_below_5": frac(raw["close"] < 5.0),
            "share_dollar_vol_below_1m": frac(raw_dv < 1e6),
            "share_dollar_vol_below_3m": frac(raw_dv < LIQ_FLOOR_USD),
            "share_market_cap_below_100m": frac(raw["market_cap"] < 1e8),
            "share_market_cap_below_300m": frac(raw["market_cap"] < 3e8),
        },
        "band_cohort_split_free_matured_1m": {
            "name_months": int(len(band)),
            "share_close_below_2_STRUCTURALLY_ZERO": frac(band["close"] < 2.0),
            "share_close_below_3": frac(band["close"] < 3.0),
            "share_close_below_5": frac(band["close"] < 5.0),
            "share_dollar_vol_below_1m": frac(band_dv < 1e6),
            "share_dollar_vol_below_3m": frac(band_dv < LIQ_FLOOR_USD),
            "share_market_cap_below_100m": frac(band["market_cap"] < 1e8),
            "share_market_cap_below_300m": frac(band["market_cap"] < 3e8),
            "share_passing_3m_liquidity_floor": frac(band_dv >= LIQ_FLOOR_USD),
        },
    }


def price_floor_short_ladder(cb: pd.DataFrame, h: int, hedge: str | None,
                             trade_cost_bps: float) -> dict:
    """The short's headline AT A LADDER OF PRICE FLOORS. Mandatory.

    84% of the point-in-time toxic cell trades under $5 (median close $3.08). A
    short of a $3 microcap is the least borrowable, least liquid, most expensive
    trade on the tape, so the row that matters most is the one with the fewest
    names in it -- and it is reported here rather than left to be discovered.
    """
    out = {"_cost_realism": (
        f"every row is netted at {trade_cost_bps:g}bps per side. Below $5 that is "
        "FICTION -- a realistic round trip on a $3 microcap is 50-200bps, and the "
        "borrow on a hard-to-borrow microcap is 20-100%+/yr, which is why the "
        "BREAKEVEN borrow rate rather than a netted return is the honest headline. "
        "Rows whose population is mostly sub-$5 are UPPER BOUNDS.")}
    if "close" not in cb.columns:
        return {"status": "CANNOT DETERMINE (no close column)"}
    for f in PRICE_FLOORS:
        g = cb if f <= 0 else cb[cb["close"] >= f]
        if g["month"].nunique() < 12:
            out[f"close_ge_{f:g}"] = {"status": "TOO_FEW_MONTHS",
                                      "months": int(g["month"].nunique()),
                                      "name_months": int(len(g))}
            continue
        bk = short_book(g, h, trade_cost_bps, hedge=hedge)
        rs0 = resid_net_on_capital(bk, 0.0, h).dropna()
        rs20 = resid_net_on_capital(bk, 20.0, h).dropna()
        st0 = series_stats(rs0, h, f"regt_ge_{f:g}")
        out[f"close_ge_{f:g}"] = {
            "name_months": int(len(g)),
            "n_months": int(len(bk)),
            "median_names_per_month": int(bk["n_names"].median()),
            "minus_resid_on_regt_zero_borrow_annualised_pct": st0.get("annualised_pct"),
            "t_block": st0.get("t_block"),
            "n_effective_date_blocks": st0.get("n_effective_date_blocks"),
            "minus_resid_on_regt_at_20pct_borrow_annualised_pct":
                series_stats(rs20, h, "r20").get("annualised_pct"),
            "median_monthly_pct": round(100.0 * float(rs0.median()), 4),
            "mean_monthly_pct": round(100.0 * float(rs0.mean()), 4),
            "breakeven_borrow_rate_pct": round(breakeven_borrow_rate_pct(
                float(bk["minus_resid_net_of_trading"].mean()), h), 2),
            "era_splits": _era_block(rs0, h),
        }
    pr = cb["close"].dropna()
    out["_population"] = {
        "name_months": int(len(cb)),
        "median_close": round(float(pr.median()), 3) if len(pr) else None,
        "share_close_below_5": round(float((pr < 5.0).mean()), 4) if len(pr) else None,
    }
    return out


def worst_name_months(c1: pd.DataFrame, n: int = N_WORST_NAME_MONTHS) -> list:
    """The squeeze table: the cohort name-months a 1-month short would have
    been hurt worst by. `fwd` here is the LONG return; the short lost fwd."""
    w = c1.nlargest(n, "fwd")
    return [{"permno": int(r.permno), "month": r.month,
             "fwd_1m_pct": round(100.0 * float(r.fwd), 1),
             "ratio": round(float(r.ratio), 2),
             "market_cap_musd": round(float(r.market_cap) / 1e6, 1)}
            for r in w.itertuples()]


# ------------------------------------------------------------------- the run

def run(trade_cost_bps: float = TRADE_COST_BPS) -> dict:
    t0 = datetime.now(timezone.utc)
    print("loading the learner's PIT table ...")
    df = pd.read_parquet(D.TRAIN_TABLE)
    print(f"  {len(df):,} rows x {df.shape[1]} cols")
    df["beta_pre"] = B.attach(df, B.load())
    split_free = ~df["split_prior_year"].astype(bool)
    dv = np.expm1(df["log_dollar_vol_20d"])
    df["dollar_vol_20d_usd"] = dv

    schema_hash = (str(df["schema_hash"].iloc[0])
                   if "schema_hash" in df.columns and len(df) else None)
    receipt: dict = {
        "artefact": "TOXIC_BAND_SHORT_V2_MINUS_RESID_ON_REGT_CAPITAL",
        "written_at_utc": t0.isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "supersedes": SUPERSEDES,
        "supersedes_reason": (
            "the superseded receipt is void twice over. (1) It was computed on "
            "`learner-train-table-1`, whose `ratio` divided the SPLIT-ADJUSTED IBES "
            "consensus by the RAW close, so `toxic_ge_5` was largely a "
            "FUTURE-REVERSE-SPLIT detector -- 74.4% of its 26,199 name-months carried "
            "one, and the short it priced was a short of names that were about to "
            "reverse-split. (2) Its headline was '+76.6%/yr hedged gross', a P&L per $1 "
            "of SHORT notional against an unfunded ~1.48x LONG market leg; roughly "
            "+27%/yr of that was the equity premium the long leg earned, and the capital "
            "the pair requires never entered the denominator. This receipt reports "
            "-resid on Reg-T capital and quotes the beta_matched leg beside it. The old "
            "file is sealed and unedited; it carries a SUPERSEDED_BY sidecar."),
        "panel": {
            "table": "backend/data/optimus/learner/train_table.parquet",
            "schema_version": "learner-train-table-2",
            "schema_hash": schema_hash,
            "rebuild_receipt": "backend/data/optimus/tracker_backtest/panel_rebuild_20260904.json",
            "numerator": "ibes__ptgsumu (UNADJUSTED IBES consensus mean target)",
            "denominator": "raw CRSP dsf close (prc), same share basis",
            "toxic_ge_5_name_months": int(((df["band"] == BAND)).sum()),
            "toxic_ge_5_name_months_on_the_void_panel": 26199,
            "known_open_limitation": (
                "`build_monthly` drops a dying name's FINAL month (`fwd_1m` needs a next "
                "monthly row). For a SHORT this cuts the RIGHT way and the wrong way at "
                "once: the missing month is usually a large negative return, which a short "
                "would have EARNED, so every short number here is CONSERVATIVE by that "
                "amount -- and the delisting incidence of the PIT toxic band is 1.79%, the "
                "highest of any band, so the omission is largest exactly here. Named, not "
                "absorbed."),
        },
        BM.STAMP_KEY: BM.declare(
            "beta_matched",
            construction=(
                "beta_matched = beta_pre x vw_crsp_common_main + (1 - beta_pre) x rf with "
                "rf = 0.0 DECLARED (a daily slope's risk-free cancels; the parent study's "
                "convention). The market leg is the value-weighted CRSP common-stock / "
                "main-exchange total return from learner.dataset.market_indices, compounded "
                "over each name's h-month forward window and carried on the panel as "
                "`mkt_vw_{h}m`; `resid = fwd - beta_pre x mkt_vw` is that leg SUBTRACTED "
                "per name. Declared rather than re-derived because this receipt reads the "
                "panel column, not the series."),
            span=[str(min(df["month"])), str(max(df["month"]))],
            n_periods=int(df["month"].nunique()),
            freq="M",
            beta_source="learner/beta_panel.parquet, OLS on daily VW market, window ends "
                        "strictly before entry_date",
            secondary_legs={
                "vw_crsp_common_main": "the short-the-market control, `short_market_control`",
                "matched:short_the_vw_market": "-mkt_vw over the same months",
            }),
        "void_columns": {
            "columns": ["prior_*", "resid_vw_*", "resid_ew_*"],
            "status": "VOID",
            "why": ("BAND_PRIOR v2 expectations, fitted on the corrupted ratio. Nothing "
                    "here reads one. The `resid` this receipt shorts is recomputed as "
                    "fwd - beta_pre x mkt_vw -- a BETA residual with no prior in it."),
        },
        "question": ("can the toxic_ge_5 exclusion be monetised on the short "
                     "side, or do borrow costs and the distribution's own "
                     "violence erase it?"),
        "parent_receipts": [
            "backend/data/optimus/tracker_backtest/band_horizon_20260903.json",
            "backend/data/optimus/tracker_backtest/upside_band_decontamination.json"],
        "dataset": {"table": str(D.TRAIN_TABLE.relative_to(REPO)),
                    "rows": int(len(df)), "months": int(df["month"].nunique()),
                    "window": "2013-2024",
                    "universe": "PRIMARY: split_prior_year == False (S30b), band "
                                "labelled by learner.prior.effective_band (hygiene "
                                "close>=$2, coverage>=2 already applied)",
                    "investable": "matured fwd target + market leg + pre-period beta "
                                  "(cohort_frame, PREREG_BAND_IS_BETA_1 convention)"},
        "conventions": {
            "short_accounting": "$1 short notional, fully collateralised, no leverage; "
                                "gross = -(EW cohort fwd); hedged adds k x mkt_vw long",
            "trade_cost_bps_per_side": trade_cost_bps,
            "trade_cost_sensitivity_bps": TRADE_COST_BPS_SENS,
            "hedge_cost_bps_per_side": HEDGE_COST_BPS,
            "borrow_tiers_pct_per_year": list(BORROW_TIERS_PCT),
            "borrow_note": "NO borrow-rate data exists in this repo. Tiers are "
                           "assumptions; the BREAKEVEN borrow rate is the honest "
                           "headline. Hard-to-borrow small caps live at 20-100%+/yr.",
            "rebate_note": "short rebate / collateral interest NOT credited (rf~0 "
                           "convention of the parent study); conservative in 2022-24.",
            "benchmark": "short-the-VW-market over the same months -- a short book's "
                         "alternative is shorting SPY, not cash. The unit-hedged "
                         "construction IS the paired difference vs that benchmark.",
            "ruin": "a phase chain passing through wealth <= 0 reports RUIN and stays "
                    "at 0; it does not compound back.",
            "zero_cost_diagnostic": False,
        },
        "population_realism": realism_fractions(df),
    }

    constructions = {
        "naive_short": {"hedge": None, "liq_floor": False},
        "hedged_unit": {"hedge": "unit", "liq_floor": False},
        "hedged_beta": {"hedge": "beta", "liq_floor": False},
        "liq_floored_naive": {"hedge": None, "liq_floor": True},
        "liq_floored_hedged_beta": {"hedge": "beta", "liq_floor": True},
    }

    out: dict = {}
    ctrl: dict = {}
    ladders: dict = {}
    n_cells = 0
    for h in HORIZONS:
        pew = panel_ew_benchmark(df[split_free], h)
        c = cohort_frame(df[split_free].assign(
            dollar_vol_20d_usd=df.loc[split_free, "dollar_vol_20d_usd"]), h, pew)
        # cohort_frame drops the liquidity column (fixed list) -- re-attach.
        # cohort_frame carries `close` and `log_dollar_vol_20d` itself since the
        # B1 rebuild, so only the derived dollar-volume column is re-attached --
        # merging `close` again would produce close_x / close_y and silently
        # break every price-floor row.
        need_merge = ["month", "permno", "dollar_vol_20d_usd"]
        if "close" not in c.columns:
            need_merge.append("close")
        c = c.merge(df.loc[split_free, need_merge].drop_duplicates(["month", "permno"]),
                    on=["month", "permno"], how="left")
        contam = contamination_months(df[split_free], df.loc[split_free, "band"] == BAND, h)
        cb = c[(c["band"] == BAND) & (~c["month"].isin(contam["excluded_months"]))]
        if h == 1:
            receipt["squeeze_table_worst_name_months_1m"] = worst_name_months(cb)
            receipt["contamination_clause"] = contam
        # short-the-market control, same months as the naive cohort
        mkt_m = cb.groupby("month")["mkt_vw"].mean()
        ctrl[f"{h}m"] = {
            "short_market_return": series_stats(-mkt_m, h, "short_mkt"),
            "terminal_wealth_short_market": phase_chains_short(
                pd.DataFrame({"g": -mkt_m}), h, "g"),
        }
        for name, cfg in constructions.items():
            g = cb[cb["dollar_vol_20d_usd"] >= LIQ_FLOOR_USD] if cfg["liq_floor"] else cb
            if g["month"].nunique() < 24:
                out.setdefault(name, {})[f"{h}m"] = {
                    "status": "TOO_FEW_MONTHS", "months": int(g["month"].nunique())}
                continue
            bk = short_book(g, h, trade_cost_bps, hedge=cfg["hedge"])
            entry = analyse_construction(bk, h, f"{name}@{h}m")
            # 25bps trading sensitivity: only the breakeven moves.
            bk25 = short_book(g, h, TRADE_COST_BPS_SENS, hedge=cfg["hedge"])
            entry["breakeven_borrow_rate_pct_after_25bps_trading"] = round(
                breakeven_borrow_rate_pct(float(bk25["net_of_trading"].mean()), h), 2)
            out.setdefault(name, {})[f"{h}m"] = entry
            n_cells += len(BORROW_TIERS_PCT)
            if name in ("hedged_beta", "naive_short"):
                ladders[f"{name}@{h}m"] = price_floor_short_ladder(
                    g, h, cfg["hedge"], trade_cost_bps)
                n_cells += len([k for k in ladders[f"{name}@{h}m"]
                                if not k.startswith("_")])
            e = entry
            print(f"  {name:24s} {h:2d}m gross {e['gross']['annualised_pct']:+8.2f}%/yr "
                  f"t_b {e['gross']['t_block']}  breakeven borrow "
                  f"{e['breakeven_borrow_rate_pct_after_10bps_trading']:6.1f}%/yr  "
                  f"worst {e['worst_period']['net_of_trading_pct']:+.1f}% "
                  f"({e['worst_period']['month']})  names/mo {e['median_names_per_month']}")

    receipt["constructions"] = out
    receipt["short_market_control"] = ctrl
    receipt["price_floor_ladder_minus_resid_on_regt"] = ladders

    # ---- the mandated disclosure. The toxic cell is the SUBJECT of this
    # receipt, so the $5-floor variant and the era split are not an appendix.
    l1 = ladders.get("hedged_beta@1m", {})
    base = l1.get("close_ge_0", {})
    f5 = l1.get("close_ge_5", {})
    receipt["MANDATORY_TOXIC_BAND_DISCLOSURE"] = {
        "rule": ("VERIFICATION_2026-09-04 SS4: the corrected toxic_ge_5 cell MUST NOT be "
                 "presented as a long, and any receipt that reports it reports the $5 "
                 "price-floor variant and the era split beside it. This receipt reports "
                 "the SHORT of the same cell, which is the same object with its sign "
                 "flipped, so the rule binds identically."),
        "object": "-resid on Reg-T capital, zero borrow, 1-month formation",
        "no_floor": {k: base.get(k) for k in (
            "minus_resid_on_regt_zero_borrow_annualised_pct", "t_block",
            "median_names_per_month", "median_monthly_pct", "mean_monthly_pct",
            "breakeven_borrow_rate_pct")},
        "close_ge_5": {k: f5.get(k) for k in (
            "minus_resid_on_regt_zero_borrow_annualised_pct", "t_block",
            "median_names_per_month", "breakeven_borrow_rate_pct", "status")},
        "era_splits_no_floor": base.get("era_splits"),
        "population": l1.get("_population"),
        "cost_realism": l1.get("_cost_realism"),
        "verdict": ("the LONG of this cell is not a signal (its sign depends on a $5 "
                    "price floor, its median monthly excess is negative against a "
                    "positive mean, and it holds single-digit names a month). The SHORT "
                    "inherits every one of those defects with the sign reversed, and adds "
                    "borrow: the breakeven borrow rate is the only number worth quoting, "
                    "because a sub-$5 name that a screen says to short is precisely the "
                    "name whose borrow is 20-100%+/yr and whose shares may not exist. "
                    "Read this receipt as a REFUSAL to monetise the band on either side."),
    }
    receipt["family"] = {
        "cells_examined": n_cells,
        "cells_definition": ("construction x horizon x borrow tier for the -resid/Reg-T "
                             "headline, plus the price-floor ladder rows"),
        "family_max_p": None,
        "family_correction_status": (
            "PENDING and NOT COMPUTED. This receipt reports t_block on n_effective DATE "
            "BLOCKS and nothing else: with 5 constructions x 4 horizons x 6 borrow tiers "
            f"= 120 headline cells plus {n_cells - 120} ladder cells, an uncorrected p "
            "would be meaningless, and the roadmap's B4 block (CPCV / Deflated Sharpe / "
            "SPA) does not exist yet. NO CELL IN THIS RECEIPT IS CLAIMED SIGNIFICANT. The "
            "receipt's own conclusion is negative, which is the direction a missing "
            "multiplicity correction cannot manufacture."),
        "model_null_status": (
            "NOT APPLICABLE. A band is a fixed threshold with no fitted parameters, so "
            "there is no model to re-fit on shuffled labels and the >=64-draw model-null "
            "bar (learner/nullbar.py) has nothing to draw. The analogue that IS run is "
            "the beta-matched control and the short-the-market control."),
    }

    # ---- headline verdict block
    def tier_row(name: str, h: int = 1) -> dict:
        e = out[name].get(f"{h}m", {})
        if e.get("status"):
            return e
        hd = e["HEADLINE_minus_resid_on_regt_capital"]
        return {"HEADLINE_minus_resid_on_regt_zero_borrow_annualised_pct":
                    hd["on_regt_capital_by_borrow_tier_pct"]["0"]["annualised_pct"],
                "HEADLINE_t_block":
                    hd["on_regt_capital_by_borrow_tier_pct"]["0"]["t_block"],
                "HEADLINE_at_20pct_borrow_annualised_pct":
                    hd["on_regt_capital_by_borrow_tier_pct"]["20"]["annualised_pct"],
                "mean_regt_capital_per_dollar_short":
                    hd["mean_regt_capital_per_dollar_short"],
                "beta_matched_leg_annualised_pct":
                    e["beta_matched_benchmark"]["leg_annualised_pct"],
                "hedged_gross_DECOMPOSITION_ONLY_annualised_pct": e["gross"]["annualised_pct"],
                "hedged_gross_t_block": e["gross"]["t_block"],
                "breakeven_borrow_pct_10bps": e["breakeven_borrow_rate_pct_after_10bps_trading"],
                "breakeven_borrow_pct_25bps": e["breakeven_borrow_rate_pct_after_25bps_trading"],
                "net_at_20pct_borrow_annualised_pct": e["net_by_borrow_tier_pct"]["20"]["annualised_pct"],
                "net_at_50pct_borrow_annualised_pct": e["net_by_borrow_tier_pct"]["50"]["annualised_pct"],
                "worst_period_pct": e["worst_period"]["net_of_trading_pct"],
                "era_2022_2024_annualised_pct":
                    e["era_splits_net_of_trading"]["2022_2024"]["annualised_pct"]}

    receipt["verdict_headline_1m"] = {k: tier_row(k) for k in constructions}
    receipt["runtime_seconds"] = round(
        (datetime.now(timezone.utc) - t0).total_seconds(), 1)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-cost-bps", type=float, default=TRADE_COST_BPS)
    ap.add_argument("--out", default=str(RECEIPT))
    a = ap.parse_args(argv)
    rep = run(a.trade_cost_bps)
    RECEIPT_OUT = Path(a.out)
    RECEIPT_OUT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_OUT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
