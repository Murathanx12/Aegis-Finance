# World model & analogous projects — an interdisciplinary sweep (2026-09-20)

Scope per Murat's brief and the reviewer's ask: MiroFish as an isolated "world
model" sidecar (seed → knowledge graph → personas → multi-agent simulation →
persistent memory → **structured consequence probabilities, never a trade
recommendation**), plus analogous projects across AI/data-science/social-media/
neuropsychology/media/politics/finance. Licence boundary throughout: the sidecar
must not become the closed family in `NEGATIVE_RESULTS.md` §19 ("LLM/agent
trading alpha is comprehensively dead") — that verdict killed *LLM decides the
trade*. A sidecar that emits typed scenario data for the deterministic engine
to rank is a different object, same as `AEGIS_STRATEGIC_INVARIANTS.md` #5
already requires ("LLMs propose... deterministic/quant engines compute").

## 1. MiroFish

**Repo:** [666ghj/MiroFish](https://github.com/666ghj/MiroFish) ("A Simple and
Universal Swarm Intelligence Engine, Predicting Anything"). **Licence: AGPL-3.0**
— network copyleft; running it as a service that others query over HTTP
triggers the AGPL's source-disclosure obligation on the *service*, not just
distributed binaries. **This is the load-bearing constraint on the whole
plan**: MiroFish/OASIS code must stay a subprocess we call, never code we
statically link into `backend/`, or the whole repo's licence posture changes.

**What it does:** upload a seed document (press release, policy draft, filing)
→ Graph Build (entity/relationship extraction, GraphRAG) → Env Setup
(generates hundreds of LLM personas with personality/opinion-bias/reaction-speed/
influence) → dual-platform simulation on **OASIS**
([camel-ai/oasis](https://github.com/camel-ai/oasis), Apache-2.0, "Open Agent
Social Interaction Simulations with One Million Agents") → hour-by-hour posts/
arguments/opinion shifts → a ReportAgent summarises. Benchmarked for realism by
[MiroBench](https://arxiv.org/pdf/2606.14715) (arXiv 2606.14715).

**What it does not do:** the upstream README lists **financial prediction and
political-news prediction as "coming soon"** — i.e. not shipped. It is a
*social-reaction* simulator, not a return forecaster; any financial use is
ours to build on top, not something MiroFish already validates.

**Memory / dependency:** stock MiroFish requires a **Zep Cloud** API key
(metered SaaS). A community fork line replaces this with self-hosted
**Graphiti** (the OSS temporal-KG library Zep Cloud itself is built on) against
local **Neo4j** — see
[koushikraj-s/mirofish](https://github.com/koushikraj-s/mirofish) and
[tt-a1i/MiroFish-local](https://github.com/tt-a1i/MiroFish-local) ("本地运行版本
| Graphiti+Neo4j替代付费Zep"). This is the fork the reviewer means; it removes
the SaaS dependency and keeps data local, which is the only variant worth
running given CLAUDE.md's data-locality and cost posture.

**Local LLM / hardware:** the offline line
([nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline),
same AGPL-3.0) targets **Ollama on :11434**, default **Qwen2.5-32B** (14B for
constrained boxes), `nomic-embed-text` (768-dim) — min 16 GB RAM/10 GB VRAM,
recommended 32 GB/24 GB VRAM. **This does not match what we already run**:
Aegis's own local stack is `llama-server` on `127.0.0.1:8080` serving
Qwen3-30B-A3B or a 7B (S52/S53 memory), not Ollama. Adopting MiroFish-Offline
as-is means running a second local-LLM server (Ollama) beside the one we
already operate, or rewriting its `openai`-SDK client to point at our existing
`:8080` endpoint (both speak the OpenAI chat-completions shape, so this is a
config change, not a rewrite) — that is the one concrete adapter needed. Graph
storage (Neo4j) is new infrastructure we do not run today (`backend/data/`
holds no graph DB — `CLAUDE.md` also says "no database" for the stateless API,
so Neo4j must live *only* inside the sidecar container, never touched by
`backend/`).

### Concrete sidecar plan

```
world_model/                          # NEW top-level dir, isolated
  docker-compose.yml                  # neo4j + mirofish-local + our llama-server client
  seeds/<event_id>.json               # ONE real event package in (typed, PIT)
  runs/<event_id>/scenarios.jsonl     # 20-50 sampled scenarios out
  runs/<event_id>/consequences.json   # structured consequence probabilities out
  adapter/to_aegis_signal.py          # the ONLY file backend/ ever imports from
```

- **In:** one real, already-public event (an 8-K, an earnings call transcript,
  a policy announcement) packaged with the PIT timestamp — never a stock
  ticker as the seed, to keep the graph from anchoring on price.
- **Sim:** 20-50 independent OASIS runs (different agent seeds/persona
  draws), each producing a discourse trace + a typed end-state
  (`{sentiment_shift, narrative_category, contested: bool, virality_decile}`).
- **Out:** the adapter aggregates the 20-50 runs into a **distribution**, not
  a point forecast — e.g. `P(narrative sticks past 5 days) = 0.34 ± CI`,
  `P(contested-by-counter-narrative) = 0.51`. This is what crosses into
  `backend/`: a typed row in the same shape as any other collector in
  `backend/services/pit_collectors.py`, carrying `evidence_grade:
  OBSERVATIONAL` per `signal_registry.yaml`'s own schema, never `PICKER`.
- **Licence boundary in code, not memory:** `world_model/` gets its own
  `LICENSE` file (AGPL-3.0, inherited), a top-of-file banner in every file
  under it, and `adapter/to_aegis_signal.py` is the ONLY crossing point —
  the same "one-way firewall" pattern the repo already uses for the Aegis
  module (`CLAUDE.md`'s four-repo table). `backend/` (MIT-equivalent-in-spirit
  stateless API) never imports OASIS/MiroFish code directly, only reads the
  adapter's JSON output — that keeps AGPL contained to a subprocess boundary.
- **What licenses this as PRODUCT_EXPERIMENT, not RESEARCH_CLAIM:** per
  CLAUDE.md's three-licence table, internal simulation output needs only a
  frozen strategy contract before the first decision consumes it — no
  significance gate yet. But nothing it emits may set `allowed_in_pm: true`
  in `signal_registry.yaml` until it clears the same bar every other
  candidate does (§19's LLM-alpha corpse applies in full if this becomes "the
  LLM picks the trade" instead of "the LLM's simulated crowd is one more
  typed observation the deterministic ranker weighs").

## 2. Ten to fifteen analogous projects

| Project | Repo/paper | Licence | Take | Refuse |
|---|---|---|---|---|
| **ABIDES** | [abides-sim/abides](https://github.com/abides-sim/abides); [jpmorganchase/abides-jpmc-public](https://github.com/jpmorganchase/abides-jpmc-public); arXiv 1904.12066 | BSD-3-Clause | Discrete-event market microstructure sim (order book, latency) for testing execution assumptions, not alpha | Its "agents" are stylised trading rules, not personas — do not conflate with MiroFish's social layer |
| **JAX-LOB** | [KangOxford/jax-lob](https://github.com/KangOxford/jax-lob); arXiv 2308.13289 | Apache-2.0/BSD (JAX ecosystem) | GPU-parallel LOB simulator (thousands of books) — useful if we ever build an execution-cost model from first principles | Research-grade only; do not use for realistic cost modelling without recalibration to Alpaca's own fills |
| **NautilusTrader** | [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0+ | Event-driven backtest/live engine architecture reference (fill models, venue sim) | LGPL is weaker copyleft than AGPL but still a linking constraint; evaluate before embedding, don't just `pip install` into `backend/` |
| **Generative Agents ("Smallville")** | [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents); Park et al. 2023, ACM UIST | MIT | The memory-stream + reflection + retrieval architecture MiroFish's personas descend from — read before tuning persona memory decay | Small-N (25 agents) toy town; not validated at social-media scale — that's what OASIS adds |
| **OASIS** | [camel-ai/oasis](https://github.com/camel-ai/oasis) | Apache-2.0 | The engine under MiroFish itself — could be driven directly (skip MiroFish's UI layer) for a leaner, non-AGPL integration path | Reaching "one million agents" needs infra we don't have; run at hundreds, not millions |
| **Concordia** | [google-deepmind/concordia](https://github.com/google-deepmind/concordia); arXiv 2312.03664 | Apache-2.0 | Game-Master pattern (a referee LLM translates agent intents into world outcomes) — cleaner than OASIS for a *causal* consequence engine, and **not AGPL** | Smaller community, less battle-tested at OASIS's agent counts |
| **TinyTroupe** | [microsoft/TinyTroupe](https://github.com/microsoft/TinyTroupe); arXiv 2507.09788 | MIT | Lightweight, Python-native persona simulation for "how would N distinct personas react to X" — a cheap MVP before standing up the full MiroFish stack | Built for ad/product testing; no built-in knowledge-graph memory, no social contagion dynamics |
| **Polymarket / Metaculus** | Polymarket public API; Metaculus API (metaculus.com/api) | Data terms, not code | Calibration benchmark: compare our engine's `P(event)` outputs against a real prediction market's price on the *same* event as an external calibration check | Do not treat market price as ground truth — it is itself a noisy aggregate; use for calibration diagnostics, not as a feature |
| **Good Judgment Project / superforecasting** | Tetlock & Mellers, IARPA ACE tournament; [goodjudgment.com](https://goodjudgment.com/about/the-science-of-superforecasting/) | Methodology, not code | Extremizing + track-record-weighted aggregation — directly reusable for combining the 20-50 MiroFish scenario outcomes into one probability (don't just average) | Superforecaster *training* effects (deliberate practice, teaming) don't transfer to LLM personas — no evidence LLM "practice" improves calibration the same way |
| **Baker-Bloom-Davis EPU** | [policyuncertainty.com](https://www.policyuncertainty.com/); Baker, Bloom, Davis, QJE 2016; FRED series `USEPUINDXD` | Free, academic | A ready macro-regime covariate (daily/monthly, 22 countries) — cheap to pull, no collector exists in `backend/services/` today | Newspaper-count methodology is coarse; do not treat as firm-level signal |
| **GDELT** | [gdeltproject.org](https://gdeltproject.org/); updates every 15 min, 100+ languages | Free, CC-style | Whole-market, Asia-inclusive event/tone data — matches the VISION file's "whole-market news, Asia first" mandate directly; no GDELT collector exists in `backend/services/` today (closest is `news_entities.py` + `news_registry.py`, which are source-specific, not event-graph) | High noise/duplicate-event rate; needs dedup before any signal use |
| **ICEWS / ACLED** | ICEWS (DARPA-derived, ~1991-present); [acleddata.com](https://acleddata.com/) | ICEWS: public via Harvard Dataverse; ACLED: free for academic/non-commercial | Political-event layer for the "politics" spoke of the brief — machine-coded (ICEWS) vs human-coded (ACLED) conflict/protest events, cross-checkable against GDELT | ACLED's non-commercial licence needs re-checking before any `CAPITAL_CANDIDATE` use; low direct equity relevance outside geopolitics-exposed names |
| **Cohen-Frazzini "Economic Links"** | Cohen & Frazzini, *J. Finance* 2008; [pdf](http://www.econ.yale.edu/~shiller/behfin/2006-04/cohen-frazzini.pdf) | Academic paper | The customer-momentum mechanism itself — **already tested and closed in this repo** (NEGATIVE_RESULTS §12, TRIAL-THEME-SUPPLY): monthly is real but too weak net of 70% churn, annual has zero spread. Reopening requires a different mechanism class per that verdict's own words: "event-conditioned links on daily data" | Do not re-register plain 12-1 customer momentum — that corpse has a receipt |
| **Supply-chain propagation via LLM embeddings** | "Supply Chain Propagation of Textual Signals" arXiv 2606.29290 | arXiv preprint | A 2026 daily/text-conditioned variant of exactly the mechanism class §12 said was needed — read before designing the event-conditioned revival | Confirm their sample avoids the same annual/monthly aggregation §12 killed before citing it as new evidence |
| **Da-Engelberg-Gao attention (SVI)** | Da, Engelberg & Gao, *J. Finance* 2011, "In Search of Attention" | Academic paper | Already the basis of `backend/services/trends_sentiment.py` in this repo — cite as the grounding, extend rather than rebuild | Google Trends is weekly-granularity and US-centric; doesn't satisfy "Asia first" alone |
| **EDGAR log-file attention** | [sec.gov EDGAR log file data sets](https://www.sec.gov/data-research/sec-markets-data/edgar-log-file-data-sets); Ryans (SSRN 2913612); Drake, Roulstone, Thornock (2015) | Free, SEC-published | "Sophisticated investor" pre-announcement attention, orthogonal to retail (Reddit/Trends) attention — a *human-download-filtered* signal with a published long-short alpha (~1.24%/mo pre-costs) to falsify against, not trust | Public files must be filtered for robot traffic yourself; no ready collector exists in `backend/services/` |
| **r/WallStreetBets attention literature** | Multiple 2024-25 ScienceDirect papers (e.g. S1057521924006537, "Dumb money?" S2405918825000212) | Academic papers | Consistent finding: buying *at peak WSB attention* loses money — a **contrarian/avoid** signal, not a buy signal; relevant to the neuropsychology spoke (disposition effect, overconfidence) | Do not build a "follow retail attention" long signal — literature says the opposite direction wins |
| **Shiller Narrative Economics** | Shiller, *Narrative Economics*, Princeton 2019; Cato summary | Book/framework | The epidemiological (SIR) contagion model for how a story spreads — directly maps onto what MiroFish's multi-round simulation should be measuring (does a narrative's simulated R₀ predict real virality) | A book of case studies, not a fitted model — treat as a hypothesis generator per Strategic Invariant #3, not as validated math |

## 3. Idea → discipline → data we hold → missing → cost → first test

| Idea | Discipline | Data we already hold (repo path) | Missing | Cost | First test (one line) |
|---|---|---|---|---|---|
| MiroFish world-model sidecar | AI / social sim | none (new subsystem) | Neo4j, Graphiti, local LLM adapter, `world_model/` dir | Free (local compute only) | Seed one already-graded historical 8-K, run 20 scenarios, check if the scenario-distribution's modal narrative matches what actually happened (retrospective calibration, not live trade) |
| Event-conditioned supply-chain momentum (daily) | Finance / quant | `backend/services/graph_propagation.py` (co-coverage graph, live) proves the graph-edge machinery already exists | Customer/supplier *link* data at daily granularity (Compustat segment files or 10-K customer-disclosure NLP) | Paid (Compustat via HKU WRDS) or scrape 10-K "significant customer" disclosures free | Re-run TRIAL-THEME-SUPPLY's design but condition on an *event day* (customer earnings surprise), not calendar rebalance — per §12's own reopening clause |
| Google Trends attention | Neuropsych / behavioural finance | `backend/services/trends_sentiment.py` (already built, cites Da-Engelberg-Gao) | Asia-market search terms (Baidu/Naver indices, not just Google) | Free (rate-limited) | Compare US vs Asia SVI z-score lead time on the same earnings surprise |
| EDGAR log-file "sophisticated attention" | Neuropsych / market microstructure | none | SEC's published log-file data sets (2003-2017, 2020-2025), robot-traffic filtering | Free (SEC-published) | Replicate Drake-Roulstone-Thornock's pre-announcement attention vs PEAD-strength relationship on our own universe |
| EPU / policy-uncertainty regime covariate | Politics / macro | none | Pull from FRED (`USEPUINDXD`, `GEPUCURRENT`) | Free | Condition an existing signal's IC on EPU tercile — does the signal's edge concentrate in low- or high-uncertainty regimes |
| GDELT whole-market event stream | Media / political science | `backend/services/news_registry.py`, `news_entities.py` (source-specific, not event-coded) | A GDELT collector (none exists) | Free (GDELT is open) | One day's GDELT GKG pull for an Asia-listed name already in `backend/data/news_entities/asia_adrs.csv`; check event-coding recall against our existing news pipeline for the same day |
| Congressional trades | Politics / insider behaviour | `backend/services/congress_trades.py` + `portfolio_intelligence/congress_collector.py` **already live** (per `docs/research_notes/2026-09-20/audit_congress_collector.md`) | Nothing — audit its silent-fragility status first | Already paid for (FMP budget) | Read the audit note before building anything new here; TRIAL-CONGRESS-IC already registered |
| Insider purchases in distress (2026 JEF finding) | Finance / behavioural | `backend/services/insider_form4.py`, `sec_insider_bulk.py`, `cmp_insider.py` | A distress flag (Altman-Z or credit-spread proxy) to condition insider buys on | Free (compute Z-score from existing fundamentals) | Slice existing insider-opportunistic signal by distress tercile, replicate the JEF 2026 "reversal after overreaction" pattern in-house |
| Option IV / borrow-fee mechanism (JFE 2025) | Quant / options | `backend/services/option_implier.py`, `options_calibrator.py`, `options_intelligence.py`, `options_pit_store.py` | Actual stock-borrow-fee feed (we likely only have IV spread as a *proxy* per NEGATIVE_RESULTS §27's own "option-implied family closes on all seven mechanism classes") | Paid (borrow-fee data, e.g. from a securities-lending vendor) or proxy via IV skew per Muravyev-Pearson-Pollet | Before paying for borrow-fee data: check whether §27's closure already covers this exact mechanism — if so this is REJECTED, not OPEN |
| Analyst textual-opinion index (JBF 2026) | Finance / NLP | `backend/services/estimate_revisions.py`, `sentiment_analyzer.py` | Full analyst-report text (we likely only have numeric estimates, not report prose) | Paid (report text vendor) or free proxy from earnings-call transcripts we may already scrape | Build the index on transcript text only (no paid report text) and check if it predicts market return the way the paper's report-text version does |
| Sticky-analyst revisions (RoF 2026) | Finance / behavioural | `backend/services/estimate_revisions.py` | Per-analyst historical forecast-update cadence (to classify "sticky" vs responsive analysts) | Free if IBES/estimate history already covers multiple analysts per name | Classify existing revision data by analyst stickiness, replicate the paper's stronger-predictability-in-sticky-subset finding |
| Meme-stock / WSB contrarian attention | Neuropsych / social media | `backend/services/trends_sentiment.py` (search only, not Reddit) | A Reddit/WSB mention-volume collector | Free (Reddit API, rate-limited) or free via Pushshift-successor mirrors | Build attention decile on a small sample, check if the literature's "peak-attention buyers lose" replicates before any live use |
| Prediction-market calibration check | Politics / forecasting | none | Polymarket/Metaculus API pull | Free | For any event where both our world-model sidecar and a real prediction market have a live price, log the divergence — a calibration diagnostic, not a signal |

## 4. Ranked TOP-5 cross-disciplinary combinations (new, not in NEGATIVE_RESULTS.md)

Section headers checked against all 58 in `NEGATIVE_RESULTS.md` (listed above,
§1-§58 plus the unnumbered TRIAL-H5 entry) — none of the five below duplicates
a closed family; three explicitly satisfy an existing reopening clause.

1. **Event-conditioned supply-chain propagation, daily cadence, text-triggered.**
   Combines Cohen-Frazzini's mechanism with GDELT/10-K-disclosure event timing
   and `graph_propagation.py`'s already-proven co-coverage machinery. §12
   killed *calendar-rebalanced* customer momentum and named the exact revival
   condition ("event-conditioned links on daily data"); arXiv 2606.29290
   shows this variant is live external research, not a dead end.
   **Falsifier:** if the B-A decile spread conditioned on customer earnings-
   surprise events is still t < 1.5 net of costs on the SAME 2004-2018 CRSP
   window §12 used, the whole mechanism class (not just the calendar variant)
   is closed.

2. **MiroFish-simulated narrative virality (Shiller SIR-shaped) as a
   CATALYST_SENSOR, not a PICKER.** Seed one real event, run 20-50 OASIS
   scenarios, fit a simple SIR curve to the simulated discourse volume, and
   test whether the fitted "R₀" predicts *real* subsequent attention (Google
   Trends / GDELT tone volume) for the same event — never price. This stays
   inside §19's boundary because the LLM never allocates; it produces one
   more typed, `OBSERVATIONAL`-grade row.
   **Falsifier:** if simulated-R₀ has zero correlation with real subsequent
   attention volume across ≥30 seeded historical events, MiroFish adds no
   information over the collectors we already run and the sidecar is
   `RETIRED_FROM_CURRENT_SEARCH`.

3. **EDGAR "sophisticated attention" as a veto on retail-attention
   contrarian signals.** Combine the EDGAR log-file professional-attention
   measure with the existing WSB/Trends retail-attention literature: the
   neuropsychological prediction is that stocks with HIGH sophisticated
   attention and HIGH retail attention behave differently (informed money
   already positioned) than HIGH retail / LOW sophisticated (pure
   speculation, the WSB-loses-money regime). Neither half is in
   NEGATIVE_RESULTS; the combination is new.
   **Falsifier:** if the two-way split shows no return-spread difference
   from either attention measure alone, the combination adds nothing over
   univariate attention and is closed as a combination (each half may still
   be tested separately).

4. **EPU-regime-conditioned signal reliability weighting.** Baker-Bloom-Davis
   EPU as a macro regime switch on `signal_registry.yaml`'s
   `reliability_weight` for existing VALIDATED/SUPPORTED signals — the
   hypothesis is that momentum-class signals degrade in high-EPU regimes
   while mean-reversion/quality signals hold up (standard in the academic
   EPU literature but never tested against THIS project's own signal set).
   **Falsifier:** if no existing signal's IC shows a significant EPU-tercile
   interaction (Wald test on the interaction term), regime-conditioning this
   signal set specifically does not work and the idea is closed as applied
   here (EPU itself is not refuted generally).

5. **Insider-purchase-in-distress reversal, screened by MiroFish-simulated
   market narrative.** The 2026 JEF finding is that insider buying in
   distressed firms partly reflects overreaction to bad news that reverses;
   the hypothesis is that a sidecar-simulated "is the bad-news narrative
   still spreading or already exhausted" state (again the Shiller-SIR
   virality curve) sharpens WHICH distressed-firm insider buys are about to
   reverse vs which face a genuinely still-worsening narrative. Requires
   idea 2 to exist first — ranked last because it is the most dependent.
   **Falsifier:** if the narrative-exhaustion flag shows no interaction with
   insider-buy forward returns beyond the distress tercile alone, drop the
   MiroFish layer and keep the plain distress-conditioned insider signal
   (idea 5's insider half, not idea 2, survives).

**Explicit non-claim, per CLAUDE.md's three licences:** nothing above is a
`RESEARCH_CLAIM`. Ideas 1-5 may enter as `PRODUCT_EXPERIMENT` books
immediately (frozen contract, no significance gate) per "Explore Dirty,
Promote Clean"; promotion to `CAPITAL_CANDIDATE` needs the full evidence
ladder CLAUDE.md already specifies, unchanged by any of this research.
