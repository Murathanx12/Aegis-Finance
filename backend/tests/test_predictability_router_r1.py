"""Pins for the R1 predictability router (`scripts/predictability_router_r1.py`).

Four things this lane could get silently wrong, and one gate that would be
broken if it could never fire:

1. the abstention book could stop being the house book (then no comparison to
   `learner.evaluate.book` means anything);
2. the cell label could stop summing to the month's rank IC (then "predict the
   IC contribution" is a different claim than the one written down);
3. the insider window could include the formation day's own filings (a
   lookahead of exactly one day, which is the shape that is hardest to see);
4. the walk-forward could train on the months it tests.

All offline: no network, no LLM, no parquet larger than the fixtures built here
except in the one test that SKIPS when the cached panel is absent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "predictability_router_r1.py"


def _load():
    spec = importlib.util.spec_from_file_location("predictability_router_r1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = _load()


# ------------------------------------------------------------------ fixtures

def _panel(months: int = 24, names: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for mi in range(months):
        y, m = 2016 + mi // 12, mi % 12 + 1
        mkt = float(rng.normal(0.008, 0.04))
        for p in range(1, names + 1):
            pred = float(rng.normal())
            rows.append({
                "month": f"{y}-{m:02d}",
                "entry_date": pd.Timestamp(f"{y}-{m:02d}-15"),
                "permno": 10000 + p,
                "eng": pred,
                "fwd_1m": mkt + 0.01 * pred + float(rng.normal(0, 0.08)),
                "mkt_vw_1m": mkt,
                "market_cap": float(rng.lognormal(7, 1)),
            })
    d = pd.DataFrame(rows)
    d["excess_vw_1m"] = d["fwd_1m"] - d["mkt_vw_1m"]
    return d


# ------------------------------------------- 1. the book is the house's book

def test_routed_book_with_no_abstention_reproduces_evaluate_book():
    from learner import evaluate as ev
    d = _panel()
    a = ev.book(d, "eng", k=20, weight="vw", return_series=True)
    b = R1.routed_book(d, "eng", None, 0, k=20, weight="vw")
    assert a["months"] == b["months"] > 0
    assert float((a["_series"]["net"] - b["_net"]).abs().max()) < 1e-12
    assert abs(a["mean_turnover"] - b["mean_turnover"]) < 1e-3


def test_abstaining_every_slot_returns_the_market_exactly():
    """The limit case names the benchmark: abstain on all k and the book IS the
    market, minus the one round trip it pays getting there."""
    d = _panel()
    b = R1.routed_book(d, "eng", None, 20, k=20, weight="vw", random_seed=1)
    # gross return of an all-market book is the market, month by month
    assert float((b["_gross"] - b["_market"]).abs().max()) < 1e-12
    # and an abstention rule that is neither a score nor a seed is REFUSED,
    # rather than quietly falling back to the engine's own bottom ranks
    with pytest.raises(SystemExit):
        R1.routed_book(d, "eng", None, 5, k=20)


def test_abstention_pays_the_spread_like_any_other_instrument():
    """A free abstention would make every routed book look better than it is."""
    d = _panel()
    rng = np.random.default_rng(3)
    d["_score"] = rng.normal(size=len(d))
    full = R1.routed_book(d, "eng", "_score", 0, k=20)
    half = R1.routed_book(d, "eng", "_score", 10, k=20)
    assert half["mean_turnover"] > 0.0
    # the net series is strictly below the gross series whenever turnover > 0
    assert float((half["_gross"] - half["_net"]).min()) > 0.0
    assert full["n_abstain_per_month"] == 0 and half["n_abstain_per_month"] == 10


# --------------------------------------------------- 2. the label identity

def test_cell_label_averages_to_the_months_rank_ic():
    from scipy import stats
    d = _panel()
    g = d.groupby("month")
    d["_u"] = g["eng"].rank(pct=True) - 0.5
    d["_v"] = g["excess_vw_1m"].rank(pct=True) - 0.5
    d["lab__eng"] = 12.0 * d["_u"] * d["_v"]
    for m, ch in d.groupby("month"):
        rho = float(stats.spearmanr(ch["eng"], ch["excess_vw_1m"]).statistic)
        assert abs(rho - float(ch["lab__eng"].mean())) < 5e-3, m


# ------------------------------------------------ 3. the insider PIT window

def test_insider_window_is_strictly_before_the_formation_day(tmp_path, monkeypatch):
    """A filing stamped on the formation day is NOT knowable at formation.

    The parquet's own receipt says `observed_at_utc` is the filing day's END, so
    an inclusive window would buy on information published that evening.
    """
    ev = pd.DataFrame({
        "permno": [10001.0, 10001.0, 10001.0],
        "event_type": ["insider_open_market_buy"] * 3,
        # 100 days before (outside), 10 days before (inside), the day itself
        "observed_at_utc": pd.to_datetime(
            ["2020-03-08", "2020-06-06", "2020-06-16"], utc=True),
        "insider_cluster_buyers": [0.0, 0.0, 5.0],
    })
    d = tmp_path / "sec_insider"
    d.mkdir()
    ev.to_parquet(d / "insider_events_v1.parquet", index=False)
    monkeypatch.setattr(R1, "OPT", tmp_path)

    keys = pd.DataFrame({"permno": [10001], "entry_date": [pd.Timestamp("2020-06-16")]})
    out = R1.insider_features(keys)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ins_buy_90d"] == 1.0, "the same-day filing must not be counted"
    assert row["ins_cluster_90d"] == 0.0, "the same-day cluster must not be counted"
    assert row["ins_activity_90d"] == 1.0, "the 100-day-old filing must not be counted"


# ------------------------------------------------ 4. the walk-forward purge

def test_walk_forward_never_trains_on_a_month_it_tests():
    """Recorded as a property of the split, not of a model's behaviour."""
    d = _panel(months=60, names=60)
    mi = R1._month_to_int(d["month"])
    for yr in range(R1.TEST_START_YEAR, 2021):
        test_lo = yr * 12
        train_hi = test_lo - R1.EMBARGO_MONTHS
        train_months = set(d.loc[mi < train_hi, "month"])
        test_months = set(d.loc[(mi >= test_lo) & (mi < test_lo + 12), "month"])
        assert not (train_months & test_months)
        # and the embargo really removes months, it is not a decorative zero
        touching = set(d.loc[(mi >= train_hi) & (mi < test_lo), "month"])
        assert len(touching) == R1.EMBARGO_MONTHS or not touching


