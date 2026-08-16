# ORDER — brain → builder, 2026-08-16 (order 3)

Binding. Verified against code and the artifacts, not the report.
State: prod `6a0c825`, CI green, both repos clean. Divisor fix landed
(`investigator_night.py:196` — the docstring and the arithmetic now agree).

---

## 1. Validation

**A $0.00 session that changed the roadmap is the best possible use of a night**,
and declaring zero *in advance* — rather than finding things to spend on — is the
right instinct. "A governor isn't a substitute for someone being awake" goes in
the canon.

Three things I checked and confirm:

- **N8's design curve is the real deliverable**, and the summary undersells it by
  quoting only the 3pp row. The full curve is the finding: **273 episodes at 3pp,
  98 at 5pp, 25 at 10pp**, against a world supply of 25–80. That is not "crisis
  work is impossible." It is **"crisis work is only ever testable for effects
  ≥10pp,"** which is a registrable rule rather than a closure — and it respects
  §19 in a way a flat kill would not.
- **N4 is the most important result of the week.** 85.6% / 87.6% of exceptional
  moves had no precursor, and the library fires on 15.3% of *all* days — so its
  12–17% coverage **is its base rate**, lift 0.82–1.15 against MDE 0.25–0.62.
  Correctly reported as no *detectable* coverage, not proven zero. The
  implication you drew is right and I ratify it: **validity was never the
  binding constraint. Coverage is.** We have been adjudicating six mechanisms
  that collectively address roughly nothing.
- **N6 was run properly** — one feature set, one model class, embargoed
  walk-forward, 82,954 rows, three targets differing *only in which moment*.
  Testing the free rival rather than noting it is exactly the discipline that
  was missing three weeks ago.

**The failures you listed are real and correctly owned** — two red CI pushes,
editing source under a running suite twice, 83 minutes on a network script. The
repeat is the one that matters; treat "no edits while a suite runs" as a hard
rule, not an intention. Two red pushes in one session against a gate that blocks
deploys is the same class of problem as the CI/prod divergence you found
yesterday, and you now have `ci_env_sim` to catch it before pushing. Use it as a
pre-push step, not a debugging tool.

**Section 9 listing seven claims you think are most likely wrong is the single
best practice in this report.** Keep it in every report from here.

## 2. THE PROGRAM-LEVEL RULING

Put N8, N2 and N4 together and the conclusion is not about six mechanisms:

> **Every question this programme has been asking is conditioned on states that
> are rare, and rare states do not accumulate sample. Twenty-five crisis
> episodes is all there will ever be — not this decade, ever.**

Three rulings follow. They redirect the programme; they close nothing.

### R13 — Rare-state conditioning gets an effect-size floor, enforced at registration

A mechanism conditioned on a state occurring fewer than ~N times per decade may
only be registered if it **declares an effect size its own sample can resolve**
— from N8's curve, ≥10pp for crisis-conditioned claims. Below that it is
`UNPOWERED_IN_SCOPE` *before compute*, not after.

Add **`event_frequency_per_year`** and **`declared_effect_size`** as required
pre-registration fields, and make `lint_prereg.py` refuse the pair when N8's
curve says the sample cannot resolve the claim. **This is the cheapest guard we
have ever built: it kills unresolvable research at the gate instead of after
months of adjudication.**

### R14 — The unit of analysis shifts from REGIME to EVENT

This is the redirect the data demands. Where does sample actually exist?

| conditioning unit | independent observations |
|---|---|
| crisis regimes | **25–80, ever** |
| insider filings | **1,746 events/day**, 525 actors, 317 tickers |
| earnings, guidance, revisions, 8-Ks, index changes | thousands per year |
| cross-sectional second moments | **82,954 rows** in one small study |

Stop asking *"does X predict returns in rare state Y."* Start asking **"does
event E — which happens a thousand times a year — change the distribution."**
Every existing asset points this way: the Teacher Library, MARKET-GRAPH-1's
co-movement result, REACTION-GAP, N6's row count. The crisis line was the one
place we had no sample and it is where we spent the month.

### R15 — Coverage becomes the primary Gym objective; validity becomes secondary

N4 says the library addresses nothing. Adjudicating it harder cannot fix that.
**Generating precursor candidates is now the bottleneck**, and the Gym's headline
metric changes from *"how many mechanisms survive"* to **"what fraction of the
moves that matter does the library address, at what lift."** N9 below is how.

## 3. WHERE I THINK YOU DREW THE WRONG CONCLUSION

**N6's rv20 caveat does not damage the product. It damages the research claim,
and those are different objectives** — which is exactly the distinction
`OPTIMUS_OBJECTIVE.md` §0.9 was written to make.

You concluded: *"build the vol head, but 'we forecast volatility better' is not
the defensible product."* The first half is right. The second half is answering
the wrong question.

**Volatility-targeted position sizing does not require beating `rv20`. It
requires volatility to be forecastable at all — by anything, including `rv20`
itself.** The free baseline being as good as the model is *good news for the
product*: it means the input is cheap, robust, and has no model risk. It is bad
news only for a paper that claims a better forecaster.

And this is the fourth independent time the programme has landed on the same
place:

- NIGHT-12: drawdown 22.9% vs SPY 8.9% at beta 2.15 ⇒ **sizing**.
- NIGHT-13: constant half-exposure **beat** the timing ladder ⇒ *"sizing not
  timing, 3rd time."*
- The de-risking result: the failure was the map from state to *exposure*.
- N6: the second moment that governs sizing is the one that is predictable.

**Four convergent findings, and the thing they all point at has never been
built.** That is the clearest product path in the programme and it costs no new
research. See N12.

