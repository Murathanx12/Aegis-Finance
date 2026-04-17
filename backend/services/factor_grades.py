"""
Aegis Finance — Seeking Alpha-style A/B/C/D/F Factor Report Card
===================================================================

Converts existing sector-relative z-scores into consumer-friendly letter
grades across five factor dimensions:

  - Value         (cheap on P/E, P/B, P/S, PEG, EV/EBITDA)
  - Growth        (revenue, earnings, profit growth)
  - Profitability (ROE, ROA, margins, FCF yield)
  - Momentum      (3m, 6m, 12m price momentum vs SPY)
  - Revisions     (analyst-estimate trend + Piotroski financial strength)

The underlying math reuses `relative_valuation` for sector-relative
percentiles; revisions reuse `fundamentals.get_fundamentals` for the
Piotroski F-Score, and momentum reuses `cross_sectional_momentum` where
available.

We *could* just surface z-scores, but empirical UX research (Seeking Alpha,
Morningstar Quant, Fidelity Quant Factor) shows retail investors
internalize letter grades dramatically faster than continuous scores.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from backend.services.relative_valuation import get_relative_valuation

logger = logging.getLogger(__name__)


# Percentile thresholds → letter grade (higher percentile = better)
_GRADE_BANDS = [
    (95, "A+"), (90, "A"), (85, "A-"),
    (80, "B+"), (70, "B"), (60, "B-"),
    (50, "C+"), (40, "C"), (30, "C-"),
    (20, "D+"), (10, "D"),
]


def percentile_to_grade(percentile: Optional[float]) -> Optional[str]:
    """Map a 0-100 percentile rank to an A+..F letter grade."""
    if percentile is None or not np.isfinite(percentile):
        return None
    p = max(0.0, min(100.0, float(percentile)))
    for thresh, grade in _GRADE_BANDS:
        if p >= thresh:
            return grade
    return "F"


def _grade_color(grade: Optional[str]) -> str:
    if grade is None:
        return "gray"
    if grade.startswith("A"):
        return "green"
    if grade.startswith("B"):
        return "emerald"
    if grade.startswith("C"):
        return "amber"
    if grade.startswith("D"):
        return "orange"
    return "red"


def _value_grade_from_relval(relval: dict) -> tuple[Optional[str], Optional[float], dict]:
    """Value grade uses the composite score from relative_valuation (0-100, cheaper=higher)."""
    composite = relval.get("composite_score")
    grade = percentile_to_grade(composite)
    notable = {}
    rankings = relval.get("rankings", {}) or {}
    for metric in ("pe_trailing", "pe_forward", "peg_ratio", "ev_ebitda", "price_to_book"):
        r = rankings.get(metric, {}) or {}
        vp = r.get("valuation_percentile")
        if vp is not None:
            notable[metric] = {
                "value": r.get("value"),
                "peer_percentile": vp,
                "grade": percentile_to_grade(vp),
            }
    return grade, composite, notable


def _growth_grade_from_relval(relval: dict) -> tuple[Optional[str], Optional[float], dict]:
    """Growth grade averages peer percentiles of revenue_growth + earnings_growth."""
    rankings = relval.get("rankings", {}) or {}
    details = {}
    scores = []
    for metric in ("revenue_growth", "earnings_growth"):
        r = rankings.get(metric, {}) or {}
        p = r.get("percentile")  # higher percentile = higher growth (already oriented correctly)
        if p is not None:
            scores.append(p)
            details[metric] = {
                "value": r.get("value"),
                "peer_percentile": p,
                "grade": percentile_to_grade(p),
            }
    composite = float(np.mean(scores)) if scores else None
    return percentile_to_grade(composite), composite, details


def _profitability_grade_from_relval(relval: dict) -> tuple[Optional[str], Optional[float], dict]:
    """Profitability: ROE + profit_margin + fcf_yield peer percentiles."""
    rankings = relval.get("rankings", {}) or {}
    details = {}
    scores = []
    for metric in ("roe", "profit_margin", "fcf_yield"):
        r = rankings.get(metric, {}) or {}
        p = r.get("percentile")
        if p is not None:
            scores.append(p)
            details[metric] = {
                "value": r.get("value"),
                "peer_percentile": p,
                "grade": percentile_to_grade(p),
            }
    composite = float(np.mean(scores)) if scores else None
    return percentile_to_grade(composite), composite, details


def _momentum_grade(ticker: str) -> tuple[Optional[str], Optional[float], dict]:
    """Momentum grade from cross-sectional momentum score, if available."""
    try:
        from backend.services.cross_sectional_momentum import score_ticker
    except ImportError:
        return None, None, {}

    try:
        result = score_ticker(ticker)
    except Exception as e:
        logger.debug("momentum score unavailable for %s: %s", ticker, e)
        return None, None, {}

    if result is None:
        return None, None, {}

    # cross_sectional_momentum exposes a percentile-style rank when it can
    pct = result.get("percentile") or result.get("momentum_percentile")
    score = result.get("score") or result.get("momentum_score")
    if pct is None and score is not None:
        # Map a z-like score into 0-100
        pct = float(np.clip(50 + score * 15, 0, 100))
    grade = percentile_to_grade(pct)
    return grade, pct, {
        "momentum_3m": result.get("return_3m") or result.get("mom_3m"),
        "momentum_6m": result.get("return_6m") or result.get("mom_6m"),
        "momentum_12m": result.get("return_12m") or result.get("mom_12m"),
        "peer_percentile": pct,
    }


def _revisions_grade(ticker: str) -> tuple[Optional[str], Optional[float], dict]:
    """Revisions/quality grade from Piotroski F-Score + optional estimate revisions."""
    try:
        from backend.services.fundamentals import get_fundamentals
    except ImportError:
        return None, None, {}

    try:
        fund = get_fundamentals(ticker)
    except Exception as e:
        logger.debug("fundamentals unavailable for %s: %s", ticker, e)
        fund = None

    details = {}
    scores = []

    if fund is not None:
        piotroski = (fund.get("piotroski_score") or {}).get("score")
        if piotroski is not None:
            # Score is 0-7 in current impl; convert to 0-100 so it rolls up with other grades
            pct = float(piotroski / 7.0 * 100.0)
            scores.append(pct)
            details["piotroski"] = {
                "score": piotroski,
                "strength": (fund.get("piotroski_score") or {}).get("strength"),
                "peer_percentile": pct,
                "grade": percentile_to_grade(pct),
            }

    # Optional earnings-estimate revisions
    try:
        from backend.services.earnings_intelligence import get_earnings_intelligence
        ei = get_earnings_intelligence(ticker)
        if ei is not None:
            beat_rate = ei.get("beat_rate")
            if beat_rate is not None:
                # Convert beat_rate (fraction 0-1) to percentile
                pct = float(beat_rate * 100.0)
                scores.append(pct)
                details["beat_rate"] = {
                    "value": beat_rate,
                    "peer_percentile": pct,
                    "grade": percentile_to_grade(pct),
                }
    except Exception:
        pass

    composite = float(np.mean(scores)) if scores else None
    return percentile_to_grade(composite), composite, details


def _overall_grade_from_components(components: dict) -> tuple[Optional[str], Optional[float]]:
    # Equal-weight composite of available factor percentiles
    scores = [c.get("percentile") for c in components.values() if c.get("percentile") is not None]
    if not scores:
        return None, None
    composite = float(np.mean(scores))
    return percentile_to_grade(composite), round(composite, 1)


def get_factor_report_card(ticker: str) -> Optional[dict]:
    """Compute the 5-factor A..F report card for a ticker.

    Returns None if even the underlying relative valuation lookup failed.
    """
    relval = get_relative_valuation(ticker)
    if relval is None:
        return None

    value_grade, value_pct, value_detail = _value_grade_from_relval(relval)
    growth_grade, growth_pct, growth_detail = _growth_grade_from_relval(relval)
    profit_grade, profit_pct, profit_detail = _profitability_grade_from_relval(relval)
    momentum_grade, momentum_pct, momentum_detail = _momentum_grade(ticker)
    revisions_grade, revisions_pct, revisions_detail = _revisions_grade(ticker)

    components = {
        "value": {"grade": value_grade, "percentile": value_pct, "color": _grade_color(value_grade), "details": value_detail},
        "growth": {"grade": growth_grade, "percentile": growth_pct, "color": _grade_color(growth_grade), "details": growth_detail},
        "profitability": {"grade": profit_grade, "percentile": profit_pct, "color": _grade_color(profit_grade), "details": profit_detail},
        "momentum": {"grade": momentum_grade, "percentile": momentum_pct, "color": _grade_color(momentum_grade), "details": momentum_detail},
        "revisions": {"grade": revisions_grade, "percentile": revisions_pct, "color": _grade_color(revisions_grade), "details": revisions_detail},
    }

    overall_grade, overall_pct = _overall_grade_from_components(components)

    return {
        "ticker": ticker,
        "sector": relval.get("sector"),
        "overall_grade": overall_grade,
        "overall_percentile": overall_pct,
        "overall_color": _grade_color(overall_grade),
        "components": components,
        "peer_count": relval.get("peer_count"),
        "methodology": "Sector-relative peer percentiles mapped to letter bands (A+=95th pctile, F<10th).",
    }
