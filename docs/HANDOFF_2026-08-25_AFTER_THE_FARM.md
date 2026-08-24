# HANDOFF — after the farm (written 2026-08-24 night)

**Supersedes** `docs/HANDOFF_2026-08-24_NEXT_SESSION.md` for sequencing. Read
`docs/SESSION_2026-08-24_NIGHT_PORTFOLIO_FARM.md` for what changed and
`docs/FINDING_2026-08-24_HOLDING_PERIOD.md` for the one result.

Every session from here **opens with the RESULTS SCOREBOARD**, before code or
test counts. If a session ships thirty excellent engineering changes and moves
none of those numbers, it says **RESULT IMPROVEMENT: NONE** in the first
paragraph. This one did.

---

## FIRST ACTS, in order, before anything new

1. **Confirm the migration gate.** `python -m scripts.monday_gate_check`. The
   three ET jobs (`pi_options_pit` 15:30, `pi_why_moved` 17:15, `pi_arena_daily`
   17:45) fire on 2026-08-24 ET, which is **05:30-05:45 HKT on the 25th**.
   Murat's PC does not need to be awake — Railway owns them. Inspect at 10-11am
   HKT or whenever.
2. **Wire the return-path guard into `why_moved`.** It is the last of the seven
   direct DeepSeek call sites without one, deferred only because it fired
   tonight. Once the run is confirmed: `_lang.guard(...)` on the reply, delete
   the `DEFERRED` entry, suite goes green with an empty exemption list — which
   is the stated goal of that dict.
3. **Launch `EVENT_RESPONSE_v1` as the first independent book.** The loader
   defect that made this impossible is fixed and proven end-to-end; what remains
   is (a) an entry in `selector_identity.SELECTORS` declaring the families it
   reads with `baseline=None`, (b) the book in the arena YAML with its own
   `selection_signal:`, (c) its score present in the day state. Run
   `lane-integrity-check` before and after, and `seed-a-lane` is attended —
   Murat flips the flag.

---

## THE QUESTION MURAT ASKED THAT I DID NOT CHANGE ANYTHING FOR

> "We are finishing the pre-market 2 hours early — maybe it's better if it is
> closer to market open so we don't lose some news."

**The observation is right and the change must not be made yet.** Three facts:

* IIF-1 ran 17:18-19:11 HKT; the US opens 21:30 HKT. So the information state
  freezes **2h19m before the open**, missing the late-Europe session and all US
  pre-market.
* **IIF-1 is a FROZEN pre-registration, 6 of 40 graded nights in.** Decision
  time is part of the information state, so moving it re-identifies the
  treatment mid-trial. `DecisionTimeStale` exists precisely to refuse that.
  Six nights of clean forward record is not worth spending on a guess.
* The run takes **~1h53m** and there is a `NightWouldSpanTheOpen` guard. Starting
  at 19:00 HKT would finish ~20:53 — 37 minutes of margin, and a slow night
  VOIDS instead of merely being late.

**So measure it instead of moving it, and it is cheap.** Snapshot the IIF
feature/information state at 17:00 HKT and again at 20:45 HKT for five days and
diff them. If the state barely moves, the question is closed for free and the
frozen clock costs nothing. If it moves a lot, that is a quantified argument for
a SUCCESSOR trial (`IIF-2`) with a later clock — declared in advance, not an
amendment to a running one.

Nobody has done this. It is a small script and it is the right next thing on
that front.

---

## THE VOCABULARY CHANGE, ADOPTED

`STOP` is retired from exploratory work. Use:

`FAILED_VARIANT` → `DEPRIORITIZED` → `RETIRED_FROM_CURRENT_SEARCH`

and reserve **`MECHANISM_REJECTED`** for genuinely broad evidence. Applying it
backwards, as the review directed:

* GRAPH-MIDCAP closes **shared-broker co-coverage propagation as formulated**.
  It does NOT close supply-chain, customer/vendor, common-ownership,
  activist/insider or event-propagation graphs. Those are different mechanisms.
* REVISION-FORECASTER closes **the numeric-event → analyst-revision → return
  route**. It does not weaken `MANAGEMENT_EVASION_DELTA`, which could act
  through volatility, downside tails, guidance credibility, future negative
  events or disagreement without revisions mediating anything.
* RELATIVE-VALUE-v1 closes **seven tabular features and a small MLP**. Not
  relative-value substitution.

