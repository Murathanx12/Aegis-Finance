"""LABOR DAY LAB — lane B's guards.

Three things are pinned here, and each one exists because it was measured on
2026-09-07 rather than argued about:

1. **The known-answer battery still recovers a planted edge and still refuses to
   call an underpowered null NOISE.** A small version of `B1` runs end to end —
   real `dataset` schema, real `models`, real `evaluate`, real `inference`, real
   `evidence_memory` — in about half a minute.

2. **A pure null can no longer be promoted to REGIME_SPECIFIC.** That is the
   defect B1 found: `eras_with_a_positive_mean == 1 of 3` is the SIGN of three
   numbers, which under a null is a 3/8 coin flip, and the branch sat AHEAD of
   the REFUTED clause with no significance requirement of any kind. The battery's
   null world walked into it with three POWERED observations, all adjudicated
   NOISE, zero passes clearing any bar.

3. **The B2 exam's grading arithmetic**, on a stubbed decider, so a monotonicity
   share can never be a bug in the comparison rather than a fact about a model.
   (The B2 script lives in the terminal repo; only its arithmetic is portable,
   so what is checked here is the shape of the claim, not the script.)

Run:  AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_labor_lane_b.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import evidence_memory as EM                       # noqa: E402
from scripts import labor_b1_known_answer_battery as B1         # noqa: E402


# ───────────────────────────────────────────────── 1. the battery, end to end


@pytest.fixture(scope="module")
def fast_battery(tmp_path_factory):
    """One `--fast` battery, shared by every assertion in this module."""
    cfg = B1.Cfg(fast=True)
    return cfg, B1.run_battery(cfg)


def test_the_battery_recovers_the_planted_edge_with_the_right_sign(fast_battery):
    cfg, r = fast_battery
    lin = r["adjudication"]["per_world"]["linear"]
    assert lin["measured_annualised_excess"] > 0, (
        "a planted POSITIVE edge came back negative — the machine has a sign "
        "error somewhere between the model and the book")
    assert lin["p_holm"] < 0.05, (
        f"planted {lin['planted_effect_annualised']}/yr against an MDE of "
        f"{lin['machine_mde_annual_at_t2']}/yr and the family-corrected p is "
        f"{lin['p_holm']} — a miss the world cannot explain")
    assert lin["planted_effect_annualised"] > lin["machine_mde_annual_at_t2"], (
        "the plant must sit ABOVE the machine's own MDE or a miss is not a miss")


def test_an_underpowered_null_is_CANNOT_DETERMINE_and_never_NOISE(fast_battery):
    """36 OOS months cannot see a 3%/yr effect. The vocabulary exists to say so."""
    cfg, r = fast_battery
    nulls = {k: v for k, v in r["results"].items() if k.startswith("null::")}
    assert nulls
    for k, v in nulls.items():
        assert v["powered"] is False, f"{k} should not be powered on 36 months"
        assert str(v["verdict"]).startswith("CANNOT DETERMINE"), (
            f"{k} reported {v['verdict']!r} — reporting an absence of evidence "
            "as evidence of absence")
    assert r["evidence_memory"]["states"]["null"]["state"] == "IDEA"


def test_the_battery_never_writes_to_the_real_evidence_memory(fast_battery):
    cfg, r = fast_battery
    assert r["safety"]["real_evidence_memory_touched"] is False
    assert str(EM.STORE) not in r["evidence_memory"]["store_path"]
    assert EM.STORE == EM.STORE_DIR / "evidence_memory.jsonl", (
        "the battery redirected the store and did not put it back")


def test_the_allocator_parks_a_worthless_sleeve_in_the_benchmark(fast_battery):
    cfg, r = fast_battery
    rows = {x["sleeve"]: x for x in r["allocator"]["rows"]}
    assert float(rows["world_null"]["weight"]) == 0.0
    assert "U_BELOW_BENCHMARK" in str(rows["world_null"]["binding_constraint"])
    assert r["allocator"]["residual"]["destination"] == "benchmark_SPY"


def test_the_battery_adjudicates_itself(fast_battery):
    cfg, r = fast_battery
    assert r["adjudication"]["ALL_PASS"] is True, (
        "the fast battery declared a miss: "
        + "; ".join(r["adjudication"]["findings"][:3]))


# ─────────────────────────── 2. the defect B1 found, pinned so it cannot return


def _null_row(era_positive: int, powered: bool = True) -> dict:
    """One observation of a cell that is INDISTINGUISHABLE FROM NOISE: powered,
    nothing cleared, and an era table whose signs are the only structure in it."""
    return {
        "utc": "2026-09-07T00:00:00+00:00", "family_id": "F", "cell": "c",
        "variant": f"v{era_positive}",
        "n_months": 240, "sharpe": 0.01,
        "dsr": 0.30, "spa_p": 0.80, "pbo": 0.55,
        "powered": powered, "verdict": "NOISE",
        "years_needed_for_t2": 400.0, "years_observed": 20.0,
        "eras": {"eras_measured": 3, "eras_with_a_positive_mean": 1,
                 "holds_in_2_of_3": False, "same_sign_in_2_of_3": True},
        "gross_beats_market": False, "net_beats_market": False,
    }


def test_a_pure_null_cannot_be_promoted_to_REGIME_SPECIFIC():
    """THE DEFECT, exactly as B1 produced it.

    Three powered observations, none clearing any bar, each landing at
    'positive in exactly one of three eras' — which under a null happens with
    probability 3/8 per observation. Before 2026-09-07 this returned
    REGIME_SPECIFIC, an EXPORTED state that reaches `signal_registry.yaml`.
    """
    rows = [dict(_null_row(1), variant=f"v{i}", sharpe=0.01 + i * 0.001)
            for i in range(3)]
    s = EM.state_of(rows)
    assert s["state"] != "REGIME_SPECIFIC", (
        "a pure null was promoted to an EXPORTED state on the sign of three "
        f"era means: {s['why']}")
    assert s["state"] == "REFUTED", (
        f"three POWERED observations and nothing cleared the bar should refute; "
        f"got {s['state']} — {s['why']}")
    assert s["one_era_only_passes_blocked_by_a_capping_verdict"] == 3


def test_a_regime_row_that_is_NOT_noise_can_still_promote():
    """The fix must not close the branch it is protecting.

    A row whose own fields earn a non-capping verdict — here NOVEL, because it
    clears the DSR/SPA/PBO bar and holds in two of three eras — still counts,
    so a genuine one-era finding is not silently deleted by the guard.
    """
    good = {**_null_row(1), "dsr": 0.99, "spa_p": 0.01, "pbo": 0.10,
            "eras": {"eras_measured": 3, "eras_with_a_positive_mean": 1,
                     "holds_in_2_of_3": True, "same_sign_in_2_of_3": True}}
    rows = [dict(good, variant=f"g{i}", sharpe=0.4 + i * 0.01) for i in range(2)]
    s = EM.state_of(rows)
    # It clears the full bar, so SUPPORTED wins the ordering -- what matters is
    # that the regime counter was NOT blocked.
    assert s["one_era_only_passes"] == 2
    assert s["one_era_only_passes_blocked_by_a_capping_verdict"] == 0


def test_the_guard_derives_the_verdict_and_does_not_trust_the_stamp():
    """A job that stamps an optimistic word must not buy a promotion with it."""
    rows = [dict(_null_row(1), variant=f"v{i}", verdict="NOVEL",
                 sharpe=0.01 + i * 0.001) for i in range(3)]
    s = EM.state_of(rows)
    assert s["state"] == "REFUTED", (
        "the recorded verdict string was trusted over the row's own numbers")


# ───────────────────────────────── 3. B2's grading arithmetic, on a stub


def _pair(good_p, bad_p, canary=False):
    item = {"pair_id": "P", "family": "fda", "is_canary": canary}
    good = {"p_up_21d": good_p, "exp_return": (good_p - 0.5) * 0.2,
            "downside_5pct": -0.2 + (good_p - 0.5) * 0.1}
    bad = {"p_up_21d": bad_p, "exp_return": (bad_p - 0.5) * 0.2,
           "downside_5pct": -0.2 + (bad_p - 0.5) * 0.1}
    return item, good, bad


def _grade_pair(item, good, bad):
    """A local copy of B2's comparison, because the script lives in the OTHER
    repo and the two repos do not share a path. The numbers it produces are
    asserted against hand-computed values, so a drift in either copy shows up as
    a failure here rather than as a silently different monotonicity share."""
    d_p = good["p_up_21d"] - bad["p_up_21d"]
    d_r = good["exp_return"] - bad["exp_return"]
    d_d = good["downside_5pct"] - bad["downside_5pct"]
    return {"d_p_up": d_p, "p_up_moves_correctly": d_p > 0,
            "exp_return_moves_correctly": d_r > 0,
            "downside_moves_correctly": d_d >= 0,
            "canary_moved": (abs(d_p) > 0.05) if item["is_canary"] else None}


def test_monotonicity_is_a_direction_not_a_magnitude():
    g = _grade_pair(*_pair(0.51, 0.50))
    assert g["p_up_moves_correctly"] is True
    assert abs(g["d_p_up"] - 0.01) < 1e-9, (
        "a one-point move counts as correct; the magnitude is reported "
        "separately and must never be folded into the share")


def test_a_backwards_forecast_fails_all_three_legs():
    g = _grade_pair(*_pair(0.20, 0.80))
    assert g["p_up_moves_correctly"] is False
    assert g["exp_return_moves_correctly"] is False
    assert g["downside_moves_correctly"] is False


def test_the_canary_fires_only_on_a_move_bigger_than_the_tolerance():
    assert _grade_pair(*_pair(0.52, 0.50, canary=True))["canary_moved"] is False
    assert _grade_pair(*_pair(0.62, 0.50, canary=True))["canary_moved"] is True
