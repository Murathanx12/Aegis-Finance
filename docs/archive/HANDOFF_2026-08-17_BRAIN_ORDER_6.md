# ORDER — brain → builder (order 6)

Binding. Verified against code at `de668d6`, not against the report. 35 commits
unpushed on `aegis-finance`, 6 on the module. Production untouched. The paid
IIF night is **Monday 2026-08-17, outer bound 12:20 UTC**, and nothing in this
order goes near it.

---

## 0. My own correction first

I told Murat the route to Wharton was closed and that he needed the campus VPN,
and that no Duo was needed because nothing could connect. Two of those three
statements were wrong, and I made the error the standing feedback names by
name: **three hosts failing looked like one cause and was one guess.** You ran
the fourth port, found `wrds-cloud:22` open and keyboard-interactive, and the
account was reachable the whole time. The rule that already exists — *check the
cheap discriminating case before naming a cause* — was written after the last
time this happened, and I did not apply it. Recorded here rather than in a
footnote because I escalated a guess into an instruction to a user.

## 1. Validation

**The vendor settled the OptionMetrics question and it was ours twice.**
`optionm.vsurfd` does not exist; `vsurfd2015` holds 404,564,776 rows across 252
distinct dates, and our extraction of the same year holds 12. "OptionMetrics is
monthly" was reported to this programme twice as a property of the data. It was
a `WHERE` clause. This is now the third instance of the house failure mode — *a
property of your extraction is not a property of the data* — and the first one
closed by the source's own table rather than by argument.

**Phase A is real and the count is not a coincidence.** 376,572 rows, 3,523
observation dates, median 6.0 coordinates per security-date in every year, no
partial cells — and 3,523 is exactly the trading-day count the prereg declared
before a single option row existed. A declared count matching the delivered
count is the cheapest possible proof that the puller did not quietly change the
question.

**`--map` refusing 12 of 18 is the correct behaviour and the reason is the
finding.** "Lowest secid" is wrong for SPY and GLD because their low secids are
dead 1990s tickers that reused the letters. A mapper that guessed would have
produced a plausible, silently wrong panel. `index_flag='0' AND issue_type='%'`
gives 18/18 cross-checked against cusips the vendor did not choose, and GLD's
2006–2007 absence is **named, not imputed**.

**The Night-1 contract passes and I accept the result.** Recovery survives
`owner_of` raising (30/30 recovered, 0 campaign strays, 0 of 20,073 campaign
rows matching the key); `prompt_hash == sha256("INTERNET-INVESTIGATOR-FWD-1:<arm>:<night>")`
makes trial membership cryptographically re-derivable, and that hash **is** the
run id; and `made_at` is minting time while the cutoff is the snapshot's
`decision_ts` — a grader reading `made_at` credits the forecaster with
information it did not have. **Run Monday as-is. Name the population in the
receipt beforehand. Change no source.**

**R13f is right, and it weakened your own registration, which is the direction
that proves it isn't decorative.** The rule as written — *the test is selection,
not citation* — is now canon: chose the rungs → `parent_trial`, spends the
calendar; supplies a number you divide by → `benchmark_source`, spends nothing;
its outcomes are why the hypothesis exists → `hypothesis_source`, spends no
calendar and **caps the claim at `ADAPTIVE_HISTORICAL_VALIDATION`**. Making it
a cap rather than a refusal is the correct call: a refusal there would duplicate
R13e and kill answerable questions, and a gate that expensive gets deleted the
week it first costs somebody a slice. My "benchmark ≠ parent" paragraph was
correct and insufficient; you built the missing third case.

**G4 V1, and the out-of-sample check is what makes it worth having.** Built and
debugged on 2015 alone (+0.19% / +1.92%, corr +0.199, beat rate 61.9%), then
thirteen unseen years moved it to +0.25% / +1.88%, corr +0.194, beat rate 64.1%.
That is the check separating a working join from one that lined up on its debug
year, and you ran it unprompted.

**The validator earned its existence on its first run.** Giving every pre-16:00
announcement a 09:30 `tradable_at` puts the entry before the announcement for
companies reporting during the session — the exact off-by-one that hands you the
move you are predicting. It refused 57 rather than admitting a negative reaction
window. I verified the clock wiring: `tradable_at` is gated against
`first_public_ts`, not `observed_at`, which is the correct choice and means the
740-day backfill tail cannot corrupt the reaction measurement.

**`ibes.det_guidance` is the best small finding in the session.** It lists in
`information_schema` with precisely the columns `guidance_state` wants and
returns permission denied for `tr_ibes_guidance`. A collector that inferred
availability from the listing would have shipped a column that silently never
populated — a passing test on an empty field. `UNKNOWN` with that sentence as
its recorded reason is exactly right.

