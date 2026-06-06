"""
Aegis Finance — Reference Portfolio Rules
============================================

Pure functions that implement the rule-based portfolio logic from
paper_portfolios.yaml. No DB, no IO, no side effects.

Functions:
  classify_asset(ticker) → "equity" | "bond" | "alternative"
  compute_target_weights(lane_config, universe, tickers) → {ticker: weight}
  should_rebalance(current, target, drift_threshold, frequency, last_rebalance) → (bool, reason)
  apply_crash_overlay(weights, crash_prob, lane_config) → (weights, was_triggered)
  enforce_position_limits(weights, max_name, max_sector, sector_map) → weights

Usage:
    from backend.services.portfolio_intelligence.rules import (
        compute_target_weights, should_rebalance,
        apply_crash_overlay, enforce_position_limits,
    )
"""

import logging
from datetime import date, timedelta
from typing import Optional

from backend.config import paper_portfolios

logger = logging.getLogger(__name__)

_universe = paper_portfolios.get("universe", {})
_BOND_ETFS = set(_universe.get("bond_etfs", []))
_ALTERNATIVES = set(_universe.get("alternatives", []))
_SECTOR_ETFS = set(_universe.get("sector_etfs", []))
_BROAD_EQUITY = set(_universe.get("broad_equity", []))


# Sector ETF → GICS sector (so a sector ETF counts toward its sector's cap).
_SECTOR_ETF_GICS = {
    "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financials",
    "XLE": "Energy", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
    "XLI": "Industrials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLB": "Materials", "XLC": "Communication Services",
}

# individual_stocks category → GICS sector (mirrors real_analyzer labels).
_PI_CATEGORY_GICS = {
    "technology": "Technology", "semiconductors": "Technology",
    "consumer_internet": "Consumer Disc.", "healthcare_biotech": "Healthcare",
    "financials": "Financials", "energy_materials": "Energy",
    "industrials_defense": "Industrials", "consumer_staples": "Consumer Staples",
    "emerging_tech": "Technology", "quantum_cleantech": "Technology",
}


def lane_sector_map(universe_cfg: dict | None = None) -> dict[str, str]:
    """Equity-sector map for the reference lanes.

    The 11 sector ETFs and the individual stocks map to GICS sectors and ARE
    subject to the per-sector cap. Broad-equity ETFs (SPY/QQQ/VTI/…), bond,
    alternative and cash sleeves are deliberately OMITTED — a ticker absent
    from this map is EXEMPT from the sector cap (a diversified SPY, or a 50%
    bond sleeve, must NOT be clipped as if it were a single equity sector).
    """
    if universe_cfg is None:
        universe_cfg = _universe
    m = dict(_SECTOR_ETF_GICS)
    individual = universe_cfg.get("individual_stocks", {}) or {}
    for category, tickers in individual.items():
        gics = _PI_CATEGORY_GICS.get(category)
        if gics:
            for t in tickers:
                m.setdefault(t, gics)
    return m


def classify_asset(ticker: str) -> str:
    """Classify a ticker as equity, bond, or alternative."""
    if ticker in _BOND_ETFS:
        return "bond"
    if ticker in _ALTERNATIVES:
        return "alternative"
    return "equity"


def _get_sleeve_tickers(universe_cfg: dict) -> dict[str, list[str]]:
    """Split universe into equity/bond/alt sleeves."""
    bond_etfs = universe_cfg.get("bond_etfs", [])
    alternatives = universe_cfg.get("alternatives", [])

    equity = (
        universe_cfg.get("sector_etfs", [])
        + universe_cfg.get("broad_equity", [])
    )
    individual = universe_cfg.get("individual_stocks", {})
    for tickers in individual.values():
        equity.extend(tickers)

    return {
        "equity": equity,
        "bond": bond_etfs,
        "alternative": alternatives,
    }


def _equal_weight(tickers: list[str], target_pct: float) -> dict[str, float]:
    """Equal-weight a list of tickers to fill a target allocation percentage."""
    if not tickers or target_pct <= 0:
        return {}
    w = target_pct / len(tickers)
    return {t: w for t in tickers}


