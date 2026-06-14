# TRIAL-002 — Portfolio-mirror lane vs Aegis rules

**Pre-registered:** 2026-06-14 (BEFORE any inception row exists — tamper-evidence, same pattern as TRIAL-001). **Purpose:** portfolio-mirror. **Status:** pre-registered; lane not yet seeded (attended write-path session).

## Hypothesis

**Aegis's rules add value over Murat's actual allocation on the same book.** The
mirror lane is seeded from Murat's real current holdings, then managed by Aegis
config v2 (leakage-safe HRP, balanced cadence) from inception forward. It answers:
"on Murat's own 12 names, does the rules engine beat buy-and-hold of his allocation?"

## Seeding discipline (critical — must not deviate)

- **Inception = TODAY (2026-06-14) at CURRENT market prices, normalized to $100k.**
- **Share counts are ground truth**; the engine fetches live prices at seeding and
  computes current-market-value weights. Do NOT use historical buy prices. Do NOT
  invent a past inception date — that is look-ahead bias, the contamination this
  project refuses.
- **Murat's prior personal return is OUT OF SCOPE** — unverifiable (no dates/cash
  flows), it can never enter the forward record. It is motivation to measure, not
  a measurement.

## Holdings (confirmed 2026-06-14, 12 names)

SOC 700 · DKNG 150 · NTLA 250 · AARD 1000 · BHVN 300 · HUBS 10 · KYTX 250 ·
PRCH 200 · QUBT 200 · AMSC 50 · ABSI 600 · SLDP 600.

## Decision rule

- **Primary metric:** full-window net Sharpe from daily `paper_nav` returns, mirror
  lane vs the **balanced** reference lane.
- **Min window:** 12 months; earliest decision 2027-06-14; quarterly cadence after.
- **Secondaries (reported, NOT deciding):** max drawdown, annualized vol, Calmar,
  turnover, transaction costs, tracking error vs the book.
- **No skill claim before 24 months.** A ~12-name concentrated small/mid-cap book
  has enormous variance; mirror-vs-balanced will swing wildly and means nothing for
  many months. The no-skill-claims footnote governs all display.

## Registry / guards

Registered at seeding (cumulative trials 3→4 with TRIAL-003 →5). Mirror and
conviction lanes are **correlated** (same underlying book) — raw N is the DSR gate
floor; T2's effective-N (`effective_independent_trials`) reports the participation
ratio so the correlation is visible. Verify N_eff counts these correctly at seeding.

## UI note (both lanes)

"Inception 2026-06-14 at current holdings; prior personal performance is not part
of this record."
