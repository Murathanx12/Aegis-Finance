"""X4's sensor: frozen thresholds, both ties pinned, and a named refusal.

Spec section 7 step 5's known answer is the boundary: feed a synthetic SPY series
with a hand-computed 21-session return and a fixed VIX, and the 2x2 cell must
land on the documented side at BOTH `19.99` and `20.00`.

The rest are about what the sensor will not do: it does not report a regime
from half its inputs, it does not substitute a last-known VIX, and -- pinned
here after it did exactly this on 2026-09-12 -- it does not apply one VIX
observation to every date in a series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import market_sensor as ms
from backend.services import protocol_p16 as pp
from scripts import night_x4_regime_route as X4


def _bars(returns, start="2025-01-02", symbol="SPY"):
    """A SPY frame whose closes produce the given per-session returns."""
    close = 100.0 * np.cumprod(1.0 + np.asarray([0.0] + list(returns)))
    dates = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({"symbol": symbol, "date": dates, "close": close})


def _flat_then(n_flat, then, total=60):
    r = [0.0] * n_flat + [then] + [0.0] * max(total - n_flat - 1, 0)
    return r[:total]


def test_a_hand_computed_21_session_return():
    """One +5% session inside the window and nothing else: the trailing
    21-session return must be exactly +5% and the trend UP."""
    bars = _bars(_flat_then(30, 0.05, total=60))
    tr = ms.spy_trend(bars)
    last = tr.iloc[-1]
    # the +5% session is 30 sessions back, outside a 21-session window
    assert last["trend_return"] == pytest.approx(0.0, abs=1e-12)
    assert last["trend"] == "TREND_DOWN", "a flat 21-session tape is not an uptrend"
    inside = tr.iloc[35]
    assert inside["trend_return"] == pytest.approx(0.05, rel=1e-9)
    assert inside["trend"] == "TREND_UP"


@pytest.mark.parametrize("vix,cell,regime", [
    (10.0, "TREND_UP x VIX_LOW", ms.RISK_ON),
    (19.99, "TREND_UP x VIX_LOW", ms.RISK_ON),
    (20.00, "TREND_UP x VIX_HIGH", ms.RISK_OFF),
    (20.01, "TREND_UP x VIX_HIGH", ms.RISK_OFF),
    (35.0, "TREND_UP x VIX_HIGH", ms.RISK_OFF),
])
def test_the_vix_boundary_lands_on_the_documented_side(vix, cell, regime):
    """Spec section 7 step 5: both 19.99 and 20.00 are tested, and the line is
    'below 20 is calm', so 20.00 is HIGH."""
    out = ms.label("TREND_UP", vix)
    assert out["cell"] == cell and out["regime"] == regime


@pytest.mark.parametrize("trend,vix,regime", [
    ("TREND_UP", 15.0, ms.RISK_ON),
    ("TREND_DOWN", 15.0, ms.RISK_OFF),
    ("TREND_UP", 25.0, ms.RISK_OFF),
    ("TREND_DOWN", 25.0, ms.RISK_OFF),
])
def test_only_one_of_the_four_cells_is_risk_on(trend, vix, regime):
    assert ms.label(trend, vix)["regime"] == regime


def test_a_half_observed_sensor_reports_unknown_and_says_which_leg():
    no_vix = ms.label("TREND_UP", None)
    assert no_vix["regime"] == ms.UNKNOWN and "VIX" in no_vix["reason"]
    no_trend = ms.label(None, 15.0)
    assert no_trend["regime"] == ms.UNKNOWN and "trend" in no_trend["reason"]


def test_the_thresholds_are_frozen_and_printed():
    """A threshold chosen by looking at the result is not a threshold."""
    assert ms.THRESHOLDS["vix_regime_line"] == 20.0
    assert ms.THRESHOLDS["trend_lookback_sessions"] == 21
    assert "NOT fitted" in ms.THRESHOLDS["source_of_the_line"]
    d = ms.declaration()
    assert d["thresholds"] == ms.THRESHOLDS
    assert set(d["states"]) == {ms.RISK_ON, ms.RISK_OFF, ms.UNKNOWN}


def test_the_first_lookback_sessions_are_null_not_zero():
    tr = ms.spy_trend(_bars([0.001] * 40))
    assert tr["trend_return"].iloc[:21].isna().all()
    assert tr["trend"].iloc[0] is None


def test_missing_bars_refuse_by_name(tmp_path):
    with pytest.raises(ms.SensorRefused) as exc:
        ms.spy_trend(bars_path=tmp_path / "absent.parquet")
    assert "no bars at" in str(exc.value)


def test_a_bar_file_without_spy_refuses_by_name(tmp_path):
    p = tmp_path / "bars.parquet"
    _bars([0.001] * 30, symbol="AAPL").to_parquet(p, index=False)
    with pytest.raises(ms.SensorRefused) as exc:
        ms.spy_trend(bars_path=p)
    assert "no market proxy" in str(exc.value)


def test_an_unavailable_fred_refuses_and_the_regime_is_unknown(monkeypatch):
    """Offline, the sensor never substitutes a last-known VIX."""
    def boom():
        raise RuntimeError("network blocked")

    monkeypatch.setattr(ms, "vix_history",
                        lambda series=None: (_ for _ in ()).throw(
                            ms.SensorRefused("FRED fetch failed: network blocked")))
    out = ms.regime("2025-06-02", bars=_bars([0.001] * 60))
    assert out["regime"] == ms.UNKNOWN
    assert "FRED fetch failed" in out["vix_refusal"]


# ------------------------------------------- the look-ahead this file caught

def test_one_vix_observation_is_not_applied_to_every_date():
    """Measured 2026-09-12: `regime_series` fetched the LATEST VIX (17.84) and
    used it for all 18 month blocks, so a 2025-01 routing decision was made
    with a 2026-09 observation. Each date must see only its own past."""
    bars = _bars([0.002] * 120)
    dates = list(pd.to_datetime(bars["date"]).dt.date)[30::20]
    n = len(bars)
    vix = pd.Series([35.0] * 40 + [10.0] * (n - 40),
                    index=pd.to_datetime(bars["date"]))
    rows = ms.regime_series(dates, bars=bars, vix_series=vix)
    early = [r for r in rows if r["as_of"] <= str(pd.Timestamp(bars["date"].iloc[39]).date())]
    late = [r for r in rows if r["as_of"] >= str(pd.Timestamp(bars["date"].iloc[60]).date())]
    assert early and late
    assert all(r["vix"] == 35.0 for r in early), early
    assert all(r["vix"] == 10.0 for r in late), late
    assert all(r["vix_observed_at"] <= r["as_of"] for r in rows if r.get("vix"))


def test_a_date_before_the_vix_series_starts_gets_no_vix():
    bars = _bars([0.002] * 80)
    vix = pd.Series([15.0] * 20, index=pd.to_datetime(bars["date"].iloc[60:80]))
    rows = ms.regime_series([pd.Timestamp(bars["date"].iloc[30]).date()],
                            bars=bars, vix_series=vix)
    assert rows[0]["regime"] == ms.UNKNOWN and rows[0]["vix"] is None


# --------------------------------------------------------------- the routing

def _answers(months, dirs_by_month):
    out = []
    for m in months:
        for i, (d, fwd) in enumerate(dirs_by_month[m]):
            out.append({"tag": "read_MASKED", "name": f"S{i}", "month": m,
                        "dir": d, "conf": 0.6, "fwd": fwd})
    return out


def test_routing_keeps_only_the_admitted_blocks():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    rng = np.random.default_rng(3)
    answers = _answers(months, {m: [(1, float(rng.normal(0, 0.05))) for _ in range(4)]
                                for m in months})
    regimes = {m: {"regime": ms.RISK_ON if i % 2 == 0 else ms.RISK_OFF}
               for i, m in enumerate(months)}
    out = X4.route(answers, regimes)
    assert len(out["blocks_admitted"]) == 6
    assert len(out["blocks_total"]) == 12
    assert out["cells_admitted"] == 24 and out["cells_total"] == 48
    assert out["comparison"]["routed_blocks"] == 6


def test_the_routed_minus_unrouted_difference_is_not_called_paired():
    """The two books hold the same positions on every admitted block; routing
    changes only which blocks are in the average, so this is not a paired test
    and must not carry a t of its own."""
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    answers = _answers(months, {m: [(1, 0.01)] for m in months})
    regimes = {m: {"regime": ms.RISK_ON} for m in months}
    c = X4.route(answers, regimes)["comparison"]
    assert "not_a_paired_test" in c and "not a paired difference" in c["not_a_paired_test"]
    assert "difference_t" not in c


def test_routing_to_a_regime_no_block_has_keeps_nothing():
    months = ["2025-01", "2025-02"]
    answers = _answers(months, {m: [(1, 0.01)] for m in months})
    regimes = {m: {"regime": ms.UNKNOWN} for m in months}
    out = X4.route(answers, regimes)
    assert out["cells_admitted"] == 0
    assert out["routed"].get("verdict", "").startswith("CANNOT DETERMINE")


def test_the_routing_decision_is_taken_at_the_months_first_day():
    """Nothing inside month M may inform the decision to trade month M."""
    assert X4.month_start("2025-07") == "2025-07-01"


def test_the_job_refuses_when_the_sensor_sees_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(X4, "OUT", tmp_path)
    monkeypatch.setattr(X4.xd, "read_answers", lambda path=None: _answers(
        ["2025-01", "2025-02"], {"2025-01": [(1, 0.01)], "2025-02": [(-1, 0.01)]}))
    monkeypatch.setattr(X4, "regime_by_month",
                        lambda months, **kw: {m: {"regime": ms.UNKNOWN,
                                                  "reason": "no bars on this checkout"}
                                              for m in months})
    payload = X4.X4_regime_route(run=3)
    assert payload["verdict"].startswith("REFUSED")
    assert pp.refuse_reasons("X4_regime_route", payload) == []


def test_the_job_makes_no_model_call(monkeypatch, tmp_path):
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    rng = np.random.default_rng(5)
    monkeypatch.setattr(X4, "OUT", tmp_path)
    monkeypatch.setattr(X4.xd, "read_answers", lambda path=None: _answers(
        months, {m: [(1, float(rng.normal(0, 0.05))) for _ in range(4)] for m in months}))
    monkeypatch.setattr(X4, "regime_by_month",
                        lambda ms_, **kw: {m: {"regime": ms.RISK_ON if i < 8 else ms.RISK_OFF}
                                           for i, m in enumerate(ms_)})

    import backend.services.free_inference as fi

    def forbidden(*a, **k):
        raise AssertionError("X4 must make no model call: it re-grades answers on disk")

    monkeypatch.setattr(fi, "complete", forbidden)
    payload = X4.X4_regime_route(run=4)
    assert payload["model_calls"] == 0
    assert payload["status"] == "EXPLORATORY_IN_SAMPLE"
    assert "out of sample" in payload["why_exploratory"].lower()
    assert pp.refuse_reasons("X4_regime_route", payload) == []
    assert payload["comparison"]["routed_blocks"] == 8


def test_the_job_is_registered():
    from scripts import night_factory_jobs as NFJ

    assert "X4_regime_route" in NFJ.JOBS


def test_the_sensor_is_reachable_from_a_caller():
    """A new service with no caller must be a red suite, not a discovery three
    weeks later. X4's night job is that caller."""
    import ast
    from pathlib import Path

    src = Path(X4.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "backend.services" in imported
    assert "market_sensor" in src
