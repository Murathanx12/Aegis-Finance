"""T2 — the four night-job books' signals, on synthetic frames.

The point of every test here is a PIT rule. Each of the four signals has one
way to be silently wrong — trading a short-interest figure before it was
published, timing an insider cluster from the transaction date instead of the
filing, weighting a reference price with a turnover the name had not traded
yet, or counting a headline whose stamp is not the venue's own — and each of
those is a test rather than a comment.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from backend.services import book_signals as BS


# --------------------------------------------------------------------------
# BOOK A — short interest x turnover


def _si_panel(rows):
    """rows: (permno, datadate, si_ratio, turnover). observed_at is derived."""
    df = pd.DataFrame(rows, columns=["permno", "datadate", "si_ratio",
                                     "turnover_21d_w"])
    df["datadate"] = pd.to_datetime(df["datadate"])
    df["observed_at"] = BS.short_interest_panel_dir and (
        df["datadate"] + pd.Timedelta(days=14))
    return df


def test_the_composite_uses_only_prints_already_published():
    # Both prints settle before the decision; only the first has been PUBLISHED.
    panel = _si_panel([(i, "2020-01-15", 0.10 - i * 0.003, 0.05 + i * 0.003)
                       for i in range(30)]
                      + [(i, "2020-01-28", 0.99, 0.99) for i in range(30)])
    scores = BS.si_turnover_composite(panel, date(2020, 2, 1))
    assert len(scores) == 30
    # The 2020-01-28 print settles before the decision but publishes on
    # 2020-02-11. Had it been used, every name would carry si 0.99 and
    # turnover 0.99, every z would be 0, and the composite would be flat.
    assert max(abs(v) for v in scores.values()) > 0.1
    assert max(scores, key=scores.get) == 29


def test_the_composite_refuses_before_the_first_publication():
    panel = _si_panel([(i, "2020-01-15", 0.01, 0.10) for i in range(30)])
    with pytest.raises(BS.SignalUnavailable, match="PUBLISHED"):
        BS.si_turnover_composite(panel, date(2020, 1, 20))   # settled, not public


def test_the_composite_refuses_a_cross_section_too_thin_to_rank():
    panel = _si_panel([(i, "2020-01-15", 0.01, 0.10) for i in range(5)])
    with pytest.raises(BS.SignalUnavailable, match="cross-sectional z"):
        BS.si_turnover_composite(panel, date(2020, 3, 1))


def test_the_composite_buys_low_si_and_high_turnover():
    rows = [(i, "2020-01-15", 0.10 - i * 0.003, 0.05 + i * 0.003)
            for i in range(30)]
    scores = BS.si_turnover_composite(_si_panel(rows), date(2020, 3, 1))
    # permno 29 has the lowest SI and the highest turnover -> the highest score
    assert max(scores, key=scores.get) == 29
    assert min(scores, key=scores.get) == 0


def test_only_the_latest_published_print_per_name_is_used():
    panel = _si_panel([(i, "2020-01-15", 0.50, 0.01) for i in range(30)]
                      + [(i, "2020-02-15", 0.10 - i * 0.003, 0.05 + i * 0.003)
                         for i in range(30)])
    scores = BS.si_turnover_composite(panel, date(2020, 4, 1))
    assert max(scores, key=scores.get) == 29


# --------------------------------------------------------------------------
# BOOK B — insider cluster length


def _buys(rows):
    """rows: (symbol, cik, trans_date, filing_date)."""
    df = pd.DataFrame(rows, columns=["symbol", "insider_cik", "event_time_utc",
                                     "observed_at_utc"])
    for c in ("event_time_utc", "observed_at_utc"):
        df[c] = pd.to_datetime(df[c], utc=True)
    df["insider_is_officer"] = True
    df["insider_dollar_value"] = 1000.0
    return df


SESSIONS = pd.bdate_range("2020-01-01", "2020-03-31")


def test_a_four_day_cluster_is_measured_in_sessions_not_calendar_days():
    # Thu 2020-01-02 .. Wed 2020-01-08 is FOUR sessions apart (the weekend does
    # not count), which is the frontier bucket; six calendar days is not.
    rows = [("AAA", f"cik{i}", d, "2020-01-20")
            for i, d in enumerate(["2020-01-02", "2020-01-03", "2020-01-06",
                                   "2020-01-07", "2020-01-08"])]
    cl = BS.cluster_lengths(_buys(rows), sessions=SESSIONS)
    assert len(cl) == 1
    assert int(cl["span_days"].iloc[0]) == 4
    assert int(cl["n_insiders"].iloc[0]) == 5


def test_the_entry_date_is_the_LATEST_filing_not_the_first():
    rows = [("AAA", "cik1", "2020-01-02", "2020-01-06"),
            ("AAA", "cik2", "2020-01-03", "2020-01-31")]
    cl = BS.cluster_lengths(_buys(rows), sessions=SESSIONS)
    assert len(cl) == 1
    assert cl["entry_date"].iloc[0] == pd.Timestamp("2020-01-31")


def test_one_insider_buying_repeatedly_is_not_a_cluster():
    rows = [("AAA", "cik1", d, "2020-01-20")
            for d in ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]]
    assert BS.cluster_lengths(_buys(rows), sessions=SESSIONS).empty


def test_a_same_day_cluster_has_span_zero():
    rows = [("AAA", "cik1", "2020-01-02", "2020-01-06"),
            ("AAA", "cik2", "2020-01-02", "2020-01-06")]
    cl = BS.cluster_lengths(_buys(rows), sessions=SESSIONS)
    assert int(cl["span_days"].iloc[0]) == BS.SAME_DAY_SPAN


def test_a_gap_of_two_sessions_splits_one_run_into_two():
    rows = [("AAA", "cik1", "2020-01-02", "2020-01-20"),
            ("AAA", "cik2", "2020-01-03", "2020-01-20"),
            ("AAA", "cik3", "2020-01-09", "2020-01-20"),
            ("AAA", "cik4", "2020-01-10", "2020-01-20")]
    cl = BS.cluster_lengths(_buys(rows), sessions=SESSIONS)
    assert len(cl) == 2
    assert sorted(cl["span_days"]) == [1, 1]


def test_eligibility_fires_only_in_the_window_the_entry_date_lands_in():
    cl = pd.DataFrame([{"symbol": "AAA", "span_days": 4,
                        "entry_date": pd.Timestamp("2020-02-10")},
                       {"symbol": "BBB", "span_days": 4,
                        "entry_date": pd.Timestamp("2020-01-02")},
                       {"symbol": "CCC", "span_days": 0,
                        "entry_date": pd.Timestamp("2020-02-10")}])
    hit = BS.cluster_eligibility(cl, date(2020, 2, 28), window_days=31)
    assert hit == {"AAA": 1.0}
    same_day = BS.cluster_eligibility(cl, date(2020, 2, 28), spans=(0,),
                                      window_days=31)
    assert same_day == {"CCC": 1.0}


def test_a_cluster_whose_entry_date_is_in_the_future_never_fires():
    cl = pd.DataFrame([{"symbol": "AAA", "span_days": 4,
                        "entry_date": pd.Timestamp("2020-03-10")}])
    assert BS.cluster_eligibility(cl, date(2020, 2, 28)) == {}


# --------------------------------------------------------------------------
# BOOK C — the Grinblatt-Han overhang


def test_full_turnover_every_period_makes_the_reference_price_the_last_price():
    # V = 1 every session: the share bought yesterday is the only one still
    # held, so RP = P[-1] and the overhang is 0 by construction.
    p = [10.0, 11.0, 12.0, 13.0]
    assert BS.capital_gains_overhang(p, [1.0] * 4) == pytest.approx(0.0)


def test_a_price_above_its_reference_is_a_positive_overhang():
    p = [10.0] * 20 + [20.0]
    cgo = BS.capital_gains_overhang(p, [0.02] * 21)
    assert 0.0 < cgo < 1.0


def test_a_price_below_its_reference_is_a_negative_overhang():
    p = [20.0] * 20 + [10.0]
    assert BS.capital_gains_overhang(p, [0.02] * 21) < 0.0


def test_a_name_that_never_traded_has_no_reference_price():
    with pytest.raises(BS.SignalUnavailable, match="did not trade"):
        BS.capital_gains_overhang([10.0] * 5, [0.0] * 5)


def test_the_conditioner_gates_on_the_EVENT_SIGN_before_it_ranks():
    cgo = {"A": 0.9, "B": 0.8, "C": 0.7, "D": -0.5}
    signs = {"A": -1.0, "B": 1.0, "C": 1.0, "D": 1.0}
    out = BS.overhang_conditioned_ranks(cgo, signs)
    # A has the largest overhang and BAD news: it must not be in the book.
    assert "A" not in out
    assert set(out) <= {"B", "C", "D"}
    assert "B" in out                               # top of the good-news set


def test_an_empty_eligible_set_refuses_rather_than_returning_nothing():
    with pytest.raises(BS.SignalUnavailable, match="empty eligible set"):
        BS.overhang_conditioned_ranks({"A": 0.5}, {"A": -1.0})


# --------------------------------------------------------------------------
# BOOK D — the abstention confidence


def test_the_confidence_z_is_signed_not_absolute():
    z = BS.confidence_z({"A": -1.0, "B": 0.0, "C": 1.0})
    assert z["A"] < 0 < z["C"]


def test_a_one_name_cross_section_has_no_z():
    with pytest.raises(BS.SignalUnavailable, match="at least two"):
        BS.confidence_z({"A": 1.0})


# --------------------------------------------------------------------------
# LANE D — the first-hour placeholder


def _row(seen_et: str, *, grade: str = "native_stamp", tickers=("AAA",)):
    from zoneinfo import ZoneInfo
    t = datetime.fromisoformat(seen_et).replace(tzinfo=ZoneInfo("America/New_York"))
    return {"pit_grade": grade, "tickers": list(tickers),
            "first_seen_utc": t.astimezone(timezone.utc).isoformat()}


def test_only_headlines_first_seen_inside_the_first_hour_count():
    rows = [_row("2026-09-11T09:45:00"),                       # in
            _row("2026-09-11T11:00:00", tickers=("BBB",)),     # after the hour
            _row("2026-09-11T09:00:00", tickers=("CCC",))]     # pre-open
    assert BS.first_hour_headlines(rows, date(2026, 9, 11)) == {"AAA": 1.0}


def test_a_stamp_that_is_not_the_venue_s_own_is_not_a_time_we_may_act_on():
    rows = [_row("2026-09-11T09:45:00", grade="inferred_from_page")]
    assert BS.first_hour_headlines(rows, date(2026, 9, 11)) == {}


def test_the_window_boundaries_are_inclusive_on_both_ends():
    rows = [_row("2026-09-11T09:30:00"), _row("2026-09-11T10:30:00",
                                              tickers=("BBB",))]
    got = BS.first_hour_headlines(rows, date(2026, 9, 11))
    assert got == {"AAA": 1.0, "BBB": 1.0}


def test_a_headline_on_another_session_does_not_leak_in():
    rows = [_row("2026-09-10T09:45:00")]
    assert BS.first_hour_headlines(rows, date(2026, 9, 11)) == {}


def test_a_multi_ticker_headline_counts_for_each_of_its_names():
    rows = [_row("2026-09-11T09:45:00", tickers=("AAA", "BBB"))]
    assert BS.first_hour_headlines(rows, date(2026, 9, 11)) == {"AAA": 1.0,
                                                                "BBB": 1.0}


def test_an_absent_corpus_day_reads_as_no_file(tmp_path):
    assert BS.load_news_rows(date(2026, 9, 11), corpus_dir=tmp_path) == []


# --------------------------------------------------------------------------
# the registry, and how `book_cadence` reaches it


def test_every_registry_adapter_takes_the_same_keywords():
    import inspect
    for name, fn in BS.REGISTRY.items():
        params = inspect.signature(fn).parameters
        assert {"book", "bars", "symbols", "asof"} <= set(params), name


def test_an_unregistered_name_refuses_by_name():
    with pytest.raises(BS.SignalUnavailable, match="not a registered book signal"):
        BS.compute("a_signal_nobody_wrote", book=None, bars=None, symbols=[],
                   asof=date.today())


def test_book_cadence_turns_a_missing_panel_into_a_named_refusal(monkeypatch):
    from backend.services import book_cadence as BC
    from backend.tests.book_helpers import make_strategy, synthetic_bars
    from backend.strategy.contract import Signal

    s = make_strategy().with_(
        signal=Signal(name="short_interest_low_x_turnover_high", direction=1))
    book = BC.PB.PaperBook(book_id="book:test", strategy=s, cadence="monthly",
                           created_utc="2026-09-12T00:00:00+00:00",
                           origin="night_job")
    monkeypatch.setattr(BS, "load_short_interest",
                        lambda *a, **k: (_ for _ in ()).throw(
                            BS.SignalUnavailable("no panel on this machine")))
    with pytest.raises(BC.UnsupportedSignal, match="no panel on this machine"):
        BC._signal_frame(book, synthetic_bars(), ["AAA", "BBB"], date.today())


def test_the_refusal_message_lists_the_registered_signals_too():
    from backend.services import book_cadence as BC
    from backend.tests.book_helpers import make_strategy, synthetic_bars
    from backend.strategy.contract import Signal

    s = make_strategy().with_(signal=Signal(name="not_a_signal", direction=1))
    book = BC.PB.PaperBook(book_id="book:test", strategy=s, cadence="monthly",
                           created_utc="2026-09-12T00:00:00+00:00",
                           origin="night_job")
    with pytest.raises(BC.UnsupportedSignal) as exc:
        BC._signal_frame(book, synthetic_bars(), ["AAA"], date.today())
    for name in BS.REGISTRY:
        assert name in str(exc.value)


# --------------------------------------------------------------------------
# the twin every long-only construction is owed


def test_a_passthrough_book_is_long_only_and_earns_a_beta_matched_twin():
    """Lane B's insider-cluster book is the programme's only `passthrough`
    book, and it came out with one twin where its pre-registration names two:
    `LONG_ONLY_RULES` was a list of the rules that existed when it was written.
    `decide_weights` produces no negative weight under any rule, so a
    passthrough book is as long-only as a top-k one."""
    from backend.services import paper_books as PB
    from backend.strategy.contract import Construction
    from backend.tests.book_helpers import make_strategy, synthetic_bars

    s = make_strategy().with_(
        construction=Construction(rule="passthrough", k=3, weighting="ew",
                                  max_single_name=0.34))
    assert PB.is_long_only(s)
    twins = PB.make_twins(s, cadence="monthly", bars=synthetic_bars(),
                          asof=date.today())
    kinds = {t.strategy.engine_params["twin"]["kind"] for t in twins}
    assert kinds == {"random_universe", "beta_matched"}


# --------------------------------------------------------------------------
# BOOKS E, F, G — the three characteristics that were already on disk
#
# Every test here is on a SYNTHETIC frame. None of them reads the JKP or IBES
# parquet: a unit test that needs a 1 GB panel is a test nobody runs twice.


def _jkp_frame(n=30, *, qmj=True, seas=True, near=False):
    """One month of the JKP characteristic panel, synthetically."""
    rows = {"permno": list(range(1, n + 1))}
    if qmj:
        rows["qmj"] = [float(i) for i in range(n)]
        rows["qmj_prof"] = [float(n - i) for i in range(n)]
    if seas:
        rows["seas_11_15an"] = [float(i) for i in range(n)]
        rows["seas_16_20an"] = [float(i) for i in range(n)]
    if near:
        rows["seas_2_5an"] = [float(n - i) for i in range(n)]
    return pd.DataFrame(rows)


def _ibes_frame(n=30, *, numest=5):
    """One month of the IBES consensus, synthetically. Dispersion rises with i."""
    return pd.DataFrame({
        "permno": list(range(1, n + 1)),
        "stdev": [0.01 * (i + 1) for i in range(n)],
        "meanest": [1.0] * n,
        "numest": [numest] * n,
    })


def test_qmj_rank_returns_the_top_tercile_and_the_junk_leg_is_its_mirror():
    f = _jkp_frame(30)
    top = BS.qmj_rank(f)
    bottom = BS.qmj_rank(f, side="bottom")
    assert top and bottom
    # The top tercile holds the HIGHEST qmj and the bottom holds the lowest;
    # the junk falsifier is the same cut read from the other end, not a second
    # threshold that could be tuned.
    assert min(top.values()) > max(bottom.values())
    assert set(top) & set(bottom) == set()
    assert max(top.values()) == 29.0 and min(bottom.values()) == 0.0


def test_qmj_rank_refuses_by_name_when_the_column_is_absent():
    f = _jkp_frame(30, qmj=False)
    with pytest.raises(BS.SignalUnavailable, match="no 'qmj' column"):
        BS.qmj_rank(f)


def test_qmj_rank_refuses_a_cross_section_too_thin_to_cut():
    with pytest.raises(BS.SignalUnavailable, match="cut of the survivors"):
        BS.qmj_rank(_jkp_frame(5))


def test_qmj_rank_reads_the_named_diagnostic_column_without_changing_the_book():
    """TRIAL-DRAFT-E section 3 lists a `qmj_prof`-only leg as reported and never
    deciding. It must be reachable and it must NOT be what the default call
    returns, or the diagnostic and the book would be the same object."""
    f = _jkp_frame(30)
    book = BS.qmj_rank(f)
    diag = BS.qmj_rank(f, column="qmj_prof")
    assert set(book) != set(diag)


def test_seasonality_requires_every_named_column_on_every_name():
    """A name carrying only the 11-15 lag is DROPPED, not averaged over what it
    has: a one-column z and a two-column z mean different things, and listing
    age is exactly what a twenty-year lag selects on."""
    f = _jkp_frame(30)
    f.loc[f["permno"] <= 5, "seas_16_20an"] = float("nan")
    got = BS.seasonality_score(f, min_names=5)
    assert set(got) <= set(range(6, 31))


def test_seasonality_refuses_when_too_few_names_carry_both_columns():
    f = _jkp_frame(30)
    f.loc[f["permno"] > 3, "seas_16_20an"] = float("nan")
    with pytest.raises(BS.SignalUnavailable, match="carried ALL of"):
        BS.seasonality_score(f)


def test_seasonality_composite_is_the_mean_of_the_two_column_z_scores():
    """Two columns that disagree perfectly cancel to a flat score, so the
    composite is genuinely averaging and not reading the first column."""
    f = _jkp_frame(30)
    f["seas_16_20an"] = [float(29 - i) for i in range(30)]
    got = BS.seasonality_score(f, tercile=0.0)
    assert len(got) == 30
    assert max(abs(v) for v in got.values()) < 1e-9


def test_seasonality_near_lags_are_a_different_book_and_say_so():
    f = _jkp_frame(30, near=True)
    far = BS.seasonality_score(f)
    near = BS.seasonality_score(f, columns=BS.SEASONALITY_COLUMNS_NEAR)
    # `seas_2_5an` is built decreasing here, so the two must not select the
    # same names -- the diagnostic is a different read, which is why
    # TRIAL-DRAFT-F section 8 forbids it becoming primary.
    assert set(far) & set(near) == set()


def test_dispersion_holds_the_LOW_leg_by_default():
    got = BS.forecast_dispersion(_ibes_frame(30))
    assert got
    # Low disagreement is the held leg; the highest-dispersion names must not
    # be in it, because section 8 forbids shorting them and the book avoids them.
    assert max(got.values()) < 0.30
    assert 30 not in got and 1 in got


def test_dispersion_drops_a_lone_analyst_and_a_pair():
    """`numest >= 3` is frozen: a two-analyst standard deviation is one pairwise
    difference and a dispersion built on it is a noise measurement."""
    f = _ibes_frame(30, numest=2)
    with pytest.raises(BS.SignalUnavailable, match="numest >= 3"):
        BS.forecast_dispersion(f)


def test_dispersion_drops_a_zero_consensus_rather_than_clipping_it():
    f = _ibes_frame(30)
    f.loc[f["permno"] <= 4, "meanest"] = 0.0
    got = BS.forecast_dispersion(f, min_names=5, tercile=0.0)
    assert set(got) == set(range(5, 31))


def test_dispersion_refuses_by_name_when_a_column_is_missing():
    f = _ibes_frame(30).drop(columns=["stdev"])
    with pytest.raises(BS.SignalUnavailable, match="no 'stdev' column"):
        BS.forecast_dispersion(f)


def test_one_tercile_implementation_serves_book_c_and_the_three_new_books():
    """`overhang_conditioned_ranks` was Book C's frozen cut and now delegates to
    `_tercile_side`. Its behaviour must be unchanged -- a control that cuts its
    tercile with a second implementation of the quantile is not cutting the same
    tercile, which is the whole reason the two were merged."""
    import numpy as np

    cgo = {i: float(i) for i in range(30)}
    sign = {i: 1.0 for i in range(30)}
    top = BS.overhang_conditioned_ranks(cgo, sign)
    expected_cut = float(np.quantile(list(cgo.values()), 2.0 / 3.0))
    assert top == {k: v for k, v in cgo.items() if v >= expected_cut}
    bottom = BS.overhang_conditioned_ranks(cgo, sign, side="bottom")
    assert bottom == {k: v for k, v in cgo.items()
                      if v <= float(np.quantile(list(cgo.values()), 1.0 / 3.0))}


# ---------------------------------------------------------------------------
# TRIAL-DRAFT-G Amendment 1 — the denominator becomes PRICE (chunk 15b)
# ---------------------------------------------------------------------------


def test_the_default_scale_is_v0_and_is_byte_identical_to_it():
    """The amendment must not be able to change v0's number by existing."""
    f = _ibes_frame(30)
    assert BS.forecast_dispersion(f) == BS.forecast_dispersion(f, scale="meanest")


