"""`openclaw_temp`: the sweep of `openclaw-plugin-build-*` and its health probe.

tmp_path only. No test touches the real temp dir, the network or the real CLI;
every date derives from `now`.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.services import openclaw_client as OC
from backend.services import openclaw_temp as OT
from backend.services import system_health as SH

PREFIX = OT.PREFIX


def _folder(root: Path, name: str, *, age_min: float, now: float, mb: int = 0) -> Path:
    d = root / name
    (d / "package-0" / "node_modules" / "x").mkdir(parents=True)
    (d / "package-0" / "node_modules" / "x" / "index.js").write_bytes(b"a" * 1000)
    if mb:
        (d / "blob.bin").write_bytes(b"\0" * (mb * 1024 * 1024))
    t = now - age_min * 60
    for p in [*d.rglob("*"), d]:
        os.utime(p, (t, t))
    return d


def _sweep(tmp: Path, now: float, **kw):
    kw.setdefault("process_starts", [])
    kw.setdefault("receipt", tmp / "receipt.jsonl")
    return OT.sweep_plugin_builds(15, temp_dir=tmp / "Temp", now=now, **kw)


@pytest.fixture
def temp(tmp_path):
    (tmp_path / "Temp").mkdir()
    return tmp_path


def _link_dir(link: Path, target: Path) -> str:
    """A junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return "junction"
    os.symlink(target, link, target_is_directory=True)
    return "symlink"


# ─────────────────────────────────────────────────────── what goes, what stays

