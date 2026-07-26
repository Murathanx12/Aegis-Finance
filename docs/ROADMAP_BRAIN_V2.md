# Investor Brain v2 — master roadmap (2026-07-22; status updated 2026-07-24)

## Status board (2026-07-24)

| Chunk | Status |
|---|---|
| 1. Factory batch 1 (price/vol) | ✅ CLOSED — 0 graduates; dip-buy theses rejected |
| 2. Factory batch 2 (fundamentals) | ✅ CLOSED — **BRAIN-008 gp-small: confirm PASS + 42-yr robustness** |
| 3. Factory batch 3 (events/alt) | 🔶 3a/3b/3c adjudicated (cust_mom + best_ideas CLOSED on merits; **both tgt_upside runs VOID** — IBES split-adjust look-ahead, fix needs `ibes.adj`); **FDA drift ADJUDICATED 2026-07-24: TRIAL-BRAIN-006 REJECT** (crosswalk built, −30.1 bps/mo t −0.89 large/mid, micro untestable at monthly resolution — daily-CAR revisit = new registration post `crsp.dsf`); **TRIAL-THEME-SUPPLY basket arm REJECT 2026-07-24** (B−A spread t=0.10 — supplier thesis fully adjudicated, both arms dead, NEG_RESULTS §12); remaining: buyback/spinoff; best_ideas_frac (3c) also CLOSED |
| 4. Confirm + fusion | 🔶 **BRAIN-007 fusion SURVIVES** (beats best single, 3.6× names); remaining: INSTR-OVERFIT-CEILING (queued, needs pre-registration before run) |
| 5. Allocation layer | 🔶 **smallmid-quality lane SEEDED + LIVE** (trial #16, first NAV rows 07-22/07-23, −1.02%, decision 2028-07-22); **NEW: Batch 4 macro-regime/cross-asset instruments** (see below); remaining: trend/managed-futures overlay trial → now INSTR-TSMOM-XA |
| 6. LLM brain v2 | ⬜ (event extraction at scale, episodic memory, thesis generator) |
| 7. Average-Joe copilot | ⬜ (holdings-first UX; most analytics already served) |

Scoreboard (updated 2026-07-24 EOD): **120** explore candidates (batch 5 =
15 signals ×2 segments, ZERO graduates, replication-sweep priors 15/15
directional; TRIAL-THEME-SUPPLY +2; voids stay counted for DSR honesty) →
2 survivors (insider — weak-positive, promoted; gp-small — confirm-tier
PASS) + 1 surviving fusion. **INSTR-HOLD-HORIZON answered "how long to
hold": FLAT 14-17 bps/mo net across 1-24mo hold-bands, 12mo gentle optimum —
signal-band exits make long holds free (sell when the name exits the band,
not on calendar/stop-loss).** **Batch 6 + BRAIN-009 ADJUDICATED same day (→ 130 cumulative): ZERO
graduates.** The dtc mirrors posted the factory's best-ever largemid net t
(3.4/3.0) and FAILED the IC leg — the two-legged rule held under maximum
temptation. inst-persist mirror refuted (both tails lose to the middle).
cust_conc = 4th sign reversal, book-inspected clean (IC t −7.4, Dhaliwal
side). Insider clusters add nothing over single opportunistic buys (BRAIN-009
closed; FF6 alpha t 3.0 is vs factors, not vs the single-buyer universe).
Round-3 panel adjudicated (`AI_PANEL_2026-07-24B.md`): horizon-first
registration rule adopted; accruals/supply-chain/news/RL re-litigations
refused. **2026-07-25: WRDS batch 4 HARVESTED (ibes_adj, funda ext cols,
dsf pharma daily, BoardEx starters, comp_pit). Batch 7 → cumulative 140:
conc_low GRADUATED explore (first since gp-small) then DIED at confirm
(TRIAL-BRAIN-010 KILL, DSR 0.0003) — first live-fire validation of the
explore/confirm wall (NEG_RESULTS §13); RE/ME strong-prior failed the bar
(value's decade); conc family closed both directions.** Unblocked next:
tgt-price rebuild (ibes_adj), FDA daily-CAR (dsf), BoardEx signal design,
Batch-4 macro instruments (daily harness)
+ 1 forward lane LIVE (SMQ). Unifying lesson: only low-turnover signals
survive honest costs (NMV recipe, independently rediscovered by our own scans).
**2026-07-25 PM (panel round 4, `AI_PANEL_2026-07-25.md`): Batch 8 = ZERO
graduates (→ 146 cumulative): si_trend IC-real/net-dead (turnover kill, as
declared), rd_gp book-without-rank (AND-rule), pead_agree INVERTED (IC t
−2.6 = 5th sign reversal; monthly-cadence PEAD closed). SIGNAL_TAXONOMY
adopted (4-tag registration rule; ranked family map in the module).
INSTR-OVERFIT-CEILING run (self-deception ceiling measured on the closed
library — see module trial doc). Amendments: INSTR-REGIME-HMM → statistical
jump model (Shu-Yu-Mulvey 2024, verified); NEW INSTR-SBCORR (stock-bond
60d correlation regime gate, descriptive); tgt rebuild inherits
dispersion-conditioned design (Palley-Steffen-Zhang MS 2025); BoardEx prior
weakened (centrality alpha may be beta — Mgmt Sci). Refused: payout,
divergences, conditional conc, hold-horizon duplicates.**

## Batch 4 — macro-regime & cross-asset (registered 2026-07-24; RUN 2026-07-25)

**Status 2026-07-25 EOD:** daily harness BUILT (`aegis_brain/macro/` in the
module); explore AND held-out confirm run one-shot (`INSTR-MACRO-BATCH4.md`).
**INSTR-REGIME-JM (jump model) = REJECT at confirm** (2022 TLT trap −21.6%,
2020 missed rebound; explore pass was one crisis in disguise; NEG_RESULTS
§15) — regime rotation with a single safe asset CLOSED. **INSTR-TSMOM-XA =
CONFIRM PASS, first macro survivor** (2020 +9.2%, 2022 flat; overlay DD
−18.8% vs SPY −33.7%; return drag t −1.86 disclosed → DEFENSIVE diversifier,
Goal B) — next: forward paper lane, attended seed. SBCORR gate claim refuted
in-window; GPR spikes not a sell signal (both descriptive receipts to the
brain layer). **Build 2 same day: TRIAL-BRAIN-011 FDA daily-CAR REJECT
(t 1.45 vs bar 2.0; attention gate refuted in its own arm; family closed
both resolutions, NEG_RESULTS §16). Round-6 brain review: prior-check gate
ADOPTED (`scripts/prior_check.py`, procedural registration requirement);
vector-DB/graph infra refused at current corpus size. Queued: Build 3 tgt
rebuild → INSTR-REGIME-JM2 (post-hoc-repair provenance declared) + batch-10
(zombie/rate-cut exclusion screen, insider role-weights) → TSMOM forward
lane seed (attended).**

**2026-07-26 (self-directed sweep, `RESEARCH_SWEEP_2026-07-26.md`): Batch 9
= 0 graduates (→ 152): conn_mom = starkest paper-vs-cost gap on record
(lit t 9.67 → net t −0.78 at 67% turnover); industry_mom flat-since-2000
confirmed; comp_issue_5y reinforces the issuance shelf (1.15/2.86).
INSTR-VOC: complexity claim NOT SUPPORTED (loses to B&H both windows,
non-monotone) — complexity class barred from the factory. Gates killed 3
candidates pre-registration (low-beta, NOA, ea_prem). Banked: OSAP
SignalDoc (calibration benchmark). Newly queued: INSTR-ANOMALY-TIME
(rdq-timing upgrade for the gp-small survivor — TOP priority),
INSTR-CZ-CALIB, INSTR-HARNESS-VALID, Chen-Velikov cost-model port.**

**2026-07-26 PM (panel round 7, `AI_PANEL_2026-07-26.md`):
INSTR-ANOMALY-TIME executed same day — PASS + UPGRADE, the factory's first
UPGRADE-class verdict (#153). EAD/rdq availability ADOPTED for the module
fundamentals stack: confirm t 0.89→1.24, +24.1→+33.5 bps/mo; disclosed
decomposition = book +2.7 bps/mo (weak) + benchmark-composition +6.8.
Adoption rests on PIT-correctness + costless weak-positive, not the
headline. Round-7 reviewer hypotheses: idio-skew and CF-volatility =
closed-family re-litigations (refused with receipts); inventory-EAD retry
now admissible; Chen-Velikov cost model endorsed (queued build). prior_check
hardened (word-split + stems) after a whole-phrase near-miss. Remaining
queue order: Build 3 tgt rebuild → INSTR-CZ-CALIB / INSTR-HARNESS-VALID →
batch 10 → TSMOM lane seed (attended).**

**2026-07-26 EOD (panel round 8, `AI_PANEL_2026-07-26B.md`): Build 3
TRIAL-TGT-REBUILD executed — REJECT, family closed (#154-155, cumulative
155). Raw target upside strongly perverse (t −3.62/−7.21); PSZ
dispersion-conditioning direction real, sign never positive (NEG_RESULTS
§17). Analyst-source pickers 0-for-3. Round-8 adoption: **GPT's Layer-2
argument → INSTR-REGIME-ANALOG queued** (deterministic k-NN historical
state retrieval, descriptive phase first, LLM narrates never allocates) as
the post-freeze Brain direction; NN-for-trading refused by all four
reviews (VOC receipt); DeepSeek's hallucinated receipts corrected
(INSTR-REVERSAL nonexistent; sentiment PIT-barred not tested-dead).
Gemini's ordering answered: calibration pair BEFORE cost model. Queue:
CZ-CALIB + HARNESS-VALID → Chen-Velikov → JM2 + REGIME-ANALOG → batch 10
(if ceiling-sensible) → ceiling ~196 → freeze → paper.**

**2026-07-26 night: calibration pair EXECUTED. HARNESS-VALID: 3/3 proxy
bars met vs French (0.927/0.778/0.645) — plumbing validated, Chen-Velikov
unblocked. CZ-CALIB: rank corr(|OSAP t|,|our t_ic|) = −0.544 (p 0.055) —
published-t is a CONTRARIAN indicator of current-window strength (sign
agreement 0.923 + harness pass = decay, not defect; median level ratio
0.378). PIT posture confirmed for Murat: forecasts/events all as-of-dated;
historical news backtests deliberately absent (forward-only); batch-10
stub added: 8-K event-flow family (EDGAR item codes = PIT-safe structured
news — the honest route to the day-by-day-news thesis).**

From the 5-AI panel adjudication (`docs/research/AI_PANEL_2026-07-24.md`):
four models independently converged on the chunk-5 allocation layer. Every
adopted claim became an instrument; nothing already adjudicated was reopened
(accruals = inverted, batch 2; supply-chain monthly = dead, batch 3b; news
sentiment backtests = barred by PIT policy).

| Instrument | Question | Gate notes |
|---|---|---|
| INSTR-REGIME-HMM | Causal 3-state regime rotation SPY/TLT/GLD vs buy-and-hold, explore 2004-2018 / confirm 2019-2024 | **AMENDED 2026-07-25: primary spec = statistical JUMP MODEL (Shu-Yu-Mulvey JAM 2024 — jump penalty forces regime persistence, kills HMM whipsaw); causal/expanding unchanged**; DSR-deflated vs cumulative count |
| INSTR-TSMOM-XA | 12-1 cross-asset TSMOM overlay (SPY/TLT/GLD/USO, vol-scaled) — crisis alpha without killing full-period return | Subsumes the chunk-5 trend-overlay item; "trend rescues momentum selection" stays CLOSED (#14) |
| INSTR-GPR-EVENT | Descriptive CAR(0,+30) of SPY/USO/ITA around >2σ daily GPR spikes | GPR revisions caveat disclosed; start Monday snapshots of the daily file NOW (PIT-forward) |
| INSTR-DOD-FWD | Forward-only DoD award drift (war.gov RSS, 17:00 ET pubDate) | Historical arm REJECTED on data (USAspending ~90-day OPSEC delay, no announcement timestamps); design note only until attended collector add |
| INSTR-SBCORR (added 2026-07-25, panel round 4) | Descriptive: 60d rolling SPY/TLT correlation as an inflation-regime gate; behavior of GLD/USO conditional on positive-correlation flips | Descriptive first (never arms); dailies on disk; registration with the daily-harness build |

Data prerequisite (small): daily ETF closes (SPY/TLT/GLD/USO/ITA) — nothing
daily exists on disk; GPR daily/monthly .xls (free, URLs verified 2026-07-24).
Later candidate (not this batch): INSTR-QUALDIP — quality-conditioned crash
deployment into the SMQ book (legitimate NEW candidate per the batch-1
dip-buy closure note).

## WRDS shopping list (next attended session, Duo tap)

1. `ibes.adj` (or CRSP `cumfacpr`) — un-voids the target-price family rebuild.
2. `comp_pit` exploration (catalog-confirmed accessible).
3. **BoardEx starter set — subscription CONFIRMED LIVE 2026-07-24 (HKU email).**
   Org/company summary + individual profiles + networks tables. Signal class:
   board-connection lead-lag, director-network-informed insider filtering,
   boardroom centrality (Larcker-So-Wang) — all low-turnover, i.e. the class
   that survives our costs.

Murat's directive: "test hundreds of simple strategies, build the brain from
the ones that work, beat SPY, and make the Average-Joe terminal." Adjudicated
against three AI reviews in `docs/research/AI_PANEL_2026-07-22.md`; research
protocol in `Aegis module/docs/STRATEGY_FACTORY.md`.

**The two goals are separated on purpose** (they need different machinery):
- **Goal A — alpha:** a confirmed, forward-verified edge vs the market.
- **Goal B — product:** the copilot that protects/improves an average
  investor's portfolio. Valuable even if Goal A takes years.

## The honest ledger on "beat SPY" (status 2026-07-22)

- Backtests (QC-confirmed): lane mandates trail SPY by construction across a
  bull decade — expected, pre-committed, not a failure of the engine.
- Paper lanes (43 days): all within noise; conviction lane −10.8% (one
  position, SOC, −10.6pp of it — a sizing lesson, not a selection lesson).
- One survivor signal exists (BRAIN-003 opportunistic insider, weak-positive
  prior, forward clock to 2027-07-21). Nothing else has cleared the bar yet.
- Beating SPY needs BOTH cross-sectional skill (factory survivors) AND an
  allocation layer (concentration + trend/exposure management). Chunks 1-4
  build the first; chunk 5 builds the second.

## Chunks

### Chunk 1 — Strategy Factory, batch 1 (price/volume) ✅ 2026-07-22
Explore/confirm protocol frozen (`baae546`); scan harness + 20 signals
(incl. Murat's dip-buy, 50%-dropper, steady-winners theses vs the
literature's 52wk-high side) × 2 cap segments on CRSP 2004-2018; confirm
window 2019-2024 held out; 40 candidates logged for DSR deflation.

### Chunk 2 — Factory batch 2: fundamentals/quality (next research session)
From the local Compustat harvest (no new data needed): gross profitability
(Novy-Marx), asset growth, accruals, net share issuance, F-score-lite,
earnings stability. This is the literature's net-of-cost survivor class and
the missing "will they still be making money in 5 years" leg of Murat's
intuition. Same protocol: pre-register batch → scan explore window → rank.

### Chunk 3 — Factory batch 3: events/alt-data
Insider×momentum interactions, PEAD refinements, congress (data exists),
13F best-ideas (best evidence-backed follower play), FDA event-drift
(sponsor→ticker mapping buildable offline), and TRIAL-THEME-SUPPLY —
Murat's suppliers-vs-appliers headline thesis, runnable at CRSP paper grade.

### Chunk 4 — Confirm + fusion
Each graduate: ONE pre-registered confirm run on 2019-2024, DSR deflated by
cumulative candidate count. ≥2 confirmed survivors re-opens BRAIN-007 fusion
(weights pre-registered before seeing singles). Optional robustness: extend
the CRSP pull to 1980 and re-run confirmed graduates once (one WRDS pull).

### Chunk 5 — Allocation layer (the actual "beat SPY" machinery)
- Trend/managed-futures overlay trial (the one diversifier with 100+ years of
  out-of-sample evidence; also fixes "rode SLDP down" — exit discipline).
- Concentrated best-signal paper lane (top-N from confirmed survivors, ~10%
  position cap — the SOC sizing lesson) seeded attended via seed-a-lane.
- Both forward-clocked; no skill claims before the clocks say so.

### Chunk 6 — LLM brain v2 (perception + memory, never allocation)
- Event extraction at scale into the ledger (earnings calls, 8-K, news) with
  calibrated probability calls, Brier-scored like the PDUFA ledger.
- Episodic memory: index past episodes (COVID, tariffs, GLP-1) → "last time
  X happened, these industries moved" retrieval for the narrative layer.
- Thesis generator: LLM proposes factory candidates (with mechanism); every
  proposal becomes a pre-registered scan, closing the loop Murat asked for
  ("the brain improves itself") without free-running on returns.

### Chunk 7 — Average-Joe copilot (product; parallel to research)
Mostly UX unification of what aegis-finance already serves:
- Holdings-first flow: paste portfolio → health score, per-stock columns
  (forecast, risk, buy/hold/sell + WHY in plain English), concentration and
  "smart money" flags (insider/congress/13F on YOUR names).
- Discovery: winning stocks by theme/industry, who-holds-what drilldown.
- Sell discipline (Murat's Micron/SLDP pain): target-proximity and
  trailing-drawdown alerts with plain-English trim suggestions.
- Daily news → portfolio impact briefs (LLM explains, cites, never orders).

## Standing duties (calendar)
- PDUFA ledger scoring: first event 2026-07-26 (SCPH), scoreable ~late Aug
  2026 via `scripts.ledger_score`; then next event batch.
- Quarterly CMP artifact refresh (~Oct 2026) + SMQ book refresh (~Oct 2026).
- Forward clocks: TRIAL-CMP-INSIDER-IC earliest decision 2027-07-21;
  TRIAL-SMQ-FWD earliest decision 2028-07-22; lane track record 24-month rule.

## Prod hygiene found by 2026-07-24 recon (→ BACKLOG)
- `/api/health/full` track_record block omits the smallmid-quality lane
  (hardcoded-lanes visibility bug pattern, again) — monitoring via health/full
  or aegis_verified_state cannot see SMQ NAV.
- ALL non-reference lanes' paper_nav rows are stamped with the reference
  config hash (`mark_lane_to_market` uses global `get_config_hash()`), not
  their own lane hash — weakens the hash-flip segment invariant; fix touches
  the sacred write path → design note + lane-integrity-check before/after.
- insider_cmp collector state is INFO-only (unobservable from public surface);
  add an IC-collector last-run/last-snapshot health section.
- yfinance "No earnings dates found" errors across ~15 large tickers in prod
  logs — new pattern, likely a yfinance API change; triage.
