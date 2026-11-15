"""CH-64: the systems status receipt reads the LIVE files and shows wrapper refusals.

Every fixture is synthetic, under `tmp_path`, and dated from `now`. Nothing here reads the
machine: no schtasks, no live data root.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import investment_committee as IC
from backend.services import system_health as SH
from backend.services import task_receipts as TR
from scripts import system_status as S


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _w(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def _by_name(rows):
    return {r["name"]: r for r in rows}


def _link_dir(link: Path, target: Path) -> None:
    """A directory link the way a release clone has one: a junction on Windows (no admin
    right needed), a symlink elsewhere."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        cp = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            pytest.skip(f"cannot create a junction here: {cp.stdout} {cp.stderr}")
    else:
        os.symlink(target, link, target_is_directory=True)


def _funnel(p: Path, at: datetime | None, n: int = 3) -> Path:
    d = {"universe": {"n": 5000}, "candidates": [{"symbol": f"S{i}"} for i in range(n)], "failures": []}
    if at is not None:
        d["generated_at"] = _iso(at)
    return _w(p, d)


def _clone_and_live(tmp_path: Path, live_at: datetime, committed_at: datetime) -> tuple[Path, Path]:
    """(clone optimus dir = a link, live funnel path). The clone carries its own older funnel."""
    live_data = tmp_path / "live" / "backend" / "data"
    (live_data / "optimus").mkdir(parents=True)
    live_funnel = _funnel(live_data / "funnel_night10.json", live_at)
    clone_data = tmp_path / "aegis-runtime-x" / "backend" / "data"
    _funnel(clone_data / "funnel_night10.json", committed_at, n=7)
    _link_dir(clone_data / "optimus", live_data / "optimus")
    return clone_data / "optimus", live_funnel


# ─────────────────────────────────────────── 1. the funnel row reads the live file


def test_funnel_row_cites_the_live_file_not_the_copy_committed_in_the_clone(tmp_path):
    now = _now()
    live_at, committed_at = now - timedelta(days=2), now - timedelta(days=40)
    opt, live_funnel = _clone_and_live(tmp_path, live_at, committed_at)
    data_dir = S.live_data_dir(opt)
    assert data_dir == live_funnel.parent.resolve()
    r = _by_name(S.universe_rows(opt, data_dir, now, None))["funnel"]
    assert r["evidence_utc"] == _iso(live_at), r
    assert r["status"] == "OK" and "3 candidates" in r["detail"]
    assert str(live_funnel.resolve()) in r["evidence_path"]
    # the copy that was NOT read is named, with its own stamp
    assert r["extra"]["not_read"]["generated_at"] == _iso(committed_at)
    assert "aegis-runtime-x" in r["extra"]["not_read"]["path"]


def test_collect_reads_the_live_funnel_through_a_linked_data_root(tmp_path):
    now = _now()
    live_at = now - timedelta(days=3)
    opt, live_funnel = _clone_and_live(tmp_path, live_at, now - timedelta(days=40))
    rec = S.collect(optimus_dir=opt, repo=tmp_path, now=now, allow_proc=False, probe_rows_in=[])
    r = _by_name(rec["sections"]["universe"]["rows"])["funnel"]
    assert r["evidence_utc"] == _iso(live_at)
    assert Path(rec["funnel_path"]) == live_funnel.resolve()


def test_the_probe_context_is_pointed_at_the_live_funnel(tmp_path, monkeypatch):
    now = _now()
    opt, live_funnel = _clone_and_live(tmp_path, now - timedelta(days=1), now - timedelta(days=40))
    ctx = SH.ProbeCtx(optimus_dir=opt, now=now, repo=tmp_path, allow_proc=False, prev_state={})
    monkeypatch.setattr(S, "raw_probe_rows", lambda c: [])
    S.collect(optimus_dir=opt, repo=tmp_path, now=now, allow_proc=False, ctx=ctx)
    assert Path(ctx.paths["funnel"]) == live_funnel.resolve()
    assert SH.p_u_funnel(ctx).evidence_utc == _iso(now - timedelta(days=1))


