"""Contest desk: reused tickers are cut, and the nn_lab size-of-move column is read PIT.

Synthetic bars and files only, dates derived from today, no network."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts import contest_calendar as cc
from scripts import contest_desk as desk

TODAY = date.today()
NO_REGS = {"by_ticker": {}, "cik_first": None, "sources": ["test"]}


def _walk(sym: str, days: pd.DatetimeIndex, px: float, vol: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = px * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"symbol": sym, "date": days, "open": o, "close": c,
                         "volume": np.full(len(days), vol)})


def _stitched_world(sym: str = "ZZZ.HK"):
    """An old company at ~$2 until ~400 sessions ago, a 60-session hole, a new one at ~$25."""
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=900)
    old = _walk(sym, days[:400], 2.0, 5e6, 1)
    new = _walk(sym, days[460:], 25.0, 5e6, 2)
    other = _walk("KEEP.HK", days, 10.0, 5e6, 3)
    return days, pd.concat([old, new, other], ignore_index=True)


def test_cut_stitched_renames_the_old_company_and_keeps_every_row():
    days, bars = _stitched_world()
    bars["src"] = "bars_HK"
    out = cc.cut_stitched(bars, "HK", regs=NO_REGS)
    assert len(out) == len(bars)                                   # rows never dropped
    assert "ZZZ.HK#1" in set(out.symbol)
    living = out[out.symbol == "ZZZ.HK"]
    assert living.date.min() == days[460]                          # history starts at the new company
    assert (out[out.symbol == "ZZZ.HK#1"].date.max()) == days[399]
    assert "ZZZ.HK" in cc.stitched_cut_symbols()
    assert "KEEP.HK" not in cc.stitched_cut_symbols()
    assert set(out[out.symbol == "KEEP.HK"].date) == set(days)     # an intact name is untouched


def test_us_suspension_by_the_same_registrant_is_kept():
    days, bars = _stitched_world("SUSP")
    bars = bars[bars.symbol == "SUSP"].copy()
    bars["src"] = "bars"
    regs = {"by_ticker": {"SUSP": {"cik": 1, "first_filed": pd.Timestamp(days[0]) - pd.Timedelta(days=900),
                                   "source": "test"}},
            "cik_first": None, "sources": ["test"]}
    out = cc.cut_stitched(bars, "US", regs=regs)
    assert set(out.symbol) == {"SUSP"}
    assert cc.STITCH_AUDIT["US"]["kept_as_suspension"] == ["SUSP"]


def test_load_bars_usd_applies_the_cut(tmp_path, monkeypatch):
    days, bars = _stitched_world()
    monkeypatch.setattr(cc, "BARS_DIR", tmp_path)
    monkeypatch.setattr(cc, "latest_universe", lambda: None)
    bars.to_parquet(tmp_path / "bars_HK.parquet", index=False)
    fx = pd.DataFrame({"symbol": "HKD=X", "date": days, "open": 7.8, "close": 7.8, "volume": 0.0})
    fx.to_parquet(tmp_path / "bars_FX.parquet", index=False)
    out = cc.load_bars_usd(["HK"], include_us=False)
    assert "ZZZ.HK#1" in set(out.symbol)
    assert out[out.symbol == "ZZZ.HK"].date.min() == days[460]
    np.testing.assert_allclose(out[out.symbol == "KEEP.HK"].close.to_numpy(),
                               bars[bars.symbol == "KEEP.HK"].close.to_numpy() / 7.8, rtol=1e-6)


def test_earnings_stamps_before_the_new_company_never_become_its_events():
    days, bars = _stitched_world()
    bars["src"] = "bars_HK"
    cut = cc.cut_stitched(bars, "HK", regs=NO_REGS).drop(columns=["src"])
    panel = desk.panel_from_long(cut)
    stamps = []
    for i in list(range(100, 400, 63)) + list(range(520, 900, 63)):
        d = days[i]
        stamps.append({"symbol": "ZZZ.HK", "source": "test",
                       "ts_utc": pd.Timestamp(datetime(d.year, d.month, d.day, 17, 0),
                                              tz="Asia/Hong_Kong").tz_convert("UTC")})
    ev = desk.build_events(panel, pd.DataFrame(stamps))
    z = ev[ev.symbol == "ZZZ.HK"]
    assert len(z) > 0
    assert (z.react_date.dropna() >= days[460]).all()
    assert (pd.to_datetime(z.ts_utc, utc=True).dt.tz_convert(None) >= days[460]).all()


def _size_file(folder, d: date, rows: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": t, "exp_abs_move_5": v, "exp_abs_move_21": 2 * v, "hi90_5": 3 * v}
                  for t, v in rows.items()]).to_parquet(folder / f"size_{d}.parquet", index=False)


def test_nn_size_forecast_uses_only_a_file_dated_before_the_sheet(tmp_path):
    asof = TODAY
    _size_file(tmp_path, asof - timedelta(days=5), {"AAA": 0.01, "BBB": 0.02})
    _size_file(tmp_path, asof - timedelta(days=2), {"AAA": 0.03})
    _size_file(tmp_path, asof, {"AAA": 0.99})                     # same day: not yet knowable
    _size_file(tmp_path, asof + timedelta(days=3), {"AAA": 0.99})
    got, name = desk.nn_size_forecast(["AAA", "BBB", "CCC"], asof, folder=tmp_path)
    assert name == f"size_{asof - timedelta(days=2)}.parquet"
    assert got.at["AAA", "nn_size_5d"] == pytest.approx(0.03)
    assert "BBB" not in got.index                                  # not in the chosen file
    assert "CCC" not in got.index
    none, nm = desk.nn_size_forecast(["AAA"], asof - timedelta(days=30), folder=tmp_path)
    assert nm is None and none.empty


def test_sheet_shows_the_nn_size_column_without_reranking(tmp_path, monkeypatch):
    from backend.tests.test_contest_desk import _long_bars, _stamps, _sheet_day
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=420)
    bars = _long_bars({"AAA": (50, 1e6), "BBB": (20, 2e6), "LOWV": (5, 1e3), "CCC.T": (30, 1e6)}, days)
    panel = desk.panel_from_long(bars)
    raw = pd.DataFrame(_stamps("AAA", days) + _stamps("BBB", days, hm=(7, 0)) + _stamps("LOWV", days)
                       + _stamps("CCC.T", days, hm=(15, 45), tz="Asia/Tokyo"))
    world = {"days": days, "bars": bars, "panel": panel, "raw": raw,
             "events": desk.build_events(panel, raw)}
    d = _sheet_day(world)
    s0 = desk.make_sheet(d, world["events"], panel, None)
    _size_file(tmp_path, d - timedelta(days=1), {"AAA": 0.2, "BBB": 0.001})
    monkeypatch.setattr(desk, "NN_SIZE_DIR", tmp_path)
    s1 = desk.make_sheet(d, world["events"], panel, None)
    assert list(s0.buys.symbol) == list(s1.buys.symbol)            # display only
    assert s1.buys.set_index("symbol").at["AAA", "nn_size_5d"] == pytest.approx(0.2)
    md, _ = desk.render_sheet(s1)
    assert "NN size 5d" in md and "20.0%" in md


def test_season_table_prints_every_season_without_pooling():
    from scripts import contest_rotation_sim as sim
    df = pd.DataFrame([{"window": w, "rule": r, "fill": "next_open", "P>+40%": p, "median": -0.01}
                       for w, p in (("2024-Oct", 0.1), ("2025-Oct", 0.2)) for r in ("ROT_ALL", "HIVOL_BH")])
    lines = sim.season_table(df, "next_open")
    assert any(ln.startswith("| 2024-Oct |") for ln in lines)
    assert any(ln.startswith("| 2025-Oct |") and "20.0%" in ln for ln in lines)


def test_a_report_after_the_last_bar_never_borrows_the_last_bar_as_its_buy_session():
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=10), periods=300)
    panel = desk.panel_from_long(_walk("FUT", days, 10.0, 5e6, 4))
    far = days[-1] + pd.Timedelta(days=30)
    last = days[-1]
    raw = pd.DataFrame([
        {"symbol": "FUT", "source": "test",
         "ts_utc": pd.Timestamp(datetime(far.year, far.month, far.day, 16, 5), tz="America/New_York").tz_convert("UTC")},
        {"symbol": "FUT", "source": "test",
         "ts_utc": pd.Timestamp(datetime(last.year, last.month, last.day, 16, 5), tz="America/New_York").tz_convert("UTC")}])
    ev = desk.build_events(panel, raw).sort_values("ts_utc")
    assert pd.isna(ev.iloc[-1].pre_date)                   # the future report: no buy session from bars
    assert ev.iloc[0].pre_date == last                     # a report after the last bar's close: bought at it
