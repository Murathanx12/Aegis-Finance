"""E3 -- adaptive conformal intervals, and the coverage table that judges them.

WHY NOT PLAIN SPLIT CONFORMAL. Split conformal's guarantee is exchangeability,
and daily equity returns are not exchangeable across a volatility regime
change: the residual pool that sized yesterday's interval was drawn from a
calmer tape. The failure is not subtle -- a 90% interval delivering ~50%
realised coverage in a high-vol window is the number
`docs/research_notes/2026-09-11/research_nn.md` section 4 already flags. So the
naive method is not a straw man here; it is the thing being demonstrated, and
its collapse in the HIGH-vol tercile is the point of the receipt.

TWO MECHANISMS, USED TOGETHER, NOT AS ALTERNATIVES.

1. **ACI** -- Gibbs & Candes, "Adaptive Conformal Inference Under Distribution
   Shift", NeurIPS 2021. One line, applied once per realised outcome:

       err_t   = 1[y_t not in C_t(alpha_t)]
       alpha_{t+1} = alpha_t + gamma * (alpha - err_t)

   It tracks the miscoverage LEVEL: miss too often and alpha falls, so the next
   interval widens. `alpha_t` is clipped to [0.001, 0.999] -- a deviation from
   the paper, which works in a continuous idealisation where the quantile
   lookup is always defined. The clip is recorded in every receipt.

2. **Non-exchangeable weighting** -- Barber, Candes, Ramdas & Tibshirani,
   "Conformal Prediction Beyond Exchangeability", Annals of Statistics 51(2)
   816-845, 2023 (DOI 10.1214/23-AOS2276). Replace the uniform empirical
   quantile of past nonconformity scores with a recency-weighted one,
   `w_i = rho^(t-i)`. It changes WHICH residuals count. `rho = 1.0` recovers
   the unweighted case exactly, so the sweep contains its own control point and
   there is no second code path to keep in step.

ACI adapts the level; the weights adapt the pool. A receipt that reports only
one of them cannot say which did the work, so `coverage_table` always runs
three methods: NAIVE (fixed alpha, rho=1), ACI (rho=1), ACI_WEIGHTED.

WHAT THIS MODULE DOES NOT DO. It does not decide what the point prediction is,
it does not size anything, and it never sees a price. It is given predictions,
outcomes and a regime label, and it returns intervals and the coverage they
actually delivered. `backend/services/calibration.py` owns ECE/Murphy for
probabilities; this is the interval-valued sibling and deliberately does not
duplicate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: ACI's step size. Gibbs & Candes' own framing: larger adapts faster and makes
#: `alpha_t` noisier. 0.01-0.05 is their range for daily data; the sweep in the
#: night job reports the whole grid rather than this file choosing.
DEFAULT_GAMMA = 0.02

#: the implementation clip on `alpha_t`. Outside it a quantile lookup on a
#: finite residual pool is not defined.
ALPHA_FLOOR, ALPHA_CEIL = 0.001, 0.999

#: recency decays swept by the night job. 1.0 IS the exchangeable control.
RHO_GRID = (0.90, 0.95, 0.99, 1.0)


def weighted_quantile(values: np.ndarray, level: float,
                      weights: np.ndarray | None = None) -> float:
    """The `level`-quantile of `values` under `weights` (uniform when None).

    The convention is the conformal one: the smallest value whose cumulative
    normalised weight reaches `level`. With uniform weights and `level` on a
    grid point this agrees with `np.quantile(..., method="higher")`, which the
    test checks rather than assumes.
    """
    v = np.asarray(values, dtype=float)
    keep = np.isfinite(v)
    v = v[keep]
    if not len(v):
        return float("nan")
    w = np.ones(len(v)) if weights is None else np.asarray(weights, dtype=float)[keep]
    if w.sum() <= 0:
        return float("nan")
    order = np.argsort(v)
    v, w = v[order], w[order]
    c = np.cumsum(w) / w.sum()
    level = float(min(max(level, 0.0), 1.0))
    i = int(np.searchsorted(c, level, side="left"))
    return float(v[min(i, len(v) - 1)])


def recency_weights(n: int, rho: float) -> np.ndarray:
    """`w_i = rho^(t-i)` over a pool ordered oldest-first. rho=1 is uniform."""
    rho = float(rho)
    if rho >= 1.0:
        return np.ones(int(n), dtype=float)
    ages = np.arange(int(n) - 1, -1, -1, dtype=float)
    return np.power(rho, ages)


def aci_step(alpha_t: float, err: int, target_alpha: float,
             gamma: float = DEFAULT_GAMMA) -> float:
    """Gibbs & Candes' update, verbatim, plus the documented clip."""
    nxt = float(alpha_t) + float(gamma) * (float(target_alpha) - float(err))
    return float(min(max(nxt, ALPHA_FLOOR), ALPHA_CEIL))


@dataclass
class ConformalRun:
    """One pass of one method over one stream. Every field is per step."""
    method: str
    alpha_target: float
    gamma: float
    rho: float
    lo: list[float] = field(default_factory=list)
    hi: list[float] = field(default_factory=list)
    alpha_t: list[float] = field(default_factory=list)
    covered: list[int] = field(default_factory=list)
    width: list[float] = field(default_factory=list)

    def as_arrays(self) -> dict:
        return {k: np.asarray(getattr(self, k), dtype=float)
                for k in ("lo", "hi", "alpha_t", "covered", "width")}


