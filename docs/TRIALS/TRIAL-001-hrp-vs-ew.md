# TRIAL-001 — HRP vs Equal-Weight (pre-registered decision rule)

> Pre-registered 2026-06-11, **before forward data accrued** (comparison
> inception 2026-06-10, config `628456e4`). This file is the tamper-evident
> commitment: the git commit timestamp proves the rule predates the outcome.
> The same rule is embedded in the trial's `rule_experiments.notes` on the
> live registry. Changing this rule after data accrues invalidates the trial.

## Hypothesis

HRP (equity-sleeve, leakage-safe, as-of panel) adds value over equal-weight
on forward data, measured as `balanced` (HRP) vs `balanced-ew-control`
(identical mandate, frozen equal-weight). Honest prior: the 2021–25
walk-forward showed HRP at LOWER net Sharpe (0.65 vs 0.93) with lower vol
(10.9% vs 14.9%) and shallower max DD (−18% vs −26%) — the forward window
decides, not the backtest.

## Decision rule

- **Primary metric (the only deciding metric):** full-window **net Sharpe**
  (after transaction costs) computed from daily `paper_nav` returns of each
  lane, from 2026-06-10 inception.
- **Minimum window:** 12 months (earliest decision date **2027-06-10**).
  Evaluated **quarterly** thereafter. No peeking decisions before month 12 —
  interim numbers are reported, never acted on.
- **Revert threshold:** if at any post-month-12 quarterly evaluation HRP's
  full-window net Sharpe trails the control by **≥ 0.30**, HRP is reverted
  to equal-weight. The revert executes as a **new config version (v3) through
  the guarded evolution loop** (recorded as a trial either way) — never an
  in-place YAML edit (content-hash reuse corrupts segment identity).
- **Adopt-confirmation:** symmetric — if HRP leads by ≥ 0.30 at month 12+,
  the trial is recorded `adopted-confirmed`; otherwise it simply continues
  (no action) and re-evaluates quarterly.
- **Secondary metrics (reported, never deciding):** max drawdown, annualized
  volatility, Calmar, turnover, total transaction costs, tracking error vs
  control.
- **Crash-event override:** if SPY draws down ≥ 20% from its in-window peak,
  no revert/adopt decision may be taken until the window includes **≥ 6
  months after the drawdown trough**. Rationale: the lane mandates are
  risk-managed; deciding mid-crash (or on a window with no stress at all
  when one just started) biases the comparison in either direction. The
  override delays decisions; it never changes the metric or threshold.
- **Contamination clause:** if either lane suffers a data/accounting defect
  (missed MTM ≥ 5 consecutive trading days, mis-booked rebalance), the
  defect window is documented and the minimum window extends by its length.

## What this rule may NOT do

No metric substitution after the fact, no window cherry-picking, no
"adjusting for regime" in the primary metric, no early revert on drawdown
panic (that's what the crash override and the secondary metrics are for —
reporting, not deciding).

## Annotation 2026-06-14 — crash overlay was DARK on both arms (trial valid)

> Added after data accrued. This annotation does NOT change the hypothesis,
> the primary metric, the threshold, or the window — it records a property of
> the engine both arms ran on, so the conclusion is not misread later. Under
> the rule above, that is permitted (it is documentation, not a rule change).

**Finding.** The crash overlay has never been operational in production. Two
independent causes, both present since before this trial's 2026-06-10
inception:

1. `reference_engine._get_crash_prob()` called `CrashPredictor.predict_proba()`
   with no arguments (wrong signature; raised every daily check, swallowed by
   a try/except) — present since the first PI commit `116d1e5`.
2. `crash_model.pkl` is gitignored (`*.pkl`) and was never baked into the
   Railway image. Confirmed live: `GET /api/crash/prediction` returns
   `status: model_not_trained`. So even with cause #1 fixed, prod has no model
   to evaluate.

**Why the trial remains valid.** Both `balanced` (HRP) and
`balanced-ew-control` ran with the overlay equally dark. The overlay is a
*shared* risk control applied identically to both arms (same `crash_overlay`
block shape); its absence subtracts the same component from both NAVs. The
comparison isolates **HRP vs equal-weight on the equity sleeve**, which is
untouched by the overlay. Therefore the primary metric (relative net Sharpe)
is unbiased by the dark overlay. No window extension is triggered: this is not
a per-lane data/accounting defect under the contamination clause — it is an
engine-wide dormant feature affecting both arms symmetrically.

**What changed 2026-06-14 (and what did NOT).** The call site was fixed and a
loud per-lane overlay status was added to `/api/health/full` (so a dark
overlay can never again hide). The overlay was **deliberately NOT armed** on
these lanes: arming a risk control mid-trial would change the strategy of an
in-flight pre-registered comparison and would require shipping an
unprovenanced binary into the forward record. If the overlay is ever armed, it
will be on **new** pre-registered lanes with a version-controlled,
provenance-documented model — never retrofitted here. See
`docs/postmortems/2026-06-14-crash-overlay-dark.md`.
