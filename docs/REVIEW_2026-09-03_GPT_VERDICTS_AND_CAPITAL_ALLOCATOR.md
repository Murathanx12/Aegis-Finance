# REVIEW RECORD + DESIGN — 2026-09-03 (overnight session, Opus)

Two things in one file, because they arrived together and cite each other:
PART A records the external reviewer's (GPT, via Murat, 2026-09-03) verdicts
on the seven S36 research questions — so the adjudication survives the session
that received it. PART B is the design consequence: the **Capital Allocator /
Decision Engine**, the component the review says is now the program's largest
bottleneck. Nothing here executes tonight; judging is 2026-09-04 11:00 ET and
the builder boundaries in `HANDOFF_2026-09-03_S36_REVIEW_AND_BUILD.md` hold.

Items marked **ATTENDED** need Murat's sign-off before they bind anything.

---

## PART A — the reviewer's verdicts on the seven S36 questions

The reviewer's framing sentence, worth keeping verbatim because it names the
bottleneck better than we did:

> "AEGIS is much better at research, falsification, safety and post-mortems
> than it is at converting an imperfect belief into a portfolio and
> committing capital to it."

1. **Null bar (Q1):** diagnosis ACCEPTED. ≥64 model-null draws is fine as the
   *development* gate; anything capital-authoritative wants ≥256 (prefer
   512–1,000) **and** — the part we had not said — when selecting among
   models the relevant null is the distribution of the **best selected
   model**: a max-statistic / White's-Reality-Check-style family test, not
   per-model nulls. (EdgeStack, the closest public architecture, runs
   SPA/Reality Check for exactly this.) → `learner/nullbar.py` carries 64 as
   dev default; the family-max correction is the v2 requirement before any
   learner feeds sizing.
2. **Band (Q2):** option (a)+shadow — **remove 3–5's privileged admission
   authority after judging**; keep `toxic_ge_5` (it survived FDR) and the
   `<1.5` floor as pure exclusion; keep the old 3–5 selection running as a
   shadow/control so the forward record keeps accruing. Positive admission
   moves to revision + learner mechanisms. **ATTENDED** (reshapes live books).
3. **Learner multiplicity (Q3):** freeze **one champion now** —
   `encoder_clf residual 1m`, exact schema, one primary portfolio metric;
   forward shadow accrual only. t 2.64 historical earns a serious forward
   experiment, not production-alpha status. No re-picking whichever learner
   looks best next week.
4. **Level signals (Q4):** **retire from alpha selection.** Levels remain as
   state/exclusion/valuation context and NN features. Alpha capital goes to
   mechanisms with demonstrated net excess — currently revision (6m).
5. **MoE (Q5):** yes — monthly gate over monthly experts only; longer-horizon
   signals enter as **fixed/slow sleeves**, because a 12m expert's trailing
   matured reliability lags the regime by construction.
6. **Scenarios (Q6):** no committee-of-N yet. One primary structured
   extractor + one independent adjudicator **only for disputed/high-value
   fields**; keep disagreement as a logged feature. (Agreement 0.225 makes a
   full parliament expensive noise.)
