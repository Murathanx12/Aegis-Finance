"""Turn a farm row from a NUMBER into an INTERVAL.

THE GAP THIS CLOSES
===================
Every figure the farm has produced is a point on one price path. "This rule
returned $77,002 against the market's $38,960" is a statement about the single
history that happened, and it carries no width — so there is no way to ask
whether the gap is bigger than the noise that produced it. With ~1,700 policies
tried, that is not a footnote: the best of 1,700 draws from a distribution
centred on zero is comfortably positive.

Two tools here, and they answer different questions. Both are `PRODUCT_EXPERIMENT`
instruments — they widen a number honestly; they do not license a claim.

**1. STATIONARY BLOCK BOOTSTRAP** (Politis & Romano 1994) on the daily
strategy-minus-benchmark series. Resampling BLOCKS rather than days is the whole
point: daily returns are serially dependent (volatility clusters, momentum
persists), and an i.i.d. bootstrap would shred that dependence and return an
interval far too narrow. Block length is geometric with declared mean, so the
resampled series is stationary rather than having a seam every `L` days.

Answers: *how wide is this rule's excess return, on resamples of its own path?*

**2. WHITE'S REALITY CHECK** (White 2000), the bootstrap answer to
"best-of-N is high because N is large". It bootstraps the MAXIMUM excess across
all policies tried, giving a p-value for the best one that already accounts for
the search. This is the honest reply to a leaderboard.

Answers: *is the best of 1,700 better than the best of 1,700 coin flips?*

WHAT NEITHER OF THEM FIXES
==========================
Both resample the ONE path that exists. A bootstrap cannot manufacture a regime
the sample never contained, so it cannot answer the question the sub-period
split raised — that the leading rule is 1.01x the market over 2013-2018 and
1.75x over 2019-2024. **More history is the fix for that; this is the fix for
"how wide".** Do not read a tight interval as robustness.
"""

from __future__ import annotations

import numpy as np

#: Mean block length in sessions for the stationary bootstrap. ~21 (a month) is
#: long enough to carry the serial dependence in daily equity returns and short
#: enough that a twelve-year sample still yields many independent blocks. It is
#: DECLARED rather than fitted: choosing it from the data being tested is how a
#: bootstrap quietly reports the width its author wanted.
DEFAULT_BLOCK = 21

#: Resamples. 2,000 is enough for a 5% tail to be stable to about ±0.5%.
DEFAULT_N = 2000

TRADING_DAYS = 252


def _stationary_indices(n: int, mean_block: int, rng) -> np.ndarray:
    """One resampled index path of length `n`, geometric block lengths, wrapping.

    Wrapping (rather than truncating at the end) is what keeps every observation
    equally likely to appear; truncation under-samples the tail of the series,
    which for an equity strategy is where the drawdowns live.
    """
    p = 1.0 / max(1, mean_block)
    out = np.empty(n, dtype=np.int64)
    i = 0
    while i < n:
        start = rng.integers(0, n)
        length = min(n - i, 1 + int(rng.geometric(p)))
        idx = (start + np.arange(length)) % n
        out[i:i + length] = idx
        i += length
    return out


