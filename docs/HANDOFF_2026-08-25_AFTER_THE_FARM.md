# HANDOFF — after the farm (written 2026-08-24 night)

**Supersedes** `docs/HANDOFF_2026-08-24_NEXT_SESSION.md` for sequencing. Read
`docs/SESSION_2026-08-24_NIGHT_PORTFOLIO_FARM.md` for what changed and
`docs/FINDING_2026-08-24_HOLDING_PERIOD.md` for the one result.

Every session from here **opens with the RESULTS SCOREBOARD**, before code or
test counts. If a session ships thirty excellent engineering changes and moves
none of those numbers, it says **RESULT IMPROVEMENT: NONE** in the first
paragraph. This one did.

---

## 0. THE ONE THING WITH A DEADLINE: IIF-1 IS NOT FUNDED TO ITS FIRST READ

Measured 2026-08-24 from DeepSeek's own `/user/balance`, not from a constant:

```
nights run                      6
nights to the first read (40)  34
measured cost per night    $0.9224   (.9197 .9185 .9023 .9304 .9410)
IIF-1 alone still needs     $31.36
balance                     $23.99   -> SHORT BY $7.37
```

`investigator_night.project_funding(0.9224)` — the repo's own funding rule,
which nobody had run against a measured balance — agrees by a second route:

```
fundable_nights_at_this_rate   26      (balance / measured cost)
nights_required                40
funding_gap_or_surplus     -$12.91     (against a fresh 40-night campaign)
```

**Six nights are already run, so the campaign reaches night 32 of 40** and voids
there. Two numbers, and they answer different questions — quote the right one:
**-$7.37** is the shortfall on the 34 nights REMAINING; **-$12.91** is the gap
against a full 40-night campaign costing $36.90.

Against the stale $57.12 the same call returns **61 fundable nights and a
+$20.22 surplus** — "FUNDED, proceed".

That is IIF-1 in isolation. The same key carries production too — roughly
$3/day unattributed — so the **combined runway is about six calendar days**,
against the ~48 that 34 weekday nights need. That second figure is softer: it
is derived against the $57.12 baseline, whose provenance is a person.

**The stale $57.12 constant would have said FUNDED.** `investigator_night.
DEFAULT_BALANCE_USD` now carries the measured $23.99 with its provenance.

**This is Murat's decision and it is ATTENDED.** The options, stated without a
recommendation because the trade is his:

* **top up.** 34 nights at $0.92 is ~$31 for IIF-1; add production and a
  comfortable margin to the checkpoint is ~$60-80. Cheap against the value of a
  clean 40-night forward record;
* **narrow the campaign** — fewer cells per night lowers $/night but changes
  the treatment mid-trial, which is exactly what the frozen pre-registration
  forbids. Effectively this means terminating and re-registering;
* **let it run dry**, which voids the campaign somewhere around night 32 and
  wastes the six clean nights already banked.

Nothing in this session changed the trial. `python -m scripts.llm_cost_audit
--snapshot` refreshes the measurement any time.

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

## THE POWER CHECK CHANGES THE ORDER OF THE CHUNKS

This is the strategic conclusion of the night and it argues against the obvious
next move.

The candidate's numbers were unresolvable at **t = 1.54** with an MDE of
**30.3%/yr** against a 16.6%/yr effect. That is not a fact about momentum. It is
a fact about **twelve years and a 35.7% tracking error**, and it applies to
every concentrated long-only equity strategy the farm can express.

So a new mechanism — `ACTIVIST_13D_v1`, `CONGRESS_FOLLOW`, `SELL_SIDE_BRAIN_v1`,
`GLOBAL_PREMARKET_RELAY_v1` — tested on the same twelve years, at a similar
tracking error, **arrives pre-doomed to the same t ≈ 1.5**. It will produce a
plausible number, a wide band, a phase spread, and a sub-period disagreement,
because that is what this sample size produces regardless of what is true.

**Building more signals to test in an under-powered sample manufactures more
unresolvable results.** That is the expensive version of doing nothing.

The order that follows:

1. **Get the sample.** CRSP 1990-2012 re-pull -> 35 years against the 36 the
   effect needs. This is now the gating task for CHUNKS B, C, D and G, not just
   for the momentum candidate.
