"""CH-22a: the systems dashboard's collector and page, OFFLINE with synthetic inputs.

Pins the behaviours the owner's rules require of a status surface: a date that is
printed is compared (old -> red), a missing input is UNKNOWN never OK, a required
section that cannot be read is a non-zero exit, the page leads with the reds, and
nothing is dated by file mtime.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import system_status as S

NOW = datetime(2026, 11, 10, 18, 0, 0, tzinfo=timezone.utc)


def _w(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def _by_name(rows):
    return {r["name"]: r for r in rows}


# -- the one age comparison ----------------------------------------------------
def test_age_past_limit_goes_red():
    lim = 36 * 3600
    assert S.judge_age(NOW - timedelta(hours=1), NOW, lim)[0] == "OK"
    assert S.judge_age(NOW - timedelta(hours=40), NOW, lim)[0] == "DEGRADED"
    assert S.judge_age(NOW - timedelta(hours=120), NOW, lim)[0] == "DOWN"


def test_undated_or_future_evidence_is_unknown_never_ok():
    assert S.judge_age(None, NOW, 3600)[0] == "UNKNOWN"
    assert S.judge_age(NOW + timedelta(hours=5), NOW, 3600)[0] == "UNKNOWN"
    assert S.judge_age(NOW - timedelta(hours=1), NOW, None)[0] == "UNKNOWN"      # no declared limit


def test_date_only_stamp_one_day_ahead_is_not_the_future():
    # the owner's local day (UTC+8) can already be tomorrow in UTC
    # (review 3 O5: the slack applies to a stamp PARSED from a date, not to
    # any datetime that happens to be midnight)
    tomorrow = S.parse_ts((NOW + timedelta(days=1)).date().isoformat())
    assert S.judge_age(tomorrow, NOW, 3 * 86400)[0] == "OK"


def test_dated_row_takes_the_worse_of_content_and_age():
    r = S.dated_row("learning", "world_digest", "OK", "digest ok", NOW - timedelta(hours=120), NOW,
                    evidence="x", action_bad="do it")
    assert r["status"] == "DOWN" and r["action"] == "do it" and r["limit_s"] == 36 * 3600
    r = S.dated_row("learning", "world_digest", "DOWN", "0 typed rows", NOW - timedelta(hours=1), NOW,
                    evidence="x", action_bad="do it")
    assert r["status"] == "DOWN"                       # fresh but failed stays red
    r = S.dated_row("learning", "world_digest", "OK", "fine", NOW - timedelta(hours=1), NOW,
                    evidence="x", action_bad="a")
    assert r["status"] == "OK" and r["action"] == ""


def test_newest_by_name_ignores_mtime(tmp_path):
    old = _w(tmp_path / "reputation_2026-10-08.json", {})
    new = _w(tmp_path / "reputation_2026-10-27.json", {})
    os.utime(new, (1, 1))                               # the newer-named file has the OLDEST mtime
    os.utime(old, (time.time(), time.time()))
    p, d = S.newest_by_name(tmp_path, "reputation_*.json")
    assert p.name == "reputation_2026-10-27.json" and d.day == 27


# -- missing input is UNKNOWN, not OK -------------------------------------------
def test_empty_runtime_yields_unknown_rows_not_ok(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()
    rows = (S.universe_rows(opt, tmp_path, NOW, None) + S.decision_rows(opt, NOW, None)
            + S.night_rows(opt, NOW, None) + S.lesson_rows(opt, NOW, None))
    assert rows and all(r["status"] == "UNKNOWN" for r in rows), [(r["name"], r["status"]) for r in rows]


def test_learning_rows_on_empty_dir_never_ok(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()

    class Ctx:
        optimus_dir = opt
        now = NOW

    rows = S.learning_rows(opt, NOW, Ctx(), None)
    assert {r["name"] for r in rows} >= {"deepseek_envelope", "world_digest", "learner", "reputation_refit",
                                         "iif1_night", "hyp_lab"}
    assert not [r for r in rows if r["status"] == "OK"], [(r["name"], r["status"]) for r in rows]


def test_funnel_age_is_compared(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()
    cands = [{"symbol": "A"}]

    def put(days, c=cands):
        _w(tmp_path / "funnel_night10.json", {"generated_at": (NOW - timedelta(days=days)).isoformat(),
                                              "universe": {"n": 5339}, "candidates": c, "failures": []})
        return _by_name(S.universe_rows(opt, tmp_path, NOW, None))["funnel"]

    assert put(44)["status"] == "DOWN"
    assert put(2)["status"] == "OK"
    assert put(2, [])["status"] == "DOWN"             # nobody was offered


def test_funnel_without_a_stamp_is_unknown(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()
    _w(tmp_path / "funnel_night10.json", {"candidates": [{"symbol": "A"}], "failures": []})
    assert _by_name(S.universe_rows(opt, tmp_path, NOW, None))["funnel"]["status"] == "UNKNOWN"


def test_universe_graph_optional_until_ch30(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()
    g = _by_name(S.universe_rows(opt, tmp_path, NOW, None))["universe_graph"]
    assert g["status"] == "UNKNOWN" and g["required"] is False


# -- books -----------------------------------------------------------------------
def _fleet(opt: Path, accounts, finished="2026-11-10T14:48:26+00:00"):
    _w(opt / "paper_accounts/fleet_manager/runs/run_20261110T144501Z-abc.json",
       {"pass": "open", "finished_utc": finished, "accounts": accounts})


def test_unprotected_position_is_down_and_retired_account_is_excused(tmp_path):
    opt = tmp_path / "optimus"
    _fleet(opt, [
        {"role": "hack1", "status": "ok", "equity": "90000", "n_positions": 1,
         "positions": [{"symbol": "CALX"}], "stop_table": [{"symbol": "CALX", "resting": []}]},
        {"role": "hack2", "status": "ok", "equity": "80000", "n_positions": 1,
         "positions": [{"symbol": "MAZE"}], "stop_table": [{"symbol": "MAZE", "resting": [{"stop_price": "1"}]}]},
        {"role": "hack3", "status": "SKIPPED", "equity": None, "n_positions": None},
    ])
    rows = _by_name(S.decision_rows(opt, NOW, None))
    assert rows["account:hack1"]["status"] == "DOWN" and "UNPROTECTED" in rows["account:hack1"]["detail"]
    assert rows["account:hack2"]["status"] == "OK" and "$80,000.00" in rows["account:hack2"]["detail"]
    assert rows["account:hack3"]["status"] == "OK" and "retired" in rows["account:hack3"]["detail"]


def test_account_receipt_age_is_compared(tmp_path):
    opt = tmp_path / "optimus"
    _fleet(opt, [{"role": "hack2", "status": "ok", "equity": "1", "n_positions": 0, "positions": []}],
           finished="2026-10-01T00:00:00+00:00")
    assert _by_name(S.decision_rows(opt, NOW, None))["account:hack2"]["status"] == "DOWN"


# -- probes mapped, not recomputed -------------------------------------------------
def _probe(probe, verdict, **kw):
    return {"name": kw.pop("name", probe), "probe": probe, "verdict": verdict, "detail": "d", "where": "pc",
            "evidence_utc": None, "proof": "p", "cadence_s": 3600, **kw}


def test_probe_verdict_mapping():
    assert S.map_probe_row(_probe("u_funnel", "ALIVE"))["status"] == "OK"
    assert S.map_probe_row(_probe("u_funnel", "STALE"))["status"] == "DEGRADED"
    assert S.map_probe_row(_probe("u_funnel", "DEAD"))["status"] == "DOWN"
    assert S.map_probe_row(_probe("u_funnel", "REFUSED"))["status"] == "DOWN"          # a refusal is red
    assert S.map_probe_row(_probe("u_funnel", "UNKNOWN"))["status"] == "UNKNOWN"
    stopped = S.map_probe_row(_probe("always_on_lab", "STOPPED_BY_OPERATOR"))
    assert stopped["status"] == "DEGRADED" and "expiry" in stopped["action"]
    rw = S.map_probe_row(_probe("railway_backend", "DEAD"))
    assert rw["status"] == "UNKNOWN" and rw["required"] is False                         # offline is not a failure
    assert S.map_probe_row(_probe("bars_panel", "ALIVE")) is None                       # replaced by own rows
    assert S.map_probe_row(_probe("u_funnel", "ALIVE", state="DEGRADED"))["status"] == "DEGRADED"


def test_lab_loops_are_grouped():
    rows = [S.map_probe_row(_probe("lab_loop", "STOPPED_BY_OPERATOR", name=f"lab_loop:l{i}")) for i in range(6)]
    rows.append(S.map_probe_row(_probe("u_funnel", "DEAD")))
    out = S.group_loops(rows)
    assert len(out) == 2 and any(r["name"].startswith("lab_loops (6") for r in out)


# -- machine -----------------------------------------------------------------------
def test_powercfg_parser():
    txt = "Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000258\n"
    assert S._powercfg(lambda a, t: (0, txt)) == (0, 600)
    assert S._powercfg(lambda a, t: (1, "")) is None


def test_machine_rows_flag_low_ram_and_unreadable_gh():
    def run(argv, timeout):
        return (1, "") if argv[0] == "gh" else (0, "")

    rows = _by_name(S.machine_rows(NOW, run=run, ram_free=lambda: 2.0, boot=lambda n: n - timedelta(days=2)))
    assert rows["ram_free"]["status"] == "DEGRADED"
    assert rows["last_boot"]["status"] == "OK"
    assert rows["open_prs"]["status"] == "UNKNOWN" and rows["open_prs"]["required"] is False
    low = _by_name(S.machine_rows(NOW, run=run, ram_free=lambda: 0.5, boot=lambda n: None))
    assert low["ram_free"]["status"] == "DOWN" and low["last_boot"]["status"] == "UNKNOWN"
    ok = _by_name(S.machine_rows(NOW, run=lambda a, t: (0, '[{"number": 1}, {"number": 2}]'),
                                 ram_free=lambda: 9.0, boot=lambda n: n - timedelta(days=1)))
    assert ok["open_prs"]["detail"] == "2 open PR(s)"


# -- lessons -----------------------------------------------------------------------
def test_lessons_newest_five_and_freshness(tmp_path):
    opt = tmp_path / "optimus"
    rules = [{"rule_id": f"R{i}", "created_utc": (NOW - timedelta(days=20 - i)).isoformat(), "rule_text": f"rule {i}"}
             for i in range(8)]
    _w(opt / "brain/learned_rules.jsonl", "\n".join(json.dumps(r) for r in rules) + "\n")
    rows = S.lesson_rows(opt, NOW, None)
    assert [r["name"] for r in rows[1:]] == [f"rule R{i}" for i in (7, 6, 5, 4, 3)]
    assert rows[0]["status"] == "DEGRADED"             # newest rule is 13 days old, limit 7


# -- collect / exit codes ------------------------------------------------------------
def test_collect_with_no_runtime_is_exit_3(tmp_path):
    opt = tmp_path / "optimus"
    opt.mkdir()
    rec = S.collect(optimus_dir=opt, repo=tmp_path, now=NOW, probe_rows_in=[], ctx=None,
                    run=lambda a, t: (1, ""))
    assert rec["exit_code"] == 3 and rec["undetermined"]
    assert S.exit_code(rec) == 3
    assert any("tasks" in u for u in rec["undetermined"])


def test_a_collector_that_raises_is_an_unknown_row_and_exit_3(tmp_path, monkeypatch):
    opt = tmp_path / "optimus"
    opt.mkdir()
    monkeypatch.setattr(S, "night_rows", lambda *a, **k: 1 / 0)
    rec = S.collect(optimus_dir=opt, repo=tmp_path, now=NOW, probe_rows_in=[], ctx=None, run=lambda a, t: (1, ""))
    assert rec["sections"]["night"]["error"].startswith("ZeroDivisionError")
    assert any(u.startswith("night:") for u in rec["undetermined"])


def _rec(rows):
    secs = {k: {"title": t, "rows": [], "error": None} for k, t in S.SECTIONS}
    for r in rows:
        secs[r["section"]]["rows"].append(r)
    counts = {k: sum(1 for r in rows if r["status"] == k and not r.get("one_shot")) for k in S.STATUSES}
    return {"receipt": S.SCHEMA, "generated_utc": S.iso(NOW), "counts": counts, "sections": secs,
            "undetermined": [], "read_me_first": "x"}


def _r(sec, name, status, **kw):
    return S.row(sec, name, status, kw.pop("detail", "d"), now=NOW, **kw)


def test_exit_codes():
    full = [_r(k, "x", "OK") for k, _ in S.SECTIONS]
    assert S.exit_code(_rec(full)) == 0
    with_down = full + [_r("night", "y", "DOWN")]
    assert S.exit_code(_rec(with_down)) == 0                         # a red SYSTEM is the page's job
    assert S.exit_code(_rec(with_down), strict=True) == 2
    unk_req = full + [_r("night", "z", "UNKNOWN")]
    assert S.exit_code(_rec(unk_req)) == 3                           # cannot determine
    unk_opt = full + [_r("night", "z", "UNKNOWN", required=False)]
    assert S.exit_code(_rec(unk_opt)) == 0
    assert S.exit_code(_rec(full[:-1])) == 3                         # a section with no rows


# -- the page ------------------------------------------------------------------------
def test_html_header_reds_first_self_contained_and_escaped():
    rows = [_r(k, "ok_" + k, "OK") for k, _ in S.SECTIONS]
    rows += [_r("learning", "bad", "DOWN", detail="<script>alert(1)</script>", action="fix it"),
             _r("night", "meh", "DEGRADED", action="look"),
             _r("tasks", "AegisReaderClean-1", "DEGRADED", one_shot=True)]
    rec = _rec(rows)
    page = S.render_html(rec, now=NOW)
    assert "7 OK · 1 degraded · 1 down · 0 unknown" in page
    assert page.index("Needs attention") < page.index("Scheduled tasks")
    assert page.index("fix it") < page.index("ok_learning")            # reds before the greens
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert not re.search(r"(src|href)=['\"]?https?://", page)        # no CDN, no network
    assert "prefers-color-scheme:dark" in page
    assert "Known one-shot tasks" in page and "AegisReaderClean-1" in page
    assert "1 degraded" in S.header_line(rec)                           # the one-shot is not counted


def test_stale_receipt_is_flagged_on_the_page():
    rec = _rec([_r(k, "x", "OK") for k, _ in S.SECTIONS])
    page = S.render_html(rec, now=NOW + timedelta(hours=5))
    assert "refresh: python -m scripts.system_status --html" in page


def test_page_links_back_to_the_rest_of_the_app():
    """CH-22 (2026-11-14): the page had no way back to the dashboard."""
    page = S.render_html(_rec([_r(k, "x", "OK") for k, _ in S.SECTIONS]), now=NOW)
    for href in ("/", "/stock", "/watchlist", "/news", "/desktop"):
        assert f"href='{href}'" in page, href
    for label in ("Dashboard", "Stocks", "Watchlist", "News", "Desktop"):
        assert f">{label}</a>" in page
    assert page.index("aria-label='Aegis app'") < page.index("Needs attention")


def test_page_says_in_plain_words_when_it_was_collected_and_how_old():
    rec = _rec([_r(k, "x", "OK") for k, _ in S.SECTIONS])
    fresh = S.render_html(rec, now=NOW + timedelta(minutes=20))
    assert "This status was collected 2026-11-10 18:00 UTC" in fresh and "20 min ago." in fresh
    assert "<p class='gen' id=generated>" in fresh
    assert fresh.index("id=generated") < fresh.index("Needs attention")
    old = S.render_html(rec, now=NOW + timedelta(hours=5))
    assert "<p class='gen stale' id=generated>" in old and "older than the 60 min limit" in old
    undated = S.render_html(dict(rec, generated_utc=None), now=NOW)
    assert "no readable collection time" in undated and "gen stale" in undated
    ahead = S.render_html(rec, now=NOW - timedelta(hours=2))
    assert "in the FUTURE" in ahead


def test_write_atomic_leaves_no_temp(tmp_path):
    p = S.write_atomic(tmp_path / "d" / "status.json", "{}")
    assert p.read_text() == "{}" and [x.name for x in p.parent.iterdir()] == ["status.json"]


def test_render_only_refuses_without_a_receipt(tmp_path):
    assert S.main(["--render-only", "--out-dir", str(tmp_path), "--optimus-dir", str(tmp_path)]) == 3


# -- the desktop routes (read one receipt; never run the collector) ---------------
def _client(monkeypatch, tmp_path, enabled=True):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.routers import system_status as R
    monkeypatch.setattr(R.C, "OPTIMUS_LEDGER_DIR", tmp_path)
    if enabled:
        monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    else:
        monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app)


def test_routes_refuse_when_the_control_plane_is_off(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, enabled=False)
    assert c.get("/system-status").status_code == 403
    assert c.get("/api/control/system-status").status_code == 403


def test_page_without_a_receipt_names_the_command(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.get("/system-status")
    assert r.status_code == 404 and "python -m scripts.system_status --html" in r.text
    for href in ("/", "/stock", "/watchlist", "/news", "/desktop"):   # L3: a way back
        assert f"href='{href}'" in r.text, href
    assert c.get("/api/control/system-status").status_code == 404


def test_page_and_json_serve_the_receipt(monkeypatch, tmp_path):
    rec = _rec([_r(k, "x", "OK") for k, _ in S.SECTIONS] + [_r("night", "bad", "DOWN", action="fix it")])
    S.write_atomic(tmp_path / "system_status" / "status.json", json.dumps(rec))
    c = _client(monkeypatch, tmp_path)
    page = c.get("/system-status")
    assert page.status_code == 200 and "1 down" in page.text and "fix it" in page.text
    assert c.get("/api/control/system-status").json()["counts"]["DOWN"] == 1
    S.write_atomic(tmp_path / "system_status" / "status.json", json.dumps({"receipt": "other"}))
    assert c.get("/system-status").status_code == 404          # a foreign file is not served


# -- review 3 (S65) on #95 ------------------------------------------------------

def _sched(monkeypatch, tasks: dict):
    from backend.services import system_health as SH
    monkeypatch.setattr(SH, "_schtasks", lambda ctx: tasks)


def test_a_task_with_no_receipt_reader_is_unknown_not_ok(monkeypatch):
    """R1: 'Last Result 0' alone is the scheduler's word, not evidence the job
    did anything (10-15 -> 11-10: rc 0 while every call was refused)."""
    _sched(monkeypatch, {"AegisNoReader": {"Last Run Time": "11/10/2026 3:00:00 AM",
                                           "Last Result": "0",
                                           "Next Run Time": "11/11/2026 3:00:00 AM",
                                           "Scheduled Task State": "Ready"}})
    r = _by_name(S.tasks_section(object(), NOW, []))["AegisNoReader"]
    assert r["status"] == "UNKNOWN" and "exit 0 with no receipt read" in r["detail"]
    assert r["required"] is False                 # does not trip exit 3 on its own
    assert r["action"]


def test_a_receipt_without_a_status_field_is_unknown(tmp_path):
    """O1: a universe_graph receipt with no `status` read OK on content."""
    opt = tmp_path / "optimus"
    _w(opt / "universe_graph" / "graph_2026-11-10.json",
       {"generated_utc": S.iso(NOW - timedelta(hours=1)), "n_nodes": 10, "n_edges": 20})
    g = _by_name(S.universe_rows(opt, tmp_path, NOW, None))["universe_graph"]
    assert g["status"] == "UNKNOWN", g


@pytest.mark.parametrize("status", ["REFUSED", "ERROR", "VOID", "FAILED"])
def test_hyp_lab_refusals_are_red(tmp_path, status):
    """O2: only BUDGET_REFUSED was red; REFUSED, ERROR and VOID read OK."""
    opt = tmp_path / "optimus"
    _w(opt / "hyp_lab" / "ledger.jsonl",
       json.dumps({"kind": "nightly", "hyp_id": "h1", "status": status,
                   "utc": S.iso(NOW - timedelta(hours=1))}) + "\n")

    class Ctx:
        optimus_dir = opt
        now = NOW
    r = _by_name(S.learning_rows(opt, NOW, Ctx(), None))["hyp_lab"]
    assert r["status"] == "DOWN", r


def test_world_digest_without_a_typed_count_is_unknown(tmp_path, monkeypatch):
    """O3: a receipt lacking n_rows skipped the typed == 0 -> DOWN check."""
    from types import SimpleNamespace

    from backend.services import task_receipts as TR
    opt = tmp_path / "optimus"
    p = _w(opt / "digest" / "world_digest_2026-11-10.json", {"writes": {}})
    monkeypatch.setattr(TR, "r_world_digest", lambda ctx, _: SimpleNamespace(
        status="OK", unknown_reason=None, detail="ran", reason=None,
        stamp=NOW - timedelta(hours=1), proof=str(p)))
    monkeypatch.setattr(TR, "_newest", lambda folder, pat: (p, {"writes": {}}))

    class Ctx:
        optimus_dir = opt
        now = NOW
    r = _by_name(S.learning_rows(opt, NOW, Ctx(), None))["world_digest"]
    assert r["status"] == "UNKNOWN" and "typed rows None" in r["detail"]


def test_envelope_row_reads_through_peek_with_deferred_spend(tmp_path, monkeypatch):
    """O4 / #97: the row reads the guard's own view (`_peek`), which applies
    deferred settlements and their blocks; pending sidecar lines are named."""
    from backend.services import provider_budget as PB
    opt = tmp_path / "optimus"
    env = _w(opt / "session_budget" / "deepseek_local.json", "{}")
    seen = {}

    def peek(p, budget_path=None):
        seen["p"] = Path(p)
        return {"month": "2026-11", "cap_units": PB._units(15), "opening_units": 0,
                "calls": {"a": {"held_units": PB._units(0.5),
                                "started_utc": S.iso(NOW - timedelta(hours=1))}},
                "blocked": None, "sidecar_pending": 2, "sidecar_oldest_age_h": 30.0}
    monkeypatch.setattr(PB, "_peek", peek)
    monkeypatch.setattr(PB, "_load", lambda p: pytest.fail("raw _load misses the sidecar"))

    class Ctx:
        optimus_dir = opt
        now = NOW
    r = _by_name(S.learning_rows(opt, NOW, Ctx(), None))["deepseek_envelope"]
    assert seen["p"] == env
    assert "$0.5000 of $15.00" in r["detail"] and "2 deferred settlement(s)" in r["detail"]
    assert r["status"] == "DEGRADED"           # past DEEPSEEK_SIDECAR_STALE_HOURS (or 12 h)


def test_envelope_row_shows_a_real_deferred_block(tmp_path, monkeypatch):
    """With #97's provider_budget on the path: a block that waits in the sidecar
    is DOWN on the dashboard, and the deferred cost is in the held amount."""
    from backend.services import provider_budget as PB
    if not hasattr(PB, "_apply_sidecar"):
        pytest.skip("provider_budget predates #97 (no sidecar); covered by the stub test above")
    opt = tmp_path / "optimus"
    env = opt / "session_budget" / "deepseek_local.json"
    env.parent.mkdir(parents=True)
    PB.initialize("fixture", 15, opening_charge_usd=0, opening_evidence="fixture", budget_path=env)
    tk = PB.reserve("s", "u", 100, model="deepseek-chat", base_url="https://api.deepseek.com",
                    purpose="fixture", budget_path=env)
    import backend.services.disk_guard as DG
    real = DG.atomic_write_json

    def busy(p, o, **kw):
        if str(p).endswith("deepseek_local.json"):
            raise PermissionError(13, "busy", str(p))
        return real(p, o, **kw)
    monkeypatch.setattr(PB, "_sleep", lambda s: None)
    monkeypatch.setattr(DG, "atomic_write_json", busy)
    from types import SimpleNamespace as NS
    PB.settle(tk, NS(model="deepseek-mystery", usage=NS(prompt_tokens=20, completion_tokens=10,
                                                       prompt_cache_hit_tokens=0)))
    monkeypatch.setattr(DG, "atomic_write_json", real)

    class Ctx:
        optimus_dir = opt
        now = NOW
    r = _by_name(S.learning_rows(opt, datetime.now(timezone.utc), Ctx(), None))["deepseek_envelope"]
    assert r["status"] == "DOWN" and "BLOCKED" in r["detail"] and "deferred" in r["detail"]


def test_a_midnight_timestamp_in_the_future_is_not_excused():
    """O5: the one-day slack is for DATE-ONLY stamps; a full timestamp that
    happens to be exactly midnight UTC and in the future is UNKNOWN."""
    lim = 3600.0 * 24
    ahead = (NOW + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    full = S.parse_ts(ahead.isoformat())
    st, _, _ = S.judge_age(full, NOW, lim)
    assert st == "UNKNOWN"
    date_only = S.parse_ts(ahead.date().isoformat())
    st2, _, _ = S.judge_age(date_only, NOW, lim)
    assert st2 == "OK"


def test_page_escapes_status_and_section_and_survives_a_foreign_status():
    """N1: status and section key were interpolated unescaped; an unknown
    status raised KeyError in the sort."""
    rows = [_r(k, "ok_" + k, "OK") for k, _ in S.SECTIONS]
    rec = _rec(rows)
    bad = dict(rows[0], status="<b>x</b>")
    rec["sections"]["tasks"]["rows"].append(bad)
    rec["sections"]["evil'><script>"] = {"title": "t", "rows": [], "error": None}
    page = S.render_html(rec, now=NOW)
    assert "<b>x</b>" not in page
    assert "evil'><script>" not in page
    assert S.reds(rec)                          # the foreign status is shown as red, not a crash
    assert S.render_text(rec)
