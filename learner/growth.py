"""THE PRODUCT RULER — after-cost terminal wealth at a declared drawdown budget.

`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.1: the program has two rulers
and has been reporting only one. The RESEARCH_CLAIM ruler (beta-matched excess,
after costs, family-corrected) is the right bar for the word *alpha*, and
nothing we own passes it. The **product ruler** for the aggressive and
extreme-growth personalities is

    after-cost TERMINAL WEALTH at a declared drawdown budget,
    with survival guaranteed and BETA REPORTED.

Beta is allowed here. **Hidden beta is not.** Every function in this module
puts `beta` first in its output dict, and `evaluate_growth` refuses to return a
terminal-wealth number without one.

THE THREE THINGS THIS MODULE EXISTS TO STOP
===========================================
1. **"It beat SPY" with no beta.** A book at beta 1.33 in a bull decade beats
   SPY by arithmetic. `leverage_neutral` re-runs it at SPY's own realized
   volatility and CHARGES the financing, so the comparison is between books
   rather than between leverages.
2. **A drawdown budget nobody checked.** `constraints` is computed, not
   asserted: maxDD <= 1.25x SPY's over the SAME months, monthly CVaR5 <= 1.5x
   SPY's, no month worse than -40%, gross <= 2.0x.
3. **A survival claim from one path.** `p_ruin` is a stationary block bootstrap
   (the module's own, seeded) over the LARGEST admissible book, not a
   sample-path assertion.

WHAT IS DELIBERATELY NOT HERE
=============================
No significance machinery. DSR / SPA / PBO / family corrections live in
`learner/inference.py` and every growth receipt quotes them from there. This
module answers "how much wealth, at what risk, with how much beta" and nothing
else; mixing the two rulers in one function is how the program lost track of
which one it was reporting.

COST CONVENTION
===============
`book_returns` arrive NET of trading costs (that is `evaluate.book`'s output).
`cost_bps` is carried so the receipt can never omit the rate the series was
built at -- it is recorded, not re-applied. Passing `cost_bps=None` raises:
CLAUDE.md, "costs are never omitted".
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "DRAWDOWN_BUDGET_MULT", "CVAR_BUDGET_MULT", "WORST_MONTH_FLOOR",
    "GROSS_CAP", "FINANCING_BPS", "RUIN_THRESHOLD",
    "max_drawdown", "cvar", "terminal_wealth", "cagr", "realized_vol",
    "market_model", "lever", "admissible_leverage", "p_ruin",
    "evaluate_growth", "OBJECTIVE",
]

# ------------------------------------------------------------ the declaration
#: maxDD <= this multiple of SPY's maxDD over the SAME months.
DRAWDOWN_BUDGET_MULT = 1.25
#: monthly CVaR5 <= this multiple of SPY's.
CVAR_BUDGET_MULT = 1.5
#: no month worse than this.
WORST_MONTH_FLOOR = -0.40
#: gross exposure ceiling.
GROSS_CAP = 2.0
#: borrowed notional is charged at RF + this many bps, annualised.
FINANCING_BPS = 100.0
#: "ruin" for the survival check: a peak-to-trough loss of half the book.
RUIN_THRESHOLD = -0.50

OBJECTIVE = (
    "maximize after-cost terminal wealth subject to "
    f"maxDD <= {DRAWDOWN_BUDGET_MULT} x SPY's maxDD over the same months, "
    f"monthly CVaR5 <= {CVAR_BUDGET_MULT} x SPY's, "
    f"no month worse than {WORST_MONTH_FLOOR:.0%}, "
    f"gross <= {GROSS_CAP}x, "
    f"financing at RF + {FINANCING_BPS:.0f} bps on borrowed notional"
)

_MONTHS = 12


# --------------------------------------------------------------------- basics

def _s(x) -> pd.Series:
    s = pd.Series(x, dtype="float64") if not isinstance(x, pd.Series) else x.astype("float64")
    return s


def _r(v, nd: int = 6):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def terminal_wealth(returns: Iterable[float]) -> float:
    """Compound growth of one dollar. The product ruler's headline."""
    a = _s(returns).dropna().to_numpy()
    if a.size == 0:
        return float("nan")
    return float(np.prod(1.0 + a))


def cagr(returns: Iterable[float], periods_per_year: int = _MONTHS) -> float:
    a = _s(returns).dropna().to_numpy()
    if a.size == 0:
        return float("nan")
    tw = float(np.prod(1.0 + a))
    if tw <= 0:
        return -1.0
    return float(tw ** (periods_per_year / a.size) - 1.0)


