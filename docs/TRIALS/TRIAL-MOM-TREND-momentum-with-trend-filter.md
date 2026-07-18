# TRIAL-MOM-TREND — 12-1 momentum + SPY 10-month trend filter (offline direction-check)

**Registered:** 2026-07-18, AFTER TRIAL-MOM-BACKTEST (#13) FAILED its frozen
run (Sharpe 0.63 vs SPY 0.87; maxDD −54.7% vs bound −42.2%) and BEFORE this
variant touches data. This is the pre-registered SUCCESSOR testing the
literature's documented fix for momentum crashes (trend overlay — the one
allocation mechanism with a surviving OOS record, F-022). It increments the
cumulative trial count (now 14). **Type:** offline direction-check — NOT a
forward clock.

## Hypothesis (honest prior stated)
Adding an SPY 10-month-SMA regime filter (risk-off → 100% cash) to the
EXACT TRIAL-MOM-BACKTEST spec lifts net Sharpe to ≥ SPY and cuts maxDD
inside 1.25×SPY, at some CAGR cost. Prior: moderate — trend filters
demonstrably truncate momentum crashes in the literature, but 2020's
V-shaped COVID whipsaw sits inside the window and punishes exactly this
rule. A second FAIL likely ends the momentum-lane idea in this window
(successor chains stop; no fishing by iteration).

## Frozen parameters
IDENTICAL to TRIAL-MOM-BACKTEST (#13) — panel, eligibility, signal,
top-50/band-100, 20 bps/side, delist haircut, window — plus ONE addition:
- At each monthly rebalance, if SPY's last monthly close < its 10-month
  SMA (10 monthly closes incl. current), liquidate to 100% cash (costs
  apply) and hold cash until the filter re-opens. No partial scaling.

## Primary metric & decision rule (unchanged)
Net Sharpe (rf=0, daily) vs SPY over the identical window.
- **PASS:** Sharpe ≥ SPY AND maxDD ≤ 1.25 × SPY maxDD → momentum-with-
  trend lane may be PROPOSED (attended, cap is Murat's).
- **FAIL:** else → NEGATIVE_RESULTS; the momentum-lane line of inquiry
  closes for this window (no third variant without new evidence from a
  different mechanism class).
- ONE run. Parameter-cloud annex reported, never deciding.

## What this rule may NOT do
Same as #13: no alpha/skill claims, nothing into paper_nav, never arms,
no re-runs under this ID, PASS ≠ lane (Murat decides).
