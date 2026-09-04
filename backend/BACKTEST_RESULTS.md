# Signal Engine Backtest Results

**Regenerated 2026-09-04** (roadmap block B1). Receipt:
`backend/data/optimus/tracker_backtest/signal_engine_backtest_20260904.json`.
Code: `backend/services/backtest.py::backtest_signal_engine` + `evaluate_backtest`.
Licence: `PRODUCT_EXPERIMENT` — this is a direction check on one instrument,
not an alpha claim.

> **WHAT THIS FILE USED TO SAY, AND WHY IT WAS WRONG.**
> The 2026-03-30 version of this file published **"+250.9% strategy vs +740.0%
> buy-and-hold"**. Two independent defects produced it:
> 1. the comparator was **`^GSPC`, the S&P 500 PRICE index** — no dividends,
>    and not an instrument anyone can buy;
> 2. all **66 OVERLAPPING** 3-month forward windows were compounded as if
>    sequential, counting each month ~3 times. Re-derived on the pinned
>    Fama-French daily vintage: compounding all 66 gives **+949.0%**, the
>    every-3rd non-overlapping chain gives **+112.2%**, and the ratio of log
>    returns is **3.123** — the inflation was ~3.1x in log space, ~7.6x in the
>    headline.
>
> The compounding defect was fixed **2026-04-15** (`726c7bf`), but this file was
> never regenerated, so the void figures propagated into nine documents for five
> months. `^GSPC` was retired **2026-09-04**; the service now reads **SPY with
> `auto_adjust=True`**, a dividend- and split-adjusted total return on a
> tradeable fund. Forensic: `docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §3.1.
> Ruler: `learner/benchmark.py`.

Period: eval dates 2020-01-01 → 2025-06-01 (66 monthly signals).
**Realised price span: 2019-12-31 → 2025-09-02** — the first anchor is the last
trading day at or before the first eval date, and each signal carries a 3-month
forward window, so the measured span extends past the last eval date. The old
file quoted the eval-date range as though it were the measured range.
Instrument: SPY total return. Costs: 32.0 bps per round trip.

## Signal Distribution
- Buy: 34 (52%)
- Hold: 27 (41%)
- Sell: 5 (8%)

## Hit Rates
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Buy hit rate (3M) | 76.5% | >60% | PASS |
| Sell hit rate (3M) | 0.0% | >55% | FAIL |

## Average Returns by Signal
| Signal | Avg 3M Return |
|--------|--------------|
| Buy | +3.05% |
| Hold | +3.25% |
| Sell | +13.93% |
| Overall | +3.95% |

The engine's ordering is **inverted** on the tails: the signal it is most
confident about (Sell) precedes the *best* forward quarter in the sample, by a
wide margin, and 0 of 5 sell calls were followed by a negative quarter.

## Strategy vs Buy-and-Hold

Compounded over **22 non-overlapping quarterly windows** (every 3rd monthly
signal), not 66 overlapping ones.

| Metric | Strategy (net) | Strategy (gross) | Buy-and-Hold |
|--------|----------------|------------------|--------------|
| Total Return | **+28.3%** | +31.6% | **+114.8%** |
| Sharpe Ratio | 0.432 | 0.470 | 0.837 |

Execution costs: 23 position changes, 32.0 bps per round trip, 7.36% total
drag; gross − net = 3.29pp.

**Verdict: timing LOSES to holding, and by a wider relative margin than the
void figures implied** — 0.247 of buy-and-hold, versus 0.339 under the old
numbers. The DIRECTION of `NEGATIVE_RESULTS.md` §1 is therefore confirmed on a
correct ruler; only its magnitudes are replaced.

Cross-check on a second, independent ruler: `learner.benchmark`'s hash-gated
pinned Fama-French vintage puts the CRSP value-weighted market total return at
**+96.67%** for a plain 2020-01-02 → 2025-05-30 hold and **+112.2%** over the
every-3rd chain's own span. SPY's +114.8% here is the same object measured on a
tradeable fund — the two rulers agree to ~2.6pp.

### One caveat that must travel with these numbers

The signal distribution itself changed (Buy 43→34, Hold 16→27, Sell 7→5),
because the signal engine reads the same price series it is scored on, and that
series changed from `^GSPC` to SPY-adjusted. **This is not a like-for-like
re-scoring of the same 66 calls**; it is the engine re-run on a total-return
instrument. Both runs are on ONE instrument, so this is a market-timing result
and says nothing about stock selection.

n = 22 independent quarters. Under the `PRODUCT_EXPERIMENT` licence there is no
significance gate, no multiplicity control and one window. A negative of this
size does not need them; a positive would.

## Analysis

### Why Sell Signals Fail
The engine generates sell signals during high-VIX, sharp-drawdown periods (e.g.
March 2020 VIX=57, Oct 2022 VIX=32). These are historically the BEST buying
opportunities due to mean reversion. The sell signal is technically correct
about current risk but wrong about forward returns — and on the regenerated run
it is wrong on **all five** occasions, with a mean forward quarter of +13.93%.

### Why Buy Signals Fail
The buy calls that failed cluster in three places: the calm bull market
immediately before an unpredictable shock (Dec 2019 – Jan 2020), late 2021
ahead of the Fed hiking cycle (a lag in regime detection), and the 2025 tariff
sell-off. The pattern is a regime detector that is accurate about the present
and mistimed about the transition.

### Key Finding
The signal engine has a **structural bias**: it correctly identifies stress but
the mean-reversion component is insufficient to convert "stress detection" into
"buy opportunity" during oversold conditions. On a correct ruler the cost of
that bias is larger than previously reported — the strategy keeps roughly a
quarter of the market's return.

### Recommendation
- The 76.5% buy hit rate is solid, but hit rate is not the objective: a
  76.5%-accurate signal that sits in cash through the best quarters still ends
  at +28.3% against +114.8%. **Terminal wealth is the criterion, not accuracy.**
- The sell signal should be retired or inverted-and-retested, not tuned. Zero
  correct calls out of five, with the largest average forward return of any
  bucket, is not a tuning problem.
- Any future regeneration of this file must go through `learner/benchmark.py`
  and carry its stamp; `backend/tests/test_benchmark_canonical.py` enforces it.

## Reproduce

```bash
# needs network (yfinance SPY + ^VIX)
python -c "from backend.services.backtest import backtest_signal_engine, evaluate_backtest; \
import json; print(json.dumps(evaluate_backtest(backtest_signal_engine()), indent=1))"
```
