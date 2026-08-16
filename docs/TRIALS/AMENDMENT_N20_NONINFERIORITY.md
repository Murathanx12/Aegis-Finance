# AMENDMENT — N20: the second test a null owes, and the diagnostic its explanation owes

**Registered:** 2026-08-16, after N20's registered verdict was produced and
reported, and **before** either computation below has been run.

**This amendment does not change N20's verdict, and may not.** The registered
primary metric, its decision rule, and its `NOT_DETECTABLE_IN_SCOPE` outcome
stand exactly as reported. Changing them after seeing the answer is the thing
this programme exists to prevent.

What it adds is the **half of the null that was owed and not paid**, and a
**diagnostic for an explanation I asserted without testing**.

---

## 1. The owed test: non-inferiority against the rescue threshold

The standing canon is:

> A null owes TWO tests: *could we have seen it* (MDE), and *have we excluded
> what would have mattered* (equivalence against an economically derived
> margin).

N20 paid the first. Its power gate compared the **width** of the 90% interval on
`Δ = E[R|fire,¬tail] − E[R|¬tail]` against the required difference, and reported
`NOT_DETECTABLE_IN_SCOPE` when the width exceeded it. That is a statement about
resolution, and it is correct as far as it goes.

It is not the statement the handoff made. The handoff wrote:

> the estimand lever is **closed**

Closing a route is an **exclusion claim**, and an exclusion claim requires a
one-sided bound against the threshold that matters — not an interval-width
check, and certainly not the sign of a point estimate.

### The test

The rescue requires the conditional mean to fall far enough to bring `L_min`
below N9's confirmed lift of 1.271. Inverting the frozen formula gives a
required difference `Δ*`, already computed in N20 from the registered formula
before any conditional statistic existed:

```
Δ* = μ_rest_needed − μ_rest_uncond   =   −0.642 pp   (20d, cost = 0.0010)
```

Let `LCB₉₅(Δ)` be the one-sided 95% lower confidence bound on `Δ` from the
**same** moving-block bootstrap N20 already ran — same seed, same blocks, same
shared block starts across the six co-moving securities, so the bound carries
both the temporal overlap and the cross-sectional dependence.

| condition | verdict |
|---|---|
| `LCB₉₅(Δ) > Δ*` | `RESCUE_RULED_OUT` — the slice **excludes** a fall large enough to rescue N4B. The estimand lever is closed, and the word is earned. |
| `LCB₉₅(Δ) ≤ Δ*` | `RESCUE_NOT_EXCLUDED` — the slice cannot rule it out. `NOT_DETECTABLE` stands and the handoff's "closed" must be withdrawn. |

**Conservatism, declared before the number:** the percentile bootstrap is not
the only defensible bound, and a claim to have *closed* a route should be hard
to earn rather than easy. Both the percentile bound and the basic
(reverse-percentile) bound `2Δ̂ − q₉₅` are computed, and **the lower of the two
decides**. Where they disagree, both are printed.

**Weakest-cell reporting is inherited**, unchanged: the verdict is the weakest
produced anywhere in the cost × block-multiplier grid.

### What this test may NOT do

- It may **not** upgrade N20's registered verdict. `NOT_DETECTABLE_IN_SCOPE`
  was the answer to "can this slice resolve the difference", and it still is.
- It may **not** be reported as a new finding about the world if it comes back
  `RESCUE_NOT_EXCLUDED`. That outcome is a statement about the slice.
- `RESCUE_RULED_OUT` closes **one** lever — the estimand. Convex-payoff hedging
  and the objective are untouched by it and remain open, as Order 5 §1 states.
- It carries N20's slice provenance intact: a re-analysis of a consumed
  exploration slice, never confirmation.

---

## 2. The owed diagnostic: is the volatility explanation actually the mechanism?

N20 reported the observation and then asserted a mechanism:

> precursors fire in high-volatility states, and high-volatility states that do
> not produce a tail are the ones that rebound hardest

The observation is measured. **The mechanism is not.** It is a plausible story
formed after seeing the sign, which is the exact shape of the explanations this
programme discards when other people offer them.

### The test

Stratify the shared calendar by **prior-day `realised_vol_20d`** into terciles
computed **within each security** (so the strata are not simply a security
ranking), and recompute the same difference `Δ` **within each stratum**.

| outcome | reading |
|---|---|
| `Δ` shrinks toward zero inside every stratum, while the pooled `Δ` is positive | the pooled difference is a **composition effect** — firing days are drawn from high-vol strata, and high-vol non-tail days pay more. The stated mechanism is **supported**. |
| `Δ` survives at roughly pooled size inside strata | volatility composition does **not** account for it; the stated mechanism is **not** supported and the explanation must be withdrawn or replaced by one that is tested. |
| strata are too thin to say | `DIAGNOSTIC_UNDERPOWERED` — the explanation stays labelled a hypothesis. |

**This is a diagnostic and decides nothing.** It cannot change any verdict, it
cannot rescue N4B, and a supportive result licenses the word "consistent with",
never "because". Its only job is to determine whether a sentence in the handoff
is a finding or a guess — and if it is a guess, to say so in the handoff.

No bootstrap decision rule is attached to it, deliberately: adding one would
invite it to be read as a fourth verdict. Point estimates and counts per
stratum are printed and interpreted as directional only.
