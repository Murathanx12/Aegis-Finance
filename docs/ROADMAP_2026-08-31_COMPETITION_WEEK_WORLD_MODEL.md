# ROADMAP — 2026-08-31 → 2026-09-04 — WORLD MODEL, PORTFOLIO BRIDGE, CONTINUOUS LEARNING

**Status:** ACTIVE TIER 1. Replaces the weekend-to-Monday execution roadmap.

**Strategic authority:** `AEGIS_STRATEGIC_INVARIANTS.md`, `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`, and `AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md`.

**Objective:** maximize expected compound P&L subject to explicit survival constraints. The competition is a live research laboratory, not a reason to abandon the long-term architecture.

---

## 0. What Murat is actually trying to build

AEGIS is not a news-sentiment bot and not a stock screener with an LLM attached. It is a continuously updated world model that:

1. observes broad economic, political, technological, regulatory, social and company-specific change;
2. compresses repeated reporting into canonical facts/events rather than counting copies;
3. maps those changes through demand, supply, bottlenecks, competitors, customers and second-order beneficiaries;
4. turns qualitative evidence into explicit numeric beliefs for several horizons;
5. maintains an adaptive whole-market company state/watchlist;
6. constructs multiple portfolios from the same opportunity set under different objectives;
7. seals what it believed before outcomes are known;
8. grades decisions, missed opportunities, execution and portfolio expression separately;
9. stores every vintage so future models/NNs learn from AEGIS's own history rather than only vendor history.

Murat's recurring problem-solving rule is part of the design: when a measurement is contaminated by memory, representation or coverage, change the representation rather than abandon the underlying question. The fantasy transposition is the canonical example.

---

## 1. Validated state entering Monday 31 Aug

### What is real and useful

- PIT corpus and forward calendar exist; collection has guards for caps, missing timestamps, rate limits, truncation, dedupe and provider failure.
- Whole-market analyst tracker exists and keeps daily vintages instead of overwriting history.
- Analyst-count scale was repaired; thinly covered names now exist in the tracker.
- IBES + CRSP 2013–2024 shows analyst-upside information survives out of sample after eliminating stale/share-basis target artifacts. The >400% upside band is a data-quality failure mode, not a legitimate forecast tail.
- The prior blanket ban on past winners is refuted over the long horizon; keep it as an experimental arm, not global truth.
- Fantasy transposition T13 works as a blinding mechanism. The present sample is underpowered and LLM probability calibration is poor, but prose contains some ranking information relative to numbers-only in the tested balanced construction.
- Friday's large losses were first-order leverage/expression failures. Gross caps, opening-range rules, stop/re-entry changes and options-risk controls are survival controls and stay.

### What is NOT connected yet

The tracker portfolio personalities are not order-reachable. `alpha.tracker.build_portfolio()` is an offline analysis/print path. `murat_rule` reads prediction claims, not the exact hack3/hack4/hack6 portfolio holdings and weights. Therefore simply enabling `murat_rule` does **not** make the newly built portfolios live.

This is P0 before calling any tracker portfolio a trading strategy.

---

## 1b. ADDENDUM — measured after this roadmap was written (2026-08-31, same day)

Everything below was verified in code or against the live deploy, not asserted.
Where it contradicts a statement above, the measurement wins.

### RESULTS SCOREBOARD (CLAUDE.md requires this before any plan)

| | |
|---|---|
| Best historical net strategy vs market | analyst-upside basket capped at 4x: **+3.88%/yr, t 2.16** (IBES+CRSP 2013-24, 10bps/side) |
| Best forward paper strategy | **none.** No tracker book has ever placed an order |
| Independent selectors live | **0** of 3 built |
| Farm candidates tested / promoted | 15 / 0 |
| External execution drag | n/a — nothing executed |

**RESULT IMPROVEMENT over the weekend: NONE.** Two days improved an orphan.

### P0 IS BUILT (`aegis-alpha-terminal@26faa7b`) — §2 becomes *prove and finish*

