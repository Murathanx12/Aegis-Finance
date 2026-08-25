"""Two implementations of one formula, and the bridge between them.

`signals.py` has a per-date function (the readable SPECIFICATION) and a
vectorised whole-grid function (the EXECUTABLE the farm actually runs). Two
implementations is two places to be wrong, and the vectorised one is where an
off-by-one hides — a window shifted one row the wrong way is a lookahead that
improves every number and raises nothing.

So every registered signal is checked at sampled rows: `matrix(panel)[i]` must
equal `fn(panel, i)`. That is the whole file. It is cheap, it runs on a
synthetic panel in milliseconds, and it is the only reason the fast vectorised
path can be trusted.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import signals as SIG
from backend.tests.test_portfolio_farm_pit import synthetic

ROWS = [260, 300, 350, 400, 419]


@pytest.mark.parametrize("name", sorted(SIG.SIGNALS))
def test_the_matrix_equals_the_per_date_function(name):
    p = synthetic()
    g = SIG.matrix(p, name)
    fn = SIG.SIGNALS[name]
    for i in ROWS:
        a = np.asarray(g[i], dtype=np.float64)
        b = np.asarray(fn(p, i), dtype=np.float64)
        both_nan = np.isnan(a) & np.isnan(b)
        assert (both_nan | np.isclose(a, b, rtol=1e-4, atol=1e-7)).all(), (
            f"{name}: vectorised grid and per-date function disagree at row "
            f"{i}. One of them is reading a different window — and the fast "
            f"one is what every leaderboard number came from.\n"
            f"  matrix[{i}][:5] = {a[:5]}\n  fn(panel,{i})[:5] = {b[:5]}")


#: The first row on which each signal may legitimately produce a number. Not a
#: blanket "row 5 must be NaN": `reversal_1w` looks back five sessions and IS
#: measurable there, and a test that pretended otherwise would have to be
#: silenced with an exemption, which is how a real warmup bug later gets waved
#: through. Each entry is the signal's own declared window.
FIRST_VALID_ROW = {
    "mom_12_1": SIG.YEAR, "mom_12_0": SIG.YEAR, "mom_6_1": SIG.HALF,
    "mom_3_1": SIG.QUARTER, "reversal_1m": SIG.MONTH, "reversal_1w": 5,
    # min_obs=31 means rows 0..30 hold 31 observations, so row 30 is the
    # first valid one. The off-by-one is the whole reason this table is
    # explicit rather than derived from the same expression the code uses.
    "low_vol": SIG.QUARTER // 2 - 1, "high_vol": SIG.QUARTER // 2 - 1,
    "illiquid": SIG.QUARTER // 2 - 1, "trend_200": 99,
    "liquid": SIG.LIQ_MIN_OBS - 1,
    # Point-in-time by construction: no trailing window to fill.
    "size_small": 0, "size_large": 0, "random": 0,
    "random_persistent": 0,
    # The EXPLICIT baselines. `-permno` / `+permno` need no history at all,
    # which is precisely what makes them baselines. They replaced `equal`,
    # whose constant score had no holdings of its own — it inherited the
    # sort's tie-break, which is permno order, i.e. listing age.
    "oldest_listing": 0, "newest_listing": 0,
    # The non-price pair. Their "window" is not a trailing count of sessions —
    # it is whether a `public_date` exists strictly before the session — so the
    # synthetic panel supplies a grid whose first row is deliberately NaN and
    # whose second is not. Row 1 is therefore the declared first valid row, and
    # the check still bites: a dispatcher that read row i instead of i-1 would
    # produce a number on row 0.
    "value_bm": 1, "profit_roe": 1,
    # The analyst-revision channels and their composite. Same construction as
    # the non-price pair: availability is a `statpers` strictly before the
    # session, not a trailing window, so row 1 is the first valid row and a
    # dispatcher reading row i instead of i-1 would produce a number on row 0.
    "rev_breadth": 1, "rev_magnitude": 1, "rev_dispersion": 1,
    "sell_side_state": 1,
}


@pytest.mark.parametrize("name", sorted(SIG.SIGNALS))
def test_nothing_is_computed_before_its_window_is_full(name):
    """Before a trailing window is full, the answer is UNKNOWN. Computing it
    from whatever history exists produces a confident number out of four days
    of data, and the farm would trade on it through every warmup."""
    p = synthetic()
    g = SIG.matrix(p, name)
    first = FIRST_VALID_ROW[name]
    if first == 0:
        assert np.isfinite(g[0]).any() or name == "equal"
        return
    assert np.isnan(g[first - 1]).all(), (
        f"{name} produced a value on row {first - 1}, one row before its "
        f"declared window ({first}) is full")
    assert np.isfinite(g[first]).any(), (
        f"{name} is still NaN on row {first}, where its window IS full — the "
        f"warmup is longer than declared and the farm loses that history")


def test_every_signal_declares_a_first_valid_row():
    """A new signal without an entry here would skip the warmup check
    silently."""
    assert set(FIRST_VALID_ROW) == set(SIG.SIGNALS)


def test_the_random_signal_is_reproducible_and_seed_dependent():
    p = synthetic()
    a = SIG.matrix(p, "random", 0)
    b = SIG.matrix(p, "random", 0)
    c = SIG.matrix(p, "random", 1)
    assert np.array_equal(a, b), "a rerun must reproduce the same null"
    assert not np.array_equal(a, c), (
        "two seeds produced the same draw — the null 'distribution' would be "
        "twenty copies of one portfolio")


def test_every_registered_signal_has_a_matrix_implementation():
    """The registry and the fast path must agree, or a policy naming a signal
    with no grid dies at run time inside a six-hundred-policy sweep."""
    p = synthetic()
    for name in SIG.SIGNALS:
        assert SIG.matrix(p, name).shape == p.close.shape


def test_an_unregistered_signal_raises_rather_than_returning_zeros():
    with pytest.raises(KeyError):
        SIG.matrix(synthetic(), "mom_18_2")


def test_the_null_signals_are_declared_as_nulls():
    """A baseline must be flagged, or the leaderboard ranks it as a strategy.

    `equal` was retired on 2026-08-25: scoring every name identically produces
    no book of its own, only whatever the sort's tie-break produces, and that
    tie-break is permno order — i.e. listing age. It is now `oldest_listing`,
    with `newest_listing` as the opposite-tail control the canon requires.
    """
    assert SIG.NULL_SIGNALS <= set(SIG.SIGNALS)
    assert "random" in SIG.NULL_SIGNALS
    assert {"oldest_listing", "newest_listing"} <= SIG.NULL_SIGNALS
    assert SIG.EXPLICIT_BASELINES <= SIG.NULL_SIGNALS
    # the retired name must not silently reappear as a registry entry
    assert "equal" not in SIG.SIGNALS
