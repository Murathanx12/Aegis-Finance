"""NIGHT LAB 2026-09-07, lane N6b: fantasy exams round 2 + path Monte Carlo.

Everything network- or LLM-shaped is exercised through `--dry-run` /
direct-function paths only — this file makes NO wire calls and needs no API
key. `scripts.n6b_path_monte_carlo`'s full pipeline reads
`backend/data/optimus/growth_book/G2_genome_series.parquet`, which is
gitignored (`*.parquet`) and therefore ABSENT on a fresh CI clone; those tests
SKIP rather than fail, per this repo's CI rule. The pure arithmetic (block
bootstrap, drawdown/TUW stats, ACF, the sealed-era provenance self-check)
needs no data file and always runs.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import n6b_fantasy_exams_round2 as EX
from scripts import n6b_path_monte_carlo as PMC

# ═══════════════════════════════════════════════════════ N6.2 fantasy exams

def test_build_exam_shape():
    items, meta = EX.build_exam(n_pairs=10, n_canaries=4, seed=1)
    # (10 + 4) groups x 2 positions
    assert len(items) == 28
    groups = {it["group_id"] for it in items}
    assert len(groups) == 14
    canaries = [it for it in items if it["is_canary"]]
    assert len(canaries) == 8                      # 4 groups x 2 positions
    reals = [it for it in items if not it["is_canary"]]
    assert len(reals) == 20                         # 10 groups x 2 positions
    # every group appears in both positions
    for gid in groups:
        positions = {it["position"] for it in items if it["group_id"] == gid}
        assert positions == {"end", "front"}


def test_front_and_end_briefs_carry_the_same_fact_different_placement():
    items, _ = EX.build_exam(n_pairs=6, n_canaries=2, seed=2)
    by_key = {(it["group_id"], it["position"]): it for it in items}
    g0_end = by_key[("PAIR-000", "end")]
    g0_front = by_key[("PAIR-000", "front")]
    # END: the boilerplate comes first, the clause is the LAST sentence.
    assert g0_end["brief_good"].index("This week,") > 0
    assert g0_end["brief_good"].rstrip().endswith(".")
    assert g0_end["brief_good"].index("This week,") > len(g0_end["company"])
    # FRONT: the clause is the FIRST sentence.
    assert g0_front["brief_good"].startswith("This week,")
    # both contain the same company name and industry (same underlying item)
    assert g0_end["company"] == g0_front["company"]


def test_select_front_subset_keeps_every_canary_and_caps_real_pairs():
    items, _ = EX.build_exam(n_pairs=EX.N_PAIRS, n_canaries=EX.N_CANARIES,
                             seed=EX.SEED)
    subset = EX.select_front_subset(items, per_family=3)
    canary_groups = {it["group_id"] for it in items if it["is_canary"]}
    assert canary_groups <= subset
    real_groups_by_family: dict[str, int] = {}
    for it in items:
        if it["position"] == "end" and not it["is_canary"] and it["group_id"] in subset:
            real_groups_by_family[it["family"]] = real_groups_by_family.get(it["family"], 0) + 1
    for fam, n in real_groups_by_family.items():
        assert n == 3
    # total call budget stays under the 150/day production cap
    n_front_calls = 2 * len(subset)
    n_end_calls = 2 * len({it["group_id"] for it in items if it["position"] == "end"})
    assert n_end_calls + n_front_calls < 150


def test_grade_pair_direction_and_all_three_agree():
    good = {"p_up_21d": 0.7, "exp_return": 0.05, "downside_5pct": -0.10}
    bad = {"p_up_21d": 0.3, "exp_return": -0.05, "downside_5pct": -0.20}
    g = EX.grade_pair("G1", "guidance", False, "end", good, bad)
    assert g["p_up_moves_correctly"] is True
    assert g["exp_return_moves_correctly"] is True
    assert g["downside_moves_correctly"] is True
    assert g["all_three_agree"] is True
    assert round(g["d_p_up"], 6) == 0.4


def test_grade_pair_backwards_direction_fails():
    good = {"p_up_21d": 0.3, "exp_return": -0.02, "downside_5pct": -0.25}
    bad = {"p_up_21d": 0.7, "exp_return": 0.02, "downside_5pct": -0.05}
    g = EX.grade_pair("G2", "index_membership", False, "front", good, bad)
    assert g["p_up_moves_correctly"] is False
    assert g["all_three_agree"] is False


def test_canary_moved_flag_uses_tolerance():
    good = {"p_up_21d": 0.55, "exp_return": 0.01, "downside_5pct": -0.10}
    bad = {"p_up_21d": 0.50, "exp_return": 0.00, "downside_5pct": -0.10}
    g = EX.grade_pair("C1", "canary_irrelevant", True, "end", good, bad)
    assert g["canary_moved"] is False        # |0.05| not > tolerance
    good2 = {"p_up_21d": 0.65, "exp_return": 0.01, "downside_5pct": -0.10}
    g2 = EX.grade_pair("C2", "canary_irrelevant", True, "end", good2, bad)
    assert g2["canary_moved"] is True        # |0.15| > tolerance


def _synthetic_rows(n_real=12, n_canary=4, front_gap=0.0, seed=0):
    """Rows shaped like `EX.grade_pair`'s output, for pure summary-function
    tests that never touch the network."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_real):
        gid = f"PAIR-{i:03d}"
        for pos, gap in (("end", 0.0), ("front", front_gap)):
            d = round(float(0.30 + rng.normal(0, 0.02)) - gap, 4)
            rows.append({"group_id": gid, "family": "earnings_surprise",
                        "is_canary": False, "position": pos, "d_p_up": d,
                        "d_exp_return": d * 0.1, "d_downside": abs(d) * 0.1,
                        "p_up_moves_correctly": d > 0,
                        "exp_return_moves_correctly": d > 0,
                        "downside_moves_correctly": True,
                        "all_three_agree": d > 0})
    for i in range(n_canary):
        gid = f"CANARY-{i:03d}"
        for pos in ("end", "front"):
            d = 0.0
            rows.append({"group_id": gid, "family": "canary_irrelevant",
                        "is_canary": True, "position": pos, "d_p_up": d,
                        "d_exp_return": 0.0, "d_downside": 0.0,
                        "p_up_moves_correctly": None,
                        "exp_return_moves_correctly": None,
                        "downside_moves_correctly": None,
                        "all_three_agree": False, "canary_moved": False})
    return rows