The seal now carries `portfolios[book]` — exact holdings and weights inside
`content_sha256` — and `alpha/brains/tracker_portfolio.py` reads that block and
nothing else. It never imports `alpha.tracker`, so it **cannot** re-rank at order
time. Registered distinctly from `murat_rule`: enabling one does not enable the
other. Verified identical to the `--portfolios` print for all three books.
Three proofs (reachability / identity / mutation) in `tests_smoke_artery.py`.
**60 suites, 2551 checks, ALL PASS. Nothing is enabled; nothing was redeployed.**

Measured against §2's artifact spec, **11 of 15 fields are present**. Missing,
and the first task: `driver exposure summary` · `derived gross` ·
`worst_case bound` · `source commit / model / rule versions`.

### A THIRD LAYER, under the two named above

The **published** seed book was stale: `docs/seed/predictions/2026-08-30.json`
held **302 considered / 1 claim (MU)** while local reseals held **749 / 10**.
`--publish` was never run after the reseal. So enabling `murat_rule` would have
traded **one name** — not ten, and not hack4's five.

### A PUSH DOES NOT DEPLOY

`df31a7f` was committed **20:58 +08** on 30 Aug; the newest Railway deployment
was **12:44 +08 the same day — eight hours earlier**. It was pushed and never
deployed. `prediction_book --publish` already prints "git push, **then
redeploy**"; that line is load-bearing. Use `railway redeploy --from-source`.

### THE THIN-NAME BAND IS UNOBSERVED, NOT MERELY UNBOUGHT

`universe.MIN_DOLLAR_VOLUME = 3_000_000`, and the measured minimum across all
**3,059** tracker rows is **$3.0m/day**. Zero names below it. So the $100k–$1m
band carrying the largest measured 11-year edge is outside the universe we
screen — and a proposed lane to log `spread_bps` for those names would have had
**nothing to measure**. Widen the observation universe (§5-adjacent) *first*,
then measure spreads, then decide whether the edge is buyable.

### THE RULE THAT MAKES THIN NAMES INVESTABLE

> **evidence density ≠ expected upside.** A biotech with 4 credible
> observations: expected +70%, confidence 0.43. NVDA with thousands: +14%,
> confidence 0.81. The biotech may rank higher and still take less capital.
> Missing evidence lowers **certainty**, never **opportunity**.

### CITATIONS ARE UNVERIFIED

The review that produced much of this roadmap cited 2025-26 papers (Management
Science on LLM earnings language; JFE on ChatGPT headline scores; a
textual-novelty paper; an SSRN analyst-narrative study). **None has been opened
by us.** They are leads, not support. **No AEGIS claim may cite them until
someone reads the paper.** The same review also described two commits that did
not exist at the time it was written.

### THE RULE THIS WHOLE EPISODE EARNS

> **A capability is not built until an entry point can reach it.** Every new
> selector, collector or model names the entry point that consumes it, in the
> same commit, or it is a print. `scripts.reachability` had been printing
> `ORPHAN alpha.tracker` for weeks, buried among 22 other orphans — a permanent
> red block teaches the reader to skim it.

---

## 2. P0 — one exact portfolio reaches one paper account  ✅ BUILT (see §1b), NOT ENABLED

**Status changed the same day this was written.** The artery below exists and is
proven (`26faa7b`); what remains is to prove it on today's data, finish the four
missing artifact fields, and make the attended decision to enable ONE account.
The requirements below stand as the spec it is measured against.

Build the smallest auditable artery:

`tracker vintage -> build_portfolio(personality) -> sealed portfolio artifact -> named portfolio selector -> agent_loop -> admission -> broker -> fill -> tracker/outcome ledger`

Requirements:

- The sealed portfolio artifact contains exact symbol, target weight/notional ceiling, personality, ranking value, source tracker vintage, reasons, exclusions summary, model/rule versions, and a content hash.
- The live selector reads the seal. It must not re-rank or re-derive after the seal.
- Fix the semantic contradiction in the prediction artifact: a forecast may have zero order authority by itself while a separately enabled selector may consume it. State that precisely.
- Add a reachability test that fails if any portfolio advertised as LIVE has no import/call path from an entry point to broker admission.
- Add a dry-run/preview that prints the exact proposed holdings and worst-case risk from the same object the selector will consume.
- Deploy to **one** account first, not the fleet. Keep independent control books intact.

**Recommended first host:** hack4, because its intended role is profit-maximization and its previous live lane has been relatively inactive/near-flat. Do not silently repurpose every account.

