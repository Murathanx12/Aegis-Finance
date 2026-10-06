# Adversarial review: C16 public-flow sensors (2026-10-07)

Reviewer: Opus 5.5, acting as data-quality officer and terms-minded operator. Read-only. I ran one live
read-only probe per source (USAspending transaction count, LDA, the Kalshi terms page). I did not edit
or commit anything.

## VERDICT: MERGE WITH FIXES

The plumbing is good: an append-only table, a PIT refusal, receipts named by run id, refusal classes,
and a DEGRADED rule. The build note is unusually candid, and it caught its own 742-row bug live. The
code is also not on any scoring path, so it cannot lose money by being merged.

It should not be **scheduled** yet. Merging the code is fine. Registering `AegisPublicFlow` is not,
until F1 to F3 are fixed. As configured, the daily job cannot see the agency the fiscal cell is about.
It still drops rows silently while labelling them "duplicates". Its "measured latency" is the age of a
backfill window, not a publication lag.

**RESULT IMPROVEMENT: NONE.** None of the three sensors can change a decision in the next 90 days
(section 9).

---

## Findings

### F1 (HIGH): the daily job is structurally blind to DoD and to every late-published row

`USA.pull()` defaults to `USASPENDING_DAILY_LOOKBACK_DAYS = 14`. The `time_period` filter is on
**action date**. The config comment says "late agency reporting lands inside it". That is false for the
agency this chunk is built around. A DoD transaction published on its ~90-day delay has an action date
about 90 days old on the day it appears, so a 14-day action-date window never contains it. The backfill
already shows this: **9 DoD rows in 90 days across six defence primes**.

Consequences:
- The daily table will under-count DoD permanently. It is not a lag that the job will eventually close.
- The note promises that "the real publication-lag distribution exists only from the daily incremental
  pulls onward". That distribution will be **censored at 14 days**.
- `fiscal_year_end_spending` names this table as its forward precursor, and the precursor will be
  missing exactly the Q4 DoD dollars.

Fix: query on the modification date (`time_period[].date_type = "last_modified_date"`; verify against
the API contract before relying on it), or run a rolling 120-day action-date window weekly. Record
`last_modified_date` on each row so that first sight can be compared with publication.

### F2 (HIGH): the 742-row bug is fixed, but its failure shape is still live (2 rows, receipt OK)

The second pull reports `rows_read 2,061 / rows_added 2,059 / duplicates 2`, with status **OK**. Both
duplicates are in the GENERAL DYNAMICS search: 637 read, 635 in the table.

My probe of `POST /api/v2/search/spending_by_transaction_count/` for the same filter and window
returned **`contracts: 637`**. So the API holds 637 transactions, we read 637 rows, and 2 of them share
a key. One of two things happened:
- **(a)** Pagination with `sort: "Action Date"` is not stable on a non-unique key. Two rows were served
  twice and two different rows were never served.
- **(b)** Two distinct transactions share `award|mod|date|type|amount`.

Either way, **two real GD transactions are not in the table**, and the receipt calls this harmless.
That is the same mechanism as the 742, at a smaller scale.

Fix: within one pull, a repeated key is an anomaly, not a "duplicate", so make it DEGRADED. Assert
`rows_read == count endpoint` per recipient. Add a unique tiebreaker to the sort, or page by date slices.

### F3 (HIGH): the published "latency" is the age of a 90-day window, not a latency

Every row in `gov_awards` has the **same** `first_seen_utc` (2026-10-06T21:50:32Z). The "median 41 d"
is therefore just the median age of rows in the window. Any 90-day window has a median near 45 days,
whatever the real publication lag. The note calls it an "upper bound", but it is not a bound on
anything except the window.

The only informative number is the **minimum (4 days)**, which says no transaction dated in the last
4 days was visible. Remove the median, p10 and p90 from the receipt headline, or label them
`window_age_not_latency`. The same applies to `latency_by_agency_median_days`.

### F4 (MEDIUM): the amount is part of the key, so a revised transaction becomes a second row

FPDS corrects transactions in place: amount, action type and date can change. The key
`generated_internal_id|Mod|Action Date|Action Type|Amount` gives a corrected record a **new** `row_id`.
The append-only table then keeps both, and dollar sums double-count. Deletions are never retracted.

Fix: key on the identity fields only (`generated_internal_id|Mod`, plus the transaction number if the
API exposes it). Store revisions as new versions with a `superseded_by` pointer, and never sum across
versions.

### F5 (MEDIUM): the receipt's dollar figure includes the duplicates

The receipt's `obligation_usd_mapped` is **$6,591,346,587.55**. The table's mapped sum is
**$6,591,196,887.54**, a difference of **$149,700.01**. The receipt sums `all_rows` before the dedupe.
A headline number has to come from the rows as written (`wr["rows"]`). LDA's `amount_usd_mapped` has
the same defect.

