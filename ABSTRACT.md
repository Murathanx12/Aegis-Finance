# Aegis Finance — Project Abstract

## Motivation

Retail investors lack access to the quantitative tools that institutional firms use daily — regime detection, Monte Carlo simulation, crash probability models, and macro risk scoring. Commercial platforms charge $100-500/month for watered-down versions. Aegis Finance makes these tools free and open-source, with full transparency into how every prediction is made.

## What It Does

Aegis Finance is a web-based market intelligence platform that combines:

1. **Crash Probability Estimation** — A LightGBM model trained on 25+ macroeconomic and market features predicts the probability of a 20%+ S&P 500 drawdown over 3, 6, and 12-month horizons. Every prediction includes SHAP feature importance so users understand *why* the model flags risk.

2. **Monte Carlo Stock Projections** — Jump-diffusion simulation (Merton 1976) with regime-aware drift, GARCH-calibrated volatility, and institutional consensus anchoring. Produces probability distributions (p5/p25/p50/p75/p95) for any ticker over 1-month to 5-year horizons.

3. **Macro Risk Dashboard** — A 9-factor composite risk score combining VIX, yield curve, credit spreads, momentum exhaustion, market breadth, and more. Real-time regime classification (Bull/Neutral/Bear/Volatile) using rule-based detection backed by a 3-state Hidden Markov Model.

4. **Sector Analysis** — Factor model projections for all 11 S&P 500 sectors using beta, momentum, mean reversion, and volatility regime adjustments. Ranked by risk-adjusted expected return.

5. **Portfolio Builder** — Goal-based portfolio construction that takes user risk tolerance and time horizon, then allocates across sectors and individual stocks using the engine's projections.

## Methodology

### Data Sources
- **Market Data:** Yahoo Finance — S&P 500, VIX, Treasury yields (3M/10Y/30Y), credit spreads (HYG/LQD), gold, NASDAQ, Russell 2000, 11 sector ETFs
- **Macro Data:** Federal Reserve (FRED) — 22+ series including yield curve slope, unemployment, CPI, consumer sentiment, high-yield OAS, initial jobless claims, NFCI financial conditions index, LEI, SLOOS lending surveys

### ML Pipeline
- **Models:** LightGBM (gradient boosting) + Logistic Regression with automatic model selection based on held-out Brier score
- **Features:** 25-30 selected via LASSO from a pool of 208 candidates (price momentum, volatility regimes, fixed income signals, tail risk metrics, FRED macro indicators)
- **Calibration:** Platt scaling for probability calibration
- **Validation:** Walk-forward expanding-window backtest (2000-present, zero data leakage, purge gaps between train/test)

### Monte Carlo Simulation
- **Process:** Geometric Brownian Motion with Merton jump-diffusion, Ornstein-Uhlenbeck stochastic volatility, block bootstrap residuals, and mean reversion
- **Key correction:** Drift compensator (`-λk` term) ensures E[S(T)] = S(0)·exp(μT) regardless of jump parameters — missing this term causes systematic bearish bias of 1.4-2.7% annually
- **Anchoring:** Drift anchored to institutional consensus (~5.9% nominal, blended from 9 major firms) rather than pure historical returns

### Scenario Framework
Eight macro scenarios with dynamically adjusted probabilities:
- Base Case (35%), AI Productivity Boom (15%), Soft Landing (15%), Market Correction (10%), Stagflation (7%), Recession (7%), AI Bubble Collapse (6%), Geopolitical Crisis (5%)
- Weights shift at runtime based on current regime, VIX, yield curve, and ML crash probability

## What Was Learned (from V7 Research)

The V7 engine (5-model ensemble, standalone Python) revealed:
- **3-month crash prediction shows measurable skill** (Brier 0.046 vs 0.12 climatology)
- **12-month crash prediction shows no improvement** over always-predict-base-rate (BSS -0.39)
- **Lagging indicators dominate SHAP** — unemployment z-score was the top feature, but unemployment peaks *after* recessions start. Leading indicators (initial claims, NFCI, yield curve dynamics) are more useful for forward-looking predictions.
- **Ensemble complexity didn't help:** LightGBM alone performed comparably to the 5-model meta-stacker ensemble for 3-month predictions. The additional models (LSTM, TCN, XGBoost, Cox) added training time without meaningful accuracy improvement.

## Limitations

- **Not financial advice.** This is an educational tool that shows *how* quantitative analysis works, not *what* to buy.
- **Crash prediction is inherently hard.** Crashes are rare, non-stationary events. No model can reliably predict them — Aegis shows probabilities, not certainties.
- **Data latency.** Market data refreshes hourly. FRED macro data updates monthly. This is analysis, not real-time trading.
- **Single-market focus.** S&P 500 and US macro only. No international, bond, commodity, or crypto forecasting.
- **No execution layer.** No position sizing, no order routing, no live trading integration.

## Technology

| Component | Choice | Why |
|-----------|--------|-----|
| Frontend | Next.js 14 + shadcn/ui + Recharts | Modern React, great DX, free Vercel hosting |
| Backend | FastAPI | Async Python, automatic OpenAPI docs, fast |
| ML | LightGBM | Best accuracy-to-speed ratio for tabular data |
| Simulation | Jump-diffusion MC | Captures fat tails + sudden crashes + mean reversion |
| Data | yfinance + FRED | Free, reliable, institutional-quality macro |
| Deploy | Vercel + Railway | Free/cheap, git-push deploys |
