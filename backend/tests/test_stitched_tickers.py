"""Stitched tickers (review 2026-09-29 F4): synthetic bars, dates derived from today, offline."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.services import stitched_tickers as ST
from backend.services import xs_ranker as XR


def _cal(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


def _series(sym: str, dates, start_px: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0005, 0.02, len(dates))
    c = start_px * np.exp(np.cumsum(r))
    return pd.DataFrame({"symbol": sym, "date": dates, "open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 5e5, "vwap": c, "trades": 2000.0})


def _panel(n=700, *, old_px=2.0, new_px=23.0):
    """SPY + a clean name + JAN: an old company for 300 sessions, a 200-session hole,
    then a new company for the last 200 sessions."""
    cal = _cal(n)
    old = _series("JAN", cal[:300], old_px, 1)
    new = _series("JAN", cal[500:], new_px, 2)
    return cal, pd.concat([_series("SPY", cal, 400.0, 3), _series("CLEAN", cal, 50.0, 4), old, new],
                          ignore_index=True)


NO_REGS = {"by_ticker": {}, "cik_first": pd.Series(dtype="datetime64[ns]"), "sources": []}


def test_a_reused_ticker_is_detected_from_the_registrant_and_cut():
    cal, b = _panel(old_px=20.0, new_px=21.0)             # prices continuous: only the CIK can tell
    regs = {"by_ticker": {"JAN": {"cik": 2_100_805, "first_filed": cal[520], "source": "test"}},
            "cik_first": pd.Series(dtype="datetime64[ns]"), "sources": ["test"]}
    g = ST.detect(b, regs=regs)
    row = g[g["symbol"] == "JAN"].iloc[0]
    assert row["verdict"] == "STITCHED"
    assert any(e.startswith("new_registrant") for e in row["evidence"])
    out, audit = ST.split_stitched(b, regs=regs)
    assert audit["cut_symbols"] == ["JAN"]
    jan = out[out["symbol"] == "JAN"]
    assert jan["date"].min() == cal[500] and len(jan) == 200
    assert out.loc[out["symbol"] == "JAN#1", "date"].max() == cal[299]
    assert len(out) == len(b)                                    # nothing dropped


def test_a_suspension_of_the_same_registrant_is_kept_joined():
    cal, b = _panel(old_px=18.9, new_px=20.0)
    regs = {"by_ticker": {"JAN": {"cik": 1_513_845, "first_filed": cal[0] - pd.Timedelta(days=900),
                                  "source": "test"}},
            "cik_first": pd.Series(dtype="datetime64[ns]"), "sources": ["test"]}
    g = ST.detect(b, regs=regs)
    assert g.iloc[0]["verdict"] == "SUSPENSION"
    out, audit = ST.split_stitched(b, regs=regs)
    assert audit["cut_symbols"] == [] and audit["kept_as_suspension"] == ["JAN"]
    assert (out["symbol"] == "JAN").sum() == 500


def test_price_jump_and_inactive_source_are_each_evidence():
    cal, b = _panel(old_px=2.0, new_px=23.0)
    g = ST.detect(b, regs=NO_REGS)
    assert g.iloc[0]["verdict"] == "STITCHED" and any("price_jump" in e for e in g.iloc[0]["evidence"])
    cal, b = _panel(old_px=20.0, new_px=21.0)
    b["_src"] = "bars"
    b.loc[(b["symbol"] == "JAN") & (b["date"] < cal[400]), "_src"] = "bars_delisted"
    g = ST.detect(b, src_col="_src", regs=NO_REGS)
    assert g.iloc[0]["verdict"] == "STITCHED" and any("inactive_source" in e for e in g.iloc[0]["evidence"])
    # no evidence at all: still cut (a window across the hole is not 12-1 momentum), but NAMED
    g = ST.detect(b.drop(columns="_src"), regs=NO_REGS)
    assert g.iloc[0]["verdict"] == "GAP_UNRESOLVED"
    assert "GAP_UNRESOLVED" in ST.CUT_VERDICTS


def test_short_gaps_are_not_candidates():
    cal = _cal(400)
    s = _series("HALT", cal, 30.0, 5)
    # consecutive bars exactly GAP_SESSIONS sessions apart: a halt, not a candidate
    ok = s[(s["date"] < cal[200]) | (s["date"] >= cal[199 + ST.GAP_SESSIONS])]
    assert ST.detect(pd.concat([_series("SPY", cal, 400.0, 3), ok]), regs=NO_REGS).empty
    # one session more is a candidate
    gap = s[(s["date"] < cal[200]) | (s["date"] >= cal[200 + ST.GAP_SESSIONS])]
    assert len(ST.detect(pd.concat([_series("SPY", cal, 400.0, 3), gap]), regs=NO_REGS)) == 1


@pytest.fixture
def _no_sec(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "SEC_FACTS_PATH", tmp_path / "none.parquet")
    monkeypatch.setattr(ST, "COMPANY_TICKERS_PATH", tmp_path / "none.json")
    ST._registrants_cached.cache_clear()
    yield
    ST._registrants_cached.cache_clear()


def test_the_live_reader_gives_a_stitched_ticker_no_momentum_until_it_has_its_own_window(tmp_path, _no_sec):
    cal, b = _panel(old_px=2.0, new_px=23.0)
    p = tmp_path / "bars.parquet"
    b.to_parquet(p)
    raw = XR.load_bars(p, split_stitched=False)
    cut = XR.load_bars(p)
    assert XR.LAST_STITCH_AUDIT["cut_symbols"] == ["JAN"]
    f_raw = XR.build_features(raw)
    f_cut = XR.build_features(cut)
    last = cal[-1]
    # the spliced reader compares the new company with the dead one ...
    assert np.isfinite(f_raw.loc[(f_raw["symbol"] == "JAN") & (f_raw["date"] == last), "mom_252_21"]).all()
    # ... the fixed reader has NO 12-1 momentum for it (200 own sessions < 252): NaN, never 0
    v = f_cut.loc[(f_cut["symbol"] == "JAN") & (f_cut["date"] == last), "mom_252_21"]
    assert len(v) == 1 and v.isna().all()
    assert f_cut.loc[f_cut["symbol"] == "JAN", "date"].min() == cal[500]
    # the unstitched name is byte-for-byte unchanged
    cols = ["mom_252_21", "mom_126", "vol_63", "px_vs_52w_high"]
    a = f_raw[f_raw["symbol"] == "CLEAN"][cols].reset_index(drop=True)
    c = f_cut[f_cut["symbol"] == "CLEAN"][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, c)


def test_a_stitched_ticker_gets_momentum_once_it_has_its_own_window(tmp_path, _no_sec):
    cal = _cal(900)
    b = pd.concat([_series("SPY", cal, 400.0, 3), _series("JAN", cal[:200], 2.0, 1),
                   _series("JAN", cal[400:], 23.0, 2)], ignore_index=True)
    p = tmp_path / "bars.parquet"
    b.to_parquet(p)
    f = XR.build_features(XR.load_bars(p))
    j = f[f["symbol"] == "JAN"].reset_index(drop=True)
    assert j["mom_252_21"].iloc[:252].isna().all()
    assert np.isfinite(j["mom_252_21"].iloc[252:]).all()
    new_close = b[(b["symbol"] == "JAN") & (b["date"] >= cal[400])]["close"].to_numpy()
    assert j["mom_252_21"].iloc[-1] == pytest.approx(new_close[-22] / new_close[-253] - 1.0)


def test_blast_radius_reads_and_never_writes(tmp_path):
    opt = tmp_path / "optimus"
    (opt / "llm_portfolio").mkdir(parents=True)
    books = opt / "llm_portfolio" / "books.jsonl"
    books.write_text('{"book_id": "b1", "name": "lib_mom", "kind": "personal", "positions": '
                     '[{"ticker": "JAN", "weight": 0.05}, {"ticker": "NVDA", "weight": 0.05}]}\n'
                     '{"book_id": "b2", "name": "x", "kind": "twin", "positions": [{"ticker": "AAPL", "weight": 1}]}\n',
                     encoding="utf-8")
    before = books.read_bytes()
    r = ST.blast_radius(["JAN"], optimus=opt)
    assert r["frozen_books"]["n_books_total"] == 2
    assert [b["book_id"] for b in r["frozen_books"]["books"]] == ["b1"]
    assert books.read_bytes() == before
