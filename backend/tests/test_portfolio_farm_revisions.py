"""Analyst-revision state: the PIT rule, the derivations, and the composite.

WHY THE PIT TESTS ARE THE POINT
===============================
This is the farm's third data source and its first behavioural one. The join
is a forward-fill from monthly `statpers` stamps onto a daily grid, and the
whole thing turns on one character:

    np.searchsorted(stamps, session, side="left") - 1

`side="right"` includes a stamp landing exactly on the session date. That is a
lookahead which improves every number and raises nothing — no coverage figure
moves, no test fails, the signal simply gets better. So the join is shared with
`characteristics` rather than rewritten, and it is tested here directly with a
value planted on a known date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import revisions as RV
from backend.services.portfolio_farm import signals as SIG
from backend.services.portfolio_farm.characteristics import join_pit_series


def _frame(rows):
    return pd.DataFrame(rows, columns=["permno", "statpers", "numest",
                                       "numup", "numdown", "meanest", "stdev"])


# ── the PIT rule ────────────────────────────────────────────────────────────


def test_a_value_stamped_on_a_date_is_NOT_usable_that_day():
    """THE LOOKAHEAD. `statpers` is the compilation cut-off, so the value is
    usable STRICTLY AFTER it. Using it on the day itself is the off-by-one
    that turns a PIT join into a peek."""
    dates = np.array(["2013-01-01", "2013-01-02", "2013-01-03", "2013-01-04"],
                     dtype=object)
    permnos = np.array([10001], dtype=np.int64)
    df = pd.DataFrame([{"permno": 10001, "statpers": "2013-01-02", "v": 5.0}])
    mat, _ = join_pit_series(df, "v", "statpers", dates, permnos,
                            lag_sessions=0, stale_max_days=10**6)
    assert np.isnan(mat[0, 0]), "value seen before its stamp existed"
    assert np.isnan(mat[1, 0]), (
        "value used ON its statpers date — this is the lookahead")
    assert mat[2, 0] == pytest.approx(5.0)
    assert mat[3, 0] == pytest.approx(5.0), "not forward-filled"


def test_the_declared_lag_pushes_availability_further_out_never_nearer():
    dates = np.array([f"2013-01-{d:02d}" for d in range(1, 9)], dtype=object)
    permnos = np.array([10001], dtype=np.int64)
    df = pd.DataFrame([{"permno": 10001, "statpers": "2013-01-02", "v": 5.0}])
    no_lag, _ = join_pit_series(df, "v", "statpers", dates, permnos,
                                lag_sessions=0, stale_max_days=10**6)
    lagged, _ = join_pit_series(df, "v", "statpers", dates, permnos,
                                lag_sessions=2, stale_max_days=10**6)
    first_no = int(np.flatnonzero(np.isfinite(no_lag[:, 0]))[0])
    first_lag = int(np.flatnonzero(np.isfinite(lagged[:, 0]))[0])
    assert first_lag == first_no + 2


def test_a_stale_consensus_expires_rather_than_carrying_forever():
    """A company analysts stopped covering has no analyst state — it is not a
    company with an old revision. Without a bound, dropped coverage becomes an
    eternal signal, and the names that lose coverage are not a random sample."""
    dates = np.array([f"2013-{m:02d}-01" for m in range(1, 13)], dtype=object)
    permnos = np.array([10001], dtype=np.int64)
    df = pd.DataFrame([{"permno": 10001, "statpers": "2013-01-15", "v": 5.0}])
    mat, _ = join_pit_series(df, "v", "statpers", dates, permnos,
                            lag_sessions=0, stale_max_days=RV.STALE_MAX_DAYS)
    live = np.isfinite(mat[:, 0])
    assert live.any(), "nothing joined at all"
    assert not live[-1], "a January consensus still live in December"


def test_the_join_never_carries_one_companys_value_onto_another():
    dates = np.array(["2013-01-01", "2013-01-05"], dtype=object)
    permnos = np.array([10001, 10002], dtype=np.int64)
    df = pd.DataFrame([{"permno": 10001, "statpers": "2013-01-02", "v": 5.0}])
    mat, _ = join_pit_series(df, "v", "statpers", dates, permnos,
                            lag_sessions=0, stale_max_days=10**6)
    assert mat[1, 0] == pytest.approx(5.0)
    assert np.isnan(mat[:, 1]).all(), "value leaked to a permno with no data"


# ── the derivations ─────────────────────────────────────────────────────────


def test_breadth_is_net_analysts_over_coverage():
    df = _frame([
        (1, "2013-01-18", 10, 7, 1, 2.0, 0.1),
        (1, "2013-02-15", 10, 0, 5, 1.8, 0.2),
    ])
    d = RV.derive(df)
    assert d["rev_breadth"].iloc[0] == pytest.approx(0.6)
    assert d["rev_breadth"].iloc[1] == pytest.approx(-0.5)


def test_breadth_ABOVE_ONE_is_real_data_and_must_survive():
    """MY OWN BUG, caught by `portfolio_farm_calibrate` on its first run.

    I bounded breadth at |1| from the FORMULA, reasoning that numup+numdown
    cannot exceed numest. The data disagrees: `numup`/`numdown` are a FLOW —
    revisions filed during the period — while `numest` is a STOCK, the
    estimates standing now. An analyst may revise twice, and revising analysts
    may since have dropped coverage. Twelve up-revisions against seven standing
    estimates is a real, heavily-covered name.

    The (-1, 1) bound dropped 16,024 rows — 1.52%, and not a random 1.52%:
    precisely the names with the MOST revision activity, which are the most
    informative observations the signal has.
    """
    dates = np.array(["2013-01-01", "2013-02-20"], dtype=object)
    permnos = np.array([10001], dtype=np.int64)
    # 12 up-revisions, 7 standing estimates -> breadth 1.714
    df = _frame([(10001, "2013-01-18", 7, 12, 0, 1.0, 0.1)])
    d = RV.derive(df)
    assert d["rev_breadth"].iloc[0] == pytest.approx(12 / 7)

    mat = RV.load_revision("rev_breadth", dates, permnos, df=d,
                           lag_sessions=0)
    assert np.isfinite(mat[1, 0]), (
        "a heavily-revised name was dropped as implausible; the bound is "
        "being asserted from the formula rather than measured from the data")
    assert mat[1, 0] == pytest.approx(12 / 7, rel=1e-4)


def test_the_breadth_bound_is_a_measured_implausibility_not_a_data_cut():
    lo, hi = RV.PLAUSIBLE["rev_breadth"]
    assert (lo, hi) == (-5.0, 5.0), (
        "5.0 was chosen because ZERO of 1,051,457 rows exceed it; tightening "
        "it back toward 1 silently removes the most-revised names")


def test_magnitude_uses_the_PREVIOUS_month_of_the_SAME_company():
    """`groupby.shift` and not `.shift()`: a plain shift carries the last
    company's consensus onto the first row of the next one, and that row is
    every company's first appearance."""
    df = _frame([
        (1, "2013-01-18", 5, 1, 0, 1.00, 0.1),
        (1, "2013-02-15", 5, 1, 0, 1.50, 0.1),
        (2, "2013-01-18", 5, 1, 0, 9.00, 0.1),   # different company
        (2, "2013-02-15", 5, 1, 0, 9.90, 0.1),
    ])
    d = RV.derive(df)
    assert np.isnan(d["rev_magnitude"].iloc[0]), "first row has no previous"
    assert d["rev_magnitude"].iloc[1] == pytest.approx(0.5)
    assert np.isnan(d["rev_magnitude"].iloc[2]), (
        "company 2's first row took company 1's consensus as its previous")
    assert d["rev_magnitude"].iloc[3] == pytest.approx(0.1)


