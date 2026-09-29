# Broken price histories in the library panel: found, cut at the reader, and the momentum lead re-read (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. HINDSIGHT for every backtest number: the rules were registered
2026-09-26, after every month here. No bar file, frozen book, ledger row or past receipt was
changed. Every correction is a new receipt. No broker call. No LLM ($0.00).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NEGATIVE, and it is the honest direction.** The project's best
historical number was partly a data error. It does not survive as a twin-beating edge.

| item | value |
|---|---|
| best historical net strategy vs the market | `mom_12_1_q`, calendar-neutral: **+458% since 2020** (was +661%). SPY +162%. CAGR 26.5% (was 30.9%). |
| its edge over the matched twin | **+0.92%/mo, t 1.83, MDE 1.41%/mo** (was +1.20%/mo, t 2.49). Sealed window **+0.26%/mo, t 0.27**. Verdict **CALENDAR_ARTEFACT** (was CANNOT_DISTINGUISH). |
| best forward paper strategy | unchanged. No forward read is due before 2026-10-26. |
| independent selector count | unchanged. The four leads are one momentum bet. |
| defect size | **174,417 non-trade rows** removed in 697 names; **95 proven level breaks** cut. With the vendor-filled holes visible, stitched gaps rise from **62 to 766**. **720 names touched** of 4,793. |
| momentum top-20 slots on impossible rows (vol_63 > 300%/yr or 12-1 > +2,000%) | **176 of 2,340 -> 84**. All 84 left are real (GME, QUBT, MARA, NVAX, SNDK, AXTI, ...). |
| frozen books selected on a broken row | **21 positions in 21 of 314 books.** WOLF is in 20 of them; ISRL is in 1 twin. |
| TRIAL-LIB-FWD-TWIN-1 | **9 of 30 pairs**, all on the book side. 7 were already in the stitched note; 2 are new. Dated amendment appended. |
| world digest ungraded share | the ungraded share of sector and macro implications falls from **29 of 80 (36%) to 4 of 80**: 43 proxy ETFs pulled, and the grader prices them |
| LLM spend | $0.00 |

## 1. What was broken, and why the stitch cut missed it

The vendor does not leave a gap when a listing goes dark. It serves the last price as a flat
**zero-volume bar on every session**. Two examples:

- **LINE** was Linn Energy at $0.1641 on every session from 2016-05-24 to 2024-07-24, then
  Lineage Inc at $73.66 on 2024-07-25. The bar file has LINE on all 2,699 sessions.
- **SN** was Sanchez Energy until 2019, flat after that, then SharkNinja from 2023-07-31.

`stitched_tickers` counts sessions between consecutive bars, so it never saw these holes. The
12-1 momentum of LINE on 2024-09-30 read +46,292%, and 63-day volatility read 89,574% a year.

Four defect classes, measured on the survivorship-free panel (`prices_deep/bars.parquet` +
`bars_delisted.parquet`, 8,563,385 bars, 4,793 symbols):

| class | rows / events | how it reads |
|---|---:|---|
| **dark runs** (zero volume, >= 5 sessions) | 7,264 runs, 173,795 rows, 664 names; 690 runs are longer than 20 sessions | a hole that hides a reused ticker or a dead listing that never dies |
| **non-trade prints** (a single zero-volume bar that moves the price > 1%) | 609 rows | a price nobody paid, e.g. TADS 2021-12-30 at $29.52 against $0.33 |
| **spike prints** (>= 4x, back within 3 sessions) | 7 events, 13 rows | KOOL 2016-03-04, MBNAB 2018-09-04 |
| **level breaks** (>= 3x on quiet volume, or across a missing session) | 95 cuts in 91 names | ch11 re-emergence under the same ticker, unadjusted exchanges, re-IPOs |

Examples of level breaks:

- Chapter 11 re-emergence under the same ticker: GPOR x527, CBL x336, XOG x111, VAL x72,
  DBD x82, CRC x13, BTU x13, WLL x34, WOLF x18.
- Unadjusted exchanges and re-IPOs: DNB, ADT, CORZ, BIOA.

