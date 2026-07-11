# TRIAL-CONGRESS-IC — Congressional (STOCK Act) trading disclosures (forward IC)

> **Pre-registered 2026-07-11.** External-investor decision data, phase 1: the
> only free, official, timestamped stream of *individual investors'* trade
> decisions is the STOCK Act disclosure feed. Validated forward only (T7: no
> backtest on survivor data certifies alpha). Descriptive only; never arms a
> lane.

## Why this source

The project accumulates decision data but has few users; congressional
disclosures are a public stream of real, attributable investment decisions
with a legally mandated timestamp. Prior literature is **mixed**: pre-2012
studies found abnormal returns for congressional purchases (Ziobrowski 2004,
2011); post-STOCK-Act studies largely find the edge faded (Belmont et al.
2022). The disclosure lag (≤45 days) further stales the information. **Honest
prior: weak-to-null positive IC on purchase clusters at 63/126d.** We measure
it instead of assuming either way.

## PIT discipline (the point of the design)

The knowledge time is **disclosureDate** — the day the public could have known
— never transactionDate (trades are disclosed up to 45 days late). Scores are
snapshotted into the PIT store with UTC `observed_at`, so the IC clock can
never accidentally "know" a trade before Congress disclosed it.

## Signal (frozen)

`compute_congress_scores` (`backend/services/congress_trades.py`):

    congress_score = n_buy_members − n_sell_members

per ticker, over disclosures with `as_of − 90d < disclosureDate ≤ as_of`,
where `n_buy_members` / `n_sell_members` count DISTINCT members (senateID)
with ≥1 purchase / sale of the ticker's common stock in the window. Distinct
members, not trade counts — the documented effect is *cluster* buying, and one
member splitting an order must not look like conviction. Common stock only
(assetType filter); ETFs, bonds, options excluded from the headline score but
counted in the payload.

**Frozen parameters:** window 90d; universe = tickers with ≥1 qualifying
disclosure in-window, capped at the 150 most-active by trade count; source =
FMP `senate-latest` + `house-latest` (both chambers, always). No amount
weighting (brackets are too coarse); no member weighting; no committee
mapping. None of these may be tuned mid-trial.

## Estimator & decision rule

- **Primary metric:** forward rank-IC (Spearman) between `congress_score` at
  *t* and forward return at 21/63/126d, block-bootstrap CI, cross-section size
  reported each period. Same estimator as the sibling IC trials
  (TRIAL-REVISIONS-IC etc.) — everything else reported, never deciding.
- **Adopt:** forward IC > 0 with 95% CI excluding 0 at ≥1 pre-registered
  horizon over a ≥6-month window with median cross-section ≥ 30 names, then
  through `evaluate_candidate` (DSR/PBO deflation against the cumulative
  registry count).
- **Reject:** CI covering 0 at all horizons after 12 months, or the source
  degrading below a usable cross-section (median < 10 names over 3 months).
- **Earliest decision:** 2027-01-11 (6 months from first snapshot).
- **Evaluation cadence:** monthly reads, reported; decisions only at/after the
  earliest decision date.
- **Crash-event override:** SPY drawdown ≥ 20% in-window → decisions deferred
  until ≥ 6 months past trough.
- **Contamination clause:** a demonstrated FMP data defect (e.g. backfilled or
  re-dated disclosures) excludes the affected windows, documented in
  NEGATIVE_RESULTS.md; the trial is abandoned (not tuned) if the source proves
  non-PIT-safe.

## What this rule may NOT do

- Arm, size, or gate any lane; no buy/sell framing anywhere it surfaces.
- Be folded into the multifactor composite before adoption.
- Swap estimator, horizons, window, cap, or scoring mid-trial (annotations
  only; a change = abandon + successor trial).
- Claim "Congress knows" in any UI copy — it is a measured candidate, and the
  registered prior is that the edge is likely dead.

## Status

- ✅ 2026-07-11: signal + fetcher + forward collector built
  (`congress_trades.py`, `congress_collector.py` on the generic
  `pit_score_collector`), wired into `scheduler._daily_check`,
  weekly-throttled. Registry row via `ensure_congress_trial` (idempotent, at
  startup). Source verified live: FMP free tier returns both chambers with
  disclosureDate + transactionDate (checked 2026-07-11; GitHub
  senate/house-stock-watcher dumps found DEAD since 2021 and rejected).
- ⬜ First snapshot on next deploy's daily check → IC clock starts.
- ⬜ First monthly IC read (reported only).
