---
name: pre-register-trial
description: Run BEFORE any new signal, strategy, factor, overlay, or hypothesis starts accruing data or gets evaluated. Creates the tamper-evident commitment (hypothesis + primary metric + decision rule + earliest decision date) in docs/TRIALS/ and the experiment registry. If it isn't pre-registered, it didn't happen (CANON §6).
---

# Pre-register a Trial

Every hypothesis enters as a registry trial with its decision rule committed
**before** data accrues. The git commit timestamp is the tamper evidence. No
metric substitution, window cherry-picking, or post-hoc regime adjustment —
ever.

## Why this exists

The registry + deflation guards are the project's defense against its own
hindsight. DSR/PBO deflate against the CUMULATIVE trial count — so every trial,
including ones that will obviously fail, must be counted. A registry showing
only adoptions is lying to itself; rejected trials are published
(NEGATIVE_RESULTS.md).

## What a registration contains (all required)

1. **Hypothesis** — one sentence, falsifiable, with the honest prior stated
   (e.g. TRIAL-EXIT: "shallower maxDD at flat-to-slightly-lower Sharpe, NOT a
   Sharpe increase").
2. **Primary metric** — the ONE deciding number (net Sharpe vs named control /
   forward rank-IC with CI / forward Brier vs climatology). Everything else is
   "reported, never deciding."
3. **Decision rule** — adopt threshold, reject threshold, minimum window,
   evaluation cadence, earliest decision date. Include the crash-event
   override where relevant (SPY −20% defers decisions to ≥6mo past trough)
   and a contamination clause for data defects.
4. **Frozen parameters** — whatever must not be tuned mid-trial, named.
5. **Hard constraints** — descriptive-only / never-arms / no buy-sell language
   until passed, where applicable.

## Procedure

1. Write the canonical doc: `docs/TRIALS/TRIAL-<NAME>-<slug>.md` following
   TRIAL-001's structure (including the "What this rule may NOT do" section).
2. Register the row: the trial enters `rule_experiments` with the decision
   rule embedded in `notes` (pattern: `ensure_lppls_trial` — idempotent,
   registers on first run). Verify `GET /api/pi/registry` shows it and
   `cumulative_trials` incremented.
3. Commit doc + code BEFORE the first forward observation. If data already
   accrued, the inception moves forward to now — prior data is excluded, never
   grandfathered.
4. Until the trial passes: the signal ships as **labeled descriptive context**
   only. No "signal", "predicts", or buy/sell framing anywhere it surfaces.

## Amendments

After data accrues, the rule may gain ANNOTATIONS (documentation of engine
properties, e.g. TRIAL-001's dark-overlay note) but never changes to
hypothesis, metric, thresholds, or window. Changing those invalidates the
trial — record it as abandoned and register a successor.

## Reality checks that gate what a trial can claim

- Backtests on our survivor-only data are direction-checks, never alpha
  evidence (T7) — selection signals validate FORWARD (PIT IC + lane NAV).
- LLM/brain picks are never backtested (profit mirage, canon A2) — the
  conviction lane is their only honest test.
- No skill claims before 24 months regardless of what any interim number says.