def test_an_old_folder_is_deleted_and_the_receipt_counts_it(temp):
    now = time.time()
    old = _folder(temp / "Temp", PREFIX + "old111", age_min=60, now=now)
    r = _sweep(temp, now)
    assert not old.exists()
    assert r["deleted"] == 1 and r["bytes_freed"] >= 1000 and r["ok"]
    rows = [json.loads(l) for l in (temp / "receipt.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["deleted"] == 1


def test_a_recent_folder_is_kept(temp):
    now = time.time()
    new = _folder(temp / "Temp", PREFIX + "new111", age_min=5, now=now)
    r = _sweep(temp, now)
    assert new.exists() and r["kept_recent"] == 1 and r["deleted"] == 0


def test_a_file_with_the_prefix_and_a_non_matching_folder_are_kept(temp):
    now = time.time()
    f = temp / "Temp" / (PREFIX + "afile")
    f.write_text("x")
    other = _folder(temp / "Temp", "openclaw-model-catalog-abc", age_min=600, now=now)
    other2 = _folder(temp / "Temp", "something-else", age_min=600, now=now)
    t = now - 3600
    os.utime(f, (t, t))
    r = _sweep(temp, now)
    assert f.exists() and other.exists() and other2.exists()
    assert r["deleted"] == 0 and r["skipped_files"] == 1


def test_a_link_inside_a_folder_is_unlinked_and_its_target_survives(temp):
    now = time.time()
    target = temp / "openclaw_install"
    target.mkdir()
    (target / "keep.txt").write_text("the real install")
    old = _folder(temp / "Temp", PREFIX + "link11", age_min=60, now=now)
    try:
        _link_dir(old / "package-0" / "node_modules" / "openclaw", target)
    except OSError as exc:
        pytest.skip(f"cannot create a directory link here: {exc}")
    r = _sweep(temp, now)
    assert not old.exists() and r["deleted"] == 1
    assert (target / "keep.txt").read_text() == "the real install"


def test_a_top_level_link_with_the_prefix_is_not_followed(temp):
    now = time.time()
    target = temp / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = temp / "Temp" / (PREFIX + "toplnk")
    try:
        _link_dir(link, target)
    except OSError as exc:
        pytest.skip(f"cannot create a directory link here: {exc}")
    r = _sweep(temp, now + 7200)
    assert link.exists() or os.path.lexists(link)
    assert (target / "keep.txt").exists()
    assert r["skipped_links"] == 1 and r["deleted"] == 0


# ─────────────────────────────────────────────────── locked, vanished, budget

@pytest.mark.skipif(os.name != "nt", reason="an open handle blocks deletion only on Windows")
def test_a_locked_folder_is_counted_and_the_sweep_continues(temp):
    now = time.time()
    locked = _folder(temp / "Temp", PREFIX + "lock11", age_min=90, now=now)
    fine = _folder(temp / "Temp", PREFIX + "fine11", age_min=60, now=now)
    fh = open(locked / "package-0" / "node_modules" / "x" / "index.js", "rb")
    try:
        r = _sweep(temp, now)
    finally:
        fh.close()
    assert r["failed"] == 1 and r["deleted"] == 1 and not fine.exists()
    assert r["errors"] and "lock11" in r["errors"][0]


def test_a_folder_that_vanishes_mid_sweep_does_not_raise(temp, monkeypatch):
    now = time.time()
    _folder(temp / "Temp", PREFIX + "gone11", age_min=60, now=now)
    kept = _folder(temp / "Temp", PREFIX + "next11", age_min=30, now=now)
    real = OT._remove_tree

    def flaky(path, deadline=None):
        if "gone11" in path:
            raise FileNotFoundError(path)
        return real(path, deadline)
    monkeypatch.setattr(OT, "_remove_tree", flaky)
    r = _sweep(temp, now)
    assert r["vanished"] == 1 and r["deleted"] == 1 and not kept.exists()


def test_the_budget_defers_the_rest(temp):
    now = time.time()
    for i in range(3):
        _folder(temp / "Temp", PREFIX + f"bud{i:03d}", age_min=60 + i, now=now)
    r = _sweep(temp, now, max_seconds=0.0)
    assert r["deleted"] == 0 and r["deferred"] == 3


def test_a_folder_born_just_after_a_live_openclaw_process_started_is_kept(temp):
    now = time.time()
    d = _folder(temp / "Temp", PREFIX + "gate11", age_min=60, now=now)
    birth = OT._birth(os.stat(d))
    r = _sweep(temp, now, process_starts=[birth - 10])
    assert d.exists() and r["kept_protected"] == 1
    r = _sweep(temp, now, process_starts=None)        # scan failed: 24 h floor
    assert d.exists() and r["process_scan"] == "failed"
    r = _sweep(temp, now + 25 * 3600, process_starts=None)
    assert not d.exists() and r["deleted"] == 1


def test_an_unreadable_temp_dir_is_ok_false_not_a_raise(tmp_path):
    r = OT.sweep_plugin_builds(15, temp_dir=tmp_path / "missing", now=time.time(),
                               process_starts=[], receipt=False)
    assert r["ok"] is False and "error" in r


# ─────────────────────────────────────────────────────── the client's hook

@pytest.fixture
def hook(monkeypatch):
    monkeypatch.setattr(OT, "hooks_enabled", lambda: True)
    monkeypatch.setitem(OT._STATE, "last", None)
    monkeypatch.setitem(OT._STATE, "running", False)
    calls = []
    monkeypatch.setattr(OT, "sweep_plugin_builds", lambda *a, **k: calls.append(a) or {})
    return calls


def test_the_rate_limit_holds(hook):
    now = time.time()
    assert OT.after_cli_call(now=now, inline=True) == "ran"
    assert OT.after_cli_call(now=now + 60, inline=True) == "rate_limited"
    assert OT.after_cli_call(now=now + 599, inline=True) == "rate_limited"
    assert OT.after_cli_call(now=now + 601, inline=True) == "ran"
    assert len(hook) == 2


def test_hooks_are_off_under_pytest_by_default():
    assert OT.hooks_enabled() is False
    assert OT.after_cli_call(inline=True) == "disabled"


def test_a_cli_call_returns_its_result_when_the_sweep_raises(monkeypatch):
    monkeypatch.setattr(OT, "hooks_enabled", lambda: True)
    monkeypatch.setitem(OT._STATE, "last", None)
    monkeypatch.setitem(OT._STATE, "running", False)

    def boom(*a, **k):
        raise RuntimeError("sweep exploded")
    monkeypatch.setattr(OT, "sweep_plugin_builds", boom)
    real_after = OT.after_cli_call
    monkeypatch.setattr(OT, "after_cli_call", lambda **k: real_after(inline=True))
    monkeypatch.setattr(OC, "_resolve_cli", lambda: {
        "bin": "x", "shim": None, "route": "exec", "prefix": ["openclaw-fake"]})
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "Version 1", ""))
    r = OC._run(["--version"])
    assert r.returncode == 0 and r.stdout == "Version 1"
    assert "sweep exploded" in (OT._STATE["last_error"] or "")

    # and an after_cli_call that itself raises is swallowed by the client
    monkeypatch.setattr(OT, "after_cli_call", lambda **k: 1 / 0)
    r = OC._run(["--version"])
    assert r.returncode == 0 and r.stdout == "Version 1"


