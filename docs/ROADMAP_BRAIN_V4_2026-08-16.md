# ROADMAP — BRAIN V4: the discovery loop

**Written 2026-08-16 by the brain, on Murat's direction. Supersedes
`ROADMAP_BRAIN_V3_2026-08-14.md`.** V3's five tracks are absorbed below; nothing
in it is cancelled, and its closed families stay closed.

Read with `OPTIMUS_OBJECTIVE.md` §0 (the mission) and
`HANDOFF_2026-08-16_BRAIN_ORDER_3.md` (R13/R14/R15).

---

## 1. Where we actually stand

Percentages are judgment dressed as measurement, and this project has spent a
month removing exactly that kind of number. Two corrections to the estimates in
circulation:

**Demonstrated investment edge is 0%, not 10–15%.** Zero valid IIF nights, zero
resolved forward predictions until today, ten paper lanes at 69 days against a
24-month floor. Nothing has been certified forward. Rounding zero up to 10–15%
because the machinery looks impressive is the exact move we have been
eliminating. The infrastructure numbers (~85% data, ~80% referee) are fair.

**So measure progress by gates passed, not by percentage felt.** Seven gates
stand between here and a self-learning investment brain:

| # | gate | status |
|---|---|---|
| G1 | A referee that cannot be fooled by its own instruments | **DOWNGRADED 2026-08-16 → OPERATIONAL / PROVISIONALLY STRONG.** I declared this passed on the strength of five denominator defects found by running. Then a **false kill was found compiled into the source** (`"NO COVERAGE"`, `n4_precursor_coverage.py:207`) — *after* the declaration. A gate asserting the referee cannot be fooled by its own instruments cannot be passed while an instrument was in fact fooling us, and the battery that would actually test it (known-answer worlds; `grep known_answer\|synthetic_world` returns nothing) **does not exist**. Flips to PASSED only when that battery recovers planted truth at declared false-positive **and false-kill** rates |
| G2 | A unit of analysis with enough sample to resolve anything | **PASSED 2026-08-16** — regime→event (R14) |
| G3 | An objective function that is terminal wealth, not return | **PARTIAL** — the wealth path landed (`policies.py:54`) and `utility.py` primitives exist, but the objective is **available, not authoritative**: `counterfactual.py:91` still sorts on `-net_return_pct` whenever no objective is passed, and `:126` computes `regret_pct` as a **`net_return_pct` difference unconditionally** — so `best()` can be selected under log-wealth while the regret beside it is reported in raw return. **A policy chosen by one criterion and measured by another is a units mismatch, not a partial build.** Three of four personalities (preservation, balanced, extreme growth) do not exist in `OBJECTIVES` |
| G4 | An expectation layer — surprise, not announcement | **NOT STARTED** |
| G5 | A world model whose heads are the moments we can actually forecast | **NOT STARTED** |
| G6 | A sizing/policy learner trained against G3 | **NOT STARTED** |
| G7 | Forward certification of anything at all | **first resolutions today** |

G1 and G2 were the hard conceptual ones and they are done. **G3 and G4 are small
builds that everything else depends on**, and both are currently missing — which
is the single most actionable fact in this document.

## 2. What we actually learned, in plain terms

**We are much better at forecasting how violent a move will be than which way it
goes.** Direction AUC ≈ 0.497 / 0.509 / 0.501 at 5/20/60 days — a coin flip.
Future realised volatility IC 0.53–0.62 on 82,954 rows.

**The caveat travels with the claim, always:** against free trailing `rv20`, the
model's edge is −0.085 to +0.025 and **not detectable** — a failure to detect
under §19, never a demonstration of no difference, and it still has no MDE
printed. So: *volatility is forecastable; our model is not yet better at it than
the cheapest possible baseline.*

**That is bad news for a paper and good news for a product**, and the two must
not be conflated. Volatility-targeted sizing does not require beating `rv20`; it
requires volatility to be forecastable *at all, by anything, including `rv20`*.

**Four independent lines have now converged on sizing** — NIGHT-12's drawdown at
beta 2.15, NIGHT-13's constant half-exposure beating the timing ladder, the
de-risking study's state→exposure map, and now N6. **Nobody has built it.**

