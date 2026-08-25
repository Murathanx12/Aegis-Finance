"""The paired power check compares a book to ANOTHER BOOK, not to the market.

Its one correctness claim is that the two series are aligned on DATES. Two
books at the same rebalance phase can still begin on different sessions — a
signal with a warm-up forfeits leading rows that a null does not — and slicing
by length would subtract Tuesday from Wednesday for the whole history, then
report the calendar as an effect.

That failure is silent: the shapes match, the arithmetic runs, and the number
is wrong. So it gets a test rather than a comment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.portfolio_farm.policy import FarmResult, Policy  # noqa: E402
from scripts import portfolio_farm_paired_power as PP  # noqa: E402


def _result(dates, nav) -> FarmResult:
    return FarmResult(policy=Policy(signal="oldest_listing", holding_days=5, top_k=10),
                      dates=list(dates), nav=[float(x) for x in nav],
                      metrics={"status": "ok", "terminal_usd": float(nav[-1])})


def _dates(n, start=0):
    return list(range(start, start + n))


def test_identical_dates_pass_through():
    n = 400
    a = _result(_dates(n), np.linspace(10_000, 12_000, n))
    b = _result(_dates(n), np.linspace(10_000, 11_000, n))
    sr, br = PP.paired_returns(a, b)
    assert len(sr) == len(br) == n   # daily_returns keeps a NaN at index 0


def test_short_overlap_is_refused_not_truncated():
    """Under a year of shared sessions returns None. A paired power check on
    100 days would print a tracking error it cannot support."""
    a = _result(_dates(300, start=0), np.linspace(10_000, 12_000, 300))
    b = _result(_dates(300, start=200), np.linspace(10_000, 11_000, 300))
    assert PP.paired_returns(a, b) is None


def test_offset_start_aligns_on_dates_not_on_length():
    """THE REGRESSION. The signal book starts 60 sessions late. Both books hold
    the SAME asset, so a correct alignment gives an excess of exactly zero; a
    length-based slice would compare offset days and manufacture one."""
    n = 500
    rng = np.random.default_rng(11)
    path = 10_000 * np.cumprod(1.0 + rng.normal(0.0004, 0.011, n))

    full = _result(_dates(n), path)
    late = _result(_dates(n)[60:], path[60:])

    sr, br = PP.paired_returns(late, full)
    assert len(sr) == len(br) == n - 60
    # same asset over the same sessions -> the difference is identically zero
    assert np.nanmax(np.abs(sr - br)) < 1e-12


def test_offset_start_would_have_been_wrong_under_length_slicing():
    """Shows the bug this guards against is real, not hypothetical: slicing the
    longer series by length instead of by date leaves a non-zero difference
    between two books holding the identical asset."""
    n = 500
    rng = np.random.default_rng(11)
    path = 10_000 * np.cumprod(1.0 + rng.normal(0.0004, 0.011, n))

    naive_s = np.diff(path[60:]) / path[60:-1]
    naive_b = np.diff(path[:n - 60]) / path[:n - 61]
    assert np.nanmax(np.abs(naive_s - naive_b)) > 1e-4


def test_disjoint_dates_return_none():
    a = _result(_dates(400, start=0), np.linspace(10_000, 12_000, 400))
    b = _result(_dates(400, start=5_000), np.linspace(10_000, 11_000, 400))
    assert PP.paired_returns(a, b) is None


def test_min_paired_sessions_is_declared_not_inlined():
    """A threshold that only exists as a literal inside a loop cannot be found
    by the next reader, and this one changes what the script will report."""
    assert PP.MIN_PAIRED_SESSIONS >= 250


@pytest.mark.parametrize("offset", [1, 7, 63, 249])
def test_alignment_holds_at_several_offsets(offset):
    n = 800
    rng = np.random.default_rng(offset)
    path = 10_000 * np.cumprod(1.0 + rng.normal(0.0003, 0.009, n))
    sr, br = PP.paired_returns(_result(_dates(n)[offset:], path[offset:]),
                               _result(_dates(n), path))
    assert len(sr) == n - offset
    assert np.nanmax(np.abs(sr - br)) < 1e-12


# --------------------------------------------------------------------------
# The breadth verdict shares this file because it is the same question asked
# a different way: what is this book's edge measured AGAINST, and is the
# number that scores it measuring what its label claims.
# --------------------------------------------------------------------------
from scripts import portfolio_farm_breadth_power as BP  # noqa: E402


def _ts(pairs, excess):
    """(k, t, excess) triples; `excess` scalar or per-k."""
    ex = excess if isinstance(excess, (list, tuple)) else [excess] * len(pairs)
    return [(k, t, e) for (k, t), e in zip(pairs, ex)]


def test_rising_t_on_negative_excess_is_not_scaling():
    """THE REGRESSION. `value_bm` ran t -0.77 -> -0.39 over k=10..50 while
    losing to the market at every breadth, and the verdict line called it
    'SCALES with breadth'. A loss shrinking as it dilutes has the same slope
    as an edge diversifying; only the sign of the excess separates them."""
    ts = _ts([(10, -0.77), (20, -0.45), (30, -0.39), (50, -0.59)], -1.23)
    v = BP.breadth_verdict(ts)
    assert v["t_vs_log_k_slope"] > 0          # the slope really does rise
    assert v["excess_positive_over_grid"] is False
    assert v["scales_with_breadth"] is False
    assert "N/A" in BP.verdict_text(v)


def test_rising_t_on_positive_excess_is_scaling():
    ts = _ts([(10, 1.12), (20, 1.67), (30, 1.19), (50, 2.47)], 2.38)
    v = BP.breadth_verdict(ts)
    assert v["scales_with_breadth"] is True
    assert BP.verdict_text(v) == "SCALES with breadth"


def test_peak_at_narrowest_book_is_not_scaling_even_with_positive_excess():
    """`liquid` — the edge lives in the extreme tail and dilutes at once."""
    ts = _ts([(10, 1.56), (20, 0.20), (30, -0.43), (50, -0.09)], 0.16)
    v = BP.breadth_verdict(ts)
    assert v["peak_t_at_k"] == 10
    assert v["scales_with_breadth"] is False
    assert "does NOT scale" in BP.verdict_text(v)


def test_slope_and_peak_conditions_are_near_collinear():
    """Documents a property of the rule rather than asserting a fiction.

    The verdict requires BOTH a rising fitted slope and a peak away from the
    narrowest book. Trying to build a case that satisfies one and not the
    other shows why: a `t` that peaks at the narrowest k drags the log-fit
    negative almost mechanically. The peak condition is therefore a backstop
    against a single noisy wide point, not an independent second test — worth
    knowing before anyone treats agreement between them as confirmation.
    """
    peaks_narrow = _ts([(10, 1.0), (20, 0.1), (30, 0.2), (50, 0.9)], 3.0)
    v = BP.breadth_verdict(peaks_narrow)
    assert v["peak_t_at_k"] == 10
    assert v["t_vs_log_k_slope"] < 0        # the slope followed the peak
    assert v["scales_with_breadth"] is False

    rises = _ts([(10, 0.5), (20, 0.6), (30, 0.7), (50, 2.1)], 3.0)
    w = BP.breadth_verdict(rises)
    assert w["peak_t_at_k"] == 50 and w["t_vs_log_k_slope"] > 0
    assert w["scales_with_breadth"] is True


def test_shipped_receipt_scores_exactly_two_signals_as_scaling():
    """Pins the 1993-2024 result itself. If a future change to the rule or the
    panel moves this, it should be a deliberate edit to this number."""
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parents[1] / "data" / "optimus"
         / "portfolio_farm" / "farm_breadth_power_1993_2024.json")
    if not p.exists():
        pytest.skip("32-year breadth receipt not present")
    d = json.loads(p.read_text(encoding="utf-8"))
    scaling = {s for s, v in d["verdicts"].items() if v["scales_with_breadth"]}
    assert scaling == {"profit_roe", "mom_12_1"}, scaling