---

## THE CHUNKS, with what today changed about each

**CHUNK A — `PORTFOLIO_FARM` + `ASOF_REPLAY`. BUILT.** ~1,000 policies over
2013-2024 across three presets. Follow-ups, cheapest first:

* `--preset breadth` — **RUN, and it does not rescue the result.** k=3..50 at
  h=21: momentum's best is k=50 at $26,804, the 85th percentile of chance, every
  smaller k worse. Concentration was not what was missing. (k=3 and k=5 give
  identical results under both sizings — a 20% cap makes those books
  all-at-the-cap, so sizing has nothing left to decide.)
* `--preset phase` — **RUN, and it changed the answer.** At k=12 the rebalance
  PHASE moves terminal wealth 1.8x-3.8x, wider than any gap between the
  strategies compared. The originally published `$38,815` was the MAX of a
  distribution whose median is `$16,633`. **Never quote a farm result from one
  phase again**; `farm.across_phases` reports the median with its spread beside
  it, and the spread is itself the finding.
* **The remaining multi-path work.** Phase medians rest on 5-7 offsets, not the
  full cycle, and there is still only ONE price path. A block bootstrap over
  formation dates would give a leaderboard row an interval rather than a number.
  That is the difference between "this rule beat the market" and "this rule
  would have beaten the market on the one history we have".
* Delisting sensitivity: re-run at `delisting_return` 0.0 and -1.0 to bound the
  assumption. One command, nobody has spent it.
* Re-pull `openprc`/`retx`/`shrout` for CRSP 1990-2012 (`AegisWRDSPullNight`
  exists). That triples the window and lets a policy be tested across regimes
  instead of one.

**CHUNK B — HUMAN/TEACHER PORTFOLIOS.** Unchanged and unblocked. The repo already
collects Congress (PIT, disclosure-date), ARK, Form 4, 13F and IBES; it measures
these actors and never gives them portfolios. `ACTIVIST_13D_v1` is the highest
prior — 5-business-day filing deadline, Item 4 intent is exactly what an LLM
reads well and a numeric learner grades. **Give each mechanism a virtual
portfolio in the farm** rather than another descriptive score; that is now a
half-day of work instead of a build, because the simulator exists.

**CHUNK C — `SELL_SIDE_BRAIN_v1`.** Unchanged.

**CHUNK D — `GLOBAL_PREMARKET_RELAY_v1`.** Unchanged. Note the connection to the
pre-market timing question above: a relay brain's whole value is the hours IIF-1
currently freezes before.

**CHUNK E — `MANAGEMENT_EVASION` prototype.** The "blocked pending transcript
purchase" claim is **withdrawn**. Open Q&A corpora exist (Lamini earnings-calls
QA, CC-BY, ~860k rows). Prototype first, buy only if the prototype earns it.

**CHUNK F — sector intelligence packages.** Data and causal ontology, not
personas. The repo's own experiments already showed role prompts produce one
brain.

**CHUNK G — richer relative value, then `DISAGREEMENT_LAB` / `META_ROUTER`.**
Still gated on three independent selectors existing. Today the count is 1 and
the BLOCKER to 2 was removed.

---

## OPEN, AND EACH NEEDS A DECISION RATHER THAN A SESSION

1. **$28.50 of DeepSeek spend over 9 days is unattributed** because production's
   telemetry file lives on Railway's volume and is not readable from the dev box.
   Either expose a spend summary on `/api/health/full` or run
   `python -m scripts.llm_cost_audit` there. Until then, no figure may be called
   programme-wide spend. Snapshotting is now automatic-capable
   (`--snapshot`), so every future delta is exact rather than measured against a
   hand-typed constant.
2. **Momentum at 12 names does not beat the market over 2013-2024**, net of 12
   bps — best net median **$35,228** against **$39,951**. That is not a reason to
   stop; it is the calibration for everything the farm tests next. Any new
   mechanism's first question is now "does it beat $39,951", not "is it
   significant". And the second question is "what is its phase spread" — a rule
   whose spread is wider than its edge has not been shown to have one.
3. **The IIF-1 read schedule stays frozen** at 40/80/120. Grading is continuous
   and automatic; READING the aggregate is what the gate blocks. A separate
   product surface showing yesterday's predictions vs outcomes is wanted and
   must not touch the frozen trial.
