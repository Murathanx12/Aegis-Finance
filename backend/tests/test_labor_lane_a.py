"""LANE A of the Labor Day Lab (2026-09-07): training and backtests.

These tests pin the BEHAVIOURS the lane's four jobs are supposed to have, not
their numbers. A number that moves because the panel was rebuilt is a finding;
a job that stops writing a receipt when it fails, or a gate that reports green
because its input was absent, is a defect -- and only the second kind belongs
in a test suite that runs offline in seconds.

Every test here is OFFLINE and touches no model fit. The heavy jobs write their
own receipts; what is pinned here is that the receipt is written AT ALL, that
refusals are named, and that the arithmetic helpers do what their docstrings say.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

A1 = pytest.importorskip("scripts.labor_a1_shadow_grader")
LAB_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"


# ------------------------------------------------------------------- A1 math

def test_a1_ols_recovers_a_planted_beta_and_alpha():
    """The market model is the whole of A1's PRIMARY claim. Plant, then recover."""
    rng = np.random.default_rng(20260907)
    n = 400
    x = rng.normal(0.008, 0.045, n)
    y = 0.002 + 1.30 * x + rng.normal(0.0, 0.005, n)
    got = A1.ols_market_model(y, x)
    assert got["beta"] == pytest.approx(1.30, abs=0.02)
    assert got["alpha_monthly"] == pytest.approx(0.002, abs=0.001)
    # t(beta - 1) must be large and positive: the planted loading IS above one.
    assert got["t_beta_minus_1_hac"] > 5
    assert got["nw_lag"] == A1.NW_LAG


def test_a1_ols_refuses_rather_than_fitting_eight_points():
    got = A1.ols_market_model([0.1, 0.2, 0.3], [0.1, 0.2, 0.3])
    assert got["verdict"] == "CANNOT DETERMINE"
    assert "fewer than 8" in got["why"]


def test_a1_window_leg_compounds_over_the_books_own_window_not_the_calendar_month():
    """A month label is an ENTRY-to-MATURITY window, not February.

    Planted so the two readings differ: the daily leg is 0 in January and 1% a
    day in February, and the book labelled `2026-01` is held 01-20 -> 02-20. A
    calendar-month reindex would return 0; the window compounding must not.
    """
    idx = pd.date_range("2026-01-01", "2026-03-31", freq="D")
    daily = pd.Series(np.where(idx.month == 2, 0.01, 0.0), index=idx)
    g = pd.DataFrame({"entry": [pd.Timestamp("2026-01-20")],
                      "mat": [pd.Timestamp("2026-02-20")]}, index=["2026-01"])
    ser, note = A1._window_leg(daily, g, pd.Index(["2026-01"]))
    assert note["months_built"] == 1
    assert note["months_missing"] == []
    # 20 February days at 1% compounded.
    assert float(ser.iloc[0]) == pytest.approx(1.01 ** 20 - 1.0, rel=1e-9)


def test_a1_window_leg_names_missing_months_and_never_silently_zero_fills():
    idx = pd.date_range("2026-01-01", "2026-01-31", freq="D")
    daily = pd.Series(0.001, index=idx)
    g = pd.DataFrame({"entry": [pd.Timestamp("2026-06-01")],
                      "mat": [pd.Timestamp("2026-06-30")]}, index=["2026-06"])
    ser, note = A1._window_leg(daily, g, pd.Index(["2026-06"]))
    assert note["months_built"] == 0
    assert note["months_missing"] == ["2026-06"]
    assert "never silently zero-filled" in note["declared"]
    assert float(ser.iloc[0]) == 0.0


def test_a1_overlap_block_counts_shared_names():
    a = {"2020-01": {1, 2, 3, 4}, "2020-02": {1, 2, 3, 4}}
    b = {"2020-01": {3, 4, 5, 6}, "2020-02": {1, 2, 3, 4}}
    got = A1.overlap_block(a, b, k=4)
    assert got["months"] == 2
    assert got["mean_names_in_common"] == pytest.approx(3.0)
    assert got["min_names_in_common"] == 2
    assert got["max_names_in_common"] == 4


def test_a1_overlap_block_cannot_determine_on_disjoint_months():
    got = A1.overlap_block({"2020-01": {1}}, {"2021-01": {1}}, k=1)
    assert got["verdict"] == "CANNOT DETERMINE"


# --------------------------------------------------------------- A1 behaviour

