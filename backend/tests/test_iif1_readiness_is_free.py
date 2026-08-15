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
