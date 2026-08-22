# DESIGN REVIEW — 2026-08-22: the news engine, the rules audit, and where ROI actually lives

Ordered by Murat ("review all your work, come up with novel tests, how the
news can be utilized, a 24/7 engine that acts like a human investor, which
rules are outdated or limiting, what needs more work"). Everything below is
grounded in receipts on disk; where a claim is a design opinion it says so.

---

## 1. Self-review of the training-gate work (what is weak in what I built)

- **The tournament's verdict machinery is sound; its POWER was assumed
  until the sensitivity worlds measured it.** I declared dispersion 0.03
  in the prereg; reality was 0.077. The §64 audit caught it before the
  verdict — the process worked — but the right order for TOURNAMENT-2 is
  **detectability first, registration second** (now a declared gate).
- **Own-construction betas are attenuated on thin names** (fully-traded
  median 0.845 vs 0.118 for names with ≥10 zero-trade days — measured,
  textbook non-synchronous trading). Harmless for the dollar-vol-filtered
  trials run today; **Dimson-adjusted beta is required before any all-cap
  panel-2 use** of these features.
- **The guard contract caught me twice in one day** (PanelRefused,
  RiskPriceRefused). Cost: one red CI. The contract is working; the lesson
  is to run it in the pre-commit loop for any new `*Refused/*Error`.
- **Three silent-wrong classes shipped in my own new code** before the
  fragility audit found them (all-NaN join, stale cache, empty-glob
  receipt). One session's distance was enough to find them — the audit
  skill should run same-session on any new loader, not "when asked".
- The z-label hypothesis was first tested in a world that could not test
  it (homoskedastic noise). The `linear_hetero` world (real per-month
  dispersion on both signal and noise) then REFUTED it: z-label +0.0001
  vs raw +0.0021. Scale, not the training objective, is the binding
  constraint — TOURNAMENT-2 needs rows, not label transforms.

## 2. Rules audit — load-bearing vs limiting (each with its receipt)

**KEEP, LOAD-BEARING (they earned it again today):** prereg-first + corpse
check (killed a duplicate-risk registration path and forced the
era-transfer design) · §64-before-verdict (stopped an over-read twice) ·
null/known-answer worlds (caught my own spec bug) · guard contract ·
"an IC is not money" · no-skill-claims-before-24mo · the execution
standard (≥+3%/yr net AND regime blocks AND holdout).

**LIMITING OR OUTDATED — propose amendment (attended where marked):**

1. **"Add no database" (CLAUDE.md)** — written for the stateless public
   API; the research brain now runs NAV tables, jobstores, ledgers, event
   stores, a 46 GB substrate. De facto dead on the brain side. *Amend the
   rule's SCOPE*: public API stays stateless; the brain side gets a
   declared store policy instead of pretending. (Doc change — attended.)
2. **Product surfaces vs research truth.** The screener/projections run on
   a 30–150 yfinance survivor universe while the research side proved its
   nulls on 4,354 PIT names. These can NEVER merge (WRDS licensing forbids
   CRSP/JKP in the public product) — so the split is permanent and should
   be EXPLICIT: product pages carry "reference analytics, not the research
   engine" labels. The T7 rule (yfinance = direction-checks only) already
   says this internally; the surface should say it too.
3. **Crash overlay: months of `model_not_deployed`.** Every lane shows the
   overlay dark because crash_model.pkl is broken. Either the new
   substrate retrains it (it is now a legitimate NAMED CONSUMER of the
   panel: crash labels + FRED + panel features) or the overlay is formally
   disarmed and removed from health. A subsystem that is neither working
   nor retired is exactly the silent-fragility class. (Attended choice;
   my recommendation: retrain as a named consumer, it is one of the few
   models here with a validated-ancestor track.)
4. **`lab/rd_loop`** — last real run 2026-04-17; superseded by the
   day-factory / night-IIF cadence. Retire formally (archive + README
   note) so CLAUDE.md stops advertising it. (Doc change.)
5. **CLAUDE.md "Healthy Output Ranges"** — stale (quotes a working crash
   model, 30-stock universe). Update or delete; a stale validation range
   is a false canary.
6. **`prediction_ledger` quarantine** (25 overdue campaign copies, 10 days
   quiet, DEGRADED on every health read) — the disposition is attended and
   overdue; it degrades the health surface daily and trains everyone to
   ignore DEGRADED, which is how the next real one gets missed.
7. **Event intel: `events_extracted: 0`, GDELT 429s.** The news pipeline
   the ORDER 29 design below needs is currently a batch fetcher that
   rate-limits itself to zero. This is the single most outdated component
   relative to where the roadmap is pointing.

**NOT outdated despite appearances:** "LLM narrates, engine computes."
NIGHT-3 (16,320 decisions, null) and GRAND-ARENA-1
(`PRESENTATION_AND_RESEARCH_ASSISTANCE`) are the receipts; ABLATION-FWD
accrues the honest re-test. The rule blocks LLM *allocation*, not LLM
*sensing* — and sensing is where the design below spends.

## 3. The 24/7 news-investor engine (ORDER 29 candidate, design)

**The honest frame first.** "Reads news every few minutes and acts like a
human investor" decomposes into three loops with very different evidence:

- **Ingest continuously — yes, cheap, and we are behind.** Latency
  matters for knowing, not (for us) for trading.
- **Decide event-conditionally — yes; this is where the receipts point**
  (PEAD/insider/FDA effects are 10–100× monthly-panel effect sizes; the
  sensitivity worlds proved the generic monthly instrument is blind at
  realistic sizes — the answer is to go where effects are big, not to
  build a bigger generic model).
- **Trade continuously — no.** Measured edges are multi-day drifts
  (disclosure+1 entries). "Every few minutes" is an ingestion
  requirement; converting it into a trading frequency would add cost and
  noise with no measured edge behind it.

**Architecture (three loops + two stores), mapped to what exists:**

1. **EVENT STORE (build).** PIT, append-only, one row per event:
   `(event_id, type, entities, accepted_at, source, payload_hash)`.
   Sources in priority order: EDGAR full-text 8-K/Form-4/13D (minute-poll,
   free, PIT by acceptance timestamp, the ONE shared rate limiter),
   earnings timestamps (IBES/rdq for research; provider calendar for
   live), prediction-market snapshots (built), GDELT (fix the 429s with
   backoff + budget), press-release RSS. The ownership/congress collectors
   already do this shape — generalize, don't rewrite.
2. **SENSOR LOOP (extend).** The LLM as a *structured sensor* per event:
   typed fields (event_type, novelty, guidance_change, uncertainty,
   affected_entities, horizon) — never buy/sell. FinBERT stays as the
   cheap first pass; DeepSeek/Claude extraction budgeted per event class.
   Every extraction lands in the event store with model+prompt hash so
   ABLATION-style factorials stay possible forever.
3. **PLAYBOOK LOOP (the "acts like an investor that learns" part).** Per
   event type, a pre-registered forward playbook: entry rule
   (acceptance+1 close), horizon, matched-control grading, kill condition
   — exactly the TEACHER-LIBRARY/BRAIN-00x pattern, generalized. The
   arena's experience/why_moved/reliability-router stack IS the learning
   loop; what it lacks is event-driven candidates instead of daily
   rebalance candidates. `EVENT_IMPACT_MATRIX` (ORDER 27 P7) becomes the
   measured object: event-type × horizon → forward return/vol
   distribution, updated by the grader, consumed by the router.
4. **Sizing stays with the engine**: router trust × declared caps ×
   quarter-Kelly until the ledger vouches. No LLM touches size.

**Build order (each step ships alone):** (a) EDGAR 8-K minute-collector +
event store + health canary; (b) event-store backfill from what EDGAR
allows historically (PIT by construction); (c) EVENT_IMPACT_MATRIX v0 on
the backfill as a SCREEN with era discipline; (d) playbook prereg for the
top 2 event types by measured impact × frequency; (e) sensor factorial on
those types only (budgeted); (f) arena book `EVENT_v1` (new ID) once a
playbook survives its screen. Cost: (a)–(c) are compute + one collector;
LLM spend only enters at (e).

## 4. Which markets, when to buy/sell — what the receipts actually license

| focus | verdict from receipts | action |
|---|---|---|
| US equities, event-conditional | Highest evidence density (PEAD/insider CONFIRM legs accruing; effects at %-scale vs bp-scale) | the ORDER 29 engine above |
| Risk/vol as the SELL discipline | Validated twice, both eras (LGBM vol head; risk stationary) | already shipping (G2 risk-sized pair, ATR lane); this IS "when to sell" today |
| US equities, generic cross-section | Two registered nulls + a blind-instrument receipt | panel-2 + detectability gate only; no more small-instrument re-asks |
| Foreign developed equities | Untouched by us; same-era confirm licensed for the one lead; pull in flight | RISK-PRICE-FOREIGN-CONFIRM-1 next session |
| Prediction markets | Arb refuted (fees eat it); divergence measurement registered | keep collecting; decide at the registered thresholds |
| Options-implied | IV-ORACLE-GAP-1 alive; options family absent from panel v1 (declared) | join as named consumer for panel v2 |
| Crypto / FX / commodities | No PIT store, no trials, no infrastructure | explicitly out of scope until a named consumer exists |

**"When to buy":** the only entry rules with evidence are event entries
(disclosure+1) and monthly formation rules. **"When to sell":** the only
validated sell logic is risk-based (vol targeting, drawdown structure,
winner-exemption under test in G2) — not prediction. Any "timing" beyond
this is currently unlicensed, and saying so is the edge over retail.

## 5. Novel tests worth registering (ranked, `P(changes roadmap)×value−cost`)

1. **EVENT-WINDOW SUPERVISED LEARNING** — train/grade on event-aligned
   samples instead of calendar months. The direct answer to the
   blind-instrument receipt: effects 10–100× larger, n smaller but
   signal-dense. Needs the event store; the corpse check must clear
   BRAIN-004/006/011 lineage (extends, not repeats).
2. **REGIME-GATED PREDICTABILITY** — the era-dependence (early + / modern
   0 for price; modern + / early 0 for risk-price) is itself the
   phenomenon. One registered screen on panel-2: family × DECLARED regime
   states (HMM already exists; states declared, never fitted post hoc).
   If predictability is regime-local, every pooled-era null is mis-asked.
3. **OVERNIGHT/INTRADAY DECOMPOSITION** — news incorporates overnight;
   dsf has openprc 2013+. Cheap, well-documented in the literature, and
   feeds the event engine's entry-timing choice directly.
4. **DIMSON-CORRECTED ALL-CAP RISK FAMILY on panel-2** — fixes today's
   measured attenuation before the family is judged at full scale.
5. **FOREIGN-CONFIRM as a pattern** — any modern-era-only US lead earns a
   13-country same-era read before more US compute (rule of thumb worth
   adopting programme-wide).
6. **LLM SENSOR QUALITY factorial on the event store** (extends
   ABLATION-FWD; contamination discipline already written).

## 6. What needs more work (the sweep Murat asked for)

Carried, unchanged priority: why_moved day-guard → retry slots · G1
correlated-worlds battery before router capital authority ·
PROFIT_ALLOCATOR_v2 behind OOS forecasts · P9 books behind a surviving
signal. New from this review: crash-overlay disposition (retrain-vs-disarm,
attended) · prediction-ledger quarantine disposition (attended) ·
event_intel/GDELT repair → event store · product-surface honesty labels ·
CLAUDE.md staleness pass · lab/rd_loop retirement.

**The one-line thesis:** stop asking small instruments generic questions;
put the compute where effects are large (events), the confirms where eras
are independent (foreign, forward), and the selling where the evidence is
(risk) — and let the 24/7 loop be an ingestion-and-learning machine, not a
trading-frequency machine.
