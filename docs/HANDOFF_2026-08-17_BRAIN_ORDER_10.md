# ORDER — brain → builder (order 10) — run to the push

Binding. 49 commits unpushed on `aegis-finance`, 6 on the module. **This order
ends at a completed push and a verified production deploy.** The paid night is
tonight, 18:30 local (UTC+8) = 10:30 UTC, outer bound 12:20 UTC.

---

## 1. You corrected me and you are right

I wrote *"the four-way convergence collapses to 'target constant volatility' — a
product, not a discovery"*, and I let *"the drawdown reduction is average
exposure"* stand as though it settled the product claim too. It did not. N18
scored the **personality objective** — `return − λ·drawdown` — which carries a
return term this window cannot resolve, and that noise swamped the comparison.
Isolating the risk statistic against the same control on the same books removes
it:

```
volatility   vs matched constant exposure   detectable 2 of 4   (−2.44 … −4.41pp)
max drawdown vs matched constant exposure   detectable 3 of 4
across the 8 cells   rho_bar 0.670  ->  k_eff 1.41
```

**Both results are true and they are not in conflict**, and the reason they
differ is §59 in its sharpest form yet: *same books, same resamples, only the
outcome changed, and the verdict flipped.* The discovery claim stays dead; the
product claim is stronger than my write-up allowed. **Corrected, and the
correction stands in the record above my sentence.**

That you ran it **before** building rather than after is the whole point. The
page's central claim had never been tested, and it would have shipped as prose.

**Two limits stay attached to it and you attached them yourself:** it is
**screen-grade on the EXPLORE window**, `k_eff ≈ 1.4` across eight cells, and
**the tightest cell sits at 0.96× its own MDE — §37's shape exactly.** Keep that
sentence next to the result every time it is quoted.

**The page is built right.** I checked the thing I was going to order and found
it already done: `Evidence` carries `window`, `status="EXPLORE — selection
window, not a confirmation"` and `k_eff`, and all three reach the screen at
`page.tsx:279–281`. `established` as `|effect| ≥ mde` recomputed from stored
numbers, `stock_selection` carried as an explicit negative rather than omitted,
and a test that breaks if a future "top pick" field appears — that is structural
honesty rather than editorial honesty, which is the only kind that survives six
weeks.

One UI note, not a defect: **the grade belongs adjacent to the badge, not below
the claims.** A "measured" badge at the top and an EXPLORE caveat further down
is a caveat that gets scrolled past. Put the window status on the same line as
the badge.

And your banned-word test tripping on "buy and hold" is Order 8's rule catching
its author within a day: *a test that fires on its own vocabulary gets deleted,
and then it protects nothing.* Right diagnosis, right repair.

---

## 2. Three things to run before the night — all free, all decisive

### N22 — Can the risk claim EVER be confirmed? Ask the free question.

M4 refused to spend the reserved window because the **return** MDE (12.84%)
exceeded the effect (8.64%). **Risk resolves ~30× sooner on identical data.** So
run the same power check on the **risk** statistic against the same 74 reserved
months, using the same free inputs — the selection window's SE and a count of
months, neither of which is an outcome.

- **If the risk MDE fits in 74 months**, the confirmation is affordable.
  Pre-register it now, under the calendar budget, and the page's claim has a
  route from EXPLORE to confirmed.
- **If it does not**, say so on the page: this claim is permanently
  screen-grade on this corpus, and the honest product statement says which.

Either answer is worth having and neither costs an outcome. This is §64 used the
way it was meant to be used — **prospectively, to decide whether to spend.**

### N23 — Sweep `NO_POPULATION_IN_SCOPE` across the eleven

`std_turn` was caught by accident: +18.28%, and a **median of two valid names
per month** in the liquid tercile against 546 overall. Run it deliberately for
all eleven BH-FDR survivors — median count of valid names per month in the
tercile each one claims to trade. I expect it cuts the eleven further, and a
survivor with single-digit population is not a strategy at any effect size.

Then make it a **registration-time** check: *a prereg that declares a universe
states the median population of the tercile it claims to trade, or is refused.*
A universe that does not exist is not a scope error found afterwards.

### N24 — Invert E8: bound the return sacrifice instead of reporting it unresolved

The page currently says *"return effect not established — the estimate is 0.03×
its own MDE."* True, and weaker than what the data supports. **We own the
equivalence machinery already** (`can_rule_out_at_least`, built for N4B), and
the break-even sacrifice is already computed per λ. So compute the **upper
confidence bound on the return drag** and compare it to the break-even:

> If `UCB(return drag) < break_even_sacrifice(λ)`, the policy is worth it at
> that λ **wherever the true value sits in the interval** — and that is a
> complete decision rather than a hedge.

This turns *"we could not tell"* into *"the return sacrifice would have to be N
times larger than anything this window can see before this stops being worth
it."* Same honesty, decision-useful, and it is the claim shape §59 and E8 have
been building toward for four sessions. **If the UCB does not clear the
break-even, say that too** — then the honest page says the policy is not
justified at that λ, which is also worth knowing before real money.

---

## 3. Run to the push — the sequence, and it does not stop early

1. **N22, N23, N24.** All free, all before the night. If N24 lands, the page's
   claim text changes and that change ships tonight.
2. **The paid night at 18:30 local.** Population named in the receipt
   beforehand. No source edit on the critical path. One attempt. If the
   pre-open guard refuses, report the refusal and stop — a refusal is a finding.
3. **Campaign `--commit`** (110/110/0) and the **`LIVE_FORWARD` quarantine.**
4. **`python -m scripts.verify_before_push`** — and run the **module suite
   directly** as well, because the gate's sibling check diffs against HEAD and
   "unchanged — nothing to run" is not "verified".
5. **Push both repos.** 49 + 6 commits.
6. **Verify production on the new commit** — the deploy, not the CI. `/risk`
   answers, `/api/risk-layer/exposure` returns a size, `aegis_verified_state`
   reports the new SHA. **A green CI and a live deploy are two different facts**
   and the skill exists because we learned that the expensive way.
7. **Fix the pre-push sibling hole in the gate itself**, first thing after the
   push lands. You worked around it correctly once; the next person will trust
   it.

Then, and only then: Railway sleep (receipt count over three consecutive days,
never `scheduler.running`) · the missing IIF-1 grader module · `check_read`
deriving `n_graded_nights` rather than accepting it.

---

## 4. Standing

Added:

- **§59, sharpest form: same books, same resamples, change only the outcome and
  the verdict can flip.** An objective containing an unresolvable term is an
  objective that cannot answer a question about the resolvable one. Score the
  statistic you are claiming.
- **A universe must state its population where it claims to trade,** at
  registration. `NO_POPULATION_IN_SCOPE` is not a discovery to be made twice.
- **A bounded sacrifice beats an unresolved estimate.** Where an equivalence
  bound clears the break-even, report the decision; do not report the hedge.
- **An evidence grade renders next to the claim, not below it.**

— brain, 2026-08-17
