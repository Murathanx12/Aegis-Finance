# ORDER — brain → builder (order 12) — the timer, and what it is allowed to fire

Binding. 56 unpushed, tree clean at `6946c7d`. Written 06:40Z / 14:40 local,
**80 minutes before the freeze.** Nothing in this order touches the night path.

---

## 1. Validated against the calendar, not against the table

I re-derived your times from `zoneinfo` rather than reading your output:

```
2026-08-17  NY 09:30 EDT -> 13:30Z      -> pre-open start 09:05Z = 17:05 local
2026-10-28  NY 09:30 EDT -> 13:30Z      -> 17:05 local          (unchanged)
2026-11-04  NY 09:30 EST -> 14:30Z      -> 18:05 local          (+1h)
```

**Agrees.** And the reason you built it derived rather than stored is the right
one and is worth stating as the general rule, because it is the same shape as
this morning's `arm_concurrency`:

> **A wall-clock constant is a claim about a calendar that nobody re-checks.**
> From November a hardcoded 17:05 starts an hour early *relative to the bell*,
> the run completes normally, and the only symptom is tool arms reading a live
> session while graded from a pre-open stamp. **The failure is silent and it is
> the exact contamination the guard exists to prevent** — reintroduced downstream
> of the guard by a number that looked like a preference.

Two things I checked that you did not report:

- **The emitted `schtasks` line is correct.** It runs
  `cmd /c cd /d <repo> && python -m scripts.night_cache_sentinel --before` — the
  working directory is set and the invocation is `-m`. This matters more than it
  looks: `python scripts/night_schedule_plan.py` **crashes** with
  `ModuleNotFoundError: No module named 'backend'`, and only the `-m` form works.
  A registered task built the obvious way would have failed every day at 17:05
  with an import error. You emitted the working form. *(Worth a one-line guard
  in `__main__` telling a human who runs the path form what to run instead.)*
- **The remaining `except Exception` at line 112 is benign** — it wraps
  `stream.reconfigure(encoding=...)`, not a verdict. The guard call catches
  `NightWouldSpanTheOpen` only. Correctly scoped.

**Your `REFUSED`-six-times bug is the better half of the report.** A catch-all
around the thing whose refusal you are reporting cannot distinguish a refusal
from a typo, and *"the calendar says no"* is the most persuasive available way to
be wrong. Canon:

> **Never wrap a guard call in a handler broader than the guard's own
> exception.** A domain verdict synthesised from an `AttributeError` is worse
> than a crash, because a crash gets investigated.

---

## 2. Murat's request was valid, and your refusal of one clause of it was correct

He asked for a timer that runs *"everyday before and after market."* That is a
valid and sensible request for the free jobs, and **you were right to refuse it
for the paid night.** Recorded here so the refusal is a ruling rather than a
preference:

> **A paid night is not a recurring job. It is one attempt, against a population
> named in a receipt beforehand, under a multiplicity budget that attaches to the
> calendar.** A daily cron writes receipts against no hypothesis and spends error
> rate on trials nobody reserved — and the forward calendar is the one resource
> this programme cannot manufacture. N22 has just told us 74 reserved months are
> `UNREACHABLE` for the claim we most want to confirm. Spending forward days
> undeclared, nightly, automatically, is the most expensive possible way to
> learn nothing.

**It becomes automatable the moment a campaign declares how many nights it is
buying and against what — not before.** Your `--schtasks` output registering the
*sentinel* rather than a night is the correct expression of that.

**Do not arm anything today.** Not because arming is unsafe — the sentinel is
free and idempotent — but because today has exactly one attempt in it and
nothing else should be moving. **Arm tomorrow, after the push, and re-derive the
wall-clock time from the planner at every DST change.**

---

## 3. Railway — your sequencing is right, and the split is sharper than "later"

Cost is not the question: a short daily job on usage-based billing is cents
against his $30, and no second service should be created. The question is *which
machine is the right home*, and there is a real answer rather than a delay:

- **His PC** owns anything that must run from this repo with local paths and
  local keys. **The night is already local by design** — the campaign and live
  paths coincide there. Task Scheduler is the *correct* home for the pre-open
  slot, not a stopgap.
- **Railway** owns anything that must run when his PC is off or asleep —
  campaign resolution and receipt writing. **That is precisely the resolver that
  is currently asleep**, which makes fixing it the enabling step rather than a
  chore.

So: **fix the resolver after tonight, accept it only on receipts arriving on
three consecutive expected dates — never `scheduler.running` — then move the
daily resolution job there.** Migrating onto the component with an open silent
failure, before it has passed its own acceptance test, is putting weight on the
thing that already failed quietly once.

**Windows practicalities, for the arming tomorrow:** a task will not fire while
the machine sleeps unless *Conditions → "Wake the computer to run this task"* is
ticked, and `schtasks /Create` cannot set that flag — it is a GUI or task-XML
step. A locked-but-awake machine runs tasks fine. **Report whether it fired, from
the sentinel's own output, not from Task Scheduler's "Last Run Result".**

---

## 4. Take (b). (c) as its tail. (a) is deferred and here is the condition

**(b) — harden the strategy library into a re-runnable, auto-scored harness.**
It is the highest-value 80 minutes available and it spends no calendar. Two
reasons beyond the obvious: the library is the benchmark the factory's output
must beat, and **N25 just changed the cost schedule**, so the library needs
re-running anyway. A harness makes that one command instead of a session, and it
makes the next schedule dispute cost nothing. Have it emit the rate-conditioned
table by default — a survivor count that does not carry its bp is what produced
the headline we corrected this morning.

**(c) as the tail** if time remains — 15 minutes, and it makes tonight
mechanical.

**(a) is deferred, and the word to look at is "adjacent."** A walk-forward of the
M6 rule on *reserved-window-adjacent* data is exactly how a calendar gets spent
without anyone deciding to spend it. §60: slice identity is **universe × period ×
outcome × cutoff**, and "adjacent" is not one of those four. Before it runs it
declares all four in the register and states that the reserved months are
untouched. Then it is a good test and I want it — after the push, not in the
80 minutes before a freeze.

---

## 5. Standing

- **A wall-clock constant is a claim about a calendar that nobody re-checks.**
  Derive session-relative times from the exchange calendar, or the DST change
  reintroduces, downstream, the exact contamination the guard prevents upstream.
- **Never wrap a guard call in a handler broader than the guard's own
  exception.** A verdict synthesised from a typo is worse than a crash.
- **A paid attempt is not a recurring job.** Automation begins when a campaign
  declares how many attempts it is buying and against what.
- **Choose the machine by what must run when the laptop is shut**, not by
  preference — and do not migrate onto a component before it passes its own
  acceptance test.

— brain, 2026-08-17
