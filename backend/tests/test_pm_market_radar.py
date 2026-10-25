"""Offline receipt-route and provenance-clock regression tests for the PM radar."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from backend import config
from backend.services import pm_actions as P


@pytest.fixture
def clock(monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setattr(P.time, "time", lambda: now.timestamp())
    return now


def receipt(path, generated_at):
    payload = {
        "generated_at": generated_at,
        "universe": {"screened": 5333},
        "stages": {"stage1": 1500, "stage4": 25},
        "failures": {"stage1_truncated": {"eligible": 2858, "kept": 1500}},
        "evidence_basis": {
            "ranked_by": "profitability_small",
            "recorded_but_not_ranked_on": ["momentum"],
        },
        "candidates": [{"symbol": "FIRST"}, {"symbol": "SECOND"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_default_reads_canonical_funnel_and_preserves_preview(tmp_path, monkeypatch, clock):
    assert P.MARKET_RADAR_PATH == config.IC_FUNNEL_PATH
    canonical = tmp_path / "funnel_night10.json"
    payload = receipt(canonical, (clock - timedelta(hours=1)).isoformat())
    monkeypatch.setattr(P, "MARKET_RADAR_PATH", canonical)
    # Reading the radar must neither enrich names nor write a refreshed receipt.
    def forbidden(*args, **kwargs):
        pytest.fail("a saved radar read attempted acquisition or a write")
    monkeypatch.setattr(P, "enrich", forbidden)
    monkeypatch.setattr(type(canonical), "write_text", forbidden)
    monkeypatch.setattr(type(canonical), "write_bytes", forbidden)
    out = P._market_radar(top=1)
    assert out == {
        "status": "OK", "generated_at": payload["generated_at"], "age_hours": 1.0,
        "universe_screened": 5333, "stages": payload["stages"],
        "funnel_failures": payload["failures"], "ranked_by": "profitability_small",
        "not_ranked_on": ["momentum"], "candidates": [{"symbol": "FIRST"}],
    }


def test_explicit_override_does_not_read_default(tmp_path, monkeypatch, clock):
    override = tmp_path / "explicit.json"
    receipt(override, clock.isoformat())
    monkeypatch.setattr(P, "MARKET_RADAR_PATH", tmp_path / "absent-default.json")
    assert P._market_radar()["status"] == "NEVER RUN"
    out = P._market_radar(override)
    assert out["status"] == "OK"
    assert len(out["candidates"]) == 2


@pytest.mark.parametrize("age_hours,status", [(0, "OK"), (36, "OK"), (36.001, "STALE")])
def test_36_hour_boundary_uses_payload_not_file_clock(tmp_path, clock, age_hours, status):
    path = tmp_path / "radar.json"
    receipt(path, (clock - timedelta(hours=age_hours)).isoformat())
    # Both checkout/copy-fresh and old filesystem timestamps leave the verdict unchanged.
    for modified in (clock.timestamp(), (clock - timedelta(days=100)).timestamp()):
        os.utime(path, (modified, modified))
        out = P._market_radar(path)
        assert out["status"] == status
        assert out["age_hours"] == round(age_hours, 1)
        if status == "STALE":
            assert "must not be traded from" in out["consequence"]
            assert out["candidates"]  # Stale evidence remains visible as stale.


@pytest.mark.parametrize("zone", [timezone.utc, timezone(timedelta(hours=8)),
                                  timezone(timedelta(hours=-4))])
def test_offset_and_z_timestamps_represent_the_same_instant(tmp_path, clock, zone):
    path = tmp_path / "radar.json"
    stamp = (clock - timedelta(hours=2)).astimezone(zone).isoformat()
    if zone == timezone.utc:
        stamp = stamp.replace("+00:00", "Z")
    receipt(path, stamp)
    out = P._market_radar(path)
    assert out["status"] == "OK"
    assert out["age_hours"] == 2.0
    assert out["generated_at"] == stamp


@pytest.mark.parametrize("bad", [None, "", "not-a-date", 123, True,
                                "2026-01-01", "2026-01-01T01:00:00"])
def test_invalid_or_ambiguous_timestamp_never_falls_back_to_mtime(tmp_path, clock, bad):
    path = tmp_path / "radar.json"
    receipt(path, bad)
    os.utime(path, (clock.timestamp(), clock.timestamp()))
    out = P._market_radar(path)
    assert out["status"] == "UNREADABLE"
    assert out["error"]
    assert "NOT as an empty market" in out["consequence"]
    assert "candidates" not in out


@pytest.mark.parametrize("contents", ['{}', '[]', 'null', '{broken'])
def test_missing_stamp_or_unreadable_receipt_stays_explicit(tmp_path, contents):
    path = tmp_path / "radar.json"
    path.write_text(contents, encoding="utf-8")
    assert P._market_radar(path)["status"] == "UNREADABLE"


def test_future_stamp_is_unreadable_even_with_old_mtime(tmp_path, clock):
    path = tmp_path / "radar.json"
    receipt(path, (clock + timedelta(seconds=1)).isoformat())
    old = (clock - timedelta(days=100)).timestamp()
    os.utime(path, (old, old))
    out = P._market_radar(path)
    assert out["status"] == "UNREADABLE"
    assert "future" in out["error"]


def test_missing_receipt_keeps_never_run_contract(tmp_path):
    out = P._market_radar(tmp_path / "missing.json")
    assert out["status"] == "NEVER RUN"
    assert out["how"] == "python -m backend.services.opportunity_funnel"
    assert "watchlist" in out["consequence"]
