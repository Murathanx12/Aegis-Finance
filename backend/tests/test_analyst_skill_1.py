"""ANALYST-SKILL-1: the registered statistic on synthetic worlds.

A planted skilled broker must raise ΔIC with t >= 2 over 60 months; a null world
must not; a noisy world must stop at the POWER gate without printing an arm
number. Plus the §4 mechanics: shrinkage, the prior for an unmeasured broker,
the >= 2-broker floor, the contamination clause and the entry convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import analyst_skill_1 as a1


def _world(*, skilled: bool, months: int = 60, names: int = 300, seed: int = 7,
           noise_ret: float = 1.0) -> tuple[pd.DataFrame, pd.Series, float]:
    """10 brokers cover every name. In the skilled world brokers B0-B2 see the
    signal and the rest see noise, and the weights favour B0-B2. In the null
    world every broker sees the same-quality signal and weights are arbitrary."""
    rng = np.random.default_rng(seed)
    rows = []
    for m in pd.period_range("2019-01", periods=months, freq="M"):
        sig = rng.normal(0, 1, names)
        fwd = 0.3 * sig + noise_ret * rng.normal(0, 1, names)
        for b in range(10):
            if skilled:
                u = (sig + 0.3 * rng.normal(0, 1, names)) if b < 3 else rng.normal(0, 1, names)
            else:
                u = sig + 1.5 * rng.normal(0, 1, names)
            rows.append(pd.DataFrame({"month": str(m), "permno": np.arange(names),
                                      "estimid": f"B{b}", "upside": u, "fwd_ret": fwd,
                                      "mcap": np.where(np.arange(names) % 2, 5e9, 5e8)}))
    panel = pd.concat(rows, ignore_index=True)
    if skilled:
        w = pd.Series({f"B{b}": (1.5 if b < 3 else 0.5) for b in range(10)})
    else:
        w = pd.Series({f"B{b}": 0.5 + b / 9 for b in range(10)})
    return panel, w, 1.0


def test_planted_skill_raises_delta_ic():
    panel, w, prior = _world(skilled=True)
    r = a1.evaluate(panel, w, prior)
    assert r["verdict"] == "ADOPT"
    assert r["delta_ic_mean"] > 0 and r["t_nw3"] >= 2.0
    assert r["power_gate"]["n_months"] == 60
    # protocol 11: by-year and the size split are in the result, and computed
    assert set(r["by_year"]) == {2019, 2020, 2021, 2022, 2023}
    assert set(r["size_split"]) == {"small", "largemid"}


def test_null_world_does_not_adopt():
    """Equal-quality brokers, arbitrary weights: never ADOPT. The mean is <= 0,
    not ~0 -- unequal weights on equally good brokers throw away averaging
    efficiency, so a skill weighting with no skill behind it COSTS IC."""
    panel, w, prior = _world(skilled=False)
    r = a1.evaluate(panel, w, prior)
    assert r["verdict"] in ("REJECT", "POWER_FAILED")
    if r["verdict"] == "REJECT":
        assert r["delta_ic_mean"] <= 0.0 or r["t_nw3"] < 1.0


def test_power_gate_runs_first_and_hides_arms():
    ic = pd.DataFrame({"month": [str(p) for p in pd.period_range("2019-01", periods=24, freq="M")],
                       "ic_ew": 0.02, "ic_sw": 0.02 + np.random.default_rng(3).normal(0, 0.2, 24)})
    ic["dic"] = ic["ic_sw"] - ic["ic_ew"]
    r = a1.decide(ic)
    assert r["verdict"] == "POWER_FAILED" and not r["power_gate"]["passed"]
    assert "delta_ic_mean" not in r and "t_nw3" not in r and "mean_ic_sw" not in r


def test_nw_se_matches_iid_formula_without_autocorrelation():
    x = np.random.default_rng(0).normal(0, 1, 5000)
    assert a1.nw_se(x, 0) == pytest.approx(x.std(ddof=0) / np.sqrt(len(x)), rel=1e-9)
    # positive autocorrelation widens the NW SE
    y = np.convolve(x, np.ones(6) / 6, mode="valid")
    assert a1.nw_se(y, 3) > a1.nw_se(y, 0)


def test_broker_skill_shrinkage_and_prior():
    g = pd.DataFrame({"estimid": ["A"] * 80 + ["B"] * 5,
                      "implied_log": 0.0,
                      "realized_log": [0.05] * 80 + [0.50] * 5})
    t, grand, prior = a1.broker_skill(g)
    assert grand == pytest.approx(-0.05)
    wa, wb = 80 / 100, 5 / 25
    assert t.loc["A", "shrunk"] == pytest.approx(wa * -0.05 + (1 - wa) * grand)
    assert t.loc["B", "shrunk"] == pytest.approx(wb * -0.50 + (1 - wb) * grand)
    assert t.loc["A", "weight"] == pytest.approx(1.5) and t.loc["B", "weight"] == pytest.approx(1.0)
    # an unmeasured broker sits AT the grand median (n = 0)
    assert 0.5 <= prior <= 1.5


def test_min_two_brokers_per_name_month():
    p = pd.DataFrame({"month": "2019-01", "permno": list(range(20)) + list(range(10)),
                      "estimid": ["X"] * 20 + ["Y"] * 10,
                      "upside": np.arange(30, dtype=float), "fwd_ret": np.arange(30, dtype=float)})
    p["fwd_ret"] = p["permno"].astype(float)
    ic = a1.monthly_ic(p, pd.Series({"X": 1.0, "Y": 1.5}), 1.0)
    assert ic.iloc[0]["n_names"] == 10


def _px(permnos=(1, 2), start="2018-11-01", end="2019-03-31", split_on=None):
    days = pd.bdate_range(start, end)
    rows = []
    for p in permnos:
        for i, d in enumerate(days):
            cf = 2.0 if (split_on and p == split_on[0] and d >= pd.Timestamp(split_on[1])) else 1.0
            rows.append((p, d, 10.0 + 0.01 * i, 0.001, cf, 1000.0))
    px = pd.DataFrame(rows, columns=["permno", "date", "prc", "ret", "cfacpr", "shrout"])
    px["tri"] = (1 + px["ret"]).groupby(px["permno"]).cumprod()
    return px


def test_eval_panel_contamination_and_entry():
    px = _px(split_on=(2, "2018-12-20"))
    t = pd.DataFrame({"permno": [1, 1, 2], "estimid": ["A", "B", "A"], "amaskcd": [1.0, 2.0, 1.0],
                      "value": [12.0, 13.0, 12.0],
                      "anndats": pd.to_datetime(["2018-12-03", "2018-12-10", "2018-12-03"])})
    dl = pd.DataFrame(columns=["permno", "dlstdt", "dlret_used"])
    panel, stats = a1.eval_panel(t, px, dl, pd.PeriodIndex(["2019-01"], freq="M"))
    # permno 2 split between anndats and the cut: excluded from BOTH arms
    assert stats["contaminated_excluded"] == 1 and set(panel["permno"]) == {1}
    # entry = first close >= Dec 31 + 3d = Jan 3; exit = first close >= Feb 3
    px1 = px[px["permno"] == 1].set_index("date")["tri"]
    want = px1[pd.Timestamp("2019-02-04")] / px1[pd.Timestamp("2019-01-03")] - 1.0
    assert panel["fwd_ret"].iloc[0] == pytest.approx(want)
    # upside against the last close on or before the cut (Dec 31)
    prc = px[(px["permno"] == 1) & (px["date"] == "2018-12-31")]["prc"].iloc[0]
    assert sorted(panel["upside"]) == pytest.approx(sorted([12.0 / prc - 1, 13.0 / prc - 1]))


def test_eval_panel_staleness_and_missing_exit_month():
    px = _px(permnos=(1,), start="2018-01-01", end="2019-01-31")
    t = pd.DataFrame({"permno": [1, 1], "estimid": ["A", "B"], "amaskcd": [1.0, 2.0],
                      "value": [12.0, 13.0],
                      "anndats": pd.to_datetime(["2018-06-01", "2018-12-01"])})   # A is > 180d stale
    dl = pd.DataFrame(columns=["permno", "dlstdt", "dlret_used"])
    panel, stats = a1.eval_panel(t, px, dl, pd.PeriodIndex(["2018-12", "2019-01"], freq="M"))
    assert stats["missing_months"] == ["2019-01"]            # exit needs Feb bars
    dec = panel[panel["month"] == "2018-12"]
    assert dec.empty      # A is stale at the 2018-11-30 cut; B is announced after it


def test_attenuation_diagnostic_separates_damping_from_information():
    rng = np.random.default_rng(5)
    ic_ew = rng.normal(-0.05, 0.15, 72)
    damp = pd.DataFrame({"ic_ew": ic_ew, "ic_sw": 0.99 * ic_ew})       # pure shrinkage
    damp["dic"] = damp["ic_sw"] - damp["ic_ew"]
    d = a1.attenuation_diagnostic(damp)
    assert d["slope"] < 0 and abs(d["intercept_dic_at_zero_ic"]) < 1e-9
    assert d["months_ic_ew_pos"]["mean_dic"] < 0 < d["months_ic_ew_nonpos"]["mean_dic"]
    info = pd.DataFrame({"ic_ew": ic_ew, "ic_sw": ic_ew + 0.01 + rng.normal(0, 0.002, 72)})
    info["dic"] = info["ic_sw"] - info["ic_ew"]
    d2 = a1.attenuation_diagnostic(info)
    assert d2["intercept_dic_at_zero_ic"] == pytest.approx(0.01, abs=0.002) and d2["intercept_t_nw3"] > 5
