# Aegis — Human Heuristics, Anti-Mainstream Discovery, and Velocity-Adaptive Roadmap

Date: 2026-08-26
Status: strategic memory / roadmap addendum
Owner intent: preserve the user's investing logic and convert it into falsifiable, data-backed research without letting LLM familiarity bias collapse discovery into mega-cap consensus names.

## 1. Core objective

Aegis is not being built to approximate an S&P 500 allocation or to maximize safety. Its target is high expected compound return / P&L subject to explicit survival constraints. Risk is a budget to spend on measured asymmetric opportunity, not something to minimize by default.

The project must search for opportunities that ordinary LLMs and mainstream screeners systematically under-cover: small/mid-cap firms, state-changing catalysts, supply-chain bottlenecks, regulatory shifts, under-followed beneficiaries, financing constraints, physical-economy signals, and cross-market causal propagation.

Index and mega-cap names may be used as sensors, regime indicators, hedges, causal anchors, or expressions when they truly dominate alternatives. Familiarity, index membership, analyst coverage, news volume, and option liquidity must never add alpha score by themselves.

## 2. Human decision logic to preserve and test

The user's historical process was not simply 'high volatility'. It was approximately:

1. Start with a broad externally generated candidate set, often from Bloomberg/analyst research.
2. Filter toward large forecast upside (historically often >50% analyst-implied upside).
3. Prefer industries believed to face durable future demand: technology, biotech/pharma R&D, energy, critical materials/metals, infrastructure.
4. Ask a causal human question: 'What will the world need, and who fulfills that need?'
5. Look for identifiable state changes/catalysts: FDA events, commercialization, policy, tariffs, domestic manufacturing support, contracts, capacity, trial results, regulation, supply shortages, backlog, adoption.
6. Treat deep drawdowns as potentially attractive only when the future-state thesis remains plausible.
7. Favor smaller/mid-cap companies when the same underlying economic trend may create larger percentage re-rating than in mega-caps.
8. Use analyst targets as candidate-generation / market-expectation data, not as ground truth.
9. Buy/sell timing matters separately from stock selection.

Historical example to preserve as a reasoning template: First Solar thesis combined U.S. protectionism / domestic manufacturing support with renewable-energy policy and First Solar's position as a major U.S. solar supplier. The important pattern is POLICY -> DOMESTIC SUPPLY ADVANTAGE -> FUNDAMENTAL BENEFICIARY -> MARKET REPRICING, not the ticker itself.

## 3. Corrections to intuitive heuristics

- Large market capitalization / high trading volume does not mechanically prevent large percentage moves. The useful hypothesis is that deep liquidity, diversified cash flows, index ownership, and lower idiosyncratic uncertainty often reduce convexity relative to small caps; test this rather than assuming size caps returns.
- Buybacks can provide marginal demand but do not guarantee downside floors.
- High volatility alone is not alpha. It can amplify a real edge or amplify losses.
- Analyst upside alone is not alpha. Target freshness, revision direction, dispersion, coverage, catalyst, drawdown, and market-implied expectations must be modeled jointly.
- A mega-cap earnings beat can move the index mechanically through index weight and behaviorally through sector/regime belief updates. These channels must be separated.

## 4. NVIDIA event thesis — reusable framework

NVIDIA should be treated as both a company event and an information shock to the broader AI complex.

Separate channels:

A. Mechanical index channel
NVDA return x current S&P 500 weight -> direct index contribution.

B. Belief-cascade channel
NVDA earnings/guide -> belief about AI demand -> semiconductor / datacenter / networking / memory / power / cooling expectations -> portfolio reallocations.

C. Risk-aversion / fear channel
Large negative surprise -> investor fear -> sector de-risking -> correlated selling -> margin/volatility feedback.

D. Supply-chain confirmation channel
Strong demand -> HBM, foundry, packaging, optics, server ODM, power, cooling, grid beneficiaries.

E. Affordability / financing channel
Higher GPU/HBM/server costs + financing dependence -> customer ROI / capex sustainability risk.

F. Competition channel
Custom silicon / AMD / alternative accelerators -> future pricing power and share.

Do not trade 'NVDA beat = NVDA up'. Compare actual state vector with analyst/option expectations and search for second-/third-order assets whose price response is too small or too large relative to their causal exposure.

