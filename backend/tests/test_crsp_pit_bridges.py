"""Offline tests for the round-2 CRSP point-in-time bridges (2026-09-30).

Each test pins a TIMING rule: an input dated after the decision date, or before
its publication lag has run, must never reach a column. Synthetic data only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import crsp_pit_bridges as PB

T = pd.Timestamp


def _keys(dates, permnos):
    rows = [(T(d), float(p)) for d in dates for p in permnos]
    return pd.DataFrame(rows, columns=["date", "permno"])


# ── short interest ─────────────────────────────────────────────────────────

def _si(datadates, shortint, permno=1):
    n = len(datadates)
    return pd.DataFrame({"permno": permno, "datadate": pd.to_datetime(datadates), "shortint": shortint,
                         "shortintadj": shortint, "shares_outstanding": [1e6] * n, "turnover_21d": [0.21] * n})


def test_si_print_is_not_used_before_its_publication_lag():
    pr = PB.si_prints(_si(["2010-01-15"], [5000.0]))
    assert pr["available"].iloc[0] == T("2010-01-15") + pd.Timedelta(days=PB.SI_LAG_DAYS)
    k = _keys(["2010-01-29", "2010-02-10", "2010-02-26"], [1])
    got = PB.si_panel(k, pr)
    assert np.isnan(got["dtc"].iloc[0])                  # 14 days after settlement: not public yet
    assert got["dtc"].iloc[1] == pytest.approx(0.5)      # 26 days = 2010-02-10: usable on that date
    k2 = _keys(["2010-02-09"], [1])
    assert np.isnan(PB.si_panel(k2, pr)["dtc"].iloc[0])  # one day earlier: not yet
    assert np.isfinite(got["dtc"].iloc[2])


def test_si_dtc_is_on_one_share_basis_and_goes_stale():
    pr = PB.si_prints(_si(["2010-01-15"], [10_000.0]))
    # 21-session volume = 0.21 x 1e6 = 210,000 shares -> 10,000 / day -> dtc 1.0
    k = _keys(["2010-02-26", "2010-05-28"], [1])
    got = PB.si_panel(k, pr)
    assert got["dtc"].iloc[0] == pytest.approx(1.0)
    assert np.isnan(got["dtc"].iloc[1])                  # > SI_STALE_DAYS after availability


def test_si_change_uses_the_print_known_91_days_earlier():
    pr = PB.si_prints(_si(["2010-01-15", "2010-04-15"], [999.0, 1999.0]))
    k = _keys(["2010-05-28"], [1])
    got = PB.si_panel(k, pr)
    assert got["si_chg_3m"].iloc[0] == pytest.approx(np.log(2000.0 / 1000.0))


# ── dated links ────────────────────────────────────────────────────────────

def test_dated_link_uses_the_row_active_on_the_event_date_and_drops_the_rest():
    link = pd.DataFrame({"gvkey": ["A", "A"], "permno": [10, 20],
                         "linkdt": ["2000-01-01", "2005-01-01"], "linkenddt": ["2004-12-31", None]})
    ev = pd.DataFrame({"gvkey": ["A", "A", "A"], "d": pd.to_datetime(["2003-06-30", "2010-06-30", "1999-06-30"])})
    out, meta = PB.dated_link(ev, link, key="gvkey", day_col="d")
    assert dict(zip(out["d"], out["permno"])) == {T("2003-06-30"): 10, T("2010-06-30"): 20}
    assert meta["rows_in"] == 3 and meta["rows_linked"] == 2


# ── 13F ────────────────────────────────────────────────────────────────────

def _f13(rows):
    return pd.DataFrame(rows, columns=["fdate", "rdate", "mgrno", "cusip", "shares"])


def test_f13_counts_only_reports_for_the_vintage_quarter():
    r = PB.f13_fresh(_f13([("2010-06-30", "2010-06-30", 1, "AAAA1111", 10),
                           ("2010-06-30", "2010-03-31", 2, "AAAA1111", 10),     # stale carry-forward
                           ("2010-06-30", "2010-06-30", 3, "AAAA1111", 0)]))    # zero shares
    assert list(r["mgrno"]) == [1]


def test_f13_initiations_and_concentration():
    prev = PB.f13_fresh(_f13([("2010-03-31", "2010-03-31", 1, "B0000001", 5),
                              ("2010-03-31", "2010-03-31", 2, "C0000001", 5)]))
    cur_rows = [("2010-06-30", "2010-06-30", 1, "A0000001", 5),      # mgr 1 reported last q: initiation
                ("2010-06-30", "2010-06-30", 1, "B0000001", 5),      # held before: not new
                ("2010-06-30", "2010-06-30", 9, "A0000001", 5)]      # mgr 9 did not report last q
    for i in range(30):                                              # mgr 2 holds 31 names: not concentrated
        cur_rows.append(("2010-06-30", "2010-06-30", 2, f"Z{i:07d}", 5))
    cur_rows.append(("2010-06-30", "2010-06-30", 2, "A0000001", 5))
    cur = PB.f13_fresh(_f13(cur_rows))
    st = PB.f13_quarter_stats(cur, prev).set_index("cusip")
    assert st.loc["A0000001", "n_inst"] == 3
    assert st.loc["A0000001", "n_init"] == 2                         # managers 1 and 2
    assert st.loc["A0000001", "n_conc_init"] == 0                    # mgr 1 holds 2 names (< 3), mgr 2 holds 31


def test_f13_quarter_is_not_known_before_the_filing_deadline():
    q = pd.DataFrame({"permno": [7, 7], "rdate": pd.to_datetime(["2009-12-31", "2010-03-31"]),
                      "n_inst": [10, 20], "n_init": [0, 1], "n_conc_init": [0, 0]})
    b = PB.f13_breadth(q)
    row = b[b["rdate"] == T("2010-03-31")].iloc[0]
    assert row["inst_breadth_chg"] == pytest.approx(np.log(2.0))
    assert row["available"] > T("2010-03-31") + pd.Timedelta(days=PB.F13_LAG_DAYS)
    k = _keys(["2010-04-30", "2010-05-14", "2010-05-28"], [7])
    got = PB.asof_panel(k, b, ["inst_breadth_chg"], on="available", age_from="rdate",
                        max_age_days=PB.F13_MAX_AGE_DAYS)["inst_breadth_chg"].to_numpy()
    assert np.isnan(got[0]) or got[0] != pytest.approx(np.log(2.0))  # Q1 not public on 04-30
    assert got[1] != pytest.approx(np.log(2.0))                      # nor on 05-14 (deadline 05-15)
    assert got[2] == pytest.approx(np.log(2.0))


# ── 8-K ────────────────────────────────────────────────────────────────────

def test_8k_after_close_is_used_from_the_next_business_day_only():
    ek = pd.DataFrame({"permno": [5.0], "acceptance_datetime": ["2015-03-02T22:30:00Z"],   # 17:30 New York
                       "filing_date": ["2015-03-02"], "items_joined": ["1.01|9.01"]})
    ev = PB.eightk_events(ek)
    assert ev["day"].iloc[0] == T("2015-03-02") and ev["usable"].iloc[0] == T("2015-03-03")
    p = PB.eightk_panel(ev, [T("2015-03-02"), T("2015-03-03")])
    assert list(p["date"]) == [T("2015-03-03")]
    assert p["n101_90"].iloc[0] == 1.0 and p["n701_90"].iloc[0] == 0.0


def test_8k_utc_acceptance_before_midnight_ny_is_the_ny_day():
    ek = pd.DataFrame({"permno": [5.0], "acceptance_datetime": ["2015-03-03T03:00:00Z"],   # 22:00 NY on 03-02
                       "filing_date": ["2015-03-03"], "items_joined": ["5.02"]})
    ev = PB.eightk_events(ek)
    assert ev["day"].iloc[0] == T("2015-03-02")


# ── analyst timing ─────────────────────────────────────────────────────────

def test_first_mover_depends_only_on_earlier_raises():
    r = pd.DataFrame({"permno": [1, 1, 1, 1, 1], "day": pd.to_datetime(
        ["2010-01-01", "2010-01-20", "2010-03-01", "2010-03-01", "2010-03-20"])})
    fm = PB.first_movers(r)
    assert list(fm) == [True, False, True, True, False]
    # adding a later raise never changes an earlier flag (no look-ahead)
    r2 = pd.concat([r, pd.DataFrame({"permno": [1], "day": [T("2010-02-25")]})], ignore_index=True)
    fm2 = PB.first_movers(r2)
    assert list(fm2[:2]) == [True, False]
    assert fm2[5] and not fm2[2] and not fm2[3]                      # 02-25 is new; 03-01 now follows it


def _daily(n=200, permno=1, start="2010-01-04", jump_at=None):
    d = pd.bdate_range(start, periods=n)
    r = np.full(n, 0.001)
    if jump_at is not None:
        r[jump_at] = 0.5
    return pd.DataFrame({"permno": permno, "date": d, "ret": r}), pd.Series(0.0, index=d)


def test_lead_window_ends_before_the_event_day():
    dly, mkt = _daily(jump_at=100)
    ev = pd.DataFrame({"permno": [1], "day": [dly["date"].iloc[100]], "sign": [1]})
    pc = PB.price_context(ev, dly, mkt)
    assert pc["ret10"].iloc[0] == pytest.approx(1.001 ** 10 - 1)     # the +50% event-day move is excluded
    assert pc["res_day"].iloc[0] == dly["date"].iloc[100 + PB.EXC_SESSIONS]


def test_skill_counts_a_raise_only_after_it_resolves():
    days = pd.bdate_range("2010-01-04", periods=30)
    ev = pd.DataFrame({"permno": 1, "broker": "B", "usable": days, "sign": 1, "ret10": -0.01, "sig10": 0.05,
                       "exc63": 0.02, "res_day": T("2010-07-01"), "first_mover": False})
    ev2 = pd.concat([ev, pd.DataFrame({"permno": [2], "broker": ["B"], "usable": [T("2010-06-01")], "sign": [1],
                                       "ret10": [0.0], "sig10": [0.05], "exc63": [0.0], "res_day": [pd.NaT],
                                       "first_mover": [True]})], ignore_index=True)
    early = PB.analyst2_panel(ev2, [T("2010-06-02")]).set_index("permno")      # 30 raises, none resolved by 06-02
    assert early.loc[2, "skill_net_raises_90"] == 0 and early.loc[2, "unskilled_net_raises_90"] == 1
    late = PB.analyst2_panel(ev2.assign(usable=ev2["usable"].where(ev2["permno"] == 1, T("2010-07-20"))),
                             [T("2010-07-21")]).set_index("permno")
    assert late.loc[2, "skill_net_raises_90"] == 1                    # >= 20 resolved (<= 07-21), mean > 0
    assert late.loc[2, "first_mover_raises_90"] == 1


def test_reliability_claims_resolve_after_the_63rd_session():
    ev = pd.DataFrame({"broker": ["B"], "sign": [1], "exc63": [0.1], "res_day": [T("2011-03-31")]})
    c = PB.reliability_claims(ev)
    assert c["public_at"].iloc[0] + pd.Timedelta(days=92) == T("2011-04-01")
    assert c["outcome"].iloc[0] == 1.0


def test_cluster_age_counts_only_usable_raises():
    raises = pd.DataFrame({"permno": [1, 1, 1], "usable": pd.to_datetime(["2010-01-05", "2010-01-20", "2010-03-10"])})
    k = _keys(["2010-01-31", "2010-02-28", "2010-03-09", "2010-03-31"], [1])
    a = PB.cluster_age_panel(raises, k)
    assert a[0] == pytest.approx(26.0)                               # chain started 01-05
    assert np.isnan(a[1])                                            # last raise 01-20 is 39 days old: inactive
    assert np.isnan(a[2])                                            # 03-10 not usable on 03-09
    assert a[3] == pytest.approx(21.0)                               # new chain from 03-10


# ── Compustat ──────────────────────────────────────────────────────────────

def test_fund_availability_is_the_later_of_rdq_and_the_filing_deadline():
    q = pd.DataFrame({"datadate": pd.to_datetime(["2010-03-31", "2010-12-31", "2010-06-30"]),
                      "rdq": pd.to_datetime(["2010-04-20", "2011-02-01", None]), "fqtr": [1, 4, 2]})
    av = PB.fund_available(q)
    assert av.iloc[0] == T("2010-03-31") + pd.Timedelta(days=45 + 2)          # rdq earlier than the deadline
    assert av.iloc[1] == T("2010-12-31") + pd.Timedelta(days=90 + 2)          # Q4 deadline
    assert av.iloc[2] == T("2010-06-30") + pd.Timedelta(days=45 + 2)          # missing rdq
    q2 = pd.DataFrame({"datadate": [T("2010-03-31")], "rdq": [T("2010-06-01")], "fqtr": [1]})
    assert PB.fund_available(q2).iloc[0] == T("2010-06-03")                   # a late rdq wins


def _fq(n=12, gap_at=None):
    dd = pd.date_range("2005-03-31", periods=n, freq="QE")
    if gap_at is not None:
        dd = dd.delete(gap_at)
    m = len(dd)
    return pd.DataFrame({"permno": 1, "gvkey": "G", "datadate": dd, "fqtr": [(d.month // 3) for d in dd],
                         "rdq": dd + pd.Timedelta(days=30), "saleq": np.arange(1, m + 1) * 10.0,
                         "cogsq": np.arange(1, m + 1) * 5.0, "oiadpq": 2.0, "niq": 1.0, "atq": 100.0,
                         "cheq": 10.0, "dlttq": 20.0, "dlcq": 5.0, "ceqq": 50.0, "xrdq": 1.0, "xsgaq": 3.0})


def test_fund_features_ttm_and_year_over_year():
    f = PB.fund_features(_fq())
    r = f.iloc[7]                                                    # quarters 5..8 vs 1..4
    assert r["rev_gr"] == pytest.approx((50 + 60 + 70 + 80) / (10 + 20 + 30 + 40) - 1)
    assert r["gross_margin_q"] == pytest.approx(0.5)
    assert np.isnan(f.iloc[2]["rev_gr"])                              # no TTM yet
    assert r["cash_at"] == pytest.approx(0.1) and r["ope_be"] == pytest.approx(8.0 / 50.0)


def test_fund_features_gap_breaks_the_chain():
    f = PB.fund_features(_fq(n=12, gap_at=5))
    assert f["rev_gr"].iloc[5:9].isna().all()                        # no four consecutive quarters across the gap


def test_asof_panel_never_uses_a_row_available_after_the_date():
    feats = pd.DataFrame({"permno": [1, 1], "available": pd.to_datetime(["2010-01-10", "2010-02-01"]),
                          "x": [1.0, 2.0]})
    k = _keys(["2010-01-31", "2010-02-01"], [1])
    got = PB.asof_panel(k, feats, ["x"], on="available")["x"].to_numpy()
    assert got[0] == 1.0 and got[1] == 2.0


def test_value_columns_units():
    v = PB.value_columns(np.array([1e9]), [10.0], [20.0], [100.0], [50.0], [400.0])
    assert v["earnings_yield"][0] == pytest.approx(0.01)
    assert v["ebit_ev"][0] == pytest.approx(20e6 / (1e9 + 100e6 - 50e6))
    assert v["ebit_ic"][0] == pytest.approx(20e6 / (400e6 + 50e6))