def compute_target_weights(
    lane_config: dict,
    universe_cfg: dict | None = None,
    price_data=None,
) -> dict[str, float]:
    """Compute target portfolio weights for a lane.

    HONEST STATUS: lanes currently run EQUAL-WEIGHT within each sleeve. Real
    HRP / Black-Litterman optimization is dormant — it only activates when
    `lane_config["optimizer"]` is "hrp"/"black-litterman" AND `price_data` is
    supplied, and today the config sets optimizer="equal_weight" (intent kept in
    `planned_optimizer`). Optimization lands later as a SHA-versioned, guard-
    gated config change (Step #2), at which point it must be wired through an
    as-of price path to avoid look-ahead. Until then this returns equal-weight.

    Args:
        lane_config: Lane configuration dict from paper_portfolios.yaml
        universe_cfg: Universe configuration dict. Uses global if None.
        price_data: Optional price DataFrame for optimizer input (unused in equal-weight fallback)

    Returns:
        {ticker: weight} dict summing to ~1.0
    """
    if universe_cfg is None:
        universe_cfg = _universe

    sleeves = _get_sleeve_tickers(universe_cfg)
    target_eq = lane_config["target_equity_pct"]
    target_bond = lane_config["target_bond_pct"]
    target_alt = lane_config["target_alt_pct"]
    optimizer = lane_config.get("optimizer", "hrp")

    weights: dict[str, float] = {}

    if optimizer == "hrp" and price_data is not None:
        try:
            from backend.services.portfolio_optimizer import optimize_hrp
            eq_tickers = sleeves["equity"]
            if eq_tickers:
                hrp_result = optimize_hrp(eq_tickers)
                if hrp_result and hrp_result.get("weights"):
                    raw = hrp_result["weights"]
                    raw_total = sum(raw.values())
                    if raw_total > 0:
                        for t, w in raw.items():
                            weights[t] = (w / raw_total) * target_eq
        except Exception as e:
            logger.warning("HRP optimization failed, falling back to equal-weight: %s", e)

    if not any(classify_asset(t) == "equity" for t in weights):
        weights.update(_equal_weight(sleeves["equity"], target_eq))

    if optimizer == "black-litterman" and price_data is not None:
        try:
            from backend.services.portfolio_engine import PortfolioEngine
            bl_result = PortfolioEngine.build_portfolio(
                risk_tolerance="moderate",
                method="black-litterman",
            )
            if bl_result and "holdings" in bl_result:
                raw = {h["ticker"]: h["weight"] / 100.0 for h in bl_result["holdings"]}
                eq_raw = {t: w for t, w in raw.items() if classify_asset(t) == "equity"}
                raw_total = sum(eq_raw.values())
                if raw_total > 0:
                    weights = {t: (w / raw_total) * target_eq for t, w in eq_raw.items()}
        except Exception as e:
            logger.warning("BL optimization failed, falling back to equal-weight: %s", e)

    weights.update(_equal_weight(sleeves["bond"], target_bond))
    weights.update(_equal_weight(sleeves["alternative"], target_alt))

    # Normalize to exactly 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {t: w / total for t, w in weights.items()}

    return weights


