"""Lane M3: the backtest leaderboard's age can go red, can go green, and an
undateable stamp is UNKNOWN. Synthetic folders; dates derived from now."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.services import backtest_staleness as BS
from backend.services import system_health as SH


def _write(d, when: datetime, *, body_run: str | None = "same", name: str | None = None):
    rid = when.strftime("%Y-%m-%dT%H%M%SZ")
    body = {"run_id": rid if body_run == "same" else body_run, "date": str(when.date())}
    p = d / (name or f"leaderboard_{rid}.json")
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


def test_a_fresh_board_is_alive(tmp_path):
    now = datetime.now(timezone.utc)
    _write(tmp_path, now - timedelta(days=1))
    r = BS.leaderboard_age(tmp_path, now, stale_days=7)
    assert r["verdict"] == "ALIVE" and 80000 < r["age_s"] < 90000


def test_an_old_board_goes_stale_and_names_the_remedy(tmp_path):
    now = datetime.now(timezone.utc)
    _write(tmp_path, now - timedelta(days=9))
    r = BS.leaderboard_age(tmp_path, now, stale_days=7)
    assert r["verdict"] == "STALE" and "night_backtest_factory" in r["detail"]


def test_the_newest_by_name_wins_and_mtime_is_never_read(tmp_path):
    now = datetime.now(timezone.utc)
    new = _write(tmp_path, now - timedelta(days=1))
    old = _write(tmp_path, now - timedelta(days=30))
    old.touch()                                   # the older file is now "written today"
    r = BS.leaderboard_age(tmp_path, now, stale_days=7)
    assert r["run_id"] in new.name and r["verdict"] == "ALIVE"
    new.unlink()
    assert BS.leaderboard_age(tmp_path, now, stale_days=7)["verdict"] == "STALE"


def test_no_board_or_an_undateable_board_is_unknown(tmp_path):
    now = datetime.now(timezone.utc)
    assert BS.leaderboard_age(tmp_path, now)["verdict"] == "UNKNOWN"
    # a date-named 'latest' copy carries no run stamp: it is not read as one
    (tmp_path / f"leaderboard_{now.date()}.json").write_text("{}", encoding="utf-8")
    assert BS.leaderboard_age(tmp_path, now)["verdict"] == "UNKNOWN"
    # a stamp shaped right but not a real time
    (tmp_path / "leaderboard_2026-13-45T999999Z.json").write_text("{}", encoding="utf-8")
    assert BS.leaderboard_age(tmp_path, now)["verdict"] == "UNKNOWN"


def test_a_body_that_disagrees_with_its_name_is_unknown(tmp_path):
    now = datetime.now(timezone.utc)
    _write(tmp_path, now - timedelta(days=1), body_run="1999-01-01T000000Z")
    assert BS.leaderboard_age(tmp_path, now)["verdict"] == "UNKNOWN"


def test_the_threshold_comes_from_config():
    from backend import config as C
    assert BS._threshold_days() == float(C.BACKTEST_LEADERBOARD_STALE_DAYS)


def test_registered_in_system_health_and_both_directions_through_run_probes(tmp_path):
    assert any(p.name == "backtest_leaderboard" for p in SH.PROBES)
    lib = tmp_path / "strategy_library"
    lib.mkdir()
    now = datetime.now(timezone.utc)
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=now, allow_proc=False)
    rows = SH.run_probes(ctx, only={"backtest_leaderboard"})
    assert [r["verdict"] for r in rows] == ["UNKNOWN"]
    _write(lib, now - timedelta(days=40))
    assert SH.run_probes(ctx, only={"backtest_leaderboard"})[0]["verdict"] == "STALE"
    _write(lib, now - timedelta(hours=3))
    assert SH.run_probes(ctx, only={"backtest_leaderboard"})[0]["verdict"] == "ALIVE"
