"""The properties `learner/neural_long.py` would be a lie without.

W3 puts a neural encoder on the 26-year panel and asks whether it beats
LightGBM. Five things about that job would make every number in its receipt
wrong while the receipt still looked green, so they are pinned here rather than
intended in a docstring:

1. **the self-supervised pass cannot see a target.** `pretrain_scope="causal"`
   is the arm a claim may be made from, and the test corrupts the TEST YEAR'S
   OWN TARGETS and demands the predictions come back bit-identical. That is the
   property, not "the code looks point-in-time".
2. **`causal` and `all` are actually different.** If `_pretrain_rows` returned
   the same rows for both, the receipt would print a leakage disclaimer about a
   distinction that does not exist -- and the honest-sounding sentence would be
   the bug.
3. **the training target is clipped and the EVALUATION target is not.** The clip
   is the guard `encoder.ClipSD` is to features; a clip that leaked onto the
   graded column would quietly delete the tail that is the result.
4. **the seed loop is not theatre.** Eight seeds are eight family cells; if two
   seeds produced identical predictions the spread would be a fabricated zero.
5. **the device is reported, never assumed.** A CPU run must say so.

Plus the house rules the module inherits: median imputation and never
`fillna(0)`; the splitter is `dataset.walk_forward_splits` and not a local
re-implementation; and `_beats_incumbent` refuses to clear on a missing
comparison.

Everything here runs OFFLINE on a synthetic frame in a few seconds. Nothing
loads WRDS, touches the network, or reads the 925k-row long panel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import dataset as DS
from learner import encoder as ENC

NL = pytest.importorskip("learner.neural_long")
torch = pytest.importorskip("torch")

pytestmark = pytest.mark.skipif(not NL._TORCH, reason="torch is not installed")

TEST_YEARS = [2018, 2019]


def _panel(n_names: int = 60, n_months: int = 84) -> pd.DataFrame:
    """A frame carrying every column `neural_long` reads, and nothing else.

    Dates are DERIVED from a base period, never literal -- a fixture that
    hard-codes a calendar moment fails the day after that moment passes.
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
    # one genuinely missing column, so the median imputer has something to do
    df.loc[rng.random(n) < 0.2, DS.FEATURES_CONTINUOUS[0]] = np.nan

    # a signal, plus a fat tail so the +/-5 sd target clip has to fire
    df["excess_vw_1m"] = (0.02 * df[DS.FEATURES_CONTINUOUS[1]]
                          + rng.standard_t(2.0, size=n) * 0.03)
    df["mat_date_1m"] = df["entry_date"] + pd.DateOffset(months=1)
    df["mkt_vw_1m"] = 0.006
    df["fwd_1m"] = df["excess_vw_1m"] + df["mkt_vw_1m"]
    df["market_cap"] = 1e9 * (1.0 + (df["permno"] % 7))
    df["prior_1m"] = 0.0
    # `close` and a REALISTIC dollar volume, spanning $100k to $100m a day, so
    # the $3m/day execution floor removes SOME of the book and not all of it.
    # With a standard-normal `log_dollar_vol_20d` every name trades about two
    # dollars, the floor empties the book, and the robustness block would report
    # "no rows" -- a gate that cannot go green rather than a strict one.
    df["close"] = np.exp(df["log_close"] * 0.3 + np.log(12.0))
    df["log_dollar_vol_20d"] = np.log1p(10.0 ** rng.uniform(5.0, 8.0, n))
    return df.reset_index(drop=True)


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _panel()


@pytest.fixture(scope="module")
def device():
    dev, info = NL.resolve_device()
    return dev, info


# ------------------------------------------------- 1. the pre-training leak

