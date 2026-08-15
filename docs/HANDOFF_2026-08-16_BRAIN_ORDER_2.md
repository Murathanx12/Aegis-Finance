# ORDER — brain → builder, second order for 2026-08-16

Binding. Extends `HANDOFF_2026-08-16_BRAIN_TO_BUILDER.md` (P0–P10 + P0.5), which
stays in force. Verified against code, not against the report.

State: `aegis-finance` @ `b8102ad`, `Aegis module` @ `70d529f`, both clean, CI
green, prod on `b8102ad`. P0/P2/P3 shipped.

---

## 1. Validation

**The CI finding is the most important thing in the session and it was found by
reading your own email, not your own code.** CI had been red since `6e8c13a`;
Railway gates on CI; production sat three commits back on `5d7ae15`. So **the
§39 timing guard — written specifically to protect a paid night — was never in
production while the handoff reported it shipped.** Cause: CI checks out one
repo, two tests assumed the sibling `Aegis module` exists, and *the code was
right both times — the tests asserted this machine.* `ci_env_sim.py` is the
correct fix, and the second failure only surfaced because you re-ran the whole
suite instead of stopping at the first green.

Canon it: **two green signals can measure different worlds, and only one gates
production.** "Shipped" now means *verified in the deployed commit*, never
*merged*.

**P0 validated, and its self-catch is the better result.** The scope layer is
built the way it was ordered — executable declarations, labels frozen before any
number exists, sign inverted in the unaffected region, `DEAD` retired, nine
verdicts, computed `revisit_when`, §18 enforced. Then **the new standard's own
first run returned `REFUTED_IN_SCOPE` ×5, and all five were manufactured**:
`n_effective` was `n` for monthly probes of a 63-day window across six
*co-moving* ETFs, and `se_pp` used raw n while `mde_pp` used n_eff. Corrected
with the hypotheses held fixed: **REFUTED 5→0, all six verdicts moved, nothing
closed.** GFC MDE went 4.7pp on "n=54" to **24.7pp on n_eff ≈ 3**.

That is the third instance this week of the same shape, and it now deserves to
be stated as a law rather than a lesson: **check a new instrument's kills before
its passes — the kills are the ones that look like it working.** You built a
scope layer to stop false kills and it produced five on its first run. Catching
that is what makes the layer trustworthy.

**The honest verdict is the right one and must not be softened:** the corpus
cannot resolve these six mechanisms **in either direction**. That is a
measurement of the corpus, not of the mechanisms. §2/N2 below is the fix, and it
is *more independent stress episodes*, never more rows.

**P2 validated.** No PIT defect — content genuinely is cut — but the evidence
for it was broken twice: `observed_at` assigned `decision_ts` on every row (a
field proving the cut was a copy of the thing it checks), and
`earnings_within_5d` storing a scheduled *future* date in `published_at`. The
detail I want kept: **a clean snapshot failing a new check on its first run is
how a real check gets switched off rather than believed.** Re-homing to
`event_at` instead of loosening the check was the right call.

**P3 validated, and `$12 → $60` is the find.** Five arms reading a
read-then-act ceiling concurrently grant 5/5 on a barrier with room for one.
`SpendGovernor` grants 1/5. Canon: **a guard written for a serial world is not
automatically a guard.**

**Correctly not run:** the paid night (past the open), P1 (attended, date-bound).

## 2. P0 FOR TOMORROW — the ÷5 divisor is not merely unvalidated, the code contradicts its own docstring in the unsafe direction

You flagged this; it is worse than flagged, and it gates the paid night.

`projected_night_minutes` (`investigator_night.py:195`) says:

> *"The projection stays deliberately pessimistic: real concurrency never
> achieves the full factor (a cell ends when its SLOWEST arm ends, and the
> slowest of five draws exceeds the mean of five). A projection that flattered
> the night would let it start too late, which is the exact failure this whole
> guard exists to prevent."*

The arithmetic on the next line is `... / conc` — **division by the full factor.
That is the optimistic bound, and it is precisely the flattering projection the
docstring says it must not be.** The comment describes the correct model
(cell = max of arms) and the code implements the wrong one (cell = mean/5).

