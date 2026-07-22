# TRIAL-SMQ-FWD — smallmid-quality forward lane (BRAIN-007 composite book)

**Pre-registered:** 2026-07-22 (this doc + `smallmid_quality_lanes.yaml` hash,
committed BEFORE the attended seed). **Lane:** `smallmid-quality`.

## Provenance (backtest prior — never merged into the forward record)

Brain-module trials, all pre-registered, one run each (module repo
`investing-test-module`, docs/STRATEGY_FACTORY.md + TRIALS/):
- BRAIN-008 gross-profitability small: explore +23.2 bps/mo net (50 bps) →
  confirm PASS on held-out 2019-2024 (+24.1, IC t 4.29) → 1982-2001 extension
  SUPPORTIVE (+18.8). Positive in three independent windows across 42 years.
- BRAIN-003 opportunistic insider: survivor (FF6 α +102 bps/mo t 1.89 large/mid).
- BRAIN-007 fusion (frozen equal-weight z-composite of the two): SURVIVES —
  +15.3 bps/mo net, NW t 1.66, beats best single with 3.6× the names.
- Honest caveats carried forward: DSR ≈ 0.10 after 61-candidate deflation;
  BRAIN-008's FF6 alpha is negative (edge may be factor tilt); deploy gate NOT
  met anywhere. This lane exists precisely because the forward clock — not the
  backtest — is the scorecard.

## Hypothesis

The BRAIN-007 composite book (top-30 by mean winsorized z of PIT gross
profitability + opportunistic-insider 12-month flag, above-median-dollar-vol
universe), held equal-weight buy-and-hold with quarterly artifact refresh,
beats an investable small/mid benchmark (IWM) on forward data.

## Mechanics (frozen)

- Holdings: the 30 tickers in `smallmid_quality_lanes.yaml` — formed by the
  brain module at commit `a64d7e5` from CRSP/Compustat/SEC data
  (artifact `backend/data/smallmid_quality_book.json`; panel_end 2024-12,
  insider filings through 2026-03, gp PIT-lagged 6 months — staleness is
  inherent to the signal's own convention).
- Equal weight at seed, $100k notional, inception = seed day at current
  prices. NO reconstructed past. Buy-and-hold (optimizer none, rebalance
  never) between quarterly refreshes.
- Quarterly refresh (same duty slot as the CMP artifact, ~Oct 2026 next) is a
  CONFIG-VERSION change through the guarded evolution loop: new YAML content →
  new hash → boundary rebalance stamped. Never an in-place silent edit.
- Seed tolerance: ≤3 of 30 tickers unpriceable at seed → dropped LOUDLY
  (audit log + seed result); >3 → seed refuses (fail-loud).

## Decision rule

- Primary metric: since-inception total return vs IWM total return.
- **Earliest decision: 2028-07-22 (24 months).** No skill claims before.
- Reading at decision: BEAT if lane − IWM > 0 with the lane's bootstrap 90% CI
  excluding 0; FAIL if lane − IWM < −5pp; else INCONCLUSIVE (extend 12 mo).
- Kill/void: >3 holdings become unpriceable and unreplaceable mid-flight →
  flag `degraded` on the lane record and note in any reading (never silently
  patched).
- This lane NEVER arms anything, moves no real money, and its backtest priors
  are never quoted as forward performance.

## Isolation invariants (lane-integrity-check before/after)

Own YAML + own hash (`get_smq_config_hash`) — `paper_portfolios.yaml`,
`book_lanes.yaml`, `conservative_atr_lanes.yaml` byte-untouched; all existing
lanes' segments/inceptions/NAV rows untouched; seeding attended + env-gated
(`AEGIS_SEED_SMALLMID_QUALITY=1`, Murat flips, then unsets).
