"""CH-11 matched-twin re-evaluation: synthetic panels only, no live data, no network.

Dates are derived from today, never written as literals."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import matched_twin_reeval as M


def _dates(n: int) -> list[pd.Timestamp]:
    end = pd.Timestamp.today().normalize() - pd.Timedelta(days=7)
    return list(pd.bdate_range(end=end, periods=n))


def _panel_bars(n_days: int = 160, n_names: int = 60, drift: dict | None = None, seed: int = 7) -> pd.DataFrame:
    """SPY + n_names stocks in ONE liquidity band (same dollar volume), similar volatility."""
    rng = np.random.default_rng(seed)
    dates = _dates(n_days)
    mkt = rng.normal(0.0003, 0.008, n_days)
    rows = []
    spy = 400 * np.cumprod(1 + mkt)
    for i, d in enumerate(dates):
        rows.append(("SPY", d, spy[i], spy[i], 5e7))
    for j in range(n_names):
        sym = f"S{j:02d}"
        mu = (drift or {}).get(sym, 0.0)
        r = mkt + mu + rng.normal(0, 0.02, n_days)
        px = 50 * np.cumprod(1 + r)
        for i, d in enumerate(dates):
            rows.append((sym, d, px[i] / (1 + r[i] / 2), px[i], 1e6))   # $50M/day -> "mid" band
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"])


def _p() -> dict:
    p = M.params()
    p.update(block_sessions=5, alpha=0.05, power=0.80)
    return p


def _setup(bars: pd.DataFrame):
    panel = M.Panel(bars)
    pools = M.Pools(bars, {}, _p())

    def keep(s: str) -> bool:
        return s in M.INDEX_PROXIES or s == M.CASH or not panel.has(s)
    return panel, pools, keep


def _decision(panel: M.Panel, names: list[str], asof_row: int) -> list[dict]:
    w = 0.95 / len(names)
    return [{"asof": panel.dates[asof_row], "fill_row": asof_row + 1, "price": "open",
             "weights": {s: (s, w) for s in names}}]


def test_twin_pool_uses_only_bars_strictly_before_the_asof():
    bars = _panel_bars(n_days=120, n_names=20)
    dates = sorted(bars["date"].unique())
    asof = pd.Timestamp(dates[80])
    # a name listed ON the asof is not a live alternative at the asof
    new = pd.DataFrame([("NEWCO", d, 20.0, 20.0, 1e7) for d in dates if d >= asof],
                       columns=bars.columns)
    # a name whose volume explodes from the asof on keeps the band its PAST volume gives
    spike = pd.DataFrame([("SPIKE", d, 20.0 * (1 + 0.001 * i), 20.0 * (1 + 0.001 * i),
                           5e3 if d < asof else 1e9) for i, d in enumerate(dates)], columns=bars.columns)
    allb = pd.concat([bars, new, spike], ignore_index=True)
    pools = M.Pools(allb, {}, _p())
    P = pools.at(str(asof.date()))
    assert P["latest_bar_used"] < str(asof.date())
    assert "NEWCO" not in P["live_set"]
    assert P["bands"]["SPIKE"].startswith("small|")
    # every drawn twin name is in the as-of pool
    panel = M.Panel(allb)
    decs = [{"asof": str(asof.date()), "fill_row": panel.session_on_or_after(str(asof.date())), "price": "open",
             "weights": {"S00": ("S00", 0.5), "S01": ("S01", 0.5)}}]
    rng = np.random.default_rng(1)
    for _ in range(50):
        tw, _fb = M.draw_twin(decs, pools, "band", rng, lambda s: False)
        assert all(s in P["live_set"] for s, _ in tw[0]["weights"].values())
        assert all(s != "NEWCO" for s, _ in tw[0]["weights"].values())


def test_book_identical_to_a_twin_draw_is_not_distinguished():
    bars = _panel_bars()
    panel, pools, keep = _setup(bars)
    base = _decision(panel, [f"S{j:02d}" for j in range(10)], 60)
    tw, _ = M.draw_twin(base, pools, M.PRIMARY_LEVEL, np.random.default_rng(12345), keep)
    ev = M.evaluate_book(tw, panel, pools, end_row=len(panel.dates) - 1, rt_bps=lambda s: 18.0, keep=keep,
                         n_twins=200, seed=99, p=_p())
    pct = ev["twins"][M.PRIMARY_LEVEL]["book_percentile"]
    assert 0.05 < pct < 0.95
    assert ev["verdict"] in ("CANNOT_DISTINGUISH", "BAND_EFFECT")
    assert all(s["mde_pp"] is not None for s in ev["twins"][M.PRIMARY_LEVEL]["origin_sweep"])
    assert len(ev["twins"][M.PRIMARY_LEVEL]["origin_sweep"]) == 5


def test_planted_outperformer_beats_its_twins_at_every_origin():
    winners = [f"S{j:02d}" for j in range(10)]
    bars = _panel_bars(drift={s: 0.005 for s in winners})
    panel, pools, keep = _setup(bars)
    decs = _decision(panel, winners, 60)
    ev = M.evaluate_book(decs, panel, pools, end_row=len(panel.dates) - 1, rt_bps=lambda s: 18.0, keep=keep,
                         n_twins=200, seed=3, p=_p())
    assert ev["verdict"] == "BEATS_TWINS_IN_SCOPE", ev["verdict_why"]
    sw = ev["twins"][M.PRIMARY_LEVEL]["origin_sweep"]
    assert all(s["t"] >= s["t_crit"] for s in sw)
    assert ev["twins"][M.PRIMARY_LEVEL]["book_percentile"] >= 0.975
    assert ev["headline_blocks"] >= 10
    # the pieces the receipt promises are present
    for k in ("excess_over_twin_median_by_month_pp", "leave_one_month_out", "top5_dates_of_book_pnl",
              "top5_names_of_book_pnl", "removal_curve_vs_twins", "decomposition_pp"):
        assert k in ev


def test_verdict_needs_every_origin_and_the_rank_test():
    sweep = [{"t": 3.0, "t_crit": 2.2}, {"t": 1.0, "t_crit": 2.2}]
    # in the top tail, one origin fails -> the tail word with its side, not CANNOT_DISTINGUISH
    word, _ = M.verdict_of(sweep, 0.99, 0.01, 0.05, -0.01, 0.05)
    assert word == "TAIL_BY_RANK_UNCONFIRMED_HIGH"
    word, _ = M.verdict_of(sweep, 0.60, 0.9, 0.05, 0.02, 0.05)
    assert word == "BAND_EFFECT"
    word, _ = M.verdict_of(sweep, 0.60, 0.9, -0.05, 0.02, 0.05)
    assert word == "CANNOT_DISTINGUISH"
    every = [{"t": 3.0, "t_crit": 2.2}] * 5
    assert M.verdict_of(every, 0.999, 0.01, 0.05, 0.0, 0.05)[0] == "BEATS_TWINS_IN_SCOPE"
    # block t at every origin but the Holm-corrected rank p does not clear -> unconfirmed tail
    assert M.verdict_of(every, 0.999, 0.20, 0.05, 0.0, 0.05)[0] == "TAIL_BY_RANK_UNCONFIRMED_HIGH"
    down = [{"t": -3.0, "t_crit": 2.2}] * 5
    assert M.verdict_of(down, 0.001, 0.01, -0.05, 0.0, 0.05)[0] == "LAGS_TWINS_IN_SCOPE"
    weak = [{"t": -1.0, "t_crit": 2.2}] * 5
    assert M.verdict_of(weak, 0.001, 0.01, -0.05, 0.0, 0.05)[0] == "TAIL_BY_RANK_UNCONFIRMED_LOW"


def test_rank_p_and_holm():
    tw = np.arange(1000, dtype=float)
    assert M.rank_p(2000.0, tw) == pytest.approx(2 / 1001)
    assert M.rank_p(-5.0, tw) == pytest.approx(2 / 1001)
    assert M.rank_p(500.0, tw) == pytest.approx(1.0)
    adj = M.holm({"a": 0.01, "b": 0.02, "c": 0.5})
    assert adj["a"] == pytest.approx(0.03) and adj["b"] == pytest.approx(0.04) and adj["c"] == pytest.approx(0.5)
    adj = M.holm({"a": 0.02, "b": 0.011})          # monotone: never below an earlier step
    assert adj["b"] == pytest.approx(0.022) and adj["a"] == pytest.approx(0.022)


def test_planted_laggard_lags_its_twins():
    losers = [f"S{j:02d}" for j in range(10)]
    bars = _panel_bars(drift={s: -0.005 for s in losers})
    panel, pools, keep = _setup(bars)
    ev = M.evaluate_book(_decision(panel, losers, 60), panel, pools, end_row=len(panel.dates) - 1,
                         rt_bps=lambda s: 18.0, keep=keep, n_twins=200, seed=4, p=_p())
    assert ev["verdict"] == "LAGS_TWINS_IN_SCOPE", ev["verdict_why"]
    assert ev["twins"][M.PRIMARY_LEVEL]["rank_p_two_sided"] <= 2 / 201 + 1e-12


def test_finalize_applies_holm_across_books():
    winners = [f"S{j:02d}" for j in range(10)]
    bars = _panel_bars(drift={s: 0.005 for s in winners})
    panel, pools, keep = _setup(bars)
    res = {}
    for k in range(3):
        ev = M.evaluate_book(_decision(panel, winners, 60), panel, pools,
                             end_row=len(panel.dates) - 1, rt_bps=lambda s: 18.0, keep=keep, n_twins=60,
                             seed=10 + k, p=_p())
        res[f"b{k}"] = {**ev, "status": "OK"}
    fam = M.finalize_verdicts(res, 0.05)
    assert fam[M.PRIMARY_LEVEL]["m"] == 3
    for r in res.values():
        lv = r["twins"][M.PRIMARY_LEVEL]
        assert "_vin" not in lv
        # raw p floor 2/61 = 0.033; Holm x3 = 0.098 > 0.05 -> cannot be BEATS any more
        assert lv["rank_p_holm"] == pytest.approx(min(1.0, 3 * lv["rank_p_two_sided"]), abs=1e-6)
        assert r["verdict"] == "TAIL_BY_RANK_UNCONFIRMED_HIGH"


def test_simulate_arithmetic():
    dates = _dates(4)
    rows = []
    for sym, opens, closes in (("SPY", [100, 100, 100, 100], [100, 100, 100, 100]),
                               ("AAA", [10, 10, 11, 12], [10, 11, 12, 12]),
                               ("BBB", [20, 20, 20, 20], [20, 20, 20, 18])):
        for d, o, c in zip(dates, opens, closes):
            rows.append((sym, d, float(o), float(c), 1e6))
    panel = M.Panel(pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"]))
    decs = [{"asof": panel.dates[0], "fill_row": 1, "price": "open",
             "weights": {"AAA": ("AAA", 0.5), "BBB": ("BBB", 0.4)}}]
    out = M.simulate(decs, panel, 3, lambda s: 20.0)      # 20 bps round trip -> 10 bps per side
    cost_in = 0.9 * 10 / 1e4
    v = 1.0 - cost_in
    sh_a, sh_b, cash = 0.5 * v / 10, 0.4 * v / 20, v - 0.9 * v
    assert out["nav"][0] == pytest.approx(cash + sh_a * 11 + sh_b * 20)
    assert out["nav"][1] == pytest.approx(cash + sh_a * 12 + sh_b * 20)
    exit_cost = (sh_a * 12 + sh_b * 18) * 10 / 1e4
    assert out["nav"][2] == pytest.approx(cash + sh_a * 12 + sh_b * 18 - exit_cost)
    assert out["cost"] == pytest.approx(cost_in + exit_cost)
    assert out["pnl"]["AAA"] == pytest.approx(sh_a * 2) and out["pnl"]["BBB"] == pytest.approx(sh_b * -2)


def test_strategy_accounting_explains_every_row():
    roi = {"rows": [
        {"account": "good", "status": "LIVE", "vs_spy_pp": 1.0},
        {"account": "tw", "status": "LIVE", "vs_spy_pp": 2.0},
        {"account": "x-control", "status": "LIVE", "vs_spy_pp": 0.1},
        {"account": "novs", "status": "LIVE", "vs_spy_pp": None},
        {"account": "dead", "status": "VOIDED", "vs_spy_pp": 3.0}]}
    dna = {"books": [{"account": "tw", "category": "twin"}, {"account": "good", "category": "strategy"}]}
    strat, dropped = M.strategy_accounting(roi, dna, ["-control"])
    assert [r["account"] for r in strat] == ["good"]
    why = {d["account"]: d["why"] for d in dropped}
    assert set(why) == {"tw", "x-control", "novs", "dead"}
    assert "twin" in why["tw"] and "-control" in why["x-control"] and "VOIDED" in why["dead"]


def test_twin_may_hold_book_names_but_never_book_only_names():
    bars = _panel_bars(n_days=90, n_names=4)
    extra = bars[bars["symbol"] == "S00"].assign(symbol="GLOBALX")
    allb = pd.concat([bars, extra], ignore_index=True)
    panel = M.Panel(allb)
    pools = M.Pools(allb, {}, _p(), eligible=set(bars["symbol"]))
    decs = [{"asof": panel.dates[60], "fill_row": 61, "price": "open",
             "weights": {"S00": ("S00", 0.3), "S01": ("S01", 0.3)}}]
    seen: set = set()
    rng = np.random.default_rng(5)
    for _ in range(200):
        tw, _fb = M.draw_twin(decs, pools, "panel", rng, lambda s: False)
        names = [s for s, _ in tw[0]["weights"].values()]
        assert len(set(names)) == len(names)
        seen |= set(names)
    assert "S00" in seen and "S01" in seen
    assert "GLOBALX" not in seen


def test_missing_db_is_a_named_refusal(tmp_path):
    with pytest.raises(M.Refused, match="aegis_pi.db missing"):
        M.open_db_copy(tmp_path / "aegis_pi.db")
    import sqlite3
    db = tmp_path / "x.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE other (a int)")
    con.commit()
    con.close()
    with pytest.raises(M.Refused, match="paper_book_decisions"):
        M.open_db_copy(db)


def test_panel_membership_flags_a_pool_before_the_membership_date(tmp_path):
    dates = _dates(60)
    rows = [("A", d, 1.0, 1.0, 1.0) for d in dates] + [("B", d, 1.0, 1.0, 1.0) for d in dates[:50]]
    f = tmp_path / "bars.parquet"
    pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"]).to_parquet(f)
    early, late = str(dates[10].date()), str(dates[55].date())
    out = M.panel_membership(f, None, str(dates[0].date()), [early, late])
    assert out["membership_date"] == str(dates[49].date())
    assert out["flagged_asofs"] == [early]
    assert "PRECEDE" in M.survivorship_line(out)
    clean = M.panel_membership(f, None, str(dates[0].date()), [late])
    assert clean["flagged_asofs"] == [] and "ON OR AFTER" in M.survivorship_line(clean)


def test_all_carried_book_is_not_evaluated():
    bars = _panel_bars(n_days=90, n_names=10)
    panel, pools, _ = _setup(bars)
    decs = [{"asof": panel.dates[40], "fill_row": 41, "price": "open", "weights": {"SPY": ("SPY", 0.9)}}]
    ev = M.evaluate_book(decs, panel, pools, end_row=len(panel.dates) - 1, rt_bps=lambda s: 6.0,
                         keep=lambda s: s == "SPY", n_twins=20, seed=1, p=_p())
    assert ev["verdict"] == M.NOT_EVALUATED


def test_block_sums_origin_shifts_the_cut_and_keeps_the_total():
    x = np.arange(12, dtype=float)
    for o in range(5):
        s = M.block_sums(x, 5, o)
        assert s.sum() == pytest.approx(x.sum())
    assert M.block_sums(x, 5, 2)[0] == pytest.approx(0 + 1)


def test_cluster_bets_collapses_at_jaccard_08():
    names = {"a": frozenset("ABCDE"), "b": frozenset("ABCDE"), "c": frozenset("ABCDF"), "d": frozenset("XYZ")}
    bet = M.cluster_bets(names, 0.8)
    assert bet["a"] == ["a", "b"]
    assert bet["d"] == ["d"]
    assert bet["c"] == ["c"]            # 4/6 = 0.67 < 0.8


def test_missing_input_is_a_nonzero_exit(tmp_path):
    out = tmp_path / "out"
    assert M.main(["--out", str(out), "--data-root", str(tmp_path / "nothing" / "optimus")]) == 2
    root = tmp_path / "data" / "optimus"
    (root / "paper_accounts").mkdir(parents=True)
    assert M.main(["--out", str(out), "--data-root", str(root)]) == 2          # no roi/book_dna pair
    assert M.main(["--out", str(root / "x"), "--data-root", str(root)]) == 2   # out inside the data folder
    assert M.main(["--out", str(out), "--data-root", str(root), "--n-twins", "10"]) == 2
    assert not out.exists() or not any(out.iterdir())
