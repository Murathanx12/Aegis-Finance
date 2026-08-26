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
