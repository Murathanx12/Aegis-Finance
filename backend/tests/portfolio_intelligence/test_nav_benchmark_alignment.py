"""The NAV date-stamp offset corrupts every DATE-JOINED benchmark statistic.

Measured 2026-08-20 while deciding P-day-2026-08-19a's scope. The facts
the decision turns on, each verifiable in the code rather than argued:

  1. `mark_lane_to_market` stamps the NAV row `date.today()` while
     `_get_current_prices` serves the last COMPLETED daily bar — usually
     the previous session's close. NAV_t therefore carries price_{t-1}.
  2. `mark_lane_to_market` persists ONLY the lane's own NAV. No benchmark
     value is stored alongside it.
  3. `comparator._fetch_benchmark_returns` pulls SPY from yfinance
     indexed by TRUE BAR DATE. It does not share the lane's offset.
  4. `real_analyzer._compute_beta_tracking` joins portfolio and benchmark
     on the DATE INDEX (`pd.DataFrame({...}).dropna()`).

Put together: lane-vs-lane comparisons cancel the offset because every
lane carries it, but **lane-vs-benchmark is already misaligned by one
day** in beta, tracking error and information ratio. The fix (stamp the
bar's own date) REPAIRS that comparison; it does not endanger it.

That reverses the guidance first written into PROPOSALS.md, which assumed
lane and benchmark were shifted together and warned that a partial fix
would break lane-vs-SPY. The real risk runs the other way: someone
"helpfully" shifting the benchmark to match would BREAK a comparison the
fix has just repaired.

These tests pin the consequence with known-answer data, so the claim is
enforced rather than remembered.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.real_analyzer import (
    _compute_beta_tracking,
)


def _known_world(n: int = 400, beta: float = 1.5, seed: int = 20260820):
    """A world where the portfolio's beta vs the benchmark is EXACTLY `beta`.

    No noise in the relationship: any departure of the measured beta from
    `beta` is caused by misalignment, not by estimation error, which is
    what makes this a known-answer test rather than a tolerance-fitting
    exercise.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    bench_ret = pd.Series(rng.normal(0, 0.01, n), index=idx)
    port_ret = beta * bench_ret
    bench_px = pd.DataFrame({"SPY": 100 * (1 + bench_ret).cumprod()},
                            index=idx)
    return port_ret, bench_px


def test_aligned_nav_recovers_true_beta():
    """Control: with correct stamps the known beta comes back exactly."""
    port_ret, bench_px = _known_world(beta=1.5)
    # bench_px.pct_change() drops the first row, so the portfolio series
    # is trimmed the same way to keep this a pure alignment test
    out = _compute_beta_tracking(port_ret.iloc[1:], "SPY", bench_px)
    assert out["beta_vs_spy"] is not None
    assert abs(out["beta_vs_spy"] - 1.5) < 0.01, out
    # a perfectly explained portfolio has active risk only from the
    # beta-1 market exposure, never from misalignment
    assert out["tracking_error_vs_spy"] is not None


def test_one_day_stamp_offset_destroys_beta():
    """The live defect: NAV stamped t while carrying price_{t-1}.

    Shifting the portfolio series forward by one index position is
    exactly what the stamp bug does to the join, and it should wreck a
    relationship that is otherwise noiseless.
    """
    port_ret, bench_px = _known_world(beta=1.5)
    shifted = port_ret.shift(1).dropna()      # NAV_t carries return_{t-1}
    out = _compute_beta_tracking(shifted, "SPY", bench_px)
    assert out["beta_vs_spy"] is not None
    # with independent daily returns, a one-day shift removes essentially
    # all covariance: the measured beta collapses toward zero
    assert abs(out["beta_vs_spy"]) < 0.3, (
        f"a one-day stamp offset should destroy beta, got "
        f"{out['beta_vs_spy']} (expected near 0, true value 1.5)")


def test_shifting_the_benchmark_too_does_not_fix_it():
    """The tempting 'fix' that must NOT ship.

    If the stamp fix moves lane NAV onto bar dates and someone also
    shifts the benchmark 'to match', the two shifts do not cancel — they
    reintroduce the same misalignment. Only the lane side is wrong, so
    only the lane side moves.
    """
    port_ret, bench_px = _known_world(beta=1.5)
    # both series shifted by one: still aligned with each other, so this
    # one RECOVERS beta and is the case that makes the point precisely —
    # shifting both is harmless ONLY if both were wrong to begin with
    both = _compute_beta_tracking(
        port_ret.shift(1).dropna(),
        "SPY",
        pd.DataFrame({"SPY": bench_px["SPY"].shift(1)}, index=bench_px.index),
    )
    # and the asymmetric case — lane corrected, benchmark ALSO shifted —
    # is the one that breaks
    asym = _compute_beta_tracking(
        port_ret.iloc[1:],
        "SPY",
        pd.DataFrame({"SPY": bench_px["SPY"].shift(1)}, index=bench_px.index),
    )
    assert both["beta_vs_spy"] is not None
    assert abs(both["beta_vs_spy"] - 1.5) < 0.01
    assert asym["beta_vs_spy"] is not None
    assert abs(asym["beta_vs_spy"]) < 0.3, (
        "correcting the lane while ALSO shifting the benchmark "
        "reintroduces the misalignment — this is the half-fix to avoid")


def test_benchmark_is_not_persisted_with_nav():
    """Fact (2): no benchmark column exists in paper_nav.

    If this ever fails, a benchmark HAS been persisted alongside NAV and
    would then inherit the lane's stamp — at which point the alignment
    reasoning above changes and this whole file must be revisited.
    """
    from backend.db import get_connection, init_db
    import tempfile
    import pathlib

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "t.db"
        init_db(p)
        conn = get_connection(p)
        try:
            cols = {r[1].lower() for r in
                    conn.execute("PRAGMA table_info(paper_nav)")}
        finally:
            conn.close()
    assert cols, "paper_nav has no columns — schema changed"
    for forbidden in ("spy", "benchmark", "bench_nav", "benchmark_value"):
        assert forbidden not in cols, (
            f"paper_nav now stores {forbidden!r}; a persisted benchmark "
            f"would inherit the lane's date stamp and the P-day-2026-08-19a "
            f"scope decision must be re-derived")
