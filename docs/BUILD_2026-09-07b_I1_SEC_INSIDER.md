# BUILD 2026-09-07b — I1: THE SEC INSIDER TRANSACTIONS BULK LOADER

**Lane:** I1 of `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 (block I,
"investor data — free, historical, nobody's WRDS").
**Licence:** none claimed. This lane produces **DATA**, not a book. No return,
no edge, no promotion. Beta-first grading and family correction belong to
whoever runs the book later.
**Status:** COMPLETE. 82/82 quarters pulled, 0 failures.

## 0. RESULT

| | |
|---|---|
| **Quarters pulled** | **82 / 82** (2006q1 → 2026q2), 0 failed |
| Transaction rows | **11,522,229** |
| Filings (distinct accessions) | 4,062,913 |
| Distinct issuers | 17,999 |
| Distinct insiders | 225,779 |
| Discretionary open-market **purchases** | 1,204,378 |
| Discretionary open-market **sales** | 1,923,246 (event rows) |
| permno link rate | **82–88%** per year 2006–2024; **0%** 2025–26 (CRSP vintage ends 2024-12-31, a counted refusal) |
| Raw on disk | 880 MB (82 ZIPs) |
| Parsed on disk | 443 MB parquet |
| Event table | 3,127,624 rows, 40.3 MB |
| Tests added | **39** in `test_sec_insider_bulk.py`, all in the fast (network-blocked) suite; full fast suite **7,364 passed** |
| LLM spend | **$0.00** — no model was called in this lane |

**What this corrects.** `scripts/n4_event_table.py` says, of Form 4: *"No Form
4 tape is entitled or present. ABSENT, not fabricated."* That was true of WRDS
and of this repo's disk. It was **not true of the world**: the SEC has
published every Form 3/4/5 it has received since 2006 Q1 as a free quarterly
ZIP, no key and no entitlement, the whole time. 20 years of insider
transactions cost one afternoon and zero dollars.

**RESULT IMPROVEMENT: NONE** — by design. This is substrate, not a result.

---

## 1. COVERAGE BY YEAR (actually produced)

Receipt: `backend/data/optimus/sec_insider/coverage_by_year.json`.
Reproduce with `python -m scripts.sec_insider_bulk_load report`.

Rows are transaction-level: one row per (accession × reporting owner ×
transaction), which is what the ownership tables mean. Years are **filing**
years, not transaction years — the PIT column is the filing date.

| year | rows | filings | issuers | insiders | buys | sales | link% | routine | opport. | unclass. |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2006 | 862,684 | 240,447 | 7,738 | 68,388 | 75,907 | 242,724 | 84.0 | 20 | 25 | 75,862 |
| 2007 | 1,034,379 | 245,926 | 7,866 | 69,087 | 133,371 | 282,660 | 84.5 | 115 | 588 | 132,668 |
| 2008 | 829,629 | 227,447 | 7,439 | 64,712 | 192,029 | 164,565 | 85.4 | 520 | 16,216 | 175,293 |
| 2009 | 505,512 | 194,379 | 6,793 | 58,694 | 71,953 | 101,864 | 82.2 | 3,625 | 13,441 | 54,887 |
| 2010 | 542,261 | 202,451 | 6,516 | 58,361 | 52,737 | 104,384 | 83.5 | 3,233 | 10,362 | 39,142 |
| 2011 | 516,940 | 197,415 | 6,354 | 57,432 | 61,566 | 80,454 | 83.2 | 5,214 | 12,550 | 43,802 |
| 2012 | 526,245 | 199,547 | 6,014 | 56,321 | 55,061 | 86,679 | 83.8 | 6,040 | 9,073 | 39,948 |
| 2013 | 523,308 | 199,641 | 5,885 | 56,255 | 37,352 | 84,856 | 84.4 | 4,749 | 6,320 | 26,283 |
| 2014 | 518,233 | 199,835 | 5,937 | 57,008 | 47,602 | 73,952 | 84.5 | 6,323 | 9,491 | 31,788 |
| 2015 | 505,782 | 198,222 | 5,948 | 56,910 | 58,219 | 62,088 | 81.8 | 7,377 | 13,429 | 37,413 |
| 2016 | 471,198 | 187,862 | 5,653 | 55,192 | 50,133 | 64,048 | 81.8 | 5,513 | 10,357 | 34,263 |
| 2017 | 477,465 | 185,812 | 5,526 | 54,742 | 38,028 | 73,307 | 82.8 | 4,457 | 8,069 | 25,502 |
| 2018 | 489,066 | 185,530 | 5,472 | 54,424 | 42,833 | 55,224 | 83.9 | 3,270 | 10,476 | 29,087 |
| 2019 | 475,736 | 180,246 | 5,283 | 53,328 | 39,943 | 55,035 | 84.2 | 3,401 | 7,726 | 28,816 |
| 2020 | 498,712 | 185,340 | 5,388 | 53,896 | 43,447 | 56,386 | 85.8 | 3,232 | 9,171 | 31,044 |
| 2021 | 624,630 | 198,982 | 5,918 | 59,083 | 40,237 | 78,330 | 87.6 | 2,555 | 11,487 | 26,195 |
| 2022 | 470,746 | 186,744 | 5,681 | 57,301 | 52,445 | 53,763 | 86.9 | 4,096 | 13,179 | 35,170 |
| 2023 | 452,287 | 185,510 | 5,651 | 55,813 | 39,390 | 52,763 | 84.9 | 4,704 | 9,295 | 25,391 |
| 2024 | 476,131 | 180,821 | 5,333 | 52,982 | 30,507 | 64,031 | 85.5 | 4,703 | 6,248 | 19,556 |
| 2025 | 440,345 | 172,180 | 5,209 | 51,356 | 27,630 | 51,821 | **0.0** | 3,944 | 5,655 | 18,031 |
| 2026 | 280,940 | 108,576 | 5,137 | 44,221 | 13,988 | 34,312 | **0.0** | 1,353 | 2,397 | 10,238 |

Three things a reader should not misread:

1. **2026 is a partial year** — the tape ends at 2026q2, so its counts are
   half a year and are not comparable to the rows above it.
2. **The 2006–2008 routine/opportunistic counts are near-zero by
   construction**, not by finding. The CMP rule needs three strictly-prior
   years of purchase history and the tape starts 2006q1, so almost everything
   before 2009 is UNCLASSIFIABLE. **The split is only usable from 2009
   onward.** A book that pools 2006–2008 into "opportunistic is rare early on"
   would be reading its own warm-up window.
3. **The 2025–26 link rate is 0.0 and that is not a broken linker** — see §5.

---

## 2. THE PIT TEST, AND WHAT MAKES IT GO RED

### The rule

```
observed_at_utc       = FILING_DATE, end of day (22:00 America/New_York), in UTC
observed_at_precision = "date"
observed_at_basis     = "FILING_DATE_EOD_CONSERVATIVE"
```

`observed_at_utc` is **never** derived from `TRANS_DATE`. A Form 4 transaction
happens up to two business days before the filing (and a Form 5 up to 45 days
after fiscal year end), so the transaction date is the one column that is
guaranteed to be unavailable when it happened.

### The honest limit, stated rather than papered over

The bulk `SUBMISSION.tsv` carries `FILING_DATE` and **no acceptance
timestamp**. Verified on four vintages — 2006q1, 2013q2, 2023q2, 2025q1: 13
columns before 2023q2, 14 after (`AFF10B5ONE` was added), and none of them is
an acceptance time. The Financial Statement Data Sets' `accepted` field has no
counterpart here.

So the bound the bulk files can defend is end-of-**filing**-day. 22:00 ET is
the close of EDGAR's filing window; a Form 4 accepted after 17:30 ET is
disseminated the next business day, so end-of-filing-day is the latest moment
the filing can be assumed public. `next_tradable_session_bound()` states the
consequence in code rather than leaving it to a caller's memory: **the
earliest tradable moment is the NEXT session's open.**

A true acceptance timestamp exists per accession at
`data.sec.gov/submissions/CIK##########.json` (`acceptanceDateTime`). That is
one HTTP request per issuer, which is a separate job. The column
`acceptance_datetime_utc` is carried **NULL** on every row and
`observed_at_basis` says so — a declared absence, not a guess wearing a
timestamp.

