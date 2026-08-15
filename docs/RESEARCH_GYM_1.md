# RESEARCH-GYM-1 — phase 1

**Registered** 2026-08-15 in `Aegis module/TRIALS/registry.jsonl`, once, as a
campaign. **Charter:** `docs/HANDOFF_OPUS5_2026-08-15.md` R2–R5.
**Code:** `backend/services/research_gym/`. **Tests:** `test_research_gym.py`
(30) + `test_gym_regret_denominator.py` (29).

> Everything in this document that carries a number is **Gym output**: a
> hypothesis, not a result. No figure here may appear in a README claim, a
> track-record surface, or a funding argument. That is wall 1, and it is
> enforced by a type that raises rather than by this paragraph.

---

## RESTATED 2026-08-15 — every number below has been recomputed

The first version of this document reported a headline of **+26.5pp mean
regret** on five de-risking decisions, classified **all five** as failures, and
printed a five-bucket base-rate table whose shape was read off the column. An
audit ordered by the brain (`HANDOFF_2026-08-15_BRAIN_TO_BUILDER.md` §2) found
two defects, both by **running the numbers rather than reading the code**:

| | defect | consequence |
|---|---|---|
| **G1** | regret was denominated against the **ex-post best of 17 policies**, whose null is large and positive | roughly half the headline was the denominator; and `MATERIAL_EDGE_PCT = 1.0` was cleared by a blameless hold **93%** of the time, so the failure *rate* measured the threshold rather than the engine |
| **G2** | the base-rate table reported `n` where it owed **n_effective**, and printed no MDE | `n=353` for VIX≥35 is 353 daily observations of a 63-day window across 19 episodes — an effective sample of **5.6** |

Both are fixed in code, and **every figure in the sections below is the
recomputed one**. The audit is the argument *for* the Gym, not against it: it
produced a number good enough to be worth auditing, and the audit found the
denominator.

## Why it exists

Murat's directive: *run many, many backtests* — with the objection that a search
over 100,000 policy variants will eventually fit 2008, COVID and 2022
beautifully whether or not there is any signal, and human review cannot undo
that once the optimiser has looked.

The resolution is not to search less. It is to **separate the place where
searching happens from the place where claims are made**:

| | Gym | Certification |
|---|---|---|
| Data | historical | forward only |
| Overfitting | **licensed** | impossible by construction |
| Output | hypotheses | verdicts |
| Citable | never | yes |

This also discharges R8 honestly. We have tested hundreds of hypotheses against
most of the history; Optimus has read it; we have read it. There is no clean
historical test set left and there never will be again. Saying so and building
around it is better than manufacturing a "fresh" 2019–2024 holdout that is
fresh in name only.

## The three walls, as code

**Wall 1 — nothing inside the Gym is evidence.** `GymResult.as_claim()` raises
`GymOutputIsNotEvidence`. The type carries its numbers and computes freely; it
simply refuses to render as a claim. The point is not that it cannot be
circumvented — anything can — but that circumventing it requires writing a line
of code that says unmistakably what is being done.

**Wall 2 — every search leaves a lineage row.** `LineageRow` records
`parent_id` **and `parent_failure`**: candidate N exists because candidate N−1
failed in a recorded way. `unledgered_search_warning(n_tried)` reports when more
candidates were tried than ledgered, because a campaign whose true
multiple-comparison count is unknown deflates against a denominator that
understates (§20).

**Wall 3 — export requires transfer + prereg + forward.** `request_export()`
returns a verdict plus everything missing. A mechanism leaves only after
surviving ≥3 slices that generated none of it, a frozen pre-registration, and
forward certification. **The episode that inspired a rule is barred from proving
it** — not down-weighted, barred, checked by set intersection.

## The DecisionEpisode (R3)

Four separable parts: **STATE** (PIT), **BELIEFS** (probabilities, `None` means
unknown and never 0.5), **ACTION** + the reason given *at the time*, **OUTCOME**
(attached later; an unresolved episode is structurally unresolved rather than
carrying zeros a mean would eat).