**Our knowledge library covers nothing.** 85–88% of exceptional moves had no
precursor, and the library's coverage *is* its base rate (lift 0.82–1.15). Six
rules discovered from a handful of SPY episodes are not a brain. **Coverage, not
validity, is the bottleneck.**

**Rare states never accumulate sample.** 273 crisis episodes needed at a 3pp bar;
25–80 exist in the entire world across twelve markets and 36 years. Only ≥10pp
effects are ever testable there.

## 3. The architecture

```
WORLD          news · laws · filings · prices · options · macro · government
               money · foreign primary sources · insider and fund behaviour
  │
  ▼
LLM PERCEPTION structured events, entities, relationships, semantic surprise
  │            — never a price forecast
  ▼
EXPECTATION    what happened MINUS what was expected MINUS what price already
  LAYER (G4)   reflected  →  the only quantity an event study may condition on
  │
  ▼
NN WORLD       second-moment heads first: magnitude · realised vol · tail
  MODEL (G5)   probability · drawdown · co-movement change · state transition
  │            · uncertainty.  Direction is A head, not the objective.
  ▼
POLICY /       given the distribution and the current book: what exposure?
  SIZING (G6)  reward = terminal log wealth under a DECLARED utility (G3)
  │
  ▼
PORTFOLIO      paper books, one per surviving mechanism family
  │
  ▼
CRITIC         perception / inference / action / sizing / timing / cost —
  │            which layer failed, measured against a matched null
  ▼
MECHANISM      retrieval at the NEXT decision: "I have seen this before"
  MEMORY
  │
  └──────────────────────────► back to perception
```

**No component has final authority.** The LLM proposes meaning, the NN finds
statistical structure, the engine grades both, and forward reality grades the
engine. That division is not a preference; NIGHT-3 measured 16,320 LLM stock
picks and found no edge, while MARKET-GRAPH-1 found the LLM's *relationship*
information real. Use each for what it demonstrably does.

## 4. Sequencing, with gates

### Phase 0 — the two missing primitives. Small, and everything waits on them.

**G3 — the objective layer.** `PolicyResult` carries return, cost, turnover and
nothing else; `ranked()` sorts by `-net_return_pct` from a menu containing 1.25×
and 1.5× levered arms. **A policy learner cannot be trained against a reward
function that does not exist in the codebase.** Add path risk (max drawdown,
time under water, realised vol, terminal log wealth) and make the objective
declared and pluggable. This is the literal prerequisite for Phase 2, and it is
an afternoon.

**G4 — the expectation layer.** *The market does not react to facts; it reacts to
facts relative to expectations.* "Company got FDA approval" is not an event.
`P(approval) = 0.95 and it arrived early with a broader label than consensus` is
an event. Every event record must carry:

```
what happened · what was expected · what price already reflected · what follows
```

Without this, every one of the ten families in §5 measures announcements, and
announcement studies are a well-populated graveyard. **G4 is not a research
family — it is the infrastructure that decides whether all of them work.** It is
also where `options-implied expected move` and `analyst revision state`, both
already built, finally earn their place.

### Phase 1 — World Model v0 (G5)

Self-supervised temporal encoder over numeric state + LLM event features +
economic graph, with **supervised second-moment heads**: magnitude, realised
vol, tail probability, drawdown, co-movement change, state transition,
uncertainty.

**Mandatory baseline ladder, published beside every head:** naive base rate →
`rv20` alone → EWMA → HAR → Log-HAR → GAM/LightGBM → NN. A neural model earns
its complexity only by beating the ladder out of sample.

**AMENDED the same day by `d7172fc`, which changes this phase's emphasis.** The
ladder was built and run: at 20 days the four cheap rungs land at
0.6096 / 0.6143 / 0.6120 / 0.6140 with **paired MDEs of 0.005–0.010** — a
*well-powered* comparison, because rungs that are nearly the same model vary
little fold to fold — and they are **indistinguishable**. The 14-feature model
adds +0.0240 against an MDE of 0.0716, and its MDE is fourteen times the gap
between the cheap rungs *because the model is the volatile one across folds*.

