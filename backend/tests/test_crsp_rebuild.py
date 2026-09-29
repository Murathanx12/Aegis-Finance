"""crsp_rebuild: the CRSP -> library-engine bridge (offline, synthetic data)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import crsp_rebuild as CR


def _cal(n: int, start: str = "2001-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _market(cal, r: float = 0.0005) -> pd.Series:
    return pd.Series(r, index=cal)


def _daily(cal, permno: int, *, ret=0.001, prc=20.0, vol=1e6, n=None, openprc=True):
    n = len(cal) if n is None else n
    px = prc * np.cumprod(np.full(n, 1.0 + ret))
    return pd.DataFrame({"permno": permno, "date": cal[:n], "prc": px, "ret": ret, "vol": vol,
                         "openprc": px * 0.999 if openprc else np.nan, "cfacpr": 1.0})


def test_close_is_a_total_return_index_and_dollar_volume_is_true():
    cal = _cal(10)
    d = _daily(cal, 10001)
    # a dividend day: the price falls 2%, the total return is +0.5%
    d.loc[5, "ret"] = 0.005
    d.loc[5:, "prc"] = d.loc[5:, "prc"] * 0.98
    W = CR.wide_from_crsp(d, None, _market(cal))
    j = int(np.searchsorted(W["symbols"], CR.permno_symbol(10001)))
    C = W["close"][:, j]
    assert C[0] == pytest.approx(d.loc[0, "prc"])
    assert C[5] / C[4] - 1 == pytest.approx(0.005)
    assert C[6] / C[5] - 1 == pytest.approx(0.001)
    # close x volume is the actual dollar volume
    assert W["close"][3, j] * W["volume"][3, j] == pytest.approx(d.loc[3, "prc"] * 1e6)
    # open rides on the index
    assert W["open"][3, j] == pytest.approx(C[3] * 0.999)
    assert W["price"][5, j] == pytest.approx(d.loc[5, "prc"])


def test_missing_open_is_yesterdays_close_and_market_is_last_symbol():
    cal = _cal(8)
    W = CR.wide_from_crsp(_daily(cal, 10002, openprc=False), None, _market(cal, 0.01))
    assert W["symbols"][-1] == CR.MARKET
    j = 0
    assert W["open"][0, j] == pytest.approx(W["close"][0, j])
    assert W["open"][4, j] == pytest.approx(W["close"][3, j])
    m = W["close"][:, -1]
    assert m[3] / m[2] - 1 == pytest.approx(0.01)
    assert W["audit"]["open_share"] == 0.0


def test_missing_ret_is_filled_from_the_split_adjusted_price_ratio():
    cal = _cal(6)
    d = _daily(cal, 10003, ret=0.0, prc=10.0)
    d.loc[3, "ret"] = np.nan
    d.loc[3:, "prc"] = 5.0          # a 2-for-1 split ...
    d.loc[:2, "cfacpr"] = 2.0       # ... that CRSP's factor undoes (adjusted = prc / cfacpr)
    W = CR.wide_from_crsp(d, None, _market(cal))
    C = W["close"][:, 0]
    assert C[3] / C[2] == pytest.approx(1.0)
    assert W["audit"]["ret_filled_from_price_ratio"] == 1


def test_delisting_return_is_booked_on_the_next_session_and_never_eligible():
    cal = _cal(12)
    a = _daily(cal, 20001, n=6)                 # stops after session 5
    b = _daily(cal, 20002, n=6)                 # stops too, no dlret, code 550 -> -30%
    c = _daily(cal, 20003, n=6)                 # code 100: still active, nothing booked
    dl = pd.DataFrame({"permno": [20001, 20002, 20003],
                       "dlstdt": [cal[6], cal[6], cal[6]],
                       "dlstcd": [241.0, 550.0, 100.0], "dlret": [-0.5, np.nan, np.nan]})
    keep = _daily(cal, 20009)                   # trades on every session (the calendar)
    W = CR.wide_from_crsp(pd.concat([a, b, c, keep]), dl, _market(cal))
    ja, jb, jc = (int(np.searchsorted(W["symbols"], CR.permno_symbol(p))) for p in (20001, 20002, 20003))
    assert W["close"][6, ja] / W["close"][5, ja] == pytest.approx(0.5)
    assert W["close"][6, jb] / W["close"][5, jb] == pytest.approx(0.7)
    assert not np.isfinite(W["close"][6, jc])
    assert W["dl_mask"][6, ja] and W["dl_mask"][6, jb] and not W["dl_mask"][6, jc]
    assert W["audit"]["delisting_returns_booked"] == 2
    assert W["audit"]["delisting_missing_dlret_filled"] == 1
    panel = pd.DataFrame({"date": [cal[6], cal[5]], "symbol": [CR.permno_symbol(20001)] * 2,
                          "eligible": [True, True], "close": [np.nan, np.nan]})
    out = CR.apply_actual_price(panel, W, min_price=3.0, max_price=1e4)
    assert out["eligible"].tolist() == [False, True]


def test_price_floor_reads_the_actual_price_not_the_index():
    cal = _cal(5)
    d = _daily(cal, 30001, ret=0.0, prc=2.0)
    W = CR.wide_from_crsp(d, None, _market(cal))
    panel = pd.DataFrame({"date": [cal[3]], "symbol": [CR.permno_symbol(30001)], "eligible": [True],
                          "close": [123.0]})
    out = CR.apply_actual_price(panel, W, min_price=3.0, max_price=1e4)
    assert out["close"].iloc[0] == pytest.approx(2.0)
    assert not out["eligible"].iloc[0]


def test_price_band_disabled_restores_the_module_constants():
    class XR:
        MIN_PRICE, MAX_PRICE = 3.0, 1e4
    with CR.price_band_disabled(XR) as (lo, hi):
        assert (XR.MIN_PRICE, XR.MAX_PRICE) == (0.0, float("inf"))
        assert (lo, hi) == (3.0, 1e4)
    assert (XR.MIN_PRICE, XR.MAX_PRICE) == (3.0, 1e4)
    with pytest.raises(RuntimeError):
        with CR.price_band_disabled(XR):
            raise RuntimeError("boom")
    assert XR.MIN_PRICE == 3.0


def test_engine_forward_return_carries_the_real_delisting_value():
    """End to end through the factory's build_panel: a name that dies inside the
    hold period exits at its delisting value (delist_return=0 in the engine)."""
    from backend.services import xs_ranker as XR
    from scripts import night_backtest_factory as F
    cal = _cal(330)
    live = _daily(cal, 40001, ret=0.001, prc=30.0, vol=5e6)
    die_at = 300
    dying = _daily(cal, 40002, ret=0.0, prc=30.0, vol=5e6, n=die_at)
    dl = pd.DataFrame({"permno": [40002], "dlstdt": [cal[die_at]], "dlstcd": [552.0], "dlret": [-0.6]})
    W = CR.wide_from_crsp(pd.concat([live, dying]), dl, _market(cal))
    with CR.price_band_disabled(XR) as (lo, hi):
        panel = F.build_panel(W, delist_return=0.0, min_index=252)
    panel = CR.apply_actual_price(panel, W, min_price=lo, max_price=hi)
    me = panel[panel["is_month_end"] & (panel["symbol"] == CR.permno_symbol(40002))]
    last_dec = me[me["date"] < cal[die_at - 1]].iloc[-1]
    assert last_dec["delisted_in_period"]
    # entry at the next open (30 x 0.999 on a flat index), exit at 30 x 0.4
    assert last_dec["fwd_ret"] == pytest.approx(0.4 / 0.999 - 1.0, rel=1e-6)
    assert XR.MIN_PRICE == lo


def test_target_cv_uses_each_firms_latest_target_strictly_before_the_date():
    d = pd.Timestamp("2010-06-30")
    t = pd.DataFrame({
        "permno": [1, 1, 1, 1, 1, 2, 2],
        "estimid": ["A", "A", "B", "C", "D", "A", "B"],
        "anndats": [d - pd.Timedelta(days=200), d - pd.Timedelta(days=10), d - pd.Timedelta(days=20),
                    d - pd.Timedelta(days=30), d, d - pd.Timedelta(days=5), d - pd.Timedelta(days=5)],
        "value": [999.0, 10.0, 12.0, 14.0, 50.0, 10.0, 11.0]})
    out = CR.target_cv(t, [d])
    assert len(out) == 1                      # permno 2 has only two firms
    v = np.array([10.0, 12.0, 14.0])          # A's stale 999 and D's same-day 50 excluded
    assert out["target_cv_180"].iloc[0] == pytest.approx(v.std(ddof=1) / v.mean())
    assert out["symbol"].iloc[0] == CR.permno_symbol(1)


def test_decile_returns_and_jt_overlap():
    rng = np.random.default_rng(3)
    dates = pd.date_range("2005-01-31", periods=4, freq="ME")
    rows = []
    for d in dates:
        for i in range(100):
            rows.append({"date": d, "symbol": f"{i:06d}", "eligible": True,
                         "mom_252_21": i / 100.0, "fwd_ret": i / 1000.0 + rng.normal(0, 1e-6)})
    dec = CR.decile_returns(pd.DataFrame(rows))
    assert list(dec.index) == list(dates)
    assert dec["d10"].iloc[0] > dec["d1"].iloc[0]
    assert dec["d10"].iloc[0] == pytest.approx(np.mean(np.arange(90, 100)) / 1000, abs=1e-5)
    tops = {d: ["a", "b"] for d in dates}
    fwd = {d: {"a": 0.1, "b": 0.3} for d in dates}
    fwd[dates[2]] = {"a": 0.1}                # b missing -> earns 0
    jt = CR.jt_overlap(tops, fwd, list(dates), hold=3)
    assert list(jt.index) == list(dates[2:])
    assert jt.loc[dates[2]] == pytest.approx(0.05)


def test_window_stats_blocks_and_hold_month_key():
    idx = pd.date_range("2000-01-31", periods=24, freq="ME")
    s = pd.Series(np.r_[np.full(12, 0.01), np.full(12, 0.03)], index=idx)
    s.iloc[::3] += 0.005
    full = CR.window_stats(s)
    assert full["n_months"] == 24 and full["n_blocks"] == 8
    assert full["t_blocks"] > 0 and full["mde_monthly"] > 0
    # the 2000-12-29 decision is HELD in 2001 (hold month = decision + 1 business day)
    w = CR.window_stats(s, "2001-01-01", None)
    assert w["n_months"] == 13


def test_share_of_total_by_date():
    s = pd.Series([0.0] * 99 + [1.0], index=pd.date_range("2000-01-31", periods=100, freq="ME"))
    out = CR.share_of_total_by_date(s)
    assert out["top_1pct_of_months"] == pytest.approx(1.0)
    assert out["top_1pct_months"] == ["2008-04-30"]


def test_verdicts():
    assert CR.factor_verdict(2.3, 0.01, 0.02) == "ALPHA_DETECTED"
    assert CR.factor_verdict(-2.1, 0.01, 0.02) == "ALPHA_DETECTED"
    assert CR.factor_verdict(0.5, 0.004, 0.01) == "BETA_EXPLAINS"
    assert CR.factor_verdict(0.5, 0.02, 0.01) == "CANNOT_DISTINGUISH"   # no power is not no alpha
    assert CR.factor_verdict(None, None, None) == "CANNOT_DISTINGUISH"
    assert CR.twin_verdict({"mean_monthly": -0.001, "t_blocks": 3.0}) == "FAILED_VARIANT"
    assert CR.twin_verdict({"mean_monthly": 0.005, "t_blocks": 2.1}) == "ALPHA_DETECTED"
    assert CR.twin_verdict({"mean_monthly": 0.005, "t_blocks": 1.2}) == "CANNOT_DISTINGUISH"
    assert CR.twin_verdict({"mean_monthly": None}) == "NOT_COMPUTED"


def test_vendor_symbol_maps_to_the_permno_valid_on_the_date():
    names = CR.ticker_map(pd.DataFrame({
        "permno": [1, 2, 3, 4], "ticker": ["LINE", "LINE", "BRK", "BRK"], "shrcls": [None, None, "A", "B"],
        "namedt": ["2006-01-01", "2024-07-25", "1990-01-01", "1996-05-09"],
        "nameenddt": ["2016-09-30", None, None, None], "shrcd": [11, 11, 11, 11],
        "exchcd": [3, 1, 1, 1]}))
    assert CR.vendor_to_permno("LINE", "2012-03-30", names)["permno"] == 1
    assert CR.vendor_to_permno("LINE#1", "2024-09-30", names)["permno"] == 2
    assert CR.vendor_to_permno("BRK.B", "2020-01-31", names)["permno"] == 4
    # no name on the date: the permno that took the ticker LATER carries the vendor history
    hit = CR.vendor_to_permno("LINE", "2020-01-31", names)
    assert (hit["permno"], hit["how"]) == (2, "later_ticker")
    assert CR.vendor_to_permno("ZZZZ", "2020-01-31", names)["permno"] is None


def test_a_renamed_company_maps_through_its_new_ticker():
    """Vendor bars sit under today's ticker: 2017's FB is META in the vendor file."""
    names = CR.ticker_map(pd.DataFrame({
        "permno": [13407, 13407, 99999], "ticker": ["FB", "META", "META"], "shrcls": [None] * 3,
        "namedt": ["2012-05-18", "2022-06-09", "2001-01-01"],
        "nameenddt": ["2022-06-08", None, "2005-12-31"], "shrcd": [11, 11, 11], "exchcd": [3, 3, 1]}))
    by = CR.names_by_ticker(names)
    assert CR.vendor_to_permno("META", "2017-06-30", by)["permno"] == 13407
    assert CR.vendor_to_permno("META", "2003-06-30", by)["permno"] == 99999
    assert CR.vendor_to_permno("META", "2023-06-30", by)["how"] == "on_date"


def test_slot_reasons():
    ok = {"permno": 5, "shrcd": 11, "exchcd": 3}
    assert CR.classify_vendor_slot({"permno": None}, None, 1.0) == "V1_no_crsp_permno"
    assert CR.classify_vendor_slot({"permno": 5, "shrcd": 31, "exchcd": 3}, None, 1.0).startswith("V2")
    assert CR.classify_vendor_slot(ok, None, 1.0).startswith("V3")
    assert CR.classify_vendor_slot(ok, {"eligible": False, "score": 1.0}, 1.0).startswith("V4")
    assert CR.classify_vendor_slot(ok, {"eligible": True, "score": 0.2}, 5.0).startswith("V6")
    assert CR.classify_vendor_slot(ok, {"eligible": True, "score": 1.02}, 1.0).startswith("V7")
    assert CR.classify_crsp_slot(None, 1.0).startswith("C1")
    assert CR.classify_crsp_slot({"eligible": False, "score": 1.0}, 1.0).startswith("C2")
    assert CR.classify_crsp_slot({"eligible": True, "score": 3.0}, 1.0).startswith("C4")
    assert CR.classify_crsp_slot({"eligible": True, "score": 1.0}, 1.01).startswith("C5")


def test_end_screen_universe_drops_only_the_alive_but_shrunk():
    dates = pd.date_range("2020-01-31", periods=6, freq="ME")
    rows = []
    for d in dates:
        rows.append({"date": d, "symbol": "live_liquid", "median_dollar_vol": 5e6})
        rows.append({"date": d, "symbol": "live_shrunk", "median_dollar_vol": 5e6 if d < dates[-1] else 1e6})
        if d < dates[2]:
            rows.append({"date": d, "symbol": "dead", "median_dollar_vol": 9e6})
    u = CR.end_screen_universe(pd.DataFrame(rows), asof=dates[-1], min_median_dollar_vol=3e6)
    assert u["keep"] == {"live_liquid", "dead"}
    assert u["alive_shrunk"] == {"live_shrunk"}
