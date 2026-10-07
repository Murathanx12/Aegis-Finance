# Contest runbook: Bloomberg Global Trading Challenge, Oct 12 - Nov 13 2026

**Licence:** `PRODUCT_EXPERIMENT`, family of one. Utility: contest rank, right tail. The book is a
**variance bet, not a demonstrated edge**. Nothing here places an order: the owner types every ticket
into TMSG by hand. Evidence, drills and odds are in
`docs/research_notes/2026-09-29/contest_dress_rehearsal_2026-09-29.md`.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | NONE in edge; the day is now rehearsed end to end |
| book (recommended, 2026-10-07) | **ROT5_TRAIL**. Each day, hold the 5 WLS names reporting next with the largest past earnings moves, 20% each, bought at the open before the print and sold at the open after it. It keeps the largest right tail at 0-10 bps a side (October null P(> +40%) 3.6-4.2% at 10 bps vs 3.3-3.8% for MAXTAIL_BH and 2.2-2.6% for MAXTAIL_EVT; lab `lab_20261006T182305Z`) |
| fallback | **MAXTAIL_BH** (v2): the 5 highest raw-sigma63 liquid operating names, series with a x2 one-day jump refused as data defects, bought ONCE on the first contest sheet (Oct 12, after the 09:00 NY start) and held to the end. Write `MAXTAIL_BH` into `contest/live/BOOK`. Cost-insensitive (turnover ~1x): at 25 bps a side it keeps October null P(> +40%) at 3.0-3.3% where ROT5_TRAIL falls to 1.5-2.2% |
| odds (10 bps a side) | P(> +40% relative) is 2.5-4.9% if the direction is a coin flip (Octobers 2019-25) and about 17% if the season's own drift repeats; P(< -20%) is about 25-30% |
| drills | 13 of 13 PASS; 4 defects fixed before the contest |
| rehearsal | live now: one sheet a day through Oct 9, graded daily (`contest/rehearsal/SCOREBOARD.md`) |
| owner items open | 11 rules to confirm (page 2); the WLS MEMB export into `contest/wls/`; the empty file `contest/REGISTERED` once registration is confirmed (it closed Oct 4 23:59 NY = Oct 5 11:59 HKT). **The live order sheet REFUSES until both exist** (receipt in `contest/live/refusals/`, line in `contest/logs/contest_live_gate.log`; check with `python -m scripts.contest_rehearsal gate`) |
| other declared books (2026-10-07) | **ROT5_DIR** v2 (ROT5_TRAIL minus names with net-Sell analyst consensus or net lowerings over 90 days) is NOT recommended: the review's event-level replay (2019+, top 5) shows it drops 28% of slots and the dropped names had the FATTER right tail (P(> +20%) 4.8% vs 4.0%) as well as the fatter left tail, with a mean gap of -0.45 pp/event (t -1.33): a variance cut, not a direction edge, the wrong trade for a top-10 objective. **MAXTAIL_EVT** v1 (MAXTAIL restricted to US names with a vendor-announced print Oct 13-Nov 12) is declared and rehearsed; in the lab it is indistinguishable from MAXTAIL_BH in Octobers (paired +1.0 pp, t 0.5, n 7) and has less tail. All three are frozen beside ROT5_TRAIL by the rehearsal task and graded side by side in `rehearsal/SCOREBOARD.md`. Note: `docs/research_notes/2026-10-06/contest_direction_sheet_2026-10-06.md` |
| ROT5_DIR replay receipt (DATED NOTE 2026-10-07, beside the line above; not an edit to it) | Our own receipt `contest/strategy_lab/direction_replay_DRR_2026-10-07_1.json` (declared and hashed first: `docs/research_notes/2026-10-07/DECLARATION_ROT5_DIR_REPLAY_v1.json`). It reproduces the mean and the left tail. **It does not reproduce the right-tail argument at top 5**: P(> +20%) is 3.5% for dropped names and 3.5% for kept names, where the review had 4.8% vs 4.0%. Top 5, 6,860 events: the filter drops 34.5%; dropped minus kept is -0.48 pp per event (day-clustered t -1.69). Top 20, 16,481 events: -0.34 pp (t -2.07). **63-day momentum control:** about a fifth of the top-20 gap is momentum. Controlled, the gap is -0.27 pp (t -1.61) at top 20 and -0.44 pp (t -1.51) at top 5. The filter drops 52-54% of low-momentum names against 18-19% of high-momentum ones. The declared trigger did not fire: the controlled gap is neither \|t\| >= 2 nor \|t\| < 1 at top 20. So the filter is a left-tail cut (P(< -20%) 4.4% vs 2.8% at top 5) with a mean gain that cannot be told apart from noise, and it does not give up right tail. Pool survivor-selected; no first-seen dates before 10-06. The recommendation above is the owner's to revisit; it is not changed here. Note: `docs/research_notes/2026-10-07/contest_direction_replay_2026-10-07.md` |