def excess_interval(strategy_ret: np.ndarray, benchmark_ret: np.ndarray, *,
                    n_boot: int = DEFAULT_N, mean_block: int = DEFAULT_BLOCK,
                    seed: int = 20260824, alpha: float = 0.05) -> dict:
    """Bootstrap CI for annualised mean excess return, and P(excess <= 0).

    Returns `status: "too_short"` rather than a number when the series cannot
    support the block length — a bootstrap run on forty observations produces an
    interval, and the interval is fiction.
    """
    s = np.asarray(strategy_ret, dtype=np.float64)
    b = np.asarray(benchmark_ret, dtype=np.float64)
    n = min(s.size, b.size)
    ok = np.isfinite(s[:n]) & np.isfinite(b[:n])
    d = (s[:n] - b[:n])[ok]
    if d.size < 10 * mean_block:
        return {"status": "too_short", "n_obs": int(d.size),
                "needed": 10 * mean_block,
                "why": ("fewer than ten expected blocks — the resamples would "
                        "be near-copies of each other and the interval would "
                        "understate its own width")}
    rng = np.random.default_rng(seed)
    point = float(d.mean()) * TRADING_DAYS
    draws = np.empty(n_boot)
    for k in range(n_boot):
        draws[k] = d[_stationary_indices(d.size, mean_block, rng)].mean()
    draws *= TRADING_DAYS
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "status": "ok",
        "n_obs": int(d.size),
        "mean_block": mean_block,
        "n_boot": n_boot,
        "excess_annual_pct": round(100 * point, 3),
        "ci_lo_pct": round(100 * float(lo), 3),
        "ci_hi_pct": round(100 * float(hi), 3),
        #: Share of resamples at or below zero. NOT a p-value for a hypothesis
        #: test — it is the bootstrap's own mass on "no excess", and it ignores
        #: every other policy that was tried. `reality_check` is the one that
        #: accounts for the search.
        "share_at_or_below_zero": round(float((draws <= 0).mean()), 4),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def reality_check(excess_by_policy: dict[str, np.ndarray], *,
                  n_boot: int = DEFAULT_N, mean_block: int = DEFAULT_BLOCK,
                  seed: int = 20260824) -> dict:
    """White's Reality Check p-value for the BEST policy among those tried.

    The null is that no policy has positive expected excess return. Each
    resample recomputes every policy's demeaned mean excess and takes the
    MAXIMUM; the p-value is the share of resamples whose maximum beats the
    observed best. A leaderboard's top row is only interesting if it survives
    this, because the top row was selected for being the top row.

    All policies must share a date axis — they are resampled on the SAME index
    path each draw, which is what preserves the cross-policy correlation that
    makes the search less severe than N independent tries.
    """
    names = list(excess_by_policy)
    if not names:
        return {"status": "no_policies"}
    mat = np.vstack([np.asarray(excess_by_policy[k], dtype=np.float64)
                     for k in names])
    finite = np.isfinite(mat).all(axis=0)
    mat = mat[:, finite]
    if mat.shape[1] < 10 * mean_block:
        return {"status": "too_short", "n_obs": int(mat.shape[1]),
                "needed": 10 * mean_block}
    means = mat.mean(axis=1)
    best_i = int(np.argmax(means))
    observed = float(means[best_i])
    centred = mat - means[:, None]           # impose the null, per policy
    rng = np.random.default_rng(seed)
    beat = 0
    for _ in range(n_boot):
        idx = _stationary_indices(mat.shape[1], mean_block, rng)
        if centred[:, idx].mean(axis=1).max() >= observed:
            beat += 1
    return {
        "status": "ok",
        "n_policies": len(names),
        "n_obs": int(mat.shape[1]),
        "best_policy": names[best_i],
        "best_excess_annual_pct": round(100 * observed * TRADING_DAYS, 3),
        "reality_check_p": round(beat / n_boot, 4),
        "n_boot": n_boot,
        "note": ("p is the share of resamples in which the BEST of all "
                 "policies tried, under the null of no excess, beats the "
                 "observed best. It prices the search. It does not price the "
                 "fact that only one price path exists."),
    }


def daily_returns(nav) -> np.ndarray:
    """Daily returns from a NAV series, NaN-safe at the joins."""
    v = np.asarray(nav, dtype=np.float64)
    out = np.full(v.size, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[1:] = np.where(v[:-1] > 0, v[1:] / v[:-1] - 1.0, np.nan)
    return out


def power_check(strategy_ret: np.ndarray, benchmark_ret: np.ndarray, *,
                power_z: float = 2.8) -> dict:
    """Can this sample resolve this effect AT ALL? Run it BEFORE believing one.

    CANON §64 requires a power check before any confirmation, and the farm ran
    ~1,700 policies without one. Doing it afterwards on the leading candidate
    explained every other result at once:

        tracking error          35.7%/yr
        standard error of mean  10.81%/yr over 10.9 years
        observed excess         16.64%/yr
        implied t                1.54
        MDE at 80% power        30.3%/yr
        years needed               36

    **The sample cannot resolve the effect.** That single fact is the same fact
    as the 3.75x rebalance-phase spread, the 1.01x-vs-1.75x sub-period
    disagreement, the bootstrap CI that contains zero, and the reality-check
    p of 0.126. They are four faces of one variance, and none of them is a
    defect in the strategy or the simulator.

    It also prices the fix exactly. Twelve years cannot do it; **thirty-six can,
    and CRSP 1990-2024 is thirty-five.** The pre-2013 re-pull is not "nice to
    have for regimes" — it is very close to the precise amount of data this
    question needs, which is why it is the first priority and why nothing else
    on the board substitutes for it.

    `power_z` 2.8 is the usual ~80%-power, 5%-two-sided constant. Declared, not
    tuned.
    """
    s = np.asarray(strategy_ret, dtype=np.float64)
    b = np.asarray(benchmark_ret, dtype=np.float64)
    n = min(s.size, b.size)
    ok = np.isfinite(s[:n]) & np.isfinite(b[:n])
    d = (s[:n] - b[:n])[ok]
    if d.size < TRADING_DAYS:
        return {"status": "too_short", "n_obs": int(d.size)}
    years = d.size / TRADING_DAYS
    te = float(d.std(ddof=0)) * np.sqrt(TRADING_DAYS)
    se = te / np.sqrt(years)
    obs = float(d.mean()) * TRADING_DAYS
    mde = power_z * se
    return {
        "status": "ok",
        "years": round(years, 2),
        "tracking_error_annual_pct": round(100 * te, 3),
        "se_of_mean_excess_pct": round(100 * se, 3),
        "observed_excess_annual_pct": round(100 * obs, 3),
        "implied_t": round(obs / se, 3) if se > 0 else None,
        "mde_at_80pct_power_annual_pct": round(100 * mde, 3),
        "years_needed_for_observed_effect": (
            round((power_z * te / obs) ** 2, 1) if obs > 0 else None),
        #: The sentence that decides whether any of the other numbers mean
        #: anything. False means the study was never able to answer its
        #: question, whatever it returned.
        "sample_can_resolve_observed_effect": bool(obs > mde),
    }
