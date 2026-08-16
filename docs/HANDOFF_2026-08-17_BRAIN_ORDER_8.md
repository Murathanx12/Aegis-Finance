# ORDER — brain → builder (order 8)

Binding. Verified against code at `243a00d`. 42 commits unpushed on
`aegis-finance`, 6 on the module. **The paid IIF night is TODAY** — Monday
2026-08-17, target ≈18:30 local (UTC+8), outer bound 20:20 local = 12:20 UTC.
It is ~18 hours out as this is written.

---

## 1. You corrected my order, and the correction is the better rule

I ordered a sweep for **one-day close-to-close windows**. That was the wrong
axis and you said so with the count attached: there are 150, flagging them would
have produced noise, and a guard that flags 150 things gets switched off — after
which it protects nothing.

**The axis is arrival relative to the last moment you could act, not the
horizon.** A signal computed from Monday's close and acted on at Monday's close
loses no gap, because the information preceded the action. `gap_is_lost(arrival)`
refusing an **undeclared** arrival rather than defaulting to benign is the right
shape, and it makes "every event result reports its tradable fraction" mechanical
instead of a rule someone has to remember.

Canon, and it is the mirror of *don't let the kill machinery become the
programme*:

> **Strictness in the wrong direction is not free.** A guard whose false-positive
> rate is high is a guard that will be deleted, and a deleted guard has a
> protection rate of zero. Precision is a safety property, not a convenience.

**And the lift sweep's result is the honest one.** 424 ratios, 29 artifacts,
zero unreportable, N9's denominator 35 SE from zero. The reason matters more
than the verdict: **N9 divides by a fire *rate* (0.1599), not by a mean return.**
Rates sit far from zero structurally; mean returns sit near it by construction.
So the refusal I ordered is real and its blast radius is small, and both halves
of that belong in the record. A sweep that finds nothing and explains *why* it
found nothing is worth more than one that finds nothing.

**The two self-corrections inside the audit are the item to act on.** It first
emitted a clean verdict on a missing input — the R13e failure mode, inside the
tool built to prevent that class — and first reported "no base rate recorded"
for the one number it was ordered to check. This family has now recurred often
enough to deserve a mechanical answer rather than another lesson:

> **Every guard ships with a test that feeds it a missing, malformed, or absent
> input and asserts a REFUSAL — never a pass and never a clean verdict.** Make it
> a shared test template so it cannot be forgotten. `n_effective = n` made false
> kills; a missing input making a clean pass is the same defect wearing the other
> sign, and we have now seen it in the tool built to prevent it.

**The cost result closed the chain and the prediction held in both halves.**
Monotone in liquidity, detectable only in the illiquid tercile at +0.83pp,
break-even 20.7bp per crossing on $11M-ADV names, four crossings because it is
long-short, before borrow and impact. Mid below MDE, liquid negative. That is
Ng/Rusticus/Verdi reproduced rather than cited, and §62 is earned rather than
asserted. **The G4 chain terminates in a negative and that is a result** — three
sequential, separately-measured reasons the same effect does not become money.

---

## 2. The ruling you asked for: the two windows share six years

You surfaced it rather than leaving it to be found, which is why it is fixable.
`window_id` puts the outcome in the identity deliberately, citing §59 — and that
citation is **correct about power and silent about error rate.**

- §59 is about **resolution**: max-drawdown resolves on this slice in ~4 years
  and terminal return needs ~95. Spending one genuinely does not spend the
  other's power. That reasoning holds.
- **Family-wise error is a different quantity.** M4-SELECTOR and
  IV-ORACLE-GAP-1 both confirm on 2020-06-01..2026-07-17. Same calendar, same
  COVID crash, same 2022 drawdown, same 2023–25 rally. Their test statistics are
  **correlated**, so two budgets of five do not give FWER 0.05 twice — they give
  something worse than 0.05 once, and neither trial's Holm correction can see
  the other.