def test_causal_pretraining_cannot_see_the_test_years_targets(panel, device):
    """THE property the `causal` arm's claim rests on.

    Not "the code reads entry_date" -- that is an inspection. This corrupts the
    test year's own targets by a large amount and demands the predictions come
    back identical. If any stage of the pipeline (pre-training, the pipeline
    fit, the target standardisation) reached into the test year, this fails.

    ONE test year, not two, and the difference matters. The window is EXPANDING,
    so 2018's rows are legitimate training data for the 2019 fold; poisoning
    both years and demanding invariance would demand that a walk-forward model
    ignore its own past, which is not the property under test. (The first
    version of this test did exactly that and failed, correctly.)
    """
    dev, info = device
    one = [2018]
    a, _ = NL.run_neural(panel.copy(), one, seeds=[7], pretrain_scope="causal",
                         device=dev, device_info=info, verbose=False)
    poisoned = panel.copy()
    hit = pd.to_datetime(poisoned["entry_date"]).dt.year >= one[0]
    assert hit.any(), "the fixture has no rows inside or after the test year"
    rng = np.random.default_rng(1)
    poisoned.loc[hit, "excess_vw_1m"] = rng.normal(5.0, 1.0, int(hit.sum()))
    b, _ = NL.run_neural(poisoned, one, seeds=[7], pretrain_scope="causal",
                         device=dev, device_info=info, verbose=False)
    for key in a:
        x, y = a[key].dropna(), b[key].dropna()
        assert len(x) > 0, "no prediction was produced at all"
        assert x.index.equals(y.index)
        np.testing.assert_allclose(
            x.to_numpy(), y.to_numpy(), rtol=0, atol=0,
            err_msg="corrupting the TEST YEAR's targets moved the predictions -- "
                    "something in the causal arm reads the future")


def test_causal_and_all_pretraining_scopes_are_actually_different(panel):
    """A leakage disclaimer about a distinction that does not exist is worse
    than no disclaimer, because it reads as diligence."""
    causal = NL._pretrain_rows(panel, 2018, "causal")
    allrows = NL._pretrain_rows(panel, 2018, "all")
    assert len(allrows) == len(panel)
    assert 0 < len(causal) < len(allrows), (
        "the causal pretraining scope is not narrower than `all` -- either the "
        "fixture has no post-cutoff rows or the scope is not being applied")
    yrs = pd.to_datetime(panel.loc[causal, "entry_date"]).dt.year
    assert yrs.max() < 2018, (
        f"the causal pretraining scope for test year 2018 reaches into {yrs.max()}")
    with pytest.raises(ValueError):
        NL._pretrain_rows(panel, 2018, "everything")


def test_the_leakage_statement_names_the_all_scope_as_a_look_ahead(panel):
    """`all` IS a mild look-ahead. The receipt must say so in the receipt --
    not in a module docstring nobody reading the JSON will open."""
    s = NL._leakage_statement()
    assert "LOOK-AHEAD" in s["pretraining_all"].upper()
    assert "POINT-IN-TIME" in s["pretraining_causal"].upper()
    assert "no target" in s["pretraining_causal"].lower()


# ------------------------------------------- 2. the splitter is the house one

def test_the_folds_are_exactly_dataset_walk_forward_splits(panel, device):
    """A local re-implementation of the splitter is the one way to lose the
    guarantee that a training row's target had MATURED before the test year."""
    dev, info = device
    _p, rec = NL.run_neural(panel.copy(), TEST_YEARS, seeds=[3], device=dev,
                            device_info=info, verbose=False)
    house = list(DS.walk_forward_splits(panel, TEST_YEARS, NL.HORIZON))
    assert rec["n_folds"] == len(house) > 0
    for note, (year, tr, te) in zip(rec["folds"], house):
        assert note["year"] == year
        assert note["n_train"] == len(tr)
        assert note["n_test"] == len(te)
        cutoff = pd.Timestamp(f"{year}-01-01")
        assert (panel.loc[tr, "mat_date_1m"] < cutoff).all(), (
            "a training row's target had not matured before the test year opened")


# --------------------------------------- 3. the target clip, and where it stops

def test_the_training_target_is_clipped_and_the_evaluation_target_is_not(panel, device):
    dev, info = device
    before = panel["excess_vw_1m"].to_numpy(copy=True)
    _p, rec = NL.run_neural(panel, TEST_YEARS, seeds=[3], device=dev,
                            device_info=info, verbose=False)
    assert sum(f["train_rows_clipped_at_5sd"] for f in rec["folds"]) > 0, (
        "no training row was clipped on a fat-tailed fixture -- the +/-5 sd "
        "target clip is not firing, and an unbounded target is exactly what "
        "produced a predicted +1,533% excess return in the v2 encoder")
    np.testing.assert_array_equal(
        panel["excess_vw_1m"].to_numpy(), before,
        err_msg="the graded target column was mutated; the tail IS the result")
    assert rec["target_clip_sd"] == NL.TARGET_CLIP_SD


