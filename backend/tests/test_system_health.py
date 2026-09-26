"""Health probes: every probe must be able to go red.

Review 2026-09-26 §4.4. Every date is derived from `now` (protocol item 5):
no fixture encodes a calendar moment.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import system_health as SH


# ───────────────────────────────────────────────────────────────── fixtures

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _w(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def _ctx(tmp_path: Path, *, now: datetime | None = None, run=None, http=None,
         cmdline=None, prev_state=None) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(
        optimus_dir=od, now=now or _now(), repo=tmp_path,
        prev_state=prev_state or {},
        paths={"funnel": tmp_path / "funnel_night10.json",
               "optimus_health": tmp_path / "no_optimus" / "aegis-health-latest.md",
               "llama_owner": tmp_path / "llama_owner.json"},
        run=run or (lambda argv, t: (None, "FileNotFoundError: not installed")),
        http_json=http or (lambda url, t: (None, 0.0, "URLError: refused")),
        pid_cmdline=cmdline or (lambda pid: None),
        railway_url="http://railway.invalid")


def _rows(out) -> dict:
    return out if isinstance(out, dict) else {"_": out}


# ─────────────────────────────── 1. missing evidence => never ALIVE (all probes)

@pytest.mark.parametrize("probe", SH.PROBES, ids=[p.name for p in SH.PROBES])
def test_every_probe_with_its_evidence_absent_is_not_alive(tmp_path, probe):
    ctx = _ctx(tmp_path)
    out = probe.fn(ctx)
    for name, r in _rows(out).items():
        assert r.verdict != "ALIVE", f"{probe.name}/{name} ALIVE on no evidence: {r.detail}"
        if probe.name != "railway_backend":           # an unanswering endpoint is DEAD
            assert r.verdict == "UNKNOWN", f"{probe.name}/{name}: {r.verdict} {r.detail}"
        assert r.detail, "UNKNOWN must say why"


def test_a_probe_that_raises_is_unknown_with_the_exception_class(tmp_path, monkeypatch):
    def boom(ctx):
        raise ZeroDivisionError("x")
    monkeypatch.setattr(SH, "PROBES", (SH.Probe("boom", "pc", timedelta(days=1), "-", boom),))
    rows = SH.run_probes(_ctx(tmp_path))
    assert rows[0]["verdict"] == "UNKNOWN" and "ZeroDivisionError" in rows[0]["detail"]


# ─────────────────────────────────────────────── 2. the lab: pid must answer

def _lab(tmp_path, utc: datetime, pid=4242, loops=None):
    _w(tmp_path / "optimus" / "lab_status.json",
       {"utc": _iso(utc), "pid": pid, "heartbeat_minutes": 5,
        "periods_minutes": {"news_pull": 15}, "loops": loops or {}})


def test_fresh_lab_status_with_a_dead_pid_is_dead(tmp_path):
    _lab(tmp_path, _now())
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: None))
    assert r.verdict == "DEAD"


def test_fresh_lab_status_with_a_reused_pid_is_dead(tmp_path):
    _lab(tmp_path, _now())
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: "notepad.exe foo.txt"))
    assert r.verdict == "DEAD" and "reused" in r.detail


def test_lab_pid_answers_but_heartbeat_is_old_is_stale(tmp_path):
    _lab(tmp_path, _now() - timedelta(hours=1))
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: "python -m scripts.always_on_lab"))
    assert r.verdict == "STALE"


def test_lab_alive_needs_both_the_pid_and_the_heartbeat(tmp_path):
    _lab(tmp_path, _now() - timedelta(minutes=2))
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: r"C:\venv\python.exe -m scripts.always_on_lab"))
    assert r.verdict == "ALIVE" and "always_on_lab" in r.proof


def test_a_lab_loop_that_errored_or_went_quiet_is_stale(tmp_path):
    now = _now()
    _lab(tmp_path, now, loops={
        "news_pull": {"last_tick_utc": _iso(now - timedelta(hours=2)), "status": "ok"},
        "status": {"last_tick_utc": _iso(now), "status": "error", "cadence_minutes": 5}})
    out = SH.p_lab_loops(_ctx(tmp_path))
    assert out["news_pull"].verdict == "STALE"
    assert out["status"].verdict == "STALE"


# ───────────────────────────────────────────────────── 3. the bars panel

def _bars(tmp_path, newest):
    import pandas as pd
    p = tmp_path / "optimus" / "prices_2025_26" / "bars.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    days, _ = SH._sessions(newest - timedelta(days=20), newest)
    pd.DataFrame({"symbol": "AAA", "date": pd.to_datetime(days),
                  "close": 1.0}).to_parquet(p, index=False)


def test_bars_current_to_the_last_session_is_alive(tmp_path):
    now = _now()
    _bars(tmp_path, SH.last_closed_session(now))
    r = SH.p_bars_panel(_ctx(tmp_path, now=now))
    assert r.verdict == "ALIVE" and "0 session(s) behind" in r.detail


def test_bars_beyond_the_session_limit_are_stale(tmp_path):
    now = _now()
    last = SH.last_closed_session(now)
    limit = SH._bars_limit()
    days, _ = SH._sessions(last - timedelta(days=30), last)
    _bars(tmp_path, days[-(limit + 2)])                  # limit+1 sessions behind
    r = SH.p_bars_panel(_ctx(tmp_path, now=now))
    assert r.verdict == "STALE"
    assert f"{limit + 1} session(s) behind" in r.detail


def test_bars_one_session_behind_prints_its_age(tmp_path):
    now = _now()
    last = SH.last_closed_session(now)
    days, _ = SH._sessions(last - timedelta(days=10), last)
    _bars(tmp_path, days[-2])
    r = SH.p_bars_panel(_ctx(tmp_path, now=now))
    assert "1 session(s) behind" in r.detail
    assert r.verdict == ("ALIVE" if SH._bars_limit() >= 1 else "STALE")


def test_the_module_never_reads_an_mtime():
    """AST guard (docstrings skipped, CLAUDE.md protocol item 10)."""
    tree = ast.parse(Path(SH.__file__).read_text(encoding="utf-8"))
    banned = {"st_mtime", "getmtime", "st_ctime", "getctime", "stat", "lstat"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned:
            hits.append((node.attr, node.lineno))
        if isinstance(node, ast.Name) and node.id in banned:
            hits.append((node.id, node.lineno))
    assert not hits, hits


# ───────────────────────────────── 4. the forecast ledger and its grader

def _ledger(tmp_path, rows):
    p = tmp_path / "optimus" / "predictions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_fresh_forecasts_with_a_grader_that_stopped_is_stale(tmp_path):
    now = _now()
    _ledger(tmp_path, [
        {"made_at": _iso(now), "resolves_after": str((now + timedelta(days=5)).date()),
         "resolved_at": None},
        {"made_at": _iso(now - timedelta(days=20)),
         "resolves_after": str((now - timedelta(days=6)).date()), "resolved_at": None},
        {"made_at": _iso(now - timedelta(days=30)),
         "resolves_after": str((now - timedelta(days=12)).date()),
         "resolved_at": str((now - timedelta(days=5)).date())}])
    ctx = _ctx(tmp_path, now=now)
    assert SH.p_u_forecast(ctx).verdict == "ALIVE"
    g = SH.p_forecast_grader(ctx)
    assert g.verdict == "STALE" and "has not moved" in g.detail


def test_a_ledger_that_did_not_grow_for_a_day_is_stale(tmp_path):
    now = _now()
    _ledger(tmp_path, [{"made_at": _iso(now - timedelta(days=3))}] * 4)
    prev = {"ledger": {"rows": 4, "utc": _iso(now - timedelta(days=1, hours=1))}}
    r = SH.p_forecast_ledger(_ctx(tmp_path, now=now, prev_state=prev))
    assert r.verdict == "STALE" and r.delta == 0 and "DEGRADED" in r.detail


def test_a_ledger_that_grew_is_alive_with_its_delta(tmp_path):
    now = _now()
    _ledger(tmp_path, [{"made_at": _iso(now)}] * 6)
    prev = {"ledger": {"rows": 4, "utc": _iso(now - timedelta(hours=3))}}
    ctx = _ctx(tmp_path, now=now, prev_state=prev)
    r = SH.p_forecast_ledger(ctx)
    assert r.verdict == "ALIVE" and r.delta == 2
    assert ctx.new_state["ledger"]["rows"] == 6


# ───────────────────────────────────────────── 5. the Railway backend

def test_railway_asleep_and_not_fresh_is_stale(tmp_path):
    body = {"deploy": {"commit": "abc", "uptime_seconds": 13, "started_at": _iso(_now())},
            "scheduler": {"nav": {"all_fresh": False, "expected_nav_date": "x",
                                  "lanes": {"a": {"last_nav_date": "y"}}}}}
    r = SH.p_railway_backend(_ctx(tmp_path, http=lambda u, t: (body, 10.1, None)))
    assert r.verdict == "STALE" and "asleep" in r.detail


def test_railway_fresh_and_up_for_days_is_alive(tmp_path):
    body = {"deploy": {"commit": "abc", "uptime_seconds": 3 * 86400,
                       "started_at": _iso(_now() - timedelta(days=3))},
            "scheduler": {"nav": {"all_fresh": True, "lanes": {}}}}
    r = SH.p_railway_backend(_ctx(tmp_path, http=lambda u, t: (body, 0.3, None)))
    assert r.verdict == "ALIVE"


# ───────────────────────────────────────── old evidence => not ALIVE, per probe

def test_telegram_pid_dead_is_dead_and_old_heartbeat_is_stale(tmp_path):
    tg = tmp_path / "optimus" / "telegram"
    _w(tg / "agent.pid", "\ufeff73584\r\n")
    _w(tg / "update_offset.json", {"at": _iso(_now() - timedelta(days=3))})
    assert SH.p_telegram_agent(_ctx(tmp_path)).verdict == "DEAD"
    _w(tg / "heartbeat.json", {"utc": _iso(_now() - timedelta(hours=2)), "pid": 73584})
    r = SH.p_telegram_agent(_ctx(tmp_path, cmdline=lambda p: "python -m scripts.telegram_agent --serve"))
    assert r.verdict == "STALE"


def test_telegram_pid_alive_without_a_heartbeat_is_unknown_not_alive(tmp_path):
    tg = tmp_path / "optimus" / "telegram"
    _w(tg / "agent.pid", "123")
    r = SH.p_telegram_agent(_ctx(tmp_path, cmdline=lambda p: "python -m scripts.telegram_agent"))
    assert r.verdict == "UNKNOWN"


def test_sim_running_with_a_dead_pid_is_dead(tmp_path):
    _w(tmp_path / "optimus" / "sim" / "session.json",
       {"id": "s1", "state": "RUNNING", "pid": 99, "heartbeat": _iso(_now())})
    assert SH.p_sim_session(_ctx(tmp_path)).verdict == "DEAD"


def test_no_sim_during_us_session_hours_is_dead(tmp_path):
    last = SH.last_closed_session(_now())
    in_session = datetime(last.year, last.month, last.day, 17, 0, tzinfo=timezone.utc)
    _w(tmp_path / "optimus" / "sim" / "session.json",
       {"id": "s1", "state": "STOPPED", "ended": _iso(in_session - timedelta(hours=10))})
    assert SH.p_sim_session(_ctx(tmp_path, now=in_session)).verdict == "DEAD"


def test_openclaw_without_operator_scope_is_stale_and_down_is_dead(tmp_path):
    ok = "\x1b[32mRuntime: running\x1b[0m\nConnectivity probe: ok\nCapability: connected-no-operator-scope\n"
    assert SH.p_openclaw_gateway(_ctx(tmp_path, run=lambda a, t: (0, ok))).verdict == "STALE"
    assert SH.p_openclaw_gateway(_ctx(tmp_path, run=lambda a, t: (1, "Runtime: stopped"))).verdict == "DEAD"


def test_old_optimus_page_is_stale(tmp_path):
    t = (_now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    _w(tmp_path / "no_optimus" / "aegis-health-latest.md", f"# h\ngenerated {t} UTC\n")
    assert SH.p_optimus_brain(_ctx(tmp_path)).verdict == "STALE"


def test_old_funnel_is_stale(tmp_path):
    _w(tmp_path / "funnel_night10.json",
       {"generated_at": _iso(_now() - timedelta(days=30)), "candidates": []})
    assert SH.p_u_funnel(_ctx(tmp_path)).verdict == "STALE"


def test_review_missing_for_the_last_session_is_stale(tmp_path):
    _w(tmp_path / "optimus" / "review" / "review_2000-01-03.json", {"asof": "2000-01-03"})
    assert SH.p_u_review(_ctx(tmp_path)).verdict == "STALE"


def test_old_pc_book_receipts_are_stale(tmp_path):
    now = _now()
    old = SH.last_closed_session(now) - timedelta(days=14)
    day = tmp_path / "optimus" / "pc_book" / str(old)
    _w(day / "ranking.json", {"asof": str(old)})
    _w(day / "intended_book.json", {"t": _iso(now - timedelta(days=14)), "asof": str(old),
                                    "acting": True})
    _w(day / "learn_distil.json", {"status": "DEGRADED rc 3", "ran_utc": _iso(now)})
    ctx = _ctx(tmp_path, now=now)
    assert SH.p_ranking(ctx).verdict == "STALE"
    assert SH.p_u_plan(ctx).verdict == "STALE"
    assert SH.p_learn_rota(ctx).verdict == "STALE"


def test_plan_over_the_gross_cap_is_stale(tmp_path):
    now = _now()
    last = SH.last_closed_session(now)
    _w(tmp_path / "optimus" / "pc_book" / str(last) / "intended_book.json",
       {"t": _iso(now), "asof": str(last), "invested_frac": 0.9})
    r = SH.p_u_plan(_ctx(tmp_path, now=now))
    assert r.verdict == "STALE" and "exceed cap" in r.detail


def test_old_or_errored_daily_pass_and_iif1_and_contract_are_stale(tmp_path):
    now = _now()
    od = tmp_path / "optimus"
    d = (now - timedelta(days=3)).date()
    _w(od / f"night_factory_{d}" / f"daily_pass_{d}.json",
       {"date": str(d), "finished_utc": _iso(now - timedelta(days=3)), "steps": []})
    assert SH.p_daily_pass(_ctx(tmp_path, now=now)).verdict == "STALE"
    t = now.date()
    _w(od / f"night_factory_{t}" / f"daily_pass_{t}.json",
       {"date": str(t), "steps": [{"step": "x", "status": "error", "utc": _iso(now)}]})
    assert SH.p_daily_pass(_ctx(tmp_path, now=now)).verdict == "STALE"
    _w(od / "iif1_nights" / "2000-01-03.json", {"status": "ok"})
    assert SH.p_iif1_night(_ctx(tmp_path, now=now)).verdict == "STALE"
    _w(od / "decisions" / f"{d}.json", {"written_utc": _iso(now - timedelta(days=3))})
    assert SH.p_decision_contract(_ctx(tmp_path, now=now)).verdict == "STALE"


def test_old_news_dowjones_reaper_and_red_sources_are_not_alive(tmp_path):
    now = _now()
    od = tmp_path / "optimus"
    _w(od / "news_corpus" / "_receipts" / "20000101T000000Z_ALL.json",
       {"written_utc": _iso(now - timedelta(hours=5)), "red": [], "refused": []})
    assert SH.p_news_collectors(_ctx(tmp_path, now=now)).verdict == "STALE"
    _w(od / "news_corpus" / "_receipts" / "20990101T000000Z_ALL.json",
       {"written_utc": _iso(now), "red": ["gdelt"], "refused": []})
    assert SH.p_news_collectors(_ctx(tmp_path, now=now)).verdict == "STALE"
    _w(od / "dowjones" / "feeds_2000-01-01.json", {"generated_utc": _iso(now - timedelta(days=4))})
    assert SH.p_dowjones_feeds(_ctx(tmp_path, now=now)).verdict == "STALE"
    _w(od / "llama_reaper.log.jsonl", json.dumps({"t": _iso(now - timedelta(hours=1)),
                                                   "action": "tick"}) + "\n")
    assert SH.p_llama_reaper(_ctx(tmp_path, now=now)).verdict == "STALE"


def test_social_refused_source_is_unknown(tmp_path):
    _lab(tmp_path, _now(), loops={"social_pull": {
        "last_tick_utc": _iso(_now()), "cadence_minutes": 360,
        "per_source": [{"source": "reddit", "status": "REFUSED", "refused": "REDDIT_KEYS_ABSENT"},
                       {"source": "youtube", "status": "OK", "rows": 3}]}})
    out = SH.p_social_sources(_ctx(tmp_path))
    assert out["reddit"].verdict == "UNKNOWN" and out["youtube"].verdict == "ALIVE"


def test_llama_waiting_units_over_an_hour_is_stale(tmp_path):
    now = _now()
    _lab(tmp_path, now, loops={"l2_typing": {"status": "PENDING_MODEL",
                                             "last_tick_utc": _iso(now)}})
    prev = {"pending_model_since": _iso(now - timedelta(hours=3))}
    assert SH.p_llama_server(_ctx(tmp_path, now=now, prev_state=prev)).verdict == "STALE"


def test_git_ahead_and_ci_red_are_stale(tmp_path):
    def run(argv, t):
        if "rev-list" in argv:
            return 0, "3\n"
        if "rev-parse" in argv:
            return 0, "deadbeef\n"
        return 0, json.dumps([{"conclusion": "failure", "status": "completed",
                               "createdAt": _iso(_now()), "workflowName": "CI"}])
    ctx = _ctx(tmp_path, run=run)
    assert SH.p_git(ctx).verdict == "STALE"
    assert SH.p_ci(ctx).verdict == "STALE"


def test_railway_cli_linked_to_a_retired_service_is_unknown(tmp_path):
    r = SH.p_railway_fleet(_ctx(tmp_path, run=lambda a, t: (0, "Linked service\n\naat-loop-hack3\n")))
    assert r.verdict == "UNKNOWN" and "aat-loop-hack3" in r.detail


# ─────────────────────────────────────────────────────────── exit codes

def _r(v):
    return {"verdict": v}


@pytest.mark.parametrize("vs,rc", [
    (["ALIVE", "DEAD", "STALE"], 1), (["ALIVE", "STALE", "UNKNOWN"], 2),
    (["UNKNOWN", "UNKNOWN"], 3), (["ALIVE", "UNKNOWN"], 0), (["ALIVE"], 0)])
def test_exit_codes(vs, rc):
    assert SH.exit_code([_r(v) for v in vs]) == rc


def test_rows_sort_dead_stale_unknown_alive(tmp_path):
    rows = SH.run_probes(_ctx(tmp_path))
    order = [SH.VERDICT_ORDER[r["verdict"]] for r in rows]
    assert order == sorted(order)


def test_cli_writes_a_receipt_and_returns_the_exit_code(tmp_path, monkeypatch):
    from scripts import health_probe as HP
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: ctx)
    rc = HP.main(["--only", "bars_panel,git"])
    hd = ctx.optimus_dir / "health"
    receipts = list(hd.glob("health_*T*Z.json"))
    assert len(receipts) == 1 and (hd / "HEALTH.md").exists()
    assert (hd / "health_index.jsonl").exists() and (hd / "_state.json").exists()
    body = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert rc == body["exit_code"] == 3                  # both UNKNOWN on an empty dir


# ─────────────────────────────────────────────────────────── the API block

def test_api_block_shape_and_request_mode_never_shells_out(tmp_path, monkeypatch):
    calls = []
    ctx = _ctx(tmp_path, run=lambda a, t: calls.append(a) or (0, ""))

    def make(**kw):
        ctx.allow_proc = kw.get("allow_proc", True)
        return ctx
    monkeypatch.setattr(SH, "make_ctx", make)
    SH._API_CACHE.clear()
    b = SH.api_block()
    SH._API_CACHE.clear()
    assert set(b) >= {"generated_utc", "source", "counts", "exit_code", "rows"}
    assert b["rows"] and set(b["rows"][0]) >= {"name", "verdict", "evidence_utc", "detail", "proof"}
    assert not calls, f"an API request shelled out: {calls}"
    names = {r["name"]: r for r in b["rows"]}
    assert names["always_on_lab"]["verdict"] == "UNKNOWN"
    assert "not computed on a request" in names["always_on_lab"]["detail"]


def test_health_full_carries_the_subsystems_block(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    stub = {"generated_utc": "x", "source": "pc_request", "counts": {}, "exit_code": 0, "rows": []}
    monkeypatch.setattr(SH, "api_block", lambda **kw: stub)
    body = TestClient(app).get("/api/health/full").json()
    assert body["subsystems"] == stub


def test_non_alive_lines_put_dead_and_stale_first(tmp_path, monkeypatch):
    rec = {"generated_utc": _iso(_now()), "rows": [
        {"name": "a", "verdict": "ALIVE", "detail": "fine"},
        {"name": "b", "verdict": "DEAD", "detail": "gone", "proof": "pid 1"},
        {"name": "c", "verdict": "UNKNOWN", "detail": "?"}]}
    monkeypatch.setattr(SH, "newest_receipt", lambda hd=None: rec)
    lines = SH.non_alive_lines()
    assert "1 DEAD/STALE, 1 UNKNOWN of 3" in lines[0]
    assert lines[1].startswith("- DEAD b -- gone") and len(lines) == 2