def test_summarise_position_perfect_monotonicity_zero_canary():
    rows = _synthetic_rows(n_real=10, n_canary=4)
    s_end = EX.summarise_position(rows, "end")
    assert s_end["pairs_graded"] == 10
    assert s_end["monotonicity_share_p_up"] == 1.0
    assert s_end["canary_rate"] == 0.0


def test_compare_positions_insensitive_when_gap_is_small():
    rows = _synthetic_rows(n_real=12, n_canary=4, front_gap=0.001)
    out = EX.compare_positions(rows)
    assert out["real_pairs"]["n"] == 12
    assert "POSITION-INSENSITIVE" in out["verdict"]


def test_compare_positions_sensitive_when_end_dominates():
    rows = _synthetic_rows(n_real=12, n_canary=4, front_gap=0.20)
    out = EX.compare_positions(rows)
    assert out["real_pairs"]["mean_end_minus_front_abs_move"] > 0.15
    assert "END > FRONT" in out["verdict"]


def test_parse_json_handles_fenced_and_bare():
    assert EX._parse_json('{"a": 1}') == {"a": 1}
    assert EX._parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert EX._parse_json('here is the answer: {"a": 3} thanks') == {"a": 3}


def test_running_cost_gate():
    calls = [{"usd": 1.0}, {"usd": 1.5}]
    assert EX.running_cost_gate(calls, 3.0) is False
    assert EX.running_cost_gate(calls, 2.0) is True


def test_dry_run_full_pipeline_writes_a_well_formed_receipt():
    """$0.00, no network: the stub decider end-to-end, small counts."""
    rec = EX.run(n_pairs=6, n_canaries=2, cap_usd=3.0, dry_run=True, seed=7,
                 argv=["test"])
    assert rec["dry_run"] is True
    assert rec["spend"]["calls"] == 0
    for key in ("summary_end_position", "summary_front_position",
               "position_control", "exam", "pairs", "_provenance"):
        assert key in rec
    assert rec["summary_end_position"]["pairs_graded"] == 6
    # every real pair moves correctly under the (deterministic) stub decider
    assert rec["summary_end_position"]["monotonicity_share_p_up"] == 1.0


# ═══════════════════════════════════════════════════ N6.3 path Monte Carlo

def test_sealed_era_status_reads_the_real_ledger_without_opening_it():
    status = PMC.sealed_era_status()
    assert status["this_script_called_sealed_or_open_sealed_window"] is False
    # G4 already spent the one permitted opening for this champion (committed
    # ledger row); a second opening would be a governance violation this
    # script must never cause.
    assert status["sealed_era_openings_for_this_champion"] >= 1
    assert status["sealed_era_openings_permitted"] == 1


def test_exact_champion_context_reads_committed_receipts():
    """G4_seal.json / G5_sizer.json are committed (unlike the parquet), so
    this always runs and never touches the sealed era itself."""
    ctx = PMC.exact_champion_context()
    assert "G4_sealed_era_2016_2024_107mo" in ctx
    assert "25bps" in ctx["G4_sealed_era_2016_2024_107mo"]
    ladder = ctx["CONTRACT_DRAFT_worst_case_ladder_sec6"]
    assert ladder["rung_1_0x"]["p_lose_half"] == 0.232


def test_acf_pure_function():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    a1 = PMC.acf(x, 1)
    assert -1.0 <= a1 <= 1.0
    # a perfectly persistent series has ACF(1) == 1
    ones = np.arange(50, dtype="float64")
    assert PMC.acf(ones, 1) > 0.9


