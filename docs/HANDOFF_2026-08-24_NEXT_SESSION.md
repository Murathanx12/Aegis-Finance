# HANDOFF — for the next session (written 2026-08-24)

Rewritten in place; the version this replaces is in git at `264b1c2`. Its three
Monday verification events survive here in §4. Read this first, then
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

---

## 1. Where we are, in one paragraph

An external review was adjudicated rather than imported, six defects were fixed,
and then **four alpha mechanisms were attempted in one night and all four now
carry receipts**: the analyst co-coverage graph is licensed AND buildable, two
screens returned STOP, and one returned a genuinely strong number (+0.0315,
t 3.19, surviving BH-FDR) that was **refused** because a precondition test
showed the edge is borrow fees. Demonstrated edge is still **0%**. What changed
is that the remaining directions are the ones that survived being attacked, and
three expensive ones are closed on evidence rather than open on hope.

## 2. What changed this session

### Fixed, with tests

1. **The arena's external paper execution was two sessions late.** It mirrored
   *settled* positions from the 16:30 job, which runs before the 17:45 pass that
   decides. It now mirrors queued **order intent** and submits inside the pass
   that produced it. `paper_broker_targets.intent()` · `_submit_arena_broker_intent`.
2. **Credentials and state could come from different Alpaca accounts.**
   `_request` resolved keys from the ENV target regardless of the caller's
   target, so `sync_alpaca_mirror(target=arena_book)` with the env unset read
   the arena and traded the **mirror lane's account** — walking around the
   refusal built to prevent exactly that. The target is threaded through now.
3. **The event taxonomy was dropped between producer and model.**
   `event_intel` emits `event_type`; the arena adapter read `category`, which no
   producer emits. The LLM saw `category: null` on every event since event
   context shipped. Fixed, with a three-hop contract test.
4. **Event identity hashed the URL**, so five syndications of one story were
   five events — while the docstring promised the opposite. Split into
   `canonical_hash` (the event) and `observation_hash` (the sighting). Done now
   because the store is empty everywhere; later would have meant a 30-day window
   of everything reporting NEW.
5. **Acceptance time was caller-controlled** and the arena passed the frozen
   snapshot's simulated clock into it. Schema 1.1.0 has three clocks —
   `source_timestamp` / `ingested_at` / `decision_asof` — availability computes
   on `ingested_at` alone, a supplied stamp is marked `ingest_clock: supplied`,
   and a future one is refused.
6. **IBES exact-midnight announcement times were read as pre-market.** 3,168
   rows; 1,234 claims moved by one session. Same fix in
   `g4_collect_earnings.py` (807 rows).

### Built

7. **`signal_reachability.py`** — enumerate the PLAN for code. Three tiers
   (reachable 250 / tooling-only 60 / orphan 20), every orphan classified with a
   typed reason, derived from the import graph rather than a hand-maintained
   list. **On its first run it found that `detectability_gate` — TOURNAMENT-2's
   declared precondition — was imported by nothing**; that is now wired and the
   gap is closed. Four gaps remain named.

10. **Two Alpaca accounts, two books.** `AEGIS_PAPER_BROKER_TARGET` was a single
    GLOBAL choice — naming an arena book would have silently stopped mirroring
    `lane:mirror`, whose third-party-verified curve the code calls the only
    independent check on our NAV maths. Two credential namespaces means two
    accounts, so both mirror at once now: new `AEGIS_ARENA_BROKER_TARGET`.
11. **The boot seeder was a silent no-op.** It called `seed_alpaca_mirror()`
    with no argument, which resolves to the LANE — seeded since inception — so
    with an arena book declared it would have logged `already_seeded` as a
    success and left the arena account empty forever. `seed_all_paper_brokers`
    visits every declared target now.
12. **`execution_ledger.py`** — one row per intended order, written at
    submission and resolved later, so the broker's real fill sits beside the
    book's synthetic one. The first thing in this repository that checks the
    `cost_bps + slippage_bps` every arena book assumes. Records what leaves no
    fill behind: never-filled, partial, and broker-filled-with-no-internal-
    match. `/api/health/full` gains `execution_ledger` and `paper_broker` rows.

### Measured

8. **The actor result survives the PIT fix.** Corpus rebuilt, same seven
   analysts licensed for INVERSE, same holdout deficits to three decimals.
