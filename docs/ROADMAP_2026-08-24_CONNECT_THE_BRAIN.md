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
| Now | P1.3 co-coverage graph probe | nothing (IBES on disk) |
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
