# ORDER — brain → builder, for the 2026-08-16 session

Binding. Supersedes the "what needs you" lists in
`HANDOFF_2026-08-15_BUILDER_REPORT.md`. Verified against code and production,
not against any session's own report.

---

## 0. Verified state

`aegis-finance` @ `a355fa6`, clean, pushed. 4,153 tests green. Eight commits
landed 08-15. Deploy carries `f2c7b6b`+ (receipt enrichment live before the run).

| | |
|---|---|
| M1 | **VERIFIED LIVE.** 2026-08-15T10:02:43Z, 163.7s. 1,252 index rows → 589 unique accessions → **589/589 fetched, coverage 1.000, 0 parse errors**. 593 SELL / 109 BUY / 1,044 mechanical. 525 actors, 317 tickers, 1,746 events. **Not the T9 shape — Railway's egress reaches EDGAR.** |
| M2 | **CORRECTLY NOT RUN.** 960 serial calls × 8.7s mean = 2.3h against a 13:30 UTC open. Now refused in code (§39) before the first paid call. |
| M3/M4/M5 | Complete. Denominators, calibrated gate, autopsy→rule, 425-cell regret tensor. |
| T1 | Measured, **data-blocked** — median actor has 1 observation; 234 of 485 have exactly one. |
| T3 | Built before any winner exists to interpret. |
| T4 | Deliberately deferred, reason recorded. Correct. |

## 1. Verdict

Accepted without reservation. Five of the session's defects share one shape —
**a number that looked like a measurement and was an artifact of what it was
divided by, compared against, or never multiplied with.** Regret against a
best-of-17 had a +17pp null; a 1.0pp gate convicted 93% of blameless holds;
n=353 was n_eff 5.6; a units error cost 75% of a findings table; a pre-open
window could never have finished pre-open. That is a session that audited its
own instruments and found them bent. It is the most valuable kind we run.

Two judgement calls were escalated rather than taken. Both were called right,
and both are ratified below.

The result I most want carried forward is the one nobody asked for: **the 67.4%
BUY hit rate scores −0.57pp against simply holding.** A hit rate is a count of
being directionally right; it is not a measure of being *usefully* right, and
the old denominator hid the gap completely. That is a sharper indictment of the
signal engine than the sell-side failure ever was, and it belongs in the README
next to the sell-side number.

## 2. THE DEFECT THIS SESSION MUST FIX FIRST — the Gym cannot represent a conditional mechanism

Murat's standing instruction: *ideas can be conditional and situational; do not
kill what merely failed in the wrong environment.* I checked whether the
machinery can honour that. **It cannot, and the gap is architectural.**

`Autopsy` **requires** `expected_unaffected_states` — validated non-empty,
validated non-overlapping, recorded into `LineageRow.params["unaffected"]`.

`adjudicate()` then **never tests it.** The verdict comes from
`CH.request_export`, which calls `transfer.n_independent_slices_passed()` —
a flat count of slices where `passed` is true, with **no notion of which slices
the mechanism itself declared it should work in.** The unaffected list is
documentation. It changes no outcome.

The consequences, in order of severity:

1. **A correctly conditional mechanism is scored as a failure.** Real in
   high-dispersion regimes, correctly silent elsewhere → the silent slices count
   as failed slices → `REFUSED — survived 1 of 3`. The machinery cannot
   distinguish *"does not generalise"* from *"is conditional, exactly as
   declared."*
2. **The strongest available evidence is being thrown away.** A mechanism that
   fires where it said it would and stays silent where it said it wouldn't is
   far better evidenced than one that fires everywhere — firing everywhere is
   what beta does. We collect the discriminating half and discard it.
3. **`DEAD` is emitted where canon says `NOT_DETECTABLE`.** §19: below its own
   MDE is *not detectable, never a kill*. `adjudicate` says
   `"DEAD — explains its parent and nothing else"` whenever `n_fired == 0` and
   the run happened. Never firing can mean the precursor's thresholds are tight
   relative to the corpus, not that the claim is false. NIGHT-10 already
   established that **195 existing kills are absence-of-evidence**; this builds
   a new machine for making the same error faster.

