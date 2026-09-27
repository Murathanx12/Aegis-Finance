"""The disk guard: a full disk refuses by name and leaves the OLD file.

No real disk is filled: `disk_usage` and the file object are fakes.
2026-09-27 incident: C: reached 0 bytes and 13 receipts were truncated to zero.
"""

from __future__ import annotations

import errno
import json
from collections import namedtuple
from pathlib import Path

import pytest

from backend.services import disk_guard as DG

Usage = namedtuple("Usage", "total used free")


def _du(free_gb: float, total_gb: float = 953.0):
    return lambda p: Usage(int(total_gb * DG.GB), int((total_gb - free_gb) * DG.GB),
                           int(free_gb * DG.GB))


def test_require_free_refuses_by_name_with_the_measured_space(tmp_path):
    with pytest.raises(DG.DiskTooFull) as ei:
        DG.require_free(3, "night_backtest_factory", path=tmp_path, disk_usage=_du(1.5))
    msg = str(ei.value)
    assert "night_backtest_factory" in msg and "REFUSED" in msg
    assert "1.50 GB free" in msg and "3 GB required" in msg


def test_require_free_passes_and_returns_the_measurement(tmp_path):
    m = DG.require_free(3, "x", path=tmp_path / "not" / "yet", disk_usage=_du(12.0))
    assert m["free_gb"] == pytest.approx(12.0) and m["volume"]


def test_an_unmeasurable_volume_refuses_rather_than_passes(tmp_path):
    def broken(p):
        raise OSError("device not ready")
    with pytest.raises(DG.DiskTooFull, match="cannot measure"):
        DG.require_free(0, "x", path=tmp_path, disk_usage=broken)


def test_disk_too_full_is_an_oserror_so_existing_handlers_still_catch_it():
    assert issubclass(DG.DiskTooFull, OSError) and issubclass(DG.DiskTooFull, RuntimeError)


def test_atomic_write_json_round_trips_and_leaves_no_temp(tmp_path):
    p = tmp_path / "d" / "r.json"
    DG.atomic_write_json(p, {"a": 1, "b": "ü"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": "ü"}
    assert [x.name for x in p.parent.iterdir()] == ["r.json"]


class _EnospcMidway:
    """A file object that accepts nothing: ENOSPC on the first write."""

    def __init__(self, path, mode):
        self._real = open(path, mode)            # the temp exists, as on a real disk

    def write(self, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    def __getattr__(self, k):
        return getattr(self._real, k)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._real.close()


def test_enospc_midway_leaves_the_old_file_whole_and_no_temp(tmp_path, monkeypatch):
    p = tmp_path / "plan_2026-09-27_111242.json"
    p.write_text(json.dumps({"old": True}), encoding="utf-8")
    monkeypatch.setattr(DG, "_open", _EnospcMidway)
    with pytest.raises(DG.DiskTooFull, match="disk full writing"):
        DG.atomic_write_json(p, {"new": True})
    assert json.loads(p.read_text(encoding="utf-8")) == {"old": True}
    assert sorted(x.name for x in tmp_path.iterdir()) == [p.name]


def test_a_short_write_is_refused_and_the_old_file_kept(tmp_path, monkeypatch):
    """The temp reached the disk EMPTY (a write that 'succeeded' with 0 bytes)."""
    p = tmp_path / "r.json"
    p.write_text('{"old": 1}', encoding="utf-8")

    class Swallow(_EnospcMidway):
        def write(self, data):
            return len(data)                     # claims success, writes nothing
    monkeypatch.setattr(DG, "_open", Swallow)
    with pytest.raises(DG.DiskTooFull, match="short write"):
        DG.atomic_write_json(p, {"new": 1})
    assert p.read_text(encoding="utf-8") == '{"old": 1}'
    assert sorted(x.name for x in tmp_path.iterdir()) == ["r.json"]


def test_an_empty_text_is_refused_not_written(tmp_path):
    p = tmp_path / "q.txt"
    p.write_text("keep", encoding="utf-8")
    with pytest.raises(DG.DiskTooFull, match="EMPTY"):
        DG.atomic_write_text(p, "")
    assert p.read_text(encoding="utf-8") == "keep"


def test_a_non_parsing_json_temp_is_refused(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text('{"old": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        DG.atomic_write_text(p, "{not json", check_json=True)
    assert p.read_text(encoding="utf-8") == '{"old": 1}'
    assert sorted(x.name for x in tmp_path.iterdir()) == ["r.json"]


# ─────────────────────────── the start-up guards refuse by name, before any work

def test_dowjones_queue_refuses_by_name_before_reading(tmp_path, monkeypatch, capsys):
    from scripts import dowjones_pull as DJ
    q = tmp_path / "QUEUE.txt"
    q.write_text("--plan x\n", encoding="utf-8")
    ran = []
    monkeypatch.setattr(DJ, "run_queue", lambda *a, **k: ran.append(1) or {"lines": []})
    monkeypatch.setattr(DG, "_disk_usage", _du(1.0))
    assert DJ.main(["--queue", str(q)]) == 2
    assert not ran
    assert "REFUSED" in capsys.readouterr().out


def test_daily_pass_refuses_by_name_before_any_step(monkeypatch, capsys):
    from scripts import daily_pass as DP
    ran = []
    monkeypatch.setattr(DP, "run_daily_pass", lambda **k: ran.append(1))
    monkeypatch.setattr(DG, "_disk_usage", _du(0.5))
    assert DP.main([]) == 2
    assert not ran
    assert "daily_pass: REFUSED" in capsys.readouterr().out


def test_night_factory_refuses_by_name_before_loading_a_panel(monkeypatch, capsys):
    from scripts import night_backtest_factory as NF
    monkeypatch.setattr(DG, "_disk_usage", _du(0.5))
    monkeypatch.setattr(NF, "load_wide", lambda *a, **k: pytest.fail("loaded a panel"))
    assert NF.main(["--offline"]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_sim_run_refuses_at_start_and_stays_resumable(monkeypatch):
    from scripts import sim_run as SR
    finished = []
    monkeypatch.setattr(SR.SS, "status", lambda: {"session": {"id": "s1", "mode": "observe"}})
    monkeypatch.setattr(SR.SS, "finish", lambda state, why, extra=None: finished.append((state, why)))
    monkeypatch.setattr(DG, "_disk_usage", _du(0.5))
    assert SR.run("s1") == 4
    assert finished and finished[0][0] == "STOPPED" and "REFUSED" in finished[0][1]
