# Stress Test Results — Aegis Finance

*Generated: 2026-03-31*

## Stock Analysis (30 Tickers)

All 30 stocks analyzed successfully via `stock_analyzer.analyze_stock()`. Each ticker runs a fundamental-aware Monte Carlo simulation (3,000 paths, 1,260 trading days / 5 years) with jump-diffusion, Merton compensator, and CAGR caps by market-cap tier.

| Ticker | Sector | Price | Cap Tier | 5Y Return | Median Ret | Sharpe | P(Loss) | MaxDD | Vol |
|--------|--------|------:|----------|----------:|-----------:|-------:|--------:|------:|----:|
| AAPL | Technology | $246.63 | mega | 114.0% | 90.1% | 0.39 | 16.3% | -45.3% | 27.4% |
| MSFT | Technology | $358.96 | mega | 92.3% | 68.5% | 0.29 | 20.4% | -45.4% | 26.2% |
| GOOGL | Communication Services | $273.50 | mega | 119.3% | 97.8% | 0.36 | 17.5% | -49.2% | 30.8% |
| NVDA | Technology | $165.17 | mega | 112.1% | 80.9% | 0.21 | 30.8% | -68.8% | 51.7% |
| META | Communication Services | $536.38 | mega | 109.5% | 79.8% | 0.21 | 28.4% | -63.2% | 43.7% |
| JPM | Financial Services | $283.77 | mega | 119.0% | 97.2% | 0.45 | 11.9% | -40.2% | 24.3% |
| GS | Financial Services | $807.60 | mega | 115.7% | 96.6% | 0.40 | 16.2% | -45.6% | 27.6% |
| BAC | Financial Services | $47.23 | mega | 79.7% | 53.5% | 0.22 | 25.3% | -47.7% | 26.8% |
| BRK-B | Financial Services | $474.66 | mega | 83.6% | 68.8% | 0.44 | 12.0% | -31.3% | 17.2% |
| JNJ | Healthcare | $242.49 | mega | 40.5% | 28.4% | 0.13 | 27.8% | -34.4% | 16.7% |
| UNH | Healthcare | $261.79 | mega | 69.3% | 39.8% | 0.14 | 32.4% | -54.5% | 31.2% |
| LLY | Healthcare | $886.63 | mega | 116.3% | 95.8% | 0.34 | 19.5% | -51.4% | 32.1% |
| PFE | Healthcare | $27.77 | large | 34.2% | 13.6% | 0.01 | 41.1% | -50.6% | 25.5% |
| XOM | Energy | $171.47 | mega | 43.9% | 21.5% | 0.06 | 38.3% | -51.0% | 26.5% |
| CVX | Energy | $210.71 | mega | 53.6% | 31.6% | 0.12 | 32.7% | -47.3% | 25.0% |
| SLB | Energy | $51.53 | large | 97.2% | 66.0% | 0.21 | 29.6% | -59.5% | 38.2% |
| COST | Consumer Defensive | $996.58 | mega | 90.1% | 69.7% | 0.35 | 17.2% | -40.0% | 22.5% |
| WMT | Consumer Defensive | $123.50 | mega | 100.3% | 82.2% | 0.43 | 12.5% | -36.7% | 21.1% |
| MCD | Consumer Cyclical | $308.53 | mega | 70.7% | 57.7% | 0.35 | 13.2% | -31.8% | 17.1% |
| SBUX | Consumer Cyclical | $86.72 | large | 74.6% | 46.9% | 0.16 | 31.3% | -54.2% | 31.3% |
| TSLA | Consumer Cyclical | $355.28 | mega | 90.3% | 44.8% | 0.13 | 39.7% | -74.2% | 59.1% |
| CAT | Industrials | $667.43 | mega | 102.4% | 76.8% | 0.31 | 20.6% | -49.3% | 29.7% |
| GE | Industrials | $273.25 | mega | 120.2% | 100.6% | 0.36 | 18.2% | -48.6% | 30.3% |
| RTX | Industrials | $187.15 | mega | 118.5% | 99.1% | 0.47 | 11.7% | -39.2% | 23.5% |
| BA | Industrials | $189.21 | large | 91.5% | 57.4% | 0.19 | 31.3% | -58.0% | 36.1% |
| NEE | Utilities | $92.05 | large | 43.4% | 20.6% | 0.03 | 39.2% | -51.1% | 26.5% |
| DUK | Utilities | $131.71 | large | 55.9% | 43.0% | 0.23 | 20.8% | -34.5% | 17.8% |
| PLD | Real Estate | $128.78 | large | 62.9% | 36.2% | 0.15 | 31.3% | -49.3% | 26.8% |
| AMT | Real Estate | $170.36 | large | 84.0% | 59.9% | 0.27 | 23.1% | -46.2% | 26.0% |
| PLTR | Technology | $137.55 | mega | 108.3% | 74.6% | 0.17 | 35.6% | -75.8% | 65.5% |

### Anomalies Detected

1. **PLTR MaxDD -75.8% and Vol 65.5%** — Highest volatility and second-worst max drawdown in the set. Consistent with PLTR's historical behavior (speculative tech, high beta 1.74). The 5Y expected return of 108% is plausible given the drift cap at 15% CAGR and high vol creating fat right tails, but the 35.6% P(Loss) is notable for a growth stock. **Verdict: plausible but extreme.**