def should_rebalance(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    drift_threshold: float,
    frequency: str,
    last_rebalance_date: date | None,
    as_of_date: date | None = None,
) -> tuple[bool, str]:
    """Check whether a rebalance should be triggered.

    Returns:
        (should_rebalance, reason) where reason is one of:
        'drift', 'monthly', 'weekly_aggressive', 'no_rebalance'
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Check drift
    all_tickers = set(list(current_weights.keys()) + list(target_weights.keys()))
    max_drift = 0.0
    max_drift_ticker = ""
    for t in all_tickers:
        drift = abs(current_weights.get(t, 0.0) - target_weights.get(t, 0.0))
        if drift > max_drift:
            max_drift = drift
            max_drift_ticker = t

    if max_drift > drift_threshold:
        return True, "drift"

    # Check schedule
    if last_rebalance_date is None:
        return True, "initialization"

    days_since = (as_of_date - last_rebalance_date).days

    if frequency == "weekly" and days_since >= 7:
        return True, "weekly_aggressive"

    if frequency == "monthly" and days_since >= 28:
        return True, "monthly"

    return False, "no_rebalance"


def apply_crash_overlay(
    target_weights: dict[str, float],
    crash_prob_3m: float,
    lane_config: dict,
) -> tuple[dict[str, float], bool]:
    """Apply crash overlay: cut equity when crash probability exceeds threshold.

    Defensive only — never levers up when risk is low.

    Returns:
        (adjusted_weights, was_triggered)
    """
    overlay = lane_config.get("crash_overlay", {})
    threshold = overlay.get("crash_prob_threshold", 1.0)
    equity_cut = overlay.get("equity_cut_pct", 0.0)

    if crash_prob_3m <= threshold:
        return target_weights, False

    adjusted = {}
    equity_removed = 0.0
    bond_tickers = []

    for t, w in target_weights.items():
        asset_class = classify_asset(t)
        if asset_class == "equity":
            cut = w * equity_cut
            adjusted[t] = w - cut
            equity_removed += cut
        else:
            adjusted[t] = w
            if asset_class == "bond":
                bond_tickers.append(t)

    # Redistribute cut equity to bonds pro-rata
    if bond_tickers and equity_removed > 0:
        bond_total = sum(adjusted[t] for t in bond_tickers)
        if bond_total > 0:
            for t in bond_tickers:
                adjusted[t] += equity_removed * (adjusted[t] / bond_total)
        else:
            per_bond = equity_removed / len(bond_tickers)
            for t in bond_tickers:
                adjusted[t] += per_bond

    # Normalize
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {t: w / total for t, w in adjusted.items()}

    return adjusted, True


def enforce_position_limits(
    weights: dict[str, float],
    max_single_name: float,
    max_sector: float,
    sector_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """Clip positions exceeding limits, redistribute excess pro-rata.

    Uses a waterfill algorithm: positions at the cap are frozen, excess is
    redistributed only to unfrozen positions. Converges when n * cap >= 1.0.

    Invariant: output weights sum to 1.0.
    """
    if not weights:
        return weights

    if sector_map is None:
        sector_map = {}

    result = dict(weights)

    # Pass 1: single-name waterfill
    frozen: set[str] = set()
    for _ in range(len(result)):
        excess = 0.0
        newly_frozen = []
        for t, w in result.items():
            if t in frozen:
                continue
            if w > max_single_name + 1e-10:
                excess += w - max_single_name
                result[t] = max_single_name
                newly_frozen.append(t)

        if excess <= 1e-10:
            break

        frozen.update(newly_frozen)
        unfrozen = [t for t in result if t not in frozen]
        unfrozen_total = sum(result[t] for t in unfrozen)
        if unfrozen_total > 0:
            for t in unfrozen:
                result[t] += excess * (result[t] / unfrozen_total)
        elif unfrozen:
            per = excess / len(unfrozen)
            for t in unfrozen:
                result[t] += per

    # Pass 2: sector waterfill — ONLY genuine equity sectors are capped.
    # A ticker absent from sector_map (or mapped to a falsy value) is EXEMPT:
    # broad-equity ETFs and the bond/alt/cash sleeves are never clipped as if
    # they were a single equity sector. Trimmed weight is redistributed to
    # UNFROZEN equity names only, so it stays in the equity sleeve rather than
    # leaking into bonds/cash.
    def _sector_of(ticker: str):
        s = sector_map.get(ticker)
        return s if s else None  # None / "" → exempt from the sector cap

    capped = [t for t in result if _sector_of(t) is not None]
    frozen_sectors: set[str] = set()
    n_sectors = len({_sector_of(t) for t in capped})
    for _ in range(n_sectors + 2):
        sector_weights: dict[str, float] = {}
        sector_tickers: dict[str, list[str]] = {}
        for t in capped:
            s = _sector_of(t)
            sector_weights[s] = sector_weights.get(s, 0.0) + result[t]
            sector_tickers.setdefault(s, []).append(t)

        excess = 0.0
        newly_frozen_s = []
        for sector, sw in sector_weights.items():
            if sector in frozen_sectors:
                continue
            if sw > max_sector + 1e-10:
                excess += sw - max_sector
                for t in sector_tickers[sector]:
                    result[t] *= (max_sector / sw)
                newly_frozen_s.append(sector)

        if excess <= 1e-10:
            break
        frozen_sectors.update(newly_frozen_s)

        unfrozen = [t for t in capped if _sector_of(t) not in frozen_sectors]
        unfrozen_total = sum(result[t] for t in unfrozen)
        if unfrozen_total > 0:
            for t in unfrozen:
                result[t] += excess * (result[t] / unfrozen_total)
        elif unfrozen:
            per = excess / len(unfrozen)
            for t in unfrozen:
                result[t] += per
        else:
            break  # all equity sectors capped — nowhere to redistribute

    # Final normalize
    total = sum(result.values())
    if total > 0:
        result = {t: w / total for t, w in result.items()}

    return result
