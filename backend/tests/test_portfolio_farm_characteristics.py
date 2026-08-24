"""The farm's first non-price join, and the off-by-one that would ruin it.

WHY THIS FILE MATTERS MORE THAN A SIGNAL TEST
=============================================
Every signal in `signals.py` before these two was a function of the CRSP daily
file, so PIT correctness was a matter of not indexing past row `i` — checked by
`test_portfolio_farm_pit.py` with a planted oracle.

A characteristic is different. It comes from a MONTHLY file with its own
availability stamp, and the join has to decide, for each daily session, which
monthly value was already public. Get the inequality backwards by one and the
book trades on a book-to-market ratio published later that same day. That is a
lookahead which improves every number and raises nothing — and unlike a
windowing bug it would not show up as an oracle correlation, because the
characteristic really is a legitimate signal, just known too early.

So the rule is stated once and tested three ways: a value stamped
`public_date = d` may be used on a session **strictly after** `d`, plus a
declared `LAG_SESSIONS` margin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import characteristics as CH

pytest.importorskip("pyarrow")

PERMNOS = np.array([10001, 10002], dtype=np.int64)
DATES = np.array([f"2000-01-{d:02d}" for d in range(1, 29)], dtype=object)


def _write(dir_, rows) -> None:
    """Both era files, so `load_characteristic` finds what it expects."""
    df = pd.DataFrame(rows)
    for src in CH.SOURCES:
        (df if src == CH.SOURCES[0] else df.iloc[0:0]).to_parquet(
            dir_ / f"{src}.parquet", index=False)


def test_a_value_is_NOT_visible_on_its_own_public_date(tmp_path):
    """The off-by-one this file exists for. `searchsorted(side="right")` would
    make the stamp date itself visible, which is trading on a number published
    that day."""
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-10",
                       "bm": 1.0, "roe": 0.5}])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    j = 0
    day10 = int(np.flatnonzero(DATES == "2000-01-10")[0])
    assert np.isnan(m[day10][j]), (
        "a value stamped 2000-01-10 was visible ON 2000-01-10 — the join is "
        "reading its own publication date")
    assert m[day10 + 1][j] == pytest.approx(1.0), (
        "the value was not visible the day AFTER publication either; the join "
        "is not late, it is broken")


def test_nothing_is_visible_before_the_first_stamp(tmp_path):
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-20",
                       "bm": 1.0, "roe": 0.5}])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    before = int(np.flatnonzero(DATES == "2000-01-20")[0])
    assert np.isnan(m[:before + 1, 0]).all()
    assert np.isfinite(m[before + 1:, 0]).all()


def test_the_declared_lag_is_applied_on_top(tmp_path):
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-10",
                       "bm": 1.0, "roe": 0.5}])
    day10 = int(np.flatnonzero(DATES == "2000-01-10")[0])
    for lag in (0, 1, 3):
        m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                                   lag_sessions=lag, stale_max_days=10_000)
        first = day10 + 1 + lag
        assert np.isnan(m[first - 1, 0]), f"lag {lag} was not applied"
        assert m[first, 0] == pytest.approx(1.0), f"lag {lag} over-applied"


def test_the_latest_stamp_wins_and_earlier_ones_do_not_reappear(tmp_path):
    """A restatement must supersede, and the old figure must not come back on
    a later session because the search landed on the wrong side of it."""
    _write(tmp_path, [
        {"permno": 10001, "public_date": "2000-01-05", "bm": 1.0, "roe": 0.1},
        {"permno": 10001, "public_date": "2000-01-15", "bm": 2.0, "roe": 0.2},
        {"permno": 10001, "public_date": "2000-01-25", "bm": 3.0, "roe": 0.3},
    ])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    at = {d: int(np.flatnonzero(DATES == d)[0]) for d in
          ("2000-01-05", "2000-01-15", "2000-01-25")}
    assert m[at["2000-01-05"] + 1, 0] == pytest.approx(1.0)
    assert m[at["2000-01-15"], 0] == pytest.approx(1.0)      # still the old one
    assert m[at["2000-01-15"] + 1, 0] == pytest.approx(2.0)
    assert m[at["2000-01-25"] + 1, 0] == pytest.approx(3.0)
    assert m[-1, 0] == pytest.approx(3.0)


def test_a_stale_value_stops_being_carried(tmp_path):
    """Without a bound, a company that stops reporting stays a value stock
    forever — and the companies that stop reporting are not a random sample."""
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-02",
                       "bm": 1.0, "roe": 0.5}])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=5)
    assert np.isfinite(m[3, 0])
    assert np.isnan(m[20, 0]), "a value from 18 calendar days ago was carried"


def test_a_permno_absent_from_the_source_is_NaN_not_zero(tmp_path):
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-02",
                       "bm": 1.0, "roe": 0.5}])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    assert np.isnan(m[:, 1]).all(), (
        "permno 10002 has no rows in the source and must be NaN — a zero would "
        "rank it as the cheapest name in the universe")


def test_an_unknown_characteristic_REFUSES(tmp_path):
    _write(tmp_path, [{"permno": 10001, "public_date": "2000-01-02",
                       "bm": 1.0, "roe": 0.5}])
    with pytest.raises(CH.CharacteristicUnavailable, match="unknown"):
        CH.load_characteristic("pe_ratio", DATES, PERMNOS, dir_=tmp_path)


def test_an_absent_source_REFUSES_rather_than_returning_all_NaN(tmp_path):
    """An all-NaN column would put a policy on the leaderboard as a signal that
    does not work, which is the most expensive way to be wrong."""
    with pytest.raises(CH.CharacteristicUnavailable, match="absent"):
        CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path)


def test_a_signal_naming_a_missing_characteristic_REFUSES(tmp_path):
    from backend.services.portfolio_farm import signals as SIG
    from backend.tests.test_portfolio_farm_pit import synthetic
    p = synthetic()
    bare = type(p)(**{**{f.name: getattr(p, f.name)
                         for f in p.__dataclass_fields__.values()},
                      "chars": {}})
    with pytest.raises(KeyError, match="was not joined"):
        SIG.matrix(bare, "value_bm")


def test_the_live_join_reaches_most_of_the_traded_panel():
    """Coverage is a property of the DATA and belongs in a receipt: a signal
    present on 8% of traded cells is a sub-universe wearing a signal's name."""
    from backend.services.portfolio_farm import panel as P
    try:
        pan = P.load_panel(2015, 2016)
    except P.PanelUnavailable:
        pytest.skip("CRSP parquets not present on this machine")
    if not pan.chars:
        pytest.skip("finratio parquets not present on this machine")
    for name, mat in pan.chars.items():
        cov = CH.coverage(mat, pan.traded)
        assert cov["share_of_traded_cells"] > 0.5, (
            f"{name} reaches only {cov['share_of_traded_cells']:.1%} of traded "
            f"cells; a book built on it is a different universe from a "
            f"price-signal book and the comparison is not like-for-like")


