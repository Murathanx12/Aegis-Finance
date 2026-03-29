# Aegis Finance — Technical Methodology

> Research paper foundation: quantitative methods, statistical models, and validation framework.

## 1. Crash Probability Estimation

### 1.1 Problem Formulation

We define a **market crash** as a peak-to-trough drawdown of 20% or more in the S&P 500 index within a given time horizon *h* (3, 6, or 12 months). The target variable is binary:

```
y_t(h) = 1 if max_drawdown(t, t+h) >= 0.20, else 0
```

### 1.2 Feature Engineering

Starting from 208 candidate features, we apply LASSO (L1-regularized logistic regression) with cross-validated lambda to select 25-30 features. Categories include:

| Category | Examples | Count |
|----------|---------|-------|
| Price momentum | SMA ratios (50/200), RSI, drawdown from ATH | ~15 |
| Volatility regime | Realized vol, VIX/VIX3M term structure, GARCH sigma | ~10 |
| Fixed income | Yield curve slope (10Y-3M), credit spreads (HY OAS, IG OAS) | ~8 |
| Macro indicators | Unemployment z-score, CPI momentum, consumer sentiment | ~12 |
| Leading indicators | Initial claims (ICSA), NFCI, LEI | ~5 |
| Tail risk | SKEW index, put/call implied vol ratio | ~3 |
| Cross-asset | Gold/equity ratio, small-cap divergence (Russell/S&P) | ~4 |

Feature matrix construction handles missing data by forward-filling (FRED series have different frequencies) and applying rolling z-scores with a 252-day window for stationarity.

### 1.3 Models

**LightGBM** — Gradient-boosted decision trees with the following hyperparameters:
- `n_estimators`: 500 (early stopping with 50-round patience)
- `max_depth`: 5 (prevents overfitting on rare crash events)
- `learning_rate`: 0.05
- `subsample`: 0.8, `colsample_bytree`: 0.8
- `scale_pos_weight`: auto (compensates for class imbalance ~8:1)

**Logistic Regression** — L2-regularized logistic regression as a calibrated baseline:
- `C`: cross-validated
- `class_weight`: balanced

Both models output calibrated probabilities via Platt scaling. The final prediction is the model with better held-out Brier score (typically LightGBM for 3-month, Logistic for 12-month).

### 1.4 Validation Protocol

**Walk-forward expanding window** (no data leakage):
- Training: 1990 to *t*
- Test: *t + purge_gap* to *t + purge_gap + 252*
- Purge gaps: 70 days (3m), 140 days (6m), 265 days (12m)
- Re-train every 252 days starting from 2000

**Metrics:**
- Brier Score (lower is better): target ≤ 0.05 for 3-month horizon
- Brier Skill Score (BSS) vs climatology: measures improvement over always-predict-base-rate
- Reliability diagram: calibration of predicted probabilities

### 1.5 Explainability

SHAP (SHapley Additive exPlanations) TreeExplainer computes per-feature contributions for every prediction. The top 10 features by absolute SHAP value are displayed, showing whether each feature pushes crash probability up (red) or down (green).

## 2. Monte Carlo Simulation

### 2.1 Jump-Diffusion Process (Merton 1976)

The S&P 500 price follows:

```
dS/S = (μ - λk) dt + σ dW + J dN
```

Where:
- `μ` = drift (anchored to institutional consensus ~5.9% nominal)
- `σ` = volatility (GARCH-calibrated)
- `λ` = jump arrival rate (~7%/year, Poisson)
- `k` = E[J] = exp(μ_J + 0.5σ_J²) - 1 (mean jump size, default -10%)
- `J` = jump size ~ LogNormal(μ_J, σ_J)
- `N` = Poisson counting process
- `W` = Brownian motion

**Critical: Merton compensator.** The `-λk` term in drift ensures E[S(T)] = S(0)·exp(μT) regardless of jump parameters. Without this term, jumps systematically bias returns downward by 1.4-2.7% annually.

### 2.2 Volatility Dynamics

Stochastic volatility follows an Ornstein-Uhlenbeck process:

```
dσ = κ(ξ - σ) dt + η dZ
```

Where:
- `ξ` = long-run volatility (calibrated from GJR-GARCH(1,1))
- `κ` = mean-reversion speed
- `η` = vol-of-vol
- `ρ` = correlation between `dW` and `dZ` (leverage effect, typically -0.7 to -0.9)

### 2.3 GJR-GARCH(1,1)

Calibrates volatility parameters from historical data:

```
σ²_t = ω + (α + γ·I_{ε<0})·ε²_{t-1} + β·σ²_{t-1}
```

The asymmetric term `γ` captures the leverage effect (negative returns increase volatility more than positive returns of equal magnitude). Persistence = α + β + γ/2 must be < 1 for stationarity.

### 2.4 Hidden Markov Model (3-State)

A 3-state Gaussian HMM classifies the market into regimes:
- **State 0 (Bull):** High mean return, low volatility
- **State 1 (Neutral):** Moderate return, moderate volatility
- **State 2 (Bear/Volatile):** Low/negative return, high volatility

HMM regime probabilities blend into the Monte Carlo drift and volatility with a mixing weight of 0.15 (configurable).

### 2.5 Scenario Framework

Seven macro scenarios with regime-adjusted weights:

| Scenario | Base Weight | Return | Volatility |
|----------|-----------|--------|-----------|
| Base Case | 42% | 6% | 16% |
| AI Productivity Boom | 15% | 14% | 22% |
| Soft Landing | 13% | 4% | 14% |
| Market Correction | 12% | -2% | 24% |
| Stagflation | 8% | -4% | 23% |
| Recession | 6% | -10% | 30% |
| Geopolitical Crisis | 4% | -15% | 35% |

