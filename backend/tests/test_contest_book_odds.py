"""scripts.contest_book_odds on synthetic bars (dates derived from today, no network)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scripts import contest_book_odds as C


def _bars(n: int = 600, sigmas=None, seed: int = 7, rho: float = 0.0) -> pd.DataFrame:
    """Synthetic long bars ending on the last business day before today."""
    sigmas = sigmas or {"AAA": 0.03, "BBB": 0.02, "CCC": 0.04, "DDD": 0.025, "EEE": 0.05,
                        "SPY": 0.01}
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(date.today()) - pd.offsets.BDay(1)
    dates = pd.bdate_range(end=end, periods=n)
    common = rng.standard_normal(n)
    rows = []
    for s, sd in sigmas.items():
        z = np.sqrt(rho) * common + np.sqrt(1 - rho) * rng.standard_normal(n)
        close = 50.0 * np.exp(np.cumsum(sd * z))
        rows.append(pd.DataFrame({"symbol": s, "date": dates, "close": close}))
    return pd.concat(rows, ignore_index=True)


def _lr(**kw) -> pd.DataFrame:
    b = _bars(**kw)
    return C.wide_log_returns(b, b["symbol"].unique())


def test_weight_above_cap_refuses_by_name():
    lr = _lr()
    with pytest.raises(C.BookRefused, match="AAA.*20% position cap"):
        C.validate_book({"AAA": 0.25, "BBB": 0.2}, lr.columns)


def test_weights_must_sum_to_at_most_one():
    lr = _lr()
    w = {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.2, "SPY": 0.2}
    with pytest.raises(C.BookRefused, match="sum to 1.2"):
        C.validate_book(w, lr.columns)
    C.validate_book({k: 0.2 for k in ("AAA", "BBB", "CCC", "DDD", "EEE")}, lr.columns)
    C.validate_book({"AAA": 0.2}, lr.columns)          # cash is allowed by the tool


def test_negative_weight_and_missing_ticker_refuse_by_name():
    lr = _lr()
    with pytest.raises(C.BookRefused) as ex:
        C.validate_book({"AAA": -0.1, "ZZZZ": 0.1}, lr.columns)
    assert "AAA: negative" in str(ex.value) and "ZZZZ: no bars" in str(ex.value)


def test_cli_refuses_with_exit_2_and_writes_receipt(tmp_path, monkeypatch):
    b = _bars()
    monkeypatch.setattr(C, "load_bars", lambda opt, syms: b)
    rc = C.main(["--book", "bad=AAA:0.3,BBB:0.2", "--book", "ok=AAA:0.2,BBB:0.2",
                 "--draws", "500", "--out-dir", str(tmp_path)])
    assert rc == 2
    rec = json.loads(next(tmp_path.glob("odds_*.json")).read_text(encoding="utf-8"))
    assert "bad" in rec["refused"] and "ok" in rec["books"]
    assert rec["run_id"] and rec["llm_spend_usd"] == 0.0


def test_one_name_book_sigma_equals_the_names():
    lr = _lr()
    s_name = float(np.expm1(lr["CCC"]).std(ddof=1))
    assert C.book_sigma_daily({"CCC": 1.0}, lr) == pytest.approx(s_name, rel=1e-12)
    assert C.book_sigma_daily({"CCC": 0.2}, lr) == pytest.approx(0.2 * s_name, rel=1e-12)


def test_bootstrap_agrees_with_normal_on_normal_data():
    # modest vols: the normal estimate ignores buy-and-hold compounding skew, which is
    # small here and large for 5%/day names (that gap is a finding, not a tolerance)
    lr = _lr(n=1500, rho=0.3, seed=11, sigmas={"AAA": 0.015, "BBB": 0.01, "CCC": 0.02,
                                               "DDD": 0.012, "EEE": 0.018, "SPY": 0.008})
    w = {k: 0.2 for k in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    lr = C.lookback_slice(lr, 1400, list(w) + ["SPY"])
    t = (0.03, 0.08)
    nrm = C.normal_odds(w, "SPY", lr, 23, t)
    blk = C.block_bootstrap(w, "SPY", lr, 23, t, n_draws=40_000, seed=3)
    assert blk["sd"] == pytest.approx(nrm["sd"], rel=0.10)
    for k in nrm["p_beat"]:
        assert blk["p_beat"][k] == pytest.approx(nrm["p_beat"][k], abs=0.03)
    win = C.window_bootstrap(w, "SPY", lr, 23, t)
    assert win["sd"] == pytest.approx(nrm["sd"], rel=0.25)


def test_short_history_refuses_by_name():
    b = _bars(n=100)
    lr = C.wide_log_returns(b, b["symbol"].unique())
    with pytest.raises(C.BookRefused, match="for a 252-session lookback"):
        C.lookback_slice(lr, 252, ["AAA"])


def test_earnings_jumps_raise_the_tail():
    lr = _lr(n=400, seed=5)
    idx = lr.index
    ek = pd.DataFrame({"ticker": "AAA", "items_joined": "2.02,9.01",
                       "filing_date": [str(idx[i].date()) for i in range(40, 400, 63)]})
    for i in range(40, 400, 63):                      # plant +/-25% reactions
        lr.iloc[i, lr.columns.get_loc("AAA")] = 0.25 if (i // 63) % 2 else -0.25
    w = {"AAA": 0.2, "BBB": 0.2}
    sl = C.lookback_slice(lr, 252, list(w) + ["SPY"])
    jumps, masks = C.earnings_reactions(ek, sl, list(w))
    assert "AAA" in jumps and "BBB" not in jumps
    base = C.block_bootstrap(w, "SPY", sl, 23, (0.05,), n_draws=5000, seed=1)
    ev2 = C.block_bootstrap(w, "SPY", sl, 23, (0.05,), n_draws=5000, seed=1,
                            event_jumps=jumps, event_masks=masks, events_per_slot=2)
    assert ev2["sd"] > base["sd"]
