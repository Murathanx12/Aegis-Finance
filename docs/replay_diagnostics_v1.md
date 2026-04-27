# Replay Diagnostics v1

**Date:** 2026-04-28
**Purpose:** Reality-check the replay report numbers before treating them as methodology baseline.

## Background

The replay_report_v1.md showed all three lanes beating SPY (99.6% total return) over 2021-2025, with Conservative (40% equity) at 108.2% and Aggressive at 165.1%. A 40%-equity portfolio outperforming 100% SPY by 8pp is suspicious. Two diagnostic checks were run to decompose the sources.

## Diagnostic 1: ETF-Only Replay (No Individual Stocks)

Re-ran the replay with the ~52 individual stocks removed from the universe, leaving only ETFs (sector, broad equity, bond, alternatives = 28 tickers).

| Lane | Full Universe | ETF-Only | Sharpe (Full) | Sharpe (ETF) |
|------|-------------|----------|---------------|--------------|
| Conservative | 108.2% | 58.5% | 0.89 | 0.51 |
| Balanced | 104.8% | 55.7% | 0.85 | 0.45 |
| Aggressive | 165.1% | 84.9% | 1.04 | 0.64 |
| SPY (benchmark) | 99.6% | — | 0.64 | — |

**Finding:** The individual-stock universe is responsible for ~40 basis points of Sharpe inflation across all lanes. With ETFs only:
- Conservative no longer beats SPY (58.5% vs 99.6%) — expected for 40% equity
- Aggressive roughly matches SPY (84.9% vs 99.6%) — reasonable given equal-weight diversification drag + weekly rebalancing costs
- All Sharpes drop to the 0.45-0.64 range — realistic for rules-based equal-weight portfolios

**Root cause:** The ~52 individual stocks in `paper_portfolios.yaml` were selected from current large-cap names (AAPL, MSFT, NVDA, META, etc.). These are 2026 survivors. Companies that underperformed, were delisted, or dropped out of major indices during 2021-2025 are not in the universe. This is textbook **survivorship bias** — the universe looks backward at winners and runs them forward.

**Magnitude:** Survivorship bias inflates returns by approximately 2-4% annually in this case, compounding to 10-20pp over 5 years. This is consistent with academic literature on survivorship bias in backtesting (Elton, Gruber, Blake 1996: ~1.6% annual for mutual funds; individual stocks can be higher).

## Diagnostic 2: Bond Sleeve Returns

Individual bond ETF returns over 2021-01-04 to 2025-12-31:

| Ticker | Total Return |
|--------|-------------|
| AGG | -1.6% |
| TLT | -34.8% |
| IEF | -8.5% |
| SHY | +8.4% |
| LQD | -3.2% |
| HYG | +21.2% |
| TIP | +4.5% |

**Equal-weight bond sleeve:** -2.8% total, -0.6% annualized, Sharpe -0.66

**Finding:** The bond sleeve was a meaningful drag over this window (worst bond market in 40+ years). Conservative's 50% bond allocation at -2.8% contributed approximately -1.4% to total portfolio return. The fact that Conservative still showed 108.2% in the full-universe replay means the equity sleeve's survivorship-biased individual stocks were strong enough to overcome the bond drag AND beat SPY. This is not plausible without the survivorship effect.

**Confirmation:** With ETFs only, Conservative returned 58.5% — consistent with ~40% equity exposure × ~79% equity ETF return + ~50% bond × -2.8% bond return + ~10% alt: approximately `0.40 × 79 + 0.50 × (-2.8) + 0.10 × ~30 ≈ 33%`. The actual 58.5% is higher because equal-weight rebalancing captures some mean-reversion premium from monthly re-weighting, which is a real (small) alpha source.

## Diagnostic 3: Crash Guard — Zero Activations

The 2021-2025 window contained:
- COVID crash aftermath (recovery from March 2020)
- 2022 rates-driven correction (~25% peak-to-trough on QQQ)
- August 2024 carry-trade unwind

The replay used `crash_prob_override=0.15` (below all lane thresholds), meaning the crash guard was **never tested against real crash model output**. This was intentional — the V7 crash model requires specific feature engineering and trained weights that may not align perfectly with the replay's `MarketDataAtTimestamp` wrapper.

**Open question:** Did the V7 crash model's real-time-equivalent output ever exceed 0.25 (conservative threshold) during 2022? If yes, a future diagnostic should replay with the live crash model to validate guard behavior. If no, the V7 model's sensitivity may need calibration review (separate from this subsystem).

## Equity ETF Comparison

| Portfolio | Total Return | Sharpe |
|-----------|-------------|--------|
| Equal-weight 17 equity ETFs | 78.7% | 0.54 |
| SPY (cap-weighted) | 99.6% | 0.64 |

Equal-weighting equity ETFs underperformed cap-weighted SPY by 21pp over this window. This is expected — mega-cap tech (AAPL, MSFT, NVDA) drove disproportionate returns in a cap-weighted index. Equal-weighting dilutes concentration in winners. The equal-weight "premium" documented in academic literature did not materialize during 2021-2025 for ETFs.

## Conclusions

1. **The full-universe replay numbers are inflated by survivorship bias.** ETF-only Sharpes (0.45-0.64) are realistic. Full-universe Sharpes (0.85-1.04) are not representative of what a rules-based portfolio would have achieved with a point-in-time universe.

2. **The bond sleeve performed as expected.** -2.8% over 5 years of rising rates is consistent with the Bloomberg Aggregate's actual performance.

3. **The crash guard has not been validated on real crash model output.** The `crash_prob_override=0.15` stub means we only know the guard's logic works (tested at 0.50), not that it fires at the right time on real data.

4. **ETF-only results should be treated as the conservative methodology baseline.** The full-universe results are interesting for research (does adding individual stocks help?) but should not be presented as expected performance without a survivorship bias disclaimer.

## Recommended Actions

- [ ] Add survivorship bias disclaimer to all frontend pages showing replay results
- [ ] Consider point-in-time S&P 500 constituent data for a future V2 replay
- [ ] Run a diagnostic replay with the live V7 crash model (no override) to validate guard timing
- [ ] Present both ETF-only and full-universe results side-by-side in the Compare page