### The test, and exactly what turns it red

`backend/tests/test_sec_insider_bulk.py::test_pit_test_goes_red_on_a_lookahead_join`

It parses the fixture quarter, then **rebuilds `observed_at_utc` from
`TRANS_DATE`** — the natural mistake, because the transaction date is the
column that *feels* like the event — and asserts `assert_pit_sane` raises with
`"observed_at_utc is not the filing_date-derived bound"`.

`assert_pit_sane` is the guard, and it goes red on three things:

| # | fatal condition | why it is the lookahead |
|---|---|---|
| 1 | `observed_at_utc != observed_at_utc(filing_date)` | the column was built from something other than the filing date. Build it from `trans_date` and **every row** fails at once, with the offending pair printed. |
| 2 | for a normally-ordered row, `observed_at_utc` is not strictly after the end of the transaction day | catches a bound that lands on or inside the transaction day |
| 3 | more than 1% of rows are future-dated, in a table of ≥1,000 rows | a month/day swap in *our* parser, not the SEC's tail |

Two sibling tests keep the guard from being decorative:
`test_pit_test_goes_red_when_observed_at_is_the_transaction_day_itself` and
`test_pit_check_refuses_a_quarter_that_is_mostly_future_dated`.

### A real finding the guard produced

**20 of 150,789 rows in the real 2025q1 file carry a `TRANS_DATE` AFTER their
`FILING_DATE`** (e.g. accession `0001137547-25-000041`, filed 2025-03-20 for a
2025-10-23 transaction). Across the whole tape, **670 of 3,127,624 event rows**
(0.021%).

