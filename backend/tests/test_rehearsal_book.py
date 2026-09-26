"""rehearsal_book: the Bloomberg dress-rehearsal selection and its declared numbers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.services import rehearsal_book as RB

DEC = pd.Timestamp("2026-09-27")          # the freeze this module was written for (a Sunday)


def _ek(rows):
    return pd.DataFrame(rows, columns=["ticker", "filing_date", "items_joined"])


def _file_end(dec=DEC):
    # any 2.02-free 8-K a few days before the decision keeps the file fresh
    return ("ZZZZ", str((dec - pd.Timedelta(days=3)).date()), "8.01")


def test_the_window_is_21_sessions_from_the_next_business_day():
    s = RB.sessions_after(DEC, RB.WINDOW_SESSIONS)
    assert len(s) == 21 and s[0] == pd.Timestamp("2026-09-28") and s[-1] == pd.Timestamp(RB.CHECK_DATE)


def test_earnings_estimate_is_last_202_plus_91_days_and_qualifies_in_window():
    ek = _ek([("AAA", "2026-07-22", "2.02,9.01"), ("AAA", "2025-10-21", "2.02"),
              ("BBB", "2026-08-20", "2.02"),                       # est 11-19: after the window
              ("CCC", "2026-07-22", "5.02"),                       # no 2.02 at all
              _file_end()])
    e = RB.earnings_estimates(ek, ["AAA", "BBB", "CCC"], DEC)
    assert e["AAA"]["status"] == "IN_WINDOW" and e["AAA"]["estimate"] == "2026-10-21"
    assert e["AAA"]["last_202"] == "2026-07-22" and "8-K item 2.02" in e["AAA"]["source"]
    assert e["AAA"]["yoy_cross_check"] == "2026-10-20"
    assert e["BBB"]["status"] == "OUTSIDE_WINDOW"
    assert e["CCC"]["status"] == "EARNINGS_UNKNOWN"


def test_a_print_that_may_sit_in_the_file_gap_is_unknown():
    # cadence says 09-28, but the same quarter last year printed 09-24: before the window
    ek = _ek([("CNX", "2026-06-29", "2.02"), ("CNX", "2025-09-25", "2.02"), _file_end()])
    e = RB.earnings_estimates(ek, ["CNX"], DEC)
    assert e["CNX"]["status"] == "EARNINGS_UNKNOWN"
    # and last year's same quarter after the window moves a cadence-in-window name out
    ek = _ek([("NVX", "2026-07-23", "2.02"), ("NVX", "2025-10-30", "2.02"), _file_end()])
    assert RB.earnings_estimates(ek, ["NVX"], DEC)["NVX"]["status"] == "OUTSIDE_WINDOW"


def test_a_stale_8k_file_or_a_future_filing_never_qualifies():
    stale = _ek([("AAA", "2026-07-22", "2.02")])                   # file ends 67 days back
    assert RB.earnings_estimates(stale, ["AAA"], DEC)["AAA"]["status"] == "EARNINGS_UNKNOWN"
    # a 2.02 filed AFTER the decision is not seen: the July one decides
    ek = _ek([("AAA", "2026-07-22", "2.02"), ("AAA", "2026-10-01", "2.02"), _file_end()])
    assert RB.earnings_estimates(ek, ["AAA"], DEC)["AAA"]["last_202"] == "2026-07-22"


def _cands():
    idx = ["A", "B", "C", "D", "E", "F"]
    return pd.DataFrame({
        "sigma63": [0.06, 0.05, 0.04, 0.03, 0.02, 0.01],
        "fund_score": [0.9, 0.2, 0.8, 0.7, 0.6, 0.95],
        "mcap": [1e9, 1e9, 1e9, 5e10, 1e9, 1e9],
        "earnings_status": ["IN_WINDOW", "IN_WINDOW", "IN_WINDOW", "IN_WINDOW",
                            "EARNINGS_UNKNOWN", "IN_WINDOW"],
        "is_semi": [True, False, True, False, False, True]}, index=idx)


def test_rank_filters_size_fundamentals_and_earnings_then_orders_by_predicted_move():
    ranked, counts = RB.rank_candidates(_cands())
    # D is a large cap; B is below the fundamentals median; E has no known print
    assert list(ranked.index) == ["A", "C", "F"]
    assert ranked["pred_move"].is_monotonic_decreasing
    assert ranked.loc["A", "pred_move"] == pytest.approx(0.06 * math.sqrt(21) * math.sqrt(2 / math.pi))
    assert counts["earnings_in_window"] == 3


def test_pick_caps_semis_and_skips_a_correlated_pair():
    ranked = pd.DataFrame({"is_semi": [True, True, True, False, False]},
                          index=["S1", "S2", "S3", "N1", "N2"])
    corr = pd.DataFrame(0.1, index=ranked.index, columns=ranked.index)
    corr.loc["N1", "S1"] = corr.loc["S1", "N1"] = 0.9
    picks, skipped = RB.pick(ranked, corr, k=3, max_semis=2)
    assert picks == ["S1", "S2", "N2"]
    assert {s["symbol"] for s in skipped} == {"S3", "N1"}
    nxt, _ = RB.pick(ranked, corr, k=2, max_semis=2, exclude=picks)
    assert nxt == ["S3", "N1"]


def _closes(n=140, seed=7):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("2026-01-02", periods=n)
    spy = rng.normal(0, 0.01, n)
    iwm = spy + rng.normal(0, 0.005, n)
    smh = spy + rng.normal(0, 0.01, n)
    a = rng.normal(0, 0.02, n)
    df = pd.DataFrame({"SPY": spy, "IWM": iwm, "SMH": smh, "A": a, "B": 2 * a}, index=d)
    return 100 * np.exp(df.cumsum())


def test_book_sigma_uses_sigma63_and_realised_correlation():
    closes = _closes()
    sig = np.log(closes).diff().iloc[-63:].std(ddof=1)
    st = RB.book_stats({"A": 0.5, "B": 0.5}, closes, sigma=sig)
    # A and B are perfectly correlated: the book sigma is the weighted sum
    assert st["sigma_daily"] == pytest.approx(0.5 * sig["A"] + 0.5 * sig["B"], rel=1e-3)
    assert st["sigma_21"] == pytest.approx(st["sigma_daily"] * math.sqrt(21))
    assert st["avg_pairwise_rho_63"] == pytest.approx(1.0, abs=1e-3)
    assert set(st["factor_exposure"]["multi"]) >= {"SPY", "IWM-SPY", "SMH-SPY"}
    # an SPY-only book has zero relative sigma and beta 1 to SPY
    st2 = RB.book_stats({"SPY": 1.0}, closes)
    assert st2["rel_sigma_daily_vs_spy"] == pytest.approx(0.0, abs=1e-9)
    assert st2["factor_exposure"]["univariate"]["SPY"] == pytest.approx(1.0)


def test_the_stop_is_a_z_score_not_a_percent():
    s = RB.stop_rule_book(0.02)
    assert s["z"] == -2.0 and "not a percent" in s["rule"]
    assert s["threshold_as_return_by_session"]["21"] == pytest.approx(-2 * 0.02 * math.sqrt(21), abs=1e-4)


def test_checks_are_the_three_verbatim_lines():
    assert RB.CHECKS_2026_10_26 == ("move-size rank correlation >= 0.3",
                                    "realised factor exposure within +/-0.3 of declared",
                                    "fills vs plan")
    assert RB.LICENCE_SENTENCE == "PRODUCT_EXPERIMENT; nothing here is a claim."


def _facts(rows):
    return pd.DataFrame(rows, columns=["ticker", "fact", "filed", "end", "period_days", "val"])


def test_fundamentals_proxy_ignores_roe_on_negative_equity_and_future_filings():
    rows = []
    for t, eq, ni in (("GOOD", 100.0, 20.0), ("DEFICIT", -50.0, -30.0), ("MID", 100.0, 5.0)):
        rows += [(t, "assets", "2026-05-01", "2026-03-31", np.nan, 400.0),
                 (t, "equity", "2026-05-01", "2026-03-31", np.nan, eq),
                 (t, "net_income", "2026-05-01", "2025-12-31", 365, ni),
                 (t, "operating_income", "2026-05-01", "2025-12-31", 365, ni * 1.5),
                 (t, "debt", "2026-05-01", "2026-03-31", np.nan, 50.0),
                 (t, "revenue", "2026-05-01", "2025-12-31", 365, 300.0),
                 (t, "cogs", "2026-05-01", "2025-12-31", 365, 200.0)]
    rows.append(("MID", "net_income", "2026-09-26", "2026-06-30", 365, 999.0))   # after the freeze
    f = RB.fundamentals_composite(_facts(rows), DEC, ["GOOD", "DEFICIT", "MID"])
    assert np.isnan(f.loc["DEFICIT", "ni_be"]) and np.isnan(f.loc["DEFICIT", "ope_be"])
    assert f.loc["MID", "ni_be"] == pytest.approx(0.05)
    assert f.loc["GOOD", "fund_score"] > f.loc["MID", "fund_score"]


def test_latest_shares_uses_filed_plus_two_days():
    f = _facts([("AAA", "shares", "2026-08-01", "2026-06-30", np.nan, 10.0),
                ("AAA", "shares", "2026-09-26", "2026-09-20", np.nan, 99.0)])
    assert RB.latest_shares(f, DEC)["AAA"] == 10.0


def test_core_satellite_tracking_error_is_the_satellite_times_the_sleeve_gap():
    closes = _closes(300)
    te = RB.core_satellite_te(["SPY"], closes)
    assert te["tracking_error_ann"] == pytest.approx(0.0, abs=1e-12)
    te = RB.core_satellite_te(["A", "B"], closes)
    assert te["tracking_error_ann"] == pytest.approx(0.2 * te["sleeve_minus_spy_sigma_ann"])


def test_spearman_needs_three_pairs():
    assert RB.spearman([1, 2], [1, 2]) is None
    assert RB.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert RB.spearman([1, 2, 3, np.nan], [3, 2, 1, 5]) == pytest.approx(-1.0)


def test_semis_flag_uses_gics_then_the_smh_correlation():
    f = RB.semis_flags(["NVX", "SW", "NEW1", "NEW2"], gind_by_symbol={"NVX": "453010", "SW": "451030"},
                       smh_corr=pd.Series({"NEW1": 0.75, "NEW2": 0.2}))
    assert list(f["is_semi"]) == [True, False, True, False]
