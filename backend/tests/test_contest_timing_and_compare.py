"""Contest desk, 2026-09-29 amendments: untimed report stamps, and the book comparison.

REVIEW_2026-09-29_CONTEST_DESK finding 1 (a 00:00 UTC stamp is "time unknown", not 09:00
Tokyo) and findings 2 and 6 (survivorship, earnings drift, gross <= 100%). Synthetic data,
dates derived from today, no network.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts import contest_book_compare as cmp
from scripts import contest_calendar as cc
from scripts import contest_desk as desk

TODAY = date.today()


def _sess(n: int = 40) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(TODAY) - pd.offsets.BDay(3), periods=n)


# ───────────────────────────── untimed stamps ─────────────────────────────

def test_a_midnight_utc_tokyo_stamp_is_unknown_and_held_two_sessions():
    sess = _sess()
    d = sess[10]
    ts = pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz="UTC")     # 09:00 JST
    assert cc.event_sessions(ts, "7203.T", sess) == (9, 11, "UNKNOWN")
    # a real afternoon release after the Tokyo close stays AMC
    amc = pd.Timestamp(datetime(d.year, d.month, d.day, 15, 30), tz="Asia/Tokyo")
    assert cc.event_sessions(amc, "7203.T", sess) == (10, 11, "AMC")


def test_a_utc_midnight_placeholder_keeps_the_vendor_date_in_new_york():
    d = pd.Timestamp(_sess()[10])
    ts = pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz="UTC")     # 20:00 ET the day before
    day, timing = cc.stamp_timing(ts, "AAA")
    assert timing == "UNKNOWN" and day == d


def test_untimed_mask_agrees_with_the_scalar_check():
    d = pd.Timestamp(_sess()[5])
    ts = pd.Series([pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz="UTC"),
                    pd.Timestamp(datetime(d.year, d.month, d.day, 6, 30), tz="UTC"),
                    pd.Timestamp(datetime(d.year, d.month, d.day, 0, 0), tz="America/New_York").tz_convert("UTC")])
    sy = pd.Series(["6758.T", "6758.T", "AAA"])
    m = cc.untimed_mask(ts, sy)
    assert list(m) == [cc.is_untimed_stamp(t, s) for t, s in zip(ts, sy)] == [True, False, True]


def test_usual_timing_needs_a_strict_majority_of_real_times():
    sess = _sess(400)
    days = [sess[i] for i in (50, 113, 176, 239)]
    mid = [pd.Timestamp(datetime(x.year, x.month, x.day, 0, 0), tz="UTC") for x in days]
    amc = [pd.Timestamp(datetime(x.year, x.month, x.day, 15, 30), tz="Asia/Tokyo") for x in days]
    assert cc.usual_timing(pd.Series(mid[:3] + amc[3:]), "7203.T") == "UNKNOWN"
    assert cc.usual_timing(pd.Series(amc[:3] + mid[3:]), "7203.T") == "AMC"
    assert cc.usual_timing(pd.Series(amc[:2] + mid[2:]), "7203.T") == "UNKNOWN"      # 2 of 4 is not a majority


def test_the_live_desk_holds_an_unknown_time_calendar_row_two_sessions():
    sess = _sess()
    d = sess[10]
    ts = desk.calendar_stamp("7203.T", d, "UNKNOWN")
    assert cc.event_sessions(ts, "7203.T", sess) == (9, 11, "UNKNOWN")
    ts = desk.calendar_stamp("AAA", d, "AMC")
    assert cc.event_sessions(ts, "AAA", sess) == (10, 11, "AMC")
    ts = desk.calendar_stamp("AAA", d, "BMO")
    assert cc.event_sessions(ts, "AAA", sess) == (9, 10, "BMO")


def test_the_calendar_receipt_splits_confirmed_dates_by_known_time(monkeypatch):
    d0 = TODAY + timedelta(days=10)
    conf = pd.DataFrame([
        {"symbol": "7203.T", "date": pd.Timestamp(d0), "timing": "UNKNOWN", "source_url": "https://x.jp/a",
         "status": "CONFIRMED_EXCHANGE"},
        {"symbol": "AAA", "date": pd.Timestamp(d0 + timedelta(days=1)), "timing": "AMC",
         "source_url": "https://x.com/b", "status": "CONFIRMED_COMPANY"}])
    monkeypatch.setattr(cc, "load_confirmations", lambda *a, **k: conf)
    uni = pd.DataFrame({"symbol": ["7203.T", "AAA"], "name": ["T", "A"], "market": ["JP", "US"],
                        "bbg_ticker": ["7203 JT Equity", "AAA US Equity"], "membership": ["U", "U"],
                        "adv_usd_3m": [5e7, 5e7]})
    cal, rec = cc.build_calendar(TODAY, window=(TODAY, TODAY + timedelta(days=30)), use_network=False,
                                 universe=uni, hist_global=pd.DataFrame(columns=["symbol", "ts_utc"]),
                                 us_events=pd.DataFrame(columns=["symbol", "ts_utc"]))
    assert rec["n_confirmed"] == 2
    assert rec["n_confirmed_timed"] == 1 and rec["n_confirmed_time_unknown"] == 1


def test_the_sheet_labels_a_confirmed_date_with_an_unknown_time():
    d = TODAY
    buys = pd.DataFrame([{"symbol": "7203.T", "rank": 1, "weight": 0.2, "bbg_ticker": "7203 JT Equity",
                          "name": "T", "market": "JP", "buy_open_hkt": pd.Timestamp(d, tz=cc.HKT),
                          "ts_utc": pd.Timestamp(d, tz="UTC"), "timing": "UNKNOWN",
                          "date_status": "CONFIRMED_EXCHANGE", "date_confirmed": True, "trail_abs": 0.08,
                          "n_prior": 6, "sig63": 0.02, "nn_size_5d": np.nan, "dv63": 3e7,
                          "membership": "UNCONFIRMED_MEMBERSHIP", "implied_move": None}])
    md, short = desk.render_sheet(desk.Sheet(d, buys, pd.DataFrame(), pd.DataFrame(columns=["symbol"]), []))
    assert "DATE CONFIRMED, TIME UNKNOWN (held two sessions)" in md
    assert "1 confirmed with time UNKNOWN" in short


# ───────────────────────────── the book comparison ─────────────────────────────

def _panel(n_days: int = 120, n_names: int = 9, seed: int = 7) -> desk.Panel:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.offsets.BDay(3), periods=n_days)
    rows = []
    for k in range(n_names):
        c = 50 * np.exp(np.cumsum(rng.normal(0, 0.002 * 1.6 ** k, n_days)))   # well-separated vols
        for i, dd in enumerate(dates):
            rows.append({"symbol": f"S{k}", "date": dd, "open": c[i] * 0.999, "close": c[i], "volume": 1e6})
    for i, dd in enumerate(dates):
        rows.append({"symbol": "ACWI", "date": dd, "open": 100.0, "close": 100.0, "volume": 1e7})
    return desk.panel_from_long(pd.DataFrame(rows))


def _events(panel: desk.Panel, days: np.ndarray) -> pd.DataFrame:
    rows = []
    t = int(days[2])
    for k in range(7):                                  # 7 names report the same day: only 5 fit
        rows.append({"symbol": f"S{k}", "ci": panel.col[f"S{k}"], "pre_i": t, "react_i": t + 2,
                     "trail_abs": 0.01 * (k + 1), "on_cadence": True, "market": "US", "timing": "UNKNOWN"})
    return pd.DataFrame(rows)


def test_season_path_holds_at_most_five_slots_and_the_untimed_hold_spans_two_sessions():
    p = _panel()
    m = cmp.market(p)
    days = np.arange(80, 100)
    ev = _events(p, days)
    sp = cmp.season_path(days, ev, m, "CURRENT")
    d = sp["daily"].set_index("t")
    assert sp["max_gross"] <= 1.0 + 1e-12
    t = int(days[2])
    assert d.at[t, "n_event"] == 5 and d.at[t + 1, "n_event"] == 5 and d.at[t + 2, "n_event"] == 0
    assert d.at[t, "traded"] == pytest.approx(5 * cmp.W)          # five buys
    assert d.at[t + 2, "traded"] == pytest.approx(5 * cmp.W)      # five sells at the reaction open


def test_fillers_take_only_empty_slots_and_prefer_the_most_volatile_operating_company():
    p = _panel()
    m = cmp.market(p)
    days = np.arange(80, 90)
    empty = pd.DataFrame(columns=["symbol", "ci", "pre_i", "react_i", "trail_abs", "on_cadence"])
    op = np.zeros(len(p.syms), dtype=bool)
    op[[p.col[f"S{k}"] for k in range(9)]] = True
    cur = cmp.season_path(days, empty, m, "CURRENT", operating=op)["daily"]
    fil = cmp.season_path(days, empty, m, "CURRENT_FILL", operating=op)["daily"]
    assert (cur.gross == 0).all()
    assert (fil.n_fill == 5).all() and fil.gross.max() == pytest.approx(1.0)
    # the five most volatile names are held, and a filler kept is not traded again
    top5 = set(np.argsort(-m.sig[int(days[0])][op.nonzero()[0]])[:5])
    assert {p.col[f"S{k}"] for k in range(4, 9)} == {op.nonzero()[0][i] for i in top5}
    assert fil.traded.iloc[1:-1].sum() == pytest.approx(0.0)


def test_the_null_removes_drift_and_the_bootstrap_keeps_it():
    rng = np.random.default_rng(1)
    book = np.full(23, 0.02)
    bench = np.zeros(23)
    cost = np.zeros(23)
    real = cmp.rel_paths(book, bench, cost)
    assert real > 0.5
    nul = cmp.probs(cmp.null_draws(book, bench, cost, rng, 4000))
    boot = cmp.probs(cmp.boot_draws(book, bench, cost, rng, 4000, 23))
    assert nul["median"] < 0.05 and boot["P>+40%"] == 1.0


def test_ibes_overnight_times_are_untimed_and_release_times_are_new_york(tmp_path):
    d = pd.Timestamp(_sess()[10])
    a = pd.DataFrame({"oftic": ["AAA", "BBB", "CCC"], "measure": "EPS", "pdicity": "QTR", "usfirm": 1,
                      "anndats": [d, d, d], "anntims": ["02:00:00", "16:05:00", None]})
    p = tmp_path / "ibes.parquet"
    a.to_parquet(p)
    s = cmp.ibes_stamps(p).set_index("symbol")
    assert cc.stamp_timing(s.at["AAA", "ts_utc"], "AAA") == (d, "UNKNOWN")
    assert cc.stamp_timing(s.at["BBB", "ts_utc"], "BBB") == (d, "AMC")
    assert cc.stamp_timing(s.at["CCC", "ts_utc"], "CCC") == (d, "UNKNOWN")


def test_dead_symbols_are_names_whose_bars_stop_early():
    p = _panel()
    j = p.col["S3"]
    p.close[-40:, j] = np.nan
    assert cmp.dead_symbols(p) == {"S3"}