2. **Re-run what exists** on 35 years — holding, breadth x phase, sub-period,
   confidence. Cheap; the machinery is built and tested.
3. **THEN** build new mechanisms, into a farm that can actually resolve them.

The exception, and it is a real one: a mechanism with a **much lower tracking
error** is resolvable in twelve years, because the MDE scales with TE, not with
cleverness. `power_check` reports `years_needed_for_observed_effect` — a design
that comes in under twelve is worth testing now. A concentrated 12-name
long-only book is not that design, and never was.

**None of this blocks CHUNK A's launch path.** `EVENT_RESPONSE_v1` as an
independent arena book is FORWARD paper accrual, which is a different evidence
route from a historical replay and is not governed by this arithmetic.

---

## THE CHUNKS, with what today changed about each

**CHUNK A — `PORTFOLIO_FARM` + `ASOF_REPLAY`. BUILT.** ~1,700 policies over
2013-2024 across six presets. What ran, in the order it overturned things:

* **`--preset phase` changed the answer.** At k=12 the rebalance PHASE moves
  terminal wealth 1.8x-3.8x, wider than any gap between the strategies compared.
  The originally published `$38,815` was the MAX of a distribution whose median
  is `$16,633`. **Never quote a farm result from one phase**;
  `farm.across_phases` reports the median with its spread beside it, and the
  spread is itself the finding.
* **`--preset delisting` exposed that the whole board rested on a guess.** With
  a declared -30% for every exit the same rule returned
  **$4,290 / $35,228 / $83,649** at -1.0 / -0.30 / 0.0 — an 18x swing straddling
  the benchmark.
* **`crsp.dsedelist` WAS ALREADY ON DISK** — `wrds/bulk/crsp__dsedelist.parquet`,
  unjoined. I had written "the top data task is a WRDS pull" into this file
  before looking, which is exactly the failure
  `feedback_test_before_declaring_blocked` names. Joined now: 97%+ of exits
  carry a MEASURED `dlret`, the fallback sensitivity collapsed 18x -> **1.09x**,
  and the leader moved $35,228 -> **$80,943** against a $38,960 market.
* **`--preset breadth_phase` settled breadth, and every single-phase reading of
  it had been wrong.** k crossed with the phase at h=5, 368 policies: an
  **interior optimum at k=10** — not k=5 (inside chance in 3 of 5 phases) and
  not k=50 (which the single-phase `--preset breadth` run had crowned). Phase
  spread narrows monotonically with breadth, 3.06x at k=5 to 1.31x at k=50: more
  names average the idiosyncratic variance down, and past k=20 they average the
  signal away too.
* **`scripts/portfolio_farm_subperiod.py` took most of the result back.** See
  the candidate block below. This is the cheapest check on the board and it is
  the one that matters.

What has NOT been done, in priority order:

1. **FIRST PRIORITY: re-pull `openprc`/`retx`/`shrout` for CRSP 1990-2012 —
   AND THE EXISTING MACHINERY CANNOT DO IT.** `wrds_pull_catchup` resumes by
   skipping "a table whose parquet exists", so twenty-three files that exist
   with the wrong columns are permanently invisible to it. This is the sibling
   of the 2026-08-23 finding that a failure-driven queue cannot see a
   NEVER-ATTEMPTED item: **an existence-keyed queue cannot see a
   PARTIALLY-PULLED item.** `python -m scripts.wrds_column_completeness` now
   makes it visible and exits non-zero (23 partial, 12 complete, usable range
   2013-2024). The pull spends a credentialed WRDS session against Murat's
   institutional account, so triggering it is ATTENDED — `pgpass.conf` is
   present, so it would run non-interactively. The sub-period split is what
   makes it urgent: what is needed is REGIMES, not precision, and three more
   decades hold the dot-com unwind, the GFC and the 2009 momentum crash.

   **And the power check prices it exactly: the effect needs 36 years to
   resolve, and CRSP 1990-2024 is 35.** The re-pull is not a nice-to-have for
   robustness — it is very nearly the precise amount of data this question
   requires, and nothing else on the board substitutes for it. That is the
   strongest argument this session produced for anything.
