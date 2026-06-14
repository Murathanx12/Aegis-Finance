"""
Tests for backend/services/macro_indicators.py (T3 — SOS recession flag).

The SOS indicator is a recession-CONFIRMATION flag (coincident-to-lagging). These
tests pin the math AND the honesty contract: the surfaced framing must carry no
leading-indicator / prediction language.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.macro_indicators import (
    RECESSION_FRAMING,
    SOS_THRESHOLD_PP,
    compute_sos_signal,
    recession_indicators,
)


def _weekly(values) -> pd.Series:
    idx = pd.date_range(end="2026-06-12", periods=len(values), freq="W")
    return pd.Series(values, index=idx, dtype=float)


# ── SOS math ────────────────────────────────────────────────────────────────


def test_sos_no_data():
    assert compute_sos_signal(None)["status"] == "no_data"
    assert compute_sos_signal(_weekly([]))["status"] == "no_data"


def test_sos_insufficient_history():
    out = compute_sos_signal(_weekly([1.2] * 40))  # < 26+52 weeks
    assert out["status"] == "insufficient_history"
    assert out["triggered"] is None


def test_sos_flat_series_does_not_trigger():
    out = compute_sos_signal(_weekly([1.2] * 120))
    assert out["status"] == "ok"
    assert out["value"] == pytest.approx(0.0, abs=1e-9)
    assert out["triggered"] is False


def test_sos_rising_rate_triggers():
    # 90 weeks flat at 1.2 (establishes the prior trough), then a clear ramp up.
    vals = [1.2] * 90 + list(np.linspace(1.25, 2.2, 30))
    out = compute_sos_signal(_weekly(vals))
    assert out["status"] == "ok"
    assert out["triggered"] is True
    assert out["value"] >= SOS_THRESHOLD_PP
    # The MA sits above its prior-52-week trough.
    assert out["ma_26w"] > out["prior_52w_min"]


def test_sos_small_rise_below_threshold_does_not_trigger():
    # A rise of only ~0.1pp in the MA — below the 0.2pp trigger.
    vals = [1.2] * 90 + list(np.linspace(1.2, 1.32, 30))
    out = compute_sos_signal(_weekly(vals))
    assert out["status"] == "ok"
    assert 0.0 < out["value"] < SOS_THRESHOLD_PP
    assert out["triggered"] is False


# ── recession_indicators bundle ───────────────────────────────────────────────


def test_recession_indicators_bundles_sahm_and_sos():
    fred = {
        "sahm_rule": _weekly([0.1, 0.2, 0.33]),
        "insured_unemployment_rate": _weekly([1.2] * 120),
    }
    out = recession_indicators(fred)
    assert set(out) == {"sahm", "sos", "framing"}
    assert out["sahm"]["status"] == "ok"
    assert out["sahm"]["triggered"] is False  # 0.33 < 0.50
    assert out["sos"]["status"] == "ok"


def test_recession_indicators_handle_missing_series():
    out = recession_indicators({})
    assert out["sahm"]["status"] == "no_data"
    assert out["sos"]["status"] == "no_data"


# ── The honesty contract: NO leading-indicator / prediction language ──────────


def test_framing_has_no_prediction_language():
    text = RECESSION_FRAMING.lower()
    forbidden = [
        "predicts", "forecast", "leading indicator", "early warning",
        "imminent", "will crash", "foresees", "ahead of the",
    ]
    for term in forbidden:
        assert term not in text, f"framing must not claim prediction: {term!r}"
    # And it must positively carry the honest anchors.
    assert "coincident-to-lagging" in text
    assert "lag-to-onset" in text
    assert "not a prediction" in text
    assert "measured forward" in text


# ── Endpoint wiring (no network — fetcher mocked) ─────────────────────────────


def test_macro_endpoint_exposes_recession_indicators(monkeypatch):
    from fastapi.testclient import TestClient

    import backend.services.data_fetcher as df_mod
    from backend.cache import cache_clear
    from backend.main import app

    synthetic = {
        "sahm_rule": _weekly([0.1, 0.2, 0.4]),
        "insured_unemployment_rate": _weekly([1.2] * 120),
        "unemployment": _weekly([3.8] * 30),
    }
    monkeypatch.setattr(
        df_mod.DataFetcher, "fetch_fred_data", lambda self: synthetic
    )
    cache_clear()  # ensure _compute_macro actually runs

    body = TestClient(app).get("/api/macro").json()
    assert "recession_indicators" in body
    ri = body["recession_indicators"]
    assert ri["sahm"]["status"] == "ok"
    assert ri["sos"]["status"] == "ok"
    assert "coincident-to-lagging" in ri["framing"].lower()
    cache_clear()  # don't leak the synthetic result to other tests
