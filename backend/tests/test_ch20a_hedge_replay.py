"""CH-20a hedge replay: fills at ask/bid, skipped days recorded, equal-drawdown twin.

All quotes are SYNTHETIC and written under tmp_path; no licensed row is used.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import ch20a_hedge_replay as R

SECID = R.SECIDS["SPY"]


def _spec() -> dict:
    return R.frozen_spec()["values"]


def _synthetic(n_days: int = 760, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    start = (pd.Timestamp.today().normalize() - pd.Timedelta(days=int(n_days * 1.5)))
    dates = pd.bdate_range(start, periods=n_days)
    r = rng.normal(0.0004, 0.011, n_days)
    r[300:320] = -0.02                                    # a crash the hedge can catch
    r[0] = 0.0
    close = 100.0 * np.cumprod(1.0 + r)
    under = pd.DataFrame({"secid": float(SECID), "date": dates.date, "close": close,
                          "cfadj": 1.0, "return": r})
    # Friday expiries every four weeks, starting on the first Friday after day 0.
    fri0 = dates[0] + pd.offsets.Week(weekday=4)
    exps = [fri0 + pd.Timedelta(days=28 * i) for i in range(n_days // 18)]
    rows = []
    for d, s in zip(dates, close):
        for ex in exps:
            dte = (ex - d).days
            if not 14 <= dte <= 45:
                continue
            for k in np.arange(np.floor(0.78 * s), np.ceil(0.99 * s) + 1):
                tv = 0.02 * s * np.sqrt(dte / 365.0) * np.exp(-3.0 * (1.0 - k / s))
                bid = max(k - s, 0.0) + tv
                rows.append({"secid": float(SECID), "date": d.date(), "exdate": ex.date(),
                             "cp_flag": "P", "strike": float(k), "best_bid": round(bid, 2),
                             "best_offer": round(bid + 0.05, 2), "ss_flag": "0",
                             "moneyness": float(k / s)})
    return under, pd.DataFrame(rows)


def _frames(under: pd.DataFrame, quotes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The loaders' output shape, built in memory (no parquet round trip)."""
    u = under.copy()
    u["date"] = pd.to_datetime(u["date"])
    u["ret"] = u["return"].astype(float)
    u["price_ret"] = u["close"].pct_change().fillna(0.0)
    u["ret_filled_from_price"] = False
    q = quotes.copy()
    q["date"] = pd.to_datetime(q["date"])
    q["exdate"] = pd.to_datetime(q["exdate"])
    return u, q


@pytest.fixture(scope="module")
def synth():
    return _synthetic()


def _expected_legs(q: pd.DataFrame, d: pd.Timestamp, spot: float, spec: dict):
    g = q[q["date"] == d]
    dte = (g["exdate"] - d).dt.days
    ok = g[(dte >= spec["CH20A_HEDGE_DTE_MIN"]) & (dte <= spec["CH20A_HEDGE_DTE_MAX"])]
    ex = min(ok["exdate"].unique(),
             key=lambda e: (abs((pd.Timestamp(e) - d).days - spec["CH20A_HEDGE_DTE_TARGET"]),
                            pd.Timestamp(e)))
    c = ok[ok["exdate"] == ex]
    L = c.loc[(c["strike"] - spec["CH20A_HEDGE_LONG_MONEYNESS"] * spot).abs().idxmin()]
    lo, hi = spec["CH20A_HEDGE_SHORT_BAND"]
    sb = c[(c["strike"] / spot >= lo) & (c["strike"] / spot <= hi)]
    S = sb.loc[(sb["strike"] - spec["CH20A_HEDGE_SHORT_MONEYNESS"] * spot).abs().idxmin()]
    return L, S


def test_fills_pay_the_ask_and_receive_the_bid(synth):
    u, q = _frames(*synth)
    spec = _spec()
    out = R.run_rolls(u, q, spec)
    r0 = out["rolls"][0]
    d, spot = r0["entry"], float(u["close"].iloc[r0["entry_i"]])
    L, S = _expected_legs(q, d, spot, spec)
    assert r0["cost"] * spot == pytest.approx(L["best_offer"] - S["best_bid"])
    mid_debit = (L["best_offer"] + L["best_bid"]) / 2 - (S["best_offer"] + S["best_bid"]) / 2
    assert r0["cost"] * spot > mid_debit                       # never the mid
    s1 = float(u["close"].iloc[r0["settle_i"]])
    exp_pay = max(L["strike"] - s1, 0) - max(S["strike"] - s1, 0)
    assert r0["pay"] * spot == pytest.approx(exp_pay)
    assert len(out["rolls"]) >= 12
    # the next roll starts on the session the previous one settled
    assert out["rolls"][1]["entry_i"] == r0["settle_i"]


def test_crossed_long_leg_skips_and_records_the_day(synth):
    u, q = _frames(*synth)
    spec = _spec()
    first = R.run_rolls(u, q, spec)["rolls"][0]
    d, spot = first["entry"], float(u["close"].iloc[first["entry_i"]])
    L, _ = _expected_legs(q, d, spot, spec)
    q2 = q.copy()
    q2.loc[L.name, "best_bid"] = L["best_offer"] + 1.0          # crossed
    out = R.run_rolls(u, q2, spec)
    assert out["rolls"][0]["entry_i"] == first["entry_i"] + 1
    assert {"date": d, "reason": "long_leg_crossed_or_no_ask"} in out["skipped"]


