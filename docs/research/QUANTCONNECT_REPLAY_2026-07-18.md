# QuantConnect lane-mandate replay — protocol (pre-registered 2026-07-18)

## Why QuantConnect
EODHD failed its survivorship acceptance gate (14/20, NEGATIVE_RESULTS §8),
so the honest 2015→today direction-check runs on QuantConnect instead:
free, survivorship-free US data, and the backtest is *hosted by a third
party* — the shareable result URL cannot be edited by us after the fact.

## What is being tested (frozen BEFORE any backtest is run)
The **mandates** — sleeve allocations + rebalancing cadence of the three
reference lanes — implemented with ETF sleeves, equal-weight within sleeve:

| Lane | Equity | Bonds | Alts | Rebalance |
|---|---|---|---|---|
| conservative | 40% | 50% | 10% | monthly |
| balanced | 70% | 25% | 5% | monthly |
| aggressive | 95% | 5% | 0% | weekly |

Explicitly NOT tested (and why): the individual-stock universe (chosen in
2026 knowing the winners — hindsight), HRP-vs-EW (open forward question,
TRIAL-001), the crash overlay (model not deployed live). See the header of
`engine/research/quantconnect/aegis_lane_mandates.py`.

## Pre-committed reading of results
- These are DIRECTION-CHECKS: "is the mandate historically sane vs SPY and
  60/40" — expected outcome for a diversified mandate in a 2015-2026 US
  bull market is **underperformance vs SPY with lower drawdown**. That
  result would be *normal*, not a failure; beating SPY would be surprising.
- No number from this replay is ever merged into the forward track record
  or reported as skill. It goes in a clearly-labeled historical section.
- Any parameter experimentation on QC (different sleeves, cadences, etc.)
  counts as trials for DSR/PBO purposes and must be logged here. The plan
  is ZERO experimentation: one run per lane, as specified.

## Murat's steps (~30 min)
1. quantconnect.com → Sign up (free, no card).
2. Create New Algorithm → Python.
3. Paste `engine/research/quantconnect/aegis_lane_mandates.py` over main.py.
4. `LANE = "conservative"` → **Backtest** → when done, click **Share** and
   copy the public results URL.
5. Repeat with `LANE = "balanced"`, then `LANE = "aggressive"` (3 runs).
6. Paste the three URLs back in chat. Next session records them here plus
   CAGR / maxDD / Sharpe into `docs/research/HONEST_REPLAY_2026.md` and
   builds the labeled UI section.

## Results (fill in after the runs)
| Lane | QC URL | CAGR | Max DD | Sharpe | SPY CAGR (same window) |
|---|---|---|---|---|---|
| conservative | — | | | | |
| balanced | — | | | | |
| aggressive | — | | | | |
