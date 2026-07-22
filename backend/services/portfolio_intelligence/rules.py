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
from datetime import date

from backend.config import (
    book_lanes,
    conservative_atr_lanes,
    paper_portfolios,
    smallmid_quality_lanes,
)
from backend.services.portfolio_intelligence.nav import CASH_TICKER

logger = logging.getLogger(__name__)

_universe = paper_portfolios.get("universe", {})

# The complete set of reference lanes, derived from the versioned YAML —
# any dict with a target_equity_pct is a lane. Single source of truth for
# scheduler / engine / routers / health (was 7 hardcoded triples).
REFERENCE_LANES: tuple[str, ...] = tuple(
    k for k, v in paper_portfolios.items()
    if isinstance(v, dict) and "target_equity_pct" in v
)

# Book lanes (P1 #6) — individual-stock share-count books, from book_lanes.yaml,
# kept SEPARATE from REFERENCE_LANES so the 4 reference lanes' whole-file hash is
# never perturbed (TRIAL-001 protection). Identified by a `purpose` tag.
BOOK_LANES: tuple[str, ...] = tuple(
    k for k, v in book_lanes.items()
    if isinstance(v, dict) and "purpose" in v
)

# Conservative-ATR lane (TRIAL-EXIT) — the conservative mandate + ATR exit
# overlay, from conservative_atr_lanes.yaml with its OWN hash. Like BOOK_LANES,
# kept SEPARATE from REFERENCE_LANES so the reference lanes' hash (and the frozen
# `conservative` control's segment) is never perturbed. Identified by `purpose`.
CONSERVATIVE_ATR_LANES: tuple[str, ...] = tuple(
    k for k, v in conservative_atr_lanes.items()
    if isinstance(v, dict) and "purpose" in v
)

# Smallmid-quality lane (TRIAL-SMQ-FWD) — the BRAIN-007 composite book, from
# smallmid_quality_lanes.yaml with its OWN hash (holdings are part of the hash:
# the book IS the strategy). Same isolation reasoning as the other attended lanes.
SMQ_LANES: tuple[str, ...] = tuple(
    k for k, v in smallmid_quality_lanes.items()
    if isinstance(v, dict) and "purpose" in v
)


def compute_book_mv_weights(
    holdings: dict[str, float], prices: dict[str, float]
) -> dict[str, float]:
    """Current-market-value weights for a share-count book. Pure.

    weight_i = (shares_i · price_i) / Σ(shares · price). Raises ValueError if any
    held ticker has no positive price, or the total market value is non-positive
    — a book lane must NEVER be seeded from a partially-priced (junk) book.
    """
    if not holdings:
        raise ValueError("empty holdings book")
    mv: dict[str, float] = {}
    for ticker, shares in holdings.items():
        px = prices.get(ticker)
        if px is None or px <= 0 or shares is None or shares <= 0:
            raise ValueError(
                f"book lane: missing/invalid price or shares for {ticker} "
                f"(price={px}, shares={shares}) — refusing to seed a junk book"
            )
        mv[ticker] = float(shares) * float(px)
    total = sum(mv.values())
    if not (total > 0) or total != total:  # non-positive or NaN
        raise ValueError(f"book lane: non-positive/NaN total market value ({total})")
    return {t: v / total for t, v in mv.items()}
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
    """Classify a ticker as cash, equity, bond, or alternative."""
    if ticker == CASH_TICKER:
        return "cash"
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


