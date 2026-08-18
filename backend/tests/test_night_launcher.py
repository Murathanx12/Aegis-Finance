"""The launcher's contract: every outcome leaves a receipt, and 17:39 is not 17:00.

These tests exist for two failures that have already happened in this project
and would happen again the moment a night runs unattended:

  * **A refusing launcher and a dead task produce identical silence.** Prod's
    `0 resolved / 25 overdue` was a guard returning REFUSED on every tick with
    all seven jobs registered, and two independent reviewers read it as a
    sleeping resolver. So the tests below assert a receipt for the REFUSAL
    path at least as hard as for the launch path.

  * **A guard whose input is on the honour system will fool its own author.**
    The launcher's window is re-derived at every firing; nothing here may pass
    because a constant happened to be right on the day it was written. The
    boundary tests therefore compute the expected time from the same
    derivation the launcher uses and then check the verdict FLIPS across it,
    rather than pinning a clock time that would report a defect on a date.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import investigator_night as N
from backend.services import night_launcher as L


# ── fixtures: a receipts world we control ───────────────────────────────────
def _night_receipt(night: str, *, elapsed_min: float = 115.36,
                   assembly_min: float = 18.22, status: str = "ok",
                   sandbox: bool = False) -> dict:
    return {
        "night": night, "status": status, "sandbox": sandbox,
        "elapsed_s": elapsed_min * 60.0,
        "decision_lag_minutes": assembly_min,
        "tickers": [f"T{i}" for i in range(40)],
        "per_arm": {a: {} for a in N.ARMS},
        "calls": 1417,
    }


@pytest.fixture
def receipts(tmp_path):
    d = tmp_path / "nights"
    d.mkdir()
    (d / "2026-08-17.json").write_text(
        json.dumps(_night_receipt("2026-08-17")), encoding="utf-8")
    return d


@pytest.fixture
def launches(tmp_path):
    d = tmp_path / "launches"
    d.mkdir()
    return d


# ── the assembly allowance: the number nobody was reading ───────────────────
def test_assembly_allowance_is_derived_from_receipts(receipts):
    a = L.derive_assembly_allowance_minutes(receipts)
    assert a["basis"] == "MEASURED_WORST_ASSEMBLY_X_DECLARED_FACTOR"
    assert a["worst_minutes"] == pytest.approx(18.22, abs=0.01)
    assert a["value"] == pytest.approx(18.22 * N.DECLARED_DURATION_SAFETY_FACTOR,
                                       abs=0.1)


def test_assembly_allowance_falls_back_to_the_cap_with_no_nights(tmp_path):
    """Zero completed nights is not zero minutes of assembly.

    The conservative direction with nothing measured is the ceiling the night's
    own staleness guard enforces, not an optimistic small number and not a
    refusal — refusing here would make any campaign's first night impossible.
    """
    a = L.derive_assembly_allowance_minutes(tmp_path / "does-not-exist")
    assert a["basis"] == "CAP_NO_COMPLETED_NIGHTS"
    assert a["value"] == float(N.MAX_DECISION_LAG_MINUTES)


def test_assembly_allowance_is_capped_by_the_staleness_guard(tmp_path):
    """A measured allowance above the cap describes a night that cannot exist.

    `assert_decision_time_fresh` refuses any snapshot older than
    MAX_DECISION_LAG_MINUTES, so an assembly longer than that never produces a
    paid run. Deriving 80 minutes of allowance from a 40-minute assembly would
    be arithmetic against the wrong world.
    """
    d = tmp_path / "slow"
    d.mkdir()
    (d / "2026-08-17.json").write_text(
        json.dumps(_night_receipt("2026-08-17", assembly_min=40.0)),
        encoding="utf-8")
    a = L.derive_assembly_allowance_minutes(d)
    assert a["basis"] == "CAP_BINDS"
    assert a["value"] == float(N.MAX_DECISION_LAG_MINUTES)
    assert a["scaled_minutes"] > a["cap"]        # the raw derivation did exceed


def test_sandbox_and_void_nights_do_not_inform_the_allowance(tmp_path):
    """A rehearsal did not discover a faster way to assemble a snapshot."""
    d = tmp_path / "mixed"
    d.mkdir()
    (d / "a.json").write_text(json.dumps(
        _night_receipt("2026-08-10", assembly_min=1.0, sandbox=True)),
        encoding="utf-8")
    (d / "b.json").write_text(json.dumps(
        _night_receipt("2026-08-11", assembly_min=1.0, status="void")),
        encoding="utf-8")
    a = L.derive_assembly_allowance_minutes(d)
    assert a["n_nights"] == 0
    assert a["basis"] == "CAP_NO_COMPLETED_NIGHTS"


# ── THE FINDING: the launch deadline is not the run-start deadline ──────────
def test_latest_safe_launch_is_earlier_than_latest_safe_run_start(receipts,
                                                                  launches):
    """17:39 is a latest-safe-RUN-START. A launcher that fires at it is refused.

    `assert_night_fits_before_open` is called from inside `run_night`, i.e.
    AFTER the snapshot has been assembled. So the launch boundary is the run
    boundary minus the assembly allowance, and quoting the run boundary as a
    launch time hands away the whole allowance.
    """
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    d = rep["derived"]
    run_start = datetime.fromisoformat(d["latest_safe_run_start_utc"])
    launch = datetime.fromisoformat(d["latest_safe_launch_utc"])
    gap = (run_start - launch).total_seconds() / 60.0
    assert gap == pytest.approx(d["assembly_allowance"]["value"], abs=0.6)
    assert launch < run_start


def test_the_verdict_flips_exactly_at_the_derived_launch_boundary(receipts,
                                                                  launches):
    """Computed from the same derivation, not pinned to a clock time.

    A test that hardcoded "17:02" would report a defect on a DATE rather than a
    CHANGE the first time a night's measured duration moved the boundary.
    """
    probe = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=probe, receipts_dir=receipts,
                            launch_dir=launches)
    boundary = datetime.fromisoformat(
        rep["derived"]["latest_safe_launch_utc"])

    before = L.evaluate_launch(now=boundary - timedelta(minutes=2),
                               receipts_dir=receipts, launch_dir=launches)
    after = L.evaluate_launch(now=boundary + timedelta(minutes=2),
                              receipts_dir=receipts, launch_dir=launches)
    codes_before = {r["code"] for r in before["refusals"]}
    codes_after = {r["code"] for r in after["refusals"]}
    assert L.PAST_LATEST_SAFE_LAUNCH not in codes_before
    assert L.PAST_LATEST_SAFE_LAUNCH in codes_after


def test_the_standing_1700_start_is_not_refused_but_is_tight(receipts,
                                                             launches):
    """The reason this number is worth a test rather than a comment.

    Under Night 1's measured assembly the standing 17:00 local start clears the
    derived launch boundary by single-digit minutes — not the ~39 that the
    widely-quoted run-start boundary suggests. If a future night's duration
    pushes this negative the launcher will refuse and say so, which is the
    correct outcome; this test asserts the margin is COMPUTED and reported, not
    that it stays positive forever.
    """
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)   # 17:00 UTC+8
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    margin = rep["derived"]["launch_margin_minutes"]
    assert isinstance(margin, float)
    # The run-start boundary would have claimed ~39 minutes of room here. The
    # honest number is far smaller, and that difference is the finding.
    run_start = datetime.fromisoformat(
        rep["derived"]["latest_safe_run_start_utc"])
    naive_margin = (run_start - now).total_seconds() / 60.0
    assert naive_margin - margin == pytest.approx(
        rep["derived"]["assembly_allowance"]["value"], abs=0.6)
    assert margin < naive_margin


# ── one attempt per night ──────────────────────────────────────────────────
def test_a_night_already_attempted_is_refused(receipts, launches):
    """Including a VOID one. A void night is an attempt: it named a population.

    Counting only successes is how a refusal gets compensated by a retry nobody
    registered, and the two attempts would be indistinguishable from one night
    in the record.
    """
    (receipts / "2026-08-18.json").write_text(
        json.dumps(_night_receipt("2026-08-18", status="void")),
        encoding="utf-8")
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    assert L.ALREADY_ATTEMPTED in {r["code"] for r in rep["refusals"]}


def test_a_torn_receipt_still_counts_as_an_attempt(receipts, launches):
    """Unparseable is not 'no night ran'.

    The filename is the session date and that alone proves an attempt. Reading
    a corrupt receipt as an absence is the exact shape of failure this launcher
    is built to avoid, with money attached.
    """
    (receipts / "2026-08-18.json").write_text("{not json", encoding="utf-8")
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    assert L.ALREADY_ATTEMPTED in {r["code"] for r in rep["refusals"]}


def test_accrual_complete_stops_the_launcher_permanently(tmp_path, launches):
    d = tmp_path / "full"
    d.mkdir()
    for i in range(N.GRADED_NIGHTS_TO_FIRST_LOOK):
        (d / f"2026-01-{i + 1:02d}.json").write_text(
            json.dumps(_night_receipt(f"2026-01-{i + 1:02d}")), encoding="utf-8")
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=d, launch_dir=launches)
    assert L.ACCRUAL_COMPLETE in {r["code"] for r in rep["refusals"]}


# ── the calendar ───────────────────────────────────────────────────────────
def test_a_weekend_is_refused_and_not_made_to_look_safer(receipts, launches):
    """A Saturday's next session is further away, which naively reads as MORE
    headroom. The pre-open lead clause is what stops that inversion."""
    sat = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=sat, receipts_dir=receipts, launch_dir=launches)
    assert not rep["may_launch"]
    assert L.NOT_PREOPEN_WINDOW in {r["code"] for r in rep["refusals"]}


def test_an_uncomputable_stamp_date_refuses_rather_than_passing(receipts,
                                                                launches,
                                                                monkeypatch):
    """A check that did not run is not a check that passed.

    An import or calendar failure here would otherwise DELETE the guard, and
    the launcher would proceed with no idea which session the night was about
    to stamp. Unavailable is not agreement.
    """
    from backend.services import iif1_features as F
    monkeypatch.setattr(F, "resolve_decision_ts",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            RuntimeError("calendar exploded")))
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    assert L.SESSION_DATE_DISAGREEMENT in {r["code"] for r in rep["refusals"]}
    assert "UNAVAILABLE" in rep["derived"]["decision_date_ny"]


def test_the_two_date_clocks_must_agree(receipts, launches):
    """The night stamps its snapshot by the NEW YORK date; the guard forecasts
    the next XNYS open. On a pre-open run those are the same day, and when they
    are not, the receipt would be filed against a session it did not forecast.
    """
    # 03:55 UTC is still the previous evening in New York.
    before_ny_midnight = datetime(2026, 8, 18, 3, 55, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=before_ny_midnight, receipts_dir=receipts,
                            launch_dir=launches)
    assert L.SESSION_DATE_DISAGREEMENT in {r["code"] for r in rep["refusals"]}


# ── receipts: the whole point ──────────────────────────────────────────────
def test_a_refusal_writes_a_receipt(receipts, launches):
    """The mirror rule, mechanised. A refusing launcher must not be silent."""
    sat = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=sat, receipts_dir=receipts, launch_dir=launches)
    path = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                                  launch_dir=launches)
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r["verdict"] == L.VERDICT_REFUSED
    assert r["refusals"] and r["refusals"][0]["code"]
    # Provenance, four-dimensional, same as the night receipts.
    assert "git_commit" in r and "implementation_version" in r
    assert "arm_implementation_fingerprint" in r


def test_a_second_receipt_for_one_date_does_not_overwrite_the_first(receipts,
                                                                    launches):
    """Two launch attempts on one date IS the finding. A writer that overwrote
    would destroy the evidence of the thing it exists to make visible."""
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=now, receipts_dir=receipts, launch_dir=launches)
    p1 = L.write_launch_receipt(rep, verdict=L.VERDICT_REHEARSAL,
                                launch_dir=launches)
    p2 = L.write_launch_receipt(rep, verdict=L.VERDICT_REHEARSAL,
                                launch_dir=launches)
    assert p1 != p2 and p1.exists() and p2.exists()


def test_receipts_that_cannot_be_written_refuse_the_launch(tmp_path):
    """The guard-contract case, asserted here too because it is the launcher's
    single most important refusal: no evidence channel, no unattended run."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(L.LaunchRefused):
        L.evaluate_launch(launch_dir=blocker / "receipts")


