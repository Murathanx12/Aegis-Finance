# Deep Research Findings — Aegis Finance

*Generated: 2026-03-31*

## 1. Current Market Snapshot

| Indicator | Current Value | Source | Date |
|-----------|--------------|--------|------|
| S&P 500 | 6,368.85 | Yahoo Finance / CNBC | 2026-03-28 |
| VIX (CBOE Volatility Index) | 31.05 | FRED VIXCLS / CBOE | 2026-03-28 |
| 10-Year Treasury Yield | 4.42% | CNBC US10Y | 2026-03-28 |
| Federal Funds Rate | 3.50%–3.75% (target range) | Federal Reserve FOMC Statement, March 18 2026 | 2026-03-18 |
| HY Credit Spread (OAS) | 3.17% (317 bps) | FRED BAMLH0A0HYM2 | 2026-03 |
| US GDP Growth (2026E) | ~2.25% (Vanguard), 2.7% (Goldman Sachs) | Vanguard VEMO / Goldman Sachs Research | 2025-12 / 2026-01 |
| S&P 500 EPS (2026E) | ~$306–$309 | Goldman Sachs / Wall Street consensus | 2026-01 |

### Context Notes

- **VIX at 31** is well above the long-run median (~17–19), signaling elevated fear. Aegis config flags VIX > 25 as stress (`vix_stress_threshold: 25`) and applies a graduated risk floor at VIX > 22/25/30.
- **10Y yield at 4.42%** is near 8-month highs (highest since July 2025), driven by Middle East conflict uncertainty, oil/inflation concerns, and a Fed on hold.
- **Fed Funds at 3.50–3.75%** — the FOMC held rates steady for a second consecutive meeting in March 2026. The dot plot projects one more 25bp cut in 2026 and one in 2027, landing at 3.00–3.25% by end-2027.
- **HY OAS at 317 bps** is moderately above its post-pandemic tights (~270–280 bps in late 2024) but well below stress levels (>500 bps). Aegis tracks this via FRED series `BAMLH0A0HYM2`.
- **S&P 500 at 6,369** is roughly 16% below the Wall Street consensus year-end target of ~7,400, reflecting the Q1 2026 selloff driven by geopolitical tensions and tariff uncertainty.

### Sources

- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)
- [CNBC US10Y](https://www.cnbc.com/quotes/US10Y)
- [FRED BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)
- [Fed FOMC Statement March 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260318a.htm)
- [CNBC Fed Decision March 2026](https://www.cnbc.com/2026/03/18/fed-interest-rate-decision-march-2026.html)
- [Vanguard 2026 VEMO](https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/2026-outlook-economic-upside-stock-market-downside.html)

---

## 2. Institutional Forecasts

### 2.1 Short-Term (Year-End 2026 S&P 500 Targets)

| Firm | Year-End 2026 Target | Implied Return from Current (~6,369) | Date Published |
|------|---------------------|--------------------------------------|----------------|
| Oppenheimer | 8,100 | +27.2% | 2025-12 |
| Deutsche Bank | 8,000 | +25.6% | 2025-12 |
| Goldman Sachs | 7,600 | +19.3% | 2025-12 (reaffirmed 2026-01) |
| JPMorgan (revised down) | 7,200 | +13.0% | 2026-03 |
| Bank of America | 7,100 | +11.5% | 2025-12 |
| Stifel (lowest) | 7,000 | +9.9% | 2025-12 |
| **Consensus range** | **7,100–7,800** | **+11.5% to +22.5%** | |

**Key driver:** Earnings growth of ~12.5% YoY (consensus EPS ~$306) plus AI-driven productivity expansion. Goldman cites 12% EPS growth in 2026, 10% in 2027.

**Note:** These short-term targets were set in late 2025 / early 2026 before the Q1 selloff. Current prices (~6,369) are well below where markets were when targets were set (~6,800–7,000 in January 2026). JPMorgan already revised down from 7,500 to 7,200 in March.

### 2.2 Long-Term Capital Market Assumptions (10-Year Annualized, Nominal)

| Firm | US Large Cap Equities (10Y Ann.) | 60/40 Portfolio | Methodology Notes | Source |
|------|----------------------------------|-----------------|-------------------|--------|
| J.P. Morgan (LTCMA 2026) | 6.7% | 6.4% | 30th edition; 200+ assets, 20 currencies; themes: economic nationalism, fiscal activism, AI transformation | [JPM LTCMA](https://am.jpmorgan.com/us/en/asset-management/adv/insights/portfolio-insights/ltcma/) |
| Schwab (2026–2035) | 5.9% | N/A | Based on data through Oct 2025; slightly lower than prior year (6.0%) due to valuations outpacing earnings | [Schwab LTCME](https://www.schwab.com/learn/story/schwabs-long-term-capital-market-expectations) |
| BlackRock (BII) | ~5.0–5.5% | N/A | Down from 6.2% at end-2024; scenario-based including AI upside scenario; updated quarterly | [BlackRock CMA](https://www.blackrock.com/institutions/en-global/institutional-insights/thought-leadership/capital-market-assumptions) |
| Vanguard (VCMM) | 3.5%–5.5% | N/A | Most cautious on US growth stocks (2.3–4.3%); more constructive on value (5.8–7.8%) and international (4.9–6.9%) | [Vanguard VEMO](https://advisors.vanguard.com/insights/article/2026-economic-and-market-outlook) |
| Fidelity | 5.8% (nominal, 20Y) | N/A | 3.2% real; roughly one-third of US stocks' 10% average real return since 2005 | [Morningstar 2026 Edition](https://www.morningstar.com/markets/experts-forecast-stock-bond-returns-2026-edition) |
| AQR | ~4.2% (est.) | 3.4% real (global 60/40) | Compressed risk premia; below long-term US average of ~5% real since 1900 | [AQR 2026 CMA](https://www.aqr.com/Insights/Research/Alternative-Thinking/2026-Capital-Market-Assumptions-for-Major-Asset-Classes) |
| Research Affiliates | ~3.1% (US large cap) | N/A | Most bearish on US large caps; more constructive on small caps (7.1%) and EM | [Morningstar 2026 Edition](https://www.morningstar.com/markets/experts-forecast-stock-bond-returns-2026-edition) |

### 2.3 Consensus Summary

The institutional consensus for **US large cap 10-year annualized nominal returns** clusters around **4.5%–6.7%**, with a median near **5.5%**. The range is wide:

- **Bears (3–4%):** Research Affiliates, AQR, Vanguard low-end — driven by stretched valuations (CAPE > 30), concentration risk in mega-caps, and mean-reversion expectations.
- **Neutral (5–6%):** Schwab, BlackRock, Fidelity — balanced view with earnings growth offset by valuation compression.
- **Bulls (6.5–7%):** J.P. Morgan, Goldman Sachs — driven by AI productivity gains, robust earnings, and sustained margin expansion.

### Sources

- [Goldman Sachs 2026 Outlook](https://www.goldmansachs.com/insights/articles/the-sp-500-expected-to-rally-12-this-year)
- [Goldman Sachs 2026 Outlooks Hub](https://www.goldmansachs.com/insights/outlooks/2026-outlooks)
- [JPM LTCMA Press Release](https://www.prnewswire.com/news-releases/jp-morgan-releases-2026-long-term-capital-market-assumptions-highlighting-resilient-6040-portfolios-and-opportunities-to-enhance-diversification-in-a-new-era-of-economic-nationalism-and-ai-advancement-302589249.html)
- [JPM LTCMA Full Report (PDF)](https://am.jpmorgan.com/content/dam/jpm-am-aem/americas/us/en/institutional/insights/portfolio-insights/ltcma-full-report.pdf)
- [JPMorgan Cuts S&P 500 Target to 7,200 (TheStreet)](https://www.thestreet.com/investing/jpmorgan-resets-sp-500-price-target-for-rest-of-2026)
- [Schwab 2026 LTCME](https://www.schwab.com/learn/story/schwabs-long-term-capital-market-expectations)
- [BlackRock 2026 Investment Outlook](https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications/outlook)
- [Vanguard 2026 Outlook](https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/2026-outlook-economic-upside-stock-market-downside.html)
- [AQR 2026 Capital Market Assumptions](https://www.aqr.com/Insights/Research/Alternative-Thinking/2026-Capital-Market-Assumptions-for-Major-Asset-Classes)
- [Morningstar: Experts Forecast Stock and Bond Returns 2026 Edition](https://www.morningstar.com/markets/experts-forecast-stock-bond-returns-2026-edition)
- [Wall Street 2026 S&P 500 Forecasts (TheStreet)](https://www.thestreet.com/investing/stocks/every-major-wall-street-analysts-sp-500-forecast-for-2026)
- [Wall Street 2026 Outlook (tker.co)](https://www.tker.co/p/wall-street-2026-stock-market-outlook)

---

## 3. Aegis Engine vs Institutional Consensus

### 3.1 What Aegis Currently Assumes

From `backend/config.py`, the Aegis engine hardcodes institutional benchmarks for its Monte Carlo and scenario models:

| Firm (in Aegis config) | Annual Return | Horizon |
|------------------------|---------------|---------|
| Vanguard | 4.7% | 10Y |
| Schwab | 5.9% | 10Y |
| BlackRock | 5.5% | 10Y |
| BNY Mellon | 7.6% | 10Y |
| Morgan Stanley | 6.8% | 10Y |
| Goldman Sachs | 6.5% | 10Y |
| J.P. Morgan | 6.7% | 10Y |
| AQR | 4.2% | 10Y |
| Research Affiliates | 3.5% | 10Y |
| **Computed consensus** | **~5.9% x 1.05 = ~6.2%** | **5Y (adjusted)** |

The `get_institutional_return()` function averages these and applies a 1.05x horizon adjustment (5Y returns expected slightly higher than 10Y due to current cycle positioning), yielding approximately **6.2% annualized** as the institutional consensus anchor.

### 3.2 Alignment Check

| Dimension | Aegis Engine | Institutional Consensus | Assessment |
|-----------|-------------|------------------------|------------|
| **5Y annualized MC return** | Target range: +2% to +8% | 4.5%–6.7% (10Y nominal) | **Well-aligned.** Aegis range brackets the consensus. |
| **Base Case scenario** | 6.0% return, 16% vol | JPM 6.7%, Schwab 5.9%, GS 6.5% | **Good fit.** Matches the neutral-to-bull consensus. |
| **AI Productivity Boom** | 14.0% return, 22% vol, 15% prob | Goldman/JPM cite AI as primary upside driver | **Reasonable.** High return justified by scenario framing. |
| **Recession scenario** | -10.0% return, 30% vol, 6% prob | Not explicitly modeled by most firms | **Conservative probability.** Historical US recession frequency is ~15% per year; 6% may be low given current VIX (31) and geopolitical stress. |
| **Vanguard benchmark** | 4.7% in config | 3.5%–5.5% (actual 2026 range) | **Within range** but could use the midpoint (4.5%) for precision. |
| **BlackRock benchmark** | 5.5% in config | ~5.0–5.5% (updated 2026) | **Aligned.** Slight downward revision in latest data. |
| **Research Affiliates** | 3.5% in config | 3.1% (latest, US large cap) | **Slightly high.** RA has become even more bearish. |
| **Risk-free rate (Fed Funds)** | Used from FRED dynamically | 3.50–3.75% (current) | **Correct.** Aegis fetches live FRED data. |

### 3.3 Gaps and Recommendations

1. **Research Affiliates is staler than reality.** Config has 3.5%; latest published figure is 3.1% for US large cap. Consider updating to 3.1%.

2. **BlackRock has revised down.** Config has 5.5%; latest is closer to 5.0–5.5%. The current value is at the top of the range. Consider 5.2%.

3. **Vanguard range is wide (3.5–5.5%).** Config uses 4.7%, which is reasonable as a midpoint. No change needed.

4. **Recession probability may be too low.** At 6%, the Recession scenario probability is below the NBER historical base rate (~15% in any given year). With VIX at 31, HY spreads at 317 bps, and active geopolitical risk, a 8–10% probability might be more defensible. However, this is a scenario probability for a 5-year horizon (cumulative), not a per-year probability, so the interpretation differs.

5. **VIX at 31 should trigger elevated risk score.** Aegis config has `vix_stress_threshold: 25` and the graduated floor adds +0.8 when VIX > 30. The current market environment (VIX 31, 10Y at 4.42%, HY OAS 317 bps) should produce a composite risk score in the +1.5 to +2.5 range, which is within the "elevated stress" zone. This is working as designed.

6. **Current S&P 500 level (6,369) vs Wall Street targets (7,100–7,800).** The ~15–20% gap between current price and consensus targets suggests either (a) a buying opportunity if fundamentals hold, or (b) targets need to be revised down. JPMorgan already cut from 7,500 to 7,200. Aegis MC simulations starting from current levels should naturally reflect this — the jump-diffusion model with current elevated vol will produce wider confidence intervals.

7. **Missing from Aegis: tariff/trade policy risk.** Multiple institutional forecasts (Vanguard, JPM LTCMA, BlackRock) cite economic nationalism, tariffs, and trade fragmentation as key themes for 2026. Aegis does not have a direct trade policy indicator. The Geopolitical Risk Index (GPRH from FRED) partially captures this, but a tariff-specific factor could improve scenario weighting.

### 3.4 Bottom Line

Aegis engine parameters are **well-calibrated against the 2026 institutional consensus**. The MC 5Y return target of +2% to +8% annualized correctly brackets the institutional range of 3.1% (Research Affiliates, bearish) to 7.6% (BNY Mellon, bullish). The scenario probability distribution (70% positive/neutral, 30% bearish) is reasonable, though the Recession scenario probability (6%) could be bumped slightly given current market stress levels. Minor updates to Research Affiliates (3.5% -> 3.1%) and BlackRock (5.5% -> 5.2%) would improve accuracy but are not urgent.