13. **`ANALYST-COCOVERAGE-GRAPH-1` ran — verdict CONTINUE**, and the three
    refinements we hoped for all measured zero. Full result:
    `docs/FINDING_2026-08-24_ANALYST_COCOVERAGE_GRAPH.md`. The effect
    replicates (+0.0228 IC) and survives own-momentum (+0.0156 paired) and
    industry momentum (+0.0090 paired); reliability-weighted edges are a
    precisely measured zero (−0.00008 ± 0.00052), direction shows no
    asymmetry, 52-week-high conditioning adds nothing. **The GNN stays
    unbuilt** — its gate was "simple graph features pay", and they do, but
    every kind of structure a GNN exists to exploit measured zero.
9. **The persistence headline was a filtered subset.** `0.516, n = 50` was 50 of
   **222**, selected by a rule nobody had written down (≥30 holdout claims).
   Unrestricted it is **0.25**. Every rung of the ladder excludes zero, so the
   premise holds; the magnitude depended on a threshold. The whole ladder is in
   `score_receipt.json` now, and the finding doc is amended.

---

## 3. Waiting on a human — and it is smaller than it was

* ~~A second Alpaca PAPER account~~ — **DONE.** The keys are in `.env` as
  `ALPACA_ARENA_API_KEY_ID` / `ALPACA_ARENA_API_SECRET_KEY`, they resolve, and
  the shared-account guard passes (the arena key differs from the lane key).
  **Set on Railway 2026-08-24** (`railway variables --skip-deploys`):
  `ALPACA_ARENA_API_KEY_ID`, `ALPACA_ARENA_API_SECRET_KEY`, and
  `AEGIS_ARENA_BROKER_TARGET=CURRENT_BEST_v1`. Note the variable name —
  declaring an arena book no longer un-mirrors the lane (§8).

  **ONE thing remains, and it is deliberately attended: the seed boot**, which
  cannot happen until the book holds positions. See §8.
  **Rotate the arena secret when convenient** — it was pasted in plain text into
  a chat session before being written to `.env`.
* Which population G7 counts (`live_forward` vs `arena_forward`).
* The standing attended queue in `MEMORY.md` is otherwise unchanged.

---

## 4. Monday's verification events — unchanged, plus two

**Read the clock carefully.** The scheduler runs on `US/Eastern` and the arena
job is `mon-fri`. A session working from a UTC+8 machine sees the local date
roll over to Monday roughly 12 hours before Eastern does, and the pass does NOT
run on the local Monday — it runs on the Eastern one. This was got wrong once
already in the session that wrote this section.

The three from the previous handoff still apply to **Monday 2026-08-24 17:45 ET**:

1. ten seed migrations to per-book identity appear in the logs;
2. nine books run (not ten — `PROFIT_ALLOCATOR_v1` retired);
3. `event_store` moves off `ABSENT`.