Three ways it errs unsafe, compounding:

1. **`MEASURED_CALL_SECONDS` is the serial mean.** Under concurrency, per-call
   latency rises — connection contention, vendor-side rate limiting, queueing.
   The input is measured in a world that no longer exists.
2. **A cell ends with its slowest arm.** `E[max of 5] > mean`, and with a p90 of
   15.6s against a mean of 8.7s the gap is nearly 2×.
3. **Tool arms are systematically slower than snapshot arms** — they were 7
   calls to 4 on Night 1 — so the max is not a random draw, it is nearly always
   a tool arm.

Concretely: projected 28 min. If real speedup is ~2.5×, true is ~55 min. The
guard would authorise a 12:50 start; the night ends 13:45, **past the open, and
it ACCRUES rather than voids.** The guard written to prevent exactly that now
permits it.

**Order:**
- Model the cell as **max-of-arms**, not sum/conc. Use the **p90** call time for
  the slowest-arm term, not the mean.
- Until a real concurrent night is measured, apply a declared **efficiency
  factor < 1** (recommend an effective divisor of 2, not 5) and say so in the
  receipt: *"speedup assumed, not measured."*
- **The first concurrent night measures and records the real speedup**,
  per-arm wall times and arm-completion skew. The divisor becomes measured on
  night two.
- Assert headroom at the **end** of the night, not only the start — and keep the
  existing choice not to abort mid-night (aborting buys contaminated forecasts).
  Record the overrun; refuse the *next* night on it.
- The rehearsal's "peak 5 in flight, skew 1.0 ms" was against a stub. **A stub
  has no latency, so it cannot test a latency guard.** The concurrency harness
  needs a stub with a realistic latency distribution — mean 8.7s, p90 15.6s,
  tool arms drawn slower — before the divisor is believed.

## 3. Order for 2026-08-16

**A. P0 above.** Gates the night.

**B. P1 — attended, date-bound, cannot slip.** First `CAMPAIGN_FORWARD`
resolutions (dry run first; due / resolvable / unresolved / source availability /
hash before / hash after / dated receipt; `--population campaign_forward`; never
pooled). Then the `LIVE_FORWARD` quarantine with byte-identical backup and
SHA-256 receipt stating *zero genuine live rows removed*.

**C. The paid night, at or before ~11:10 UTC**, after A. One attempt, hard stop,
operational receipt only, **no H1 read**. Report measured all-in cost against
the $1.43 break-even and the **measured concurrency speedup**.

**D. Idempotency — free, from the 06:00 EDT overlap.** Duplicate accessions
absorbed · TeacherEvents not duplicated · amendments still expressible · counts
reconcile.

**E. P0.5, still outstanding** — `PolicyResult` has no drawdown, no path risk, no
utility; `ranked()` sorts by `-net_return_pct` alone, from a menu containing
1.25× and 1.5× levered arms. Until this lands, every Gym number answers the
wrong question. See N3 for the extension that makes it worth more than a fix.

## 4. NOVEL TESTS — candidates, not registered. Ranked by EV, per §0.8.

`EV = P(changes the roadmap) × value of the decision improved − cost`

### N1 — The disclosure-lag decay curve. **Do this first; it is cheap and it can kill a whole track.**

A Form 4 trade happens at *t* and becomes public at *t + lag*. Measure the
return path from **transaction date** against the path from **disclosure date**,
across the 109 buys and 593 sells already collected, then across the backfill.

**If the return accrues before disclosure, COPY-LAB is dead regardless of how
good the insider signal is** — the signal would be real and uncopyable. That is
a *feasibility* result, it costs almost nothing, it uses data already on disk,
and it either licenses or terminates the entire Teacher Library product thesis.
Running it before more Teacher Library investment is the highest EV move
available. Split by role, by cluster/non-cluster, and by lag bucket.

### N2 — Break the n_eff ≈ 3 wall with partially independent stress episodes

The binding constraint on the whole Gym is **independent stress episodes**, and
US index history offers roughly a dozen. But stress episodes are far more
numerous **cross-sectionally**: Japan 1990s, Europe 2011–12, EM 1997–98, China
2015, single-name crashes, sector dislocations, other asset classes.

