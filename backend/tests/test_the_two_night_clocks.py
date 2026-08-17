"""Two clocks, named, and the one the guard forecasts.

THE DEFECT (found in review, 2026-08-17)
========================================
Night 1's receipt says the night took **115.4 minutes**. The first version of
the timing calibration wrote its constants against a **133-minute** "actual wall
clock". Both numbers are real; neither is wrong; calling both "wall clock" is
what produced a false calibration.

    CLOCK_RUN_ELAPSED         115.4 min  elapsed_s / 60  ==  timing.actual_minutes
    CLOCK_DECISION_TO_FINISH  133.6 min  decision_lag_minutes_at_end
    difference                 18.2 min  decision_lag_minutes  (snapshot assembly)

Everything derived from 133.6 was wrong: it gave 199.5 s/cell where the receipt's
own `measured.mean_cell_wall_seconds` is **173.0** — and 173.0 x 40 cells = 115.3
min, which is CLOCK_RUN_ELAPSED. It also produced the claim that the measured
3.529x efficiency "counts calls in flight, not wall-clock speedup"; the receipt
shows it is exactly `mean_cell_serial_seconds / mean_cell_wall_seconds`, a
genuine per-cell wall-clock speedup.

These tests pin the arithmetic against Night 1's REAL receipt, so the clocks
cannot be conflated again by anyone reading a summary instead of the file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import investigator_night as N

RECEIPT = (Path(__file__).resolve().parents[1]
           / "data" / "optimus" / "iif1_nights" / "2026-08-17.json")

pytestmark = pytest.mark.skipif(
    not RECEIPT.exists(),
    reason="Night 1's receipt is the evidence these tests are about; without it "
           "there is nothing to reconcile and a synthetic stand-in would pin "
           "arithmetic rather than the night that happened")


@pytest.fixture(scope="module")
def r() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_the_two_clocks_differ_by_exactly_the_snapshot_lag(r):
    """The whole reconciliation, from the receipt's own fields."""
    clock_a = r["elapsed_s"] / 60.0                       # run_night stopwatch
    clock_b = r["decision_lag_minutes_at_end"]            # snapshot -> last cell
    lag = r["decision_lag_minutes"]                       # snapshot -> run start

    assert clock_a == pytest.approx(115.4, abs=0.1)
    assert clock_b == pytest.approx(133.6, abs=0.1)
    assert clock_b - clock_a == pytest.approx(lag, abs=0.1), (
        "the two clocks must differ by exactly the assembly lag; if they do not, "
        "one of them is measuring something nobody has named")


def test_the_receipts_actual_minutes_is_CLOCK_RUN_ELAPSED_not_the_other(r):
    """`timing.actual_minutes` is the run stopwatch. Named, not assumed."""
    assert r["timing"]["actual_minutes"] == pytest.approx(
        r["elapsed_s"] / 60.0, abs=0.1)
    assert r["timing"]["actual_minutes"] != pytest.approx(
        r["decision_lag_minutes_at_end"], abs=1.0)


def test_the_true_per_cell_wall_time_is_173_not_199(r):
    """199.5 s/cell was 133.6 min / 40. The receipt measured 173.0 directly."""
    m = r["timing"]["measured"]
    n_cells = m["n_cells_measured"]
    assert n_cells == 40
    assert m["mean_cell_wall_seconds"] == pytest.approx(173.0, abs=0.5)
    # And it reconstructs CLOCK_RUN_ELAPSED, which is what makes it the right one.
    assert m["mean_cell_wall_seconds"] * n_cells / 60.0 == pytest.approx(
        r["elapsed_s"] / 60.0, rel=0.01)
    # The number the bad calibration used, shown as the artefact it was.
    assert r["decision_lag_minutes_at_end"] * 60 / n_cells == pytest.approx(
        199.5, abs=1.0)


def test_the_measured_efficiency_IS_a_wall_clock_speedup(r):
    """Correcting a claim this repo made and got wrong.

    `measured_concurrency_efficiency` was described as counting calls in flight.
    It does not: it is serial-equivalent cell seconds over actual cell seconds.
    """
    m = r["timing"]["measured"]
    assert m["measured_efficiency"] == pytest.approx(
        m["mean_cell_serial_seconds"] / m["mean_cell_wall_seconds"], rel=1e-3)
    assert m["measured_efficiency"] == pytest.approx(3.529, abs=0.01)