Removed rows by year:

| year | rows removed |
|---|---:|
| 2016 | 12,029 |
| 2017 | 16,102 |
| 2018 | 23,987 |
| 2019 | 30,625 |
| 2020 | 31,157 |
| 2021 | 21,227 |
| 2022 | 17,664 |
| 2023 | 14,169 |
| 2024 | 6,612 |
| 2025 | 488 |
| 2026 | 357 |

Level cuts by year run from 3 (2016) to 14 (2024 and 2026).

**Same registrant does not mean same equity.** 29 gaps are SUSPENSION by the SEC registrant
test: the same CIK filed on both sides. Twelve of them carry a >= 3x level change:

- BTU, CBL, CORZ, CRC, DBD, DCTH, EXE, GPOR, VAL, OBE, SD and LTM.
- These are mostly chapter 11 cases. The registrant survives and the old shares are
  cancelled.

The defect screen cuts them anyway, and a test pins this (`test_a_same_registrant_gap_with_a_level_break_is_cut_anyway`).
The 2021 momentum contamination came from exactly these names. NBIS (18.94 -> 20.00) and the
other flat resumptions stay joined.

## 2. The second source (CRSP daily, 2016-2024)

Each large move was linked by ticker and CRSP name dates to `wrds/crsp_dsf_<y>.parquet`.

- **Calibrating the rules** (moves >= 3x that CRSP covers and that no zero-volume bar precedes,
  before the screen): 78 were real and 23 were vendor defects. **No real move traded below 2.2x its trailing median volume.** Five
  defects did (DHCP 0.25x, TST 0.36x, CBIO 0.96x, WLL 1.05x, EVHC 1.31x). That is why the
  quiet-break threshold is 2x.
- **Events the screen acted on:** 102. CRSP covers 18 of them: 17 are confirmed defects and 1
  was real (a GPOR +585% day in March 2020 that reversed within three sessions, removed as a
  spike print).
- **What the screen leaves in:** 211 moves >= 3x. CRSP covers 96 of them: **79 are real and 17
  are defects left in.** The defects left in are mostly spin-offs booked as price drops on
  heavy volume: CNX 2017-11-29, RTX 2020-04-03, IAC 2020-07-01, FNF, HRI, RRD, TRN, UHAL, CYH.
  Three are positive (CUR, RMGN, VIVO). Price and volume alone cannot separate a spin-off from
  a real crash. The screen names the 2-10x-volume class as **SUSPECT** (20 events, mostly these
  spin-offs), keeps them in the panel, and checks books against them (§3).

The receipt is `backend/data/optimus/bar_defects/bar_defects_2026-09-29T035954Z.json`. The
first run, `...033458Z.json`, has the same counts and predates the suspect list.

## 3. The fix, at the reader

`backend/services/bar_defects.screen` runs **inside `stitched_tickers.split_stitched`**. That
means every reader gets it:

- `xs_ranker.load_bars`, which feeds the ranker, the sim, `daily_review`, `llm_portfolio` and
  the book factory;
- every `cut_reader_bars` caller, which includes the strategy library's `load_wide` and, through
  it, the calendar-offset triplet, the bridge report and the sizing lab;
- the contest calendar.

It has four rules:

1. **Dark rows** are removed. After that, the stitch detector sees the hole and judges it with
   its own evidence.
2. **Spike prints** are removed.
3. **Quiet level breaks** (>= 3x on < 2x median volume) and **gap level breaks** (>= 3x across
   a missing session) are cut. The old segment becomes `SYM#k` and takes the delisting fill.
   The living symbol starts at the break, so every trailing feature is NaN until it has its
   own history.
4. **No price is changed.**

The audit dict (`stitched_tickers.LAST_AUDIT["defect_screen"]`) lists every removed run, spike,
cut and suspect.

**The book refusal.**

- `bar_defects.flagged_keys(panel)` marks every (date, name) whose 12-1 window or hold window
  contains a SUSPECT break.