### F6 (MEDIUM): agency-month PIT is half done

- `pit_ok` for `gov_agency_month_obligations` checks `snapshot_date` against `first_seen`, which are
  always the same day. The check is a tautology.
- The real look-ahead risks are not guarded:
  - The current month is partial. FY2027 month 1 (Oct 2026) was snapshotted on 10-06 with `period_end`
    10-31, and it carries no partial flag.
  - Months inside the 90-day DoD window carry no per-row `settled` flag. Settledness exists only at FY
    level, and only inside `q4_share()`.
- `q4_share(rows)` groups by (agency, FY) and **sums across every snapshot passed in**. It also takes
  `settled` from the max snapshot across those rows. A caller that hands it `read_table()` after a
  month of daily snapshots mixes vintages, and the ratio silently becomes an average of revisions.
- No `as_of(t)` reader exists. The first runner will write one, and nothing pins it to
  `snapshot_date <= t`.

Fix:
- add `partial` and `settled` per row;
- make `q4_share` refuse more than one snapshot;
- ship `agency_months_as_of(t)` with a test that a later snapshot cannot change an earlier as-of read.

The shipped receipt shows DoD FY2026 at 1.0% with `complete: true` and has no `settled` field, because
it predates that flag. Its body is misleading as written, and its correction exists only in the note.

### F7 (MEDIUM): the crosswalk maps to today's owner with no dates, and some confidence labels contradict its own header

The header defines `medium` as "a recent spin-off / acquisition changed the owner". The file still
labels these entries **high**:
- LHX, whose patterns include AEROJET ROCKETDYNE (a separate listed company until 2023-07) and HARRIS /
  L3 (until 2019);
- RTX (ROCKWELL COLLINS until 2018-11, RAYTHEON COMPANY until 2020-04);
- LMT (SIKORSKY was UTX's until 2015-11).

CVS/AETNA and CI/EXPRESS SCRIPTS are correctly medium. There is no `valid_from` / `valid_to`, so a
backfill assigns, for example, FY2019 Aerojet dollars to LHX.

Today's 90-day pull is unaffected. Any history read is affected, and the fiscal cell hashes this file
as its universe.

**False positives on the prefix rule (plausible, not observed in data yet):**
- LDA `MERCK` matches "MERCK KGAA".
- `ANTHEM` matches unrelated "Anthem ..." firms (the note admits this, but the entry is still medium).
- `HONEYWELL` (high) matches "HONEYWELL FEDERAL MANUFACTURING AND TECHNOLOGIES". That is the NNSA
  Kansas City M&O contractor, the same kind of dollars the file labels **low** for Sandia.
- `FLUOR` (high) matches FLUOR MARINE PROPULSION (Naval Nuclear Laboratory M&O), with the same problem.
- LDA `JACOBS` matches Jacobs Technology clients, which belong to Amentum after 2024-09.

The prefix rule correctly keeps GENERAL DYNAMICS from matching DYNETICS. But **Dynetics is Leidos's**,
so it is a false negative.

The owners of the NOT_MAPPED subsidiaries are listed honestly; I agree they should not be added
post hoc. Not adding them post hoc does not make them right to leave out, though. QTC Medical (Leidos,
30 rows), CSRA, DynPort and Metro Machine (GD), Zeta (LMT), Aquilent (BAH) and Millennium Space (BA)
together make per-ticker dollars systematically low. Jeppesen ForeFlight is correctly *not* mapped,
since Boeing sold it in 2025, and that sale is the reason the file needs dates.

**Ticker reuse, measured in the gate's own universe (`fiscal_ye_universe()`, CRSP stocknames,
2008-10..2024-09):**
- `COR` pulls in **Cortex Pharmaceuticals** (2008-2009).
- `MRNA` pulls in **MDRNA / Marina Biotech** (2008-2012).
- `HEI` appears as **two permnos** (two share classes of one company, double-weighted).
- `PL` was Protective Life until 2015.
- Renamed names are lost before their rename: RTX before 2020-04, LHX before 2019-07, LDOS before
  2013-09, ELV before 2022-06, VVX before 2022-07, J before 2019-12. The universe therefore drifts
  toward today's names year by year. That is a composition bias in a cell whose unit is the FY.

### F8 (MEDIUM): the fiscal cell's gate passed on a unit the cell does not test, and the precursor cannot be known when the declaration says it can

- **Unit.** The gate counted **8,577 name-months**, with the control = 7,134 OTHER_MONTHS and an
  i.i.d. MDE of 0.83% against a 1.0% bar. The declared primary is **one basket per FY, 8 validate
  FYs**. The gate's pass therefore says nothing about the test that will be run. The declaration's
  `honesty` field says so, which is to its credit, but the gate still printed `ok`.