## 5. Accounting/depreciation concern to test

The recalled Coffeezilla/Burry argument is primarily about hyperscalers extending useful lives/depreciation schedules for AI/data-center equipment, not NVIDIA simply keeping its own old graphics cards on its balance sheet to inflate NVIDIA revenue.

Research lane: AI_DEPRECIATION_REALITY_GAP_v1

Question: Are reported hyperscaler profits/free cash flow overstated relative to economic depreciation because AI hardware becomes technologically obsolete faster than accounting useful lives?

Data:
- company depreciation policy changes by year
- useful-life assumptions for servers/network equipment
- capex and depreciation expense
- GPU resale values / secondary-market prices by generation
- NVIDIA generation cadence / performance-per-dollar decay
- impairment/write-off history
- lease/purchase obligations
- datacenter utilization / replacement cycles

Outputs:
- accounting depreciation vs estimated economic depreciation
- adjusted owner earnings / FCF
- customer affordability and future capex pressure
- beneficiaries/losers if replacement cycles shorten

## 6. Anti-mainstream discovery architecture

Discovery must occur before ticker familiarity can bias reasoning.

Pipeline:
FULL TRADABLE UNIVERSE
-> size / liquidity / sector / coverage strata
-> quantitative + event + causal candidate generation
-> standardized evidence packet
-> anonymized company ID
-> LLM / agent reasoning
-> reveal ticker only after score freeze
-> market-expectation comparison
-> expression selection

Required guards:
- FAME_BIAS: identical packet should not score differently when a famous ticker is revealed.
- COVERAGE_BIAS: evidence quantity/news count cannot increase conviction by itself.
- EVIDENCE_BUDGET_EQUALIZATION: comparable source budget for every candidate.
- MEGACAP_COLLAPSE: warn when discovery output converges excessively to mega-cap tech.
- ANALYST_HERDING_GUARD: analyst ratings hidden during first-pass fundamental/causal reasoning.

## 7. Analyst-upside candidate funnel

Build ANALYST_DISLOCATION_FUNNEL_v1.

Start from all tradable names, not names an LLM remembers.

Features:
- consensus target gap
- target age / freshness
- target revision direction and magnitude
- analyst count / coverage density
- dispersion across targets
- current price drawdown from 52w high and from last target revision
- catalyst proximity
- market cap / liquidity
- short interest
- options-implied distribution where available
- cash runway / financing risk
- state-change score
- sector / causal-theme exposure

Primary hypothesis is interaction, not a single variable:
TARGET_GAP x FRESHNESS x DRAWDOWN x CATALYST x STATE_CHANGE x COVERAGE.

Use analyst data as market expectations/candidate generation. The engine must be allowed to conclude that analysts are stale/wrong.

## 8. Need-map / bottleneck investing

Formalize the human question 'What will we need, and who fulfills it?' as NEEDS_GRAPH_v1.

Examples:
AI compute demand
-> accelerators
-> HBM
-> foundry / advanced packaging
-> networking / optics
-> server ODM / racks
-> cooling
-> power conversion
-> transformers / switchgear
-> generation / storage
-> grid connection
-> construction labor / land / water

Energy transition / industrial policy
-> domestic manufacturing
-> tariffs/subsidies
-> constrained domestic suppliers
-> capacity expansion
-> materials / equipment / permitting

At each node estimate:
- demand acceleration
- current capacity utilization / backlog
- concentration
- substitution difficulty
- pricing power
- capex lag
- market expectation / coverage
- investable public entities

Core rule: follow the closest binding bottleneck, not the most famous end-market company.

## 9. Behavioral / neuropsychology layer

Human intuitions become explicit hypotheses, never unlogged trade rules.

BEHAVIORAL_PROPAGATION_v1 should model:
- limited attention
- salience
- fear / loss aversion
- anchoring to prior earnings/targets
- herding / information cascades
- disposition effect
- retail chase / squeeze dynamics
- institutional de-risking
- margin-call / forced-selling feedback
- index / ETF mechanical flows
- dealer gamma / options hedging

For each event, separate:
FUNDAMENTAL SHOCK
MECHANICAL INDEX EFFECT
BELIEF UPDATE
ATTENTION EFFECT
FLOW / POSITIONING EFFECT
LIQUIDITY EFFECT

