# Replay Report v1

**Period:** 2021-01-04 to 2025-12-31
**Generated:** 2026-04-27
**Engine:** Equal-weight fallback (no optimizer), crash overlay active

## SPY Benchmark

| Metric | Value |
|--------|-------|
| Total Return | 99.6% |
| Ann. Return | 14.9% |
| Ann. Volatility | 17.1% |
| Sharpe | 0.64 |
| Max Drawdown | -24.5% |

## Lane Results

| Lane | Total Return | Ann. Return | Ann. Vol | Sharpe | Max DD | Rebalances | Crash Guard | Turnover |
|------|-------------|-------------|----------|--------|--------|------------|-------------|----------|
| conservative | 108.2% | 17.3% | 15.0% | 0.89 | -25.4% | 66 | 0 | 232.6% |
| balanced | 104.8% | 16.9% | 15.2% | 0.85 | -26.5% | 66 | 0 | 233.4% |
| aggressive | 165.1% | 24.2% | 19.5% | 1.04 | -28.1% | 261 | 0 | 440.7% |

## Rebalance Frequency Detail

### Conservative
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 232.65%
- Total cost: 34.3 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Balanced
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 233.40%
- Total cost: 34.1 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Aggressive
- Total rebalances: 261
- Crash guard activations: 0
- Total turnover: 440.71%
- Total cost: 75.2 bps
- Reasons: {'initialization': 1, 'weekly_aggressive': 260}

## Notes

- Uses equal-weight fallback (HRP/BL optimizers not invoked in replay)
- Crash probability override used (no live crash model in replay)
- Transaction costs: 5 bps + 1 bps slippage per trade
- Risk-free rate: 4% (for Sharpe computation)