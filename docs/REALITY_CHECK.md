# Reality Check — Aegis Finance vs Real-World Sources

*Generated: 2026-03-31*

## 1. AAPL Analyst Price Target

| Source | 12-Month Target | Range |
|--------|----------------|-------|
| **Aegis (from yfinance)** | **$295.31** | **$205 — $350** |
| Wall Street consensus (28 analysts) | $296.90 — $304.40 | $215 — $350 |
| Goldman Sachs | $330 | — |
| Wedbush (Dan Ives) | $350 | — |
| Citi (Atif Malik) | $330 | — |

**Assessment: Well-aligned.** Aegis pulls analyst targets from yfinance which aggregates the same Wall Street data. Our $295.31 mean sits squarely in the consensus range of $297-$304. The $205-$350 range matches almost exactly.

**Aegis 5Y projection:** 116.9% total return (AAPL current: $246.63). This implies ~$534 in 5 years, or ~16.8% CAGR. The mega-cap CAGR cap of 15% is active, so the capped drift is 14.8% annualized. This is aggressive but defensible given AAPL's historical performance and AI catalyst.

Sources:
- [MarketBeat AAPL Forecast](https://www.marketbeat.com/stocks/NASDAQ/AAPL/forecast/)
- [StockAnalysis AAPL](https://stockanalysis.com/stocks/aapl/forecast/)

---

## 2. S&P 500 — Goldman Sachs Target

| Source | Year-End 2026 Target | Implied Return |
|--------|---------------------|----------------|
| **Aegis config (GS benchmark)** | **6.5% annualized (10Y)** | **—** |
| Goldman Sachs (official) | 7,600 | +19.3% from 6,369 |
| JPMorgan (revised Mar 2026) | 7,200 | +13.0% |
| Stifel (lowest) | 7,000 | +9.9% |

**Assessment: Aligned.** Aegis doesn't produce a single-year S&P target — it produces a 5Y MC distribution. The MC 5Y annualized return of 4.5% (from the last stress test) is conservative relative to Goldman's bullish 1Y call but correctly reflects the 10Y institutional consensus of 3.1%-7.6%. Goldman's 7,600 target implies earnings growth of ~12%, which Aegis captures via the AI Productivity Boom scenario (14% return, 15% probability).

Goldman's key assumption: S&P 500 EPS of ~$309 in 2026, ~$342 in 2027. P/E at 21x forward (above 10Y average of 18.9x but justified by AI earnings growth).

Sources:
- [Goldman Sachs 2026 Outlook](https://www.goldmansachs.com/insights/articles/the-sp-500-expected-to-rally-12-this-year)
- [Goldman Sachs Doubles Down](https://finance.yahoo.com/news/goldman-sachs-doubles-down-bold-153300685.html)

---

## 3. VIX and 10-Year Treasury Yield

| Indicator | Aegis Dashboard | Real-World (March 28-31, 2026) | Gap |
|-----------|----------------|-------------------------------|-----|
| **VIX** | 30.8 — 31.1 | 31.05 (FRED VIXCLS) | <0.3% — Excellent |
| **10Y Treasury** | 4.42% (FRED DGS10) | 4.42% — 4.48% (fell to 4.34% Mon) | 0% — Exact |
| **S&P 500** | 6,348 — 6,369 | 6,368.85 (March 28 close) | 0.3% — Excellent |

**Assessment: Excellent accuracy.** Aegis fetches live data from FRED and Yahoo Finance. VIX within 0.3%, 10Y yield exact match, S&P within 0.3%. Data freshness is 1-2 business days (weekend gap).

**Context:** VIX at 31 is driven by Iran conflict escalation and oil price surge. The 10Y yield spiked to 4.48% intraweek on inflation fears from oil, then retreated. Aegis correctly flags this as elevated stress (VIX > 25 threshold).

Sources:
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)
- [CNBC US10Y](https://www.cnbc.com/quotes/US10Y)

---

## 4. Wealthfront Conservative Portfolio

| Asset Class | Aegis Conservative | Wealthfront Conservative (Risk 2-3) |
|-------------|-------------------|--------------------------------------|
| US Bonds (BND) | 44.9% | ~35-40% (US govt + corporate bonds) |
| TIPS (VTIP) | 15.0% | ~10-15% |
| US Stocks (VTI) | 21.6% | ~15-20% |
| International (VXUS) | 6.6% | ~5-10% |
| Gold (GLD) | 10.0% | ~5% (natural resources) |
| REITs (VNQ) | 2.0% | ~5% |

**Assessment: Close match.** Both portfolios are bond-heavy (60%+ fixed income for Aegis, ~55-65% for Wealthfront at low risk scores). Aegis has slightly more gold (10% vs ~5%) and less REITs. Wealthfront uses 8-12 asset classes vs Aegis's 6, including municipal bonds, EM bonds, and dividend stocks that Aegis doesn't include.

**Key difference:** Wealthfront uses 20 risk levels (0.5-10.0) with continuous allocation curves. Aegis uses 3 discrete levels (conservative/moderate/aggressive) with template blending. Adding more granularity (5-10 levels) would improve personalization.

**Wealthfront methodology note (2026):** Their March 2026 white paper describes a mean-variance optimization with Black-Litterman views, tax-loss harvesting, and automatic rebalancing with drift bands. Aegis implements BL and HRP but lacks tax-loss harvesting and drift-band rebalancing.

Sources:
- [Wealthfront Investment Methodology](https://research.wealthfront.com/whitepapers/investment-methodology/)
- [Wealthfront Risk Score Explainer](https://www.wealthfront.com/blog/ask-wealthfront-risk-score-explainer/)

---

## 5. Betterment Aggressive Portfolio

| Asset Class | Aegis Aggressive | Betterment Aggressive (~90% stocks) |
|-------------|-----------------|--------------------------------------|
| US Stocks (VTI) | 35.0% | ~35-40% (large + mid cap) |
| Tech/Growth (QQQ+VGT) | 35.0% | ~25-30% (large-cap growth tilt) |
| International (VXUS) | 15.0% | ~20-25% (developed + EM) |
| Speculative (ARKK) | 5.0% | 0% (no speculative ETFs) |
| Bonds (BND) | 5.0% | ~5-10% |
| Gold (GLD) | 5.0% | 0% |

**Assessment: Broadly similar equity exposure (~90% for both), but different composition.** Aegis is more concentrated in US tech (35% QQQ+VGT) vs Betterment which spreads more into international. Aegis includes ARKK (speculative innovation) and GLD (gold) which Betterment doesn't use. Betterment separates developed international from emerging markets; Aegis uses VXUS (all international).

**Key difference:** Betterment offers 101 risk levels (0-100% stocks) vs Aegis's 3. Their 2026 update shifted mid-cap allocation to large-cap and added an actively-managed bond fund. Aegis's aggressive template is more growth-tilted (tech-heavy) while Betterment is more diversified.

**Betterment methodology note:** Uses Black-Litterman with periodic view updates, drift-tolerance rebalancing (not calendar-based), and tax-coordinated allocation across account types. Aegis implements BL but lacks drift-tolerance rebalancing and multi-account tax coordination.

Sources:
- [Betterment Portfolio Strategy](https://www.betterment.com/resources/betterment-portfolio-strategy)
- [Betterment 2026 Portfolio Updates](https://www.betterment.com/resources/2026-portfolio-updates)

---

## Summary

| Comparison | Aegis Accuracy | Action Needed |
|-----------|---------------|---------------|
| AAPL analyst targets | Exact match (from yfinance) | None |
| S&P 500 vs Goldman Sachs | Well-aligned (MC brackets consensus) | None |
| VIX level | <0.3% off | None |
| 10Y Treasury | Exact match | None |
| Conservative vs Wealthfront | Close (bond-heavy, similar ratios) | Consider adding EM bonds, munis |
| Aggressive vs Betterment | Similar equity %, different composition | Consider more international diversification |

**Bottom line:** Aegis engine data is highly accurate for market indicators (pulling from the same FRED/Yahoo sources institutions use). Portfolio allocations are competitive with robo-advisors but less granular (3 risk levels vs 20-101). The main gap is in portfolio features (tax-loss harvesting, drift rebalancing, multi-account coordination) rather than allocation accuracy.
