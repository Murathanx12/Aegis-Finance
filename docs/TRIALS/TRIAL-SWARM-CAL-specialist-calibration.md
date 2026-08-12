# TRIAL-SWARM-CAL — are the swarm specialists' stated probabilities calibrated?

**Pre-registered:** 2026-08-12 (this commit) · **Purpose:** measurement
(calibration), not a trading signal · **Status:** ACCRUING (forward-only) ·
**Campaign:** GRAND-ARENA-1 chunk 3, LLM-SWARM-1

## Hypothesis (falsifiable, honest prior)

Per specialist role, the forward Brier score of the probabilities minted by
`llm_swarm` is **below that role's own realised climatology**
(`base_rate x (1 - base_rate)` on the same resolved slice).

**Honest prior: we expect most roles to FAIL this.** NIGHT-3 measured that LLM
output earns no role in stock ORDERING (t = 0.04 and 0.93 over 16,320
decisions). Calibration is a different question with a different instrument,
and it has never been measured here — but the prior from that result, from the
literature on LLM overconfidence, and from the fact that the model has no live
data feed, is that stated probabilities will be **overconfident** (mean
probability above base rate) and will not beat climatology. A single role
clearing the bar on a well-powered slice would be the surprise, and is the only
reason the trial is worth accruing.

## What accrues (frozen)

`PredictionRecord`s written by `backend/services/llm_swarm.py` into the Optimus
ledger (`belief_state.PREDICTIONS`), one per accepted forecast:

- **Universe:** the 459 securities frozen in
  `backend/data/swarm/swarm_1_universe.json`, assembled from repo sources that
  pre-date this campaign plus a seeded random sample of the cached 5,324-name
  US listing, gated on >= 252 trading days of history at the observation
  timestamp.
- **Snapshot:** PIT by construction — the price panel is truncated at `as_of`
  before any field is computed (`snapshot_from_panel`). Pinned by
  `test_nothing_after_the_observation_timestamp_reaches_the_snapshot`.
- **Roles:** the 14 in `llm_swarm.SPECIALISTS`, each called separately with no
  sight of any other role's answer.
- **Model:** `deepseek-chat`, recorded per record as `model_version` from the
  API response, so a model swap is visible in the slices rather than mixed into
  them.
- **Observables and horizons:** the frozen `belief_state.Observable` and
  `HORIZONS` sets. Nothing else is admissible.

## Outcome + primary metric (frozen)

- **Outcome:** resolved by `belief_state.resolve_one` against adjusted closes,
  unchanged. No separate resolver is written for this trial.
- **Primary (deciding), per specialist:** mean Brier minus that slice's own
  climatology Brier. Negative = informative. **Adopt** a role as informative
  only when the gap is negative AND clears its own 80%-power MDE (CANON §19).
  **Reject** when the gap is positive and clears the MDE in that direction.
  Anything between is **NOT DETECTABLE** and is never a kill.
- **Minimum window:** no per-role read before **200 resolved records in that
  role's slice**, and no swarm-level read before **2,000 resolved records**.
  Earliest decision date **2026-11-15** (the 60-day horizons are the first
  slice that can be well powered; the 1- and 2-day slices resolve sooner and
  accrue n fast but are mostly noise and are reported, never deciding).
- **Reported, never deciding:** overconfidence (mean probability minus base
  rate), reliability curves, per-observable and per-horizon slices,
  `effective_distinct_ideas`, abstention rate, cost per gradeable output.
- **Crash override:** if SPY enters a >= 20% drawdown, decisions defer to >= 6
  months past the trough.
- **Contamination clause:** a discovered defect (a threshold units error, a
  wrong benchmark column, a snapshot leak) VOIDS the affected records via
  `void_reason` rather than deleting them, disclosed in this file.

## Frozen parameters

`SWARM_COIN_FLIP_EPS`, `SWARM_MAX_FORECASTS_PER_CALL`,
`SWARM_SCENARIO_PROB_TOL`, `SWARM_BENCHMARK`, the 14 role prompts, the
`CONTRACT` text, and the universe file. Changing any of them after accrual
starts invalidates the trial: a successor is registered, the predecessor is
recorded abandoned.

## What this rule may NOT do

- May NOT arm a lane, size a position, rank securities, or emit buy/sell
  language. It measures a forecaster; it does not select stocks. NIGHT-3's
  ordering null stands and is not contested by this trial.
- May NOT swap the outcome, the metric, the minimum window or the thresholds
  after data accrues.
- May NOT be quoted as "the LLM is calibrated" before the minimum window and
  the earliest decision date.
- **ARCHITECTURE_RESULT_ONLY on anything historical.** The foundation model may
  know history that overlaps any backtest, so only the FORWARD resolution of
  these records is evidence. No historical replay of these prompts may be
  quoted as calibration.
- Volume is not n. 8,000 calls to one model is one correlated opinion sampled
  8,000 times; every claim prints `effective_distinct_ideas` beside its raw
  count (CANON §20).
