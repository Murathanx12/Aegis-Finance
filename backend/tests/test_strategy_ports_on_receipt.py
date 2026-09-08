"""S3-S8 -- the ports are WIRED, so every `run_one` receipt carries them.

The failure this file exists to stop: a detector that feeds nobody. Each block
appears on every receipt either as a number or as a NAMED `CANNOT DETERMINE`
saying which input was missing -- never absent, because an absent block reads
as "not a problem" rather than "not measured".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.strategy import (Benchmark, BookState, Construction, CostModel,
                              HoldRule, Licence, LossBudget, Objective, Signal,
                              Sizing, Strategy, Universe, Window, run_one)

PORT_BLOCKS = ("execution", "exit_ladder", "protections", "leak_analysis",
               "manifold", "marginal_contribution")


def _series(n: int = 120, seed: int = 20260908):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2010-01", periods=n, freq="M").astype(str)
    bench = pd.Series(rng.normal(0.007, 0.04, n), index=idx)
    book = pd.Series(bench.to_numpy() * 1.1 + rng.normal(0.001, 0.02, n),
                     index=idx)
    rf = pd.Series(np.full(n, 0.0015), index=idx)
    return book, bench, rf


def _strategy(**kw) -> Strategy:
    base = dict(
        strategy_id="ports:demo",
        title="a demo book, for wiring only",
        universe=Universe(name="tradable", floor_dollar_vol_usd=3e6),
        signal=Signal(name="demo", column="demo"),
        construction=Construction(rule="top_k", k=20, weighting="ew"),
        hold=HoldRule(horizon_periods=12, min_hold_periods=3,
                      roi_ladder={0: 0.15, 6: 0.05}, stop_loss=-0.10),
        sizing=Sizing(rule="equal_weight", gross_cap=1.0),
        costs=CostModel(transaction_cost_bps=10.0, slippage_bps=2.0),
        benchmark=Benchmark(name="SPY TR"),
        objective=Objective(name="alpha_intercept", periods_per_year=12),
        loss_budget=LossBudget(positions_judged=20, expected_losers=8),
        licence=Licence.PRODUCT_EXPERIMENT,
        engine="series")
    base.update(kw)
    return Strategy(**base)


def _run(**data) -> dict:
    book, bench, rf = _series()
    payload = {"book": book, "benchmark": bench, "rf": rf, "n_boot": 50}
    payload.update(data)
    return run_one(_strategy(), window=Window("2010-01", "2019-12"),
                   data=payload)


# --------------------------------------------------------------------------


def test_every_port_block_is_on_the_receipt():
    r = _run()
    for key in PORT_BLOCKS:
        assert key in r, f"{key} is missing from the receipt"


def test_a_missing_input_is_a_NAMED_cannot_determine_not_an_absent_block():
    r = _run()
    for key in ("leak_analysis", "manifold", "marginal_contribution"):
        assert "CANNOT DETERMINE" in r[key]["verdict"]
    assert "never differenced" in r["leak_analysis"]["verdict"]
    assert "ungated" in r["manifold"]["verdict"]
    assert "re-expression, not a mechanism" in r["marginal_contribution"]["verdict"]


def test_beta_is_STILL_the_first_key_after_the_ports():
    r = _run()
    assert next(iter(r)) == "beta"


def test_S5_the_breakeven_fee_is_on_the_row_with_the_declared_cost_rate():
    r = _run()
    be = r["execution"]["breakeven"]
    # PER SIDE: transaction 10 + slippage 2. The round trip (24) is printed
    # beside it but is NOT what the breakeven is compared against.
    assert be["declared_cost_bps_per_side"] == pytest.approx(12.0)
    assert be["declared_round_trip_bps"] == pytest.approx(24.0)
    assert "PER SIDE" in be["units"]
    assert be["breakeven_fee_bps"] is not None or "CANNOT DETERMINE" in be["verdict"]


def test_S6_the_stop_width_is_compared_to_the_books_OWN_volatility():
    r = _run()
    sv = r["exit_ladder"]["stop_vs_volatility"]
    assert sv["stop_pct"] == pytest.approx(0.10)
    assert sv["min_hold_can_bind"] in (True, False)
    assert r["exit_ladder"]["exit_priority"][0] == "THESIS_INVALIDATED"
    assert "CANNOT DETERMINE" in r["exit_ladder"]["meta_labelled_exits"]["verdict"]


def test_S6_a_caller_supplied_volatility_overrides_the_books_own():
    r = _run(**{})
    auto = r["exit_ladder"]["sd_source"]
    r2 = run_one(_strategy(), window=Window("2010-01", "2019-12"),
                 data={"book": _series()[0], "benchmark": _series()[1],
                       "rf": _series()[2], "n_boot": 50,
                       "per_period_sd": 0.02})
    assert auto == "the book own period return sd"
    assert r2["exit_ladder"]["sd_source"] == "supplied by the caller"
    sv = r2["exit_ladder"]["stop_vs_volatility"]
    assert sv["per_period_sd"] == pytest.approx(0.02)
    assert sv["stop_in_sd"] == pytest.approx(5.0)                 # 10% / 2%
    assert sv["holding_period_sd"] == pytest.approx(0.02 * 3 ** 0.5)
    assert sv["min_hold_can_bind"] is True


def test_S7_the_guard_list_is_never_empty_and_locks_on_an_unmeasured_book():
    r = _run()
    p = r["protections"]
    assert p["n_protections"] >= 5
    assert p["entries_allowed"] is False           # nothing was measured
    assert p["n_cannot_determine"] >= 1
    assert "no live book state" in p["state_note"]
    assert p["blocks"] == "entries only -- no protection can ever block an exit"


def test_S7_the_five_live_profile_bounds_travel_on_every_receipt():
    bounds = _run()["protections"]["profile_bounds"]
    assert bounds["conservative"]["worst_case_pct_of_equity"] == pytest.approx(0.018)
    assert bounds["aggressive"]["worst_case_pct_of_equity"] == pytest.approx(0.10)
    assert bounds["maximum"]["worst_case_pct_of_equity"] == pytest.approx(0.09)
    assert bounds["basket"]["worst_case_pct_of_equity"] == pytest.approx(0.12)
    assert bounds["convex"]["worst_case_pct_of_equity"] == pytest.approx(0.08)
    assert all(b["levered"] is False for b in bounds.values())


def test_S7_a_measured_book_inside_its_bounds_is_admitted():
    state = BookState(equity_usd=100_000.0,
                      notional_by_name={f"N{i}": 10_000.0 for i in range(8)},
                      stop_pct=0.03, realised_pnl_today_usd=0.0,
                      peak_equity_usd=100_000.0,
                      periods_since_last_exit_by_name={})
    r = _run(book_state=state, risk_profile="aggressive")
    p = r["protections"]
    assert p["profile"] == "aggressive"
    assert p["entries_allowed"] is True
    assert p["n_cannot_determine"] == 0


def test_S7_the_contracts_own_gross_times_stop_is_printed_beside_the_guards():
    w = _run()["protections"]["worst_case_from_the_contract"]
    assert w["gross_cap"] == 1.0
    assert w["stop_pct"] == pytest.approx(0.10)
    assert w["worst_case_pct_of_equity"] == pytest.approx(0.10)
    assert "is ever quoted alone" in w["note"]


def test_S3_a_supplied_feature_builder_gets_BOTH_detectors_run():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    frame = pd.DataFrame({"close": 100 + np.cumsum(rng.normal(0, 1, 400))},
                         index=idx)

    def build(d):
        return pd.DataFrame({"sma3": d["close"].rolling(3).mean(),
                             "leak": d["close"].shift(-1)}, index=d.index)

    r = _run(feature_builder=build, raw_frame=frame, declared_warmup=20)
    la = r["leak_analysis"]
    assert la["lookahead"]["biased_columns"] == ["leak"]
    assert la["recursive"]["verdict"] in ("CONVERGED", "WARMUP_DRIFT_DETECTED")


def test_S4_a_supplied_training_matrix_gets_a_do_predict_gate():
    rng = np.random.default_rng(3)
    train = pd.DataFrame(rng.normal(size=(300, 3)),
                         columns=["f1", "f2", "f3"])
    rows = pd.DataFrame({"f1": [0.0, 40.0], "f2": [0.0, 40.0],
                         "f3": [0.0, 40.0]})
    r = _run(manifold_train=train, manifold_score_rows=rows)
    m = r["manifold"]
    assert m["gate"] == "books admit a name only when do_predict == 1"
    assert m["n_scored"] == 2
    assert m["n_trustworthy"] == 1
    assert m["share_trustworthy"] == pytest.approx(0.5)


def test_S8_a_supplied_panel_gets_an_MMC_number():
    rng = np.random.default_rng(5)
    frames = []
    for e in range(12):
        m = rng.normal(size=100)
        frames.append(pd.DataFrame({"era": f"E{e:02d}", "meta": m,
                                    "cand": m, "y": 0.05 * m + rng.normal(size=100)}))
    panel = pd.concat(frames, ignore_index=True)
    r = _run(mmc_panel=panel, mmc_pred_col="cand", mmc_meta_col="meta",
             mmc_target_col="y", mmc_era_col="era")
    assert r["marginal_contribution"]["mean_mmc"] == pytest.approx(0.0, abs=1e-12)
    assert "RE-EXPRESSION" in r["marginal_contribution"]["verdict"]


def test_S8_a_broken_mmc_request_is_a_refusal_on_the_receipt_not_a_crash():
    r = _run(mmc_panel=pd.DataFrame({"a": [1.0]}), mmc_pred_col="a",
             mmc_meta_col="nope", mmc_target_col="a", mmc_era_col="a")
    assert "CANNOT DETERMINE" in r["marginal_contribution"]["verdict"]


def test_the_whole_receipt_still_serialises():
    import json

    json.dumps(_run(), default=str)