def test_the_pipeline_median_imputes_and_reuses_the_encoders_clip(panel):
    """`fillna(0)` is banned by the house, and the +/-5 sd feature clip is
    IMPORTED from `learner.encoder` rather than copied -- one bound, one place."""
    pipe = NL.make_pipeline()
    assert [n for n, _ in pipe.steps] == ["impute", "scale", "clip"]
    assert pipe.named_steps["impute"].strategy == "median"
    assert isinstance(pipe.named_steps["clip"], ENC.ClipSD)
    assert NL.CLIP_SD == ENC.CLIP_SD

    X = panel[NL.feature_cols()].to_numpy(dtype="float64")
    assert np.isnan(X).any(), "the fixture has no NaN, so this proves nothing"
    Z = pipe.fit_transform(X)
    assert not np.isnan(Z).any()
    assert np.abs(Z).max() <= NL.CLIP_SD + 1e-9


# ------------------------------------------------- 4. the seed loop is real

def test_two_seeds_do_not_produce_the_same_predictions(panel, device):
    """Eight seeds are eight cells in the multiplicity family. If they agreed,
    the reported spread would be a fabricated zero and the DSR would be paying
    for a search that never happened."""
    dev, info = device
    preds, rec = NL.run_neural(panel, TEST_YEARS, seeds=[11, 12], device=dev,
                               device_info=info, verbose=False)
    assert set(preds) == {"s11", "s12"}
    a, b = preds["s11"].dropna(), preds["s12"].dropna()
    assert a.index.equals(b.index) and len(a) > 100
    assert not np.allclose(a.to_numpy(), b.to_numpy()), (
        "two seeds produced identical predictions -- the seed is not reaching "
        "the initialisation or the batch order")
    assert rec["seeds"] == [11, 12]


def test_the_same_seed_reproduces(panel, device):
    dev, info = device
    a, _ = NL.run_neural(panel, TEST_YEARS, seeds=[11], device=dev,
                         device_info=info, verbose=False)
    b, _ = NL.run_neural(panel, TEST_YEARS, seeds=[11], device=dev,
                         device_info=info, verbose=False)
    np.testing.assert_allclose(a["s11"].dropna().to_numpy(),
                               b["s11"].dropna().to_numpy(), rtol=0, atol=0)


def test_spread_reports_the_range_not_the_best():
    s = NL._spread({"a": 1.0, "b": -3.0, "c": 5.0, "d": None})
    assert s == {"n": 3, "min": -3.0, "median": 1.0, "max": 5.0,
                 "sd": round(float(np.std([1.0, -3.0, 5.0], ddof=1)), 4),
                 "share_positive": round(2 / 3, 4)}
    assert NL._spread({"a": None})["n"] == 0


# ---------------------------------------------------- 5. the device is stated

def test_a_cpu_run_says_so():
    dev, info = NL.resolve_device(prefer_cuda=False)
    assert dev.type == "cpu"
    assert info["device_actually_used"] == "cpu"
    assert info["device_warning"], "a CPU run with no warning reads as a GPU result"
    assert info["cuda_requested"] is False


def test_a_cuda_receipt_names_the_card_it_ran_on():
    dev, info = NL.resolve_device()
    assert info["torch_version"]
    if info["cuda_available"]:
        assert dev.type == "cuda"
        assert info["device_actually_used"] == "cuda"
        assert info["device_warning"] is None
        assert info.get("device_name")
    else:
        assert info["device_actually_used"] == "cpu"
        assert "must not be quoted as a GPU result" in info["device_warning"]


# ------------------------------------- 6. the bar has TWO legs, not one

def test_beating_the_market_is_not_the_question_when_an_incumbent_exists():
    assert NL._beats_incumbent({})["clears"] is False
    strong = {"deflated_sharpe": {"dsr": 0.99}, "spa": {"p_spa_consistent": 0.01},
              "pbo": {"pbo": 0.2}}
    assert NL._beats_incumbent(strong)["clears"] is True
    for weak in ({"deflated_sharpe": {"dsr": 0.5}, "spa": {"p_spa_consistent": 0.01}},
                 {"deflated_sharpe": {"dsr": 0.99}, "spa": {"p_spa_consistent": 0.4}},
                 {"deflated_sharpe": {"dsr": 0.99}, "spa": {"p_spa_consistent": 0.01},
                  "pbo": {"pbo": 0.8}}):
        assert NL._beats_incumbent(weak)["clears"] is False