Do not label a behavioral story as causal until a discriminating placebo is specified.

## 10. Mega-cap as sensor, smaller-cap as expression

Build ANCHOR_TO_TORQUE_v1.

Hypothesis: a mega-cap event may be the highest-quality sensor for a theme while an under-followed supplier/beneficiary offers greater percentage convexity.

Example:
NVDA state update -> infer AI demand regime -> rank MU / memory / optics / power / cooling / grid / server suppliers by causal exposure, priced-in state, and liquidity.

The anchor is not automatically the trade.

## 11. Normalization and cross-sectional comparability

Raw trillion-dollar vs $900M values should not dominate model reasoning.

For candidate ranking, compute both raw economic values and normalized transforms:
- sector/size percentile
- z-score or robust rank
- revenue growth percentile
- margin change percentile
- target gap percentile
- volatility percentile
- drawdown percentile
- short-interest percentile
- news/coverage percentile
- causal-exposure percentile

Never discard raw values; normalized values are for comparison, not replacement.

Use within-sector and within-size normalization to prevent scale from being mistaken for quality.

## 12. Hedge-fund / high-leverage replication research

Study successful and failed concentrated funds as strategy archetypes, not heroes to copy.

Priority case: Situational Awareness / Leopold Aschenbrenner.

Research questions:
- What was the economic thesis?
- Which securities represented each causal node?
- What portion of return came from stock selection vs leverage/options?
- Gross/net exposure and hidden factor concentration?
- Financing terms / margin requirements / liquidity?
- What drawdown would have survived at 1x, 1.5x, 2x, etc.?
- Did the thesis remain right while the financing structure killed the fund?
- Could Aegis reproduce the convex upside using bounded-loss options or dynamic leverage with a survival constraint?

Build LEVERAGE_WITH_SURVIVAL_v1:
maximize expected terminal wealth subject to explicit ruin / forced-liquidation probability ceiling, not fixed leverage.

Required stress scenarios include correlated AI selloff, vol expansion, borrow/margin changes, gap risk, and liquidity disappearance.

## 13. Stock holding vs options

Expression is downstream of the thesis.

For every candidate compare:
- shares
- leveraged shares if allowed
- calls/puts
- debit spreads
- calendars
- stock + protective option
- beta/sector-neutral pair
- cash

Score:
EXPECTED NET P&L
CAPITAL EFFICIENCY
THETA
VEGA/GAMMA EXPOSURE
SPREAD/SLIPPAGE
GAP RISK
HORIZON FIT
SURVIVAL COST

Do not use options just because the stock is volatile or the chain is liquid.

## 14. Velocity-adaptive roadmap — replace date-bound thinking

Aegis is an unusually fast agentic project. Roadmap items should be controlled primarily by dependencies, evidence gates, and parallel capacity, not arbitrary weekly/monthly time boxes.

Each roadmap item must carry:
- dependency graph
- decision it can change
- cheapest decisive experiment
- max research spend
- promotion criteria
- kill criteria
- execution-surface impact
- parallelizable? yes/no
- night-safe? yes/no

Work states:
IDEA -> CHEAP PROBE -> ADVERSARIAL BATTERY -> PREREG SHADOW -> FORWARD PAPER -> CAPITAL CANDIDATE -> PROMOTED / KILLED.

Fast-path rule: if all gates are satisfied in one session, advance immediately. Never wait for a calendar milestone merely because the roadmap expected more time.

Slow-path rule: no amount of agent speed bypasses missing statistical power or prospective evidence.

## 15. Session-memory / continuity contract

At every substantial session end:
1. update docs/HANDOFF.md with current truth, not intended work;
2. update roadmap item states;
3. record killed hypotheses in NEGATIVE_RESULTS / finding docs;
4. record open questions and exact next discriminating tests;
5. record execution processes / hashes / configs where relevant;
6. ingest/distill the session into Optimus Tier-2 Aegis project memory when the Optimus pipeline is available;
7. preserve strategic user intent separately from transient experiment results.

Never rely on one LLM conversation to preserve roadmap state.

## 16. Immediate research queue

Competition-safe / night-safe where possible:

