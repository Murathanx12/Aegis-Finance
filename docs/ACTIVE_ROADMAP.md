# AEGIS ACTIVE ROADMAP

Status: ACTIVE
Window: Saturday 29 August 2026 -> Monday 31 August 2026 pre-open
Builder handoff: Opus
Strategic authority: `docs/AEGIS_STRATEGIC_INVARIANTS.md` and `docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`

This is the single active weekend execution plan. It does not replace the strategic invariants. Old ROADMAP/HANDOFF files are evidence/history, not competing authority.

## 0. Mission for this weekend

Improve expected trading P&L by fixing the failures exposed on hackathon day one and connecting AEGIS's existing research brain to the live trading machine.

Do not optimize for elegance or publication. Do not optimize to Friday's P&L alone. Preserve point-in-time evidence, causal attribution, and the original decision/version for every existing trade.

The target system is:

WORLD SENSORS -> POINT-IN-TIME EVENT STORE -> ENTITY/CAUSAL GRAPH -> MULTIPLE OPPORTUNITY GENERATORS -> CONDITIONAL FORECASTS -> EXPRESSION -> PORTFOLIO/RISK -> EXECUTION -> PREDICTION LEDGER -> AUTOPSY/OPPORTUNITY RECALL -> LEARNING

No universal stock rule. Most alpha should be conditional on regime x event type x industry x size/liquidity x company state x causal exposure.

## 1. Friday 28 August: measured fleet result

End-of-day equity from Railway logs, each starting from $100,000:

- hack1: about $99,251 (-0.75%)
- hack2: about $99,239 (-0.76%)
- hack3: about $90,949 (-9.05%)
- hack4: about $99,108 (-0.89%)
- hack5: about $91,414 (-8.59%)
- hack6: about $90,718 (-9.28%)

Interpretation: the aggressive theme/convexity books failed together while the safer/measured books stayed around flat-to-minus-one-percent. This is strong evidence of structure/authority/concentration failure, not merely random single-name noise.

Specific receipts:

- hack3/hack6 held many names that behaved as one economic bet. Correlated theme exposure dominated account risk.
- hack6 still had at least one functioning measured exit: DKNG closed around +2.58% after reaching its +2.5% measured target. Do not conclude every lane failed.
- hack5 held short-dated Sep-4 long calls in QS, SMR, PLUG, BE and NVDA. Account drawdown continued after the daily loss latch because the latch blocks new entries but does not neutralize existing option risk.
- hack3 had a protective-stop submission on BE refused by Alpaca for a potential wash-trade/opposite-order conflict before a replacement stop was placed. Execution/order-state reconciliation must be audited.
- five of six overnight counterfactual workers are currently failing because ordinary equity symbols such as BBW/AG can reach an option-quote path that expects OCC option symbols. This breaks learning/what-if marking even when live order execution remains alive.

Root-cause hierarchy to test, not assume:

1. portfolio authority/concentration: many tickers represented one hidden macro/theme factor;
2. weak/unvalidated candidate generation in the theme basket;
3. expression mismatch: short-dated long options added theta/IV/spread risk to already-high-beta directional bets;
4. entry timing / opening spread / event timing;
5. execution-state defects around stops/opposite orders;
6. forecast error by individual names;
7. ordinary noise.

The recent 8% stop / no-same-session-reentry / 36% basket-authority fix is a useful guard, but it is not the final cure. Twelve correlated names must count as one bet when their causal/factor exposure is the same.

## 2. P0 — Saturday: repair observability before adding intelligence

These are blockers because we cannot learn correctly while they are broken.

### P0.1 Counterfactual type routing

Fix equity-vs-option instrument typing before any quote request. Add tests proving common stocks, ETFs, OCC options and malformed symbols route correctly. Counterfactual jobs must fail per instrument, not abort the full batch.

Acceptance:
- all six workers complete one closed-market counterfactual cycle;
- no equity ticker is sent to the options endpoint;
- receipt records marked/refused/missing separately;
- missing quote cannot silently become zero P&L.

### P0.2 Order/stop reconciliation

Audit existing-order conflict behavior. One canonical protective order per position; cancel/replace atomically where Alpaca requires it. Distinguish a broker refusal from a strategy refusal.

Acceptance:
- synthetic tests for opposite-side existing order, partial fill, resized position, stale stop and restart recovery;
- no unprotected position because a replacement stop collided with an old order.

### P0.3 Portfolio causal concentration

Add a portfolio-level exposure report before touching sizing rules again. Cluster positions by sector, theme, factor beta, causal driver and catalyst. Names sharing the same dominant driver contribute to one risk bucket.

