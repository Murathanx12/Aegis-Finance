# FINDING — 2026-08-24: the mediator is trivially predictable and carries nothing

**Trial** `REVISION-FORECASTER-1` — roadmap item C of the external review
**Pre-registration** `Aegis module/TRIALS/PREREG_REVISION_FORECASTER_1.md` @ `d81577e`, corpse-linted **PASS**, committed before the target column existed anywhere
**Receipt** `backend/data/optimus/revision_forecaster/receipt.json`
**Code** `scripts/revision_forecaster_v1.py` · 8 tests

## Verdict: **STOP**, on the registered rule, exactly as the registered prior predicted

The pre-registration recorded: *"I expect this to fail on Q3 and I am running it
anyway."* It failed on Q3, and on Q1, and the way it failed is worth more than
the verdict.

---

## 1. The chain, measured link by link

The proposal was to stop asking *event state → return* and insert the mechanism
that is supposed to do the work:

```
event state  ──(1)──▶  next analyst consensus revision  ──(2)──▶  price response
```

| link | measurement | IC | t |
|---|---|---|---|
| **(1)** event state → revision | `numeric_surprise_pct` → `revision_raw` | **+0.623** | **+60.4** |
| **(2)** revision → subsequent return, *timed correctly* | `revision_raw` → `fwd5` from `t1` | +0.0028 | +0.21 |
| | `revision_raw` → `fwd21` from `t1` | +0.0071 | +0.48 |
| **composition** | `numeric_surprise_pct` → `fwd21` | −0.0005 | −0.04 |

**Link 1 is nearly deterministic. Link 2 is not there. The composition is zero.**

An earnings surprise predicts what analysts do next with a rank correlation of
0.62 — that is mechanical, and it is the part of the idea that obviously works.
It buys nothing, because the component of the revision that a public numeric
surprise explains is precisely the component the market has already priced.

## 2. The registered questions

| | | result |
|---|---|---|
| **Q1** (precondition) | does the realised revision rank subsequent returns? | **NOT ESTABLISHED.** +0.0028 (h5) / +0.0071 (h21), both far under MDE80 ≈ 0.037–0.042 |
| **Q2** (precondition) | is the revision predictable from event state? | **YES, overwhelmingly** — but only in the component that carries no return information |
| **Q3** (deciding) | does routing beat direct prediction on returns? | **STOP.** Every paired cell under its MDE80 |

Q3's paired differences, routed − direct:

| cell | difference | paired SE | realised ρ | paired MDE80 | band |
|---|---|---|---|---|---|
| ridge h21 | +0.0051 | 0.0143 | +0.26 | 0.0401 | STOP |
| lightgbm h21 | −0.0005 | 0.0196 | −0.03 | 0.0548 | STOP |
| ridge h5 | +0.0146 | 0.0138 | +0.35 | 0.0387 | build-and-watch |
| lightgbm h5 | −0.0522 | 0.0174 | +0.11 | 0.0488 | STOP |

No arm survived BH-FDR at q ≤ 0.10 across the eight declared arms.

**The equivalence statement the canon requires:** this design resolves no
routed-minus-direct effect smaller than **≈0.04**, so the STOP bounds the
decomposition rather than refuting it.

## 3. The registered power calculation was wrong, and by how much

The pre-registration declared a paired MDE80 of **0.0158**. The realised value
is **0.039–0.055** — two to three times worse. Two causes, both worth carrying:

* **The realised dispersion of a monthly rank IC exceeds its null dispersion by
  ~45%.** I derived `outcome_dispersion` from the sampling noise of a Spearman
  IC (1/√(n−1) per month → 0.0873). The realised sd is ~0.125, because monthly
  ICs have genuine time-variation on top of sampling noise. **A comparable
  prior measurement was available and I did not use it:** `EVENT-RESPONSE-2`
  reported MDE80 0.0276 on this same panel, which is close to what actually
  happened.
* **The paired arms do not correlate.** I assumed ρ = 0.8, which would have cut
  the paired SE to 0.63× the single-arm SE. Realised ρ is **−0.03 to +0.35**, so
  the pairing *raised* the SE to ≈1.3× instead. The pre-registration required
  the recomputation and the code does it from the realised paired differences
  directly, so the verdict was never read against the wrong number.

That low ρ is itself informative rather than merely inconvenient: **a model
trained on the mediator produces a nearly uncorrelated ranking to one trained on
the outcome.** The decomposition really does make a different bet. This sample
simply cannot say whose bet is better.

