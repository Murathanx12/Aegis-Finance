"""
Aegis Finance — Tail Risk Analytics
=====================================

Institutional-grade risk metrics missing from standard portfolio analysis:
  - Sortino Ratio: risk-adjusted return using only downside deviation
  - Omega Ratio: probability-weighted gain/loss ratio (Keating & Shadwick, 2002)
  - Calmar Ratio: annualized return / max drawdown (used by hedge funds)
  - Downside Deviation: volatility of negative returns only (Sortino & Price, 1994)
  - Maximum Drawdown Duration: longest recovery time in trading days
  - Tail Concentration Index: fraction of total loss concentrated in worst 5% of days
  - Gain/Pain Ratio: sum of positive returns / abs(sum of negative returns)
  - Ulcer Index: RMS of drawdown percentage (Peter Martin, 1987)

These metrics are standard at Bloomberg, QuantConnect, and prop desks but were
entirely absent from Aegis. They provide a more complete picture of downside
risk than Sharpe ratio alone.

Usage:
    from backend.services.tail_risk import compute_tail_risk_metrics
    metrics = compute_tail_risk_metrics(daily_returns, risk_free_rate=0.04)
"""

import logging

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)

# Load thresholds from config
_TAIL_CFG = config.get("tail_risk", {})
_TAIL_PCT = _TAIL_CFG.get("tail_percentile", 5)
_MIN_OBSERVATIONS = _TAIL_CFG.get("min_observations", 60)


def compute_tail_risk_metrics(
    daily_returns: np.ndarray,
    risk_free_rate: float | None = None,
    threshold: float = 0.0,
) -> dict:
    """Compute a full suite of tail risk metrics from daily returns.

    Args:
        daily_returns: Array of daily simple returns (not log returns).
        risk_free_rate: Annual risk-free rate for Sortino computation.
            Defaults to config value if None.
        threshold: Minimum acceptable return (MAR) for Omega/Sortino.
            0.0 means any negative return counts as downside.

    Returns:
        Dict with all tail risk metrics. Values are None when insufficient data.
    """
    if risk_free_rate is None:
        risk_free_rate = config.get("risk_free_rate", 0.04)

    returns = np.asarray(daily_returns, dtype=np.float64)
    returns = returns[np.isfinite(returns)]

    if len(returns) < _MIN_OBSERVATIONS:
        logger.warning("Tail risk: only %d observations (need %d)", len(returns), _MIN_OBSERVATIONS)
        return _empty_metrics()

    rf_daily = risk_free_rate / 252.0
    excess = returns - rf_daily

    # ── Downside Deviation (Sortino & Price, 1994) ──────────────────────
    downside_dev_daily = float(np.sqrt(np.mean(np.minimum(returns - threshold, 0) ** 2)))
    downside_dev_annual = downside_dev_daily * np.sqrt(252)

    # ── Sortino Ratio ───────────────────────────────────────────────────
    annual_return = float(np.mean(returns) * 252)
    sortino = float((annual_return - risk_free_rate) / downside_dev_annual) if downside_dev_annual > 1e-10 else None

    # ── Omega Ratio (Keating & Shadwick, 2002) ──────────────────────────
    # Omega = E[max(R - threshold, 0)] / E[max(threshold - R, 0)]
    gains_above = np.mean(np.maximum(returns - threshold, 0))
    losses_below = np.mean(np.maximum(threshold - returns, 0))
    omega = float(gains_above / losses_below) if losses_below > 1e-10 else None

    # ── Drawdown series ─────────────────────────────────────────────────
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    drawdown = (cum - peak) / peak
    max_dd = float(np.min(drawdown))

    # ── Calmar Ratio ────────────────────────────────────────────────────
    calmar = float(annual_return / abs(max_dd)) if abs(max_dd) > 1e-10 else None

    # ── Maximum Drawdown Duration (days) ────────────────────────────────
    max_dd_duration = _max_drawdown_duration(cum)

    # ── Tail Concentration Index ────────────────────────────────────────
    # What fraction of total losses come from the worst N% of days?
    tail_concentration = _tail_concentration(returns, _TAIL_PCT)

    # ── Gain/Pain Ratio ─────────────────────────────────────────────────
    total_gains = float(np.sum(returns[returns > 0]))
    total_losses = float(np.abs(np.sum(returns[returns < 0])))
    gain_pain = float(total_gains / total_losses) if total_losses > 1e-10 else None

    # ── Ulcer Index (Peter Martin, 1987) ────────────────────────────────
    # RMS of drawdown percentages — penalizes deep + prolonged drawdowns
    ulcer_index = float(np.sqrt(np.mean(drawdown ** 2)))

    # ── Win rate and avg win/loss ───────────────────────────────────────
    n_positive = int(np.sum(returns > 0))
    n_negative = int(np.sum(returns < 0))
    win_rate = float(n_positive / len(returns)) if len(returns) > 0 else 0.0
    avg_win = float(np.mean(returns[returns > 0])) if n_positive > 0 else 0.0
    avg_loss = float(np.mean(returns[returns < 0])) if n_negative > 0 else 0.0
    # Profit factor = avg_win * n_wins / (avg_loss * n_losses)
    profit_factor = float(
        (avg_win * n_positive) / abs(avg_loss * n_negative)
    ) if n_negative > 0 and abs(avg_loss) > 1e-10 else None

    return {
        "sortino_ratio": _round(sortino),
        "omega_ratio": _round(omega),
        "calmar_ratio": _round(calmar),
        "downside_deviation_annual": _round(downside_dev_annual * 100),  # percentage
        "max_drawdown_pct": _round(max_dd * 100),
        "max_drawdown_duration_days": max_dd_duration,
        "tail_concentration_pct": _round(tail_concentration * 100),
        "gain_pain_ratio": _round(gain_pain),
        "ulcer_index": _round(ulcer_index * 100),  # percentage
        "win_rate_pct": _round(win_rate * 100),
        "avg_win_pct": _round(avg_win * 100),
        "avg_loss_pct": _round(avg_loss * 100),
        "profit_factor": _round(profit_factor),
        "n_observations": len(returns),
    }


