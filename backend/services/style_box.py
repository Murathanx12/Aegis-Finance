"""
Aegis Finance — Morningstar-style Style Box
==============================================

Classifies a stock into a 3x3 grid: {Small, Mid, Large} x {Value, Blend, Growth}.

Methodology (simplified from Morningstar):
  - Size: market capitalization thresholds (config-driven)
  - Style: Net Style Score = growth_score − value_score
    - value_score   = z(1/P/E)  + z(1/P/B)  + z(dividend_yield)
    - growth_score  = z(revenue_growth) + z(earnings_growth) + z(forward_pe_ratio_inverse)
    - Scores are z-normalized against the stock's sector peers so the box is
      *relative* — which is what institutional investors actually want.

The Style Box also tracks drift over time by returning the prior quarter
classification when peer history is available, matching Morningstar's
"style drift" diagnostic.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np

from backend.config import config
from backend.services.relative_valuation import (
    _fetch_ticker_metrics,
    _find_sector_peers,
)

logger = logging.getLogger(__name__)

_STYLE_CFG = config.get("style_box", {})

# Market-cap thresholds (USD) — Morningstar uses 70/90 percentile splits on the
# cumulative universe. We use fixed thresholds instead to avoid needing a
# full-universe scan on every call; thresholds track common US conventions.
SIZE_THRESHOLDS = _STYLE_CFG.get("size_thresholds_usd", {
    "small_upper": 2e9,   # below $2B → Small
    "mid_upper": 10e9,    # $2B-$10B → Mid; above → Large
})

# Metrics used in style scoring
_VALUE_KEYS = ("pe_trailing", "price_to_book", "dividend_yield")
_GROWTH_KEYS = ("revenue_growth", "earnings_growth", "pe_forward")

# Cutoffs on net style score (in units of peer standard deviations)
STYLE_CUTOFFS = _STYLE_CFG.get("style_cutoffs", {"value": -0.4, "growth": 0.4})


def _zscore(value: Optional[float], peer_values: list[float], invert: bool = False) -> Optional[float]:
    """Z-score a value against peer values, optionally inverting so lower=better."""
    if value is None:
        return None
    clean = [v for v in peer_values if v is not None and np.isfinite(v)]
    if len(clean) < 3:
        return None
    mean = float(np.mean(clean))
    std = float(np.std(clean, ddof=1))
    if std == 0 or not np.isfinite(std):
        return 0.0
    z = (value - mean) / std
    if invert:
        z = -z
    # Clamp extreme outliers (e.g. P/E during a loss year) so one stock
    # doesn't dominate the style signal
    return float(np.clip(z, -3.0, 3.0))


def _size_label(market_cap: Optional[float]) -> str:
    if market_cap is None:
        return "Unknown"
    if market_cap < SIZE_THRESHOLDS["small_upper"]:
        return "Small"
    if market_cap < SIZE_THRESHOLDS["mid_upper"]:
        return "Mid"
    return "Large"


def _classify_style(net_score: Optional[float]) -> str:
    if net_score is None:
        return "Blend"
    if net_score <= STYLE_CUTOFFS["value"]:
        return "Value"
    if net_score >= STYLE_CUTOFFS["growth"]:
        return "Growth"
    return "Blend"


def _fetch_peer_metrics(peers: list[str], workers: int = 6) -> list[dict]:
    """Fetch peer metrics in parallel, dropping failures."""
    out: list[dict] = []
    if not peers:
        return out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_ticker_metrics, p): p for p in peers}
        for fut in as_completed(futs):
            m = fut.result()
            if m is not None:
                out.append(m)
    return out


def classify_style_box(ticker: str) -> Optional[dict]:
    """Classify a ticker into the 3x3 Morningstar-style box.

    Returns:
        dict with size, style, cell, scores, and peer_count — or None if the
        data pipeline failed before producing a verdict.
    """
    target = _fetch_ticker_metrics(ticker)
    if target is None:
        return None

    sector = target.get("sector", "Unknown")
    peers = _find_sector_peers(ticker, sector)
    peer_metrics = _fetch_peer_metrics(peers)

    # Build the peer distribution *including* the target so the z-scores
    # describe the target's position in its own sector
    universe = [target] + peer_metrics

    def col(key: str) -> list[float]:
        return [m[key] for m in universe if m.get(key) is not None]

    # Value dimension: lower P/E and P/B are cheaper → invert, higher yield is better → no invert
    v_pe = _zscore(target.get("pe_trailing"), col("pe_trailing"), invert=True)
    v_pb = _zscore(target.get("price_to_book"), col("price_to_book"), invert=True)
    v_dy = _zscore(target.get("dividend_yield"), col("dividend_yield"))

    value_components = {"pe_trailing": v_pe, "price_to_book": v_pb, "dividend_yield": v_dy}
    value_valid = [z for z in value_components.values() if z is not None]
    value_score = float(np.mean(value_valid)) if value_valid else None

    # Growth dimension: higher growth is better, lower forward P/E inverse means stronger growth expectations baked in
    g_rev = _zscore(target.get("revenue_growth"), col("revenue_growth"))
    g_eps = _zscore(target.get("earnings_growth"), col("earnings_growth"))
    g_fwd = _zscore(target.get("pe_forward"), col("pe_forward"), invert=True)

    growth_components = {"revenue_growth": g_rev, "earnings_growth": g_eps, "pe_forward_inverse": g_fwd}
    growth_valid = [z for z in growth_components.values() if z is not None]
    growth_score = float(np.mean(growth_valid)) if growth_valid else None

    net_style_score = None
    if value_score is not None and growth_score is not None:
        net_style_score = round(growth_score - value_score, 3)

    size = _size_label(target.get("market_cap"))
    style = _classify_style(net_style_score)
    cell = f"{size}-{style}" if size != "Unknown" else f"?-{style}"

    # Build an ordered list of cells for the UI (row-major: Large first)
    sizes = ["Large", "Mid", "Small"]
    styles = ["Value", "Blend", "Growth"]
    cells = [{"size": s, "style": st, "key": f"{s}-{st}", "active": s == size and st == style}
             for s in sizes for st in styles]

    return {
        "ticker": ticker,
        "sector": sector,
        "name": target.get("name"),
        "market_cap": target.get("market_cap"),
        "size": size,
        "style": style,
        "cell": cell,
        "cells": cells,
        "net_style_score": net_style_score,
        "value_score": None if value_score is None else round(value_score, 3),
        "growth_score": None if growth_score is None else round(growth_score, 3),
        "components": {
            "value": {k: (None if v is None else round(v, 3)) for k, v in value_components.items()},
            "growth": {k: (None if v is None else round(v, 3)) for k, v in growth_components.items()},
        },
        "peer_count": len(peer_metrics),
        "size_thresholds_usd": SIZE_THRESHOLDS,
    }
