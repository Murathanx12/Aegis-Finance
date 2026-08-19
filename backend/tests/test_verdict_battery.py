"""VERDICT-BATTERY-1 — the judge's error rates, pinned at suite scale.

Small n_sims keeps the suite fast; the full 1000-sim receipt is produced
by the battery run and committed as data. What the suite pins: the
false-kill property (a true effect at the bar is never declared
noninferior at this dispersion), the null world's FWER, and refusals.
"""

from __future__ import annotations

import pytest

from backend.services import verdict_battery as VB


def test_true_effect_at_bar_is_never_declared_noninferior():
    r = VB.simulate_verdicts(true_delta=0.01, n_sims=40, seed=7, n_boot=150)
    assert r["LINEAR_NONINFERIOR"] == 0.0, (
        "FALSE KILL: a true effect at the economic bar was declared "
        "noninferior — the door-closing verdict on a live idea")


def test_null_world_win_rate_respects_fwer():
    r = VB.simulate_verdicts(true_delta=0.0, n_sims=60, seed=11, n_boot=150)
    assert r["COMPLEX_WINS"] <= 0.10, (
        f"false-positive rate {r['COMPLEX_WINS']} above tolerance — "
        f"Holm is not doing its job")


def test_large_effect_is_detected():
    # 2x the MDE at this dispersion — construction says ~high power
    mde = 2.8 * VB.MEASURED_PER_DATE_SD / (126 ** 0.5)
    r = VB.simulate_verdicts(true_delta=2 * mde, n_sims=40, seed=13, n_boot=150)
    assert r["COMPLEX_WINS"] >= 0.7, r


def test_battery_refuses_undeclared_worlds():
    with pytest.raises(VB.BatteryRefused):
        VB.simulate_verdicts(true_delta=float("nan"), n_sims=10)
    with pytest.raises(VB.BatteryRefused):
        VB.simulate_verdicts(true_delta=0.01, n_sims=0)


def test_not_established_is_the_honest_underpowered_answer():
    # at the bar with the measured dispersion, the dominant verdict must be
    # NOT_ESTABLISHED — the door stays open by name, not by accident
    r = VB.simulate_verdicts(true_delta=0.01, n_sims=40, seed=17, n_boot=150)
    assert r["NOT_ESTABLISHED"] >= 0.5, r