**And now two more, from this session's changes.** `AEGIS_ARENA_BROKER_TARGET
= CURRENT_BEST_v1` IS set on Railway, so the pass will speak — and exactly what
it should say is predictable:

4. `Execution reconcile: target=arena:CURRENT_BEST_v1 status=nothing_pending`
   — nothing has been submitted yet, so there is nothing to reconcile.
5. `Paper broker submit: target=arena:CURRENT_BEST_v1 status=not_seeded
   basis=... trades=0` — **zero trades is the CORRECT outcome.** The Alpaca
   account is empty and `sync` deliberately will not open the first position;
   only the attended seed does that (§8).

**A `trades=N` with N > 0 on Monday would be the finding**, not the success:
it would mean the account was seeded by something nobody authorised.

6. **`options_pit` leaves `ABSENT`.** `pi_options_pit` first fires 15:30 ET
   Monday. If `/api/health/full` still shows `ABSENT` on Tuesday, the collector
   is not running — and unlike every other subsystem here that is not a delay,
   it is **lost evidence**: option chains have no history, so the days it misses
   cannot be recovered by fixing it later.

Also still falsifiable: **`why_moved` runs 17:15 ET Monday.** If `live_forward`
is still quiet on Tuesday, that is a P0, not a puzzle.

If a book raises `ConfigDrift` saying "refusing to migrate", the YAML changed
before the stamp took: restore it, let it migrate, then re-edit.

> **Item 1 is not a formality — it is a one-way door.** Until those ten
> migrations land, every seed is verified against the WHOLE-FILE `config_hash`,
> and `assert_config_current` refuses to migrate from a config that has already
> changed. So adding ANY book to `arena_books_v1.yaml` before Monday's pass
> strands all ten NAV histories permanently. Two books are queued behind that
> gate (`EVENT_RESPONSE_v1`, and `GRAPH_PROPAGATION_v1` if its universe problem
> is ever solved). **Confirm the migration in `/api/arena/status` before
> touching that file.**

---

## 5. Do these next, in order

**Two verdicts from the first pass were re-tested overnight and BOTH FLIPPED.**
That is the state of the board:

| trial | was | is now | why |
|---|---|---|---|
| `EVENT-RESPONSE-2` | NOT LICENSED (borrow) | **BUILD** | the borrow slice had been implemented wrongly |
| `ANALYST-COCOVERAGE-GRAPH-1` | licensed AND buildable | **not buildable here** | the live graph is 100% dense ⇒ the signal is reversal |
| `EVENT-RESPONSE-1` | STOP | STOP | PEAD real at 7bps, unrankable |
| `RELATIVE-VALUE-NN-1` | STOP | STOP | mlp worst of three |

**Demonstrated edge remains 0%.** One mechanism is now licensed to build and
has no blocking objection: the options-implied event response.

> ### AMENDED 2026-08-24 EVENING — read this before §5.1 and §5.2
>
> Two of the three blockers below were attacked at the root rather than worked
> around, and both moved. Neither verdict *flipped*; both reasons were replaced,
> which is the more useful outcome.
>
> **`iv_put_minus_call_30d` TRANSFERS.** Not by calibration and not by a fitted
> map — by fixing two conventions that were wrong.
> `docs/FINDING_2026-08-24_OPTIONS_CONVENTION.md`.
>
> | | median | gap vs stdopd +0.00194 | transfers |
> |---|---|---|---|
> | vendor IV *(where this started)* | −0.02428 | −0.02622 | no |
> | ours, declared r, trailing q | −0.00338 | −0.00532 | no |
> | **ours, declared r, q over the option's own WINDOW** | **−0.00179** | **−0.00373** | **yes** |
>
> 1. **Yahoo's `impliedVolatility` column discounts nothing** — our solver at
>    r = 0, q = 0 reproduces it to 0.0009. That was the whole 0.026, and it is
>    why both spent routes failed: matched-strike fixed which strikes, the rank
>    fixed the scale, and both kept reading the disputed column.
> 2. **The trailing dividend yield is the wrong `q` for a 30-day option.** Only
>    11 of 39 names carry an ex-date inside the window; for the rest the correct
>    `q` is zero and the trailing yield over-subtracts.
>
> Ruled out on the way: early exercise (−0.0007, wrong direction, via a
> Bjerksund-Stensland arm), and — importantly — **my own preferred explanation.**
> I claimed the transfer test was mis-specified because the panel spans rate
> regimes; the panel's residual regressed on FEDFUNDS over 168 months gives
> slope +0.00001, t 0.04, R² 0.000. Flat. OptionMetrics discounts correctly, so
> the rate is already absorbed; ours moved with it because ours was wrong.
>
> `option_implier.py` ships (22 tests), and the store records our residual and
> its conventions from its first row (schema 1.2.0) because `pi_options_pit`
> first fires Monday 15:30 ET and a chain has no history to go back for.
>
> **The graph's density verdict was measuring the null.**
> `docs/FINDING_2026-08-24_GRAPH_BACKBONE.md`. A degree-preserving null on the
> same coverage predicts **95.8%** edge density against the observed 100.0%, so
> `min_shared=1` was admitting pairs whose overlap is BELOW chance. Weighted
> edges reach corr −0.234 with own return at 100% of the universe rankable,
> which no `min_shared` value achieved. The graph then fails on the question
> that matters: it concentrates 97% as much as its own null (z = −10.6 — real,
> and negligible). Verdict unchanged; `graph_beats_null()` ships as a
> precondition that TRANSPORTS to any candidate universe.

### 1. `EVENT_RESPONSE_v1` — the mechanism that survived scrutiny

`docs/FINDING_2026-08-24_EVENT_RESPONSE_V2_AMENDMENT1.md`

`lightgbm@1d[with_options]`: **IC +0.0315, t 3.19, survives BH-FDR, MDE₈₀
0.0276** — the only adequately-powered result this programme has produced. The
central feature is `gap_vs_implied` = |overnight gap| / implied daily move: did
it move more than was priced. Ridge gains nothing, so the relationship is
non-linear, which is what that feature *should* be.

The borrow precondition does **not** fire. Excluding hard-to-borrow names from
the EVALUATION leaves the effect intact (0.0329, t 3.56); the original's
halving came from excluding them from **training** as well, which is a
different experiment. Reproduced exactly (variant C = 0.01505, t 1.42).

#### The input it needs now exists and is ACCRUING

`backend/services/options_pit_store.py` — the store
`expectation_store._V0_UNKNOWNS` has been naming as absent since G4 v0
(`"options_implied_move": "options PIT store not built"`). Scheduled
`pi_options_pit`, 15:30 ET weekdays, on the health surface as `options_pit`.

**It was built before the book deliberately, and that is the opposite call from
the one next door.** yfinance option chains are a snapshot with no history: an
implied move not captured before its event is gone permanently. Every day
without the collector is forward evidence destroyed. `GRAPH_PROPAGATION_v1` was
built before its viability was measured and that was wrong; here the input is
perishable, so building early is the only thing that works.

It interpolates to **constant 30/60-day maturities, linear in total variance**,
because `stdopd` is a *standardized* surface. Reading "the nearest expiry" would
make the feature drift with the expiry cycle — rich before a monthly, cheap
after — and that drift is a seasonal pattern the screen never validated wearing
its name.

#### BEFORE THE BOOK TRADES: one feature does not transfer

`backend/data/optimus/options_pit/train_serve_skew_receipt.json`

The model is FIT on OptionMetrics and would be SERVED on yfinance. Measured
across 60 live names:

| feature | live median | stdopd median | live %>0 | stdopd %>0 |
|---|---|---|---|---|
| `atm_iv_30` | 0.340 | 0.361 | 100% | 100% |
| `implied_move_1d` | 0.0214 | 0.0227 | 100% | 100% |
| `iv_term_slope` | +0.0019 | −0.0001 | 57% | 49% |
| **`iv_put_minus_call_30d`** | **−0.0237** | **+0.0019** | **25%** | **55%** |

**The central feature transfers. The put-call residual does not** — only 15% of
live names clear the screen's borrow cut instead of 20%. A tree splits on
absolute thresholds, so that column would split wrongly in production. A
matched-strike parity residual (both legs at the SAME strike) was implemented
and moved the median only −0.0254 → −0.0237: the strike-composition artefact
was real but small, and the rest is a genuine solver/convention difference.

Dropping it is not free. Declared rule was "servable iff within one paired SE at
both horizons":

* `drift1` full **0.0315 (t 3.19)** → servable **0.0228 (t 2.52)**, diff
  −0.0087 ± 0.0074 — **outside one SE**
* `drift5` full 0.0288 → servable 0.0249, diff −0.0040 ± 0.0063 — within

⇒ **NEEDS_CALIBRATION.** The servable-only model still clears the 0.01
economic bar, but its own MDE₈₀ is 0.0253 against an IC of 0.0228 — back under
its own detectable threshold, like everything else here.

**The rank route was tried and is spent** (`AMENDMENT-2`, hash
`3e4c2c744895a856`, `docs/FINDING_2026-08-24_EVENT_RESPONSE_V2_AMENDMENT2.md`).
A cross-sectional rank is invariant to monotonic distortion, so it should have
removed the problem without fitting anything. It did not:

| arm | drift1 vs A | drift5 vs A |
|---|---|---|
| B drop the column | ✗ | **✓** |
| C rank the column only | ✗ | ✗ *(worse than deleting it)* |
| D rank ALL option features | **✓** | ✗ *(collapses, t 2.69 → 0.96)* |

**Each candidate passes at exactly one horizon.** Declaring only `drift1` ships
arm D; declaring only `drift5` ships arm B — two different models chosen by
which horizon was written down first. The both-horizons rule, declared before
the numbers existed, is the only thing that caught it.

**Three routes remain, none free:** a fitted quantile map (owes its own
validation, can drift — the thing the rank was chosen to avoid); serve arm B and
say plainly it sits under its MDE₈₀ (defensible under PRODUCT_EXPERIMENT, which
needs no significance gate); or match the rate and dividend assumptions properly
— the untried root-cause route, since the matched-strike fix moved the median
only −0.0254 → −0.0237.

> **THE THIRD ROUTE WAS TAKEN, 2026-08-24 evening, and it closed the item.**
> `docs/FINDING_2026-08-24_OPTIONS_CONVENTION.md`. It was never about matching
> assumptions *to* the vendor — the vendor has none. yfinance's implied-vol
> column is computed with **r = 0 and q = 0**, which our own solver reproduces
> to 0.0009, and that is the entire 0.026. Inverting the prices ourselves cuts
> the gap to **0.0053**, which misses the declared bar by 0.0003.
>
> The last 0.005 was the **dividend tenor**: trailing-12m yield over-states `q`
> for a 30-day option, because only ~a third of quarterly payers have an ex-date
> inside the window (measured: 11 of 39). Fixing it lands at −0.00179, inside
> both declared bars. `OPTIONS-DIVIDEND-WINDOW-1`, declared with a point
> prediction before running — the prediction was right in mechanism and wrong in
> magnitude (+0.00159 actual against +0.0059 predicted, because the median of a
> heterogeneous shift is not the shift at the median).
>
> **The `q = 0` arm also clears the bar and must NOT be shipped**: it is wrong
> for the 28% of names that do pay inside the window and lands by a compensating
> error. That refusal was written down before the window arm existed.
>
> **The fallback (drop the feature) is no longer needed.** It would now cost a
> feature that clears its transfer bar.
>
> **Still open, and not small:** one day and 39 names; `pct_positive` 46.2% vs
> the panel's 54.8% (inside the bar, the largest remaining difference, and a
> tree splits on thresholds); and the residual median still sits 0.0037 below
> the panel, where implied financing above OIS and general borrow both live
> unmeasured. The collector accrues daily from Monday — the honest version of
> this number is the same comparison over a month of snapshots.

Build it as its own PRODUCT_EXPERIMENT book, never a composite weight — and
note the collector needs lead time before the book has rows to decide on.

### 2. `GRAPH_PROPAGATION_v1` — module exists, book must NOT be registered

`docs/FINDING_2026-08-24_GRAPH_PROPAGATION_DENSITY.md`

The vendor can supply the data (98.3% of names, median 17 covering firms, 14.4
years). **The data cannot supply a graph.** At the licensed `min_shared=1` the
live 179-name universe is **100.0% dense** — every major bank covers every
mega-cap — so

    peer_eq_i = (S − r_i)/(n − 1)

and corr(peer_eq, own return) = **−1.0000, sd 0.0000** over 200 draws. The
ranking is exactly short-horizon reversal, a Holm-surviving **ANTI-signal**
here. `assert_graph_informative` now refuses it.

Sparsifying by shared-broker count only helps around k=8–12, costs 11–45% of
the universe, and — decisively — **is not the mechanism the screen validated**
(`peer_shared` was an arm there and did not beat `peer_eq`).

**To revive it you need a universe whose coverage is SELECTIVE** — mid/small
caps followed by a handful of brokers, which is what the screen's own graph
looked like. That is a universe change with its own declaration, not a
parameter change, and it needs the vendor-depth measurement re-run on thinner
names.

> **AMENDED 2026-08-24 evening — the verdict stands, the reason does not.**
> `docs/FINDING_2026-08-24_GRAPH_BACKBONE.md`.
>
> A degree-preserving null on this same coverage predicts **95.8%** binary edge
> density against the observed 100.0%. With 176 names drawing ~17 firms from a
> pool of 94, "shares at least one broker" is a birthday-paradox certainty, and
> the median EXPECTED overlap is 3.43 — so `min_shared = 1` was admitting pairs
> connected *below* chance. The sweep's correlation starts moving at 3–4, which
> is exactly where it crosses that. The density number was a fact about the
> threshold.
>
> The identity also needs UNIFORM weights, not just completeness, and the sweep
> never varied what an edge is worth. Significance-weighted edges reach corr
> **−0.234** and the hypergeometric backbone **−0.198**, both inside the
> borrowed 0.25 bar, at **100% of the universe rankable** — which `min_shared`
> could never do.
>
> It fails anyway, on the right question: effective peer count **151.8 vs a null
> 156.4 ± 0.4, z = −10.6, ratio 0.97**. The structure is real and negligible —
> an equivalence result, far stronger than the density heuristic.
>
> **What that buys the successor:** `min_shared = k` does not transport (one
> shared broker means different things at 4 covering firms and at 17), but
> "overlap above the degree-preserving null at a declared FDR" does, and carries
> no parameter. And `graph_propagation.graph_beats_null()` screens any candidate
> mid-cap universe for the cost of one coverage pull, **before** a price is
> fetched. Run it first.

### 3. P0.2 the information bus — **DONE, both halves**

**Superseded 2026-08-24 evening.** This section previously read "the only
original roadmap item never started", which was already false when written: the
registry shipped in `bca1b99`. The external review then found that the registry
was the *audit* half only — `spec.book_fingerprint` still ended with the bare
global `discovery.COMPOSITE_VERSION`, so nothing consumed the fingerprint the
bus computed.

Both halves are now in:

* `information_bus.py` — the declared family registry, `bus_version`,
  `composite_fingerprint`, `family_fingerprint` (the generalisation: any
  selector can print the identity of the set IT reads).
* `selector_identity.py` — book identity that carries the selector this book
  actually selects on, split into a hand-declared ALGORITHM version and DERIVED
  dependency prints (families **and weights**). `SelectorNotDeclared` refuses an
  undeclared selector rather than defaulting it to the composite's dependencies.
* health key `selector_identity` on `/api/health/full`.
* `test_selector_identity.py` — 10 tests, including the three properties the
  review named and the migration pin below.

**All ten live fingerprints are byte-identical to the legacy formula**, verified
by test. That was mandatory: the books migrate to per-book identity on Monday's
pass and `assert_config_current` migrates only while the legacy hash verifies,
so a formula that moved would have stranded every NAV history. Dependency prints
contribute only when they differ from their seed baselines
(`COMPOSITE_FAMILIES_BASELINE`, `COMPOSITE_WEIGHTS_BASELINE`) — constants that
record history and must **never** be updated to track the current value.

> #### STILL TRUE: DO NOT ADD ANY BOOK TO `arena_books_v1.yaml` UNTIL THE ARENA RUNS
>
> The ten books seeded 2026-08-21 carry only the **legacy whole-file**
> fingerprint and migrate to per-book identity on their **next arena pass**.
> `assert_config_current` migrates only while the legacy hash still verifies, so
> adding a book first makes it refuse to run **and** refuse to migrate — all
> ten, permanently, NAV histories stranded. Pinned by
> `test_migration_REFUSES_when_the_config_already_changed`.
>
> **Monday's pass therefore does two jobs**, and the second was invisible: it
> queues decisions AND migrates the seeds. Confirm via `/api/arena/status`
> before registering the EVENT_RESPONSE book.

### 4. Roadmap item C ran and returned STOP — `REVISION-FORECASTER-1`

`docs/FINDING_2026-08-24_REVISION_FORECASTER.md`. Pre-registered before the
target column existed, corpse-linted PASS, verdict STOP on the registered rule.

The chain `event state -> revision -> return` has a first link of **IC +0.623**
(t 60) and a second link of **+0.003** — so the composition is zero. What a
public numeric surprise predicts about the next revision is exactly what the
market has already priced.

**Two instrument lessons, and they are the reusable part:**

* **Derive `outcome_dispersion` from a realised prior on the same panel, never
  from the theoretical null.** The registered paired MDE80 was 0.0158; realised
  was 0.039-0.055. The null understates monthly-IC dispersion by ~45%, and
  `EVENT-RESPONSE-2`'s own 0.0276 on this same panel was available and unused.
  Assumed arm correlation ρ = 0.8; realised −0.03 to +0.35, so pairing *raised*
  the SE.
* **When a mediator is observed at `t1`, the return window must start after
  `t1`.** The first Q1 measured returns from the EVENT while `t1` sits a median
  20 days later — inside both windows. It produced IC +0.0504 at **t 4.04** and
  a written interpretation before the check. Correctly timed: +0.0108, t 0.81.

Item **B (`MANAGEMENT_EVASION_DELTA_v1`) is blocked on data** — no earnings-call
text exists anywhere in this repository, and FMP/Bigdata acquisition is unpriced.
Transcripts are archival, so unlike the options collector there is no
perishability urgency. This trial also weakens B's case: a text model that
merely predicts the revision predicts something already priced.

### Standing rules for any of the above

* **`feature_leakage_guard.assert_no_target_leakage` before fitting anything.**
* **A slice that changes a verdict must say which side of the fit it changes.**
  Training population and evaluation population are different experiments, and
  the receipt must name which one ran. This cost a wrong verdict.
* **A number that decides a verdict belongs in a runnable committed file**, not
  a terminal. The original borrow slice's script was never committed, so the
  verdict rested on numbers nobody could re-derive.
* **Measuring an input's abundance is not measuring its information.** "Median
  17 covering firms" read as a rich graph and was the symptom that destroyed
  the signal.
* **Nulls are still under-powered.** State them as "no effect larger than X".

---

## 5.5. RAILWAY WILL NOT DEPLOY WHILE CI IS RED — and nothing said so

**Found 2026-08-24 the hard way.** Two pushes (`67c26ff`, `a7c4448`) were
reported as successful `git push`es and never reached production. The service
kept serving `1e2dda0` while the working tree was three commits ahead.

```
railway deployment list --json
  -> 'status': 'SKIPPED', 'skippedReason': 'CI check suite failed'
