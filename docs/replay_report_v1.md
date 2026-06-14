# Replay Report v1

**Period:** 2021-01-04 to 2025-12-31
**Generated:** 2026-06-14
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
| conservative | 75.0% | 11.9% | 10.9% | 0.73 | -17.6% | 66 | 0 | 373.4% |
| balanced | 68.8% | 11.1% | 10.9% | 0.65 | -18.3% | 66 | 0 | 390.1% |
| aggressive | 91.2% | 13.9% | 13.6% | 0.73 | -19.7% | 261 | 0 | 1204.0% |

## Rebalance Frequency Detail

### Conservative
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 373.40%
- Total cost: 56.9 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Balanced
- Total rebalances: 66
- Crash guard activations: 0
- Total turnover: 390.07%
- Total cost: 58.5 bps
- Reasons: {'initialization': 1, 'monthly': 65}

### Aggressive
- Total rebalances: 261
- Crash guard activations: 0
- Total turnover: 1204.00%
- Total cost: 200.6 bps
- Reasons: {'initialization': 1, 'weekly_aggressive': 260}

## Notes

- Uses equal-weight fallback (HRP/BL optimizers not invoked in replay)
- Crash probability override used (no live crash model in replay)
- Transaction costs: 5 bps + 1 bps slippage per trade
- Risk-free rate: 4% (for Sharpe computation)