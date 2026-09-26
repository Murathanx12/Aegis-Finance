"""matched_twins: a characteristic-matched random twin removes a pure style tilt. Offline."""
import numpy as np
import pandas as pd
import pytest

from backend.services import matched_twins as MT


def _panel(n_months: int = 60, n_names: int = 400, seed: int = 1) -> pd.DataFrame:
    """Four size bands; ONLY the band pays (mega +2%/month), plus noise.
    vol and past return are noise with no premium."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-31", periods=n_months, freq="ME")
    mdv_levels = np.array([3e9, 3e8, 5e7, 5e6])
    band_of = np.arange(n_names) % 4
    rows = []
    for d in dates:
        for i in range(n_names):
            b = band_of[i]
            rows.append({"date": d, "symbol": f"S{i:03d}", "eligible": True,
                         "median_dollar_vol": mdv_levels[b] * (1 + 0.1 * rng.random()),
                         "vol_63": rng.uniform(0.1, 0.8), "mom_252_21": rng.normal(0, 0.3),
                         "fwd_ret": (0.02 if b == 0 else 0.0) + rng.normal(0, 0.03)})
    return pd.DataFrame(rows)


def _size_tilt_rule(panel: pd.DataFrame, k: int = 20, seed: int = 2) -> dict:
    """The 'rule' is a pure size tilt: k random MEGA names each month, equal weight."""
    rng = np.random.default_rng(seed)
    held, wts, months = {}, {}, []
    for d, g in panel.groupby("date"):
        mega = g.loc[g["median_dollar_vol"] >= 1e9, "symbol"].to_numpy()
        pick = list(rng.choice(mega, size=k, replace=False))
        ds = str(d.date())
        held[ds], wts[ds] = pick, [1.0 / k] * k
        gross = float(g.set_index("symbol").loc[pick, "fwd_ret"].mean())
        months.append({"date": ds, "gross": gross, "cost": 0.0, "net": gross, "rebalanced": True})
    return {"id": "size_tilt", "held_symbols_by_date": held, "weights_by_date": wts,
            "monthly_return_series": months}


def test_size_band_uses_the_factory_cost_bands():
    assert list(MT.size_band([2e9, 2e8, 3e7, 1e6, np.nan])) == ["mega", "large", "mid", "small", "na"]


def test_seed_is_derived_from_the_rule_id():
    assert MT.seed_for("mom_12_1") == MT.seed_for("mom_12_1")
    assert MT.seed_for("mom_12_1") != MT.seed_for("mom_12_1_q")
    assert MT.seed_for("mom_12_1", 1) != MT.seed_for("mom_12_1")


def test_the_matched_twin_removes_a_pure_size_tilt():
    panel = _panel()
    rule = _size_tilt_rule(panel)
    ts = MT.twin_series(rule, panel, seed=MT.seed_for(rule["id"]))
    # the reconstruction of the rule's own gross from its holdings is exact here
    assert np.allclose(ts["rule_gross_recon"], ts["stored_gross"], atol=1e-12)
    # an UNMATCHED random draw from the whole panel: ~1/4 of it is mega
    rng = np.random.default_rng(3)
    rnd = pd.Series({d: float(g["fwd_ret"].to_numpy()[rng.choice(len(g), 50, replace=False)].mean())
                     for d, g in panel.groupby("date")})
    mask = np.ones(len(ts), dtype=bool)
    out = MT.compare(ts["stored_net"], ts["twin_gross"], rnd, mask)
    # the rule beats random by the size premium (~ +2%/mo x 3/4 -> ~ +19%/yr)...
    assert out["rule_minus_random_1"] > 0.10
    # ...and the matched twin takes it away
    assert abs(out["rule_minus_twin"]) < 0.04
    assert out["share_removed"] > 0.75
    # nearly every twin came from the full cell (100 mega names in 9 cells, 20 held:
    # a thin cell can run out and fall back to band x vol)
    fb = [f for f in ts["fallbacks"] if f]
    assert sum(f["cell"] for f in fb) >= 0.95 * 20 * len(fb)
    assert sum(f["any"] + f["none"] for f in fb) == 0
    # and every twin name is a MEGA name different from the rule's own holdings
    cells = MT.cell_table(panel[panel["date"] == panel["date"].min()])
    d0 = str(panel["date"].min().date())
    pairs, _ = MT.draw_twins(rule["held_symbols_by_date"][d0], cells,
                             panel[panel["date"] == panel["date"].min()],
                             np.random.default_rng(MT.seed_for("size_tilt")))
    held = set(rule["held_symbols_by_date"][d0])
    assert all(t not in held and cells.loc[t, "band"] == "mega" for _, t, _ in pairs)
    assert len({t for _, t, _ in pairs}) == len(pairs)          # without replacement


def test_a_book_that_selects_within_its_cell_keeps_its_excess():
    """The control: a rule that picks the names that PAY inside a band is not a style."""
    panel = _panel(seed=4)
    # plant a within-cell signal: half of every band ((i // 4) even) earns +3% on top
    idx = panel["symbol"].str[1:].astype(int)
    panel.loc[(idx // 4) % 2 == 0, "fwd_ret"] += 0.03
    rng = np.random.default_rng(5)
    held, wts, months = {}, {}, []
    for d, g in panel.groupby("date"):
        g2 = g[(g["median_dollar_vol"] < 1e9) & ((g["symbol"].str[1:].astype(int) // 4) % 2 == 0)]
        pick = list(rng.choice(g2["symbol"].to_numpy(), size=20, replace=False))
        ds = str(d.date())
        held[ds], wts[ds] = pick, [0.05] * 20
        gr = float(g.set_index("symbol").loc[pick, "fwd_ret"].mean())
        months.append({"date": ds, "gross": gr, "cost": 0.0, "net": gr, "rebalanced": True})
    rule = {"id": "selector", "held_symbols_by_date": held, "weights_by_date": wts,
            "monthly_return_series": months}
    ts = MT.twin_series(rule, panel, seed=MT.seed_for("selector"))
    out = MT.compare(ts["stored_net"], ts["twin_gross"], ts["twin_gross"] * 0, np.ones(len(ts), bool))
    assert out["rule_minus_twin"] > 0.15                         # ~ +1.5%/mo survives matching


def test_a_rebalance_off_the_panel_refuses():
    panel = _panel(n_months=3, n_names=40)
    rule = _size_tilt_rule(panel, k=5)
    rule["held_symbols_by_date"]["1999-12-31"] = ["S000"]
    rule["monthly_return_series"].insert(0, {"date": "1999-12-31", "gross": 0, "cost": 0, "net": 0})
    with pytest.raises(MT.TwinInputMissing):
        MT.twin_series(rule, panel, seed=1)


def test_hold_months_keep_the_twin_between_rebalances():
    panel = _panel(n_months=6, n_names=80)
    rule = _size_tilt_rule(panel, k=5)
    keep = {d: v for i, (d, v) in enumerate(rule["held_symbols_by_date"].items()) if i % 3 == 0}
    rule["held_symbols_by_date"] = keep
    ts = MT.twin_series(rule, panel, seed=7)
    assert [f is not None for f in ts["fallbacks"]] == [True, False, False, True, False, False]
