"""Task receipt for AegisDynamicBooks (CH-45): the step's own run row, dated by its own utc. Fixtures only."""
import json
from datetime import datetime, time, timedelta, timezone

import pytest

from backend.services import system_health as SH, task_receipts as TR

NAME = "AegisDynamicBooks"


def setup(tmp_path, *, now=None, **kw):
    now = now or datetime.now(timezone.utc)
    p = tmp_path / "runs.jsonl"
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now, repo=tmp_path, paths={"dynamic_book_runs": p})
    row = {"task": NAME, "utc": now.isoformat(), "mode": "step", "action": "MARKED", "rc": 0,
           "through": "fixture", "cohorts_total": 5, "paths_total": 30, "paths_written": 3,
           "stored_rows_rechecked": 27, "stored_rows_differ": 0, "calendar_stale": {}}
    row.update(kw)
    return ctx, p, row


def judge(ctx, path, row):
    path.write_text(json.dumps(row) + "\n", encoding="utf8")
    return TR.judge(ctx, NAME, {"TaskName": NAME, "Scheduled Task State": "Enabled", "Last Result": "0"})


def test_the_task_is_declared_with_its_own_journal():
    spec = TR.TASK_RECEIPT[NAME]
    assert spec.reader is TR.r_dynamic_books and "dynamic_books/runs.jsonl" in spec.receipt


@pytest.mark.parametrize("action,rc,expected", [
    ("BORN", 0, "ALIVE_PROGRESSING"), ("MARKED", 0, "ALIVE_PROGRESSING"),
    ("NOTHING_DUE", 0, "ALIVE_IDLE_EXPECTED"), ("STALE_CALENDAR", 3, "DEGRADED"),
    ("REFUSED", 2, "REFUSED"), ("SOMETHING_ELSE", 0, "DEGRADED")])
def test_actions(tmp_path, action, rc, expected):
    ctx, p, row = setup(tmp_path, action=action, rc=rc)
    assert judge(ctx, p, row).state == expected


def test_an_unscheduled_leader_on_a_fresh_calendar_stays_ok(tmp_path):
    # v3: a leader with no announced next date is named on the row, exit 0, not a fault
    ctx, p, row = setup(tmp_path, contract_version="v3",
                        calendar_unscheduled={"GOOGL": ["no announced next date (ONLY_PAST_DATES)"]})
    assert judge(ctx, p, row).state == "ALIVE_PROGRESSING"


def test_a_stale_forward_calendar_reads_degraded_and_names_it(tmp_path):
    ctx, p, row = setup(tmp_path, action="STALE_CALENDAR", rc=3, contract_version="v3",
                        calendar_stale={"_forward_calendar": ["STALE: fc_x_receipt.json 3.4 d old"]})
    j = judge(ctx, p, row)
    assert j.state == "DEGRADED" and "_forward_calendar" in j.detail


def test_a_stale_calendar_names_the_leaders(tmp_path):
    ctx, p, row = setup(tmp_path, action="STALE_CALENDAR", rc=3,
                        calendar_stale={"NVDA": ["newest report 2026-08-26 is 81 days old (> 80)"]})
    j = judge(ctx, p, row)
    assert j.state == "DEGRADED" and "NVDA" in j.detail and "81 days" in j.detail


@pytest.mark.parametrize("reason", [
    "3 stored path row(s) differ from the recompute (first: ...)",
    "the rolling grading config the base book depends on changed since the declaration: ROLLING_COHORT_X",
    "code version ffff differs from the declared aaaa and from every accepted one"])
def test_drift_and_mismatch_refusals_read_refused_with_their_reason(tmp_path, reason):
    ctx, p, row = setup(tmp_path, action="REFUSED", rc=2, reason=reason)
    j = judge(ctx, p, row)
    assert j.state == "REFUSED" and reason[:30] in j.detail


def test_a_success_row_with_a_wrong_rc_or_a_recompute_difference_is_degraded(tmp_path):
    ctx, p, row = setup(tmp_path, rc=3)
    assert judge(ctx, p, row).state == "DEGRADED"
    ctx, p, row = setup(tmp_path, stored_rows_differ=2)
    assert judge(ctx, p, row).state == "DEGRADED"
    ctx, p, row = setup(tmp_path, task="SomethingElse")
    assert judge(ctx, p, row).state == "DEGRADED"


def test_never_ok_without_a_fresh_row(tmp_path):
    now = datetime.now(timezone.utc)
    ctx, p, row = setup(tmp_path, now=now, utc=(now - timedelta(days=4)).isoformat())
    assert judge(ctx, p, row).state not in ("ALIVE_PROGRESSING", "ALIVE_IDLE_EXPECTED")
    ctx, p, _ = setup(tmp_path / "empty")
    j = TR.judge(ctx, NAME, {"TaskName": NAME, "Scheduled Task State": "Enabled", "Last Result": "0"})
    assert j.state not in ("ALIVE_PROGRESSING", "ALIVE_IDLE_EXPECTED")


def test_a_real_step_row_and_a_cli_refusal_are_read(tmp_path, monkeypatch):
    from backend.tests import test_dynamic_exposure_books as T
    from backend import config as _config
    from backend.services.portfolio_intelligence import branch_population_rolling as R
    from backend.services.portfolio_intelligence import dynamic_exposure_books as D
    from scripts import dynamic_books as CLI
    monkeypatch.setattr(_config, "ROLLING_COHORT_ANCHOR", T.DAYS[T.ANCHOR_I].date().isoformat())
    monkeypatch.setattr(_config, "DYNAMIC_BOOK_LEADERS", ("AAPL",))
    bars = T.make_bars()
    sessions = R.bench_sessions(bars)
    cpath = T._contracts(tmp_path)
    d = sessions[T.ANCHOR_I + 10]
    root = T._data_root(tmp_path, bars[bars["date"] <= d])
    out = tmp_path / "dxb"
    now = datetime.combine(d.date(), time(23, 0), tzinfo=timezone.utc)
    D.run("step", data_root=root, out=out, contracts_path=cpath, asof=d, now=now, calendar=T.FakeCal())
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now + timedelta(minutes=5), repo=tmp_path,
                      paths={"dynamic_book_runs": out / "runs.jsonl"})
    task = {"TaskName": NAME, "Scheduled Task State": "Enabled", "Last Result": "0"}
    assert TR.judge(ctx, NAME, task).state == "ALIVE_PROGRESSING"            # BORN
    # a refusal through the CLI is journaled and read REFUSED (the contracts file is absent)
    monkeypatch.setattr(D, "CONTRACTS_REL", "docs/TRIALS/does-not-exist.json")
    assert CLI.main(["step", "--data-root", str(root), "--out", str(out), "--asof", str(d.date())]) == 2
    last = json.loads((out / "runs.jsonl").read_text(encoding="utf8").splitlines()[-1])
    assert last["action"] == "REFUSED" and last["rc"] == 2
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=datetime.now(timezone.utc), repo=tmp_path,
                      paths={"dynamic_book_runs": out / "runs.jsonl"})
    assert TR.judge(ctx, NAME, task).state == "REFUSED"