def test_the_neural_arm_sees_exactly_the_columns_lgbm_sees():
    """A column the incumbent has and the challenger does not turns an
    architecture question into a feature question."""
    from learner import models as M
    assert NL.feature_cols() == M.arm_features(DS.feature_columns(), "raw", NL.HORIZON)
    assert len(NL.feature_cols()) == len(DS.feature_columns()) + 1


def test_describe_declares_what_was_reused_and_what_changed():
    d = NL.describe()
    assert d["seeds"] >= 8
    assert d["horizon_months"] == 1
    assert any("ClipSD" in s for s in d["reused_from_encoder"])
    assert any("seeds" in s for s in d["changed_from_encoder"])
    assert set(d["variants"]) == set(NL.VARIANTS)


# ---------------------------------------- 7. the receipt a lab runner reads

@pytest.mark.parametrize("variant", [0, 1, 2, 3])
def test_job_returns_the_weekend_lab_receipt_shape(panel, variant):
    """The runner writes whatever the job returns. A missing key is a receipt
    that cannot be graded, discovered at 3am."""
    r = NL.job(variant, test_years=TEST_YEARS, seeds=[5, 6], panel=panel.copy(),
               verbose=False)
    for k in ("question", "family_id", "cells_looked_at", "inference",
              "headline", "verdict"):
        assert k in r, f"receipt is missing {k!r}"
    assert r["variant_name"] == NL.VARIANTS[variant]
    assert r["family_id"] == f"weekend-W3-{NL.VARIANTS[variant]}"
    assert r["cells_looked_at"] >= 4
    assert r["verdict"] in {"NOVEL", "NOISE", "CANNOT DETERMINE (underpowered)",
                            "CANNOT DETERMINE", "FAILED",
                            "NOISE (clears the market bar, does NOT beat lgbm)"}
    assert "device" in r and r["device"]["device_actually_used"] in {"cuda", "cpu"}
    # the incumbent leg must exist, or "beats lgbm" was never asked
    assert "vs_lgbm" in r and "inference" in r["vs_lgbm"]
    assert r["vs_lgbm"]["lgbm_book_10bps"], "no lgbm book was graded"
    # power beside the t, always
    assert "power" in r["inference"]
    assert "years_needed_for_t2" in r["inference"]["power"]


def test_a_novel_verdict_requires_beating_lgbm_too(panel, monkeypatch):
    """The extra clause. A cell that clears the market bar and loses to the
    incumbent is not a finding, and the verdict must not read as one."""
    monkeypatch.setattr(NL, "_beats_incumbent",
                        lambda inf: {"clears": False, "reading": "stubbed"})
    import scripts.weekend_lab_jobs as WLJ
    monkeypatch.setattr(WLJ, "verdict_from", lambda inf, eras: "NOVEL")
    r = NL.job(0, test_years=TEST_YEARS, seeds=[5], panel=panel.copy(), verbose=False)
    assert r["verdict"] == "NOISE (clears the market bar, does NOT beat lgbm)"


# ------------------------------- 8. what the headline number is made of

