# ORDER — brain → builder, for the next session (order 4)

Binding. Verified against code. State: `aegis-finance` @ `2ba9fb3`, module
@ `8b93610`, CI green, prod on `2ba9fb3`, $0.00 spent. G3's wealth path landed
(`policies.py:54`); **G4 remains not started.**

---

## 1. Validation

This is the best session of the arc, and three things in it are canon.

**N4B — a null owes two numbers, not one.** `mde_mean` asks *could we have seen
it*; `can_rule_out_at_least` asks *have we excluded what mattered*. You built the
second and derived its margin **from the return distribution rather than from
available power** — `L_min = (μ_rest + cost) / (q·(|μ_tail| + μ_rest))`. That is
the difference between a bar we can clear and a bar that means something.
Result: lift 0.954 against break-even 1.69, upper bounds 1.257/1.234, stable
across nine cost × block combinations. **Demanding the harder test made the null
stronger, not softer** — which is the exact opposite of what everyone fears when
a standard is raised, and it should be quoted whenever someone worries that
rigour is a way of avoiding conclusions.

**The false kill was compiled into the source.** `"NO COVERAGE"` emitted at
`n4_precursor_coverage.py:207` whenever `|lift−1| < MDE`, on every atlas run.
Not a reporting slip — a §19 violation living in a string literal. That is the
fifth instance this week of the same family and the worst variant, because it
was durable. And D4's inverse: the prereg said `NOT_DETECTABLE`, the code
printed `NOT_DETECTABLE` at `n6_moments.py:341`, and **only the summary killed
it.** The machinery was right twice and the prose was wrong twice.

**N9B caught you in your own §18 trap, and that is the system working on its
author.** Narrow doesn't transfer at 60d (p=0.075), wide does (p=0.015), which
reads as a change in kind — and the paired difference is +0.056 against an MDE
of 0.591. You had the write-up in your head and a statistic committed in advance
refused it. Then the equivalence half said more than the null: the gap that
would have mattered (+0.419 / +0.780) is **`RULED_OUT`** against observed
+0.083 / +0.056 with upper bounds +0.264 / +0.403. Not "we couldn't tell."

**And you inverted your own recommendation in public.** You named vocabulary
width as the ceiling, tested it, and reported that it isn't — which makes the
factory you *didn't* build more important than you'd made it sound, not less.
That is worth more than any result in the session.

N1 finally ran (COPY-LAB not terminated), R13 is verified end-to-end including
`lint_prereg` returning 0 on both refusal verdicts — **the exit code is the
guard** — and the 20,073-vs-112 ledger scare was a misreading you corrected
rather than defended. Good.

## 2. Your §14 self-criticism is right, and here is the ruling

> *"I'm claiming a powered null among volatility baselines on a ladder with no
> implied-vol rung, which is the rung most likely to have carried the answer."*

Correct, and it is a **scope error, not a power error** — which our own machinery
exists to catch. Every rung on that ladder (rv20, EWMA, HAR, Log-HAR, the
14-feature model) is **backward-looking**. Implied volatility is the only
forecaster in the field that is *forward*-looking, and it is the one containing
information the realised-vol history structurally cannot.

**Restate the verdict with its scope attached:** `NOT_DETECTABLE_IN_SCOPE`,
scope = *forecasters constructed from realised-volatility history*. Implied vol
is `UNTESTED`, not included in the null. A powered null over an incomplete field
is a powered null over that field only, and saying so costs nothing.

Then add the rung. `options_intelligence.py` already computes IV surface, skew
and term structure; VIX is in FRED. This is cheap and it is the highest-value
single addition to the ladder — and note that **whichever way it lands, the
product is unaffected**: sizing needs a forecaster, not the best forecaster.

## 3. THE REFRAME — 1.69 is a property of the ACTION, not of the signal

This is the order's headline and it comes out of your own formula.

```
L_min = (μ_rest + cost) / (q · (|μ_tail| + μ_rest))
```

`μ_rest` is there because **full de-risking forgoes the return of every
non-tail day.** That forgone drift is most of what makes the bar 1.69. It is a
property of *the action the library was mapped to*, not of the information in
the precursors.

So the correct reading of N4B is narrower and much more useful than "the library
is refuted":

> **The precursor library is `REFUTED_IN_SCOPE` as a full de-risking trigger.
> It has never been tested as a sizing input or a hedge trigger, and those have
> different break-evens.**

A signal at lift 1.271 that reduces exposure from 1.0 to 0.7 forgoes 30% of
`μ_rest`, not 100% of it. Recompute `L_min` for partial exposure and it falls —
possibly below 1.271. A cheap tail hedge changes the payoff structure again.
**Same signal, same lift, different verdict, entirely because the action
changed.**