7. **States (Q7):** first consumer is **position sizing / risk budget** — NOT
   stop width (path-dependent; we have already watched a sensible stop
   destroy winners), and definitely not hard admission. States rank loss/tail,
   which is what sizing consumes. Stop adaptation becomes its own later
   shadow experiment. *(This overrules the handoff's stop-width lean.)*

**Reviewer's build-order change, adopted:** PotentialUniverse **before** MoE
(an MoE with no decision consumer is another excellent experiment that changes
nothing we own), then the Capital Allocator immediately after, then MoE as a
strategy/allocation selector, then DecisionArtifact local→Railway, and only
after all that graph/sequence models.

**External evidence base** (public repos; hackathon P&L claims are marketing
until the history is public): 1rok (constructor with a mandate: ≥85%
invested, ≤8 names, run→artifact separated from execute→broker);
renee-jia/trading-bot (+34.5% vs SPY +16.1% but −26.8% max DD — beta
amplifier mistaken for alpha; the anti-lesson on leverage); itsang89's Claude
trading agent (+0.30% vs SPY +3.36% in 12 days, 40–56% cash — *knew* it was
underinvested, wrote about it daily, never deployed: our mirror);
TheCromazone/alpaca-paper-bot (every decision routine reads its own
performance-vs-SPY first — regret as an INPUT, not a report); EdgeStack
(SPA/Reality Check, CPCV/PBO); Eventus (mechanism-specific books behind
capital firewalls); PX5000 (predict realized magnitude, trade only where it
disagrees with implied — the template for State-0 options).

---

## PART B — Capital Allocator / Decision Engine (design v0)

### The one-line spec

> **AEGIS always knows what the next dollar should be doing.** "17 names
> failed admission so $70,000 is idle" is not a decision; every unused dollar
> gets a documented competing allocation, and cash must *beat the benchmark
> in expectation* to be held.

Tonight's live receipt of the disease
(`aegis-alpha-terminal/state/benchmark_regret_20260903.json`): SPY flat
(+0.07%) over the competition window while hack3/4/6 sit 60–67% cash with no
opinion recorded about the idle two-thirds. The kickoff-day stop cascade is
explained and fixed; the idle capital has never been *decided*.

### Position in the pipeline

```
WORLD MODEL → POTENTIAL UNIVERSE → STRATEGY SLEEVES → CAPITAL ALLOCATOR
    → DECISION ARTIFACT → EXECUTION (sealed, gates-only cuts)
```

- **Input:** PotentialUniverse (one scorecard per observable company-vintage:
  engine prior, v1/v2 predictions, state/anomaly, disagreement, execution
  capacity, OBSERVE_ONLY flag, reasons+falsifiers) + per-sleeve capacity and
  matured forward reliability + benchmark nowcast.
- **Output:** a DecisionArtifact whose LAST ROW IS ALWAYS the residual-capital
  decision: `unallocated → benchmark exposure (named instrument)` unless the
  artifact carries an explicit bearish/deleveraging thesis for cash. Cash
  requires a thesis; benchmark is the default parking orbit. (S36's
  holding-period study reached the same rule from the stop side: stops park
  proceeds in SPY, never cash.)

### Objective (per sleeve i, declared not implied)

```
U_i = E[R_i − R_bench] − λ1·CVaR_i − λ2·Costs_i − λ3·Uncertainty_i
```

subject to mandate + survival constraints (gross ceiling, per-name cap,
worst-case-in-dollars printed for the largest admissible book — the session-
start protocol §4 number). λs are per-personality (preservation / balanced /
aggressive / extreme growth) and live in config, not prose. `Uncertainty_i`
is where model-null percentile + states-based tail estimates + sleeve
reliability enter — Q7's sizing consumer, Q1's bar, one term.

### What makes it honest (the licences)

- v1 is a **PRODUCT_EXPERIMENT**: frozen strategy contract before the first
  decision, shadow first; no significance gate. It does NOT need the
  allocator to be *right*, it needs the allocation to be *recorded with its
  reasons* so regret is computable.
- **Benchmark regret is a first-class daily metric** (already receipted as of
  tonight). The nightly report decomposes:
  `selection alpha + beta + sizing + timing + cash drag + execution + risk interventions`
  so a $10k loss is attributable to forecast vs underdeployment vs
  concentration vs stops vs market.
- Leverage enters only as a ladder on a frozen contract: 1× → 1.5× → 2×,
  each rung graded on compound wealth *after* drawdown, before the next rung.
  The 4× experiment is the END of that curve. (renee-jia is the cautionary
  receipt.)

### Post-judging fleet remap (reviewer's table, adopted as intent) — **ATTENDED**

| account | job | tests |
|---|---|---|
| hack1 | benchmark/control: SPY + survival layer | the opportunity cost every book must beat |
| hack2 | **Revision-6M**: monthly overlapping cohorts (~1/6 of sleeve/month, 6m hold, hard falsifier exits) | the only net-VW-beating admission family |
| hack3 | **Learner-v2 monthly**: frozen champion, esp. `no_opinion` names | forward estimate of the t 2.64 finding |
| hack4 | **Profit-max ensemble**: v2 ∩ revision ∩ event evidence, concentrated | where the leverage ladder eventually lives |
| hack5 | **Vol/convexity**: predicted realized/tail move vs implied; defined-risk options only | PX5000's lesson on our states |
| hack6 | **Market-neutral challenger** | alpha without an up market |

Nothing redeploys before judging completes 2026-09-04.

### Two new research strategies (preregister before any accrual)

1. **State-0 tail mispricing (options):** don't buy broken lottery tickets;
   price them. `state 0 + learner tail forecast + catalyst → P(+25/+50%) →
   option-implied tail price → call-spread EV`; trade only where physical
   beats implied after spread/slippage. Needs `pre-register-trial` — the
   state's mean is negative and only the tail is the thesis.
2. **Toxic-band short expression:** `toxic_ge_5` survived FDR as an
   exclusion; test whether it is monetizable (borrow-adjusted short, put
   spreads, call credit spreads, market-neutral basket) or whether borrow +
   options pricing already ate it. Either answer is a finding.

### Build order consequence (updates handoff queue #5/#6)

1. PotentialUniverse v1 (in build tonight, shadow-persisted, graded like a book)
2. Capital Allocator v1 (shadow: emits DecisionArtifacts + regret decomposition; consumes #1)
3. Revision-6M + Learner-v2-monthly + benchmark control as frozen contracts
4. State-0 options + toxic-band short as preregistered research
5. MoE as allocation selector (monthly experts; slow sleeves fixed)
6. DecisionArtifact laptop→Railway bridge
7. Graph/sequence models last
