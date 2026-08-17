# The quarantine had a one-record release. It was diagnosed a day early, declined as attended, and it was not attended

**2026-08-17. Reproduced, fixed, and pinned by tests that fail on the pre-fix
source. The full fast suite is green (4630 passed, 14 skipped, exit 0).**

## Attribution first: this was already known

`scripts/verify_live_forward_disarm.py` — written before Night 1 — states the
defect exactly, in its own docstring:

> `ledger_resolver.resolve_due` refuses to grade LIVE_FORWARD while the
> population is unestablished… The predicate asks "is ANY record genuine?" where
> the decision it gates is "which records may be graded" — so the first genuine
> write flips it for the whole file, including the 112 copies, 25 of which are
> already overdue. **This is the house failure mode inverted. Every other guard
> this week fired when it should not have; this one stops firing exactly when it
> starts to matter.**

That session then declined to fix it: *"It does not fix anything and it does not
touch a real ledger. Both remedies are attended."*

**That reasoning was right about two remedies and wrong about a third.** Deleting
the 112 rows is attended (irreversible, outward-facing). Ruling on where Night
1's records belong is attended (a ruling, not a patch). But **narrowing the
predicate is neither** — it strictly *reduces* what an unattended job may grade.
It removes an automatic irreversible write and adds nothing. Leaving it for a
human was the one option that kept the risk live, and the risk sat unmoved for a
day while three sessions wrote about it.

The lesson generalises: **"attended" is a property of an action, not of a topic.**
A defect's neighbourhood being attended does not make every fix in it attended,
and bundling a safe fix with a dangerous one buys the delay of the dangerous one.

## What both reviews said, and what is actually true

Both reviewers read prod's `prediction_ledger` block — `n_records 112`,
`n_resolved 0`, `n_overdue 25` — as a dead resolver:

> GPT: "Railway's resolver is sleeping anyway… A sleeping process cannot run a
> scheduler. Move resolution to something guaranteed to wake/run."
>
> Fable: "the resolver is asleep at 25 overdue, 0 resolved."

It is not asleep. `aegis_verified_state` shows all seven scheduler jobs
registered, `pi_ledger_resolve` among them, next run 16:30 ET, jobstore
persistent. The job runs, calls `resolve_due(population="live_forward")`, and
gets back **`status: REFUSED`** from a guard added on 2026-08-15:

```
ledger_resolver.py:189   if pop is EP.EvidencePopulation.LIVE_FORWARD:
                             est = EP.live_forward_is_established(path=path)
                             if est["n_records"] and not est["established"]:
                                 return {... "status": "REFUSED" ...}
```

`0 resolved` is that guard firing on every tick. The 25 overdue records are the
quarantined campaign copies it is refusing to grade. **The scheduler needed no
work at all**, and "move resolution somewhere that wakes up" would have been
effort spent on a system that was already doing its job — while the actual defect
sat one item further down the same list.

This is the canon rule (*a scheduler's acceptance test is receipts, never
`scheduler.running`*) meeting its mirror image: **a scheduler that produces no
receipts is not necessarily broken — a guard that refuses produces no receipts
either, and the two look identical from the health page.** That is a reporting
defect, and it is fixed below.

## The defect: `established` is released by one unrelated record

`live_forward_is_established()` answers "has the deployed product accrued
anything the campaign did not already write?":

```python
established = shared < len(live)
```

That is the correct answer to that question. The problem is that
`ledger_resolver` used it as the gate on whether to **grade the file** — and
`resolve_all` rewrites the whole file. So the condition protecting 112
quarantined campaign copies is released by the arrival of **one** unrelated
record.

Reproduced on the real (split-path) prod topology before fixing anything:

```
BEFORE  established=False n=112  shared=112
AFTER   established=True  n=113  shared=112     ← one genuine record appended

records the resolver would then treat as due: 112
  of which content-identical campaign copies: 112
```

The next genuine forecast the deployed product writes flips the gate, and the
following 16:30 ET tick grades all 112 campaign rows into the live product's
forward record — **automatically and unattended**. Every surface reading "the
deployed product's forward record" would then be reading the swarm, which is the
exact outcome the 2026-08-15 adjudication exists to prevent. It was rebuilt one
level up: the *records* were quarantined, but the *gate* was not.

An outcome written onto a record is the thing that makes it evidence. It cannot
be un-written.

### How imminent it actually was — latent, not firing

Stated precisely, because overstating it would be the same error in the other
direction. **No production code path currently writes a genuine LIVE_FORWARD
record.** `why_moved` mints forward records but `write_ledger` defaults to
`False` and `pi_why_moved` does not override it; the other appenders
(`investigator_night`, `run_llm_swarm_1`, `run_optimus_specialists`) are local
and campaign-stamped. Prod's ledger confirms it: `last_written 2026-08-12`,
`days_quiet 5`. Nothing was going to fire tonight.

