# RESEARCH-GYM-1 — phase 1

**Registered** 2026-08-15 in `Aegis module/TRIALS/registry.jsonl`, once, as a
campaign. **Charter:** `docs/HANDOFF_OPUS5_2026-08-15.md` R2–R5.
**Code:** `backend/services/research_gym/`. **Tests:** `test_research_gym.py` (30).

> Everything in this document that carries a number is **Gym output**: a
> hypothesis, not a result. No figure here may appear in a README claim, a
> track-record surface, or a funding argument. That is wall 1, and it is
> enforced by a type that raises rather than by this paragraph.

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

## Dataset zero: the timing backtest

66 decisions, SPY, 2020-01 → 2025-06, 63-day horizon. **Conditional base rates,
1990–2026:**

| state | n | P(up \| state) | mean 63d |
|---|---:|---:|---:|
| VIX < 15 | 2947 | 0.735 | +2.15% |
| VIX 15–20 | 2777 | 0.686 | +1.76% |
| VIX 20–25 | 1824 | 0.643 | **+1.56%** |
| VIX 25–35 | 1248 | 0.732 | +4.60% |
| VIX ≥ 35 | 353 | 0.731 | **+6.97%** |

**The relationship is U-shaped, not monotone.** The worst forward returns follow
the *middle* bucket; the best follow the *highest-stress* bucket. The signal
engine fires sells above VIX 25 — precisely where history most strongly says to
be long.

**All 5 de-risking decisions classify as `state_to_forecast_failure`.** Mean
regret against the best available alternative **+26.5pp**; median realised
63-day return **+15.6%**; the best alternative was `buy_50` in 4 of 5.

The classifier is not degenerate — it discriminates. Within the 28 HOLD
decisions the same test splits 7 `state_to_forecast` against 7 `forecast`
(unlucky), plus 8 sizing and 5 timing.

### What this does and does not establish

It **does** convert an assertion into a measurement. The README has said for
months that sells fired at VIX>25, "historically the best buying opportunities".
That was a claim about a base rate that nobody had computed, applied to episodes
nobody had replayed. Now both exist, and the mechanism is more specific than the
sentence was: it is not that stress is bullish, it is that the map from stress to
expected return is **non-monotone** and the engine assumed it was monotone.

It **does not** establish that any fix works. This is Gym output on data this
project has studied for months. The obvious next hypothesis — *extreme stress +
falling volatility + still-depressed price is a re-entry state, not an exit
state* — is exactly the kind of rule that will fit this history beautifully. It
leaves the Gym only through wall 3.

## What is deliberately NOT built

**WORLD-MODEL-v1 is not authorized** (Order 7) and is not scaffolded. It waits
for the episode dataset and for RESEARCH-GYM-1 to produce transfer-tested
candidates. When it comes, the division stays: **LLM teaches meaning, market
teaches weights, Aegis judges truth.**

**AUTOPSY-TO-RULE-1 (R5)** is the next headline: given a resolved episode and its
surface, Optimus proposes a structured hypothesis — contemporaneous evidence and
post-outcome evidence kept *separate*, a proposed mechanism, an executable rule —
and the rule is then evaluated only on foreign crashes, stocks and decades. The
episode substrate it needs now exists.

## Running it

```bash
python -m scripts.gym_dissect_timing --write     # dataset zero, with lineage
```

Writes `backend/data/optimus/research_gym/dataset_zero_<stamp>.jsonl` (one line
per episode: the full record plus the full surface) and appends a lineage row.
