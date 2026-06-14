# V3 Data Layer — the point-in-time (as-of) store

> **The linchpin.** Created 2026-06-14 (BACKLOG V3). One decision makes three asks
> possible at once: (1) safe web-scraping, (2) leak-free paper-lane feedback, and
> (3) a compounding, uncopyable data moat. Skip it and scraped *current* values
> silently inject look-ahead bias into every backtest — the exact failure that
> would destroy the credibility this project has earned.

## The problem it solves
Today data is fetched live and used immediately. That is fine for a live read, but
it means we can never honestly ask "what did the engine *see* on 2024-03-01?" —
because FRED/yfinance return **revised** series, and a scraped value has no record
of *when we first saw it*. Every reviewer flagged "2 sources / thin data"; the
real fix is not just *more* sources but **timestamped** sources.

## Core contract
```
snapshot(key, value, as_of_ts, observed_ts, source, revision) -> id
get_as_of(key, as_of_ts) -> the value we WOULD have seen at as_of_ts
```
- **`as_of_ts`** = the date the value *refers to* (e.g. the CPI print's month).
- **`observed_ts`** = when *we* first recorded it (server clock). This is the
  anti-leak field: backtests read by `observed_ts ≤ test_date`.
- **Never overwrite.** A revision is a new row; the original observation is kept.
  This is what lets us reconstruct the world as it actually looked.
- **Backfill nothing.** History from APIs is already revised/contaminated. The
  store's value accrues *forward* — in a year it is a point-in-time macro/options/
  sentiment dataset nobody can retroactively reconstruct. That is the moat.

## Storage
Extend the existing PI SQLite (no new DB — anti-goal). One additive table:
```sql
CREATE TABLE pit_observations (
  id           INTEGER PRIMARY KEY,
  key          TEXT NOT NULL,        -- e.g. "fred:CPIAUCSL", "13f:BRK-A:AAPL", "ipo:count:weekly"
  as_of        TEXT NOT NULL,        -- ISO date the value refers to
  observed_at  TEXT NOT NULL,        -- ISO ts we recorded it (server)
  value        REAL,                 -- numeric payload (JSON blob column for structured)
  payload      TEXT,                 -- optional JSON for non-scalar
  source       TEXT NOT NULL,        -- "fred" | "edgar" | "scrape:fearandgreed" ...
  revision     INTEGER NOT NULL DEFAULT 0,
  UNIQUE(key, as_of, observed_at)
);
CREATE INDEX ix_pit_key_asof ON pit_observations(key, as_of);
```
Migration is additive + idempotent (the project's established pattern — see the v5
`effective_trials` migration).

## Ingestion rules (non-negotiable)
1. **API-first, scrape-last.** A scraper is only written when no free/official API
   exists.
2. **Every writer wraps `data_quality.py`** (staleness / range / completeness).
   Scrapers break silently — degradation must be **loud** (BACKLOG H5 class).
3. Each writer is a small idempotent collector run by the existing scheduler;
   writes a row only when the value or revision changed.
4. Provenance is mandatory: `source` + `observed_at` on every row.

## Source priority (the "track investors / firms / politicians" ask)
| Pri | Source | Key data | Access | Honesty label |
|---|---|---|---|---|
| 1 | **SEC EDGAR 13F** | institutional positioning (where the big players are) | free API (`edgartools` already a dep) | 45-day lag → **descriptive/regime**, not timing |
| 2 | **SEC Form 4** | insider buy/sell clusters | free API (have partial via Finnhub) | days lag; cluster-buy is the signal candidate |
| 3 | **Congressional trades** (STOCK Act) | politician disclosures | free filings / Capitol-Trades-style | **30–45 day legal lag → descriptive only**, never a timing call |
| 4 | **Options chains** | IV skew, P/C, gamma, VIX term | yfinance free / Tradier delayed | predictive at the short risk horizon — registered trial |
| 5 | **Breadth + sentiment** | %>200dma, A/D, AAII, NAAIM, Fear&Greed | mostly scrape | regime context |
| 6 | **Funding/credit** | SOFR, MOVE, repo | FRED-adjacent | extends NFCI/OAS |
| 7 | **IPO issuance** | S-1/424B volume, first-day pops | EDGAR + count feed | **the crash-hypothesis trigger** — enters fragility as a tested candidate (BACKLOG V1) |

## Verified source specifics (research 2026-06-14 — see `FRAGILITY_RESEARCH_2026-06-14.md`)

**SEC EDGAR (priorities 1, 2, 7) — confirmed, free, no API key:**
- **10 requests/second** hard cap; exceeding → ~10-minute IP block.
- **Mandatory** descriptive `User-Agent` (app name + admin email) + accept
  gzip/deflate. **No CORS.** SEC blocks default fetcher UAs with 403 — set ours.
- **Latency:** general filings after 5:30pm ET → next business day; **ownership
  Forms 3/4/5 after 10:00pm ET → next day**; indexes rebuilt nightly. Bake this
  lag into `as_of` vs `observed_at`.
- No SEC support for scripted access — wrap in `data_quality` and expect silent
  schema drift.

**Still unverified (focused follow-up research owed before building these
collectors):** Congressional/STOCK Act feeds, options chains (IV skew/gamma/PC),
breadth (%>200dma, A/D), sentiment surveys (AAII/NAAIM/Fear&Greed). Finnhub's
congressional endpoint exists but scored unreliable in the research pass.

## What it unlocks
- **V1 (crash answer):** IPO-froth, options-skew, valuation, leverage become
  *tested* fragility inputs — each a registered trial, each timestamped so the
  forward Brier is honest.
- **V4 (alerts + event lane):** the alert engine evaluates rules against the PIT
  store; the event-driven lane's forward NAV is leak-free *because* decisions read
  `observed_at ≤ decision_date`. This is the live proof the backtest can't give.
- **Paper racers:** lanes "compete against the market and the big players" by
  reading 13F/insider/congress positioning as context — measured forward, not
  curve-fit.
- **The moat:** competitors can copy the code; they cannot copy a year of
  point-in-time observations or the forward NAV. Both are functions of elapsed
  time already spent.

## Guardrails
- Politician/insider/13F data is **descriptive with the disclosure lag stated** —
  never presented as a timing edge.
- No source feeds a *signal* claim until it passes a registered IC/Brier trial
  (DSR/PBO deflated against the cumulative trial count).
- `paper_nav` write-path is untouched by this layer (read-only consumer).