That is far stronger than "we could not tell". It is: **at five thousandths of
an IC we still cannot tell four free volatility forecasters apart.**

The consequence for this phase is direct: **realised volatility is a solved,
commoditised head, and it is not where a neural network earns its keep.** Take
the free forecaster and move on. World Model v0's value must come from the heads
that are *not* commoditised — **tail probability, drawdown, co-movement change,
state transition, and uncertainty** — each of which needs its own cheap-baseline
ladder before the NN is allowed to claim anything. Build those ladders first;
they may commoditise too, and finding that out costs nothing.

My N11 premise was also refuted here, cleanly and on slices declared before the
numbers: volatility is **more** predictable at regime transitions and high
vol-of-vol (IC 0.633 / 0.652 vs 0.614), not less. Two of the four places the
baseline was supposed to break are where everything works best.

**Direction is a head, not the objective.** Everything we have measured says
first moments are not there and second moments are.

### Phase 2 — the sizing learner (G6). The highest-value build in this document.

Given the world model's distribution and the current book: what exposure?
Reward is terminal log wealth under a declared utility, with drawdown and ruin
probability printed beside return, against equal-weight and constant-exposure
controls.

**Start with `rv20` vol-targeting as the baseline product, immediately, before
any NN.** Four convergent findings justify it, it needs no new research, and it
gives Phase 1 something to beat. Labelled `PRODUCT_EXPERIMENT`, never an alpha
claim, and the honest framing is that we are implementing a known technique
because our own evidence kept independently pointing at it.

**Not RL yet.** Supervised world state → supervised policy → *then* consider RL.
RL over historical episodes offers a million ways to learn backtest artifacts,
and we have measured how easily this project's own instruments manufacture
findings.

### Phase 3 — the mechanism factory (coverage, R15)

**N9: mine the 85%.** Autopsy the exceptional moves that had *no* precursor —
not to explain them, but to ask what was knowable beforehand, at scale. Each
emits an executable precursor candidate, parent-barred, into the atlas. At
$0.00103 per structured autopsy, a thousand candidates costs a dollar. This is
the only proposal on the table that attacks coverage rather than validity.

Target: move from **6 mechanisms** to **hundreds of candidates**, and report
coverage lift with its MDE as the Gym's headline number.

### Phase 4 — latent discovery, and its entrance exam

Let the NN find states nobody named — "Asian dollar-funding stress + weakening
semiconductor inventories + rising cross-asset correlation" — then hand the
nearest historical episodes to the LLM to *explain*, then convert the
explanation into a falsifiable mechanism and test it where it was not found.

**Gate: known-answer worlds first.** An unsupervised latent state that appears to
predict is precisely the object most likely to be an artifact, and this project
has measured how convincingly its own instruments manufacture results.
`WORLD-CONDITIONAL` — positive edge in state A, negative in B, global average
zero — plus a measured **false-kill rate** and false-discovery rate, is the
entrance exam. No latent state is trusted before it.

### Phase 5 — shadow books

Every surviving mechanism family gets its own paper capital and is graded by
reality continuously, not by a backtest verdict. Over months a higher-level
allocator can learn which families add value *together*. This is cheap, it is
forward evidence rather than fitted evidence, and it is how the programme stops
arguing about backtests.

## 5. The event families, sorted by the only thing that matters

Murat's list is the right list. **R13 sorts it**: every family declares
`event_frequency_per_year` and `declared_effect_size` before compute, and
`lint_prereg.py` refuses the pair the sample cannot resolve. Sorted:

**Ample sample — build these first**

