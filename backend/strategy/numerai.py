"""S8 -- NUMERAI HABITS IN THE LEARNER: per-era scoring, neutralisation,
era-boosting, and MMC.

THE ONE THAT MATTERS IS MMC
===========================
`COMPOSITE_WEIGHTS` is momentum 1.0 + multifactor 1.0 + four 0.5s, and coverage
is `{"1": 206, "6": 1}`: 99.5% of arena names carry exactly one factor, 12-1
momentum. Every new mechanism in this repository has been graded on whether it
predicts returns. NONE has been graded on whether it predicts returns THAT
MOMENTUM DOES NOT ALREADY PREDICT, which is the only question that decides
whether adding it changes any portfolio.

MMC answers exactly that, as a number: neutralise the candidate against the
ensemble it would join, then score what is left. `MMC ~ 0` is therefore the
EXPECTED NULL for anything momentum-shaped -- a book can have a healthy IC and
a zero MMC, and that book is a re-expression, not a mechanism. A genuinely
positive MMC would be a real result.

THE DEFINITION USED HERE, and how it differs from numer.ai's
============================================================
Per era:
    p  = gaussianise(rank(prediction))           # tie-broken, shape-free
    m  = gaussianise(rank(meta_model))
    r  = p - beta * m,  beta = cov(p, m) / var(m)      # OLS residual
    t  = target - mean(target)
    corr = mean(p * t) / (sd(p) * sd(t))
    MMC  = mean(r * t) / (sd(p) * sd(t))               # SAME denominator

The scores are then averaged over eras. numer.ai divides by a fixed constant
(0.29^2, the standard deviation of THEIR target); that constant is meaningless
on a returns panel, so the denominator here is the candidate's own scale --
`sd(p) * sd(t)`, the same denominator `corr` uses. Two properties follow, and
both are pinned by tests because they are what make the number readable:

  * a book scored against ITSELF as the meta-model has MMC exactly 0;
  * a book scored against a meta-model uncorrelated with it has MMC == corr.

So MMC is on the same scale as the correlation beside it, and
`corr - MMC` is precisely the part of the book's signal the ensemble already
had. That is the sentence the roadmap asks for -- "are its errors DIFFERENT
errors?" -- as an arithmetic quantity.

WHAT IS NOT CLAIMED
===================
MMC is a CORRELATION-space statement about one panel and one meta-model. It is
not a portfolio result, not net of costs, and not evidence that a positive-MMC
book makes money. A positive MMC says "this is not the ensemble"; a book still
has to beat its benchmark after costs, at a beta, on its own receipt.

SOURCE: docs.numer.ai (per-era scoring, feature neutralisation, era boosting,
MMC). Public documentation of a method, reimplemented; no code copied.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: An era with fewer than this many names cannot support a cross-sectional
#: correlation; it is DROPPED and COUNTED, never scored on three rows.
MIN_NAMES_PER_ERA = 20


class EraScoringRefused(ValueError):
    """The panel cannot support a per-era score as asked."""


# --------------------------------------------------------------------------
# primitives


def gaussianize(x: Sequence[float] | pd.Series) -> np.ndarray:
    """Rank to uniform, then to a standard normal. Ties get average ranks.

    Shape-free by construction: two books that order names identically get the
    same vector however differently they scale their scores, which is the whole
    reason the comparison is done here rather than on raw predictions.
    """
    from scipy.stats import norm

    s = pd.Series(list(x), dtype=float)
    ok = s.notna()
    out = np.full(len(s), np.nan)
    if int(ok.sum()) < 2:
        return out
    r = s[ok].rank(method="average")
    u = (r - 0.5) / len(r)
    out[ok.to_numpy()] = norm.ppf(u.to_numpy())
    return out


def _pair(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m = np.isfinite(a) & np.isfinite(b)
    return a[m], b[m]


def neutralize(predictions: Sequence[float] | pd.Series,
               exposures: pd.DataFrame | pd.Series,
               *, proportion: float = 1.0) -> np.ndarray:
    """Residualise a prediction against one or more exposures (OLS, no intercept
    beyond the centring already done by gaussianising).

    `proportion=1.0` removes the exposure entirely; 0.5 removes half. The
    partial form exists because full neutralisation of a factor a book is
    SUPPOSED to express destroys the book, and half is often the honest
    compromise -- but it must be declared, so it is an argument and it lands on
    the receipt.
    """
    y = np.asarray(pd.Series(list(predictions), dtype=float), dtype=float)
    X = pd.DataFrame(exposures).astype(float)
    if X.shape[0] != len(y):
        raise EraScoringRefused(
            f"REFUSED: {len(y)} predictions against {X.shape[0]} exposure rows.")
    Xv = X.to_numpy(dtype=float)
    ok = np.isfinite(y) & np.isfinite(Xv).all(axis=1)
    out = np.full(len(y), np.nan)
    if int(ok.sum()) < 2 or Xv.shape[1] == 0:
        return out
    A = Xv[ok]
    A = A - A.mean(axis=0, keepdims=True)
    yy = y[ok] - y[ok].mean()
    beta, *_ = np.linalg.lstsq(A, yy, rcond=None)
    out[ok] = yy - float(proportion) * (A @ beta)
    return out


# --------------------------------------------------------------------------
# per-era scoring


def per_era_scores(df: pd.DataFrame, *, pred_col: str, target_col: str,
                   era_col: str, min_names: int = MIN_NAMES_PER_ERA) -> dict:
    """One score per era, then the distribution of those scores.

    CANON section 58: `n_effective` counts DATE BLOCKS, not name-days. An era
    IS the date block, so the era count is the sample size and the t is
    computed on it -- pooling 259,234 name-days once printed t -65 for an
    effect that was t -16.6 per period.
    """
    for c in (pred_col, target_col, era_col):
        if c not in df.columns:
            raise EraScoringRefused(f"REFUSED: no column {c!r} in the panel.")

    rows: list[dict] = []
    dropped: dict[str, str] = {}
    for era, g in df.groupby(era_col, sort=True):
        gg = g[[pred_col, target_col]].dropna()
        if len(gg) < int(min_names):
            dropped[str(era)] = (
                f"{len(gg)} usable name(s) < min_names {min_names}; a "
                f"cross-sectional correlation on that many rows is noise")
            continue
        p = gaussianize(gg[pred_col])
        t = gg[target_col].to_numpy(dtype=float)
        p, t = _pair(p, t)
        if len(p) < int(min_names) or p.std() == 0 or t.std() == 0:
            dropped[str(era)] = "degenerate: zero variance after alignment"
            continue
        rows.append({"era": era, "n": int(len(p)),
                     "corr": float(np.corrcoef(p, t)[0, 1])})

    if not rows:
        return {"verdict": (f"{CANNOT_DETERMINE}: no era survived the "
                            f"min_names {min_names} filter."),
                "n_eras": 0, "eras_dropped": dropped}

    s = pd.Series([r["corr"] for r in rows], dtype=float)
    n = int(len(s))
    sd = float(s.std(ddof=1)) if n > 1 else float("nan")
    t = float(s.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else None
    return {
        "n_eras": n,
        "n_eras_dropped": len(dropped),
        "eras_dropped": dropped,
        "mean_corr": float(s.mean()),
        "sd_corr": sd,
        "sharpe_of_era_corr": (float(s.mean() / sd) if sd > 0 else None),
        "share_of_eras_positive": float((s > 0).mean()),
        "worst_era": {"era": rows[int(s.idxmin())]["era"], "corr": float(s.min())},
        "best_era": {"era": rows[int(s.idxmax())]["era"], "corr": float(s.max())},
        "t_on_eras": t,
        "by_era": rows,
        "n_effective": n,
        "n_effective_note": ("the sample size is the ERA count, not the "
                             "name-day count (CANON section 58)"),
    }


# --------------------------------------------------------------------------
# era boosting


def era_boost_weights(era_scores: Mapping[Any, float], *,
                      keep_fraction: float = 0.5,
                      boost: float = 2.0) -> dict:
    """Upweight the WORST eras. The model that only works in easy regimes is
    the model whose excess is five months (S42), and era boosting is the
    training-side answer to it: fit again with the eras it did worst on
    weighted up, and see whether anything survives.

    Returns weights per era summing to the era count, so a caller can multiply
    them onto sample weights without changing the effective sample size.
    """
    if not era_scores:
        return {"verdict": f"{CANNOT_DETERMINE}: no era scores.", "weights": {}}
    if not 0.0 < keep_fraction <= 1.0:
        raise EraScoringRefused("keep_fraction must be in (0, 1]")
    s = pd.Series(dict(era_scores), dtype=float).dropna()
    if s.empty:
        return {"verdict": f"{CANNOT_DETERMINE}: every era score is NaN.",
                "weights": {}}
    k = max(1, int(round(len(s) * float(keep_fraction))))
    worst = set(s.nsmallest(k).index)
    raw = pd.Series({e: (float(boost) if e in worst else 1.0) for e in s.index})
    w = raw * (len(s) / raw.sum())
    return {
        "weights": {str(k_): float(v) for k_, v in w.items()},
        "boosted_eras": sorted(str(e) for e in worst),
        "keep_fraction": float(keep_fraction),
        "boost": float(boost),
        "n_eras": int(len(s)),
        "note": ("weights sum to the era count, so the effective sample size "
                 "is unchanged and only the emphasis moves"),
    }


# --------------------------------------------------------------------------
# MMC -- the marginal contribution


def mmc(df: pd.DataFrame, *, pred_col: str, meta_col: str, target_col: str,
        era_col: str, min_names: int = MIN_NAMES_PER_ERA) -> dict:
    """Marginal contribution of `pred_col` over `meta_col`. See the module head.

    Returns `corr`, `mmc` and `corr_with_meta` per era and averaged, plus the
    verdict. `corr - mmc` is the part of the book's signal the ensemble already
    had.
    """
    for c in (pred_col, meta_col, target_col, era_col):
        if c not in df.columns:
            raise EraScoringRefused(f"REFUSED: no column {c!r} in the panel.")

    # dict.fromkeys, not a set: pred_col == meta_col is the SELF case, which is
    # a known answer this module is tested on, and a duplicated label would make
    # `gg[pred_col]` a frame instead of a series.
    cols = list(dict.fromkeys([pred_col, meta_col, target_col]))
    rows: list[dict] = []
    dropped: dict[str, str] = {}
    for era, g in df.groupby(era_col, sort=True):
        gg = g[cols].dropna()
        if len(gg) < int(min_names):
            dropped[str(era)] = f"{len(gg)} usable name(s) < {min_names}"
            continue
        p = gaussianize(gg[pred_col])
        m = gaussianize(gg[meta_col])
        t = gg[target_col].to_numpy(dtype=float)
        ok = np.isfinite(p) & np.isfinite(m) & np.isfinite(t)
        p, m, t = p[ok], m[ok], t[ok]
        if len(p) < int(min_names) or p.std() == 0 or t.std() == 0:
            dropped[str(era)] = "degenerate: zero variance"
            continue
        tc = t - t.mean()
        pc = p - p.mean()
        mc = m - m.mean()
        beta = float(mc @ pc / (mc @ mc)) if float(mc @ mc) > 0 else 0.0
        resid = pc - beta * mc
        denom = float(p.std() * t.std())
        rows.append({
            "era": era, "n": int(len(p)),
            "corr": float(np.mean(pc * tc) / denom),
            "mmc": float(np.mean(resid * tc) / denom),
            "corr_with_meta": (float(np.corrcoef(p, m)[0, 1])
                               if m.std() > 0 else None),
            "meta_corr": (float(np.mean(mc * tc) / (m.std() * t.std()))
                          if m.std() > 0 else None),
        })

    if not rows:
        return {"verdict": (f"{CANNOT_DETERMINE}: no era survived the "
                            f"min_names {min_names} filter."),
                "n_eras": 0, "eras_dropped": dropped}

    f = pd.DataFrame(rows)
    n = len(f)

    def _t(col: str):
        sd = float(f[col].std(ddof=1)) if n > 1 else float("nan")
        return (float(f[col].mean() / (sd / np.sqrt(n)))
                if n > 1 and sd > 0 else None), sd

    t_mmc, sd_mmc = _t("mmc")
    t_corr, _ = _t("corr")
    mean_mmc = float(f["mmc"].mean())
    mean_corr = float(f["corr"].mean())
    return {
        "pred": pred_col, "meta_model": meta_col, "target": target_col,
        "n_eras": n, "n_eras_dropped": len(dropped),
        "mean_corr": mean_corr,
        "mean_mmc": mean_mmc,
        "sd_mmc": sd_mmc,
        "t_mmc_on_eras": t_mmc,
        "t_corr_on_eras": t_corr,
        "share_of_eras_mmc_positive": float((f["mmc"] > 0).mean()),
        "mean_corr_with_meta": float(f["corr_with_meta"].mean(skipna=True)),
        "mean_meta_corr": float(f["meta_corr"].mean(skipna=True)),
        "explained_by_the_ensemble": mean_corr - mean_mmc,
        "share_of_signal_the_ensemble_already_had": (
            (mean_corr - mean_mmc) / mean_corr if mean_corr != 0 else None),
        "eras_dropped": dropped,
        "by_era": rows,
        "verdict": _mmc_verdict(mean_corr, mean_mmc, t_mmc),
        "definition": ("MMC = mean(resid * centred target) / (sd(gauss pred) * "
                       "sd(target)), resid = gauss pred orthogonalised against "
                       "gauss meta-model, per era, then averaged. Same "
                       "denominator as corr, so the two are comparable and "
                       "corr - MMC is what the ensemble already had."),
        "not_claimed": ("a correlation-space statement about one panel and one "
                        "meta-model: not a portfolio result, not net of costs, "
                        "and not evidence that a positive-MMC book makes money"),
    }


def _mmc_verdict(corr: float, m: float, t: float | None) -> str:
    if corr == 0:
        return f"{CANNOT_DETERMINE}: the candidate has no correlation to score."
    share = 1.0 - (m / corr)
    if abs(m) < 0.1 * abs(corr):
        return (f"RE-EXPRESSION: MMC {m:+.4f} is under a tenth of corr "
                f"{corr:+.4f}; the ensemble already had {share:.0%} of this "
                f"book's signal. Adding it changes no portfolio. This is the "
                f"EXPECTED NULL when 99.5% of names carry one factor.")
    if m > 0 and (t is None or t > 2.0):
        return (f"DIFFERENT ERRORS: MMC {m:+.4f} survives neutralisation "
                f"against the ensemble (corr {corr:+.4f}; the ensemble had "
                f"{share:.0%}). This is the result the roadmap asks for, and it "
                f"is a correlation claim, not a portfolio one.")
    if m > 0:
        return (f"MMC {m:+.4f} is positive but its era t is {t}; not yet "
                f"separable from noise across eras.")
    return (f"WORSE THAN THE ENSEMBLE: MMC {m:+.4f} is negative -- what this "
            f"book adds beyond the ensemble points the wrong way.")


__all__ = ["CANNOT_DETERMINE", "EraScoringRefused", "MIN_NAMES_PER_ERA",
           "era_boost_weights", "gaussianize", "mmc", "neutralize",
           "per_era_scores"]
