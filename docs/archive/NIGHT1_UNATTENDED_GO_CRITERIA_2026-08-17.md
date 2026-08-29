# Night 1 — go/no-go criteria, written before the readiness numbers arrived

**2026-08-17, ~17:25 local.** Murat left for the gym at 17:05 with: *"you have
full permission, since I am not here dont wait for me do everything yourself."*

That is an explicit authorisation to run the paid night unattended, and it
overrides the standing rule from Orders 8–12 that the night is his own
keystrokes. I am taking it as his decision and proceeding — **but the reason
that rule existed does not disappear because the rule was lifted.** Order 12
assigned exactly one check to human eyes: *the evidence population named in the
receipt*. If I am going to discharge that check on his behalf, the standard has
to be written down before I can see what would pass it.

Frozen SHA: **`8393c03`**, working tree clean.

---

## GO requires all six

1. **The pre-open guard passes at `arm_concurrency=1`** at the actual start
   time, with **≥60 minutes of headroom**. Not the 121 minutes it showed at
   17:09 — the number at the moment of launch. Serial, because a verdict that
   holds on the pessimistic branch does not depend on a caller-supplied number.
2. **`night_cache_sentinel --before` returns OK** — no rate-limit breaker
   already hot from another process.
3. **The readiness assembly's own log carries none of the abort patterns**
   (`Yahoo rate limit hit`, `serving stale history`). The readiness run does a
   full 40-name assembly against Yahoo, so it is itself the exposure the
   sentinel was written for, and its log is a captured log.
4. **The population is what was declared.** Trigger count equals the frozen
   `TRIGGERS_PER_NIGHT`, five arms, no substituted or sandbox universe, and the
   snapshot is a production snapshot rather than a sandbox one.
5. **Projected spend is inside the declared ceiling** and inside the recorded
   balance.
6. **The tree is still clean at `8393c03`** at launch. No source edit on the
   critical path — including mine.

## STOP AND REPORT on any of these

* Any guard refuses. **A refusal is a finding**, and the finding is the output.
* The population differs from the declared one **in any way that requires a
  judgement about what Murat intended**. I can check *"is this what was
  declared"*; I cannot check *"is this what he meant"*, and the difference is
  the entire reason that check was assigned to a human.
* Any sign of stale or degraded input data.
* Spend projection over the ceiling.
* Anything I did not anticipate in this document. An unanticipated condition at
  18:00 on a one-shot paid run is not a thing to improvise through; the window
  runs to **19:10 local** and stopping costs less than guessing.

## What I will not do regardless

* **No source edit on the critical path.** If something is broken, that is the
  night's result.
* **No second attempt.** One attempt is the rule and a retry is a different
  experiment with a spent snapshot behind it.
* **No campaign `--commit` and no `LIVE_FORWARD` quarantine.** Those are
  separately and repeatedly reserved as attended operations, and "run the night"
  is not authorisation for them. They wait for him.
* **No push before the night completes.**

## Why this file exists at all

The criteria above are the kind that get adjusted by one number once the number
is visible — 60 minutes becomes 45, "as declared" becomes "close enough". That
is exactly the failure this programme keeps finding in its own work, and the
only defence that has ever worked is writing the threshold down while it is
still cheap to be strict.