The separation is the design. A bad outcome can come from a wrong belief or from
a right belief converted into a wrong action; those need opposite fixes, and a
record storing only "sold, lost money" cannot tell them apart.

Exposures are **fractions**. `exposure_after=50.0` raises — this repo has
already written a batch of guaranteed-wrong records by taking a percent for a
fraction.

## The counterfactual surface

17 declared policies — hold, sell 25/50/100, buy 25/50, delayed re-entry at
3/10/21 days, drawdown-triggered re-entry at −5%/−10%, volatility-rollover
re-entry, scale-in, hedged. Every episode is replayed under **all of them** and
the **whole surface** is recorded.

Recording only the winner would be recording a maximum over seventeen tries on a
single sample — a selection bias the size of the menu, with no standard error.
Turnover is charged at 10bp per unit of exposure changed, because a menu that
ignored cost would rank the busiest policy first every time, and the busiest
policy is the one most likely to be fitting noise.

### Three denominators, never one (G1)

The original `regret_pct()` was documented as *"best available minus what was
done. Never negative by construction."* That last clause is the defect stated
out loud: a quantity that can never exonerate is not a measurement of skill.
Measured on ^GSPC 1990–2026, 63-day horizon, 10bp cost, same menu — this is
what a decision-maker with **no skill at all** scores:

| state | always-HOLD | always-SELL_100 |
|---|---:|---:|
| VIX < 15 | +3.19pp | +5.44pp |
| VIX 15–20 | +4.55pp | +6.42pp |
| VIX 20–25 | +5.88pp | +7.54pp |
| VIX 25–35 | +6.15pp | +10.85pp |
| **VIX ≥ 35** | +10.24pp | **+17.31pp** |

So every regret figure is now reported as a **triple** (`regret.RegretTriple`):

1. **vs the ex-post best** — kept, labelled an **upper bound** everywhere.
2. **vs a fixed default (HOLD)** — one pre-declared alternative, no selection
   bias, and **it can be negative** when the decision was good.
3. **excess over the state-and-action-matched null** — (1) minus the table
   above, which is the skill-relevant number.

Matchedness is enforced, not assumed: the first measurement of this null was run
on SPY at 5bps while dataset zero ran on ^GSPC at 10bps — three mismatches
inside a comparison whose only purpose is to be matched. `regret_triple()` now
**raises** rather than subtract a null computed at a different cost, horizon or
universe, and the policy menu is hashed into the null's identity because regret
vs the best of 17 and vs the best of 25 are different quantities.

### The gate, calibrated (G1)

`MATERIAL_EDGE_PCT = 1.0` sounded conservative and was the opposite: measured
**P(a blameless always-HOLD showing more than 1.0pp regret) = 0.931**. The gate
is now a **percentile of the matched null for that state and that action**, so
the bar moves with the situation — 3pp of regret in a calm market and 3pp after
a VIX-50 panic are not the same claim. The p90 gate for a full sell at VIX ≥ 35
is **35.16pp, not 1pp**. The old constant survives only as a labelled
`UNCALIBRATED` fallback for when no null is available.

## The failure taxonomy (R4), and the mode that had to be added

The first dataset-zero run classified **all five** de-risking failures as
`forecast_failure`. True, and an artefact: under the definition "expected down,
went up", a sell followed by a rally can barely classify as anything else. The
label distinguished nothing.

Murat's directive is sharper than the label was — *"stress detection itself was
correct; the failure came from mapping high stress → zero exposure"* — and it
separates three layers, not two:

```
PERCEPTION   what is the state?          VIX 57 — CORRECT, measured not forecast
INFERENCE    what follows from it?       "expect down" — THE ERROR
ACTION       what do we do?              sell
```

So `state_to_forecast_failure` was added, and it is decided **against the state's
own historical base rate rather than against the outcome**:

- expectation contradicted the base rate → wrong in a way the data already knew,
  **learnable**;
- expectation agreed with the base rate and lost anyway → an unlucky draw, and
  "fixing" it is fitting noise.

Base rates are computed from long history (1990–), never from the episodes being
judged — that circularity would be invisible.

