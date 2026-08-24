"""A COLUMN IS NOT DATA: the openprc coverage gate.

WHY THIS TEST EXISTS
====================
`replayable_years` certified a year on the presence of `openprc`, `retx` and
`shrout` in its parquet schema. That rule was correct for the failure it was
written against — the 1990-2012 pull requested five columns and the years had
to be refused by name.

The 2026-08-25 re-pull then gave those years the full twelve-column schema, and
the schema check alone would have flipped every one of them to REPLAYABLE. But
CRSP has no open prices before mid-1992:

    1990   0.0%    1992  41.6%    1993  82.6%    2013  93.2%    2024  99.4%

A 1990 replay would therefore have run with an `openprc` matrix that is
entirely NaN. `replay` refuses to fill at a non-positive open, so every
decision would go unfilled and the "strategy" would be a buy-and-never-trade
book wearing a momentum policy's name and hash — the strongest form of the
failure mode this package has hit four times already, where the INSTRUMENT
moves the answer more than the strategy does.

Fixing the pull created the hole. These tests hold it shut.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import panel as P

pytest.importorskip("pyarrow")


def _write_year(dir_, year: int, *, open_frac: float, n_permno: int = 6,
                n_days: int = 40) -> None:
    """One year's parquet with a DECLARED share of usable open prices."""
    rng = np.random.default_rng(year)
    dates = pd.bdate_range(f"{year}-01-01", periods=n_days).astype(str)
    rows = []
    for j in range(n_permno):
        for i, d in enumerate(dates):
            rows.append({"permno": 10000 + j, "date": d,
                         "prc": 50.0 + i, "ret": 0.001, "retx": 0.001,
                         "vol": 1e6, "shrout": 1e5, "openprc": np.nan,
                         "askhi": 51.0, "bidlo": 49.0,
                         "cfacpr": 1.0, "cfacshr": 1.0})
    df = pd.DataFrame(rows)
    k = int(round(open_frac * len(df)))
    if k:
        df.loc[rng.permutation(len(df))[:k], "openprc"] = 50.0
    df.to_parquet(dir_ / f"crsp_dsf_{year}.parquet", index=False)


def test_an_empty_openprc_column_is_not_a_replayable_year(tmp_path):
    """The exact hole the re-pull opened: full schema, no data in it."""
    _write_year(tmp_path, 1990, open_frac=0.0)

    # the schema check — the OLD rule — is satisfied.
    assert P.REQUIRED_COLUMNS <= P.year_columns(1990, tmp_path)
    # and the year is still refused.
    assert P.replayable_years(tmp_path) == []


def test_the_floor_sits_in_the_gap_CRSP_itself_leaves(tmp_path):
    """1992 (41.6%) is refused, 1993 (82.6%) is admitted.

    No year in CRSP lands between those two, so where the floor sits inside
    that gap cannot change a verdict. Pinned so a later edit that "tidies" the
    constant to 0.9 or 0.3 has to argue with a test.
    """
    _write_year(tmp_path, 1992, open_frac=0.416)
    _write_year(tmp_path, 1993, open_frac=0.826)
    assert P.replayable_years(tmp_path) == [1993]
    assert 0.416 < P.OPEN_COVERAGE_FLOOR < 0.826


def test_load_panel_refuses_the_empty_year_and_says_there_is_no_re_pull(tmp_path):
    """An absent column and an empty one need DIFFERENT fixes, so they get
    different refusals. Re-pulling 1990 forever will not produce an open."""
    _write_year(tmp_path, 1990, open_frac=0.0)
    _write_year(tmp_path, 1991, open_frac=0.0)
    with pytest.raises(P.PanelUnavailable) as e:
        P.load_panel(1990, 1991, dir_=tmp_path)
    msg = str(e.value)
    assert "nearly) empty" in msg or "empty" in msg
    assert "nothing to re-pull" in msg
    assert "1990" in msg


def test_coverage_is_measured_from_statistics_not_guessed(tmp_path):
    _write_year(tmp_path, 2000, open_frac=0.5)
    assert P.year_open_coverage(2000, tmp_path) == pytest.approx(0.5, abs=0.02)
    _write_year(tmp_path, 2001, open_frac=1.0)
    assert P.year_open_coverage(2001, tmp_path) == pytest.approx(1.0, abs=1e-6)


def test_a_missing_openprc_column_reads_as_zero_coverage(tmp_path):
    """Not an exception: the two gates compose, and a year with no column at
    all must fail the coverage gate as well as the schema gate."""
    df = pd.DataFrame({"permno": [1, 1], "date": ["2000-01-03", "2000-01-04"],
                       "prc": [1.0, 1.0], "ret": [0.0, 0.0], "vol": [1.0, 1.0]})
    df.to_parquet(tmp_path / "crsp_dsf_2000.parquet", index=False)
    assert P.year_open_coverage(2000, tmp_path) == 0.0
    assert P.replayable_years(tmp_path) == []


def test_negative_opens_count_as_missing_in_the_panels_own_figure(tmp_path):
    """CRSP writes a NEGATIVE open for a bid/ask midpoint on a no-trade day,
    and `replay` will not fill at one. The statistics-based gate cannot see a
    sign, so `Panel.open_coverage` is the figure that must.
    """
    _write_year(tmp_path, 2005, open_frac=1.0)
    p = tmp_path / "crsp_dsf_2005.parquet"
    df = pd.read_parquet(p)
    half = len(df) // 2
    df.loc[:half - 1, "openprc"] = -50.0        # midpoints, not trades
    df.to_parquet(p, index=False)

    # the cheap gate still sees a full column ...
    assert P.year_open_coverage(2005, tmp_path) == pytest.approx(1.0)
    # ... and the loaded panel reports the truth that governs the fills.
    pan = P.load_panel(2005, 2005, dir_=tmp_path)
    assert pan.open_coverage == pytest.approx(0.5, abs=0.02)


def test_the_live_window_is_reported_and_is_high(tmp_path):
    """Guard against the gate silently starting to pass everything: the real
    2013-2024 window must still report a coverage, and a high one."""
    try:
        pan = P.load_panel(2023, 2023)
    except P.PanelUnavailable:
        pytest.skip("CRSP parquets not present on this machine")
    assert 0.90 <= pan.open_coverage <= 1.0
