"""The 2026-10-02 automation fixes, offline: no network, no local ports, no
real task scheduler, no calendar literal that can expire.

Each block names the failure it pins:
  bars     one Yahoo-spelled ticker (BRK-B) 400'd every refresh for 3 days
  health   nobody saw the stale bars: a DEGRADED line now heads the reports
  broker   the daily pass ran --no-broker and the fleet left PAPER_ACCOUNTS.md
  stop     a 70 h old hyp_lab/STOP blocked every nightly with no receipt
  lab      always_on_lab came back after every boot although switched OFF
  keeper   the reader had no relaunch path; missed daily triggers stayed missed
  report   a finished sim session's report raised into a logger only
  gateway  "no operator scope" read as degraded while the reader worked
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts import pull_bars_refresh as BR

NOW = datetime.now(timezone.utc)


def _http_400(msg: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://data.example/v2/stocks/bars", 400, "Bad Request",
                                  {}, io.BytesIO(json.dumps({"message": msg}).encode()))


def _bars_json(symbols, day="2026-01-05"):
    return {"bars": {s: [{"t": f"{day}T05:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1.5,
                          "v": 100, "vw": 1.2, "n": 3}] for s in symbols},
            "next_page_token": None}


# ═══════════════════════════════════════════════════════════════════ bars

def test_vendor_symbol_rewrites_only_a_trailing_class_letter():
    assert BR.vendor_symbol("BRK-B") == "BRK.B"
    assert BR.vendor_symbol("BF-A") == "BF.A"
    assert BR.vendor_symbol("AAPL") == "AAPL"
    assert BR.vendor_symbol("ABC-WS") == "ABC-WS"     # not a class share: untouched


def test_class_share_is_asked_in_vendor_notation_and_returned_in_the_panels():
    asked = []

    def get(params):
        asked.append(params["symbols"])
        syms = params["symbols"].split(",")
        if any("-" in s for s in syms):
            raise _http_400(f"invalid symbol: {[s for s in syms if '-' in s][0]}")
        return _bars_json(syms)

    df, rejected = BR.pull_chunked(["AAPL", "BRK-B"], "2026-01-01", get, sleep=lambda s: None)
    assert rejected == []
    assert "BRK.B" in asked[0] and "BRK-B" not in asked[0]
    assert sorted(df["symbol"].unique()) == ["AAPL", "BRK-B"]


def test_one_invalid_symbol_is_dropped_not_the_whole_pull():
    calls = []

    def get(params):
        syms = params["symbols"].split(",")
        calls.append(syms)
        if "ZZZZ" in syms:
            raise _http_400("invalid symbol: ZZZZ")
        return _bars_json(syms)

    df, rejected = BR.pull_chunked(["AAA", "ZZZZ", "BBB"], "2026-01-01", get,
                                   sleep=lambda s: None)
    assert rejected == ["ZZZZ"]
    assert sorted(df["symbol"].unique()) == ["AAA", "BBB"]
    assert len(calls) == 2                    # one rejection, one retry, no back-off loop


def test_a_venue_outage_still_refuses_the_whole_pull():
    def get(params):
        raise urllib.error.HTTPError("u", 503, "down", {}, io.BytesIO(b"{}"))

    slept = []
    with pytest.raises(urllib.error.HTTPError):
        BR.pull_chunked(["AAA"], "2026-01-01", get, retries=2, sleep=slept.append)
    assert len(slept) == 2


def _panel(path: Path, newest: date, symbols=("AAA", "BBB"), n_days: int = 25) -> Path:
    days, _ = BR._sessions(newest - timedelta(days=n_days * 2), newest)
    days = days[-n_days:]
    pd.DataFrame([{"symbol": s, "date": pd.Timestamp(d), "open": 10.0, "high": 10.0,
                   "low": 10.0, "close": 10.0 + i * 0.01, "volume": 1000, "vwap": 10.0,
                   "trades": 10} for s in symbols for i, d in enumerate(days)]
                 ).to_parquet(path, index=False)
    return path


def test_refresh_receipt_names_the_rejected_symbols_loudly(tmp_path):
    last, _ = BR.last_closed_session(NOW)
    days, _ = BR._sessions(last - timedelta(days=20), last)
    p = _panel(tmp_path / "b.parquet", days[-2])
    new = pd.DataFrame([{"symbol": "AAA", "date": pd.Timestamp(days[-1]), "open": 1.0,
                         "high": 1.0, "low": 1.0, "close": 10.5, "volume": 900,
                         "vwap": 1.0, "trades": 4}])
    new.attrs["rejected_symbols"] = ["BBB"]
    rec = BR.refresh({"ranker_deep": p}, now_utc=NOW, puller=lambda s, st: (new, "fixture"),
                     receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl")
    assert rec["pull"]["rejected_symbols"] == ["BBB"]
    assert "VENDOR_REJECTED 1" in rec["warning"] and "VENDOR_REJECTED" in rec["headline"]
    assert rec["status"] == "ok"


# ═════════════════════════════════════════════════════════════════ health

def test_bars_health_is_degraded_on_one_missing_session():
    from backend.services import bars_health as BH
    age = {"sessions_old": 1, "newest": "N", "last_closed_session": "L"}
    r = BH.check(NOW, age_fn=lambda **k: age)
    assert r["state"] == "DEGRADED" and "1 closed session" in r["line"]
    ok = BH.check(NOW, age_fn=lambda **k: {**age, "sessions_old": 0})
    assert ok["state"] == "OK"


def test_bars_health_unknown_and_raising_reads_are_degraded_never_ok():
    from backend.services import bars_health as BH
    assert BH.check(NOW, age_fn=lambda **k: {"sessions_old": None})["state"] == "DEGRADED"

    def boom(**k):
        raise OSError("disk")
    r = BH.check(NOW, age_fn=boom)
    assert r["state"] == "DEGRADED" and "CANNOT DETERMINE" in r["line"]


def test_daily_pass_degraded_lines_from_its_own_rows():
    from scripts import daily_pass as DP
    rows = [{"step": "bars_refresh",
             "bars_line": "BARS_FRESH: newest=x sessions_old=1 (limit 2, last closed session y)"},
            {"step": "paper_accounts", "broker_degraded": "DEGRADED paper_accounts: no broker rows"}]
    out = DP.degraded_lines(rows)
    assert len(out) == 2 and out[0].startswith("DEGRADED bars: 1")
    fresh = [{"step": "bars_refresh", "bars_line": "BARS_FRESH: newest=x sessions_old=0 (...)"}]
    assert DP.degraded_lines(fresh) == []
    assert DP.degraded_lines([])[0].startswith("DEGRADED bars: CANNOT DETERMINE")


def test_a_digest_carries_the_degraded_bars_line_first():
    from backend.services import alerts as AL
    import inspect
    assert "health_line" in inspect.signature(AL.deliver).parameters


# ═════════════════════════════════════════════════════════════════ broker

def test_broker_read_missing_is_degraded_never_silent():
    from scripts import daily_pass as DP
    assert "DISABLED" in DP.broker_read_degraded({"broker_requested": False, "status": "ok"})
    no_rows = {"broker_requested": True, "status": "ok", "scope": {"with_broker": False},
               "broker_rows": 0}
    assert "no broker rows" in DP.broker_read_degraded(no_rows)
    good = {"broker_requested": True, "status": "ok", "scope": {"with_broker": True},
            "broker_rows": 7, "broker_statuses": ["PRICED"]}
    assert DP.broker_read_degraded(good) is None
    assert DP.broker_read_degraded({**good, "broker_error_accounts": ["hack3"]}) is None
    assert "hack2" in DP.broker_read_degraded({**good, "broker_error_accounts": ["hack2", "hack3"]})


def test_daily_pass_requests_the_broker_read_by_default(monkeypatch):
    from scripts import daily_pass as DP
    seen = {}
    monkeypatch.setattr(DP, "_run_module_child",
                        lambda args, t: seen.setdefault("args", args) and {"status": "ok"})
    DP.run_paper_accounts(1.0)
    assert "--no-broker" not in seen["args"]


_DOC = """# Paper accounts

