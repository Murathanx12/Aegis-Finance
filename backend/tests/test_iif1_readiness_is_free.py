"""`--readiness` spends no money AND no snapshot slot.

THE TRAP THIS CLOSES (found 2026-08-15 by reading the path before running it)
============================================================================
The readiness report is documented as "spends nothing", and it spends no money.
But `assemble_and_freeze` wrote a PRODUCTION snapshot as a side effect, and:

  * the decision timestamp is `now`;
  * the snapshot is keyed by night date;
  * `write_snapshot` refuses to overwrite, correctly — a rebuilt snapshot would
    substitute today's corrected calendar and adjusted prices for what the
    model actually saw.

So running the safe-by-documentation command at 05:20 UTC, ahead of a pre-open
night at 11:50 UTC, would freeze that night's point-in-time record six and a
half hours early. The night would then fail the 45-minute decision-lag guard
and REFUSE — the identical failure that voided the previous attempt, arriving
through the one command whose purpose is to make the attempt safe.

The order said "run `--readiness` first". It did not say when, and the only
answer that worked was "within 45 minutes of the night". That is a guard living
in an operator's memory, which is where guards go to fail. It now lives next to
the irreversible write.
"""

from __future__ import annotations

import pytest


def test_readiness_assembles_without_claiming_the_nights_snapshot(monkeypatch):
    from backend.services import iif1_features as F
    from backend.services import iif1_run as R

    wrote = []
    monkeypatch.setattr(F, "assemble",
                        lambda ts, universe=None: {
                            "decision_ts": str(ts), "decision_ts_tz": "NY",
                            "n_universe": 3, "status_counts": {"OK_DATA": 3},
                            "n_with_any_feature": 3, "n_fully_unavailable": 0,
                            "unavailable": {}, "features": {}})
    monkeypatch.setattr(F, "write_snapshot",
                        lambda *a, **k: wrote.append(1) or "path")

    snap = R.assemble_and_freeze(None, freeze=False)

    assert wrote == [], (
        "the readiness path wrote a snapshot — that consumes the night's one "
        "point-in-time slot and guarantees a staleness refusal at pre-open")
    assert snap["n_universe"] == 3      # and it still produced a usable report


def test_the_default_still_freezes_because_a_real_night_must():
    """The fix must not disarm the freeze it exists to protect."""
    import inspect
    from backend.services import iif1_run as R
    sig = inspect.signature(R.assemble_and_freeze)
    assert sig.parameters["freeze"].default is True


def test_the_cli_passes_freeze_false_exactly_when_readiness_is_asked(monkeypatch):
    """Wiring, not intent — the flag has to reach the call that writes."""
    import inspect

    from backend.services import iif1_run as R
    src = inspect.getsource(R.main)
    assert "freeze=not a.readiness" in src, (
        "the readiness flag no longer reaches assemble_and_freeze; the "
        "docstring would then describe a guard that is not wired")


def test_the_report_does_not_tell_you_to_reuse_a_snapshot_it_never_wrote():
    """A stale instruction is a broken instruction.

    The report ended with `--reuse-snapshot`, which was correct while readiness
    froze a snapshot as a side effect. Removing the freeze without changing the
    line would have handed a FileNotFoundError to whoever typed the last line
    of a report that had just printed READY — the same half-a-fix shape as
    writing receipts nowhere anything could read them.
    """
    import inspect

    from backend.services import iif1_run as R
    src = inspect.getsource(R.readiness_report)
    # The PRINTED command, not the prose around it — the docstring and the
    # comment both mention the removed flag on purpose.
    printed = [ln for ln in src.splitlines()
               if "iif1_run{stamp}" in ln or "iif1_run --" in ln]
    assert printed, "the report no longer prints a command at all"
    assert not any("--reuse-snapshot" in ln for ln in printed), printed
    assert "ASSEMBLES A FRESH SNAPSHOT" in src


