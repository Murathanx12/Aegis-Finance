"""
Tests for the descriptive structural-fragility composite + TRIAL-CRASH.

Pins the aggregation math, graceful degradation, the forward-Brier accumulation,
idempotent TRIAL-CRASH pre-registration, and — hardest — the identity contract:
the composite is descriptive, never arms a lane, and NO lane/rebalance code path
reads it (grep-guard).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import db as db_module
from backend.db import count_cumulative_trials, get_connection, init_db
from backend.services.portfolio_intelligence import fragility as frag


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "frag_comp.db"
    monkeypatch.setattr(db_module, "DB_PATH", db)
    init_db(db)
    return db


def _patch_subsignals(monkeypatch, *, lppls=0.4, sos=0.1, sahm=0.2,
                      turb_pctl=80.0, absorption=0.7):
    monkeypatch.setattr(frag, "evaluate_lppls",
                        lambda prices: {"status": "evaluated", "confidence": lppls})
    monkeypatch.setattr(
        "backend.services.macro_indicators.recession_indicators",
        lambda fred: {"sos": {"status": "ok", "value": sos},
                      "sahm": {"status": "ok", "value": sahm}},
    )
    monkeypatch.setattr(
        "backend.services.systemic_risk.compute_systemic_risk",
        lambda data: {"turbulence_percentile": turb_pctl,
                      "absorption_ratio_current": absorption},
    )
    # Net liquidity expanding steadily → low fragility, but available.
    hist = [{"net_liquidity": 6.0 + 0.01 * i} for i in range(52)]
    monkeypatch.setattr(
        "backend.services.net_liquidity.get_net_liquidity",
        lambda: {"history": hist, "current": {"net_liquidity": 6.5}},
    )


def _synthetic_inputs():
    idx = pd.date_range(end="2026-06-12", periods=300, freq="D")
    data = pd.DataFrame({"SP500": np.linspace(100, 130, 300)}, index=idx)
    fred = {
        "hy_oas": pd.Series(np.arange(1, 101, dtype=float)),   # last → pctl 1.0
        "ig_oas": pd.Series(np.arange(100, 0, -1, dtype=float)),  # last → pctl 0.01
    }
    return data, fred


# ── aggregation math ──────────────────────────────────────────────────────────


def test_composite_equal_weights_available_inputs(monkeypatch):
    _patch_subsignals(monkeypatch)
    data, fred = _synthetic_inputs()
    out = frag.compute_fragility_index(data=data, fred_data=fred)

    assert out["status"] == "ok"
    assert out["n_inputs"] == 8  # all 8 active inputs resolved
    comp = out["components"]
    assert comp["lppls_confidence"]["normalized"] == 0.4
    assert comp["sos"]["normalized"] == pytest.approx(0.2)       # 0.1/0.5
    assert comp["sahm"]["normalized"] == pytest.approx(0.2)      # 0.2/1.0
    assert comp["turbulence"]["normalized"] == pytest.approx(0.8)
    assert comp["absorption_ratio"]["normalized"] == pytest.approx(0.7)
    assert comp["hy_oas"]["normalized"] == pytest.approx(1.0)
    assert comp["ig_oas"]["normalized"] == pytest.approx(0.01)

    # composite is the equal-weighted mean of the available normalized inputs
    norms = [c["normalized"] for c in comp.values() if c["available"]]
    assert out["composite"] == pytest.approx(round(float(np.mean(norms)), 4))
    assert 0.0 <= out["composite"] <= 1.0
    assert "descriptive" in out["level"]
    assert out["arms_lane"] is False


def test_composite_graceful_degradation(monkeypatch):
    # Only LPPLS resolves; everything else unavailable.
    monkeypatch.setattr(frag, "evaluate_lppls",
                        lambda prices: {"status": "evaluated", "confidence": 0.6})
    monkeypatch.setattr("backend.services.macro_indicators.recession_indicators",
                        lambda fred: {"sos": {"status": "no_data"}, "sahm": {"status": "no_data"}})
    monkeypatch.setattr("backend.services.systemic_risk.compute_systemic_risk",
                        lambda data: {"turbulence_percentile": None, "absorption_ratio_current": None})
    monkeypatch.setattr("backend.services.net_liquidity.get_net_liquidity",
                        lambda: {"history": []})
    idx = pd.date_range(end="2026-06-12", periods=300, freq="D")
    data = pd.DataFrame({"SP500": np.linspace(100, 130, 300)}, index=idx)
    out = frag.compute_fragility_index(data=data, fred_data={})  # no OAS either
    assert out["status"] == "ok"
    assert out["n_inputs"] == 1
    assert out["composite"] == pytest.approx(0.6)


def test_composite_no_inputs(monkeypatch):
    monkeypatch.setattr(frag, "evaluate_lppls", lambda prices: {"status": "eval_error"})
    monkeypatch.setattr("backend.services.macro_indicators.recession_indicators",
                        lambda fred: {"sos": {"status": "no_data"}, "sahm": {"status": "no_data"}})
    monkeypatch.setattr("backend.services.systemic_risk.compute_systemic_risk",
                        lambda data: {"turbulence_percentile": None, "absorption_ratio_current": None})
    monkeypatch.setattr("backend.services.net_liquidity.get_net_liquidity", lambda: {"history": []})
    idx = pd.date_range(end="2026-06-12", periods=300, freq="D")
    data = pd.DataFrame({"SP500": np.linspace(100, 130, 300)}, index=idx)
    out = frag.compute_fragility_index(data=data, fred_data={})
    assert out["status"] == "no_inputs"
    assert out["composite"] is None


def test_candidate_inputs_logged_not_active(monkeypatch):
    _patch_subsignals(monkeypatch)
    data, fred = _synthetic_inputs()
    out = frag.compute_fragility_index(data=data, fred_data=fred)
    names = [c["name"] for c in out["candidate_inputs"]]
    assert "ipo_issuance" in names  # Murat's feature: candidate, not asserted
    assert "ipo_issuance" not in out["components"]  # NOT an active input yet


# ── persistence + forward Brier ───────────────────────────────────────────────


def test_persist_and_forward_brier_accumulates(tmp_db, monkeypatch):
    _patch_subsignals(monkeypatch)
    data, fred = _synthetic_inputs()
    result = frag.compute_fragility_index(data=data, fred_data=fred)
    frag.persist_fragility_eval(result, db_path=tmp_db)

    fb = frag.forward_brier_status_composite(db_path=tmp_db)
    assert fb["status"] == "insufficient_forward_data"
    assert fb["readings_accumulated"] == 1
    assert fb["trial"] == "TRIAL-CRASH"
    assert fb["crash_threshold"] == 0.20


def test_realized_drawdown_20pct_threshold():
    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    # ~-30% over 40 days → clears -20% comfortably within the first 30 days.
    prices = pd.Series(np.linspace(100, 70, 40), index=idx)
    assert frag._realized_drawdown_within(prices, "2026-01-01", 30, threshold=0.20) == 1
    mild = pd.Series(np.linspace(100, 90, 40), index=idx)    # -10%, below 20%
    assert frag._realized_drawdown_within(mild, "2026-01-01", 30, threshold=0.20) == 0


# ── TRIAL-CRASH pre-registration ──────────────────────────────────────────────


def test_ensure_crash_trial_idempotent_and_raw_floor_only(tmp_db):
    rid1 = frag.ensure_crash_trial(db_path=tmp_db)
    assert count_cumulative_trials(get_connection(tmp_db)) == 1  # raw floor +1
    rid2 = frag.ensure_crash_trial(db_path=tmp_db)
    assert rid1 == rid2
    assert count_cumulative_trials(get_connection(tmp_db)) == 1

    # Non-lane trial → effective-N (lanes-only) is unaffected by it.
    from backend.services.portfolio_intelligence.experiment_registry import (
        effective_independent_trials,
    )
    eff = effective_independent_trials(db_path=tmp_db)
    assert eff["n_lanes"] == 0  # the crash trial added no return stream

    conn = get_connection(tmp_db)
    try:
        row = conn.execute(
            "SELECT param, lane_id, notes FROM rule_experiments WHERE id = ?", (rid1,)
        ).fetchone()
    finally:
        conn.close()
    assert row["param"] == frag.CRASH_TRIAL_PARAM
    assert row["lane_id"] is None
    import json
    notes = json.loads(row["notes"])
    assert notes["decision_rule"]["trial"] == "TRIAL-CRASH"
    assert "NEVER arms" in notes["decision_rule"]["hard_constraint"]


# ── identity contract: NO lane/rebalance path reads the composite ─────────────


def test_grep_guard_no_lane_path_reads_composite():
    base = Path(__file__).resolve().parents[2] / "services" / "portfolio_intelligence"
    forbidden_tokens = ["compute_fragility_index", "fragility_composite",
                        "FRAGILITY_LABEL", "forward_brier_status_composite"]
    # The decision/rebalance path must never import or read the composite.
    for fname in ("rules.py", "rebalancer.py", "reference_engine.py"):
        text = (base / fname).read_text(encoding="utf-8")
        for tok in forbidden_tokens:
            assert tok not in text, f"{fname} must not reference the composite ({tok})"
        # And must not import the fragility module at all on the decision path.
        assert "import fragility" not in text and "fragility import" not in text, (
            f"{fname} must not import the fragility module")


# ── endpoint ──────────────────────────────────────────────────────────────────


def test_fragility_endpoint_exposes_composite(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    _patch_subsignals(monkeypatch)
    # Make the endpoint's internal fetch use our synthetic data (no network).
    data, fred = _synthetic_inputs()
    monkeypatch.setattr(
        "backend.services.data_fetcher.DataFetcher.fetch_market_data",
        lambda self: (data, None),
    )
    monkeypatch.setattr(
        "backend.services.data_fetcher.DataFetcher.fetch_fred_data",
        lambda self: fred,
    )

    body = TestClient(app).get("/api/pi/fragility").json()
    assert "composite" in body
    assert body["composite"]["status"] == "ok"
    assert body["composite"]["arms_lane"] is False
    assert body["composite_forward_brier"]["status"] == "insufficient_forward_data"
    assert body["composite_trial"]["trial"] == "TRIAL-CRASH"
    assert "imminent" in body["disclaimer"].lower()  # explicitly disclaims it


# ── lead/lag transparency labels (Chunk 3, research 2026-06-14) ───────────────


def test_research_graded_lead_lag_labels(monkeypatch):
    _patch_subsignals(monkeypatch)
    data, fred = _synthetic_inputs()
    out = frag.compute_fragility_index(data=data, fred_data=fred)
    comp = out["components"]
    # The two the deep research graded explicitly.
    assert comp["turbulence"]["lead_lag"] == "coincident"
    assert comp["absorption_ratio"]["lead_lag"] == "leading"
    # By-construction calls.
    assert comp["sahm"]["lead_lag"] == "lagging"
    assert comp["sos"]["lead_lag"] == "lagging"
    assert comp["lppls_confidence"]["lead_lag"] == "leading"
    # Every available component carries a class + a note.
    for c in comp.values():
        if c["available"]:
            assert c["lead_lag"] in {"leading", "coincident", "lagging", "unclassified"}
            assert isinstance(c["lead_lag_note"], str) and c["lead_lag_note"]
    assert "equal-weighted over ALL" in out["lead_lag_note"]


def test_leading_composite_is_equal_weight_subset(monkeypatch):
    _patch_subsignals(monkeypatch)
    data, fred = _synthetic_inputs()
    out = frag.compute_fragility_index(data=data, fred_data=fred)
    comp = out["components"]

    leading = [c["normalized"] for c in comp.values()
               if c["available"] and c["lead_lag"] == "leading"]
    assert out["leading_inputs"] == len(leading)
    assert out["leading_composite"] == pytest.approx(round(float(np.mean(leading)), 4))

    # The MAIN composite is untouched: still equal-weight over ALL inputs (this is
    # the TRIAL-CRASH metric — labels must not re-weight it).
    alln = [c["normalized"] for c in comp.values() if c["available"]]
    assert out["composite"] == pytest.approx(round(float(np.mean(alln)), 4))


def test_leading_composite_none_when_no_leading_input(monkeypatch):
    # Only Sahm (lagging) resolves → no leading input → leading_composite None.
    monkeypatch.setattr(frag, "evaluate_lppls", lambda prices: {"status": "eval_error"})
    monkeypatch.setattr("backend.services.macro_indicators.recession_indicators",
                        lambda fred: {"sos": {"status": "no_data"},
                                      "sahm": {"status": "ok", "value": 0.3}})
    monkeypatch.setattr("backend.services.systemic_risk.compute_systemic_risk",
                        lambda data: {"turbulence_percentile": None,
                                      "absorption_ratio_current": None})
    monkeypatch.setattr("backend.services.net_liquidity.get_net_liquidity",
                        lambda: {"history": []})
    idx = pd.date_range(end="2026-06-12", periods=300, freq="D")
    data = pd.DataFrame({"SP500": np.linspace(100, 130, 300)}, index=idx)
    out = frag.compute_fragility_index(data=data, fred_data={})
    assert out["status"] == "ok" and out["n_inputs"] == 1
    assert out["leading_inputs"] == 0
    assert out["leading_composite"] is None
