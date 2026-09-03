"""The properties LEARNER v2 adds, and the v1 surface it must not have moved.

`backend/tests/test_learner_pit.py` pins v1 and is not touched by this file.
These are the FIVE new things that, if they broke, would make every number in
`learner_v2_20260903.json` a lie that still looked green:

1. a multi-horizon fit masks each horizon's target by ITS OWN maturity date --
   the one leak a shared-trunk architecture invites;
2. the encoder's residual form reconstructs `prior + f(X)` exactly, and its
   trunk never sees a prior column;
3. a temporal calibrator is never fitted on the month it scores;
4. an overlapping book actually HOLDS for h months, and a name whose return
   goes missing becomes cash rather than vanishing from the denominator;
5. v1's `evaluate.book()` still returns exactly the keys v1's receipt recorded
   -- the v2 additions are opt-in flags, not a changed default.

They run OFFLINE on synthetic frames in about a second. Nothing here loads
WRDS, touches the network, or reads the 441k-row training table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import calibrate as C
from learner import dataset as D
from learner import encoder as EN
from learner import evaluate as E
from learner import prior as P


# --------------------------------------------------------------- a fixture

def _panel(n_names: int = 8, n_months: int = 60) -> pd.DataFrame:
    """Names x months with every column the v2 code reads.

    Dates are DERIVED from a base period, never literal: a fixture that
    hard-codes a calendar moment fails the day after that moment passes.
    """
    rng = np.random.default_rng(11)
    months = pd.period_range("2013-01", periods=n_months, freq="M")
    rows = []
    for j, permno in enumerate(range(10001, 10001 + n_names)):
        for i, mp in enumerate(months):
            entry = mp.to_timestamp(how="end").normalize()
            rows.append({
                "permno": permno, "month": str(mp),
                "vintage": entry - pd.Timedelta(days=3), "entry_date": entry,
                "close": 10.0 + j + i * 0.1, "coverage": 3 + (j % 4),
                "ratio": 1.0 + (i % 9) * 0.5,
                "f_a": float(rng.normal()), "f_b": float(rng.normal()),
                "market_cap": 1e9 * (1 + j % 3),
                "log_dollar_vol_20d": float(np.log1p(5e6)),
                "in_admissible": False, "sector_code": j % 5, "band_code": i % 4,
            })
    df = pd.DataFrame(rows)
    for h in D.HORIZONS:
        df[f"mat_date_{h}m"] = df["entry_date"] + pd.DateOffset(months=h)
        df[f"excess_vw_{h}m"] = rng.normal(0.0, 0.05 * np.sqrt(h), len(df))
        df[f"prior_{h}m"] = P.horizon_prior(df["ratio"], df["close"],
                                            df["coverage"], h).values
        df[f"resid_vw_{h}m"] = df[f"excess_vw_{h}m"] - df[f"prior_{h}m"]
        df[f"pos_vw_{h}m"] = (df[f"excess_vw_{h}m"] > 0).astype(float)
    df["fwd_1m"] = df["excess_vw_1m"] + 0.008
    df["mkt_vw_1m"] = 0.008
    return df


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _panel()


# ------------------ 1. the multi-horizon mask is per horizon, not per row

def test_multi_horizon_mask_uses_each_horizons_own_maturity_date(panel):
    """The leak a shared trunk invites: admit a row because its 1m target
    matured, then train the 12m head on it too."""
    year = 2016
    cutoff = pd.Timestamp(f"{year}-01-01")
    got = list(EN.multi_horizon_splits(panel, [year], min_train_months=6))
    assert got, "no split formed at all"
    _y, tr, _te, masks = got[0]
    train = panel.loc[tr]
    for h in EN.HORIZONS:
        md = train[f"mat_date_{h}m"].to_numpy()
        m = np.asarray(masks[h], bool)
        assert len(m) == len(train), f"mask for {h}m is not aligned to the train index"
        assert (pd.Series(md[m]) < cutoff).all(), (
            f"the {h}m mask admits rows whose {h}m target matures on or after "
            f"{cutoff.date()} -- the 12m head would be trained on the test year")


def test_a_row_can_be_a_1m_example_and_not_a_12m_one(panel):
    """The mask must be able to disagree with itself across horizons.

    If every horizon's mask were the same array the guard above would pass
    vacuously -- and it would pass on the buggy 'admit if ANY matured'
    implementation too, because that one also produces four identical masks.
    """
    year = 2016
    _y, tr, _te, masks = next(iter(EN.multi_horizon_splits(panel, [year],
                                                           min_train_months=6)))
    m1, m12 = np.asarray(masks[1], bool), np.asarray(masks[12], bool)
    assert m1.sum() > m12.sum(), (
        "the 1m and 12m masks admit the same rows -- the per-horizon mask is not "
        "doing anything, which is exactly the leak this design exists to close")
    assert (m12 & ~m1).sum() == 0, "a 12m-matured row that is not 1m-matured is impossible"


def test_multi_horizon_test_rows_are_inside_the_test_year_only(panel):
    for year, _tr, te, _m in EN.multi_horizon_splits(panel, [2016, 2017],
                                                     min_train_months=6):
        d = panel.loc[te, "entry_date"]
        assert d.min() >= pd.Timestamp(f"{year}-01-01")
        assert d.max() < pd.Timestamp(f"{year + 1}-01-01")


def test_train_rows_never_overlap_the_test_year(panel):
    for year, tr, _te, masks in EN.multi_horizon_splits(panel, [2016, 2017],
                                                        min_train_months=6):
        cutoff = pd.Timestamp(f"{year}-01-01")
        for h in EN.HORIZONS:
            m = np.asarray(masks[h], bool)
            if m.sum() == 0:
                continue
            assert panel.loc[tr, f"mat_date_{h}m"].to_numpy()[m].max() < cutoff


# ---------------------------- 2. the encoder's arms mean what they say

def test_encoder_residual_reconstructs_prior_plus_correction_exactly(panel):
    raw = np.linspace(-0.05, 0.05, len(panel))
    for h in EN.HORIZONS:
        got = EN.reconstruct(raw, panel, "residual", h)
        want = raw + panel[f"prior_{h}m"].to_numpy()
        assert np.allclose(got, want, rtol=0, atol=0), (
            f"the {h}m residual reconstruction is not prior + correction")
        assert np.array_equal(EN.reconstruct(raw, panel, "raw", h), raw), (
            "the raw arm must be the identity on the excess scale")


def test_the_residual_trunk_never_sees_a_prior_column():
    cols = ["f_a", "f_b", "ratio"]
    res = EN.arm_feature_cols(cols, "residual")
    raw = EN.arm_feature_cols(cols, "raw")
    assert not [c for c in res if c.startswith("prior_")], (
        "the residual trunk sees a prior column -- it would then be the raw arm "
        "wearing a different target and the comparison would measure nothing")
    assert [c for c in raw if c.startswith("prior_")] == ["prior_1m"], (
        "the raw arm must carry EXACTLY one prior column: prior_h is a monotone "
        "function of prior_1m, so four copies are four chances to overfit one number")


def test_encoder_target_columns_are_excess_for_raw_and_residual_for_residual():
    for h in EN.HORIZONS:
        assert EN.arm_target_col("raw", h) == f"excess_vw_{h}m"
        assert EN.arm_target_col("residual", h) == f"resid_vw_{h}m"


def test_the_feature_clip_bounds_the_input_and_does_not_zero_fill():
    """The clip is load-bearing: without it the regression heads returned an sd
    of 15.3 in excess-return units. It must bound, and it must not become a
    disguised `fillna(0)`."""
    X = np.array([[0.0, 1.0], [50.0, -80.0], [-3.0, 2.0]])
    out = EN.ClipSD(clip=5.0).fit(X).transform(X)
    assert out.max() <= 5.0 and out.min() >= -5.0
    assert out[1, 0] == 5.0 and out[1, 1] == -5.0, "clipping must saturate, not zero"
    assert out[2, 0] == -3.0, "a value inside the bound must be untouched"


def test_the_shuffled_null_permutes_inside_the_month_and_keeps_y_with_its_label():
    """S24: a shuffled-DATE null tests the calendar, not the plumbing. And the
    return and its 0/1 label must move TOGETHER or the two heads are trained
    against different nulls."""
    month = np.array(["2013-01"] * 5 + ["2013-02"] * 5)
    y = np.arange(10, dtype="float64")
    b = (y > 4.5).astype("float64")
    m = np.ones(10, bool)
    ys, bs = EN._shuffle_within_month(y, b, m, month, np.random.default_rng(3))
    for lo, hi in ((0, 5), (5, 10)):
        assert sorted(ys[lo:hi]) == sorted(y[lo:hi]), (
            "values crossed a month boundary -- that is a shuffled-DATE null")
    assert np.array_equal(bs, (ys > 4.5).astype("float64")), (
        "the label did not travel with its return")


# ------------------------------ 3. a calibrator never scores its own fit rows

def test_temporal_calibrator_never_fits_on_the_month_it_scores():
    """Constructed as a counterfactual, not asserted from the code.

    If the mapping for month M were fitted on month M, changing month M's
    OUTCOMES would change month M's calibrated predictions. It must not.
    """
    rng = np.random.default_rng(5)
    n_months, per = 40, 300
    months = np.repeat([f"20{13 + i // 12:02d}-{i % 12 + 1:02d}" for i in range(n_months)], per)
    p = rng.uniform(0.3, 0.7, n_months * per)
    y = (rng.uniform(size=n_months * per) < p).astype(float)
    cal_a, _ = C.temporal_calibrate(y, p, months, method="platt", min_train_months=12)
    last = months == months[-1]
    y_b = y.copy()
    y_b[last] = 1.0 - y_b[last]                # flip every outcome in the last month
    cal_b, _ = C.temporal_calibrate(y_b, p, months, method="platt", min_train_months=12)
    assert np.isfinite(cal_a[last]).any(), "the last month was never calibrated at all"
    assert np.allclose(cal_a[last], cal_b[last], equal_nan=True), (
        "flipping a month's outcomes changed that month's calibrated predictions -- "
        "the calibrator is being fitted on the rows it scores")


def test_months_without_enough_history_are_nan_not_silently_raw():
    rng = np.random.default_rng(6)
    months = np.repeat([f"2013-{i + 1:02d}" for i in range(12)]
                       + [f"2014-{i + 1:02d}" for i in range(12)], 300)
    p = rng.uniform(0.3, 0.7, len(months))
    y = (rng.uniform(size=len(months)) < p).astype(float)
    cal, meta = C.temporal_calibrate(y, p, months, method="isotonic", min_train_months=12)
    early = np.isin(months, [f"2013-{i + 1:02d}" for i in range(12)])
    assert np.isnan(cal[early]).all(), (
        "a month with no calibration history came back with a number -- a table half "
        "raw and half calibrated, labelled calibrated, is worse than an honest hole")
    assert meta["months_without_history"] == 12


def test_brier_and_reliability_are_arithmetic_not_opinion():
    y = np.array([1.0, 1.0, 0.0, 0.0])
    assert C.brier(y, y) == pytest.approx(0.0)
    assert C.brier(y, np.full(4, 0.5)) == pytest.approx(0.25)
    assert C.base_rate(y) == pytest.approx(0.5)
    rng = np.random.default_rng(2)
    p = rng.uniform(0.2, 0.8, 5000)
    yy = (rng.uniform(size=5000) < p).astype(float)
    rel = C.reliability(yy, p, n_bins=10)
    assert rel["n_bins"] == 10
    assert sum(b["n"] for b in rel["bins"]) == 5000
    assert rel["ece"] >= 0.0
    # A perfectly calibrated generator must land near the diagonal.
    assert rel["ece"] < 0.03 and 0.7 < rel["reliability_slope"] < 1.3


def test_the_reference_for_a_probability_is_the_base_rate_not_one_half():
    """The whole point of the module: 0.49 read against 0.5 is bearish, read
    against a base rate of 0.45 it is not."""
    y = np.zeros(1000)
    y[:450] = 1.0
    p = np.full(1000, 0.49)
    blk = C.score_block(y, p)
    assert blk["base_rate_realised"] == pytest.approx(0.45)
    assert blk["mean_predicted_minus_base_rate"] == pytest.approx(0.04)


# ------------------------------------- 4. the overlapping book actually holds

def test_overlapping_book_holds_for_the_whole_horizon(panel):
    df = panel.copy()
    df["pred"] = np.linspace(0, 1, len(df))
    b1 = E.overlapping_book(df, "pred", 1, k=3)
    b12 = E.overlapping_book(df, "pred", 12, k=3)
    assert b1["mean_live_cohorts"] == pytest.approx(1.0)
    assert b12["mean_live_cohorts"] > 6.0, (
        "a 12-month book is running roughly one live cohort -- it is not holding")
    assert b12["mean_turnover"] < b1["mean_turnover"], (
        "holding 12 months did not reduce turnover below monthly rebalancing, which "
        "means the cohorts are being rebuilt every month")
    assert b12["horizon_months"] == 12


def test_a_name_whose_return_goes_missing_becomes_cash_not_a_deletion():
    """Deleting a dead name from the denominator is survivorship bias with
    extra steps: the book would report the survivors' return as the book's."""
    rows = []
    for permno in (1, 2):
        for i, m in enumerate(["2013-01", "2013-02", "2013-03"]):
            r = 0.10 if permno == 1 else 0.10
            if permno == 2 and i > 0:
                r = np.nan                      # name 2 dies after month 1
            rows.append({"permno": permno, "month": m, "pred": 1.0,
                         "fwd_1m": r, "mkt_vw_1m": 0.0, "market_cap": 1e9})
    df = pd.DataFrame(rows)
    b = E.overlapping_book(df, "pred", 3, k=2, weight="ew")
    # Month 2: the first cohort holds half a live name (+10%) and half cash (0%).
    assert b["months"] >= 2
    assert b["terminal_wealth_net"] < (1.10 ** 3), (
        "the book compounded as if the dead name kept earning -- it was deleted, "
        "not liquidated into cash")
    assert b["terminal_wealth_net"] > 1.0, "the surviving name's return vanished too"


def test_overlapping_book_refuses_a_liquidity_floor_it_cannot_compute():
    """A GATE THAT CANNOT FIRE IS A BROKEN GATE -- v1 shipped one that silently
    passed everything for exactly this reason."""
    df = pd.DataFrame({"permno": [1, 2], "month": ["2013-01", "2013-01"],
                       "pred": [1.0, 2.0], "fwd_1m": [0.01, 0.02],
                       "mkt_vw_1m": [0.0, 0.0], "market_cap": [1e9, 1e9]})
    with pytest.raises(SystemExit, match="REFUSED"):
        E.overlapping_book(df, "pred", 3, k=2, tradable_floor=3e6)


def test_risk_stats_measure_the_wealth_path_not_the_worst_month():
    """A drawdown computed on returns is a worst month with a longer name."""
    r = pd.Series([0.10, -0.10, -0.10, -0.10, 0.05])
    dd = E.max_drawdown(r)
    assert dd is not None and dd < -0.25, (
        "three consecutive -10% months produced a drawdown no worse than one of them")
    assert dd < r.min(), "the drawdown is not deeper than the single worst month"


def test_paired_difference_is_computed_on_shared_months_with_n_equal_months():
    a = pd.Series({"2013-01": 0.02, "2013-02": 0.03, "2013-03": 0.01})
    b = pd.Series({"2013-01": 0.01, "2013-02": 0.01, "2013-04": 0.09})
    d = E.paired_difference(a, b, "a", "b")
    assert d["months"] == 2, "the difference used a month one side did not have"
    assert d["mean_monthly_difference"] == pytest.approx(0.015)


# ------------- 4b. an overlapping target's t is corrected, not republished

def test_an_overlapping_series_loses_roughly_sqrt_h_of_its_naive_t():
    """The artefact `docs/TRIAL_RESULT_2026-09-03_BAND_HORIZON.md` measured on
    the engine prior: a 12-month target sampled monthly counts one history
    twelve times, and the naive t rises for a purely mechanical reason.

    Built as a construction, not asserted from a fit: iid monthly shocks summed
    into rolling 12-month windows have a KNOWN overlap and no extra signal.
    """
    rng = np.random.default_rng(1)
    x = rng.normal(0.01, 0.05, 400)
    ov = pd.Series([x[i:i + 12].sum() for i in range(len(x) - 12)])
    got = E.overlap_corrected(ov, 12)
    assert got["t_naive"] is not None and got["t_newey_west"] is not None
    assert got["t_newey_west"] < got["t_naive"] / 2.0, (
        "the Newey-West t did not deflate a series that overlaps twelve-fold")
    assert got["block_n_effective"] == pytest.approx(len(ov) // 12, abs=1)
    assert got["block_t_block"] < got["t_naive"] / 2.0


def test_a_one_month_series_is_not_deflated():
    """The correction must not fire where there is nothing to correct -- a
    guard that always deflates is a guard that says nothing."""
    rng = np.random.default_rng(4)
    s = pd.Series(rng.normal(0.01, 0.05, 200))
    got = E.overlap_corrected(s, 1)
    assert "t_newey_west" not in got
    assert got["t_naive"] is not None
    assert "does not overlap" in got["read_as"]


def test_hac_and_block_agree_on_an_iid_series():
    rng = np.random.default_rng(9)
    s = pd.Series(rng.normal(0.02, 0.05, 600))
    from learner.evaluate import _t_from_series
    naive = _t_from_series(s)
    hac = E.hac_t(s, lag=5)
    assert hac is not None and abs(hac - naive) < 0.35 * abs(naive), (
        "HAC moved an iid series materially -- it is correcting noise, not overlap")


def test_monthly_ic_series_is_one_number_per_month(panel):
    df = panel.copy()
    df["pred"] = np.linspace(0, 1, len(df))
    s = E.monthly_ic_series(df, "pred", "excess_vw_1m", min_names=5)
    assert len(s) == df["month"].nunique()
    assert s.index.is_monotonic_increasing
    assert ((s >= -1.0) & (s <= 1.0)).all()


# ------------------------------------------ 5. the v1 surface did not move

def test_v1_book_still_returns_exactly_the_keys_v1_recorded(panel):
    """v2 added `with_risk` and `return_series` to `evaluate.book`. Both must be
    OFF by default, or v1's receipt stops being reproducible by v1's own code.
    """
    df = panel.copy()
    df["pred"] = np.linspace(0, 1, len(df))
    default = E.book(df, "pred", k=3)
    expected = {
        "months", "k", "weight", "cost_bps_per_side", "tradable_floor_usd",
        "rows_after_tradable_floor", "mean_names_per_month", "mean_turnover",
        "terminal_wealth_net", "terminal_wealth_gross",
        "terminal_wealth_market_same_months", "cagr_net", "cagr_market",
        "mean_monthly_excess", "annualised_excess", "t_stat_paired_vs_market",
        "months_beating_market", "worst_month_net", "hit_rate",
    }
    assert set(default) == expected, (
        "evaluate.book()'s DEFAULT output changed shape -- learner_v1.json is no "
        "longer reproducible by the code that wrote it")
    assert "risk" in E.book(df, "pred", k=3, with_risk=True)
    assert "_series" in E.book(df, "pred", k=3, return_series=True)


def test_v1_numbers_are_unchanged_by_the_v2_flags(panel):
    df = panel.copy()
    df["pred"] = np.linspace(0, 1, len(df))
    a = E.book(df, "pred", k=3)
    b = E.book(df, "pred", k=3, with_risk=True, return_series=True)
    for key in a:
        assert a[key] == b[key], f"{key} moved when a v2 flag was switched on"


def test_v2_runner_and_new_modules_have_no_broker_authority():
    """The v1 test globs `learner/*.py` and so already covers encoder.py and
    calibrate.py. The v2 RUNNER lives in `scripts/` and would not be covered,
    so it is asserted here rather than assumed."""
    import ast
    import pathlib

    banned_modules = ("alpaca", "alpaca_trade_api", "tradeapi", "alpha",
                      "requests", "httpx", "urllib", "aiohttp", "socket")
    banned_calls = ("submit_order", "place_order", "create_order", "close_position")
    src = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "learner_v2_run.py"
    assert src.exists(), "the v2 runner is missing"
    offenders = []
    for node in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            offenders += [f"import {a.name}" for a in node.names
                          if a.name.split(".")[0] in banned_modules]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in banned_modules:
                offenders.append(f"from {node.module}")
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in banned_calls:
                offenders.append(f"call {name}()")
    assert not offenders, f"scripts/learner_v2_run.py reaches an execution surface: {offenders}"


def test_the_v2_receipt_path_is_not_the_v1_receipt_path():
    """v2 must never overwrite v1's receipt: v1 is the benchmark v2 is measured
    against, and a benchmark that gets rewritten by its challenger is not one."""
    from scripts import learner_v2_run as R

    assert R.RECEIPT != R.V1_RECEIPT
    assert R.RECEIPT.name == "learner_v2_20260903.json"