- `assert_book_clean` REFUSES a book when more than **2%** of its slots sit on flagged rows.
- The triplet applies it to every cell. On today's panel all four leads have 0 flagged slots.
- An earlier refusal on feature magnitude (vol_63 > 3 or |12-1| > 20) was tried and dropped
  **before** any verdict was read from it. After the screen it refused all four leads, and the
  rows it cited were real (NVAX 2020, MARA 2021, AXSM 2019). A threshold on magnitude cannot
  tell LINE from NVAX. `implausible_rows` stays as a descriptive count only.

**Cost.** `xs_ranker.load_bars` on the real panel takes 13.5 s, against 11.9 s with the stitch
cut alone.

## 4. The leads re-read (old vs new)

All four leads are at k = 20, calendar-neutral (one third in each quarterly offset), costs on.
Each is measured against its 21-draw matched twin, with the t on non-overlapping blocks.

There are three legs:

- **OLD** is the 2026-09-28 triplet (`calendar_offsets_2026-09-28T065615Z.json`), before
  either fix.
- **STITCH** is the same code on today's bars with the stitch cut only
  (`calendar_offsets_2026-09-29T033644Z.json`, `--bar-screen off`, the audit leg).
- **SCREEN** is the stitch cut plus the defect screen, the reader default
  (`calendar_offsets_2026-09-29T034413Z.json`).

The comparison receipt is
`backend/data/optimus/strategy_library/broken_price_histories_compare_2026-09-29T034617Z.json`.
In the table, "LOO worst" is the leave-one-hold-year-out mean monthly difference, with the year
dropped in brackets.

| rule | leg | cum net since 2020 | rule - twin %/mo | t | MDE %/mo | LOO worst | verdict |
|---|---|---:|---:|---:|---:|---|---|
| `mom_12_1_q` | OLD | +661% | +1.20 | 2.49 | 1.35 | +1.08 (2020) | CANNOT_DISTINGUISH |
| | STITCH | +587% | +1.15 | 2.36 | 1.37 | +1.03 (2020) | CANNOT_DISTINGUISH |
| | **SCREEN** | **+458%** | **+0.92** | **1.83** | **1.41** | **+0.76 (2020)** | **CALENDAR_ARTEFACT** |
| `mom_12_1_q_trend` | OLD | +304% | +1.22 | 2.80 | 1.22 | +1.09 (2020) | CANNOT_DISTINGUISH |
| | STITCH | +265% | +1.14 | 2.54 | 1.26 | +1.00 (2020) | CANNOT_DISTINGUISH |
| | **SCREEN** | **+186%** | **+0.96** | **2.03** | **1.33** | **+0.80 (2020)** | **CALENDAR_ARTEFACT** |
| `qc470_mom252_quarterly_riskparity` | OLD | +585% | +1.12 | 2.62 | 1.19 | +0.96 (2024) | CANNOT_DISTINGUISH |
| | STITCH | +546% | +1.07 | 2.46 | 1.22 | +0.91 (2024) | CANNOT_DISTINGUISH |
| | **SCREEN** | **+395%** | **+0.84** | **1.91** | **1.23** | **+0.67 (2019)** | CANNOT_DISTINGUISH |
| `disp_short_avoid` | OLD | +466% | +0.81 | 1.80 | 1.26 | +0.67 (2022) | CALENDAR_ARTEFACT |
| | STITCH | +416% | +0.74 | 1.61 | 1.29 | +0.60 (2022) | CALENDAR_ARTEFACT |
| | **SCREEN** | **+342%** | **+0.58** | **1.26** | **1.29** | **+0.42 (2019)** | CANNOT_DISTINGUISH |

**`mom_12_1_q`, rule minus twin by hold year** (sum of monthly differences):

| hold year | OLD | SCREEN |
|---|---:|---:|
| 2017 | -0.05 | -0.07 |
| 2018 | +0.16 | +0.18 |
| 2019 | +0.22 | +0.21 |
| 2020 | +0.27 | +0.27 |
| **2021** | **+0.12** | **+0.02** |
| 2022 | +0.16 | +0.20 |
| 2023 | +0.16 | +0.15 |
| **2024** | **+0.22** | **+0.06** |
| 2025 | +0.03 | +0.05 |
| 2026 | +0.07 | -0.02 |

