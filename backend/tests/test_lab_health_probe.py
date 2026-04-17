"""Tests for lab/health_probe.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

LAB = Path(__file__).parent.parent.parent / "lab"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import health_probe  # noqa: E402


def test_probe_all_shape_and_keys():
    with patch.object(health_probe, "_probe_dns", return_value={"ok": True}), \
         patch.object(health_probe, "_probe_yfinance", return_value={"ok": True, "rows": 5}), \
         patch.object(health_probe, "_probe_fred", return_value={"ok": True, "rows": 100}):
        out = health_probe.probe_all()
    assert set(out.keys()) == {"healthy", "live_sources", "total_sources", "results"}
    assert out["healthy"] is True
    assert out["live_sources"] == 3
    assert out["total_sources"] == 3


def test_probe_all_unhealthy_when_yfinance_down():
    with patch.object(health_probe, "_probe_dns", return_value={"ok": True}), \
         patch.object(health_probe, "_probe_yfinance", return_value={"ok": False, "error": "timeout"}), \
         patch.object(health_probe, "_probe_fred", return_value={"ok": True, "rows": 100}):
        out = health_probe.probe_all()
    assert out["healthy"] is False
    assert out["live_sources"] == 2


def test_probe_all_healthy_when_fred_down_but_yf_up():
    with patch.object(health_probe, "_probe_dns", return_value={"ok": True}), \
         patch.object(health_probe, "_probe_yfinance", return_value={"ok": True, "rows": 5}), \
         patch.object(health_probe, "_probe_fred", return_value={"ok": False, "error": "no key"}):
        out = health_probe.probe_all()
    # yfinance is the floor — FRED outage is tolerated
    assert out["healthy"] is True
    assert out["live_sources"] == 2
