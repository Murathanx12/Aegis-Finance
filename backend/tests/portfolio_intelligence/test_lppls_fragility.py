"""
Tests for the LPPLS descriptive-fragility flag (T1).

Pins the identity-level contract as hard as the math:
  - the flag is descriptive — it NEVER arms a lane (armed is hard-False),
  - a scheduled eval persists an lppls_eval row that the canary reads,
  - the forward-Brier harness scores skill vs climatology but reports
    insufficient_forward_data until enough matured observations exist,
  - TRIAL-LPPLS pre-registration is idempotent and enters the registry.
"""

import numpy as np
import pandas as pd
import pytest

from backend import db as db_module
from backend.db import count_cumulative_trials, get_connection, init_db
from backend.services.portfolio_intelligence import fragility as frag


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "frag.db"
    monkeypatch.setattr(db_module, "DB_PATH", db)
    init_db(db)
    return db


# ── evaluate_lppls + the never-arms invariant ─────────────────────────────────


def test_evaluate_lppls_maps_bubble_status(monkeypatch):
    monkeypatch.setattr(
        "backend.services.bubble_detector.get_bubble_status",
        lambda prices, ticker="SP500": {
            "confidence": 0.42, "is_bubble": False, "tc_date": "2026-09-01",
            "n_valid_fits": 7, "status": "normal",
        },
    )
    prices = pd.Series(np.linspace(100, 130, 200),
                       index=pd.date_range("2025-01-01", periods=200))
    out = frag.evaluate_lppls(prices)
    assert out["status"] == "evaluated"
    assert out["confidence"] == 0.42
    # Identity contract echoed into every reading:
    assert out["arms_lane"] is False
    assert out["descriptive_only"] is True
    assert "NOT a crash-timing forecaster" in out["label"]


def test_evaluate_lppls_handles_missing_lppls(monkeypatch):
    monkeypatch.setattr(
        "backend.services.bubble_detector.get_bubble_status",
        lambda prices, ticker="SP500": {"confidence": None, "status": "lppls not installed"},
    )
    prices = pd.Series(np.linspace(100, 130, 200),
                       index=pd.date_range("2025-01-01", periods=200))
    out = frag.evaluate_lppls(prices)
    assert out["status"] == "lppls_not_installed"
    assert out["confidence"] is None


def test_evaluate_lppls_short_series_is_data_unavailable():
    out = frag.evaluate_lppls(pd.Series([100.0, 101.0, 102.0]))
    assert out["status"] == "data_unavailable"


def test_persist_and_status_roundtrip_never_arms(tmp_db):
    from backend.services.portfolio_intelligence.scheduler import lppls_status

    frag.persist_lppls_eval(
        {"status": "evaluated", "confidence": 0.3, "is_bubble": False,
         "tc_date": None, "as_of": "2026-06-12", "arms_lane": False,
         "descriptive_only": True, "label": frag.LPPLS_LABEL},
        db_path=tmp_db,
    )
    st = lppls_status()
    assert st["status"] == "evaluated"
    assert st["operational"] is True
    assert st["armed"] is False  # HARD invariant
    assert st["confidence"] == 0.3


def test_status_never_evaluated(tmp_db):
    from backend.services.portfolio_intelligence.scheduler import lppls_status
    st = lppls_status()
    assert st["status"] == "never_evaluated"
    assert st["operational"] is False
    assert st["armed"] is False


# ── Brier skill (pure) ────────────────────────────────────────────────────────


def test_brier_perfect_forecast_has_full_skill():
    y = [0, 1, 0, 1, 1, 0]
    out = frag.brier_skill(forecasts=[float(v) for v in y], outcomes=y)
    assert out["brier_flag"] == pytest.approx(0.0, abs=1e-9)
    assert out["skill_score"] == pytest.approx(1.0, abs=1e-9)