The screen took the edge out of exactly two years:

- **2021**: the re-emerged energy equities (GPOR, XOG, VAL, WLL, CRC, CBL, OBE), bought on
  12-1 scores of +2,000% to +60,000%.
- **2024**: SN, DBD, CORZ, LINE and BIOA.

By calendar offset (cum since 2020, OLD -> SCREEN):

| offset | OLD | SCREEN |
|---|---:|---:|
| jajo | +1,323% | +971% |
| fman | +424% | +298% |
| mjsd | +433% | +263% |

Delisting fills barely moved (9/16/13 -> 8/15/14), so the drop is not dead names dying earlier.

**Does the lead survive? No, not as an edge over its twin.**

- `mom_12_1_q` still compounds well above SPY on this panel.
- Its excess over the characteristic-matched twin is +0.92%/mo at t 1.83. That is below the
  project's t 2 bar and smaller than the 1.41%/mo MDE.
- Its sealed-window excess is +0.26%/mo at t 0.27.
- The calendar verdict moves to CALENDAR_ARTEFACT.

`mom_12_1_q_trend` keeps t 2.03 on the neutral average, but its offsets split and it is also
CALENDAR_ARTEFACT. The other two are CANNOT_DISTINGUISH at t < 2. Every number here is
hindsight on a panel whose living names were chosen alive on 2026-09-01.

## 5. Frozen books (read-only)

Receipt: `backend/data/optimus/bar_defects/books_2026-09-29T034841Z.json`.

**The test.** For each position, at the book's `asof`, compute 12-1 momentum and 63-day
volatility from the same bars with the reader before and after the screen. The position counts
as selected on a broken row when:

- the screen cuts its history inside the window, or
- ln(1+mom) moves by more than 0.10, or
- vol_63 changes by more than 1.5x.

**The result: 21 positions in 21 of 314 books, two tickers.**

- **WOLF**, 20 books. Wolfspeed's old equity closed at $1.21 on 2025-09-26, and the
  post-reorganisation equity opened at $22.10 on 2025-09-29. That is an 18x "move" on 1.1x
  volume, and the 12-1 score read it as momentum. The books are the momentum and
  low-asset-growth library books and their `__ew` twins, at 5% (3.5% in the inverse-vol
  `__control` books).
- **ISRL**, 1 twin: `cards_supports_2026-09-25__random_same_band`.

**TRIAL-LIB-FWD-TWIN-1: 9 of 30 pairs, all on the book side.**

- 7 were already in the 2026-09-28 stitched note.
- 2 are new: `lib_low_asset_growth_sealed_2026-09-26` and
  `lib_resid_mom_12_1_large_sealed_2026-09-26`.

A dated amendment in `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md` widens S3
to S3'. S3' removes WOLF as well as the stitched names, and a SURVIVES now needs S3' too.

No book, twin, weight or id was changed.

## 6. The world digest's ungraded third

The digest reads `prices_2025_26/bars.parquet`. The forecast grader reads the same file plus
the supplementary `bars_forecast_only.parquet` (`forecast_grader._with_forecast_only`). Neither
held sector ETFs, TLT or GLD. So every sector or macro implication was written off as
`NOT_A_TICKER_NO_PROXY_IN_PANEL`: 29 of 80 (36%) on the 2026-09-29 digest.

Five changes:

1. **`config.WORLD_DIGEST_SUBJECT_PROXIES`**: one table mapping subject -> (proxy, sign).
   - Sectors map to SPDRs and industry ETFs.
   - `rates` / `inflation` map to TLT with sign -1 (yields up means TLT down).
   - Other macro subjects: dollar -> UUP, oil -> USO, gold -> GLD, credit -> HYG,
     growth -> IWM, housing -> XHB, and the country ETFs.
   - The table also carries the free-text words the model actually wrote (utilities, defense,
     regional_banks, usd, us_rates, ...). An ETF named directly (xlf, smh, xbi) maps to itself.
   - `config.FORECAST_PROXY_ETFS` is the fixed list (45 names).
