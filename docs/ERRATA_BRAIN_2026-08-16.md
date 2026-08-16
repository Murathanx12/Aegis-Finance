# ERRATA — brain, 2026-08-16

Four claims I made in review feedback are wrong. External review caught all
four; I verified each against the lineage and the arithmetic rather than
conceding on authority. **Committed, not pushed** — the paid night is Monday
2026-08-17 and production is not to be disturbed before it.

---

## E1 — "Five independent routes agree the library is dead." FALSE, and I made it worse.

The builder wrote *"five independent routes now agreeing — N4 coverage, N9
lift, N20 estimand, N21 direct, and the cost side."* I repeated it **and
escalated it into a decision**: *"I'd treat that as settled and stop spending on
it."*

**They are not five independent routes.** N20 measured `μ_rest | fire` — fire of
**N9's rules**. N21 froze and hashed **N9's rules** before fetching a price. The
cost side runs on the same selection. So the lineage is:

| route | parent |
|---|---|
| N4 / N4B coverage | the original six autopsy mechanisms |
| N9 lift · N20 estimand · N21 direct · cost side | **all descendants of the N9 selection** |

**Two routes, not five** — and the second has a **20-day embargo leak in its
parent**, discovered in the same session.

This is precisely the §20 error (a batch checked against itself) that this
project has a standing rule against, and I committed it while reviewing
someone else's discipline. The independence claim is what turned a repeated
failure into "settled", and the recommendation to stop spending followed from
the false count, not from the evidence.

**Corrected statement:** *the current precursor family has repeatedly failed to
demonstrate economic usefulness, but its N9-derived evidence must be
revalidated after the temporal leak is fixed.*

## E2 — "Fixing the N9 leak can only push 1.271 downward." FALSE.

Leakage biases estimates upward **in expectation**. A single corrected re-run is
one draw and can land either way. I stated a mathematical certainty where only a
prior exists — the exact "likely → guaranteed" slip I have criticised in others
twice this week.

**Corrected:** the prior is downward; the outcome is unknown until it runs, and
the re-run is not permitted to be reported as confirmatory of a direction
declared beforehand.

## E3 — "Market-level directional claims are unresolvable by construction." TOO STRONG.

The ρ̄ bound `k/(1+(k−1)ρ̄)` limits the **cross-sectional** dimension: correlated
series stop adding independent information, bounded by `1/ρ̄ ≈ 2`. **Time still
adds information.** The 172-year figure is a *time* requirement computed at that
effective cross-section — it says the claim is **expensive at 20 years**, not
impossible in principle. And by N8's own logic, large market-level effects
remain resolvable; only small ones do not.

**Corrected:** *market-level return and timing effects of the size we care about
(~3%/yr) need on the order of 172 years at this effective cross-section, while
cross-sectional and event designs supply roughly an order of magnitude more
independent information over the same calendar span.* That is more than enough
to justify the pivot without claiming an impossibility.

## E4 — "We measure risk reduction; the wealth claim follows from a declared λ." WRONG, and the most dangerous of the four.

With `U = E[R] − λ·Risk`, **λ expresses how much risk is disliked. It cannot
supply a missing return estimate.** If it could, an arbitrarily large λ would
make cash optimal — a reductio that shows the sentence was not a utility
statement at all.

I collapsed two different things: *the trade-off between two measured
quantities* (λ's job) and *the estimation of one of them* (not λ's job, and not
possible by declaration).

**Corrected:** we measure `ΔRisk`. `ΔE[R]` is **not resolvable at this sample**,
so any wealth claim must carry an **explicit, declared assumption** about
`ΔE[R]`, labelled as an assumption and not as a measurement — and λ only trades
the two off once both exist. A policy that provably reduces risk with an unknown
return effect may be reported as *"risk reduced; return effect not
established"* and **nothing stronger**.

The "one brain, four personalities" design is unaffected: λ remains the
personality. What is affected is the claim that could be made without measuring
the return term — which is none.

---

## E5–E7 — three more, found by the builder executing P0

**E5 — "172 years" is arithmetically wrong; it is ≈95.** The cross-section was
used once as a multiplier and dropped when converting back: 172 = 95 × 1.81.
The need counts effective observations and the slice supplies **3.62/yr, not 2**.
I amplified the number in the direction that made it louder. The design's
conclusion is unaffected — the threshold is not reached either way — but the
figure must not be quoted again.

**E6 — "the bound is 1/ρ̄ ≈ 2 however many you add" was scoped wrong.** That
describes series that **move together**. `design_effect_n(100, 0.10) = 9.2`
against 2.03 at high correlation. So the *extension* I drew — that residual,
firm-relative claims buy roughly an order of magnitude — is confirmed; the
*bound* as I stated it was not general. State ρ̄ with every effective-n claim.

**E7 — "pin LightGBM's seed" was a fix that could not fix anything.** Seed 1 ≡
999983, and with no subsampling there is nothing to randomise. Had it been
applied, reproducibility would have appeared to improve and nobody would have
looked again. **A fix that cannot fail is as dangerous as a guard that cannot
fire** — and I proposed one three days after writing the second half of that
sentence. The residual 1.22617 → 1.22598 is a live defect, cause unknown;
OpenMP thread scheduling in histogram construction is a **candidate**, testable
via `deterministic=true` + `force_row_wise=true` + fixed `num_threads`, and must
be reported as diagnosed only if it reproduces.

## E8 — the λ repair is better than my correction

I withdrew the λ claim as unrecoverable. The builder's repair is right and it is
constructive: **λ cannot supply ΔE[R], but it converts a measured ΔRisk into a
break-even ΔE[R]** — *"this policy is worth it iff expected return falls by no
more than X."* That is the same shape as `L_min`, it is honest about what was
measured, and it is decision-useful. It should become a reusable primitive:
every risk-reducing policy reports its break-even return sacrifice.

## What survives

The pivot survives all four corrections and is strengthened by E3's precise
form: **move from predicting market direction to ranking opportunities within
the market** — event surprise, second-order lag, options disagreement, insider
surprise, policy/government money, revisions, foreign transmission, corporate
pivots. Firm-relative and event-relative claims net out the common factor, so
residual ρ̄ runs ~0.05–0.15 and the effective sample rises by roughly 10×.
R14 (regime→event) reached the same destination independently.

Also endorsed, and better designed than what I proposed: **`IV-ORACLE-GAP-1`**.
I asked for "add the implied-vol rung." The right question is bounded:
**how much of the oracle's measured 21.4% tail-pinball headroom can option
prices recover?** A known ceiling, a cheap test, newly-confirmed daily
OptionMetrics, and an answer that is informative in both directions.

And the warning worth heeding most: **do not let the kill machinery become the
programme.** Aggressive generation in the Gym, cheap falsifiers first, expensive
tests only for survivors. Hundreds of candidate mechanisms, not six — 500
generated, ~30 credible transfers, ~10 shadow books, ~2 useful strategies is a
successful discovery system, and the failure mode of never searching is as real
as the failure mode of believing noise.

## Operational

The paid IIF night is **Monday 2026-08-17**, target ≈18:30 MYT, safer upper edge
≈19:25 MYT, outer bound ≈20:20 MYT (= 12:20 UTC, consistent with the standing
guard). **Do not push the outstanding commits or otherwise disturb production
before that run.**

— brain, 2026-08-16
