# TRIAL-LEAK-1 — does the model KNOW, or does it REMEMBER?

**Pre-registered:** 2026-08-12, before any forecast call · **Campaign:**
GRAND-ARENA-1 chunk 3B, LLM-LEAKAGE-PROBE-1 · **Purpose:** measurement of the
INSTRUMENT · **Status:** ACCRUING · **Class:** `ARCHITECTURE_RESULT_ONLY`
(Amendment A, A6)

## Why this exists rather than another swarm

LLM-SWARM-1 measured its own ceiling: 22,607 forecasts → 6,772 effective
distinct ideas (ratio **0.2996**), fourteen roles differing by a mean
probability spread of **0.059**, and every one of its 20,073 records unresolved
until 2026-08-16. More of the same buys more correlated exploration and no more
evidence.

This buys two things it could not: records that resolve the moment they are
made, and a measurement of whether the model reasons from the evidence or
recalls the answer. **If the second one comes back positive, every historical
LLM result this programme has ever produced — including anything anyone tries to
read off the first swarm — is invalidated.** That is why it is worth the money.

## The predecessor, with receipts

**TRIAL-LLM-AMNESIA-1 / 1B** (2026-08-08) already ran named-vs-masked over 120
events and found: an instruction to forget does nothing (recall 15.8% vs 15.8%);
masking works (0 of 240 identifications); removing identity cost 0.007 Brier;
memory is *real, sparse and self-selecting* (95.8% declined; 5 of 5 correct when
it did answer, every one a famous collapse). **But its task was unlearnable** —
every arm sat at the climatology Brier of 0.25, and so did the cheap logistic
baseline, so it could not tell *no skill* from *no signal*. Its own retirement
note specified the successor: short-horizon reactions, famous-case
stratification, canaries from the start, and a baseline bank.

This trial is that successor. It adds one thing AMNESIA-1 did not have — an
**era stratum** — because the identified-minus-masked gap alone confounds memory
with "a stripped prompt is harder to read".

## Hypothesis (falsifiable, honest prior)

**H1 (primary).** On paired items, `Brier(identified) − Brier(masked)` is more
negative in the **pre-cutoff era (2015–2023)** than in the **recent era
(2025–2026)**. That difference-in-differences is the leakage estimate.

**Honest prior: we expect H1 to come back NOT DETECTABLE.** AMNESIA-1 measured
the identity effect at 0.007 Brier against a design that could not resolve it,
and it measured recall at ~4% of cases. A 4%-prevalence effect on a noisy
observable is very unlikely to clear an 80%-power MDE at this n. **A null is the
expected outcome and is a useful one**: it is the only evidence that would let
historical LLM replays be used for architecture work at all. The surprise —
and the expensive one — would be a detectable positive gap concentrated in the
pre-cutoff era.

**H2.** The identification canary names the correct ticker on ≤ 5% of masked
items and the correct year on ≤ 15%. (AMNESIA-1 got 0/240 on a percentile-based
mask; this mask is weaker by design, keeping raw numerics, so a higher rate is
expected and would BOUND the primary result rather than void it.)

**H3.** `effective_distinct_ideas` does not exceed 0.40 in any independent
condition. Prior: the swarm's 0.2996 was not a property of that prompt but of
one model sampled repeatedly, and temperature will move it least.

**H4.** No specialist × observable slice with n ≥ 200 beats BOTH its own
climatology and the PIT baseline. Prior from NIGHT-3 (ordering null over 16,320
decisions) and from AMNESIA-1's flat arms.

**H5 (model arm, added after the alias defect was found — see below).**
`deepseek-v4-pro` does not beat `deepseek-v4-flash` on paired items by more than
the arm's own MDE.

## What accrues (frozen)

- **Ledger:** `backend/data/optimus/leakage_probe_predictions.jsonl`. **NEVER
  `predictions.jsonl`.** The forward ledger's entire value is that it is
  forward-only; backfilled historical records would destroy it.
- **Items:** frozen in `backend/data/leakage_probe/items.json` before the first
  call — securities × observation dates, each with its PIT snapshot and its
  slate. Securities are drawn from `config.stock_universe.sector_stocks`, which
  pre-dates this campaign, gated on continuous 2014–2026 history.
- **Eras:** pre-cutoff `2015-01-01 … 2023-12-31`; recent `2025-03-01 …
  2026-05-01`. **2024 is excluded deliberately** — it is the band where "has the
  model seen this" is genuinely unknown.