If the exact portfolio-to-runner path cannot be proven before the open, keep the new book shadow-only for the session. Do not pretend `murat_rule` is the same experiment.

---

## 3. Boundaries: what is hard, what is an experiment

Do not use the word "cap" for four different things.

### HARD — survival

Gross exposure, per-position notional/premium risk, defined-risk options requirements, opening-range protection, daily-loss/account breakers, broker state reconciliation. These constrain **how much one bad belief can cost**, not what AEGIS is allowed to believe.

### HARD — data integrity

PIT timestamps, stale-data refusal, corporate-action/share-basis target sanity, units, duplicate detection, source failures and unverifiable catalysts. Bad input must not become confidence.

### EXPERIMENTAL — portfolio construction

Top-k, analyst buckets, liquidity bands, sector count caps, downside bands, past-winner exclusion, catalyst requirement. They are personality parameters with receipts, not universal laws. The temporary sector cap stays through the competition as a crude protection against Friday's hidden concentration, but the long-term replacement is **causal-driver/factor risk budgeting**, not arbitrary sector counts.

### SOFT — decision confidence

AEGIS should not require 95% certainty to speak. Every eligible name should receive a probability/expected-return/downside/confidence state where inputs permit. Low evidence means lower confidence and smaller/zero capital authority, not automatic deletion from discovery.

---

## 4. World Sensor Mesh — broad first, company second

The live funnel becomes:

`GLOBAL EVENTS -> CANONICAL EVENT CLUSTERS -> THEMES/NEEDS -> CAUSAL EXPOSURES -> WHOLE-MARKET CANDIDATES -> DEEP COMPANY RESEARCH -> MULTI-HORIZON FORECASTS -> PORTFOLIOS`

Do not fetch 4,000 stocks one by one as the primary discovery architecture. First ingest the world; entity-map and cluster it; then spend expensive reasoning on the short list.

Priority source families:

1. SEC/EDGAR filings and exhibits; issuer IR/press releases.
2. earnings/recommendation/estimate/target revisions and analyst narratives where licensed.
3. FDA, ClinicalTrials, PDUFA, patents and healthcare regulatory events.
4. Federal Register, USAspending/contracts, tariffs, sanctions, export controls, budgets and procurement.
5. GDELT/global multilingual news and local-language feeds for Asia-first lead information.
6. licensed archival news when entitlement exists; first check WRDS for RavenPack before paying for another vendor.
7. physical-economy series: capacity, shipments, inventories, commodity/material bottlenecks, power/grid, freight and manufacturing.
8. social attention/disagreement as a separate regime-dependent sensor, never as ground truth.

Common Crawl is a historical open-web backfill source, not a clean real-time newswire. X full archive is a paid optional source. Reddit-derived raw user content must respect current data/API rights; do not assume it can be used to train the NN.

---

## 5. News compression and text -> numbers

A thousand syndicated NVIDIA stories are not a thousand independent observations. Build a canonical `EventCluster` and retain the raw-source links behind it.

Each canonical event should carry at least:

- `event_type`
- `first_seen_at`, `effective_at`, `known_by`
- involved entities and relationship roles
- `source_count`, `independent_source_count`, `source_quality`
- `novelty_vs_company_history`, `novelty_vs_theme_history`
- `dissemination_speed`
- `directional_effect`
- `magnitude_estimate`
- `surprise_vs_expectation`
- `already_priced_proxy`
- `demand_delta`, `supply_delta`, `capacity_constraint`
- `contract_or_policy_dollars`
- `estimated_revenue_exposure`
- `causal_driver`, `causal_hop`, `causal_uncertainty`
- `social_attention_z`, `social_disagreement`
- `analyst_revision_velocity`, `analyst_disagreement`
- `evidence_density`

Keep **expected edge**, **evidence quality/confidence**, and **capital authority** as separate fields. A thinly covered biotech can have huge expected upside, low evidence density, and still deserve a small exploratory allocation. Raw lack of coverage must never equal a bearish score.

Normalize news/features against the name's own historical baseline and appropriate sector/size/liquidity/coverage peers. Never use raw article count cross-sectionally.

---

