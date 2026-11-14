"""Health readers for the rolling cohorts and the pinned branching owner (fixtures only)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import system_health as SH, task_receipts as TR

NAME = "AegisRollingCohorts"


def setup(tmp_path, **kw):
    now = datetime.now(timezone.utc)
    p = tmp_path / "runs.jsonl"
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now, repo=tmp_path, paths={"rolling_cohort_runs": p})
    row = {"task": NAME, "utc": now.isoformat(), "action": "MARKED", "rc": 0, "forward_age_sessions": 3,
           "newest_forward_cohort": "fixture", "cohorts_total": 5, "cohorts_live": 5, "marks_total": 10}
    row.update(kw)
    return ctx, p, row


def judge(ctx, path, row):
    path.write_text(json.dumps(row) + "\n", encoding="utf8")
    return TR.judge(ctx, NAME, {"TaskName": NAME, "Scheduled Task State": "Enabled", "Last Result": "0"})


@pytest.mark.parametrize("action,expected", [
    ("BORN", "ALIVE_PROGRESSING"), ("MARKED", "ALIVE_PROGRESSING"), ("NOTHING_DUE", "ALIVE_IDLE_EXPECTED"),
    ("WAIT_PRICES", "ALIVE_IDLE_EXPECTED"), ("MISSED_ENTRY_WINDOW", "DEGRADED"), ("REFUSED", "REFUSED"),
    ("WAIT_LOCK", "ALIVE_IDLE_EXPECTED"),
    ("SOMETHING_ELSE", "DEGRADED")])
def test_actions(tmp_path, action, expected):
    ctx, p, row = setup(tmp_path, action=action)
    assert judge(ctx, p, row).state == expected


def test_no_forward_cohort_for_more_than_two_cadences_is_degraded(tmp_path):
    limit = TR._config.ROLLING_COHORT_CADENCE_SESSIONS * TR._config.ROLLING_COHORT_STALE_CADENCES
    ctx, p, row = setup(tmp_path, forward_age_sessions=limit)
    assert judge(ctx, p, row).state == "ALIVE_PROGRESSING"
    row["forward_age_sessions"] = limit + 1
    r = judge(ctx, p, row)
    assert r.state == "DEGRADED"
    row.pop("forward_age_sessions")
    assert judge(ctx, p, row).state == "DEGRADED"


def test_identity_and_clock(tmp_path):
    ctx, p, row = setup(tmp_path, task="Other")
    assert judge(ctx, p, row).state == "DEGRADED"
    row.update(task=NAME, utc=(ctx.now + timedelta(minutes=5)).isoformat())
    assert judge(ctx, p, row).state == "DEGRADED"
    row["utc"] = (ctx.now - timedelta(hours=3)).isoformat()
    assert judge(ctx, p, row).state == "STALE"


def test_branching_owner_price_wait_is_idle_other_refusals_stay_red(tmp_path):
    now = datetime.now(timezone.utc)
    p = tmp_path / "automation_runs.jsonl"
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now, repo=tmp_path, paths={"local_branching_runs": p})
    name = "AegisLocalBranchingPrivateGrade"
    row = {"task": name, "utc": now.isoformat(), "action": "REFUSED",
           "reason": "RuntimeError: owned child exited 1: Traceback ...\r\n    raise ValueError('WAIT_SHARED_PRICE_REFRESH')\r\nValueError: WAIT_SHARED_PRICE_REFRESH"}
    p.write_text(json.dumps(row) + "\n", encoding="utf8")
    task = {"TaskName": name, "Scheduled Task State": "Enabled", "Last Result": "1"}
    assert TR.judge(ctx, name, task).state == "ALIVE_IDLE_EXPECTED"
    row["reason"] = "TimeoutExpired: Command '['git', 'rev-parse', 'HEAD']' timed out after 5 seconds"
    p.write_text(json.dumps(row) + "\n", encoding="utf8")
    assert TR.judge(ctx, name, task).state == "REFUSED"


def test_branching_owner_says_the_population_is_static(tmp_path):
    now = datetime.now(timezone.utc)
    p = tmp_path / "automation_runs.jsonl"
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now, repo=tmp_path, paths={"local_branching_runs": p})
    name = "AegisLocalBranchingPrivateGrade"
    row = {"task": name, "utc": now.isoformat(), "action": "WAIT_CONSTITUENT_MARKS",
           "resource_proof": {"child_reaped": True, "aggregate_limit_bytes": 512 * 1024 ** 2,
                              "aggregate_peak_upper_bound": 64 * 1024 ** 2},
           "population1000": {"action": "POPULATION_OPERATED", "activation": "NONE", "new_frozen_books": 0,
                              "marked": 886, "pending_entry": 0}}
    p.write_text(json.dumps(row) + "\n", encoding="utf8")
    r = TR.r_local_branching_private_grade(ctx, None)
    assert "STATIC" in r.reason
