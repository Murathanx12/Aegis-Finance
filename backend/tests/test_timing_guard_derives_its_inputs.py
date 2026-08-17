"""The timing guard derives its inputs, and decides on the branch it can trust.

THE DEFECT (Night 1, 2026-08-17)
================================
`arm_concurrency` was supplied by the caller and derived by nobody. The schedule
planner validated the start time at 1 while the runner executed at 5 — a
five-fold gap with nothing positioned to notice, because both numbers were inputs
and neither was a measurement.

It did not bite, and why it did not is worse than if it had: conc=1 is the
PESSIMISTIC branch, so it absorbed a second error on a different axis
(`MEASURED_CALLS_PER_CELL = 4.8` against a measured 7.085 — 48% low). Two wrong
constants cancelled into 91.5 minutes of apparent headroom that was 4 minutes at
the declared efficiency. **A projection agreeing with reality is not evidence
either input is right.**

THE PART THAT SURPRISED THE FIX
===============================
Deriving the runner's concurrency and projecting on it makes the guard LESS SAFE.
Against Night 1's actual 133-minute wall clock (40 cells, 199.5 s/cell):

    serial, calls/cell 7.085            205.5 min   OVER  -> safe
    conc=5 at declared efficiency 2.0   102.7 min   UNDER -> unsafe
    conc=5 at "measured" eff 3.529       58.2 min   UNDER -> unsafe

The realized speedup was 1.545x, BELOW the declared 2.0 whose comment calls it
conservative. So the refusal rests on the serial branch always: a verdict that
holds serially does not depend on an input the guard cannot verify.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.services import investigator_night as N

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def prereg_readable(monkeypatch):
    """Make the frozen pre-registration readable WITHOUT the sibling repo.

    Same fixture as `test_iif1_readiness_is_free.py`, and for the same paid-for
    reason: CI checks out ONE repo, so `../Aegis module/scripts/iif1_config.py`
    is genuinely absent there. **A test whose result depends on what else happens
    to be checked out is not a test of the code** — and the signal it corrupts is
    the one gating production. Tests that need the registration say so.
    """
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", P.runtime_surface)
    return P


# ── calls per cell: derived from COMPLETED nights, conservatively ───────────
def _receipt(tmp_path, night, *, status="ok", calls=1417, k=40, arms=5,
             sandbox=False):
    p = tmp_path / f"{night}.json"
    p.write_text(json.dumps({
        "night": night, "status": status, "sandbox": sandbox,
        "calls": calls,
        "tickers": [f"T{i}" for i in range(k)],
        "per_arm": {f"arm{i}": {} for i in range(arms)},
    }), encoding="utf-8")
    return p


def test_calls_per_cell_is_measured_from_a_completed_night(tmp_path):
    _receipt(tmp_path, "2026-08-17", calls=1417, k=40, arms=5)
    out = N.derive_calls_per_cell(tmp_path)
    assert out["value"] == pytest.approx(7.085, abs=1e-3)
    assert out["basis"] == "MEASURED_MAX_OVER_COMPLETED_NIGHTS"
    assert out["n_nights"] == 1
    assert out["declared"] == N.MEASURED_CALLS_PER_CELL


def test_a_void_night_is_excluded_because_it_undercounts_by_construction(
        tmp_path):
    """2026-08-14 reads 2.8 calls/cell because it was TRUNCATED.

    Projecting a complete night from an incomplete one is the denominator error
    in a new costume: the night that stopped early did not discover a cheaper
    way to run, it simply stopped.
    """
    _receipt(tmp_path, "2026-08-14", status="void", calls=224, k=40, arms=2)
    out = N.derive_calls_per_cell(tmp_path)
    assert out["n_nights"] == 0
    assert out["basis"] == "DECLARED_NO_COMPLETED_NIGHTS"
    assert out["value"] == N.MEASURED_CALLS_PER_CELL


def test_a_sandbox_night_is_excluded(tmp_path):
    _receipt(tmp_path, "2026-08-16", sandbox=True, calls=99_999)
    assert N.derive_calls_per_cell(tmp_path)["n_nights"] == 0


def test_the_maximum_is_taken_not_the_mean(tmp_path):
    """This feeds a guard deciding whether a paid night beats the bell.

    An average projection is wrong half the time in the direction that
    contaminates the trial.
    """
    _receipt(tmp_path, "2026-08-17", calls=1417)          # 7.085
    _receipt(tmp_path, "2026-08-18", calls=2000)          # 10.0
    out = N.derive_calls_per_cell(tmp_path)
    assert out["value"] == pytest.approx(10.0), "took the mean, not the max"


def test_observations_may_only_make_the_guard_more_conservative(tmp_path):
    """A cheap night must not talk the projection down into a window it fits.

    If the receipts say less than the rehearsal constant did, the constant is
    retained — observations are allowed to raise this number and never lower it.
    """
    _receipt(tmp_path, "2026-08-17", calls=200)   # 1.0 calls/cell, very cheap
    out = N.derive_calls_per_cell(tmp_path)
    assert out["value"] == N.MEASURED_CALLS_PER_CELL
    assert out["basis"] == "DECLARED_EXCEEDS_MEASURED"


def test_a_torn_receipt_is_skipped_not_counted_as_a_free_night(tmp_path):
    (tmp_path / "2026-08-19.json").write_text("{not json", encoding="utf-8")
    _receipt(tmp_path, "2026-08-17", calls=1417)
    out = N.derive_calls_per_cell(tmp_path)
    assert out["n_nights"] == 1
    assert out["value"] == pytest.approx(7.085, abs=1e-3)


def test_an_absent_receipts_dir_says_so_rather_than_refusing(tmp_path):
    """With zero completed nights there is nothing to derive.

    Refusing here would make the first night of any campaign impossible. The
    LABEL is what stops the fallback from being silent.
    """
    out = N.derive_calls_per_cell(tmp_path / "does-not-exist")
    assert out["basis"] == "DECLARED_NO_COMPLETED_NIGHTS"
    assert out["value"] == N.MEASURED_CALLS_PER_CELL


# ── concurrency: derived, or refused ───────────────────────────────────────
def test_the_runner_concurrency_is_derived_from_the_frozen_prereg(
        prereg_readable):
    assert N.derive_runner_concurrency() == 5


def test_the_guard_REFUSES_when_it_cannot_derive_the_concurrency(monkeypatch):
    """The canon-mandated missing-input test.

    A guard whose input is on the honour system will fool its own author. With
    the registration unreadable there is no way to know what the runner will do,
    and a default would be exactly the thing that failed on Night 1.
    """
    import backend.services.iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse",
                        lambda: (_ for _ in ()).throw(RuntimeError("no prereg")))
    with pytest.raises(N.ConcurrencyNotDerivable, match="Refusing|refus"):
        N.derive_runner_concurrency()


def test_a_registration_without_the_field_refuses_rather_than_defaulting(
        monkeypatch):
    import backend.services.iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", lambda: {"TRIGGERS_PER_NIGHT": 40})
    with pytest.raises(N.ConcurrencyNotDerivable,
                       match="MAX_ARM_CONCURRENCY"):
        N.derive_runner_concurrency()


def test_a_caller_supplied_concurrency_that_disagrees_is_refused(
        prereg_readable):
    """The five-fold gap, stated as a test.

    Passing 1 while the runner runs 5 is no longer a quiet pessimism that
    happens to absorb another error — it is a refusal that names both numbers.
    """
    with pytest.raises(N.ConcurrencyNotDerivable, match="five-fold|disagrees"):
        N.assert_night_fits_before_open(k=40, n_arms=5, arm_concurrency=1)


# ── the decision basis ─────────────────────────────────────────────────────
def test_every_concurrency_branch_underprojects_night_1s_real_wall_clock():
    """The measurement that decided the design.

    If this ever stops being true, the concurrency model has been fixed and the
    decision basis can be revisited. Until then, projecting on the runner's real
    concurrency would let a night through that cannot finish.
    """
    ACTUAL_MINUTES = 133.0            # 17:44 -> 19:58 local, 40 cells
    serial = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=1,
                                       calls_per_cell=7.085)
    at_declared = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5,
                                            calls_per_cell=7.085)
    at_measured_eff = N.projected_night_minutes(
        k=40, n_arms=5, arm_concurrency=5, calls_per_cell=7.085,
        efficiency=3.529)

    assert serial > ACTUAL_MINUTES, "the serial branch is no longer conservative"
    assert at_declared < ACTUAL_MINUTES, (
        "the declared-efficiency branch no longer under-projects — recheck "
        "whether the decision may safely move off serial")
    assert at_measured_eff < at_declared, (
        "the 'measured' efficiency is supposed to be the MORE optimistic one; "
        "it measures calls in flight, not wall-clock speedup")


def test_an_underivable_concurrency_does_not_block_the_serial_decision(
        monkeypatch):
    """THE SCOPING LESSON, AND CI TAUGHT IT.

    The first version of this fix made `derive_runner_concurrency()` a hard
    precondition of the guard. The CI-simulated world points the `Aegis module`
    sibling at a nonexistent path, so `verify_or_refuse` raises there — and the
    guard refused outright, failing 15 tests and making a projection impossible
    in any environment without the sibling repo.

    Wrong coupling: the decision is SERIAL and consumes no concurrency value, so
    refusing on an unreadable registration refused on an input the verdict never
    reads. A PAID night still cannot run there (`verify_or_refuse` gates the
    first dollar), so nothing is weakened by letting the projection through.
    """
    from backend.services import market_sessions as MS

    monkeypatch.setattr(N, "derive_runner_concurrency",
                        lambda: (_ for _ in ()).throw(
                            N.ConcurrencyNotDerivable("no prereg. Refusing.")))
    now = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(MS, "next_session_open",
                        lambda _n: datetime(2026, 8, 17, 13, 30,
                                            tzinfo=timezone.utc))
    rep = N.assert_night_fits_before_open(k=5, n_arms=5, now=now)

    assert rep["decision_basis"] in ("MEASURED_DURATION_BOUND",
                                     "MODELLED_SERIAL_PESSIMISTIC")
    assert rep["decision_clock"] == N.CLOCK_RUN_ELAPSED
    assert rep["minutes_of_headroom"] > 0, "the decision must still stand"
    assert rep["concurrency_basis"] == "UNAVAILABLE_PREREG_UNREADABLE"
    assert rep["runner_concurrency_derived"] is None
    # OMITTED, not guessed. A number here would be an assumption wearing a
    # measurement's field name.
    assert rep["projected_minutes_at_runner_concurrency"] is None


def test_a_caller_supplied_concurrency_IS_refused_when_it_cannot_be_checked(
        monkeypatch):
    """The teeth stay where they bite.

    A concurrency the caller asserts and the guard cannot verify is exactly the
    honour-system input that differed five-fold from the runner on Night 1. With
    no registration to check it against, the claim is refused — unlike the
    derived case above, where there is no claim to be wrong about.
    """
    monkeypatch.setattr(N, "derive_runner_concurrency",
                        lambda: (_ for _ in ()).throw(
                            N.ConcurrencyNotDerivable("no prereg. Refusing.")))
    with pytest.raises(N.ConcurrencyNotDerivable, match="cannot be checked"):
        N.assert_night_fits_before_open(k=5, n_arms=5, arm_concurrency=5)


def test_the_decision_basis_and_every_input_basis_are_on_the_report(
        monkeypatch, prereg_readable):
    """Night 1's headroom was a number with no provenance attached.

    Two constants were wrong in opposite directions and cancelled, and the
    projection agreeing with reality proved nothing about either. So each input
    carries where it came from, and a reader can tell a measurement from an
    assumption without going to the source.

    The BELL is stubbed rather than skipped-around. `exchange_calendars` is a
    real dependency and the guard rightly REFUSES without it — but these
    assertions are about the projection's provenance, not about the calendar, and
    an `importorskip` here would silently stop testing the whole point of the
    change on any machine missing the package.
    """
    from backend.services import market_sessions as MS

    now = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    bell = datetime(2026, 8, 17, 13, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(MS, "next_session_open", lambda _now: bell)
    rep = N.assert_night_fits_before_open(k=5, n_arms=5, now=now)

    assert rep["decision_basis"] in ("MEASURED_DURATION_BOUND",
                                     "MODELLED_SERIAL_PESSIMISTIC")
    assert rep["runner_concurrency_derived"] == 5
    assert rep["calls_per_cell_basis"] in (
        "MEASURED_MAX_OVER_COMPLETED_NIGHTS", "DECLARED_EXCEEDS_MEASURED",
        "DECLARED_NO_COMPLETED_NIGHTS")
    assert "calls_per_cell_assumed" in rep
    assert "projected_minutes_at_runner_concurrency" in rep
    # The informational projection must be FASTER than the one decided on, or
    # the report is claiming concurrency makes the night longer.
    assert (rep["projected_minutes_at_runner_concurrency"]
            <= rep["projected_minutes"])
    # And the decision must NOT have used the concurrent projection: it is the
    # max of the modelled serial and the measured-duration bound.
    expected, _b, _s, _d = N.decision_minutes(
        k=5, n_arms=5, calls_per_cell=rep["calls_per_cell_assumed"])
    assert rep["projected_minutes"] == pytest.approx(expected, abs=0.2)