def test_block_length_evidence_shape():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.02, size=202)
    out = PMC.block_length_evidence(x)
    assert out["n_months"] == 202
    assert out["chosen_block_mean_periods"] == PMC.BLOCK_MEAN_PERIODS
    assert len(out["acf_raw_returns_lags_1_12"]) == 12


def test_block_bootstrap_paths_deterministic_and_shaped():
    a = np.array([0.01, -0.02, 0.03, -0.01, 0.02, -0.03] * 10)
    p1 = PMC.block_bootstrap_paths(a, n_boot=50, block=4.0, horizon=24, seed=1)
    p2 = PMC.block_bootstrap_paths(a, n_boot=50, block=4.0, horizon=24, seed=1)
    assert p1.shape == (50, 24)
    np.testing.assert_array_equal(p1, p2)          # np.random.default_rng(seed)
    p3 = PMC.block_bootstrap_paths(a, n_boot=50, block=4.0, horizon=24, seed=2)
    assert not np.array_equal(p1, p3)


def test_path_stats_on_a_planted_crash_path():
    """A path that halves once (-50%) and stays flat: p_lose_half must read
    1.0 on every bootstrap draw (every block contains the crash month, since
    the series is short and the block wraps)."""
    a = np.array([-0.50] + [0.0] * 11)
    paths = PMC.block_bootstrap_paths(a, n_boot=200, block=1.0, horizon=12,
                                      seed=3)
    st = PMC.path_stats(paths)
    assert st["drawdown_distribution"]["worst"] <= -0.49
    assert 0.0 <= st["p_lose_half"] <= 1.0
    assert st["time_under_water_months"]["longest_streak_median"] >= 0


def test_path_stats_flat_series_has_zero_drawdown_and_no_ruin():
    a = np.zeros(24)
    paths = PMC.block_bootstrap_paths(a, n_boot=100, block=4.0, horizon=24,
                                      seed=4)
    st = PMC.path_stats(paths)
    assert st["p_lose_half"] == 0.0
    assert st["drawdown_distribution"]["worst"] == 0.0
    assert st["time_under_water_months"]["longest_streak_median"] == 0.0


_PROXY_PARQUET = (PMC.GROWTH_DIR / "G2_genome_series.parquet")


@pytest.mark.skipif(not _PROXY_PARQUET.exists(),
                    reason="G2_genome_series.parquet is gitignored (*.parquet) "
                          "and absent on a fresh CI clone")
def test_load_proxy_dev_series_never_crosses_into_the_sealed_era():
    from learner import growth_lab as GL
    s, path = PMC.load_proxy_dev_series(25.0)
    assert len(s) > 100
    assert str(s.index.max()) < GL.SEALED_START
    # the module's own self-check must pass without raising
    GL.assert_development_only(s, "test proxy series")


@pytest.mark.skipif(not _PROXY_PARQUET.exists(),
                    reason="G2_genome_series.parquet is gitignored (*.parquet) "
                          "and absent on a fresh CI clone")
def test_full_run_produces_a_well_formed_receipt():
    rec = PMC.run(argv=["test"])
    assert rec["llm_spend_usd"] == 0.0
    assert rec["sealed_era_status"]["this_script_called_sealed_or_open_sealed_window"] is False
    for label in ("1.0x", "1.3x"):
        r = rec["results_by_leverage"][label]
        assert 0.0 <= r["p_lose_half"] <= 1.0
        assert r["drawdown_distribution"]["worst"] <= r["drawdown_distribution"]["p95"]
        assert r["drawdown_distribution"]["p95"] <= r["drawdown_distribution"]["median"]
        assert r["time_under_water_months"]["longest_streak_median"] >= 0
    # 1.3x must be at least as risky as 1.0x on the SAME bootstrap horizon —
    # leverage cannot make a fixed return path safer.
    assert (rec["results_by_leverage"]["1.3x"]["p_lose_half"]
           >= rec["results_by_leverage"]["1.0x"]["p_lose_half"])
    assert "block_length_sensitivity_1_0x" in rec
    assert "existing_context_read_not_recomputed" in rec


def test_receipt_json_serialisable_end_to_end(tmp_path):
    """Both scripts' receipts must round-trip through json.dumps — a hidden
    numpy/pandas type is the usual way a receipt writer silently breaks."""
    rec = EX.run(n_pairs=4, n_canaries=2, cap_usd=1.0, dry_run=True, seed=9,
                 argv=["test"])
    out = tmp_path / "ex.json"
    EX.write_receipt(rec, out)
    json.loads(out.read_text(encoding="utf-8"))     # must not raise

    if _PROXY_PARQUET.exists():
        rec2 = PMC.run(argv=["test"])
        out2 = tmp_path / "pmc.json"
        PMC.write_receipt(rec2, out2)
        json.loads(out2.read_text(encoding="utf-8"))
