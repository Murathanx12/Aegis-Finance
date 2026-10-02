# Contest dress rehearsal, 2026-09-29 night: the desk run daily until Oct 9, thirteen failure drills, and the book comparison re-run

**Licence:** `PRODUCT_EXPERIMENT`, family of one. Utility, declared: **contest rank, right tail**
(first place or top 10 of about 2,700 teams; a large chance of a loss is accepted). Whatever this
book returns is never evidence for or against the project's skill.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE in edge.** The book is a variance bet. No direction prior has survived, and none is used |
| best historical rule (Oct 2019-25, 10 bps a side, zero-skill null) | ROT5_TRAIL, the desk's frozen rule: P(> +40% relative) **2.5-4.9%**, P(< -20%) **24-25%** (range across two event pools) |
| same rule, 2024-26 regime (11 / 9 seasons) | null P(> +40%) **6.4-7.9%**; season-drift bootstrap **24-30%**; realised 2-3 of 9-11 seasons above +40% |
| best forward paper | none yet. Tonight's sheet missed the open (below); the first gradable sheet is 2026-09-30 |
| independent selector count | unchanged (this book is its own family) |
| new actionable findings | four defects found by the drills and fixed before the contest (holiday sessions, two share classes, >100% gross on two-session holds, pattern-estimated dates); US report times are **unknown for 82%** of Nasdaq's rows |
| drills | **13 of 13 PASS** after the fixes (`contest/rehearsal/drills/drills_20260929T135128Z.json`) |
| LLM spend | $0.00 |

## Tonight's sheet (answers "make tonight's sheet")

- The instruction arrived at 21:23 Hong Kong time, 7 minutes before the 21:30 US open. The first
  frozen sheet (2026-09-29) was frozen at **13:43 UTC, 13 minutes after the open**. Its five US buys
  (CNXC, AIR, FDS, JBL, CALM) are therefore **VOID_LATE**: printed for the record, never graded. No
  Asian name was eligible in that window. This is the "PC late at sheet time" drill happening for real,
  and the code did what it should.
- **The next session's sheet, 2026-09-30, was frozen at 13:48 UTC on 09-29**, about 32 hours before its
  first open. Sheet code **BE6D9938**:

| ticket | side | shares | limit | session (HKT / New York) | report (vendor date, not confirmed) |
|---|---|---|---|---|---|
| PRGS US Equity | BUY | 4,833 | 41.38 | Wed 30 Sep 21:30 / 09:30 | 10-01 AMC |
| MU US Equity | BUY | 180 | 1,107.00 | Wed 30 Sep 21:30 / 09:30 | 10-01 AMC |
| AYI US Equity | BUY | 622 | 321.21 | Wed 30 Sep 21:30 / 09:30 | 10-01 BMO |
| ACN US Equity | BUY | 1,091 | 183.19 | Wed 30 Sep 21:30 / 09:30 | 10-01 BMO |
| 4088 JT Equity | BUY | 10,600 (lot 100) | JPY 2,959 | Thu 01 Oct 08:00 / Wed 20:00 | time unknown, held two sessions (vendor ESTIMATE) |

  Control: 5 lines, 17,326 BUY shares, $998,095 at the limits. On this sheet the note column's "report"
  date is the EXIT session. The label was fixed for later sheets; the frozen file is not edited.
- The scheduled task `AegisContestRehearsal` (daily 14:30 HKT, Sep 30 to Oct 15) was triggered once by
  hand tonight. It exited 0, graded (5 positions, PENDING_ENTRY) and refused to rewrite the frozen sheet.

## What a rehearsal day is (identical to a contest day except the folder)

1. **14:30 HKT.** The task grades every position whose exit bar exists. It then builds the desk's
   ranking for the window [d 14:00, d+1 14:00 HKT): Europe d, US d, Asia d+1.
   - The rehearsal uses a near-dated calendar in `contest/rehearsal/calendar/`; the contest calendar
     is never touched.