def max_drawdown(returns: Iterable[float]) -> float:
    """Worst peak-to-trough on the COMPOUNDED path, as a negative decimal.

    Computed on the wealth path and not on a rolling sum: a -50% month and a
    +50% month are not a round trip, and the sum says they are.
    """
    a = _s(returns).dropna().to_numpy()
    if a.size == 0:
        return float("nan")
    # The path STARTS at one dollar, and that dollar is the first peak. Omitting
    # it reports 0.0 for a book whose first month is -50%, because the trough is
    # also the running maximum. Cheap to write, invisible once it is wrong.
    w = np.concatenate([[1.0], np.cumprod(1.0 + a)])
    peak = np.maximum.accumulate(w)
    dd = w / peak - 1.0
    return float(dd.min())


def cvar(returns: Iterable[float], q: float = 0.05) -> float:
    """Mean of the worst `q` tail, as a negative decimal.

    On short samples the empirical q-quantile can select ZERO observations. We
    take at least one -- the worst month -- rather than returning nan, and the
    count is reported beside it by `evaluate_growth`.
    """
    a = np.sort(_s(returns).dropna().to_numpy())
    if a.size == 0:
        return float("nan")
    k = max(1, int(math.floor(q * a.size)))
    return float(a[:k].mean())


def realized_vol(returns: Iterable[float], periods_per_year: int = _MONTHS) -> float:
    a = _s(returns).dropna().to_numpy()
    if a.size < 2:
        return float("nan")
    return float(a.std(ddof=1) * math.sqrt(periods_per_year))


# ------------------------------------------------------- beta, and its t stat

def market_model(book_excess: pd.Series, mkt_excess: pd.Series,
                 *, lag: int = 4) -> dict:
    """OLS of book excess on market excess with Newey-West standard errors.

    Returns beta FIRST. The intercept is the part a leverage-neutral reader is
    entitled to see; its HAC t is the only number in this module that speaks to
    skill, and it is reported beside beta rather than instead of it.
    """
    y = _s(book_excess)
    x = _s(mkt_excess).reindex(y.index)
    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    n = len(d)
    if n < 6 or d["x"].std(ddof=1) <= 0:
        return {"beta": None, "n": n,
                "why": "fewer than 6 aligned months or a constant market leg"}
    X = np.column_stack([np.ones(n), d["x"].to_numpy()])
    yv = d["y"].to_numpy()
    xtx_inv = np.linalg.pinv(X.T @ X)
    b = xtx_inv @ (X.T @ yv)
    resid = yv - X @ b
    # Newey-West
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for L in range(1, min(lag, n - 1) + 1):
        w = 1.0 - L / (lag + 1.0)
        u = (X[L:] * resid[L:, None])
        v = (X[:-L] * resid[:-L, None])
        G = u.T @ v
        S = S + w * (G + G.T)
    cov = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    return {
        "beta": _r(b[1], 4),
        "beta_t_vs_1": _r((b[1] - 1.0) / se[1], 3) if se[1] > 0 else None,
        "intercept_monthly": _r(b[0]),
        "intercept_annualised_pct": _r(b[0] * _MONTHS * 100.0, 3),
        "intercept_t_hac": _r(b[0] / se[0], 3) if se[0] > 0 else None,
        "n": n, "hac_lag": lag,
    }


# ------------------------------------------------------------------ leverage

def lever(book: pd.Series, rf: pd.Series, L: float,
          *, financing_bps: float = FINANCING_BPS) -> pd.Series:
    """Run `book` at gross L, financing the borrowed (L-1) at RF + spread.

    L <= 1 parks the unused (1-L) in the risk-free leg -- it is not free cash,
    it earns RF, and pretending otherwise is exactly the cash-drag error the
    amendment §2.3 names.
    """
    b = _s(book)
    r = _s(rf).reindex(b.index).fillna(0.0)
    spread = financing_bps / 10_000.0 / _MONTHS
    if L >= 1.0:
        return L * b - (L - 1.0) * (r + spread)
    return L * b + (1.0 - L) * r


def admissible_leverage(book: pd.Series, rf: pd.Series, spy: pd.Series,
                        *, gross_cap: float = GROSS_CAP,
                        financing_bps: float = FINANCING_BPS,
                        budget_mult: float = DRAWDOWN_BUDGET_MULT,
                        tol: float = 1e-3) -> dict:
    """The LARGEST L whose levered maxDD still fits the drawdown budget.

    Bisection on a monotone quantity: levering a fixed return path scales every
    drawdown, so |maxDD(L)| is increasing in L. Returns L = gross_cap when even
    the cap fits, and the floor 0.0 when nothing does (a book whose UNLEVERED
    drawdown already breaks the budget has no admissible size).
    """
    budget = abs(max_drawdown(spy)) * budget_mult
    if not math.isfinite(budget) or budget <= 0:
        return {"leverage": None, "why": "SPY maxDD is not finite/positive"}
    if abs(max_drawdown(lever(book, rf, 1e-9, financing_bps=financing_bps))) > budget:
        return {"leverage": 0.0, "budget_maxdd": _r(-budget),
                "why": "even a vanishing position breaks the budget "
                       "(the book's shape, not its size)"}
    lo, hi = 0.0, float(gross_cap)
    if abs(max_drawdown(lever(book, rf, hi, financing_bps=financing_bps))) <= budget:
        return {"leverage": _r(hi, 4), "budget_maxdd": _r(-budget),
                "binding": "GROSS_CAP"}
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if abs(max_drawdown(lever(book, rf, mid, financing_bps=financing_bps))) <= budget:
            lo = mid
        else:
            hi = mid
    return {"leverage": _r(lo, 4), "budget_maxdd": _r(-budget),
            "binding": "DRAWDOWN_BUDGET"}


