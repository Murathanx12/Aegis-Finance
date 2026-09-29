# Stitched tickers in the live ranker's bars: found from the data, cut at the reader (2026-09-29)

Answers `docs/reviews/REVIEW_2026-09-29_NN_LAB.md` F4. Licence `PRODUCT_EXPERIMENT`. No bar
file, frozen book, ledger row or past receipt was changed. No broker call, no order, no LLM.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE in money.** A data error that was choosing names is removed from
the live reader. What changes is what the ranker is allowed to believe.

| item | value |
|---|---|
| candidate gaps (> 20 sessions) in the survivorship-free panel | **63** in 63 symbols: 17 in `prices_deep/bars.parquet`, **46 inside `bars_delisted.parquet`** |
| verdicts | **62 STITCHED**, 1 SUSPENSION (NBIS: the same registrant, CIK 1513845, filed from 2012) |
| stitched names whose new company resumed inside the 12-1 window | **42** (JAN, LIFE, AKTS, MLPI, VIA, WLTH, ...) |
| in today's live ranking (`pc_book/2026-09-28/ranking.json`, top 25) | **JAN #2, MLPI #4** |
| in tonight's paper book, orders, decisions and paper positions | **none** (checked at 15:30Z; PROBE book = NVDA INCY AAPL SNDR META AVPT AMZN GOOGL JAZZ TSM) |
| frozen books holding a stitched name | **45 of 312** (the review counted 31 of 312 over JAN/LIFE/AKTS only) |
| TRIAL-LIB-FWD-TWIN-1 pairs affected | **20 of 30** (16 on the book side, 4 on the twin side only) |
| strategy-library cells whose holdings used a straddled 12-1 window | 390 of 919 cells, 163 of 307 rules (most are random or small-cap rules drawing the new listings) |
| `mom_12_1_q` (k 20, the +661% row) | **2 of 39** rebalance dates (2026-04-30, 2026-07-31), 10% of the book on those dates |
| receipt | `backend/data/optimus/stitched_tickers/stitched_20260928T153245Z.json` |

## 1. Verified, and wider than reported

The reviewer counted 17 living symbols with an internal gap in `prices_deep`. That is right for
that file. The live ranker reads `survivorship_free_paths()` = `prices_deep` + `bars_delisted`,
and the delisted file has 46 more. It was pulled BY TICKER for Alpaca's 1,830 inactive listed
assets (`scripts/pull_delisted_bars.py`), and the bars endpoint answers every listing ever made
under a ticker: MLPI is a fund that died at $9.98 in 2020 plus a listing at $44.08 from
2025-12-18 that still trades. MLPI is #4 in today's ranking, from exactly that splice.

## 2. Detection, from the data (`backend/services/stitched_tickers.py`)

A candidate is a symbol whose consecutive bars are more than `STITCH_GAP_SESSIONS` (20) market
sessions apart. The gap never decides alone. Evidence per gap:

- **same_registrant**: the ticker's current SEC registrant has filings on disk dated before the
  old segment ended -> one legal company -> SUSPENSION, kept joined (NBIS);
- **new_registrant**: the current CIK's first filing on disk is AFTER the old segment ended
  (JAN: CIK 2100805, first filed 2026-05-06; the old JAN ended 2024-07-12);
- **cik_band_after**: no filings on disk, but CIKs numbered near the current one first filed
  well after the old segment ended (an estimate; labelled so; ITG, BID, JONE, ...);
- **inactive_source**: the old segment comes from the inactive-asset pull;
- **price_jump**: a level change of 3x or more across the gap;
- **recent_file_first_trade** (receipt only): the nightly-refreshed `prices_2025_26` file first
  trades the symbol after its own start date, contradicting the older history.

