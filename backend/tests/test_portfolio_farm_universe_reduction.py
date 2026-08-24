"""The liquidity reduction must save memory WITHOUT changing a selection.

WHY THE REDUCTION EXISTS
========================
Every `Panel` matrix is dense (dates x permnos), so a permno the farm never
holds still costs a full float32 column. Over 2013-2024 that was affordable.
Over 1993-2024 it is not: the CRSP files union to ~18,700 permnos across 8,064
sessions — 0.6 GB per matrix, ~4.8 GB for the eight a `Panel` carries, before
the pandas frame that builds them.

And it is nearly all waste. Measured 2026-08-25 over 2013-2024, only 1,967 of
6,894 permnos (28.5%) ever reach the top 500 by trailing dollar volume.

WHY IT IS ALLOWED TO
====================
`liquid_permnos` applies the SAME criterion `replay` uses — traded, finite
close, close >= min_price, finite trailing 21-day mean dollar volume, ranked by
that mean — and keeps to `universe_n * UNIVERSE_KEEP_MULTIPLE`. A name outside
the kept set was never in the top `universe_n` on any date, so no book could
have held it.

That argument is only as good as its enforcement, which is what these tests
are. The reduction is NOT point-in-time — it reads the whole window to decide
which columns to materialise — and that is sound for a MEMBERSHIP question and
would be fatal for a signal. The line between those two is the price floor and
the universe depth, so both REFUSE rather than degrade.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import farm, panel as P
from backend.services.portfolio_farm import replay as R
from backend.services.portfolio_farm.policy import Policy

pytest.importorskip("pyarrow")


def _synthetic_year(dir_, year: int, n_liquid: int = 30, n_dust: int = 120,
                    n_days: int = 60) -> None:
    """A year where a few names are always liquid and many never are."""
    rng = np.random.default_rng(year)
    dates = pd.bdate_range(f"{year}-01-01", periods=n_days).astype(str)
    rows = []
    for j in range(n_liquid + n_dust):
        liquid = j < n_liquid
        base = 40.0 + 5 * j
        vol = 5e6 if liquid else 2e3
        px = base
        for d in dates:
            px *= 1.0 + rng.normal(0, 0.01)
            rows.append({"permno": 10000 + j, "date": d, "prc": px,
                         "ret": 0.0004, "retx": 0.0004, "vol": vol,
                         "shrout": 1e5, "openprc": px,
                         "cfacpr": 1.0})
    pd.DataFrame(rows).to_parquet(dir_ / f"crsp_dsf_{year}.parquet",
                                  index=False)


def test_the_kept_set_excludes_names_no_book_could_hold(tmp_path):
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y)
    keep, rec = P.liquid_permnos(2000, 2001, universe_n=5, dir_=tmp_path,
                                 cache=False)
    # At least the cut depth survives, and never more than the liquid names:
    # the union over dates can exceed `kept_to_rank` because rank membership
    # moves as prices drift, which is the correct behaviour and not a leak.
    assert keep.size >= 5 * P.UNIVERSE_KEEP_MULTIPLE
    assert keep.size <= 30
    assert rec["kept_to_rank"] == 5 * P.UNIVERSE_KEEP_MULTIPLE
    assert rec["n_permnos_kept"] == keep.size
    # and they are the LIQUID ones, not an arbitrary slice
    assert set(keep) <= set(range(10000, 10030))


def test_the_reduced_panel_replays_to_the_SAME_nav(tmp_path):
    """The claim the whole reduction rests on. Not 'close' — identical."""
    for y in (2000, 2001, 2002):
        _synthetic_year(tmp_path, y, n_days=120)
    pol = Policy(signal="mom_12_1", holding_days=5, top_k=3,
                 sizing="equal_weight", universe_n=10, min_price=5.0)

    full = P.load_panel(2000, 2002, dir_=tmp_path, with_characteristics=False)
    red = P.load_panel(2000, 2002, dir_=tmp_path, reduce_for_universe_n=10, with_characteristics=False)
    assert red.shape[1] < full.shape[1], "reduction removed nothing"

    a = R.run(full, pol, warmup=30)
    b = R.run(red, pol, warmup=30)
    assert np.allclose(a.nav, b.nav, rtol=0, atol=1e-9)
    assert a.metrics["terminal_usd"] == pytest.approx(b.metrics["terminal_usd"])


def test_a_deeper_universe_is_REFUSED_not_truncated(tmp_path):
    """The failure this guard exists for: the same policy hash quietly drawing
    from a universe that no longer contains the names beyond the cut."""
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y)
    red = P.load_panel(2000, 2001, dir_=tmp_path, reduce_for_universe_n=5, with_characteristics=False)
    deep = Policy(signal="mom_12_1", holding_days=5, top_k=3,
                  sizing="equal_weight", universe_n=100)
    with pytest.raises(ValueError, match="liquidity-reduced to rank"):
        R.run(red, deep)


def test_a_different_price_floor_is_REFUSED(tmp_path):
    """A floor shrinks the eligible set, so the top-N cut reaches deeper into
    the ranking — the reduction computed at one floor is not valid at another.
    """
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y)
    red = P.load_panel(2000, 2001, dir_=tmp_path, reduce_for_universe_n=5, with_characteristics=False)
    cheap = Policy(signal="mom_12_1", holding_days=5, top_k=3,
                   sizing="equal_weight", universe_n=5, min_price=0.0)
    with pytest.raises(ValueError, match="min_price"):
        R.run(red, cheap)


def test_an_unreduced_panel_refuses_nothing(tmp_path):
    """The guard must not fire on the full panel — it has every name."""
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y, n_days=120)
    full = P.load_panel(2000, 2001, dir_=tmp_path, with_characteristics=False)
    assert full.universe_reduced_to is None
    R.run(full, Policy(signal="mom_12_1", holding_days=5, top_k=3,
                       sizing="equal_weight", universe_n=100, min_price=0.0),
          warmup=30)


def test_the_receipt_records_what_was_assumed(tmp_path):
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y)
    _, rec = P.liquid_permnos(2000, 2001, universe_n=5, dir_=tmp_path,
                              cache=False)
    for k in ("window", "universe_n", "keep_multiple", "kept_to_rank",
              "min_prices", "n_permnos_kept", "n_dates_scanned"):
        assert k in rec, k
    assert rec["min_prices"] == list(P.REDUCTION_MIN_PRICES)


def test_the_cache_round_trips(tmp_path):
    for y in (2000, 2001):
        _synthetic_year(tmp_path, y)
    a, ra = P.liquid_permnos(2000, 2001, universe_n=5, dir_=tmp_path)
    b, rb = P.liquid_permnos(2000, 2001, universe_n=5, dir_=tmp_path)
    assert np.array_equal(a, b)
    assert ra == rb
