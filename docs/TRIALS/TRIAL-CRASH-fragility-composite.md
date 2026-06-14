# TRIAL-CRASH — Structural-fragility composite (descriptive)

**Pre-registered:** 2026-06-14 · **Purpose:** experimental · **Status:** forward-measuring
**Canonical decision rule:** mirrored in the experiment registry notes (param `fragility-composite`) and `backend/services/portfolio_intelligence/fragility.py::CRASH_DECISION_RULE`. Git-timestamped before the composite emits any UI-visible output — same tamper-evidence pattern as TRIAL-001 / TRIAL-LPPLS.

## Why this exists

Murat's standing hypothesis is that a market crash looks **inevitable after the
IPO/AI-valuation glut.** The honest way to test that — established in the
2026-06-14 deep research and the fragility reframe in `V2_GOALS` A5 — is **not** a
timing call (short-horizon crash timing has ≈0 IC). It is to **measure fragility
forward and let the data speak.** This trial pre-commits that measurement so any
later claim is OOS, not reverse-engineered.

## The composite (descriptive, equal-weighted)

An equal-weighted mean of already-fetched structural signals, each normalized to a
[0,1] fragility scale (1 = most fragile). **Weights are not fitted** — fitting them
to past crashes is the hindsight overfitting this project refuses.

**Active inputs (8):** LPPLS confidence · SOS · Sahm · turbulence percentile ·
absorption ratio · net-liquidity 4-wk drain (vs 52-wk history) · HY OAS percentile ·
IG OAS percentile.

**Candidate inputs (logged, NOT active — enter only as *tested* features, never
asserted):** VIX term structure (backwardation), options put/call IV skew, and
**IPO issuance** — the feature Murat's specific hypothesis rides on. IPO issuance
joins the composite once a cheap, free, point-in-time source is wired and it has
been measured against this same baseline; until then it is a documented candidate,
never a thumb on the scale.

## Measurement (forward, out-of-sample)

- **Forecast:** the composite ∈ [0,1], used as a conservative pseudo-probability.
- **Outcome:** SPY drawdown ≥ **20%** within the horizon (peak-to-trough from the reading date).
- **Horizons:** 30, 60, 90 days.
- **Baseline:** climatology — predict the in-sample base rate every period.
- **Metric:** Brier per horizon + calibration; `skill_score = 1 − brier_flag / brier_climatology`.
- **Accumulation:** each daily PI cycle persists one market-level `fragility_eval`
  row. `/api/pi/fragility` exposes the live composite + `composite_forward_brier`,
  which reports `insufficient_forward_data` until ≥30 matured observations per horizon.

### Rarity caveat (stated, not glossed)

A ≥20% drawdown within 90 days is **rare**, so the climatology base rate is low and
a meaningful forward Brier needs a **long** window; calibration at this rarity is
weak. This is reported honestly in the harness — the trial measures whether the
composite ever beats climatology, knowing the bar is statistically demanding.

## Decision rule

- **Adopt as a signal** only if `skill_score > 0` across all horizons on a
  pre-registered forward window. Adopting a *signal* (anything that could inform a
  rule or lane) is a **separate** registry trial gated on this result.
- **Otherwise** it remains descriptive context; a published negative result is itself
  a differentiator.

## Hard constraints (identity-level)

- **Descriptive-only. NEVER arms a lane, sizes a position, or emits buy/sell
  language. No "crash imminent" framing anywhere in the UI or API.** A grep-guard
  test asserts no lane/rebalance path reads the composite.
- No skill claim before the forward Brier clears the bar (and never before the
  24-month track-record threshold for any skill claim at all).

## Registry interaction (effective-N)

TRIAL-CRASH is a **non-lane** trial: it increments the **raw** cumulative trial
count (the DSR strictness floor, 2→3) but carries no return stream, so the
effective-N (`N_eff`) computation — which runs over `REFERENCE_LANES` only — is
unaffected. This is the intended D3 mapping (raw floor counts all rows; N_eff over
lane streams only).