These are filer errors or pre-announced scheduled trades, and they are **not a
PIT hazard**: the filing is still the moment the row became public, and it is
*earlier* than the transaction, not later. The first version of the guard died
on them. That was wrong twice over — it would have made the loader unrunnable
for a hazard that points the safe way, and hiding them would have lost a real
data fact. They are now **counted, reported in the receipt, and not fatal**,
with a fraction cap so a genuine parser bug still fires.

Two more the fabrication guard found: `TRANS_DATE` = **2035-01-10** and
**2028-01-01** in 2025q1. Same treatment — counted as `implausible_dates`,
never raised, because they are the SEC's typos and not our invention.

**A ratio floor must be checked against its own denominator.** The 1%
future-dated cap only applies at ≥1,000 rows: on a 6-row fixture "1 in 6" is
17% and says nothing. `MIN_ROWS_FOR_FRACTION_CHECK` exists because the first
version of that cap failed its own fixture.

---

## 3. ROUTINE vs OPPORTUNISTIC (Cohen-Malloy-Pomorski)

**The rule.** An insider who bought in the **same calendar month in each of the
three strictly-prior years** is ROUTINE. An insider with purchases in each of
the three prior years but no such month pattern is OPPORTUNISTIC. Anyone
without three prior years of purchases is **UNCLASSIFIABLE** and is dropped —
never defaulted to opportunistic, which would silently double the
opportunistic count with every insider who simply had not traded for three
years.

**Counts over the whole 2006–2026 tape** (discretionary open-market purchases
only):

| class | rows | share |
|---|---:|---:|
| **opportunistic** | 185,555 | 15.4% |
| **routine** | 78,444 | 6.5% |
| **unclassifiable** | 940,379 | 78.1% |
| total open-market purchases | 1,204,378 | 100% |
| insiders with any purchase history | 80,675 | |

The 78% unclassifiable share is the honest cost of the rule: most insiders do
not buy stock three years running. It is inflated further by the 2006–2008
warm-up window (§1, note 2). A book that wants the CMP long leg gets **185,555
opportunistic buys**, and the **78,444 routine buys are its matched control
arm** — CLAUDE.md rule 4, the informative unit is winner vs matched loser, and
the control is already typed and on disk.

