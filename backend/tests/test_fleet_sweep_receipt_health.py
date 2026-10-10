"""The scheduled late-fill sweep is judged by its newest durable receipt."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import system_health as SH
from backend.services import task_receipts as TR


NAME = "AegisFleetProtectSweep"
TASK = {"TaskName": "\\" + NAME, "Scheduled Task State": "Enabled", "Last Run Time": "-"}


def _ctx(tmp_path, now):
    root = tmp_path / "optimus"
    root.mkdir(parents=True, exist_ok=True)
    return SH.ProbeCtx(optimus_dir=root, now=now, repo=tmp_path,
                       prev_state={}, paths={}, run=lambda *_: (None, "unused"),
                       pid_cmdline=lambda _: None)


def _receipt(ctx, at, status="ALREADY_COVERED", *, live=True, roles=None, warnings=None, suffix=""):
    folder = ctx.optimus_dir / "paper_accounts/fleet_manager/sweeps"
    folder.mkdir(parents=True, exist_ok=True)
    data = {"schema": "fleet_protect_sweep/1", "started_utc": at.isoformat(),
            "finished_utc": at.isoformat(), "status": status, "live_flag": live,
            "roles": roles if roles is not None else [
                {"role": "hack1", "status": "ALREADY_COVERED", "candidates": 0,
                 "held_symbols": 0}],
            "history_warnings": warnings if warnings is not None else [],
            "requests_upper_bound": 1, "http_requests": 1}
    path = folder / f"sweep_{at:%Y%m%dT%H%M%S%fZ}{suffix}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _change(path: Path, **changes):
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def _row(monkeypatch, ctx, task=TASK):
    monkeypatch.setattr(SH, "_schtasks", lambda _: {NAME: task} if task else {})
    return SH.p_scheduled_tasks(ctx)[NAME]


def _session_day(year, month, day):
    d = datetime(year, month, day, tzinfo=timezone.utc).date()
    assert SH._sessions(d, d)[0] == [d]
    return d


@pytest.mark.parametrize("status,live,expect", [
    ("ALREADY_COVERED", True, "ALIVE_PROGRESSING"),
    ("ALREADY_COVERED", False, "DEGRADED"),
    ("DRY_PLAN", False, "DEGRADED"),
    ("INCOMPLETE", True, "DEGRADED"),
    ("REFUSED", True, "REFUSED"),
    ("REFUSED", False, "REFUSED"),
])
def test_real_task_receipt_to_health_row(tmp_path, monkeypatch, status, live, expect):
    _session_day(2026, 10, 9)
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, now - timedelta(minutes=5), status, live=live)
    row = _row(monkeypatch, ctx)
    assert row.state == expect, row.detail
    assert row.proof.endswith(".json")


def test_newest_refusal_or_corrupt_receipt_cannot_hide_behind_prior_success(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, now - timedelta(minutes=10))
    _receipt(ctx, now - timedelta(minutes=2), "REFUSED")
    assert _row(monkeypatch, ctx).state == "REFUSED"
    p = next((ctx.optimus_dir / "paper_accounts/fleet_manager/sweeps").glob("*155800*.json"))
    p.write_text("{", encoding="utf-8")
    assert _row(monkeypatch, ctx).state not in TR.ALIVE_STATES


def test_exact_window_due_and_closed_session_boundaries(tmp_path, monkeypatch):
    friday = _session_day(2026, 10, 9)
    assert friday.isoformat() == "2026-10-09"
    start = datetime(2026, 10, 9, 15, 5, tzinfo=timezone.utc)
    allowed = TR.allowed_age_s(NAME, TR.TASK_RECEIPT[NAME], start, start)
    assert allowed == 15 * 60 * (1 + SH.GRACE)
    ctx = _ctx(tmp_path, start + timedelta(seconds=allowed))
    _receipt(ctx, start)
    assert _row(monkeypatch, ctx).state == "ALIVE_PROGRESSING"
    ctx.now += timedelta(seconds=1)
    assert _row(monkeypatch, ctx).state == "STALE"
    # A late receipt proves the completed Friday window; weekend/closed hours are idle.
    end = datetime(2026, 10, 9, 19, 5, tzinfo=timezone.utc)
    _receipt(ctx, end)
    ctx.now = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)
    assert _row(monkeypatch, ctx).state == "ALIVE_IDLE_EXPECTED"
    ctx.now = datetime(2026, 10, 12, 15, 5, tzinfo=timezone.utc)
    assert _row(monkeypatch, ctx).state == "ALIVE_IDLE_EXPECTED"
    ctx.now += timedelta(seconds=allowed + 1)
    assert _row(monkeypatch, ctx).state == "STALE"
    ctx.now = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
    assert _row(monkeypatch, ctx).state == "STALE"  # missed Monday's whole window


def test_uninstalled_sweep_is_explicit_not_healthy(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, datetime(2026, 10, 9, 16, tzinfo=timezone.utc))
    row = _row(monkeypatch, ctx, None)
    assert row.state == "DEAD"
    _receipt(ctx, ctx.now - timedelta(minutes=1), "REFUSED", live=False)
    row = _row(monkeypatch, ctx, None)
    assert row.state == "REFUSED" and "NO scheduled task" in row.detail


def test_prior_partial_window_stays_stale_and_holiday_does_not_create_due_run(tmp_path, monkeypatch):
    assert not SH._sessions(datetime(2026, 11, 26, tzinfo=timezone.utc).date(),
                            datetime(2026, 11, 26, tzinfo=timezone.utc).date())[0]
    now = datetime(2026, 11, 26, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, datetime(2026, 11, 25, 15, 10, tzinfo=timezone.utc))
    assert _row(monkeypatch, ctx).state == "STALE"  # most of Wednesday's repeats missing
    _receipt(ctx, datetime(2026, 11, 25, 19, 5, tzinfo=timezone.utc))
    assert _row(monkeypatch, ctx).state == "ALIVE_IDLE_EXPECTED"


def test_unverified_already_covered_payload_does_not_claim_coverage(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, now - timedelta(minutes=1), roles=[
        {"role": "hack1", "status": "CANDIDATE", "candidates": 1, "held_symbols": 1}])
    assert _row(monkeypatch, ctx).state == "DEGRADED"


def test_verified_no_action_with_unresolved_history_needs_attention(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, now - timedelta(minutes=1), warnings=[
        {"role": "hack1", "symbol": "TEST", "code": "UNRESOLVED_PRIOR_STOP_INTENT",
         "identity_sha256": "0" * 64}])
    row = _row(monkeypatch, ctx)
    assert row.state == "DEGRADED" and "unresolved historical stop intent" in row.detail


@pytest.mark.parametrize("changes", [
    {"status": "PROTECTED", "roles": [{"role": "hack1", "status": "REFUSED",
                                      "candidates": 1, "held_symbols": 1}],
     "candidates": [{"role": "hack1", "symbol": "TEST", "status": "PROTECTED"}]},
    {"status": "PROTECTED", "roles": [{"role": "hack1", "status": "CANDIDATE",
                                      "candidates": 1, "held_symbols": 1}],
     "candidates": [{"status": "PROTECTED"}]},
    {"roles": [{"role": "hack1", "status": "ALREADY_COVERED",
                "candidates": False, "held_symbols": 0}]},
    {"status": "PROTECTED", "roles": [{"role": "hack1", "status": "CANDIDATE",
                                      "candidates": 2, "held_symbols": 2}],
     "candidates": [{"role": "hack1", "symbol": "TEST", "status": "PROTECTED"},
                    {"role": "hack1", "symbol": "TEST", "status": "PROTECTED"}]},
    {"roles": [{"role": "unknown", "status": "ALREADY_COVERED",
                "candidates": 0, "held_symbols": 0}]},
])
def test_contradictory_or_incomplete_success_shape_is_degraded(tmp_path, monkeypatch, changes):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    path = _receipt(ctx, now - timedelta(minutes=1))
    _change(path, **changes)
    assert _row(monkeypatch, ctx).state == "DEGRADED"


def test_real_protected_candidate_shape_is_accepted(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    path = _receipt(ctx, now - timedelta(minutes=1), "PROTECTED", roles=[
        {"role": "hack1", "status": "CANDIDATE", "candidates": 1, "held_symbols": 1}])
    _change(path, candidates=[{"role": "hack1", "symbol": "TEST", "status": "PROTECTED"}])
    assert _row(monkeypatch, ctx).state == "ALIVE_PROGRESSING"


def test_candidate_resolved_as_already_covered_has_consistent_census(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    path = _receipt(ctx, now - timedelta(minutes=1), roles=[
        {"role": "hack1", "status": "CANDIDATE", "candidates": 1, "held_symbols": 1}])
    _change(path, candidates=[{"role": "hack1", "symbol": "TEST", "status": "ALREADY_COVERED"}])
    assert _row(monkeypatch, ctx).state == "ALIVE_PROGRESSING"


@pytest.mark.parametrize("change", [
    {"started_utc": "2026-10-09T17:00:00+00:00"},
    {"started_utc": "2026-10-09T15:59:00"},
    {"finished_utc": "2026-10-09T15:58:00+00:00"},
    {"finished_utc": None},
])
def test_sweep_chronology_and_filename_must_match(tmp_path, monkeypatch, change):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    path = _receipt(ctx, now - timedelta(minutes=1))
    _change(path, **change)
    assert _row(monkeypatch, ctx).state not in TR.ALIVE_STATES


def test_half_day_final_tick_and_postclose_refusal_are_calendar_verified(tmp_path, monkeypatch):
    now = datetime(2026, 11, 27, 18, 20, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    assert TR._sweep_window(now.date())[1] == datetime(2026, 11, 27, 17, 50, tzinfo=timezone.utc)
    _receipt(ctx, datetime(2026, 11, 27, 17, 50, tzinfo=timezone.utc))
    assert _row(monkeypatch, ctx).state == "ALIVE_IDLE_EXPECTED"
    refused = _receipt(ctx, now - timedelta(minutes=1), "REFUSED")
    _change(refused, why="FleetRefusal: sweep venue closed, clock stale, or inside frozen close buffer")
    row = _row(monkeypatch, ctx)
    assert row.state == "ALIVE_IDLE_EXPECTED" and "final tick 17:50" in row.detail
    assert "+" in row.proof  # both final success and later expected refusal are visible
    _change(refused, history_warnings=[{"role": "hack1", "symbol": "TEST",
                                        "code": "UNRESOLVED_PRIOR_STOP_INTENT",
                                        "identity_sha256": "0" * 64}])
    assert _row(monkeypatch, ctx).state == "REFUSED"


def test_half_day_missing_final_tick_or_inwindow_clock_refusal_stays_actionable(tmp_path, monkeypatch):
    now = datetime(2026, 11, 27, 18, 20, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    _receipt(ctx, datetime(2026, 11, 27, 15, 10, tzinfo=timezone.utc))
    assert _row(monkeypatch, ctx).state == "STALE"
    refused = _receipt(ctx, now - timedelta(minutes=1), "REFUSED")
    _change(refused, why="FleetRefusal: sweep venue closed, clock stale, or inside frozen close buffer")
    assert _row(monkeypatch, ctx).state == "REFUSED"
    ctx2 = _ctx(tmp_path / "other", datetime(2026, 11, 27, 17, 45, tzinfo=timezone.utc))
    refused = _receipt(ctx2, ctx2.now - timedelta(minutes=1), "REFUSED")
    _change(refused, why="FleetRefusal: sweep venue closed, clock stale, or inside frozen close buffer")
    assert _row(monkeypatch, ctx2).state == "REFUSED"


@pytest.mark.parametrize("middle_status,warnings", [
    ("ALREADY_COVERED", [{"role": "hack1", "symbol": "TEST",
                          "code": "UNRESOLVED_PRIOR_STOP_INTENT", "identity_sha256": "0" * 64}]),
    ("INCOMPLETE", []),
    ("REFUSED", []),
    ("CORRUPT", []),
])
def test_postclose_idle_cannot_skip_newer_nonclean_eligible_attempt(
        tmp_path, monkeypatch, middle_status, warnings):
    now = datetime(2026, 11, 27, 18, 20, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now)
    original = _receipt(ctx, datetime(2026, 11, 27, 17, 50, tzinfo=timezone.utc))
    middle = _receipt(ctx, datetime(2026, 11, 27, 17, 51, tzinfo=timezone.utc),
                      middle_status, warnings=warnings)
    if middle_status == "CORRUPT":
        middle.write_text("{", encoding="utf-8")
    after = _receipt(ctx, now - timedelta(minutes=1), "REFUSED")
    _change(after, why="FleetRefusal: sweep venue closed, clock stale, or inside frozen close buffer")
    row = _row(monkeypatch, ctx)
    assert row.state == "REFUSED"
    assert original.name not in row.proof and middle.name in row.proof and after.name in row.proof
    assert "latest preceding attempt" in row.detail
    if warnings:
        assert "unresolved historical stop intent" in row.detail
