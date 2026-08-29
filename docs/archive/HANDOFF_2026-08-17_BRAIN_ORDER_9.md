# ORDER — brain → builder (order 9)

Binding. 47 commits unpushed on `aegis-finance`, 6 on the module, both trees
clean. The paid IIF night is Monday 2026-08-17, **target 18:30 local (UTC+8) =
10:30 UTC**, outer bound 20:20 local = 12:20 UTC.

---

## 0. On running the night early — the code already answered, and the answer is no

Murat asked whether the night could be moved earlier so he can sleep. **It
cannot be moved to now, and it should not be moved to the earliest legal
moment.** Checked rather than judged:

```
next XNYS open      Mon 2026-08-17 13:30Z
now                 Sun 2026-08-16 18:02Z
lead                19.47h   vs MAX_PREOPEN_LEAD_HOURS = 18
```

`assert_night_fits_preopen` raises `NightWouldSpanTheOpen` **right now**. The
earliest legal start is **19:30 UTC Sunday = 03:30 local Monday**.

And it should not run then either, for a reason the guard is not built to see.
The primary contrast is `A_snapshot` vs `B_tools` — *does live investigation
beat a frozen snapshot?* The tool arms' entire advantage is **fresh
information**. Sunday 19:30 UTC is the quietest information moment of the week.
Starting at the 18-hour edge hands the arms under test the least informative
window available, which pushes the primary contrast toward the null **for a
reason that has nothing to do with the hypothesis.** The guard is a floor on
validity, not a recommendation; the trial's premise is *shortly before the
session*, and 18:30 local is three hours before the bell.

**There is also no conflict to resolve.** It is 02:00 local Monday. The target
is **18:30 local Monday — this evening, sixteen hours after Murat wakes.**
Sleeping now costs the night nothing. Keep the declared target.

---

## 1. The wheel does not pay, and that is the session

**206 predictors, net of 10bp, 2006–2019: median −0.12%/yr. BH-FDR keeps 11.
Exactly one is detectable net in the liquid tercile, at 1.01× its own MDE.
Momentum's gross spread is +0.40%/yr. HML, PEAD, BAB and reversal are all
negative net. None of the eight measured seeds survives.**

This is the direct, measured answer to the question Murat has asked twice — *if
there is a working method, adopt it; we do not have to reinvent the wheel.* We
went and got 209 published predictors and measured them on our own panel under
our own standard. **The wheel does not turn in the names we can trade.**

And your framing of what that implies is right and is the more important half:

> *"The factory's bar is not 3%/yr from momentum — there is no established
> published benchmark in the tradable tercile at all. That cuts both ways, and
> the second way matters: the standard that keeps killing our stuff has now been
> applied to the incumbents."*

**Ruling: this validates the standard rather than indicting it.** It is
Novy-Marx & Velikov reproduced — most anomalies do not survive trading costs —
and it is consistent with Chen & Zimmermann's own replication work and with
McLean–Pontiff decay. Our number agrees with the literature's honest
self-assessment. The standard is calibrated correctly and the eighteen months of
kills it produced were not excessive rigour.

**But it forces a decision we have deferred for three sessions, and it should be
taken now.** Our execution standard is *net excess CAGR ≥ +3%/yr*. Essentially
nothing in the published literature clears that bar in tradable names. So either
the bar comes down, or **the product's claim is not about return at all** —
and §59 has been saying the second for three sessions:

> Risk outcomes are ~30× closer to resolution than return outcomes on identical
> data. You measured that ratio this session.

**Order: the execution standard is amended to declare its outcome.** A RETURN
claim keeps the +3%/yr bar and is understood to be, on present evidence,
unreachable on this corpus. A RISK claim — drawdown, tail, exposure control —
carries its own bar, its own MDE, and the break-even return sacrifice that E8
made a reusable primitive. **The product Murat runs is a risk product with an
honest return statement, not a return product.** Write that into
`docs/OPTIMUS_OBJECTIVE.md` and stop quoting a bar nothing has ever cleared as
though it were the target.

### The new failure mode you found is not "fails after costs"

`std_turn` at +18.28% has a **median of two valid names per month in the liquid
tercile against 546 overall**. Your sentence is the finding: *"it is not a
strategy that fails in large caps; it does not exist there."* That is a distinct
verdict from a cost kill and it needs its own name — **`NO_POPULATION_IN_SCOPE`**:
the universe where the effect lives and the universe where we can act do not
intersect. It reproduces G4's cost finding independently on an unrelated corpus,
which is what makes it worth a verdict rather than a footnote.

---

## 2. M4 refused to spend the window, and that is the best thing this programme has built

**+8.64%/yr against an MDE of 12.84% over the 74 reserved months. Ruling: do not
spend.** This is §19 applied *prospectively*, and the property that makes it
usable is the one you named:

> *"Asking cost nothing — the calculation uses the selection window's SE and a
> count of months, and a month count is not an outcome."*

**Canon, and it is now mandatory:**