1. Resolve NVDA pre-registered state vector before price reaction and grade old vs information-first brain.
2. CAUSAL_CONTAGION_NVDA_v1: measure NVDA earnings shock propagation to SMH/QQQ and under-followed second-order beneficiaries; separate direct index weight from residual behavioral contagion.
3. ANALYST_DISLOCATION_FUNNEL_v1 / STALE_TARGET_v2.
4. NEEDS_GRAPH_v1 seeded with AI datacenter and U.S. industrial-policy chains.
5. AI_DEPRECIATION_REALITY_GAP_v1.
6. ANCHOR_TO_TORQUE_v1.
7. FAME_BIAS + COVERAGE_BIAS benchmark.
8. LEVERAGE_WITH_SURVIVAL_v1 using Situational Awareness as historical case.
9. NON_PRINT_BOUNCE_v1 adversarial battery (already identified, do not skip execution-unit checks).
10. Persistent causal-edge IDs so repeated earnings/data releases accumulate evidence rather than creating isolated event trees.
11. Build research-alpha / multiple-testing budget before autonomous strategy generation scales further.

## 17. Strategic non-goals

- Do not optimize for appearing academically legitimate at the cost of never trading.
- Do not lower evidentiary standards merely to produce activity.
- Do not let the LLM's familiarity with famous companies determine the investable universe.
- Do not confuse high volatility with positive expected value.
- Do not confuse an analyst target with truth.
- Do not make a one-event causal graph pretend to be statistically validated.
- Do not freeze the roadmap to calendar durations when agents can complete validated work faster.

## 18. Long-term target

Aegis should continuously:

WORLD SENSORS
-> generate structured evidence
-> update persistent causal beliefs
-> identify where human/market expectations differ from physical/economic reality
-> search the entire tradable universe for the most asymmetric expressions
-> compare shares/options/pairs/cash
-> allocate risk to strategies by marginal expected contribution
-> observe reality
-> learn which data sources, causal edges, behavioral templates, models, and strategy archetypes actually work.

The LLM expands possibility space. The quantitative engine computes and falsifies. The market supplies reward. Optimus preserves the accumulated project memory and decision logic.

---

# SESSION-13 ADDENDUM (2026-08-26, Opus day) — validation, and what the sealed record already says

Everything above is the original document, unchanged. This section is what was
CHECKED against our own data and sealed records before any of it is acted on.

## 0.1 A correction I owe, about this very document

My first act was to report that the two documents above had never been
committed: `git cat-file -t 174b6796` and `889a9ef5` both returned "not a valid
object", and neither path was on disk.

**That was wrong, and the error was mine.** I ran `cat-file` against stale local
refs without fetching this repository first (I had fetched a different one), and
I looked for `AEGIS_STRATEGIC_INVARIANTS.md` at the repo root when it lives at
`docs/AEGIS_STRATEGIC_INVARIANTS.md`. Both commits exist and were pushed
directly to GitHub.

The rule this actually earns is the sharper one:

> **Absence of a local object is not evidence of absence of a commit.** Fetch
> first, then check, and check the real path. A confident "it does not exist"
> from an unfetched repo is exactly the class of false negative that
> `feedback_silence_is_not_evidence` is about — and I produced one while writing
> a memory about producing them.

## 0.2 What was validated against the sealed NVDA record

| Claim | Verdict |
|---|---|
| Street Q3 FY2027 revenue ~$104.2bn | **CONFIRMED** — identical to the sealed vector, field rank 1 |
| Q2 consensus ~$92.18bn | **CONSISTENT** — sealed record carries $92.05bn as of 25 Aug |
| Company GM guide ~75% | **CONFIRMED** — sealed field rank 2 |
| Options imply ~5.4% | **SUPERSEDED.** That is a *reported* preview figure. Our record already holds a reported 5.58% marked CROSS-CHECK ONLY, and our own measurement from our own chain is **5.10%**. Use 5.10%. |
| S&P opened ~-0.14%, Nasdaq ~-0.20% | **CORROBORATED** — our own bars give SPY open gap -0.15%, QQQ -0.33% |
| NVDA is ~7.99% of the S&P 500 | **UNVERIFIED** — plausible, not checked from a primary source |
| Q1 FY2027 was $81.6bn / $1.87 adj vs $78.9bn / $1.75, and the stock still fell after hours | **UNVERIFIED**, and load-bearing for the "a beat is not enough" argument — verify before grading it |
| Hyperscaler useful-life extension understates depreciation | **UNVERIFIED** as to magnitude. The *direction* of the correction in section 5 is accepted and is a real fix to the original recollection |
| Situational Awareness: +439%, 13F ~28% SNDK / ~28% MU / ~9% BE / ~6% TSM / ~6% Nebius | **UNVERIFIED, AND BLOCKING** for section 12. Verify from the 13F filings themselves before writing reconstruction code. |

