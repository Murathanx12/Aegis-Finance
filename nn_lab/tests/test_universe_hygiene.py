"""Universe hygiene (2026-09-30): ETFs out, reused dead tickers kept as their own dead name,
CRSP-recovered deaths verified against CRSP returns. Synthetic data, dates from today."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from nn_lab import config as C
from nn_lab import deaths_crsp as D
from nn_lab import table as T
from nn_lab import universe_filter as U


def _cal(n):
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


def _bars(cal, syms, seed=5):
    rng = np.random.default_rng(seed)
    out = []
    for s in syms:
        c = 30 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(cal))))
        out.append(pd.DataFrame({"symbol": s, "date": cal, "open": c, "high": c * 1.01, "low": c * 0.99,
                                 "close": c, "volume": np.full(len(cal), 5e5, dtype="float32"),
                                 "vwap": c, "trades": np.full(len(cal), 2000.0)}))
    return pd.concat(out, ignore_index=True)


def test_a_planted_etf_never_reaches_the_table(tmp_path, monkeypatch):
    cal = _cal(300)
    b = _bars(cal, [C.MARKET, "AAA", "FUNDX"])
    ex = tmp_path / "etf.json"
    ex.write_text(json.dumps({"symbols": {"FUNDX": {"source": "test", "name": "Planted 3X Daily ETF"}}}))
    monkeypatch.setattr(C, "ETF_EXCLUSIONS", ex)
    monkeypatch.setattr(C, "EXCLUDE_ETFS", True)
    U._CACHE.clear()
    rows = T.price_rows(b, T.session_calendar(b), keep_dates=None)
    assert "FUNDX" not in set(rows["symbol"]) and "AAA" in set(rows["symbol"])
    monkeypatch.setattr(C, "EXCLUDE_ETFS", False)
    rows2 = T.price_rows(b, T.session_calendar(b), keep_dates=None)
    assert "FUNDX" in set(rows2["symbol"])
    U._CACHE.clear()


def test_fund_names_are_funds_and_trusts_that_are_companies_are_not():
    assert U.is_fund_name("iPath Series B S&P 500 VIX Short-Term Futures ETN")
    assert U.is_fund_name("Direxion Daily Natural Gas Bear 3X Shares")
    assert U.is_fund_name("SPDR Gold Trust")
    assert not U.is_fund_name("Healthcare Realty Trust Incorporated")
    assert not U.is_fund_name("WisdomTree, Inc.")
    assert not U.is_fund_name("Apple Inc. Common Stock")


def test_a_ticker_crsp_lists_as_a_company_during_its_bars_is_kept():
    months = {"EV": {"2019-05", "2020-01"}, "VXX": {"2019-05"}}
    crsp = {"EV": {"2019-05"}}
    assert U.company_in_its_life(months, crsp) == {"EV"}


def test_a_dead_company_whose_ticker_was_reused_becomes_its_own_dead_name(tmp_path, monkeypatch):
    cal = _cal(400)
    b = _bars(cal, [C.MARKET, "S00", "S01"])
    live = b[(b["symbol"] == "S00") & (b["date"] >= cal[250])]
    dead = b[(b["symbol"] == "S01") & (b["date"] < cal[150])].assign(symbol="S00")
    overlap = b[(b["symbol"] == "S01") & (b["date"] >= cal[200]) & (b["date"] < cal[300])].assign(symbol="S00")
    p1, p2, p3 = tmp_path / "l.parquet", tmp_path / "d.parquet", tmp_path / "o.parquet"
    pd.concat([live, b[b["symbol"] == C.MARKET]]).to_parquet(p1)
    dead.to_parquet(p2)
    overlap.to_parquet(p3)
    monkeypatch.setattr(C, "RENAME_REUSED_DEAD", True)
    out = T.load_bars([p1, p2])
    assert len(out[out["symbol"] == "S00"]) == 150 and len(out[out["symbol"] == "S00#d"]) == 150
    out2 = T.load_bars([p1, p3])                       # overlapping histories: still dropped
    assert "S00#d" not in set(out2["symbol"]) and len(out2[out2["symbol"] == "S00"]) == 150
    monkeypatch.setattr(C, "RENAME_REUSED_DEAD", False)
    out3 = T.load_bars([p1, p2])
    assert "S00#d" not in set(out3["symbol"])


def test_crsp_death_is_kept_only_inside_its_life_and_only_if_returns_match():
    cal = _cal(200)
    b = _bars(cal, ["DEADX", "WRONG"], seed=9)
    b = b.assign(date=pd.to_datetime(b["date"]))
    r = b.sort_values(["symbol", "date"]).copy()
    r["ret"] = r.groupby("symbol")["close"].pct_change()
    deaths = pd.DataFrame({"permno": [1, 2], "ticker": ["DEADX", "WRONG"],
                           "first": [cal[20], cal[0]], "last": [cal[150], cal[180]]})
    rets = pd.concat([r[r["symbol"] == "DEADX"].assign(permno=1)[["permno", "date", "ret"]],
                      r[r["symbol"] == "WRONG"].assign(permno=2, ret=np.random.default_rng(1).normal(0, 0.02, 200))
                      [["permno", "date", "ret"]]])
    kept, rep = D.verify_and_trim(b, deaths, rets)
    assert set(kept["symbol"]) == {"DEADX"} and rep["mismatch"] == 1
    k = kept[kept["symbol"] == "DEADX"]
    assert k["date"].min() >= cal[20] and k["date"].max() <= cal[150] + pd.Timedelta(days=D.TAIL_DAYS)


def test_crsp_death_colliding_with_a_panel_ticker_is_renamed_never_spliced():
    df = pd.DataFrame({"symbol": ["AAA"] * 3 + ["BBB"] * 2, "permno": [1, 1, 1, 2, 2],
                       "date": pd.to_datetime(["2001-01-02", "2001-01-03", "2001-01-04", "2001-01-02", "2001-01-03"])})
    out, ren = D.rename_collisions(df, taken={"AAA"})
    assert set(out["symbol"]) == {"AAA#c", "BBB"} and ren == ["AAA#c"]


def test_a_split_after_t_leaves_close_raw_at_t_unchanged():
    from nn_lab import raw_prices as RP
    cal = _cal(260)
    raw = pd.Series(np.linspace(100, 140, len(cal)), index=cal)
    split_day = cal[200]                               # 4:1 split AFTER t = cal[150]
    def adjusted(split_after_pull: bool):
        f = np.where(cal < split_day, 4.0, 1.0) if split_after_pull else np.ones(len(cal))
        rp = raw.values / np.where(cal < split_day, 1.0, 4.0)   # the raw price drops at the split
        return pd.DataFrame({"symbol": "AAA", "date": cal, "close": rp / (f if split_after_pull else 1.0)}), rp
    adj, rp = adjusted(True)
    months = pd.DataFrame({"symbol": "AAA", "date": cal, "close_raw": rp})
    months["month"] = months["date"].dt.strftime("%Y-%m")
    monthly = months.groupby("month").tail(1)[["symbol", "month", "close_raw"]]
    ratios = RP.month_end_ratios(adj, monthly)
    out = RP.attach_close_raw(adj, ratios)
    t = 150
    # true raw close at t, known without the future split
    got = out.loc[out["date"] == cal[t], "close_raw"].iloc[0]
    assert abs(got - rp[t]) / rp[t] < 1e-9
    # and a row long after the split is also right (the split is then in the past)
    got2 = out.loc[out["date"] == cal[-1], "close_raw"].iloc[0]
    assert abs(got2 - rp[-1]) / rp[-1] < 1e-9


def test_a_ticker_kept_by_a_merger_is_not_a_death():
    df = pd.DataFrame({"symbol": ["JCX"] * 2 + ["OLDX"] * 2, "permno": [1, 1, 2, 2],
                       "date": pd.to_datetime(["2001-01-02", "2001-06-01", "2001-01-02", "2001-06-01"])})
    spans = pd.DataFrame({"first_other": pd.to_datetime(["2001-03-01"]), "last_other": pd.to_datetime(["2009-01-01"])},
                         index=pd.Index(["JCX"], name="symbol"))
    out, dropped = D.drop_overlaps(df, spans)
    assert set(out["symbol"]) == {"OLDX"} and dropped == ["JCX"]
