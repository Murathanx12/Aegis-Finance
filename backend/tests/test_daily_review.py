"""u_review: the patience rule, UNPRICED rows, label forecasts.

Dates derive from `date.today()` (protocol item 5).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.services import daily_review as DR


def _bars(tickers, *, n=90, last_move=None, seed=0, end=None):
    """Quiet random walks (daily sd 1%) ending `end`; `last_move` sets the
    final day's return per ticker."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end or date.today())
    dates = pd.bdate_range(end=end, periods=n)
    rows = []
    for t in tickers:
        r = rng.normal(0, 0.01, n)
        if last_move and t in last_move:
            r[-1] = last_move[t]
        px = 100 * np.cumprod(1 + r)
        rows += [{"symbol": t, "date": d, "close": c} for d, c in zip(dates, px)]
    return pd.DataFrame(rows), str(dates[-1].date())


def _book(*tickers, source="murat_book", cap=1.0):
    return [{"source": source, "max_single_name": cap,
             "positions": [{"ticker": t, "shares": 100} for t in tickers]}]


def test_a_three_sigma_drop_is_watch_not_sell():
    bars, asof = _bars(["AAA", "BBB"], last_move={"AAA": -0.03})
    # a forecast that would SELL (p < 0.40) on AAA
    fc = {"AAA": {5: {"probability": 0.30}}}
    r = DR.review_holdings(asof, bars=bars, books=_book("AAA", "BBB"), forecasts=fc)
    row = {x["ticker"]: x for x in r["rows"]}["AAA"]
    assert row["z_1d"] < -2
    assert row["label"] == "WATCH"
    assert row["base_label"] == "sell"
    assert "decide next session" in row["reason"]


def test_sell_is_allowed_the_following_session():
    bars, asof = _bars(["AAA"], last_move={"AAA": -0.03})
    fc = {"AAA": {5: {"probability": 0.30}}}
    r = DR.review_holdings(asof, bars=bars, books=_book("AAA"), forecasts=fc,
                           watched={("murat_book", "AAA")})
    row = r["rows"][0]
    assert row["label"] == "sell"
    assert "WATCH last session" in row["reason"]


def test_trim_is_allowed_the_following_session():
    bars, asof = _bars(["AAA", "BBB"], last_move={"AAA": 0.04})
    books = [{"source": "pc_paper", "max_single_name": 0.12,
              "positions": [{"ticker": "AAA", "weight": 0.30},
                            {"ticker": "BBB", "weight": 0.05}]}]
    day1 = DR.review_holdings(asof, bars=bars, books=books)
    assert {x["ticker"]: x for x in day1["rows"]}["AAA"]["label"] == "WATCH"
    day2 = DR.review_holdings(asof, bars=bars, books=books,
                              watched={("pc_paper", "AAA")})
    assert {x["ticker"]: x for x in day2["rows"]}["AAA"]["label"] == "trim"


def test_a_jump_is_not_a_buy_more_on_the_day_either():
    bars, asof = _bars(["AAA"], last_move={"AAA": 0.05})
    r = DR.review_holdings(asof, bars=bars, books=_book("AAA"),
                           forecasts={"AAA": {1: {"probability": 0.70}}})
    assert r["rows"][0]["label"] == "WATCH"
    assert r["rows"][0]["base_label"] == "buy_more"


def test_a_quiet_day_takes_decide_labels_answer():
    bars, asof = _bars(["AAA"], last_move={"AAA": 0.001})
    r = DR.review_holdings(asof, bars=bars, books=_book("AAA"),
                           forecasts={"AAA": {5: {"probability": 0.30}}})
    assert r["rows"][0]["label"] == "sell"


def test_a_held_ticker_absent_from_the_panel_is_unpriced_not_skipped():
    bars, asof = _bars(["AAA"])
    r = DR.review_holdings(asof, bars=bars, books=_book("AAA", "ZZZZ"))
    rows = {x["ticker"]: x for x in r["rows"]}
    assert set(rows) == {"AAA", "ZZZZ"}
    assert rows["ZZZZ"]["label"] == "UNPRICED"
    assert r["counts"]["UNPRICED"] == 1


