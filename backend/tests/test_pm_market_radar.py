"""CH-05 R1: the brief's market radar reads the funnel the CLI writes and
dates it by the receipt's own `generated_at`, never by the file's mtime.

The old radar read `docs/opportunity_funnel_run.json` (tracked, written by
nothing, generated 2026-08-10) and aged it by `st_mtime`, so a fresh checkout
reported an August screen as OK. Ported from the runtime checkout.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from backend import config as _config
from backend.services import pm_actions as PA


def _write(p, generated_at):
    p.write_text(json.dumps({"generated_at": generated_at, "universe": {"screened": 7},
                             "stages": [], "failures": {}, "candidates": [{"ticker": "X"}]}),
                 encoding="utf-8")
    return p


def test_the_radar_reads_the_file_the_funnel_writes():
    assert PA.MARKET_RADAR_PATH == _config.IC_FUNNEL_PATH


def test_an_old_receipt_with_a_fresh_mtime_is_stale(tmp_path):
    """A checkout touches every file today; the receipt's own stamp decides."""
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    p = _write(tmp_path / "f.json", old)
    now = time.time()
    os.utime(p, (now, now))
    out = PA._market_radar(p)
    assert out["status"] == "STALE" and out["age_hours"] > 900


def test_a_fresh_receipt_is_ok(tmp_path):
    fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    out = PA._market_radar(_write(tmp_path / "f.json", fresh))
    assert out["status"] == "OK" and out["universe_screened"] == 7


def test_an_undateable_receipt_is_unreadable_not_fresh(tmp_path):
    for bad in (None, "2026-11-01T00:00:00", "not a date",
                (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()):
        out = PA._market_radar(_write(tmp_path / "f.json", bad))
        assert out["status"] == "UNREADABLE", bad