- **Back-of-envelope (an estimate, not measured).** A 2-month equal-weight contractor basket against
  the VW market has a common-component sd of roughly 3-5%. Over 8 FYs that gives an SE of about
  1.1-1.8% and an **MDE of about 3-5%, which is 6-10x** the 0.5% effect worth having. At the honest
  unit, the gate would REFUSE.
- **Precursor.** The text says fiscal-Q4 (Jul-Sep) obligations are "knowable before Aug 1". On Aug 1
  only July has happened, and DoD's July is not published until about October. Only *prior* FYs' settled
  Q4 shares are knowable, and those are a slow-moving agency trait with little year-to-year variation.
  The history backtest has no PIT precursor at all. In practice the cell is a **calendar anomaly
  conditional on GOVDOM presence**, and the "precursor" is decorative until at least FY2028.
- **Rule mismatch.** The generic `decision` text ("t on non-overlapping 3-month blocks", "strict
  majority of validate years") was copied in, but the primary series is a 2-month-a-year window.

### F9 (MEDIUM): terms

- **USAspending.** Public domain. Fine.
- **LDA.** The citation required by the API terms is on the receipt and on every row
  (`citation: "Senate Office of Public Records (LDA)"`). That honours the requirement. Keep the full
  sentence wherever the public tool displays LDA numbers.
- **Kalshi.** I could **NOT VERIFY** the clause first-hand. My direct fetch of
  `kalshi.com/developer-agreement` returned **429**, and a third-party fetch returned only the page
  shell. The spec quotes the agreement as prohibiting "collecting, caching, **aggregating**, or storing
  data ... except for purposes of facilitating your own trading". If that quote is accurate, the
  `derived_only` default **is the prohibited verb "aggregating"**. A daily per-meeting implied
  distribution is an aggregate of stored API data, so the default buys less protection than the note
  implies. The note's own sentence ("whether a derived aggregate is outside 'storing data' is a reading
  of Kalshi's terms, not a certainty") is the honest one. On the same quote, `none` is the only
  defensible default until the owner decides D18. Fetching and transient processing for display is the
  least exposed use. A persisted aggregate is not obviously in that category.
- **Factual error in the note.** It says TRIAL-PREDMARKET-1 "was persisting daily raw Kalshi snapshots
  in a public repository". The directory `backend/data/optimus/prediction_markets/` is **gitignored**
  (`.gitignore:162`), and `git log --all` shows no Kalshi snapshot ever committed. Locally there is
  **one** snapshot day (2026-08-21). So the exposure was smaller than stated. The trial is also not
  accruing locally at all, which makes "D18 costs the trial its Kalshi leg" mostly moot.
- **Public-flow tables are NOT gitignored** (`git check-ignore` returns nothing). The
  `public_flow/tables/*.jsonl` files and receipts would be committed to a public repo. That is fine for
  USAspending (public domain) and for LDA with the citation. For the crypto row, CoinGecko's free tier
  requires attribution and Binance/OKX restrict redistribution of market data. A daily scalar is tiny,
  but the decision should be explicit: gitignore the table, or keep only derived numbers.
- **FEC (D19).** Correctly not pulled. I agree with the default.

### F10 (LOW): LDA amounts double-count when summed

- Amendments (`1A..4A`) have distinct `filing_uuid`s and are summed alongside their originals.
- A self-filer's reported expenses generally already include what it pays outside firms. Summing those
  expenses with the outside firms' reported income for the same client double-counts. OpenSecrets
  de-duplicates exactly this.

The table is currently empty, so nothing wrong has been written yet. Fix before the first live rows:
keep the latest amendment per (client, registrant, period), and do not add outside-firm income to a
self-filing client's expenses.

### F11 (LOW): the LDA 403 is an edge rule, not a header problem

My one probe used a descriptive User-Agent, `Accept: application/json`, and the read-only endpoint
`/api/v1/constants/filing/filingtypes/`. It got **403 from AkamaiGHost**, with an "Access Denied" body
naming the internal `$(SERVE_403)` path. That is a configured edge deny, the shape of a geographic or
hosting-range block. It is not a missing-header rejection, and no header change makes it work. The
builder's two options stand: an LDA key (which may not lift an edge geo rule) or a US-hosted run (the
likelier fix).

The class is also mislabelled. The receipt says `BOT_CHECK`, while the note and the code's intent say
`ACCESS_DENIED`. `official_sources.classify_response` returns BOT_CHECK on the "Access Denied" marker,
so the 403 → ACCESS_DENIED override never fires.

### F12 (LOW): silent-fragility gaps in the status rule

