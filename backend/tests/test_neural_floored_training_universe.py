"""W3b: the properties that separate a FLOORED TRAINING UNIVERSE from a floored book.

W3 fitted the neural encoder on all 925,757 panel rows and then restricted the
BOOK to names trading $3m a day above $5. W3b applies the same floor one stage
earlier -- to the rows the model is fitted on. The two are easy to confuse, they
produce receipts that look alike, and the difference is the entire experiment.
So the things that would make the W3b receipt a relabelled W3 receipt are pinned
here rather than asserted in a docstring:

1. **the floor actually removes rows, and every survivor clears BOTH halves.**
   `evaluate.book`'s first floor asked for a column the panel does not carry,
   found it absent and skipped the filter in SILENCE -- so a book labelled
   `tradable_3m` was byte-identical to the unfiltered one. The same silence is
   available here and would be worse: a "floored training universe" that quietly
   trained on everything makes W3b a re-run of W3 under a new heading.
2. **a missing liquidity column REFUSES.** Derive the input or refuse; never
   pass everything.
3. **unknown is not tradable.** A row whose price or dollar volume is NaN is
   dropped. "We could not tell" is not evidence that it was buyable.
4. **fitting on the floored universe changes the predictions.** This is THE
   property. If `run_neural` on the floored panel returned what `run_neural` on
   the full panel returns for the same rows, then the floor never reached the
   fit and W3b would be measuring W3.
5. **the grading floor is then a no-op** -- the proof that the training universe
   and the graded universe are the same population, not two.
6. **`job(universe_floor=...)` is off by default**, so W3's own receipts are
   unchanged, and the family id CHANGES when it is on, so two incompatible cell
   populations cannot pool into one deflation.
7. **`lgbm_clf` returns a probability**, ranked directly and never rescaled onto
   an excess-return axis.
8. **the declared decision rule on disk still matches the rule in the code** --
   the tamper-evidence that "we set the bar before we saw the number" rests on.

Everything runs OFFLINE on a synthetic frame. Nothing loads WRDS, touches the
network, or reads the 925k-row long panel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learner import dataset as DS

NL = pytest.importorskip("learner.neural_long")
torch = pytest.importorskip("torch")

pytestmark = pytest.mark.skipif(not NL._TORCH, reason="torch is not installed")

REPO = Path(__file__).resolve().parents[2]
TEST_YEARS = [2018]


def _panel(n_names: int = 60, n_months: int = 84) -> pd.DataFrame:
    """A frame carrying every column the floored job reads, and nothing else.

    Dates are DERIVED from a base period, never literal: a fixture that hardcodes
    a calendar moment fails the day after that moment passes.

    `log_dollar_vol_20d` spans $100k to $100m a day and `close` spans roughly $2
    to $60, so the $3m/day + $5 floor removes SOME rows and not all of them. A
    fixture where the floor empties the frame would make every assertion below
    vacuously true, which is the shape of a gate that cannot go green.
    """
    rng = np.random.default_rng(20260906)
    months = pd.period_range("2013-01", periods=n_months, freq="M")
    permnos = np.arange(10001, 10001 + n_names)
    idx = pd.MultiIndex.from_product([permnos, months], names=["permno", "mp"])
    df = pd.DataFrame(index=idx).reset_index()
    df["month"] = df["mp"].astype(str)
    df["entry_date"] = df["mp"].dt.to_timestamp(how="end").dt.normalize()
    df["vintage"] = df["entry_date"] - pd.Timedelta(days=3)
    df = df.drop(columns=["mp"])

    n = len(df)
    for c in NL.feature_cols():
        df[c] = rng.normal(size=n)
    df.loc[rng.random(n) < 0.2, DS.FEATURES_CONTINUOUS[0]] = np.nan

    df["excess_vw_1m"] = (0.02 * df[DS.FEATURES_CONTINUOUS[1]]
                          + rng.standard_t(2.0, size=n) * 0.03)
    df["mat_date_1m"] = df["entry_date"] + pd.DateOffset(months=1)
    df["mkt_vw_1m"] = 0.006
    df["fwd_1m"] = df["excess_vw_1m"] + df["mkt_vw_1m"]
    df["pos_vw_1m"] = (df["excess_vw_1m"] > 0).astype("float64")
    df["market_cap"] = 1e9 * (1.0 + (df["permno"] % 7))
    df["prior_1m"] = 0.0
    df["close"] = np.exp(rng.normal(np.log(9.0), 0.7, n))
    df["log_dollar_vol_20d"] = np.log1p(10.0 ** rng.uniform(5.0, 8.0, n))
    return df.reset_index(drop=True)


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _panel()


@pytest.fixture(scope="module")
def device():
    dev, info = NL.resolve_device()
    return dev, info


# ------------------------------------------ 1. the floor is not a no-op, and binds

def test_the_floor_removes_rows_and_every_survivor_clears_both_halves(panel):
    out, rec = NL.tradable_universe(panel)
    assert rec["rows_removed"] > 0, (
        "the floor removed NOTHING -- either the fixture is already floored or the "
        "filter never fired, and a receipt claiming a floored fit would be false")
    assert 0 < len(out) < len(panel), "the floor emptied the frame or kept all of it"
    dv = np.expm1(out["log_dollar_vol_20d"].to_numpy())
    assert (dv >= NL.TRADABLE_FLOOR_USD).all()
    assert (out["close"].to_numpy() >= NL.TRADABLE_MIN_CLOSE).all()
    assert rec["rows_before"] == len(panel)
    assert rec["rows_after"] == len(out)
    assert rec["rows_before"] - rec["rows_after"] == rec["rows_removed"]
    assert "warning" not in rec


def test_the_floor_is_the_house_floor_and_not_a_second_copy_of_it():
    """One floor, one place. A local 3_000_000.0 would drift the day the house
    one moved, and the receipt would still say `TRADABLE_DOLLAR_VOL`."""
    from learner import evaluate
    assert NL.TRADABLE_FLOOR_USD is evaluate.TRADABLE_DOLLAR_VOL \
        or NL.TRADABLE_FLOOR_USD == evaluate.TRADABLE_DOLLAR_VOL


# ------------------------------------------------- 2/3. refusals and unknowns

def test_a_missing_liquidity_column_refuses_rather_than_passing_everything(panel):
    bad = panel.drop(columns=["log_dollar_vol_20d"])
    with pytest.raises(SystemExit) as exc:
        NL.tradable_universe(bad)
    assert "REFUSED" in str(exc.value)


def test_a_missing_price_column_refuses_when_a_price_floor_was_asked_for(panel):
    bad = panel.drop(columns=["close"])
    with pytest.raises(SystemExit) as exc:
        NL.tradable_universe(bad)
    assert "REFUSED" in str(exc.value)
    # ... and does NOT refuse when no price floor was requested
    out, rec = NL.tradable_universe(bad, min_close=None)
    assert len(out) > 0 and rec["min_close_usd"] is None


def test_unknown_liquidity_is_dropped_not_kept(panel):
    d = panel.copy()
    hit = d.index[:200]
    d.loc[hit, "log_dollar_vol_20d"] = np.nan
    d.loc[d.index[200:300], "close"] = np.nan
    out, rec = NL.tradable_universe(d)
    assert not out.index.intersection(hit).size, (
        "a row whose dollar volume is unknown survived the floor -- 'we could not "
        "tell' is not evidence that it was tradable")
    assert out["close"].notna().all()
    assert rec["rows_with_unknown_dollar_volume_dropped"] == 200


# ------------------------------- 4. THE property: the fit itself sees the floor

def test_fitting_on_the_floored_universe_changes_the_predictions(panel, device):
    """W3b vs W3, in one assertion.

    Fit on the FULL panel and read the predictions for the floored rows; fit on
    the FLOORED panel and read the predictions for the same rows. If those agreed
    the floor never reached the fit -- the pipeline's medians and standard
    deviations, the inner temporal holdout, the target's mean and sd and every
    gradient step would all still have come from the microcap population -- and
    W3b would be W3 with a different heading on the receipt.
    """
    dev, info = device
    floored, _ = NL.tradable_universe(panel)
    full_pred, _ = NL.run_neural(panel.copy(), TEST_YEARS, seeds=[7], device=dev,
                                 device_info=info, verbose=False)
    flo_pred, _ = NL.run_neural(floored.copy(), TEST_YEARS, seeds=[7], device=dev,
                                device_info=info, verbose=False)
    a = full_pred["s7"].reindex(floored.index).dropna()
    b = flo_pred["s7"].dropna()
    common = a.index.intersection(b.index)
    assert len(common) > 50, "the two runs share too few rows to compare"
    assert not np.allclose(a.loc[common].to_numpy(), b.loc[common].to_numpy(),
                           rtol=0, atol=1e-12), (
        "fitting on the floored universe produced IDENTICAL predictions to fitting "
        "on the whole panel -- the training universe filter never reached the fit")


def test_the_floored_fit_never_sees_a_row_below_the_floor(panel, device):
    """The negative half of the same property, stated on the fold itself."""
    dev, info = device
    floored, _ = NL.tradable_universe(panel)
    seen = 0
    for _y, tr, te in DS.walk_forward_splits(floored, TEST_YEARS, NL.HORIZON):
        for idx in (tr, te):
            rows = floored.loc[idx]
            assert (np.expm1(rows["log_dollar_vol_20d"]) >= NL.TRADABLE_FLOOR_USD).all()
            assert (rows["close"] >= NL.TRADABLE_MIN_CLOSE).all()
            seen += len(rows)
    assert seen > 0, "no fold was produced at all -- the assertions above never ran"


# ------------------------------------------ 5. the grading floor is then a no-op

def test_the_grading_floor_removes_nothing_from_an_already_floored_panel(panel):
    from learner import evaluate
    floored, _ = NL.tradable_universe(panel)
    d = floored.copy()
    d["_p"] = np.arange(len(d), dtype="float64")
    with_floor = evaluate.book(d, "_p", k=50, weight="vw", cost_bps=10,
                               ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                               tradable_floor=NL.TRADABLE_FLOOR_USD)
    gradeable = int(d[["_p", "fwd_1m", "mkt_vw_1m"]].dropna().shape[0])
    assert with_floor["rows_after_tradable_floor"] == gradeable, (
        "the grading floor removed rows from a panel that was floored before the "
        "fit -- the training universe is NOT the graded universe")


# --------------------------------------------- 6. the option is off by default

def test_job_does_not_floor_the_training_universe_unless_asked(panel, device):
    """W3's receipts must be unchanged byte for byte by W3b's existence."""
    r = NL.job(0, panel=panel.copy(), seeds=[7], test_years=TEST_YEARS,
               verbose=False)
    assert r["family_id"] == "weekend-W3-supervised", r["family_id"]
    assert "GRADING ONLY" in r["training_universe"]["applied_to"]


def test_job_with_the_floor_on_records_it_and_changes_the_family_id(panel, device):
    r = NL.job(0, panel=panel.copy(), seeds=[7], test_years=TEST_YEARS,
               verbose=False, universe_floor=True)
    assert r["family_id"] == "weekend-W3-supervised-floored", r["family_id"]
    uni = r["training_universe"]
    assert uni["rows_removed"] > 0
    assert uni["dollar_volume_floor_usd_per_day"] == NL.TRADABLE_FLOOR_USD
    assert uni["min_close_usd"] == NL.TRADABLE_MIN_CLOSE
    assert "THE TRAINING UNIVERSE" in uni["applied_to"]


# ------------------------------------------------ 7. the classifier incumbent

def test_lgbm_clf_returns_a_probability_and_is_not_rescaled(panel):
    floored, _ = NL.tradable_universe(panel)
    pred, rec = NL.run_lgbm_clf(floored, TEST_YEARS, verbose=False)
    p = pred.dropna()
    assert len(p) > 0, "the classifier produced no prediction at all"
    assert float(p.min()) >= 0.0 and float(p.max()) <= 1.0, (
        "lgbm_clf's score left [0, 1] -- a probability dressed as an expected "
        "return is a units error, not a baseline")
    assert rec["kind"] == "lgbm_clf"
    assert "never rescaled" in rec["score"]


# --------------------------------- 8. the rule was declared before the result

def test_the_declared_decision_rule_on_disk_still_matches_the_code():
    """The tamper-evidence. If the rule in `w3_neural_floored.py` is edited after
    the declaration was written, this fails -- which is the whole point of having
    written it down first."""
    W = pytest.importorskip("scripts.w3_neural_floored")
    if not W.DECLARATION.exists():
        pytest.skip("no declaration on disk (the job has not been declared here)")
    dec = json.loads(W.DECLARATION.read_text(encoding="utf-8"))
    assert dec["decision_rule_sha256"] == W._rule_sha(), (
        "the decision rule in the code no longer hashes to the rule that was "
        "declared before the run")
    assert dec["decision_rule_declared_before_the_result"] == W.DECISION_RULE


def test_the_rule_judges_the_ensemble_and_names_lgbm_clf():
    W = pytest.importorskip("scripts.w3_neural_floored")
    rule = W.DECISION_RULE
    assert "SEED-MEAN ENSEMBLE" in rule["the_object_judged"]
    assert any("lgbm_clf" in i for i in rule["incumbents"])
    assert len(rule["beats_requires_ALL_of"]) == 4