def _snap(**over):
    s = {"decision_ts": "2026-08-15T07:50:00-04:00",
         "decision_ts_tz": "America/New_York", "n_universe": 182,
         "status_counts": {"OK_DATA": 1073, "OK_EMPTY": 3, "UNAVAILABLE": 16},
         "n_with_any_feature": 182, "n_fully_unavailable": 0,
         "unavailable": {"AAA": ["price"]}, "assembly_seconds": 1187.4,
         "features": {}, "sandbox": False}
    s.update(over)
    return s


def _sel(**over):
    s = {"tickers": ["WMT", "AMD"], "n_selected": 40, "n_eligible": 179,
         "n_scored": 182, "n_excluded": 3,
         "selected": [{"ticker": "WMT", "score": 4.08}], "excluded": []}
    s.update(over)
    return s


@pytest.fixture
def prereg_readable(monkeypatch):
    """Make the frozen pre-registration readable WITHOUT the sibling repo.

    WHY THIS FIXTURE EXISTS — a CI break that this file caused, 2026-08-15
    ====================================================================
    `readiness_report` calls `iif1_prereg.verify_or_refuse()`, which reads
    `../Aegis module/scripts/iif1_config.py` and **deliberately ignores**
    `AEGIS_IIF1_PREREG_ABSENT_OK`. That is correct: a context that cannot read
    the registered rule must not be able to wave itself through.

    But CI checks out ONE repo, so the sibling is genuinely absent there, the
    report correctly reports a blocker, and it returns 1. The smoke test below
    asserted 0 — true on this machine, false everywhere else. It went green
    locally on 4,153 tests and turned CI red for three commits, which stopped
    every deploy: prod sat on `5d7ae15` while `a355fa6` was reported as shipped.

    The lesson is not "mock the dependency". It is that **a test whose result
    depends on what else happens to be checked out is not a test of the code**,
    and the signal it corrupts is the one gating production. So both worlds are
    now pinned explicitly: readable → READY here, absent → NOT READY below.
    """
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", P.runtime_surface)
    return P


def test_the_report_runs_to_its_last_line_without_a_20_minute_assembly(
        capsys, prereg_readable):
    """A runtime smoke test of the block that only runs after the slow part.

    The other tests here assert on the report's SOURCE. That is weaker than it
    looks: a source string cannot tell you the final block executes. This one
    calls it, and it caught nothing only because a hand-run had already caught
    the fixture's missing keys — the code itself was fine. Keeping it means the
    next edit to that block is checked in under a second instead of after
    twenty minutes of assembly.
    """
    from backend.services import iif1_run as R
    rc = R.readiness_report(_snap(), _sel(), as_of=None, balance_usd=57.12)
    out = capsys.readouterr().out
    assert rc == 0
    assert "READY." in out
    # The corrected command, and NOT the one that points at nothing.
    assert "python -m backend.services.iif1_run\n" in out
    assert "--reuse-snapshot" not in out
    # The assembly budget, stated where the operator decides when to start.
    assert "20 minutes, leaving roughly 25 of the 45-minute allowance" in out
    # And the topped-up balance, not the stale one.
    assert "$57.12" in out and "$1.428/night" in out


def test_a_report_that_is_NOT_ready_says_so_and_does_not_print_the_command(
        capsys, prereg_readable):
    """The last line is an instruction. It must not appear under a refusal.

    The fixture matters here too. Without it this test passed in CI for the
    wrong reason — the missing sibling blocked the report, so the assertion
    never exercised the trigger-pool blocker it names.
    """
    from backend.services import iif1_run as R
    # No reachable triggers: the night cannot fill its registered cell count.
    rc = R.readiness_report(_snap(), _sel(n_selected=0, n_eligible=0),
                            as_of=None, balance_usd=57.12)
    out = capsys.readouterr().out
    assert rc == 1
    assert "NOT READY" in out
    assert "SHORT OF K" in out, (
        "the refusal must come from the empty trigger pool this test set up, "
        "not from some other blocker that happens to also be present")
    assert "python -m backend.services.iif1_run\n" not in out


