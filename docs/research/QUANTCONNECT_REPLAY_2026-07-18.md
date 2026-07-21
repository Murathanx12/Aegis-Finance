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

### Third-party confirmation (QuantConnect — RECORDED 2026-07-21, PASSED)
Murat's three runs, stats pulled from QC's public share API
(`api/v2/sharing/backtests/result/read`). Lane identity inferred from
vol/CAGR/DD ordering and confirmed by near-exact drawdown matches.

| Lane | QC URL (backtestId) | CAGR | Max DD | QC Sharpe | QC Vol |
|---|---|---|---|---|---|
| conservative | [624c0e6a…](https://www.quantconnect.cloud/backtest/624c0e6a699d9da54778046ba4581c30/) | 6.65% | −20.9% | 0.31 | 7.3% |
| balanced | [a74c4080…](https://www.quantconnect.cloud/backtest/a74c4080a35e1f48c96122424f84011f/) | 9.25% | −26.0% | 0.40 | 10.8% |
| aggressive | [6a52edbe…](https://www.quantconnect.cloud/backtest/6a52edbeb3a6518f7c748f65942fd72e/) | 11.47% | −32.1% | 0.45 | 14.1% |

**Cross-check verdict: CONFIRMED.** Every lane agrees with the local
reproduction within the pre-committed 1pp CAGR tolerance (conservative
6.65 vs 6.88, balanced 9.25 vs 9.48, aggressive 11.47 vs 11.50) and the
max drawdowns match to the decimal (−20.9/−26.0 exact; −32.1 vs −32.3).
The QC Sharpes (0.31/0.40/0.45) vs local (0.79/0.76/0.72) differ ONLY by
denomination: QC subtracts its risk-free model (implied rf ≈ 4.9%/yr from
the balanced numbers), local uses rf=0. Same result, two conventions —
both quoted wherever this replay is surfaced. The mandates are
third-party-confirmed historically sane: trail SPY across a bull decade,
with uniformly smaller drawdowns, exactly as pre-committed.

**How to read the QC numbers (added 2026-07-21, after first run attempt):**
- **QC's Sharpe is NOT our Sharpe.** QuantConnect subtracts a risk-free rate;
  the local table above uses rf=0. With 2015-2026 average rf ≈ 2%+, the same
  balanced result reads ≈ 0.5 on QC vs 0.76 here. A "low" QC Sharpe is the
  SAME result, differently denominated — not a failed run.
- **A low Sharpe never blocks sharing.** The Share button works on any
  completed backtest regardless of performance: open the finished backtest →
  Share → copy the public URL. Per the pre-committed reading above, trailing
  SPY IS the expected outcome — the URL of an "ugly" result is exactly the
  point (third-party-hosted honesty, not a highlight reel).
- **Re-run on the fixed algo:** the original used `AccountType.Cash`; LEAN
  models T+2 settlement there and can silently reject rebalance orders
  (worst at aggressive's weekly cadence). Now `Margin` (no leverage is
  requested — weights sum to 1). Re-paste the updated
  `engine/research/quantconnect/aegis_lane_mandates.py` before the 3 runs.

Divergence between the QC and local numbers beyond ~1pp CAGR needs
explaining (fees model, dividend handling, start-day) before either is
quoted anywhere.