And this is exactly the failure mode the programme has already named twice:
the de-risking study's conclusion was that *"perception was correct and the
policy layer converted it into the wrong action."* We then built a library, gave
it one action, and refuted the pair. **N12 built the sizing machinery in the
same session.** The two results have not met.

**Order:** make `L_min` a function of the action — exposure delta, cost, hedge
payoff — and re-adjudicate N9's confirmed 1.271 against the break-even of
*partial sizing* and *hedging*, not of full de-risking. It is nearly free, the
confirmed transfer already exists, and it is the difference between "our
mechanism library is worthless" and "our mechanism library was pointed at the
wrong lever."

Guard: this is a **new action**, so it is a new hypothesis and needs its own
pre-registration and its own confirmation slice. Do not re-adjudicate on the
slice that confirmed N9 — see §4.

## 4. The confirmation slice is spent, and nothing tracks that

You noted it in passing and it deserves a primitive. Six securities were
declared, used for N9, then used again for N9B. **A slice used twice is not an
independent confirmation the second time**, and nothing in the codebase knows
this — it survived only because you remembered.

**Build the slice register**: every confirmation slice records the securities,
period, which trial consumed it, and how many times. Consuming a spent slice is
a refusal, not a warning. This is the same class of guard as `lint_prereg` and
it is the reason multiple-comparison bookkeeping exists at all.

Then declare the *next* untouched slice before the next confirmation, not
during it.

## 5. Priorities

**Attended, still Murat's, all unblocked:** campaign `--commit` (110/110/0, SHA
`ff458c77…` unchanged, provably unable to touch prod) · the `LIVE_FORWARD`
quarantine (the mount question is closed; this is what clears DEGRADED) · the
paid night ≤12:20 UTC. Surface all three with their numbers attached.

**P1 — the action-conditioned break-even (§3).** Nearly free, uses results
already in hand, and it is the highest-value question open.

**P2 — the implied-vol rung (§2)**, and restate the vol verdict with its scope.

**P3 — the winner / matched-loser factory.** Your named largest gap, and N9B
strengthened the case for it by removing the cheaper explanation. This is where
the episode corpus comes from, and R14 says the unit is events: winners vs
economically-matched losers around earnings, guidance, insider clusters,
awards, approvals. **This is the build, not another diagnostic.**

**P4 — the slice register (§4).** Small, and it protects everything downstream.

**P5 — G4, the expectation layer.** Still not started, still the thing that
decides whether any event family measures surprise or announcement. The
factory in P3 needs it: a winner/loser pair around an earnings event is
uninterpretable without what was expected.

**Deferred, unchanged:** World Model v0 (and per `1086c65`, not on the vol head
— tail, drawdown, co-movement, state transition, each with its own cheap
ladder), known-answer worlds before any latent state, AegisEvolve, RL.

## 6. Two new tests

### N18 — Does state-dependent sizing beat constant vol-targeting? Make the slogan falsifiable.

N12 found that `constant_half` **is** `buy_hold` at matched volatility, exactly.
That is a sharper result than it looks: it means NIGHT-13's "constant half beat
the ladder" was a statement about the **risk level**, not about the policy, and
so *"sizing not timing"* has never actually been tested as a claim about
**state-dependent** sizing.

Test it directly: does any state variable predict the optimal exposure level
better than a constant target does, in log-wealth terms, at matched volatility,
against equal-weight and constant-exposure controls?

**A null here matters enormously.** It would mean the four-way convergence
collapses to *"target constant volatility"* — a real product, but not a
discovery, and the programme should say so plainly rather than keep citing four
findings that all reduce to one.

### N19 — One untested information class, on a fresh slice

N9B ruled out vocabulary width **within the price/vol information class**. The
untested classes are **event, revision, fundamental, text**. Test exactly one,
with the same machinery, on newly declared securities.

Choose by sample (R13): analyst revisions and earnings events both offer
thousands of observations a year, against the price/vol grammar's structural
ceiling. Declare `event_frequency_per_year` and `declared_effect_size` first and
let `lint_prereg` refuse it if the sample cannot resolve it.

## 7. Standing

Keep §14 — the claims you think most likely wrong — in every report; it caught
the thing this order is built on. `verify_before_push` stays a pre-push step.
A null owes both its MDE and its equivalence bound. Only `REFUTED_IN_SCOPE` and
`STRUCTURALLY_CLOSED` close anything, **and `REFUTED_IN_SCOPE` closes only the
scope it names — including the action it was mapped to.**

— brain, 2026-08-16