2. **The ORDER SHEET** (`scripts/contest_orders.py`). Each ticket shows:
   - the Terminal ticker with its exchange code, the side, and the quantity in shares;
   - a limit 5% above the last close;
   - the session in HKT and New York time;
   - a two-character line code.
   Sizing: the notional AT THE LIMIT stays under min(20% of NAV, $200k). SELLs come first. A control
   block gives the line count, the shares per side and an 8-character SHEET CODE.
3. **Frozen once.** `orders.json` is written once; a second write is refused. Its sha256 goes to
   `freeze_log.jsonl`. A line whose session opened before the freeze is VOID_LATE.
4. **Graded at the opens.** Buy at the open of the buy session, sell at the open of the exit session
   (an untimed print is held two sessions). Everything is in shares and USD, against ACWI opens.
   - Halted at entry: no fill. Open above the limit: no fill. Halted at exit: sell at the next open.
     Price source down: PENDING, never guessed.
5. **Verify.** `python -m scripts.contest_rehearsal verify --date <d> --entered <blotter>` names every
   mistake in the typed blotter and prints the sheet code only for an exact entry. On the real 09-30
   sheet it caught a slipped zero, a flipped side and a missing exchange code in one pass.

The rehearsal writes buying sheets through **Oct 9**, then SELL-only sheets for 5 days, so every
position closes and is graded. From **Oct 11** the contest desk task (`AegisContestDesk`) runs the
same code in contest mode and writes `contest/live/sheets/<date>/order_sheet.md`.

## Failure drills (each executed; receipt `contest/rehearsal/drills/drills_20260929T135128Z.json`)

| # | drill | verdict | what happened / what was fixed |
|---|---|---|---|
| 1 | earnings date moved or wrong | PASS | Miss rates were measured (next table). A frozen sheet refuses a rewrite. Every sheet carries reserves. **Fixed:** a date whose only source is ESTIMATED_PATTERN is refused (exact on 27.7% of 19,210 past prints) |
| 2 | report time unknown | PASS | Unknown time: held two sessions, from the session before the date to the session after it. A Japanese 00:00 UTC stamp is read as UNKNOWN |
| 3 | fewer than five names | PASS | The names that report are bought and the rest stays in cash, stated on the sheet. Filling empty slots measured -1.0 pp a season (t -1.2) |
| 4 | name not in WLS | PASS | With a MEMB export, a non-member is refused and the next name moves up. **Still owed: the export itself** |
| 5 | halted or gapping name | PASS | Halted at entry: NO_FILL. Open above the limit: NO_FILL. Halted at exit: sold at the next open. A 40% gap reads GAP: skip |
| 6 | price source down | PASS | Grades go PENDING (never fabricated). The sheet is still written from the last bars with a STALE banner. **Fixed:** the drill no longer writes to the real bar files |
| 7 | PC asleep at sheet time | PASS | Both tasks now have WakeToRun + StartWhenAvailable, and the local power conditions were relaxed (recorded locally). A late freeze VOIDs opened sessions; a missed sell prints OVERDUE. **Owner:** the machine's wake setting does not yet let the tasks wake it (recorded locally), and the tasks run only while signed in |
| 8 | holiday or half day | PASS after fix | **Fixed:** future sessions came from weekdays, so the desk would have bought on Japan's Sports Day (Oct 12, contest day 1) and in China's Golden Week. Now `exchange_calendars`. No US holiday or half day falls inside the contest |
| 9 | split between sheet and fill | PASS | Terminal price beyond 30% of the sheet's reference: within 3% of a split ratio reads SPLIT_SUSPECT (shares / ratio); otherwise GAP (skip) |
| 10 | two share classes | PASS after fix | **Fixed:** every listing was ranked separately, so GOOGL + GOOG would take two slots on one print. Now one line per issuer. The proxy universe has 2,453 issuers with 2+ listings |
| 11 | stitched or defect-flagged ticker | PASS | A `bar_defects` flag inside the 2-year trailing window refuses the name. A reused ticker's old history is cut before any feature |
| 12 | 20% cap breached by drift | PASS after fix | **Fixed:** the desk bought five new names daily while two-session holds were still open, so gross could exceed 100% (leverage). Held slots now count. A +50% move puts a name at 27% of NAV; the trim is printed. **Owner:** at entry or at all times? |
| 13 | manual-entry mistake | PASS | Seven blotters tested: the exact one passes with the same code; slipped zero, transposed digits, flipped side, ticker typo, missing exchange code and missing line are each named |

