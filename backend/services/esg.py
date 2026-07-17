"""
Aegis Finance — ESG Score Aggregator
======================================

Blends ESG (Environmental / Social / Governance) and controversies data
from multiple free providers into a single normalised score per ticker.

Why this exists
---------------
Bloomberg's ESG terminal module costs add-on fees; MSCI ESG Manager is
quote-only. Both Finnhub and FMP expose useful ESG endpoints on their
free tier — Aegis already uses both providers — so a thin blender lets
the platform ship ESG scoring without a paid SKU.

Public surface
--------------
- ``fetch_finnhub_esg(ticker)``  — raw provider blob (cached)
- ``fetch_fmp_esg(ticker)``      — raw provider blob (cached)
- ``compute_esg_score(ticker)``  — blended {E, S, G, total, controversies}

Output schema (compute_esg_score)
---------------------------------
{
    "ticker": "AAPL",
    "total_score": 78.4,          # 0..100, higher = better
    "grade": "A",                  # F..A+
    "environmental": 76.0,
    "social": 82.0,
    "governance": 77.0,
    "controversies": {
        "level": "low",            # none / low / moderate / high / severe
        "count_12m": 1,
    },
    "sources": ["finnhub", "fmp"],
    "as_of": "2026-04-17",
    "methodology": "Equal-weighted blend of available providers; subscores
                    averaged when reported by multiple."
}
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from backend.cache import cache_get, cache_set
from backend.config import api_keys

logger = logging.getLogger(__name__)

_FINNHUB_BASE = "https://finnhub.io/api/v1"
_FMP_BASE = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 10
_CACHE_TTL = 24 * 60 * 60  # 24h — ESG scores update monthly at most


# ── Provider fetchers ───────────────────────────────────────────────────────


def fetch_finnhub_esg(ticker: str) -> Optional[dict]:
    """Pull Finnhub's company ESG score endpoint.

    Schema (per Finnhub docs as of 2026):
        { "symbol": "AAPL", "totalESG": 18.4, "environmentScore": 5.2,
          "socialScore": 7.1, "governanceScore": 6.1,
          "controversyLevel": 3, "controversyCategoriesNumber": 2 }
    """
    if not api_keys.has("finnhub"):
        return None
    cache_key = f"esg_finnhub:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached or None

    try:
        r = requests.get(
            f"{_FINNHUB_BASE}/stock/esg",
            params={"symbol": ticker, "token": api_keys.finnhub},
            timeout=_TIMEOUT,
        )
        if r.status_code in (401, 403, 429):
            return None
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict) or not data:
            cache_set(cache_key, {})
            return None
        cache_set(cache_key, data)
        return data
    except Exception as e:
        logger.debug("Finnhub ESG fetch failed for %s: %s", ticker, e)
        return None


def fetch_fmp_esg(ticker: str) -> Optional[dict]:
    """Pull FMP's ESG risk ratings endpoint.

    Schema typically returns an array of dicts ordered by year descending:
        [{ "symbol": "AAPL", "date": "2025-12-31",
           "environmentalScore": 80, "socialScore": 75,
           "governanceScore": 78, "ESGScore": 77.6,
           "ESGRiskRating": "Low" }, ...]
    """
    if not api_keys.has("fmp"):
        return None
    cache_key = f"esg_fmp:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached or None

    # ESG is a nice-to-have — never let it eat the shared FMP quota that the
    # pre-registered congress-IC collector needs (2026-07-17 budget ledger).
    from backend.services import fmp_budget
    if not fmp_budget.try_spend():
        return None

    try:
        r = requests.get(
            f"{_FMP_BASE}/esg-environmental-social-governance-data",
            params={"symbol": ticker, "apikey": api_keys.fmp},
            timeout=_TIMEOUT,
        )
        if r.status_code in (401, 403, 429):
            return None
        r.raise_for_status()
        data = r.json()
        if not data:
            cache_set(cache_key, {})
            return None
        # Most-recent record (FMP returns newest first)
        latest = data[0] if isinstance(data, list) else data
        cache_set(cache_key, latest)
        return latest
    except Exception as e:
        logger.debug("FMP ESG fetch failed for %s: %s", ticker, e)
        return None


# ── Normalisation ───────────────────────────────────────────────────────────


def _normalise_finnhub(blob: dict) -> Optional[dict]:
    """Map Finnhub raw ESG payload into the unified schema (0..100 scale)."""
    if not blob:
        return None
    # Finnhub uses a 0..40 risk-style scale where LOWER is better. Convert
    # to a 0..100 "higher is better" view so it composes with FMP cleanly.
    def _flip(score: float) -> float:
        score = max(0.0, min(40.0, float(score)))
        return round(100.0 - score * 2.5, 2)

    e = blob.get("environmentScore")
    s = blob.get("socialScore")
    g = blob.get("governanceScore")
    total = blob.get("totalESG")
    controversy_level = blob.get("controversyLevel")  # 1..5 (5 = severe)
    n_categories = blob.get("controversyCategoriesNumber")

    return {
        "environmental": _flip(e) if e is not None else None,
        "social": _flip(s) if s is not None else None,
        "governance": _flip(g) if g is not None else None,
        "total_score": _flip(total) if total is not None else None,
        "controversy_level": (
            ["none", "low", "low", "moderate", "high", "severe"][int(controversy_level)]
            if controversy_level is not None
            and 0 <= int(controversy_level) <= 5
            else None
        ),
        "controversy_count": n_categories,
    }


def _normalise_fmp(blob: dict) -> Optional[dict]:
    """FMP already uses a 0..100 'higher is better' scale."""
    if not blob:
        return None
    e = blob.get("environmentalScore")
    s = blob.get("socialScore")
    g = blob.get("governanceScore")
    total = blob.get("ESGScore")
    risk_rating = (blob.get("ESGRiskRating") or "").lower() or None

    return {
        "environmental": float(e) if e is not None else None,
        "social": float(s) if s is not None else None,
        "governance": float(g) if g is not None else None,
        "total_score": float(total) if total is not None else None,
        "controversy_level": risk_rating,  # FMP labels: low/medium/high/severe
        "controversy_count": None,
        "as_of": blob.get("date"),
    }


def _avg(*xs) -> Optional[float]:
    vals = [v for v in xs if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _grade(total: Optional[float]) -> Optional[str]:
    """Map a 0..100 score to a letter grade."""
    if total is None:
        return None
    if total >= 85:
        return "A+"
    if total >= 75:
        return "A"
    if total >= 65:
        return "B"
    if total >= 55:
        return "C"
    if total >= 40:
        return "D"
    return "F"


def _worst_controversy(level_a: Optional[str], level_b: Optional[str]) -> Optional[str]:
    """Pick the worse of two controversy levels — used when blending sources."""
    rank = {"none": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "severe": 4}
    candidates = [(rank.get(l, -1), l) for l in (level_a, level_b) if l]
    if not candidates:
        return None
    return max(candidates)[1]


# ── Public API ──────────────────────────────────────────────────────────────


def compute_esg_score(ticker: str) -> dict:
    """Blend Finnhub + FMP ESG into a single per-ticker view."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"error": "ticker required"}

    cache_key = f"esg_blend:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    raw_finnhub = fetch_finnhub_esg(ticker)
    raw_fmp = fetch_fmp_esg(ticker)

    n_fh = _normalise_finnhub(raw_finnhub)
    n_fmp = _normalise_fmp(raw_fmp)

    sources = []
    if n_fh:
        sources.append("finnhub")
    if n_fmp:
        sources.append("fmp")

    if not sources:
        result = {
            "ticker": ticker,
            "error": "No ESG data available from configured providers",
            "sources": [],
        }
        cache_set(cache_key, result)
        return result

    # Equal-weight average across providers
    e = _avg(n_fh and n_fh.get("environmental"), n_fmp and n_fmp.get("environmental"))
    s = _avg(n_fh and n_fh.get("social"), n_fmp and n_fmp.get("social"))
    g = _avg(n_fh and n_fh.get("governance"), n_fmp and n_fmp.get("governance"))
    total = _avg(
        n_fh and n_fh.get("total_score"),
        n_fmp and n_fmp.get("total_score"),
    )
    # If subscores exist but no provider reported a total, derive it
    if total is None:
        total = _avg(e, s, g)

    controversy_level = _worst_controversy(
        n_fh and n_fh.get("controversy_level"),
        n_fmp and n_fmp.get("controversy_level"),
    )

    result = {
        "ticker": ticker,
        "total_score": total,
        "grade": _grade(total),
        "environmental": e,
        "social": s,
        "governance": g,
        "controversies": {
            "level": controversy_level,
            "count_12m": (n_fh or {}).get("controversy_count"),
        },
        "sources": sources,
        "as_of": (n_fmp or {}).get("as_of"),
        "methodology": (
            "Equal-weighted blend of available providers; subscores averaged "
            "when reported by multiple. Finnhub risk-style scores are flipped "
            "to a higher-is-better 0..100 scale before blending."
        ),
    }
    cache_set(cache_key, result)
    return result
