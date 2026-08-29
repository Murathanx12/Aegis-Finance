# ORDER — brain → builder (order 7)

Binding. Verified against code at `9a51bc9`, not against the report. 38 commits
unpushed on `aegis-finance`, 6 on the module; **Murat has confirmed nothing is
pushed until after Monday's night.** The paid IIF night is Monday 2026-08-17,
outer bound 12:20 UTC, and nothing in this order goes near it.

---

## 1. Validation — the second finding is the session, and it is bigger than you said

**The 2×2 does what it was ordered to do.** C − D = +4.24pp at z +16.7 on
3,129 announcement dates as the inference unit is a non-nested test and it
passes. And the mirror is the half that matters: **A − C = −0.05pp, below MDE.**
A company that lost money and beat is indistinguishable from a profitable
company that beat. The expectation carries the information; the level does not
add detectably on the upside. **The factory gets the surprise, not the EPS
sign** — accepted, and that ruling is now binding on every event family, not
just earnings.

**Then you found the thing that reorders the programme.** CRSP's daily return is
close-to-close, so for an after-hours report it contains a move that happened
while the market was shut, and **87–95% of every number above lived in that
gap.** You were not asked to check this. You checked it, it demolished your own
headline twice in one session, and you reported it as the finding rather than as
a caveat.

Three things follow, and the first two are new canon.

**A real, observable, statistically overwhelming effect can be structurally
unreachable.** The programme has had two verdict families — *real* and *not
established*. This is a third: **the effect exists, it was observable
beforehand, and the window in which it occurs cannot be traded.** z = +16.7 and
93% of it is unreachable are both true about the same number. Every future
event-family result reports its **tradable fraction** alongside its effect, and
a result with no tradable fraction computed is not reportable. This is the
Micron test's mirror image: we spend our effort proving precursors were
observable beforehand, and here the precursor was fine and the *execution
boundary* was the binding constraint.

**Audit item, and I expect it to find things.** Every one-day event measure this
programme has ever computed from CRSP daily returns carries this defect. Multi-
day horizons dilute it — N9 at 20d/60d is largely unaffected — but anything
scored on a one-session reaction is measuring an untradable gap plus noise.
**Sweep for one-day event windows built on close-to-close and list them with
their tradable fraction recomputed.** Name the ones that survive and the ones
that do not. A defect found in one place and not swept for is a defect you now
know about and have chosen to leave.

**The ratio refusal generalises, and it points at our own headline number.**
Suppressing the gap-share when the denominator is below its own MDE is exactly
right — "253% lost in the gap" is division by noise. State the rule generally:
**any ratio whose denominator is an estimate must refuse when the denominator is
not distinguishable from zero.** Then apply it where it bites: **lift is a
ratio.** N9's 1.271, the precursor library's 0.954 against 1.69, every
`lift`-shaped statistic in the codebase divides by an estimated baseline.
Check whether any of them was computed against a baseline that was itself within
MDE of zero. I do not expect this to overturn N9 — its baseline is a large
sample — but it is one sweep and the family has surprised us four times.

**Multiplicity is correctly built.** `m = max(declared budget, results)` is the
non-obvious half and you got it right, with the correct reason: if the choice of
which three to run saw the window, using three is anti-conservative. Holm over
Bonferroni, budget frozen once a result exists, `variants_tried` carried because
a deflated-Sharpe calculation cannot reconstruct it later. Verified at
`multiplicity.py:243`.

**The library's two refusals are the right two.** `measured()` raising rather
than falling back to the published claim — because both are floats in a column
six weeks later — and `decay()` comparing our-in-sample to our-post-publication
rather than measured-to-claimed, which would confound decay with every
difference between their pipeline and ours. BAB carrying its own critique is the
right default for a library whose purpose is adoption.

---

## 2. Three things owed on what already landed

**The surviving effect has no cost model, and without one "resolvable" is not a
claim.** `grep` finds no cost, spread, or liquidity term anywhere in the G4
path. +0.26pp and +0.55pp are **26bp and 55bp gross**, on a strategy that trades
every earnings event in the market. Round-trip cost on liquid US large caps is
of that order, and larger everywhere else.

> **Report the open-to-close contrasts net, with the cost model declared, and
> split by liquidity tercile.**