Required outputs per book:
- gross/net exposure;
- single-name stress;
- theme/causal stress;
- factor beta estimates;
- option premium-at-risk and Greeks where available;
- liquidity/spread penalty;
- largest three correlated loss scenarios.

Do not promote a hard new concentration threshold until replay/backtest shows the trade-off.

## 3. P1 — Saturday/Sunday: Global Event Mesh v0

The current premarket digest is still a preselected universe: window printers + theme names + indexes. Replace the upstream assumption, not merely the ranking formula.

### 3.1 Source families

Build collectors/adapters with point-in-time timestamps and provenance for:

Corporate primary:
- SEC 8-K, 10-Q, 10-K, S-1, 13D/G, Form 4, 13F;
- company investor-relations releases/calendars;
- earnings releases, calls and guidance;
- investor days, conferences, product showcases, launch dates;
- M&A announcement, vote, regulatory and expected-close milestones.

Health/science:
- FDA approvals, CRLs, clinical holds, AdComs and public calendars;
- sponsor-reported PDUFA dates from filings/IR;
- ClinicalTrials.gov expected primary-completion/readout windows;
- trial publications, patents and licensing deals.

Government/policy:
- Federal Register;
- US procurement/contract awards and budgets;
- tariffs/export controls/subsidies/industrial policy;
- defense budgets/procurement;
- relevant Asian regulators/exchanges/government releases.

Physical economy:
- semiconductors/memory/packaging capacity;
- grid/power/data-center construction;
- commodities/rare earths/metals;
- freight/customs/supply-chain disruptions;
- batteries, robotics/actuators, defense manufacturing.

Market/positioning:
- price/volume/volatility;
- options OI/volume/skew with feed-latency label;
- ETF/fund flows;
- short interest/borrow where available;
- analyst rating/target/estimate revisions.

News/attention:
- Alpaca/Benzinga;
- Reuters and other licensed/search-accessible news;
- local-language Asia sources;
- social/news-discussion sources as attention/hypothesis signals, never as unverified truth.

### 3.2 Cost architecture

Do not spend frontier/DeepSeek tokens to summarize every transcript/article.

Tier A deterministic/local:
- fetch, parse, deduplicate, entity-link, timestamp, classify event type, extract numbers/dates, compute deltas.

Tier B local model/Hugging Face on demand:
- batch classification, embeddings, clustering, novelty and relevance scoring;
- start only for a job and unload afterward; do not leave the model resident in RAM.

Tier C DeepSeek/Featherless/NVIDIA:
- ambiguous event interpretation;
- causal-chain synthesis;
- multilingual reading where local extraction is weak;
- contradiction/red-team pass;
- structured forecast hypothesis.

Tier D frontier/Fable/Optimus:
- cross-source adjudication, research design, failure analysis and promotion decisions.

Every provider call must have `why`, expected decision impact and measured spend.

Note: voice transcription may have called Featherless “Federalist”; use the existing configured provider unless a genuinely separate API/key exists.

### 3.3 EventObservation schema

Minimum fields:
`event_id, observed_at, effective_at, source, source_type, entity_ids, event_type, raw_ref, extracted_facts, numbers, dates, novelty, source_independence_root, confidence, language, point_in_time_safe`.

No backtest may use a fact before `observed_at`.

## 4. P2 — Sunday: entity graph + multiple candidate generators

A single ranking formula must not decide which companies exist.

Graph nodes: company, security, product, technology, person, fund, government, country, commodity, facility, supplier, customer, regulation, clinical asset, event, macro variable.

Core edges: supplier/customer, competitor, ownership, licensing, acquisition, regulatory exposure, subsidy/procurement, geography, commodity dependency, technology dependency, capacity/bottleneck, facility, employment/management, factor exposure.

Run independent generators, then union/deduplicate:

1. Event/catalyst generator — new filings, earnings, approvals, trial news, product events, M&A.
2. Causal-propagation generator — event happens to A; suppliers/customers/competitors/bottlenecks B/C/D receive second-order economics.
3. Future-needs/bottleneck generator — what the world will need more of, who controls scarce capacity, and who can capture value.
4. Analyst-dislocation generator — revisions, dispersion and large implied upside, normalized by sector/size/coverage.
5. Under-covered novelty generator — unusual independent information arrival relative to a stock's own normal attention and peer cohort.
6. Ownership/flow generator — Form 4, 13D/G, 13F context, ETF/flow/short/options evidence. Treat delayed filings according to their actual latency.
7. Cross-country lead generator — Asia/Europe events with mapped US exposures before New York opens.
8. Contradiction generator — price moves one way while fundamental/causal evidence moves the other.
9. Human-thesis generator — Murat/LLM intuition becomes a typed hypothesis with alternatives and falsifier, never an unlogged override.

### Murat-selection lane