- **Slate (frozen, identical in every arm):** `return_sign@5`,
  `return_sign@20`, `beats_benchmark@20`, `abs_move_exceeds@20` (threshold =
  1σ over 20 days from PIT realised vol), `drawdown_exceeds@60` (0.8σ over 60
  days). Thresholds are PIT and identical across arms, so every answer has a
  partner.
- **Arms:** `identified` (real ticker, name, date, price level) · `masked`
  (identity removed, every numeric feature unchanged) · `deep_masked` (identity
  + era channel removed).
- **Roles:** the six sector-free roles in `leakage_probe.ROLES`.
- **Models:** requested by REAL id only. Every record stores `served_model` read
  off the response body.

## Outcome + primary metric (frozen)

- **Outcome:** `belief_state.resolve_one` against adjusted closes. No separate
  resolver.
- **Primary (deciding):** the **difference-in-differences** of the paired mean
  Brier gap between eras, with a date-cluster bootstrap SE (§18) and a
  **measured** 80%-power MDE (§19, by planting effects of known size into
  date-clustered resampled worlds — never a formula).
- **Decision rule.** *Leakage DETECTED* only if the DiD is positive AND exceeds
  its own MDE. *Leakage REJECTED* only if it is negative and exceeds the MDE in
  that direction. Anything between is **NOT DETECTABLE** and is never a kill.
- **Reported, never deciding:** the pooled gap, per-era gaps, per-observable,
  per-horizon, per-role slices, the salient-outcome slice, the deep-mask arm,
  the canaries, calibration, diversity, cost.
- **Salience slice** is defined on the OUTCOME (|60d move| ≥ 20%) and is
  therefore a REPORTED slice only. It may never be used to select items.

## What may NOT happen

- These records may **NOT** set production specialist weights (A5), arm a lane,
  size a position, or be quoted as forward calibration. `ARCHITECTURE_RESULT_
  ONLY` (A6). Forward records from 2026-08-16 remain the only certification
  path.
- The primary metric, the eras, the slate and the decision rule may not change
  after accrual. Any change registers a successor and records this abandoned.
- No slice may be promoted to the headline after the numbers are seen. The
  headline is fixed above: **one** primary metric, **one** estimator.
- A null below the MDE may not be quoted as "no leakage". It is "not detectable
  by this design", and the MDE is printed beside it.

## Amendment 1 (2026-08-12, before the first forecast call)

The brief specified a model-diversity arm of `deepseek-chat` vs
`deepseek-reasoner`. **That arm is VOID BY CONSTRUCTION and was never run.**
Measured against the live account: `GET /models` returns exactly two ids,
`deepseek-v4-flash` and `deepseek-v4-pro`; **both** `deepseek-chat` and
`deepseek-reasoner` are served by `deepseek-v4-flash`. The arm would have
compared one model with itself, and its null would have been a configuration bug
reported as a finding.

Replaced by H5: **v4-flash vs v4-pro**, requested by real id, paired on the same
items, tested as a difference with its own SE and its own MDE. Two further
measured facts are frozen here because they change what the arm costs and
whether it yields anything at all:

1. Thinking is ON by default for both real ids and for the `deepseek-reasoner`
   alias. `extra_body={"thinking": {"type": "disabled"}}` turns it off and
   reproduces the `deepseek-chat` signature exactly.
2. **A thinking-on call returns EMPTY CONTENT at ordinary token caps.** At
   `max_tokens` 300, 600, 1500 and 3000 the entire budget went to reasoning
   tokens and `content_len` was 0 with `finish_reason="length"`. Only at 8,000
   did v4-pro finish. Thinking arms therefore run at `max_tokens=12000`; an arm
   run at an ordinary cap would be 100% zero-yield and would look like a parser
   fault.

All dollar figures in this trial are **PROVISIONAL**: the price table was keyed
on the alias names and was corrected mid-campaign, so the ledger mixes two price
regimes.

## Contamination clause

A discovered defect — a mask leak, a threshold units error, a wrong benchmark
column, a non-PIT field — **VOIDS** the affected records via `void_reason`
rather than deleting them, disclosed here. Masked cells whose rendered prompt
fails `masking_violations` are refused **before the wire** and counted; they are
never repaired and re-sent.