Scenario weights adjust at runtime based on current VIX, yield curve slope, and ML crash probability.

### 2.6 Block Bootstrap

Residuals are resampled in blocks of 21 trading days (~1 month) to preserve volatility clustering and serial correlation patterns.

### 2.7 Mean Reversion

When simulated prices deviate significantly from fair value (based on institutional consensus), a mean-reversion force is applied:
- Below fair value by 20%+: positive drift boost (0.08 annualized)
- Above fair value by 30%+: negative drift drag (0.04 annualized)

## 3. Risk Scoring

### 3.1 Composite Risk Score

A 9-factor z-score weighted by empirical importance:

| Factor | Weight | Signal |
|--------|--------|--------|
| VIX level | 2.0 | Elevated implied volatility |
| Yield curve slope | 1.8 | Inversion predicts recession |
| Credit spread (HY OAS) | 1.9 | Widening = credit stress |
| Long-term yield volatility | 1.0 | Uncertainty in rate expectations |
| Momentum exhaustion | 1.5 | Overbought/oversold RSI |
| Short-term realized vol | 1.3 | Recent turbulence |
| Gold/stock ratio | 1.2 | Flight to safety |
| Market breadth | 1.0 | Narrow leadership |
| Small-cap divergence | 1.1 | Risk appetite indicator |

Each indicator is converted to a rolling z-score (252-day window), then weighted and summed. Range: approximately [-4, +4], where > 2.0 indicates elevated stress.

### 3.2 Regime Detection

Rule-based classification using VIX thresholds and risk score:
- **Bull:** VIX < 16, risk score < -0.5, positive 12-month returns > 8%
- **Neutral:** Default state
- **Bear:** Negative 12-month returns < -5%, risk score > 1.5
- **Volatile:** VIX > 25, risk score > 1.5

Validated by multi-check confirmation: 200-day SMA trend, market breadth, institutional consensus alignment.

## 4. External Validation

### 4.1 Cross-Check Framework

The crash model's output is independently validated against:
- **Leading Economic Index (LEI):** 3-month rate of change direction
- **Senior Loan Officer Survey (SLOOS):** Credit tightening trend
- **Fed Funds trajectory:** Tightening vs easing cycle
- **Consumer Sentiment:** Level and momentum

Each signal is classified as bullish, neutral, or bearish. The consensus direction is computed, and agreement with the crash model is measured as a percentage.

### 4.2 Divergence Alerts

When the crash model diverges significantly from external consensus, divergence alerts are generated to flag potential model overconfidence or missed signals.

## 5. Sector Analysis

Factor model projections for 11 S&P 500 sectors:
- **Beta adjustment:** Sector return = market return × sector beta
- **Momentum factor:** 6-month and 12-month momentum contribute ±20% to expected return
- **Volatility penalty:** Higher-vol sectors are penalized in risk-adjusted ranking
- **Mean reversion:** Sectors with extreme recent performance revert toward long-run averages

Each sector is simulated with 5,000 Monte Carlo paths using sector-specific parameters.

## 6. Portfolio Analytics

### 6.1 Metrics
- **VaR (95%):** Daily value at risk — the loss threshold exceeded only 5% of trading days
- **CVaR (95%):** Conditional VaR — average loss in the worst 5% of days
- **Sharpe Ratio:** (Return - Risk-free rate) / Volatility, annualized
- **Max Drawdown:** Largest peak-to-trough decline in the historical period

### 6.2 Stress Testing
Portfolio impact estimated under historical crisis scenarios (2008, 2020, 2022, 1987) using beta-adjusted drawdowns per holding.

## 7. Data Pipeline

### 7.1 Thread Safety
Yahoo Finance (yfinance) is not thread-safe. All yfinance calls are serialized through a global threading lock to prevent DataFrame corruption under concurrent FastAPI requests.

### 7.2 Caching Strategy
- Stock data: 15-minute TTL
- Market-level data: 5-minute TTL
- Sector analysis: 1-hour TTL
- Simulation results: 1-hour TTL
- Macro indicators: 5-minute TTL

### 7.3 Data Quality
Automated checks on every data fetch:
- **Staleness:** Alert if data is older than 3 business days
- **Range validation:** Flag S&P 500 daily returns > 10%, VIX outside [5, 90]
- **Completeness:** Alert if NaN percentage exceeds 20%

## 8. Known Limitations

1. **Survivorship bias:** Only currently-listed stocks are analyzed
2. **Single market:** US equities and macro only
3. **Data frequency:** Hourly prices, monthly FRED — not suitable for intraday analysis
4. **Regime detection lag:** Rule-based regime classification can lag true regime transitions by weeks
5. **Crash rarity:** With ~4 crashes per century, the training sample is inherently small
6. **No execution:** Educational analysis only — no position sizing, order routing, or live trading
7. **yfinance dependency:** Free but rate-limited; some tickers may fail transiently

## References

- Merton, R.C. (1976). "Option pricing when underlying stock returns are discontinuous." *Journal of Financial Economics*, 3(1-2), 125-144.
- Glosten, L.R., Jagannathan, R., & Runkle, D.E. (1993). "On the Relation between the Expected Value and the Volatility of the Nominal Excess Return on Stocks." *Journal of Finance*, 48(5), 1779-1801.
- Lundberg, S.M. & Lee, S.I. (2017). "A Unified Approach to Interpreting Model Predictions." *NeurIPS*.
- Ke, G., Meng, Q., Finley, T., et al. (2017). "LightGBM: A Highly Efficient Gradient Boosting Decision Tree." *NeurIPS*.
