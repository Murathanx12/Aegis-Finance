"""THE ONE PLACE A VERDICT IS COMPUTED -- and the house rules it must obey.

`backend/strategy/multipletesting.py` is a verbatim MIT vendor of
Vibe-Trading's `quantlib/multipletesting.py`: PSR, DSR, expected-max-Sharpe,
BH-FDR and PBO via CSCV. This module is the Aegis side of that boundary. It
adds nothing to the mathematics of the vendored file and edits none of it; it
adds the three house rules that file has no opinion about, because they are
this repository's rules and not the upstream project's.

THE THREE HOUSE RULES
=====================
1. **SCREEN uses BH-FDR, EXPORT uses Holm** (CANON section 63). Screening asks
   "which of these hundreds is worth another look" and can tolerate a known
   false-discovery fraction; exporting a claim asks "is THIS one real" and must
   control the family-wise error. The vendored file has BH only, so `holm` is
   here. `screen_then_export` runs both and reports both, because a family
   where BH keeps forty and Holm keeps none is a different finding from a
   family where both keep the same three.
2. **`n_effective` counts DATE BLOCKS, not name-days** (CANON section 58).
   259,234 name-days printed t -65; one portfolio return per session printed
   t -16.6 ([[name-days-are-not-periods]]). Every statistic here takes a period
   count, and `n_effective_date_blocks` is the only admissible way to produce
   one from a panel.
3. **A null owes TWO tests.** `deflated_sharpe_from_returns` refuses to return
   a verdict word when the sample is too short for its own moments rather than
   reporting a number that reads as a pass.

WHY THIS IS NOT A THIN WRAPPER OVER `learner.inference`
=======================================================
It is not a replacement for `learner.inference` either. `inference.deflated_sharpe`
and `inference.pbo` remain the receipt-shaped implementations the growth book
and the farm already wrote receipts with, and CHANGING THEM WOULD INVALIDATE
EVERY SEALED RECEIPT THAT QUOTES THEM. Measured 2026-09-07 (see
`docs/BUILD_2026-09-07b_S1_STRATEGY_INTERFACE.md` section 3) the two
implementations agree with the sealed numbers:

    family PBO  0.6428571428571429  vendored   vs  0.6429 receipt (4 dp)
    cell DSR    0.27822766444123914 vendored   vs  0.2782 receipt (4 dp)

so the vendored library is adopted as the CALCULATOR for new verdicts while
`learner.inference` stays the historical record. `agreement_report` is the
function that proves that claim rather than asserting it.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from backend.strategy import multipletesting as MT

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: Sharpe dispersion used when a search did not record its trials' Sharpes.
#: Bailey-Lopez de Prado's analytic null: the sd of a Sharpe estimated on T
#: observations of zero-edge returns. Stated on the row, never assumed silently.
def analytic_trial_sharpe_std(n_observations: int) -> float:
    return 1.0 / math.sqrt(max(1, int(n_observations) - 1))


def moments(returns: Sequence[float]) -> dict:
    """Per-observation Sharpe with the skew and NON-EXCESS kurtosis beside it.

    The second gotcha in the vendored module's header: `scipy.stats.kurtosis`
    and `pandas.Series.kurt` both return the EXCESS form (0 for a Gaussian),
    and feeding that in makes the PSR variance term too small and the
    confidence too high. These are the raw standardised moments.
    """
    a = np.asarray(list(returns), dtype="float64")
    a = a[np.isfinite(a)]
    n = a.size
    if n < 2:
        return {"n": int(n), "verdict": f"{CANNOT_DETERMINE} ({n} finite observations)"}
    sd = float(a.std(ddof=1))
    if sd <= 0:
        return {"n": int(n), "verdict": f"{CANNOT_DETERMINE} (zero variance)"}
    mu = float(a.mean())
    return {
        "n": int(n),
        "sharpe_per_observation": float(mu / sd),
        "mean": mu,
        "sd": sd,
        "skew": float(((a - mu) ** 3).mean() / sd ** 3),
        "kurtosis_non_excess": float(((a - mu) ** 4).mean() / sd ** 4),
    }


def deflated_sharpe_from_returns(returns: Sequence[float], *, n_trials: int,
                                 trial_sharpes: Sequence[float] | None = None,
                                 confidence: float = 0.95) -> dict:
    """DSR over a family, receipt-shaped, computed by the vendored library.

    `trial_sharpes` is the dispersion the search actually produced -- draws
    already paid for. Absent, the analytic null is used and the row SAYS SO,
    because the two differ and a reader cannot tell from the number alone.
    """
    m = moments(returns)
    if "sharpe_per_observation" not in m:
        return {"verdict": m["verdict"], "n_periods": m.get("n", 0)}
    n = m["n"]
    if n < MT.MIN_OBSERVATIONS:
        return {"verdict": (f"{CANNOT_DETERMINE} ({n} periods; the vendored PSR "
                            f"refuses below {MT.MIN_OBSERVATIONS} because the skew "
                            f"and kurtosis estimates are hopeless there)"),
                "n_periods": int(n)}
    if trial_sharpes is not None and len(list(trial_sharpes)) >= 2:
        arr = np.asarray(list(trial_sharpes), dtype="float64")
        arr = arr[np.isfinite(arr)]
        sd_basis = f"sd of {arr.size} observed trial Sharpes"
        trial_sd = float(arr.std(ddof=1))
    else:
        trial_sd = analytic_trial_sharpe_std(n)
        sd_basis = "analytic 1/sqrt(T-1) -- the search did not record its trial Sharpes"
    res = MT.deflated_sharpe_ratio(
        observed_sharpe=m["sharpe_per_observation"],
        n_trials=int(max(1, n_trials)),
        n_observations=int(n),
        trial_sharpe_std=trial_sd,
        skew=m["skew"],
        kurtosis=m["kurtosis_non_excess"],
        confidence=confidence,
    )
    return {
        "dsr": float(res.deflated_sharpe_ratio),
        "sharpe": m["sharpe_per_observation"],
        "sharpe_benchmark_sr0": float(res.expected_maximum_sharpe),
        "n_trials": int(res.n_trials),
        "n_periods": int(res.n_observations),
        "trial_sharpe_std": trial_sd,
        "null_sd_basis": sd_basis,
        "skew": m["skew"],
        "kurtosis_non_excess": m["kurtosis_non_excess"],
        "survives": bool(res.survives),
        "confidence": float(res.confidence),
        "verdict": ("CLEARS_DEFLATED_SHARPE" if res.survives else "WITHIN_SELECTION_NOISE"),
        "computed_by": "backend.strategy.multipletesting (Vibe-Trading, MIT)",
    }


def holm(p_by_name: Mapping[str, float], *, alpha: float = 0.05) -> dict:
    """Holm-Bonferroni step-down. THE EXPORT RULE.

    Not in the vendored file, which stops at BH. Holm controls the family-wise
    error rate and is what a claim leaving this repository is judged by; BH
    controls the expected false-discovery FRACTION and is what a screen uses.
    Adjusted p is the running MAXIMUM up the sorted order, so it cannot
    decrease -- the mirror of BH's running minimum down the order.
    """
    items = [(k, float(v)) for k, v in p_by_name.items()
             if v is not None and math.isfinite(float(v))]
    dropped = [k for k, v in p_by_name.items()
               if v is None or not math.isfinite(float(v))]
    if not items:
        return {"verdict": f"{CANNOT_DETERMINE} (no finite p-values)",
                "n_dropped_non_finite": len(dropped)}
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    survivors = sorted(k for k, v in adjusted.items() if v <= alpha)
    return {
        "method": "holm-bonferroni (EXPORT)",
        "alpha": float(alpha),
        "family_size": m,
        "adjusted": adjusted,
        "survivors": survivors,
        "n_survivors": len(survivors),
        "best_adjusted_p": min(adjusted.values()),
        "n_dropped_non_finite": len(dropped),
        "dropped_non_finite": sorted(dropped),
    }


def bh_fdr(p_by_name: Mapping[str, float], *, fdr: float = 0.05) -> dict:
    """Benjamini-Hochberg. THE SCREEN RULE. Delegated to the vendored library."""
    items = [(k, float(v)) for k, v in p_by_name.items()
             if v is not None and math.isfinite(float(v))]
    dropped = [k for k, v in p_by_name.items()
               if v is None or not math.isfinite(float(v))]
    if not items:
        return {"verdict": f"{CANNOT_DETERMINE} (no finite p-values)",
                "n_dropped_non_finite": len(dropped)}
    names = [k for k, _ in items]
    res = MT.benjamini_hochberg([p for _, p in items], fdr=fdr)
    adjusted = {n: float(p) for n, p in zip(names, res.adjusted_p_values)}
    survivors = sorted(n for n, r in zip(names, res.rejected) if bool(r))
    return {
        "method": "benjamini-hochberg (SCREEN)",
        "fdr": float(fdr),
        "family_size": len(names),
        "adjusted": adjusted,
        "survivors": survivors,
        "n_survivors": int(res.n_rejected),
        "best_adjusted_p": min(adjusted.values()),
        "threshold": float(res.threshold),
        "n_dropped_non_finite": len(dropped),
        "computed_by": "backend.strategy.multipletesting (Vibe-Trading, MIT)",
    }


def screen_then_export(p_by_name: Mapping[str, float], *,
                       fdr: float = 0.05, alpha: float = 0.05) -> dict:
    """Both corrections, both reported. CANON section 63 in one call.

    A family where BH keeps forty and Holm keeps none is a DIFFERENT finding
    from one where both keep the same three, and quoting only the one that
    suits the paragraph is how a screen becomes a claim without anyone
    deciding that it should.
    """
    s = bh_fdr(p_by_name, fdr=fdr)
    e = holm(p_by_name, alpha=alpha)
    return {
        "screen_bh_fdr": s,
        "export_holm": e,
        "screened_not_exported": sorted(set(s.get("survivors", []))
                                        - set(e.get("survivors", []))),
        "reading": ("SCREEN=BH-FDR admits a known false-discovery fraction and is "
                    "for deciding what to look at next; EXPORT=Holm controls the "
                    "family-wise error and is what a claim leaving this repository "
                    "is judged by. `screened_not_exported` is the gap between "
                    "'worth another look' and 'defensible'."),
    }


def pbo(performance, *, n_splits: int = 8) -> dict:
    """PBO via CSCV, receipt-shaped, computed by the vendored library.

    `n_splits` DEFAULTS TO 8, not to the vendored file's 16, because 8 is what
    every existing Aegis receipt was computed at (`learner.inference.pbo`) and
    a shared library that silently changes the default would make two sessions'
    numbers incomparable -- the exact problem it was adopted to fix.
    """
    M = np.asarray(performance, dtype="float64")
    if M.ndim != 2 or M.shape[1] < 2:
        return {"verdict": f"{CANNOT_DETERMINE} (need >= 2 arms; got shape {M.shape})"}
    try:
        res = MT.probability_of_backtest_overfitting(M, n_splits=int(n_splits))
    except ValueError as exc:
        return {"verdict": f"{CANNOT_DETERMINE} ({exc})",
                "n_periods": int(M.shape[0]), "n_arms": int(M.shape[1])}
    p = float(res.pbo)
    return {
        "pbo": p,
        "n_partitions": int(res.n_splits),
        "n_arms": int(res.n_strategies),
        "n_periods": int(res.n_observations),
        "dropped_observations": int(res.dropped_observations),
        "median_logit": float(np.median(res.logits)),
        "performance_degradation": (float(res.performance_degradation)
                                    if math.isfinite(res.performance_degradation)
                                    else None),
        "verdict": ("SELECTION_IS_STABLE" if p <= 0.25 else
                    "SELECTION_IS_OVERFIT" if p >= 0.5 else "SELECTION_IS_FRAGILE"),
        "reading": ("share of in-sample/out-of-sample partitions in which the "
                    "in-sample champion finished BELOW the out-of-sample median. "
                    "0.5 is a coin flip. PBO is a property of the SEARCH, not of "
                    "any arm on it."),
        "computed_by": "backend.strategy.multipletesting (Vibe-Trading, MIT)",
    }


def n_effective_date_blocks(dates: Sequence[Any]) -> dict:
    """CANON section 58. The period count is DISTINCT DATES, never rows.

    [[name-days-are-not-periods]]: pooling 259,234 name-days printed t -65; one
    portfolio return per session printed t -16.6. Every statistic in this
    module takes `n_observations`, and this is the only admissible way to
    produce one from a panel.
    """
    seen = {str(d) for d in dates if d is not None}
    return {
        "n_rows": int(len(list(dates))),
        "n_effective": int(len(seen)),
        "basis": "distinct DATE BLOCKS",
        "reading": ("a t computed on rows rather than date blocks is inflated by "
                    "roughly sqrt(rows / date blocks)"),
    }


def agreement_report(*, vendored: Mapping[str, Any],
                     receipt: Mapping[str, Any],
                     tolerance: float = 1e-9) -> dict:
    """Did the ported library reproduce the number on a sealed receipt?

    Returns findings; raises nothing. A disagreement is a FINDING to be
    reported with its delta and a statement of which implementation is right --
    never a silent adoption of whichever ran last.
    """
    rows = []
    for key, want in receipt.items():
        got = vendored.get(key)
        if want is None or got is None:
            rows.append({"field": key, "receipt": want, "vendored": got,
                         "status": "NOT_COMPARABLE"})
            continue
        # A receipt value that was rounded when it was written can only be
        # compared at its own precision; comparing at 1e-9 against a 4-dp
        # receipt would report a disagreement that is a rounding artefact.
        decimals = _decimals(want)
        tol = max(tolerance, 0.5 * 10 ** (-decimals)) if decimals is not None else tolerance
        delta = abs(float(got) - float(want))
        rows.append({"field": key, "receipt": float(want), "vendored": float(got),
                     "delta": delta, "tolerance": tol,
                     "receipt_decimals": decimals,
                     "status": "AGREES" if delta <= tol else "DISAGREES"})
    bad = [r for r in rows if r["status"] == "DISAGREES"]
    return {"rows": rows, "n_fields": len(rows), "n_disagreements": len(bad),
            "verdict": "AGREES" if not bad else "DISAGREES",
            "disagreements": bad}


def _decimals(x: Any) -> int | None:
    s = repr(float(x))
    if "e" in s or "E" in s or "." not in s:
        return None
    return len(s.split(".", 1)[1])