```

Railway is wired to the GitHub check suite and **skips the deploy entirely when
CI fails** — no build, no error, nothing in the service logs. `railway status`
still says the service is healthy, because the OLD deployment is healthy. That
setting is correct and should stay; what was missing is that anyone knew.

**So a green local suite is not evidence that anything shipped.** The deploy
verification for any push must read `deploy.commit` from
`/api/health/full` and compare it to the pushed SHA. It already did — which is
the only reason this was caught at all.

### How to read CI without the `gh` CLI (not installed on this machine)

GitHub's check-runs endpoint is readable **unauthenticated** for this repo:

```bash
curl -s -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/Murathanx12/Aegis-Finance/commits/<SHA>/check-runs" \
  | python -c "import json,sys; [print(r['name'], r['status'], r['conclusion'])
                for r in json.load(sys.stdin)['check_runs']]"
```

Job LOGS need auth; the pass/fail per job does not, and that is enough to know
which of the two jobs (`backend pytest` / `frontend next build`) broke.

### The CI-mimic recipe, because local and CI differ in one load-bearing way

`backend/config.py` calls `load_dotenv(PROJECT_ROOT / ".env")` **at import**, so
every local test run sees whatever secrets are on this machine. CI has no
`.env`. That is exactly how the 2026-08-24 failure happened: `execution_ledger.
reconcile` short-circuits to `not_configured` without credentials, so eleven
tests passed locally **because a secrets file existed** and failed in CI.

To reproduce CI before pushing:

```bash
( trap 'mv -f .env.hidden .env 2>/dev/null' EXIT
  mv .env .env.hidden
  AEGIS_IIF1_PREREG_ABSENT_OK=1 python -m pytest backend/tests/ -m "not slow" -q
  mv -f .env.hidden .env )