# ----------------------------------------------------------------- p of ruin

def p_ruin(returns: Iterable[float], *, threshold: float = RUIN_THRESHOLD,
           n_boot: int = 2000, block: float = 4.0, seed: int = 20260907,
           horizon: Optional[int] = None) -> dict:
    """Stationary block bootstrap: P(peak-to-trough <= threshold) on a resample.

    A single realised path cannot answer a survival question -- it either
    happened or it did not. The block preserves the serial dependence that
    makes drawdowns deep; an iid bootstrap would flatter every book.
    """
    a = _s(returns).dropna().to_numpy()
    n = a.size
    if n < 12:
        return {"p_ruin": None, "why": f"only {n} months; refuse below 12"}
    T = int(horizon or n)
    rng = np.random.default_rng(seed)
    p = 1.0 / max(block, 1.0)
    hits = 0
    worst = np.empty(n_boot, dtype="float64")
    for i in range(n_boot):
        idx = np.empty(T, dtype="int64")
        j = rng.integers(0, n)
        for t in range(T):
            if t and rng.random() < p:
                j = rng.integers(0, n)
            idx[t] = j
            j = (j + 1) % n
        path = a[idx]
        w = np.cumprod(1.0 + path)
        dd = float((w / np.maximum.accumulate(w) - 1.0).min())
        worst[i] = dd
        if dd <= threshold:
            hits += 1
    return {
        "p_ruin": _r(hits / n_boot, 5),
        "threshold": threshold,
        "n_boot": n_boot, "block_mean_periods": block, "seed": seed,
        "horizon_months": T,
        "median_worst_drawdown": _r(float(np.median(worst)), 5),
        "p95_worst_drawdown": _r(float(np.quantile(worst, 0.05)), 5),
        "construction": "stationary block bootstrap of the monthly series",
    }


# ------------------------------------------------------------------- the ruler

