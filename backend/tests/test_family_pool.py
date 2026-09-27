"""Pooled family tests, holdings for every cell, matched twins that refuse a hole. Offline.

1. pooling three rules with a common alpha recovers it with a smaller SE than
   any single rule;
2. a family of DUPLICATES does not shrink the SE (effective n ~ 1, printed);
3. the factory's per-cell holdings round-trip into the record matched twins read,
   and reproduce each cell's stored gross exactly;
4. matched twins for a cell with a missing month refuse by the cell's name.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import family_pool as FP
from backend.services import matched_twins as MT
from backend.services import strategy_library as SL


def _idx(n: int = 120) -> pd.DatetimeIndex:
    return pd.date_range("2016-01-31", periods=n, freq="ME")


def _masks(idx: pd.DatetimeIndex) -> dict:
    sealed = np.asarray(idx >= pd.Timestamp("2024-01-01"))
    return {"dev": ~sealed, "sealed": sealed}


def test_pooling_three_rules_with_a_common_alpha_shrinks_the_se():
    rng = np.random.default_rng(11)
    idx = _idx()
    alpha = 0.006
    frame = pd.DataFrame({f"r{i}": alpha + rng.normal(0, 0.04, len(idx)) for i in range(3)},
                         index=idx)
    out = FP.family_test(frame, _masks(idx), family="planted")
    full = out["windows"]["full"]
    pooled = full["pooled"]
    singles = [FP.mean_test(frame[c]) for c in frame.columns]
    # the pooled mean is the mean of the members' means, near the planted alpha...
    assert abs(pooled["mean_monthly"] - np.mean([s["mean_monthly"] for s in singles])) < 1e-12
    assert abs(pooled["mean_monthly"] - alpha) < 2.5 * pooled["se_used"]
    # ...with an SE below EVERY single rule's, near 1/sqrt(3) of the median
    assert pooled["se_used"] < min(s["se_used"] for s in singles)
    assert 0.45 < full["se_ratio_pooled_to_single"] < 0.75
    assert full["effective_n"]["n_eff"] > 2.4
    assert pooled["mde_80"] == pytest.approx(2.8 * pooled["se_used"])


def test_a_family_of_duplicates_does_not_shrink_the_se():
    rng = np.random.default_rng(12)
    idx = _idx()
    base = 0.004 + rng.normal(0, 0.04, len(idx))
    # three near-copies of one rule (a label filter that changes one name in fifty)
    frame = pd.DataFrame({f"d{i}": base + rng.normal(0, 0.001, len(idx)) for i in range(3)},
                         index=idx)
    out = FP.family_test(frame, _masks(idx), family="duplicates")
    full = out["windows"]["full"]
    en = full["effective_n"]
    assert en["n"] == 3 and en["mean_pair_rho"] > 0.99
    assert en["n_eff"] < 1.05                                     # printed: one bet, not three
    assert full["se_ratio_pooled_to_single"] > 0.97               # the SE did not shrink
    assert full["se_ratio_implied_by_n_eff"] > 0.97


def test_a_family_below_three_rules_is_refused_by_name():
    idx = _idx(40)
    frame = pd.DataFrame({"a": np.zeros(40), "b": np.zeros(40)}, index=idx)
    with pytest.raises(FP.FamilyPoolRefused, match="'pair'"):
        FP.family_test(frame, _masks(idx), family="pair")


def test_the_verdict_reads_the_ex_ante_hedge_with_factors():
    rng = np.random.default_rng(13)
    idx = _idx()
    f = pd.DataFrame({"SMH-SPY": rng.normal(0, 0.05, len(idx))}, index=idx)
    # pure beta: every member is 1.0 x the spread + noise, no alpha
    frame = pd.DataFrame({f"b{i}": f["SMH-SPY"] + rng.normal(0, 0.01, len(idx)) for i in range(4)},
                         index=idx)
    out = FP.family_test(frame, _masks(idx), family="beta", X=f)
    assert out["verdict"] in FP.SS.VERDICTS and out["verdict"] != "ALPHA_DETECTED"
    assert abs(out["windows"]["full"]["ols"]["betas"]["SMH-SPY"] - 1.0) < 0.05


def test_dsr_is_counted_over_families():
    rng = np.random.default_rng(14)
    s = {f"f{i}": pd.Series(rng.normal(0.002, 0.02, 100)) for i in range(4)}
    d4 = FP.dsr_over_families(s, 4)
    d40 = FP.dsr_over_families(s, 40)
    assert all(d4[k] is not None and d4[k] >= d40[k] for k in s)


# ── holdings for every cell ─────────────────────────────────────────────────

def _planted():
    from backend.tests.test_strategy_library import planted_panel, planted_spy
    p = planted_panel(36, 60)
    rng = np.random.default_rng(15)
    for c in ("vol_63", "mom_252_21"):                 # the characteristics twins match on
        if c not in p.columns:
            p[c] = rng.normal(0.3, 0.1, len(p))
    return p, planted_spy(p)


def test_holdings_round_trip_through_the_factory(tmp_path, monkeypatch):
    from scripts import night_backtest_factory as F
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    p, spy = _planted()
    rules = [SL.Strategy("planted", "planted_family", "the planted alpha", SL.col("alpha")),
             SL.Strategy("noise_a", "fam", "noise", SL.seeded_noise(1001)),
             SL.Strategy("noise_b", "fam", "noise", SL.seeded_noise(1002))]
    out = tmp_path / "lib"
    today = date.today()
    F.run_factory(p, spy, {"source": "t"}, today=today, rules=rules, out=out,
                  checkpoint_every=1, log=lambda *_: None)
    man = F.write_holdings(F.board_done(out, today), p, out=out, today=today, run_id="RID")
    chk = man["check"]
    assert chk["n_ok_cells"] == chk["n_cells_with_holdings"] == chk["n_cells_monthly_rows_equal_n_months"] > 0
    assert man["files"]["holdings"]["n_rules"] == 3
    for f in man["files"].values():
        assert len(f["sha256"]) == 64 and f["rows"] > 0
    recs = MT.cell_records(pd.read_parquet(out / "holdings_RID.parquet"),
                           pd.read_parquet(out / "cell_monthly_RID.parquet"))
    # the round trip equals a direct run of the same rule
    hold: list = []
    m = SL.run_strategy(p, rules[0], k=20, holdings=hold)
    rec = recs[("planted", 20)]
    assert rec["held_symbols_by_date"] == {h["date"]: h["symbols"] for h in hold}
    assert rec["weights_by_date"] == {h["date"]: h["weights"] for h in hold}
    assert [x["net"] for x in rec["monthly_return_series"]] == pytest.approx(m["net"].tolist(), abs=1e-15)
    # and the twin module rebuilds the stored gross from those holdings
    tp = pd.read_parquet(out / "twin_panel_RID.parquet")
    ts = MT.twin_series(rec, tp, seed=1, grid=sorted(tp["date"].unique()))
    assert np.allclose(ts["rule_gross_recon"], ts["stored_gross"].astype(float), atol=1e-12)


def test_a_cash_rebalance_round_trips_to_an_empty_book():
    h = MT.holdings_frame([("r", 10, [{"date": "2020-01-31", "symbols": ["A", "B"], "weights": [0.5, 0.5]},
                                      {"date": "2020-02-29", "symbols": [], "weights": [],
                                       "risk_off": True}])])
    m = MT.monthly_frame([("r", 10, pd.DataFrame({"date": pd.to_datetime(["2020-01-31", "2020-02-29"]),
                                                  "gross": [0.01, 0.0], "cost": [0.001, 0.001],
                                                  "net": [0.009, -0.001], "rebalanced": [True, True],
                                                  "n_held": [2, 0]}))])
    rec = MT.cell_records(h, m)[("r", 10)]
    assert rec["held_symbols_by_date"] == {"2020-01-31": ["A", "B"], "2020-02-29": []}
    assert rec["risk_off_dates"] == ["2020-02-29"]


def test_matched_twins_for_a_cell_with_a_missing_month_refuse_by_name():
    from backend.tests.test_matched_twins import _panel, _size_tilt_rule
    panel = _panel(n_months=6, n_names=80)
    rule = _size_tilt_rule(panel, k=5)
    rule["id"] = "hole_rule@k5"
    grid = sorted(panel["date"].unique())
    MT.twin_series(rule, panel, seed=1, grid=grid)                # whole: runs
    del rule["monthly_return_series"][2]                          # one month lost inside the span
    with pytest.raises(MT.TwinInputMissing, match="hole_rule@k5.*missing"):
        MT.twin_series(rule, panel, seed=1, grid=grid)
