"""
Aegis Finance — Regime Validation
====================================

Confirms or challenges HMM/rule-based regime calls using:
1. Price structure (SPX vs 200-day SMA)
2. Market breadth (sector advance/decline ratio)
3. Institutional consensus alignment

A BEAR call is only "CONFIRMED" when multiple independent signals agree.

Adapted from V7 validation/regime_validator.py.

Usage:
    from backend.services.regime_validator import validate_regime
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.config import config


@dataclass
class RegimeValidation:
    """Result of regime cross-validation checks."""

    regime: str
    confirmed: bool
    price_confirmed: bool
    breadth_confirmed: bool
    consensus_aligned: bool
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    notes: list = field(default_factory=list)


def validate_regime(
    data: pd.DataFrame,
    current_regime: str,
) -> RegimeValidation:
    """Run three confirmation checks on the current regime call.

    Args:
        data: Market DataFrame with SP500, Sector_* columns
        current_regime: Current regime string

    Returns:
        RegimeValidation with confirmation status and notes
    """
    notes = []
    is_bearish = current_regime in ("Bear", "Crisis", "Volatile")

    price_confirmed = _check_price_structure(data, is_bearish, notes)
    breadth_confirmed = _check_breadth(data, is_bearish, notes)
    consensus_aligned = _check_consensus(current_regime, notes)

    checks_passed = sum([price_confirmed, breadth_confirmed, consensus_aligned])

    if is_bearish:
        confirmed = checks_passed >= 2
        if checks_passed == 3:
            confidence = "HIGH"
        elif checks_passed == 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
            notes.append(
                f"BEAR regime called but only {checks_passed}/3 checks confirm"
            )
    else:
        confirmed = checks_passed >= 1
        confidence = "HIGH" if checks_passed >= 2 else "MEDIUM" if checks_passed == 1 else "LOW"

    return RegimeValidation(
        regime=current_regime,
        confirmed=confirmed,
        price_confirmed=price_confirmed,
        breadth_confirmed=breadth_confirmed,
        consensus_aligned=consensus_aligned,
        confidence=confidence,
        notes=notes,
    )


def _check_price_structure(
    data: pd.DataFrame,
    is_bearish: bool,
    notes: list,
) -> bool:
    sma_period = 200

    if "SP500" not in data.columns or len(data) < sma_period:
        notes.append("Insufficient data for 200d SMA check")
        return False

    sp = data["SP500"]
    sma_200 = sp.rolling(sma_period).mean()
    current_price = float(sp.iloc[-1])
    current_sma = float(sma_200.iloc[-1])

    if np.isnan(current_sma):
        notes.append("200d SMA not available")
        return False

    pct_from_sma = (current_price - current_sma) / current_sma * 100

    if is_bearish:
        confirmed = current_price < current_sma
        label = "bear signal confirmed" if confirmed else "bear signal NOT confirmed"
    else:
        confirmed = current_price > current_sma
        label = "bullish structure intact" if confirmed else "bullish call contradicted"

    notes.append(f"Price {pct_from_sma:+.1f}% from 200d SMA — {label}")
    return confirmed


def _check_breadth(
    data: pd.DataFrame,
    is_bearish: bool,
    notes: list,
) -> bool:
    breadth_period = 21
    min_declining = 6

    sector_cols = [c for c in data.columns if c.startswith("Sector_")]
    if len(sector_cols) < 3:
        notes.append("Insufficient sector data for breadth check")
        return False

    n_declining = 0
    n_total = 0
    for col in sector_cols:
        series = data[col].dropna()
        if len(series) < breadth_period + 1:
            continue
        ret = float(series.iloc[-1] / series.iloc[-breadth_period] - 1)
        n_total += 1
        if ret < 0:
            n_declining += 1

    if n_total == 0:
        notes.append("No sector returns available for breadth check")
        return False

    n_advancing = n_total - n_declining

    if is_bearish:
        confirmed = n_declining >= min_declining
        notes.append(f"Breadth: {n_declining}/{n_total} sectors declining")
    else:
        confirmed = n_advancing > n_declining
        notes.append(f"Breadth: {n_advancing}/{n_total} sectors advancing")

    return confirmed


def _check_consensus(current_regime: str, notes: list) -> bool:
    benchmarks = config.get("institutional_benchmarks", {})
    if not benchmarks:
        notes.append("No institutional benchmarks available")
        return False

    returns = []
    for name, info in benchmarks.items():
        if isinstance(info, dict) and "annual" in info:
            returns.append(float(info["annual"]))

    if not returns:
        notes.append("No valid institutional return forecasts found")
        return False

    consensus_return = np.mean(returns)
    is_bearish = current_regime in ("Bear", "Crisis", "Volatile")

    if is_bearish:
        confirmed = consensus_return < 0.03
    else:
        confirmed = consensus_return >= 0.03

    notes.append(f"Consensus annual return {consensus_return*100:.1f}%")
    return confirmed
