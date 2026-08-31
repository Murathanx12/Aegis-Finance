# AEGIS CONTINUITY CHECKPOINT — 2026-08-31 — V1 DECISION ENGINE

**Purpose:** canonical continuity record after two concurrent Claude sessions touched the same program and Murat accidentally closed the main Fable conversation. Chat history is not the authority. This document + the active Tier-0/Tier-1 docs + code/receipts are.

**Active strategic authority remains:**
- `AEGIS_STRATEGIC_INVARIANTS.md`
- `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`
- `AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md`
- `ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`
- `SOURCE_REGISTRY_2026-08-31_FREE_NEWS_AND_ARCHIVES.md`

This file is a checkpoint/addendum, not a replacement for those documents.

---

## 1. THE GOAL — DO NOT LET SESSION LOSS SHRINK IT

AEGIS is a profit-first, self-improving investment decision organism. The hackathon is a live experiment, not the objective.

North star:

> **maximize expected compound P&L / terminal wealth subject to survival and data-integrity constraints.**

The intended architecture is:

`WORLD SENSORS -> EVIDENCE -> CANONICAL EVENTS -> CAUSAL GRAPH -> COMPANY STATE -> MARKET EXPECTATIONS -> DIVERGENCE -> DECISION -> PORTFOLIO/EXPRESSION -> ADMISSION -> BROKER/FILL -> OUTCOME -> MEMORY/LEARNING`

It must eventually:
1. observe broad economic, political, technological, regulatory, social and company-specific change;
2. discover opportunities across the market, especially under-covered small/mid names, rather than start from a fixed mega-cap list;
3. convert text/world information into structured numerical beliefs;
4. preserve causal chains (demand -> bottleneck -> supplier/customer/competitor -> company impact), not only ticker sentiment;
5. maintain append-only multi-horizon CompanyState vintages;
6. make an explicit numerical decision for every sufficiently observed candidate rather than hide behind `REJECT` / `I DON'T KNOW`;
7. compare candidates and say why A is preferred to B;
8. construct multiple portfolio personalities from the same opportunity set;
9. seal beliefs before outcomes;
10. learn from chosen, rejected and missed opportunities, including real paper fills and execution failures;
11. later train neural/graph/sequence models on AEGIS's own accumulated decision history.

Murat's operating rule is binding:

> **make a decision -> see the result -> diagnose which component was right/wrong -> update -> repeat.**

Do not mutate the whole strategy because one stock won or lost. Diagnose sensor, representation, forecast, ranking, portfolio, expression, execution and risk separately.

---

## 2. BOUNDARIES — FOUR DIFFERENT THINGS MUST NOT BE CALLED ONE 'LIMIT'

### HARD: survival
Gross/account loss breakers, broker reconciliation, opening-range controls, defined-risk options, per-position/premium ceilings. These bound how much a wrong belief can cost.

### HARD: data integrity
Point-in-time timestamps, stale-data refusal, corporate-action/share-basis sanity, source failure vs absence, units/deduplication and provenance. Bad data must not become confidence.

### EXECUTION AUTHORITY
Liquidity/participation/market-impact constraints determine **how much may be traded**, not whether AEGIS is allowed to know/reason about the company.

### STATISTICAL PRIORS / EXPERIMENTAL PORTFOLIO RULES
Analyst-upside bands, coverage bands, top-k, sector caps, past-winner exclusion, catalyst requirements, max-downside personality settings. These are measured priors/experimental parameters, not universal laws unless evidence supports a case-level hard rule.

Expected edge, evidence quality/confidence and capital authority remain separate fields.

---

## 3. WHAT LANDED OVER THE LAST ~3 DAYS

### A. Exact tracker portfolio artery — BUILT
The former orphan is now connected:

`tracker vintage -> portfolio build -> sealed exact holdings/weights -> tracker_portfolio brain -> run_pass universe -> sealed weight ceiling -> admission -> broker`

Key properties now tested:
- exact sealed holdings rather than `murat_rule` claimers;
- selector never imports/re-ranks `alpha.tracker` at order time;
- sealed names are injected into `run_pass` when `tracker_portfolio` is enabled;
- sealed stock notional is a reduce-only ceiling, not decorative metadata;
- option structures refuse the stock-notional interpretation rather than equating share notional to premium risk;
- missing/pre-artery/unreadable seal refuses rather than silently substituting another mandate.

Published 2026-08-31 seal: `e6f967a62863131c`.
Books: hack3 10/10, hack4 5/5, hack6 15/15.

### B. Hack4 declared mandate — BUILT, LIVE RUNTIME VERIFICATION STILL REQUIRED
Repo mandate now says:
- `tracker_portfolio`
- profit-max personality
- shares only
- old post-event drift retained as shadow comparison.

