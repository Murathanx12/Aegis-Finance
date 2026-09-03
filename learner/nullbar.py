"""THE NULL BAR. One place that knows what a shuffled null can and cannot say.

WHY THIS EXISTS (2026-09-03, Session 36)
========================================
The repo's standing null test was: shuffle the target (or run a random
ranking), require the null's `|t| < 2`, and if it stays under the bar, trust
the real model's t. Session 36 measured that bar against itself and found it
mis-specified in a way that no amount of drawing random RANKINGS can repair:

    A model FITTED ON NOISE holds ONE persistent tilt for the whole panel.

A fitted model applies the same ranking to every month, so its monthly ICs
are serially correlated, and the naive across-months t assumes they are not.
Measured on the v2 encoder, the null statistic's own sd is ~2-3 and its naive
t spans **-9..+12 across seeds** -- `|t| < 2` on ONE draw is close to a coin
flip. A random-ranking null cannot catch this (200 draws reached a max paired
t of 1.72 at 1m) because a random ranking re-randomises every month and its
factor tilts wash out, while a model fitted on noise keeps its tilt.

THE REPLACEMENT BAR
===================
Fit the SAME model pipeline on shuffled data many times (a "model null") and
quote the real model's statistic as a PERCENTILE of that distribution:

    p_one_sided = (#{null >= observed} + 1) / (n_draws + 1)

with the add-one convention, so a statistic above every draw still reports
1/(n+1) rather than an impossible zero. The shuffle itself must be WITHIN the
date block (S24: a shuffled-DATE null was the calendar), and every draw must
go through the identical universe filters as the real arm (S36: the v2 nulls
held 8-13% of their book in split-contaminated rows the arms excluded).

DRAW COUNTS, AND WHAT EACH LICENCE OWES
=======================================
* **64 draws is the DEV gate** -- the floor below which this module REFUSES
  to produce a p-value at all. It resolves the p = 0.05 tail to ~3 draws,
  enough for a PRODUCT_EXPERIMENT reading. The memory-file rule is verbatim:
  ">= 64 model-null draws, quote the percentile."
* **Anything capital-authoritative wants >= 256 draws**, and -- when the claim
  is "the BEST of my arms beats the null" rather than "this one pre-named arm
  does" -- a max-statistic / Reality-Check family correction: compare the best
  observed statistic against the distribution of the per-draw MAXIMUM across
  arms (`family_max_p` below). Selecting the winner and then quoting its
  un-corrected percentile is the multiple-comparisons error wearing a null's
  clothes. (GPT review 2026-09-03 accepted the S36 diagnosis with exactly
  this caveat; it is a caveat here, not a footnote in a receipt.)

A guard DERIVES its inputs or REFUSES: below the floor this module raises
`InsufficientDrawsError` from the driver and returns an explicit
`CANNOT_DETERMINE` from the verdict helper. It never silently passes.

WHAT THIS MODULE DOES NOT DO
============================
It does not run the fits -- the caller owns the pipeline, the walk-forward
splits and the within-month shuffle, because those are what make the null a
MODEL null rather than a ranking null. It also cannot tell you whether your
shuffle destroys the right thing; `backend/services/research_gym/
null_invariance.py` is the contract for that question on treatment masks.

First user: `scripts/learner_v2_run.py --model-null` (receipt key
`model_null_distribution` in learner_v2_20260903.json). Gates still carrying
the OLD bar are annotated with `LEGACY_SHUFFLED_RANKING` so no future reader
trusts them silently.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

import numpy as np

#: The floor: fewer draws than this and no p-value exists. The DEV gate.
MIN_DRAWS = 64
#: What capital-authoritative claims want instead (plus `family_max_p` when
#: the claim selects among arms). Quoted in refusals so the reader learns the
#: right number from the error, not from this file.
MIN_DRAWS_AUTHORITATIVE = 256

#: The annotation stamped on every gate still running the old one-draw
#: shuffled-ranking bar. Grep for this string to find un-migrated gates.
LEGACY_SHUFFLED_RANKING = "LEGACY_SHUFFLED_RANKING (mis-specified, see learner/nullbar.py)"
#: The annotation for gates on the correct bar.
MODEL_NULL_BAR = "MODEL_NULL_PERCENTILE (>=64 fitted-on-shuffled draws, learner/nullbar.py)"

CANNOT_DETERMINE = "CANNOT_DETERMINE"

#: A fit callable: `fit_fn(panel, seed, shuffle_target)` runs the SAME
#: pipeline end to end and returns {metric_name: statistic}. With
#: `shuffle_target=True` the training target must be permuted WITHIN each
#: date block using `np.random.default_rng(seed)`; everything else --
#: universe filters, costs, splits -- must be identical to the real arm.
FitFn = Callable[[object, int, bool], Mapping[str, float]]


class InsufficientDrawsError(ValueError):
    """Raised when a model-null p-value is requested from < MIN_DRAWS draws.

    Deliberately an exception rather than a warning: a p-value from 8 draws
    resolves nothing below p = 0.11 and WILL be quoted as if it did.
    """


def p_one_sided(observed: float, null_draws: np.ndarray | Sequence[float]) -> float:
    """P(null >= observed) with the add-one convention.

    The convention matters at the edge: an observed statistic above every one
    of n draws reports 1/(n+1), never 0.0 -- a permutation test cannot claim
    more resolution than it has draws. This is the exact formula the v2
    receipt's `p_vs_model_null_*` fields were computed with.
    """
    a = np.asarray(null_draws, dtype="float64")
    a = a[~np.isnan(a)]
    if a.size == 0:
        raise InsufficientDrawsError("p_one_sided: zero usable null draws")
    return float(((a >= observed).sum() + 1) / (a.size + 1))


def percentile_of(observed: float, null_draws: np.ndarray | Sequence[float]) -> float:
    """Share of the null strictly below the observed statistic, in [0, 1]."""
    a = np.asarray(null_draws, dtype="float64")
    a = a[~np.isnan(a)]
    if a.size == 0:
        raise InsufficientDrawsError("percentile_of: zero usable null draws")
    return float((a < observed).mean())


def summarise_null(null_draws: np.ndarray | Sequence[float], ndigits: int = 3) -> dict:
    """The five numbers a receipt keeps about a null distribution."""
    a = np.asarray(null_draws, dtype="float64")
    a = a[~np.isnan(a)]
    if a.size == 0:
        return {"n_draws": 0}
    return {
        "n_draws": int(a.size),
        "p50": round(float(np.median(a)), ndigits),
        "p95": round(float(np.quantile(a, 0.95)), ndigits),
        "min": round(float(a.min()), ndigits),
        "max": round(float(a.max()), ndigits),
        "sd": round(float(a.std(ddof=1)), ndigits) if a.size > 1 else None,
    }


def model_null_percentile(
    fit_fn: FitFn,
    panel: object,
    *,
    n_draws: int = MIN_DRAWS,
    metrics: Sequence[str] = ("t_stat",),
    seed: int = 0,
    observed: Mapping[str, float] | None = None,
) -> dict:
    """Fit the same pipeline on shuffled data `n_draws` times; quote percentiles.

    `fit_fn(panel, seed, shuffle_target)` is the caller's ENTIRE pipeline (see
    `FitFn`). The real statistics come from `observed` if the caller already
    holds them (a sealed receipt, say), else from one un-shuffled call at the
    base seed. Each null draw i uses seed `seed + 1 + i`, so the observed fit
    and the draws never share a seed.

    REFUSES below MIN_DRAWS (=64, the DEV gate): a guard derives its inputs
    or refuses. Capital-authoritative claims want n_draws >= 256, and a
    `family_max_p` correction when the claimed arm was SELECTED for winning.

    Returns, per metric:
        {"observed", "null" (summarise_null), "percentile_of_observed",
         "p_one_sided", "n_draws"}
    under {"null_bar": MODEL_NULL_BAR, "n_draws": ..., "metrics": {...}}.
    """
    if n_draws < MIN_DRAWS:
        raise InsufficientDrawsError(
            f"REFUSED: {n_draws} draws < {MIN_DRAWS} (the DEV gate). A model-null "
            f"p-value from fewer draws resolves nothing it will be quoted for; "
            f"capital-authoritative claims want >= {MIN_DRAWS_AUTHORITATIVE}.")
    if observed is None:
        observed = fit_fn(panel, seed, False)
    draws = [fit_fn(panel, seed + 1 + i, True) for i in range(n_draws)]
    out: dict = {"null_bar": MODEL_NULL_BAR, "n_draws": int(n_draws), "metrics": {}}
    for m in metrics:
        obs = observed.get(m)
        arr = np.asarray([d.get(m, np.nan) for d in draws], dtype="float64")
        arr = arr[~np.isnan(arr)]
        if obs is None or arr.size < MIN_DRAWS:
            # A metric some draws failed to produce has a SMALLER null than
            # requested; quoting its percentile anyway would launder the gap.
            out["metrics"][m] = {
                "observed": obs, "n_draws": int(arr.size),
                "verdict": f"{CANNOT_DETERMINE} (usable draws {arr.size} < {MIN_DRAWS}"
                           f"{' and no observed statistic' if obs is None else ''})"}
            continue
        out["metrics"][m] = {
            "observed": round(float(obs), 6),
            "n_draws": int(arr.size),
            "null": summarise_null(arr),
            "percentile_of_observed": round(percentile_of(float(obs), arr), 4),
            "p_one_sided": round(p_one_sided(float(obs), arr), 4),
        }
    return out


def family_max_p(observed: Mapping[str, float],
                 draws: Sequence[Mapping[str, float]]) -> dict:
    """The Reality-Check correction: best observed arm vs the per-draw MAX.

    When the claim is "the best of my arms clears the null", the null of the
    CLAIM is the distribution of the best-looking arm under noise, not of any
    one arm. Each draw contributes max over the same arm names; the observed
    side contributes its own max. Selecting the winner first and quoting its
    single-arm percentile after is the error this exists to make impossible.
    """
    names = [k for k, v in observed.items() if v is not None]
    if not names:
        raise InsufficientDrawsError("family_max_p: no observed arm statistics")
    best_name = max(names, key=lambda k: observed[k])
    per_draw_max = np.asarray(
        [max((d.get(k, -np.inf) for k in names), default=-np.inf) for d in draws],
        dtype="float64")
    per_draw_max = per_draw_max[np.isfinite(per_draw_max)]
    if per_draw_max.size < MIN_DRAWS:
        return {"best_arm": best_name, "n_draws": int(per_draw_max.size),
                "verdict": f"{CANNOT_DETERMINE} (usable draws "
                           f"{per_draw_max.size} < {MIN_DRAWS})"}
    return {"best_arm": best_name,
            "observed_max": round(float(observed[best_name]), 6),
            "n_draws": int(per_draw_max.size),
            "null_max": summarise_null(per_draw_max),
            "p_one_sided_family": round(
                p_one_sided(float(observed[best_name]), per_draw_max), 4)}


def verdict(observed: float, null_draws: np.ndarray | Sequence[float],
            alpha: float = 0.05) -> dict:
    """The mechanical read. Refuses -- explicitly -- below the draw floor.

    Returns {"verdict": ..., "p_one_sided": ..., "n_draws": ...} where verdict
    is one of:
        "CLEARS_MODEL_NULL"    p <= alpha on >= MIN_DRAWS draws
        "WITHIN_MODEL_NULL"    p >  alpha on >= MIN_DRAWS draws
        "CANNOT_DETERMINE ..." fewer usable draws than the floor -- never a
                               pass, never a fail, and it says why inline so
                               a reader who only sees the string still knows.
    """
    a = np.asarray(null_draws, dtype="float64")
    a = a[~np.isnan(a)]
    if a.size < MIN_DRAWS:
        return {"verdict": f"{CANNOT_DETERMINE} (usable draws {a.size} < "
                           f"{MIN_DRAWS}; a p-value from fewer draws would be "
                           f"quoted as if it resolved what it cannot)",
                "p_one_sided": None, "n_draws": int(a.size)}
    p = p_one_sided(float(observed), a)
    return {"verdict": "CLEARS_MODEL_NULL" if p <= alpha else "WITHIN_MODEL_NULL",
            "p_one_sided": round(p, 4), "n_draws": int(a.size)}
