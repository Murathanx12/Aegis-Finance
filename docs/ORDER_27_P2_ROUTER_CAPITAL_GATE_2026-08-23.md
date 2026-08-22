# ORDER 27 P2 discharged — the G1 correlated-worlds battery, and what it found

**Date:** 2026-08-23 · **Commits:** this session · **Status:** gate BUILT and
ENFORCED; the live router **FAILS** it and is therefore **not licensed** for
capital authority beyond v1's aggression knob.

ORDER 27 P2 declared the gate:

> RELIABILITY_ROUTER gains no capital authority beyond v1's aggression knob
> until a correlated-worlds battery (hundreds of worlds, clustered by decision
> date, correlated names, regime blocks) passes at ≤5% null recommendation AND
> reports null-world capital exposure.

That sentence is now code on both sides: a battery that measures
(`scripts/g1_correlated_battery.py`) and a gate that refuses
(`backend/services/router_capital_gate.py`).

## 1. The world, and why its own integrity is tested

v1's known-answer battery planted one ticker per decision with each name's
fate drawn independently. That world does not exist. The v2 world carries the
three structures ORDER 27 named:

| property | v1 | v2 |
|---|---|---|
| decisions per date | 1 | 8 names × 3 actors, same morning |
| name outcomes | independent | latent day factor, loading ρ = 0.6 |
| vol regime | absent | persists in 4-day blocks, loads by beta, scales the factor |
| actors | 1 | 3 sharing one market (the router actually *chooses*) |

Measured on the built world, not assumed: **within-day variance inflation
8.6×**, marginal null hit rate 0.481 (0.50 planted, inside clustered sampling
error), vol terciles populated 120/120/120 with no UNKNOWN_VOL.
`backend/tests/test_g1_correlated_world.py` pins all three — a battery whose
planting is wrong is correct arithmetic against the wrong world, which is the
house failure mode.

## 2. What the battery found (300 null / 80 edge / 80 harmful worlds)

Measured out-of-sample on seed `77771111`, after the estimator work below was
developed against a different seed.

| | live v1 (shipped) | v1.1 (correction ON) | bar |
|---|---|---|---|
| null recommendation rate | **0.293** [0.245, 0.347] | **0.030** | ≤ 0.05 |
| null capital exposure, deployed | 0.293 | 0.030 | reported |
| …given deployed | 1.00 | 1.00 | reported |
| edge recovery (p=0.62, 16 days) | 0.788 | **0.188** | ≥ 0.70 (added) |
| harmful leak | 6/80 = 0.075 | 2/80 = 0.025 | ≤ 0.05 (added) |

**The live router recommends in 29% of worlds where nothing is there**, and in
every one of those worlds 100% of the capital a consumer would deploy goes to
an actor with no edge. This is not hypothetical exposure: `engine.py:166` reads
the router's verdict and sizes `ce_kelly` books at full declared aggression
instead of `abstain_kelly_factor` whenever it says RECOMMENDED. The knob is
being flipped by noise roughly three times in ten.

v1's high "recovery" (0.788) is not power. It recommends nearly everything;
finding the real edge is a by-product of a bar low enough to find edges that
are not there.

## 3. Why v1 fails, in three defects — each measured, not argued

The first correction was not enough and the reason is worth recording, because
each intermediate number was a plausible stopping point.

1. **Standard error priced off rows, not decisions.** The reported SE
   understated the actual dispersion of the router's own estimate by **2.03×**.
   Dividing each cell's rows by the design effect its own decision-date
   clustering measures got the null rate only 0.387 → 0.303.
2. **Effective counts added across cells that are the same mornings.** The
   three vol_state cells of one actor are three views of the same decision
   days; summing their effective counts counts every morning three times.
   Measuring the design effect **once per actor over deduplicated decisions**
   brought SE calibration to **0.98** (from 2.03) and the per-actor
   false-positive rate to 5.0%.
3. **No multiplicity control across actors.** A calibrated 5% per-actor bar,
   applied to a best-of-3 choice, is ~14% per world. The router's entire job is
   picking the best of *m*; canon §63 requires multiplicity control for exactly
   this shape everywhere else in the codebase. The corrected bar is Bonferroni
   in the number of actors and scales itself as the arena gains model_ids.

