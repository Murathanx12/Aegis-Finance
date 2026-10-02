# TRIAL-CONGRESS-PTR-FWD-1: House PTR stock purchases, entered after disclosure (forward only)

**Registered 2026-09-30, before any return on these rows is computed. STATUS: REGISTERED_UNPOWERED (accrual only).** Licence `PRODUCT_EXPERIMENT`.
Zero capital. Descriptive only: never arms a lane, sizes a book or carries buy/sell language until it passes.

Resurrects: TRIAL-CONGRESS-IC (2026-07-11, FMP feed, cross-sectional score IC); new instrument: the official
House Clerk PTR PDFs read by `official_sources` (row-level disclosure date and `tradable_from_utc`), measured as
an EVENT study at the next open, not a monthly score IC. The FMP source is not used.

## Why forward only (the power statement)

`backend/data/optimus/official/tables/politician_trades.jsonl` held 855 rows on 2026-09-30, disclosed over 74
days (2026-07-15..09-27): 279 common-stock purchases with a ticker, 163 tickers, 50 members, median lag 23 days,
88% in the $1k-15k bracket; 25 tickers had purchases by two or more members. A 21-session market-adjusted
return on large caps has a per-event sd of roughly 7%. Detecting +0.5% per event at 2.8 SE needs about 1,500
independent events; the table grows about 1,400 purchases a year before de-duplication, and events are
clustered (same tickers, same members). **Reading these 279 rows now would be reading noise (MDE about 1.2%
per event even if independent).** The Senate is refused by source (403 + agreement form).

## Hypothesis (honest prior)

House member common-stock purchases, entered at the first US session open at or after `tradable_from_utc`,
earn a 21-session return above the market (FF-style value-weighted proxy: SPY total return when CRSP is
not available for the window). Prior: null to weakly positive (post-STOCK-Act literature finds the edge
faded; the 23-day disclosure lag stales it further).

## Primary metric (the one deciding number)

Mean over events of (stock return from the entry open to the close 20 sessions later) minus (SPY over the
same sessions) minus a round trip of 10 bps, with the SE clustered by disclosure week. One event per
(member, ticker) per 30 days; sales, options, funds and non-ticker assets excluded.

Reported, never deciding: the two-or-more-member cluster subset; sales as a mirror; the $15k+ bracket; 5-session.

## Decision rule

- **Earliest interim read (description only, no decision): 2027-04-01.** Checks that rows accrue, the entry
  timestamps are never before `tradable_from_utc`, and prints the running mean with its MDE.
- **Decision read: 2028-04-01**, or earlier only when the events-to-date MDE falls below 0.5%.
- Adopt (for a CAPITAL_CANDIDATE review, not a book): mean > 0 with t >= 2 at the decision read and > 0 in
  each of the two halves by disclosure date.
- Reject: t <= 0 at the decision read, or fewer than 800 de-duplicated events by 2028-04-01 (source
  degraded: POWER, not refuted).
- Contamination: a disclosure-date or tradable-time defect in `official_sources` voids the affected rows,
  never shifts them earlier.

## Frozen parameters

Entry at the open at or after `tradable_from_utc`; horizon 20 sessions after entry; benchmark SPY; 10 bps
round trip; one event per member-ticker per 30 days; purchases (`tx_type` starting "P") of `asset_type` ST
with a ticker. None may be tuned before the decision read.

## What this rule may NOT do

It may not trade, size, weight or rank anything; it may not appear in a digest as a "signal"; an interim
read may not stop, extend or modify it; rows disclosed before 2026-09-30 are excluded from the decision
(they were looked at while writing this file).

Search count: +1 at registration: 42,705 = 42,666 + 19 investable + 8 vol-managed + 8 insider event + 3 ledger nightly cells + this row.

## Power fields

- declared_effect_size: 0.5pp per event over 20 sessions, net of a 10 bps round trip
- event_frequency_per_year: 700 independent events (about 1,400 raw purchases before the member-ticker 30-day de-duplication)
- outcome_dispersion: 7pp per event over 20 sessions (large caps; clustering by week inflates the SE)
- corpus_years: 1.5 (2026-10 to the 2028-04-01 decision read)
- dependence_unit: one disclosure week (members file in batches and buy the same large caps, so events inside a week share the market move)
- cross_sectional_n: 15 events per week on average
- cluster_size: 5 (same ticker bought by several members, or one member filing several purchases at once)

## Linter verdict at registration (Aegis module `scripts/lint_prereg.py`, 358 prior experiments)

**UNPOWERED_AT_REGISTRATION.** With a disclosure week as the dependence unit, the corpus supplies about 14
effective observations by the decision date against 1,538 needed for 0.5pp; the smallest resolvable effect is
5.2pp. This is recorded, not argued away: the file registers the ACCRUAL (the table keeps growing at $0 and
the timestamps are frozen now) and the first read date. The 2028-04-01 read may decide ONLY if the realised
effective sample makes the MDE at most 0.5pp; otherwise its verdict is NOT_DETECTABLE (POWER), never a
refutation, and the trial is either extended by a dated amendment or retired.