**No lane may cite an UNVERIFIED row as evidence.** They are leads.

## 0.3 Three of the proposed NVDA hypotheses are ALREADY SEALED — do not re-record them

The sealed `NVDA_2026-08-27` vector already carries, and states more strongly:

- "NVDA beats Q2 consensus" is field `revenue_surprise`, sealed at **rank 13 of
  13** — deliberately the least important field;
- "a headline beat does not guarantee a gain" is asserted by the ranking itself;
- "the Q3 guide dominates the reaction" is sealed at **rank 1**.

Re-recording them as a fresh human-hypothesis record would create two records of
one claim and let us grade whichever wins. **Refused.** Genuinely new, and added
as a separate shadow record that does not touch the seal: contagion beyond the
mechanical index contribution, size torque after controlling NVDA and SMH beta,
and attention lag in low-coverage names.

**And the power verdict binds all three.**
`FINDING_2026-08-26_THE_SHOCK_GRAPH_CANNOT_RESOLVE_ONE_EVENT`: per-node
one-event MDE runs 5.9% (TSM) to 24.0% (AAOI) against a 5.10% implied move, and
the residual is a sector factor, not idiosyncratic noise. Adding SMH cuts the
capacity-edge MDE to 3.8% — the smallest detectable *abnormal* return, which is
not comparable to NVDA's own move. **On one event, only a near-total
non-response is resolvable.** These are recorded for CALIBRATION and to
accumulate across repeated events. A session that reports them as a result
tonight has misread the power arithmetic.

## 0.4 The split section 16 does not make

Section 16 mixes two programmes with different clocks: work that can change the
**4 Sep competition outcome** — about six trading sessions — and the **Aegis
research programme**, which is months. Items 2 through 8 and 10 are the second
kind. An analyst funnel, a fame-bias study and a needs graph will not produce a
gradeable edge in six sessions, and pretending otherwise is how a roadmap grows
without moving.

**Competition-affecting work is small and comes first. Everything else is
explicitly after.** The exception is `FAME_BIAS`, which is cheap, night-safe,
needs no new data, and could change the candidate funnel today.

## 0.6 STATUS AFTER THE 2026-08-26 UNATTENDED BLOCK

**Every P0 item is closed.** Receipts in the hackathon repo.

| lane | status |
|---|---|
| `LOOP_LIVENESS_v1` | **DONE** — heartbeat, process scan, PRE-BEAT. The PID probe is MEASURED, because `os.kill(pid,0)` reports a *dead* process as ALIVE on Windows and would have certified a dead loop |
| ledger chain break | **DONE** — six breaks, CONCURRENT_WRITE confirmed, epoch-declared not repaired |
| `REPEATED_INVARIANT_ESCALATION` | **DONE** — WARN/ELEVATED/FAIL, no acknowledge verb, its absence asserted by test |
| defect 4 | **CLOSED, and I had mis-sized it** — 1500s was a constant, measured median 368s; 7 of 9 structures are long-only so a late exit cannot breach a budgeted loss |
| refusal decomposition | **DONE** — `already_held=32, evidence=12, execution=4, risk=0`: **saturated**, not barren and not over-strict |
| `LEVERAGE_WITH_SURVIVAL_v1` | **UNBLOCKED, phase 1 DONE** — 13F verified from SEC EDGAR; see below |
| `FAME_BIAS_v1` | **RUN. NOT DETECTED** — drift −0.36p vs a 2.64p noise floor, MDE 3.53p, NOT PROMOTABLE |
| `ANALYST_DISLOCATION_FUNNEL_v1` | **PARTIALLY UNBLOCKED** — see below |
| `CAUSAL_CONTAGION_NVDA_v1` | **baseline fitted BEFORE the print**, event path refuses until the session exists |
| P0.5 competition admission | **PROPOSAL written, nothing enforced** |

