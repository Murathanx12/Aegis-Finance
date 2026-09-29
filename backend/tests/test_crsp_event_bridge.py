"""Offline tests for the CRSP point-in-time event bridge (2026-09-29).

Pins the timestamp rule: IBES rows dated by max(anndats, actdats), one trading
day of lag, usable only at decision dates on/after the lagged day; the IBES
link taken on the EVENT date; the earnings return used only after e+1; no
event after the decision date can move a feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services import crsp_event_bridge as B

T = pd.Timestamp


def test_event_day_is_later_of_announcement_and_activation():
    d = B.event_day(pd.Series([T("2005-03-01"), T("2005-03-10")]), pd.Series([T("2005-03-04"), T("2005-03-02")]))
    assert list(d) == [T("2005-03-04"), T("2005-03-10")]


def test_usable_is_one_business_day_later_and_skips_weekend():
    u = B.usable_date(pd.Series([T("2005-03-03"), T("2005-03-04")]))   # Thu, Fri
    assert list(u) == [T("2005-03-04"), T("2005-03-07")]


def test_link_uses_the_row_active_on_the_event_date():
    link = pd.DataFrame({"ticker": ["AAA", "AAA"], "permno": [10001, 20002],
                         "sdate": [T("1990-01-01"), T("2001-01-01")], "edate": [T("2000-12-31"), T("2024-12-31")],
                         "score": [1, 1]})
    ev = pd.DataFrame({"ticker": ["AAA", "AAA", "AAA"], "day": [T("1995-05-05"), T("2010-05-05"), T("1985-01-01")]})
    out, meta = B.link_permno(ev, link)
    assert sorted(out["permno"].tolist()) == [10001, 20002]
    assert meta["events_in"] == 3 and meta["events_linked"] == 2   # the 1985 event has no active link: dropped


def test_link_lowest_score_wins():
    link = pd.DataFrame({"ticker": ["A", "A"], "permno": [1, 2], "sdate": [T("1990-01-01")] * 2,
                         "edate": [T("2030-01-01")] * 2, "score": [4, 1]})
    out, _ = B.link_permno(pd.DataFrame({"ticker": ["A"], "day": [T("2000-01-03")]}), link)
    assert out["permno"].tolist() == [2]


def test_target_signs_same_broker_only_and_stale_prior_is_not_a_raise():
    p = pd.DataFrame({"permno": [1, 1, 1, 1], "broker": ["X", "X", "Y", "X"],
                      "day": [T("2000-01-03"), T("2000-02-01"), T("2000-02-02"), T("2002-01-01")],
                      "value": [10.0, 12.0, 5.0, 20.0]})
    s = B.target_signs(p).sort_values("day")
    assert s["sign"].tolist() == [0, 1, 0, 0]     # Y's first target is not a lower vs X; X after 700 days is not a raise
    assert abs(s["chg"].iloc[1] - 0.2) < 1e-12


def test_rec_actions_lower_code_is_upgrade():
    r = pd.DataFrame({"permno": [1, 1, 1], "broker": ["X"] * 3,
                      "day": [T("2000-01-03"), T("2000-02-01"), T("2000-03-01")], "code": [3, 2, 4]})
    assert B.rec_actions(r).sort_values("day")["action"].tolist() == ["init", "up", "down"]


def _ev(days, signs, permno=1, broker="X"):
    d = pd.Series([T(x) for x in days])
    return pd.DataFrame({"permno": permno, "usable": B.usable_date(d).to_numpy(), "broker": broker,
                         "sign": signs, "chg": np.nan})


def test_flow_counts_only_events_usable_by_the_decision_date():
    d = T("2005-03-31")                                       # Thursday
    ev = _ev(["2005-03-29", "2005-03-30", "2005-03-31"], [1, 1, 1])
    f = B.flow_panel(ev, [d]).set_index("permno")
    # 03-29 usable 03-30, 03-30 usable 03-31 (counted), 03-31 usable 04-01 (not yet)
    assert f.loc[1, "net_raises"] == 2.0


def test_future_events_cannot_change_past_features():
    d = [T("2005-01-31"), T("2005-02-28")]
    base = _ev(["2004-12-15", "2005-01-10"], [1, -1])
    fut = pd.concat([base, _ev(["2005-02-10", "2005-02-27"], [1, 1])], ignore_index=True)
    a = B.flow_panel(base, d).set_index(["date", "permno"])
    b = B.flow_panel(fut, d).set_index(["date", "permno"])
    assert a.loc[(d[0], 1)].equals(b.loc[(d[0], 1)])
    assert b.loc[(d[1], 1), "net_raises"] == 2.0                  # 12-15 fell out of 90d? no: (d-90, d] keeps 12-15
    assert b.loc[(d[1], 1), "net_raises_30"] == 2.0


def test_covered_name_with_empty_window_reads_zero_not_nan():
    ev = _ev(["2004-06-01"], [1])
    f = B.flow_panel(ev, [T("2005-01-31")]).set_index("permno")
    assert f.loc[1, "net_raises"] == 0.0 and f.loc[1, "n_firms"] == 0.0


def test_insider_uses_filing_day_plus_one():
    ev = pd.DataFrame({"permno": [7, 7], "usable": B.usable_date(pd.Series([T("2010-06-29"), T("2010-06-30")])).to_numpy(),
                       "event_type": [B.BUY, B.BUY], "insider_cik": ["a", "b"], "insider_is_officer": [True, False],
                       "insider_dollar_value": [100.0, 50.0]})
    f = B.insider_panel(ev, [T("2010-06-30")]).set_index("permno")
    assert f.loc[7, "ins_buyers_90"] == 1.0 and f.loc[7, "ins_officer_buyers_90"] == 1.0


def test_earnings_events_drop_late_restatements_and_after_close_moves_reaction():
    a = pd.DataFrame({"permno": [1, 1, 1], "pends": [T("2012-12-31"), T("2013-03-31"), T("2013-03-31")],
                      "anndats": [T("2014-02-14"), T("2013-04-25"), T("2013-05-10")],
                      "anntims": ["18:41:00", "16:05:00", "08:00:00"]})
    e = B.earnings_events(a)
    assert len(e) == 1 and e["anndats"].iloc[0] == T("2013-04-25")
    assert e["reaction_day"].iloc[0] == T("2013-04-26")


def test_three_day_car_and_known_after_e_plus_one():
    dates = pd.bdate_range("2013-04-22", periods=8)
    daily = pd.DataFrame({"permno": 1, "date": dates, "ret": [0, 0, 0, 0.10, 0, 0, 0, 0]})
    mkt = pd.Series(0.0, index=dates)
    out = B.three_day_car(daily, mkt, pd.DataFrame({"permno": [1], "reaction_day": [dates[4]]}))
    assert abs(out["ear"].iloc[0] - 0.10) < 1e-9                 # e-1 is dates[3]
    assert out["known"].iloc[0] == dates[6]                      # e+1 = dates[5]; usable the day after


def test_earnings_panel_ignores_unknown_ear():
    er = pd.DataFrame({"permno": [1], "anndats": [T("2013-04-29")], "ear": [0.05], "known": [T("2013-05-02")]})
    d = [T("2013-04-30"), T("2013-05-31")]
    f = B.earnings_panel(er, d, B.next_decision(d)).set_index(["date", "permno"])
    assert np.isnan(f.loc[(d[0], 1), "ear_last"])
    assert f.loc[(d[1], 1), "ear_last"] == 0.05
