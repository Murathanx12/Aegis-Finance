"""P2 — does `decision_ts` mean what the trial grades against?

THE QUESTION, AND WHY IT OUTRANKED PARALLELISM
==============================================
Snapshot assembly takes ~13-20 minutes and `decision_ts` is stamped when it
STARTS. If some observations are retrieved after that instant and are not cut to
it, the trial compares timestamp LABELS rather than information sets — a
point-in-time defect sitting underneath the experiment. Concurrency changes
exactly these timings, so this had to be answered first.

WHAT WAS MEASURED, NOT ASSUMED (2026-08-14 production snapshot, 1,092 rows)
==========================================================================
    decision_ts        2026-08-14T07:50:25-04:00   (11:50:25 UTC)
    fetched_at         11:50:25 UTC -> 12:03:54 UTC   -- 13.5 minutes AFTER
    observed_at        ONE distinct value: decision_ts, on all 1,092 rows
    published_at       price/volume    max 2026-08-13      (last bar: cut)
                       filing_within_2d max 08-14 03:43 ET (same morning: cut)
                       earnings_within_5d max 2026-11-13   (three months out)

**No point-in-time defect.** The content genuinely is cut: prices stop at the
last completed bar, filings at acceptance times before the decision. Retrieval
running past `decision_ts` is safe because of that cut.

**But nothing in the snapshot proved it, and one field would have lied.**
`observed_at` is ASSIGNED the decision time on every row, so the field that
should evidence the cut is a copy of the thing it is supposed to check — an
audit trail that confirms itself. And `earnings_within_5d` stored a SCHEDULED
FUTURE earnings date in `published_at`, so the one field that could prove the
cut reported a maximum three months after the decision. A cutoff check written
against it would have refused 170 rows of a snapshot with nothing wrong with it,
on its first run, and been switched off by lunchtime.

Fixed: scheduled events move to `event_at`; the snapshot carries
`snapshot_started_at` / `snapshot_frozen_at` / `information_cutoff_at`; and
`assert_snapshot_pit_safe` runs at the freeze, before the immutable file exists.
"""

from __future__ import annotations

import json

import pytest

from backend.services import iif1_features as F


def _prov(published=None, event=None, observed="2026-08-14T07:50:25-04:00"):
    return {"AAPL": {"price": {"value": 1.0, "status": F.OK_DATA,
                               "source": "yf", "observed_at": observed,
                               "fetched_at": "2026-08-14T12:03:54+00:00",
                               "published_at": published, "event_at": event}}}


def _snap(**over):
    s = {"trial": F.TRIAL,
         "decision_ts": "2026-08-14T07:50:25-04:00",
         "information_cutoff_at": "2026-08-14T07:50:25-04:00",
         "snapshot_started_at": "2026-08-14T11:50:25+00:00",
         "snapshot_frozen_at": "2026-08-14T12:03:58+00:00",
         "provenance": _prov(published="2026-08-13T00:00:00-04:00"),
         "features": {}, "status_counts": {}, "unavailable": {},
         "n_universe": 1, "n_with_any_feature": 1, "n_fully_unavailable": 0}
    s.update(over)
    return s


def test_a_snapshot_whose_content_predates_the_decision_passes():
    rep = F.assert_snapshot_pit_safe(_snap())
    assert rep["max_input_published_at"] == "2026-08-13T00:00:00-04:00"
    assert rep["n_checked"] == 1


def test_information_dated_AFTER_the_decision_instant_is_refused():
    """The actual defect this exists to catch."""
    bad = _snap(provenance=_prov(published="2026-08-14T09:15:00-04:00"))
    with pytest.raises(F.PointInTimeViolation, match="NEWER than the decision"):
        F.assert_snapshot_pit_safe(bad)


