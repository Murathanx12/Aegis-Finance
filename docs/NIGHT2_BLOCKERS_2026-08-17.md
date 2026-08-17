# Three Night-2 blockers, and the two that behaved unlike the order predicted

**2026-08-17, after the quarantine fix
(`docs/LEDGER_QUARANTINE_RELEASE_2026-08-17.md`). Every number below is from a
receipt or a test, not from a recomputation of the orders.**

---

## 1. The `dict(args)` crash — reproduced exactly, then fixed

The reviews called it `dict(model_args)`. There is no `model_args` anywhere in the
tree; the real line is `investigator_agent.py:444`. Reproduced against the
pre-fix source, and it prints the receipt's error verbatim:

```
PRE-FIX                                    POST-FIX
[B_tools/ICE] investigation failed         status          : ok
  investigator_agent.py:444                n_forecasts     : 3
    args = dict(call.get("args") or {})    tool_call_drops : {'args_not_a_mapping': 1}
ValueError: dictionary update sequence
  element #0 has length 3; 2 is required   CELL SURVIVED   : True
status : failed   n_forecasts : 0
```

A malformed tool call now costs a **lookup**, never a cell. Four shapes are
handled, and one of them is the one that would *not* have raised:

* `args` not a mapping — the Night 1 case;
* `call` not a mapping;
* **`calls` a bare string** — this would have iterated as CHARACTERS and produced
  six nonsense tool calls with no error at all. Worse than the crash that was
  found, and it was one line away.

**Deliberately not permissive.** `[["ticker", "AAPL"]]` is coercible by `dict()`
and is still refused: inventing an interpretation of a malformed reply would
silently change which tool ran with what arguments, and for the anonymised arm a
guessed `ticker` would redirect a lookup to another company. A tool that does not
run beats a tool that runs on guessed arguments.

## 2. Per-arm failure counts, and the asymmetry stated as a test

`tool_call_drops` uses its own closed vocabulary, separate from `DROP_REASONS`,
because the two are not the same kind of event: a forecast drop costs a forecast,
a malformed tool call cost the whole cell. Counts appear on **every** receipt
including clean ones — a field that only shows up when it is bad teaches the
reader that absence means fine, and this count's entire value is being read on
clean nights.

The reason it is per-arm rather than a night total is pinned by
`test_a_snapshot_arm_can_never_record_a_tool_call_drop`: `A_snapshot` cannot
reach the code that records it. So the losses are **one-sided by construction** —
a bias with a direction (toward the null, which is the direction that looks like
a clean negative), not noise. A night-level count would average that away into a
number that looks tolerable while the primary contrast is already skewed.

## 3. `implementation_version`, plus the fingerprint that checks it

`IMPLEMENTATION_VERSION = 2`. Night 1 ran at 1. Hardening the tool-call parsing
changed the behaviour of the tool-using arms **mid-campaign**, so a contrast
pooled across the boundary mixes two versions of B, and the analysis must report
within-version as well as pooled. This was the sharpest catch in the reviews and
the fix had been ordered without it.

A hand-maintained integer is on the honour system — the person changing arm
behaviour is the person who must remember to bump it — so the receipt also carries
`arm_implementation_fingerprint`, a hash of the module that *defines* arm
behaviour. Two nights with the same version and different fingerprints are a
forgotten bump, detectable afterwards instead of assumed away. An unreadable
source returns `UNAVAILABLE` rather than a stable-looking constant that would make
different implementations compare equal.

---

## 4. The timing guard — where deriving the input made it WORSE

The order was "make the guard derive `arm_concurrency` or refuse". Doing exactly
that makes the guard **less safe**, and the measurement is unambiguous. Against
Night 1's actual 133-minute wall clock (40 cells, 199.5 s/cell):

| basis | projected | vs reality |
|---|---|---|
| serial, calls/cell 7.085 | **205.5 min** | over → safe |
| conc=5 at declared efficiency 2.0 | 102.7 min | **under → unsafe** |
| conc=5 at "measured" efficiency 3.529 | 58.2 min | **under → unsafe** |

The realized speedup at concurrency 5 was **1.545×**, below the declared 2.0
whose own comment calls it conservative. And the 3.529 that
`measured_concurrency_efficiency()` reports counts **calls in flight, not
wall-clock speedup** — feeding it in is a measurement that makes a guard more
dangerous.

