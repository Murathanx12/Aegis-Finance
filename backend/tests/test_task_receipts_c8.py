"""C8 (2026-10-07): a scheduled task is judged by the receipt it must advance.

Every date is derived from `now` (protocol item 5). No machine details.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import system_health as SH
from backend.services import task_receipts as TR

REPO = Path(__file__).resolve().parents[2]


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
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now or _now(), repo=tmp_path,
                       prev_state=prev_state or {},
                       paths={"terminal_repo": tmp_path / "no_terminal"},
                       run=lambda argv, t: (None, "not installed"),
                       pid_cmdline=lambda pid: None)


def _task(name: str, **kw) -> dict:
    return {"TaskName": "\\" + name, "Scheduled Task State": "Enabled",
            "Last Run Time": "-", "Last Result": "0", "Next Run Time": "-", **kw}


# ─────────────────────────── 1. no task is UNKNOWN by omission

def _task_names_in_source() -> set[str]:
    """Every Aegis task NAME the repo registers or starts: a string literal
    `Aegis<Name>` on a line that also says TaskName / /TN / TASK / Register."""
    names: set[str] = set()
    roots = [REPO / "scripts", REPO / "backend" / "services", REPO / "nn_lab"]
    pat = re.compile(r"[\"'](Aegis[A-Z][A-Za-z0-9]+)[\"']")
    for root in roots:
        for f in root.rglob("*.py"):
            if "tests" in f.parts:
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in src.splitlines():
                if not re.search(r"TaskName|/TN|TASK|Register-ScheduledTask|schtasks", line):
                    continue
                names.update(pat.findall(line))
    return names


def test_every_task_the_repo_registers_has_a_declared_receipt():
    tk = ast.parse((REPO / "scripts" / "task_keeper.py").read_text(encoding="utf-8"))
    from scripts import task_keeper as K
    declared = set(K.CATCHUP_TASKS) | {getattr(K, n) for n in dir(K)
                                       if n.startswith("TASK_") and isinstance(getattr(K, n), str)}
    found = _task_names_in_source() | declared
    assert tk is not None and found, "the enumeration found no task at all -- a broken guard"
    missing = sorted(n for n in found if n not in TR.TASK_RECEIPT)
    assert not missing, f"tasks with no receipt reader (would read UNKNOWN): {missing}"


@pytest.mark.parametrize("name", sorted(TR.TASK_RECEIPT))
def test_each_declared_reader_is_callable_and_never_raises_on_an_empty_machine(tmp_path, name):
    spec = TR.TASK_RECEIPT[name]
    assert callable(spec.reader) and spec.receipt
    j = TR.judge(_ctx(tmp_path), name, _task(name), spec)
    assert j.state in TR.STATES
    assert not j.detail.startswith("receipt reader raised"), j.detail
    # nothing on disk is never ALIVE_PROGRESSING
    assert j.state != "ALIVE_PROGRESSING", (name, j.detail)


def test_every_declared_task_has_a_cadence_in_config():
    missing = [n for n, s in TR.TASK_RECEIPT.items()
               if not (s.retired or s.registered_only) and n not in C.HEALTH_TASK_CADENCE_H]
    assert not missing


def test_an_unmapped_scheduled_task_is_a_visible_unknown(tmp_path):
    j = TR.judge(_ctx(tmp_path), "AegisSomethingNew", _task("AegisSomethingNew"))
    assert j.state == "UNKNOWN" and "TASK_RECEIPT" in j.detail


# ─────────────────────────── 2. progress: same output too long => STALE

def test_same_substance_with_moving_stamps_goes_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    dj = ctx.optimus_dir / "dowjones"
    allowed_h = C.HEALTH_TASK_CADENCE_H["AegisReaderSupervisor"] * (1 + SH.GRACE)
    _jl(dj / "night_reader_supervisor.jsonl",
        [{"t": (now - timedelta(minutes=2)).isoformat(), "event": "tick",
          "page_loads_total": 500, "new_loads": 0}])
    first = (now - timedelta(hours=allowed_h * 4)).isoformat(timespec="seconds")
    import hashlib
    h = hashlib.sha256(b"500").hexdigest()[:16]
    ctx.prev_state = {"progress": {"AegisReaderSupervisor": {"hash": h, "first_seen_utc": first,
                                                             "n_same": 5}}}
    j = TR.judge(ctx, "AegisReaderSupervisor", _task("AegisReaderSupervisor"))
    assert j.state == "STALE" and "same output for" in j.detail, j.detail


def test_moving_substance_is_progressing_and_the_hash_is_recorded(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    _jl(ctx.optimus_dir / "dowjones" / "night_reader_supervisor.jsonl",
        [{"t": (now - timedelta(minutes=2)).isoformat(), "event": "tick", "page_loads_total": 501}])
    ctx.prev_state = {"progress": {"AegisReaderSupervisor": {"hash": "different", "n_same": 9,
                                                             "first_seen_utc": (now - timedelta(days=3)).isoformat()}}}
    j = TR.judge(ctx, "AegisReaderSupervisor", _task("AegisReaderSupervisor"))
    assert j.state == "ALIVE_PROGRESSING", j.detail
    assert ctx.new_state["progress"]["AegisReaderSupervisor"]["n_same"] == 1


def test_substance_ignores_clocks_and_ids():
    a = TR.substance({"utc": "x", "run_id": "1", "n": 3, "inner": {"started_utc": "y", "k": 1}})
    b = TR.substance({"utc": "z", "run_id": "2", "n": 3, "inner": {"started_utc": "w", "k": 1}})
    assert a == b and TR.substance({"n": 4}) != TR.substance({"n": 3})


def test_old_receipt_is_stale_by_its_own_stamp(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    old = now - timedelta(days=3)
    _w(ctx.optimus_dir / "digest" / f"world_digest_{old:%Y%m%dT%H%M%SZ}.json",
       {"stamp": f"{old:%Y%m%dT%H%M%SZ}", "n_items": 4})
    j = TR.judge(ctx, "AegisWorldDigest", _task("AegisWorldDigest"))
    assert j.state == "STALE" and "old" in j.detail


# ─────────────────────────── 3. REFUSED with its reason

def test_a_receipt_that_refuses_shows_refused_with_the_reason(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    st = now - timedelta(minutes=30)
    _w(ctx.optimus_dir / "contest" / "live" / "refusals" / f"live_gate_{st.date()}_{st:%Y%m%dT%H%M%SZ}.json",
       {"receipt": "contest_live_gate", "written_utc": f"{st:%Y%m%dT%H%M%SZ}", "result": "REFUSED",
        "reasons": ["contest/REGISTERED is missing"]})
    j = TR.judge(ctx, "AegisContestDesk", _task("AegisContestDesk"))
    assert j.state == "REFUSED" and j.verdict == "REFUSED"
    assert "REGISTERED is missing" in j.detail


def test_hyp_lab_stop_receipt_is_refused_not_unknown(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(hours=2)
    _w(ctx.optimus_dir / "hyp_lab" / "receipts" / f"nightly_{t:%Y%m%dT%H%M%SZ}.json",
       {"started_utc": t.isoformat(), "status": "REFUSED", "reason": "STOP file present 3 d"})
    j = TR.judge(ctx, "AegisHypLabNightly", _task("AegisHypLabNightly"))
    assert j.state == "REFUSED" and "STOP file" in j.detail


def test_analyst_pull_refuses_while_the_us_session_is_open(tmp_path):
    from scripts import task_keeper as K
    # a weekday 15:00 UTC is inside 09:30-16:00 ET in either DST state
    d = _now().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    days, _ = SH._sessions(d - timedelta(days=10), d)
    s = days[-1]
    open_ = datetime(s.year, s.month, s.day, 16, 0, tzinfo=timezone.utc)
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


# ─────────────────────────── 4. idle windows are not DEAD

def _non_session_day(now: datetime):
    d = SH._et(now).date()
    for i in range(0, 10):
        c = d - timedelta(days=i)
        if not SH._sessions(c, c)[0]:
            return c
    raise AssertionError("no non-session day in 10")


def test_weekend_reads_idle_expected_for_a_session_only_task(tmp_path):
    day = _non_session_day(_now())
    now = datetime(day.year, day.month, day.day, 18, 0, tzinfo=timezone.utc)
    prev = [s for s in SH._sessions(day - timedelta(days=7), day)[0] if s < day][-1]
    t = datetime(prev.year, prev.month, prev.day, 14, 48, tzinfo=timezone.utc)
    ctx = _ctx(tmp_path, now=now)
    _w(ctx.optimus_dir / "paper_accounts" / "fleet_manager" / "runs" / f"run_{t:%Y%m%dT%H%M%SZ}-aaaaaa.json",
       {"pass": "open", "started_utc": t.isoformat(), "finished_utc": t.isoformat(), "accounts": []})
    j = TR.judge(ctx, "AegisFleetManagerOpen", _task("AegisFleetManagerOpen"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and j.verdict == "ALIVE", j.detail
    assert "no XNYS session" in j.detail


def test_outside_window_receipt_reads_idle_expected(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    t = now - timedelta(minutes=10)
    _w(ctx.optimus_dir / "straddle_forward" / "runs" / f"pass_{t:%Y%m%dT%H%M%SZ}.json",
       {"stamp": f"{t:%Y%m%dT%H%M%SZ}", "now_utc": t.isoformat(), "state": "OBSERVE_ONLY",
        "window": {"in_window": False, "window_et": ["10:45", "15:30"], "reason": "BEFORE_WINDOW"}})
    j = TR.judge(ctx, "AegisStraddleForward", _task("AegisStraddleForward"))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "outside its declared window" in j.detail


def test_a_never_run_task_before_its_first_day_is_idle_not_dead(tmp_path):
    first = TR._contest_live_first_day()
    if first is None:
        pytest.skip("contest calendar not importable")
    now = datetime(first.year, first.month, first.day, tzinfo=timezone.utc) - timedelta(days=2)
    j = TR.judge(_ctx(tmp_path, now=now), "AegisContestDesk",
                 _task("AegisContestDesk", **{"Last Result": TR.NEVER_RAN_RC}))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "not yet due" in j.detail


def test_a_declared_task_missing_from_the_scheduler_is_not_alive(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
    _w(ctx.optimus_dir / "data_catalog" / f"catalog_{now:%Y%m%dT%H%M%SZ}.json",
       {"utc": now.isoformat(), "summary": {"n": 1}})
    assert TR.judge(ctx, "AegisDataCatalog", None).state == "DEGRADED"
    (tmp_path / "b").mkdir()
    assert TR.judge(_ctx(tmp_path / "b"), "AegisDataCatalog", None).state == "DEAD"


def test_retired_task_names_the_delete_command(tmp_path):
    j = TR.judge(_ctx(tmp_path), "AegisWRDSPullNight", _task("AegisWRDSPullNight"))
    assert j.state == "DEGRADED" and "schtasks /Delete /TN AegisWRDSPullNight /F" in j.detail


# ─────────────────────────── 5. nn_lab contract wired

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


# ─────────────────────────── 6. the probe surface

def test_task_rows_carry_state_and_coarse_verdict_and_no_unknown_for_mapped(tmp_path, monkeypatch):
    now = _now()
    ctx = _ctx(tmp_path, now=now)
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


def test_decision_contract_names_eligibility_not_stale_file():
    c = {"candidate_set": {"n_candidates": 25, "n_considered": 2, "candidates_age_days": 0.1,
                           "excluded_by_gate": {"ranking score <= 0": 19, "NO_EVIDENCE": 4}}}
    assert SH._n_considered_cause(c).startswith("NOT a stale file")
    c["candidate_set"]["candidates_age_days"] = 40
    assert "STALE candidate file" in SH._n_considered_cause(c)