**Rule for the next pre-registration in this family:** derive
`outcome_dispersion` from a realised prior measurement on the same panel, never
from the theoretical null. The null understates it by ~45% here.

## 4. The instrument was wrong once, and it produced a t of 4.04

**This is the part to remember.**

The first implementation of Q1 scored the revision against returns measured from
the **event**. But `t1` — the post-event IBES cut where the revision is observed
— sits a median of **20 calendar days** after the event, well inside both the
5-session (~7 days) and 21-session (~30 days) windows. The revision was being
scored against a return that had already happened when it was observed.

It looked excellent:

| | contaminated (from event) | correct (from `t1`) |
|---|---|---|
| `revision_raw` → fwd5 | +0.0454, **t 3.56** | +0.0028, t 0.21 |
| surprise-orthogonal residual → fwd5 | +0.0504, **t 4.04** | +0.0108, t 0.81 |
| surprise-orthogonal residual → fwd21 | +0.0396, **t 2.98** | +0.0041, t 0.27 |

I had already written the interpretation: *the predictable part of the revision
is priced, the residual carries the alpha, and that is the quantitative case for
building the transcript model.* It was a good story, it was consistent with the
mechanism, and **it was entirely an artifact of window overlap** — analysts and
the market responding to the same news over windows that intersect.

It cost two minutes to check, and the check was "is `t1` inside the return
window?" A t of 4.04 is precisely the number nobody goes back to re-examine.

The contaminated figures are kept in the receipt under
`contaminated_from_event_DO_NOT_CITE`, and `test_revision_forecaster.py` pins
the timing so the bug cannot return silently.

**This is the fourth instrument defect this session and the most consequential**
— after the graph work's mis-specified `n_eff` gate, its single-null-draw
comparison, and the options rate-regime subset of one month. All four were found
by running the instrument and asking what it actually measured.

## 5. What this buys, and it is not nothing

`ANALYST-IBES-1` (2026-08-11) already recorded EPS revision breadth as dead net
(max net t 0.88). This adds the *event-conditioned, gross, properly-timed*
version and it agrees: **in this sample analyst EPS revisions do not carry
forward return information once you stop letting them see the return.**

That is a coherent picture across two independent trials, and it closes a route
that looked open.

**For roadmap item B (`MANAGEMENT_EVASION_DELTA_v1`)**, the honest reading is
weaker than the one the contaminated run would have supported. It does **not**
now come with "and the residual revision is worth IC 0.05". What survives:

* the mediator is trivially predictable from the numeric print, so a text model
  that merely predicts the revision is predicting something already priced;
* if the call text is worth anything, it must be worth it **against returns
  directly**, or against a revision component this trial could not isolate;
* B remains blocked on a transcript source in any case — nothing in this
  repository has earnings-call text, and FMP/Bigdata acquisition is unpriced.

## 6. Where a SCREEN gets registered, since the skill's step 2 does not apply

`pre-register-trial` step 2 says to insert a row into `rule_experiments` and
check `cumulative_trials` incremented. **That table is for forward-accruing lane
trials** — insider, congress, ARK, fragility, LPPLS, smartgrowth — each with a
live clock and an earliest-decision date. Checked: **no screen in this
programme registers there.** `EVENT-RESPONSE-1`, `EVENT-RESPONSE-2`,
`GRAPH-BACKBONE`, `RELATIVE-VALUE-NN` all live in the prereg folder alone.

For a historical screen the register IS
`Aegis module/TRIALS/PREREG_*.md`, and the corpse linter reads it: it scores
against "148 graveyard rows, the trial registry **or the prereg folder**". This
trial is in that corpus. Recorded here so the next session does not re-litigate
it, or worse, write a forward-trial row for something with no forward clock.

## 7. What was not done, and why

The routed model was not re-run against the *residual* revision as a training
target. That would be selecting a target after seeing which decomposition
looked good — and the decomposition that looked good was the contaminated one.
Any successor needs its own pre-registration and a mediator whose timing is
declared relative to the return window before a number exists.

## 8. The lesson

**Predicting a mediator well does not imply predicting the outcome well** — the
pre-registration said so in its honest prior, and the measurement made it
concrete: a link of 0.62 composed with a link of ~0 gives ~0.

And the practical one: **when a mediator is observed at time `t1`, the only
honest return window starts after `t1`.** Everything else measures the
mediator's own past.
