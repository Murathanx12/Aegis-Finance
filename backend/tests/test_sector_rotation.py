"""Tests for sector rotation model (unit tests, no network)."""

import pytest

from backend.services.sector_rotation import (
    _estimate_cycle_phase,
    _compute_rotation_signal,
)


class TestCyclePhaseEstimation:
    def test_early_recovery_leaders(self):
        result = _estimate_cycle_phase(["Consumer Disc.", "Financials", "Technology"])
        assert result["phase"] == "early_recovery"

    def test_late_cycle_leaders(self):
        result = _estimate_cycle_phase(["Energy", "Materials", "Healthcare"])
        assert result["phase"] == "late_cycle"

    def test_recession_leaders(self):
        result = _estimate_cycle_phase(["Consumer Staples", "Healthcare", "Utilities"])
        assert result["phase"] == "recession"

    def test_confidence_range(self):
        result = _estimate_cycle_phase(["Technology", "Industrials", "Materials"])
        assert 0 <= result["confidence"] <= 1

    def test_empty_leaders(self):
        result = _estimate_cycle_phase([])
        assert "phase" in result


class TestRotationSignal:
    def test_risk_on(self):
        sectors = [
            {"direction": "accelerating"} for _ in range(8)
        ] + [{"direction": "stable"} for _ in range(3)]
        result = _compute_rotation_signal(sectors)
        assert result["signal"] == "risk_on"

    def test_risk_off(self):
        sectors = [
            {"direction": "decelerating"} for _ in range(8)
        ] + [{"direction": "stable"} for _ in range(3)]
        result = _compute_rotation_signal(sectors)
        assert result["signal"] == "risk_off"

    def test_neutral(self):
        sectors = [
            {"direction": "accelerating"},
            {"direction": "decelerating"},
            {"direction": "stable"},
        ]
        result = _compute_rotation_signal(sectors)
        assert result["signal"] in ("neutral", "mildly_risk_on", "mildly_risk_off")

    def test_counts_correct(self):
        sectors = [
            {"direction": "accelerating"},
            {"direction": "improving"},
            {"direction": "decelerating"},
            {"direction": "stable"},
        ]
        result = _compute_rotation_signal(sectors)
        assert result["accelerating"] == 2
        assert result["decelerating"] == 1
        assert result["stable"] == 1