def test_brier_climatology_forecast_has_zero_skill():
    y = np.array([0, 1, 0, 1, 0, 0, 1, 0])
    base = y.mean()
    out = frag.brier_skill(forecasts=[base] * len(y), outcomes=y)
    assert out["skill_score"] == pytest.approx(0.0, abs=1e-9)


def test_brier_worse_than_climatology_is_negative_skill():
    y = np.array([0, 0, 0, 0, 1])  # base rate 0.2
    out = frag.brier_skill(forecasts=[0.9] * 5, outcomes=y)  # confidently wrong
    assert out["skill_score"] < 0


def test_brier_no_data():
    assert frag.brier_skill([], [])["status"] == "no_data"


# ── realized drawdown helper ──────────────────────────────────────────────────


def test_realized_drawdown_detects_crash():
    idx = pd.date_range("2026-01-01", periods=45, freq="D")
    # ~-18% over 45 days → comfortably past -10% within the first 30 days.
    prices = pd.Series(np.linspace(100, 82, 45), index=idx)
    y = frag._realized_drawdown_within(prices, "2026-01-01", 30)
    assert y == 1


def test_realized_drawdown_flat_is_zero():
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    prices = pd.Series([100.0] * 60, index=idx)
    assert frag._realized_drawdown_within(prices, "2026-01-01", 30) == 0


def test_realized_drawdown_unmatured_is_none():
    idx = pd.date_range("2026-01-01", periods=10, freq="D")
    prices = pd.Series(np.linspace(100, 99, 10), index=idx)
    # window of 90 days but only 10 days of data → not matured
    assert frag._realized_drawdown_within(prices, "2026-01-01", 90) is None


# ── forward Brier status accumulates honestly ─────────────────────────────────


def test_forward_brier_insufficient_until_accumulated(tmp_db):
    # seed a handful of evaluated readings (< 30)
    for i in range(5):
        frag.persist_lppls_eval(
            {"status": "evaluated", "confidence": 0.2, "as_of": f"2026-05-0{i+1}"},
            db_path=tmp_db,
        )
    out = frag.forward_brier_status(db_path=tmp_db)
    assert out["status"] == "insufficient_forward_data"
    assert out["readings_accumulated"] == 5
    assert out["trial"] == "TRIAL-LPPLS"


# ── TRIAL-LPPLS pre-registration is idempotent ────────────────────────────────


def test_ensure_lppls_trial_idempotent(tmp_db):
    rid1 = frag.ensure_lppls_trial(db_path=tmp_db)
    assert count_cumulative_trials(get_connection(tmp_db)) == 1
    rid2 = frag.ensure_lppls_trial(db_path=tmp_db)
    assert rid1 == rid2  # same row, not a duplicate
    assert count_cumulative_trials(get_connection(tmp_db)) == 1

    conn = get_connection(tmp_db)
    try:
        row = conn.execute(
            "SELECT param, verdict, notes FROM rule_experiments WHERE id = ?", (rid1,)
        ).fetchone()
    finally:
        conn.close()
    assert row["param"] == frag.LPPLS_TRIAL_PARAM
    import json
    notes = json.loads(row["notes"])
    assert notes["decision_rule"]["trial"] == "TRIAL-LPPLS"
    assert notes["purpose"] == "experimental"
    assert "NEVER arms" in notes["decision_rule"]["hard_constraint"]


# ── /api/pi/fragility endpoint ────────────────────────────────────────────────


def test_fragility_endpoint(tmp_db):
    from fastapi.testclient import TestClient
    from backend.main import app

    frag.persist_lppls_eval(
        {"status": "evaluated", "confidence": 0.25, "is_bubble": False,
         "as_of": "2026-06-12", "arms_lane": False, "label": frag.LPPLS_LABEL},
        db_path=tmp_db,
    )
    body = TestClient(app).get("/api/pi/fragility").json()
    assert body["latest_reading"]["armed"] is False
    assert body["forward_brier"]["status"] == "insufficient_forward_data"
    assert body["trial"]["trial"] == "TRIAL-LPPLS"
    assert "arms a lane" in body["disclaimer"].lower()