### Order — scope-aware adjudication

- **Label every transfer slice** against the autopsy's own declaration:
  `AFFECTED` / `UNAFFECTED` / `OUT_OF_SCOPE`. The labelling is derived from
  `expected_affected_states` / `expected_unaffected_states`, which are frozen
  when the autopsy is minted — so it cannot be chosen after seeing results.
- **Export requires both halves:** clears its MDE in ≥k declared-AFFECTED
  slices **AND** shows no detectable effect in declared-UNAFFECTED slices.
- **Invert the sign where it belongs.** Failing in a declared-UNAFFECTED slice
  is **confirming**. *Firing strongly* in a declared-UNAFFECTED slice is
  **disconfirming** — it means the thing found is broader and dumber than the
  mechanism claimed. This makes the unaffected list a placebo family built into
  the hypothesis, which is what canon has always asked for ("new mechanisms
  carry their corpse as control") and has never had structurally.
- **Split the verdict vocabulary.** One of:
  `EXPORTABLE` · `CONDITIONAL_SUPPORT` (holds in declared scope, silent outside,
  below the bar to export but alive and re-testable) · `NOT_DETECTABLE` (ran,
  fired, below its own MDE — §19, never a kill) · `DEAD` (ran, fired, and was
  wrong-signed or failed its own falsifier) · `UNTESTED` (vocabulary failure —
  already correct, keep it). **Only `DEAD` closes anything.**
- **Every non-export carries `revisit_when`** — the condition that would make
  re-testing worthwhile (`n_effective > X`, the regime recurs, the corpus gains
  a feature). A kill without a resurrection condition is how a project loses
  ideas it never actually disproved.
- Re-run all six existing mechanisms through the new adjudication and restate
  `RESEARCH_GYM_1.md`. Expect verdicts to move; report every move.

This is not a loosening. Requiring the unaffected half to be *silent* is a
strictly harder test than the current one. It is a loosening only for
mechanisms that were never being tested against their own claim.

## 3. Rulings on the three escalations

### R10 — PARALLELISE THE NIGHT. Approved, with a registered amendment.

Ratified. The argument that licensed the `MAX_TOKENS` fix and cell-major
ordering licenses this identically: **zero valid nights have accrued, so there
are no results to change the rules after.** A pre-registration exists to stop
rules moving once data exists; there is no data.

The scientific case is stronger than the operational one. Cell-major exists so
the five arms of one cell see the same world. Running them **concurrently makes
them more simultaneous, not less** — it sharpens the primary contrast.

The operational case is that serial is not merely slow, it is **fragile in a way
that compounds**: 2.3h at mean latency, 4.2h at p90, against a window that must
end at 13:30 UTC. Latest safe start ≈11:10 UTC, ≈09:20 at p90. Over 40 nights a
meaningful fraction will refuse themselves, each refusal costs a calendar day,
and the trial's true duration becomes unpredictable. ~28 minutes makes it
comfortable.

Conditions, all binding:
- **Register the amendment BEFORE the first valid night.** Concurrency, retry
  policy and any changed rate-limit handling are named in the frozen prereg.
- **Re-run the full five-arm rehearsal concurrently** and verify: chain cursor
  integrity under concurrent minting; arms of one cell still resolve against one
  information timestamp; retry behaviour; vendor rate-limit response. A
  rehearsal that passes serially proves nothing about the concurrent path.
- Keep `assert_night_fits_before_open` armed. A faster night does not retire the
  guard; it just means the guard stops firing.
- If concurrency measurably changes yield or cost per cell, that is a finding,
  and it is reported before the accrual starts.

### R11 — Do NOT expand the transfer corpus in reaction. Approved as refused.

You were right, and for the right reason: expanding after seeing a mechanism sit
at 2 of 3 slices is choosing the test to fit the result. Approved path: a
**pre-declared** expansion — securities, periods and slice definitions written
down and committed *before* the run — applied to **all six** mechanisms
simultaneously, never to the near-miss alone.

Sequence it **after** §2. Expanding a scope-blind test just manufactures more
slices for a conditional mechanism to "fail."

### R12 — Per-actor Form 4 backfill. APPROVED.

It is the only thing that unblocks Actor Surprise, and the blocker is measured,
not assumed: `P(action | actor history)` on a median of one observation restates
the action.

The distinction that makes this safe, and it must be enforced in code, not
convention:

- The backfill computes **actor baselines** — how unusual is this action for
  this actor. It is a *reference distribution*, exactly like the 1990–2026 price
  history behind the base rates.
- It is **not** a COPY-LAB fill, **not** a track record, and **no signal derived
  from a backfilled event may enter COPY-LAB or any forward lane.** COPY-LAB's
  refusal of pre-inception trades stays absolutely intact — these are different
  objects and the code must not be able to confuse them.
- PIT-safe throughout: an actor's baseline as of date *d* uses only filings
  publicly available before *d*.

## 4. Ordered work

### MUST

**A1. 2026-08-16 — the first CAMPAIGN_FORWARD resolutions. ATTENDED.**
This is the headline of the day and the easiest thing on the list to lose under
the Gym work. It is the first time in the program's history that reality grades
a forward prediction. `--population campaign_forward`, dated receipt, never
pooled with `LIVE_FORWARD`. Report the resolution counts and nothing
interpretive — no reads of any accruing trial, no early H1.

**A2. Scope-aware adjudication (§2), and restate the six mechanisms.**
Blocks R11 and everything downstream.

**A3. Tomorrow's collector run — idempotency, measured for free.**
Whether `duplicates` absorbs the overlap. Answered by the receipt, not by
assertion.

**A4. The paid night — any day at or before 11:10 UTC, one attempt, hard stop.**
Do R10 first if it can be done cleanly; a 28-minute night removes the schedule
risk from all 40. If R10 slips, run serial inside the measured window rather
than waiting. Report measured all-in cost against the **$1.43/night**
break-even; balance $57.12.

### THEN

**B1. R12 — the actor backfill and Actor Surprise**, with the baseline/lane
firewall in code.
**B2. R11 — the pre-declared corpus expansion**, all six mechanisms.
**B3. The conditional register.** Every finding in the registry carries its
declared scope (regime · cap · sector · horizon · liquidity), and every kill
carries `revisit_when`. Then re-open the **graveyard census under scope
awareness**: of the 195 under-powered kills, which were killed on *pooled* data
where a conditional effect would be structurally invisible? This is the direct
execution of Murat's instruction and I expect it to return live ideas.
**B4. Put the −0.57pp BUY result in the README** beside the sell-side number.

### DEFERRED — still not started, reasons unchanged

T4 stress-shape · known-answer worlds · AegisEvolve · WORLD-MODEL-v1 (authorised
in principle, gated behind known-answer worlds + declared baselines; the
correctly-denominated substrate gate was cleared 08-15) · Mechanism Graph ·
REACTION-GAP-1 · OOD model · absence signals. Nothing here is cancelled. The
sequencing argument proved itself on 08-15: a network trained yesterday would
have learned a 2×-inflated regret signal and a 93%-artifact failure label, and
it would have looked like it was working.

## 5. Standing

`GymResult.as_claim()` keeps raising. No Gym number is an alpha claim. 10 lanes
at 69 days against a 24-month floor — no skill claims. LLM spend is not the
constraint ($17.65 lifetime, $0.00103 per structured autopsy); **schemas that
refuse untestable output are what convert spend into evidence**, so build the
schema before buying the volume. The 14.2% of calls producing nothing gradeable
is the real inefficiency — measure it per arm before spending more.

The 112 `LIVE_FORWARD` rows still sit on the volume; the guard prevents the
false claim, so quarantine them attended **after** A1, so the two events cannot
be confused.

## 6. Report back

1. A1 — campaign resolutions, counts, receipt
2. §2 — scope-aware verdicts, all six restated, what moved
3. Clocks — collector idempotency, paid night, measured cost vs $1.43
4. R10 — amendment registered, concurrent rehearsal results
5. R12 — backfill, Actor Surprise, firewall proof
6. B3 — conditional register, graveyard re-census, ideas returned to life
7. Defects found **by running things**
8. Tests / SHAs / deploy verification
9. Next bottleneck

— brain, 2026-08-15