Pre-declare a corpus of non-US, non-overlapping crisis episodes **generically**
— never fitted to the near-miss — and ask whether the stress→forward-return
relationship measured *there* transfers to the US. This is what
`TRANSFER_ATLAS_V1` needs to be, and it is the difference between a Gym that can
resolve a hypothesis and one that structurally cannot. **More independent
episodes, never more rows.**

### N3 — Report break-even risk aversion γ*, not "selling was wrong"

Extends P0.5 and is worth more than it. For each de-risking episode, compute the
certainty-equivalent across a range of risk-aversion parameters and solve for
**γ\*: the risk aversion at which selling becomes correct.**

The output stops being *"de-risking cost 13.87pp"* and becomes *"de-risking is
wrong for anyone less risk-averse than γ\*, and right above it."* That is a
strictly more informative statement, it is honest about a result currently
computed with no risk term at all, and it is **exactly the machinery the four
personalities need** (§0.9). Nobody has computed γ\* for any Aegis result.

### N4 — Precursor Coverage Index: the Micron test as a program metric

For every large realised move (top decile |63d return|, cross-sectional), ask
whether **any** mechanism in the library had a precursor firing beforehand.

That yields a coverage number: *what fraction of the moves that matter is our
mechanism library even addressing?* If it is 3%, the validity of each individual
mechanism is close to irrelevant, and the roadmap should be about generating
candidate precursors rather than adjudicating the six we have. **Nobody measures
this, and it directly answers "are we even looking in the right places."**

### N5 — Grade the LLM's scope declarations. Free, from data already on disk.

Every autopsy declares `expected_affected_states` and
`expected_unaffected_states`. **That is a prediction, and nobody grades it.**

Score it: when the LLM says "this works in X and not in Y", how often is the
*unaffected* declaration borne out? This is the first direct test of whether LLM
reasoning **localises** mechanisms — and the entire scope layer now inherits
whatever noise is in those declarations. If the LLM cannot localise, the scope
layer is built on sand and we need to know before P6. Costs nothing beyond
compute already spent.

### N6 — The second-moment regularity, stated and then exploited

Look at what has actually survived in this program: MARKET-GRAPH-1 H1 is a
**co-movement** result. GRAPH-COVARIANCE-1 closed because the trailing sample
matrix already captures forward correlation. IIF-1's power analysis chose
**magnitude/volatility** over direction because σ_π was 0.0036 against 0.1183 —
a direction primary never resolves at any n. NIGHT-3 found no LLM edge in stock
**selection**.

**Second moments keep being detectable; first moments keep not being.** That is
a program-level empirical regularity and it should reorder the world model:
build the **volatility / co-movement / drawdown / rebound-magnitude heads
first**, and treat direction as a low-priority head rather than the objective.
It also suggests the honest product framing — Aegis is better at *how much* and
*what moves together* than at *which way*, and a risk-model product may be the
defensible one.

### N7 — Insider clusters vs the sum of individuals. Testable now, no actor history required.

Actor Surprise is data-blocked at the actor level, but **clusters are not**. Do
≥3 independent insiders acting within N days predict better than the sum of the
individual actions? That is a test of *coordination information* rather than
actor identity, it needs no per-actor baseline, and it is runnable on the corpus
already collected. Matched control: the same issuers with one insider acting.

### N8 — Derive the required corpus size instead of guessing it

Build `WORLD-CONDITIONAL` **calibrated at n_eff = 3** and ask what effect size
we would detect. That converts *"the corpus cannot resolve the six"* into a
**corpus design requirement**: *K independent episodes are needed to detect an
effect of size E at 80% power.* Then N2's expansion has a target instead of an
ambition.

## 5. Standing

Unchanged. Only `REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` close anything.
Every non-support carries `revisit_when`. §18 on every conditional claim. No Gym
number is an alpha claim. Spend escalates to Murat only above ~$2/night;
information per dollar, not calls minimised.

**"Shipped" means verified in the deployed commit.** After every push that
deploys, confirm the deploy commit matches HEAD before reporting anything as
live.

— brain, 2026-08-15