2. **TSLA MaxDD -74.2% and Vol 59.1%** — Similar to PLTR. Tesla's beta of 1.93 and historical volatility justify this. The mean-median gap (90.3% vs 44.8%) reveals heavy right-skew — most paths underperform the mean. 39.7% P(Loss) is high. **Verdict: plausible, reflects true tail risk.**

3. **PFE Sharpe 0.01** — Near-zero Sharpe for a large-cap pharma stock. Historical drift was -0.33% (negative), and the capped drift of 4.2% barely exceeds the 4% risk-free rate. P(Loss) at 41.1% is the highest in the set. **Verdict: correct — PFE has been in a multi-year decline since COVID peak.**

4. **NEE Sharpe 0.03** — Near-zero risk-adjusted return for a utility. Historical drift of 6.6% was capped to 4.9%, barely above risk-free. 39.2% P(Loss). **Verdict: correct — NEE has underperformed since 2022 rate hikes.**

5. **XOM Sharpe 0.06, P(Loss) 38.3%** — Despite strong recent performance, the mega-cap CAGR cap limits drift to 5.5%. The model correctly penalizes energy's mean-reversion tendency. **Verdict: defensible — CAGR caps may be slightly aggressive for current energy regime.**

6. **GE 5Y Return 120.2% (highest)** — Drift capped at 15% (mega-cap max). Historical drift was 29.2% due to post-spinoff rally. The model correctly caps this but the 120% total return is at the high end. **Verdict: reasonable — cap is working as intended.**

7. **UNH hist_drift -5.3% but capped_drift 8.4%** — Historical drift is negative (recent drawdown from healthcare policy headwinds), but CAGR floor of 2% (mega: 0.04 * 0.5 = 0.02 minimum) plus analyst blend pushed it to 8.4%. **Verdict: correct behavior — floor prevents unreasonably bearish projection from temporary drawdown.**

8. **All mega-cap stocks hit 15% CAGR ceiling** — GOOGL, NVDA, GS, LLY, GE, RTX, PLTR all had historical drifts well above 15% but were capped. This is by design but worth noting: the cap compresses differentiation among high-momentum mega-caps.

### No Critical Anomalies

- No negative expected returns (all > 34%)
- No impossibly high returns (all < 121%, well under 300% cap)
- No negative Sharpe ratios
- All P(Loss) values in 11.7%–41.1% range (reasonable for 5Y horizon)
- All MaxDD values in -31.3% to -75.8% range (plausible)
- Volatility range 16.7% to 65.5% (reflects true cross-section dispersion)

### Summary Statistics

| Metric | Mean | Median | Min | Max | Std Dev |
|--------|-----:|-------:|----:|----:|--------:|
| 5Y Expected Return | 88.7% | 91.0% | 34.2% | 120.2% | 26.1% |
| 5Y Median Return | 62.2% | 63.0% | 13.6% | 100.6% | 25.9% |
| Sharpe Ratio | 0.24 | 0.22 | 0.01 | 0.47 | 0.13 |
| P(Loss) 5Y | 25.3% | 25.3% | 11.7% | 41.1% | 9.4% |
| Avg Max Drawdown | -49.5% | -49.3% | -75.8% | -31.3% | 12.0% |
| Annualized Volatility | 29.5% | 26.7% | 16.7% | 65.5% | 11.5% |

### Observations

1. **Mean-median gap reveals right-skew**: The mean 5Y return (88.7%) exceeds the median (62.2%) by 26.5 percentage points. This is expected from log-normal Monte Carlo — the right tail (positive surprises) pulls the mean above the median. For high-vol stocks like PLTR and TSLA, the gap is extreme (34% and 46% respectively).

2. **Sharpe clustering**: 24 of 30 stocks have Sharpe between 0.10 and 0.45. The compression comes from CAGR caps limiting the numerator while volatility varies freely. Top Sharpe stocks (RTX 0.47, JPM 0.45, BRK-B 0.44, WMT 0.43) are all low-vol, high-drift names — correct behavior.

3. **Sector patterns are coherent**:
   - Technology: High returns, high vol, moderate Sharpe
   - Financials: JPM/GS/BRK-B show strong risk-adjusted returns
   - Energy: Lower Sharpe due to CAGR caps on recent performance
   - Healthcare: Wide dispersion (LLY 116% vs PFE 34%) — correct
   - Utilities: Lowest returns and Sharpe — correct for defensive sector

4. **CAGR cap compression**: 7 of 30 stocks hit the mega-cap 15% ceiling. This is a design trade-off: prevents unrealistic extrapolation of recent momentum but compresses differentiation among momentum leaders. Consider whether the 15% cap should be revisited or whether analyst target blending (40% weight) provides sufficient differentiation.

5. **Runtime performance**: Average 5.9 seconds per ticker (total ~3 minutes for 30 stocks). Dominated by Yahoo Finance API calls, not Monte Carlo computation. Suitable for on-demand analysis but too slow for batch screener without caching.

### Test Configuration

- Monte Carlo paths: 3,000 per stock
- Forecast horizon: 1,260 trading days (5 years)
- Risk-free rate: 4%
- Jump frequency: 7% annual
- Jump mean: -10%, Jump std: 5%
- CAGR caps: mega (4%-15%), large (5%-20%)
- Analyst target blend: 60% capped historical / 40% analyst
- Max 5Y return cap: 300%