**PIT.** The classification only ever consults strictly prior years
(`test_classification_only_ever_looks_at_strictly_prior_years`), and a purchase
in year *y−1* was filed within two business days of itself, so it was public
long before any year-*y* purchase is classified.

**No drift with the live scorer.** `classify_routine_opportunistic` reproduces
`backend.services.cmp_insider.classify_buy` — the classifier behind
TRIAL-CMP-INSIDER-IC — and `test_bulk_classifier_agrees_with_the_live_cmp_scorer`
runs both on the same histories and asserts they agree. A tape classified one
way and a live buy classified another would be two signals wearing one name.

**The prior is not the claim.** CMP 2012 reports 82 bp/month value-weighted
long-short over 1989–2007. That is the prior that motivates carrying the split.
**This lane makes no return claim of any kind.**

---

## 4. THE TRANSACTION-CODE MAPPING

Source: the "Explanation of Responses" code table on Forms 4/5 and the
`FORM_345_readme.htm` shipped inside every quarterly ZIP. All 20 documented
codes are mapped; `test_every_documented_sec_transaction_code_is_mapped` fails
if one falls out, and an unmapped code becomes `UNKNOWN_CODE` and is **reported
in the receipt**, never dropped (20 such rows in 11.5 M — blank codes).

| code | `trans_class` | meaning | discretionary open-market buy? |
|---|---|---|:---:|
| **P** | `OPEN_MARKET_PURCHASE` | Open market or private purchase | **YES** (with the four clauses below) |
| **S** | `OPEN_MARKET_SALE` | Open market or private sale | no (typed sale) |
| V | `VOLUNTARY_EARLY_REPORT` | Reported earlier than required | no |
| **A** | `GRANT_AWARD` | Grant/award under Rule 16b-3(d) | no — nobody paid cash |
| D | `DISPOSITION_TO_ISSUER` | Disposition to the issuer, 16b-3(e) | no |
| **F** | `TAX_OR_EXERCISE_WITHHOLDING` | Shares delivered/withheld for exercise price or tax | no |
| I | `PLAN_DISCRETIONARY` | Discretionary transaction under 16b-3(f) (benefit plan) | no |
| **M** | `OPTION_EXERCISE` | Exercise/conversion exempt under 16b-3 | no |
| C | `DERIVATIVE_CONVERSION` | Conversion of derivative security | no |
| E | `DERIVATIVE_EXPIRATION` | Expiration of short derivative position | no |
| H | `DERIVATIVE_EXPIRATION` | Expiration/cancellation of long derivative with value received | no |
| O | `OPTION_EXERCISE` | Exercise of out-of-the-money derivative | no |
| X | `OPTION_EXERCISE` | Exercise of in/at-the-money derivative | no |
| G | `GIFT` | Bona fide gift | no |
| L | `SMALL_ACQUISITION` | Small acquisition under Rule 16a-6 | no |
| W | `INHERITANCE` | Acquisition/disposition by will or descent | no |
| Z | `VOTING_TRUST` | Deposit into / withdrawal from voting trust | no |
| J | `OTHER` | Other acquisition or disposition (footnote required) | no |
| K | `EQUITY_SWAP` | Equity swap or similar instrument | no |
| U | `TENDER` | Disposition in a change-of-control tender | no |

### `is_open_market_purchase` — every clause is load-bearing

```
table == "NONDERIV"                 a derivative 'P' is buying an OPTION, not the stock
trans_class == OPEN_MARKET_PURCHASE code 'P'
acquired_disposed == "A"            acquired, not disposed
plan_10b5_1 != "YES"                a scheduled plan trade carries no decision
shares > 0                          a zero-share row is a footnote artefact
```

Each clause has its own assertion in
`test_only_code_P_acquired_nonderivative_is_a_discretionary_purchase`.

### Class totals over 11.5 M rows