**And the disagreement is now graded rather than asserted (G2).** The first
version returned a bare `True` whenever the historical P(up) sat more than 0.10
on the other side of a coin flip — an answer that read identically at
`n_effective` 44 and at `n_effective` 5.6. `base_rate.assess()` returns one of
three grades: **established** (the tendency is distinguishable from a coin flip
at the effective sample size), **suggestive** (the point estimate disagrees and
this bucket cannot establish it), **too_thin** (nothing can be said either way,
which is *not* evidence of agreement). Every `state_to_forecast_failure` in
dataset zero is currently **suggestive**.

## Dataset zero: the timing backtest

66 decisions, SPY, 2020-01 → 2025-06, 63-day horizon. **Conditional base rates,
1990–2026 — with the sample size they actually have (G2):**

| state | n | **n_eff** | episodes | P(up) | mean 63d | **MDE** | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| VIX < 15 | 2947 | 31.0 | 31 | 0.735 | +2.15% | 2.46 | below its own MDE |
| VIX 15–20 | 2777 | 44.1 | 72 | 0.686 | +1.76% | 2.85 | below its own MDE |
| VIX 20–25 | 1824 | 29.0 | 68 | 0.643 | **+1.56%** | 4.48 | below its own MDE |
| VIX 25–35 | 1248 | 19.8 | 54 | 0.732 | +4.60% | 5.31 | below its own MDE |
| VIX ≥ 35 | 353 | **5.6** | 19 | 0.731 | **+6.97%** | 15.27 | below its own MDE |

`n_eff` is the smaller of two corrections — overlap (`n / horizon`) and episode
clustering (occurrences more than 21 trading days apart) — because taking the
larger would let whichever correction happened to be gentler set the sample
size. **Not one row's mean is detectable at 80% power.**

### Is the U-shape a shape? (§18)

Five means in a column let the eye supply a curve. The U-shape is a claim that
the middle bucket is *lower than* the extremes, which is a **difference**, and
§18 requires differences to be tested as differences with their own SE. Each arm
against the trough (VIX 20–25):

| arm | diff | SE | t | MDE | verdict |
|---|---:|---:|---:|---:|---|
| VIX < 15 | +0.59 | 1.83 | 0.32 | 5.11 | not detectable |
| VIX 15–20 | +0.21 | 1.90 | 0.11 | 5.31 | not detectable |
| VIX 25–35 | +3.04 | 2.48 | 1.23 | 6.95 | not detectable |
| **VIX ≥ 35** | +5.41 | 5.68 | **0.95** | 15.92 | not detectable |

**No arm of the U is detectable.** The right arm — the +6.97% on which the whole
re-entry hypothesis rests — is `t = 0.95` against the trough. The shape may well
be real; this sample cannot establish it, and the earlier version of this
document asserted it from a column of point estimates.

### Does the panic add anything to the drawdown?

VIX ≥ 35 essentially never occurs except after a large fall, so the named
confound is that +6.97% is rebound from a depressed price rather than
information in the volatility. Measured, with "deep" = 15%+ below the trailing
252-day high:

| cell | n | n_eff | P(up) | mean 63d |
|---|---:|---:|---:|---:|
| deep drawdown, **no** panic | 851 | 13.5 | 0.522 | **−0.67%** |
| deep drawdown **and** panic | 283 | 4.5 | 0.696 | +6.59% |
| panic without the drawdown | 70 | 1.1 | 0.871 | +8.50% *(no MDE — unusable)* |

Panic's marginal contribution over the drawdown alone is **+7.25pp, SE 7.33,
t = 0.99 — not detectable.** But note the direction: buying a deep drawdown
*without* the panic earned −0.67% at a 52% hit rate, so the "it is only
mechanical rebound" explanation is **not** what the data shows either. Both
halves are honest and neither is established.

**Corpse control.** "Buy the VIX spike" is among the most published and most
traded rules in existence. Any Aegis re-entry mechanism must be measured against
that naive published rule before pre-registration, never against a strawman.

### The 66 decisions, restated

