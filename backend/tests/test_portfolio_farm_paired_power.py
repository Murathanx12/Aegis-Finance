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
    return FarmResult(policy=Policy(signal="equal", holding_days=5, top_k=10),
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
