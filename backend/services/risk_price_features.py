"""RISK_PRICE family, OWN construction — computable identically in BOTH eras.

RETURN-PANEL-TOURNAMENT-1's screen found exactly one family with a pulse:
RISK_PRICE (JKP's betas / idiosyncratic vol / skew block, 2013+ only).
Chasing that lead into 1990–2012 needs the family rebuilt from raw CRSP
daily data with definitions that do not change across eras — otherwise an
era difference is a construction difference wearing a costume.

Eleven features, all from (prc, ret, vol) + FF daily market factor:

    rvol_21d, rvol_252d      realized vol
    beta_252d, corr_252d     CAPM slope / correlation vs mktrf
    betadown_252d            downside beta (mkt<0 days, min 60 obs)
    ivol_capm_21d, _252d     residual vol around the CAPM fit
    rskew_21d                return skewness
    rmax1_21d                largest daily return in the window
    ami_126d                 Amihud |ret|/dollar volume
    zero_trades_21d          zero-volume-or-zero-return day count

`shrout` is absent from the early-era daily pull, so turnover is NOT in
the family — declared here, not silently dropped downstream.

Memory discipline: each feature matrix is sampled at month-ends and freed
before the next is built (the early panel is ~5,800 days × ~6,900 names).
"""

from __future__ import annotations

import pandas as pd

from backend import config as _config

WRDS_DIR = _config.OPTIMUS_LEDGER_DIR / "wrds"
FF_PATH = WRDS_DIR / "ff_factors_daily.parquet"

FEATURES = ("rvol_21d", "rvol_252d", "beta_252d", "corr_252d",
            "betadown_252d", "ivol_capm_21d", "ivol_capm_252d",
            "rskew_21d", "rmax1_21d", "ami_126d", "zero_trades_21d")


class RiskPriceRefused(RuntimeError):
    """A required input is missing. Refused, not defaulted."""


def _load_daily(years: tuple[int, int]):
    parts = []
    for yr in range(years[0], years[1] + 1):
        p = WRDS_DIR / f"crsp_dsf_{yr}.parquet"
        if not p.exists():
            raise RiskPriceRefused(f"{p.name} missing")
        parts.append(pd.read_parquet(
            p, columns=["permno", "date", "prc", "ret", "vol"]))
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    px = df.pivot_table(index="date", columns="permno", values="prc",
                        aggfunc="last").abs().sort_index()
    ret = df.pivot_table(index="date", columns="permno", values="ret",
                         aggfunc="last").sort_index()
    vol = df.pivot_table(index="date", columns="permno", values="vol",
                         aggfunc="last").sort_index()
    return px, ret, vol


def _market(index: pd.DatetimeIndex) -> pd.Series:
    if not FF_PATH.exists():
        raise RiskPriceRefused(f"{FF_PATH} missing")
    ff = pd.read_parquet(FF_PATH, columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    mkt = ff.set_index("date")["mktrf"].reindex(index)
    if mkt.isna().mean() > 0.01:
        raise RiskPriceRefused("FF market factor does not cover the panel "
                               "window — a beta against NaN is not a beta")
    return mkt


def build(years: tuple[int, int]) -> pd.DataFrame:
    """Month-end rows (date, permno, 11 features). PIT: every window ends
    at the formation date; nothing forward-looking anywhere."""
    px, ret, vol = _load_daily(years)
    mkt = _market(ret.index)
    month_ends = px.groupby(px.index.to_period("M")).tail(1).index

    def _sample(mat: pd.DataFrame, name: str) -> pd.DataFrame:
        s = mat.loc[mat.index.isin(month_ends)].stack()
        s.name = name
        return s.reset_index().rename(columns={"level_1": "permno"})

    out = None

    def _merge(mat, name):
        nonlocal out
        piece = _sample(mat, name)
        out = piece if out is None else out.merge(
            piece, on=["date", "permno"], how="outer")

    _merge(ret.rolling(21).std(ddof=1), "rvol_21d")
    _merge(ret.rolling(252).std(ddof=1), "rvol_252d")

    # rolling CAPM moments via rolling means of products
    mkt_sq = mkt * mkt
    rm = ret.mul(mkt, axis=0)
    for w, tag in ((252, "252d"),):
        e_r = ret.rolling(w).mean()
        e_m = mkt.rolling(w).mean()
        e_rm = rm.rolling(w).mean()
        var_m = mkt_sq.rolling(w).mean() - e_m * e_m
        cov = e_rm.sub(e_r.mul(e_m, axis=0))
        beta = cov.div(var_m, axis=0)
        _merge(beta, f"beta_{tag}")
        var_r = ret.rolling(w).var(ddof=0)
        corr = cov.div((var_r.clip(lower=0) ** 0.5)
                       .mul(var_m.clip(lower=0) ** 0.5, axis=0))
        _merge(corr, f"corr_{tag}")
        ivol = (var_r - cov.pow(2).div(var_m, axis=0)).clip(lower=0) ** 0.5
        _merge(ivol, f"ivol_capm_{tag}")
        del e_r, e_rm, var_m, cov, beta, var_r, corr, ivol

    # 21d ivol (same construction, short window)
    w = 21
    e_r = ret.rolling(w).mean()
    e_m = mkt.rolling(w).mean()
    e_rm = rm.rolling(w).mean()
    var_m = mkt_sq.rolling(w).mean() - e_m * e_m
    cov = e_rm.sub(e_r.mul(e_m, axis=0))
    var_r = ret.rolling(w).var(ddof=0)
    ivol21 = (var_r - cov.pow(2).div(var_m, axis=0)).clip(lower=0) ** 0.5
    _merge(ivol21, "ivol_capm_21d")
    del e_r, e_m, e_rm, var_m, cov, var_r, ivol21, rm, mkt_sq

    # downside beta: moments over mkt<0 days only, min 60 observations
    down = mkt < 0
    ret_d = ret.where(down)
    mkt_d = mkt.where(down)
    e_rd = ret_d.rolling(252, min_periods=60).mean()
    e_md = mkt_d.rolling(252, min_periods=60).mean()
    e_rmd = ret_d.mul(mkt_d, axis=0).rolling(252, min_periods=60).mean()
    var_md = ((mkt_d * mkt_d).rolling(252, min_periods=60).mean()
              - e_md * e_md)
    _merge(e_rmd.sub(e_rd.mul(e_md, axis=0)).div(var_md, axis=0),
           "betadown_252d")
    del ret_d, mkt_d, e_rd, e_md, e_rmd, var_md

    _merge(ret.rolling(21).skew(), "rskew_21d")
    _merge(ret.rolling(21).max(), "rmax1_21d")
    dollar = px * vol
    _merge((ret.abs() / dollar.where(dollar > 0)).rolling(
        126, min_periods=60).mean() * 1e6, "ami_126d")
    _merge(((vol.fillna(0) == 0) | (ret.fillna(0) == 0))
           .rolling(21).sum(), "zero_trades_21d")

    out["permno"] = out["permno"].astype(int)
    return out