def _max_drawdown_duration(cum_wealth: np.ndarray) -> int | None:
    """Find the longest period (in days) spent in a drawdown.

    A drawdown period starts when cumulative wealth drops below
    the running peak, and ends when it recovers to a new peak.
    """
    if len(cum_wealth) < 2:
        return None

    peak = np.maximum.accumulate(cum_wealth)
    in_dd = cum_wealth < peak

    max_duration = 0
    current_duration = 0
    for is_dd in in_dd:
        if is_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0

    return max_duration if max_duration > 0 else 0


def _tail_concentration(returns: np.ndarray, percentile: float = 5.0) -> float:
    """Fraction of total negative returns concentrated in the worst N% of days.

    A value near 1.0 means losses are concentrated in a few extreme days
    (fat tails). A value near percentile/100 means losses are evenly spread
    (thin tails).
    """
    negative = returns[returns < 0]
    if len(negative) < 5:
        return 0.0

    total_loss = np.sum(np.abs(negative))
    if total_loss < 1e-10:
        return 0.0

    # Sort by magnitude (worst first)
    sorted_losses = np.sort(np.abs(negative))[::-1]
    n_tail = max(1, int(len(negative) * percentile / 100.0))
    tail_loss = np.sum(sorted_losses[:n_tail])

    return float(tail_loss / total_loss)


def _round(val: float | None, decimals: int = 4) -> float | None:
    """Round a value, preserving None."""
    if val is None:
        return None
    return round(float(val), decimals)


def _empty_metrics() -> dict:
    """Return empty metrics dict when insufficient data."""
    return {
        "sortino_ratio": None,
        "omega_ratio": None,
        "calmar_ratio": None,
        "downside_deviation_annual": None,
        "max_drawdown_pct": None,
        "max_drawdown_duration_days": None,
        "tail_concentration_pct": None,
        "gain_pain_ratio": None,
        "ulcer_index": None,
        "win_rate_pct": None,
        "avg_win_pct": None,
        "avg_loss_pct": None,
        "profit_factor": None,
        "n_observations": 0,
    }
