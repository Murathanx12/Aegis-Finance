# PROPOSAL — decide on events, not on a 30-minute clock; and never compile a stop

**Origin:** Murat, 2026-09-05, on being asked whether to make the passed-deadline
gate permanent: *"never make permanent or hard rules — we will need to make
immediate and fast changes, we need to make changes at ready. we don't need time
boundaries but rather good timing. rather than waiting 30 min intervals to buy or
sell we might make realtime better calls."*
**Status:** proposal + one principle already applied. **Sequenced, not queued** —
part 1 is a standing rule from now on; part 3 must not ship before B2 §1-3.
**Roadmap:** amends `ROADMAP_2026-09-04_PROFIT_ENGINE.md` B2; new lane.

---

## 1. THE PRINCIPLE, ADOPTED: no compiled-in permanent stops

The question that prompted this was whether `deadline_liquidation_due` should
return `True` forever once the deadline date has passed. **The answer is no**,
and the reasoning generalises into a rule worth keeping:

> **A stop that cannot be lifted in seconds is a stop that will be lifted in the
> wrong way.** Every safety state is a DECLARED, INSTANTLY-FLIPPABLE value —
> an environment variable, a config row, a flag on a mandate — never a hard-coded
> permanent condition that needs a code change, a push, a build and a deploy to
> undo.

The fleet's disarm today is exactly this shape, which is why it worked in
minutes and needed no push:

| what | where | flip |
|---|---|---|
| ordinary entry pass disarmed | `AAT_LOOP_ARGS` contains `--manage-only` | remove the token from the variable |
| pre-open auction disarmed | `AAT_ENTRY_STYLE` absent on all six | set it back to `open_auction` / `staggered` |
| daily liquidation curfew | `exits.LIQUIDATE_BY_ET`, shared by the entry gate | config, one value, one predicate |

`deadline_liquidation_due` stays a **daily time-of-day curfew** — including its
sharp edge, that it returns `False` again the next morning. That edge is now
*documented and deliberately owned by the variable layer* rather than patched
into the predicate, because the predicate is shared with exits and a permanent
version would silently change exit semantics too. Two predicates that can drift
is the failure this whole block exists to fix.

**What this costs, stated plainly:** the safety of the fleet now rests on a
variable being right, not on code being right. So the variable's value must be
*visible* — `scripts/utilization.py` and the nightly learning report should print
the armed/disarmed state of every entry path per role, so "we thought it was
disarmed" cannot happen quietly. That is a small B2 addition and it is the price
of choosing agility.

## 2. WHY SHORTENING THE INTERVAL FIRST WOULD BACKFIRE

The instinct is right and the ordering matters. Today the loop enters every
**30 minutes** and exits every **5**. Making either faster, right now, makes
things worse rather than better, because the exit machinery is broken in four
measured ways:

1. **No minimum hold.** The only precondition for closing a share position is
   `cost_basis > 0` (`alpha/exits.py:371`). No book or contract carries
   `expected_horizon` or `min_hold` — the strings do not exist in the repo.
2. **60% of round trips close in the session they open** (hack3/4/6; 54.5% across
   all six roles), against a 21-session declared thesis. hack6's MLYS cycled
   three times; hack3's TNXP stopped at −3.5% and was re-bought **86 minutes**
   later.
3. **The stop that fires is not the stop that was declared.**
   `equity.STOP_FRACTION_BY_PROFILE` rests 8% at the venue for hack3 and 6% for
   hack4, and `exits.stop_hit` closes at a flat un-profiled **3%** on every
   5-minute pass. The graded receipt says it outright for TNXP: *"venue stop at
   8% never reached."* The same un-profiled 3% is also the sizing charge, so the
   per-name worst case is **understated ~2.5×** — one constant, two opposite
   errors.
4. **The re-entry guard cannot see these exits and fails open anyway.**
   `close_position` mints no `client_order_id`, `protect.py:105` keys on
   `aat-stop-`, and `runner.py:1136-1138` sets `stopped = set()` on any
   exception.

**A faster clock on that machinery is not better timing — it is more churn per
hour.** So: **B2 §1-3 (hold fields, contract-aware typed exits, a re-entry guard
that sees every exit) ship BEFORE any cadence change.** That ordering is the
whole recommendation of this section, and it is the one thing here I would push
back on if asked to reverse.

Note also what the evidence does *not* say: the churn has not been shown to lose
money. The only fill-level attribution on disk reads *"hack4 is the only book
with POSITIVE realized P&L (+$2,027: NVDA put spread +$1,368, **ABAT churn
+$798**, RZLV +$296)."* The mechanism is indefensible — a 21-session thesis
tested for 4 minutes — but "churn costs us money" is a hypothesis B2 §5's regret
decomposition is built to settle, not an established fact.

## 3. WHAT "GOOD TIMING" SHOULD ACTUALLY MEAN

