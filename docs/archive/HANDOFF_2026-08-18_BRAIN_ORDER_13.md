# ORDER — brain → builder (order 13) — the night ran, the loop that learns from it does not

Binding. Tree clean at `fe6c743`, **0 unpushed**, prod verified live. Night 1
completed: `ok`, `void_reason none`, 585 records, $0.919725 against a $12.00
ceiling. **The run is a success and the most valuable thing in it is a defect.**

---

## 1. The timing model was wrong in both inputs, and the safety came from the wrong place

```
calls per cell     declared 4.8    actual 7.09    actual is 48% HIGHER
concurrency eff    declared 2.0    measured 3.53  actual is 76% HIGHER
projected 69.6 min                 actual 115.4 min
```

*(Your table labels the first `-48%`; the direction in your prose is right and
the sign in the table is not. On the one number whose sign decides whether a run
spans the opening bell, write it as "actual/declared = 1.48".)*

**Your reading is correct and I want to sharpen where the margin actually came
from, because it was not where either of us thought.** I recomputed with the
true call volume:

```
conc=1 (the pessimistic branch), 4.8 calls/cell      139.2 min
conc=1 (the pessimistic branch), TRUE 7.09           205.6 min
as-run wall clock                                    ~133   min
```

So the pessimistic branch was **pessimistic on concurrency while carrying a
stale constant on the other axis**, and the two errors happened to leave the
truth inside the envelope. **That is not a guard working. That is one
conservative axis absorbing an unmeasured error on a different axis, which is
luck with a receipt attached.** Had calls-per-cell come in at 9 rather than 7.09,
the truth would have sat *above* the pessimistic branch and nothing in the
system would have noticed.

Canon, and it is the generalisation of Order 11 rather than a repeat of it:

> **Being conservative on one input does not make a projection safe. A guard
> must derive every input it multiplies, or state which ones are declared and
> refuse to be quoted as validated.** `MEASURED_CALLS_PER_CELL = 4.8` had the
> word *measured* in its name and was 48% wrong.

**The forward consequence, which changes tonight's schedule:** once the constant
is corrected to 7.09, the guard at `conc=1` refuses any start after **10:04Z =
18:04 local**.

```
ordered start 17:05 local  ->  59 min inside the pessimistic bound
actual  start 17:44 local  ->  20 min inside it
```

**It launched 39 minutes late, unattended, and that ate two thirds of the
margin.** Not a failure — but the slip is unexplained and an unexplained 39
minutes on a slot with a hard right edge is the next incident. Find out why it
slipped before the campaign arms.

---

## 2. The bug that costs five times its size, and it has a direction

`[B_tools/ICE]` died on `dict(call.get("args"))` — a model-emitted `args` that
was not a mapping. One cell in 200 (0.5%) removed **2.5%** of the contrast,
because the pairing key spans ticker × observable × horizon × threshold and a
dropped cell is dropped from every arm. **You are right that this is the matched
design working correctly.** The part to act on is the part you named last:

> **It can only strike tool-using arms. So it is not noise — it is a bias with a
> direction, and the direction is against the arms under test.**

The primary contrast is `A_snapshot` vs `B_tools`. A failure mode available only
to B biases the estimate **toward the null**, which is the direction that looks
like a clean negative result. At 1 cell in 200 the magnitude is small; the
principle is not.

**Order:** harden the parse, and **report per-arm failure counts in every
receipt.** A contrast whose arms had different failure rates carries a
directional bias term, and it is stated with the result or the result is not
reportable. Same shape as §62's tradable fraction: a number that must accompany
the estimate rather than be available on request.

---

## 3. P0 — the loop that learns from all this is open at both ends

Prod warns `/app/.../predictions.jsonl` holds records absent from the
authoritative ledger at `/data/...`, and the count moved by exactly **585** —
Night 1's own output. Meanwhile the resolver is asleep: **25 overdue, 0
resolved.**

**This is a recurrence.** `80bcfa5` is titled *"The receipts were written where
nothing could read them."* We fixed that once, and the fix was **path-specific
rather than structural** — so the same class returned through a different writer.

> **A write path is not verified by the write succeeding.** The test is that the
> authoritative reader can see the record. Every writer of forward evidence
> asserts a round-trip through the path the resolver actually reads, or it is
> writing to a place it has not proven anything can read.

Two independent failures that compound into one: **nothing this programme
produces forward is currently being resolved.** Night 1's forecasts are safe in
git and are not in the resolution path; they would not be scored even if the
resolver woke up. **This is P0 and it outranks every timing fix**, because until
it closes, every night we buy is a receipt nobody grades.

---

## 4. Your two errors — both are recurrences of canon, which is the useful part

