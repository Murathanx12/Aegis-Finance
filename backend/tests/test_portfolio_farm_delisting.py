"""The delisting return is MEASURED, and the wrong join is worth 57% of wealth.

WHY THIS FILE EXISTS
====================
For three of this package's first four presets, every holding that left CRSP was
resolved at a DECLARED -30%. The sensitivity sweep then showed that one number
was worth an 18x swing in terminal wealth — larger than signal, holding period,
breadth and rebalance phase combined, and wide enough to straddle the market
benchmark. The answer was an assumption wearing a result.

`crsp__dsedelist.parquet` was already on disk, in the WRDS bulk pull, unjoined.
Measured over the 3,089 real events in 2013-2024:

    2xx mergers        1,962   dlret median  +0.0004
    5xx dropped          891   dlret median  -0.2000
    all                3,089   dlret median   0.0000, 60.5% at or above zero

A merged shareholder receives the deal consideration, so -30% was simply wrong
for two thirds of the population — and 12-1 momentum is especially exposed
because it systematically selects acquisition targets.

So the tests here are about the JOIN, not the arithmetic: the code filter, the
fallback, and the counting that lets a receipt say how much of its own answer is
still an assumption.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import panel as P, replay
from backend.services.portfolio_farm.panel import Panel
from backend.services.portfolio_farm.policy import Policy
from backend.tests.test_portfolio_farm_replay import _flat_panel, _pol

T = 420


def _write(tmp_path, rows) -> "object":
    p = tmp_path / "dsedelist.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


# ── the join ────────────────────────────────────────────────────────────────


def test_measured_returns_are_aligned_to_the_permno_axis(tmp_path):
    path = _write(tmp_path, [
        {"permno": 3, "dlstcd": 231, "dlret": 0.0125},
        {"permno": 1, "dlstcd": 574, "dlret": -0.4200},
    ])
    ret, code = P.load_delisting(np.array([1, 2, 3, 4]), path=path)
    assert ret[0] == pytest.approx(-0.42)
    assert np.isnan(ret[1]), "a permno with no event must be NaN, not 0.0"
    assert ret[2] == pytest.approx(0.0125)
    assert np.isnan(ret[3])
    assert code[0] == 574 and code[2] == 231


def test_code_100_is_STILL_ACTIVE_and_is_excluded(tmp_path):
    """`dlstcd=100` means the security is live. 2013-2024 holds 3,866 such rows
    against 3,089 real events, so joining them would resolve live positions —
    the book would liquidate names that never delisted."""
    path = _write(tmp_path, [{"permno": 1, "dlstcd": 100, "dlret": 0.0}])
    ret, _ = P.load_delisting(np.array([1]), path=path)
    assert np.isnan(ret[0]), "an ACTIVE security was joined as a delisting"


def test_a_missing_file_yields_NaN_and_not_zero(tmp_path):
    """Zero is a real delisting return (a merger at the last price). 'We do not
    know' must not render as 'the holder lost nothing'."""
    ret, code = P.load_delisting(np.array([1, 2]),
                                 path=tmp_path / "absent.parquet")
    assert np.isnan(ret).all() and np.isnan(code).all()


def test_the_LAST_event_wins_when_a_permno_has_several(tmp_path):
    path = _write(tmp_path, [
        {"permno": 7, "dlstcd": 231, "dlret": 0.01},
        {"permno": 7, "dlstcd": 574, "dlret": -0.55},
    ])
    ret, _ = P.load_delisting(np.array([7]), path=path)
    assert ret[0] == pytest.approx(-0.55)


# ── what the engine does with it ────────────────────────────────────────────


def _panel_that_delists(measured):
    """A flat book where the whole universe leaves the file at row 300."""
    p = _flat_panel(n_names=4)
    close = p.close.copy()
    close[300:, :] = np.nan
    return Panel(**{**p.__dict__, "close": close, "traded": np.isfinite(close),
                    "delist_ret": np.asarray(measured, dtype=np.float64)})


def test_the_MEASURED_return_is_used_in_preference_to_the_declared_one():
    """A merger at 0.0 must not be booked at the -30% fallback."""
    merged = _panel_that_delists([0.0, 0.0, 0.0, 0.0])
    assumed = _panel_that_delists([np.nan] * 4)
    pol = _pol(signal="oldest_listing", holding_days=1000, delisting_return=-0.30)
    a = replay.run(merged, pol, warmup=260)
    b = replay.run(assumed, pol, warmup=260)
    assert a.metrics["terminal_usd"] > b.metrics["terminal_usd"] * 1.3
    assert a.diagnostics["n_delist_measured"] == 4
    assert a.diagnostics["n_delist_assumed"] == 0
    assert b.diagnostics["n_delist_measured"] == 0
    assert b.diagnostics["n_delist_assumed"] == 4


def test_the_split_is_COUNTED_so_a_receipt_can_say_how_much_is_assumed():
    """A run that fell back on most of its exits still has an assumption for a
    headline. The only way a reader can tell is if the counts are on the row."""
    mixed = _panel_that_delists([0.0, np.nan, -0.2, np.nan])
    res = replay.run(mixed, _pol(signal="oldest_listing", holding_days=1000), warmup=260)
    d = res.diagnostics
    assert d["n_delist_measured"] == 2
    assert d["n_delist_assumed"] == 2
    assert d["n_delistings"] == d["n_delist_measured"] + d["n_delist_assumed"]


def test_a_panel_with_no_delisting_data_still_runs_on_the_declared_value():
    """The farm must not require the join to exist — it must require the
    receipt to SAY the join did not exist."""
    p = _panel_that_delists([np.nan] * 4)
    p = Panel(**{**p.__dict__, "delist_ret": None})
    res = replay.run(p, _pol(signal="oldest_listing", holding_days=1000,
                             delisting_return=-1.0), warmup=260)
    assert res.diagnostics["n_delist_assumed"] == res.diagnostics["n_delistings"]
    assert res.diagnostics["n_delist_measured"] == 0