def test_a_checkout_that_cannot_READ_the_frozen_rule_is_NOT_READY(
        capsys, monkeypatch):
    """CI's actual world, pinned deliberately instead of discovered in red.

    This is the behaviour that broke the build, and it is the CORRECT
    behaviour — `verify_or_refuse` ignores the opt-out variable on purpose, so
    a checkout without the `Aegis module` sibling cannot certify a night it has
    no way to check. Asserting it here means the next person who "fixes" CI by
    loosening the guard breaks a test that explains why they must not.
    """
    import pathlib

    from backend.services import iif1_prereg as P
    from backend.services import iif1_run as R
    monkeypatch.setattr(P, "CONFIG_PATH",
                        pathlib.Path("/nonexistent/iif1_config.py"))
    monkeypatch.setenv(P.OPT_OUT_ENV, "1")      # must NOT rescue a paying night

    rc = R.readiness_report(_snap(), _sel(), as_of=None, balance_usd=57.12)
    out = capsys.readouterr().out
    assert rc == 1
    assert "frozen pre-registration unreadable" in out
    assert "python -m backend.services.iif1_run\n" not in out


def test_the_assembly_note_cannot_crash_the_last_line_of_the_report():
    """It runs AFTER ~20 minutes of assembly, on the report's final line.

    Added in the same change that removed the freeze, so it did not exist the
    last time the readiness report ran for real. A throw here would kill the
    report at its end — having already spent the twenty minutes, and having
    already printed READY — which is the most expensive place in the whole
    script to raise.
    """
    from backend.services import iif1_run as R

    # Recorded, missing, zero, and absurd. None may raise.
    assert "20 minutes" in R._assembly_note({"assembly_seconds": 1200.0})
    assert "unrecorded" in R._assembly_note({})
    assert "unrecorded" in R._assembly_note({"assembly_seconds": 0})
    # An assembly longer than the whole allowance must clamp at zero remaining
    # rather than print a negative budget.
    long_note = R._assembly_note({"assembly_seconds": 60 * 60 * 3})
    assert "0 of the" in long_note


def test_the_receipt_records_how_stale_the_snapshot_was_when_the_night_ENDED():
    """The guard checks the start. The night keeps running afterwards.

    `assert_decision_time_fresh` fires once, before the first paid call, and
    that is right — aborting halfway buys contaminated forecasts AND loses the
    night. But it means a night that starts 30 minutes stale and runs for 60
    ends with its tool arms reading a world 90 minutes newer than the timestamp
    their forecasts are graded from, while the receipt reported 30.

    The exposure is DIFFERENTIAL — the tool arms get it, the snapshot arm does
    not — which is the same bias structure that voided Night 1. So it is
    measured. Nothing depends on the number yet; it has to exist before anyone
    can argue about what value is acceptable.
    """
    from datetime import datetime, timedelta, timezone

    from backend.services import investigator_night as N
    from backend.tests.test_investigator_night import (_feats, good_llm,
                                                       no_tools)

    started = datetime.now(timezone.utc) - timedelta(minutes=7)
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True,
                      decision_ts=started.isoformat())

    assert res.decision_lag_minutes_at_end is not None
    assert 6.5 <= res.decision_lag_minutes_at_end <= 10.0
    assert "decision_lag_minutes_at_end" in res.as_dict()


def test_a_frozen_snapshot_still_refuses_to_be_rebuilt(tmp_path, monkeypatch):
    """The immutability rule is what makes the slot single-use. Pin it."""
    import json

    from backend.services import iif1_features as F

    snap = {"decision_ts": "2026-08-15T07:50:00-04:00"}
    p = tmp_path / "2026-08-15.json"
    p.write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(F, "snapshot_path", lambda ts, sandbox=False: p)

    with pytest.raises(FileExistsError, match="not rebuilt"):
        F.write_snapshot(snap)