Neither extreme is right. Full sharing means six years supports five tests for
the entire programme forever, which kills everything and would be deleted within
a month (§1's own rule). Full separation is what we have now, and it understates
the error rate.

**We already own the primitive.** §58's design effect is not about samples — it
is about correlated units, and tests are units:

```
effective_tests = k / (1 + (k−1)·ρ̄)      ρ̄ = mean correlation of the test
                                            statistics on the shared calendar
```

**Order:** the budget attaches to the **calendar window**, and outcomes within it
count at their **effective** number, not their raw one. Two outcomes with ρ̄ ≈ 0
count as two; with ρ̄ ≈ 1 they count as one. Where ρ̄ can be estimated from
history, estimate it and record it with the budget; where it cannot, **declare a
conservative ρ̄ and say that it was declared** — the honour-system failure is
declaring nothing and letting independence be the silent default.

This is the same sentence as §58 pointed at a different axis: **n_effective
counts correlated units, and it does not stop counting when the units are
hypotheses instead of dates.**

---

## 3. What is left, in the order it happens

### Today — Murat's keystrokes, attended

1. **The paid IIF night.** Target ≈18:30 local, hard outer bound 20:20 local
   (12:20 UTC). **Name the evidence population in the receipt before the run.
   No source edit on the critical path.** One attempt.
2. **Campaign `--commit`** (110 due / 110 resolvable / 0 unpriceable, SHA
   `ff458c77…`).
3. **The `LIVE_FORWARD` quarantine** — this is what clears DEGRADED.

### After the night, same evening

4. **`python -m scripts.verify_before_push` → push 42 + 6 commits → verify prod
   on the new commit.** In that order, and the third step is not optional: the
   skill exists because a green CI and a live deploy are two different facts.

### Before IIF-1 accrues — not before tonight, but before any read

5. **Railway sleeping.** Verify by **receipt count over three consecutive days**,
   never by `scheduler.running` — that field describes the process answering the
   question.
6. **There is no IIF-1 grader module at all.** The read gate cannot detect a
   grading pipeline that never ran.
7. **`check_read` must derive `n_graded_nights` from the ledger it can see, or
   refuse.** Taking it as an input is the last honour-system guard we know about.

### The research line, resuming after the push

8. **The PIT characteristics pull.** Shared infrastructure for both the factory
   and the library.
9. **Measure the strategy library** (M3) — ten literature-specified specs, our
   panel, net of costs, with `decay()` comparing our-in-sample to
   our-post-publication. This is the benchmark the factory's output must beat and
   the shortest path to something Murat can use.
10. **The first factory batch** (M2), scored on `market_reaction_tradable`,
    handed the surprise rather than the EPS sign.
11. **M4 the selector** — which method, when, at what size, under which declared
    λ. The actually-novel piece, and its confirmation window is already reserved.
12. **M5 replay as the standard evaluation, M6 the page Murat uses.**

### On tonight specifically

You stopped short of the pull on a freeze assumption tighter than the real one.
The night is ~18 hours out and my declared idle deadline is **14:00 local
(06:00 UTC)** — thirteen hours from now. **Start the pull with a hard stop at
14:00 local.** If it is not finished, kill it and resume after the night; the
pull is resumable and the night is not. Verify the machine is idle at 14:00
regardless of how the pull ended.

Do not push. Do not touch production, IIF, NAV, or the live registry.

---

## 4. Standing

Added by this order:

- **Strictness in the wrong direction is not free** — a guard with a high
  false-positive rate is a guard that gets deleted, and precision is therefore a
  safety property.
- **Every guard ships with a test that feeds it a missing input and asserts a
  refusal.** Shared template, not per-guard discipline.
- **n_effective does not stop counting when the units are hypotheses instead of
  dates.** Budgets attach to the calendar window; outcomes count at their
  effective number with ρ̄ declared or measured, never assumed to be zero.

And the one worth saying out loud on a day the programme's flagship chain
terminated in a negative: **three separately-measured reasons an effect does not
become money is a result, and it is the kind this project exists to produce.**
The alternative was believing the +1.88%.

— brain, 2026-08-17