def test_an_unavailable_book_is_reported():
    bars, asof = _bars(["AAA"])
    books = _book("AAA") + [{"source": "pc_paper", "unavailable": "no creds",
                             "positions": []}]
    r = DR.review_holdings(asof, bars=bars, books=books)
    assert r["unavailable"] == [{"source": "pc_paper", "why": "no creds"}]


def test_sigma_excludes_the_move_it_measures():
    s = DR.price_stats([100.0] * 10 + [100.0 * (1.01 ** i) for i in range(70)]
                       + [50.0])
    # a halving is enormous against the prior 63 days, whatever it does to sd
    assert s["z_1d"] < -10


def test_intraday_live_price_uses_last_close():
    closes = list(100 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 80)))
    s = DR.price_stats(closes, live_price=closes[-1] * 0.95)
    assert s["ret_1d"] == pytest.approx(-0.05, abs=1e-6)
    assert s["z_1d"] < -2


def test_intraday_triggers_skip_names_already_rereviewed():
    table = {"AAA": {"last_close": 100.0, "sigma_63": 0.01},
             "BBB": {"last_close": 100.0, "sigma_63": 0.01}}
    trig = DR.intraday_triggers(table, {"AAA": 96.0, "BBB": 100.5}, already=())
    assert [t["ticker"] for t in trig] == ["AAA"]
    assert DR.intraday_triggers(table, {"AAA": 96.0}, already=["AAA"]) == []


def test_prior_watch_reads_the_latest_earlier_review(tmp_path):
    today = date.today()
    y = (today - timedelta(days=1)).isoformat()
    old = (today - timedelta(days=5)).isoformat()
    (tmp_path / f"review_{old}.json").write_text(json.dumps(
        {"rows": [{"source": "murat_book", "ticker": "OLD", "label": "WATCH"}]}))
    (tmp_path / f"review_{y}.json").write_text(json.dumps(
        {"rows": [{"source": "murat_book", "ticker": "AAA", "label": "WATCH"},
                  {"source": "murat_book", "ticker": "BBB", "label": "hold"}]}))
    assert DR.prior_watch(today.isoformat(), review_dir=tmp_path) == {
        ("murat_book", "AAA")}


def test_run_daily_writes_review_morning_and_label_rows(tmp_path):
    bars, asof = _bars(["AAA", "BBB"], last_move={"AAA": -0.03})
    ledger = tmp_path / "predictions.jsonl"
    snap = {"equity": 1000.0, "positions": [
        {"symbol": "BBB", "qty": 1, "market_value": 100.0}]}
    res = DR.run_daily(asof=asof, bars=bars, snapshot=snap, review_dir=tmp_path,
                       ledger_path=ledger)
    rv = json.loads((tmp_path / f"review_{asof}.json").read_text(encoding="utf-8"))
    md = (tmp_path / f"morning_{asof}.md").read_text(encoding="utf-8")
    assert len(md.strip().splitlines()) <= 15
    assert "pc_paper" in {r["source"] for r in rv["rows"]}
    # WATCH and UNPRICED mint nothing; every decisive label is one h=5 row
    decisive = [r for r in rv["rows"] if r["label"] in DR.LABEL_PROBABILITY]
    minted = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(minted) == len(decisive) == res["n_minted"]
    assert all(m["specialist"] == "review:v0" and m["horizon_days"] == 5
               for m in minted)


def test_intraday_rereview_never_mints(tmp_path):
    bars, asof = _bars(["BBB"])
    ledger = tmp_path / "predictions.jsonl"
    snap = {"equity": 1000.0, "positions": [
        {"symbol": "BBB", "qty": 1, "market_value": 100.0}]}
    res = DR.run_daily(asof=asof, bars=bars, snapshot=snap, review_dir=tmp_path,
                       ledger_path=ledger, live_prices={"BBB": 90.0},
                       intraday_tag="1030")
    assert res["n_minted"] == 0 and not ledger.exists()
    assert (tmp_path / f"review_{asof}_intraday_1030.json").exists()