# ── acceptance ─────────────────────────────────────────────────────────────
def _write_receipt(launches, session_date: str, verdict=L.VERDICT_REHEARSAL,
                   invocation=L.INVOCATION_SCHEDULED, contradicted=False):
    (launches / f"{session_date}.json").write_text(
        json.dumps({"session_date": session_date, "verdict": verdict,
                    "invocation_mode": invocation,
                    "contradicted": contradicted}),
        encoding="utf-8")


def test_acceptance_needs_three_consecutive_trading_dates(launches):
    """CONSECUTIVE SESSIONS, not calendar days. A launcher that produced
    receipts on Thursday and Friday has skipped nothing over the weekend."""
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)   # Thursday
    for d in ("2026-08-18", "2026-08-19", "2026-08-20"):
        _write_receipt(launches, d)
    acc = L.acceptance_report(launch_dir=launches, now=now)
    assert acc["accepted"] is True
    assert acc["n_consecutive"] == 3


def test_a_gap_breaks_the_streak(launches):
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    for d in ("2026-08-18", "2026-08-20"):          # 08-19 missing
        _write_receipt(launches, d)
    acc = L.acceptance_report(launch_dir=launches, now=now)
    assert acc["accepted"] is False
    assert acc["n_consecutive"] == 1


def test_refusal_receipts_count_toward_acceptance(launches):
    """What is being accepted is that the launcher WAKES UP AND DECIDES.

    A refusal delivered on time is exactly as much evidence of that as a
    launch — and requiring three LAUNCHES would make acceptance impossible
    across any holiday or any night the guards legitimately refuse.
    """
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    for d in ("2026-08-18", "2026-08-19", "2026-08-20"):
        _write_receipt(launches, d, verdict=L.VERDICT_REFUSED)
    assert L.acceptance_report(launch_dir=launches, now=now)["accepted"]