**And the factory's scale bug is a better find than the factory.** Pooling the
covariate spread inside each calendar block is degenerate where it matters: in a
block of two the sd *is* the difference, so every pair sits 1.41σ apart and
nothing matches — and the run reports "no acceptable pairs found" as though that
were a fact about the world. **Covariate scale is a property of the population,
not of the block**, and refusing below a minimum rather than inventing a spread
from six points is the right repair. `min_episodes_for_scale=30` with
`covariate_scale_source` reported is a guard that derives what it checks.

---

## 2. G4 is not finished, and one cheap test decides whether it is a finding

The headline as stated is confounded and you should attack it before anyone else
does:

| claim | events | mean reaction |
|---|---|---|
| positive EPS — an announcement fact | 51,384 | +0.25% |
| beat by >1σ — a surprise fact | 28,010 | +1.88% |

**These two sets overlap heavily, and the second is a stronger selection than
the first.** A stronger conditioning producing a larger conditional mean is
arithmetic, not evidence about expectations. As written, the contrast cannot
distinguish "surprise carries information beyond level" from "we sorted harder."

**The discriminating test is the 2×2, and every cell exists in the corpus you
already have:**

|  | beat > 1σ | miss > 1σ |
|---|---|---|
| **EPS positive** | ? | ? |
| **EPS negative** | ? | ? |

If the expectation layer is doing work, **`EPS negative × big beat` is positive**
and **`EPS positive × big miss` is negative** — the sign follows the surprise
and crosses the level. If instead reaction tracks the EPS sign *within* surprise
strata, then the layer is measuring level with extra steps and the +1.88% is a
selection artefact. This is one grouping over 60,402 records, costs nothing, and
it is the difference between G4 being plumbing and G4 being the programme's
**first surviving positive since N9 was withdrawn.**

Report the four cell means with counts and the interaction term with its own
standard error — §18: the claim is a **difference**, so it is tested as one.

Two smaller things while you are in there:

- Report the surprise effect **conditional on the announcement fact** as well as
  marginally. The decision-useful quantity is incremental information, not total.
- The 740-day disclosure tail is correctly flagged. State the one place it bites:
  **any strategy that consumes the IBES actual as an input must gate on
  `observed_at`, not `first_public_ts`.** Two clocks, two questions, and only one
  of them is ours. Reaction studies use the public clock; anything we would trade
  uses our feed's clock.

---

## 3. The gap the factory is about to walk into — reservations and the α budget

This is the order's headline and it is a defect in the discipline layer, not in
your code.

`slice_register` tracks **consumed** slices, filtered by lineage. It has no
notion of a **reservation** — a future window claimed by a registered trial that
has not confirmed yet — and no notion of **how many trials one clean window can
support.** The lineage filter is correct for leakage and silent about
multiplicity. So:

> Fifty unrelated mechanisms confirming on 2020–2026 at p<0.05 yield about two
> and a half false winners, **and the register reports every one of those
> windows as clean**, because none of them shares a lineage with the others.

The factory's entire purpose is to generate mechanisms in bulk — 500 generated,
~30 transfers, ~10 shadow books. Point that at a shared forward window with no
family-wise accounting and the survivors are uninterpretable by construction,
and we will discover it three sessions after the first positive. That is the N9
sequence again, on a different axis.

**Order, and it is a precondition on §4:**

1. **Reservations are recorded at registration, not at confirmation.**
   `IV-ORACLE-GAP-1` has already reserved 2020-06-01..2026-07-17 and nothing in
   the register knows. Add reservation records: trial, window, outcome, horizon,
   status (`RESERVED` / `SPENT` / `RELEASED`).
2. **Every clean window carries a declared confirmation budget** — how many
   independent trials may confirm against it, fixed before the first one runs,
   with the correction named (Bonferroni, Holm, or Benjamini–Hochberg at a
   declared FDR; pick one and write down why). Exceeding it is a **refusal**,
   not a warning, in the same shape as R13e.
3. **The budget is declared before the filter runs, not after the survivors are
   known** — otherwise the count is chosen by the result, which is §20 wearing
   a different hat.

My recommendation for the number: the 2020–2026 window supports **five**
confirmations at FWER 0.05, and the factory's job in the Gym is to get from
hundreds of candidates down to five before it touches the window at all. If five
feels small, that is the correct feeling — it is what "we only have one future"
actually costs, and it is the argument for cross-sectional and event designs,
which buy independent information without spending calendar.

---

## 4. Routing — take it, with three conditions

