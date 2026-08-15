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