def test_hand_run_rehearsals_do_not_count_toward_acceptance(launches):
    """THE CLAUSE THAT KEEPS ACCEPTANCE FROM BEING FAKEABLE.

    What is under test is not the code path — it is that NOBODY HAD TO BE
    THERE. Three afternoons of running the command by hand is evidence of the
    first and none of the second, and counting it would let the honour system
    this launcher exists to remove back in through its own acceptance test.
    """
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    for d in ("2026-08-18", "2026-08-19", "2026-08-20"):
        _write_receipt(launches, d, invocation=L.INVOCATION_MANUAL)
    acc = L.acceptance_report(launch_dir=launches, now=now)
    assert acc["accepted"] is False
    assert acc["n_receipts_total"] == 3 and acc["n_receipts_counted"] == 0
    # Excluded, and SAID SO. A count that shrank invisibly is the denominator
    # failure wearing a different hat.
    assert len(acc["excluded"]) == 3
    assert all("manual" in e["why"] for e in acc["excluded"])


def test_an_undeclared_receipt_does_not_count(launches):
    """Silence is not a declaration of `scheduled`.

    Reading a missing field as the permissive value is how `()` came to stand
    in for "no parent declared" and cost R13e a slice.
    """
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    (launches / "2026-08-20.json").write_text(
        json.dumps({"session_date": "2026-08-20", "verdict": "REFUSED"}),
        encoding="utf-8")
    acc = L.acceptance_report(launch_dir=launches, now=now)
    assert acc["n_receipts_counted"] == 0
    assert acc["excluded"][0]["why"].endswith("undeclared")