Hack4 sealed holdings on 2026-08-31:
`RZLV, NB, LAES, ABAT, ALMU`, 10% target notional each, gross 50%.

Risk must always report BOTH:
- stop-based scenario: about **-3.0%** if stops fill as intended;
- modelled joint 5%-downside gap case: about **-18.4%** if all five realize their own modelled 5% downside.

Profit-max deliberately has no `max_downside` unlike hack3/hack6; that is a mandate property, not an unnoticed artifact.

### C. News discovery became adaptive — BUILT
The digest no longer starts from only a fixed famous-stock list. A measured run found 111 newsmaking names and combined them with tracker candidates (~499-name working universe). Raw article count is not the rank; attention is normalized against the name's own baseline/source diversity so fame does not equal opportunity.

WBUY was ranked first by the digest on 2026-08-31 and received a real one-session bullish forecast (+10%, 70% already priced, falsifier attached). The stock subsequently moved about 20% that day.

### D. Discovery -> runner reachability gap — BUILT, NOT YET DEFAULT-LIVE
`inject_news_universe` / proof 7 now lets a valid premarket digest feed names into the universe the placing runner can actually ask about. Missing/stale/undateable digest refuses instead of turning 'never ran' into 'found nothing'.

**Important:** `--news-universe` remains OFF by default and, as of this checkpoint, no production loop invocation is proven to enable it. Therefore the connection exists but is not yet a production claim.

### E. Observation vs execution split — CODE BUILT, WIDE OBSERVATION FILE NOT YET REBUILT
The old `$3m/day` constant answered two incompatible questions: `may we observe this?` and `may we execute this?`.

Now:
- `MIN_OBSERVE_DOLLAR_VOLUME ~ $20k/day`
- `MIN_EXECUTE_DOLLAR_VOLUME = $3m/day` remains the existing execution threshold
- `execution_authority()` returns an explicit tier/ceiling instead of deleting unbuyable names.

Example from the implementation: a ~$25k/day name such as WBUY becomes `OBSERVE_ONLY` with tiny/zero capital authority rather than disappearing from research.

**Blocker:** the stored universe was still built under the old execute scope. `build(scope="observe")` against the venue has not yet been completed/verified. Until it is, the wider observation design is structure without the wider dataset.

### F. CompanyState — V1 FOUNDATION BUILT
Append-only daily CompanyState exists and is wired to tracker finalization. It joins existing tracker/news/EDGAR/seal facts rather than re-fetching copies.

Properties:
- absence remains `None`, never fake zero;
- vintages append/rerun beside prior files rather than overwrite;
- `observed_at` and `written_at` are separate;
- horizon states are explicit; missing horizons stay missing rather than copying one forecast across clocks.

EDGAR counting was corrected to read the underlying observation corpus rather than a lossy overwritten summary; coverage reached ~3,054/3,059 tracker names in the corrected vintage.

Still missing for v1: broad observe-scope names, EventCluster/causal fields, full multi-horizon forecasts, ownership/insider/politician fields, fills/outcome writeback.

### G. EDGAR / primary-source coverage — STRONG START
Backfill produced roughly 150k+ filings across ~3,056 names. This directly reduces famous-company media bias: primary filings exist even when a name has little/no mainstream coverage.

### H. Analyst data — FAR RICHER THAN THE LIVE TRACKER
We already own via WRDS/IBES `ptgdetu` approximately:
- 4.66m individual price targets, 2013-2026;
- 37k+ tickers;
- 1,348 brokers;
- 33k+ analysts;
- stable analyst IDs (`amaskcd`) and PIT announcement dates.

Therefore analyst provenance/skill/revision research should be built from entitled data before buying Koyfin/InvestingPro merely to recreate analyst history. External fair-value products can still be benchmark models, not truth.

### I. >400% target-band root-cause test — IMPORTANT INVERSION
The hypothesis that the >400% band's poor performance was mainly stale/share-basis contamination was **refuted** when decontaminated.

Measured 2013-2024:
- CLEAN >=400% cell: about **-41.4%/yr, t -8.94**;
- dirty-any >=400%: about **-17.0%/yr**;
- the data garbage was diluting the damage, not creating it.

But Murat's concern about lost huge winners is also real **one band lower**:
- +200-400% upside in cheap/crashed/thin cells produced very large positive historical returns in the tested cells;
- the 4.0 bar already admits those; the execution/observation split was the larger practical exclusion.

Case-level nuance:
- clean >=400% gets a strong adverse prior;
- split-prior-year upside becomes unreadable;
- a WBUY-shaped sub-$2 cell was statistically uninformative, so the prior should be silent rather than falsely negative.

