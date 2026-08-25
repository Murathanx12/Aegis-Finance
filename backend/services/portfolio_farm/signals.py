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

THIRTEEN SIGNALS WERE THIRTEEN VIEWS OF ONE FILE
================================================
Audited 2026-08-25. Every non-null signal below reads from exactly three
quantities — past returns, market cap, dollar volume — all of them columns of
`crsp.dsf`. A library like that cannot produce an INDEPENDENT selector however
many entries it gains, because independence is a property of the DATA and not
of the formula. The 2013-2024 grid showed what that looks like: zero of
thirteen resolvable at 80% power, and a reality-check p of 0.358.

So `value_bm` and `profit_roe` are here, sourced from `characteristics.py`
(WRDS `finratio`, PIT-stamped by `public_date`, both eras). They are the first
signals in this module that are not transformations of price. See that module
for the join rule and its caveats — chiefly that `bm` has a price in its
denominator and `roe` does not, which makes `roe` the cleaner test of whether a
second data source buys anything.

STILL DELIBERATELY ABSENT
=========================
Estimate revisions, insider filings, news events, options state. Those live in
the arena's information bus and in the collectors. IBES consensus IS on disk
for both eras (`ibes_consensus_monthly*`, with `numup`/`numdown`), so a
revision signal is the obvious next one and it is not built yet.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

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



def oldest_listing(panel, i: int) -> np.ndarray:
    """The k OLDEST surviving eligible listings. Formerly, and wrongly, `equal`.

    THIS IS WHAT `equal` ALWAYS WAS. Scoring every name 0.0 does not produce a
    neutral book — it produces whatever the tie-break produces, and `top_k`
    breaks ties in permno order, which CRSP assigns roughly in listing order.
    The holdings are unchanged by this rename; only the honesty is.

    Scored EXPLICITLY as `-permno` so the selection is declared rather than
    inherited from sort stability. A baseline whose holdings depend on the
    stability of a sort is one refactor away from silently becoming a different
    baseline, and nothing would print differently when it did.

    IT IS A CONFOUND DETECTOR, NOT A NULL. It is the hardest benchmark the farm
    has: high-ROE large caps ARE old listings, so `profit_roe` measured against
    the cap-weighted market needed 31 years and measured against THIS needed
    126 (`portfolio_farm_paired_power`, 2026-08-25). Use it to ask "is my
    signal distinguishable from listing age?", never to ask "did I beat
    chance" — `random_persistent` answers that and comes with a distribution.
    """
    return -panel.permnos.astype(np.float64)


def newest_listing(panel, i: int) -> np.ndarray:
    """The k NEWEST eligible listings — the opposite tail of `oldest_listing`.

    The canon requires an opposite-tail control, and on 2026-08-24 that
    requirement caught a wrong ship (AMENDMENT-1). Age is a real exposure only
    if its two ends behave differently: if both the oldest and the newest books
    beat the market, the story is the universe and the costs, and "age" was
    never the mechanism.
    """
    return panel.permnos.astype(np.float64)


#: The old name, kept resolvable because receipts already on disk carry it and
#: a receipt that no longer parses is a mutated history. Every lookup goes
#: through `resolve_alias`, so nothing reads `SIGNALS["equal"]` directly.
DEPRECATED_ALIASES = {"equal": "oldest_listing"}


def resolve_alias(name: str) -> str:
    """Map a retired signal name onto its current one, loudly."""
    new = DEPRECATED_ALIASES.get(name)
    if new is None:
        return name
    logger.warning(
        "signal %r was renamed to %r on 2026-08-25: scoring every name equally "
        "does not produce an equal-weight book, it produces the tie-break, and "
        "the tie-break is permno order (= listing age). Same holdings, honest "
        "name.", name, new)
    return new