## PAGE 1: WHAT RUNS WHEN

Hong Kong time (HKT) is UTC+8. New York is **12 h behind until Sun Nov 1** and **13 h behind after**. The contest's own times are New York times; every HKT below is derived from them.

| HKT (NY before / after Nov 1) | what | who |
|---|---|---|
| **14:30** (02:30 / 01:30) | `AegisContestDesk` runs two jobs. (1) It writes the research sheet `contest/sheets/<date>.md`. (2) It grades, then writes and FREEZES the **ORDER SHEET** `contest/live/sheets/<date>/order_sheet.md`. From Oct 11 on. Oct 11's sheet carries only Oct 12's Asian opens and Europe's Oct 12 open (03:00-04:00 NY), all before the 09:00 NY start, so the code refuses them: the first tickets are on the Oct 12 sheet. A buy whose print reacts after 17:00 NY Nov 13 is refused too. Every sheet prints its worst case in dollars, a DRIFT line per held name (the trim if the 20% cap applies at all times: the public rules do not say), and refuses a ticket above 20% of notional. The live sheet trades the book named in `contest/live/BOOK` (absent = ROT5_TRAIL); write it with `Set-Content -Path backend\data\optimus\contest\live\BOOK -Value MAXTAIL_BH`. A file that cannot be read never loses the day: the sheet trades ROT5_TRAIL and `contest/live/REFUSED_<date>.txt` says why. Previews (`dry`) are titled DRY PREVIEW - NOT AN ORDER SHEET and are written to `contest/dry_preview/`, never `contest/live/`. Every sheet prints its worst case in dollars and refuses a ticket above 20% of notional. | machine |
| 14:45 - 15:00 | Open the ORDER SHEET, not the research sheet. For every BUY, run three checks. If any check fails, SKIP the name and take the next reserve printed on the sheet. | **owner** |
| | - `EVTS <GO>`: the date and time match. | |
| | - `MEMB <GO>` of WLS Index: the name is a member. | |
| | - `CACS <GO>`: no split. | |
| 15:00 / 16:00 after Oct 25 | Europe opens: enter any EU tickets. | owner |
| **before 21:30 / 22:30** | Type the SELL tickets first, then the BUYs, exactly as printed. | **owner** |
| | - Ticker with its exchange code, side, SHARES. | |
| | - LIMIT for a buy; MARKET AT OPEN for a sell. | |
| | Then paste the blotter into `python -m scripts.contest_rehearsal verify --mode contest --date <d> --entered blotter.txt`. It must print ok and the SHEET CODE from the sheet. | |
| 21:30 / 22:30 (09:30 NY) | The US opens and the tickets fill. | Terminal |
| 04:00 / 05:00 (16:00 NY) | The US closes. | - |
| 08:00 - 09:30 | Japan and Korea open at 08:00, Taiwan at 09:00, Hong Kong and China at 09:30, India at 11:45: Asian tickets on the sheet. | owner |
| Friday evening | Read the leaderboard. If inside about the top 15 in week 4, switch to MAXTAIL (lock in); otherwise keep rotating. | owner |
| any day | Write the Terminal NAV so the next sheet sizes on it: `python -m scripts.contest_rehearsal nav --mode contest --set <USD>` | owner |

**Key dates.**