def test_a_funnel_older_than_the_configured_limit_is_red(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    opt.mkdir()
    fp = tmp_path / "funnel_night10.json"

    def status(days: float) -> dict:
        _funnel(fp, now - timedelta(days=days))
        return _by_name(S.universe_rows(opt, tmp_path, now, None))["funnel"]

    lim = IC.FUNNEL_STALE_DAYS
    assert status(lim - 1)["status"] == "OK"
    over = status(lim + 0.2)
    assert over["status"] == "DEGRADED" and over in S.reds({"sections": {"u": {"rows": [over]}}})
    assert over["limit_s"] == lim * 86400 and over["action"]
    assert status(lim * S.C.SYSTEM_STATUS_DOWN_FACTOR + 1)["status"] == "DOWN"
    # the limit is the decision path's own constant, not the dashboard's table
    assert status(lim - 1)["extra"]["limit_days"] == IC.FUNNEL_STALE_DAYS
    assert _by_name(S.universe_rows(opt, tmp_path, now, {"funnel": 1}))["funnel"]["status"] == "OK"


def test_a_funnel_with_no_stamp_or_no_file_cannot_be_determined(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    opt.mkdir()
    fp = _funnel(tmp_path / "funnel_night10.json", None)
    os.utime(fp, None)                                   # written this second: mtime must not date it
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["funnel"]
    assert r["status"] == "UNKNOWN" and r["evidence_utc"] is None and "CANNOT DETERMINE" in r["detail"]
    fp.unlink()
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["funnel"]
    assert r["status"] == "UNKNOWN" and "CANNOT DETERMINE" in r["detail"] and r["required"] is True


# ─────────────────────────────────────────── 2. the graph row reads latest.json


def _graph(opt: Path, built: datetime | None, *, status: str | None = "OK", receipt: bool = True) -> Path:
    bid = "ug_fixture_1"
    g = opt / "universe_graph"
    latest = {"build_id": bid, "as_of": "fixture", "path": str(g / bid)}
    if built is not None:
        latest["built_utc"] = _iso(built)
    if receipt:
        rc = {"schema": "universe_graph/v1", "build_id": bid, "counts": {"n_nodes": 564, "n_edges": 22532},
              "panel_last_session": "fixture"}
        if status is not None:
            rc["status"] = status
        _w(g / bid / "receipt.json", rc)
    return _w(g / "latest.json", latest)


def test_graph_row_cites_latest_json_with_its_own_stamp(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    built = now - timedelta(hours=3)
    lp = _graph(opt, built)
    old = (now - timedelta(days=30)).timestamp()
    os.utime(lp, (old, old))                             # an old mtime must not age it
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]
    assert r["status"] == "OK", r
    assert r["evidence_utc"] == _iso(built) and str(lp) in r["evidence_path"]
    assert "nodes 564" in r["detail"] and "edges 22532" in r["detail"]
    assert r["required"] is True


def test_graph_row_goes_red_on_age_and_on_a_degraded_build(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    lim_h = S.C.SYSTEM_STATUS_LIMITS_H["universe_graph"]
    _graph(opt, now - timedelta(hours=lim_h + 1))
    assert _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]["status"] == "DEGRADED"
    _graph(opt, now - timedelta(hours=1), status="DEGRADED")
    assert _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]["status"] == "DEGRADED"
    _graph(opt, now - timedelta(hours=1), status=None)   # no status word in the receipt is not OK
    assert _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]["status"] == "UNKNOWN"


def test_graph_latest_json_without_a_stamp_cannot_be_determined(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    lp = _graph(opt, None)
    os.utime(lp, None)                                   # freshly written: still not fresh
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]
    assert r["status"] == "UNKNOWN" and r["evidence_utc"] is None and r["age_s"] is None
    assert "CANNOT DETERMINE" in r["detail"] and "built_utc" in r["detail"]