| family | frequency | note |
|---|---|---|
| INSIDER-INTELLIGENCE | **~1,750 events/day** | already ingesting; unusual-for-*this-actor*, clusters, role, post-drawdown, 10b5-1 |
| CORPORATE-PIVOT | thousands/yr | abrupt 10-K/8-K language shifts, hiring, capex, patents — the "shoe company becomes AI" case. Separate genuine pivots from narrative by capital actually deployed |
| M&A-PROPAGATION | hundreds–thousands/yr | the trade may be the *next* company revalued, not the announced one |
| GOVERNMENT-MONEY | thousands/yr | USAspending awards; measure *acceleration* and size vs revenue, not the award |
| POLICY-CHAIN | thousands/yr | Congress.gov actions → agency → award → supplier → material → bottleneck |
| FDA-EVENT | hundreds/yr | openFDA; approval/rejection/label/recall, and **the expectation layer decides whether it is an event at all** |
| SEMANTIC-DISAGREEMENT | every event | see §6 — the best new idea on the list |

**Frequent if framed as data releases, not as crises**

| CROSS-BORDER / MULTILINGUAL-LEAD | monthly per series | METI/BOJ publish on schedule with precise timestamps. The question is **not** "read Japanese news first" — professionals already do. It is *which foreign information is economically connected to a US security and not yet reflected in its price*, with the information-time gap **measured** rather than assumed |

**Currently unregistrable as stated — reframe or wait**

| family | problem |
|---|---|
| THEME-BUBBLE ("will AI crash") | **n = 1.** This is the 25-episode trap wearing a new hat. Reframe as *"do financing, capex, skew and correlation concentration jointly forecast drawdown magnitude across many historical theme unwinds"* — then it has sample |
| GEOPOLITICAL-SUPPLY-GRAPH | major shocks are rare. Reframe around **tariff and export-control announcements**, which are frequent, scheduled and documented |

On the DeepSeek anecdote: High-Flyer was a quant fund using ML before DeepSeek
existed, which makes it inspiration for *spending compute to find structure* —
not evidence that reading Chinese news early makes money. Test the
information-lag idea ourselves; do not inherit it as a premise.

## 6. The three ideas I would add

**Opportunity Gap = Aegis-estimated impact − market-implied impact.** For every
event: the LLM's economic significance, against the options-implied expected
move, the realised reaction, and the analyst revision. When Aegis thinks an
event matters far more than the market's reaction implies, does drift follow?
When the market moves 15% and the LLM finds little fundamental change, does it
revert? **This is a far better use of an LLM than "will NVDA rise tomorrow",
because it asks the model for something it demonstrably has (economic
understanding) and asks the market for something it demonstrably has (a price),
and trades the difference.** It also has enormous sample — every event is an
observation.

**Second-order lag is where to search.** The obvious AI stock has priced the
news. The transformer manufacturer, the cooling supplier, the rare-earth
processor and the utility have not. MARKET-GRAPH-1's surviving result is exactly
the machinery for finding them, and REACTION-GAP-1 is exactly the measurement.
This is the highest-value application of the one clean positive we own.

**Actor skill must be decomposed, not scored.** An actor with no selection skill
may have excellent *sell timing*; another may be good only in biotech; a third
may look good because they are permanently long tech. And the decisive question
for every one of them: **does the apparent skill survive the disclosure delay?**
N1 — the disclosure-lag decay curve — answers that for the whole Teacher Library
in an afternoon, and if the return accrues before disclosure the signal is real
and uncopyable. **It was ordered as highest-EV and has still not been run.**

## 7. What this does not change

The referee stays exactly as strict, and R13 makes it stricter at the gate.
Aggressive exploration, strict promotion. No Gym number is an alpha claim. Only
`REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` close anything, and a global
negative still does not answer a conditional question that was never asked.
Forward evidence remains the only citable kind.

**The discipline is not there to conclude that nothing works. It is there to stop
a self-learning machine from learning bullshit — and the more the machine
learns, the more load it carries.**

## 8. Immediate order

1. **G3** — the objective layer. Prerequisite for Phase 2. An afternoon.
2. **G4** — the expectation layer. Decides whether §5 works at all.
3. **`rv20` vol-targeting** as the baseline sizing product — no NN, no new
   research, four convergent findings behind it.
4. **N9** — mine the 85%, the coverage factory.
5. **N1** — the disclosure-lag curve. Still unrun, still cheapest, still able to
   terminate a whole track.
6. **World Model v0** with its baseline ladder, after G3/G4.
7. Known-answer worlds before any latent state is believed.

— brain, 2026-08-16
