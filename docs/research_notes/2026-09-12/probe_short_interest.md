# Probe 2026-09-12 — short interest and turnover for Book A (Sonnet, read-only; corrects `spec_first_books.md` §A.2)

**Headline: the panel the spec says does not exist already does.**
`backend/data/optimus/wrds/bulk/comp__sec_shortint.parquet` (5,279,203 rows, `datadate`
2006-07-14..2026-08-14) and `comp__sec_shortint_legacy.parquet` (4,770,658 rows, `datadate`
1973-01-15..2024-12-31) were pulled by `scripts/wrds_pull_everything.py`. Columns: `gvkey, iid,
shortint, shortintadj, datadate, splitadjdate`. `datadate` is the SETTLEMENT date, not the publication
date — the same PIT trap as FINRA. Join: `gvkey/iid` → `permno` through
`backend/data/optimus/wrds/link_ccm.parquet` (33,324 rows; interval join on `linkdt ≤ datadate ≤
linkenddt`, `linktype ∈ {LC, LU}`), then `crsp_dsf_<year>.parquet` on `permno` + date for `shrout`.
`spec_first_books.md` §A.2's claim that no historical panel exists is wrong for the WRDS bulk pull;
`backend/services/short_interest.py` (a live yfinance snapshot) has no history, the bulk data does.

## Sources
| source | coverage | key | PIT stamp | note |
|---|---|---|---|---|
| WRDS `comp.sec_shortint` + `_legacy` (local) | 1973-2026 | gvkey/iid → permno via `link_ccm` | `datadate` = settlement; usable from **publication** (measured lag 10-26 calendar days, median 14; nominal 8 business days) | zero new pull; dedupe the 2006-2024 overlap |
| FINRA bi-monthly CSV (free) `https://cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv` | 2017-12-29 → today (403 at every date ≤ 2017-10-31) | ticker symbol only | `settlementDate` field; publish lag as above | pipe-delimited despite `.csv`; NYSE/Nasdaq AND OTC names in the file (the "OTC-only pre-2021" claim on FINRA's page is empirically false for this endpoint); schema: `symbolCode, currentShortPositionQuantity, previousShortPositionQuantity, averageDailyVolumeQuantity, daysToCoverQuantity, revisionFlag, settlementDate, …`; samples pulled: `shrt20260814.csv` 22,483 rows, `shrt20171229.csv` 15,496 rows |
| `wrdsapps_eushort` (local) | 2003-2026 | ISIN | — | **EU short-position disclosures, not US** — a false lead |
| FRED | — | — | — | no short-interest series |

## Turnover
`crsp_dsf_<year>.parquet` (1990-2024, 35 files): `permno, date, prc, ret, retx, vol, shrout, askhi,
bidlo, openprc, cfacpr, cfacshr`. `shrout` is thousands of shares; `vol` reads as raw shares (permno
10026: 89,969 / 19,367k → 0.46 %/day, sane). 20-name June-2024 sample: median monthly turnover 17.7%,
median daily 0.93%; one low-float outlier at 4,073 %/month — winsorise on shares outstanding. **The
Nasdaq double-counting adjustment (Anderson-Dyl 2005) was NOT verified here** — confirm against WRDS's
own `crsp.dsf` volume notes before trusting pre-2001 turnover unadjusted.

## The §24 features
`dtc_low`, `si_chg_low`, `si_trend` in NEGATIVE_RESULTS §24 came from `batch8.py`, which exists in
the `Aegis module` repo, not here; nothing from that run persisted into this repo's data dirs. Book A's
join is built here from the WRDS panel above.

## Join plan
`sec_shortint_legacy` + `sec_shortint` (dedupe overlap) → `link_ccm` interval join → `crsp_dsf` on
permno + date. PIT: `observed_at = datadate + measured publication lag`, forward-filled, never
interpolated. Layout: `short_interest/comp_sec_shortint/<year>.parquet` (historical) and
`short_interest/finra/<year>.parquet` (forward), mirroring `crsp_dsf_<year>` partitioning. Forward pull:
check daily around the 1st and the 15th HKT, since publication drifts 10-26 days.

## Recommendation
1988-2024 backtest: the local Compustat panel through `link_ccm` — zero new pull. 2025-26 forward paper
leg: FINRA's free CDN by ticker, gated by the measured lag before a print is PIT-usable.