def test_a1_heartbeat_never_raises_even_when_a_selector_module_explodes(monkeypatch):
    """A heartbeat that dies is a night with no evidence. It must degrade to ERROR."""
    import learner.shadow as SH
    monkeypatch.setattr(SH, "latest_tracker_day",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    hb = A1.heartbeat("2026-09-07")
    assert hb["lgbm_clf_daily_shadow"]["status"] == "ERROR"
    assert "boom" in hb["lgbm_clf_daily_shadow"]["reasons"][0]
    # the OTHER selector is still reported; one failure does not eat the night
    assert "status" in hb["nn_pre_causal_shadow"]


def test_a1_forward_gate_cannot_determine_when_the_panel_is_absent(monkeypatch, tmp_path):
    import learner.long_panel as LP
    monkeypatch.setattr(LP, "LONG_TABLE", tmp_path / "nope.parquet")
    got = A1._forward_gate()
    assert got["verdict"] == "CANNOT DETERMINE"
    assert "absent" in got["why"]


def test_a1_main_writes_a_receipt_even_when_the_run_crashes(monkeypatch, tmp_path):
    """A TRACEBACK IS A RECEIPT. Pinned, because the alternative is a silent night."""
    monkeypatch.setattr(A1, "RECEIPT", tmp_path / "A1_crash.json")
    monkeypatch.setattr(A1, "OUT_DIR", tmp_path)
    monkeypatch.setattr(A1, "run",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("planted")))
    assert A1.main([]) == 0
    rec = json.loads((tmp_path / "A1_crash.json").read_text(encoding="utf-8"))
    assert rec["status"] == "CRASHED"
    assert "planted" in rec["error"]
    assert "traceback" in rec
    assert rec["_provenance"]["git_commit"]
    assert rec["_provenance"]["sys_argv"]


# ----------------------------------------------------- the receipts on disk

def _receipt(name: str) -> dict | None:
    p = LAB_DIR / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [
    "A1_shadow_grader_run01.json",
    "A3_cpcv_pbo_run01.json",
    "A4_holding_cross_run01.json",
    "A2_retrain_cadence_run01.json",
])
def test_every_lane_a_receipt_that_exists_stamps_its_provenance(name):
    """Every headline number belongs in a receipt, and every receipt names its inputs."""
    rec = _receipt(name)
    if rec is None:
        pytest.skip(f"{name} has not been produced")
    prov = rec.get("_provenance") or {}
    for key in ("sys_argv", "resolved_config", "_inputs_opened", "git_commit",
                "generated_utc"):
        assert key in prov, f"{name} provenance is missing {key}"
    assert rec.get("llm_spend_usd") == 0.0, f"{name} claims LLM spend"
    assert rec.get("llm_calls") == 0
    for inp in prov["_inputs_opened"]:
        assert "path" in inp and "exists" in inp


def test_a1_receipt_puts_beta_matched_first_and_the_raw_market_second():
    """The incumbents' excess is a LOADING. A grader that leads with the raw
    market is reporting leverage as skill, so the key names themselves are pinned."""
    rec = _receipt("A1_shadow_grader_run01.json")
    if rec is None or (rec.get("historical_grade") or {}).get("status") != "OK":
        pytest.skip("A1 historical grade not present")
    for key, cell in rec["historical_grade"]["by_cell"].items():
        assert "PRIMARY_beta_matched" in cell, key
        assert "SECONDARY_raw_market" in cell, key
        assert cell["market_regression"]["beta"] is not None


def test_a1_receipt_reproduces_the_C1_betas_exactly():
    """A re-grade that does not reproduce its parent is a finding, not a rounding."""
    rec = _receipt("A1_shadow_grader_run01.json")
    if rec is None:
        pytest.skip("A1 receipt not present")
    rep = (rec.get("historical_grade") or {}).get("reproduces_C1")
    if not rep:
        pytest.skip("C1 receipt was not on disk when A1 ran")
    for cell, blk in rep.items():
        assert blk["beta_matches"], f"{cell}: beta {blk} does not reproduce C1"
        assert blk["excess_matches"], f"{cell}: excess does not reproduce C1"


def test_a1_receipt_reports_the_lgbm_clf_refusal_rather_than_hiding_it():
    rec = _receipt("A1_shadow_grader_run01.json")
    if rec is None:
        pytest.skip("A1 receipt not present")
    blk = rec["heartbeat"]["lgbm_clf_daily_shadow"]
    assert blk["status"] in {"OK", "REFUSED", "ERROR"}
    if blk["status"] == "REFUSED":
        assert blk["reasons"], "a refusal with no named reason is not a finding"


def test_a1_forward_gate_is_derived_not_asserted():
    rec = _receipt("A1_shadow_grader_run01.json")
    if rec is None:
        pytest.skip("A1 receipt not present")
    gate = rec["heartbeat"]["can_either_selector_produce_a_FORWARD_vintage_tonight"]
    assert "verdict" in gate
    if gate["verdict"] != "CANNOT DETERMINE":
        # it must have READ the panel's last month, not hardcoded one
        assert gate["panel_last_month"]
        assert isinstance(gate["months_between_panel_end_and_first_grade_date"], int)


# ------------------------------------------------------------------------- A3

A3 = pytest.importorskip("scripts.labor_a3_cpcv_pbo")