| symbol | old last bar | old close | new first bar | new close | gap (sessions) | inside 12-1 window | evidence | verdict |
|---|---|---:|---|---:|---:|---|---|---|
| AHL | 2019-02-14 | 42.74 | 2025-05-08 | 32.5 | 1566 | no | inactive_source | STITCHED |
| AKTS | 2024-12-17 | 0.0372 | 2026-01-09 | 22.4 | 265 | yes | new_registrant, price_jump, recent_file_first_trade | STITCHED |
| APC | 2019-08-08 | 69.92 | 2026-02-12 | 16.86 | 1637 | yes | new_registrant, inactive_source, price_jump | STITCHED |
| AT | 2021-05-14 | 3.02 | 2026-09-15 | 20.03 | 1339 | yes | inactive_source, price_jump | STITCHED |
| ATC | 2022-08-16 | 20.15 | 2026-05-12 | 21.68 | 937 | yes | inactive_source | STITCHED |
| BID | 2019-10-02 | 56.99 | 2026-07-20 | 9.84 | 1706 | yes | cik_band_after, inactive_source, price_jump | STITCHED |
| BITA | 2020-11-04 | 15.36 | 2026-06-16 | 50.87 | 1408 | yes | cik_band_after, inactive_source, price_jump | STITCHED |
| BREW | 2020-09-29 | 16.51 | 2026-05-06 | 25.51 | 1406 | yes | inactive_source | STITCHED |
| BVAL | 2020-07-30 | 15.9 | 2025-06-23 | 24.86 | 1229 | no | inactive_source | STITCHED |
| CAI | 2021-11-22 | 56 | 2025-06-18 | 28 | 895 | no | new_registrant | STITCHED |
| CCXI | 2022-10-19 | 51.99 | 2026-02-09 | 10.26 | 828 | yes | new_registrant, price_jump | STITCHED |
| CEFZ | 2020-03-26 | 3.275 | 2025-08-04 | 7.116 | 1345 | no | inactive_source | STITCHED |
| CHA | 2021-01-08 | 24.87 | 2025-04-17 | 30.5 | 1073 | no | new_registrant | STITCHED |
| CHAC | 2019-10-28 | 10.55 | 2025-05-19 | 9.9 | 1396 | no | inactive_source | STITCHED |
| CTAA | 2021-02-12 | 25.06 | 2026-04-16 | 9.89 | 1298 | yes | cik_band_after, inactive_source | STITCHED |
| EMES | 2019-05-31 | 0.2087 | 2025-05-15 | 19.94 | 1498 | no | inactive_source, price_jump | STITCHED |
| FIYY | 2020-12-10 | 101.1 | 2026-05-05 | 24.67 | 1354 | yes | inactive_source, price_jump | STITCHED |
| FLAG | 2023-09-12 | 7.826 | 2025-04-16 | 24.14 | 400 | no | inactive_source, price_jump | STITCHED |
| FLXN | 2021-11-18 | 8.209 | 2025-07-03 | 22.57 | 907 | no | inactive_source | STITCHED |
| FLY | 2021-08-02 | 17.03 | 2025-08-07 | 60.35 | 1008 | no | new_registrant, price_jump | STITCHED |
| FLYT | 2022-01-14 | 49.01 | 2025-10-23 | 24.57 | 946 | yes | inactive_source | STITCHED |
| FNG | 2019-10-04 | 10.41 | 2026-06-16 | 12.77 | 1682 | yes | inactive_source | STITCHED |
| GLDW | 2019-09-09 | 119.5 | 2025-10-30 | 40.1 | 1545 | yes | inactive_source | STITCHED |
| GNMX | 2020-02-03 | 0.1659 | 2026-05-06 | 25.71 | 1572 | yes | inactive_source, price_jump | STITCHED |
| HAWK | 2018-06-14 | 45.15 | 2026-05-07 | 34 | 1984 | yes | new_registrant | STITCHED |
| ITG | 2019-02-28 | 30.23 | 2026-07-01 | 17.71 | 1844 | yes | cik_band_after | STITCHED |
| JAN | 2024-07-12 | 2.206 | 2026-03-20 | 23.34 | 423 | yes | new_registrant, price_jump | STITCHED |
| JCAP | 2020-11-05 | 16.2 | 2025-06-26 | 17.44 | 1163 | no | new_registrant | STITCHED |
| JHDG | 2019-03-14 | 25.44 | 2026-04-08 | 25.59 | 1776 | yes | inactive_source | STITCHED |
| JONE | 2018-11-26 | 2.13 | 2026-09-03 | 9.84 | 1952 | yes | cik_band_after, inactive_source, price_jump | STITCHED |
| LEND | 2021-06-25 | 15.95 | 2026-05-18 | 24.58 | 1228 | yes | inactive_source | STITCHED |
| LIFE | 2024-06-04 | 1.9 | 2026-01-29 | 16.85 | 414 | yes | new_registrant, price_jump | STITCHED |
| LMNX | 2021-07-13 | 36.99 | 2025-10-16 | 16.32 | 1071 | yes | inactive_source | STITCHED |
| LOGO | 2018-09-28 | 16.71 | 2025-05-28 | 19.91 | 1673 | no | inactive_source | STITCHED |
| MB | 2019-02-14 | 36.46 | 2025-04-10 | 4.1 | 1547 | no | cik_band_after, inactive_source, price_jump | STITCHED |
| MIC | 2022-07-20 | 4.09 | 2026-06-26 | 21.67 | 987 | yes | inactive_source, price_jump | STITCHED |
| MLPI | 2020-11-23 | 9.978 | 2025-12-18 | 44.08 | 1273 | yes | inactive_source, price_jump | STITCHED |
| NBIS | 2024-08-19 | 18.94 | 2024-10-21 | 20 | 44 | no | same_registrant | **SUSPENSION** |
| NIQ | 2023-06-23 | 12.87 | 2025-07-23 | 19.01 | 521 | no | new_registrant | STITCHED |
| NP | 2022-07-05 | 32 | 2025-10-01 | 24.8 | 814 | yes | new_registrant | STITCHED |
| NYNY | 2019-11-15 | 9.75 | 2026-05-06 | 25.38 | 1624 | yes | inactive_source | STITCHED |
| PAAC | 2020-06-16 | 7.61 | 2026-04-06 | 10 | 1457 | yes | cik_band_after, inactive_source | STITCHED |
| PCI | 2021-12-10 | 19.4 | 2025-08-01 | 47.7 | 912 | no | inactive_source | STITCHED |
| PPLC | 2020-09-25 | 43.17 | 2026-03-04 | 49.32 | 1364 | yes | inactive_source | STITCHED |
| PS | 2021-04-05 | 22.37 | 2026-04-29 | 24.12 | 1273 | yes | new_registrant | STITCHED |
| RISE | 2020-10-30 | 19.57 | 2026-04-23 | 19.13 | 1374 | yes | inactive_source | STITCHED |
| SCA | 2021-02-11 | 22.11 | 2026-05-27 | 22.07 | 1327 | yes | inactive_source | STITCHED |
| SEMG | 2019-12-04 | 15.01 | 2025-05-14 | 25.31 | 1367 | no | inactive_source | STITCHED |
| SIC | 2021-10-20 | 14.49 | 2026-08-17 | 49.83 | 1209 | yes | inactive_source, price_jump | STITCHED |
| SMHD | 2020-03-20 | 2.37 | 2026-08-04 | 41.62 | 1600 | yes | inactive_source, price_jump | STITCHED |
| STLR | 2018-12-13 | 10.4 | 2026-04-01 | 20.33 | 1833 | yes | inactive_source | STITCHED |
| TACO | 2022-03-07 | 12.51 | 2025-06-05 | 10.3 | 815 | no | cik_band_after, inactive_source | STITCHED |
| TAPR | 2020-11-30 | 77 | 2025-04-01 | 24.31 | 1088 | no | inactive_source, price_jump | STITCHED |
| THOR | 2020-01-22 | 67.71 | 2026-06-23 | 24.88 | 1612 | yes | inactive_source | STITCHED |
| TIER | 2019-06-14 | 28.42 | 2025-06-26 | 25.14 | 1516 | no | inactive_source | STITCHED |
| TRIL | 2021-11-16 | 18.44 | 2025-09-30 | 20.04 | 970 | yes | inactive_source | STITCHED |
| ULTI | 2019-05-02 | 172.8 | 2025-10-31 | 13.47 | 1635 | yes | inactive_source, price_jump | STITCHED |
| UN | 2020-11-27 | 60.5 | 2026-07-07 | 26.22 | 1405 | yes | inactive_source | STITCHED |
| VIA | 2024-06-13 | 10.99 | 2025-09-12 | 49.51 | 312 | yes | new_registrant, price_jump | STITCHED |
| WLTH | 2023-06-12 | 8.325 | 2025-12-12 | 14.19 | 629 | yes | new_registrant | STITCHED |
| XCOM | 2020-10-01 | 62.5 | 2026-06-03 | 25.26 | 1423 | yes | inactive_source | STITCHED |
| XDIV | 2021-12-10 | 105.7 | 2025-07-10 | 25.26 | 896 | no | inactive_source, price_jump | STITCHED |
| XE | 2017-09-05 | 9.734 | 2026-04-24 | 29.2 | 2170 | yes | new_registrant | STITCHED |