def _characteristic(panel, name: str) -> np.ndarray:
    """The PIT-joined characteristic grid `load_panel` attached, or a REFUSAL.

    Joined once when the panel is built, not lazily here: `run_many` calls
    `matrix()` once per policy, and rebuilding a ~1.9M-row groupby eighty times
    for one grid is the kind of cost that quietly makes a sweep un-runnable.

    A missing characteristic is an error and not an all-NaN column. A policy
    that names `value_bm` and silently holds nothing would appear on the
    leaderboard as a signal that does not work, which is the most expensive
    possible way to be wrong.
    """
    m = (panel.chars or {}).get(name)
    if m is None:
        raise KeyError(
            f"characteristic {name!r} was not joined onto this panel. Either "
            f"the finratio parquets are absent from backend/data/optimus/wrds/ "
            f"or the panel was built with with_characteristics=False. This is "
            f"a refusal rather than an all-NaN signal, because a book that "
            f"silently holds nothing looks exactly like a signal that does not "
            f"work.")
    return m


def value_bm(panel, i: int) -> np.ndarray:
    """Book-to-market. HIGH is cheap, so high scores buy value.

    Not a price transformation, though price IS in the denominator — which is
    why `profit_roe` is the cleaner test of whether a second data source adds
    anything the price file did not already contain.
    """
    return _characteristic(panel, "bm")[i].astype(np.float64)


def profit_roe(panel, i: int) -> np.ndarray:
    """Return on equity. HIGH is profitable. No price anywhere in it."""
    return _characteristic(panel, "roe")[i].astype(np.float64)


def rev_breadth(panel, i: int) -> np.ndarray:
    """Net share of analysts revising UP. (numup - numdown) / numest.

    Bounded in [-1, 1] by construction, so no denominator can blow it up —
    which is why it is the component to trust when `rev_magnitude` and the
    census disagree.
    """
    return _characteristic(panel, "rev_breadth")[i].astype(np.float64)


def rev_magnitude(panel, i: int) -> np.ndarray:
    """How far the FY1 consensus moved this month, floored to kill rounding.

    Two analysts nudging by a cent is not one analyst halving their number,
    and `rev_breadth` scores those identically. Carries the IBES split-restate
    caveat (`revisions.py` docstring) — it is the component to distrust first.
    """
    return _characteristic(panel, "rev_magnitude")[i].astype(np.float64)


def rev_dispersion(panel, i: int) -> np.ndarray:
    """NEGATED analyst disagreement, so HIGH means analysts agree.

    The sign is declared here rather than discovered from a result: forecast
    dispersion is a documented NEGATIVE return predictor, so agreement scores
    high and the direction is on the record before any number is computed.
    """
    return _characteristic(panel, "rev_dispersion")[i].astype(np.float64)


def sell_side_state(panel, i: int) -> np.ndarray:
    """SELL_SIDE_STATE_v1 — the three analyst channels, equally weighted.

    Cross-sectional z-score of each component on the date, then a plain sum.
    Equal weights, not fitted ones: a weight learned on the same history that
    is about to be scored is the leakage this project has already paid for,
    and the fixed-combination baseline has to exist BEFORE any learned router
    can be said to beat something.

    A name missing any component is NaN and therefore not selectable. Missing
    is missing, never "average" — the same rule `replay` applies to volatility
    for inverse-vol sizing.
    """
    raw = [f(panel, i) for f in (rev_breadth, rev_magnitude, rev_dispersion)]
    valid = np.isfinite(raw[0]) & np.isfinite(raw[1]) & np.isfinite(raw[2])
    parts = [zscore(r) for r in raw]
    out = parts[0] + parts[1] + parts[2]
    # A name missing ANY channel is not selectable. Requiring all three is
    # what makes this a state rather than "whichever channel happened to have
    # data" — and it keeps the composite's universe identical to the universe
    # its components are diagnosed on.
    return np.where(valid, out, np.nan)


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
    # the first two that are not transformations of price
    "value_bm": value_bm,
    "profit_roe": profit_roe,
    # THE THIRD DATA SOURCE: what analysts SAID, not what prices did.
    # Components and composite both registered — see `sell_side_state`.
    "rev_breadth": rev_breadth,
    "rev_magnitude": rev_magnitude,
    "rev_dispersion": rev_dispersion,
    "sell_side_state": sell_side_state,
    "random": random_signal,
    "random_persistent": random_persistent,
    # EXPLICIT BASELINES. Each states what it selects; none of them relies on
    # a tie-break to decide its holdings. See `test_explicit_baselines.py`.
    "oldest_listing": oldest_listing,
    "newest_listing": newest_listing,
}