- A target that returns **zero rows on a weekday while others return rows** produces an OK receipt.
  HUMANA returned 0 rows in 90 days, against a multi-billion-dollar TRICARE contract, and the run is OK.
  Fix: keep a per-target expected-activity floor (any target with rows in the previous 90 days that
  returns 0 is DEGRADED for that target).
- A US federal holiday on a weekday will show DEGRADED. That false alarm is cheap but will teach
  skimming.
- 429 → `RATE_LIMITED` is fatal and stops the run. That is correct, but untested; add one test.
- 5xx and `HTTP_400` are non-fatal and skip the target. The receipt shows them in `refusals` and status
  goes DEGRADED, which is correct.
- The receipt does distinguish "API answered empty for every target" (DEGRADED, `degraded_why`) from a
  refusal (REFUSED).

### What checked out

- **PIT on transactions:** 0 of 2,059 rows have `action_date` later than `first_seen_utc`.
- The bad first-run table was replaced, not merged: every row now uses the new key, and no transaction
  tuple appears twice.
- No reader of today's revised totals back-fills a past as-of. No reader of any kind exists yet, which
  is why F6 must land before the first one is written.

---

## 8. Tests (run by the reviewer)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_public_flow_sensors.py \
  backend/tests/test_prediction_markets.py backend/tests/test_guard_missing_input_contract.py -q
........................................................................ [ 43%]
........................................................................ [ 86%]
......................                                                   [100%]
166 passed in 10.31s
```

What the tests mock:
- HTTP is injected via `_serve(body, status)` into the `Client.http` hook, and served from trimmed live
  fixtures in `backend/tests/fixtures/public_flow/`;
- the crypto sensor is mocked by monkeypatching `crypto_market._sensor_get`;
- Kalshi is mocked with `monkeypatch.setitem(prediction_markets.SOURCES, "kalshi", ...)` plus
  `config.PREDMARKET_KALSHI_STORAGE`;
- `sleep_fn` is replaced with a no-op or a recorder.

The LDA fixture is constructed from the documented schema, not taken from a live page. The note says so.

**Missing tests:**
- within-pull key collision → DEGRADED (F2);
- corrected-amount revision → no double count (F4);
- receipt dollars == table dollars (F5);
- `q4_share` refusing mixed snapshots (F6);
- 429 handling;
- an as-of reader.

## 9. The investor's question: what changes a decision in the next 90 days?

**Nothing here does.**
- **USAspending.** Feeds one cell, `fiscal_year_end_spending`, which is DECLARED ONLY, has no runner,
  and acts in Aug-Sep. The earliest forward decision is August 2027. The one thing it *could* do within
  90 days is a history read of the calendar effect on CRSP FY2009-2024. At 8 validate FYs (F8), that
  would almost certainly return CANNOT_DISTINGUISH. It is cheap to run and worth running only to close
  the idea, not to open a book.
- **LDA.** REFUSED from this host, and quarterly. Zero.
- **Crypto sensor.** No declared cell reads it, and grep finds no reader. Zero until a cell names it.
- **Kalshi derived Fed path.** This is the only one with an obvious decision use (a regime variable),
  and no code reads `prediction_markets/derived/` either.

## Three things I would have done instead

1. **Pull USAspending by modification date with a stable key, and reconcile against the count
   endpoint.** Query `last_modified_date` daily, key on `generated_internal_id|Mod`, keep a version
   history, and fail the run when `rows_read != count`. That single design gives a real publication-lag
   distribution, sees DoD, and makes a silent drop impossible.
2. **Declare the fiscal cell at the FY unit, with a FY-unit power check, before any precursor talk.**
   Compute the design-fold basket sd per FY. If 8 validate FYs cannot reach an MDE of 2x the 0.5%
   effect, record `REFUSED_UNPOWERED` and spend the budget elsewhere. If a cell must exist, make it
   cross-sectional dose within each FY (high vs low GOVDOM share, same months), which has more
   independent variation than the calendar. Link by permco/gvkey with dated crosswalk rows from the
   start.
3. **Default Kalshi to `none`, gitignore the crypto table, and give the crosswalk dates.** Do not
   persist anything the terms might call "aggregating" until the owner decides D18. Add
   `valid_from`/`valid_to` and a parent-at-date rule to the crosswalk. Downgrade every entry whose
   patterns include an acquired company to medium, as the file's own header says.

## Score: 64 / 100

| item | effect |
|---|---|
| plumbing, refusals, receipts, candour of the note | strong base |
| silent drop still possible and labelled benign (F2) | -8 |
| daily window cannot see DoD (F1) | -8 |
| "latency" headline is window age (F3) | -5 |
| revision double-count, receipt dollars (F4, F5) | -5 |
| agency-month PIT incomplete (F6) | -4 |
| crosswalk dating and confidence contradictions, ticker reuse (F7) | -3 |
| gate passed on the wrong unit (F8) | -3 |
