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


def test_verdict_needs_every_origin():
    sweep = [{"t": 3.0, "t_crit": 2.2}, {"t": 1.0, "t_crit": 2.2}]
    word, _ = M.verdict_of(sweep, 0.99, 0.05, -0.01, 0.05)
    assert word == "CANNOT_DISTINGUISH"
    word, _ = M.verdict_of(sweep, 0.99, 0.05, 0.02, 0.05)
    assert word == "CANNOT_DISTINGUISH"          # in the twins' tail: not "book ~ twins"
    word, _ = M.verdict_of(sweep, 0.60, 0.05, 0.02, 0.05)
    assert word == "BAND_EFFECT"


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