| date | what |
|---|---|
| **Oct 4 23:59 NY = Oct 5 11:59 HKT** | registration closed (HKU's page reads "Closed" on Oct 6). The owner confirms the team registered, then creates `contest/REGISTERED` |
| Oct 11 (Sun) 14:30 HKT | the first contest ORDER SHEET |
| **Oct 12 09:00 NY = Oct 12 21:00 HKT** | the contest starts. Asian and European sessions of Oct 12 open before this (Asia: the evening of Oct 11 in New York; Europe: 03:00-04:00 NY) and are refused by the code. Japan is CLOSED (Sports Day); the US opens at 21:30 HKT |
| **Oct 16 23:59 NY = Oct 17 11:59 HKT** | initial positions are due (public rules, 2026). The US session of Oct 16 (21:30 HKT that day) is the last US open before the deadline |
| Nov 1 | US clocks change |
| Nov 12 | the last buying sheet |
| **Nov 13 17:00 NY = Nov 14 06:00 HKT** | the end (NY is UTC-5 after Nov 1, so 13 h behind HKT) |

**To stop everything:** create the empty file `backend/data/optimus/contest/STOP`.

### When something goes wrong

| failure | what the sheet / code does | what the owner does |
|---|---|---|
| date moved or wrong | Pattern-only dates are refused (right 28% of the time); vendor dates are labelled NOT CONFIRMED | `EVTS` before each BUY. If the date moved out of the hold, skip and take the next reserve. A move after entry: sell at the printed exit anyway |
| report time unknown | held two sessions (the session before the date to the session after it) | if `EVTS` shows the time, still follow the sheet (the hold covers both cases) |
| fewer than 5 names | buys what reports; the sheet states the cash | nothing; do not double a slot |
| name not in WLS | refused once the MEMB export is in `contest/wls/` | until then, `MEMB` check by hand; skip, next reserve |
| halted / gapping | a buy above its limit does not fill; a halted exit sells at the next open | never chase with a market order |
| price source down | the sheet carries a PRICE SOURCE STALE banner; grades wait | check each price on the Terminal; beyond ±30% of the sheet: split / gap rule |
| PC asleep or late | tasks wake the PC and catch up; lines whose session already opened print VOID_LATE; missed sells print OVERDUE | keep the PC plugged in and signed in. VOID lines are never entered |
| holiday / half day | sessions come from exchange calendars (Oct 12 and Nov 3 Japan; Oct 19 Hong Kong; Oct 20 and Nov 10 India; Oct 26 Taiwan) | none |
| split between sheet and fill | the SPLIT_SUSPECT rule | on `CACS`, confirm; shares = sheet shares ÷ ratio |
| two share classes | one line per issuer | none |
| stitched / defect-flagged ticker | refused | none |
| 20% cap by drift | sizes at min(20% NAV, $200k) AT THE LIMIT | if the rule is "at all times", sell the trim printed by the drift check at the next open |
| manual-entry mistake | `verify` names it | fix the ticket before the open; re-run `verify` |

## PAGE 2: RULES CHECKLIST (the owner confirms each from TMSG Help / the T&C)

**Assumptions and what changes if they are wrong.** Items marked **CONFIRM** change the book.

| # | rule | desk's current assumption | if the assumption is wrong | confirm? |
|---|---|---|---|---|
| 1 | **fill price convention** | a ticket entered before the open fills at that session's open | Close fills: the tail is similar, but the realised history is about 10 pp lower. "Next open after a close decision" (the gap is lost): the rotation fails, so **switch to MAXTAIL_BH** | **CONFIRM** |
| 2 | **commissions** | 0, with 10 bps as the planning case | At 25 bps a side the October null P(> +40%) falls from 2.5-4.9% to about 1.9%: **switch to MAXTAIL_BH** (rerun 2026-10-07, `lab_20261006T182305Z`: ROT5_TRAIL 1.5-2.2% at 25 bps vs MAXTAIL_BH 3.0-3.3%) | **CONFIRM** |
| 3 | **20% cap: basis** | min(20% of current NAV, $200k), because the T&C say "20% of the notional amount" | Fixed $200k: after gains the book cannot stay fully invested, and the upside compounds more slowly | **CONFIRM** |
| 4 | **20% cap: at entry or at all times** | at entry; holds last 1-2 sessions | At all times: sell the printed trim at the next open after a big move | **CONFIRM** |
| 5 | **sale proceeds usable the same session** | yes: SELLs and BUYs at the same open | T+1 or T+2 settlement: the rotation needs about 2x cash. Run 3 slots or MAXTAIL | **CONFIRM** |
| 6 | **fully invested requirement** | invested in full by the Oct 16 deadline only; cash is allowed after | If full investment is continuous, fill empty slots with the highest-vol names (measured cost -1.0 pp a season) | **CONFIRM** |
| 7 | shorting | not allowed (T&C 2021-25, verbatim) | none: the book is long only | known |
| 8 | leverage | not allowed (T&C 2021-25) | none: gross ≤ 100% at every open, enforced | known |
| 9 | cash interest | none | negligible for ranking | optional |
| 10 | **currency / non-US pricing** | USD P&L at the day's FX; Asian tickets fill at their own session open | If TMSG fills a non-US ticket at a US-hours quote, drop the non-US legs (they add nothing to the tail) | **CONFIRM** |
| 11 | corporate actions and dividends | splits are adjusted by TMSG; the benchmark is WLS *price* return | a split handled by hand: use the split rule; dividends are small over 5 weeks | CONFIRM |
| 12 | **relative P&L definition** | book return minus WLS return on the full notional | If relative P&L is measured on invested capital only, cash days are neutral and nothing changes. If it is time-weighted, the same | **CONFIRM** (TMSG Help) |
| 13 | minimum positions / trades; ticker re-entry; orders per day | none, and re-entry allowed | a limit on trades or re-entry breaks a daily rotation: **switch to MAXTAIL_BH** | **CONFIRM** |
| 14 | **deadline time zones** | SETTLED from the public rules (2026-10-06): all times New York. Registration Oct 4 23:59 NY = Oct 5 11:59 HKT; start Oct 12 09:00 NY = Oct 12 21:00 HKT; initial positions Oct 16 23:59 NY = Oct 17 11:59 HKT; end Nov 13 17:00 NY = Nov 14 06:00 HKT. Every HKT here is computed from New York with the DST rule (`contest_direction.contest_times`, pinned by a test) | Asian and European sessions of Oct 12 open before the start: the code refuses them | known |
| 15 | order types | LIMIT buys, MARKET-AT-OPEN sells | If only market orders exist, drop the limit and check the gap by eye (the ±30% rule) | CONFIRM |
| 16 | board lots | JP / CN / ID 100, TW 1000, HK per stock (look it up), US / EU / KR / IN 1: all UNVERIFIED | the sheet rounds down to the lot; wrong lots are refused by TMSG | CONFIRM |
| 17 | WLS membership | UNCONFIRMED until `MEMB` is exported to `contest/wls/`. The live gate accepts only a CSV/Excel whose name or header rows say WLS and that holds at least 1,000 member rows (WLS has about 10,000); every sheet prints the export's file name and row count | a non-member ticket is rejected, or scores outside the universe | **EXPORT** |

If any of items 1, 2, 5 or 13 goes against the assumption, write `MAXTAIL_BH` into `contest/live/BOOK` and trade **MAXTAIL_BH** (the contest-mode path exists from 2026-10-07: same gate, freeze, worst case and `verify`): buy once on the first
sheet, hold, and re-read the leaderboard weekly.

## Commands (run from the repo root; `--mode contest` from Oct 11, `--mode rehearsal` before)

| command | what it does |
|---|---|
| `python -m scripts.contest_rehearsal status --mode contest` | frozen sheets and open positions |
| `python -m scripts.contest_rehearsal verify --mode contest --date <d> --entered <file>` | checks the typed blotter against the frozen sheet |
| `python -m scripts.contest_rehearsal nav --mode contest --set <USD>` | the next sheet sizes on this NAV |
| `python -m scripts.contest_rehearsal grade --mode contest` | the local shadow grade; the Terminal is the truth |
| `python -m scripts.contest_drills` | re-runs the 13 drills |
| `backend/data/optimus/contest/STOP` (empty file) | stops both tasks |
| `Unregister-ScheduledTask -TaskName AegisContestRehearsal -Confirm:$false` | removes the rehearsal task |

**WHAT WORKS**

- One code path for the rehearsal and the contest.
- Sheets are frozen before the open, written once, and hashed.
- Tickets are hard to mistype, and `verify` catches the rest.
- Holidays, share classes, gross exposure and pattern dates are handled before the day.

**WHAT DOES NOT**

- No edge: the tail is bought, not predicted.
- Six rules that decide the book are unconfirmed (1, 2, 3, 5, 12, 13).
- WLS membership is unconfirmed.
- The tasks need the PC signed in and on AC power.

**HIGHEST-EV EXPERIMENT**

Before Oct 4, read TMSG Help for items 1, 2, 5 and 13. On Oct 12, place one small US ticket and one
small Asian ticket, and record fill against quote. These decide between ROT5_TRAIL and MAXTAIL_BH at a
cost of about one hour.