def test_the_modelled_serial_branch_was_safe_only_BY_CANCELLATION(r):
    """The finding that moved the decision basis.

    The serial branch was adopted as "a verdict that needs no unverifiable
    input". It needs `MEASURED_CALL_SECONDS`, and Night 1 shows that is 1.98x
    low — so the modelled serial is HALF the true serial cost and conservative
    against the real run only because ignoring a 3.529x speedup cancels the
    latency error. This project's signature failure mode, inside the fix written
    to eliminate it.
    """
    m = r["timing"]["measured"]
    true_serial_min = m["mean_cell_serial_seconds"] * m["n_cells_measured"] / 60.0
    modelled = N.projected_night_minutes(
        k=40, n_arms=5, arm_concurrency=1,
        calls_per_cell=N.derive_calls_per_cell()["value"])
    actual = r["elapsed_s"] / 60.0

    assert true_serial_min == pytest.approx(407.0, abs=2.0)
    assert modelled == pytest.approx(205.5, abs=1.0)
    assert modelled / true_serial_min == pytest.approx(0.50, abs=0.03), (
        "the modelled serial is meant to be a pessimistic bound and is half the "
        "measured serial cost")
    # The cancellation, as an identity: conservatism == speedup / latency error.
    implied_latency = m["mean_cell_serial_seconds"] / (5 * 7.085)
    latency_error = implied_latency / N.MEASURED_CALL_SECONDS
    assert latency_error == pytest.approx(1.98, abs=0.05)
    assert (m["measured_efficiency"] / latency_error
            == pytest.approx(modelled / actual, rel=0.05)), (
        "the modelled serial's apparent safety factor should equal the measured "
        "speedup divided by the latency understatement — that identity IS the "
        "cancellation")


# ── the bound that replaced it ──────────────────────────────────────────────
def _receipt(tmp_path, night, *, status="ok", elapsed_s=6921.8, sandbox=False):
    (tmp_path / f"{night}.json").write_text(json.dumps({
        "night": night, "status": status, "sandbox": sandbox,
        "elapsed_s": elapsed_s, "calls": 1417,
        "tickers": [f"T{i}" for i in range(40)],
        "per_arm": {f"a{i}": {} for i in range(5)},
    }), encoding="utf-8")


def test_the_duration_bound_is_the_worst_night_times_a_DECLARED_factor(tmp_path):
    _receipt(tmp_path, "2026-08-17", elapsed_s=6921.8)          # 115.36 min
    out = N.derive_night_duration_bound(tmp_path)
    assert out["worst_minutes"] == pytest.approx(115.36, abs=0.05)
    assert out["safety_factor"] == 2.0
    assert out["value"] == pytest.approx(230.7, abs=0.2)
    assert out["clock"] == N.CLOCK_RUN_ELAPSED
    assert out["n_nights"] == 1


def test_the_factor_is_declared_rather_than_fitted_to_a_preferred_schedule():
    """2.0 is a round number, not the 1.78 that would reproduce the old answer.

    Fitting the factor so the bound lands on the previously-published 205.5 would
    be choosing the safety margin to bless a schedule already decided — the exact
    move this project forbids elsewhere. The declared 2.0 is TIGHTER than the old
    basis, which is the direction a declared constant is allowed to be wrong in.
    """
    assert N.DECLARED_DURATION_SAFETY_FACTOR == 2.0
    assert 115.36 * N.DECLARED_DURATION_SAFETY_FACTOR > 205.5


def test_void_and_sandbox_nights_are_excluded_from_the_bound(tmp_path):
    _receipt(tmp_path, "2026-08-14", status="void", elapsed_s=999_999)
    _receipt(tmp_path, "2026-08-16", sandbox=True, elapsed_s=999_999)
    out = N.derive_night_duration_bound(tmp_path)
    assert out["value"] is None
    assert out["basis"] == "NO_COMPLETED_NIGHTS"


def test_the_maximum_is_taken_not_the_mean(tmp_path):
    _receipt(tmp_path, "2026-08-17", elapsed_s=6921.8)     # 115.4
    _receipt(tmp_path, "2026-08-18", elapsed_s=9000.0)     # 150.0
    out = N.derive_night_duration_bound(tmp_path)
    assert out["worst_minutes"] == pytest.approx(150.0, abs=0.1)


def test_a_measurement_can_only_TIGHTEN_the_guard_never_loosen_it(monkeypatch):
    """The max() rule, stated as the property that matters.

    A cheap night must not license a start the previous basis refused. With a
    tiny measured duration the modelled serial floor still governs.
    """
    monkeypatch.setattr(N, "derive_night_duration_bound",
                        lambda *a, **k: {"value": 5.0, "basis": "x",
                                         "n_nights": 1, "observed": [],
                                         "safety_factor": 2.0,
                                         "clock": N.CLOCK_RUN_ELAPSED})
    from backend.services import market_sessions as MS
    from datetime import datetime, timezone
    monkeypatch.setattr(MS, "next_session_open",
                        lambda _n: datetime(2026, 8, 17, 13, 30,
                                            tzinfo=timezone.utc))
    rep = N.assert_night_fits_before_open(
        k=40, n_arms=5, now=datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc))
    assert rep["decision_basis"] == "MODELLED_SERIAL_PESSIMISTIC"
    assert rep["projected_minutes"] == pytest.approx(
        rep["modelled_serial_minutes"], abs=0.1)


def test_the_report_names_the_clock_it_forecasts(monkeypatch):
    from backend.services import market_sessions as MS
    from datetime import datetime, timezone
    monkeypatch.setattr(MS, "next_session_open",
                        lambda _n: datetime(2026, 8, 17, 13, 30,
                                            tzinfo=timezone.utc))
    rep = N.assert_night_fits_before_open(
        k=40, n_arms=5, now=datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc))
    assert rep["decision_clock"] == N.CLOCK_RUN_ELAPSED
    assert "measured_duration_bound" in rep
    assert "modelled_serial_minutes" in rep
