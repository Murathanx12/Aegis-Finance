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

## Results

### Local reproduction (run 2026-07-18, same spec, yfinance adjusted closes)
`engine/research/mandate_replay.py` — survivorship-safe here because every
sleeve ETF is alive (the delisted-data problem was the STOCK universe, T7).
One run per lane, zero parameter search. 6 bps per-side costs, rf=0.

| 2015-01→2026-07 | CAGR | Vol | Sharpe | Max DD | $100k → |
|---|---|---|---|---|---|
| conservative | 6.88% | 8.9% | 0.79 | −20.9% | $215,465 |
| balanced | 9.48% | 13.2% | 0.76 | −26.0% | $284,201 |
| aggressive | 11.50% | 17.1% | 0.72 | −32.3% | $351,107 |
| SPY | 13.66% | 17.6% | 0.82 | −33.7% | $438,034 |
| 60/40 | 9.06% | 10.9% | 0.85 | −21.5% | $271,896 |

**Reading (matches the pre-commitment above):** every mandate trails SPY
and every mandate has a smaller drawdown — the normal, expected shape for
diversified allocations across a bull decade. Balanced edges 60/40 on CAGR
(+0.4pp) but not on Sharpe. No skill claim lives here; this is the
direction-check that says the mandates are historically sane.

### Third-party confirmation (QuantConnect, fill in when Murat's runs finish)
| Lane | QC URL | CAGR | Max DD | Sharpe |
|---|---|---|---|---|
| conservative | — | | | |
| balanced | — | | | |
| aggressive | — | | | |

Divergence between the QC and local numbers beyond ~1pp CAGR needs
explaining (fees model, dividend handling, start-day) before either is
quoted anywhere.