```

**Always inside a subshell with the trap.** A run that dies with `.env` moved
leaves the machine without its keys.

> **AND `.env.hidden` WAS NOT GITIGNORED** (found 2026-08-24, fixed in
> `.gitignore` along with `.env.*.hidden`). For the ~10 minutes this recipe
> runs, the repository contains an untracked, unignored copy of every secret in
> it, under a name `git status` shows and `git add -A` would happily stage.
> Two commits went out this session with `git add -A` while a suite was
> running; neither overlapped the window, which is luck rather than design.
> The recipe was correct about the risk it was written for and created a
> different one.

---

## 6. Traps

* **A new custom exception under `services/` fails the suite** until it is
  enrolled in `backend/tests/test_guard_missing_input_contract.py` (`CASES`) or
  exempted with a reason. Cost 6 minutes this session; it is working as
  designed.
* **`.env` had raw dashboard text pasted into it** (`SECOND ALPACA`, `Key`,
  `Secret` as bare lines). `python-dotenv` logs "could not parse statement at
  line N" and carries on, so the keys were simply absent with no error anywhere.
  If credentials appear to be unset, read the file before reading the code.
* **A column name is not a measurement.** THREE times in one session a
  property of data was asserted from its description and was wrong:
  `stdopd` "standardized options" (ATM-only, no wings, so no skew); a daily
  return "excluding" the overnight gap (CRSP is close-to-close, so it includes
  it); and `cs_rank` (the cross-sectional rank OF THE FORWARD RETURN, sitting in
  a feature list). Two were caught by reading. The third was caught only because
  the resulting IC was 0.99 — **which is not a method**, since the same leak at
  0.15 would have shipped. `backend/services/feature_leakage_guard.py` now
  refuses any feature whose within-block rank IC against the target exceeds 0.5,
  **before any model is fitted**. Call it from every screen.
* **Every screen so far has been under-powered by its own design.** All three
  report an MDE at 80% power ABOVE their own observed effect. That is not a
  reason to discount them — it is the reason each null is stated as "no effect
  larger than X", never "no effect".
* **A test can pass because of a file on your machine.** `backend/config.py`
  loads `.env` at import, so the suite sees local secrets CI never has. If a
  code path branches on "are credentials configured", its tests must stub that
  branch rather than inherit the answer from disk. See §5.5 for the recipe that
  reproduces CI locally.
* **`git push` succeeding does not mean anything deployed** (§5.5). Railway
  skips the deploy when the GitHub check suite fails, silently.
* **An autouse fixture calling `tmp_path_factory.mktemp` runs per TEST.** Added
  once here it took the fast suite from 8:46 to 14:37 — 5,570 directories.
  Session-scope the directory; only the monkeypatch needs to be per-test.
* **The suite writes into real ledger paths unless something stops it.** Found
  by reading `git status` after a run — twice now, by two different sessions.
  `test_paper_broker_targets` drives `sync_alpaca_mirror` against a fake
  broker, and the sync records submissions, so PENDING orders for AAPL/MSFT
  landed in the real execution ledger and would have aged into `NEVER_FILLED`.
  An autouse conftest fixture now redirects the root, matching
  `_sandbox_telemetry_to_tmp` directly above it. **Read `git status` after a
  suite run** whenever a service starts writing files.
* **An append-only ledger cannot count open work by row state.** A resolved
  order leaves a PENDING row *and* a resolution row, so counting rows-in-state
  counted every resolved order forever. Derive by identity.
* **CRSP schema drift**: `crsp_dsf_1990..2012` carry no `shrout`/`cfacpr`,
  2013+ do. Refuse those years rather than defaulting the split factor — an
  unadjusted price makes every split look like a crash against a 52-week high.
* **Fixture datetimes must be in the past.** `event_store.make_record` now
  refuses a future ingestion stamp, and several tests used "today at 17:00",
  which is a coin flip on the hour the suite runs.
* `backend/routers/portfolio.py` carries a **BOM**. Python's importer strips it;
  `ast.parse` does not. Read source with `utf-8-sig` in any tooling.

---

## 7. The standard

**Every roadmap item now carries a receipt.** Four alpha mechanisms attempted in
one night: one licensed and buildable, two STOP, one strong number correctly
refused.

**Demonstrated edge is still 0%**, and that is the honest reading. But the night
closed three expensive directions on evidence rather than leaving them open on
hope — including the GNN, closed by measuring that the structure it exists to
exploit is not there — and it refused a BUILD that would otherwise have shipped
at t 3.19.

### The two things worth carrying forward

**Order of operations, twice.** `feature_leakage_guard` exists because an IC of
0.99 was caught by luck rather than method. `EVENT-RESPONSE-2` was refused
rather than retracted because its confound test was a PRECONDITION. Both times
the difference was *when* the check ran, not whether it existed.

**A description is not a measurement.** Six times in one session a property of
data or code was asserted from its name or its docs and was wrong: `stdopd`
"standardized options" (ATM-only), a daily return "excluding" the gap (CRSP is
close-to-close), `cs_rank` (the rank of the outcome), a module global restored
after every fit, the ET/local clock, and the standing-vs-actions gap (87.1%
already actions). Five were caught by reading or measuring. One was caught by
luck.

The machinery keeps improving and the edge keeps not moving, because only
matured decisions move it. What changed is that the next thing to build is
finally something that survived being attacked.
