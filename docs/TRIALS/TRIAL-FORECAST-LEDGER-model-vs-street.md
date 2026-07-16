# TRIAL-FORECAST-LEDGER — Model vs Street forecast-error ledger

**Pre-registered:** 2026-07-16 (this commit) · **Purpose:** measurement (calibration), not a trading signal · **Status:** 🕐 ACCRUING (forward-only)

## Hypothesis (falsifiable, honest prior)

Over matured 12-month windows, the engine's Monte-Carlo-implied 1-year median
return forecast has **absolute error no worse than the Wall Street consensus
price-target-implied return** for the same stock on the same date
(MAE_model ≤ MAE_street), with **smaller optimistic bias**
(|mean signed error| smaller). Honest prior: the literature says street
12-month targets carry a large systematic optimistic bias; our MC bakes in
crash risk and caps drift, so we expect to win on bias and roughly tie on MAE.
Losing on MAE is a fully plausible outcome and will be published either way.

## What accrues (frozen)

Weekly PIT snapshots via the generic `collect_pit_scores` engine,
key `fcast:model1y:{ticker}`, one row per screener ticker per collection:

- **value** = model-implied 1y return % (frozen derivation:
  `((1 + mc_median_5y_return/100) ** (1/5) − 1) × 100` from the cached
  screener row — the annualized MC median).
- **payload** = `{price, street_target_mean, street_1y_pct, mc_median_5y_pct,
  as_of_source}` where `street_1y_pct = (street_target_mean/price − 1) × 100`.
- Universe: whatever the screener computed that day (~56-80 large caps).
  Tickers missing either forecast are recorded with `payload.missing=true`
  and EXCLUDED from scoring (both forecasts must exist on the same row).
- Source: the SAME cached screener computation supplies price, MC median and
  street mean — no timing mismatch between the two forecasts.
- Throttle: ≥5 calendar days between collections (weekly cadence at the
  daily check). `observed_at` is UTC (leak-safe).

## Outcome + primary metric (frozen)

- **Outcome:** realized simple price return over the 365 calendar days
  following `as_of` (close nearest to `as_of+365d`, within ±7 trading days;
  no dividends — both forecasts are price-level forecasts).
- **Primary (deciding): paired MAE comparison** — MAE_model vs MAE_street
  over all matured pairs, plus mean signed error (bias) for each.
- **Minimum window:** no reads before **30 matured (ticker, as_of) pairs
  spanning ≥ 2 distinct collection dates**; earliest decision date
  **2027-07-16** (first snapshots need 12 months to mature).
- **Reported, never deciding:** median AE, per-sector breakdown, rank
  correlation of forecast vs realized, hit-rate of direction.
- **Crash override:** if SPY enters a ≥20% drawdown, decisions defer to
  ≥6 months past the trough (both forecast families will miss huge in a
  crash; the comparison is still valid but not decided mid-crisis).
- **Contamination clause:** a discovered defect (price-split misalignment,
  target-staleness bug, screener cache mixing dates) voids affected rows,
  disclosed in this file.

## What this rule may NOT do

- May NOT arm a lane, size a position, or emit buy/sell language — ever.
  This is a measurement of forecast quality, not a signal.
- May NOT swap the outcome (e.g., to total return), the derivation formula,
  the maturity window, or the primary metric after data accrues.
- May NOT be quoted as "our model beats Wall Street" before the minimum
  window and earliest decision date — until then any surface shows the
  ledger as "accruing, matures from 2027-07".
- Survivor caveat: the universe is today's large caps (T7); a delisted
  ticker's realized return uses its last available price, disclosed per row
  (`payload.delisted_partial=true`). This biases BOTH forecast families
  identically, so the paired comparison survives; absolute MAE levels do not
  generalize beyond large caps.