def test_the_denominator_floor_stops_rounding_becoming_a_signal():
    """Summary EPS estimates are ROUNDED. A consensus of $0.02 going to $0.03
    is a 50% 'revision' that is mostly the rounding grid."""
    df = _frame([
        (1, "2013-01-18", 5, 0, 0, 0.02, 0.01),
        (1, "2013-02-15", 5, 1, 0, 0.03, 0.01),
    ])
    d = RV.derive(df)
    # 0.01 / max(0.02, FLOOR=0.10) = 0.10, not 0.50
    assert d["rev_magnitude"].iloc[1] == pytest.approx(0.10)


def test_dispersion_is_negated_so_high_means_agreement():
    """The sign is a declaration made before any result, not something read
    off one afterwards."""
    df = _frame([
        (1, "2013-01-18", 5, 0, 0, 2.0, 0.05),   # analysts agree
        (2, "2013-01-18", 5, 0, 0, 2.0, 0.90),   # analysts disagree
    ])
    d = RV.derive(df)
    agree, disagree = d["rev_dispersion"].iloc[0], d["rev_dispersion"].iloc[1]
    assert agree > disagree
    assert (d["rev_dispersion"] <= 0).all(), "negation lost"


def test_implausible_values_are_dropped_and_not_clipped():
    """A top-k book RANKS by the value and takes the extreme end, so it does
    not merely tolerate an artefact — it selects one every date in preference
    to every real firm. Clipping would make them all TIE at the cap, which
    hands the selection back to the permno tie-break."""
    for name, (lo, hi) in RV.PLAUSIBLE.items():
        assert lo < hi