#: Signals that exist to be BEATEN, not to win. Reported separately on the
#: leaderboard so a null cannot be quoted as a discovery.
#:
#: They are NOT interchangeable and `farm.compare_within_groups` does not pool
#: them: `random` re-draws every formation date (MAXIMUM turnover — 492x/yr at
#: a 1-session holding period, 29.5%/yr of cost at 6 bps), `random_persistent`
#: is one fixed basket (near-zero turnover), and `oldest_listing` /
#: `newest_listing` are deterministic reference lines that state what they
#: select. The bar a real signal must clear against CHANCE is the 90th
#: percentile of the two RANDOM families — chance at both ends of the
#: trading-cost axis. The age books are a different and harder question:
#: "is this distinguishable from listing age?", which is the one raw
#: `profit_roe` failed.
NULL_SIGNALS = frozenset({"random", "random_persistent",
                          "oldest_listing", "newest_listing"})

#: Baselines that are DELIBERATE STRATEGIES rather than draws from chance.
#: They are reported separately from the random family because beating them
#: means something different: `random*` asks "better than luck", these ask
#: "distinguishable from a named alternative explanation".
EXPLICIT_BASELINES = frozenset({"oldest_listing", "newest_listing"})


def zscore(x: np.ndarray) -> np.ndarray:
    """Cross-sectional z, NaN-safe. Used to combine signals; never to rank a
    single one (ranking is scale-free, and z-ing first would only add a way to
    be wrong about the dispersion).

    A ROW WITH NOTHING TO STANDARDISE RETURNS NaN, NOT ZEROS. Returning zeros
    was the original behaviour and it is a silent tie: every name scores the
    same, `top_k` falls through to the permno tie-break, and the book quietly
    becomes `oldest_listing` on exactly the dates where the signal had no data.
    That is the same defect the `equal` rename fixed one level up, and here it
    would appear only on the dates with no coverage — the hardest place to
    notice it. `sell_side_state` has no IBES coverage before 1990 and thin
    coverage at the edges of the window, so this is a live path and not a
    hypothetical.

    NaN means "not selectable", which `replay` already handles: `_targets`
    filters on `np.isfinite(sig_row)` and counts an empty selection.
    """
    a = np.asarray(x, dtype=np.float64)
    if not np.isfinite(a).any():
        # An all-NaN row is an EXPECTED state, not an anomaly: IBES has no
        # coverage at the edges of the window. Answer it directly rather than
        # letting nanmean warn its way to the same result.
        return np.full_like(a, np.nan)
    m = np.nanmean(a)
    s = np.nanstd(a)
    if not np.isfinite(s) or s == 0:
        return np.full_like(a, np.nan)
    return (a - m) / s


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
    name = resolve_alias(name)
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
    if name in ("rev_breadth", "rev_magnitude", "rev_dispersion"):
        return _characteristic(panel, name).astype(np.float64)
    if name == "sell_side_state":
        parts = [_characteristic(panel, n).astype(np.float64)
                 for n in ("rev_breadth", "rev_magnitude", "rev_dispersion")]
        # z-score ROW BY ROW: a cross-sectional z is a statement about the
        # names available on that date, and pooling across dates would let a
        # later date's dispersion set an earlier date's scale — a lookahead
        # that no PIT join would catch because it happens after the join.
        zs = [np.apply_along_axis(zscore, 1, m) for m in parts]
        valid = (np.isfinite(parts[0]) & np.isfinite(parts[1])
                 & np.isfinite(parts[2]))
        return np.where(valid, zs[0] + zs[1] + zs[2], np.nan)
    if name == "value_bm":
        return _characteristic(panel, "bm").astype(np.float64)
    if name == "profit_roe":
        return _characteristic(panel, "roe").astype(np.float64)
    if name == "liquid":
        return _roll_mean(panel.dolvol.astype(np.float64), MONTH, LIQ_MIN_OBS)
    if name == "oldest_listing":
        return np.tile(-panel.permnos.astype(np.float64), (T, 1))
    if name == "newest_listing":
        return np.tile(panel.permnos.astype(np.float64), (T, 1))
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
    raise KeyError(f"no matrix implementation for signal {name!r}")