**Yes: do the PIT characteristics pull (CRSP size / momentum / vol / drawdown /
liquidity) and run the factory over the 60,402 G4 episodes.** No LLM spend, no
production path, no Railway, nothing that can touch Monday. Holding local
research until after the night buys nothing — the night's risk is on the
machine's state and the receipt, not on whether a CRSP pull happened on Sunday.

Conditions:

1. **Declare the factory run's selection period before the first pair forms.**
   2006–2019 is about to become a selection calendar for every mechanism the
   factory ever emits. Under R13e that makes the factory run the `parent_trial`
   of all of them. Register it as a Gym `EXPLORE` with `slice_period`
   2006-01-03..2019-12-31, and reserve the confirmation calendar **at
   registration** per §3. Doing this afterwards is not possible; that is the
   whole lesson of N9.
2. **Stop by Sunday night.** The machine is clean for Monday, and a long CRSP
   pull that runs into the morning is exactly the kind of ambient load nobody
   attributes correctly when the one paid attempt behaves oddly.
3. **Do not push.** Unchanged and unconditional until the night is done.

Order within the session: §2's 2×2 first (it is minutes and it may change what
the factory is asked to explain), then §3's reservation records, then the pull,
then the matching run.

---

## 5. The roadmap, restated — what we are actually building over the next three months

Murat has asked for this twice and I owe it as a standing order rather than as
scattered rulings. Three deliverables, one system: **his capital, a tool other
people run at their own utility function, and a paper if a defensible novel
result appears.** The third is conditional on the first two; it is not the goal.

**M1 — The expectation layer and the event corpus (now).** G4 V1 exists. Finish
it with §2. This is the substrate: every event family the programme cares about
— earnings, guidance, revisions, insider clusters, approvals, policy — is
uninterpretable without what was expected, and we now have that for earnings.

**M2 — The factory, producing matched pairs at scale.** Winner vs *economically
matched* loser, the mission's rule 4 and the one we have broken most often.
Output is candidate mechanisms with executable precursors, in the Gym, on a
declared selection calendar. This is where hundreds of candidates come from.

**M3 — Adopt before inventing.** Murat is right and I have been slow on it. A
published method with a documented out-of-sample record is a stronger starting
point than a mechanism we invented last Tuesday, and refusing to use one is not
rigour. **The rule is not "don't adopt" — it is "adopt, and measure the
post-publication decay yourself before sizing it."** Time-series momentum,
cross-sectional momentum, betting-against-beta, quality, trend-following, PEAD:
each is a known method with a literature, and each has a measurable answer to
*"does it still work on 2015–2026 net of costs?"* that we can compute from data
we now hold. That answer is worth more than another invented candidate, it is
cheap, and a negative is as publishable as a positive. **This becomes a
standing lane in the Gym: the strategy library.**

**M4 — The selector.** Given a library of methods that each work somewhere, the
product question is *which one, when, at what size, for which declared utility.*
This is the thing that is actually novel and it is where the four personalities
live — λ is the personality, sizing is the lever, and §59 says risk outcomes are
resolvable at this sample where return outcomes are not. **Every risk-reducing
policy reports its break-even return sacrifice.** Aggressive mode is a declared
λ, not a tuned one.

**M5 — Time-machine replay as the standard evaluation.** *"Given what was
knowable at t, what action, what alternative, what happened, why, what changes"*
— rule 1 of the mission, and the Gym's episode format already carries it. Many
start dates, many horizons, always with the matched alternative, never a gallery
of survivors.

**M6 — Usable by Murat.** A page that says: here is your portfolio, here is what
the selector would hold at your declared λ, here is what it would have held at
each of the last N decision points and what that cost or earned, and here is the
one thing that would change its mind. Not a research console. Three months is
achievable for this **if M3 supplies the library**, and not if we are still
generating candidates from scratch in November.

What is deferred and stays deferred: World Model v0, AegisEvolve, RL, latent
state before known-answer worlds.

---

## 6. Standing

Unchanged: §14 in every report — it caught the thing order 4 was built on. A
null owes both its MDE and its equivalence bound. Only `REFUTED_IN_SCOPE` and
`STRUCTURALLY_CLOSED` close anything, and `REFUTED_IN_SCOPE` closes only the
scope it names, including the action it was mapped to. `verify_before_push` is a
pre-push step. Do not let the kill machinery become the programme.

Added by this order:

- **A stronger conditioning producing a larger conditional mean is arithmetic.**
  Any two-group comparison where one group is a subset of the other, or selected
  more tightly, states the incremental quantity or states nothing.
- **A clean window is a finite, shared resource, and lineage-cleanliness is
  silent about multiplicity.** Reservations at registration; a declared
  confirmation budget per window; exceeding it is a refusal.
- **Adopt before inventing, and measure the decay yourself.**

— brain, 2026-08-16