Reconstruct explicitly as a testable generator:

future technological/social need -> exposed company -> revenue/earnings/capacity inflection potential -> sparse/under-covered expectation set -> analyst estimate/target revisions or high implied upside -> price dislocation/drawdown -> catalyst path -> asymmetric payoff.

Do not use “small” or “down a lot” as bonuses by themselves. Test whether the decline is transitory versus thesis impairment. Prefer analyst revisions/estimate changes over static target levels.

## 5. P3 — Sunday: coverage normalization and expectation gap

Information scarcity is contextual.

For each company estimate:
- current independent-source count vs its own 1y baseline;
- analyst count and revision activity;
- peer/sector/market-cap expected coverage;
- novelty residual;
- source independence;
- dispersion/uncertainty;
- price move already realized;
- causal-hop uncertainty;
- liquidity.

Example: six independent reports for a name normally receiving two can be more informative than NVDA's 300th article.

Do not award a direct low-coverage score until retrospective testing demonstrates incremental selection lift.

## 6. P4 — Sunday: catalyst calendar

Build one point-in-time event calendar with confidence/source receipts for the next day, week, month, quarter and year.

Include:
- earnings and guidance;
- FDA/PDUFA/AdCom/clinical-readout windows;
- product/showcase/investor-day/conference dates;
- M&A votes/regulatory decisions/close windows;
- macro releases/Fed/central banks;
- elections/geopolitical deadlines where economically relevant;
- tariff/export-control effective dates;
- government budgets/procurement/contract milestones;
- debt/refinancing/lock-up/secondary-offering events where material.

A scraped calendar is a lead, not truth. Promote dates only after source verification from regulator/company/exchange when possible.

## 7. P5 — Sunday/Monday: prediction ledger v2

Before forecasts can train a neural network, predictions need stable labels.

For every generated candidate record before the outcome:
- symbol/entity;
- observed event(s);
- causal chain;
- alternatives;
- direction;
- expected magnitude distribution;
- horizons: 1d, 5d, 20d, 63d, 126d, 252d where data permits;
- probability/confidence;
- probability already priced;
- expression recommendation or ABSTAIN;
- falsifier;
- model/provider/version;
- decision hash;
- risk/correlation bucket.

Score later on calibration, magnitude error, ranking lift and economic P&L after costs. Preserve forecasts that were wrong. Never rewrite history after outcome.

Add the second question to every autopsy: **Which of the day's largest economically tradable movers did AEGIS never generate, and why?**

Track opportunity recall by event type/size/sector/market cap. Friday examples already show that ranking accuracy alone is insufficient when the generator never sees a mover.

## 8. P6 — Backtest factory before neural-network promotion

Run multiple replay families; no single omnibus backtest.

Required test families:

- event-type conditional replay;
- sector/industry conditional replay;
- size/liquidity/coverage cohorts;
- analyst-revision x drawdown interaction;
- causal-propagation hop count;
- catalyst run-up / already-priced behavior;
- Asia->US lead mapping;
- ownership/flow features;
- selection vs sizing decomposition;
- stock vs option expression;
- portfolio causal-concentration limits;
- transaction-cost/spread/slippage stress;
- crisis/regime robustness;
- matched losers and negative controls.

Use point-in-time data, purged temporal splits and embargo around overlapping labels. Separate exploration results from capital candidates.

A strategy can adapt when evidence warrants; the decision contract attached to an already-entered position stays immutable.

## 9. P7 — Neural-network progression

Do not start with a giant end-to-end network. The weekend goal is a trainable event panel and a benchmark.

Stage 0: deterministic features + simple calibrated baseline.
Stage 1: logistic/linear + gradient-boosted tree baselines for each horizon/event family.
Stage 2: mixture-of-experts / conditional model with gates for event type, regime, industry, size/liquidity and company state.
Stage 3: temporal heterogeneous graph model using event/entity/causal edges.
Stage 4: sequence model over event histories only if it beats simpler baselines out of time.
Stage 5: portfolio policy/RL only after prediction calibration and cost-aware simulator are trustworthy.

Promotion requirement: out-of-time improvement in calibration/ranking/economic utility after costs, not training loss. Keep a simple baseline permanently as a falsification ruler.

## 10. P8 — options and expression rules to investigate

Friday hack5 is a warning against using short-dated calls as a generic amplifier.

Research separately:
- shares vs calls vs call spreads vs abstain;
- DTE aligned with forecast horizon/catalyst;
- max premium-at-risk;
- bid/ask width and open-interest/liquidity gates;
- IV percentile / event-volatility regime;
- delta/gamma/theta/vega concentration;
- same-factor option basket stress;
- exit policy and overnight gap risk.

