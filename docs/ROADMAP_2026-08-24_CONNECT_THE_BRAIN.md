# ROADMAP — 2026-08-24: connect the brain

**Supersedes the queue in `ROADMAP_2026-08-23_PROFIT_FIRST.md`. Does not
supersede its licences** — the three-licence structure (`PRODUCT_EXPERIMENT` /
`CAPITAL_CANDIDATE` / `RESEARCH_CLAIM`) stands unchanged and governs everything
below.

---

## 0. The diagnosis, verified rather than accepted

An external review argued that the arena's ten books are not ten brains. That is
correct, and it is now measured rather than argued:

* **All ten book entries in `arena_books_v1.yaml` declare
  `selection: composite_top_k`** over one signal, `arena_composite`
  (`selection_signal` is set once, at the file's defaults).
* `arena_composite` is a hand-weighted blend
  (`discovery.COMPOSITE_WEIGHTS`): `mom_12_1` 1.0, `multifactor` 1.0 — itself
  momentum + insider + revisions — then revisions, insider, PEAD and quality at
  0.5.
* Coverage, measured 2026-08-20: `coverage_histogram {"1": 206, "6": 1}`. For
  **99.5% of names, exactly one factor is present**, and that factor is 12-1
  momentum.

So the books differ in **sizing, concentration, screens, LLM tilts and winner
handling** — how to *hold* a signal — and not at all in **where the signal comes
from**. The arena has been running a well-instrumented experiment on portfolio
treatment and calling it a competition between strategies.

**That is why five months of guardrails did not move the demonstrated edge off
0%, and why another 0.5-weight factor will not either.** The bottleneck is alpha
*source* diversity, and it always was.

### The other half: the brain cannot see most of what Aegis computes

The repository already contains options intelligence, an options→Monte-Carlo
path, prediction-market snapshots on two venues, a catalyst calendar, a
distributional world model, short-interest infrastructure and cross-asset
monitoring. The arena's frozen information state consumes **six** score families
and a price block. Most of what this system computes reaches no decision.

Adding more collectors to that picture is the failure mode, not the fix.

---

## 0.5. Where this roadmap actually stands

Three denominators, because they answer different questions and only one of them
is the mission.

| Measure | Done | Left |
|---|---|---|
| **Items shipped** — 7 available (router and GNN are gated, not available) | **2 / 7 ≈ 29%** | 5 |
| **Weighted by effort** — the two shipped are the two cheapest | **≈ 14%** | ≈ 86% |
| **Demonstrated edge** | **0%** | 100% |

The gap between 29% and 14% is the honest part. `P0.1` (the reachability audit)
and `P0.3` (the review defects) were a day's work each. The five that remain —
the information bus, three alpha brains and the options surface — are each
multi-day research builds, and **none of the seven has produced a single paper
outcome yet.**

By this roadmap's own standard, we are at the start of the part that counts.
The infrastructure is materially ahead of the forecasting intelligence, which is
the imbalance §0 exists to correct.

---

## 1. What this roadmap does NOT do

* **It does not add a factor to `arena_composite`.** New mechanisms arrive as
  separate `PRODUCT_EXPERIMENT` books with their own identity, or they do not
  arrive. Folding them into the composite would hide exactly the thing being
  tested: whether their errors are different errors.
* **It does not build a router first.** `META_ROUTER_v1` is only interesting
  over selectors that are actually independent. It comes after they exist and
  have produced independent outputs, not before.
* **It does not build a GNN.** Not until simple graph-propagation features beat
  a non-graph baseline on the same split.
* **It does not run the fifteen-test list as a list.** Scored by
  `P(changes the roadmap) × value of the decision improved − cost`, three
  survive as next work. The rest are logged in §5, not queued. Fifteen good
  ideas at 1/15 depth each is how five months produced 0%.

---

## 2. P0 — make what exists reachable (cheap, mechanical, high information)

### P0.1 Signal reachability audit — **DONE this session**

`backend/services/signal_reachability.py`. The `forecast_populations.py` idea —
enumerate the PLAN, fail on an unclaimed entry — applied one layer up, to code
rather than ledgers. Reachability is **derived** from the import graph, not
listed in a registry, for the reason `guard_contract.py` already settled: a list
somebody maintains by memory is the honour system with extra steps.

Three tiers, because "unreachable" hides two very different facts:

| tier | meaning | count |
|---|---|---|
| **reachable** | a request or a timer can call it | 250 |
| **tooling_only** | only `scripts/` reaches it — offline research, no defect | 60 |
| **orphan** | neither. Only its own test can call it | 20 |

Every orphan carries a reason, and the reasons are typed: `OK` (correctly
callable from nowhere), `AWAITS` (built before its consumer, and the roadmap
owns it), `GAP` (should have a caller and does not).

**What the first run found, in the first minute:**

> **`detectability_gate` — TOURNAMENT-2's declared precondition — was imported
> by nothing.** `scripts/panel2_planted_worlds.py` names it three times, all in
> comments. "The T2 runner MUST call `assert_detectable`" had been true as a
> sentence and false as a fact since 2026-08-22.

**Fixed in the same session**: the planted-worlds script now calls the gate, and
adjudicates through it rather than through a second reader of the same receipt.
No default bar — `--min-recovery` comes from the prereg or the receipts are
written and explicitly **NOT ADJUDICATED**, because a bar this script picked
would be a bar chosen by whoever wanted the run to pass.

**Four gaps remain named** (`execution_boundary`, `strategy_library`,
`verdict_battery`, `winner_loser_factory`) — three of them enforcement
machinery that has never been run against the thing it was built to check, and
one of them CANON rule 4's matched-control factory. They are not queued here;
they are *named*, which is the difference between a known gap and a surprise.

It also found a **BOM on `backend/routers/portfolio.py`** that made the router
unparseable to `ast`, so its whole dependency tree read as orphaned — a
discovery rule that under-detects, which is the exact failure mode
`guard_contract` warns about one level up.

**Ships with a test that fails when a new module is unreachable and
unclassified**, and one that fails when a gap closes — so a gap closes
*visibly*.

### P0.2 A versioned information bus into the frozen state — **DONE 2026-08-24** (registry) · **COMPLETED 2026-08-24 evening** (identity)

`backend/services/arena/information_bus.py` · health key `information_bus` ·
12 tests · bus_version `4846fb0f33912200`, composite_fingerprint
`7418cb394c109879`.

`backend/services/arena/selector_identity.py` · health key `selector_identity` ·
10 tests (`test_selector_identity.py`).

> **The first half shipped a fingerprint nothing consumed.** External review,
> 2026-08-24: the bus was an *audit* surface — `spec.book_fingerprint` still
> ended with the bare global `discovery.COMPOSITE_VERSION`, so the loop P0.2
> claimed to close was open at both ends. Fixed below; the item is not
> "done" in the earlier entry's sense and the scorecard now says so.

The frozen state's inputs were a bare module-level dict (`SCORE_PREFIXES`).
Adding a key silently widened every book's inputs mid-trial, and nothing
recorded that it happened, when, or why.

**The constraint above is satisfied by separating two things that both get
called "adding a factor":**

| status | meaning | drifts books? |
|---|---|---|
| `ADMITTED_TO_COMPOSITE` | enters `COMPOSITE_WEIGHTS`; changes what books DECIDE | **yes, correctly** — a NAV series spanning the change describes two policies |
| `ADMITTED_TO_STATE` | frozen into the state, consumed by NO book | **no** — nothing any book decides changed |
| `CANDIDATE` | declared, not yet computed | no |

`composite_fingerprint()` is blind to the second and third, so admitting a
family nobody consumes is byte-identical and every seeded book keeps verifying
under its own inception. That is what lets a mechanism **accrue PIT history
before its book exists** — which matters precisely because history cannot be
backfilled for anything a vendor does not keep (see the options PIT store).

**It hashes the family NAMES, not the prose.** The first version hashed whole
entries, so rewording a `why` re-identified every composite book — reintroducing
the comment-only-edit defect that drifted 10 of 10 books on 2026-08-23. Caught
by a test whose name contradicted its own assertion.

`assert_registry_matches_code` refuses in **both** directions: a family in code
but undeclared (an undeclared widening) and a family declared but absent from
code (a book believing it decides on something it never sees). Enrolled in the
missing-input guard contract.

**Found while writing it:** `insider_cmp` is read into the frozen state and
carries **no composite weight** — the one already-existing state-only family,
undocumented until now.

#### The completion: identity that carries only what the book CONSUMES

    book fingerprint = book config
                     + SELECTOR IDENTITY      <- new
                     + router identity, if consumed
                     (+ execution-policy identity, when one exists)

and selector identity separates the two things that must both bind:

| component | what it covers | how it moves |
|---|---|---|
| ALGORITHM version | what the estimator *means* — `arena_composite@3-universe_quality` | hand-declared; "we changed how the z-scores blend" is not derivable from any input list |
| DEPENDENCY prints | *which* families it reads (`information_bus.composite_fingerprint()`) and at *what weights* (`composite_weight_fingerprint()`) | **derived**, so it cannot be forgotten |

Both are required, and the weights print is the one the review did not ask for:
`mom_12_1: 1.0 -> 2.0` is a different policy with an identical family set, and
before this the only thing that re-identified those books was whether the
editor also remembered to bump a string.

**Every live fingerprint is byte-identical today**, and that was mandatory, not
lucky. The nine books are still on the LEGACY whole-file scheme and take their
per-book stamp on Monday's pass; `assert_config_current` migrates only while the
legacy hash verifies, so a formula that moved would have stranded ten NAV
histories. Each dependency print therefore contributes **only when it differs
from the value the live seeds were sealed under** — the same two-axis scoping
`ROUTER_FINGERPRINT_BASELINE` already uses, with the same rule attached: those
baselines record history and must never be "updated" to track the current value.

`SelectorNotDeclared` refuses a book whose `selection_signal` has no dependency
map, rather than defaulting it to the composite's. That refusal *is* the
feature: the obvious fallback would have given `EVENT_RESPONSE_v1` momentum's
dependencies and drifted it every time the composite moved, with every hash
verifying. Enrolled in the missing-input guard contract.

The three properties the review named are asserted directly: a real
`ADMITTED_TO_STATE` family drifts **no** composite book; promoting it drifts
**every** one; and changing the composite in both ways leaves an independent
selector's book **byte-identical**.

### P0.3 — DONE this session

The four defects from the external review, plus a fifth found while fixing them.
See `ADJUDICATION_2026-08-24_EXTERNAL_REVIEW.md`. In particular the arena's
external paper execution was running **two sessions late** and is now submitted
inside the pass that decides.

---

## 3. P1 — three independent alpha mechanisms, in dependency order

Each is a separate `PRODUCT_EXPERIMENT` selector. Each gets a **ridge and a
LightGBM baseline on the same split**, and each is split **by date block**
(CANON §58: `n_effective` counts date blocks, never rows). None of them touches
`arena_composite`.

### P1.1 `EVENT_RESPONSE_v1` — does the first move continue or reverse?

**Why first.** It is the only one of the three whose corpus is both on disk and
large: `g4/earnings_v1` carries 2006→present announcements with surprise,
expectation, dispersion, run-up and an exchange-calendar `tradable_at` that has
already survived a validator. TAQ is pulled. The event store started accruing
this week but has no history, so **the historical model is built on the earnings
corpus, not the event store** — the store is what lets the same model run
forward on news later.

**Target.** Conditional on an event and its initial reaction, does the move
continue or revert over 30m / 1d / 2d / 5d — as a distribution, not a point.

**Inputs.** Event semantics and surprise · initial gap · liquidity · IV and
skew (from §4) · revisions · size · regime · novelty (once the store has 30
days).

**Why this and not "is the news good".** Stocks trade on surprise. The 2026 JFE
result on LLM news interpretation is that drift varies sharply *by news type* —
which is a statement about conditioning, and conditioning is what a model can
learn and a sentiment score cannot.

**Gate.** Planted-detectability before any result counts
(`detectability_gate.assert_detectable`). Beat both baselines out of block, or
it does not become a book.

### P1.2 `RELATIVE_VALUE_NN_v1` — should B replace A, net of costs?

**Why second.** The corpus exists (`NEURAL-RELATIVE-VALUE-1`: 72,495 pairwise
capital-substitution labels with measured transaction costs) and it answers a
question the composite cannot even ask: not "is this stock good" but "is this
stock better than the one whose capital it would take".

**The n is 145, not 72,495.** The pairs come from 145 date blocks. Under CANON
§58 that is the effective sample, and every split is by date block. A model
validated on pair-random splits would be measuring how well it interpolates
within a month.

**Architecture.** Small shared encoder over A and B, difference and interaction
features, multiple heads: `P(B beats A net of costs)` · expected net improvement
· drawdown improvement · `P(large gain)` · `P(large loss)`. Compared against
logistic regression, ridge, LightGBM and a small MLP.

**The decision rule is declared now, before the run:** if an MLP does not beat
LightGBM out of block, **there is no neural challenger** and this line closes
with a receipt. That is the point of running it early — it is cheap and it
settles a standing question.

**Portfolio context is v2, not v1.** `AAPL → NVDA` is a different decision in a
70%-semiconductor book, and the label should eventually be
`ΔU(B ← A | Portfolio)`. v1 establishes whether the pairwise signal exists at
all; conditioning it on the book is only worth doing if it does.

### P1.3 `ACTOR_MAGNITUDE_v1` — from "were they right" to "how much"

**Why third and not first.** The premise is validated (§6.1 of the adjudication:
persistence positive at every threshold), the corpus is on disk, and the
estimator exists. But direction-only hit rate is not tradable and never was —
so the next honest step is magnitude and interaction, not more analysts.

**Two extensions, both cheap:**

* **Magnitude.** Expected excess *size* conditional on actor, not just sign.
* **Actor × domain.** A biotech analyst's read on a trial and on semiconductor
  guidance are different forecasters. `actor_intelligence` already carries the
  dimensions (`actor × domain × claim_type × horizon × regime`); nothing has
  populated them.

**And one that is nearly free, because IBES is already on disk:**

* **`ANALYST_COCOVERAGE_GRAPH_v1`.** Which companies share analysts is a
  relationship graph that costs one groupby. Shared-analyst coverage is a
  documented information-spillover channel, and the Aegis-specific extension is
  to weight the edge by the shared analysts' **measured reliability** — which
  no published version can do, because reliability is what §6 just built.

  **This is the "simple graph features before a GNN" step.** If reliability-
  weighted co-coverage edges carry no information, the graph programme stops
  here for a groupby's worth of cost.

---

## 4. P2 — the options surface, from data already owned

`OPTIONS_EXPECTATION_SURFACE_v1`: the market's implied distribution around an
event, as an **expectation sensor** — not a bullish/bearish score. The existing
`options_intelligence.py` heuristics (high skew → bearish, extreme put/call →
contrarian) become descriptive features; nothing routes capital on a hand-signed
mapping.

**The source is `optionm.stdopd`, not `opprcd`** — corrected from the review.
**And then corrected again, against the data rather than against the catalogue
(see §4.9.1): `stdopd` cannot produce skew.**

* `stdopd` gets a **named consumer** and comes off the deferred list — the same
  rule that released `vsurfd`, working as designed.
* **`opprcd` (4.31B rows, 30 partitions) stays deferred.** It is contract-level:
  open interest, volume, max pain. The first version needs none of them. When
  one of those features earns its place, it will name itself.

Feeds P1.1 directly: `LLM/model implied distribution vs option-implied
distribution` is the disagreement that makes an event interesting.

---

## 4.5. Adjudicated from the second external review (2026-08-24)

Same standing rule: a review is adjudicated, not imported. Accepted here, with
what changed:

| Proposal | Ruling |
|---|---|
| Make the analyst graph **directional** (leader → laggard) | **Accepted and BUILT** into `ANALYST-COCOVERAGE-GRAPH-1`. Result in §4.6 — the asymmetry does not replicate. |
| Add **52-week-high** conditioning | **Accepted and BUILT.** Result in §4.6 — it adds nothing. |
| Test **revision propagation** as a second target | **Deferred to `REVISION_FORECASTER_v1`**, where it is the primary target rather than a secondary one. Bolting it on here would have doubled the arm count and the multiplicity bar with it. |
| `OPTIONS_BORROW_CONFOUND_v1` before believing option-implied predictability | **Accepted, and promoted to a PRECONDITION of §4** rather than a follow-up. If IV skew is largely a borrow-fee proxy, the surface work should know that before it is built, not after. |
| `MANAGEMENT_EVASION_DELTA_v1` — evasion relative to the executive's OWN baseline | **Accepted; queued after `EVENT_RESPONSE_v1`**, which supplies the event scaffolding it needs. |
| `ACTOR_DIALOGUE_EPISODE_v1` — questioner skill × evasion × subsequent revision | **Accepted; after the two above.** It is the strongest actor × event × LLM connection available, and it is also the one that needs both of them to exist first. |
| `REVISION_FORECASTER_v1` — event → analyst revision → price | **Accepted into P2.** Decomposing the causal chain is likely easier to learn than mapping news text to returns in one hop. |
| `DISAGREEMENT_LAB_v1` | **Accepted, gated** on ≥3 independent selectors, same gate as the router. |
| **Failure attribution** in the nightly critic (discovery / data / perception / graph / forecast / routing / selection / sizing / exit / execution) | **Accepted into P0.** "The trade lost" teaches nothing about what to fix. |
| **`OUTCOME_CORRECT` separate from `MECHANISM_CORRECT`** | **Accepted into P0, and it is the more important half.** A win for the wrong reason must not reinforce the thesis that was wrong. |
| **Order-level execution ledger** — decision→intent→submit→fill→slippage, so captured edge is measurable | **Accepted, and BUILT this session** (`execution_ledger.py`, §4.7). It was urgent: the arena's first external fills arrive this week, and what is not recorded then cannot be reconstructed later. |

---

## 4.6. `ANALYST-COCOVERAGE-GRAPH-1` — RUN, and it answered

Full result: `docs/FINDING_2026-08-24_ANALYST_COCOVERAGE_GRAPH.md`.
Verdict **CONTINUE** under the rule frozen before the run (`spec_hash
0e1578bd0410653b`), on 131 months.

**Replicates, past both obvious confounds:** equal-weighted co-coverage peer
return, IC **+0.0227** (t 2.35). Paired, it beats own momentum by +0.0155
(t 2.57) and plain SIC2 industry momentum by **+0.0088 (t 2.24)** — and the
graph restricted to **cross-industry links only** still clears the bar at
+0.0159 (p 0.043). It is not sector momentum in disguise.

**All three refinements measured zero:**

| hoped-for | measured (paired) |
|---|---|
| reliability-weighted edges | **−0.00008 ± 0.00052 (t −0.15)** |
| leader → laggard asymmetry | +0.0025 ± 0.0037 (t 0.68) |
| 52-week-high conditioning | −0.0006 (t −0.05) |

The reliability arm nearly produced a **false negative**: its first form
(`max(0, edge)`) left 0.1% of 2014 coverage weighted, so it was starved rather
than tested. Re-posed as a tilt around an intact graph it is a precisely
measured zero. Reliability grades *claims* well and says nothing about
*relationships* — different questions, and only one is answered.

**Consequences for this roadmap:**

1. `GRAPH_PROPAGATION_v1` is licensed as its own book, using the plain
   equal-weighted signal. Nothing fancier earned its place.
2. **The GNN gate is NOT met in spirit and the GNN stays unbuilt.** It was
   gated on simple graph features paying. They pay — but the three kinds of
   structure a GNN exists to exploit each measured zero. A model whose
   advantage is learning richer edge structure has just been told the richer
   edge structure is not there.
3. The result is **under-powered by its own design**: every passing arm's IC
   sits below its own 80%-power MDE. It licenses building, not believing.

---

## 4.7. `execution_ledger` — BUILT this session

`backend/services/portfolio_intelligence/execution_ledger.py`. One row per
intended order, written at SUBMISSION time and resolved later, so the broker's
real fill can be set beside the book's synthetic one.

Two NAV curves diverging tells you the strategies differ. It cannot tell you
whether the difference is slippage, a partial fill, or an order that never
filled at all — and a fill nobody recorded cannot be reconstructed from an
equity series a month later. This is the first thing in the repository that
checks the `cost_bps + slippage_bps` every arena book assumes.

**What it deliberately records rather than drops**, because omission is the
failure mode here and every one of these leaves no fill behind:

* the order that was **never filled** — the most expensive outcome there is;
* the **partial** fill, with its fraction;
* the broker filling something the book has no synthetic fill for — the two
  sides disagreeing about what was traded;
* a broker that could not be READ, kept as `PENDING` rather than written as
  missing fills. A network outage must not read as an execution finding.

`assert_captured_edge_reportable` refuses a summary while too much is
unresolved. **Orders do not resolve at random** — the ones that hang are the
illiquid, the wide-spread and the never-filled — so a summary taken too early
describes the easy subset and reads as *good* execution precisely when
execution was worst.

Reconciliation runs inside the 17:45 pass, immediately BEFORE the next
submission: that is the first moment both sides of the previous decision exist.

**A bug worth recording**, caught by its own test: the ledger is append-only, so
a resolved order leaves a `PENDING` row *and* a resolution row. Counting rows in
state `PENDING` therefore counted every resolved order forever — `health` would
have gone DEGRADED five days after the first successful reconciliation and
stayed there, reporting a stuck pipeline that was working perfectly. Open orders
are now derived by order identity, not row state.

---

## 4.8. `EVENT-RESPONSE-1` — RAN, and it says STOP

Full result: `docs/FINDING_2026-08-24_EVENT_RESPONSE.md`. 50,910 events, 168
event months, `spec_hash 9a54b0c3da4cfe56` frozen before the first number.

**PEAD is there and the pipeline proves it works**: unconditional drift +0.00066
at 1 session (t 2.66), +0.00084 at 2 (t 2.58), gone by 5. Right sign, plausible
magnitude, right decay — so the null below is about the question, not the
plumbing. It is also ~7bps, which is economically nothing.

**No model ranks WHICH events drift.** Nine arms, nothing survives BH-FDR.
LightGBM at 1d/2d reaches p ≈ 0.06/0.08 — precisely the number that becomes a
finding if you run nine arms and report the best. The published PEAD prior
(surprise alone) is flat.

**Under-powered again**: MDE₈₀ 0.024–0.030 against a best observed 0.019, so
~50–60% power. The honest null is "no ranking of size ≥ 0.025 exists in these
features", not "no effect".

**What this changes:** do not build an earnings-response selector on daily bars
without options data. That is the entire content of the STOP.

**And it hands §4 its named consumer.** The most likely reason nothing appeared
is that `options_implied_move` is `None` throughout the corpus — so "surprise"
was measured against analyst consensus only, when the tradable quantity is
`surprise − what was already priced`. The successor is one experiment:
`OPTIONS_EXPECTATION_SURFACE_v1` from `stdopd`, re-asking this question with the
implied move as the central feature. `opprcd`'s 4.31B rows remain unneeded.

---

## 4.9. The options pull is FEASIBLE and small — measured, not assumed

`OPTIONS_EXPECTATION_SURFACE_v1` was deferred behind "OptionMetrics is 4.31B
rows". §4.8 gave it a named consumer; this measures what it would actually cost,
before anybody pulls anything.

**Linkage (the thing that could have blocked it entirely):**
`wrdsapps__opcrsphist` maps permno → secid with validity windows, and it is on
disk.

| | |
|---|---|
| earnings events linked to a permno | **52,604** |
| with a **date-valid** secid link | **52,604 — 100.0%** |
| distinct secids needed | **2,418** |
| event years | 2006–2019 |

**Bounded pull size**, `stdopd` restricted to those secids on the sessions
around each event. Corrected after reading the grid (§4.9.1): the real density
is **14.0 rows per secid-date** — 11 maturities × 2 sides, some absent — not the
4 coordinates first assumed.

| window | rows |
|---|---|
| ±1 session | ~2.2M |
| ±3 sessions | ~5.2M |
| **±5 sessions** | **~8.1M** |

**~8.1M rows, against the 4,310M of `opprcd` that caused the deferral.** The deferral was about `opprcd` and about pulling a
whole family blind; a pull bounded by a named consumer's actual event set is
three orders of magnitude smaller and follows the pattern
`wrds_pull_vsurfd_daily` already established — bounded by design, declared in the
manifest so a later reader cannot mistake a narrow extraction for missing data.

**And the file already carries the lesson**: `vsurfd`'s docstring records that
month-end coverage was reported twice as a property of OptionMetrics when it was
a property of our own `WHERE` clause. A property of your extraction is not a
property of the data.

Remaining before pulling: a link-quality check on `score` (the link table
carries a match-confidence column that this count ignored), and confirming
`stdopd`'s coordinate grid actually contains the maturities an earnings window
needs.

---

### 4.9.1 CORRECTION — `stdopd` is ATM-only, so it cannot produce skew

Earlier today §4 asserted that "ATM IV, term structure, 25Δ skew and risk
reversals all derive from" `stdopd`. **Half of that is false**, and reading the
file rather than the table description is what showed it.

`optionm__stdopd1996` holds exactly **one row per (secid, date, maturity,
side)** — 6.7M rows, 2,222 secids, 252 dates, 11 maturities (10/30/60/91/122/
152/182/273/365/547/730 days). The delta is not a coordinate; it is whatever the
at-the-money strike happens to give:

| 30-day | min | median | max |
|---|---|---|---|
| calls | +0.501 | **+0.523** | +0.900 |
| puts | −0.787 | **−0.482** | −0.122 |

Both sides sit on the money. **There are no OTM wings, so there is no 25Δ, no
risk reversal and no butterfly.** A "skew" computed from this file would be a
number produced by code that ran green and measured something else.

| feature | source |
|---|---|
| ATM implied vol | **`stdopd`** ✓ |
| term structure (11 maturities) | **`stdopd`** ✓ |
| implied MOVE around an event | **`stdopd`** ✓ — the one §4.8 actually needs |
| 25Δ skew, risk reversal, butterfly | **`vsurfd`** — the standardized-DELTA surface |
| open interest, volume, max pain | `opprcd` — **still not needed** |

**This does not block §4.8's successor.** What that experiment needs is
`surprise − implied move`, and the implied move is an ATM quantity: `stdopd`
supplies it. Skew is a second question, and `vsurfd` already has a named
consumer, so bounding it the same way (2,418 secids × event windows) is the same
small pull rather than the 10.07B-row family.

**This is the third time on this dataset.** `wrds_pull_vsurfd_daily`'s docstring
records that month-end coverage was twice reported as a property of
OptionMetrics when it was a property of our own `WHERE` clause. Here the
catalogue said "standardized options" and the reasonable inference — standardized
on delta as well as maturity — was wrong. **Read the grid before promising the
feature.**

---

## 4.10. `RELATIVE-VALUE-NN-1` — RAN: STOP, and the NN question is closed

Full result: `docs/FINDING_2026-08-24_RELATIVE_VALUE_NN.md`. 71,647 pairs,
**n_effective 145 date blocks**, 105 test dates.

| model | IC | t | BH-FDR |
|---|---|---|---|
| ridge | +0.0233 | 1.05 | ✗ |
| lightgbm | +0.0117 | 0.98 | ✗ |
| mlp | +0.0034 | 0.30 | ✗ |

Nothing survives. The MLP is **worst of the three** — behind both the tree
(−0.008 paired) and the line (−0.020 paired). Per the rule declared before the
run, **`NEURAL-RELATIVE-VALUE` closes as a v1 question with a receipt**, and the
multi-head torch model this roadmap described is **not built**.

Under-powered as usual: MDE₈₀ 0.033–0.062 against observed 0.003–0.023.

**AND THE FIRST RUN WAS A LEAK.** It returned IC 0.97–0.99 with t over 1,000 and
declared the signal licensed. `cs_rank` — in the feature list — is the
cross-sectional rank **of the forward return** (measured IC +1.0000). The
script's own docstring already said forward quantities are the answer, not
features; the column *name* was trusted over the column.

That is the **third instance in one session** of asserting a property of data
from its description rather than measuring it (`stdopd` skew, the event-response
gap, `cs_rank`). Two were caught by reading. This one was caught only because
the number was absurd — **which is not a method**, since a leak yielding 0.15
would have shipped.

**So it is now structural:** `backend/services/feature_leakage_guard.py` refuses
any feature whose within-block rank IC against the target exceeds 0.5, **before
any model is fitted**. Verified against the real leak. Every future screen calls
it. `0.99 → 0.023` is the guard's value in one number.

---

## 4.11. Scoreboard after one night of building alpha

Three alpha mechanisms attempted, all three now have receipts:

| item | verdict | what it cost to learn |
|---|---|---|
| `ANALYST-COCOVERAGE-GRAPH-1` | **CONTINUE** — effect replicates past own- and industry-momentum; all three refinements measured zero | one groupby |
| `EVENT-RESPONSE-1` | **STOP** — PEAD real at 7bps, nothing ranks which events drift | one evening |
| `RELATIVE-VALUE-NN-1` | **STOP** — nothing out of block; the neural question closes | one evening |

**Demonstrated edge remains 0%**, and that is the honest reading: the roadmap's
premise was that alpha-source diversity is the bottleneck, and the first three
attempts at new sources returned one plain published effect and two nulls.

That is not a reason to abandon the premise — it is the premise being *tested*
instead of assumed, which is what the previous five months did not do. What it
does say is that the cheap-and-on-disk ideas are now mostly spent, and the next
ones (options-conditioned events, actor magnitude, management language) need
**data that is not yet extracted** rather than another model on the same panel.

---

## 4.12. AMENDMENT-3 — the licensed selector CAN be computed live (mostly)

§4.6 licensed `GRAPH_PROPAGATION_v1` on a signal measured at **analyst**
granularity (`amaskcd`) — which exists only in IBES, a WRDS research dataset.
Production has firm-attributed upgrades/downgrades via yfinance. **A signal that
cannot be computed live is not a selector**, so this was asked before anyone
built it.

Measured, 2014–2024 US recommendations: **8,336 analysts vs 589 firms**, median
coverage **4 names vs 14**. A firm graph is far denser and far less selective,
so survival was a real question.

| arm | analyst IC (t) | firm IC (t) | bar | BH |
|---|---|---|---|---|
| `own_ret_1m` *(control)* | +0.0072 (0.77) | +0.0074 (0.81) | ✗ | ✗ |
| **`peer_eq`** | +0.0228 (2.35) | **+0.0218 (3.05)** | ✓ | ✓ |
| `peer_shared` | +0.0226 (2.31) | +0.0220 (2.77) | ✓ | ✓ |
| `peer_leader` | +0.0186 (2.12) | +0.0181 (2.66) | ✓ | ✓ |
| `peer_laggard` | +0.0160 (1.92) | +0.0109 (1.72) | ✓ | ✗ |

**It survives, and is better measured at firm level** — slightly lower IC, higher
t, because a denser graph makes each month's estimate less noisy. The control
stays flat, so this is not own-momentum leaking in.

### The remaining gap — and it is SMALLER than first written here

This section first claimed that `estimid` is "standing coverage" while a live
feed gives only actions, implying the live path loses a lot: *"a bank covering a
name quietly all year appears in IBES and not in an actions feed"*.

**Measured, rather than asserted: 87.1% of IBES recommendation rows are already
changes or initiations** (174,522 of 200,357, 2014–2024 US).

The reason is that `ibes.recddet` rows are recommendation EVENTS, not daily
snapshots of who covers what — and `coverage()` here defines coverage as
*"issued a recommendation in the trailing 12 months"*. That was **already
close to an actions feed**, not to standing coverage. The gap between what was
validated and what an upgrade/downgrade feed supplies is ~13%, not a large hole.

This was the same error as the night's others: describing what a dataset
contains without measuring it. Recorded rather than quietly edited, because the
correction is the interesting part.

**AMENDMENT-4 RAN, and it clears.** A graph built ONLY from rows a live feed
would report:

| arm | standing | actions-only | bar | BH |
|---|---|---|---|---|
| `own_ret_1m` *(control)* | +0.0074 (t 0.81) | +0.0072 (t 0.77) | ✗ | ✗ |
| **`peer_eq`** | +0.0218 (t 3.05) | **+0.0213 (t 3.00)** | ✓ | ✓ |
| `peer_shared` | +0.0220 (t 2.77) | +0.0213 (t 2.76) | ✓ | ✓ |
| `peer_leader` | +0.0181 (t 2.66) | +0.0182 (t 2.72) | ✓ | ✓ |

**`GRAPH_PROPAGATION_v1` is licensed AND buildable.** The effect survives both
reductions a production path forces — firm rather than analyst, and actions
rather than standing coverage — with the control flat throughout.

**What is still untested** is the vendor, not the granularity: yfinance's
upgrade/downgrade history is not IBES, and its depth and history length are its
own question. That is a data-availability check on one feed, not a question
about whether the signal exists in a computable form.

AMENDMENT-4's original text tested the strict version — a graph built ONLY from rows a live feed
would report — offline, by reconstructing the actions feed from IBES's own
recommendation levels. Comparing against yfinance directly would confound
actions-vs-standing with that vendor's coverage differences; IBES has the level,
so the reconstruction is exact and isolates the one question.

---

## 4.13. `EVENT-RESPONSE-2` — the hypothesis was right, the edge is borrow fees

Full result: `docs/FINDING_2026-08-24_EVENT_RESPONSE_V2.md`. 49,357 events,
168 event months, 21.1M rows of `stdopd` pulled to make it possible.

**v1's own diagnosis tested POSITIVE.** Adding the implied move takes the tree
from +0.0105 (t 1.04) to **+0.0315 (t 3.19)**, surviving BH-FDR; paired on
identical months, **options help by +0.0210 ± 0.0093 (t 2.27)**. Ridge gains
nothing, so the relationship is non-linear — which is what "did it move more
than priced" should be. And it was **adequately powered**, uniquely this
session: MDE₈₀ 0.0276 against observed 0.0315.

**Then the declared precondition killed it.**

| | all | excl. high-borrow |
|---|---|---|
| `drift1` | +0.0315 (t 3.19) | +0.0151 (t **1.42**) |
| `drift5` | +0.0288 (t 2.61) | +0.0113 (t **0.96**) |

Removing the top borrow quintile — 20% of events — removes **52% / 61%** of the
effect and all significance. The point estimate halved while MDE₈₀ moved only
0.0276 → 0.0297, so this is not a power artefact.

**Verdict: NOT LICENSED — borrow-confounded.** Downgraded from BUILD, with both
verdicts kept in the receipt so the downgrade is visible.

### The order of operations is the whole story

`OPTIONS_BORROW_CONFOUND_v1` was promoted to a **PRECONDITION** of this work in
§4.5 rather than left as a follow-up. Had it been a follow-up, this session
would have shipped a BUILD on IC 0.0315 with t 3.19 — a genuinely strong
number — and retracted it later.

That is the **second time in one session** that ordering decided whether
something became a refusal or a retraction. The first was
`feature_leakage_guard`, built after an IC of 0.99 was caught by luck.

**What is NOT concluded:** that the option feature is useless. It says this
edge, on these names, at this horizon, is not separable from borrow. Conditioning
on borrow explicitly — trading only where it survives, or modelling the fee as a
cost — is a different experiment and needs its own declaration.

---

## 5. Logged, not queued

Good ideas with no owner and no date. Recorded so they are not re-derived, and
explicitly **not** work in progress: surprise-of-surprise · second-order
earnings read-through · actor behavioural surprise (distance from an actor's own
distribution) · management credibility and evasion delta from earnings calls ·
questioner intelligence · consensus topology and revision acceleration ·
originator vs echoer · information half-life and diffusion curves · prediction-
market → equity exposure betas · attention-conditioned insider signal ·
narrative crowding and migration · event-induced correlation jumps · the
three-way uncertainty split (aleatoric / epistemic / data) · model failure
probability · convexity heads · mechanism-vs-outcome grading · regret
decomposition · value-of-information LLM scheduling.

Several are excellent. **The constraint is not idea supply.** Anything promoted
from this list displaces something in §3, and says what it displaces.

---

## 6. Sequencing

| When | What | Blocks on |
|---|---|---|
| ~~Now~~ | ~~P0.1 reachability audit~~ — **DONE**, and it found a live gap | — |
| ~~Now~~ | ~~P1.3 co-coverage graph probe~~ — **DONE**, verdict CONTINUE; all three refinements measured zero (§4.6) | — |
| ~~Next~~ | ~~P1.1 `EVENT_RESPONSE_v1`~~ — **RAN: STOP** (§4.8). The daily options-blind spec is refuted; the successor is the options surface, which now has a named consumer | — |
| ~~Next~~ | ~~P1.2 `RELATIVE_VALUE_NN_v1`~~ — **RAN: STOP** (§4.10); the NN question is closed with a receipt | — |
| ~~After P0.1~~ | ~~P0.2 information bus~~ — **registry DONE**; **identity wiring DONE 2026-08-24 evening** (`selector_identity.py`), which is what the first half left open | — |
| ~~NOW~~ | ~~P2 options surface~~ — **DONE**: 21.1M rows pulled, `EVENT-RESPONSE-2` run, verdict NOT LICENSED (borrow-confounded, §4.13) | — |
| After ≥3 independent selectors have live output | `META_ROUTER_v1` | independence, measured not assumed |
| Only if graph features pay | GNN | P1.3 returning something |

**Nothing here is a claim.** Every item ships under `PRODUCT_EXPERIMENT`: a
frozen strategy contract before the first decision, paper only. A
`RESEARCH_CLAIM` needs the full apparatus and none of this is close to it.

---

## 7. The scorecard, unchanged

Demonstrated edge: **0%.** The machinery got better again this session and that
number did not move, because only matured decisions move it. What changed is
that the next thing to build is finally the thing that could: mechanisms whose
errors are different errors, competing where the outcome is recorded.