What makes it urgent anyway is **where** the trap sits. It fires the moment
someone enables a live writer — and enabling a live writer is precisely what
both reviews ask for next ("make Night-1 forecasts resolver-visible", "the lanes
are recording, not teaching"). The trap is not on a distant path; it is on the
next one.

### Why the review ordering made this worse

GPT's ordered list put "make Night-1 forecasts resolver-visible" at **1** and
"fix the quarantine defect before a genuine LIVE_FORWARD record can release those
old 112 campaign copies" at **3**. Item 3 is the correct observation — and item 1
is an instance of the action that *triggers* it. Working the list in order writes
a record to the live volume, releases the quarantine, and the damage lands before
the item that prevents it is reached. Item 3 was done first.

## The fix: quarantine per RECORD, not per population

- `evidence_population.quarantined_hashes()` — the copies' identity by content
  hash. Survives the population becoming established, because it never consulted
  a population-wide boolean.
- `belief_state.resolve_all(..., skip_hashes=...)` — named records are written
  back **verbatim** and counted in `skipped_quarantined`. Necessary because
  resolution rewrites the whole file: without it, earning the right to grade one
  record in a ledger is earning the right to grade every record in it.
- `ledger_resolver.resolve_due` — excludes the copies from `due` before the price
  panel is built (otherwise their tickers get fetched nightly forever and every
  one lands in `unpriceable`, reading as a resolver fault), and reports them under
  a separate `quarantine` key.
- The refusal now distinguishes **two reasons a record sits overdue**, because
  their remedies are opposite: a price gap is a bug to fix, a quarantined copy is
  supposed to sit there until Murat disposes of it. One conflated count is
  precisely how prod's "25 overdue" read to two reviewers as a dead resolver.

### The missing-input refusal, and where it binds

If the campaign ledger cannot be read, `shared` is 0, every copy looks genuine,
and the quarantine **clears itself** — the guard would pass *because* it could
not see the thing it checks. So `quarantined_hashes()` refuses on a missing
comparison set rather than returning a clean verdict.

Two deliberate narrowings, both of which cost a test to find:

1. `live_forward_is_established()` does **not** raise — health surfaces call it,
   and a missing repo artifact must not take a status page down. It reports
   `comparison_available: False`. Describing and refusing are different jobs.
2. The resolver refuses only when something is **due**. A ledger with nothing
   matured is in no danger whatever the campaign artifact's state, and refusing
   there would strand a clean live ledger on any machine with no campaign
   history — a guard inventing work rather than preventing harm. The condition is
   derived from the records, not declared.

## Night 1's 585 records do not need to reach `/data`

The reviews frame this as `predict → persist in git → STOP`, with the remedy
being a filtered path into the authoritative `/data` ledger. The framing of the
gap is right; the remedy is aimed at the wrong ledger.

All 585 records are stamped **`campaign_forward`** (verified: 20,073 untagged
legacy rows + 585 stamped, 117 per arm × 5 arms — the 117 confirming the three
cells lost with the `B_tools/ICE` failure). `campaign_forward`'s resolver is
`scripts/resolve_campaign_ledger.py`, **attended and local, by declaration**.
The production resolver is *forbidden* from reading the repo ledger, and
`assert_write_allowed` would refuse a copy of these records onto the volume as a
cross-population write. So:

- there is no plumbing to build for Night 1;
- the loop closes by running the attended campaign resolver;
- **nothing from Night 1 is due until 2026-08-21** (195 records at h=1) and
  2026-08-27 (390 at h=5). All 585 currently have `outcome: null` correctly.

That is four days of runway, and it means "the resolver loop is open" is a
statement about a deadline, not about today. The thing that would waste the
runway is building a `/app → /data` path that the population guard exists to
refuse.

## The verification script's own verdict was stale

`verify_live_forward_disarm.py` keyed its verdict and exit code on the
**predicate** (`disarmed and status != "REFUSED"`), so with the fix in place it
printed "THE GUARD DID NOT HOLD… 0 record(s) entered grading" — accusing a fixed
system in the same breath as reporting the fix. The predicate *should* flip: once
the product writes a genuine record the population genuinely is established. The
harm was never the boolean, it was copies entering grading. Retargeted at that,
it now reports:

```
resolve_due(population='live_forward') -> PROCEEDED
  due=0  newly_resolved=0  pending=1
  the guard held per-RECORD: it PROCEEDED (correctly — the population is
  established) but carried 0 campaign copies into grading, with 112 quarantined
  by content hash (25 of them past due).
```

Its exit code also gated on `not armed` — "Night 1's records will not reach the
live population" — which was a live warning before Night 1 and is **settled
history after it**. `armed` is now False permanently, so that gate could never
pass again. A gate that can never pass is not a guard; it teaches its readers to
ignore the exit code, which is the exact failure the house rule *the exit code IS
the guard* exists to prevent. It now gates the one thing still falsifiable:
whether copies can reach grading. Exit 0.

## What remains, in the order the dependencies actually impose

1. **DONE** — the one-record release, fixed and pinned.
2. Grade Night 1 through the **campaign** resolver, attended, on or after
   **2026-08-21**. Not a plumbing task.
3. Harden `dict(model_args)` **and stamp `implementation_version` on every
   receipt** in the same change. Fable's sharpest catch: hardening a treatment
   arm mid-campaign makes the 40 nights non-homogeneous, so the contrast must be
   reported within-version as well as pooled.
4. Per-arm failure counts on every receipt. A 0.5% cell failure cost 2.5% of the
   contrast and can only strike tool arms — it biases toward the null, which is
   the direction that looks like a clean negative.
5. Spend telemetry must fail conservative: unknown spend is not zero spend.
6. `arm_concurrency` **derived from the runner or refused** — the input nobody
   derived differed five-fold from the runner.
7. Attended and still unauthorised by "run the night": campaign `--commit`, and
   the LIVE_FORWARD quarantine disposition (deleting the 112 is Murat's, not a
   session's).

## On the research half of Order 14

Fable's two corrections stand and neither needs re-deriving here: the knowledge
cutoff is a look-ahead leak that prompt hygiene cannot reach (and "hide the
name" is unfalsifiable — you cannot show a model failed to recall), and
`k_eff = N/(1+(N-1)ρ̄)` means a thousand replays buy ~0.02 effective tests over a
hundred. Both are already canon. The one thing worth adding: **the scoring
harness in item 2 above is the prerequisite for every morning replay**, mechanical
ones included. Until outcomes can be graded, a replay is an unscored simulation,
and building more of them adds breadth of condition to a pile of ungraded work.