def test_a3_pbo_baseline_is_derived_from_the_arm_count_not_assumed_to_be_half():
    """`inference.pbo` says "0.5 is a coin flip". That is FALSE for a small odd N.

    With N arms the OOS rank is discrete and PBO counts `j + 1 <= (N+1)/2`, so
    under pure noise the rate is floor((N+1)/2)/N: 0.500 at N=8, 6/11 at N=11,
    and 2/3 at N=3. A three-arm family quoted against 0.5 reads as catastrophic
    overfitting when its own null is already 0.667.
    """
    rng = np.random.default_rng(11)
    for n_arms, want in ((3, 2 / 3), (8, 0.5), (11, 6 / 11), (22, 0.5)):
        M = pd.DataFrame(rng.normal(0, 0.03, size=(120, n_arms)),
                         columns=[f"a{i}" for i in range(n_arms)])
        blk = A3.pbo_block(M)
        assert blk["pbo_baseline_under_pure_noise_for_this_n_arms"] == pytest.approx(
            want, abs=1e-4), f"N={n_arms}"
        if n_arms < 6:
            assert "small_family_caveat" in blk


def test_a3_pbo_block_reports_the_difference_from_its_own_baseline():
    rng = np.random.default_rng(12)
    M = pd.DataFrame(rng.normal(0, 0.03, size=(120, 8)),
                     columns=[f"a{i}" for i in range(8)])
    blk = A3.pbo_block(M)
    assert blk["pbo_minus_baseline"] == pytest.approx(
        blk["pbo"] - blk["pbo_baseline_under_pure_noise_for_this_n_arms"], abs=1e-9)
    assert blk["verdict_against_its_own_baseline"] in {
        "WORSE THAN A COIN FLIP", "AT THE COIN FLIP", "BETTER THAN A COIN FLIP"}


def test_a3_cpcv_picks_the_planted_dominant_arm_in_every_partition():
    """A planted world with one obviously best arm must select it everywhere.

    If this fails the selection machinery is broken and every PBO in the receipt
    is a number about that bug rather than about the leaderboard.
    """
    rng = np.random.default_rng(13)
    T = 180
    M = pd.DataFrame({
        "good": rng.normal(0.02, 0.01, T),
        "meh": rng.normal(0.000, 0.03, T),
        "bad": rng.normal(-0.01, 0.03, T),
    }, index=pd.period_range("2000-01", periods=T, freq="M").astype(str))
    got = A3.cpcv_path_distribution(M, purge=1, embargo=1)
    assert got["champion_is_the_same_arm_in_every_partition"] is True
    assert list(got["in_sample_champion_counts"]) == ["good"]
    assert got["oos_annualised_distribution"]["share_of_paths_negative"] == 0.0
    assert got["share_of_partitions_won_by_a_NULL_arm"] == 0.0


def test_a3_cpcv_cannot_determine_on_a_short_series():
    M = pd.DataFrame(np.zeros((5, 3)), columns=list("abc"))
    got = A3.cpcv_path_distribution(M, purge=1, embargo=1)
    assert got["verdict"] == "CANNOT DETERMINE"


def test_a3_seed_finding_counts_individual_seeds_not_the_seed_mean():
    fams = {
        "f": {"pbo": {"pbo": 0.5, "verdict": "x"},
              "cpcv_path_distribution": {"in_sample_champion_counts": {
                  "nn_pre_causal_s20260912|10bps": 9,
                  "nn_pre_causal_seedmean|10bps": 6}}},
    }
    got = A3._seed_finding(fams)
    assert got["f"]["won_by_an_individual_SEED"] == 9
    assert got["f"]["partitions"] == 15
    assert got["f"]["share_won_by_a_seed"] == pytest.approx(0.6)


def test_a3_receipt_family_definitions_are_spelled_out_and_shortfalls_named():
    rec = _receipt("A3_cpcv_pbo_run01.json")
    if rec is None:
        pytest.skip("A3 receipt not present")
    lf = rec.get("learner_family") or {}
    if lf.get("status") == "OK":
        gd = lf["grid_32_definition"]
        assert gd["cells_expected"] == 32
        assert gd["cells_found"] == gd["cells_expected"], \
            "the 32-cell grid must be 32 cells or say which are missing"
    nf = rec.get("neural_family") or {}
    if nf.get("status") == "OK":
        sh = nf["family_shortfall"]
        # 40 cells were looked at; the receipt must NOT claim 40 series
        assert sh["w3b_cells_looked_at"] == 40
        assert sh["cells_reconstructible_from_disk"] < 40
        assert nf["stage_files_absent"], "a shortfall with no named absent file"


def test_a3_receipt_fits_no_models():
    rec = _receipt("A3_cpcv_pbo_run01.json")
    if rec is None:
        pytest.skip("A3 receipt not present")
    assert rec["models_fitted"] == 0
