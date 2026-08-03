"""Regression tests: quantile_return_spread must refuse degenerate cross-sections.

Motivating defect (found 2026-08-02, audit Part V-B L2):
`pd.qcut(x.rank(method="first"), 5)` on an all-tied factor breaks ties by ROW
ORDER. The panel is built in sorted-ticker order, so a factor that is identically
zero was bucketed ALPHABETICALLY into five clean quantiles and reported
`available: True` with a fabricated top-minus-bottom spread.

Measured before the fix: a 12-name, 5-date, all-zero factor produced
`top_minus_bottom = +0.01739` (+174 bp) with `available: True`, while the IC leg
correctly reported `n_periods: 0`. The live `insider_opp` PIT series had exactly
this shape (72 observations, 1 distinct value, all 0.0), so every forward-IC
receipt built on it carried a manufactured spread.

These tests are deliberately offline and dependency-free.
"""

import numpy as np
import pandas as pd

from engine.validation.factor_ic import analyze_factor, quantile_return_spread

TICKERS = [
    "AARD", "ABSI", "AMSC", "BHVN", "DKNG", "HUBS",
    "KYTX", "NTLA", "PRCH", "QUBT", "SLDP", "SOC",
]


def _panel(factor_fn, n_dates: int = 5, seed: int = 42) -> pd.DataFrame:
    """Long panel shaped like the live book universe, sorted-ticker order."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-06-16", periods=n_dates, freq="7D")
    rows = [
        {
            "date": d,
            "ticker": t,
            "factor": factor_fn(i, d),
            "fwd": rng.normal(0, 0.06),
        }
        for d in dates
        for i, t in enumerate(TICKERS)
    ]
    return pd.DataFrame(rows)


def test_constant_factor_is_refused_not_scored():
    """A dead signal must not produce a spread. This is the exact live defect."""
    res = quantile_return_spread(_panel(lambda i, d: 0.0), "factor", "fwd")

    assert res["available"] is False
    assert res["reason"] == "degenerate cross-section"
    assert res["n_degenerate_dates"] == 5
    assert "top_minus_bottom" not in res


def test_sparse_factor_is_refused():
    """Sparse signals (insider scores are 0 for most names) are also degenerate.

    Only 3 distinct values across 12 names < 5 quantiles, so the remaining
    spread would come from tie-breaking, not information.
    """
    res = quantile_return_spread(
        _panel(lambda i, d: float(i) if i >= 10 else 0.0), "factor", "fwd"
    )

    assert res["available"] is False
    assert res["reason"] == "degenerate cross-section"


def test_healthy_factor_still_scores():
    """The fix must not suppress genuine cross-sectional variation."""
    rng = np.random.default_rng(7)
    res = quantile_return_spread(
        _panel(lambda i, d: float(rng.normal())), "factor", "fwd"
    )

    assert res["available"] is True
    assert res["n_dates_used"] == 5
    assert "top_minus_bottom" in res
    assert "n_degenerate_dates_skipped" not in res


def test_partial_degeneracy_is_disclosed_not_hidden():
    """Dates that could not be bucketed must be surfaced, not silently dropped."""
    rng = np.random.default_rng(11)
    dead_dates = pd.to_datetime(["2026-06-16", "2026-06-23"])

    def factor(i, d):
        return 0.0 if d in dead_dates else float(rng.normal())

    res = quantile_return_spread(_panel(factor), "factor", "fwd")

    assert res["available"] is True
    assert res["n_degenerate_dates_skipped"] == 2
    assert res["n_dates_used"] == 3
    assert "warning" in res


def test_analyze_factor_reports_dead_signal_consistently():
    """Both legs must agree that a constant factor carries no information."""
    res = analyze_factor(_panel(lambda i, d: 0.0), "factor", "fwd")

    assert res["ic"]["n_periods"] == 0
    assert res["quantiles"]["available"] is False
