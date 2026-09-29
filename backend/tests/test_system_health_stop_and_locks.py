"""Health probes (2026-09-29): a lab stopped by its STOP file is
STOPPED_BY_OPERATOR (read from its stop record), not DEAD and not ALIVE; empty
`.lock` sidecars are not zero-byte receipts. Both directions."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services import system_health as SH


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ctx(tmp_path: Path, cmdline) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=_now(), repo=tmp_path, prev_state={},
                       allow_proc=True, pid_cmdline=cmdline)


def _lab(tmp_path, **extra):
    p = tmp_path / "optimus" / "lab_status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"utc": (_now() - timedelta(hours=2)).isoformat(),
                             "pid": 4242, "heartbeat_minutes": 5,
                             "periods_minutes": {"news_pull": 15},
                             "loops": {"news_pull": {"last_tick_utc": (_now() - timedelta(hours=2)).isoformat(),
                                                     "status": "ok"}},
                             **extra}), encoding="utf-8")




def test_a_lab_stopped_by_its_stop_file_is_stopped_by_operator(tmp_path):
    _lab(tmp_path, running=False, stopped_by="STOP_file")
    ctx = _ctx(tmp_path, cmdline=lambda pid: None)
    r = SH.p_always_on_lab(ctx)
    assert r.verdict == "STOPPED_BY_OPERATOR", r.detail
    assert "STOP_file" in r.proof
    loops = SH.p_lab_loops(ctx)
    assert {x.verdict for x in loops.values()} == {"STOPPED_BY_OPERATOR"}
    rows = [{"verdict": "STOPPED_BY_OPERATOR"}, {"verdict": "ALIVE"}]
    assert SH.exit_code(rows) == 0 and SH.counts(rows)["STOPPED_BY_OPERATOR"] == 1


def test_the_lock_exit_reason_is_also_a_stop_record_for_the_same_pid(tmp_path):
    _lab(tmp_path)
    lock = tmp_path / "optimus" / "always_on_lab_lock.json"
    lock.write_text(json.dumps({"pid": 4242, "exit_reason": "STOP_file",
                                "exit_utc": _now().isoformat()}), encoding="utf-8")
    assert SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: None)).verdict \
        == "STOPPED_BY_OPERATOR"
    lock.write_text(json.dumps({"pid": 9999, "exit_reason": "STOP_file"}), encoding="utf-8")
    assert SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: None)).verdict == "DEAD"


def test_a_crashed_lab_is_still_dead_even_with_a_stop_file_on_disk(tmp_path):
    _lab(tmp_path, running=True)
    od = tmp_path / "optimus"
    (od / "STOP").write_text("x", encoding="utf-8")        # a file is not a record
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: None))
    assert r.verdict == "DEAD"
    assert all(x.verdict != "STOPPED_BY_OPERATOR"
               for x in SH.p_lab_loops(_ctx(tmp_path, cmdline=lambda pid: None)).values())


def test_a_running_lab_with_a_stale_stop_record_is_not_stopped(tmp_path):
    _lab(tmp_path, running=False, stopped_by="STOP_file",
         utc=_now().isoformat())
    r = SH.p_always_on_lab(_ctx(tmp_path, cmdline=lambda pid: "python -m scripts.always_on_lab"))
    assert r.verdict == "ALIVE"


def test_empty_lock_files_are_not_zero_byte_receipts(tmp_path):
    now = _now()
    od = tmp_path / "optimus"
    (od / "dj").mkdir(parents=True)
    stamp = f"{now:%Y-%m-%d_%H%M%S}"
    (od / "dj" / f"plan_{stamp}.json").write_text('{"a":1}', encoding="utf-8")
    (od / "dj" / f"plan_{stamp}.json.lock").write_bytes(b"")
    (od / "dj" / f"seen_{stamp}.jsonl.lock").write_bytes(b"")
    r = SH.p_zero_byte_receipts(SH.ProbeCtx(optimus_dir=od, now=now, allow_proc=False))
    assert r.verdict == "ALIVE" and r.delta == 0, r.detail
    # the other direction: a real empty receipt beside them is still counted
    (od / "dj" / f"out_{stamp}.json").write_bytes(b"")
    r = SH.p_zero_byte_receipts(SH.ProbeCtx(optimus_dir=od, now=now, allow_proc=False))
    assert r.verdict == "STALE" and r.delta == 1 and ".lock" not in r.detail