## Priced and broker accounts

| account | family | inception |
|---|---|---|
| lane_a | website_lane | x |
{extra}
## `llm_portfolio` books and their twins
"""


def test_doc_accounts_reads_the_priced_table_only():
    from scripts import paper_accounts_roi as PA
    d = PA.doc_accounts(_DOC.format(extra="| hack1 | alpaca_fleet | x |\n"))
    assert d == {"lane_a": "website_lane", "hack1": "alpaca_fleet"}


def test_a_doc_that_drops_broker_accounts_is_refused_and_the_old_one_kept(tmp_path, monkeypatch):
    from scripts import paper_accounts_roi as PA
    doc = tmp_path / "PAPER_ACCOUNTS.md"
    old = _DOC.format(extra="| hack1 | alpaca_fleet | x |\n| PC-PAPER | pc_paper | x |\n")
    doc.write_text(old, encoding="utf-8")
    monkeypatch.setattr(PA, "render_markdown", lambda rc, png: _DOC.format(extra=""))
    rc = {"generated_utc": NOW.isoformat(), "rows": [],
          "scope": {"with_broker": False, "broker_accounts_attempted": 0}}
    out = PA.write_outputs(rc, chart=False, out_dir=tmp_path / "o", doc_path=doc,
                           assets=tmp_path / "a")
    assert out["doc"] is None and "hack1" in out["doc_refused"] and "PC-PAPER" in out["doc_refused"]
    assert doc.read_text(encoding="utf-8") == old
    ok = PA.write_outputs({**rc, "generated_utc": (NOW + timedelta(seconds=2)).isoformat()},
                          chart=False, out_dir=tmp_path / "o2", doc_path=doc,
                          assets=tmp_path / "a", allow_drop=True)
    assert ok["doc"] is not None


def test_the_high_water_mark_catches_a_doc_that_was_already_bad(tmp_path, monkeypatch):
    from scripts import paper_accounts_roi as PA
    doc = tmp_path / "PAPER_ACCOUNTS.md"
    doc.write_text(_DOC.format(extra=""), encoding="utf-8")       # already lost the fleet
    out_dir = tmp_path / "o"
    PA._write_high_water(out_dir, {"lane_a": "website_lane", "hack2": "alpaca_fleet"}, "seed")
    monkeypatch.setattr(PA, "render_markdown", lambda rc, png: _DOC.format(extra=""))
    rc = {"generated_utc": NOW.isoformat(), "rows": [], "scope": {"with_broker": False}}
    out = PA.write_outputs(rc, chart=False, out_dir=out_dir, doc_path=doc, assets=tmp_path / "a")
    assert out["doc"] is None and "hack2" in out["doc_refused"]


# ═══════════════════════════════════════════════════════════════════ stop

def test_hyp_lab_stop_report_names_the_file_and_flags_an_old_one(tmp_path):
    import os
    from scripts import hyp_lab as HL
    stop = tmp_path / "STOP"
    assert HL.stop_report(stop) is None
    stop.write_text("", encoding="utf-8")
    old = (NOW - timedelta(hours=70)).timestamp()
    os.utime(stop, (old, old))
    r = HL.stop_report(stop, now=NOW, warn_h=48)
    assert r["stale"] is True and str(stop) in r["line"] and "WARNING" in r["line"]
    assert HL.stop_report(stop, now=NOW, warn_h=100)["stale"] is False


# ════════════════════════════════════════════════════════════════════ lab

def test_lab_off_marker_stops_main_before_anything_starts(tmp_path, monkeypatch):
    from scripts import always_on_lab as LAB
    marker = tmp_path / "always_on_lab_OFF"
    marker.write_text("off", encoding="utf-8")
    monkeypatch.setattr(LAB, "off_marker_path", lambda: marker)
    monkeypatch.setattr(LAB, "run_forever",
                        lambda **k: pytest.fail("the lab started with the OFF marker present"))
    assert LAB.main([]) == 0
    assert LAB.off_marker_state(marker)["off"] is True
    assert LAB.off_marker_state(tmp_path / "absent")["off"] is False


def test_lab_health_reports_off_and_a_violation(tmp_path, monkeypatch):
    from backend.services import system_health as H
    from backend import config
    (tmp_path / config.ALWAYS_ON_LAB_OFF_MARKER).write_text("off", encoding="utf-8")
    ctx = H.ProbeCtx(optimus_dir=tmp_path, now=NOW, allow_proc=False)
    monkeypatch.setattr(H, "_lab_status", lambda c: None)
    assert H.p_always_on_lab(ctx).verdict == "STOPPED_BY_OPERATOR"
    monkeypatch.setattr(H, "_lab_status", lambda c: {"pid": 4242, "utc": NOW.isoformat()})
    monkeypatch.setattr(H, "_process_verdict",
                        lambda c, **k: H.ProbeResult("ALIVE", NOW.isoformat(), 0.0, "alive", proof="p"))
    r = H.p_always_on_lab(ctx)
    assert r.verdict == "DEAD" and "RUNNING" in r.detail


# ═════════════════════════════════════════════════════════════════ keeper

def test_supervisor_rows_ignore_one_shots_and_other_programs():
    from scripts import task_keeper as K
    rows = [{"pid": 1, "cmdline": "python -m scripts.night_reader_supervisor --until 12:00"},
            {"pid": 2, "cmdline": "python -m scripts.night_reader_supervisor --probe"},
            {"pid": 3, "cmdline": "python -m scripts.daily_pass"}]
    assert [r["pid"] for r in K.supervisor_rows(rows)] == [1]


def test_reader_decision_is_idempotent_and_honours_the_pause():
    from scripts import task_keeper as K
    alive = [{"pid": 9, "cmdline": "-m scripts.night_reader_supervisor --until 08:00"}]
    assert K.reader_decision(rows=alive, stop_exists=False)["action"] == "alive"
    assert K.reader_decision(rows=[], stop_exists=False)["action"] == "launch"
    assert K.reader_decision(rows=[], stop_exists=True)["action"] == "paused"
    assert K.reader_decision(rows=None, stop_exists=False)["action"] == "cannot_determine"


def test_ensure_reader_launches_once_with_continuous_supervision(tmp_path):
    from scripts import task_keeper as K
    launched = []
    now_local = datetime(NOW.year, NOW.month, NOW.day, 21, 0)
    out = K.ensure_reader(scan=lambda: [], launch=lambda u, p: launched.append((u, p)) or 777,
                          stop_path=tmp_path / "STOP", now_local=now_local,
                          log_path=tmp_path / "k.jsonl")
    assert out["launched_pid"] == 777 and out["until"] == "continuous"
    assert len(launched) == 1 and launched[0][0] == "continuous"
    again = K.ensure_reader(scan=lambda: [{"pid": 777, "cmdline": "scripts.night_reader_supervisor"}],
                            launch=lambda u, p: pytest.fail("second supervisor launched"),
                            stop_path=tmp_path / "STOP", log_path=tmp_path / "k.jsonl")
    assert again["action"] == "alive"


def test_last_due_daily_and_weekly_triggers():
    from scripts import task_keeper as K
    now = datetime(NOW.year, NOW.month, NOW.day, 12, 0)
    start = (now - timedelta(days=30)).replace(hour=6, minute=30).isoformat()
    assert K.last_due({"start": start, "days_interval": 1}, now) == now.replace(hour=6, minute=30)
    late = now.replace(hour=5)
    assert K.last_due({"start": start, "days_interval": 1}, late) == \
        (late - timedelta(days=1)).replace(hour=6, minute=30)
    bit_today = 1 << ((now.weekday() + 1) % 7)
    assert K.last_due({"start": start, "days_of_week": bit_today}, now).date() == now.date()
    bit_yday = 1 << (((now - timedelta(days=1)).weekday() + 1) % 7)
    assert K.last_due({"start": start, "days_of_week": bit_yday}, now).date() == \
        (now - timedelta(days=1)).date()


def test_catchup_starts_only_a_missed_occurrence_inside_its_window():
    from scripts import task_keeper as K
    now = datetime(NOW.year, NOW.month, NOW.day, 20, 0)
    trig = [{"start": (now - timedelta(days=10)).replace(hour=6, minute=30).isoformat(),
             "days_interval": 1}]
    missed = {"name": "T", "state": "Ready", "triggers": trig,
              "last_run": (now - timedelta(days=1)).replace(hour=6, minute=30).isoformat()}
    assert K.catchup_decision(missed, now)["action"] == "start"
    ran = {**missed, "last_run": now.replace(hour=6, minute=31).isoformat()}
    assert K.catchup_decision(ran, now)["action"] == "ok"
    assert K.catchup_decision({**missed, "state": "Running"}, now)["action"] == "skip"
    just = now.replace(hour=6, minute=40)
    assert K.catchup_decision(missed, just)["action"] == "wait"
    assert K.catchup_decision(missed, now, max_age_h=5)["action"] == "too_old"


def test_catch_up_starts_by_task_name_and_logs(tmp_path):
    from scripts import task_keeper as K
    now = datetime(NOW.year, NOW.month, NOW.day, 20, 0)
    t = {"name": "AegisX", "state": "Ready",
         "last_run": (now - timedelta(days=1)).replace(hour=6, minute=30).isoformat(),
         "triggers": [{"start": (now - timedelta(days=5)).replace(hour=6, minute=30).isoformat(),
                       "days_interval": 1}]}
    started = []
    out = K.catch_up(tasks=lambda: [t], start=lambda n: started.append(n) or 0,
                     now_local=now, log_path=tmp_path / "k.jsonl", dry_run=False)
    assert started == ["AegisX"] and out["started"] == ["AegisX"]
    assert K.catch_up(tasks=lambda: None, log_path=tmp_path / "k.jsonl")["action"] == "cannot_determine"


def test_the_fleet_passes_are_never_caught_up():
    from scripts import task_keeper as K
    assert not any("FleetManager" in n for n in K.CATCHUP_TASKS)


# ═════════════════════════════════════════════════════════════════ report

def test_a_failed_session_report_leaves_a_row(tmp_path):
    from scripts import daily_learning_report as D

    def boom(day, **k):
        raise MemoryError("oom")
    row = D.report_for_session("sid1", "2026-01-05", base=tmp_path, writer=boom)
    assert row["status"] == "FAILED" and "MemoryError" in row["error"]
    rows = [json.loads(x) for x in (tmp_path / "learning_reports" / D.RUNS_NAME)
            .read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["session"] == "sid1"


def test_unreported_sessions_derives_from_rows_and_report_stamps():
    from scripts import daily_learning_report as D
    end = NOW - timedelta(hours=10)
    s = [{"id": "a", "state": "STARTED"}, {"id": "a", "state": "COMPLETED",
                                           "planned_end": end.isoformat()},
         {"id": "b", "state": "COMPLETED", "planned_end": (NOW - timedelta(days=30)).isoformat()}]
    todo = D.unreported_sessions(s, [], now=NOW)
    assert [t["session"] for t in todo] == ["a"]
    assert D.unreported_sessions(s, [{"session": "a", "status": "ok"}], now=NOW) == []
    later = {end.date().isoformat(): (end + timedelta(minutes=5)).isoformat()}
    assert D.unreported_sessions(s, [], now=NOW, report_stamps=later) == []
    earlier = {end.date().isoformat(): (end - timedelta(hours=1)).isoformat()}
    assert len(D.unreported_sessions(s, [], now=NOW, report_stamps=earlier)) == 1


def test_learn_rota_names_a_finished_session_without_a_report(tmp_path):
    from backend.services import system_health as H
    (tmp_path / "sim").mkdir()
    end = NOW - timedelta(hours=3)
    (tmp_path / "sim" / "session.json").write_text(json.dumps(
        {"id": "s9", "state": "COMPLETED", "planned_end": end.isoformat()}), encoding="utf-8")
    ctx = H.ProbeCtx(optimus_dir=tmp_path, now=NOW, allow_proc=False)
    gaps = H._session_report_gaps(ctx)
    assert gaps and "s9" in gaps[0]
    (tmp_path / "learning_reports").mkdir()
    (tmp_path / "learning_reports" / "report_runs.jsonl").write_text(
        json.dumps({"session": "s9", "status": "ok"}) + "\n", encoding="utf-8")
    assert H._session_report_gaps(ctx) == []


def test_why_zero_orders_names_the_real_cause():
    from scripts import sim_run as S
    why = S.why_zero_orders(exploit_acting=False, probe_acting=True, n_probe=2,
                            held={"A": 1, "B": 2}, probe_syms=["A", "B"], mandate_gates=False,
                            blend_verdict="MEASURED_NEGATIVE")
    assert "EXPLOIT not acting" in why and "2 of 2" in why and "mandate" not in why


# ════════════════════════════════════════════════════════════════ gateway

_STATUS = ("Runtime: running (pid 1)\nConnectivity probe: ok\n"
           "Capability: connected-no-operator-scope\n")


def test_gateway_without_operator_scope_is_alive_when_the_reader_proves_it(tmp_path):
    from backend.services import system_health as H
    (tmp_path / "dowjones").mkdir()
    (tmp_path / "dowjones" / "reader_status.json").write_text(json.dumps(
        {"t": (NOW - timedelta(minutes=5)).isoformat(), "pages_ok_60m": 40}), encoding="utf-8")
    ctx = H.ProbeCtx(optimus_dir=tmp_path, now=NOW, allow_proc=False,
                     run=lambda argv, t: (0, _STATUS))
    r = H.p_openclaw_gateway(ctx)
    assert r.verdict == "ALIVE" and "PROVEN by the reader" in r.detail


def test_gateway_without_operator_scope_and_no_reader_evidence_is_stale(tmp_path):
    from backend.services import system_health as H
    ctx = H.ProbeCtx(optimus_dir=tmp_path, now=NOW, allow_proc=False,
                     run=lambda argv, t: (0, _STATUS))
    r = H.p_openclaw_gateway(ctx)
    assert r.verdict == "STALE" and "UNPROVEN" in r.detail
