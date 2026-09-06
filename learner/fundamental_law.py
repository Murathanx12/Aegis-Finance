"""learner/fundamental_law.py -- WHY A REAL IC PRODUCED NO MONEY.

THE ONE IDENTITY THIS FILE MEASURES
===================================
Grinold-Kahn, with Clarke-de Silva-Thorley's third term:

    IR  ~=  IC  x  sqrt(BR)  x  TC

    IC  -- the cross-sectional information coefficient of the forecast
    BR  -- the number of INDEPENDENT bets taken per year (breadth)
    TC  -- the transfer coefficient: how much of the unconstrained bet the
           realised portfolio actually expresses

The programme has spent five months measuring the FIRST term and never the
other two. `BRAINSTORM_2026-09-06` §1.2 states the consequence in one line: an
IC of 0.08 with breadth 7 and TC 0.3 is IR ~= 0.06 -- invisible at any sample
size we will ever own -- while the SAME IC with breadth 300 and TC 0.8 is IR
~= 1. Nothing about the forecast changes between those two sentences. Only the
construction does.

So this module is deliberately NOT a signal test. It is an instrument that
reads a book that has already been built and says which of the three terms is
responsible for what it earned. A book whose TC is 0.3 has a CONSTRUCTION
defect; reporting "the signal did not work" from it is a category error, and
it is the error this repo has been making.

THE THREE TERMS, DEFINED THE WAY THEY ARE COMPUTED HERE
=======================================================

**IC.** The monthly cross-sectional Spearman rank correlation between the
forecast and the realised forward return, averaged over months. Rank, not
Pearson, because every selector in this repo is used as a RANK (the books all
sort and cut) and because a Pearson IC on a fat-tailed cross-section is one
outlier's opinion. The Pearson IC is reported beside it, never instead of it.

**Effective breadth.** Per month, `(sum w)^2 / sum w^2` over the book's
weights -- the standard inverse-Herfindahl participation count. For an
equal-weighted k-name book this is exactly k; for a value-weighted top-50 book
of US equities it is nearer 7, which is the S36 receipt that started this. It
is a count of NAMES, not of independent bets: names in one book are correlated,
so `BR_year = mean_monthly_effective_names x 12` is an UPPER BOUND on breadth
and is labelled as one. `implied_ir_annual` inherits that: it is a ceiling.

**Transfer coefficient.** The cross-sectional correlation, per month, between
the ACTIVE weights the book actually ran and the active weights an
unconstrained portfolio of the same signal would have run, averaged over
months.

    active_realised(i) = w_book(i) - w_benchmark(i)
    active_ideal(i)    = z(signal(i))  (cross-sectionally standardised)

The benchmark defaults to equal weight over the month's admissible names,
because that is the universe the book chose from; pass `benchmark_weights` to
use another. TC = 1 means the book expressed the signal exactly. Every
constraint in this repo -- long-only, top-50, the 40% UNCLASSIFIED cap, the
$3m floor, the -3% stop -- can only ever LOWER it. That is the point: TC is
where the constraints show up in the arithmetic, and until now they showed up
nowhere.

WHAT THIS MODULE REFUSES TO DO
==============================
It does not compute a p-value, a verdict or a benchmark. A fundamental-law
block is DIAGNOSTIC and attaches BESIDE the graded result, never in place of
it. And it refuses rather than guesses: a month with fewer than
`MIN_NAMES_FOR_CORR` admissible names contributes no TC observation, and a
book with no month that qualifies gets `transfer_coefficient: None` with a
reason, not a zero that reads like a measurement.

    from learner import fundamental_law as FL
    blk = FL.receipt(df, "lgbm_clf", weights_by_month, net=net, market=mkt)
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "TC_DEFECT_BELOW", "MIN_NAMES_FOR_CORR",
    "effective_breadth", "effective_breadth_series",
    "transfer_coefficient", "information_coefficient",
    "realised_ir", "implied_ir", "receipt",
]

#: Below this the book is a CONSTRUCTION defect and its signal verdict is not
#: readable from it. 0.5 is Grinold-Kahn's own rule of thumb and is quoted as
#: such -- it is a convention, not a measurement.
TC_DEFECT_BELOW: float = 0.5

#: A cross-sectional correlation on three names is noise wearing a number.
MIN_NAMES_FOR_CORR: int = 10

#: Months per year. Every book in this repo rebalances monthly.
_MONTHS: int = 12


def _finite(x) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _r(x, nd: int = 6):
    f = _finite(x)
    return round(f, nd) if f is not None else None


# ------------------------------------------------------------------ breadth

def effective_breadth(weights: Sequence[float] | Mapping[object, float]) -> float | None:
    """`(sum w)^2 / sum w^2` -- the inverse-Herfindahl participation count.

    Equal weights over k names give exactly k. One name at 100% gives 1. The
    value-weighted top-50 book that started this enquiry gives ~7.

    Negative weights (a long-short book) are handled by the same formula on
    the ABSOLUTE weights, because a short is a bet and the sum of signed
    weights of a market-neutral book is zero -- the signed formula would divide
    by nothing and report an infinity.
    """
    w = np.asarray(list(weights.values()) if isinstance(weights, Mapping) else list(weights),
                   dtype="float64")
    w = w[np.isfinite(w)]
    if w.size == 0:
        return None
    a = np.abs(w)
    denom = float((a ** 2).sum())
    if denom <= 0:
        return None
    return float((a.sum() ** 2) / denom)


def effective_breadth_series(weights_by_month: Mapping[object, Mapping[object, float]]
                             ) -> pd.Series:
    """Effective names, month by month. The mean of this is what `receipt` quotes."""
    out = {m: effective_breadth(w) for m, w in weights_by_month.items()}
    return pd.Series({m: v for m, v in out.items() if v is not None}).sort_index()


# ------------------------------------------------------- transfer coefficient

def _zscore(x: np.ndarray) -> np.ndarray | None:
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(x)
    if ok.sum() < 2:
        return None
    sd = float(np.std(x[ok], ddof=1))
    if not math.isfinite(sd) or sd <= 0:
        return None                       # a constant signal expresses nothing
    z = np.full(x.shape, np.nan)
    z[ok] = (x[ok] - float(np.mean(x[ok]))) / sd
    return z


def transfer_coefficient(signal: Sequence[float], realised_weights: Sequence[float],
                         benchmark_weights: Sequence[float] | None = None
                         ) -> float | None:
    """One month's TC: corr(active realised, active ideal).

    `signal` and `realised_weights` are aligned arrays over the month's
    ADMISSIBLE names -- every name the book could have bought, with weight 0
    for the ones it did not. Passing only the held names would compute the
    correlation on the very names the constraint selected and report ~1 for
    every book ever built, which is the trap this function exists to avoid.
    """
    s = np.asarray(list(signal), dtype="float64")
    w = np.asarray(list(realised_weights), dtype="float64")
    if s.shape != w.shape or s.size < MIN_NAMES_FOR_CORR:
        return None
    b = (np.full(s.shape, 1.0 / s.size) if benchmark_weights is None
         else np.asarray(list(benchmark_weights), dtype="float64"))
    if b.shape != s.shape:
        return None
    ideal = _zscore(s)
    if ideal is None:
        return None
    active = w - b
    ok = np.isfinite(ideal) & np.isfinite(active)
    if ok.sum() < MIN_NAMES_FOR_CORR:
        return None
    a, i = active[ok], ideal[ok]
    if float(np.std(a, ddof=1)) <= 0 or float(np.std(i, ddof=1)) <= 0:
        return None
    c = float(np.corrcoef(a, i)[0, 1])
    return c if math.isfinite(c) else None


# ------------------------------------------------------------------------ IC

def information_coefficient(df: pd.DataFrame, pred_col: str, ret_col: str,
                            month_col: str = "month",
                            method: str = "spearman") -> dict:
    """Monthly cross-sectional IC, and the t of its mean over months."""
    d = df[[month_col, pred_col, ret_col]].dropna()
    vals = {}
    for m, g in d.groupby(month_col, sort=True):
        if len(g) < MIN_NAMES_FOR_CORR:
            continue
        if g[pred_col].nunique() < 2 or g[ret_col].nunique() < 2:
            continue
        c = g[pred_col].corr(g[ret_col], method=method)
        if c is not None and math.isfinite(c):
            vals[m] = float(c)
    s = pd.Series(vals).sort_index()
    if s.empty:
        return {"ic": None, "months": 0, "why": "no month had enough names"}
    sd = float(s.std(ddof=1))
    t = float(s.mean() / (sd / math.sqrt(len(s)))) if sd > 0 and len(s) > 2 else None
    return {"ic": _r(s.mean()), "ic_sd": _r(sd), "t_ic": _r(t, 3),
            "months": int(len(s)), "method": method,
            "share_positive": _r(float((s > 0).mean()), 4)}


# ------------------------------------------------------------------------ IR

#: A "constant" float series has a standard deviation of ~1e-18, not 0. Dividing
#: by it produced an IR of 6.6e15 in the first version of this function -- the
#: same shape of defect as the degenerate OLS that turned CI red on 2026-09-06,
#: where a t was made entirely of rounding error. The test is therefore RELATIVE
#: to the series' own scale, not `sd > 0`.
_DEGENERATE_SD_REL: float = 1e-9


def realised_ir(excess: Sequence[float], periods_per_year: int = _MONTHS) -> float | None:
    """Annualised IR of a monthly ACTIVE return series (mean / sd x sqrt(12)).

    Refuses on a series with no dispersion. A perfectly constant active return
    is not an infinitely good strategy; it is an input that was never a return
    series, and an instrument that answers 6.6e15 to it will be believed once.
    """
    s = pd.Series(list(excess), dtype="float64").dropna()
    if len(s) < 3:
        return None
    sd = float(s.std(ddof=1))
    scale = float(np.max(np.abs(s.to_numpy()))) if len(s) else 0.0
    if not math.isfinite(sd) or sd <= max(_DEGENERATE_SD_REL * scale, 0.0) or sd <= 0:
        return None
    return float(s.mean() / sd * math.sqrt(periods_per_year))


def implied_ir(ic: float | None, effective_names_per_month: float | None,
               tc: float | None, periods_per_year: int = _MONTHS) -> float | None:
    """`IC x sqrt(BR) x TC`, annualised, with BR = names/month x periods/year.

    This is a CEILING, not a forecast: it assumes the names in a month are
    independent bets, which they are not. A realised IR far BELOW it points at
    a term this identity does not carry (costs, timing, the sizing overlay); a
    realised IR far ABOVE it points at leverage or beta, not at skill.
    """
    if ic is None or effective_names_per_month is None or tc is None:
        return None
    br = float(effective_names_per_month) * float(periods_per_year)
    if br <= 0:
        return None
    return float(ic) * math.sqrt(br) * float(tc)


# -------------------------------------------------------------------- receipt

def receipt(df: pd.DataFrame, pred_col: str,
            weights_by_month: Mapping[object, Mapping[object, float]],
            *,
            net: pd.Series | None = None,
            benchmark: pd.Series | None = None,
            beta: float | None = None,
            ret_col: str = "fwd_1m", month_col: str = "month",
            id_col: str = "permno",
            periods_per_year: int = _MONTHS) -> dict:
    """The block that attaches to EVERY book receipt from tonight on.

    `weights_by_month` is `{month: {permno: weight}}` -- exactly what
    `evaluate.book(..., return_weights=True)` now returns under `_weights`.
    `net` and `benchmark` are the book's monthly net return and the benchmark
    it is graded against (beta-matched, normally); their difference is the
    realised active return whose IR is compared with the implied one.

    Every term can come back None with a reason. A fundamental-law block that
    silently reports 0.0 for a term it could not measure is worse than no block
    at all -- it would read as "the construction expresses nothing", which is a
    finding, when the truth is "not measured", which is not.
    """
    ic_blk = information_coefficient(df, pred_col, ret_col, month_col=month_col)
    br_s = effective_breadth_series(weights_by_month)
    eff = _finite(br_s.mean()) if len(br_s) else None

    # TC month by month, over the ADMISSIBLE cross-section (not the holdings).
    d = df[[month_col, id_col, pred_col]].dropna()
    tcs, skipped = {}, 0
    for m, g in d.groupby(month_col, sort=True):
        wm = weights_by_month.get(m)
        if wm is None:
            wm = weights_by_month.get(str(m))
        if not wm:
            continue
        ids = g[id_col].astype("int64").to_numpy()
        w = np.array([float(wm.get(int(i), wm.get(str(int(i)), 0.0))) for i in ids],
                     dtype="float64")
        tc = transfer_coefficient(g[pred_col].to_numpy(), w)
        if tc is None:
            skipped += 1
            continue
        tcs[m] = tc
    tc_s = pd.Series(tcs).sort_index()
    tc = _finite(tc_s.mean()) if len(tc_s) else None

    active = None
    if net is not None and benchmark is not None:
        n = pd.Series(net).astype("float64")
        b = pd.Series(benchmark).reindex(n.index).astype("float64")
        active = (n - b).dropna()

    r_ir = realised_ir(active, periods_per_year) if active is not None else None
    i_ir = implied_ir(ic_blk.get("ic"), eff, tc, periods_per_year)

    out = {
        "identity": "IR ~= IC x sqrt(BR) x TC  (Grinold-Kahn; TC after Clarke-de Silva-Thorley)",
        "information_coefficient": ic_blk,
        "effective_breadth": {
            "mean_effective_names_per_month": _r(eff, 3),
            "median": _r(br_s.median(), 3) if len(br_s) else None,
            "min": _r(br_s.min(), 3) if len(br_s) else None,
            "max": _r(br_s.max(), 3) if len(br_s) else None,
            "months": int(len(br_s)),
            "annual_breadth_upper_bound": _r((eff * periods_per_year) if eff else None, 2),
            "note": ("(sum w)^2 / sum w^2 -- an inverse-Herfindahl count of NAMES. "
                     "Names are correlated, so BR_year = names x 12 is an UPPER BOUND "
                     "on independent bets and `implied_ir_annual` is a ceiling."),
        },
        "transfer_coefficient": {
            "tc": _r(tc, 4),
            "months_measured": int(len(tc_s)),
            "months_skipped": int(skipped),
            "min": _r(tc_s.min(), 4) if len(tc_s) else None,
            "max": _r(tc_s.max(), 4) if len(tc_s) else None,
            "benchmark": "equal weight over the month's admissible names",
            "note": ("corr(active realised weights, z(signal)) over ALL admissible "
                     "names, not the holdings. Long-only, top-k, caps, floors and "
                     "stops can only LOWER it."),
        },
        "beta": _r(beta, 4),
        "realised_ir_annual": _r(r_ir, 4),
        "implied_ir_annual": _r(i_ir, 4),
        "realised_over_implied": (_r(r_ir / i_ir, 4)
                                  if (r_ir is not None and i_ir not in (None, 0.0))
                                  else None),
        "active_months": int(len(active)) if active is not None else 0,
    }
    if tc is None:
        out["transfer_coefficient"]["why_none"] = (
            "no month produced a readable cross-sectional correlation "
            f"({skipped} months skipped; needs >= {MIN_NAMES_FOR_CORR} admissible names "
            "and a non-constant signal)")
    out["construction_verdict"] = (
        "CANNOT DETERMINE (transfer coefficient not measurable)" if tc is None else
        f"CONSTRUCTION_DEFECT (TC {tc:.3f} < {TC_DEFECT_BELOW}: the book expresses less "
        "than half of the bet its own signal implies; a signal verdict read from this "
        "book is a category error)" if tc < TC_DEFECT_BELOW else
        f"CONSTRUCTION_OK (TC {tc:.3f})")
    return out
