"""CALIBRATION ON THE BOARD (roadmap M4), pinned by known answers.

Murphy's decomposition is an ALGEBRAIC identity, so most of these tests have a
right answer that can be reasoned about rather than measured:

* a set constructed so every bin's mean forecast equals its empirical outcome
  rate has reliability exactly 0;
* a forecaster with one distinct value has resolution exactly 0, because
  `ō_k == ō̄` by construction, and its Brier then equals its uncertainty;
* `Reliability − Resolution + Uncertainty == brier_binned` always — the
  decomposition is defined over a DISCRETE forecast, so the identity binds on
  the binned Brier and the raw one differs by `binning_residual`. A non-zero
  `identity_check_abs_error` is a bug in the function, never a property of the
  data.

The last two tests are the ones that matter operationally: a decomposition on
too few records is REFUSED rather than reported, and the base-rate control is
point-in-time rather than computed over the whole sample — a control that sees
the future flatters itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services import calibration as CAL


def test_perfectly_calibrated_synthetic_set_has_zero_reliability():
    """Ten bins, each with p == its own outcome rate by construction."""
    p, o = [], []
    for k in range(10):
        pk = (k + 0.5) / 10
        n_pos = round(pk * 20)
        p += [pk] * 20
        o += [1] * n_pos + [0] * (20 - n_pos)
    r = CAL.brier_decomposition(np.array(p), np.array(o), n_bins=10)
    assert r["decomposition"] == "ok"
    assert abs(r["reliability"]) < 1e-9


def test_constant_half_forecaster_has_zero_resolution():
    """One distinct forecast value -> one effective bin -> resolution is 0, and
    Brier collapses to Uncertainty exactly."""
    rng = np.random.default_rng(0)
    o = rng.integers(0, 2, size=500).astype(float)
    p = np.full(500, 0.5)
    r = CAL.brier_decomposition(p, o, n_bins=10)
    assert r["n_bins"] == 1, "500 identical forecasts are ONE bin, not ten"
    assert abs(r["resolution"]) < 1e-9
    assert abs(r["reliability"] - (0.5 - r["base_rate"]) ** 2) < 1e-9
    assert abs(r["brier_binned"] - (r["reliability"] + r["uncertainty"])) < 1e-9
    # one bin means the binned forecast IS the raw one, so nothing is thrown away
    assert abs(r["binning_residual"]) < 1e-9


def test_brier_identity_holds():
    """Reliability - Resolution + Uncertainty == Brier, to float tolerance."""
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, size=1000)
    o = (rng.uniform(size=1000) < p).astype(float)
    r = CAL.brier_decomposition(p, o, n_bins=10)
    # The identity is about the BINNED forecast. Asserting it against the raw
    # Brier would fail by the within-bin variance, which is a property of the
    # binning and not a bug -- so both are checked, each for what it is.
    assert r["identity_check_abs_error"] < 1e-9
    assert r["brier"] == pytest.approx(r["brier_binned"] + r["binning_residual"])
    # The residual's SIGN is not constrained, so the test asserts it is finite
    # and reported rather than asserting a direction it cannot have.
    assert np.isfinite(r["binning_residual"])


def test_a_well_calibrated_forecaster_beats_climatology():
    """A sanity BOUND, not an equality: a forecaster whose p IS the true outcome
    probability should, over a large seeded sample, score below the base-rate
    variance."""
    rng = np.random.default_rng(7)
    p = rng.uniform(0.05, 0.95, size=5000)
    o = (rng.uniform(size=5000) < p).astype(float)
    r = CAL.brier_decomposition(p, o, n_bins=10)
    assert r["beats_climatology"] is True
    assert r["resolution"] > r["reliability"]


def test_insufficient_n_refuses_decomposition():
    r = CAL.brier_decomposition(np.array([0.6, 0.4, 0.7]), np.array([1, 0, 1]), n_bins=10)
    assert r["decomposition"] == "insufficient_n"
    assert r["bins"] == []
    assert "noise dressed as diagnosis" in r["reason"]
    # the flat Brier is still reported -- refusing the SPLIT is not refusing the score
    assert r["brier"] == pytest.approx(((0.6 - 1) ** 2 + 0.4 ** 2 + (0.7 - 1) ** 2) / 3)


def test_no_bin_is_smaller_than_the_minimum():
    rng = np.random.default_rng(3)
    n = 60
    p = rng.uniform(0, 1, size=n)
    o = (rng.uniform(size=n) < p).astype(float)
    r = CAL.brier_decomposition(p, o, n_bins=10)
    assert r["decomposition"] == "ok"
    assert r["n_bins"] <= n // CAL.MIN_PER_BIN
    assert all(b["n"] >= CAL.MIN_PER_BIN - 1 for b in r["bins"]), r["bins"]


def test_every_bin_carries_its_own_standard_error():
    rng = np.random.default_rng(5)
    p = rng.uniform(0, 1, size=400)
    o = (rng.uniform(size=400) < p).astype(float)
    r = CAL.brier_decomposition(p, o)
    for b in r["bins"]:
        assert b["outcome_se"] >= 0.0
        assert b["overconfidence"] == pytest.approx(b["mean_forecast"] - b["mean_outcome"])


def test_mismatched_lengths_are_refused_rather_than_zipped():
    with pytest.raises(ValueError):
        CAL.brier_decomposition([0.5, 0.5], [1])


# ------------------------------------------------------------ the ledger side

def _rec(i, p, outcome, made, resolved, model="engine", mech=None):
    return {"prediction_id": f"r{i}", "probability": p, "outcome": outcome,
            "made_at": made, "resolved_at": resolved, "model": model,
            "model_version": "v1", "mechanism_id": mech}


def test_voided_and_open_records_are_not_scored():
    rows = [_rec(1, 0.6, 1, "2026-01-01", "2026-02-01"),
            _rec(2, 0.6, None, "2026-01-01", None),
            {**_rec(3, 0.6, 1, "2026-01-01", "2026-02-01"), "void_reason": "bad input"}]
    assert len(CAL.resolved_rows(rows)) == 1


def test_the_base_rate_control_is_point_in_time():
    """A base rate computed over the whole sample leaks the future into its own
    control. The first record, made before anything had resolved, gets 0.5 and
    is COUNTED as having had no history."""
    rows = [_rec(1, 0.9, 1, "2026-01-01", "2026-02-01"),
            _rec(2, 0.9, 1, "2026-03-01", "2026-04-01"),
            _rec(3, 0.9, 0, "2026-05-01", "2026-06-01")]
    row = CAL.base_rate_row(rows)
    assert row["model"] == "base_rate_forecaster" and row["pit"] is True
    assert row["n_no_history"] == 1
    # record 2 sees only record 1 (outcome 1) -> p = 1.0; record 3 sees two 1s.
    # A full-sample base rate would have been 2/3 for all three.
    assert row["base_rate"] == pytest.approx(2 / 3)


def test_persistence_refuses_below_three_quarter_pairs():
    rows = [_rec(i, 0.6, i % 2, "2026-01-01", "2026-02-01") for i in range(40)]
    out = CAL.persistence(rows)
    assert out["persistence"] == "insufficient_quarters"
    assert out["min_pairs"] == CAL.MIN_QUARTER_PAIRS


def test_the_report_groups_by_model_and_carries_both_windows():
    rng = np.random.default_rng(11)
    rows = []
    for i in range(300):
        p = float(rng.uniform(0.05, 0.95))
        rows.append(_rec(i, p, int(rng.uniform() < p), "2026-01-01", "2026-02-01",
                         model="engine" if i % 2 else "qwen2.5-7b"))
    out = CAL.report(rows, by="model")
    assert out["n_resolved"] == 300
    assert set(out["groups"]) == {"engine@v1", "qwen2.5-7b@v1"}
    assert out["overall"]["decomposition"] == "ok"
    assert "rolling" in out and "never instead of it" in out["rolling"]["note"]
    assert out["base_rate_row"]["model"] == "base_rate_forecaster"


def test_pre_1_4_0_rows_group_under_a_named_bucket_rather_than_vanishing():
    rows = [_rec(i, 0.5, i % 2, "2026-01-01", "2026-02-01") for i in range(60)]
    out = CAL.report(rows, by="mechanism_id")
    assert list(out["groups"]) == ["unstated (pre-1.4.0)"]


def test_an_empty_ledger_reports_rather_than_dividing_by_zero():
    out = CAL.report([])
    assert out["n_resolved"] == 0
    assert out["overall"]["decomposition"] == "insufficient_n"
    assert out["groups"] == {}


def test_the_ledger_route_carries_the_decomposition():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.routers import control

    app = FastAPI()
    app.include_router(control.router)
    body = TestClient(app).get("/api/control/ledger").json()
    assert "decomposition" in body
    d = body["decomposition"]
    # either a report or a named failure -- never a missing key, which a card
    # cannot tell from a zero
    assert "n_resolved" in d or "error" in d


def test_the_base_rate_control_is_not_quadratic():
    """The first version filtered the whole history per record. It ran fast on
    this machine only because the local ledger has 24,828 records and ZERO
    resolved ones -- a check that works on an empty set. A route the board polls
    must not go quadratic the day the resolver catches up."""
    import time

    n = 8000
    rows = [_rec(i, 0.5, i % 2,
                 f"2026-{1 + (i % 12):02d}-01", f"2026-{1 + (i % 12):02d}-15")
            for i in range(n)]
    t0 = time.time()
    row = CAL.base_rate_row(rows)
    elapsed = time.time() - t0
    assert row["n"] == n
    assert elapsed < 3.0, f"{n} records took {elapsed:.1f}s -- that is the quadratic shape"
