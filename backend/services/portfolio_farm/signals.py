"""The alpha sources the farm searches over — every one PIT by construction.

THE ONE RULE
============
A signal function receives `(panel, i)` and may read rows `0 .. i` INCLUSIVE
and nothing else. Row `i` is the decision day's CLOSE, which is public when the
decision is taken (the arena's own convention: decisions freeze after the close,
fills happen at the next open). Reading row `i+1` is reading tomorrow.

This is enforced twice: every function here slices with `[:i + 1]`, and
`replay.py` passes a VIEW that has been truncated, so a function that indexed
past the end would raise rather than peek. `test_portfolio_farm_pit.py` plants
a perfect-foresight column and asserts no signal can reach it.

WHY THE NULLS ARE FIRST-CLASS
=============================
`random_signal` and `equal_weight` are in the library, not in a test file. A
leaderboard whose top entry cannot be compared to a coin flip on the same
universe, the same costs and the same holding period is a ranking of luck. The
farm runs them as ordinary policies so they appear in the same table.

WHAT IS DELIBERATELY ABSENT
===========================
Anything derived from a fundamental, an estimate revision, an insider filing or
a news event. Those live in the arena's information bus and in the collectors,
they are not in the CRSP daily file, and joining them here PIT-correctly is
CHUNK B/C work. This module is the PRICE-ONLY baseline the later mechanisms
have to beat — which is the right order, because the repo's own training gate
already found that 412 characteristics did not beat a price floor.
"""

from __future__ import annotations

import numpy as np

#: Trading days. Named constants because "252" appearing in four functions is
#: four places to disagree about what a year is.
MONTH, QUARTER, HALF, YEAR = 21, 63, 126, 252


def _tri_return(tri: np.ndarray, i: int, back: int, skip: int = 0) -> np.ndarray:
    """Total return from `i-back` to `i-skip`, using rows <= i only.

    `skip` is what makes 12-1 momentum 12-1: the most recent month is EXCLUDED
    because short-horizon winner-chasing is a Holm-surviving ANTI-signal in this
    repository's own results (streak_up5 -0.366%/21d), not because the textbook
    says so.
    """
    a, b = i - back, i - skip
    if a < 0 or b <= a:
        return np.full(tri.shape[1], np.nan, dtype=np.float64)
    return (tri[b] / tri[a]) - 1.0


def mom_12_1(panel, i: int) -> np.ndarray:
    """The workhorse. t-252 to t-21."""
    return _tri_return(panel.tri, i, YEAR, MONTH)


def mom_6_1(panel, i: int) -> np.ndarray:
    return _tri_return(panel.tri, i, HALF, MONTH)


def mom_3_1(panel, i: int) -> np.ndarray:
    return _tri_return(panel.tri, i, QUARTER, MONTH)


def mom_12_0(panel, i: int) -> np.ndarray:
    """12 months INCLUDING the last one — the version the anti-chase findings
    say should be worse. Kept precisely so the farm can show the gap rather
    than the repository asserting it."""
    return _tri_return(panel.tri, i, YEAR, 0)


def reversal_1m(panel, i: int) -> np.ndarray:
    """SHORT the last month's winners. The sign is the hypothesis."""
    return -_tri_return(panel.tri, i, MONTH, 0)


def reversal_1w(panel, i: int) -> np.ndarray:
    return -_tri_return(panel.tri, i, 5, 0)