2. ~~A block bootstrap over formation dates.~~ **DONE — and the POWER CHECK it
   came with is the most important number of the night.**
   `python -m scripts.portfolio_farm_confidence`:

   ```
   tracking error   35.7%/yr     implied t          1.54
   excess           16.6%/yr     MDE at 80% power  30.3%/yr
   bootstrap CI     contains zero in ALL FIVE phases (P(<=0) 0.07-0.17)
   reality-check p  0.13 over 45 policies
   years needed     36
   ```

   **The sample could never have resolved the effect.** Canon §64 requires a
   power check before any confirmation and the farm ran ~1,700 policies without
   one. Run it FIRST from now on: a row whose
   `sample_can_resolve_observed_effect` is False answered nothing, whatever
   terminal wealth it reported.

   And it is the SAME fact as everything else — the 3.75x phase spread, the
   1.01x-vs-1.75x sub-period disagreement and the wide CI are four faces of one
   variance. None of them is a defect in the strategy or the simulator.
3. ~~Audit the 6,894-PERMNO superset for forward-looking eligibility.~~
   **DONE, and it cannot bind.** The superset admits any permno that ever
   cleared $100M/month; the farm's 500th name trades $76M-$137M per DAY, a
   **15.4x minimum margin** (median 20.4x), with 2,770-3,439 eligible per date
   against a 500-name cut. `python -m scripts.portfolio_farm_universe_audit`
   re-runs it and gates at 3x. The `shrcd`/`exchcd` restriction is untouched and
   is a DECLARED universe choice, not lookahead.

**THE CANDIDATE — AND THE CHECK THAT LARGELY TOOK IT BACK.**
`mom_12_1 / hold 5d / k=10 / inverse_vol / top-500-liquid / 12 bps round trip`
returns a $77,002 median across five phases against the market's $38,960 over
2013-2024, clearing both nulls in 5 of 5 phases.

Then `python -m scripts.portfolio_farm_subperiod` split the window:

| window | median | worst phase | market | ratio | clears both nulls |
|---|---:|---:|---:|---:|:--|
| **2013-2018** | $15,737 | $15,107 | $15,613 | **1.01x** | **2 of 5** |
| **2019-2024** | $33,844 | $26,676 | $19,330 | 1.75x | 5 of 5 |

**The edge lives almost entirely in the second half.** Over 2013-2018 it is a
coin flip against buy-and-hold, worst phase BELOW the market, inside its own
nulls in three phases of five. **This is a one-regime result and it must not be
seeded as a forward book.** Not a holdout either — the candidate was picked
after seeing the whole window, so no significance may be read off the split.

It also loses to the market on Sharpe (0.61 vs 0.72), Sortino and Calmar in
every phase of the full window, at ~2.4x the volatility and a -60% drawdown.
Under terminal wealth it is ~2x the market; under any risk-adjusted objective it
is worse. Naming the objective is a standing rule, not a caveat.

**SO THE PRIORITY ORDER FLIPPED.** Re-pulling `openprc`/`retx`/`shrout` for CRSP
**1990-2012** was second priority when the question was precision. It is FIRST
now that the question is whether anything here exists outside 2019-2024. Three
more decades contain the dot-com unwind, the GFC and the 2009 momentum crash —
the regimes that would actually test this. `AegisWRDSPullNight` already exists.

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
2. **The bar every new mechanism is measured against is $38,960** — the CRSP
   value-weighted market, buy and hold, 2013-2024 from $10,000. The best rule the
   farm has found clears it on the full window ($77,002 median) and is **1.01x
   over 2013-2018**, so the calibration is not "beat $38,960 once". It is three
   questions, in order:

   1. **does it beat $38,960** — not "is it significant";
   2. **what is its phase spread** — a rule whose spread is wider than its edge
      has not been shown to have one;
   3. **does it survive the window split** —
      `python -m scripts.portfolio_farm_subperiod`. This is the one that killed
      the current leader, and it is cheap.

   Under which objective, always. Terminal wealth and Sharpe disagreed about
   every result on this board.
3. **The IIF-1 read schedule stays frozen** at 40/80/120. Grading is continuous
   and automatic; READING the aggregate is what the gate blocks. A separate
   product surface showing yesterday's predictions vs outcomes is wanted and
   must not touch the frozen trial.
