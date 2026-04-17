"""
Aegis Finance — Multi-Currency Portfolio Analytics
====================================================

Detects non-USD-listed positions in a portfolio, FX-translates them to a
configurable base currency, and decomposes total return into local +
currency components. Built on top of the existing FX curves service so we
inherit FRED short-rate fall-backs.

Public surface
--------------
- ``infer_listing_currency(ticker)``     — heuristic from suffix or override
- ``translate_position(position, base)`` — wrap a position with FX context
- ``currency_exposure(positions, base)`` — exposure breakdown + concentration
- ``hedged_vs_unhedged(positions, base, *, period)`` — FX-impact decomp
- ``portfolio_currency_report(positions, base)`` — full UI rollup

Why this exists
---------------
Bloomberg PORT, FactSet, and Refinitiv all default to multi-currency
accounting. Aegis previously reported nominal USD only — if a user
holds ASML.AS or 7203.T, their FX P&L is silently rolled into "stock
return" rather than being decomposed. This module exposes that.

Conventions
-----------
- Currency codes are ISO 4217 (USD, EUR, JPY, GBP, ...).
- ``base`` defaults to USD.
- FX rates are quoted as ``base_per_quote`` — multiplying a quote-currency
  amount by the rate gives the base-currency amount.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Mapping from yfinance suffix → ISO listing currency. Sourced from
# yfinance docs / Yahoo Finance market codes; covers the major venues
# users hold via cross-listings.
_SUFFIX_CURRENCY: dict[str, str] = {
    # Europe
    ".L": "GBP",       # London
    ".AS": "EUR",      # Amsterdam
    ".PA": "EUR",      # Paris
    ".DE": "EUR",      # Xetra (Frankfurt)
    ".F": "EUR",       # Frankfurt
    ".MI": "EUR",      # Milan
    ".MC": "EUR",      # Madrid
    ".BR": "EUR",      # Brussels
    ".LS": "EUR",      # Lisbon
    ".VI": "EUR",      # Vienna
    ".HE": "EUR",      # Helsinki
    ".OL": "NOK",      # Oslo
    ".ST": "SEK",      # Stockholm
    ".CO": "DKK",      # Copenhagen
    ".SW": "CHF",      # Swiss
    ".VX": "CHF",      # Swiss VirtX
    ".IS": "TRY",      # Istanbul
    ".AT": "EUR",      # Athens
    ".WA": "PLN",      # Warsaw
    # Asia / Pacific
    ".T": "JPY",       # Tokyo
    ".HK": "HKD",      # Hong Kong
    ".KS": "KRW",      # Korea
    ".KQ": "KRW",      # Kosdaq
    ".SS": "CNY",      # Shanghai
    ".SZ": "CNY",      # Shenzhen
    ".SI": "SGD",      # Singapore
    ".NS": "INR",      # NSE (India)
    ".BO": "INR",      # BSE (India)
    ".TW": "TWD",      # Taiwan
    ".AX": "AUD",      # ASX (Australia)
    ".NZ": "NZD",      # New Zealand
    # Americas
    ".TO": "CAD",      # Toronto
    ".V": "CAD",       # TSX-V
    ".SA": "BRL",      # São Paulo (Bovespa)
    ".MX": "MXN",      # Mexican Bolsa
    ".SN": "CLP",      # Santiago
    ".BA": "ARS",      # Buenos Aires
}

DEFAULT_BASE = "USD"


def infer_listing_currency(ticker: str, override: Optional[str] = None) -> str:
    """Best-effort listing currency from yfinance suffix.

    ``override`` lets a caller pin the currency (e.g. ADR holdings that
    quote in USD even though the underlying is foreign).
    """
    if override:
        return override.upper()
    if not ticker:
        return DEFAULT_BASE
    t = ticker.upper().strip()
    # Match longest suffix first so ".KQ" wins over ".K"
    for suffix in sorted(_SUFFIX_CURRENCY.keys(), key=len, reverse=True):
        if t.endswith(suffix):
            return _SUFFIX_CURRENCY[suffix]
    return DEFAULT_BASE


def fx_rate(quote: str, base: str = DEFAULT_BASE) -> Optional[float]:
    """Return base-per-quote FX rate (e.g. fx_rate('EUR') ≈ 1.08 USD/EUR).

    Falls back to ``None`` when the underlying spot is unavailable, in
    which case callers should treat the position as untranslated.
    """
    if quote == base:
        return 1.0

    # Try directly: ``QUOTEBASE`` (e.g. EURUSD)
    from backend.services.fx_curves import fetch_spot

    direct_pair = f"{quote}{base}"
    spot = fetch_spot(direct_pair)
    if spot is not None and spot > 0:
        return float(spot)

    # Try inverse: ``BASEQUOTE`` (e.g. USDJPY → invert)
    inv_pair = f"{base}{quote}"
    inv = fetch_spot(inv_pair)
    if inv is not None and inv > 0:
        return float(1.0 / inv)

    # Triangulate via USD as last resort (e.g. ARSCAD → ARSUSD * USDCAD)
    if base != "USD" and quote != "USD":
        leg_a = fx_rate(quote, "USD")
        leg_b = fx_rate("USD", base)
        if leg_a and leg_b:
            return leg_a * leg_b
    return None


def translate_position(
    position: dict, base: str = DEFAULT_BASE
) -> dict:
    """Enrich a single position with FX context and base-currency value.

    Position fields used:
        ticker         (str, required)
        shares         (float, optional)
        current_price  (float, optional, in listing currency)
        market_value   (float, optional, in listing currency; computed if missing)
        currency       (str, optional override — e.g. for ADRs)
    """
    base = (base or DEFAULT_BASE).upper()
    ticker = (position.get("ticker") or "").upper()
    listing_ccy = infer_listing_currency(ticker, position.get("currency"))

    shares = float(position.get("shares") or 0)
    price = float(position.get("current_price") or 0)
    mv_local = float(
        position.get("market_value")
        if position.get("market_value") is not None
        else shares * price
    )

    rate = fx_rate(listing_ccy, base) if listing_ccy != base else 1.0
    mv_base = mv_local * rate if rate is not None else None

    return {
        "ticker": ticker,
        "listing_currency": listing_ccy,
        "base_currency": base,
        "shares": shares,
        "price_local": price,
        "market_value_local": round(mv_local, 4),
        "fx_rate_to_base": round(rate, 6) if rate is not None else None,
        "market_value_base": round(mv_base, 4) if mv_base is not None else None,
        "fx_translated": rate is not None and listing_ccy != base,
        "fx_unavailable": rate is None,
    }


def currency_exposure(
    positions: list[dict], base: str = DEFAULT_BASE
) -> dict:
    """Aggregate positions by listing currency.

    Returns ``{currency: {weight, market_value_base, n_positions}}``
    plus a Herfindahl currency-concentration index for quick risk reads.
    """
    base = (base or DEFAULT_BASE).upper()
    enriched = [translate_position(p, base) for p in positions]
    total_mv = sum(
        p["market_value_base"] or 0.0
        for p in enriched
        if p["market_value_base"] is not None
    )

    by_ccy: dict[str, dict] = {}
    for p in enriched:
        ccy = p["listing_currency"]
        b = by_ccy.setdefault(
            ccy,
            {"market_value_base": 0.0, "n_positions": 0, "weight": 0.0, "tickers": []},
        )
        if p["market_value_base"] is not None:
            b["market_value_base"] += p["market_value_base"]
        b["n_positions"] += 1
        b["tickers"].append(p["ticker"])

    if total_mv > 0:
        for ccy, b in by_ccy.items():
            b["weight"] = round(b["market_value_base"] / total_mv, 6)
            b["market_value_base"] = round(b["market_value_base"], 4)

    # Currency-concentration HHI (0..1; 1 means single currency)
    weights = [b["weight"] for b in by_ccy.values() if b["weight"] > 0]
    hhi = round(sum(w * w for w in weights), 6) if weights else 0.0

    n_ccys = sum(1 for w in weights if w > 0)
    fx_unavailable = [p["ticker"] for p in enriched if p["fx_unavailable"]]

    return {
        "base_currency": base,
        "total_market_value_base": round(total_mv, 4),
        "n_positions": len(positions),
        "n_currencies": n_ccys,
        "currency_hhi": hhi,
        "exposures": dict(
            sorted(by_ccy.items(), key=lambda kv: -kv[1]["market_value_base"])
        ),
        "fx_unavailable_tickers": fx_unavailable,
        "is_pure_base_currency": n_ccys == 1 and base in by_ccy,
    }


def hedged_vs_unhedged(
    positions: list[dict],
    base: str = DEFAULT_BASE,
    *,
    period_days: int = 30,
) -> dict:
    """Decompose a portfolio's recent return into local + FX components.

    Computes ``r_total ≈ r_local + r_fx + cross-term``. The decomposition
    is exact for log-returns and a useful approximation for simple
    returns. Requires per-position recent returns + recent FX changes.

    Position fields used in addition to ``translate_position``:
        return_local_pct  (float, optional) — return in listing currency
                           over the period (decimal, e.g. 0.034 for +3.4%)
    """
    base = (base or DEFAULT_BASE).upper()
    enriched = [translate_position(p, base) for p in positions]

    # Determine FX returns by currency over the period
    fx_returns: dict[str, Optional[float]] = {}
    for p in enriched:
        ccy = p["listing_currency"]
        if ccy in fx_returns:
            continue
        if ccy == base:
            fx_returns[ccy] = 0.0
            continue
        fx_returns[ccy] = _fx_return_pct(ccy, base, days=period_days)

    rows: list[dict] = []
    weights = []
    contrib_local = []
    contrib_fx = []

    total_mv = sum(
        p["market_value_base"] or 0.0
        for p in enriched
        if p["market_value_base"] is not None
    )

    for raw, p in zip(positions, enriched):
        if not p["market_value_base"] or total_mv <= 0:
            continue
        w = p["market_value_base"] / total_mv
        r_local = float(raw.get("return_local_pct") or 0.0)
        r_fx = fx_returns.get(p["listing_currency"]) or 0.0
        # Linear approximation: r_total ≈ r_local + r_fx
        r_total = r_local + r_fx + r_local * r_fx
        rows.append(
            {
                "ticker": p["ticker"],
                "weight": round(w, 6),
                "return_local_pct": round(r_local * 100, 4),
                "return_fx_pct": round(r_fx * 100, 4),
                "return_total_pct": round(r_total * 100, 4),
                "currency": p["listing_currency"],
            }
        )
        weights.append(w)
        contrib_local.append(w * r_local)
        contrib_fx.append(w * r_fx)

    port_local = sum(contrib_local) if contrib_local else 0.0
    port_fx = sum(contrib_fx) if contrib_fx else 0.0
    port_total = port_local + port_fx + port_local * port_fx

    return {
        "base_currency": base,
        "period_days": period_days,
        "portfolio_return_local_pct": round(port_local * 100, 4),
        "portfolio_return_fx_pct": round(port_fx * 100, 4),
        "portfolio_return_total_pct": round(port_total * 100, 4),
        "fx_attribution_share": (
            round(port_fx / port_total, 4)
            if abs(port_total) > 1e-9
            else None
        ),
        "fx_returns_pct": {
            ccy: (round(r * 100, 4) if r is not None else None)
            for ccy, r in fx_returns.items()
        },
        "positions": rows,
    }


def _fx_return_pct(quote: str, base: str, *, days: int = 30) -> Optional[float]:
    """Spot %change of `quote` measured in `base` over the lookback window."""
    if quote == base:
        return 0.0
    try:
        import yfinance as yf

        # Build the yfinance pair ticker with USD triangulation when needed
        if quote == "USD" or base == "USD":
            pair = (
                f"{quote}{base}=X" if quote != "USD" else f"{base}{quote}=X"
            )
        else:
            # Triangulate via USD by aggregating two legs
            leg_a = _fx_return_pct(quote, "USD", days=days)
            leg_b = _fx_return_pct("USD", base, days=days)
            if leg_a is None or leg_b is None:
                return None
            return (1 + leg_a) * (1 + leg_b) - 1

        hist = yf.Ticker(pair).history(period=f"{max(days * 2, 5)}d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        recent = closes.iloc[-1]
        anchor = closes.iloc[max(-len(closes), -days - 1)]
        if anchor <= 0:
            return None
        # If we built BASEQUOTE pair instead of QUOTEBASE, invert
        if pair.startswith(base) and quote != "USD":
            return float(anchor / recent - 1.0)
        return float(recent / anchor - 1.0)
    except Exception as e:
        logger.debug("fx return fetch failed for %s->%s: %s", quote, base, e)
        return None


def portfolio_currency_report(
    positions: list[dict], base: str = DEFAULT_BASE
) -> dict:
    """Full report combining exposure + recent FX return decomposition."""
    base = (base or DEFAULT_BASE).upper()
    if not positions:
        return {"base_currency": base, "error": "no positions provided"}

    exposure = currency_exposure(positions, base)
    decomp = hedged_vs_unhedged(positions, base, period_days=30)

    return {
        "base_currency": base,
        "exposure": exposure,
        "recent_decomposition_30d": decomp,
        "interpretation": _interpretation(exposure, decomp),
    }


def _interpretation(exposure: dict, decomp: dict) -> str:
    n_ccy = exposure.get("n_currencies", 0)
    fx_share = decomp.get("fx_attribution_share")
    if n_ccy <= 1:
        return "Single-currency portfolio — no FX attribution applicable."
    if fx_share is None:
        return f"Multi-currency portfolio ({n_ccy} currencies) — flat recent return."
    pct = abs(fx_share) * 100
    direction = "tailwind" if (decomp.get("portfolio_return_fx_pct") or 0) > 0 else "headwind"
    return (
        f"Multi-currency portfolio ({n_ccy} currencies). FX has been a "
        f"{direction}, contributing ~{pct:.0f}% of the last 30 days' return."
    )
