"""Signal families grouped by INFORMATION CLASS, for INFORMATION-DIMENSION-1.

STRATEGY-EFFECTIVE-DIMENSION-1 measured the mega-sweep-1 corpus and found
86 books collapsing to an effective rank of ~3.5. That reframes what a
bigger sweep is for. Enumerating thousands more combinations of the SAME
seven price/fundamental signals cannot raise a dimensionality that the
signal set has already exhausted — it would produce a larger corpus of
the same handful of behaviours and a longer leaderboard to overfit.

The question worth compute is therefore not "how many books" but:

    does a NEW INFORMATION CLASS buy a genuinely new DIRECTION in the
    space of portfolio behaviours, or does it re-express one we own?

Which needs a matched control, and this is the part that is easy to get
wrong: adding any signals at all will nudge the effective rank upward,
simply because more distinct portfolios span more directions. So the
options/expectations/liquidity classes are contrasted against an equal
number of ADDITIONAL PRICE signals — more of a class we already have.
The comparison is new-class-vs-more-of-the-same, never new-class-vs-
nothing.

Every signal returns "higher = better" scores at the as-of date and is
declared with its direction here, before any book is run. As-of lookups
index the availability stamp (opt_date, statpers, public_date), so a
signal cannot read a value before the world could.

NOTE ON SCOPE: this module measures STRUCTURE, not profitability. Whether
any of these signals earns money is a separate question that needs its
own pre-registration; the families here are explicitly NOT being screened
for returns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config

WRDS_DIR = _config.OPTIMUS_LEDGER_DIR / "wrds"

#: information class -> signal names. The PRICE_EXTRA class is the
#: matched control: same information class as what the corpus already
#: has, added in comparable quantity.
CLASSES = {
    "price_base": ("mom_12_1", "mom_63", "rev_21", "low_vol"),
    "fundamental": ("value_bm", "quality_roe"),
    "price_extra": ("mom_252", "rev_63", "dd_recovery", "vol_21_low"),
    "options": ("opt_iv_low", "opt_skew_low", "opt_pc_low"),
    "expectations": ("exp_breadth", "exp_disp_low", "exp_revision"),
    "liquidity": ("liq_dvol_trend", "liq_dvol_high"),
}


def _asof(piv: pd.DataFrame, asof) -> pd.Series:
    sub = piv.loc[:asof]
    if not len(sub):
        return pd.Series(dtype=float)
    return sub.iloc[-1].dropna()


# ── extras builders ────────────────────────────────────────────────────────
def options_pivots(years=(2013, 2024)) -> dict:
    """permno x opt_date pivots of the 30d surface features.

    Indexed by the OBSERVATION date, so an as-of lookup at t can only see
    surfaces published on or before t.
    """
    from scripts.net_ladder_rungs_run import options_monthly
    opt = options_monthly(years=years)
    opt["opt_date"] = pd.to_datetime(opt["opt_date"])
    out = {}
    for c in ("opt_iv_atm", "opt_skew", "opt_pc50"):
        out[c] = opt.pivot_table(index="opt_date", columns="permno",
                                 values=c, aggfunc="last").sort_index()
    return out


def expectations_pivots(early: bool = False) -> dict:
    """permno x statpers pivots of IBES consensus state.

    `statpers` is the date the consensus was computed, so it is the
    honest knowledge date. `actual`/`anndats_act` are deliberately NOT
    used: CHRONOLOGY-AUDIT-1 C3 measured that 99.9% of rows carrying an
    `actual` have anndats_act AFTER statpers, a median 161 days of
    lookahead for anyone who reads it at statpers.
    """
    f = ("ibes_consensus_monthly_early.parquet" if early
         else "ibes_consensus_monthly.parquet")
    e = pd.read_parquet(WRDS_DIR / f,
                        columns=["permno", "statpers", "fpi", "numest",
                                 "numup", "numdown", "meanest", "stdev"])
    e = e[e["fpi"] == "1"].copy()
    e["statpers"] = pd.to_datetime(e["statpers"])
    e = e.sort_values("statpers")
    e["exp_breadth"] = np.where(
        e["numest"] > 0, (e["numup"] - e["numdown"]) / e["numest"], np.nan)
    e["exp_disp"] = np.where(e["meanest"].abs() >= 0.01,
                             e["stdev"] / e["meanest"].abs(), np.nan)
    prev = e.groupby("permno")["meanest"].shift(1)
    e["exp_rev"] = np.where(prev.abs() >= 0.01,
                            (e["meanest"] - prev) / prev.abs(), np.nan)
    out = {}
    for c in ("exp_breadth", "exp_disp", "exp_rev"):
        out[c] = e.pivot_table(index="statpers", columns="permno",
                               values=c, aggfunc="last").sort_index()
    return out


def liquidity_pivots(years=(2013, 2024)) -> dict:
    """Dollar-volume level and trend from the CRSP daily panel."""
    parts = []
    for yr in range(years[0], years[1] + 1):
        p = WRDS_DIR / f"crsp_dsf_{yr}.parquet"
        if not p.exists():
            continue
        parts.append(pd.read_parquet(p, columns=["permno", "date", "prc",
                                                 "vol"]))
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["dvol"] = df["prc"].abs() * df["vol"].fillna(0.0)
    piv = df.pivot_table(index="date", columns="permno", values="dvol",
                         aggfunc="last").sort_index()
    short = piv.rolling(63).mean()
    long = piv.rolling(252).mean()
    return {"dvol_level": np.log1p(short),
            "dvol_trend": (short / long.replace(0, np.nan))}


def build_extras(panel, *, years=(2013, 2024), early: bool = False,
                 include=("options", "expectations", "liquidity")) -> dict:
    """Extend lane_factory_sim's extras with the new information classes."""
    from backend.services.lane_factory_sim import prepare_extras
    fr = ("finratio_monthly_early.parquet" if early
          else "finratio_monthly.parquet")
    ex = prepare_extras(panel, finratio_path=WRDS_DIR / fr)
    if "options" in include:
        ex["options"] = options_pivots(years=years)
    if "expectations" in include:
        ex["expectations"] = expectations_pivots(early=early)
    if "liquidity" in include:
        ex["liquidity"] = liquidity_pivots(years=years)
    return ex