def run_stream(pred: np.ndarray, truth: np.ndarray, *, alpha: float = 0.10,
               gamma: float = DEFAULT_GAMMA, rho: float = 1.0, adaptive: bool = True,
               warmup: int = 30, pool: int = 500) -> ConformalRun:
    """Walk the stream once, forming each interval from residuals SEEN SO FAR.

    Step t uses only residuals from steps < t. The interval is
    `pred_t +/- q`, where `q` is the (1 - alpha_t) weighted quantile of the
    trailing absolute residuals -- so nothing about step t is used to size step
    t's own interval, which is the property that makes the realised coverage
    meaningful rather than circular. Steps before `warmup` residuals exist are
    not graded (NaN interval, not covered, excluded from every count).
    """
    pred = np.asarray(pred, dtype=float)
    truth = np.asarray(truth, dtype=float)
    if len(pred) != len(truth):
        raise ValueError("pred and truth must be the same length")
    method = ("ACI_WEIGHTED" if (adaptive and rho < 1.0)
              else "ACI" if adaptive else "NAIVE")
    run = ConformalRun(method=method, alpha_target=float(alpha), gamma=float(gamma),
                       rho=float(rho))
    resid: list[float] = []
    a_t = float(alpha)
    for t in range(len(pred)):
        if len(resid) < int(warmup) or not np.isfinite(pred[t]) or not np.isfinite(truth[t]):
            run.lo.append(float("nan"))
            run.hi.append(float("nan"))
            run.alpha_t.append(a_t)
            run.covered.append(-1)                # -1 = not graded, never 0
            run.width.append(float("nan"))
            if np.isfinite(pred[t]) and np.isfinite(truth[t]):
                resid.append(abs(truth[t] - pred[t]))
                resid = resid[-int(pool):]
            continue
        w = recency_weights(len(resid), rho)
        q = weighted_quantile(np.asarray(resid), 1.0 - a_t, w)
        lo, hi = pred[t] - q, pred[t] + q
        cov = int(lo <= truth[t] <= hi)
        run.lo.append(float(lo))
        run.hi.append(float(hi))
        run.alpha_t.append(float(a_t))
        run.covered.append(cov)
        run.width.append(float(hi - lo))
        if adaptive:
            a_t = aci_step(a_t, 1 - cov, float(alpha), gamma)
        resid.append(abs(truth[t] - pred[t]))
        resid = resid[-int(pool):]
    return run


def terciles(x: np.ndarray) -> np.ndarray:
    """LOW / MID / HIGH by the finite values' own 33rd and 67th percentiles.

    Returns an integer array with -1 where the regime could not be computed,
    so an ungraded step is never quietly filed under LOW.
    """
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), -1, dtype=int)
    fin = np.isfinite(x)
    if fin.sum() < 3:
        return out
    lo, hi = np.quantile(x[fin], [1 / 3, 2 / 3])
    out[fin] = np.where(x[fin] <= lo, 0, np.where(x[fin] <= hi, 1, 2))
    return out


_REGIME_NAMES = {0: "LOW", 1: "MID", 2: "HIGH"}


def coverage_table(runs: dict[str, ConformalRun], regime: np.ndarray) -> dict:
    """THE RECEIPT'S HEADLINE: realised coverage per method per vol tercile.

    Not a footnote under a point estimate -- the roadmap item's own wording is
    "the realised coverage per vol regime as the receipt's headline". A cell
    with fewer than 10 graded blocks reports CANNOT DETERMINE rather than a
    coverage computed from four observations.
    """
    regime = np.asarray(regime, dtype=int)
    out: dict[str, dict] = {}
    for name, run in runs.items():
        a = run.as_arrays()
        graded = a["covered"] >= 0
        cells = {}
        for key, mask in [("ALL", graded)] + [
                (_REGIME_NAMES[r], graded & (regime == r)) for r in (0, 1, 2)]:
            n = int(mask.sum())
            if n < 10:
                cells[key] = {"n_date_blocks": n, "status": "CANNOT DETERMINE -- fewer than 10 graded blocks"}
                continue
            cells[key] = {
                "n_date_blocks": n,
                "nominal_coverage": round(float(1.0 - np.mean(a["alpha_t"][mask])), 4),
                "realised_coverage": round(float(np.mean(a["covered"][mask])), 4),
                "mean_interval_width": round(float(np.nanmean(a["width"][mask])), 6),
            }
        out[name] = {"method": run.method, "alpha_target": run.alpha_target,
                     "gamma": run.gamma, "rho": run.rho, "by_vol_tercile": cells}
    return out


def declaration() -> dict:
    """What this module is, for a receipt that has to name its method."""
    return {
        "module": "backend.services.conformal",
        "methods": ["NAIVE (fixed alpha, uniform weights)",
                    "ACI (Gibbs & Candes 2021, alpha tracking)",
                    "ACI_WEIGHTED (ACI + Barber et al. 2023 recency weights rho^(t-i))"],
        "citations": {
            "aci": "Gibbs & Candes, Adaptive Conformal Inference Under Distribution Shift, NeurIPS 2021",
            "non_exchangeable": ("Barber, Candes, Ramdas & Tibshirani, Conformal Prediction "
                                 "Beyond Exchangeability, Ann. Statist. 51(2) 816-845, 2023, "
                                 "DOI 10.1214/23-AOS2276"),
        },
        "deviations": [f"alpha_t clipped to [{ALPHA_FLOOR}, {ALPHA_CEIL}] so the quantile "
                       "lookup on a finite residual pool is defined"],
        "rho_grid": list(RHO_GRID),
        "control_point": "rho = 1.0 IS the exchangeable control; no separate code path exists",
    }