| class | rows |
|---|---:|
| `OPEN_MARKET_SALE` | 3,204,960 |
| `GRANT_AWARD` | 2,557,074 |
| `OPTION_EXERCISE` | 2,079,921 |
| `OPEN_MARKET_PURCHASE` | 1,365,484 |
| `TAX_OR_EXERCISE_WITHHOLDING` | 833,630 |
| `OTHER` | 509,277 |
| `DERIVATIVE_CONVERSION` | 357,908 |
| `DISPOSITION_TO_ISSUER` | 335,012 |
| `GIFT` | 210,113 |
| `SMALL_ACQUISITION` | 21,983 |
| `TENDER` | 18,492 |
| `PLAN_DISCRETIONARY` | 16,546 |
| `DERIVATIVE_EXPIRATION` | 6,693 |
| `INHERITANCE` | 3,279 |
| `VOTING_TRUST` | 1,837 |
| `UNKNOWN_CODE` | 20 |

Note the gap between 1,365,484 code-`P` rows and 1,204,378 rows that pass all
five clauses: **161,106 'purchases' are not discretionary open-market stock
buys.** Anyone who screens on `TRANS_CODE == 'P'` alone gets those for free.

### The 10b5-1 split, and its era boundary

`plan_10b5_1` is `YES` / `NO` / `UNKNOWN` — **never a silent False**.

| source | rows |
|---|---:|
| `ABSENT` → UNKNOWN | 8,355,148 |
| `FOOTNOTE_TEXT` → YES | 1,665,072 |
| `AFF10B5ONE` checkbox | 1,502,009 |

The `AFF10B5ONE` checkbox only exists **from 2023 Q2** (the SEC's Dec-2022 rule
amendment). Before that the only evidence is the filer's own footnote prose,
which can say YES but whose absence is *not* evidence of absence — so a
pre-2023 footnote miss stays UNKNOWN. **8.36 M of 11.5 M rows are UNKNOWN, and
a book must handle that as missing data, not as "not a plan trade."**

One live-file trap the parser handles: 2025q1's `AFF10B5ONE` column carries
`'0'`, `'1'`, `'true'`, `'false'` **and** `''` in the same column. A parser that
only knew 0/1 would read `'false'` as truthy garbage
(`test_the_four_way_boolean_encoding_of_the_real_files_is_handled`).

---

## 5. THE permno LINK, AND ITS REFUSALS

**CIK → ticker needs no external map.** The SEC's own `SUBMISSION.tsv` carries
`ISSUERTRADINGSYMBOL` *as of the filing*, which is point-in-time by
construction and strictly better than today's `company_tickers.json` — a ticker
is a dated alias (SECURITY-IDENTITY-LAYER-1: MMC was "unexplained absent" for a
session because it had been MRSH since 2026-01-14).

**Ticker → permno** is an interval join against
`backend/data/optimus/wrds/bulk/crsp__stocknames.parquet` (46,108 rows), with
`namedt <= filing_date <= nameenddt`, breaking a tie on `shrcd ∈ (10, 11)`.

**An unlinked row is a counted refusal carrying WHICH refusal, never a dropped
row:**

| refusal | meaning |
|---|---|
| `REFUSED_OUTSIDE_CRSP_VINTAGE` | the filing is after 2024-12-31, where the entitled CRSP vintage ends |
| `REFUSED_TICKER_NOT_IN_CRSP` | the ticker has no CRSP interval covering that date (OTC, foreign private issuer, funds, pre-IPO Form 3s) |
| `REFUSED_AMBIGUOUS_TICKER` | two permnos share the ticker on that date and neither is uniquely common-stock |
| `REFUSED_NO_SYMBOL` | the filing carries no trading symbol |

Link rate by year is in the §1 table. **2025 and 2026 read 0.0% and that is not
a broken linker** — every one of those rows is
`REFUSED_OUTSIDE_CRSP_VINTAGE` (2025: 440,345 of 440,345). The entitled CRSP
vintage ends 2024-12-31, which was already on the record in
`security_identity.py`. Separating "our link is bad" from "CRSP does not reach
this year" is the whole point of naming the refusal; a bare NULL would have
read as a bug for the two most recent years.

