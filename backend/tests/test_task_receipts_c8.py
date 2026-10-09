"""C8 (2026-10-07): a scheduled task is judged by the receipt it must advance.

Review 2026-10-07 (docs/reviews/REVIEW_2026-10-07_C8_PROGRESS_AWARE_HEALTH.md):
every reader is fed its producer's WORST real receipt (committed, trimmed, under
fixtures/c8/) and must not read ALIVE. Every date is derived from `now` (protocol
item 5); fixture stamps are re-dated relative to today. No machine details.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import system_health as SH
from backend.services import task_receipts as TR

REPO = Path(__file__).resolve().parents[2]
FX = Path(__file__).resolve().parent / "fixtures" / "c8"


@pytest.mark.parametrize("status,rows,tokens,cleanup,expected", [
    ("OK", 20, 10, True, "ALIVE_PROGRESSING"),
    ("REFUSED", 20, 0, True, "REFUSED"),
    ("FAILED", 20, 0, True, "DEGRADED"),
    ("METADATA_ONLY", 20, 0, True, "DEGRADED"),
    ("OK", 0, 10, True, "DEGRADED"),
    ("OK", 20, 0, True, "DEGRADED"),
    ("OK", 20, 10, False, "DEGRADED"),
])
def test_local_digest_health_requires_inference_and_useful_input(tmp_path, status, rows, tokens, cleanup, expected):
    ctx = _ctx(tmp_path)
    _w(ctx.optimus_dir / "local_runtime_digest/digest_20261009T130000.json", {
        "generated_utc": ctx.now.isoformat(), "status": status, "paid_fallback": False,
        "cost_usd": 0, "tokens_out": tokens, "served_models": ["Qwen2.5-7B"],
        "summary": "A sampled summary", "owned_server_stopped": cleanup,
        "inputs": [{"exists": True, "sampled_rows": rows, "invalid_rows": 0}],
    })
    assert TR.judge(ctx, "AegisLocalRuntimeDigest", _task("AegisLocalRuntimeDigest")).state == expected


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _w(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def _jl(p: Path, rows: list[dict]) -> Path:
    return _w(p, "\n".join(json.dumps(r) for r in rows) + "\n")


def _ctx(tmp_path: Path, *, now: datetime | None = None, prev_state=None) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(parents=True, exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now or _now(), repo=tmp_path,
                       prev_state=prev_state or {},
                       paths={"terminal_repo": tmp_path / "no_terminal"},
                       run=lambda argv, t: (None, "not installed"),
                       pid_cmdline=lambda pid: None)


def _task(name: str, **kw) -> dict:
    return {"TaskName": "\\" + name, "Scheduled Task State": "Enabled",
            "Last Run Time": "-", "Last Result": "0", "Next Run Time": "-", **kw}


def _session_at(now: datetime, et_hhmm: tuple[int, int], back: int = 0) -> datetime:
    """A UTC instant at `et_hhmm` US/Eastern on the `back`-th most recent XNYS session."""
    from zoneinfo import ZoneInfo
    et = SH._et(now)
    days, _ = SH._sessions(et.date() - timedelta(days=20), et.date())
    d = days[-1 - back]
    return datetime.combine(d, dtime(*et_hhmm), ZoneInfo("America/New_York")).astimezone(timezone.utc)


def _non_session_day(now: datetime) -> date:
    d = SH._et(now).date()
    for i in range(0, 10):
        c = d - timedelta(days=i)
        if not SH._sessions(c, c)[0]:
            return c
    raise AssertionError("no non-session day in 10")


# ─────────────────────────── 1. no task is UNKNOWN by omission (structured scan)

_TN = re.compile(r"""(?:/TN\s+|-TaskName\s+)["']?([A-Za-z][A-Za-z0-9 ]*?[A-Za-z0-9])["']?(?=\s|$|["'])""")


def _strings_in(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def _task_names_from_code() -> set[str]:
    """Task names the repo REGISTERS, read structurally: string constants bound to a
    TASK-named variable (TASK, TASK_NAME, TASK_*, *_TASKS), and `/TN X` / `-TaskName X`
    inside string literals that are NOT docstrings; plus `.ps1` registrations."""
    names: set[str] = set()
    for root in (REPO / "scripts", REPO / "backend" / "services", REPO / "nn_lab"):
        for f in root.rglob("*.py"):
            if "tests" in f.parts or ".venv" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            docs = set()
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if n.body and isinstance(n.body[0], ast.Expr) and isinstance(
                            getattr(n.body[0], "value", None), ast.Constant):
                        docs.add(id(n.body[0].value))
            for n in ast.walk(tree):
                if isinstance(n, ast.Assign):
                    tgt = [t.id for t in n.targets if isinstance(t, ast.Name)]
                    if any(re.fullmatch(r"TASK(_[A-Z_]+)?|[A-Z_]*_TASKS?", t) for t in tgt):
                        names.update(s for s in _strings_in(n.value) if re.fullmatch(r"Aegis[A-Z]\w+", s))
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                    for m in _TN.finditer(n.value):
                        if m.group(1).startswith("Aegis"):
                            names.add(m.group(1))
    for f in REPO.rglob("*.ps1"):
        if ".venv" in f.parts or "node_modules" in f.parts:
            continue
        for m in _TN.finditer(f.read_text(encoding="utf-8", errors="replace")):
            if m.group(1).startswith("Aegis"):
                names.add(m.group(1))
    return names


def test_every_task_the_repo_registers_has_a_declared_receipt():
    from scripts import task_keeper as K
    declared = set(K.CATCHUP_TASKS) | {getattr(K, n) for n in dir(K)
                                       if n.startswith("TASK_") and isinstance(getattr(K, n), str)}
    found = _task_names_from_code() | declared
    assert {"AegisDailyPass", "AegisSimOwner", "AegisBrainRefresh"} <= found, \
        "the structured scan lost known registrations -- a broken guard"
    missing = sorted(n for n in found if n not in TR.TASK_RECEIPT)
    assert not missing, f"tasks with no receipt reader (would read UNKNOWN): {missing}"


def test_the_scan_ignores_a_docstring_that_explains_a_task():
    tree = ast.parse('def f():\n    """schtasks /Create /TN "AegisExplainedOnly" ..."""\n    return 1\n')
    doc = tree.body[0].body[0].value
    assert isinstance(doc, ast.Constant)        # the docstring node the scan skips by id


@pytest.mark.parametrize("name", sorted(TR.TASK_RECEIPT))
def test_each_declared_reader_never_raises_and_nothing_on_disk_is_never_progressing(tmp_path, name):
    spec = TR.TASK_RECEIPT[name]
    assert callable(spec.reader) and spec.receipt
    j = TR.judge(_ctx(tmp_path), name, _task(name), spec)
    assert j.state in TR.STATES
    assert not j.detail.startswith("receipt reader raised"), j.detail
    assert j.state != "ALIVE_PROGRESSING", (name, j.detail)


def test_every_declared_task_has_a_cadence_in_config():
    missing = [n for n, s in TR.TASK_RECEIPT.items()
               if not (s.retired or s.registered_only) and n not in C.HEALTH_TASK_CADENCE_H]
    assert not missing


def test_an_unmapped_scheduled_task_is_a_visible_unknown(tmp_path):
    j = TR.judge(_ctx(tmp_path), "AegisSomethingNew", _task("AegisSomethingNew"))
    assert j.state == "UNKNOWN" and "TASK_RECEIPT" in j.detail


# ─────────────────────────── 2. the ONE status mapping (review F1)

@pytest.mark.parametrize("word,expect", [
    ("ok", "OK"), ("OK", "OK"), ("nothing_to_do", "OK"), ("OBSERVE_ONLY: x", "OK"),
    ("refused", "REFUSED"), ("REFUSED: bars", "REFUSED"), ("error", "DEGRADED"),
    ("ERROR", "DEGRADED"), ("timeout", "DEGRADED"), ("HTTP_401", "DEGRADED"),
    ("failed", "DEGRADED"), ("STOPPED: STOP file", "STOPPED"), ("paused", "STOPPED"),
    ("outside_window", "IDLE"), ("SKIPPED", "IDLE"), ("something_new", "DEGRADED")])
def test_map_status(word, expect):
    assert TR.map_status(word) == expect


@pytest.mark.parametrize("bad", ["REFUSED", "DEGRADED", "STOPPED", "DEAD"])
@pytest.mark.parametrize("name", sorted(n for n, s in TR.TASK_RECEIPT.items()
                                        if not (s.retired or s.unregistered_ok)))
def test_property_a_failed_reading_is_never_alive(tmp_path, name, bad):
    now = _now()
    spec = TR.TASK_RECEIPT[name]
    fake = TR.TaskSpec(lambda ctx, task: TR.Reading(stamp=now - timedelta(minutes=1), status=bad,
                                                     reason=f"{bad} for the test", substance="x"),
                       spec.receipt, session_only=spec.session_only, window_cfg=spec.window_cfg)
    j = TR.judge(_ctx(tmp_path, now=now), name, _task(name), fake)
    assert j.state not in TR.ALIVE_STATES, (name, bad, j.state, j.detail)


# ─────────────────────────── 3. the worst REAL receipts (review F1, F3, F4)

def _redate_steps(d: dict, now: datetime) -> dict:
    stamps = [TR.parse_stamp(s.get("utc")) for s in d["steps"] if s.get("utc")]
    shift = now - timedelta(hours=1) - max(stamps)
    for s in d["steps"]:
        if s.get("utc"):
            s["utc"] = (TR.parse_stamp(s["utc"]) + shift).isoformat()
    return d


def test_blackout_daily_pass_0930_is_not_alive(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    d = _redate_steps(json.loads((FX / "daily_pass_2026-09-30.json").read_text(encoding="utf-8")), now)
    day = now.date()
    _w(ctx.optimus_dir / f"night_factory_{day}" / f"daily_pass_{day}.json", d)
    j = TR.judge(ctx, "AegisDailyPass", _task("AegisDailyPass"))
    assert j.state == "DEGRADED" and "bars_refresh=refused" in j.detail, j.detail


def test_grading_nothing_to_do_while_rows_are_due_is_degraded(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    day = now.date()
    _w(ctx.optimus_dir / f"night_factory_{day}" / f"daily_pass_{day}.json",
       {"steps": [{"step": "grade_forecasts", "status": "nothing_to_do",
                   "utc": (now - timedelta(hours=1)).isoformat()}]})
    ctx.cache["ledger"] = {"due_unresolved": 40}
    j = TR.judge(ctx, "AegisDailyPass", _task("AegisDailyPass"))
    assert j.state == "DEGRADED" and "40 due row(s)" in j.detail


def test_straddle_refusal_1001_reads_refused(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    d = json.loads((FX / "straddle_pass_20261001T174630Z.json").read_text(encoding="utf-8"))
    t = now - timedelta(minutes=5)
    d["now_utc"], d["stamp"] = t.isoformat(), t.strftime("%Y%m%dT%H%M%SZ")
    _w(ctx.optimus_dir / "straddle_forward" / "runs" / f"pass_{d['stamp']}.json", d)
    j = TR.judge(ctx, "AegisStraddleForward", _task("AegisStraddleForward"))
    assert j.state == "REFUSED" and "bars newest" in j.detail, j.detail


def _fleet_run(ctx, which: str, t: datetime, statuses: dict) -> None:
    accts = [{"role": r, "status": s, "why": "HTTP 401" if s == "ERROR" else None, "equity": 1.0}
             for r, s in statuses.items()]
    _w(ctx.optimus_dir / "paper_accounts" / "fleet_manager" / "runs" / f"run_{t:%Y%m%dT%H%M%SZ}-abcdef.json",
       {"pass": which, "started_utc": t.isoformat(), "finished_utc": t.isoformat(), "accounts": accts})


def test_all_error_fleet_pass_is_dead_and_one_error_is_degraded(tmp_path):
    now = _now()
    t = now - timedelta(minutes=30)
    ctx = _ctx(tmp_path, now=now)
    _fleet_run(ctx, "open", t, {f"hack{i}": "ERROR" for i in (1, 2, 4, 5, 6)} | {"hack3": "SKIPPED"})
    j = TR.judge(ctx, "AegisFleetManagerOpen", _task("AegisFleetManagerOpen"))
    assert j.state == "DEAD" and "EVERY account failed" in j.detail, j.detail
    ctx2 = _ctx(tmp_path / "b", now=now)
    _fleet_run(ctx2, "open", t, {"hack1": "ok", "hack2": "ERROR", "hack3": "SKIPPED"})
    j = TR.judge(ctx2, "AegisFleetManagerOpen", _task("AegisFleetManagerOpen"))
    assert j.state == "DEGRADED" and "hack2=ERROR" in j.detail


# ─────────────────────────── 4. contest desk (review F2)

def test_contest_desk_never_run_after_first_day_is_stale_or_dead(tmp_path):
    first = TR._contest_live_first_day()
    now = datetime(first.year, first.month, first.day, 20, tzinfo=timezone.utc) + timedelta(days=4)
    never = _task("AegisContestDesk", **{"Last Result": TR.NEVER_RAN_RC})
    j = TR.judge(_ctx(tmp_path, now=now), "AegisContestDesk", never)
    assert j.state == "STALE" and "NEVER run" in j.detail, j.detail
    assert TR.judge(_ctx(tmp_path / "b", now=now), "AegisContestDesk", None).state == "DEAD"
    early = datetime(first.year, first.month, first.day, tzinfo=timezone.utc) - timedelta(days=2)
    j = TR.judge(_ctx(tmp_path / "c", now=early), "AegisContestDesk", never)
    assert j.state == "ALIVE_IDLE_EXPECTED" and "not yet due" in j.detail


def test_contest_calendar_import_failure_is_unknown_with_the_class(tmp_path, monkeypatch):
    def boom():
        raise ModuleNotFoundError("no contest_calendar")
    monkeypatch.setattr(TR, "_contest_live_first_day", boom)
    j = TR.judge(_ctx(tmp_path), "AegisContestDesk", _task("AegisContestDesk"))
    assert j.state == "UNKNOWN" and "ModuleNotFoundError" in j.detail


def test_a_receipt_that_refuses_shows_refused_with_the_reason(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    st = now - timedelta(minutes=30)
    _w(ctx.optimus_dir / "contest" / "live" / "refusals" / f"live_gate_{st.date()}_{st:%Y%m%dT%H%M%SZ}.json",
       {"receipt": "contest_live_gate", "written_utc": f"{st:%Y%m%dT%H%M%SZ}", "result": "REFUSED",
        "reasons": ["contest/REGISTERED is missing"]})
    j = TR.judge(ctx, "AegisContestDesk", _task("AegisContestDesk"))
    assert j.state == "REFUSED" and "REGISTERED is missing" in j.detail


# ─────────────────────────── 5. straddle window (review F4)

def _straddle(ctx, t: datetime) -> None:
    _w(ctx.optimus_dir / "straddle_forward" / "runs" / f"pass_{t:%Y%m%dT%H%M%SZ}.json",
       {"now_utc": t.isoformat(), "state": "OBSERVE_ONLY: none", "summary": {"n_usable": 3}})


def test_straddle_after_its_window_is_idle_not_stale(tmp_path):
    now = _session_at(_now(), (20, 0), back=1)                   # 20:00 ET, after the window
    ctx = _ctx(tmp_path, now=now)
    _straddle(ctx, _session_at(_now(), (15, 16), back=1))        # last in-window pass
    j = TR.judge(ctx, "AegisStraddleForward", _task("AegisStraddleForward"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "outside its declared window" in j.detail, j.detail


def test_straddle_window_that_produced_nothing_is_stale(tmp_path):
    now = _session_at(_now(), (20, 0), back=1)
    ctx = _ctx(tmp_path, now=now)
    _straddle(ctx, _session_at(_now(), (15, 16), back=3))        # two sessions earlier
    j = TR.judge(ctx, "AegisStraddleForward", _task("AegisStraddleForward"))
    assert j.state == "STALE" and "produced no receipt" in j.detail, j.detail


def test_straddle_on_a_non_session_day_is_idle(tmp_path):
    day = _non_session_day(_now())
    now = datetime(day.year, day.month, day.day, 18, tzinfo=timezone.utc)
    prev = [s for s in SH._sessions(day - timedelta(days=7), day)[0] if s < day][-1]
    from zoneinfo import ZoneInfo
    t = datetime.combine(prev, dtime(15, 16), ZoneInfo("America/New_York")).astimezone(timezone.utc)
    ctx = _ctx(tmp_path, now=now)
    _straddle(ctx, t)
    j = TR.judge(ctx, "AegisStraddleForward", _task("AegisStraddleForward"))
    assert j.state == "ALIVE_IDLE_EXPECTED", j.detail


# ─────────────────────────── 6. other readers read their failure fields (review F5)

def test_world_digest_zero_items_or_failed_calls_is_degraded(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(hours=1)
    _w(ctx.optimus_dir / "digest" / f"world_digest_{t:%Y%m%dT%H%M%SZ}.json",
       {"stamp": f"{t:%Y%m%dT%H%M%SZ}", "n_items": 0, "spend": {"calls": 10, "failed": 4}})
    j = TR.judge(ctx, "AegisWorldDigest", _task("AegisWorldDigest"))
    assert j.state == "DEGRADED" and "zero items" in j.detail and "4 of 10" in j.detail


def test_alerts_read_their_state_and_bars_health(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(minutes=5)
    _w(ctx.optimus_dir / "alerts" / "receipts" / f"alert_pass_{t:%Y%m%dT%H%M%SZ}_1.json",
       {"created_utc": t.isoformat(), "state": "OK",
        "bars_health": {"state": "STALE", "line": "bars 3 sessions old"}})
    j = TR.judge(ctx, "AegisAlerts", _task("AegisAlerts"))
    assert j.state == "DEGRADED" and "bars 3 sessions old" in j.detail


def test_sim_owner_outside_window_is_idle(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    _jl(ctx.optimus_dir / "sim" / "owner.jsonl",
        [{"utc": (now - timedelta(minutes=10)).isoformat(), "action": "outside_window",
          "why": "before the first start"}])
    j = TR.judge(ctx, "AegisSimOwner", _task("AegisSimOwner"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "before the first start" in j.detail


def test_analyst_failed_run_is_refused_and_a_manual_pull_is_named(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(hours=2)
    _w(ctx.optimus_dir / "analyst" / f"analyst_pull_{t.date()}.json",
       {"written_utc": t.isoformat(), "day": str(t.date()), "n_snapshots": 3000, "n_requested": 3100})
    never = _task("AegisAnalystPull", **{"Last Result": TR.NEVER_RAN_RC})
    j = TR.judge(ctx, "AegisAnalystPull", never)
    assert j.state == "ALIVE_IDLE_EXPECTED" and "MANUAL pull" in j.detail
    _jl(ctx.optimus_dir / "task_keeper" / "analyst.jsonl",
        [{"utc": (now - timedelta(minutes=5)).isoformat(), "job": "analyst", "action": "failed",
          "why": "timed out after 150 min"}])
    j = TR.judge(ctx, "AegisAnalystPull", _task("AegisAnalystPull"))
    assert j.state == "REFUSED" and "timed out" in j.detail


def test_analyst_pull_refuses_while_the_us_session_is_open(tmp_path):
    from scripts import task_keeper as K
    open_ = _session_at(_now(), (12, 0), back=1)
    ran = []
    row = K.run_analyst_pull(now_utc=open_, runner=lambda *a, **k: ran.append(a),
                             log_path=tmp_path / "analyst.jsonl")
    assert row["action"] == "refused" and "US session is open" in row["why"] and not ran


def test_brain_refresh_refuses_with_a_reason_when_the_repo_is_absent(tmp_path):
    from scripts import task_keeper as K
    row = K.run_brain_refresh(root=tmp_path / "no_optimus", log_path=tmp_path / "brain.jsonl")
    assert row["action"] == "refused" and "refresh_aegis.py not found" in row["why"]
    ctx = _ctx(tmp_path)
    _jl(ctx.optimus_dir / "task_keeper" / "brain.jsonl", [row])
    j = TR.judge(ctx, "AegisBrainRefresh", _task("AegisBrainRefresh"))
    assert j.state == "REFUSED" and "refresh_aegis.py" in j.detail


def test_hyp_lab_stop_receipt_is_refused_not_unknown(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(hours=2)
    _w(ctx.optimus_dir / "hyp_lab" / "receipts" / f"nightly_{t:%Y%m%dT%H%M%SZ}.json",
       {"started_utc": t.isoformat(), "status": "REFUSED", "reason": "STOP file present 3 d"})
    j = TR.judge(ctx, "AegisHypLabNightly", _task("AegisHypLabNightly"))
    assert j.state == "REFUSED" and "STOP file" in j.detail


def test_nn_lab_contract_wired_refused_and_alive(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    rd = ctx.optimus_dir / "nn_lab" / "receipts"
    t = now - timedelta(hours=3)
    _w(rd / f"nightly_{t:%Y%m%dT%H%M%SZ}.json",
       {"status": "STALE_BARS", "written_utc": t.isoformat(), "refused": "bars 4 sessions behind"})
    j = TR.judge(ctx, "AegisNNLabNightly", _task("AegisNNLabNightly"))
    assert j.state == "REFUSED" and "STALE_BARS" in j.detail
    t2 = now - timedelta(hours=1)
    _w(rd / f"nightly_{t2:%Y%m%dT%H%M%SZ}.json", {"status": "OK", "written_utc": t2.isoformat()})
    j = TR.judge(ctx, "AegisNNLabNightly", _task("AegisNNLabNightly"))
    assert j.state == "ALIVE_PROGRESSING", j.detail


# ─────────────────────────── 7. the same-output hash (review F6)

def test_rehearsal_grades_1003_to_1005_hash_identical():
    rows = [json.loads(l) for l in (FX / "rehearsal_runs_2026-10-03_05.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(rows) == 3
    hashes = {TR.substance(TR.pick(r, TR.REHEARSAL_PROGRESS)) for r in rows}
    assert len(hashes) == 1, hashes


def test_substance_keeps_progress_keys_and_normalises_dates_in_values():
    a = TR.substance({"utc": "x", "run_id": "1", "rows_written": 3, "outcome": "up",
                      "coverage_rate": 0.5, "n_blocks": 4, "file": "daily_pass_2026-10-03.json",
                      "inner": {"started_utc": "y", "k": 1}})
    b = TR.substance({"utc": "z", "run_id": "2", "rows_written": 3, "outcome": "up",
                      "coverage_rate": 0.5, "n_blocks": 4, "file": "daily_pass_2026-10-04.json",
                      "inner": {"started_utc": "w", "k": 1}})
    assert a == b
    for k in ("rows_written", "outcome", "coverage_rate", "n_blocks"):
        assert k in a
    assert TR.substance({"rows_written": 4}) != TR.substance({"rows_written": 3})


def test_same_substance_with_moving_stamps_goes_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    allowed_h = C.HEALTH_TASK_CADENCE_H["AegisReaderSupervisor"] * (1 + SH.GRACE)
    _jl(ctx.optimus_dir / "dowjones" / "night_reader_supervisor.jsonl",
        [{"t": (now - timedelta(minutes=2)).isoformat(), "event": "tick",
          "page_loads_total": 500, "new_loads": 0}])
    first = (now - timedelta(hours=allowed_h * 4)).isoformat(timespec="seconds")
    h = hashlib.sha256(b"500").hexdigest()[:16]
    ctx.prev_state = {"progress": {"AegisReaderSupervisor": {"hash": h, "first_seen_utc": first, "n_same": 5}}}
    j = TR.judge(ctx, "AegisReaderSupervisor", _task("AegisReaderSupervisor"))
    assert j.state == "STALE" and "same output for" in j.detail, j.detail


def test_identical_ok_declared_by_the_producer_is_idle(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(hours=1)
    _w(ctx.optimus_dir / "digest" / f"world_digest_{t:%Y%m%dT%H%M%SZ}.json",
       {"stamp": f"{t:%Y%m%dT%H%M%SZ}", "n_items": 5, "identical_ok": True,
        "identical_reason": "holiday: no new items expected"})
    first = (now - timedelta(days=2)).isoformat()
    h = hashlib.sha256(TR.substance(TR.pick({"n_items": 5}, ("n_items", "counts", "themes"))).encode()).hexdigest()[:16]
    ctx.prev_state = {"progress": {"AegisWorldDigest": {"hash": h, "first_seen_utc": first, "n_same": 4}}}
    j = TR.judge(ctx, "AegisWorldDigest", _task("AegisWorldDigest"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "holiday" in j.detail, j.detail


def test_old_receipt_is_stale_by_its_own_stamp(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    old = now - timedelta(days=3)
    _w(ctx.optimus_dir / "digest" / f"world_digest_{old:%Y%m%dT%H%M%SZ}.json",
       {"stamp": f"{old:%Y%m%dT%H%M%SZ}", "n_items": 4})
    j = TR.judge(ctx, "AegisWorldDigest", _task("AegisWorldDigest"))
    assert j.state == "STALE" and "old" in j.detail


# ─────────────────────────── 8. registration states (review F7, F10)

def test_unregistered_task_with_an_old_refusal_is_dead(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(days=5)
    _w(ctx.optimus_dir / "hyp_lab" / "receipts" / f"nightly_{t:%Y%m%dT%H%M%SZ}.json",
       {"started_utc": t.isoformat(), "status": "REFUSED", "reason": "STOP"})
    assert TR.judge(ctx, "AegisHypLabNightly", None).state == "DEAD"


def test_disabled_without_a_marker_is_stale_and_with_one_is_stopped(tmp_path):
    ctx = _ctx(tmp_path)
    dis = _task("AegisDailyPass", **{"Scheduled Task State": "Disabled"})
    j = TR.judge(ctx, "AegisDailyPass", dis)
    assert j.state == "STALE" and "Disabled" in j.detail
    _w(ctx.optimus_dir / "task_keeper" / "disabled" / "AegisDailyPass", "owner: paused for the move")
    j = TR.judge(ctx, "AegisDailyPass", dis)
    assert j.state == "STOPPED_BY_OPERATOR" and "paused for the move" in j.detail


def test_public_flow_unregistered_is_not_dead(tmp_path):
    j = TR.judge(_ctx(tmp_path), "AegisPublicFlow", None)
    assert j.state == "UNREGISTERED" and j.verdict == "STOPPED_BY_OPERATOR"


def test_a_declared_task_missing_from_the_scheduler_is_not_alive(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    _w(ctx.optimus_dir / "data_catalog" / f"catalog_{now:%Y%m%dT%H%M%SZ}.json",
       {"utc": now.isoformat(), "summary": {"n": 1}})
    assert TR.judge(ctx, "AegisDataCatalog", None).state == "DEGRADED"
    assert TR.judge(_ctx(tmp_path / "b"), "AegisDataCatalog", None).state == "DEAD"


def test_retired_task_names_the_delete_command(tmp_path):
    j = TR.judge(_ctx(tmp_path), "AegisWRDSPullNight", _task("AegisWRDSPullNight"))
    assert j.state == "DEGRADED" and "schtasks /Delete /TN AegisWRDSPullNight /F" in j.detail


def test_weekend_reads_idle_expected_for_a_session_only_task(tmp_path):
    day = _non_session_day(_now())
    now = datetime(day.year, day.month, day.day, 18, 0, tzinfo=timezone.utc)
    prev = [s for s in SH._sessions(day - timedelta(days=7), day)[0] if s < day][-1]
    t = datetime(prev.year, prev.month, prev.day, 14, 48, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now=now)
    _fleet_run(ctx, "open", t, {"hack1": "ok", "hack3": "SKIPPED"})
    j = TR.judge(ctx, "AegisFleetManagerOpen", _task("AegisFleetManagerOpen"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and j.verdict == "ALIVE", j.detail
    assert "no XNYS session" in j.detail


# ─────────────────────────── 9. the probe surface (F7, F8, F10)

def test_task_rows_carry_state_and_coarse_verdict(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    sched = {n: _task(n) for n, sp in TR.TASK_RECEIPT.items() if not sp.registered_only}
    monkeypatch.setattr(SH, "_schtasks", lambda c: sched)
    rows = SH.run_probes(ctx, only={"task"})
    names = {r["name"] for r in rows}
    assert {f"task:{n}" for n in sched} <= names
    assert not any(f"task:{n}" in names for n, sp in TR.TASK_RECEIPT.items() if sp.registered_only)
    for r in rows:
        assert r["state"] in TR.STATES and TR.COARSE[r["state"]] == r["verdict"]
        assert r["state"] != "UNKNOWN" or "AnalystPanel" in r["name"], r
    out = SH.run(ctx=ctx, only={"task"})
    assert sum(out["state_counts"].values()) == len(out["rows"])


def test_non_alive_lines_name_refused_rows(tmp_path, monkeypatch):
    rec = {"generated_utc": _now().isoformat(), "rows": [
        {"name": "a", "verdict": "ALIVE", "detail": "fine"},
        {"name": "task:AegisNNLabNightly", "verdict": "REFUSED", "detail": "STALE_BARS"}]}
    monkeypatch.setattr(SH, "newest_receipt", lambda hd=None: rec)
    monkeypatch.setattr(SH, "disk_status", lambda **kw: {"verdict": "ALIVE", "line": "disk free: ok"})
    lines = SH.non_alive_lines()
    assert "1 REFUSED" in lines[0]
    assert any(l.startswith("- REFUSED task:AegisNNLabNightly") for l in lines), lines


def test_railway_fleet_stopped_on_purpose(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.run = lambda argv, t: (0, "Linked service aat-loop-hack3")
    monkeypatch.setattr(C, "RAILWAY_FLEET_STOPPED_REASON", "stopped on purpose (test)")
    r = SH.p_railway_fleet(ctx)
    assert r.verdict == "STOPPED_BY_OPERATOR" and "stopped on purpose" in r.detail


def test_u_plan_missing_plan_is_a_finding(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.optimus_dir / "pc_book" / str(ctx.now.date())).mkdir(parents=True)
    r = SH.p_u_plan(ctx)
    assert r.verdict == "STALE" and r.state == "DEGRADED" and "no plan written for session" in r.detail


def test_openclaw_bridge_heartbeat_read(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    hb = ctx.optimus_dir / "openclaw_api_bridge" / "heartbeat.json"
    assert SH.p_openclaw_api_bridge(ctx).verdict == "UNKNOWN"
    _w(hb, {"started_utc": (now - timedelta(hours=1)).isoformat(),
            "last_call_utc": (now - timedelta(minutes=5)).isoformat(),
            "last_tool": "aegis_health_full", "n_calls": 3, "n_errors": 0, "last_error": None})
    r = SH.p_openclaw_api_bridge(ctx)
    assert r.verdict == "ALIVE" and r.state == "ALIVE_PROGRESSING"
    _w(hb, {"last_call_utc": (now - timedelta(minutes=5)).isoformat(), "last_tool": "aegis_pi_get",
            "last_error": "HTTP 503", "n_calls": 4, "n_errors": 1})
    r = SH.p_openclaw_api_bridge(ctx)
    assert r.verdict == "STALE" and r.state == "DEGRADED" and "HTTP 503" in r.detail


def test_bridge_records_a_call_without_breaking_it(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ocb", REPO / "scripts" / "openclaw_api_bridge.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "HEARTBEAT", tmp_path / "hb.json")
    out = m.aegis_pi_get("../../etc")             # refused before any request
    assert "refused" in out
    hb = json.loads((tmp_path / "hb.json").read_text(encoding="utf-8"))
    assert hb["n_calls"] == 1 and hb["last_error"] is None and hb["last_refused"]


def test_decision_contract_leads_with_the_cause():
    c = {"candidate_set": {"n_candidates": 25, "n_considered": 2, "candidates_age_days": 0.1,
                           "excluded_by_gate": {"ranking score <= 0": 19, "NO_EVIDENCE": 4}}}
    assert SH._n_considered_cause(c).startswith("NOT a stale file")
    c["candidate_set"]["candidates_age_days"] = 40
    assert "STALE candidate file" in SH._n_considered_cause(c)
