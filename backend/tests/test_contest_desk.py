"""Contest desk: synthetic calendars and bars, dates derived from today, no network."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts import contest_calendar as cc
from scripts import contest_desk as desk

TODAY = date.today()


# ───────────────────────────── helpers ─────────────────────────────

def _long_bars(symbols: dict, days: pd.DatetimeIndex, seed: int = 7) -> pd.DataFrame:
    """symbols: name -> (price, volume). Random-walk closes, opens near the prior close."""
    rng = np.random.default_rng(seed)
    rows = []
    for s, (px, vol) in symbols.items():
        r = rng.normal(0, 0.02, len(days))
        c = px * np.exp(np.cumsum(r))
        o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.005, len(days)))
        rows.append(pd.DataFrame({"symbol": s, "date": days, "open": o, "close": c,
                                  "volume": np.full(len(days), vol)}))
    return pd.concat(rows, ignore_index=True)


def _stamps(sym: str, days: pd.DatetimeIndex, every: int = 63, hm=(16, 5),
            tz: str = "America/New_York") -> list[dict]:
    out = []
    for i in range(70, len(days), every):
        d = days[i]
        ts = pd.Timestamp(datetime(d.year, d.month, d.day, *hm), tz=tz).tz_convert("UTC")
        out.append({"symbol": sym, "ts_utc": ts, "source": "test"})
    return out


@pytest.fixture()
def world():
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=420)
    bars = _long_bars({"AAA": (50, 1e6), "BBB": (20, 2e6), "LOWV": (5, 1e3), "CCC.T": (30, 1e6)}, days)
    panel = desk.panel_from_long(bars)
    stamps = (_stamps("AAA", days) + _stamps("BBB", days, hm=(7, 0)) + _stamps("LOWV", days)
              + _stamps("CCC.T", days, hm=(15, 45), tz="Asia/Tokyo"))
    raw = pd.DataFrame(stamps)
    ev = desk.build_events(panel, raw)
    return {"days": days, "bars": bars, "panel": panel, "raw": raw, "events": ev}


# ───────────────────────────── calendar honesty ─────────────────────────────

def test_estimated_date_is_never_shown_as_confirmed():
    d = pd.Timestamp(TODAY + timedelta(days=20))
    cand = pd.DataFrame([
        {"symbol": "AAA", "date": d, "status": "ESTIMATED_PATTERN", "timing": "AMC", "source": "pattern",
         "spread_days": 3, "confidence": "HIGH"},
        {"symbol": "AAA", "date": d, "status": "VENDOR_ANNOUNCED", "timing": "AMC", "source": "nasdaq",
         "spread_days": np.nan, "confidence": "VENDOR"},
        {"symbol": "BBB", "date": d + pd.Timedelta(days=1), "status": "CONFIRMED_EXCHANGE", "timing": "UNKNOWN",
         "source": "https://www.jpx.co.jp/x.xlsx", "spread_days": 0, "confidence": "EXCHANGE"},
    ])
    cal = cc.merge_calendar(cand)
    got = dict(zip(cal.symbol, cal.is_confirmed))
    assert got == {"AAA": False, "BBB": True}
    assert cal.set_index("symbol").at["AAA", "status"] == "VENDOR_ANNOUNCED"
    cc.assert_calendar_honest(cal)
    forged = cal.copy()
    forged["is_confirmed"] = True
    with pytest.raises(cc.CalendarRefused):
        cc.assert_calendar_honest(forged)


def test_unknown_status_is_refused():
    cand = pd.DataFrame([{"symbol": "AAA", "date": pd.Timestamp(TODAY), "status": "PROBABLY",
                          "timing": "AMC", "source": "x", "spread_days": 0, "confidence": ""}])
    with pytest.raises(cc.CalendarRefused):
        cc.merge_calendar(cand)


def test_confirmation_without_source_is_refused(tmp_path):
    p = tmp_path / "confirmations.csv"
    d = (TODAY + timedelta(days=15)).isoformat()
    p.write_text(f"symbol,date,timing,source_url\nAAA,{d},AMC,https://ir.example.com/q3\nBBB,{d},AMC,\n",
                 encoding="utf-8")
    c = cc.load_confirmations(p)
    assert c.symbol.tolist() == ["AAA"]
    assert set(c.status) <= set(cc.CONFIRMED_STATUSES)


def test_estimate_uses_only_prints_before_asof():
    asof = TODAY
    hist = []
    for k in range(1, 5):
        hist.append(pd.Timestamp(asof - timedelta(days=365 * k - 30), tz="UTC"))
    hist.append(pd.Timestamp(asof - timedelta(days=60), tz="UTC"))
    future = pd.Timestamp(asof + timedelta(days=5), tz="UTC")       # must be ignored
    e1 = cc.estimate_from_history(pd.Series(hist), asof)
    e2 = cc.estimate_from_history(pd.Series(hist + [future]), asof)
    assert e1 == e2
    assert e1 is not None and e1["date"] > asof


def test_event_timing_maps_to_sessions():
    sess = pd.bdate_range(end=pd.Timestamp(TODAY), periods=30)
    d = sess[10]
    amc = pd.Timestamp(datetime(d.year, d.month, d.day, 16, 5), tz="America/New_York")
    bmo = pd.Timestamp(datetime(d.year, d.month, d.day, 7, 0), tz="America/New_York")
    mid = pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz="America/New_York")
    assert cc.event_sessions(amc, "AAA", sess) == (10, 11, "AMC")
    assert cc.event_sessions(bmo, "AAA", sess) == (9, 10, "BMO")
    assert cc.event_sessions(mid, "AAA", sess) == (9, 11, "UNKNOWN")


# ───────────────────────────── refusals and weights ─────────────────────────────

def test_no_bars_and_illiquid_names_are_refused_by_name():
    c = pd.DataFrame([
        {"symbol": "GOOD1", "trail_abs": 0.10, "n_prior": 8, "dv63": 50e6, "price_usd": 20, "has_bars": True},
        {"symbol": "NOBARS", "trail_abs": 0.30, "n_prior": 8, "dv63": np.nan, "price_usd": np.nan, "has_bars": False},
        {"symbol": "THIN", "trail_abs": 0.25, "n_prior": 8, "dv63": 2e6, "price_usd": 20, "has_bars": True},
        {"symbol": "NEW", "trail_abs": np.nan, "n_prior": 1, "dv63": 50e6, "price_usd": 20, "has_bars": True},
        {"symbol": "OUT", "trail_abs": 0.2, "n_prior": 8, "dv63": 50e6, "price_usd": 20, "has_bars": True,
         "membership": "NOT_IN_WLS_EXPORT"},
    ])
    c["membership"] = c.get("membership").fillna("UNCONFIRMED_MEMBERSHIP")
    ok, refused = desk.rank_candidates(c)
    assert ok.symbol.tolist() == ["GOOD1"]
    why = dict(zip(refused.symbol, refused.refusal))
    assert why["NOBARS"] == "REFUSED_NO_BARS"
    assert why["THIN"].startswith("REFUSED_ILLIQUID")
    assert why["NEW"].startswith("REFUSED_HISTORY")
    assert why["OUT"] == "REFUSED_NOT_IN_WLS"


def test_weights_never_exceed_cap_and_sum_to_at_most_one():
    c = pd.DataFrame([{"symbol": f"S{i}", "trail_abs": 0.01 * i, "n_prior": 8, "dv63": 50e6,
                       "price_usd": 10, "has_bars": True, "membership": "UNCONFIRMED_MEMBERSHIP"}
                      for i in range(1, 12)])
    ok, _ = desk.rank_candidates(c)
    assert ok.weight.max() <= cc.POSITION_CAP + 1e-12
    assert ok.weight.sum() <= 1 + 1e-12
    assert (ok.weight > 0).sum() == desk.K_SLOTS
    with pytest.raises(desk.SheetRefused):
        desk.check_weights(np.array([0.25, 0.2]))
    with pytest.raises(desk.SheetRefused):
        desk.check_weights(np.array([0.2] * 6))
    with pytest.raises(desk.SheetRefused):
        desk.check_weights(np.array([0.2, -0.1]))


# ───────────────────────────── the sheet uses nothing dated after it ─────────────────────────────

def _sheet_day(world) -> date:
    ev = world["events"]
    us = ev[(ev.symbol == "AAA") & ev.pre_date.notna() & ev.react_date.notna()].iloc[-2]
    return us.pre_date.date()


def test_sheet_uses_nothing_dated_after_its_date(world):
    d = _sheet_day(world)
    s1 = desk.make_sheet(d, world["events"], world["panel"], None)
    assert "AAA" in set(s1.buys.symbol)
    # corrupt every bar from the sheet date on, and every reaction after it
    bars = world["bars"].copy()
    after = bars.date >= pd.Timestamp(d)
    bars.loc[after, ["open", "close"]] *= 7.0
    bars.loc[after, "volume"] *= 0.001
    panel2 = desk.panel_from_long(bars)
    ev2 = desk.build_events(panel2, world["raw"])
    s2 = desk.make_sheet(d, ev2, panel2, None)
    cols = ["symbol", "trail_abs", "n_prior", "dv63", "rank", "weight"]
    pd.testing.assert_frame_equal(s1.buys[cols].reset_index(drop=True), s2.buys[cols].reset_index(drop=True))


def test_sheet_refuses_the_illiquid_name_and_renders_unconfirmed(world):
    d = _sheet_day(world)
    s = desk.make_sheet(d, world["events"], world["panel"], None)
    assert "LOWV" in set(s.refused.symbol)
    assert s.refused.set_index("symbol").at["LOWV", "refusal"].startswith("REFUSED_ILLIQUID")
    md, short = desk.render_sheet(s)
    assert "CONFIRMED (" not in md.replace("NOT CONFIRMED (", "")
    assert "NOT CONFIRMED" in md
    assert "LOWV" in md
    top = s.buys[s.buys.weight > 0]
    assert top.weight.sum() <= 1 + 1e-12 and top.weight.max() <= 0.2 + 1e-12


def test_sheet_window_orders_markets_by_hong_kong_open():
    d = TODAY
    w0, w1 = desk.sheet_window(d)
    us_open = desk.session_open_hkt("AAA", pd.Timestamp(d))
    jp_open_next = desk.session_open_hkt("CCC.T", pd.Timestamp(d + timedelta(days=1)))
    assert w0 <= us_open < w1
    assert w0 <= jp_open_next < w1
    assert us_open < jp_open_next


# ───────────────────────────── the shrink guard ─────────────────────────────

def test_shrink_guard_refuses(tmp_path):
    p = tmp_path / "t.parquet"
    big = pd.DataFrame({"a": range(10)})
    cc.safe_write_parquet(big, p)
    with pytest.raises(cc.ShrinkRefused):
        cc.safe_write_parquet(big.head(3), p)
    assert len(pd.read_parquet(p)) == 10
    cc.safe_write_parquet(pd.concat([big, big]), p)
    assert len(pd.read_parquet(p)) == 20


def test_pull_bars_never_shrinks(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "BARS_DIR", tmp_path)
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=2), periods=20)

    def dl(tickers, start, end):
        return _long_bars({t: (10, 1e5) for t in tickers}, days)

    r1 = cc.pull_bars(["X1", "X2"], "JP", downloader=dl, sleep=0)
    assert r1["rows_after"] == 40

    def dl_empty(tickers, start, end):
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])

    r2 = cc.pull_bars(["X1", "X2"], "JP", downloader=dl_empty, sleep=0)
    assert r2["rows_after"] == 40 and r2["n_failed"] == 2


# ───────────────────────────── membership ─────────────────────────────

def test_wls_export_marks_membership(tmp_path):
    (tmp_path / "wls.csv").write_text("Ticker,Weight\nAAPL US Equity,1.0\n7203 JT Equity,0.3\n",
                                      encoding="utf-8")
    u = pd.DataFrame({"symbol": ["AAPL", "7203.T", "ZZZZ"],
                      "bbg_ticker": ["AAPL US Equity", "7203 JT Equity", "ZZZZ US Equity"]})
    m = cc.apply_wls(u, tmp_path)
    assert dict(zip(m.symbol, m.membership)) == {"AAPL": "CONFIRMED_WLS", "7203.T": "CONFIRMED_WLS",
                                                 "ZZZZ": "NOT_IN_WLS_EXPORT"}
    empty = tmp_path / "none"
    empty.mkdir()
    assert set(cc.apply_wls(u, empty).membership) == {"UNCONFIRMED_MEMBERSHIP"}


def test_bloomberg_tickers():
    assert cc.bloomberg_ticker("AAPL") == "AAPL US Equity"
    assert cc.bloomberg_ticker("0700.HK") == "700 HK Equity"
    assert cc.bloomberg_ticker("7203.T") == "7203 JT Equity"
    assert cc.bloomberg_ticker("SAP.DE") == "SAP GY Equity"
    assert cc.market_of("BBRI.JK") == "ID"


def test_duplicate_stamps_of_one_report_collapse_to_the_most_primary():
    d = pd.Timestamp(TODAY - timedelta(days=30))
    ny = "America/New_York"
    raw = pd.DataFrame([
        {"symbol": "AAA", "ts_utc": pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz=ny), "source": "nasdaq_calendar"},
        {"symbol": "AAA", "ts_utc": pd.Timestamp(datetime(d.year, d.month, d.day, 7, 0), tz=ny), "source": "yahoo_earnings_dates"},
        {"symbol": "AAA", "ts_utc": pd.Timestamp(datetime(d.year, d.month, d.day, 7, 2), tz=ny), "source": "sec_8k_2.02"},
        {"symbol": "AAA", "ts_utc": pd.Timestamp(datetime(d.year, d.month, d.day, 7, 0), tz=ny) + pd.Timedelta(days=91), "source": "yahoo_earnings_dates"},
    ])
    out = desk.dedupe_stamps(raw)
    assert len(out) == 2
    assert out.iloc[0].source == "sec_8k_2.02"