2014 is the shape of a normal year: 84.5% linked, 79,334
`REFUSED_TICKER_NOT_IN_CRSP`, 829 `REFUSED_AMBIGUOUS_TICKER`.

---

## 6. THE EVENT-TABLE JOIN

`python -m scripts.sec_insider_bulk_load events` →
`backend/data/optimus/sec_insider/insider_events_v1.parquet` (40.3 MB,
**3,127,624 rows**), receipt `insider_events_v1_receipt.json`.

Written as its **own** parquet rather than appended into `event_table_v1`:
that table is a sealed artefact of the night lab, and mutating someone else's
receipt is not this lane's business. `scripts/n4_event_table.py` reads this file
when it next runs. Columns follow N4's shape (`permno`,
`permno_link_method`, `symbol`, `event_type`, `event_time_utc`,
`observed_at_utc`, `observed_at_precision`, `source`, `independence_group`,
`year`) plus an `insider_*` block.

**`observed_at_utc` = the filing-acceptance day (date precision), never the
transaction date.** `event_time_utc` carries the transaction date and is
labelled NOT safe to condition on. `assert_pit_sane` runs over the whole table
before it is written: **0 violations on 3,127,624 rows.**

### The `insider_*` families

| family | rows | definition |
|---|---:|---|
| `insider_open_market_sell` | 1,923,246 | code S, disposed, non-derivative, not 10b5-1 |
| `insider_open_market_buy` | 940,379 | code P, acquired, non-derivative, not 10b5-1 — CMP class unclassifiable |
| `insider_opportunistic_buy` | 185,555 | the same, by a CMP-**opportunistic** insider |
| `insider_routine_buy` | 78,444 | the same, by a CMP-**routine** insider — the control arm |
| `insider_cluster_buy` (flag) | 639,189 rows with ≥3 buyers | ≥3 distinct insiders of one issuer on the same **filing** day |

The cluster flag is keyed on the **filing** day, not the transaction day — a
cluster you could actually have seen. `insider_cluster_buyers` carries the
count on every buy row.

Link rate on the event table: **77.99%** (2,439,106 rows carry a permno). It is
below the 82–88% of the linkable years because the table spans 2025–26, where
every row is refused for want of a CRSP vintage.

---

## 7. HOW FAR THE PULL GOT, AND HOW TO RESUME

**It finished.** 82 of 82 published quarters, 2006q1 → 2026q2, **0 failures**.
`_cursor.json` lists all 82 in `done` and `{}` in `failed`.

```
2026-09-07T10:30:26  pull start pid=132828 argv=pull --start 2006q1 --end 2026q2 --keep-raw
2026-09-07T10:30:26  plan: 82 quarters in [2006q1..2026q2]; 1 already done; 81 to do this run
...
2026-09-07T10:41:08  [81/81] 2026q2 OK rows=128137 subs=56102 buys=6686 link=0.0 zip=11498860B 10.2s
2026-09-07T10:41:08  pull end ok=81 failed=0 done_total=82
```

That second log line **is** the resume proof: a one-quarter smoke run had
already done 2025q1, and the full run skipped it and did 81.

### The download, measured honestly

The lane brief asked for one quarter's real size before looping. **2025q1: 12.80 MB
on the wire, 2.5 s, 63,284 submissions → 150,789 transaction rows.** Members:

```
FOOTNOTES.tsv        41.6 MB     NONDERIV_TRANS.tsv   11.4 MB
REPORTINGOWNER.tsv    9.5 MB     SUBMISSION.tsv        6.7 MB
DERIV_TRANS.tsv       6.3 MB     OWNER_SIGNATURE.tsv   5.1 MB
NONDERIV_HOLDING.tsv  2.3 MB     DERIV_HOLDING.tsv     1.8 MB
```

