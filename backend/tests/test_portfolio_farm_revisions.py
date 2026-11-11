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

from backend.services import ibes_pit_consensus as PIT
from backend.services.portfolio_farm import revisions as RV
from backend.services.portfolio_farm import signals as SIG
from backend.services.portfolio_farm.characteristics import join_pit_series


def _frame(rows):
    """As-quoted rows (what `ibes_pit_consensus` hands `derive`), no splits."""
    f = pd.DataFrame(rows, columns=["permno", "statpers", "numest",
                                    "numup", "numdown", "meanest", "stdev"])
    return f.assign(share_basis=PIT.AS_QUOTED, adj_factor=1.0)


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


def test_a_near_zero_QUOTED_level_is_floored_not_dropped():
    """As quoted, $0.02 -> $0.03 is real cents on that month's share basis (the
    split-adjusted file, where it was disproportionately a future splitter, is
    no longer read). The original FLOOR applies: 0.01 / 0.10 = +10%. The PR #94
    interim guard (NaN below an ADJUSTED $0.25) selected on the future split
    factor and is gone (review 3, 2026-11-11)."""
    df = _frame([
        (1, "2013-01-18", 5, 0, 0, 0.02, 0.01),
        (1, "2013-02-15", 5, 1, 0, 0.03, 0.01),
    ])
    d = RV.derive(df)
    assert d["rev_magnitude"].iloc[1] == pytest.approx(0.10)


def test_the_floor_still_bounds_a_real_level_change():
    df = _frame([
        (1, "2013-01-18", 5, 0, 0, 0.30, 0.05),
        (1, "2013-02-15", 5, 1, 0, 0.36, 0.05),
    ])
    d = RV.derive(df)
    assert d["rev_magnitude"].iloc[1] == pytest.approx(0.20)


# -- a FUTURE split must not move the signal (review 3, 2026-11-11) ----------

_N, _SPLITTER, _FUTURE = 40, 0, 256.0


def _quoted_month():
    """One month, as quoted: dispersion rises with firm index, and the SPLITTER
    carries the HIGHEST dispersion of all (stdev 0.90 on a $3.00 consensus)."""
    rows = []
    for i in range(_N):
        me = 3.0 if i == _SPLITTER else 1.0 + 2.0 * i / _N
        cv = 0.30 if i == _SPLITTER else 0.02 + 0.006 * i
        rows.append({"ticker": f"T{i:02d}", "statpers": pd.Timestamp("2004-06-17"),
                     "fpi": "1", "measure": "EPS", "numest": 8.0, "numup": 1.0,
                     "numdown": 1.0, "meanest": round(me, 2), "medest": round(me, 2),
                     "stdev": round(cv * me, 2), "fpedats": pd.Timestamp("2004-12-31")})
    return pd.DataFrame(rows)


def _vendor_adjusted(q):
    """What `statsum_epsus` ships: today's shares (the splitter later splits 256x),
    rounded to cents -- 3.00 / 0.90 becomes 0.01 / 0.00."""
    a = q.copy()
    f = np.where(a["ticker"] == f"T{_SPLITTER:02d}", _FUTURE, 1.0)
    for c in ("meanest", "medest", "stdev"):
        a[c] = np.round(a[c] / f, 2)
    return a


def _link():
    return pd.DataFrame({"ticker": [f"T{i:02d}" for i in range(_N)],
                         "permno": [1000 + i for i in range(_N)],
                         "sdate": pd.Timestamp("1980-01-01"), "edate": pd.NaT, "score": 1})


def _adj():
    return pd.DataFrame({"ticker": [f"T{_SPLITTER:02d}"] * 2,
                         "spdates": [pd.Timestamp("1980-01-01"), pd.Timestamp("2015-01-15")],
                         "adj": [_FUTURE, 1.0]})


def _assert_splitter_reads_as_disagreement(d):
    """THE INVARIANT: the planted most-dispersed firm is present and scores at the
    disagreement end (rev_dispersion is negated: high = agreement)."""
    by = dict(zip(d["permno"], d["rev_dispersion"]))
    sp = by.get(1000 + _SPLITTER)
    assert sp is not None and np.isfinite(sp), "the future splitter was dropped"
    others = [v for k, v in by.items() if k != 1000 + _SPLITTER]
    assert sp < np.median(others), (
        f"future splitter scored {sp:.4f} vs median {np.median(others):.4f}: a split "
        f"that has not happened yet moved the signal")


def test_farm_dispersion_is_untouched_by_a_future_split():
    d = RV.derive(PIT.from_frames(_quoted_month(), _link(), _adj()))
    _assert_splitter_reads_as_disagreement(d)


def test_the_invariant_FAILS_on_the_leaky_adjusted_input():
    """The pre-2026-11-11 input (vendor-adjusted values), forced through derive by
    mislabelling it: the splitter reads 0.00 -- perfect agreement, the maximum."""
    leaky = PIT.from_frames(_vendor_adjusted(_quoted_month()), _link(), _adj())
    d = RV.derive(leaky)
    assert d.loc[d["permno"] == 1000 + _SPLITTER, "rev_dispersion"].iloc[0] == 0.0
    with pytest.raises(AssertionError):
        _assert_splitter_reads_as_disagreement(d)


def test_the_interim_0_25_guard_also_fails_the_invariant():
    """PR #94's first fix: NaN below an ADJUSTED $0.25. It drops the future
    splitter -- selection on the future in the other direction."""
    a = _vendor_adjusted(_quoted_month())
    guarded = a.assign(rev_dispersion=np.where((a["meanest"].abs() >= 0.25) & (a["stdev"] > 0),
                                               -a["stdev"] / a["meanest"].abs(), np.nan),
                       permno=[1000 + i for i in range(_N)])
    with pytest.raises(AssertionError, match="dropped"):
        _assert_splitter_reads_as_disagreement(guarded)


def test_a_magnitude_across_a_past_split_is_on_one_share_basis():
    """A 2:1 split between two months halves the quoted consensus; with IBES's own
    factors the revision is 0, not -50%."""
    q = pd.concat([_quoted_month().assign(statpers=pd.Timestamp("2004-05-20")),
                   _quoted_month()], ignore_index=True)
    t1 = (q["ticker"] == "T01") & (q["statpers"] == pd.Timestamp("2004-06-17"))
    q.loc[t1, ["meanest", "medest", "stdev"]] = q.loc[t1, ["meanest", "medest", "stdev"]] / 2.0
    adj = pd.concat([_adj(), pd.DataFrame({"ticker": ["T01", "T01"],
                                           "spdates": [pd.Timestamp("1980-01-01"),
                                                       pd.Timestamp("2004-06-10")],
                                           "adj": [2.0, 1.0]})], ignore_index=True)
    d = RV.derive(PIT.from_frames(q, _link(), adj))
    r = d.loc[(d["permno"] == 1001) & (d["statpers"] == pd.Timestamp("2004-06-17")), "rev_magnitude"]
    assert r.iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_derive_refuses_a_frame_that_does_not_declare_its_share_basis():
    f = _frame([(1, "2013-01-18", 5, 0, 0, 2.0, 0.05)]).drop(columns=["share_basis"])
    with pytest.raises(ValueError, match="share_basis"):
        RV.derive(f)


def test_derive_refuses_when_every_split_factor_is_unknown():
    f = _frame([(1, "2013-01-18", 5, 0, 0, 2.0, 0.05)]).assign(adj_factor=np.nan)
    with pytest.raises(RV.RevisionsUnavailable):
        RV.derive(f)


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