def test_a_single_analyst_is_not_a_consensus():
    assert RV.MIN_ESTIMATES >= 3


# ── the composite ───────────────────────────────────────────────────────────


def test_the_composite_is_registered_NEXT_TO_its_components():
    """`arena_composite` declared six weighted factors and was 12-1 momentum
    for 99.5% of names; nobody could see it because only the composite was
    ever reported. Components stay independently rankable."""
    for n in RV.AVAILABLE:
        assert n in SIG.SIGNALS
    assert "sell_side_state" in SIG.SIGNALS


def test_a_name_missing_any_channel_is_not_selectable():
    """Missing is missing, never 'average' — the same rule `replay` applies to
    volatility for inverse-vol sizing."""
    from backend.tests.test_portfolio_farm_pit import synthetic
    p = synthetic()
    N = p.close.shape[1]
    p.chars["rev_magnitude"] = p.chars["rev_magnitude"].copy()
    p.chars["rev_magnitude"][:, 0] = np.nan          # one name loses a channel
    g = SIG.matrix(p, "sell_side_state")
    assert np.isnan(g[:, 0]).all(), (
        "a name with only two of three channels was still selectable")
    assert np.isfinite(g[5, 1:]).any(), "the other names lost their score too"


def test_an_all_nan_date_scores_NOTHING_rather_than_tying_every_name():
    """THE SILENT TIE. `zscore` used to return ZEROS for a row with nothing to
    standardise. Every name then scores identically, `top_k` falls through to
    the permno tie-break, and the book quietly becomes `oldest_listing` on
    exactly the dates where the signal had no data — the hardest place to
    notice it, and a live path because IBES coverage is thin at the window's
    edges."""
    z = SIG.zscore(np.array([np.nan, np.nan, np.nan]))
    assert np.isnan(z).all(), (
        "an all-NaN row produced finite scores, so every name ties and the "
        "tie-break silently chooses the book")

    flat = SIG.zscore(np.array([2.0, 2.0, 2.0]))
    assert np.isnan(flat).all(), (
        "a zero-variance row produced a tie rather than a refusal")


def test_composite_scores_are_not_all_equal_on_a_populated_date():
    from backend.tests.test_portfolio_farm_pit import synthetic
    g = SIG.matrix(synthetic(), "sell_side_state")
    row = g[10]
    fin = row[np.isfinite(row)]
    assert fin.size > 2 and len(np.unique(fin)) > 1, (
        "the composite is constant across names, so its holdings would come "
        "from the tie-break")


# ── the module refuses rather than degrading ────────────────────────────────


def test_missing_source_files_are_a_REFUSAL_not_a_silent_empty_signal():
    """A run that silently dropped its only behavioural signal would look like
    a result ABOUT that signal."""
    with pytest.raises(RV.RevisionsUnavailable):
        RV._load_raw(dir_=__import__("pathlib").Path("no-such-dir"))


def test_available_reports_empty_when_the_files_are_absent():
    from pathlib import Path
    assert RV.available(dir_=Path("no-such-dir")) == ()


def test_only_FY1_eps_is_used_and_it_is_declared():
    """`fpi` also carries FY2, next-quarter and long-term growth. Mixing
    horizons would silently change what the signal means mid-panel."""
    assert (RV.MEASURE, RV.FPI) == ("EPS", "1")