### Vendor-date miss rates (receipt `contest/rehearsal/vendor_miss/vendor_miss_20260929T133948Z.json`, no network)

| comparison | n | result |
|---|---|---|
| A. IBES actuals vs SEC 8-K, US, 2015-2026 (two after-the-fact sources) | 73,744 matched | same date 93.2%; off by 1 business day 5.5%, 2+ 1.3%; **reaction session differs 3.0%**; improving yearly (86.8% same day in 2015 to 95.7% in 2026) |
| B. the desk's pattern estimator, 14 days ahead, 2022-26 | 19,210 | **exact 27.7%**, within 1 day 40.8%, off 2+ days 59.3%. It is unusable without EVTS |
| C. Nasdaq day listings vs Yahoo stamps, same days | 180 / 42 matched | same date 97.6%; **82% of Nasdaq rows carry no time** |
| D. two FORWARD vendors (Nasdaq vs Yahoo screener), Sep 29 - Oct 2 | 22 | same date 72.7%; 88.9% when Yahoo says "announced" |

**Reading.**

- A forward VENDOR_ANNOUNCED date is probably right 85-95% of the time. That is between D and A, and
  the real forward rate is being measured now by the rehearsal.
- A pattern date is wrong 72% of the time.
- The strategy lab replays date misses as slots that hold the name through an ordinary session:
  - 10% misses: the October null P(> +40%) barely moves;
  - 30% misses: it falls from 2.5-4.9% to 2.0-2.3%;
  - 30% misses, 2024-26: from 6.4-7.9% to 3.5-4.1%.

## Strategy comparison (receipt `contest/strategy_lab/lab_20260929T134312Z.{json,md}`)

**Setup.**

- US listings, 5 slots of 20%, long only; gross ≤ 100% is asserted.
- Buy at the open of the session before the print, sell at the reaction session's open. Report timing
  is corrected.
- Two pools:
  - SEC8K: the desk's pool; it has no dead names;
  - IBES_ALL: dead names included, the survivorship-free reading through the IBES end.
- Costs of 0 / 10 / 25 bps a side; 4,000 draws a season. Monte Carlo noise is about ±1 pp: two runs of
  the same cell read 3.5% and 2.5%.
- NULL is zero direction skill. BOOT resamples the season's own days, so it keeps the drift and is
  optimistic.

**October seasons 2019-25, 10 bps a side**, P(> +20% / > +40% / > +60% / < -20%). The two numbers in
each cell are SEC8K / IBES_ALL.