Extrapolating 82 × ~13 MB predicted ~1.0 GB. **Actual: 921,904,566 bytes
(880 MB) downloaded, 443 MB of parsed parquet, ~11 minutes wall clock.**

### To resume, or to re-run

```bash
# resumes from the cursor; already-done quarters are skipped
python -m scripts.sec_insider_bulk_load pull --keep-raw

# a bounded slice, absolute quarters (never "N quarters from today")
python -m scripts.sec_insider_bulk_load pull --start 2020q1 --end 2021q4

# stop after N quarters this run
python -m scripts.sec_insider_bulk_load pull --limit 5

# re-do quarters already in the cursor / re-fetch ZIPs already on disk
python -m scripts.sec_insider_bulk_load pull --force --redownload

# the newest quarter appeared? re-scrape the index
python -m scripts.sec_insider_bulk_load pull --refresh-index
```

State lives in `backend/data/optimus/sec_insider/`:

| file | role |
|---|---|
| `_cursor.json` | rewritten **atomically after every quarter**. A kill at 83% resumes at 83%. |
| `_load.log` | one line per quarter, on disk, as it happens |
| `_load.pid` | so a later session kills by **PID**, never by image name (CLAUDE.md rule 6) |
| `receipts/<quarter>.json` | coverage receipt **per quarter**, not only at the end |
| `_zip_index.json` | the scraped SEC index, cached so a resume does not re-fetch it |
| `coverage_by_year.json` | the §1 table |
| `insider_events_v1{,_receipt}.parquet/json` | the §6 event rows |

Every one of those is the news backfill's failure in negative: it died at
83.6% of 134 months **with no cursor and no log**, so finishing it meant
starting from zero.

**A design detail that mattered:** the ZIP list is **scraped** from the SEC
index page, not generated from a URL pattern — because the pattern is already
wrong. 2026q2 is served from `/files/datastandardsinnovation/...` while
2006q1–2026q1 come from `/files/structureddata/...`. A hard-coded pattern would
have silently skipped the newest quarter. `discover_zip_urls` refuses outright
if the page yields no links rather than falling back to the pattern.

**SEC manners:** User-Agent `AEGIS Research mrthnabdullaev@gmail.com`, a
0.2 s floor between requests (one request per quarter — far under the 10/s
cap), and a **403 is raised with its body's first line, logged, and recorded in
the cursor** — never swallowed into an empty result. The last collector that
assumed it was fine 403'd on 100% of prod fetches.

---

## 8. TESTS

`backend/tests/test_sec_insider_bulk.py` — **39 tests, all passing, none marked
`slow` or `network`**, so every one of them runs inside the fast suite's socket
+ curl_cffi block. **Nothing added in this lane touches the network in the fast
suite**: the parser takes a `Path` and opens no socket, and `requests` is
imported *lazily inside* `_get()` in the loader so importing the script under
the guard is safe. The fixture builds a real quarterly ZIP in `tmp_path` with
the true member names, the true `DD-MON-YYYY` dates and the true four-way
boolean encoding.

| group | tests | what they pin |
|---|---:|---|
| dates | 2 | `DD-MON-YYYY`; the observed-at bound derived from `today`, never a literal calendar moment |
| code mapping | 5 | all 20 SEC codes mapped; unmapped reported not dropped; the five clauses of `is_open_market_purchase`; 10b5-1 never a silent False; the four-way boolean |
| parser | 4 | end-to-end on the fixture; footnote-sourced 10b5-1; skipped scan stays UNKNOWN; a **missing member is a refusal, not an empty quarter** |
| **PIT** | **5** | the lookahead join goes red; observed-at on the transaction day goes red; the mostly-future-dated cap; the cap not applied below its row floor; observed-at never before the filing day |
| **fabrication** | **6** | invented accession, invented column, no filing date, doctored `dollar_value` all rejected; source and derived field sets do not overlap |
| routine/opportunistic | 7 | routine, opportunistic, unclassifiable-not-defaulted, strictly-prior-years, **parity with the live `cmp_insider` scorer** (3 cases), history counts only open-market buys |
| permno link | 3 | interval match; every refusal is a NAMED reason; outside-interval does not link |
| quarters | 2 | inclusive range (82 quarters 2006q1→2026q2); malformed/reversed refused |
| loader | 3 | cursor/log/receipt paths and families declared; cursor round-trips atomically; an old-version cursor starts fresh and is **kept** |