def test_a_SCHEDULED_FUTURE_event_does_NOT_trip_the_check():
    """The regression that would have switched the check off on day one.

    A next-earnings date three months out is not lookahead — it is a calendar
    entry that was public at the decision. It lives in `event_at` now, and a
    cutoff check that refused it would have been deleted rather than believed.
    """
    ok = _snap(provenance=_prov(published="2026-08-13T00:00:00-04:00",
                                event="2026-11-13"))
    assert F.assert_snapshot_pit_safe(ok)["n_checked"] == 1


def test_the_check_does_NOT_read_fetched_at():
    """Assembly legitimately runs for ~20 minutes past the decision instant.

    Every `fetched_at` in the real snapshot is later than `decision_ts`. A check
    on retrieval time would refuse every genuine snapshot, which is a check that
    lasts exactly one morning.
    """
    s = _snap()
    s["provenance"]["AAPL"]["price"]["fetched_at"] = "2027-01-01T00:00:00+00:00"
    assert F.assert_snapshot_pit_safe(s)      # unbothered, on purpose


def test_the_check_cannot_be_satisfied_by_observed_at():
    """`observed_at` is the decision time on every row BY CONSTRUCTION.

    A check reading it would pass on a snapshot that had never cut anything —
    the self-confirming audit trail this replaces.
    """
    bad = _snap(provenance=_prov(published="2026-08-20T00:00:00-04:00",
                                 observed="2026-08-14T07:50:25-04:00"))
    with pytest.raises(F.PointInTimeViolation):
        F.assert_snapshot_pit_safe(bad)


def test_a_snapshot_that_names_no_cutoff_cannot_be_certified():
    s = _snap()
    s.pop("information_cutoff_at"), s.pop("decision_ts")
    with pytest.raises(F.PointInTimeViolation, match="names no information"):
        F.assert_snapshot_pit_safe(s)


def test_the_freeze_refuses_BEFORE_the_immutable_file_exists(tmp_path,
                                                            monkeypatch):
    """A frozen snapshot cannot be corrected, only argued about."""
    p = tmp_path / "2026-08-14.json"
    monkeypatch.setattr(F, "snapshot_path", lambda ts, sandbox=False: p)
    bad = _snap(provenance=_prov(published="2026-08-14T09:15:00-04:00"))
    with pytest.raises(F.PointInTimeViolation):
        F.write_snapshot(bad)
    assert not p.exists(), "a violating snapshot was written to disk anyway"


def test_a_clean_snapshot_still_freezes(tmp_path, monkeypatch):
    p = tmp_path / "2026-08-14.json"
    monkeypatch.setattr(F, "snapshot_path", lambda ts, sandbox=False: p)
    F.write_snapshot(_snap())
    assert json.loads(p.read_text(encoding="utf-8"))["information_cutoff_at"]


def test_assemble_records_the_three_instants_separately(monkeypatch):
    """start / frozen / cutoff. One number cannot describe all three."""
    monkeypatch.setattr(F, "default_universe", lambda: ["AAPL"])
    monkeypatch.setattr(
        F, "assemble_ticker",
        lambda t, ts: {"price": F.FeatureValue(
            1.0, F.OK_DATA, "yf", ts.isoformat(), F._now_iso(),
            published_at="2026-08-13T00:00:00-04:00")})
    snap = F.assemble(as_of="2026-08-14T07:50:00")
    for k in ("snapshot_started_at", "snapshot_frozen_at",
              "information_cutoff_at", "max_input_published_at"):
        assert snap.get(k), k
    assert snap["information_cutoff_at"] == snap["decision_ts"]
    assert F.assert_snapshot_pit_safe(snap)


def test_the_earnings_date_lands_in_event_at_and_not_published_at(monkeypatch):
    """The field that made the only usable cutoff check unusable."""
    import backend.services.earnings_intelligence as EI
    monkeypatch.setattr(EI, "get_earnings_summary",
                        lambda t: {"status": "OK",
                                   "next_earnings_date": "2026-11-13"})
    fv = F._earnings_within("AAPL", F.resolve_decision_ts("2026-08-14T07:50:00"),
                            "2026-08-14T12:00:00+00:00")
    assert fv.event_at == "2026-11-13"
    assert fv.published_at is None
