"""Broken price histories (2026-09-29): the bar-defect screen at the reader, the
book refusal, and the world digest's sector / macro proxies.

Offline, synthetic bars, every date derived from today (protocol item 5).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend import config as _cfg
from backend.services import bar_defects as BD
from backend.services import stitched_tickers as ST
from backend.services import world_digest as WD

N = 700


def _cal(n: int = N) -> pd.DatetimeIndex:
    end = pd.Timestamp.today().normalize() - pd.offsets.BDay(1)
    return pd.bdate_range(end=end, periods=n)


def _walk(n: int, seed: int, start: float = 50.0, sd: float = 0.015) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(0, sd, n)))


def _frame(sym: str, dates, close, volume=None) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    vol = np.full(len(close), 5e5) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({"symbol": sym, "date": dates, "open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close, "volume": vol})


@pytest.fixture(autouse=True)
def _no_registrants(monkeypatch):
    """No SEC files: the stitch verdict rests on price / source evidence alone."""
    monkeypatch.setattr(ST, "registrants", lambda *a, **k: {"by_ticker": {}, "cik_first": pd.Series(dtype="datetime64[ns]"),
                                                            "sources": []})
    monkeypatch.setattr(BD, "ENABLED", True)


def _panel(*frames) -> pd.DataFrame:
    cal = _cal()
    spy = _frame("SPY", cal, _walk(len(cal), 0, 400.0, 0.01), np.full(len(cal), 5e7))
    return pd.concat([spy, *frames], ignore_index=True)


def test_a_vendor_filled_hole_becomes_a_gap_and_the_reused_ticker_is_cut():
    cal = _cal()
    close = _walk(N, 1, 1.0)
    vol = np.full(N, 3e6)
    dark = slice(100, 500)                        # 400 flat zero-volume sessions
    close[dark] = close[99]
    vol[dark] = 0
    close[500:] = _walk(N - 500, 2, 75.0)         # the new company, ~75x the old level
    bars = _panel(_frame("LINE", cal, close, vol))
    out = ST.cut_reader_bars(bars)
    line = out[out["symbol"] == "LINE"]
    old = out[out["symbol"] == "LINE#1"]
    assert line["date"].min() == cal[500]         # the living symbol starts at the new company
    assert old["date"].max() == cal[99]           # the old one dies at its last TRADE
    assert (out.loc[out["symbol"].str.startswith("LINE"), "volume"] > 0).all()
    a = ST.LAST_AUDIT["defect_screen"]
    assert a["rows_removed_by_reason"]["DARK_RUN"] == 400
    assert a["dark_runs"][0]["sessions"] == 400 and a["dark_runs"][0]["symbol"] == "LINE"


def test_a_symbol_without_volume_information_is_left_alone():
    cal = _cal()
    bars = _panel(_frame("NOVOL", cal, _walk(N, 3), np.zeros(N)))
    out = ST.cut_reader_bars(bars)
    assert (out["symbol"] == "NOVOL").sum() == N


def test_a_clean_symbol_is_byte_for_byte_unchanged():
    cal = _cal()
    clean = _frame("CLEAN", cal, _walk(N, 4))
    out = ST.cut_reader_bars(_panel(clean))
    got = out[out["symbol"] == "CLEAN"].reset_index(drop=True)
    pd.testing.assert_frame_equal(got[clean.columns], clean.reset_index(drop=True), check_dtype=False)


def test_a_spike_that_reverts_is_a_bad_print_and_is_removed():
    cal = _cal()
    close = _walk(N, 5)
    close[300] = close[299] * 10.0                # one print at 10x, back the next day
    out = ST.cut_reader_bars(_panel(_frame("SPK", cal, close)))
    s = out[out["symbol"] == "SPK"]
    assert len(s) == N - 1 and cal[300] not in set(s["date"])
    assert set(out["symbol"]) == {"SPY", "SPK"}   # removed, not cut
    sp = ST.LAST_AUDIT["defect_screen"]["spikes"]
    assert sp[0]["symbol"] == "SPK" and sp[0]["rows"] == 1


def test_a_quiet_level_break_is_cut_and_a_loud_one_is_kept():
    cal = _cal()
    quiet = _walk(N, 6)
    quiet[400:] = quiet[400:] * 5.0               # 5x on ordinary volume
    loud = _walk(N, 7)
    loud[400:] = loud[400:] * 5.0
    lvol = np.full(N, 5e5)
    lvol[400] = 5e7                               # 100x volume: a market move
    mid = _walk(N, 8)
    mid[400:] = mid[400:] * 5.0
    mvol = np.full(N, 5e5)
    mvol[400] = 2.5e6                             # 5x volume: SUSPECT
    out = ST.cut_reader_bars(_panel(_frame("QUIET", cal, quiet), _frame("LOUD", cal, loud, lvol),
                                    _frame("MID", cal, mid, mvol)))
    syms = set(out["symbol"])
    assert {"QUIET", "QUIET#1"} <= syms
    assert out.loc[out["symbol"] == "QUIET", "date"].min() == cal[400]
    assert "LOUD#1" not in syms and (out["symbol"] == "LOUD").sum() == N
    assert "MID#1" not in syms
    a = ST.LAST_AUDIT["defect_screen"]
    assert [c["reason"] for c in a["cuts"]] == ["QUIET_LEVEL_BREAK"]
    assert [s["symbol"] for s in a["suspects"]] == ["MID"]


def test_a_level_break_across_a_short_dark_run_is_cut():
    cal = _cal()
    close = _walk(N, 9)
    vol = np.full(N, 5e5)
    close[300:306] = close[299]
    vol[300:306] = 0                              # six dark sessions (< the 20-session stitch gap)
    close[306:] = close[306:] * 4.0
    vol[306] = 5e7                                # heavy volume: rule C would keep it
    out = ST.cut_reader_bars(_panel(_frame("EMRG", cal, close, vol)))
    assert out.loc[out["symbol"] == "EMRG", "date"].min() == cal[306]
    assert [c["reason"] for c in ST.LAST_AUDIT["defect_screen"]["cuts"]] == ["GAP_LEVEL_BREAK"]


def test_the_screen_can_be_switched_off_for_the_audit_leg_only(monkeypatch):
    cal = _cal()
    close = _walk(N, 10)
    close[300] = close[299] * 10.0
    monkeypatch.setattr(BD, "ENABLED", False)
    out = ST.cut_reader_bars(_panel(_frame("SPK", cal, close)))
    assert (out["symbol"] == "SPK").sum() == N
    assert _cfg.BAR_DEFECT_SCREEN is True         # the reader default is ON


def test_flagged_keys_mark_a_suspect_inside_the_window_and_the_book_refuses():
    today = pd.Timestamp.today().normalize()
    d0, d1 = today - pd.Timedelta(days=60), today - pd.Timedelta(days=700)
    panel = pd.DataFrame({"date": [d0, d0, d1], "symbol": ["MID", "OK", "MID#1"]})
    sus = [{"symbol": "MID", "date": str((d0 - pd.Timedelta(days=30)).date()), "ratio": 5.0,
            "volume_ratio": 5.0}]
    fk = BD.flagged_keys(panel, sus)
    assert fk == {(d0, "MID")}                    # MID#1 at d1: the suspect is outside its window
    hold = [{"date": d0, "symbols": ["MID"] + [f"N{i}" for i in range(9)]}]
    with pytest.raises(BD.BarDefectRefusal):
        BD.assert_book_clean(hold, fk)            # 1 of 10 slots = 10% > 2%
    wide = [{"date": d0, "symbols": ["MID"] + [f"N{i}" for i in range(59)]}]
    r = BD.assert_book_clean(wide, fk)            # 1 of 60 = 1.7% <= 2%
    assert r["flagged_slots"] == 1 and not r["refuse"]


def test_implausible_rows_is_descriptive_and_missing_columns_never_flag():
    p = pd.DataFrame({"vol_63": [0.5, 9.0, np.nan], "mom_252_21": [0.2, 0.1, 50.0]})
    assert BD.implausible_rows(p).tolist() == [False, True, True]
    assert not BD.implausible_rows(pd.DataFrame({"x": [1.0]})).any()


# ── the world digest's proxies ──────────────────────────────────────────────

def _imp(**kw):
    d = {"subject": "semiconductors", "subject_type": "sector", "direction": "up",
         "size_bucket": "above_normal", "horizon_sessions": 5, "confidence": 0.8, "order": 1,
         "chain": "Capex follows pricing.", "contradiction": "Orders fall.", "mentioned": None}
    d.update(kw)
    return d


def test_subject_proxy_maps_sectors_flips_rates_and_takes_an_etf_name():
    assert WD.subject_proxy(_imp())["subject"] == "SMH"
    r = WD.subject_proxy(_imp(subject="rates", subject_type="macro", direction="up"))
    assert r["subject"] == "TLT" and r["direction"] == "down" and r["proxy_of"]["sign"] == -1
    assert WD.subject_proxy(_imp(subject="xlf"))["subject"] == "XLF"
    assert WD.subject_proxy(_imp(subject="robotics")) is None
    for tkr, sign in _cfg.WORLD_DIGEST_SUBJECT_PROXIES.values():
        assert tkr in _cfg.FORECAST_PROXY_ETFS and sign in (1, -1)


def test_a_macro_implication_is_written_on_its_proxy_with_the_subject_kept():
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.offsets.BDay(1), periods=300)
    px = pd.DataFrame({"TLT": _walk(300, 11, 90.0, 0.008), "SPY": _walk(300, 12, 500.0, 0.01)}, index=idx)
    made = (pd.Timestamp.today().normalize()).strftime("%Y-%m-%dT03:00:00+00:00")
    recs, why = WD.implication_records(
        _imp(subject="rates", subject_type="macro", direction="up"),
        theme={"title": "Yields", "urls": ["https://example.org/a"]}, digest_id="d", made_at=made,
        px=px, stitched=set(), model="m", prompt_hash="p", have=set())
    assert why == "OK" and {r.ticker for r in recs} == {"TLT"}
    dirn = next(r for r in recs if r.observable == "beats_benchmark")
    assert dirn.inputs_used["direction"] == "down"            # yields up -> TLT down
    assert dirn.inputs_used["proxy_of"] == {"subject": "rates", "subject_type": "macro",
                                            "direction": "up", "sign": -1}
    size = next(r for r in recs if r.observable == "abs_move_exceeds")
    sig = px["TLT"].pct_change().dropna().iloc[-63:].std()
    assert math.isclose(size.threshold, sig * math.sqrt(5), rel_tol=1e-4)


def test_the_puller_asks_only_for_proxies_the_main_panel_lacks():
    from scripts import pull_forecast_bars as PF
    got = PF.proxy_tickers({"SPY", "QQQ", "IWM", "TLT"})
    assert "TLT" not in got and "IWM" not in got and "XLU" in got
    from scripts import pull_bars_refresh as BR
    assert "forecast_only" in BR.PANELS and "forecast_only" not in BR.GATED_PANELS


def test_a_same_registrant_gap_with_a_level_break_is_cut_anyway():
    """A chapter 11 keeps the registrant (CIK) and cancels the shares: the stitch
    detector calls it a SUSPENSION, and the defect screen cuts it on the break."""
    cal = _cal()
    close = _walk(N, 13, 0.2)
    vol = np.full(N, 3e6)
    close[400:] = _walk(N - 400, 14, 20.0)
    bars = _panel(_frame("REORG", cal[:350], close[:350], vol[:350]),
                  _frame("REORG", cal[400:], close[400:], vol[400:]))
    regs = {"by_ticker": {"REORG": {"cik": 7, "first_filed": cal[0] - pd.Timedelta(days=900),
                                    "source": "test"}}, "cik_first": None, "sources": ["test"]}
    out, audit = ST.split_stitched(bars, src_col="nope", regs=regs)
    assert audit["kept_as_suspension"] == ["REORG"]
    assert audit["defect_cut_symbols"] == ["REORG"]
    assert out.loc[out["symbol"] == "REORG", "date"].min() == cal[400]