A clock is a *poor proxy* for the thing we want, which is: **act when something
changed, and only when the change is worth acting on.** Three layers, in
dependency order:

### 3a. Event triggers replace the entry clock (after B2 §1-3)
The loop stops asking *"has 30 minutes passed?"* and starts asking *"has anything
happened?"* Candidate triggers, all of which the program already ingests:

| trigger | source already in the repo | why it is a decision point |
|---|---|---|
| a dated catalyst enters the window | `corpus_digest.dated_catalyst` | the thesis clock started |
| an 8-K item lands on a held or watched name | `backend/services/edgar_events.py` + the new `eightk_items` tape | a typed, dated state change |
| a target/estimate revision prints | `target_rev_1m`, `net_rev_1m` | the tape's own opinion moved |
| a price or realised-vol threshold crosses | venue stream | the position's risk changed, not the clock |
| a sealed book's admission set changes | the seal | our own opinion moved |
| the venue's own fill/partial-fill events | Alpaca stream | execution state changed |

The honest first version is **event-triggered evaluation with a rate limit**, not
tick-by-tick trading: an event wakes the pass, the pass still has to clear every
existing gate, and a per-name cooldown (which is what `min_hold` is) prevents an
event storm from becoming a churn storm.

### 3b. A decision-worthiness test, so a trigger is not an order
Waking up is not deciding. Each woken evaluation answers: *does this change the
action, by enough to pay the spread?* That is the same `P(changes the decision) ×
value − cost` test the program already applies to experiments (mission rule 5),
applied to trades. A trigger that does not move the action is logged as a typed
refusal and costs nothing — which also gives us the dataset for measuring whether
event timing beats the clock.

### 3c. Only then, faster reaction
With hold integrity in place and a worthiness test in front of the order, latency
becomes worth buying. Before that, it is worth nothing.

## 4. HOW WE WOULD KNOW THIS WORKED

Event-driven timing is a **hypothesis**, and the standing rule applies: it needs
an executable comparison, not an argument. The clean design is already available
because the fleet has six roles — run the clock arm and the event arm on
*separate roles with the same selector*, and compare:

- median hold vs declared horizon (the thing being fixed);
- realised slippage per decision;
- **premature-exit regret** — actual vs held-to-horizon vs held-to-next-review
  (B2 §5 computes exactly this);
- decisions per day, and the fraction that changed the action.

Which means B2 §5's nightly regret receipt is a **prerequisite**, not a
follow-up: without it there is no scoreboard on which "better timing" can win or
lose. And the entry-timing tournament this session paused (`open_auction` vs
`staggered`) is the existing precedent for that A/B — it should be restarted, on
fixed hold integrity, as the control arm for 3a.

## 5. WHAT WAS DONE TODAY, AND WHAT IS ASKED

**Done, variables only, no push, no code deployed** (all six loop services
verified afterwards: `ENTRY_STYLE` absent, `--manage-only` present, exits alive,
ledger chains intact, accounts flat):

- `--manage-only` prepended to `AAT_LOOP_ARGS` on all six → ordinary entry pass
  disarmed; proven by log line and by 0 entry passes across a full 30-minute
  cycle while 7 exit passes ran per role.
- `AAT_ENTRY_STYLE` deleted on hack4 and hack6 → the pre-open auction path is
  disarmed too. This was the gap: `scripts/agent_loop.py:330` runs the
  `open_auction` branch *before* the `manage_only` check at `:347`, so
  `--manage-only` alone did not cover it, and the daily curfew resets each
  morning. Unset is the intended control-arm state —
  `entry_open.entry_style()` returns `None` and `should_run` short-circuits.
- Held locally, **not pushed** (`fd0c75b` in the terminal repo): the structural
  entry-side deadline gate with a typed `PAST_LIQUIDATION_DEADLINE` refusal, and
  `Mandate.manage_only` as an explicit field so hack1's written "exits only"
  caveat is enforced by config rather than by prose.

**Asked of Murat:**

1. **Push `fd0c75b`?** Railway builds from GitHub, so the structural gate is
   inert until you do. The variables already hold the line, so this is not
   urgent — but two mechanisms are better than one, and the code version survives
   someone editing a variable.
2. **Restart the entry-timing tournament when B2 §1-3 land?** It is the control
   arm for §3a and it is currently paused by the `AAT_ENTRY_STYLE` deletion.
3. **`aat-loop-staging` is Failed** ("Deployment does not have an associated
   build") and was left untouched. Repair or delete?
4. One open question nobody has answered: **why was hack1 shorting PANW at all?**
   The mechanism is stopped, the selector is not. hack1 is `post_event_drift` on
   a fixed list containing PANW; whether that short was a legitimate drift claim
   or a sign inversion needs its decision rows read. If it is a sign inversion,
   it is a bigger finding than the churn.