**`timeout … | tail` handed you `tail`'s exit code.** Our standing rule is
literally *"The exit code IS the guard"*, and a pipeline discards every exit code
but the last. Add `set -o pipefail` or capture `PIPESTATUS`, and treat *"the
readiness run reported success"* as unproven wherever a pipe stands between the
command and the check.

**The abort monitor grepped `Traceback` and cried wolf on a handled per-cell
error.** The mirror of Order 8: a monitor with a high false-positive rate is a
monitor that gets ignored, and an ignored monitor has a detection rate of zero.
Match on the *unhandled* marker, not on the word.

---

## 5. What is left, in the order I would take it

1. **The `/app` → `/data` ledger gap, and the sleeping resolver, as one unit.**
   They are the same loop. Acceptance: a Night-1 record round-trips into the
   authoritative ledger *and* is resolved on its due date, **verified by receipt
   count on three consecutive expected dates — never `scheduler.running`.**
2. **`dict(model_args)` hardening + per-arm failure counts in the receipt.** Cheap,
   and it removes a directional bias from every future night.
3. **Derive `arm_concurrency` and `calls_per_cell` from the last N receipts**, with
   the missing-input refusal test. Not "raise the constants" — derive them, and
   have the guard refuse when it cannot.
4. Dead tickers · telemetry · Railway migration (after the resolver passes its
   own acceptance test, per Order 12).

**Still reserved for Murat and still not authorised by "run the night":**
campaign `--commit` and the `LIVE_FORWARD` quarantine. H1 stays unread.

---

## 6. The campaign may now be armed — bounded, not open-ended

Order 12 said automation begins *"the moment a campaign declares how many nights
it is buying and against what."* **IIF-1 declares 40, and the economics are now
measured rather than assumed:** $0.92/night, $12.00 ceiling, 62 fundable against
40 required.

So the condition is met, and the ruling changes accordingly:

> **Arm the pre-open slot for exactly 40 nights with a hard counter that stops
> itself, not for "every night".** The counter is derived from receipts written,
> not from a config someone decrements. When it reaches 40 it stops and the
> campaign is read once, under the declared budget.

Three conditions on arming, all from tonight's evidence: the guard runs at
`conc=1` **with the corrected 7.09**, which puts the last safe start at 18:04
local · the launch fires at **17:05**, and a slip past 17:30 aborts the night
rather than compressing the margin · **the resolver passes §5.1 first**, because
40 unresolved nights cost $37 and teach nothing.

---

## 7. On replicating this in the mornings — the honest constraint first

Murat is right that the evening is spent and the morning is free. **But the one
thing that cannot be backtested is the thing this trial is about.**

> **You cannot backtest an LLM investigator on history, because the model's
> weights already contain the outcome.** Point a tool-using arm at 2019 and its
> advantage over the snapshot arm is not investigation — it is recall. The
> knowledge cutoff *is* a look-ahead leak, and it is not fixable by prompt
> hygiene, because it is not in the prompt.

That is why IIF-1 is a forward trial and it is why it costs money. What the
mornings **can** do, in descending order of value:

- **Score the design, not the content.** Build the resolution and pairing harness
  against synthetic and historical records so that the moment §5.1 closes, 585
  records grade themselves. This is the highest-value morning work available and
  it is what makes the 40 nights worth buying.
- **Backtest the mechanical arm.** `A_snapshot`'s features → forecast mapping is
  a model, not an investigator, and it replays honestly on history under the Gym
  charter with the reserved windows untouched.
- **Post-cutoff windows only** for anything involving the LLM, and stated as such
  — a narrow, real, and shrinking resource.
- **Replicate the statistics**: MDE, `k_eff`, pairing loss under cell failure.
  Tonight showed a 0.5% cell failure costing 2.5% of the contrast; nobody had
  computed that multiplier in advance, and it is computable without a single
  paid call.

**Answering the question underneath his question:** the paper lanes accrue NAV
daily and will keep accruing — but *learning* requires resolution, and resolution
is asleep with 25 overdue. **Right now the lanes are recording, not teaching.**
§5.1 is what turns that back on, which is why it is P0 rather than housekeeping.

---

## 8. Standing

- **Conservative on one input is not safe.** Derive every input a projection
  multiplies, or mark the projection declared and refuse to quote it as validated.
- **A failure mode available to only one arm is a bias, not noise**, and its
  direction is reported with the estimate.
- **A write path is proven by the authoritative reader seeing the record**, never
  by the write returning success. Round-trip or it is unwritten.
- **A pipe discards the guard.** `pipefail`, or the exit code you checked is not
  the exit code you meant.
- **An LLM's knowledge cutoff is a look-ahead leak that prompt hygiene cannot
  reach.** Forward trials are not a preference for rigour; they are the only
  available instrument.

— brain, 2026-08-18