Enrolment guards, both of which fired on this work and were satisfied properly
rather than exempted:

* `test_guard_missing_input_contract::test_every_guard_is_enrolled` — added a
  real `_case_sec_insider_bulk` (a quarterly ZIP missing `REPORTINGOWNER.tsv`
  must raise), **not** an entry in `NOT_INPUT_GUARDS`. Passes.
* `test_signal_reachability::test_every_orphan_is_classified` — `sec_insider_bulk`
  is reachable through `scripts/sec_insider_bulk_load.py`, no classification
  needed.

### Runs

```
backend/tests/test_sec_insider_bulk.py            39 passed        0.7 s
+ the adjacent insider suites + guard contract   150 passed        8.3 s
FULL FAST SUITE  (AEGIS_IGNORE_DOTENV=1, -m "not slow")
    7,364 passed · 7 failed · 20 skipped · 124 deselected · 713 s
```

**None of the 7 failures is this lane's.** `sec_insider` appears zero times in
the failure output. Six were `test_arena_brain.py`, and they were **transient**:
another agent was mid-edit of `llm_research.py` / `model_provider.py` during the
12-minute run, and the suite re-runs **62 passed** now. The seventh was
`test_every_guard_is_enrolled` reporting `scrape_store` — another agent's
untracked module — which that agent has since enrolled; the two enrolment
guards re-run **10 passed**.

A note for the lead session, because it is a real hazard rather than a
grumble: **a 12-minute full-suite run across a tree six agents are writing to
does not measure the tree, it measures a moving average of it.** Trust the
targeted re-runs above over the wall-clock full run.

---

## 9. WHAT THIS LANE DELIBERATELY DID NOT DO

No book. No return. No IC, no beta, no t-statistic, no promotion, no order, no
deploy, no seal. **$0.00 of LLM spend.** The deliverable is clean PIT data plus
its coverage receipt, exactly as the brief scoped it.

What the next session gets, ready to run:

* **185,555 opportunistic buys** and **78,444 routine buys** as a pre-typed
  matched pair, 2009–2026 (the split is warm-up-limited before 2009);
* **639,189 cluster-buy rows** (≥3 distinct insiders, same issuer, same filing
  day);
* **2,439,106 permno-linked event rows** joinable to CRSP;
* a coverage receipt that names every refusal, so any coverage claim about this
  tape can be checked rather than believed.

Three things that must be carried into any book built on it:

1. **Enter on the next session's open**, not the filing date —
   `next_tradable_session_bound()` says so in code.
2. **8.36 M rows have `plan_10b5_1 == UNKNOWN`.** Pre-2023q2 that is a data
   limit, not a "no". Treat it as missing.
3. **The 2025–26 slice has no permno.** Either refresh the CRSP vintage or
   declare the window as 2006–2024.

---

## 10. FILES

| path | what |
|---|---|
| `backend/services/sec_insider_bulk.py` | the offline parser, classifiers, PIT and fabrication guards, permno linker (new) |
| `scripts/sec_insider_bulk_load.py` | the resumable loader: `pull` / `report` / `events` (new) |
| `backend/tests/test_sec_insider_bulk.py` | 39 offline tests (new) |
| `backend/tests/test_guard_missing_input_contract.py` | `+ _case_sec_insider_bulk`, enrolled in `CASES` |
| `docs/DATA_MANIFEST.md` | the raw/parsed substrate catalogued with its rebuild command |
| `.gitignore` | ignores the 880 MB of raw ZIPs and the load log; receipts stay tracked |
| `backend/data/optimus/sec_insider/` | cursor, log, 82 per-quarter receipts, coverage receipt, event table |
