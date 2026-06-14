# Replay Report v1

**Period:** 2021-01-04 to 2025-12-31
**Generated:** 2026-06-06
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
| conservative | 130.3% | 18.3% | 14.7% | 0.97 | -24.6% | 66 | 0 | 239.0% |
| balanced | 125.7% | 17.8% | 14.9% | 0.93 | -25.6% | 66 | 0 | 240.0% |
| aggressive | 172.5% | 22.4% | 19.2% | 0.95 | -29.2% | 261 | 0 | 481.6% |

## Rebalance Frequency Detail

### Conservative
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 238.99%
- Total cost: 36.8 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Balanced
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 240.02%
- Total cost: 36.5 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Aggressive
- Total rebalances: 261
- Crash guard activations: 0
- Total turnover: 481.63%
- Total cost: 78.3 bps
- Reasons: {'initialization': 1, 'weekly_aggressive': 260}

## Notes

- Uses equal-weight fallback (HRP/BL optimizers not invoked in replay)
- Crash probability override used (no live crash model in replay)
- Transaction costs: 5 bps + 1 bps slippage per trade
- Risk-free rate: 4% (for Sharpe computation)