def test_price_scaling_divides_by_price_and_not_by_forecast_eps():
    f = _ibes_frame(30)
    f["meanest"] = [0.5] * 30          # halving EPS would DOUBLE v0's score
    f["price"] = [20.0] * 30
    got = BS.forecast_dispersion(f, scale="price", tercile=0.0, min_names=5)
    # stdev_i = 0.01*(i+1), price = 20 -> score = 0.0005*(i+1)
    assert got[1] == pytest.approx(0.01 / 20.0)
    assert got[30] == pytest.approx(0.30 / 20.0)
    v0 = BS.forecast_dispersion(f, tercile=0.0, min_names=5)
    assert v0[1] == pytest.approx(0.01 / 0.5), "v0 still divides by meanest"


def test_the_earnings_level_channel_is_exactly_what_price_scaling_removes():
    """The amendment's whole claim, as an arithmetic fact rather than prose.

    Two names with IDENTICAL forecast uncertainty per dollar of price, one with
    near-zero consensus EPS. Under v0 the near-zero-EPS name looks like the most
    disagreed-about name in the market and is AVOIDED; under the amendment the
    two are ranked together, because neither is more uncertain per dollar.
    """
    f = pd.DataFrame({
        "permno": [1, 2, 3, 4, 5, 6],
        "stdev": [0.10] * 6,
        "meanest": [5.0, 5.0, 5.0, 5.0, 5.0, 0.01],   # name 6: EPS near zero
        "numest": [5] * 6,
        "price": [50.0] * 6,
    })
    v0 = BS.forecast_dispersion(f, tercile=0.0, min_names=5)
    amended = BS.forecast_dispersion(f, scale="price", tercile=0.0, min_names=5)
    assert v0[6] == pytest.approx(10.0), "the EPS level, not disagreement"
    assert v0[6] > 100 * v0[1]
    assert amended[6] == amended[1] == pytest.approx(0.002)