So: **the refusal is computed on the serial branch, always.** A verdict that
holds serially does not depend on an input the guard cannot verify. Concurrency
is still derived (and still refuses when the frozen registration is unreadable),
but it now sizes only an informational projection reported beside the decision —
so the model's error becomes a measured quantity next night instead of an
argument.

### Calls per cell: derived, with three rules that each cost something

`MEASURED_CALLS_PER_CELL = 4.8` has *measured* in its name and came from a
rehearsal. Night 1's receipt says 1417 calls over 40×5 = **7.085**. Order 13
computed that correction and never applied it — a number in a document is not a
number the guard reads.

* **Void and sandbox nights excluded.** 2026-08-14 reads 2.8 because it was
  truncated, not because it was efficient. Projecting a complete night from an
  incomplete one is the denominator error in a new costume.
* **Maximum, not mean.** An average projection is wrong half the time in the
  direction that contaminates the trial.
* **Never below the declared constant.** Observations may only make this guard
  more conservative. One cheap night must not talk the projection down into a
  window it does not fit.

### The number that moved, and the direction it moved in

```
serial latest safe start   11:10Z  ->  10:04Z      (19:10 -> 18:04 local)
```

**Measuring the runtime cost 66 minutes of window.** More data bought less
freedom, because the constant it replaced was optimistic. This reproduces Fable's
corrected figure exactly, from the code rather than from arithmetic in a review.

### What the corrected model means for Night 2's start time — a decision, not a fix

Serial projection is now **205.5 min** (was 139.2). Against the 13:30Z bell, with
local = UTC+8:

| local | Z | available | headroom | ratio |
|---|---|---|---|---|
| 15:00 | 07:00 | 390 | 185 | **1.90×** |
| 16:00 | 08:00 | 330 | 125 | 1.61× |
| 17:00 | 09:00 | 270 | 65 | 1.31× |
| 18:04 | 10:04 | 206 | 1 | 1.00× — **guard refuses after this** |
| 19:10 | 11:10 | 140 | −65 | 0.68× (the old "latest safe start") |

**The 1.9× cushion the planner targets now requires starting at 15:00 local — and
15:00 is the freshness floor** ("not before 15:00", so the tool arms are reading
something recent). So the corrected model leaves **no start that gets more than
1.9× without breaking the freshness floor**, and the ordered 17:00 buys 1.31×.

That is a trade-off between cushion and information freshness, and both sides are
declared preferences rather than things a session should settle. Flagging it
rather than picking: 15:00 for margin, 17:00 for freshness, nothing after 18:04 at
any price.

