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

### P0.2 A versioned information bus into the frozen state

Once P0.1 names the orphans, the frozen information state needs a declared way
to admit them — versioned, so adding a family is a policy event with a hash and
not a silent widening of every book's inputs mid-trial.

Constraint that makes this non-trivial and must not be skipped: **the seeded
books' `policy_fingerprint` must not change when a field they do not consume is
added.** Per-book identity (shipped 2026-08-23) is what makes this possible at
all; it is the reason this is P0 now and was impossible last week.

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
Standardized options at fixed maturities and deltas carry `impl_volatility`,
`delta`, `gamma`, `vega`; ATM IV, term structure, 25Δ skew and risk reversals
all derive from them. **1996 is already on disk (6.7M rows).**

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
| Next | P1.1 `EVENT_RESPONSE_v1` | nothing (g4 + TAQ on disk) |
| Next | P1.2 `RELATIVE_VALUE_NN_v1` | nothing (corpus on disk) |
| After P0.1 | P0.2 information bus | knowing which orphans are worth admitting |
| After P1.1 | P2 options surface | a consumer that needs it |
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