# ─────────────────────────────────────────────────────────────── the probe

def _ctx(tmp_path: Path, temp_dir: Path | None) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(exist_ok=True)
    paths = {} if temp_dir is None else {"openclaw_temp_dir": temp_dir}
    return SH.ProbeCtx(optimus_dir=od, now=datetime.now(timezone.utc), repo=tmp_path,
                       paths=paths)


def test_the_probe_is_red_above_the_count_threshold_and_green_below(temp, monkeypatch):
    now = time.time()
    monkeypatch.setattr(OT._config, "OPENCLAW_TEMP_DEGRADED_COUNT", 2, raising=False)
    monkeypatch.setattr(OT._config, "OPENCLAW_TEMP_DEGRADED_GB", 100.0, raising=False)
    for i in range(2):
        _folder(temp / "Temp", PREFIX + f"cnt{i:03d}", age_min=5, now=now)
    r = OT.p_openclaw_temp_builds(_ctx(temp, temp / "Temp"))
    assert r.verdict == "ALIVE" and "2 " in r.detail
    _folder(temp / "Temp", PREFIX + "cnt999", age_min=5, now=now)
    r = OT.p_openclaw_temp_builds(_ctx(temp, temp / "Temp"))
    assert r.verdict == "STALE" and r.detail.startswith("DEGRADED")


def test_the_probe_is_red_above_the_size_threshold(temp, monkeypatch):
    now = time.time()
    monkeypatch.setattr(OT._config, "OPENCLAW_TEMP_DEGRADED_COUNT", 100, raising=False)
    monkeypatch.setattr(OT._config, "OPENCLAW_TEMP_DEGRADED_GB", 1 / 1024, raising=False)  # 1 MB
    _folder(temp / "Temp", PREFIX + "big111", age_min=5, now=now, mb=2)
    r = OT.p_openclaw_temp_builds(_ctx(temp, temp / "Temp"))
    assert r.verdict == "STALE" and "DEGRADED" in r.detail


def test_the_probe_is_unknown_when_the_temp_dir_cannot_be_read(tmp_path):
    r = OT.p_openclaw_temp_builds(_ctx(tmp_path, tmp_path / "no_such_dir"))
    assert r.verdict == "UNKNOWN" and "cannot list" in r.detail
    r = OT.p_openclaw_temp_builds(_ctx(tmp_path, None))      # test ctx: never the real Temp
    assert r.verdict == "UNKNOWN"


def test_the_probe_is_time_boxed_count_exact_size_sampled(temp):
    now = time.time()
    for i in range(5):
        _folder(temp / "Temp", PREFIX + f"box{i:03d}", age_min=5, now=now)
    m = OT.measure_builds(temp / "Temp", budget_s=0.0)
    assert m["count"] == 5 and m["sized"] == 0 and m["est_bytes"] is None
    m = OT.measure_builds(temp / "Temp", budget_s=5.0)
    assert m["count"] == 5 and m["sized"] == 5 and m["size_exact"]