> **A power check that consumes no outcome is free, and therefore obligatory
> before any confirmation.** Compute the MDE from the selection window's SE and
> the reserved window's length; if the MDE exceeds the effect, refuse. A test
> whose MDE exceeds its effect returns whatever the world does, and afterwards
> the window is gone and nothing was learned.

**This is the question N9 was never asked.** The programme spent eighteen months
learning that lesson by paying for it, and it has now built the machine that
declines to pay again. Nothing else this session matters as much.

**Erratum to §59, and it is mine.** My canon reads *"max drawdown ~4 yrs,
terminal return ≈95 yrs."* You report that the **~30× ratio reproduces and the
4-year figure does not — and that it rested on exactly one crisis.** The ratio
survives; the absolute number is withdrawn. A resolution estimate resting on one
crisis is one draw, not a rate. §59 is amended to state the ratio and to state
that the absolute figure is unestablished.

**N18 is answered, and it is null.** 0 of 16 timing effects detectable against
matched-constant-exposure controls; the drawdown reduction is average exposure.
Order 4 said a null here would matter enormously, and it does:

> **The four-way convergence collapses to "target constant volatility." That is
> a product, not a discovery, and the programme should stop citing four findings
> that reduce to one.**

Say it plainly in the next status document. It is also, usefully, the exact
claim a risk product is entitled to make.

---

## 3. Five self-caught defects, and two of them are canon

**Detectable was compared gross while the table printed net** — cutting tradable
survivors from four to one. A comparison and a display in different units is the
house failure mode wearing new clothes, and it changed the headline.

**The k_eff measurement was measuring the random number generator.** Unpaired
bootstrap streams returned ρ̄ = 0.002 across sixteen cells that are four
λ-variants of two statistics **on one path** — obviously wrong, and only obvious
because you knew what the cells were. Paired streams give **k_eff 1.08**, i.e.
sixteen tests cost the budget roughly one. Canon:

> **A bootstrap that resamples independently per cell measures the resampler,
> not the dependence.** Any ρ̄ feeding an effective-count must come from paired
> streams, and a ρ̄ near zero between things that share a path is a bug report
> about the estimator, not a finding about the world.

That one lands directly on Order 8: the module's conservative default forces
ρ̄ = 0 when unmeasured, which is the right direction — and now that it is
*measured* at high correlation, those sixteen cells stop consuming a budget they
never should have consumed.

**Order 8's guard contract found a swallowed error on its first run** —
`lookAheadInMatching` caught and raised nowhere, §47 one step earlier, **in the
module the factory batch runs through next.** A template ordered eighteen hours
ago found a live defect on the path of the next piece of work. Keep it and
extend it to every guard in the module.

**And the pre-push gate has a real hole you worked around rather than closed.**
Its sibling check diffs against HEAD, so *"unchanged — nothing to run"* reports
success for a reason unrelated to the question — the §56 family exactly. You ran
the sibling suite by hand (775 green) so tonight is covered, **but fix the gate
itself after the push**: a pre-push check that silently skips the sibling repo's
unpushed commits will be trusted the next time by someone who did not read this.

---

## 4. What happens next

**Tonight, Murat's keystrokes:** the paid night at **18:30 local**, population
named in the receipt beforehand, no source edit on the critical path · campaign
`--commit` · the `LIVE_FORWARD` quarantine.

**After it, same evening:** `verify_before_push` → push 47 + 6 → **verify prod
on the new commit.**

**Then, before IIF-1 accrues:** Railway sleeping (receipt count over three days)
· the missing IIF-1 grader module · `check_read` deriving `n_graded_nights`
· the pre-push sibling hole.

**Then M6 — the page, and it is now the priority.** The routed research line is
complete and it terminated in a chain of measured negatives. That is not a
setback; it is the information needed to build the right product. We now know,
measured on our own panel:

- return prediction does not clear its bar, ours or the literature's;
- risk control does resolve on this data, ~30× sooner;
- constant-volatility targeting is what the four convergent findings actually
  say;
- the honest claim shape is *"risk reduced by X; return effect not established,
  break-even sacrifice Y."*

**Build the page around that.** Murat's portfolio, the exposure the risk layer
would hold at his declared λ, what it would have held at each of the last N
decision points and what that cost or earned, and the one thing that would
change its mind. Not a research console. This is the three-month deliverable and
the research just told us what it is allowed to say.

---

## 5. Standing

Added by this order:

- **A power check that consumes no outcome is free, and therefore obligatory
  before any confirmation.**
- **`NO_POPULATION_IN_SCOPE`** — the universe where the effect lives and the
  universe where we can act do not intersect. Distinct from a cost kill.
- **A bootstrap that resamples independently per cell measures the resampler.**
- **§59 erratum:** the ~30× risk-vs-return resolution ratio reproduces; the
  "~4 years for drawdown" figure is withdrawn — it rested on one crisis.
- **The execution standard must declare its outcome.** A +3%/yr return bar that
  nothing in the published literature clears is not a target, it is a statement
  about the asset class.

— brain, 2026-08-17
