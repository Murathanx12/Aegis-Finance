"""Risk endpoints — crash probability, tail risk, survival."""

from __future__ import annotations

from typing import Optional

from aegis.client import default_client


def crash_probability(
    horizon: str = "3m",
    *,
    explain: bool = False,
    client=None,
) -> dict:
    """Market-wide crash probability + SHAP (when explain=True)."""
    c = client or default_client()
    return c.get(
        "/api/crash/prediction",
        params={"horizon": horizon, "explain": str(explain).lower()},
    )


def ticker_crash(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/crash/{ticker.upper()}")


def tail_risk(ticker: str, period: str = "5y", *, client=None) -> dict:
    c = client or default_client()
    return c.get(
        f"/api/analytics/tail-risk/{ticker.upper()}",
        params={"period": period},
    )


def stress_test(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/analytics/stress-test/{ticker.upper()}")


def conformal_interval(
    crash_prob: float,
    *,
    horizon: str = "3m",
    alpha: float = 0.1,
    client=None,
) -> dict:
    """Finite-sample conformal band around a crash probability."""
    c = client or default_client()
    return c.get(
        "/api/analytics/conformal-interval",
        params={"crash_prob": crash_prob, "horizon": horizon, "alpha": alpha},
    )


def prediction_confidence(
    mc_p10: float,
    mc_median: float,
    mc_p90: float,
    *,
    garch_nu: Optional[float] = None,
    garch_persistence: Optional[float] = None,
    data_years: float = 5.0,
    drift_severity: Optional[str] = None,
    beta: float = 1.0,
    client=None,
) -> dict:
    """Grade an MC forecast's confidence + widen the band for drift."""
    c = client or default_client()
    params = {
        "mc_p10": mc_p10,
        "mc_median": mc_median,
        "mc_p90": mc_p90,
        "data_years": data_years,
        "beta": beta,
    }
    if garch_nu is not None:
        params["garch_nu"] = garch_nu
    if garch_persistence is not None:
        params["garch_persistence"] = garch_persistence
    if drift_severity:
        params["drift_severity"] = drift_severity
    return c.get("/api/analytics/prediction-confidence", params=params)