## 6. Persistent company state — the dataset AEGIS owns

Write one append-only `CompanyState` row per tracked symbol per decision vintage. Minimum state:

identity/sector/industry; causal drivers/exposures; analyst target/upside/count/revisions/disagreement; canonical event features; filings/catalysts; social attention/disagreement; price/volume/abnormal reaction; drawdown/momentum/volatility/liquidity; multi-horizon `p_up`, expected return, downside and confidence; status by horizon; current portfolio roles; thesis/falsifiers; last transition; source/model/version hashes.

Forecast horizons: 1, 5, 20/21, 63, 126, 252 sessions. Do not force one clock onto all mechanisms.

Fills, exits and realized outcomes must write back into this history. Until fills -> state/outcome is connected, the "self-learning tracker" loop is incomplete.

---

## 7. Candidate generators — independent lanes, not one blended score

Run independent generators so a global negative cannot kill a conditional mechanism:

1. analyst dislocation: upside + revision velocity + drawdown/expectation gap;
2. coverage initiation / under-covered novelty;
3. earnings/FDA/contract/policy surprise conditioned on initial reaction;
4. world-demand/bottleneck causal propagation;
5. cross-country lead: Asia/Europe/local news -> US exposures;
6. ownership/insider/government-money/flow;
7. social attention + disagreement with regime flag;
8. contradiction: bullish future state vs depressed price/consensus, or strong price vs deteriorating state;
9. human thesis lane;
10. replacement edge: compare a new candidate with what the portfolio already owns.

Every generator publishes ranked candidates even when confidence is weak; promotion to capital is separate.

---

## 8. Experiment factory — run continuously

Priority experiments for competition week and the research paper:

1. **Fantasy Causal Transposition v2:** more eras, common rebalance dates, multiple decider families; calibrate rank separately from probability.
2. **Theme-first replay:** give the model world/industry information first, require it to identify needs/bottlenecks, then rank an anonymized company-exposure table. This tests discovery rather than ticker explanation.
3. **Matched-loser tournament:** every historical winner paired with same-sector/size/liquidity/coverage names exposed to similar bullish narratives that did not win.
4. **Opportunity recall:** of the subsequent top 20/50 tradable winners, how many did each generator surface before the move? Label misses as sensor/entity/rank/portfolio/expression misses.
5. **Analyst revision velocity vs static target:** 11-year IBES test.
6. **Coverage initiation 0 -> 1 analyst:** matched size/sector controls.
7. **Surprise x reaction:** event surprise plus abnormal day-0 price/volume reaction, controlling for 5-day and 12-month momentum.
8. **Compression test:** raw duplicated news vs canonical event clusters vs numeric-only vs causal summary.
9. **Asia lead-lag:** information observable before the US open vs US-only baseline.
10. **Evidence-density test:** does sparse evidence reduce calibration while leaving rank/return opportunity intact?
11. **Portfolio expression tournament:** broad equal weight, top-k, expected-return weighted, risk-budgeted/fractional-Kelly, causal-driver constrained, and cash.
12. **Decision cadence:** daily/weekly/monthly/quarterly by horizon and regime.
13. **Hold/re-underwrite test:** buy-and-hold until thesis break vs fixed take-profit vs trailing/replacement-edge rules.
14. **Model disagreement premium:** test whether independent LLM disagreement predicts subsequent dispersion/error and deserves a risk haircut.
15. **Causal-hop decay:** direct beneficiary vs supplier-of-supplier; measure how edge/confidence decays with hop count.
16. **Synthetic monotonic stress exams:** vary one causal fact at a time in fictional scenarios; forecasts should move in the economically correct direction.

Every experiment writes an immutable manifest before outcomes: family ID, universe, horizon, features, portfolio rule, costs, controls/nulls, decision cadence and model versions.

---

## 9. NVIDIA and model roles

Use NVIDIA components where they reduce a real bottleneck, not for branding.

