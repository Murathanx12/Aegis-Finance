# TRIAL-REVISIONS-IC — Analyst revision momentum (forward IC)

> **Pre-registered 2026-06-17.** Roadmap item 4: *flip the analyst factor — rank by
> the FLOW of revisions/upgrades, NOT raw implied upside.* Validated forward only
> (T7: no backtest on survivor data certifies alpha).

## The flip (why)

The old analyst read ranks by `implied_upside_pct = target/price − 1` — a *level*,
dominated by tiny-caps with one stale sky-high target (probe: KYTX showed +286%
implied upside, a fluke). That is the metric we are moving away from. The
literature (Novy-Marx 2013; Jegadeesh-Livnat 2006) finds the predictive signal is
the *change* in analyst views — the revision/upgrade flow — not the level.

## Signal (frozen)

`compute_revision_momentum_score` (`backend/services/estimate_revisions.py`):

    revisions_score = (raises − lowers) + (upgrades − downgrades)

over dated analyst actions with `as_of − 90d < date ≤ as_of` (leak-safe). Source:
yfinance `.upgrades_downgrades` (a dated log: `priceTargetAction` ∈ Raises/Lowers,
`Action` ∈ up/down/…). Consensus rating drift (0m vs −2m from `.recommendations`)
is exposed in the payload but **not** folded into the headline score (keeps it a
clean, interpretable count). Verified discrimination on real data: NVDA +23,
AAPL +16, DKNG −4 (6 raises vs 9 lowers — deteriorating), KYTX 0 (sparse).

## Estimator & decision rule

Forward rank-IC (Spearman) between `revisions_score` at *t* and forward return at
21/63/126d, with a block-bootstrap CI and cross-section size each period.
Descriptive until proven; adoption only after a forward window with IC > 0 (CI
excluding 0), then through `evaluate_candidate`. Never arms a lane meanwhile.

## Status

- ✅ Signal + forward collector WIRED 2026-06-17. `revisions_collector.py` (on the
  generic `pit_score_collector`) snapshots `revisions_score:{ticker}` for the 12
  book names into the PIT store, weekly-throttled, in `scheduler._daily_check`.
  Forward clock starts next deploy. Tests: `test_revisions_signal.py` (10 — net
  count, leak-safe future-exclusion, 90d window, drift-in-payload, collector
  PIT-write/throttle/failure-isolation).
- ⬜ IC measurement — forward, once a window accrues. Small-N (12 names) reported.