def test_graph_missing_or_without_its_receipt_is_never_ok(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    opt.mkdir()
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]
    assert r["status"] == "UNKNOWN" and "CANNOT DETERMINE" in r["detail"] and r["required"] is True
    _graph(opt, now - timedelta(hours=1), receipt=False)
    r = _by_name(S.universe_rows(opt, tmp_path, now, None))["universe_graph"]
    assert r["status"] == "UNKNOWN" and r["evidence_utc"] == _iso(now - timedelta(hours=1))


# ─────────────────────────────────────────── 3. the SEC raw row finds its receipt

_CONHOST = ('C:\\Windows\\System32\\conhost.exe --headless "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\'
            'powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -File "')


def _ctx(tmp_path: Path, now: datetime) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(parents=True, exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now, repo=tmp_path / "repo", prev_state={},
                       paths={"terminal_repo": tmp_path / "no_terminal"},
                       run=lambda argv, t: (None, "not installed"), pid_cmdline=lambda pid: None)


def _raw_receipt(folder: Path, t: datetime) -> Path:
    return _w(folder / f"{t.strftime('%Y%m%dT%H%M%SZ')}_1.json",
              {"job": "keyless_sec_raw_collection", "status": "OK", "reason": "ROWS_WRITTEN",
               "started_utc": _iso(t), "written_utc": _iso(t + timedelta(seconds=5)), "rows_new": 2,
               "consecutive_failures": 0})


def _cut_task(text: str) -> dict:
    return {"TaskName": "\\AegisRawSecCollection", "Scheduled Task State": "Enabled", "Last Run Time": "-",
            "Last Result": "0", "Next Run Time": "-", "Task To Run": text}


def test_raw_sec_receipt_is_found_when_schtasks_cut_the_action(tmp_path):
    """The live shape on 2026-11-16: the CSV column ends inside the harness folder's name."""
    now = _now()
    h = tmp_path / "evidence" / "sec-cursor-runtime-r6"
    _w(h / "run_raw_collection.ps1", "# fixture")
    t = now - timedelta(minutes=20)
    rp = _raw_receipt(h / "receipts", t)
    ctx = _ctx(tmp_path, now)
    for cut in (str(h), str(h)[:-3], str(h) + "\\", str(h / "run_raw_coll")):
        rd = TR.r_raw_sec(ctx, _cut_task(_CONHOST + cut))
        assert rd.unknown_reason is None, (cut, rd.unknown_reason)
        assert rd.stamp == t + timedelta(seconds=5) and rd.status == "OK"
        assert str(rp) in rd.proof and rd.proof                     # a full, non-empty receipt path
    assert TR.judge(ctx, "AegisRawSecCollection", _cut_task(_CONHOST + str(h))).state == "ALIVE_PROGRESSING"


def test_raw_sec_cut_action_that_is_ambiguous_or_leads_nowhere_cannot_be_determined(tmp_path):
    now = _now()
    ev = tmp_path / "evidence"
    for name in ("runtime-r6", "runtime-r6b"):
        _w(ev / name / "run_raw_collection.ps1", "# fixture")
        _raw_receipt(ev / name / "receipts", now - timedelta(minutes=5))
    ctx = _ctx(tmp_path, now)
    rd = TR.r_raw_sec(ctx, _cut_task(_CONHOST + str(ev / "runtime-r")))
    assert rd.unknown_reason and "2 folders" in rd.unknown_reason and rd.stamp is None
    rd = TR.r_raw_sec(ctx, _cut_task(_CONHOST + str(ev / "nothing-he")))
    assert rd.unknown_reason and "cannot be derived" in rd.unknown_reason
    j = TR.judge(ctx, "AegisRawSecCollection", _cut_task(_CONHOST + str(ev / "nothing-he")))
    assert j.state == "UNKNOWN"


# ─────────────────────────────────────────── 4. refusals


def _journal(opt: Path, rows: list) -> Path:
    return _w(opt / S.RUN_JOURNAL_REL,
              "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")