def test_implausible_values_are_DROPPED_not_clipped(tmp_path):
    """A top-k book ranks by the characteristic and takes the EXTREME end, so
    it does not merely tolerate an accounting artefact — it selects one, every
    date, in preference to every real firm.

    Measured on `finratio_monthly`: `bm` runs to 89,351 and `roe` from -21,992
    to +5,304, against medians of 0.50 and 0.056. Those are book equities of
    approximately zero, not companies.

    DROPPED rather than winsorised: clipping makes every extreme value TIE at
    the cap, and `top_k` then falls through to permno order — replacing "the
    most extreme artefacts" with "the oldest listings among them", which is
    worse because it looks deliberate.
    """
    _write(tmp_path, [
        {"permno": 10001, "public_date": "2000-01-02", "bm": 1.0, "roe": 0.1},
        {"permno": 10002, "public_date": "2000-01-02", "bm": 89351.0,
         "roe": 5303.7},
    ])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    assert m[10, 0] == pytest.approx(1.0)
    assert np.isnan(m[10, 1]), (
        "a book-to-market of 89,351 survived; a top-k book would hold it on "
        "every date in preference to every real firm")
    r = CH.load_characteristic("roe", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    assert np.isnan(r[10, 1])


def test_non_positive_book_to_market_is_excluded(tmp_path):
    """Zero or negative book equity is a distressed accounting state, not a
    cheap stock. A bm of exactly 0 would sort as the most EXPENSIVE name in the
    universe rather than the most broken."""
    _write(tmp_path, [
        {"permno": 10001, "public_date": "2000-01-02", "bm": 0.0, "roe": 0.1},
        {"permno": 10002, "public_date": "2000-01-02", "bm": 0.5, "roe": 0.1},
    ])
    m = CH.load_characteristic("bm", DATES, PERMNOS, dir_=tmp_path,
                               lag_sessions=0, stale_max_days=10_000)
    assert np.isnan(m[10, 0])
    assert m[10, 1] == pytest.approx(0.5)


def test_the_bounds_sit_OUTSIDE_the_real_distribution():
    """They must remove the arithmetic tail and leave the signal. Pinned
    against a later edit that tightens them into the data — the 99.9th
    percentiles are bm 11.7 and roe 8.9."""
    assert CH.PLAUSIBLE["bm"] == (0.0, 20.0)
    assert CH.PLAUSIBLE["roe"] == (-10.0, 10.0)
    assert CH.PLAUSIBLE["bm"][1] > 11.7
    assert CH.PLAUSIBLE["roe"][1] > 8.9


def test_the_int64_and_string_search_paths_agree_exactly():
    """The join searchsorts on INT64 day numbers when every panel date parses,
    and on the raw strings when they do not (the synthetic grid uses ordering
    markers). Two code paths is two places to be wrong, and the fast one is
    what every 1993-2024 receipt will come from.

    Measured on 2013-2016, 3.7M finite cells, zero mismatches.
    """
    import pandas as pd
    from backend.services.portfolio_farm import panel as P
    try:
        pan = P.load_panel(2015, 2016, with_characteristics=False)
    except P.PanelUnavailable:
        pytest.skip("CRSP parquets not present on this machine")
    if not CH.available_characteristics():
        pytest.skip("finratio parquets not present on this machine")

    fast = CH.load_characteristic("bm", pan.dates, pan.permnos)

    saved = CH.pd.to_datetime

    def _one_bad_date(x, *a, **k):
        out = saved(x, *a, **k)
        if isinstance(out, pd.Series) and len(out) == len(pan.dates):
            out = out.copy()
            out.iloc[0] = pd.NaT          # forces the string path
        return out

    CH.pd.to_datetime = _one_bad_date
    try:
        slow = CH.load_characteristic("bm", pan.dates, pan.permnos)
    finally:
        CH.pd.to_datetime = saved

    a, b = fast[1:], slow[1:]             # row 0 differs by construction
    same = (np.isnan(a) & np.isnan(b)) | (a == b)
    assert same.all(), (
        f"{int((~same).sum())} cells differ between the int64 and string "
        f"search paths — the fast join is not the join that was tested")