Do not change the bar merely because one winner exists; condition it on root cause and keep measuring.

### J. Liquidity migration study — FEATURE, NOT STANDALONE DIRECTION
Changing liquidity band widened outcome dispersion. Climbers had fatter right tails but also worse downside; after controls, direction was weak. Use band/band-change/spread/participation as CompanyState and options-volatility features, not 'liquidity rose -> buy'.

### K. 13F / holder-change lane — STRONG RESEARCH RESULT, NOT 'COPY FUNDS'
PIT trap corrected: vendor `fdate` equalled report date, so use `rdate + 45d` as an explicit optimistic public-availability bound rather than granting 45 days of hindsight.

Measured 2013-2024 result inverted the original intuition:
- institutions selling >10% subsequently outperformed buying >10% in the tested design;
- survives controls for institutional popularity and trailing return;
- survives measured quoted-spread costs in every measured liquidity band;
- strongest practical cell reported in $10m-$50m/day where quoted cost is small.

Interpretation: 13F is stale structure/crowding data, not a live catalyst and not proof that institutional selling causally creates gains.

Still needed: ownership % of float, top-1/top-5/top-10 concentration, manager-level skill, new entrants/full exits, crowding and integration into CompanyState.

### L. Source/data failures are increasingly explicit
Finnhub 503 storm left 75 observed rows with `rec_status=error` rather than deleting them. New seal provenance will count data gaps so absent vs observed-but-unreadable is distinguishable.

---

## 4. WHAT THE TWO CONCURRENT SESSIONS DID — COLLISION RECONCILIATION

They did not materially overwrite each other's core work.

**Opus lane:**
- WBUY discovery->runner diagnosis;
- proof 7 news-universe injection;
- observation/execution split;
- analyst-provenance entitlement finding;
- +400% root-cause/decontamination study;
- validation pass on merged tree.

**Fable lane:**
- repaired/published 2026-08-31 tracker seal;
- hack4 fleet mandate update;
- explicit -3% stop / ~-18.4% model-gap risk reporting;
- data-gap provenance;
- Railway deploy/flip lane.

Coordination instruction between sessions explicitly gave Fable Railway/seal authority and Opus stayed off it.

Merged suite after both lanes: **62 suites / 2,726 checks green** at the latest reported validation point.

### Current Railway caveat at checkpoint
A newer hack4 deployment has succeeded. However, do not call the new tracker mandate operationally verified until a runtime log/diagnostic explicitly shows:
- `AAT_ACCOUNT_ROLE=hack4`;
- `tracker_portfolio` is the executing brain;
- shares-only structure set;
- the 2026-08-31 sealed content hash loaded;
- the five sealed names visible/reachable;
- dry/first entry pass applies the sealed notional ceilings.

A deployment success alone is not the same as a strategy activation success.

---

## 5. V1 DECISION ENGINE — DEFINITION OF DONE

V1 is NOT 'all long-term AEGIS research completed'. V1 means one end-to-end decision organism can repeatedly observe, decide, rank, execute on paper and learn from outcomes.

For every serious observed company/candidate, V1 should be able to produce a **DecisionCard** like:

- symbol / as-of / horizon;
- `p_up`;
- expected return;
- bad-case/downside distribution;
- evidence confidence/quality;
- probability/already-priced estimate;
- bull/base/bear thesis with falsifiers;
- internal fair-value scenarios appropriate to the sector;
- external analyst/vendor forecasts, each labelled by evidence class/provenance/freshness;
- key analyst revisions/disagreement and analyst/firm historical skill when available;
- causal drivers and exposure;
- ownership/insider/politician/government-money context where known;
- liquidity/expected trading cost/participation;
- `execution_authority` independent of expected edge;
- rank versus alternatives and explicit `prefer A over B because ...`;
- portfolio role/target ceiling if selected;
- sealed model/source/version hashes.

Then V1 must:
1. rank the same observed opportunity set under multiple portfolio objectives;
2. seal decisions before outcome;
3. send at least one portfolio through the exact paper path;
4. record orders/fills/refusals/slippage;
5. write 1/5/21/63/126/252 outcome checkpoints back against the original decision ID;
6. run daily discovery/autopsy/opportunity-recall so missed winners also become labelled data.

---

## 6. COMPLETION ESTIMATE — AS OF THIS CHECKPOINT

These percentages are engineering estimates against explicit scopes, not statistical confidence intervals.

### Last ~3-day tactical build: **~75% complete**
Done: artery, exact seal, portfolio identities, adaptive digest, news reachability code, observation/execution architecture, CompanyState foundation, EDGAR breadth, 13F experiment, liquidity experiment, target-band root-cause test, hack4 repo mandate.