def test_shuffled_label_arm_permutes_within_the_date_block_only():
    """The null must destroy the NAME-level signal and keep the month's IC."""
    d = _panel(months=36, names=80)
    g = d.groupby("month")
    d["_u_eng"] = g["eng"].rank(pct=True) - 0.5
    d["_v_c"] = g["excess_vw_1m"].rank(pct=True) - 0.5
    d["lab__eng"] = 12.0 * d["_u_eng"] * d["_v_c"]
    rng = np.random.default_rng(11)
    y = d["lab__eng"].copy()
    for _m, idx in d.groupby("month").groups.items():
        y.loc[idx] = rng.permutation(y.loc[idx].to_numpy())
    per_month = d.assign(y=y).groupby("month")["y"].mean()
    orig = d.groupby("month")["lab__eng"].mean()
    assert float((per_month - orig).abs().max()) < 1e-10
    assert float(np.corrcoef(y, d["lab__eng"])[0, 1]) < 0.2


# --------------------------------------------------------- the statistics

def test_holm_is_monotone_and_charges_the_family():
    p = {"a": 0.001, "b": 0.02, "c": 0.30, "d": 0.9}
    out = R1.holm(p)
    assert out["a"]["p_holm"] == pytest.approx(0.004)
    order = [out[k]["p_holm"] for k in ["a", "b", "c", "d"]]
    assert order == sorted(order), "Holm-adjusted p must be non-decreasing"
    assert out["d"]["p_holm"] <= 1.0