# ── signals ────────────────────────────────────────────────────────────────
def _px(pn, t):
    return pn.px.loc[:t]


def register(signals: dict) -> dict:
    """Additively register the new families into a SIGNALS registry.

    Additive on purpose: MEGA-SWEEP-1's declaration froze m=84 over the
    ORIGINAL seven signals, and adding families later must not
    retroactively change what that screen tested.
    """
    new = {
        # --- price_extra: the MATCHED CONTROL class -------------------
        "mom_252": lambda pn, t, ex: (
            _px(pn, t).iloc[-1] / _px(pn, t).iloc[-252] - 1.0).dropna()
            if len(_px(pn, t)) >= 252 else pd.Series(dtype=float),
        "rev_63": lambda pn, t, ex: (
            -(_px(pn, t).iloc[-1] / _px(pn, t).iloc[-63] - 1.0)).dropna()
            if len(_px(pn, t)) >= 63 else pd.Series(dtype=float),
        "dd_recovery": lambda pn, t, ex: (
            _px(pn, t).iloc[-1] / _px(pn, t).iloc[-252:].max()).dropna()
            if len(_px(pn, t)) >= 252 else pd.Series(dtype=float),
        "vol_21_low": lambda pn, t, ex: (
            1.0 / pn.ret.loc[:t].iloc[-21:].std(ddof=1).replace(0, np.nan)
        ).dropna() if len(pn.ret.loc[:t]) >= 21 else pd.Series(dtype=float),
        # --- options: low implied risk / low crash fear = higher score
        "opt_iv_low": lambda pn, t, ex: -_asof(
            ex["options"]["opt_iv_atm"], t),
        "opt_skew_low": lambda pn, t, ex: -_asof(
            ex["options"]["opt_skew"], t),
        "opt_pc_low": lambda pn, t, ex: -_asof(
            ex["options"]["opt_pc50"], t),
        # --- expectations -------------------------------------------
        "exp_breadth": lambda pn, t, ex: _asof(
            ex["expectations"]["exp_breadth"], t),
        "exp_disp_low": lambda pn, t, ex: -_asof(
            ex["expectations"]["exp_disp"], t),
        "exp_revision": lambda pn, t, ex: _asof(
            ex["expectations"]["exp_rev"], t),
        # --- liquidity ----------------------------------------------
        "liq_dvol_high": lambda pn, t, ex: _asof(
            ex["liquidity"]["dvol_level"], t),
        "liq_dvol_trend": lambda pn, t, ex: _asof(
            ex["liquidity"]["dvol_trend"], t),
    }
    signals.update(new)
    return signals


#: which extras key each new signal requires — run_book refuses without it
REQUIRES = {s: cls for cls, names in CLASSES.items() for s in names
            if cls in ("options", "expectations", "liquidity")}