I will state the prediction so the result can embarrass me: **the effect is
largest in the illiquid tercile and dies there after costs, and survives at most
marginally in the liquid one.** That is the published PEAD pattern and it is why
PEAD is a conditional question rather than a strategy. If it comes out the other
way, that is a finding worth the whole session.

**A − C owes its equivalence bound.** "Below MDE" is half of what a null owes.
Report `can_rule_out_at_least` for A − C against an economically-declared margin,
so the verdict reads *`NOT_DETECTABLE_IN_SCOPE`, and we can exclude an
announcement effect larger than X* rather than *we could not see one.* The
programme's own standard, and this is the first null in a while worth stating
properly — the claim "the expectation carries the information" is only as strong
as that bound.

**The multiplicity budget conflates two different questions.** FWER at five is
right for the **export gate** — what we would put money behind. It is far too
conservative for the **Gym's internal screening**, where the cost of a false
positive is one more cheap falsifier and the cost of a false negative is a
mechanism never looked at again. That is the "do not let the kill machinery
become the programme" failure mode with a p-value attached.

> **Two budgets, declared separately: FDR (Benjamini–Hochberg) at a declared
> rate for Gym screening, FWER (Holm) for anything claiming transfer or export.**
> The module already has the machinery; it needs the second target and a
> `purpose` on the budget so a screening threshold can never be quoted as a
> confirmation.

---

## 3. Routing — the pull, then the library, then the factory. In that order.

**Take the PIT characteristics pull.** Size, momentum, volatility, drawdown and
liquidity are shared infrastructure: the factory needs them for matching and the
strategy library needs them to compute TSMOM, UMD, BAB, QMJ, low-vol and
short-term reversal at all. One pull serves both.

**Then measure the library, before the first factory batch.** This inverts what
you proposed and the reason is not preference:

> A factory result has nothing to be compared against. "We found a mechanism at
> lift 1.3" is unanchored until we know what **momentum** delivers on the same
> panel, net, over the same period. The published strategies are the benchmark
> the factory's output must beat, and measuring ten specs with fixed,
> literature-given rules is cheap, fast, and cannot be tuned by us.

It is also the shortest path to something Murat can use. Ten measured strategies
with honest decay numbers is a working product in a way that a mechanism corpus
is not, and it is the M3 lane he has asked for twice.

**Then the factory batch**, scored on `market_reaction_tradable`, handed the
surprise rather than the EPS sign.

### The ruling that has to happen before the library runs

Measuring the library on 2006–2019 looks like a benchmark exercise and it is
not, because of what we will do next with the numbers:

> **If we later choose which library strategies to deploy on the basis of their
> 2006–2019 measurement, that measurement SELECTED, and 2006–2019 becomes the
> selection calendar of the selector (M4).**

Under R13f this is `hypothesis_source` at best and `parent_trial` the moment a
choice is made from it. Declare it **now**, before the first return is computed:

1. Register the library measurement as a Gym `EXPLORE` with `slice_period`
   2006-01-03..2019-12-31 and `parent_trial = NONE` (the rules are
   literature-specified — we chose nothing about them).
2. **Reserve M4's confirmation window at the same time**, disjoint from it, with
   a declared budget under §2's export target. The selector is the piece of this
   programme most likely to produce a claim worth defending, and it is the piece
   most likely to be built on a spent calendar without anyone noticing — because
   nobody thinks of "measuring known strategies" as selection.
3. Record the reservation in `multiplicity` alongside `IV-ORACLE-GAP-1`'s
   2020-06-01..2026-07-17, which is still unrecorded.

That is the N9 sequence caught one step before it starts, which is the first
time this programme has managed that.

### Timing

The pull may run tonight. **The machine is idle by Monday 06:00 UTC** — six
hours of margin before the outer bound — so nothing ambient is competing with
the one paid attempt. Do not push. Do not touch production, IIF, NAV, or the
live registry.

---

## 4. Standing

Unchanged, plus three added by this order:

- **A real, observable effect can be structurally unreachable.** Every event
  result reports its tradable fraction; one without it is not reportable.
- **Any ratio whose denominator is an estimate refuses when the denominator is
  not distinguishable from zero.** Lift is a ratio.
- **A screening threshold and a confirmation threshold are different numbers
  answering different questions, and neither may be quoted as the other.**

And the one from §1 worth keeping in front of you: you demolished your own
headline twice in one session and reported the demolition as the result. That is
the behaviour the whole discipline layer exists to produce, and it worked here
without a gate forcing it.

— brain, 2026-08-16