- **Quantitative Signal Discovery Agent pattern:** use the Signal -> Code -> Evaluation loop as the autonomous experiment factory. Replace the demo's S&P CSV/operator set with AEGIS CompanyState/EventCluster fields and AEGIS's own graders.
- **NeMo Agent Toolkit / AI-Q:** orchestrate broad web/deep-research tasks, tool calls, provenance and tracing. Web retrieval is a sensor; deterministic code stores/dedupes/grades.
- **NeMo Data Designer + Curator pattern:** generate balanced fantasy financial scenarios and semantically dedupe them. Use this specifically to create rare-event exams (FDA rejection/approval, sanctions, funding withdrawal, war, supply shock, contract loss/win) that historical news under-samples.
- Hosted NIM/API first. Do not run 30B/120B financial research models locally on the 8 GB laptop GPU.

Model cost ladder remains: deterministic extraction/dedupe first; cheap bulk LLM second; independent skeptic/adjudicator only for high-value ambiguity/disagreement. Paid DeepSeek escalation should have a recorded budget rather than silently becoming the fallback for every row.

---

## 10. Paper accounts are experiments, not six copies of one strategy

During the competition, preserve independent hypotheses. Suggested target architecture after the P0 bridge is proven:

- hack1: anchor/control lane;
- hack2: measured post-event drift lane;
- hack3: broad analyst-dislocation/breadth experiment;
- hack4: profit-max world-model/tracker portfolio;
- hack5: options-expression experiment using the same underlying forecasts;
- hack6: preservation/causal-driver-balanced experiment.

Do not relabel an account without actually rewiring its running brain and recording the mandate change. Do not reset the accounts to erase Friday.

The competition's short horizon cannot validate 3–12 month alpha. Use it to test reachability, execution, calibration checkpoints, opportunity recall, portfolio construction and learning-loop integrity while the historical farm tests the longer horizon.

---

## 11. Monday market-state test case

Before the US open, treat the current macro state as an input to the world model rather than a one-off story: oil/geopolitical risk, higher rate expectations and AI-infrastructure bottleneck news should generate conditional exposures and portfolio-driver concentration checks. A factual claim and a social-media/video claim are different evidence classes; provenance must affect confidence.

Today's Soitec photonics story is a model example of the desired causal chain: AI capex -> optical-interconnect demand -> silicon-photonics substrate bottleneck -> multi-year customer commitments -> capacity/pricing implications. The engine should then search customers, competitors, equipment/material suppliers and under-covered adjacent beneficiaries rather than stop at the named company.

---

## 12. Promotion order

P0: exact sealed portfolio -> runner on one account + fill/outcome write-back.

P1: world-event ingestion + canonical event clustering + company-state schema.

P2: broad candidate generators + opportunity-recall ledger.

P3: historical experiment factory using QSD-style Signal/Code/Eval loop.

P4: rank calibration layer: LLM supplies contextual ordering/features; code maps scores/ranks to probabilities from PIT historical base rates (isotonic/Platt or comparable calibrated model).

P5: tabular baselines (logistic/linear/GBT) and mixture-of-experts/gates.

P6: temporal heterogeneous graph model once enough causal/event/company vintages exist.

P7: sequence model and portfolio RL only after they beat simpler baselines out of sample after costs.

---

## 13. What not to do

Do not equate more news with more opportunity; do not make absence of news a bearish signal; do not require a catalyst for every discovery lane; do not hide a live wiring gap behind a printed portfolio; do not globalize hack6's preservation constraints; do not call a sector-count cap the final concentration model; do not use a 95% certainty gate to silence probabilistic decisions; do not train on Reddit/X raw content without rights; do not buy a news vendor before checking existing WRDS entitlements; do not promote a neural network because it is more complex; do not erase losses or rejected ideas from the learning record.

---

## 14. Competition-week scoreboard

Report daily, separately:

1. paper P&L and drawdown by account;
2. gross/driver/factor concentration;
3. opportunity recall at top-k;
4. prediction rank IC / hit rate / calibration by horizon and generator;
5. missed-opportunity causes;
6. execution slippage/refusals/options marks;
7. tracker additions/removals/revisions;
8. world-event clusters and newly emerging drivers;
9. experiment manifests completed, positive/negative/dormant;
10. learning-loop health: sensor -> state -> prediction -> portfolio -> fill -> outcome all reachable.

A profitable week is useful. A week that produces a trustworthy, increasingly informed decision system is the larger asset. The objective remains P&L; the accumulated state and receipts are how AEGIS improves its odds of producing it repeatedly.