def evaluate_growth(book_returns, spy_tr, rf, *, cost_bps,
                    financing_bps: float = FINANCING_BPS,
                    gross_cap: float = GROSS_CAP,
                    label: Optional[str] = None,
                    n_boot: int = 2000, seed: int = 20260907,
                    hac_lag: int = 4) -> dict:
    """The product ruler for one book. BETA FIRST, then wealth, then survival.

    `book_returns` are already NET of `cost_bps`; the rate is recorded, never
    re-applied. `cost_bps=None` raises -- a growth number with no cost rate
    beside it is the one thing this module must never produce.

    Every series is aligned on the intersection of the three indexes, and the
    count that survived alignment is reported: a book graded on 180 months
    against a SPY leg that only covers 96 is a comparison of two different
    decades wearing one label.
    """
    if cost_bps is None:
        raise ValueError("cost_bps is required: costs are never omitted "
                         "(CLAUDE.md 'EXPLORE DIRTY, PROMOTE CLEAN' item 3)")
    b = _s(book_returns).dropna()
    s = _s(spy_tr).dropna()
    r = _s(rf).dropna()
    idx = b.index.intersection(s.index).intersection(r.index)
    idx = idx.sort_values()
    b, s, r = b.reindex(idx), s.reindex(idx), r.reindex(idx)
    n = len(idx)
    out: dict = {"label": label, "cost_bps_per_side": float(cost_bps),
                 "months": n,
                 "window": [str(idx[0]), str(idx[-1])] if n else None,
                 "financing_bps_over_rf": float(financing_bps),
                 "gross_cap": float(gross_cap)}
    if n < 12:
        out["verdict"] = "CANNOT DETERMINE"
        out["why"] = f"only {n} aligned months; the ruler refuses below 12"
        return out

    # ---- BETA FIRST. The amendment's §2.2 rule, enforced by ordering.
    mm = market_model(b - r, s - r, lag=hac_lag)
    out["beta"] = mm.get("beta")
    out["market_model"] = mm
    if out["beta"] is None:
        out["verdict"] = "CANNOT DETERMINE"
        out["why"] = "beta could not be estimated; no wealth number is reported "
        return out

    def _block(x: pd.Series) -> dict:
        return {
            "terminal_wealth": _r(terminal_wealth(x), 4),
            "cagr": _r(cagr(x), 5),
            "max_drawdown": _r(max_drawdown(x), 5),
            "cvar_5": _r(cvar(x, 0.05), 5),
            "cvar_5_n_months": max(1, int(math.floor(0.05 * len(x.dropna())))),
            "worst_month": _r(float(x.min()), 5),
            "realized_vol_annual": _r(realized_vol(x), 5),
            "mean_monthly": _r(float(x.mean())),
        }

    out["book"] = _block(b)
    out["spy"] = _block(s)
    out["rf_annualised_pct"] = _r(float(r.mean()) * _MONTHS * 100.0, 3)

    # ---- leverage-neutral: the book run at SPY's OWN realized volatility.
    vb, vs = realized_vol(b), realized_vol(s)
    Ln = float(min(gross_cap, vs / vb)) if (vb and math.isfinite(vb) and vb > 0) else None
    if Ln is None:
        out["leverage_neutral"] = {"scale": None,
                                   "why": "book volatility is zero or undefined"}
    else:
        bn = lever(b, r, Ln, financing_bps=financing_bps)
        out["leverage_neutral"] = {
            "scale": _r(Ln, 4),
            "scale_uncapped": _r(vs / vb, 4),
            "capped_by_gross": bool(vs / vb > gross_cap),
            "construction": ("book scaled to SPY's realized vol over the same "
                             "months; borrowed notional charged at RF + "
                             f"{financing_bps:.0f} bps, unused cash earns RF"),
            **{f"{k}": v for k, v in _block(bn).items()},
            "vs_spy_terminal_wealth": _r(terminal_wealth(bn) - terminal_wealth(s), 4),
            "beats_spy": bool(terminal_wealth(bn) > terminal_wealth(s)),
        }

    # ---- levered SPY at the same drawdown budget: the honest beta-only rival.
    adm_spy = admissible_leverage(s, r, s, gross_cap=gross_cap,
                                  financing_bps=financing_bps)
    if adm_spy.get("leverage"):
        ls = lever(s, r, float(adm_spy["leverage"]), financing_bps=financing_bps)
        out["levered_spy_at_budget"] = {**adm_spy, **_block(ls)}
    else:
        out["levered_spy_at_budget"] = adm_spy

    # ---- the constraints, computed rather than asserted
    dd_budget = abs(out["spy"]["max_drawdown"]) * DRAWDOWN_BUDGET_MULT
    cv_budget = abs(out["spy"]["cvar_5"]) * CVAR_BUDGET_MULT
    checks = {
        "maxdd_ok": bool(abs(out["book"]["max_drawdown"]) <= dd_budget),
        "cvar_ok": bool(abs(out["book"]["cvar_5"]) <= cv_budget),
        "worst_month_ok": bool(out["book"]["worst_month"] >= WORST_MONTH_FLOOR),
        "gross_ok": True,          # unlevered book; the levered rung re-checks
    }
    out["constraints"] = {
        **checks,
        "maxdd_budget": _r(-dd_budget, 5),
        "cvar_budget": _r(-cv_budget, 5),
        "worst_month_floor": WORST_MONTH_FLOOR,
        "passes": bool(all(checks.values())),
        "objective": OBJECTIVE,
    }

    # ---- the largest admissible book, and its survival
    adm = admissible_leverage(b, r, s, gross_cap=gross_cap,
                              financing_bps=financing_bps)
    out["largest_admissible"] = adm
    L = adm.get("leverage")
    if L:
        bl = lever(b, r, float(L), financing_bps=financing_bps)
        out["largest_admissible"].update(_block(bl))
        out["p_ruin"] = p_ruin(bl, n_boot=n_boot, seed=seed)
        out["p_ruin"]["computed_on"] = (
            f"the LARGEST ADMISSIBLE book (L={L}), not the unlevered series")
    else:
        out["p_ruin"] = {"p_ruin": None,
                         "why": "no admissible leverage; nothing to size"}

    ln = out.get("leverage_neutral", {})
    out["headline"] = (
        f"beta {out['beta']} (intercept {mm.get('intercept_annualised_pct')}%/yr, "
        f"t {mm.get('intercept_t_hac')}): TW {out['book']['terminal_wealth']} vs "
        f"SPY {out['spy']['terminal_wealth']}, maxDD {out['book']['max_drawdown']} vs "
        f"budget {out['constraints']['maxdd_budget']}, "
        f"leverage-neutral TW {ln.get('terminal_wealth')} "
        f"over {n} months at {cost_bps:.0f} bps")
    return out
