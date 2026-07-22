# Investor Brain v2 — master roadmap (2026-07-22; status updated same day EOD)

## Status board (EOD 2026-07-22)

| Chunk | Status |
|---|---|
| 1. Factory batch 1 (price/vol) | ✅ CLOSED — 0 graduates; dip-buy theses rejected |
| 2. Factory batch 2 (fundamentals) | ✅ CLOSED — **BRAIN-008 gp-small: confirm PASS + 42-yr robustness** |
| 3. Factory batch 3 (events/alt) | 🔶 3a done (SI/congress/gemini/daily adjudicated), 3b running (customer momentum, best-ideas, tgt upside); remaining: FDA drift, buyback/spinoff (needs event data), theme BASKET arm |
| 4. Confirm + fusion | 🔶 **BRAIN-007 fusion SURVIVES** (beats best single, 3.6× names); remaining: INSTR-OVERFIT-CEILING |
| 5. Allocation layer | 🔶 **smallmid-quality lane SHIPPED (`bc0608f`, awaiting Murat's seed flag)**; remaining: trend/managed-futures overlay trial |
| 6. LLM brain v2 | ⬜ (event extraction at scale, episodic memory, thesis generator) |
| 7. Average-Joe copilot | ⬜ (holdings-first UX; most analytics already served) |

Scoreboard: 84 explore candidates → 2 confirmed survivors (insider, gp-small)
+ 1 surviving fusion + 1 forward lane awaiting seed. Unifying lesson: only
low-turnover signals survive honest costs (NMV recipe, independently
rediscovered by our own scans).

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
- PDUFA ledger scoring (first ~late Aug 2026) + next event batch.
- Quarterly CMP artifact refresh (~Oct 2026).
- Forward clocks: TRIAL-CMP-INSIDER-IC earliest decision 2027-07-21; lane
  track record 24-month rule.