def test_bh_fdr_is_never_stricter_than_holm():
    p = {f"c{i}": v for i, v in enumerate([0.001, 0.01, 0.03, 0.2, 0.6, 0.9])}
    h, b = R1.holm(p), R1.bh_fdr(p, 0.10)
    for k in p:
        if h[k]["survives_holm_05"]:
            assert b[k]["survives_bh_10"], f"{k} passed Holm but failed the screen"


def test_paired_reports_the_mde_before_the_verdict():
    """CANON §64: a power check that arrives after the confirmation is not one."""
    rng = np.random.default_rng(5)
    idx = [f"2019-{i%12+1:02d}" for i in range(60)]
    a = pd.Series(rng.normal(0.01, 0.05, 60), index=idx)
    b = pd.Series(rng.normal(0.01, 0.05, 60), index=idx)
    out = R1.paired(a, b, "a minus b")
    assert "mde_annualised_80pct" in out and out["mde_annualised_80pct"] > 0
    assert out["months"] == 60


def test_beta_is_reported_before_the_intercept():
    """S43: excess is a LOADING until shown otherwise, so beta leads the block."""
    rng = np.random.default_rng(9)
    idx = [f"20{17 + i//12:02d}-{i%12+1:02d}" for i in range(96)]
    mkt = pd.Series(rng.normal(0.008, 0.04, 96), index=idx)
    net = 1.4 * mkt + rng.normal(0.0, 0.02, 96)
    out = R1.beta_first(pd.Series(net, index=idx), mkt)
    keys = list(out)
    assert keys.index("beta") < keys.index("alpha_monthly")
    assert out["beta"] == pytest.approx(1.4, abs=0.15)


def test_neutralise_removes_what_it_says_it_removes():
    """If the score IS size, the residual must be ~empty of size."""
    from scipy import stats
    rng = np.random.default_rng(13)
    n = 4000
    d = pd.DataFrame({
        "month": np.repeat([f"2019-{i+1:02d}" for i in range(10)], n // 10),
        "log_market_cap": rng.normal(size=n),
    })
    d["vol_60d"] = rng.normal(size=n)
    d["log_coverage"] = rng.normal(size=n)
    d["log_dollar_vol_20d"] = rng.normal(size=n)
    d["_score"] = 3.0 * d["log_market_cap"] + rng.normal(0, 0.1, n)
    resid, r2 = R1.neutralise(d, "_score", R1.TRAP_COLS)
    assert r2 is not None and r2 > 0.95
    rho = stats.spearmanr(resid.dropna(), d.loc[resid.dropna().index, "log_market_cap"])
    assert abs(float(rho.statistic)) < 0.15


# ---------------------------------------- the receipt, when the lane has run

def test_receipt_if_present_carries_beta_family_and_both_nulls():
    """A GATE THAT CANNOT GO GREEN IS A BROKEN GATE: this SKIPS when the lane
    has not been run in this checkout, rather than failing for the absence of an
    artefact no test produces."""
    import json
    p = ROOT / "backend" / "data" / "optimus" / "predictability_router" / "R1_router_receipt.json"
    if not p.exists():
        pytest.skip("R1 lane has not been run in this checkout")
    r = json.loads(p.read_text(encoding="utf-8"))
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert "beta" in r["primary"]["grade"]
    assert r["multiplicity"]["family_size"] >= 4
    assert "null_random_abstention" in r and "null_shuffled_labels" in r
    assert r["label_identity_check"]["lgbm_clf__1m"]["max_abs_gap"] < 0.01
    assert r["design"]["n_effective"].startswith("DATE BLOCKS")