def low_vol(panel, i: int) -> np.ndarray:
    """-stdev of daily total return over a quarter. Low-vol anomaly, and also
    the sizing input Order 24 found beat the risk model on all five routes."""
    a = max(0, i - QUARTER + 1)
    w = panel.ret[a:i + 1]
    with np.errstate(invalid="ignore"):
        sd = np.nanstd(w.astype(np.float64), axis=0)
    n = np.isfinite(w).sum(axis=0)
    sd = np.where(n >= QUARTER // 2, sd, np.nan)
    return -sd


def high_vol(panel, i: int) -> np.ndarray:
    """The deliberate opposite. An 'extreme growth' personality is a DECLARED
    preference (CLAUDE.md), so the farm must be able to express it."""
    return -low_vol(panel, i)


def trend_200(panel, i: int) -> np.ndarray:
    """Price relative to its 200-day mean. A different functional form of the
    same tape than momentum, so a leaderboard carrying both is evidence about
    form, not two draws of one bet."""
    a = max(0, i - 200 + 1)
    w = panel.tri[a:i + 1].astype(np.float64)
    with np.errstate(invalid="ignore"):
        ma = np.nanmean(w, axis=0)
    cur = panel.tri[i].astype(np.float64)
    n = np.isfinite(w).sum(axis=0)
    out = np.where(n >= 100, cur / ma - 1.0, np.nan)
    return out


def size_small(panel, i: int) -> np.ndarray:
    """-log(market cap). Small-cap tilt."""
    mc = panel.mktcap[i].astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return -np.log(np.where(mc > 0, mc, np.nan))


def size_large(panel, i: int) -> np.ndarray:
    return -size_small(panel, i)


def illiquid(panel, i: int) -> np.ndarray:
    """Amihud: mean |ret| / dollar volume over a quarter. Higher = more
    illiquid. The illiquidity premium is real and mostly untradeable — which is
    exactly why it belongs in a farm that charges costs."""
    a = max(0, i - QUARTER + 1)
    r = np.abs(panel.ret[a:i + 1].astype(np.float64))
    v = panel.dolvol[a:i + 1].astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(v > 0, r / v, np.nan)
        out = np.nanmean(ratio, axis=0)
    n = np.isfinite(ratio).sum(axis=0)
    return np.where(n >= QUARTER // 2, out * 1e6, np.nan)


#: Minimum real observations before a trailing dollar-volume mean is a number.
#: The SAME value the universe screen uses in `farm.run_many` — a signal and a
#: screen that disagree about when a name is measurable would admit names to
#: the universe that the signal cannot rank, and exclude names it can.
LIQ_MIN_OBS = 5


def liquid(panel, i: int) -> np.ndarray:
    """Trailing dollar volume. Not an alpha claim — the CONTROL for illiquid,
    so a farm winner that is really 'I bought things nobody can buy' shows up
    as its opposite scoring badly rather than as a mystery."""
    a = max(0, i - MONTH + 1)
    w = panel.dolvol[a:i + 1].astype(np.float64)
    with np.errstate(invalid="ignore"):
        m = np.nanmean(w, axis=0)
    return np.where(np.isfinite(w).sum(axis=0) >= LIQ_MIN_OBS, m, np.nan)


def random_signal(panel, i: int) -> np.ndarray:
    """A coin flip, seeded by the DATE INDEX so a rerun is identical.

    First-class, not a test fixture. Every leaderboard prints this row, and a
    strategy that does not beat it on the same universe, costs and holding
    period has not been shown to do anything.
    """
    rng = np.random.default_rng(1_000_003 + i)
    return rng.standard_normal(panel.close.shape[1])


def random_persistent(panel, i: int) -> np.ndarray:
    """A random score per NAME, FIXED for the whole sample. The low-turnover null.

    WHY A SECOND NULL, MEASURED 2026-08-24. `random_signal` re-draws every
    session, so at a 1-day holding period it re-ranks the whole universe daily
    and turns over ~492x/yr — against ~45x/yr for 12-1 momentum, whose ranks
    barely move day to day. At 6 bps that is 29.5%/yr of cost for the null and
    2.7%/yr for the strategy, and over twelve years the null's median terminal
    collapsed to $1,123 while momentum's was $36,623. Reported as "momentum
    sits at the 100th percentile of chance", that comparison is mostly a
    statement about turnover.

    So the farm carries TWO nulls that bracket churn:

      * `random`            — maximum turnover; re-draws every formation date;
      * `random_persistent` — near-zero turnover; the same twelve names for
                              twelve years, changing only as eligibility does.

    A signal that beats both has beaten chance at both ends of the trading-cost
    axis. A signal that beats only one has told you which end it lives at,
    which is itself the finding.
    """
    rng = np.random.default_rng(500_009)
    return rng.standard_normal(panel.close.shape[1])



def equal_universe(panel, i: int) -> np.ndarray:
    """No ranking at all — every eligible name scores the same.

    READ THE TIE-BREAK BEFORE USING THIS AS A CONTROL. With every score equal,
    `top_k` falls through to the stable sort's tie-break, which is **permno
    order**, and CRSP permnos are assigned roughly in listing order. So this is
    not a neutral null: it is "the twelve OLDEST surviving eligible listings",
    a real and quite specific strategy with a survivorship flavour.

    It stays in the library because "did the SELECTION do anything, or was it
    the universe and the costs?" is worth asking, and because a single
    deterministic reference line is useful. It is NOT the neutral null —
    `random_persistent` is, and unlike this one it comes with a distribution.
    """
    return np.zeros(panel.close.shape[1], dtype=np.float64)


#: The registry the policy grid enumerates. A signal not in here cannot be
#: named by a policy, so a typo is a refusal rather than an all-NaN run that
#: silently holds nothing.
SIGNALS = {
    "mom_12_1": mom_12_1,
    "mom_6_1": mom_6_1,
    "mom_3_1": mom_3_1,
    "mom_12_0": mom_12_0,
    "reversal_1m": reversal_1m,
    "reversal_1w": reversal_1w,
    "low_vol": low_vol,
    "high_vol": high_vol,
    "trend_200": trend_200,
    "size_small": size_small,
    "size_large": size_large,
    "illiquid": illiquid,
    "liquid": liquid,
    "random": random_signal,
    "random_persistent": random_persistent,
    "equal": equal_universe,
}

#: Signals that exist to be BEATEN, not to win. Reported separately on the
#: leaderboard so a null cannot be quoted as a discovery.
#:
#: They are NOT interchangeable and `farm.compare_within_groups` does not pool
#: them: `random` re-draws every formation date (MAXIMUM turnover — 492x/yr at
#: a 1-session holding period, 29.5%/yr of cost at 6 bps), `random_persistent`
#: is one fixed basket (near-zero turnover), and `equal` is a deterministic
#: reference line whose tie-break makes it "the oldest surviving listings"
#: rather than a neutral draw. The bar a real signal must clear is the 90th
#: percentile of the two RANDOM families — chance at both ends of the
#: trading-cost axis.
NULL_SIGNALS = frozenset({"random", "random_persistent", "equal"})


def zscore(x: np.ndarray) -> np.ndarray:
    """Cross-sectional z, NaN-safe. Used to combine signals; never to rank a
    single one (ranking is scale-free, and z-ing first would only add a way to
    be wrong about the dispersion)."""
    m = np.nanmean(x)
    s = np.nanstd(x)
    if not np.isfinite(s) or s == 0:
        return np.zeros_like(x)
    return (x - m) / s


# ── the vectorised twin, and why there are two of everything ────────────────
#
# The functions above are the READABLE definition: one date, one slice, easy to
# check by eye. They are also far too slow for the farm — a 1-day holding
# period over fifteen years is ~3,800 formation dates, and re-slicing a 252-day
# window at each one is billions of float operations per policy.
#
# So the farm runs `matrix(panel, name)`, which computes the whole (T, N) grid
# once and is shared by every policy that names the same signal. Two
# implementations of one formula is a place for them to disagree, so
# `test_portfolio_farm_signals.py` asserts the matrix equals the per-date
# function at sampled rows for EVERY registered signal. The scalar version is
# the specification; the matrix version is the executable; the test is the
# bridge. That is cheaper than trusting one clever vectorisation.


def _roll(x: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Trailing (sum, count) over the window ENDING at each row, inclusive.

    NaN is missing, not zero: the count comes back separately so a caller can
    require a minimum number of real observations instead of averaging a
    mostly-empty window into a confident-looking number.
    """
    ok = np.isfinite(x)
    z = np.where(ok, x, 0.0).astype(np.float64)
    c = ok.astype(np.float64)
    cs, cc = np.cumsum(z, axis=0), np.cumsum(c, axis=0)
    s_out, c_out = cs.copy(), cc.copy()
    if w < len(x):
        s_out[w:] = cs[w:] - cs[:-w]
        c_out[w:] = cc[w:] - cc[:-w]
    return s_out, c_out


def _roll_mean(x: np.ndarray, w: int, min_obs: int) -> np.ndarray:
    s, c = _roll(x, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / c
    return np.where(c >= min_obs, m, np.nan)


def _roll_std(x: np.ndarray, w: int, min_obs: int) -> np.ndarray:
    """Population stdev, matching `np.nanstd`'s default ddof=0."""
    s, c = _roll(x, w)
    s2, _ = _roll(np.where(np.isfinite(x), x, np.nan) ** 2, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = s2 / c - (s / c) ** 2
    var = np.where(var > 0, var, 0.0)
    return np.where(c >= min_obs, np.sqrt(var), np.nan)


def _tri_ret_matrix(tri: np.ndarray, back: int, skip: int) -> np.ndarray:
    """(T, N) of `tri[i-skip] / tri[i-back] - 1`, NaN where the window is not
    fully inside the sample. Row i uses rows <= i only, by construction."""
    t = tri.astype(np.float64)
    out = np.full(t.shape, np.nan)
    if back >= len(t):
        return out
    num = t[back - skip:len(t) - skip] if skip else t[back:]
    den = t[:len(t) - back]
    with np.errstate(invalid="ignore", divide="ignore"):
        val = np.where(den > 0, num / den - 1.0, np.nan)
    out[back:] = val
    return out


def _vol_matrix(panel, w: int = QUARTER) -> np.ndarray:
    return _roll_std(panel.ret.astype(np.float64), w, w // 2)


def matrix(panel, name: str, seed: int = 0) -> np.ndarray:
    """The whole (T, N) signal grid for one registered signal.

    `seed` only reaches `random`. It exists because ONE coin flip is not a
    control: a single random draw of twelve names from five hundred has an
    enormous terminal-wealth spread, so "the strategy beat the random policy"
    is a coin toss dressed as a comparison. The farm runs a BENCH of seeds and
    reports the null's distribution — see `farm.rank_report`.
    """
    T, N = panel.close.shape
    if name == "mom_12_1":
        return _tri_ret_matrix(panel.tri, YEAR, MONTH)
    if name == "mom_6_1":
        return _tri_ret_matrix(panel.tri, HALF, MONTH)
    if name == "mom_3_1":
        return _tri_ret_matrix(panel.tri, QUARTER, MONTH)
    if name == "mom_12_0":
        return _tri_ret_matrix(panel.tri, YEAR, 0)
    if name == "reversal_1m":
        return -_tri_ret_matrix(panel.tri, MONTH, 0)
    if name == "reversal_1w":
        return -_tri_ret_matrix(panel.tri, 5, 0)
    if name == "low_vol":
        return -_vol_matrix(panel)
    if name == "high_vol":
        return _vol_matrix(panel)
    if name == "trend_200":
        ma = _roll_mean(panel.tri.astype(np.float64), 200, 100)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(ma > 0, panel.tri.astype(np.float64) / ma - 1.0,
                            np.nan)
    if name == "size_small":
        mc = panel.mktcap.astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            return -np.log(np.where(mc > 0, mc, np.nan))
    if name == "size_large":
        mc = panel.mktcap.astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.log(np.where(mc > 0, mc, np.nan))
    if name == "illiquid":
        v = panel.dolvol.astype(np.float64)
        r = np.abs(panel.ret.astype(np.float64))
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(v > 0, r / v, np.nan)
        return _roll_mean(ratio, QUARTER, QUARTER // 2) * 1e6
    if name == "liquid":
        return _roll_mean(panel.dolvol.astype(np.float64), MONTH, LIQ_MIN_OBS)
    if name == "random":
        out = np.empty((T, N), dtype=np.float64)
        base = 1_000_003 + 7_919 * int(seed)
        for i in range(T):
            out[i] = np.random.default_rng(base + i).standard_normal(N)
        return out
    if name == "random_persistent":
        row = np.random.default_rng(500_009 + 7_919 * int(seed)
                                    ).standard_normal(N)
        return np.repeat(row[None, :], T, axis=0)
    if name == "equal":
        return np.zeros((T, N), dtype=np.float64)
    raise KeyError(f"no matrix implementation for signal {name!r}")