def _hrp_equity_weights(
    eq_tickers: list[str],
    price_data,
    target_eq: float,
    meta: dict,
) -> dict[str, float] | None:
    """Leakage-safe HRP for the equity sleeve.

    price_data is a wide close-price DataFrame whose LAST ROW IS <= THE AS-OF
    DATE — the caller owns that bound (live: latest bar; replay: truncated at
    the simulated date). Nothing here fetches data.

    Returns sleeve weights summing to target_eq, or None (with meta noting
    why) so the caller falls back to equal-weight. The gate: enough history,
    finite non-negative weights, and no degenerate collapse to a handful of
    names. A failed gate is a loud fallback, never garbage targets.
    """
    opt_cfg = paper_portfolios.get("optimizer_params", {}) or {}
    lookback = int(opt_cfg.get("lookback_days", 504))
    min_obs = int(opt_cfg.get("min_observations", 252))
    min_nonzero_frac = float(opt_cfg.get("min_nonzero_fraction", 0.5))

    available = [t for t in eq_tickers if t in getattr(price_data, "columns", [])]
    # Visibility (P1 #6): record which names are dropped and why — no as-of price,
    # or thin as-of history — so the rebalance audit shows when HRP is actually
    # biting vs quietly excluding names (and never a silent equal-weight). Purely
    # additive (meta only); the returned weights are unchanged.
    dropped = {t: "no as-of price" for t in eq_tickers if t not in available}
    meta["optimizer_dropped"] = dropped
    if len(available) < 2:
        meta["optimizer_fallback"] = f"only {len(available)} equity tickers have prices"
        return None

    panel = price_data[available].dropna(how="all")
    returns = panel.pct_change().dropna(how="all").iloc[-lookback:]
    returns = returns.dropna(axis=1, thresh=min_obs).dropna()
    for t in available:
        if t not in returns.columns:
            dropped[t] = f"thin as-of history (<{min_obs} obs)"
    if len(returns) < min_obs or returns.shape[1] < 2:
        meta["optimizer_fallback"] = (
            f"insufficient as-of history ({len(returns)} obs, "
            f"{returns.shape[1]} tickers; need {min_obs}+)"
        )
        return None

    try:
        from backend.services.portfolio_optimizer import optimize_hrp
        result = optimize_hrp(list(returns.columns), returns=returns)
    except Exception as e:
        meta["optimizer_fallback"] = f"optimizer raised: {e}"
        return None

    raw = (result or {}).get("weights") or {}
    if not raw:
        meta["optimizer_fallback"] = "optimizer returned no weights"
        return None
    vals = list(raw.values())
    if any((w is None) or (w != w) or (w < 0) for w in vals):  # NaN/None/short
        meta["optimizer_fallback"] = "optimizer output contains NaN/negative weights"
        return None
    raw_total = sum(vals)
    if raw_total <= 0:
        meta["optimizer_fallback"] = "optimizer weights sum to zero"
        return None
    nonzero = sum(1 for w in vals if w > 1e-6)
    if nonzero < max(2, int(min_nonzero_frac * len(returns.columns))):
        meta["optimizer_fallback"] = (
            f"degenerate concentration: {nonzero}/{len(returns.columns)} names"
        )
        return None

    meta["optimizer_used"] = "hrp"
    meta["optimizer_n_obs"] = len(returns)
    meta["optimizer_as_of"] = str(returns.index[-1])[:10]
    return {t: (w / raw_total) * target_eq for t, w in raw.items()}


def compute_target_weights(
    lane_config: dict,
    universe_cfg: dict | None = None,
    price_data=None,
    meta: dict | None = None,
) -> dict[str, float]:
    """Compute target portfolio weights for a lane.

    Since config v2 (2026-06-11) lanes with `optimizer: hrp` run leakage-safe
    HRP on the EQUITY SLEEVE ONLY: sleeve-level allocations stay the lane
    mandate, bond/alt sleeves stay equal-weight, and the crash overlay +
    position limits apply downstream unchanged. The as-of bound on price_data
    belongs to the caller (live: latest bar; replay: simulated date).

    HARD GATE: if the optimizer can't produce valid weights for ANY reason
    (no panel, short history, NaN/negative/degenerate output, exception), the
    equity sleeve falls back to equal-weight and `meta["optimizer_fallback"]`
    carries the reason — the engine logs it, audits it, and names it in the
    rebalance explanation. Garbage weights cannot reach the track record.

    Args:
        lane_config: Lane configuration dict from paper_portfolios.yaml
        universe_cfg: Universe configuration dict. Uses global if None.
        price_data: As-of wide close-price DataFrame for the optimizer.
        meta: Optional dict the function annotates (fallback reason, as-of
            date, observation count) for audit/explanation use.

    Returns:
        {ticker: weight} dict summing to ~1.0
    """
    if universe_cfg is None:
        universe_cfg = _universe
    if meta is None:
        meta = {}

    sleeves = _get_sleeve_tickers(universe_cfg)
    target_eq = lane_config["target_equity_pct"]
    target_bond = lane_config["target_bond_pct"]
    target_alt = lane_config["target_alt_pct"]
    optimizer = lane_config.get("optimizer", "equal_weight")

    weights: dict[str, float] = {}

    if optimizer == "hrp":
        if price_data is None:
            meta["optimizer_fallback"] = "no as-of price panel supplied"
            logger.error(
                "HRP requested but no as-of price panel — equal-weight fallback"
            )
        elif sleeves["equity"]:
            hrp = _hrp_equity_weights(sleeves["equity"], price_data, target_eq, meta)
            if hrp:
                weights.update(hrp)
            else:
                logger.error(
                    "HRP fallback to equal-weight: %s",
                    meta.get("optimizer_fallback", "unknown"),
                )

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

    # Explicit cash/T-bill sleeve (earns rf; zero duration). Held as a $-balance
    # under CASH_TICKER, not as shares.
    target_cash = lane_config.get("target_cash_pct", 0.0)
    if target_cash and target_cash > 0:
        weights[CASH_TICKER] = weights.get(CASH_TICKER, 0.0) + target_cash

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

    for t, w in target_weights.items():
        if classify_asset(t) == "equity":
            cut = w * equity_cut
            adjusted[t] = w - cut
            equity_removed += cut
        else:
            adjusted[t] = w

    # Rotate the cut equity into CASH — zero-duration and earning the short
    # rate, so it is genuinely defensive even in a rates-driven selloff where
    # long bonds (TLT/IEF) also fall. ("To cash, not just bonds.")
    if equity_removed > 0:
        adjusted[CASH_TICKER] = adjusted.get(CASH_TICKER, 0.0) + equity_removed

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
