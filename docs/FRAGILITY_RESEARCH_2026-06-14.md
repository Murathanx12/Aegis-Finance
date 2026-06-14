# Deep Research — Fragility, Data Sources, Brain & Discipline (2026-06-14)

> Adversarially-verified web research (107 agents, 25 sources, 94 claims → 25
> verified, **0 refuted**, 8 synthesized). Run from the validation-session context.
> Companion to `DEEP_RESEARCH_2026-06-14_DECISION.md` (the earlier run). Confidence
> labels and votes are the workflow's; **time-sensitive Part-1 gauges that did NOT
> reach the confirmed set are flagged as OPEN, not asserted.**

## The headline (the crash hypothesis, answered honestly)

**Mixed, not unambiguously pre-crash — and the evidence does NOT support a
confident mid-2026 crash-timing call.** That is itself the most important result:
it is exactly what the validated "measure fragility, don't time crashes" thesis
predicts you should be able to say, and nothing more.

- **The IPO "glut" is not a glut by historical standard.** 2025 had **90
  operating-company IPOs** (vs **476 in 1999**, **311 in 2021**); first-day pop
  **29.3%** (vs **71.2% in 1999**). Rising, yes; mania, no. *(HIGH, 3-0.
  PwC Q1'26; Ritter dataset.)*
- **The real mania signal is in PRIVATE markets, not public equity.** Q1 2026 VC
  hit **$267B**, ~**$140B from two AI deals** (OpenAI $110B — largest private
  round ever; Anthropic $30B). Concentration is extreme *upstream* of the listed
  market. *(HIGH, 3-0. PwC/PitchBook/KPMG.)*
- **Secondary-market gauges remain OPEN** — Shiller CAPE, equity-risk-premium,
  Mag-7 / top-10 concentration share, margin debt, HY/IG OAS, MOVE, VIX term
  structure did **not** survive into the verified set this run (sources existed —
  e.g. margin debt reported at a record high April 2026 — but weren't
  adversarially confirmed). **Do not quote these as fact yet** (open question #1).

→ **Action:** the honest fragility readout needs the secondary-market gauges
sourced through the point-in-time layer and measured forward — not asserted from
an unverified single source. This is BACKLOG **V1** + **V3**.

## Part 3 — Methodology: what has skill (this is the validation)

| Measure | Verdict | Detail |
|---|---|---|
| **Absorption ratio** (Kritzman) | 🟢 **Validated fragility measure — keep** | "Near-necessary, not sufficient" for severe drawdowns: 100% of 1%-worst monthly drawdowns (1998-2010) preceded by a 1-SD AR spike. Authors frame it as **fragility, not a crash predictor**. Caveat: that stat is in-sample/descriptive. *(HIGH, 3-0)* |
| **Financial turbulence** (Mahalanobis) | 🟢 **OOS vol skill, but COINCIDENT** | Beats AR out-of-sample for volatility forecasting (GARCH-MIDAS, 7 economies), **but peaks *during* crises, not before** (BCD-AUC 0.605). Use de-risk-on-**persistence** (Kritzman-Li 2010), not as a leading trigger. *(HIGH, 3-0)* |
| **LPPL / log-periodic** (Sornette) | 🔴 **Refuted — keep descriptive-only** | Fitted ranges held for only **7 of 11** crashes; posited mechanism held for ~half of bubbles. A 2025 Nature paper contests this but is itself a single in-sample backtest (the overfitting genre we warn against). *(HIGH, 3-0)* |

**Consensus: measure fragility, do not time crashes.** This is a direct external
validation of canon A5 and of keeping the crash overlay dark. Aegis's fragility
composite already uses absorption + turbulence — **the one refinement the research
demands: label turbulence as coincident and weight absorption (leading) for any
forward read.**

## Part 4 — The brain: process-learning beats P&L-learning (validates A2)

- **"Profit mirage" confirmed and extended.** Backtested LLM returns evaporate OOS
  past the knowledge cutoff because agents **memorize outcomes (and ticker
  identity)**, not causal drivers. *(HIGH, 3-0; one sub-claim 2-1.)*
- **New hard number (KTD-Fin, arXiv 2605.28359, May 2026):** under blinded
  evaluation, **Claude Opus 4.7 = +58.80% total return but only +0.2% selection
  alpha; 9 of 10 models had *negative* selection alpha** despite positive
  cumulative returns — returns collapse into style-factor harvesting. Corroborated
  by StockBench (most LLM agents fail to beat buy-and-hold post-cutoff).
- **Implication for the Optimus brain (V5):** the firewall (forward-only,
  process-knowledge, never RL-on-own-P&L) is the *correct and necessary*
  architecture. FactFin's counterfactual-perturbation idea (force causal, not
  memorized, learning) is a concrete technique worth borrowing for the conviction
  lane's prompting.

## Part 5 — Overfitting discipline (validates the guards + M2)

- **CPCV with purging/embargo is the best-documented defense** — lower PBO, higher
  Deflated Sharpe than K-Fold, Purged K-Fold, and **especially Walk-Forward**
  (Arian/Norouzi/Seco 2024, *Knowledge-Based Systems*). *(HIGH, 3-0.)*
- **Caveat that matters:** Walk-Forward is still better for *realistic live-trading
  simulation*; CPCV can't anticipate true structural breaks; off-by-one purging
  bugs silently leak. → For **M2** (the crash-Brier error bar): a block-bootstrap
  CI ships today; routing through CPCV is the stronger second pass, implemented
  carefully.

## Part 2 — Data sources: only SEC EDGAR verified this run

**SEC EDGAR (`data.sec.gov`)** — 🟢 verified, free, no auth/API key:
- **Rate limit: 10 req/s** (exceeding → ~10-min IP block). **Must** send a
  descriptive `User-Agent` (app name + admin email) and accept gzip/deflate.
  **No CORS**, no SEC support for scripted access. SEC blocks default fetcher UAs
  (403) — enforcement is active.
- **Latency:** filings after 5:30pm ET disseminate next business day;
  **ownership Forms 3/4/5 after 10:00pm ET → next day**; indexes rebuilt nightly.
- Covers 13F, Form 4, and XBRL financials (10-K/Q, 8-K, 20-F/40-F/6-K).
- → Folded into `V3_DATA_LAYER_DESIGN.md` priorities 1-2 & 7 (EDGAR-sourced).

**Still OPEN (open question #2):** Congressional/STOCK Act feeds, options chains
(IV skew/gamma/put-call), breadth (%>200dma, A/D), sentiment surveys (AAII/NAAIM/
Fear&Greed). Finnhub's congressional endpoint appeared but scored unreliable.
A focused follow-up research pass on these is owed before building those collectors.

## Open questions carried forward (the honest debt)
1. Current secondary-market fragility values (CAPE, ERP, Mag-7 share, margin debt,
   OAS, MOVE, VIX term) + their percentiles/analogues — **unverified**.
2. Non-EDGAR data-source APIs/limits/ToS (congress, options, breadth, sentiment).
3. Quantitative magnitude of the profit-mirage OOS return drop (beyond the
   directional finding + the KTD-Fin example).
4. Concrete retail-horizon slippage-modeling recipe + bootstrap-CI recipe for a
   ~7-event Brier.

## Key new citations (not previously in canon)
- KTD-Fin memory benchmark — **arXiv 2605.28359** (May 2026) — selection-alpha
  collapse under blinding. *Adds a hard number to A2.*
- CPCV superiority — Arian, Norouzi M. & Seco (2024), *Knowledge-Based Systems*
  S0950705124011110. *Backs the CPCV-for-M2 direction.*
- Salisu, Demirer & Gupta (2022), *Global Finance Journal* S1044028322000011 —
  turbulence/AR OOS volatility skill.
- ORCA regime paper — arXiv 2604.17251 (Apr 2026) — turbulence coincident, AR
  "strongest classical baseline."
- Brée & Joseph (2013) S1057521913000719 — LPPL refutation.
