# TRIAL-LPPLS — LPPLS bubble-structure flag (descriptive)

**Pre-registered:** 2026-06-14 · **Purpose:** experimental · **Status:** forward-measuring
**Canonical decision rule:** mirrored in the experiment registry notes (param `lppls-fragility-flag`) and `backend/services/portfolio_intelligence/fragility.py::LPPLS_DECISION_RULE`.

## Why this is pre-registered before any claim

The Log-Periodic Power Law Singularity (LPPLS) model describes the *structure* of
a speculative regime. Its predictive skill for crash **timing** was adversarially
**REFUTED twice** in the 2026-06-14 deep research
(`DEEP_RESEARCH_2026-06-14_DECISION.md` §1.1) — even by the Sornette-favorable
source. So we ship it **descriptive-only** and measure forward, honestly, before
ever calling it a signal. This trial exists so the measurement is pre-committed,
not reverse-engineered from whatever the data later shows.

## Hypothesis

LPPLS bubble-structure confidence on the S&P 500 has **forward skill** at flagging
elevated crash risk over 30 / 60 / 90-day horizons.

**Prior (honest):** expected null. The literature predicts no forward skill.

## Measurement (forward, out-of-sample)

- **Forecast:** LPPLS confidence ∈ [0,1], used as a deliberately conservative
  pseudo-probability of a crash within the horizon.
- **Outcome:** SPY drawdown ≥ **10%** within the horizon (peak-to-trough from the
  reading date).
- **Horizons:** 30, 60, 90 days.
- **Baseline:** climatology — predict the in-sample base rate every period.
- **Metric:** Brier score per horizon; `skill_score = 1 − brier_flag / brier_climatology`.
- **Accumulation:** each daily PI cycle persists one market-level `lppls_eval`
  audit row. `/api/pi/fragility` and `/api/health/full`'s `lppls` block expose the
  latest reading + canary; the Brier reports `insufficient_forward_data` until
  ≥30 matured observations exist per horizon.

## Decision rule

- **Adopt as a signal** only if `skill_score > 0` (i.e. `brier_flag <
  brier_climatology`) across all horizons on a pre-registered forward window.
  Adopting a *signal* is a **separate** registry trial gated on this result.
- **Otherwise** it remains descriptive context, and a published negative result
  is itself a differentiator.

## Hard constraints (identity-level)

- **Descriptive-only. NEVER arms a lane, never sizes a position, never emits
  buy/sell language.** There is no code path from this flag to a trade
  (`fragility.py` returns readings only; `lppls_status().armed` is hard-`False`).
- No skill claim before the forward Brier clears the bar above (and never before
  the 24-month track-record threshold for any skill claim at all).
- Revisit the LPPLS calibration method (nested-MC vs quantile regression, D1)
  ONLY if the forward Brier ever shows skill — otherwise calibration polish on a
  refuted-as-predictive signal is wasted effort.
