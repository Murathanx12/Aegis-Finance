# Night 1 — three ledger findings, verified, none remediated

**2026-08-16.** Ordered: determine before the paid night whether the 25 overdue
forecasts invalidate IIF-1 grading, and prepare the exact attended action if
they do. **Nothing here was fixed.** All three remedies are attended.

Reproduce: `python -m scripts.verify_live_forward_disarm` (offline, touches no
real ledger, exit 2 while either finding stands).

---

## A. The refusal predicate is defective — confirmed, and NOT armed on Monday

`evidence_population.py:387`

```python
established = shared < len(live)
```

Volume: 112 records, all content-identical to CAMPAIGN_FORWARD rows, so
`112 < 112` is False and `resolve_due` refuses. Reproduced against the real
guard:

```
BEFORE the first genuine write:  n_records=112  shared=112  established=False
AFTER ONE genuine record:        n_records=113  shared=112  established=True
resolve_due(population='live_forward') -> PROCEEDED   due=25
```

The predicate asks *"is any record genuine?"* where the decision it gates is
*"which records may be graded"*. One genuine write lifts it for the whole file,
including the 112 copies — 25 of them due as of today, matching production's
`n_overdue: 25` exactly.

**No second barrier.** The first 112 campaign rows carry **no**
`evidence_population` field (checked: 0 of 112 stamped), so on the volume they
are attributed to `live_forward` by file ownership and `assert_single_population`
sees no foreign population. Downstream, `resolve_all` rewrites the whole file —
nothing filters by population after the refusal.

**But it does not fire on Monday, and the reason is finding B.**

## B. Night 1's genuine records are born stamped `campaign_forward` — THIS is the date-bound one

Night 1 runs **locally and attended** by ruling: the deployed image cannot run a
paying night because `verify_or_refuse()` needs an `Aegis module` sibling it does
not have (`IIF1_PRE_NIGHT_1_CHECKLIST.md`). And `investigator_night.py:1485` is

```python
belief_state.append(all_records)          # no path, no population
```

On this machine:

```
campaign path : backend/data/optimus/predictions.jsonl
live path     : backend/data/optimus/predictions.jsonl
paths_coincide: True
an unstamped record written here is attributed: campaign_forward
```

So the volume never sees Night 1 — `112 < 112` stays False and finding A stays
dormant. What happens instead is its mirror: **the product's first genuine
forward evidence is written into the 20,073-row campaign ledger and stamped
`campaign_forward`**, and `stamp()` refuses to re-label afterwards ("a record
does not change population"). The mislabel is permanent by design, and it lands
on the one night that cannot be repeated.

This is not hypothetical and it is not a matter of tidiness: `LIVE_FORWARD` is
the population that certifies the deployed product. A night whose records enter
`CAMPAIGN_FORWARD` produces zero live forward evidence, however well it runs.

**Attended options, for Murat — pick one before the night:**

1. **Run Night 1 with the population named.** Smallest change, no deploy:
   `belief_state.append(records, path=<live ledger>, population="live_forward")`.
   Locally the paths coincide, so the *path* cannot separate them — the
   population argument is the only thing that can, and `stamp()` will then
   write `evidence_population: live_forward` onto each record. Requires a
   one-line edit to `investigator_night.py` before the run, which is a source
   change on the night's critical path — state that trade-off out loud.
2. **Run Night 1 as-is and rule that its records are campaign-population**,
   recorded in the receipt, with a separate later ruling on whether IIF-1 can
   certify from that population. Zero risk to the run; defers the question.
3. **Point `OPTIMUS_LEDGER_DIR` at a distinct live path for the run**, so the
   two paths stop coinciding and ownership attributes correctly. Environment
   only, no source change — but it creates a third ledger file, and a third
   ledger is how the first two got confused.

Recommendation: **(2) for the run itself, decided and written down before it
starts** — a one-line source edit on the critical path of a one-shot paid run is
exactly the improvisation the standing order forbids, and option 1 can be done
deliberately afterwards for Night 2. What must not happen is running the night
without having decided, and discovering the population afterwards.

## C. The container does not stay up, so the nightly resolver cannot be relied on

Two `aegis_verified_state` calls, ~28 minutes apart:

| call | `started_at` | `uptime_seconds` |
|---|---|---|
| 12:18 UTC | 2026-08-16T12:18:02Z | 1 |
| 12:53 UTC | 2026-08-16T12:46:51Z | 378 |

Two different start times inside half an hour: the container restarted, and the
first reading caught it waking on the request itself. Corroborated by
`n_resolved: 0`, `days_quiet: 4`, `n_overdue: 25` against a job scheduled
nightly.

APScheduler cannot fire at 20:30 UTC if nothing is running at 20:30 UTC.
`scheduler.running: true` reads true right now and has read true throughout —
it describes the process that is answering, not the process that was supposed to
run last night. **Verify by receipt count across three consecutive days, never
by `running`.** Remedies (a plan/setting that prevents sleep, an external
pinger, or moving the resolver off the container) are operational and outside
this session's mandate.

---

## Does any of this invalidate IIF-1 grading?

**Not by corruption — by stalling, if at all.** Nothing here writes a wrong
outcome onto an IIF-1 record. The exposure is that the machinery which would
grade them is (B) possibly pointed at the wrong population and (C) not reliably
running. `scripts/iif1_read_gate.py` takes `n_graded_nights` as an *input*; it
does not derive it from the ledger, so it cannot detect a grading pipeline that
never ran. **That is the open question I could not close from here** and it
should be closed before accrual, not before Night 1: Night 1 is one night
against a first licensed look at forty.

None of this is a reason to move Monday.