Current options data/feed latency must be carried as a feature/constraint. Do not claim reactive options alpha from delayed/indicative quotes.

## 11. P9 — Monday pre-open integration target

Deadline target: core implementation/tests complete before the US premarket decision window on Monday 31 August; do not make the first live test the 09:30 ET open.

Minimum Monday-ready deliverables:

A. observability repaired: counterfactual routing + stop reconciliation tested;
B. portfolio causal-concentration report available on all six books;
C. Global Event Mesh v0 can ingest broad source families with PIT receipts;
D. at least four independent candidate generators operate on a much broader tradable universe than the current ~130-name digest;
E. Asia-first pass maps Asian events into US causal exposures;
F. catalyst calendar has source/confidence fields;
G. sealed pre-open prediction book records all candidate forecasts before outcomes;
H. discovery autopsy measures missed movers;
I. model spending report shows local/deterministic first, paid LLM only on high-value ambiguity;
J. baseline conditional model/backtest report exists before any neural model is given authority.

If a component misses the deadline, fail closed for that component and keep the proven/measured lanes; do not substitute an untested guess merely because Monday arrived.

## 12. Research run: current high-information themes to seed, not hard-code

Weekend external research on 29 August identified several live chains worth feeding to the Event Mesh and backtesting rather than directly trading:

- AI infrastructure demand remains strong, while memory/component supply is constrained. This makes memory, HBM, packaging, power and cooling second-order candidates rather than only NVDA/AVGO.
- China's CXMT is growing rapidly while facing US national-security restrictions/litigation: DRAM supply/competition/geopolitical policy is one causal chain.
- semiconductor tariff/reshoring policy may affect chips and products containing chips; policy is not yet final, so encode as probabilistic event, not fact.
- US polysilicon trade protection beginning in December creates a solar/semiconductor-materials chain with domestic producers/users and pre-effective-date import behavior.
- GLP-1 label expansion and new approvals continue to broaden the metabolic/cardiovascular market; map drug success to manufacturers, delivery, supply capacity and competitors.
- mRNA personalized cancer vaccines achieved a major late-stage milestone, creating a platform/supply/biomarker/manufacturing chain beyond the two headline partners.
- China is explicitly supporting global biotech licensing/M&A, increasing cross-border asset/licensing discovery value.
- US/Asian defense, drones, autonomy and solid-rocket/hypersonic procurement remain future-demand chains requiring supplier/bottleneck mapping.

These are research seeds only. The system must discover equivalent chains independently and score whether they are already priced.

## 13. Opus build order

Do not parallelize everything at once. Recommended dependency order:

1. P0 counterfactual + order-state tests.
2. Portfolio causal-concentration report.
3. EventObservation schema + source registry.
4. Primary-source catalyst calendar adapters.
5. Broad universe/entity master.
6. Event/analyst/undercoverage/causal candidate generators.
7. Prediction ledger v2 and sealed pre-open book.
8. Discovery-autopsy opportunity recall.
9. Backtest factory + baselines.
10. Local-model lifecycle and batch inference.
11. Conditional mixture-of-experts baseline.
12. Temporal graph NN only after data panel passes PIT/leakage checks.
13. Integrate validated outputs into executor behind explicit authority gates.

For every implementation PR: state the hypothesis, changed decision surface, tests, rollback, data provenance, and whether it is RESEARCH, SHADOW, PAPER-CAPITAL-CANDIDATE or LIVE-PAPER authority.

## 14. What not to do

- Do not scan only S&P 500 or only famous tickers.
- Do not spend LLM tokens summarizing every article/transcript.
- Do not turn analyst targets into truth.
- Do not give small caps an automatic alpha bonus.
- Do not confuse twelve correlated tickers with diversification.
- Do not use a wider stop as the sole fix for bad concentration.
- Do not train a neural network on post-outcome/leaky text.
- Do not let social posts become factual evidence without a primary/independent receipt.
- Do not erase Friday by resetting accounts just because the P&L is ugly; the day is valuable causal evidence.
- Do not freeze strategy evolution; freeze the historical decision contract for attribution.
- Do not create another strategic North Star in the executor repo. Aegis-Finance is the strategic brain; the terminal is the execution brain.

## 15. Monday decision packet

Before giving any new system more authority, produce one short packet containing:

1. six-account Friday attribution;
2. repaired-observability receipts;
3. top missed opportunities and why they were missed;
4. top Monday candidates from each independent generator;
5. causal chains and alternative explanations;
6. upcoming catalyst calendar (day/week/month);
7. model calibration/backtest table;
8. portfolio correlation/causal stress by account;
9. proposed authority changes with counterfactual expected benefit;
10. exact components that remain shadow-only.

That packet, not narrative confidence, decides Monday's authority.