def test_a_contradicted_receipt_does_not_count(launches):
    """`scheduled` claimed while stdin was a terminal. Declared vs derived, and
    the derived observation wins — same pattern as version vs fingerprint."""
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    for d in ("2026-08-18", "2026-08-19"):
        _write_receipt(launches, d)
    _write_receipt(launches, "2026-08-20", contradicted=True)
    acc = L.acceptance_report(launch_dir=launches, now=now)
    assert acc["n_consecutive"] == 0, "the contradicted date breaks the streak"
    assert any("terminal" in e["why"] for e in acc["excluded"])


def test_observe_invocation_never_records_unknown_as_not_a_terminal(monkeypatch):
    """`stdin_isatty` is None when it could not be determined, never False.

    "We did not look" reading the same as "we looked and there was no console"
    is the `git_dirty` lesson, and here it would launder a manual run into a
    scheduled one.
    """
    import sys

    class _Broken:
        def isatty(self):
            raise OSError("no stream")

    monkeypatch.setattr(sys, "stdin", _Broken())
    obs = L.observe_invocation(L.INVOCATION_SCHEDULED)
    assert obs["stdin_isatty"] is None
    assert obs["contradicted"] is False    # unknown is not a contradiction...

    class _Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", _Tty())
    assert L.observe_invocation(L.INVOCATION_SCHEDULED)["contradicted"] is True
    assert L.observe_invocation(L.INVOCATION_MANUAL)["contradicted"] is False