def test_the_covered_band_is_v0s_under_both_scales():
    """`meanest != 0` stays a MEMBERSHIP test even when it is not the divisor.

    If it did not, the amendment would rank a different set of names and the two
    reads would differ by coverage as well as by construction -- and neither
    number would be comparable to the other.
    """
    f = _ibes_frame(30)
    f["price"] = [40.0] * 30
    f.loc[f["permno"] <= 4, "meanest"] = 0.0
    got = BS.forecast_dispersion(f, scale="price", min_names=5, tercile=0.0)
    assert set(got) == set(range(5, 31)), "the same four names v0 drops"


def test_a_zero_or_missing_price_is_dropped_not_clipped():
    f = _ibes_frame(30)
    f["price"] = [40.0] * 30
    f.loc[f["permno"] <= 3, "price"] = 0.0
    got = BS.forecast_dispersion(f, scale="price", min_names=5, tercile=0.0)
    assert set(got) == set(range(4, 31))


def test_price_scaling_refuses_by_name_when_the_price_column_is_absent():
    with pytest.raises(BS.SignalUnavailable, match="no 'price' column"):
        BS.forecast_dispersion(_ibes_frame(30), scale="price")


def test_an_unknown_scale_is_refused_and_never_falls_back_to_v0():
    """A silent fallback would publish v0's number under the amendment's name."""
    f = _ibes_frame(30)
    with pytest.raises(BS.SignalUnavailable, match="unknown dispersion scale"):
        BS.forecast_dispersion(f, scale="ebitda")
    assert BS.DISPERSION_SCALES == ("meanest", "price")
