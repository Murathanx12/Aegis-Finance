# Contest desk, 2026-09-29: the evening sheet for the Bloomberg Trading Challenge

**Licence:** `PRODUCT_EXPERIMENT`, family of one. Utility: "contest rank, right tail".
Whatever this book returns is never evidence for or against the project's skill.

> **AMENDED 2026-09-29 (see the AMENDMENT at the end):** the negative medians below are the zero-skill NULL's, not the rule's history (ROT_ALL's actual-sign median is positive), and the Asian report times were misread. The original text is kept unchanged below.

**Every rule below loses more often than it wins.** The median relative result is negative for
every rule, every fill, and every era. The desk sells variance for rank, and it assumes zero
skill at predicting direction. $0 LLM, no orders, no broker calls, nothing sent.

## THE OWNER'S CHECKLIST (short)

1. **Register before Sun Oct 4, 11:59 am New York (23:59 Hong Kong time).** Check that the team
   shows on portal.bloombergforeducation.com. The PDF's Key Dates say *am*; use that time, not
   the FAQ's *pm*.
2. **Export `MEMB` for `WLS Index`** (CSV or Excel) into `backend/data/optimus/contest/wls/`.
   - The folder is git-ignored because the Terminal's data is licensed.
   - With the export, the desk marks every name `CONFIRMED_WLS` or refuses it as `NOT_IN_WLS`.
   - Until then every name says `UNCONFIRMED_MEMBERSHIP`.
3. **Read `TMSG` Help and the T&C.** Write down five things:
   - the cost basis (Next Open, Next Close, VWAP...);
   - commissions;
   - whether the 20% cap is checked on the order or on market value;
   - how a non-US name is priced during US hours;
   - whether you may re-enter a ticker you already traded.

   Email bbgtradecomp@bloomberg.net with any question the Help does not answer. No draft was
   written or sent tonight.
4. **Oct 12: place one small US ticket and one small Asian ticket.** Record each fill against
   the quote. This tells you which simulation column applies:
   - fills at the close before the report: use `close`;
   - fills at the next open: use `next_open` or `open_25`.

   If fills are at the next open and there are commissions, the rotation's edge over
   buy-and-hold mostly goes away (table below).
5. **Every evening from Fri Oct 9, open `backend/data/optimus/contest/sheets/<date>.md`.**
   - The sheet is written at about 14:30 Hong Kong time. The one-line version is `<date>.txt`.
   - Do the SELL lines first, then the BUY lines in the order shown, which is Hong Kong opening
     order.
   - Before each buy, check the report date on `EVTS`. If the date moved, or the name is not in
     WLS, take the next name in section 3 of the sheet.
6. **Record a date you verified yourself** in `backend/data/optimus/contest/calendar/confirmations.csv`,
   with columns `symbol,date,timing,source_url`. A row without a URL is refused.
7. **Write the week-4 rule down before Oct 12:** inside the top ~15, lock into the five largest
   WLS weights; otherwise keep rotating. Also sign the one-line utility: "EMR" or "MAX TAIL
   (fallback)".
8. **To stop the desk,** create the empty file `backend/data/optimus/contest/STOP`. To remove the
   task: `schtasks /Delete /TN "AegisContestDesk" /F`.

## WHAT ALREADY EXISTED / WHAT I REUSED / WHAT IS NEW

| | item | where |
|---|---|---|
| EXISTED (previous builder, 2026-09-28, uncommitted) | the data layer: markets and hours in Hong Kong time, price limits, the proxy universe (Yahoo screener, market cap ≥ $300M, 18,350 names), global bars, earnings history, and a calendar with six honest date statuses | `scripts/contest_calendar.py` |
| EXISTED | the desk: the event panel, ranking by trailing \|reaction\|, the sheet, the dry run, snapshots of the option-implied move | `scripts/contest_desk.py` |
| EXISTED | the simulator: 7 rules × 3 fills, zero direction skill by construction (daily sign flip) | `scripts/contest_rotation_sim.py` |
| EXISTED | the odds script for the static book, and its tests | `scripts/contest_book_odds.py`, `backend/tests/test_contest_book_odds.py` |
| EXISTED | 23 desk tests; the scheduled task `AegisContestDesk` (daily 14:30 HKT, Oct 9 to Nov 14, STOP file aware); the pre-registration `TRIAL-CONTEST-MAG-1` | `backend/tests/test_contest_desk.py`, `docs/TRIALS/` |
| REUSED | the project's yfinance downloader; SEC 8-K item 2.02 acceptance times (US report times); `prices_deep` bars including delisted names; the stitched-ticker detector; nn_lab's frozen size-of-move file | `backend/services/global_prices.py`, `edgar_8k/`, `prices_deep/`, `backend/services/stitched_tickers.py`, `nn_lab/size_forecast/` |
| NEW tonight | the history pull and calendar build finished; the calendar for Oct 12 to Nov 13 is on disk | `contest/calendar/calendar_2026-09-29.parquet` + receipt |
| NEW | **reused tickers are cut.** Every market passes through `cut_stitched` before any feature is computed. It cuts 62 US names (the detector's 62), plus 0300.HK, 8303.T and FORCEMOT.NS. A report stamp before the new company's first bar never becomes its event | `contest_calendar.cut_stitched`, `contest_desk.build_events` |
| NEW | **a look-ahead bug fixed.** A report dated after a name's last bar was given the last bar as its buy session. On the first dry run this put Korean and Japanese names with reports in late October onto the Sep 22–24 sheets (1,048 "candidates" on Sep 24). Two future reports also collapsed into one | `contest_desk.build_events` |
| NEW | **ranking columns: `vol63 /day` and `NN size 5d`.** The second is nn_lab's forecast of the size of the 5-session move, read from its file dated strictly before the sheet (nn_lab code is never imported). It covers US names only and is display only: the frozen rule still ranks by trailing \|reaction\| | `contest_desk.nn_size_forecast` |
| NEW | `--preview` mode (writes to `contest/preview/`, never read back as holdings); `--no-refresh` now also skips the option-chain fetch; nonsense revision ratios (near-zero base) show as n/a | `contest_desk.py` |
| NEW | a table of every season, one line per season, no pooling | `contest_rotation_sim.season_table` |
| NEW | a secondary measurement registered in `TRIAL-CONTEST-MAG-1`: past move size beyond trailing volatility, global. Linter: PASS vs 358 | `docs/TRIALS/TRIAL-CONTEST-MAG-1-earnings-magnitude-beyond-implied.md` |
| NEW | the prior for that measurement, by market | `contest/prereg_prior_global_by_market.json` |
| NEW | 8 tests (synthetic, dates from today, no network) | `backend/tests/test_contest_stitch_and_size.py` |

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE in demonstrated edge.** This is a lottery ticket chosen for its shape; no rule here has shown directional skill |
| best historical rule (zero-skill sim, 2024–26, next-open fills) | ROT_ALL / ROT_US: P(> +40% relative) ≈ **9.1%**, median **−4%**, p05 **−39%**. Buy-and-hold of the five most volatile names (HIVOL_BH): 2.6% |
| best forward paper | none. The dry run Sep 14–25 is the first read, and it lost (below) |
| independent selector count | unchanged; this book is its own family |
| new actionable finding | past earnings-move size predicts the next move's size **beyond trailing volatility in every market group and year 2021–2026**. Rank-regression b: Asia 0.21–0.26, Europe 0.22–0.34, US 0.28–0.39. It is a size signal, not a direction signal |
| calendar coverage (Oct 12 – Nov 13) | 7,540 names; 64 CONFIRMED (JPX exchange file); 7,476 NOT confirmed |
| global bars | 3,620 non-US symbols + 74 extra US + 16 FX/benchmarks; ~5.9M rows; daily from 2019-06; last bar Sep 23–25 |
| LLM spend | $0.00 |

### Calendar coverage, by market and date status (all names; liquid = median $ volume ≥ $10M in brackets)

| market | CONFIRMED_EXCHANGE | VENDOR_ANNOUNCED | VENDOR_ESTIMATE | ESTIMATED_PATTERN | total |
|---|---|---|---|---|---|
| US | 0 | 2,848 (2,172) | 47 (22) | 27 (22) | 2,922 (2,216) |
| Europe | 0 | 1,551 (289) | 469 (26) | 67 (60) | 2,087 (375) |
| Japan | 64 (15) | 477 (293) | 185 (118) | 60 (29) | 786 (455) |
| India | 0 | 214 (74) | 312 (83) | 194 (102) | 720 (259) |
| Taiwan | 0 | 25 (23) | 89 (72) | 247 (186) | 361 (281) |
| China A | 0 | 0 | 0 | 290 (290) | 290 (290) |
| Korea | 0 | 33 (26) | 75 (49) | 95 (69) | 203 (144) |
| Hong Kong | 0 | 15 (12) | 92 (58) | 31 (23) | 138 (93) |
| Indonesia | 0 | 4 (1) | 24 (7) | 5 (2) | 33 (10) |
| **all** | **64 (15)** | **5,167 (2,890)** | **1,293 (435)** | **1,016 (783)** | **7,540 (4,123)** |

How to read the statuses:

- **VENDOR_ANNOUNCED is not confirmed.** It means Nasdaq's or Yahoo's vendor marks the date as
  announced. Nasdaq's calendar also lists projected dates, so this column overstates what
  companies have actually said.
- **Only the three `CONFIRMED_*` statuses render as confirmed.**
- **ESTIMATED_PATTERN** projects the last four years' same-quarter dates forward. The spread
  shown with it has a median of 7 days and a 75th percentile of 21 days.
- **Report timing** is BMO 1,381, AMC 2,303, INTRA 825 and UNKNOWN 3,031. An unknown time is held
  for two sessions.

Every name has `UNCONFIRMED_MEMBERSHIP` until the WLS export lands.

### Simulation (zero direction skill; 4,000 sign-flip draws a season; benchmark ACWI; relative to it)

**Oct 12 – Nov 13 windows, 2019–2025 (n = 7 seasons; mean of per-season numbers):**

| rule | fill | P>+20% | P>+40% (range) | P>+100% | median | p05 |
|---|---|---|---|---|---|---|
| ROT_ALL (rotation by past move, all markets) | close | 20.4% | 8.0% (3.0–17.2) | 0.6% | −3.5% | −37.4% |
| | next_open | 16.9% | 4.8% (1.0–10.0) | 0.1% | −2.5% | −31.1% |
| | open_25 | 7.1% | 1.6% (0.0–5.3) | 0.0% | −13.1% | −38.6% |
| ROT_US | close / next_open / open_25 | 20.5 / 17.2 / 7.1% | 8.2 / 5.0 / 1.7% | 0.7 / 0.1 / 0.0% | −3.8 / −2.7 / −12.7% | −37.0 / −31.2 / −38.5% |
| ROT_ASIA | close / next_open / open_25 | 8.2 / 4.1 / 0.3% | 0.7 / 0.0 / 0.0% | 0 | −0.8 / −0.4 / −9.0% | −20.2 / −16.1 / −23.5% |
| ROT_RANDOM (control: random rank) | close / next_open / open_25 | 7.3 / 4.5 / 0.8% | 0.3 / 0.1 / 0.0% | 0 | −0.8 / −0.4 / −11.4% | −19.9 / −17.2 / −27.7% |
| MOM_ROT (momentum rotation) | close / next_open / open_25 | 15.1 / 16.9 / 7.0% | 2.8 / 4.4 / 1.1% | 0 | −1.8 / −1.9 / −12.3% | −27.6 / −30.4 / −38.3% |
| HIVOL_BH (hold 5 most volatile) | close / next_open / open_25 | 11.5 / 11.1 / 10.7% | 2.6 / 2.5 / 2.6% | 0 | −1.6 / −1.7 / −1.9% | −24.1 / −24.6 / −24.7% |
| REHEARSAL_BH (10 × 10% US, rehearsal-shaped proxy) | close / next_open / open_25 | 8.3 / 8.1 / 7.4% | 1.0 / 1.0 / 0.9% | 0 | −1.1 / −1.2 / −1.7% | −20.0 / −20.0 / −20.5% |

**2024–26, all four seasons (n = 11):**

| rule | close P>+40% | next_open P>+40% | open_25 P>+40% | next_open median / p05 |
|---|---|---|---|---|
| ROT_ALL | 10.0% | 9.1% | 4.4% | −4.0% / −39.0% |
| ROT_US | 9.8% | 9.1% | 4.7% | −4.3% / −38.9% |
| ROT_ASIA | 0.9% | 0.2% | 0.0% | −0.7% / −17.5% |
| ROT_RANDOM | 1.0% | 0.4% | 0.0% | −0.9% / −19.6% |
| MOM_ROT | 4.3% | 4.4% | 1.0% | −2.0% / −30.7% |
| HIVOL_BH | 2.7% | 2.6% | 2.5% | −2.0% / −23.2% |
| REHEARSAL_BH | 1.1% | 1.2% | 1.1% | −1.4% / −20.2% |

Every season is printed on its own line in `contest/sim/sim_20260928T182048Z.md`. For ROT_ALL,
next open, P(> +40%) was 1.5–16.8% by season: 10.0% in Oct 2024, 7.8% in Oct 2025, and 16.8%
in Jul 2026, the latest.

**What the tables say:**

- **The magnitude ranking is the whole effect.** With the same rotation and a random rank,
  P(> +40%) falls from 9.1% to 0.4%.
- **An Asia-only rotation is not the route here.** Asian earnings reactions are smaller, and
  the ranking still works there (b 0.21–0.26), but (inferred, not measured) the largest Asian moves are too small to
  reach the tail. Only ~3% of Asian report stamps lack a time, so two-session holds do not
  explain it.
- **The winners' Asian route was limit moves on momentum, and our MOM_ROT does not reproduce it:**
  4.4% at next open, 1.0% with 25 bps a side.
- **With 25 bps a side, the rotation's advantage over buy-and-hold shrinks** (4.4% against 2.5%).

**Caveats:**

- Outside the US the panel is **survivor-selected**: today's listings only, which overstates
  every non-US rule.
- The bars are unadjusted.
- Non-US report dates are Yahoo's (vendor).
- The benchmark is ACWI, a proxy for WLS.
- One sim step is one day even when a hold spans two sessions.

### Dry run, Sep 14–25 2026 (sheets built each day from data before that day)

The report dates in the dry run are the **actual** ones: Nasdaq's calendar for the US, Yahoo's
elsewhere. The live desk will know them only as vendor or estimated dates, so the dry run is
kinder than live.

| fill | book NAV end | vs ACWI (+0.5%) |
|---|---|---|
| close before the report | 0.929 | **−7.6 pp** |
| next open | 0.963 | **−4.2 pp** |
| next open, 25 bps a side | 0.945 | **−6.0 pp** |

- **What it bought:** 22 positions over 8 active days, mostly US (PLAY, WOR, CBRL, KBH, SNX, PAYX,
  SCHL, COST, ...), plus 9961.HK, 4716.T, ABVX.PA and HM-B.ST.
- **Two days had nothing to buy** (Sep 15, Sep 25), and one (Sep 24) is partly unscored
  because NB's reaction is not in the bars yet.
- **Late September is a thin earnings week,** so this is a pipeline check, not a performance
  read.

### Preview: the Oct 12 sheet from today's calendar (`contest/preview/2026-10-12.md`)

It would buy UNH, ACI, WFC and BLK (US, BMO Oct 13, bought at the 21:30 HKT open), plus
600256.SS (China A, 09:30 HKT Oct 13). Reserves: 8267.T, C and GS.

- All five dates are NOT CONFIRMED.
- The bars are 17–19 days stale in the preview. On the night, the task tops them up.

## What this does NOT do

- **It does not predict direction.**
- **It does not prove WLS membership, confirm dates, or settle any contest convention.**
  Membership needs the export; dates need `EVTS`; conventions need the Terminal Help.
- **It does not model Asian daily price limits in the fills.** The limits are listed per market
  in `contest_calendar.MARKETS`, most marked UNVERIFIED.
- **It does not register `TRIAL-CONTEST-MAG-1` in the experiment registry (`rule_experiments`).**
  That code lives in files outside this builder's ownership. The trial file must be committed
  before the first reaction session, Oct 12 13:30 UTC.

**WHAT WORKS:** the ranking picks names that move. Past earnings-move size beats trailing
volatility at predicting the next move's size in the US, Europe and Asia in every year
2021–2026. The rotation built on it roughly triples buy-and-hold's chance of +40% relative under
zero direction skill.

**WHAT DOES NOT:** direction is a coin flip. Every rule's median is negative, and the dry run
lost 4–8 pp in two weeks. Asian-only and momentum rotations do not reach the tail. Commissions
or next-open fills take away most of the rotation's advantage.

**HIGHEST-EV EXPERIMENT:** on Oct 12, place the two small test tickets (one US, one Asian) and
read the fill convention. That one observation decides between ROT and MAX TAIL, and between
roughly 9% and 2–4% odds of a top-10 result. It costs nothing.


---

## AMENDMENT 2026-09-29 (builder, after `docs/reviews/REVIEW_2026-09-29_CONTEST_DESK.md`)

This is a dated amendment. The text above is unchanged, and so are the receipts it cites. Each
correction below was checked against the code and the receipts before it was written.

**RESULTS SCOREBOARD.**

- RESULT IMPROVEMENT: **NONE in edge.**
- The owner had been told two wrong things, both corrected below:
  - the median of the zero-skill null was presented as the rotation's own median;
  - Asian report times were read wrongly.
- The comparison the owner asked for ran on 31 seasons, 3 event pools and 4 books.
- Its verdict: **keep the desk's rule; the reviewer's book is not measurably better or worse.**
- LLM spend: $0. No network was used.
- New receipts:
  - `contest/sim/sim_20260929T030501Z.json` (the same sim, with corrected timing);
  - `contest/compare/compare_20260929T031424Z.json`, with `_derived.md` / `_derived.json` and `_daily.parquet`;
  - `contest/compare/prior_by_market_timingfix_20260929T032407Z.json`.

### A1. A 00:00 UTC report stamp is "time unknown" (finding 1: verified)

**What was wrong.**

- Yahoo writes "time not supplied" as exactly 00:00 UTC. That is 13,298 of 21,458 Japanese
  history stamps (62%).
- The code read these as 09:00 JST, i.e. INTRA, so the desk measured and traded the day BEFORE
  the reaction.
- Across all non-US history, the fix reclassifies **17,281 of 80,922** stamps to UNKNOWN:

  | market | stamps reclassified |
  |---|---|
  | JP | 13,298 |
  | EU | 1,341 |
  | TW | 1,231 |
  | CN | 745 |
  | KR | 276 |
  | HK | 163 |
  | IN | 128 |
  | ID | 99 |

- The note's line "only ~3% of Asian report stamps lack a time" was wrong.

**What changed** (`contest_calendar.is_untimed_stamp` / `stamp_timing` / `untimed_mask`):

- An untimed report is held for two sessions, from the session before its day to the session
  after it. That covers the reaction whether the print comes before the open or after the
  close.
- The same rule is now used by `event_sessions`, `usual_timing`, `dedupe_stamps` and the live
  desk's calendar stamps (`contest_desk.calendar_stamp`).
- `usual_timing` now needs a strict majority of real times.
- The live desk used to assume AMC for an unknown time. That buys a BMO print a day late and
  can sell before the reaction.
- The screener's real release times (20:00 or 12:30 UTC) are now read, except on estimated
  dates.

**"Confirmed" now separates the date from the time.**

- The calendar receipt carries `n_confirmed_timed` and `n_confirmed_time_unknown`.
- The sheet prints "DATE CONFIRMED, TIME UNKNOWN (held two sessions)".
- On `calendar_2026-09-29.parquet`, all 64 CONFIRMED (JPX) rows are confirmed dates with
  **unknown times**: 58 were UNKNOWN, and 6 carried a placeholder INTRA. **Confirmed and timed:
  0.** The file on disk predates the fix; the next calendar build writes the split.

**The Asia analysis, re-run** (next-open fills; NULL = zero direction skill):

| ROT_ASIA | NULL P(> +40%), Oct 2019-25 | NULL P(> +40%), 2024-26 | realised median, Oct | realised median, 2024-26 |
|---|---|---|---|---|
| before (`sim_20260928T182048Z`) | 0.0% | 0.2% | +7.5% | n/a (not printed) |
| after (`sim_20260929T030501Z`) | 0.1% | 0.8% | +10.2% | +14.2% (9 of 11 seasons positive) |

**Restated conclusion.**

- An Asia-only rotation still does not reach the right tail under zero skill: P(> +40%) stays
  at or below 1%, now measured on the correct sessions.
- Asian earnings reactions are too small to carry a five-name book past +40%.
- Their size is still predictable. Re-measured with the corrected timing, b is 0.20-0.28 in
  Asia excluding India, 0.14-0.19 in India, 0.18-0.33 in Europe, and unchanged in the US.
- ROT_ALL and ROT_US are indistinguishable (2024-26 NULL P(> +40%): 8.9% vs 9.1%). Asia adds
  nothing to the tail.

### A2. The rotation's own distribution (finding 2: verified)

**The median in the header is the null's, not the rule's.** The header's "every rule's median is
negative" is the median of the zero-skill null, which puts one random sign on each day. The
same receipt stores the actual-sign path as `realised`.

**ROT_ALL, next-open fills, all 31 seasons 2019-26, actual signs.** Measured on the corrected
timing (`sim_20260929T030501Z`); the pre-fix receipt is in brackets.

| statistic | value |
|---|---|
| median | +6.3% [+11.1%] |
| mean | +12.5% [+12.7%] |
| seasons positive | 21 of 31 [20] |
| above +20% | 10 of 31 [10] |
| above +40% | 6 of 31 [5] |
| below −20% | 4 of 31 [4] |

**October seasons only (the contest's season, 7 of them).**

| rule | median | positive | above +20% | above +40% | below −20% |
|---|---|---|---|---|---|
| ROT_ALL | +12.1% | 5 of 7 | 2 of 7 | 1 of 7 | 2 of 7 |
| ROT_US | +1.3% | 4 of 7 | 2 of 7 | 1 of 7 | 2 of 7 |

The null's medians (−2.5% to −4%) are a property of the null, and the tables now print both.

**Is the positive realised drift real, or survivorship?** The US event pool (SEC 8-K item 2.02)
holds events for 0 of the 1,638 names in the panel whose bars stop early. IBES actuals (on
disk: announcement date and New York time) add 700 of them, with 10,958 events. Book-level
results from `compare_20260929T031424Z`, 10 bps a side:

- **Survivorship inside IBES:** dead names included minus dead names excluded.
  - +1.2 pp a season on average (median 0.0, t 1.56).
  - Including the dead names did NOT lower the result.
  - The last season where any difference appears is 2022-Jul. The bars hold almost no deaths
    after 2022, so for 2023-26 survivorship is **unmeasured**. It is bounded only by the
    2019-22 reading, which pointed the other way.
- **The print itself:** the desk rule minus a control that holds, in each slot, a liquid
  company with no report within 5 sessions and the nearest 63-session volatility.
  - SEC pool: +9.0 pp a season on average (median +1.5, 18 of 31 seasons positive, t 1.76).
    Leaving out the best season gives +6.2.
  - IBES pool: +9.8 pp (median +5.0, t 2.03).
  - A random ranking of reporting names also has a positive realised median: +2.9% after the
    fix, and +8.3% in Octobers.
- **Reading:** most of the drift belongs to holding names that are reporting, and it is right
  skewed (2020 and 2025-Jul dominate). That is consistent with the documented
  announcement-period effect. At about 30 seasons and t ≤ 2.03 it is **not a claim**. It is a
  reason to expect the realised path to beat the null, not to size on.

### A3. The reviewer's book against the current one (the owner's brief, 2026-09-29)

**Utility, declared: RISK-SEEKING.** The objective is a top-10 finish of about 2,700 teams.
The quantity maximised is P(relative > +40%). A loss worse than "not top 10" is not
penalised. The top-10 line itself is soft, somewhere between +20% and +55%.

**Contest rules applied.**

- US listings only; five slots at 20% of NAV; long only.
- Gross exposure is never above 100%; the simulator asserts it.
- Buy at the open of the session before the print, sell at the next open. An untimed print is
  held two sessions.
- Costs of 0, 10 and 25 bps a side. Commissions are the owner's to confirm.
- Benchmark: ACWI, as a proxy for WLS.

**The four books.**

| book | what it holds |
|---|---|
| CURRENT | the desk's rule: trailing mean \|earnings reaction\|; cash when fewer than 5 names report |
| CURRENT_FILL | the same, with empty slots filled by the most volatile liquid operating companies |
| REVIEWER | ranked by the expected earnings move, i.e. the mean rank of trailing \|reaction\| and nn_lab's walk-forward size-of-move forecast (from 2020); empty slots filled with the most volatile names |
| VOLMATCH_CONTROL | the control from A2 |

The option-implied move could not be used: no history of it exists on disk.

**How to read the P columns.**

- **NULL** is zero direction skill.
- **BOOT** resamples the season's own days, so it keeps that season's drift. It is an
  optimistic, conditional reading.
- The truth for a new October is between the two.
- Realised counts are seasons out of n.

**The contest table** (SEC 8-K pool, the desk's own; 10 bps a side). Each P cell reads
P(> +20% / > +40% / > +60% / < −20%).

| window | book | realised median | realised > +20 / > +40 / > +60 / < −20 | NULL P | BOOT P |
|---|---|---|---|---|---|
| Oct 2019-25 (n 7) | CURRENT | −2.5% | 2 / 0 / 0 / 2 | 12.1 / 3.2 / 0.8 / 21.9% | 34.0 / 16.8 / 6.7 / 29.9% |
| | CURRENT_FILL | −3.2% | 2 / 0 / 0 / 2 | 12.9 / 3.3 / 1.0 / 25.0% | 33.2 / 16.0 / 5.9 / 30.2% |
| | REVIEWER | −3.6% | 1 / 1 / 1 / 1 | 13.0 / 3.6 / 0.7 / 25.0% | 35.2 / 22.9 / 13.2 / 31.1% |
| 2024-26, all seasons (n 11) | CURRENT | +3.4% | 4 / 2 / 1 / 2 | 17.3 / 7.8 / 3.2 / 31.1% | 39.3 / 22.8 / 14.6 / 18.5% |
| | CURRENT_FILL | +3.3% | 4 / 2 / 1 / 2 | 19.2 / 8.4 / 3.7 / 31.5% | 38.7 / 21.2 / 12.8 / 18.1% |
| | REVIEWER | +6.1% | 3 / 2 / 2 / 1 | 18.3 / 7.7 / 2.8 / 32.7% | 39.8 / 28.3 / 20.2 / 17.4% |
| 2019-26, all (n 31) | CURRENT | +0.1% | 8 / 3 / 1 / 7 | 13.1 / 4.3 / 1.7 / 24.4% | 30.0 / 15.9 / 7.8 / 24.6% |
| | REVIEWER | −0.3% | 7 / 4 / 2 / 6 | 15.1 / 5.5 / 1.8 / 27.1% | 32.2 / 19.4 / 11.3 / 23.6% |

**The effect of costs** (CURRENT, 2024-26, NULL / BOOT P(> +40%)):

| cost a side | NULL | BOOT |
|---|---|---|
| 0 bps | 9.1% | 26.2% |
| 10 bps | 7.8% | 22.8% |
| 25 bps | 5.2% | 17.9% |

Every season is printed on its own line, all four P's, in
`contest/compare/compare_20260929T031424Z_derived.md`.

**Paired season differences, 10 bps** (`_derived.json`):

| comparison | SEC pool | IBES pool |
|---|---|---|
| REVIEWER minus CURRENT | +1.0 pp (t 0.36) | −1.4 pp (t −0.49) |
| CURRENT_FILL minus CURRENT | −1.0 pp (t −1.2) | — |

Two reasons the reviewer's changes do not show:

- The size-of-move blend moves the ranking. Its sign flips with the event pool.
- The no-cash rule is almost never used. In season there is nearly always a fifth reporting
  name: fillers averaged 0.1-0.2 of the 5 slots.

**Which book maximises P(top 10).**

- Under the null the books cannot be told apart. P(> +40%) is 3-4% for Octobers and about 8%
  for 2024-26 at 10 bps.
- Under the season-drift bootstrap, REVIEWER is ahead on the SEC pool (22.9% against 16.8% in
  October) and behind on the IBES pool (22.3% against 27.2% in 2024-26).
- None of the differences is distinguishable. **Recommendation: keep CURRENT**, the frozen
  desk rule:
  - it is the book the registered TRIAL-CONTEST-MAG-1 grades;
  - the reviewer's changes buy no measurable odds;
  - the implied-move ranking cannot be backtested here.
- **The honest odds** for a top-10 finish with CURRENT at 10 bps:
  - P(> +40%) between about 3% (the October null) and about 17-23% (a season whose drift
    repeats);
  - realised history: 3 of 31 seasons above +40%, and 0 of 7 Octobers.
- **The price:** P(< −20%) is 22-31% under the null.
- If fills turn out to be at the next open with 25 bps a side, every tail probability falls
  by about a third.

**Not done here:**

- The vendor-date miss rate (finding 3). The dry run and the simulation use the actual dates;
  the live desk will not have them.
- Pricing the implied move (finding 4). The desk already snapshots it forward, into
  `contest/implied/`, for the trial.