A fourth defect surfaced only once the first three were fixed: with the trust
bar correctly raised, almost everything lands in `NO_EDGE`, whose fallback
funded **any actor not *proven* harmful** — handing a truly harmful actor
(0.35 against a 0.50 prior) a third of the weight in **half of all harmful
worlds**. Failing to reject harm is not evidence of safety. Under v1.1 the
fallback funds only actors whose own estimate is at least the prior, and holds
no capital at all if none is: leak 40/80 → 3/80.

**Zero harmful leak is not attainable and v1's battery only ever claimed it
because its world was easy.** On a few dozen independent decisions a harmful
actor sometimes looks fine. The bar is now a rate with an interval — ORDER 27's
own instruction ("quote the cost rate or don't quote the count") applied to the
metric that prompted it.

## 4. The cost, stated plainly: the arena has nowhere near enough evidence

Under v1.1 the false-trust rate is controlled — and power at the live arena's
breadth is near zero. Recovery of a genuine 0.62-hit actor, by world size:

| clustered decision days | 16 | 32 | 64 | 128 |
|---|---|---|---|---|
| edge recovery | 0.18 | 0.38 | **0.80** | 0.95 |

The 70% crossing sits between **32 and 64 decision days** — at the battery's
2-session stride, roughly **six months of live arena** before the router can
detect an actor that is genuinely 12 points above chance. Both settings
therefore fail the gate today, for opposite reasons: **v1 on false positives,
v1.1 on power.** That is the true state of the router, and it is the honest
answer to "may it size capital": not yet, and here is the number of days.

This restates §59 (risk resolves ~30× faster than return) at the routing
layer: correlated decisions buy far less information than their row count
suggests, and the only axis that buys more is *days*, not names per day.

## 5. What shipped, and what is attended

**Shipped (live behaviour unchanged):**

- `scripts/g1_correlated_battery.py` — the battery, ~0.15 s/world, receipts
  stamped `KNOWN_ANSWER_BATTERY`.
- `backend/services/router_capital_gate.py` — `assert_router_licensed`.
  Refuses on: missing/unreadable receipt · not a known-answer battery · wrong
  gate · **router fingerprint mismatch (estimator hashed by SOURCE, since every
  correction above lives in a function body and moves no constant)** · fewer
  than 200 null worlds · rate above bar · unreported capital exposure ·
  recovery below floor · leak above bar.
- `reliability.design_effect` / `_actor_clustering` — the counting brain now
  measures the clustering the router cannot see, and reports `n_decisions`,
  `deff`, `n_clusters`, `n_effective` per cell and per actor.
- `trust_router` v1.1 behind **`CLUSTER_ADJUST_DEFAULT = False`**.
- 33 tests (`test_router_capital_gate.py`, `test_g1_correlated_world.py`, one
  guard-contract case). Fast suite 5,341 passed.

**Two conditions the ORDER did not state** were added to the gate and are
declared rather than smuggled: a recovery floor (without it a router that never
recommends anything passes perfectly) and a harmful-leak bar. Both can only
make the gate stricter.

**ATTENDED — Murat's keyboard:** flipping `CLUSTER_ADJUST_DEFAULT` to `True`.
Every v1.1 change rides on that one flag, so the decision is single and
coherent, and the gate **refuses the v1.1 receipt while the flag is off** ("a
battery passed under a setting that is not switched on is a description of a
router nobody is running"). It is attended because the router's verdict is in
a live book's sizing path: flipping it makes `ce_kelly` books more conservative
more often, which is one live NAV series describing two policies mid-segment
unless the change is taken deliberately.

The recommendation is to flip it. v1's measured behaviour is a 29% false-trust
rate with full capital exposure behind it; v1.1's is 3% with the power to find
nothing yet. Between a router that is wrong and a router that is silent, the
silent one is the one that can be improved by waiting.

## 6. Live pins

`test_the_live_router_is_not_licensed` asserts the shipped receipt FAILS at the
live fingerprint, and `test_the_corrected_receipt_licenses_nothing_until_the_flip`
asserts the v1.1 receipt is refused while the default is off. If either turns
green without the corresponding work being done, the gate has inverted and
every refusal in it is decoration.
