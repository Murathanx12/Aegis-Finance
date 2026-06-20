"""
Cross-asset rotation — DECISION CORE (pure; not yet a live lane)
================================================================

Research (2026-06-20): bonds win *regimes*, not outright. The robust small-account
play is a cross-asset sleeve — equities / long + intermediate duration / IG credit
/ gold / cash — where defensives supply convexity exactly when the fragility engine
flags stress (TLT +~33% in 2008 while SPY −37%; both crushed in 2022's rate shock,
which is why the sleeve diversifies the duration leg and keeps cash).

This is the pure weight-generating core only. A NEW pre-registered lane would
consume it on its OWN inception (env-gated seed, attended — exactly how
conservative-atr was seeded), never retrofitting a live lane (canon). Mirrors how
exit_overlay / exposure_multiplier were built before their lanes.

Anti-hindsight by construction: there is NO regime→weight lookup table fit to
which assets won in past crises (that is the profit mirage the 2026-06-15
postmortem rejected). Base weights are inverse-volatility (risk-parity-lite, not
fit to outcomes); the ONLY tilt is the descriptive fragility exposure multiplier,
which scales the equity sleeve down and routes the freed weight to defensives.
Every backtest of a lane built on this is directional-grade on free data (see
data_integrity) — forward NAV is the only sizing-grade truth.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.fragility import exposure_multiplier

# ETF proxies for each sleeve. Equity is the only "risk" sleeve; the rest are
# defensives the fragility overlay rotates into.
EQUITY_ASSETS = ["SPY"]
DEFENSIVE_ASSETS = ["TLT", "IEF", "LQD", "GLD", "SHY"]
ASSET_SLEEVE = {
    "equity": ["SPY"],            # US equities
    "long_duration": ["TLT"],     # 20y+ Treasuries (convexity in deflationary stress)
    "intermediate_duration": ["IEF"],  # 7-10y Treasuries
    "credit": ["LQD"],            # IG corporate credit
    "gold": ["GLD"],              # real-asset / tail hedge
    "cash": ["SHY"],              # 1-3y, near-cash
}
ALL_ASSETS = EQUITY_ASSETS + DEFENSIVE_ASSETS


def inverse_vol_weights(asset_returns: pd.DataFrame) -> dict:
    """Risk-parity-lite base: weight inversely to each asset's volatility.

    Not fit to outcomes (no hindsight) — just equalizes risk contribution as a
    first approximation. Assets with no/zero variance are dropped. Returns {} if
    nothing is usable.
    """
    if asset_returns is None or asset_returns.empty:
        return {}
    vols = asset_returns.std()
    inv = (1.0 / vols.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    total = float(inv.sum())
    if inv.empty or total <= 0:
        return {}
    return {str(k): float(v / total) for k, v in inv.items()}


def crossasset_target_weights(
    asset_returns: pd.DataFrame,
    fragility_composite: Optional[float] = None,
) -> dict:
    """Pure cross-asset target weights: inverse-vol base, tilted by the
    descriptive fragility exposure multiplier.

    The equity sleeve is scaled by the multiplier (1.0 = full, floor = most
    defensive); the freed weight is routed to the defensive sleeve pro-rata to its
    base weights, then the book is renormalized. With ``fragility_composite=None``
    (or no equity/defensive split available) it returns the untilted inverse-vol
    base. DESCRIPTIVE: no code path here arms or scales a live lane.
    """
    base = inverse_vol_weights(asset_returns)
    if not base:
        return {}

    mult_info = exposure_multiplier(fragility_composite)
    mult = mult_info.get("multiplier")
    if mult is None:
        mult = 1.0

    eq_cols = [c for c in base if c in EQUITY_ASSETS]
    def_cols = [c for c in base if c not in EQUITY_ASSETS]

    out = dict(base)
    if eq_cols and def_cols and mult < 1.0:
        freed = sum(base[c] * (1.0 - mult) for c in eq_cols)
        for c in eq_cols:
            out[c] = base[c] * mult
        def_total = sum(base[c] for c in def_cols)
        if def_total > 0 and freed > 0:
            for c in def_cols:
                out[c] += freed * (base[c] / def_total)

    s = sum(out.values())
    if s > 0:
        out = {k: round(v / s, 6) for k, v in out.items()}
    return out