def test_robustness_regrades_under_the_execution_floor_and_names_the_tail(panel):
    """The block that exists because a 561x terminal wealth went out of the
    first full pass with nothing in the receipt able to contradict it.

    `evaluate.book`'s default output has no liquidity column, no tail
    decomposition and no holdings profile, so a pass without this block cannot
    tell a model result from a microcap-with-five-good-months result.
    """
    df = panel.copy()
    df["pred"] = df["excess_vw_1m"] + np.random.default_rng(4).normal(0, 0.02, len(df))
    r = NL.robustness(df, "pred")
    assert r["tradable_floor_usd"] == NL.TRADABLE_FLOOR_USD
    for block in ("plain", "tradable_floor", "at_25bps"):
        assert block in r, f"robustness is missing {block!r}"
        assert "terminal_wealth_net" in r[block] or "error" in r[block]
    # THE FLOOR MUST BITE AND MUST NOT EMPTY THE BOOK. Both failures are silent:
    # a floor that removes nothing reads as "the edge is liquid", and a floor
    # that removes everything returns `months: 0` and reads as an error.
    fl = r["tradable_floor"]
    assert fl.get("months"), "the tradable floor emptied the book -- it cannot go green"
    assert fl["rows_after_tradable_floor"] > 0
    assert fl["rows_after_tradable_floor"] < len(df), "the floor removed nothing"

    t = r["tail"]
    assert len(t["best_5_months"]) == 5
    assert t["terminal_wealth_without_them"] < r["plain"]["terminal_wealth_net"]
    # like with like: the MARKET's terminal wealth over the same removed months
    assert "market_terminal_wealth_without_them" in t

    h = r["holdings"]
    for k in ("median_market_cap_musd", "median_close_usd", "median_dollar_volume_usd",
              "share_of_book_under_5_dollars", "share_of_book_under_1m_dollar_volume"):
        assert k in h, f"holdings profile is missing {k!r}"
        assert h[k] is not None


def test_the_floor_uses_the_houses_own_constant():
    """One floor, one place. A second copy of $3m/day is a second floor."""
    from learner import evaluate as E
    assert NL.TRADABLE_FLOOR_USD == E.TRADABLE_DOLLAR_VOL == 3_000_000.0


def test_holdings_refuses_rather_than_guessing_when_the_columns_are_absent(panel):
    df = panel.copy()
    df["pred"] = df["excess_vw_1m"]
    r = NL.robustness(df.drop(columns=["log_dollar_vol_20d"]), "pred")
    assert r["holdings"]["verdict"] == "CANNOT DETERMINE"
    assert "log_dollar_vol_20d" in r["holdings"]["why"]


def test_a_receipt_carries_the_floor_comparison_against_lgbm(panel):
    r = NL.job(0, test_years=TEST_YEARS, seeds=[5, 6], panel=panel.copy(), verbose=False)
    ex = r["execution_floor"]
    assert ex["floor_usd_per_day"] == NL.TRADABLE_FLOOR_USD
    # BOTH legs under the floor -- a floor that helps the incumbent and hurts the
    # challenger reverses the comparison, and only printing one side hides that.
    for k in ("terminal_wealth_plain", "terminal_wealth_under_floor",
              "lgbm_terminal_wealth_plain", "lgbm_terminal_wealth_under_floor"):
        assert k in ex
    assert isinstance(ex["still_ahead_of_lgbm_under_the_floor"], bool)
    assert "lgbm_raw" in r["robustness"]
    # THE HONEST OBJECT TOO. The best cell is the max of a seed draw and cannot
    # be chosen in advance; on the first real pass the champion cleared the floor
    # and the seed-mean ensemble did not.
    assert ex["seed_mean_ensembles"], "no ensemble was graded under the floor"
    for c, v in ex["seed_mean_ensembles"].items():
        assert c.endswith("seedmean")
        assert isinstance(v["ahead_of_lgbm_under_the_floor"], bool)
    assert isinstance(ex["every_ensemble_ahead_of_lgbm_under_the_floor"], bool)


def test_clearing_every_bar_on_an_untradable_book_is_not_a_finding(panel, monkeypatch):
    import scripts.weekend_lab_jobs as WLJ
    monkeypatch.setattr(WLJ, "verdict_from", lambda inf, eras: "NOVEL")
    monkeypatch.setattr(NL, "_beats_incumbent",
                        lambda inf: {"clears": True, "reading": "stubbed"})
    real = NL.robustness

    def _dead(df, col, bps=10.0):
        out = real(df, col, bps)
        # the challenger dies at the floor; the incumbent does not
        out["tradable_floor"]["terminal_wealth_net"] = 9.0 if col == "lgbm_raw" else 0.5
        return out

    monkeypatch.setattr(NL, "robustness", _dead)
    r = NL.job(0, test_years=TEST_YEARS, seeds=[5], panel=panel.copy(), verbose=False)
    assert r["verdict"] == "NOISE (clears every bar, dies at the $3m/day execution floor)"
    assert r["execution_floor"]["still_ahead_of_lgbm_under_the_floor"] is False