def test_no_receipts_is_not_accepted(launches):
    acc = L.acceptance_report(launch_dir=launches,
                              now=datetime(2026, 8, 20, 9, 0,
                                           tzinfo=timezone.utc))
    assert acc["accepted"] is False and acc["n_consecutive"] == 0


def test_acceptance_never_consults_a_running_flag():
    """The one thing acceptance must not be. Asserted structurally: the source
    of `acceptance_report` may not mention scheduler liveness at all."""
    import inspect
    src = inspect.getsource(L.acceptance_report)
    for forbidden in ("scheduler", ".running", "is_alive"):
        assert forbidden not in src.split('"""')[2], (
            f"acceptance_report's body references {forbidden!r} — receipts "
            f"prove a job ran; a liveness flag proves nothing (prod had all 7 "
            f"jobs registered and running while every tick refused)")


# ── the launch manifest and equivalence pinning (Order 16 §1) ──────────────
def test_the_manifest_carries_the_bytes_that_define_the_night():
    man = L.launch_manifest()
    for f in ("prereg_hash", "module_hashes", "implementation_version",
              "arm_implementation_fingerprint", "git_commit", "git_dirty",
              "frozen_surface"):
        assert f in man, f"manifest is missing {f}"
    assert set(man["module_hashes"]) == set(L.NIGHT_MODULES)


def _manifest(**overrides) -> dict:
    """A COMPLETE synthetic manifest, built rather than captured.

    The first version of these tests called `launch_manifest()` and mutated the
    result. That passed on this machine and failed all four in the CI-simulated
    world, because CI has no `Aegis module` sibling, so `prereg_hash` and
    `frozen_surface` come back UNAVAILABLE and equivalence correctly refuses
    before it ever reaches the field under test. The code was right; the tests
    were measuring a different world — the exact defect `ci_env_sim` exists for,
    reproduced inside tests written the same afternoon.

    What is under test here is the COMPARISON, so the inputs are constructed.
    The real `launch_manifest()` is exercised separately, in a way that holds in
    both worlds.
    """
    man = {
        "manifest_version": 1,
        "prereg_hash": "441d098c1f8074ea",
        "frozen_surface": {"ARMS": ["A_snapshot", "B_tools"],
                           "TRIGGERS_PER_NIGHT": 40},
        "module_hashes": {m: f"hash{i:02d}" for i, m in
                          enumerate(L.NIGHT_MODULES)},
        "implementation_version": 2,
        "arm_implementation_fingerprint": "abc123def456",
        "git_commit": "a" * 40,
        "git_dirty": False,
    }
    man.update(overrides)
    return man


def test_identical_manifests_are_equivalent():
    man = _manifest()
    assert L.assert_invocation_equivalent(man, _manifest())["equivalent"] is True


def test_a_changed_module_breaks_the_pinning():
    """The claim a rehearsal makes, made checkable. Main changes all day; the
    rehearsal only licenses the launch if the two run the same experiment."""
    a = _manifest()
    b = json.loads(json.dumps(a))
    b["module_hashes"]["backend.services.investigator_agent"] = "deadbeefdeadbeef"
    with pytest.raises(L.LaunchRefused, match="NOT the one that was rehearsed"):
        L.assert_invocation_equivalent(a, b)


def test_a_changed_frozen_surface_breaks_the_pinning():
    a = _manifest()
    b = _manifest(frozen_surface={"ARMS": ["A_snapshot"],
                                  "TRIGGERS_PER_NIGHT": 40})
    with pytest.raises(L.LaunchRefused, match="frozen_surface"):
        L.assert_invocation_equivalent(a, b)