**DECIDED 2026-08-17 (review session, on Murat's delegation): 17:00 local stands.**
Four reasons, in order of weight:

1. **The 1.31× is against the worst case, not the expectation.** 205.5 min is the
   serial decision basis; the runner executes at concurrency 5 and Night 1's
   realized wall clock was 133 min, so 17:00 carries a **2.03× cushion against the
   only night that has ever run** — and still completes with 65 min spare if
   concurrency delivers nothing at all.
2. **The 1.9× target was priced in a 139-minute world.** It is a planner
   preference formed under the wrong constants, not a registered parameter.
   Preserving the *ratio* by sliding to 15:00 buys it at the cost of the thing the
   freshness floor exists to protect — and fresh inputs are the treatment arms'
   entire mechanism.
3. **The failure modes are asymmetric.** At 17:00 the bad outcome is a truncated
   night: bounded (one of 40), loud (receipt shows it), and already excluded from
   the calls/cell derivation. At 15:00 the bad outcome is systematically staler
   snapshots on every remaining night — unbounded, silent, and sitting directly on
   the measured contrast.
4. **Consistency.** 17:00 is the ordered start Night 1 ran under; moving it now
   adds a second information-set boundary mid-campaign on top of the
   `implementation_version` 1→2 boundary this same commit created.

Standing rule attached to the decision: **the guard is never overridden.** If the
derived calls/cell grows past ~9.3, the serial projection exceeds 270 min and the
guard will refuse a 17:00 start — the response is that the *next* night starts
earlier (the readiness report now prints the derived latest-safe-start, so the
operator sees it the day before), never that the refusal is argued with. Margin is
bought when the measurement says it is needed, freshness kept when it is not.

### A second source of truth, found on the way

`iif1_run.readiness_report` computed the operator-facing "latest safe start" from
`projected_night_minutes`'s **module defaults** — so a human would have read a
deadline based on 4.8 calls/cell while the guard enforced 7.085, about an hour
apart, with nothing saying so. The report now reads calls/cell from the same
derivation the guard uses, prints its basis, and names the serial row as the one
to plan from. It also handles `ConcurrencyNotDerivable`: only
`NightWouldSpanTheOpen` was caught, so the new refusal would have been laundered
into a generic "session window unavailable", which is how a refusal stops being
read as information.

---

### And a scoping error CI caught, which is the sharper half of the lesson

The first version made `derive_runner_concurrency()` a **hard precondition** of
the guard. `verify_before_push` refused with 15 failures: the CI-simulated world
hides the `Aegis module` sibling, so `verify_or_refuse` raises there, and the
guard refused outright — no projection possible in **any** environment without the
sibling repo.

That was the wrong coupling, and the reason is the same one that made serial the
decision basis: **the verdict consumes no concurrency value, so refusing on an
unreadable registration refused on an input the decision never reads.** Planning
and readiness reporting legitimately run without the sibling; a *paid* night
cannot (`verify_or_refuse` already gates the first dollar), so nothing is weakened
by letting the projection through.

The teeth stay exactly where they bite:

| situation | behaviour |
|---|---|
| registration readable, no argument | derive, report it |
| registration readable, argument disagrees | **refuse** — the five-fold gap |
| registration unreadable, no argument | serial decision stands; concurrency reported `UNAVAILABLE_PREREG_UNREADABLE`, informational projection **omitted, not guessed** |
| registration unreadable, argument supplied | **refuse** — a claim that cannot be checked |

Generalised: **scope a refusal to what the decision actually consumes.** A guard
that refuses on an unused input is not more careful, it is broken in a new place —
and I would not have found it without the CI-simulated world, because my direct
run was green on 4666 tests.

## The frozen-pre-registration guard caught me, and it was right

`DECLARED_CONCURRENCY_EFFICIENCY` was changed from 2.0 to the realized 1.545.
`verify_or_refuse()` refused the tree:

```
FrozenPreregDrifted: the runtime disagrees with the registered rule on
['DECLARED_CONCURRENCY_EFFICIENCY']: {'runtime': 1.545, 'frozen': 2.0}
```

That constant is **part of the frozen pre-registration**, so editing it is an
amendment to a registered trial — attended, and not a session's call. The edit was
reverted and the finding recorded in the comment instead.

This is the same distinction that made the quarantine fix legitimate, arriving
from the other direction: *"attended" is a property of an action.* Amending a
registered parameter is attended. Restructuring the projection so the decision no
longer depends on that parameter is not — and that is what was done, which is also
why **nothing operational is waiting on the amendment.**

`MEASURED_CALLS_PER_CELL` and `MEASURED_CALL_SECONDS` are *not* frozen, which is
why deriving them needs no amendment; `MAX_ARM_CONCURRENCY` *is*, which is why it
is the correct thing to derive concurrency from.

---

## Verification

* **Full fast suite green** (see the run recorded with this commit); the new files
  add 39 tests across
  `test_malformed_tool_calls_cost_a_call_not_a_cell.py` (12),
  `test_receipt_records_the_arm_boundary.py` (6),
  `test_timing_guard_derives_its_inputs.py` (14), plus 7 updated.
* The malformed-tool-call tests were confirmed to **fail on the pre-fix source**
  by reproducing the ICE crash directly, not merely by an import error.
* `exchange_calendars` had gone missing from the dev environment mid-session; it
  is a declared requirement and was reinstalled. 33 of the 38 failures in an
  intermediate run were that, not the change — the remaining 5 were real and are
  fixed above.

## Tests that were changed, and why that is not a weakening

Six timing tests pinned literals from a 139-minute world (`n_calls_projected ==
960` is 40×5×4.8). They now compute their boundaries from `_guard_minutes()` — the
**same basis the guard decides on** — so a future measurement moves the tests and
the guard together instead of turning six tests red on a correct change. Two that
encoded arithmetic (`09:00 fits at p90`, `11:20Z fits in winter`) were rewritten
to assert the property their own names claim: a slower vendor moves the deadline
**earlier**, and a start exists that fits a 14:30 bell and refuses a 13:30 one.

`n_calls_projected` is still a literal — **1417** — because that is the one place
the measured total should be readable rather than recomputed.
