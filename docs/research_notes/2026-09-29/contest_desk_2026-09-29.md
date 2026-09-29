# Contest desk, 2026-09-29: the evening sheet for the Bloomberg Trading Challenge

**Licence:** `PRODUCT_EXPERIMENT`, family of one. Utility: "contest rank, right tail".
Whatever this book returns is never evidence for or against the project's skill.

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