Remaining: prove hack4 live runtime, rebuild wide observation universe, enable/grade live news->decision path, close fill->state loop, stabilize provider degradation/night barrier, begin source-mesh backfills.

### V1 decision engine: **~60% complete**
Approximate component status:
- broad sensing / observation: 55%
- discovery reachability: 75% code / lower in live production
- CompanyState: 55%
- numerical per-stock DecisionCard / fair value / multi-horizon reasoning: 35%
- portfolio construction + sealing: 90%
- paper execution infrastructure: 85%
- live new-mandate verification: 60%
- outcome/writeback/self-learning loop: 40%
- continuous experiment factory: 60%
- source/archive expansion: 35%

The biggest V1 deficit is no longer infrastructure. It is **the explicit per-company decision layer plus outcome writeback**.

### Full long-term AEGIS vision: **~30-35% complete**
The persistent causal world graph, mature EventCluster, global/Asia sensor mesh, robust sector-specific valuation, full social/political/ownership graph, long historical text archive, model ensemble, temporal/graph neural models and learned allocation policy are not complete.

---

## 7. NEXT QUEUE — ORDER MATTERS

### P0 — verify the one live artery
1. verify hack4's actual Railway runtime mandate, seal hash, five holdings, shares-only structure and sealed-notional clamp;
2. if runtime still carries obsolete window/candidate args, remove them from the declared mandate instead of tolerating configuration drift;
3. preserve hack1/hack2 as controls.

### P1 — observation must actually become broad
4. run/verify `build(scope="observe")` against the venue;
5. measure count gained below $3m/day and source/price coverage by liquidity band;
6. ensure low-liquidity names receive CompanyState + DecisionCards even if `execution_authority=OBSERVE_ONLY/zero`;
7. WBUY becomes the canonical replay/exam: could AEGIS have seen it earlier, what did it know, what would it decide after the move, and how is that graded?

### P2 — V1 DecisionCard
8. build the explicit numerical DecisionCard contract;
9. populate bull/base/bear, multi-horizon probabilities/returns/downside/confidence, already-priced, falsifiers and comparison/ranking;
10. build sector-specific internal fair-value scenario models;
11. integrate IBES target provenance, revisions, analyst/firm skill and disagreement;
12. external fair-value/vendor models are benchmark features, not blended truth.

### P3 — close the learning loop
13. fills/orders/refusals/slippage -> DecisionCard/CompanyState IDs;
14. outcome checkpoints 1/5/21/63/126/252;
15. decision-vs-outcome error attribution (sensor / entity / forecast / rank / portfolio / expression / execution);
16. replacement-edge and regret/opportunity-recall.

### P4 — world/event state
17. build EventCluster canonicalization and dedupe;
18. add causal drivers/exposures/needs/bottlenecks;
19. integrate EDGAR + GDELT + primary government/FDA/contract sources;
20. begin SC454k first, then FNSPID/Common Crawl bounded historical probes.

### P5 — ownership / public actors
21. 13F level + concentration + manager skill fields;
22. SEC Form 4 live insider lane;
23. STOCK Act politician disclosures with transaction_date / filing_date / first_seen_at separated;
24. measure politician/manager-specific skill conditional on sector/committee/context; never 'copy famous person' by assumption.

### P6 — experiment factory
25. T14 theme-first replay;
26. opportunity recall / missed-winner taxonomy;
27. matched losers;
28. analyst revision velocity and coverage initiation;
29. compression raw-vs-EventCluster-vs-causal summary;
30. Asia lead-lag;
31. portfolio-expression and hold/reunderwrite/replacement tournaments;
32. model-disagreement and calibration experiments.

### P7 — neural models only after the labels exist
Start with tabular GBT/calibration on CompanyState, then mixture-of-experts by mechanism/horizon, temporal/graph models, sequence models, and only later RL allocation when the outcome/action dataset is large enough. NN before the decision/outcome loop is complete mostly learns vendor history rather than AEGIS's decisions.

---

## 8. COLLISION PROTOCOL FROM NOW ON

Before either Fable/Opus edits a shared execution surface:
1. pull latest both repos;
2. state lane ownership in the handoff;
3. one owner at a time for Railway/seal/fleet/order-path mutations;
4. research/data experiments may run concurrently when they do not mutate the same artifacts;
5. after merge, re-run the full suite on the merged tree, not each branch in isolation;
6. a claim is not `DONE` until entry-point reachability and runtime/receipt evidence exist where relevant;
7. no session-local memory is strategic authority — write result/decision/queue changes into the repo.

This document exists specifically so closing a chat session does not erase AEGIS's intent or state.