def test_a_changed_commit_alone_does_not_break_the_pinning():
    """A docs-only commit moves the SHA and changes nothing that runs. Refusing
    on it would train the operator to re-rehearse for no reason, which is how a
    guard gets routed around. The module hashes carry the real claim."""
    a = _manifest()
    b = _manifest(git_commit="0" * 40)
    assert L.assert_invocation_equivalent(a, b)["equivalent"] is True


def test_two_unavailable_hashes_are_not_agreement():
    """The failure this whole manifest exists to catch: a missing input passing
    for equality because both sides are equally missing."""
    a = _manifest(prereg_hash="UNAVAILABLE: FileNotFoundError: nope")
    b = _manifest(prereg_hash="UNAVAILABLE: FileNotFoundError: nope")
    with pytest.raises(L.LaunchRefused, match="missing input passing for"):
        L.assert_invocation_equivalent(a, b)


def test_an_unhashable_module_refuses_even_when_both_sides_match():
    hashes = dict(_manifest()["module_hashes"])
    hashes["backend.services.iif1_run"] = "UNAVAILABLE: OSError"
    a, b = _manifest(module_hashes=hashes), _manifest(module_hashes=dict(hashes))
    with pytest.raises(L.LaunchRefused, match="could not hash"):
        L.assert_invocation_equivalent(a, b)


def test_the_real_manifest_pins_itself_or_refuses_and_never_in_between():
    """Exercised on the REAL manifest, and it holds in both worlds.

    With the `Aegis module` sibling present the manifest is complete and pins
    itself. Without it — CI, the prod image, any context that cannot read the
    registered rule — `prereg_hash` is UNAVAILABLE and equivalence REFUSES.
    Both are correct and they are the only two outcomes: a context that cannot
    read the registration cannot certify that a launch runs it.
    """
    man = L.launch_manifest()
    readable = not str(man["prereg_hash"]).startswith("UNAVAILABLE")
    if readable:
        assert L.assert_invocation_equivalent(man, L.launch_manifest())[
            "equivalent"] is True
    else:
        with pytest.raises(L.LaunchRefused, match="missing input passing for"):
            L.assert_invocation_equivalent(man, L.launch_manifest())


def test_every_receipt_carries_a_manifest_including_refusals(receipts, launches):
    """A manifest attached only to launches would leave the REHEARSAL — the one
    receipt whose entire purpose is to pin a later launch — with nothing to
    compare against."""
    sat = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
    rep = L.evaluate_launch(now=sat, receipts_dir=receipts, launch_dir=launches)
    p = L.write_launch_receipt(rep, verdict=L.VERDICT_REFUSED,
                               launch_dir=launches)
    r = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(r["launch_manifest"], dict)
    assert "module_hashes" in r["launch_manifest"]


def test_the_latest_rehearsal_manifest_is_found_and_refusals_are_not(launches):
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    (launches / "2026-08-19.json").write_text(json.dumps(
        {"session_date": "2026-08-19", "verdict": L.VERDICT_REFUSED,
         "written_at_utc": "2026-08-19T09:00:00+00:00",
         "launch_manifest": {"prereg_hash": "refusal"}}), encoding="utf-8")
    assert L.latest_rehearsal_manifest(launches) is None, (
        "a REFUSED receipt must not be mistaken for a rehearsal that pins a "
        "launch — the night it describes never ran")
    (launches / "2026-08-20.json").write_text(json.dumps(
        {"session_date": "2026-08-20", "verdict": L.VERDICT_REHEARSAL,
         "written_at_utc": "2026-08-20T09:00:00+00:00",
         "launch_manifest": {"prereg_hash": "abc"}}), encoding="utf-8")
    assert L.latest_rehearsal_manifest(launches) == {"prereg_hash": "abc"}
    assert now  # fixture time is not consulted; recency comes from the receipt


# ── arming is attended ─────────────────────────────────────────────────────
def test_arming_is_env_gated_and_off_by_default(monkeypatch):
    monkeypatch.delenv("AEGIS_IIF1_LAUNCHER_ARMED", raising=False)
    assert L.is_armed() is False
    monkeypatch.setenv("AEGIS_IIF1_LAUNCHER_ARMED", "true")
    assert L.is_armed() is False, "only the literal '1' arms it"
    monkeypatch.setenv("AEGIS_IIF1_LAUNCHER_ARMED", "1")
    assert L.is_armed() is True