def _refused(at: datetime, module: str, *, low_memory: bool = False) -> dict:
    if low_memory:
        return {"wrapper_pid": 1, "clone": "c", "head": "h", "utc": _iso(at), "event": "refused",
                "reason": "LOW_MEMORY", "why": "LOW_MEMORY: 1.1 GB free is below the floor of 4 GB",
                "free_gb": 1.1, "min_free_gb": 4, "argv": [["-m", module, "--x"]], "rc": 93}
    return {"utc": _iso(at), "event": "refused", "wrapper_pid": 2, "clone": "c",
            "why": "aegis_pi.db exists and is not the live database (a split brain)",
            "argv": ["--pythonw", "-m", module, "step"], "rc": 90}


def _ran(at: datetime, module: str = "scripts.system_status") -> dict:
    return {"wrapper_pid": 3, "utc": _iso(at), "event": "end", "segment": 0, "module": module, "rc": 0}


def test_refused_rows_inside_and_outside_the_last_hour_are_counted(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    _journal(opt, [
        _refused(now - timedelta(days=3), "scripts.old_one"),                     # outside both windows
        _refused(now - timedelta(hours=5), "scripts.dynamic_books"),              # 24 h only
        _refused(now - timedelta(hours=2), "scripts.lab_night", low_memory=True),  # 24 h only
        _ran(now - timedelta(minutes=50)),
        _refused(now - timedelta(minutes=40), "scripts.ticker_hub"),
        _refused(now - timedelta(minutes=25), "scripts.ticker_hub"),
        _refused(now - timedelta(minutes=10), "scripts.nn_lab", low_memory=True),
        _ran(now - timedelta(minutes=2)),
    ])
    r = S.refusal_row(opt, now, None)
    assert r["name"] == "refused in the last hour" and r["section"] == "infrastructure"
    assert r["status"] == "DOWN" and r["action"]
    ex = r["extra"]
    assert (ex["n_refused_1h"], ex["n_refused_24h"]) == (3, 5)
    assert ex["tasks_1h"] == ["scripts.nn_lab", "scripts.ticker_hub"]
    assert ex["reasons_1h"] == ["LOW_MEMORY", "rc 90"]
    assert "scripts.dynamic_books" in ex["tasks_24h"] and "scripts.old_one" not in ex["tasks_24h"]
    assert "3 refused in the last 1 h" in r["detail"] and "5 in the last 24 h" in r["detail"]
    assert "scripts.ticker_hub x2" in r["detail"] and "LOW_MEMORY" in r["detail"]
    assert r["evidence_utc"] == _iso(now - timedelta(minutes=2))      # the journal's newest row


def test_no_refusal_in_the_last_hour_is_ok_and_still_shows_the_day(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    _journal(opt, [_refused(now - timedelta(hours=3), "scripts.world_digest"), _ran(now - timedelta(minutes=5))])
    r = S.refusal_row(opt, now, None)
    assert r["status"] == "OK" and r["action"] == ""
    assert (r["extra"]["n_refused_1h"], r["extra"]["n_refused_24h"]) == (0, 1)
    assert "0 refused in the last 1 h" in r["detail"] and "scripts.world_digest" in r["detail"]


@pytest.mark.parametrize("content", [None, "", "not json\n{broken\n", "[1, 2]\n"])
def test_an_unreadable_journal_cannot_be_determined(tmp_path, content):
    now = _now()
    opt = tmp_path / "optimus"
    opt.mkdir()
    if content is not None:
        _w(opt / S.RUN_JOURNAL_REL, content)
    r = S.refusal_row(opt, now, None)
    assert r["status"] == "UNKNOWN" and "CANNOT DETERMINE" in r["detail"]
    assert r["required"] is True and r["evidence_utc"] is None


def test_a_journal_that_is_a_folder_cannot_be_determined(tmp_path):
    opt = tmp_path / "optimus"
    (opt / S.RUN_JOURNAL_REL).mkdir(parents=True)
    r = S.refusal_row(opt, _now(), None)
    assert r["status"] == "UNKNOWN" and "CANNOT DETERMINE" in r["detail"]


def test_a_silent_journal_and_an_undated_refusal_are_not_ok(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    lim_h = S.C.SYSTEM_STATUS_LIMITS_H["runtime_journal"]
    _journal(opt, [_ran(now - timedelta(hours=lim_h + 1))])
    r = S.refusal_row(opt, now, None)
    assert r["status"] == "DEGRADED" and r["extra"]["n_refused_1h"] == 0     # zero refusals from a silent journal
    bad = _refused(now, "scripts.x")
    bad["utc"] = "yesterday-ish"
    _journal(opt, [bad, _ran(now - timedelta(minutes=1))])
    r = S.refusal_row(opt, now, None)
    assert r["status"] == "UNKNOWN" and r["extra"]["undated_refused"] == 1


def test_collect_carries_the_refused_row(tmp_path):
    now = _now()
    opt = tmp_path / "optimus"
    _journal(opt, [_refused(now - timedelta(minutes=3), "scripts.dynamic_books")])
    rec = S.collect(optimus_dir=opt, repo=tmp_path, now=now, allow_proc=False, probe_rows_in=[])
    r = _by_name(rec["sections"]["infrastructure"]["rows"])["refused in the last hour"]
    assert r["status"] == "DOWN" and rec["counts"]["DOWN"] >= 1
    assert "refused in the last hour" in S.render_text(rec)


# ─────────────────────────────────────────── 5. ISO next-run beside the locale text


def test_task_rows_carry_iso_run_times_beside_the_old_fields(monkeypatch):
    now = _now()
    nxt_local = (now + timedelta(hours=3)).astimezone().replace(tzinfo=None)
    last_local = (now - timedelta(hours=1)).astimezone().replace(tzinfo=None)
    fmt = "%m/%d/%Y %I:%M:%S %p"
    monkeypatch.setattr(SH, "_schtasks", lambda ctx: {
        "AegisA": {"Last Run Time": last_local.strftime(fmt), "Last Result": "0",
                   "Next Run Time": nxt_local.strftime(fmt), "Scheduled Task State": "Ready"},
        "AegisB": {"Last Run Time": "N/A", "Last Result": "267011", "Next Run Time": "N/A",
                   "Scheduled Task State": "Ready"}})
    rows = _by_name(S.tasks_section(object(), now, []))
    ex = rows["AegisA"]["extra"]
    assert ex["next_run"] == nxt_local.strftime(fmt) and ex["last_run"] == last_local.strftime(fmt)   # kept
    got = datetime.fromisoformat(ex["next_run_utc"])
    assert got.tzinfo is not None and got == now + timedelta(hours=3)
    assert datetime.fromisoformat(ex["last_run_utc"]) == now - timedelta(hours=1)
    assert rows["AegisB"]["extra"]["next_run_utc"] is None and rows["AegisB"]["extra"]["last_run_utc"] is None


def test_day_file_takes_the_iso_field_over_the_locale_text():
    from scripts import day_file as DF
    now = _now()
    r = {"extra": {"next_run": "03/04/2026 1:00:00 PM", "next_run_utc": S.iso(now)}}
    assert DF._row_time(r, "next_run", None) == now
    assert DF._row_time({"extra": {"next_run": "03/04/2026 1:00:00 PM", "next_run_utc": None}}, "next_run", "mdy") \
        is not None                                   # no ISO value: the old text is still read


def test_out_is_an_alias_of_out_dir(tmp_path, monkeypatch):
    opt = tmp_path / "optimus"
    opt.mkdir()
    out = tmp_path / "elsewhere"
    monkeypatch.setattr(S, "collect", lambda **kw: {"receipt": S.SCHEMA, "generated_utc": S.iso(_now()),
                                                    "counts": dict.fromkeys(S.STATUSES, 0), "sections": {},
                                                    "undetermined": []})
    assert S.main(["--optimus-dir", str(opt), "--out", str(out), "--quiet", "--no-proc"]) == 0
    assert (out / "status.json").exists() and not (opt / "system_status").exists()
