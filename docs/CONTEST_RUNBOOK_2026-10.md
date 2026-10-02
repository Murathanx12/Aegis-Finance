# Contest runbook: Bloomberg Global Trading Challenge, Oct 12 - Nov 13 2026

**Licence:** `PRODUCT_EXPERIMENT`, family of one. Utility: contest rank, right tail. The book is a
**variance bet, not a demonstrated edge**. Nothing here places an order: the owner types every ticket
into TMSG by hand. Evidence, drills and odds are in
`docs/research_notes/2026-09-29/contest_dress_rehearsal_2026-09-29.md`.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | NONE in edge; the day is now rehearsed end to end |
| book | **ROT5_TRAIL**. Each day, hold the 5 WLS names reporting next with the largest past earnings moves, 20% each, bought at the open before the print and sold at the open after it |
| fallback | **MAXTAIL_BH**: the 5 highest-volatility WLS names, bought once and held |
| odds (10 bps a side) | P(> +40% relative) is 2.5-4.9% if the direction is a coin flip (Octobers 2019-25) and about 17% if the season's own drift repeats; P(< -20%) is about 25-30% |
| drills | 13 of 13 PASS; 4 defects fixed before the contest |
| rehearsal | live now: one sheet a day through Oct 9, graded daily (`contest/rehearsal/SCOREBOARD.md`) |
| owner items open | 11 rules to confirm (page 2), the WLS export, registration by Oct 4 23:59 HKT |

## PAGE 1: WHAT RUNS WHEN

Hong Kong time (HKT) is UTC+8. New York is **12 h behind until Sun Nov 1** and **13 h behind after**.

| HKT (NY before / after Nov 1) | what | who |
|---|---|---|
| **14:30** (02:30 / 01:30) | `AegisContestDesk` runs two jobs. (1) It writes the research sheet `contest/sheets/<date>.md`. (2) It grades, then writes and FREEZES the **ORDER SHEET** `contest/live/sheets/<date>/order_sheet.md`. From Oct 11 on (Oct 11's sheet carries Oct 12's Asian opens). | machine |
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
| **Oct 4 23:59 HKT** (11:59 NY) | registration closes |
| Oct 11 (Sun) 14:30 HKT | the first contest ORDER SHEET |
| Oct 12 | the contest starts. Japan is CLOSED (Sports Day); the US is open |
| **Oct 16** | initial positions are due. The 2025 wording was "09:00 ET", which is **21:00 HKT, before that day's US open**: enter the Oct 16 tickets the evening before, or confirm |
| Nov 1 | US clocks change |
| Nov 12 | the last buying sheet |
| Nov 13 16:00 NY (Nov 14 05:00 HKT) | the end |

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
| 2 | **commissions** | 0, with 10 bps as the planning case | At 25 bps a side the October null P(> +40%) falls from 2.5-4.9% to about 1.9%: **switch to MAXTAIL_BH** | **CONFIRM** |
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
| 14 | **deadline time zones** | registration Oct 4 23:59 HKT (owner confirmed); start Oct 12 (zone unknown); initial positions Oct 16 09:00 ET (2025 wording) | If Asian sessions of Oct 12 fall before the start (Oct 11 in NY), the Oct 11 sheet's Asian lines are void | **CONFIRM** |
| 15 | order types | LIMIT buys, MARKET-AT-OPEN sells | If only market orders exist, drop the limit and check the gap by eye (the ±30% rule) | CONFIRM |
| 16 | board lots | JP / CN / ID 100, TW 1000, HK per stock (look it up), US / EU / KR / IN 1: all UNVERIFIED | the sheet rounds down to the lot; wrong lots are refused by TMSG | CONFIRM |
| 17 | WLS membership | UNCONFIRMED until `MEMB` is exported to `contest/wls/` | a non-member ticket is rejected, or scores outside the universe | **EXPORT** |

If any of items 1, 2, 5 or 13 goes against the assumption, trade **MAXTAIL_BH**: buy once on the first
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