| group | vs ex-post best *(upper bound)* | **vs HOLD** *(unbiased)* | excess over matched null |
|---|---:|---:|---:|
| de-risking (5) | +26.54pp | **+13.87pp** | +10.53pp |
| adding (33) | +4.16pp | **−0.57pp** | +0.20pp |
| hold (28) | +6.55pp | 0.00pp | +1.20pp |

**The honest statement of the de-risking finding is "selling cost 13.87pp
against simply holding", not "+26.5pp of regret".** The direction survives; the
magnitude was roughly doubled by the denominator, and the vs-HOLD column is the
one with no selection bias in it at all.

Classification, on the calibrated gate:

| group | no_failure | state_to_forecast | forecast | timing |
|---|---:|---:|---:|---:|
| de-risking (5) | **4** | 1 *(suggestive)* | 0 | 0 |
| adding (33) | 30 | 0 | 3 *(suggestive)* | 0 |
| hold (28) | **24** | 1 *(suggestive)* | 2 *(suggestive)* | 1 |

The previous run labelled **all 5** de-risking decisions and **27 of 28** holds
as failures. That was the 1.0pp gate, not the engine: a blameless hold clears
1.0pp 93% of the time. Every surviving `state_to_forecast` label is marked
**suggestive**, meaning the base rate's point estimate contradicts the belief
and its effective sample cannot establish that it does.

### What this does and does not establish

It **does** convert an assertion into a measurement, twice over. The README said
for months that sells fired at VIX>25, "historically the best buying
opportunities" — a claim about a base rate nobody had computed, applied to
episodes nobody had replayed. Both now exist. And the second measurement is the
one that matters more: **the de-risking decisions cost 13.87pp against a
pre-declared HOLD**, which is a comparison with no maximum-over-a-menu inside it.

A finding nobody was looking for: the **adding** decisions — the celebrated
67.4% hit rate — score **−0.57pp against HOLD** and **+0.20pp of excess over the
null**. Buying on the signal was indistinguishable from simply staying invested.
The old denominator hid this completely, because +4.16pp of raw regret looks
like a result until you learn that doing nothing scores about the same.

It **does not** establish that any fix works, and now it establishes rather less
than the first version claimed. The obvious next hypothesis — *extreme stress +
falling volatility + still-depressed price is a re-entry state* — rests on an
arm of a curve with `t = 0.95` and on 19 crises, is a rule already widely
published, and will fit this history beautifully. It leaves the Gym only through
wall 3.

## What is deliberately NOT built

**WORLD-MODEL-v1 is authorized in principle** as of 2026-08-15 (Murat's call,
reversing R7) but is **gated** and is not scaffolded: it waits for known-answer
worlds, a correctly denominated episode/regret substrate, and declared simple
baselines. Never all-data → NN → BUY/SELL. It waits
for the episode dataset and for RESEARCH-GYM-1 to produce transfer-tested
candidates. When it comes, the division stays: **LLM teaches meaning, market
teaches weights, Aegis judges truth.**

**AUTOPSY-TO-RULE-1 and the REGRET_TENSOR are built** — see
`docs/AUTOPSY_TO_RULE_1.md` for what they do, the defect the first live run
produced, and the first six mechanisms (0 exportable; one at 2 of its 3
required transfer slices). What follows is the original statement of intent.

**AUTOPSY-TO-RULE-1 (R5)** is the next headline: given a resolved episode and its
surface, Optimus proposes a structured hypothesis — contemporaneous evidence and
post-outcome evidence kept *separate*, a proposed mechanism, an executable rule —
and the rule is then evaluated only on foreign crashes, stocks and decades. The
episode substrate it needs now exists.

## Running it

```bash
# 1. the matched null FIRST — without it every regret number below falls back
#    to the biased denominator and the uncalibrated 1.0pp gate
python -m scripts.gym_build_matched_null

# 2. dataset zero, with lineage
python -m scripts.gym_dissect_timing --write
```

Writes `backend/data/optimus/research_gym/dataset_zero_<stamp>.jsonl` (one line
per episode: the full record plus the full surface) and appends a lineage row.