| book | NULL | BOOT | realised: >+20 / >+40 / <-20 (of 7) |
|---|---|---|---|
| **ROT5_TRAIL** (the desk's rule, past move size, held through the print) | 12-15 / **2.5-4.9** / 0.7-1.2 / 24-25% | 34-35 / 17 / 6-9 / 28-30% | 2 / 0-1 / 2 |
| ROT3_TRAIL (3 names, 60% gross) | 9-10 / 1.3 / 0.1-0.2 / 13-17% | 19-28 / 4-14 / 0.4-3.5 / 17-28% | 0-2 / 0-1 / 1 |
| ROT5_TRAIL_BEFORE (sold before the print) | 0.3-0.4 / 0.0 / 0.0 / 2-3% | ≤ 0.7 / 0.0 / 0.0 / 16-21% | 0 / 0 / 0-1 |
| ROT5_BLEND (past move + nn_lab size forecast) | 11-12 / 3.0-3.1 / 0.5-0.8 / 21-25% | 39-40 / 22-26 / 9-15 / 21-27% | 2-3 / 0-1 / 1 |
| ROT5_SIZE (nn_lab size forecast alone) | 10-11 / 2.6-2.8 / 0.5 / 18-20% | 16-20 / 6-9 / 1-3 / 28-33% | 1 / 0 / 1-2 |
| ROT5_RANDOM (selection null) | 3.5-4.3 / 0.1-0.3 / 0.0 / 10-12% | 12-19 / 3-6 / 0.3-0.9 / 11-15% | 0-1 / 0 / 0-1 |
| MAXTAIL_BH (5 highest-vol names, held) | 9-13 / 2.2-2.9 / 0.4-1.0 / 9-13% | 8-13 / 3.5-7 / 1-4 / 9-14% | 1 / 0 / 0 |

**Costs.** ROT5_TRAIL, October null P(> +40%): 4.3-6.0% at 0 bps, 2.5-4.9% at 10 bps, 1.8-1.9% at
25 bps. MAXTAIL_BH does not move with costs.

**All seasons, 2024-26 regime, 10 bps, NULL P(> +40%).**

| book | NULL P(> +40%) |
|---|---|
| ROT5_TRAIL | 6.4-7.9% |
| ROT5_BLEND | 4.6-7.8% |
| ROT5_SIZE | 3.7-6.7% |
| ROT3_TRAIL | 3.1-3.7% |
| MAXTAIL_BH | 3.4-3.9% |
| ROT5_RANDOM | 0.3-0.7% |

**Realised October seasons, ROT5_TRAIL, 10 bps.**

| pool | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| SEC8K | -33% | +26% | -12% | -31% | -2% | +3% | +36% |
| IBES_ALL | -44% | +20% | -8% | -21% | +28% | +53% | +12% |

The same rule on two event pools differs by up to 50 pp in one season (2024-Oct). **Sampling noise
dominates every season-level comparison here.**

**Paired realised differences, 31 / 29 seasons, 10 bps. None is a claim.**

| comparison | mean | t |
|---|---|---|
| ROT5_TRAIL minus ROT5_RANDOM | +4.1 to +4.8 pp | 0.9-1.1 |
| held through the print minus sold before it | +8.7 to +9.9 pp | 1.8-2.2 |
| BLEND minus TRAIL | -1.0 to +2.6 pp | -0.3 to 1.0 |
| SIZE minus TRAIL | -5.5 to -6.6 pp | -1.4 to -1.6 |
| 3 names minus 5 names | -2.4 to -2.6 pp | -0.8 to -0.9 |

**What the table says.**

- **Hold through the print.** Selling before it removes the tail entirely. P(> +40%) is 0.0% under both
  NULL and BOOT: the variance being bought IS the print.
- **Five names, not three.** The 20% cap forbids concentrating above 20% a name. Three names means 40%
  cash, and 40% cash lowers the right tail: null P(> +40%) is 1.3% against 2.5-4.9% in October.
- **Past move size, not the nn size forecast.** The forecast alone is worse in 5 of 6 era-pool cells,
  and the blend is indistinguishable (it helps on the SEC pool and hurts on IBES).
- **A direction prior: none.** None has survived (09-29: 76 bridged rules, none beats the market;
  TRIAL-PT-REVERSAL-1 FAILED_VARIANT). The book assumes a coin flip on direction.

### What a top-10 finish has needed

**Unknown.** Bloomberg publishes no distribution. The public anchors on disk
(`docs/research_notes/2026-09-25/research_bloomberg.md`, `REVIEW_2026-09-28_CONTEST_BOOK.md` §6) are
these:

| year | anchor |
|---|---|
| 2025 | rank 69 of ~2,700 at about +5.3% relative |
| 2024 | top 3% at about +20.5% |
| 2022 | #2 at +31% relative |
| winners | +67.7% (2023, absolute), about +168% (2024), +400% (2025) |

A top-10 line in 2024-25 was therefore probably above +40%, but no source puts a number on it. The
table above gives P at +20 / +40 / +60 so the reader can pick the line.

### Recommendation

- **The book: ROT5_TRAIL**, the desk's frozen rule, delivered through the order sheet with tonight's
  refusals (issuer, defect, pattern date) and slot accounting. At 10 bps a side:

  | reading | P(> +40%) | P(< -20%) |
  |---|---|---|
  | zero skill, Octobers | 2.5-4.9% | about 25% |
  | the season's drift repeats | about 17% | about 30% |
  | the 2024-26 regime (zero skill) | 6-8% | |
  | realised history | 0-1 of 7 Octobers | 2 of 7 Octobers |

- **Fallback: MAXTAIL_BH.** Hold the five highest-volatility WLS names, bought once. Use it if TMSG
  fills at the next open after a close decision, if commissions are 25 bps or more, or if the owner
  cannot enter tickets daily.

  | P(> +40%), zero skill | P(< -20%) | realised above +40% |
  |---|---|---|
  | 2.2-3.9%, insensitive to costs | 9-15% | 0 of 31 seasons |

- **This is a variance bet, not a demonstrated edge.** Every probability above assumes zero skill at
  direction or replays a season's own drift. The magnitude ranking's measured contribution (TRAIL
  minus RANDOM) is t ≈ 1.

## Code (uncommitted, work branch)

| file | what |
|---|---|
| `scripts/contest_orders.py` | new: tickets, sizing at the limit, lots, sheet code, `verify`, split / drift / issuer / defect checks |
| `scripts/contest_rehearsal.py` | new: daily (grade, then freeze), sheet, grade, verify, nav, vendor-miss, status; `--mode contest` |
| `scripts/contest_drills.py` | new: the 13 drills |
| `scripts/contest_strategy_lab.py` | new: the book comparison, including the date-miss variants |
| `scripts/contest_desk.py` | `live_sheet` factored out of `run_live` (same behaviour); future sessions from exchange calendars |
| `backend/config.py` | appended `CONTEST_*` parameters |
| `backend/tests/test_contest_rehearsal.py` | 25 offline tests; the 5 contest test files pass 69 of 69 |
| `docs/TRIALS/TRIAL-CONTEST-MAG-1-...md` | dated amendment: nothing that is graded changes |
| `docs/CONTEST_RUNBOOK_2026-10.md` | the runbook and the rules checklist |
| scheduled tasks | `AegisContestRehearsal` (new, 14:30 HKT daily, Sep 30 - Oct 15); `AegisContestDesk` now also writes the contest ORDER SHEET, and both tasks wake the PC and catch up when missed |

**WHAT WORKS**

- The whole day runs unattended, from calendar to frozen sheet to grade, and the scheduled path was
  exercised end to end.
- The sheet is hard to mistype, and `verify` catches the mistakes a human makes.
- Four defects that would have cost money on the day were found by the drills and fixed before any
  contest data exists:
  - a buy on a holiday;
  - two share classes of one issuer;
  - gross above 100%;
  - trading on pattern-estimated dates.

**WHAT DOES NOT**

- No forward result exists yet. Tonight's own sheet missed the open by 13 minutes.
- The book's edge over a random rotation is t ≈ 1, and its October history is 0-1 in 7 above +40%.
- 82% of Nasdaq's US rows have no report time, so most live holds will be two sessions.
- WLS membership, the fill convention, the cap basis and commissions are all unconfirmed.

**HIGHEST-EV EXPERIMENT**

Read the owner-confirm items in `docs/CONTEST_RUNBOOK_2026-10.md` from TMSG Help before Oct 4. Of these,
the **fill convention** and **whether sale proceeds are available the same session** decide between
ROT5_TRAIL and MAXTAIL_BH. On the Oct 12 test tickets, record fill against quote.

- **Cost:** an hour of the owner's time, $0.
- **Stakes:** the difference between about 3-5% and about 2-3% odds of a +40% month, and a book that
  may not even be executable if proceeds settle T+1.