### The finding that transfers: effective N by RISK

Situational Awareness LP's Q2 2026 book — every figure verified from the filings
themselves — measured **5.34 by weight and 1.43 by RISK**, and on its worst July
session **20 of 21 names fell together**. Marked through the drawdown its
**unlevered return was −23.3% and it survived**; margin broke at 2.0x on 16 July.
Carrying its reported +439% in, 1.0x ends at **+313%**. *The thesis was right and
the financing killed it.*

Our own books, same code, weighted by true max loss: **dev 1.51, exp1 1.27** —
exp1 below the fund's value at forced liquidation. This is the measurement
`MAX_THESIS_CLUSTER` needed, with a threshold argued from a real liquidation
rather than picked round.

### What is still genuinely blocked, and why

**The target-gap leg of the analyst funnel.** Finnhub's free tier refuses
`stock/price-target` (HTTP 403), so Murat's literal ">50% analyst upside" screen
**cannot be reproduced from this source**. Recorded as `UNAVAILABLE_FREE_TIER`
and never approximated — a fabricated column in a PIT panel is worse than a
missing one. What IS available is the **revision-direction leg**: recommendation
counts by period, hence net breadth and its monthly change.

`scripts/analyst_panel.py` now captures that daily at 17:30 ET, stratified across
dollar-volume buckets so it is not another mega-cap list. **We cannot recover
vintages we never recorded, so the only way to unblock this lane is to start the
clock — and every day it does not run is a day permanently missing.**

## 0.5 P0 — protect the forward record (competition-affecting)

- **`LOOP_LIVENESS_v1`: DONE** (`alpha/liveness.py`, `scripts/liveness.py`, dashboard panel). A DNS blip killed both loops on 26 Aug and the same
  cause silently killed session 9's. Transport conversion and a supervisor are
  in; they are necessary, not sufficient. **Correcting the review's design:** an
  external watchdog process on this machine can also die, reproducing the
  original bug one level up. Liveness must be **pull-based from somewhere
  already being read** — a receipt the day session and the handoff consult —
  never a second daemon nobody watches.
- **Ledger chain break: DONE.** `docs/FINDING_LEDGER_CHAIN_BREAK_2026-08-25.md`
  in the hackathon repo. Cause **CONFIRMED CONCURRENT_WRITE**; it was **six**
  breaks, not one, because `verify_chain` returned at the first. Not repaired —
  declared as an epoch, with a manifest hash so the accepted list cannot be
  widened later to absorb a new break.
- **`REPEATED_INVARIANT_ESCALATION`.** The chain warning printed 53+ times over
  two days unread. A warning that no action can clear stops carrying
  information.
- **Defect 4: CLOSED, and it was mis-sized.** The "up to 1500s" exposure was a configured constant; ten measured passes run median 368s / max 439s. And 7 of 9 live structures are LONG-ONLY, whose max loss is the premium already charged at entry, so a late exit cannot breach a budgeted loss. **Slippage, not ruin.** Ceiling cut to 600s, and an exit pass now runs immediately after every entry pass. Venue-side option stops REFUSED for the original reason: not leg-level stops,
  stopping one leg of a spread can leave a naked short option. Structure-level
  only, and it depends on loop liveness because a software-side stop is only as
  alive as the loop.
- **The competition account starts CLEAN.** The rehearsal book carries 72.9% of
  equity in true max loss. **Live observation motivating a thesis-cluster cap:**
  on 26 Aug the dev book held AMD, AVGO, NVDA, QQQ, META and TSLA at once — one
  causal cluster, on the eve of that cluster's event. Bounded contractual loss
  per structure does not make that a diversified book.
- **Refusal decomposition: DONE, and it answered a question we had been asking
  wrong.** `48 refused` never distinguished a barren alpha layer from an
  over-strict risk layer. Measured on live forecasts:
  **`already_held=32  evidence=12  execution=4  risk=0`** — **neither. The
  system is SATURATED.** Two thirds of refusals are "we already own it", and
  admission never got to speak. The loop is spending forecast budget on names it
  cannot act on. Direct evidence for a thesis-cluster cap and for starting the
  competition account clean.
