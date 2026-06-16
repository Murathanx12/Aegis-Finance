# TRIAL-MULTIFACTOR-IC — Multi-factor selection model (forward IC)

> **Pre-registered 2026-06-17.** Roadmap item 5 (3b/T8): combine the per-name
> factors into one cross-sectional rank — "the HK-rent approach, done honestly."
> Validated forward only (T7).

## Model (frozen)

`compute_multifactor_scores` (`backend/services/portfolio_intelligence/multifactor.py`):
z-score each factor across the universe, then an **equal-weighted mean** of the
available factors per ticker (a missing factor for a name just uses the rest).

    v1 factors = momentum + insider + revisions   (equal weight)

- **momentum** — `cross_sectional_momentum` percentile; reconstructable leak-free
  from price history (no forward snapshot needed).
- **insider** — `insider_opp:{ticker}` from the PIT store (TRIAL-INSIDER-IC).
- **revisions** — `revisions_score:{ticker}` from the PIT store (TRIAL-REVISIONS-IC).

**Quality (Piotroski) is DEFERRED**, not forgotten: `get_fundamentals` routes
through edgartools, which hung ~50 min in testing (see TRIAL-INSIDER-IC). It must
not sit in a scheduled collector until a guarded fundamentals path exists. Adding
it is a one-line factor extension once that path is built.

## Why this is honest (vs the survivor-backtest trap)

The composite is **snapshotted forward** (`multifactor_score:{ticker}`), reading
insider/revisions from the leak-safe PIT store and computing momentum from price
history up to the snapshot date. No survivor universe, no lookahead — it measures
the model's *prospective* ranking, exactly what a backtest on today's large-caps
cannot (T7).

## Estimator & decision rule

Forward rank-IC between the composite at *t* and forward return at 21/63/126d
(block-bootstrap CI, cross-section size each period). Descriptive until proven;
adoption only after a forward window with IC > 0 (CI excluding 0) AND the composite
beating each single factor's IC, then through `evaluate_candidate`. Never arms a
lane meanwhile.

## Status

- ✅ Combiner + forward collector WIRED 2026-06-17, in `scheduler._daily_check`
  AFTER the insider/revisions collectors (reads their fresh PIT values). Weekly-
  throttled, descriptive. Tests: `test_multifactor.py` (7 — z-score combine,
  missing-factor handling, zero-spread, PIT write, throttle, momentum-failure
  degradation).
- ⬜ IC measurement — forward, once a window accrues. Add quality factor when a
  hang-safe fundamentals path exists. Widen the 12-name cross-section later.
