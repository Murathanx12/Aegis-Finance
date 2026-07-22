# Data-source survey — what to add, free vs paid (2026-07-22)

Murat's ask: "find more data; tell me if it's paid; strategies matter more."
Verdict up front: **the biggest unlocks are FREE — they're deeper pulls from
the WRDS subscription HKU already pays for.** Nothing needs buying today; two
cheap paid options become worth it only at specific future milestones.

## Tier 1 — free, high value, actionable now

| Source | What it unlocks | Strategy it feeds |
|---|---|---|
| **WRDS: Compustat Segment Customer File** | Customer-supplier links (SFAS 131: customers >10% of revenue), the exact data behind Cohen-Frazzini (2008) customer momentum | **TRIAL-THEME-SUPPLY** at paper grade — Murat's suppliers thesis |
| **WRDS: Thomson/Refinitiv 13F (s34)** | Institutional holdings HISTORY (vs our forward-only EDGAR parsing) | 13F best-ideas backtest (the one evidence-backed follower play) |
| **WRDS: CRSP pre-2002** | Extend panel to 1980 (or 1926) | Robustness re-runs of confirmed graduates only |
| **WRDS: FactSet Revere** (check if in HKU sub) | Higher-quality supply-chain graph | Upgrade for THEME-SUPPLY if available |
| **Congress archives (GitHub, free)** | 54k+ disclosed transactions 2012→present (senate-stock-watcher-data; congress-trading-monitor). Note: House Stock Watcher S3 is dead (403) — use the mirrored repos | **INSTR-CONGRESS-HIST** at $0 |
| **FINRA short interest** (free, bi-monthly) | Short-squeeze / crowding signals | batch 3 candidate |
| **CFTC COT reports** (free, weekly) | Futures positioning | trend/managed-futures lane context (chunk 5) |
| **SEC EDGAR full-text** (free, have) | 10-K principal-customer names (LLM-extractable), 8-K events | supply-chain graph fallback; LLM perception layer |

## Tier 2 — paid, each gated on a milestone (do NOT buy yet)

| Source | ~Cost | Buy when |
|---|---|---|
| **Sharadar Core US Bundle** (Nasdaq Data Link) | pricing not public; historically ~$50-100/mo range — [verify](https://data.nasdaq.com/databases/SEP) | We need DAILY-updated survivorship-free fundamentals for LIVE scoring at scale (WRDS annual cut ends 2024-12; fine for research, thin for live). Milestone: a confirmed fundamental survivor goes live |
| **Tiingo** | ~$10-30/mo individual — [pricing](https://www.tiingo.com/about/pricing) | Live news feed + IEX prices for the copilot product (news archive is 3mo on individual tier — NOT usable for backtests) |
| **Quiver Quantitative API** | ~$10-75/mo tiers | Only if free congress archives prove stale/dirty |
| **Polygon options / ORATS** | $29-199/mo | Only if an options-signal batch gets designed |
| **BiopharmCatalyst** | ~$40/mo | Convenience only; PDUFA hand-curation is free |
| RavenPack / Benzinga / FactSet direct | institutional $$$ | Skip (Revere possibly free via WRDS) |

## Explicitly rejected

- **EODHD** — failed survivorship acceptance gate 14/20 (NEG_RESULTS §8);
  renewal to be canceled.
- Any "historical news sentiment" backtest on free news APIs — coverage
  bias + no PIT timestamps; narrative signals validate FORWARD only (the
  Brier-scored event ledger), same rule as T7.

## Sources
- [Sharadar/Nasdaq Data Link](https://data.nasdaq.com/databases/SEP) · [Sharadar coverage](https://sharadar.com/) · [QuantRocket Sharadar notes](https://www.quantrocket.com/sharadar/)
- [Tiingo pricing](https://www.tiingo.com/about/pricing)
- [senate-stock-watcher-data](https://github.com/timothycarambat/senate-stock-watcher-data) · [congress-trading-monitor](https://github.com/kadoa-org/congress-trading-monitor)
- [WRDS linking suite](https://wrds-www.wharton.upenn.edu/pages/grid-items/linking-suite-wrds/) · Cohen-Frazzini customer-supplier literature ([Oxford RE overview](https://oxfordre.com/economics/display/10.1093/acrefore/9780190625979.001.0001/acrefore-9780190625979-e-631), [Customer Momentum](https://arxiv.org/pdf/2301.11394))