def test_missing_short_leg_buys_long_put_alone_and_counts_it(synth):
    u, q = _frames(*synth)
    spec = _spec()
    first = R.run_rolls(u, q, spec)["rolls"][0]
    d, spot = first["entry"], float(u["close"].iloc[first["entry_i"]])
    L, _ = _expected_legs(q, d, spot, spec)
    lo, hi = spec["CH20A_HEDGE_SHORT_BAND"]
    drop = (q["date"] == d) & (q["strike"] / spot >= lo) & (q["strike"] / spot <= hi)
    out = R.run_rolls(u, q[~drop], spec)
    r0 = out["rolls"][0]
    assert r0["entry_i"] == first["entry_i"]
    assert r0["long_only"] and r0["short_reason"] == "short_leg_missing"
    assert r0["cost"] * spot == pytest.approx(L["best_offer"])


def test_equal_average_drawdown_twin_and_by_year_table(synth):
    u, q = _frames(*synth)
    spec = _spec()
    roll = R.run_rolls(u, q, spec)
    idx = R.daily_indices(u, spec)
    pr = R.period_returns(u, roll, idx, spec, "base")
    res = R.compare(pr, spec)
    tgt = res["scales"]["target_avg_drawdown"]
    if R.avg_dd(pr["unhedged"].to_numpy()) > tgt:
        assert res["metrics"]["hold_less"]["avg_drawdown"] == pytest.approx(tgt, abs=2e-3)
        assert res["scales"]["hold_less_gross"] < 1.0
    years = {row["year"] for row in res["by_year"]}
    assert years == set(pr["year"])
    for row in res["by_year"]:
        for k in ("hedged", "unhedged", "hold_less", "trend", "inverse_ctrl",
                  "hedge_cost_pct_equity"):
            assert k in row
    assert res["verdict"]["label"] in {"HEDGE_BEATS_TWINS", "TWIN_WINS", "CANNOT_DISTINGUISH"}
    assert all(row["hedge_cost_pct_equity"] > 0 for row in res["by_year"])


def test_budget_variant_caps_spend(synth):
    u, q = _frames(*synth)
    spec = _spec()
    roll = R.run_rolls(u, q, spec)
    idx = R.daily_indices(u, spec)
    pr = R.period_returns(u, roll, idx, spec, "budget")
    caps = np.array([spec["CH20A_HEDGE_BUDGET_PER_YEAR"] * r["dte"] / 365.0
                     for r in roll["rolls"]])
    assert (pr["cost_pct"].to_numpy() <= caps + 1e-12).all()


def test_decide_rule_is_symmetric():
    m = {x: {"terminal_wealth": 1.0} for x in R.TWINS}
    m["hedged"] = {"terminal_wealth": 2.0}
    ahead = {x: {"hedge_ahead_full": True, "hedge_ahead_in_n_of": [5, 5]} for x in R.TWINS}
    assert R.decide(m, ahead)["label"] == "HEDGE_BEATS_TWINS"
    ahead["trend"]["hedge_ahead_in_n_of"] = [4, 5]
    assert R.decide(m, ahead)["label"] == "CANNOT_DISTINGUISH"
    behind = {x: {"hedge_ahead_full": False, "hedge_ahead_in_n_of": [0, 5]} for x in R.TWINS}
    m2 = {**m, "hold_less": {"terminal_wealth": 3.0}}
    v = R.decide(m2, behind)
    assert v["label"] == "TWIN_WINS" and v["twin"] == "hold_less"


def test_main_writes_receipt_and_leaves_data_folder_unchanged(synth, tmp_path: Path):
    under, quotes = synth
    data = tmp_path / "quotes"
    data.mkdir()
    for y, g in quotes.groupby(pd.to_datetime(quotes["date"]).dt.year):
        g.to_parquet(data / f"quotes_{y}.parquet", index=False)
    for y, g in under.groupby(pd.to_datetime(under["date"]).dt.year):
        g.to_parquet(data / f"under_{y}.parquet", index=False)
    n_files = len(list(data.glob("*")))
    out = tmp_path / "out"
    rc = R.main(["--out", str(out), "--data-dir", str(data), "--symbols", "SPY"])
    assert rc == 0
    assert len(list(data.glob("*"))) == n_files
    js = list(out.glob("ch20a_hedge_replay_*.json"))
    assert len(js) == 1 and js[0].with_suffix(".md").exists()
    rec = json.loads(js[0].read_text(encoding="utf-8"))
    assert rec["spec"]["sha256"] and rec["inventory"]["years"]
    spy = rec["symbols"]["SPY"]
    assert spy["n_rolls"] >= 12 and "skipped_quote_days_in_window" in spy
    assert set(spy["variants"]) == {"base", "budget"}
    assert spy["variants"]["base"]["by_year"]
    assert "SPY" in rec["verdict_lines"]
    md = js[0].with_suffix(".md").read_text(encoding="utf-8")
    assert "Verdicts" in md and "hold_less" in md


def test_empty_data_dir_is_a_red_exit_and_files_nothing(tmp_path: Path):
    data = tmp_path / "q"
    data.mkdir()
    (data / "quotes_2001.meta.json").write_text("{}", encoding="utf-8")   # a worktree's view
    out = tmp_path / "o"
    assert R.main(["--out", str(out), "--data-dir", str(data), "--symbols", "SPY"]) != 0
    assert not list(out.glob("ch20a_hedge_replay_*"))


def test_unknown_symbol_is_a_red_exit(synth, tmp_path: Path):
    under, quotes = synth
    data = tmp_path / "q"
    data.mkdir()
    y = pd.to_datetime(under["date"]).dt.year.iloc[0]
    under[pd.to_datetime(under["date"]).dt.year == y].to_parquet(data / f"under_{y}.parquet")
    quotes[pd.to_datetime(quotes["date"]).dt.year == y].to_parquet(data / f"quotes_{y}.parquet")
    assert R.main(["--out", str(tmp_path / "o"), "--data-dir", str(data),
                   "--symbols", "NVDA"]) != 0
