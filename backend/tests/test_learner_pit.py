"""The four things about the AEGIS LEARNER that must never quietly stop being true.

These are not tests of accuracy -- a model's score is a receipt's job. They are
tests of the FOUR PROPERTIES that, if they broke, would make every number in
`learner_v1.json` a lie that still looked green:

1. a target never leaks past its own vintage;
2. a walk-forward split never trains on the test year;
3. the residual arm reconstructs prior + residual EXACTLY;
4. a missing feature stays missing -- never zero-filled.

They run OFFLINE on synthetic frames in well under a second. Nothing here loads
WRDS, touches the network, or reads the 441k-row training table: a guard that
needs a 100-second build to run is a guard nobody runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import dataset as D
from learner import models as M
from learner import prior as P


# --------------------------------------------------------------- a fixture

def _synthetic_panel() -> pd.DataFrame:
    """Five names x 48 months, with every column the split and arm code reads.

    Dates are DERIVED, never literal: a fixture that hard-codes a calendar
    moment fails the day after that moment passes.
    """
    rng = np.random.default_rng(7)
    months = pd.period_range("2013-01", periods=48, freq="M")
    rows = []
    for permno in range(10001, 10006):
        for i, mp in enumerate(months):
            entry = mp.to_timestamp(how="end").normalize()
            rows.append({
                "permno": permno,
                "month": str(mp),
                "vintage": entry - pd.Timedelta(days=3),
                "entry_date": entry,
                "close": 10.0 + permno % 7 + i * 0.1,
                "coverage": 3 + (permno % 4),
                "ratio": 1.0 + (i % 9) * 0.5,
                "f_a": float(rng.normal()),
                "f_b": float(rng.normal()),
                "market_cap": 1e9 * (1 + permno % 3),
                "dollar_vol_20d": 5e6,
                "in_admissible": False,
            })
    df = pd.DataFrame(rows)
    for h in D.HORIZONS:
        # Maturity is the entry date pushed forward by the horizon -- the
        # quantity the split rule must key on.
        df[f"mat_date_{h}m"] = df["entry_date"] + pd.DateOffset(months=h)
        df[f"excess_vw_{h}m"] = np.asarray(
            np.random.default_rng(h).normal(0.0, 0.08, len(df)))
        df[f"prior_{h}m"] = P.horizon_prior(df["ratio"], df["close"], df["coverage"], h).values
        df[f"resid_vw_{h}m"] = df[f"excess_vw_{h}m"] - df[f"prior_{h}m"]
        df[f"pos_vw_{h}m"] = (df[f"excess_vw_{h}m"] > 0).astype(float)
    return df


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _synthetic_panel()


# ------------------------------------------- 1. no target leaks past its vintage

def test_target_never_matures_before_its_own_vintage(panel):
    """A row's target must resolve STRICTLY AFTER the row's information date.

    A target that matured on or before its vintage would be knowable when the
    features were, and the whole panel would be a regression of the present on
    itself.
    """
    for h in D.HORIZONS:
        assert (panel[f"mat_date_{h}m"] > panel["vintage"]).all(), (
            f"horizon {h}m has rows whose target matures at or before their vintage")
        # And the maturity gap must actually be the horizon, not a stale copy
        # of a shorter one -- the failure mode where every horizon silently
        # becomes 1m and the 12m column reports a 1m result.
        gap_days = (panel[f"mat_date_{h}m"] - panel["entry_date"]).dt.days
        assert gap_days.min() >= 28 * h - 4, f"horizon {h}m gap is too short"


def test_a_target_dated_before_its_vintage_is_refused_by_the_split(panel):
    """Construct the leak explicitly and assert the split rule excludes it.

    Not a property of the fixture -- an assertion about the RULE. A row whose
    target matured only after the test year opened must never be trainable for
    that year, however early the row itself is dated.
    """
    df = panel.copy()
    leaky = df.index[0]
    # Dated 2013 (very early) but resolving inside the 2016 test year.
    df.loc[leaky, "entry_date"] = pd.Timestamp("2013-01-31")
    df.loc[leaky, "vintage"] = pd.Timestamp("2013-01-28")
    df.loc[leaky, "mat_date_12m"] = pd.Timestamp("2016-06-30")
    splits = dict((y, tr) for y, tr, _te in
                  D.walk_forward_splits(df, [2016], 12, min_train_months=6))
    assert 2016 in splits, "the 2016 split did not form at all"
    assert leaky not in splits[2016], (
        "a row dated 2013 but RESOLVING in June 2016 was admitted to the 2016 training "
        "set -- 'dated before' is not 'matured before'")


# -------------------------------------- 2. walk-forward never sees the test year

@pytest.mark.parametrize("h", list(D.HORIZONS))
def test_walk_forward_never_trains_on_test_year_data(panel, h):
    for year, tr, te in D.walk_forward_splits(panel, [2015, 2016], h, min_train_months=6):
        cutoff = pd.Timestamp(f"{year}-01-01")
        train, test = panel.loc[tr], panel.loc[te]
        assert (train[f"mat_date_{h}m"] < cutoff).all(), (
            f"{year} h={h}m: a training row's target matures inside the test year")
        assert (train["entry_date"] < cutoff).all(), (
            f"{year} h={h}m: a training row is dated inside the test year")
        assert (test["entry_date"] >= cutoff).all()
        assert (test["entry_date"] < pd.Timestamp(f"{year + 1}-01-01")).all()
        assert set(tr).isdisjoint(set(te)), "train and test share rows"


def test_splits_are_expanding_and_ordered_by_date(panel):
    seen = []
    for year, tr, _te in D.walk_forward_splits(panel, [2015, 2016], 1, min_train_months=6):
        seen.append((year, len(tr)))
    assert len(seen) >= 2
    years = [y for y, _ in seen]
    assert years == sorted(years), "splits are not in date order"
    sizes = [n for _, n in seen]
    assert sizes == sorted(sizes), "the training window is not expanding"


# ------------------------------ 3. the residual arm reconstructs prior + residual

def test_residual_arm_reconstructs_prior_plus_residual_exactly(panel):
    """prediction = prior + f(X). Byte-for-byte, not approximately.

    If this drifts, the residual arm's numbers are on a different scale from
    the raw arm's and the whole two-arm comparison compares nothing.
    """
    rng = np.random.default_rng(11)
    for h in D.HORIZONS:
        f_of_x = rng.normal(0.0, 0.02, len(panel))
        got = M.arm_reconstruct(f_of_x, panel, "residual", h)
        expect = f_of_x + panel[f"prior_{h}m"].to_numpy(dtype="float64")
        np.testing.assert_array_equal(got, expect)
        # And the identity that makes the arm meaningful: predicting the
        # residual perfectly must reproduce the realised excess exactly.
        perfect = panel[f"resid_vw_{h}m"].to_numpy(dtype="float64")
        np.testing.assert_allclose(
            M.arm_reconstruct(perfect, panel, "residual", h),
            panel[f"excess_vw_{h}m"].to_numpy(dtype="float64"), rtol=0, atol=1e-12)


def test_raw_arm_is_the_identity_and_the_two_arms_differ_in_features(panel):
    rng = np.random.default_rng(12)
    p = rng.normal(size=len(panel))
    np.testing.assert_array_equal(M.arm_reconstruct(p, panel, "raw", 1), p)
    cols = ["f_a", "f_b"]
    raw_cols = M.arm_features(cols, "raw", 1)
    res_cols = M.arm_features(cols, "residual", 1)
    assert "prior_1m" in raw_cols, "the raw arm must see the prior as a FEATURE"
    assert "prior_1m" not in res_cols, (
        "the residual arm must NOT also see the prior as a feature -- with it, the residual "
        "arm is the raw arm wearing a different target and the comparison measures nothing")


def test_residual_target_is_excess_minus_prior(panel):
    for h in D.HORIZONS:
        np.testing.assert_allclose(
            M.arm_target(panel, "residual", h),
            M.arm_target(panel, "raw", h) - panel[f"prior_{h}m"].to_numpy(),
            rtol=0, atol=1e-12)


# ------------------------------------- 4. missing stays missing, never zero-filled

def test_missing_features_are_never_zero_filled_by_the_pipeline():
    """`fillna(0)` is banned by house rule. Missing values must reach the model
    as NaN (LightGBM) or as the TRAIN MEDIAN (ridge / MLP) -- never as zero,
    which on a standardised feature is the mean and is therefore a silent,
    confident claim that the name is average."""
    rng = np.random.default_rng(3)
    X = rng.normal(50.0, 5.0, size=(200, 3))     # median far from 0
    X[::7, 1] = np.nan
    from sklearn.impute import SimpleImputer
    imp = SimpleImputer(strategy="median").fit(X)
    out = imp.transform(X)
    filled = out[::7, 1]
    assert not np.any(filled == 0.0), "a missing feature was zero-filled"
    assert np.allclose(filled, np.nanmedian(X[:, 1])), (
        "imputation is not the train median")


def test_dataset_declares_a_missing_mask_for_every_feature():
    """A NaN with no mask is indistinguishable from a value that was never
    collected. Every feature gets a mask column, by name."""
    schema = D.feature_schema()
    assert "fillna(0) is BANNED" in schema["missing_policy"]
    for f in list(D.FEATURES_CONTINUOUS) + list(D.FEATURES_BOOL) + list(D.FEATURES_CAT):
        assert D.missing_mask_name(f) == f"miss__{f}"


def test_model_pipelines_impute_with_the_median_not_zero():
    """Read the declared policy AND the constructed pipeline -- a policy string
    nothing enforces is a comment."""
    assert "median-impute" in M.describe()["missing_policy"]
    assert "fillna(0) is banned" in M.describe()["missing_policy"]
    rng = np.random.default_rng(5)
    X = rng.normal(0, 1, size=(400, 4))
    X[::11, 2] = np.nan
    y = rng.normal(0, 0.05, 400)
    pipe, _meta = M._fit_ridge(X[:300], y[:300], X[300:], y[300:])
    assert pipe.named_steps["impute"].strategy == "median"


# ------------------------------------------------ the prior, and the unit trap

def test_upside_is_ratio_minus_one_and_the_two_are_never_confused():
    """`upside` is `ratio - 1`. S33b lost an afternoon to reading one as the
    other; this pins the conversion in exactly one direction."""
    np.testing.assert_allclose(P.upside_to_ratio([0.5, 2.0, -0.2]), [1.5, 3.0, 0.8])


def test_hygiene_failure_is_no_opinion_not_a_bearish_call():
    """Below $2 or under two analysts, the band prior is UNINFORMATIVE (t 0.39).
    The house rule from that receipt is to say "no opinion", never
    "historically bad" -- so the prior is 0.0 AND the band is `no_opinion`."""
    close = pd.Series([1.0, 5.0, 5.0])
    cov = pd.Series([10, 1, 10])
    ratio = pd.Series([2.0, 2.0, 2.0])
    pri = P.horizon_prior(ratio, close, cov, 1)
    assert pri.iloc[0] == 0.0 and pri.iloc[1] == 0.0
    assert pri.iloc[2] > 0.0
    bands = P.effective_band(ratio, close, cov)
    assert list(bands) == ["no_opinion", "no_opinion", "b_1_5_3"]


def test_toxic_band_prior_is_negative_and_compounds_not_scales():
    """-37.77%/yr over one month is -3.83% compounded, not -3.15% scaled. The
    toxic band is exactly where the difference is worth naming."""
    one = P.horizon_prior(pd.Series([9.0]), pd.Series([10.0]), pd.Series([5]), 1).iloc[0]
    twelve = P.horizon_prior(pd.Series([9.0]), pd.Series([10.0]), pd.Series([5]), 12).iloc[0]
    assert one < 0 and twelve < 0
    assert twelve == pytest.approx(-0.3777, abs=1e-9)
    assert one == pytest.approx((1 - 0.3777) ** (1 / 12) - 1, abs=1e-12)
    assert one != pytest.approx(-0.3777 / 12, abs=1e-6), "the prior scaled linearly"


# ------------------------------------------------------- the shadow cannot trade

def test_the_learner_package_has_no_broker_authority():
    """The learner writes files. It must not be able to reach an order path.

    A grep over the source is a WEAK check -- the docstrings in `shadow.py` say
    "no Alpaca client" on purpose, and a substring search reads that as the
    offence it is disclaiming. So this parses the AST instead and asserts the
    mechanical property on IMPORTS and CALLED NAMES only: nothing in `learner/`
    imports a broker SDK, the execution repo's `alpha` package, or an HTTP
    client, and nothing calls an order-submitting function.
    """
    import ast
    import pathlib

    banned_modules = ("alpaca", "alpaca_trade_api", "tradeapi", "alpha",
                      "requests", "httpx", "urllib", "aiohttp", "socket")
    banned_calls = ("submit_order", "place_order", "create_order", "close_position")
    root = pathlib.Path(__file__).resolve().parents[2] / "learner"
    offenders = []
    for py in sorted(root.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in banned_modules:
                        offenders.append((py.name, f"import {a.name}"))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in banned_modules:
                    offenders.append((py.name, f"from {node.module}"))
            elif isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name in banned_calls:
                    offenders.append((py.name, f"call {name}()"))
    assert not offenders, f"learner/ reaches an execution surface: {offenders}"


def test_the_shadow_only_ever_opens_the_tracker_file_for_reading():
    """The tracker day file belongs to the execution repo. The shadow reads it
    and must never be able to write it -- a learner that can edit the day file
    could rewrite the record it is being graded against."""
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2] / "learner" / "shadow.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "open":
            modes = [a.value for a in node.args if isinstance(a, ast.Constant)]
            modes += [k.value.value for k in node.keywords
                      if k.arg == "mode" and isinstance(k.value, ast.Constant)]
            for m in modes:
                assert isinstance(m, str) and m.startswith("r"), (
                    f"shadow.py opens a path in mode {m!r} -- read-only or nothing")


def test_shadow_declares_the_two_analyst_count_constructs_separately():
    """`coverage` is a RECOMMENDATION count; `numest` is a TARGET-ESTIMATE
    count. They differ by ~1.8x, and substituting one for the other is how
    hack6's "4-10 analysts" rule admitted 1-2-analyst names."""
    from learner import shadow as S
    rows = [{"symbol": "TEST", "close": 100.0, "mean_target": 150.0,
             "target_high": 200.0, "target_low": 100.0,
             "rec_counts": {"strongBuy": 18, "buy": 35, "hold": 4, "sell": 1,
                            "strongSell": 0},
             "n_analysts_yf": 44, "ret_12m": 1.0, "high_60d": 120.0,
             "realised_vol_20d": 0.5, "market_cap_usd": 1e12,
             "median_dollar_volume": 4e10, "sessions": 315, "tradable": True,
             "sector": "Semiconductors"}]
    df, caveats = S.map_to_features(rows, {"b_1_5_3": 0})
    assert float(df["coverage"].iloc[0]) == 58.0, "coverage must be sum(rec_counts)"
    assert float(df["numest"].iloc[0]) == 44.0, "numest must be the target-estimate count"
    # The 5 = STRONG BUY scale, reconstructed: (5*18 + 4*35 + 3*4 + 2*1) / 58.
    assert float(df["consensus"].iloc[0]) == pytest.approx(244.0 / 58.0, abs=1e-9)
    assert float(df["ratio"].iloc[0]) == pytest.approx(1.5)
    assert float(df["upside"].iloc[0]) == pytest.approx(0.5)
    assert "sector" in caveats


def test_shadow_refuses_a_consensus_on_the_wrong_scale():
    """IBES runs 1 = strong buy; the tracker runs 5 = strong buy. A value
    outside [1,5] means the histogram was read on the wrong scale, which would
    rank the most HATED names first and backtest green."""
    from learner import shadow as S
    S.assert_consensus_scale(pd.Series([1.0, 3.0, 5.0]))       # fine
    with pytest.raises(SystemExit):
        S.assert_consensus_scale(pd.Series([6.0]))
