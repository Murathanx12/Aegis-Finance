# TRIAL-ARK-IC — ARK daily holdings flow (forward IC)

> **Pre-registered 2026-07-11.** External-investor decision data, phase 2
> (T12): ARK Invest publishes each ETF's full holdings EVERY trading day —
> the only free, official, DAILY stream of a real active manager's decisions.
> Validated forward only (T7). Descriptive only; never arms a lane.

## Why this source

Congressional disclosures (TRIAL-CONGRESS-IC) arrive on a ≤45-day lag; ARK's
CSVs are published same-day, so share-count *diffs* between consecutive days
are attributable manager trades with ~zero disclosure lag. Honest prior:
**weak-to-null and possibly NEGATIVE** — the literature on copying ARK flows
post-2021 is unflattering (crowding, price impact, poor subsequent returns);
a negative IC would itself be usable knowledge. We measure it.

## PIT discipline

`as_of` = the CSV's own file date (the trading day the holdings describe);
`observed_at` = UTC collection time. Diffs are only ever computed between
snapshots that were both observable — no backfilled history (ARK does not
serve it; the archive builds forward from today).

## Data (phase 1 — accruing now)

`ark_shares:{FUND}:{ticker}` — raw share count per fund per holding, snapshot
daily (deduped on unchanged). Funds (frozen): ARKK, ARKW, ARKG, ARKQ, ARKF,
ARKX. Non-equity rows (cash, empty tickers) excluded.

## Signal (frozen — computed once ≥21 sessions accrue)

    ark_score(ticker, t) = Σ_funds [ shares(t) − shares(t−21) ] / shares(t−21)

clipped to [−1, +1] per fund before summing (a new full position = +1, a full
exit = −1). Snapshot as `ark_score:{ticker}`. No dollar weighting (share
counts are the manager's own sizing); no fund weighting. The score stays
UNWRITTEN until a 21-session baseline exists — an early score would be
false-neutral zeros.

## Estimator & decision rule

- **Primary metric:** forward rank-IC (Spearman) between `ark_score` at *t*
  and forward return at 21/63/126d, block-bootstrap CI (same estimator as the
  sibling IC trials).
- **Adopt:** IC ≠ 0 with 95% CI excluding 0 at ≥1 horizon over ≥6 months with
  median cross-section ≥ 25 names, then `evaluate_candidate`. (A robustly
  NEGATIVE IC is also an adoption of the *inverse* reading as descriptive
  context — recorded as its own successor trial, never silently flipped.)
- **Reject:** CI covers 0 at all horizons after 12 months of scores.
- **Earliest decision:** 6 months after the FIRST `ark_score` snapshot
  (expected ≈ 2026-08-10 + 6mo ≈ 2027-02-10; the actual date is fixed by the
  first score row).
- **Crash-event override / contamination clause:** same as TRIAL-CONGRESS-IC.

## What this rule may NOT do

- Arm, size, or gate any lane; no buy/sell framing.
- Change funds, window, clipping, or estimator mid-trial.
- Enter the multifactor composite before adoption.

## Status

- ✅ 2026-07-11: all 6 fund CSV endpoints verified live (assets.ark-funds.com,
  yesterday's date, clean schema). `ark_holdings.py` fetch+parse (fail-loud:
  HTTP error, empty CSV, and header-drift all raise) + `ark_collector.py`
  daily raw-shares snapshots + guarded score writer, wired in
  `scheduler._daily_check`, registry row via `ensure_ark_trial`.
- ⬜ 21-session baseline accrues → first `ark_score` rows (~mid-Aug 2026).
- ⬜ First monthly IC read (reported only).