(The `recent_file_first_trade` line is in the receipt for the 16 names where it fires; it is
left out of this table except where it was the only extra evidence.)

Twelve of the 62 rest on `inactive_source` alone with prices within 3x (RISE $19.57 -> $19.13,
SCA $22.11 -> $22.07). Two listing periods under a ticker the vendor names as one inactive asset
is two assets, and a trailing window across a multi-year hole is not the quantity its name
claims either way, so the cut is the conservative side. A `GAP_UNRESOLVED` verdict exists for a
gap with no evidence at all; it is also cut and is counted apart (0 today).

## 3. The fix, at the reader, in one function

`backend/services/xs_ranker.load_bars` now tags each file's rows with their source and calls
`stitched_tickers.split_stitched`, which renames every segment before a STITCHED gap `SYM#k`.
The living symbol's history starts at the new company's first bar, so every feature that needs a
longer window is **NaN** for it (never zero, never the old company's prices), and the dead
company stays in the panel as its own dead name. Rows are never dropped and no price changes.
`load_bars(..., split_stitched=False)` returns the raw concatenation for audits;
`xs_ranker.LAST_STITCH_AUDIT` holds the last call's audit. On the real panel the load rises from
3.5 s to 11.9 s.

Readers that go through `xs_ranker.load_bars` and are therefore fixed: `scripts/sim_run.py` (the
ranking subprocess), `backend/services/daily_review.py`, `backend/services/llm_portfolio.py`,
`scripts/book_factory.py` (freeze).

**Readers that bypass it and are NOT fixed here** (file ownership). Each needs one call,
`stitched_tickers.split_stitched(df, src_col=...)`, after its own concat and dedupe:
`scripts/night_backtest_factory.load_wide` (the strategy library, and through it
`scripts/bridge_report.py`, `scripts/calendar_offset_triplet.py`,
`scripts/fast_mover_forensics.py`, `scripts/finra_short_volume_rules.py`),
`backend/services/source_registry.load_close_panel`, `backend/services/pit_features.main`,
`backend/services/fast_mover_forensics._load_bars_since`, `scripts/bridge_report.load_bars`,
`scripts/decision_autopsy.load_bars`, `scripts/contest_calendar.load_bars_usd` (reads
`prices_deep` directly), `backend/services/source_scorecard.load_bars`. `nn_lab` keeps its own
conservative cut (every gap over 20 sessions, NBIS included) because it imports nothing from
`backend/`.

**The running 10-hour paper sim** (`f496cf18b433`, started 12:26Z) was not stopped or
restarted. Its ranking runs in a subprocess that imports `xs_ranker` fresh, but it re-ranks only
when the bar files' fingerprint changes, and the next bar refresh (06:30 HKT) comes after the
sim's planned end (22:26Z). So tonight's sim keeps the ranking with JAN #2 and MLPI #4; the first
ranking on the fixed reader is the next one after the refresh.

**Did tonight's paper book buy a stitched name? No.** At 15:30Z the intended book
(`pc_book/2026-09-28/intended_book.json`, cycle 16) holds NVDA, INCY, AAPL, SNDR, META, AVPT,
AMZN, GOOGL, JAZZ and TSM at 2% each; `decisions.jsonl` mentions no stitched name; no paper
position (pc_snapshot, review, pc_book) holds one; the candidate funnel (2026-09-24) has none.
The PROBE shortlist comes from the committee funnel, not from the ranking's top, which is why
JAN #2 did not reach an order. The sim still has cycles to run; re-read the receipt's
`blast_radius` block (`python -m backend.services.stitched_tickers`) after it ends.

## 4. Blast radius, reported, nothing mutated

- **Frozen books:** 45 of 312 hold at least one stitched name (full list with weights in the
  receipt). Largest: `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control` 26.5%
  (JAN 15.0%), `lib_mom_12_1_ivw_lead_2026-09-27__control` 26.3% (JAN 14.9%), their `ranks_`
  twins 23.4% / 22.9% (MLPI), `lib_disp_short_avoid_2026-09-27` and its `__ew` twin 20% (AKTS,
  LIFE, JAN, MLPI). No book was changed.
- **TRIAL-LIB-FWD-TWIN-1:** 20 of 30 pairs. A dated note was appended to
  `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md` before any forward return was
  read: the deciding read is unchanged, three sensitivity reads (S1 without the 16 book-side
  pairs, S2 without all 20, S3 with the stitched holdings removed and re-weighted) are printed
  beside it at both dates, and a SURVIVES stands only if S3 also passes.

## 5. The strategy library (not rerun tonight)

Counted from `strategy_library/holdings_2026-09-28T141504Z.parquet` (the 2026-09-27 run gives
the same counts): a holding is contaminated when its rebalance date is on or after the new
company's first bar and less than 252 sessions after it, so the 12-1 window straddles the hole.

| rule (k) | rebalance dates | dates holding a straddled name | names | weight on those dates |
|---|---:|---:|---|---:|
| `mom_12_1_q` (20) | 39 | **2** (2026-04-30, 2026-07-31) | AKTS; AKTS, JAN, LIFE | 5%, 15% |
| `mom_12_1` (20) | 115 | 5 (2026-03-31 .. 2026-07-31) | AKTS, JAN, LIFE | 11% mean |
| `mom_12_1_small` (20) | 115 | 7 (2025-11-28 .. 2026-07-31) | AKTS, JAN, LIFE, MLPI, VIA | 13% mean |
| `mom_no_downgrades` (20) | 115 | 5 | AKTS, JAN, LIFE | 11% mean |
| `disp_short_avoid` (20) | 39 | 2 | AKTS, JAN, LIFE | 10% mean |
| `mom_12_1_q_trend` (20) | 54 | 2 | AKTS, JAN, LIFE | 10% mean |
| `qc470_mom252_quarterly_riskparity` (20) | 39 | 2 | AKTS, JAN, LIFE | 16% mean |

For the headline `mom_12_1_q`: the contaminated holdings sit only in the last two quarters of a
2020-2026 record. A close-to-close estimate (not the library's cost model): AKTS +17.7% over
2026-04-30 -> 07-31 at 5% adds about +0.9 pp to that quarter; AKTS -12.0%, JAN -0.2%, LIFE
+68.0% over 2026-07-31 -> 09-25 at 5% each add about +2.8 pp. That is roughly 3.7% of the
jajo calendar's ending wealth (+1,323% -> about +1,270%). The other two calendars' holdings are
not stored, so their share of the calendar-neutral **+661%** is not counted. The +661% does
include stitched names, on at most two rebalances per calendar, and the error is small against
the headline; it is not small against the 2024-26 window the twin comparison leans on.

**What a rerun needs:** one call to `stitched_tickers.split_stitched(df, src_col=...)` inside
`scripts/night_backtest_factory.load_wide` after its dedupe (tag each file's rows with its stem
first), then the factory, the calendar-offset triplet and the matched twins rerun on the same
run-id convention. Owned by the library, not done here.

## 6. Tests

`backend/tests/test_stitched_tickers.py` (synthetic bars, dates from today, offline): a reused
ticker detected from the registrant alone and cut; a suspension of the same registrant kept;
price-jump and inactive-source evidence; a gap of exactly the threshold not a candidate; through
`xs_ranker.load_bars` + `build_features`, a stitched ticker has NaN 12-1 momentum until it has
its own 252 sessions and the exact value after, while an unstitched name is byte-for-byte
unchanged; the blast radius reads and never writes.
