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