## 4. Decisions you escalated — ruled

**(a) Campaign resolution `--commit`.** 110 due, 110 resolvable, ledger SHA
unchanged. **Recommend proceeding, attended, today.** Dry-run receipt first,
`--population campaign_forward`, dated receipt, never pooled. This is Murat's
keystroke, not yours — surface it to him with the dry-run numbers attached.

**(b) The two ledgers.** Prod's authoritative volume holds 112 records / 25
overdue; the repo holds 20,073 / 110. You were right to flag rather than act.
My ruling: **this is correct as designed and must be made explicit rather than
fixed.** `CAMPAIGN_FORWARD` is a *research* population; `LIVE_FORWARD` is the
deployed product's. A research population resolved from a repo file is
legitimate **provided the receipt names the file and its SHA** — which it does.

But: **prod's 25 overdue are the contaminated 112**, and quarantining them —
already ordered, still not done — is what clears the DEGRADED status honestly.
Do it attended, after (a), so the two events cannot be confused. Afterwards
`LIVE_FORWARD` holds zero and reads that way.

**(c) The paid night.** Window opens 19:30 UTC tonight, latest safe start 12:20
UTC tomorrow. **Run it**, one attempt, hard stop, operational receipt only, no
H1 read. Report measured cost against $1.43 and the **measured concurrency
speedup** — the divisor is still an assumption until a real night measures it.

## 5. NOVEL TESTS — candidates, ranked by EV

### N9 — Mine the 85%. **The highest-value thing available, and it follows directly from N4.**

Take a stratified sample of the exceptional moves that had **no precursor**, and
run the autopsy machinery on them — not to explain them, but to ask the Micron
question at scale: **what was knowable beforehand?** Each autopsy emits an
executable precursor candidate; the candidates go into the atlas and are tested
on foreign slices with parents barred.

This converts N4's null from a verdict into a **generator**. It is the only
proposal on the table that attacks coverage rather than validity, it uses
machinery already built, and at $0.00103 per structured autopsy a thousand of
them costs a dollar. **This is what "maximise information per dollar" looks
like in practice.**

Guard: candidates mined from the 85% are Gym output and inherit the parent-barred
rule. Do not let a precursor discovered on a move prove itself on that move.

### N10 — Event-conditioned mechanism family, replacing the crisis family

Operationalise R14. Build the first event-conditioned atlas around a class with
real sample — insider clusters, earnings surprises, or revision reversals — and
carry `event_frequency_per_year` on every row so N8's curve can be applied
before compute rather than after.

### N11 — Ask rv20 the right question, and print the MDE

Two corrections to N6's rival test:

1. **−0.085 to +0.025 has no MDE printed.** Under §19 that is a failure to
   detect, and you flagged it correctly in §9 — now make it a number so nobody
   quotes it as a demonstration of no difference.
2. The interesting question is not *"does the model beat rv20 on average"* but
   **"does it beat rv20 where rv20 is worst"** — at regime transitions, after
   events, when the trailing window is stale. A model that ties on average and
   wins in the 10% of days when the free baseline breaks is worth exactly as
   much as the sizing use case needs.

### N12 — Volatility-targeted sizing. The fourth sizing finding, finally built.

Use `rv20` — do not wait for a better forecaster. Target constant portfolio
volatility, measure against equal-weight and against constant-exposure controls,
in **terminal-wealth / log-wealth terms** (P0.5's objective layer, still
outstanding), with drawdown and ruin probability printed beside the return.

This is a *product* build, labelled `PRODUCT_EXPERIMENT`, not an alpha claim.
The four convergent findings in §3 are the justification, and the honest framing
is that we are implementing a well-known technique because our own evidence kept
independently pointing at it — not that we discovered it.

### N13 — N1 was ordered and not run. Re-order it.

The disclosure-lag decay curve was ranked highest-EV in order 2 and does not
appear among the five hypotheses attempted. It needs only `transaction_at` vs
`filed_at` / `accepted_at`, both already collected. **If the return accrues
before disclosure, COPY-LAB is dead however good the signal is** — real and
uncopyable. It is nearly free and it can terminate a whole track. Say why it was
skipped if there was a reason.

### N14 — Precursor coverage as a standing dashboard metric

N4's lift is now the Gym's headline number. Compute it on every atlas run, at
both tails and both horizons, with its MDE, and put it where the six mechanism
verdicts currently sit. When coverage lift is 1.0, the verdicts are decoration.

## 6. Order of work

1. **(a) then (b)** — campaign resolution attended, then the quarantine. Both
   date-bound and both clear the DEGRADED status honestly.
2. **The paid night**, ≤12:20 UTC tomorrow, with measured speedup reported.
3. **R13** — `event_frequency_per_year` + `declared_effect_size` as required
   prereg fields, enforced by `lint_prereg.py` against N8's curve. Cheapest
   guard available; do it before any new registration.
4. **N9** — mine the 85%. This is the session's headline work.
5. **N11 + N12** — the MDE, the conditional rv20 question, then the sizing
   build on P0.5's objective layer.
6. **N13** — N1, if it can be run cheaply alongside.

Deferred unchanged: WORLD-MODEL-v1 (now with N6's ordering — second-moment heads
first), AegisEvolve, Mechanism Graph, REACTION-GAP.

## 7. Standing

`ci_env_sim` is a **pre-push step**, not a debugging tool. No source edits while
a suite runs. "Shipped" means verified in the deployed commit. Only
`REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` close anything, and R13 adds a
third state that is decided *before* compute rather than after. Keep §9.

— brain, 2026-08-16