2. **`world_digest`** changed in two places, with no restructuring:
   - `subject_proxy()` re-types a sector or macro implication onto its proxy, with the
     direction times the sign. The row keeps the original subject in `inputs_used.proxy_of`.
   - `load_closes()` also reads the supplementary panel.
   - Proxy rows are graded but kept out of the shadow contract, which reads ticker subjects only.
3. **`scripts/pull_forecast_bars`** adds the proxies the main panel lacks (`--proxies-only`
   pulls just those). The receipt name now carries a run id, and a wrong returned-count was
   fixed (it counted the whole file).
4. **`scripts/pull_bars_refresh.PANELS`** gains `forecast_only`, not gated, so the nightly
   refresh keeps the proxies current. Before this, nothing ever refreshed that file.
5. **Pulled once:** 43 proxies, 2025-01-02 .. 2026-09-28, 435 sessions each. IWM and QQQ are
   already in the main panel. Receipt `prices_2025_26/forecast_bars_pull_20260929T035149Z.json`.
   `forecast_grader.local_price_fetch(["XLU","TLT","KRE"], ...)` returns their closes.

**On the 2026-09-29 digest, 25 of the 29 non-ticker implications now have priced proxies.**
The four without one (`coal`, `cnh`, `ai_regulation`, `robotics`) stay ungraded on purpose:
none has a single proxy whose sign is unambiguous.

## 7. Files

| role | path |
|---|---|
| the screen, the book refusal, the audit CLI | `backend/services/bar_defects.py` |
| wired into every reader | `backend/services/stitched_tickers.py` (`split_stitched`; the rename loop made range-based, 42 s -> 13.5 s) |
| triplet: `--bar-screen on/off`, per-cell refusal, screen summary on the receipt | `scripts/calendar_offset_triplet.py` |
| old vs new receipt | `scripts/broken_price_histories_compare.py` |
| frozen-book exposure (read-only) | `scripts/broken_price_histories_books.py` |
| config | `backend/config.py` (`BAR_DEFECT_*`, `WORLD_DIGEST_SUBJECT_PROXIES`, `FORECAST_PROXY_ETFS`) |
| digest proxies | `backend/services/world_digest.py`, `scripts/pull_forecast_bars.py`, `scripts/pull_bars_refresh.py` |
| trial amendment | `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md` |
| tests (13, offline, dates from today) | `backend/tests/test_bar_defects.py` |
| test edits | `test_world_digest.py`: the no-proxy refusal now uses `robotics`. `test_contest_stitch_and_size.py`: the same-registrant suspension resumes near its old price. |

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS.**

- The screen finds what the stitch cut could not, from the bars alone. It is precise where it
  cuts: 17 of 18 CRSP-covered actions were confirmed defects.
- It runs at every reader for about 1.6 s more.
- Momentum's impossible top-20 slots fell from 176 to 84, and every one left is a real
  momentum name.
- A third of the digest's implications can now be graded.

**WHAT DOES NOT.**

- The momentum lead. Its twin-beating edge was partly bought with fake 12-1 scores on
  re-emerged bankrupt equities (2021) and reused tickers (2024). Clean, it is +0.92%/mo at
  t 1.83, below its own MDE, and ~0 in the sealed window.
- Spin-offs booked as price drops are still in the panel (17 CRSP-confirmed left in). They are
  named SUSPECT and guarded by the refusal, not fixed.
- The 2025-26 bars have no second source on disk.

**HIGHEST-EV EXPERIMENT.** Rebuild the momentum signal from CRSP total returns (`ret`, which
handles spin-offs, distributions and delistings) for 2016-2024. Then run the same triplet and
twin comparison on that panel, and read the Alpaca-panel number beside it.

- **If the CRSP leg also sits near +0.9%/mo at t < 2:** the momentum lead retires from the
  current search (`DEPRIORITIZED`).
- **If it recovers:** the remaining spin-off defects were depressing it.

It costs one CPU hour, no dollars, and decides whether the only lead on the board is worth the
forward books frozen on it.
