"""The null invariance contract, tested against the null that failed.

The load-bearing test is `test_n21s_registered_placebo_fails_the_contract`:
N21's matched-exposure placebo must be REFUSED by this module. A contract that
passes the design it was written because of has not been shown to do anything.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.research_gym import null_invariance as NI


def _clustered_mask(n=2000, seed=0, n_bursts=12, burst=40):
    """Fires arrive in bursts, as precursor fires actually do."""
    rng = np.random.default_rng(seed)
    m = [False] * n
    for s in rng.choice(n - burst, size=n_bursts, replace=False):
        for i in range(int(s), int(s) + burst):
            m[i] = True
    return m


def _dates(n=2000, start="2006-01-01"):
    import pandas as pd
    return [str(d)[:10] for d in pd.bdate_range(start, periods=n)]


# ── the defect, refused ────────────────────────────────────────────────────

def test_n21s_registered_placebo_fails_the_contract():
    """Same exposure, uniform windows — clustering is not preserved."""
    real = _clustered_mask()
    rng = np.random.default_rng(20260816)
    n_on = sum(real)
    draws = [NI.uniform_random_windows(len(real), n_on // 20, 20, rng)
             for _ in range(50)]

    spec = NI.NullSpec("matched_exposure_uniform_windows",
                       preserves=("frequency", "clustering"))
    v = NI.verify(spec, NI.summarise(real),
                  [NI.summarise(d) for d in draws])
    assert not v.ok
    failed = {c.detail for c in v.checks if not c.ok}
    passed = {c.detail for c in v.checks if c.ok}
    # And the shape of the failure is the reason a shallow check misses it:
    # matching the WINDOW LENGTH makes the placebo indistinguishable at lag 1.
    # It is only at lags beyond one window that the bursts show up as bursts.
    assert "1" in passed
    assert failed >= {"5", "10", "20"}
    assert "clustering" in v.why()
    with pytest.raises(NI.NullContractViolation):
        NI.assert_verified(spec, NI.summarise(real),
                           [NI.summarise(d) for d in draws])


def test_the_circular_block_shift_passes_the_same_contract():
    """The null N21 should have registered."""
    real = _clustered_mask()
    rng = np.random.default_rng(20260816)
    draws = [NI.circular_block_shift(real, int(rng.integers(1, len(real))))
             for _ in range(50)]
    spec = NI.NullSpec("circular_block_shift",
                       preserves=("frequency", "clustering", "run_lengths",
                                  "turnover"))
    v = NI.verify(spec, NI.summarise(real), [NI.summarise(d) for d in draws])
    assert v.ok, v.why()


def test_a_p_value_cannot_be_computed_from_a_violating_null():
    real = _clustered_mask()
    rng = np.random.default_rng(1)
    draws = [NI.uniform_random_windows(len(real), sum(real) // 20, 20, rng)
             for _ in range(50)]
    spec = NI.NullSpec("matched_exposure", preserves=("frequency", "clustering"))
    with pytest.raises(NI.NullContractViolation, match="NULL CONTRACT VIOLATED"):
        NI.p_value(-6.843, [-1.0] * 50, spec=spec,
                   real_summary=NI.summarise(real),
                   placebo_summaries=[NI.summarise(d) for d in draws])


def test_a_verified_null_does_produce_a_p_value():
    real = _clustered_mask()
    rng = np.random.default_rng(2)
    draws = [NI.circular_block_shift(real, int(rng.integers(1, len(real))))
             for _ in range(200)]
    spec = NI.NullSpec("circular_block_shift",
                       preserves=("frequency", "clustering", "run_lengths"))
    stats = list(rng.normal(-5.0, 3.0, 200))
    out = NI.p_value(-6.843, stats, spec=spec,
                     real_summary=NI.summarise(real),
                     placebo_summaries=[NI.summarise(d) for d in draws])
    assert 0.0 < out["p_value"] <= 1.0
    assert out["null_contract"]["ok"]
    # What the null leaves free is reported beside the p-value, not omitted.
    assert "turnover" in out["leaves_free"]


# ── the ways a contract can be hollow ──────────────────────────────────────

def test_declaring_nothing_is_refused():
    with pytest.raises(ValueError, match="must declare what it preserves"):
        NI.NullSpec("anything_goes", preserves=())


def test_an_unknown_invariant_is_refused():
    with pytest.raises(ValueError, match="unknown invariant"):
        NI.NullSpec("typo", preserves=("clusteringg",))


def test_declaring_an_invariant_nothing_measured_is_refused():
    """`seasonality` without dates is a declaration with no measurement."""
    real = _clustered_mask(400)
    draws = [NI.circular_block_shift(real, k) for k in (7, 40, 91)]
    spec = NI.NullSpec("seasonal", preserves=("frequency", "seasonality"))
    with pytest.raises(NI.NullContractViolation, match="was not measured"):
        NI.verify(spec, NI.summarise(real), [NI.summarise(d) for d in draws])


def test_an_empty_ensemble_is_refused():
    spec = NI.NullSpec("x", preserves=("frequency",))
    with pytest.raises(NI.NullContractViolation, match="no placebo draws"):
        NI.verify(spec, NI.summarise([True, False]), [])


def test_undeclared_invariants_are_listed_not_silently_skipped():
    real = _clustered_mask(500)
    draws = [NI.circular_block_shift(real, k) for k in (11, 97, 213)]
    spec = NI.NullSpec("frequency_only", preserves=("frequency",))
    v = NI.verify(spec, NI.summarise(real), [NI.summarise(d) for d in draws])
    assert v.ok
    assert set(v.undeclared) >= {"clustering", "run_lengths", "turnover"}
    assert "NOT held fixed" in v.why()


# ── measurement ────────────────────────────────────────────────────────────

def test_summarise_measures_what_it_says():
    m = [False, True, True, True, False, False, True, False]
    s = NI.summarise(m)
    assert s["frequency"] == pytest.approx(4 / 8)
    assert s["run_lengths"] == {"mean": 2.0, "max": 3, "n_runs": 2}
    assert s["turnover"] == pytest.approx(4 / 8)


def test_a_rotation_preserves_run_lengths_exactly():
    real = _clustered_mask(600, seed=3)
    rot = NI.circular_block_shift(real, 137)
    a, b = NI.summarise(real), NI.summarise(rot)
    assert a["frequency"] == b["frequency"]
    # A rotation can split one spell across the seam; the mean is preserved to
    # within that single boundary effect, never more.
    assert abs(a["run_lengths"]["n_runs"] - b["run_lengths"]["n_runs"]) <= 1


def test_seasonality_is_measured_over_the_treated_bars_only():
    dates = _dates(500)
    m = [d[5:7] == "03" for d in dates]
    s = NI.summarise(m, dates=dates)
    assert s["seasonality"]["03"] == pytest.approx(1.0)
    assert s["seasonality"]["07"] == pytest.approx(0.0)


def test_cross_sectional_sync_needs_a_panel():
    a = _clustered_mask(300, seed=1)
    s_solo = NI.summarise(a)
    assert "cross_sectional_sync" not in s_solo
    s_panel = NI.summarise(a, panel={"A": a, "B": a, "C": a})
    assert s_panel["cross_sectional_sync"] == pytest.approx(1.0)
    s_split = NI.summarise(a, panel={"A": a, "B": [not x for x in a]})
    assert s_split["cross_sectional_sync"] == pytest.approx(0.0)


# ── which invariants an outcome forces ─────────────────────────────────────

def test_a_path_dependent_outcome_forces_clustering():
    assert "clustering" in NI.declared_invariants_for("max drawdown per block")
    assert "clustering" in NI.declared_invariants_for("terminal log growth")
    assert "run_lengths" in NI.declared_invariants_for("time under water")


def test_a_mean_outcome_does_not():
    inv = NI.declared_invariants_for("mean forward 20-day return")
    assert "clustering" not in inv
    assert "frequency" in inv
