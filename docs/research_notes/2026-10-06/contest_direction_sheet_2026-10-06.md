# Contest: a second rehearsal book, ROT5_DIR, graded beside ROT5_TRAIL (chunk C9)

Written 2026-10-07 (HKT). Licence `PRODUCT_EXPERIMENT`. No LLM, $0. Nothing here places an order.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE.** This adds a measurement. It does not add an edge |
| books frozen by the 14:30 HKT rehearsal task from 2026-10-07 | **ROT5_TRAIL** (the order sheet, unchanged), **ROT5_DIR** (shadow), **MAXTAIL_BH** (shadow; the runbook's fallback) |
| tonight's sheets (day 2026-10-07, DRY preview) | ROT5_TRAIL `2D2355E3` and ROT5_DIR `54E1AEAC` hold the **same five Japanese names**. All five are UNRATED in the direction source, so nothing is dropped. MAXTAIL_BH `C69122F4`: CAPR, AXTI, AEHR, REPL, AAOI |
| worst case, largest admissible book | 5 x $200,000 = **$1,000,000**, which is 0.98 of equity for ROT5_TRAIL (NAV $1,023,073) and 1.00 for the shadow books. Loss **$50,000 at a 5% stop** and **$100,000 at a 10% stop**. At a 2-sigma63 move: **$103,382** for the two rotations and **$332,217** for MAXTAIL_BH |
| can the rehearsal settle the Oct 11 choice? | **No.** ROT5_DIR has three buying sheets (Oct 7, 8 and 9), and in this window almost every reporter is a non-US listing with no analyst rows. The two books will hold the same names most nights. See section 6 for the test that would settle it |
| live gate | in place. The live order sheet REFUSES without a WLS MEMB export in `contest/wls/` **and** the owner's hand-made `contest/REGISTERED` file. Today it refuses for both reasons |

## 1. Why the second book exists

The owner's point (2026-10-06): ROT5_TRAIL ranks reporters only by the size of their past earnings
moves. On the stock list, the names at the top (NVEC, MAN, RHI, IRDM) had Sell/Hold analyst
consensus. A magnitude-only book therefore takes the opposite side of the consensus on direction
without ever having tested that choice against the alternative. The contest pays for relative
return, so variance is worth buying, but the direction should be a measured choice.

Two facts frame this before any grade exists:

- **The rehearsal's actual rank key is `trail_abs`**: the mean |close-to-close earnings reaction|
  over the last 8 reports (`contest_desk.rank_candidates`). The "sigma63 move 21s" column comes
  from the stock-list PDF (`stock_lists_v3_build.py`), not from the order sheet. Both are
  magnitude-only, so the criticism applies to both.
- **On the point-in-time analyst source, none of the four named names is net Sell.** The source is
  the dated upgrades and downgrades in `analyst/target_revisions.parquet`, as of 2026-10-06:
  - NVEC: no coverage.
  - MAN: 2 Buy, 5 Hold. Net raises +7 of 7 over 90 days.
  - RHI: 2 Buy, 3 Hold, 2 Sell, so consensus is exactly 0. Net raises +3.
  - IRDM: 2 Buy, 2 Hold, 1 Sell.

  The stock list's "Sell/Hold" came from a MarketWatch snapshot, which is not point-in-time. The
  declared rule drops only net Sell. Dropping all four would need a threshold set to fit these four
  names, and that is exactly the choice that may not be made after looking.

## 2. The declared rule (frozen before the first sheet)

The contract is appended to `backend/data/optimus/contest/rehearsal/freeze_log.jsonl` as a
`STRATEGY_CONTRACT` row (declared 2026-10-06T16:22:07 UTC, before the 2026-10-07 06:30 UTC run):

| book | contract sha256 |
|---|---|
| ROT5_DIR v1 | `7d7cb923ec31b5d04e0b04d1e2c3e09492b52b843e19bac276da6e2ba85a2c8b` |
| MAXTAIL_BH v1 | `1307374645d6d86eb7247d7ca30a9528b0ef85fdf5840299fed4ac0c5822a7f1` |

If the rule is edited under the same name, every later shadow sheet REFUSES with
`ContractChanged`. A new rule needs a new name.

**ROT5_DIR** (the code is `scripts/contest_direction.py`, `RULES["ROT5_DIR"]`):

- **Universe, sizing, entry and exit:** identical to ROT5_TRAIL. It starts from the desk's ranked
  reporters after `filter_ranked`. It holds 5 slots at min(20% NAV, $200k), with a limit 5% above
  the last close. It buys at the open before the print and sells at the open after it. There is no
  stop.
- **Point in time:** a row is used only if `event_date` is before the sheet day (00:00 UTC) **and**
  `event_date` is no later than `pulled_at`. One vendor row was dated after its own pull (AMR); rows
  like it are excluded and counted.
- **Consensus:** each firm's latest grade in the last 365 days. Buy family = +1, Hold family = 0,
  Sell family = -1. Consensus is the mean over firms.
- **Revision flow over 90 days:** +1 for an upgrade or a target raise, -1 for a downgrade or a
  target cut. `net_raises` is the sum. `rev_mom` is `net_raises` divided by the number of signed
  rows.
- **Drop rules (long only):** drop a name if consensus < 0 (net Sell) or `net_raises` < 0 (net
  lowering).
- **UNRATED names are admitted.** A name with no evidence either way stays in. This covers every
  non-US listing, because the pull is US-only. The two books therefore differ by exactly the names
  with negative analyst evidence, plus the order inside a bucket.
- **Order:** first by `floor(trail_abs x 100)`, descending, so magnitude is kept at 1-point
  resolution. Within a bucket, by `rev_mom`, then consensus, then `trail_abs`.
- **Source age:** the sheet REFUSES when the source is more than 14 days old.

**MAXTAIL_BH:** the runbook's fallback. It takes the 5 highest-volatility liquid operating names
(at least 3 past reactions, not defect-flagged or stitched, one line per issuer), buys them once on
its first sheet and holds them until the first open after the last buying sheet.

- **Changed before the freeze:** its sigma63 leaves out the window's single largest move. The first
  DRY preview ranked three one-jump series at the top on raw sigma63: CTVA x6.2 on 2026-10-01, SION
  x11 on 2026-08-10 and MRNA x2.8 on 2026-08-19. These are splits, spin-offs or bad prints. The
  change was made for data validity before the contract was frozen. No outcome was read.
- **Not a test of the contest version:** a buy-and-hold over three rehearsal sessions says almost
  nothing about the 5-week version.

## 3. Tonight's sheets side by side (sheet day 2026-10-07; DRY)

These previews come from `python -m scripts.contest_rehearsal dry --date 2026-10-07 --no-refresh`,
written to `backend/data/optimus/contest/rehearsal/dry/2026-10-07/<book>/`. They use the calendar
on disk (`calendar_2026-10-06`). Nothing is frozen and no log is touched. **The real freeze is the
14:30 HKT task run.** That run refreshes the calendar and the bars, so its names can differ.

| | ROT5_TRAIL | ROT5_DIR | MAXTAIL_BH |
|---|---|---|---|
| sheet code (preview) | 2D2355E3 | 54E1AEAC | C69122F4 |
| SELL | 3391 JT 14,100 (held from Oct 6) | none (its first sheet) | none |
| BUY 1 | 6323 JT 6,600 (trail 4.2%) | 6323 JT 6,600, UNRATED | CAPR US 24,482 (sigma 10.4%/day ex-max) |
| BUY 2 | 9983 JT 400 (3.4%) | 9983 JT 400, UNRATED | AXTI US 2,198 (9.1%) |
| BUY 3 | 2809 JT 6,900 (2.8%) | 2809 JT 6,900, UNRATED | AEHR US 1,824 (7.8%) |
| BUY 4 | 7649 JT 24,100 (2.3%) | 7649 JT 24,100, UNRATED | REPL US 14,482 (7.5%) |
| BUY 5 | 3382 JT 15,100 (2.1%) | 3382 JT 15,100, UNRATED | AAOI US 1,566 (7.3%) |
| dropped by direction | n/a | 0 of 5 | n/a |
| BUY notional at limits | $992,709 | $992,709 | $999,833 |

**Tonight the two rotations hold the same names.** The difference will only appear on nights when
a US reporter with negative analyst evidence ranks in the top five.

**Illustration, not evidence.** On ROT5_TRAIL's past sheets, the rule run at each sheet's own date
would have dropped two names: AYI on 09-30 (net raises -2) and NKE on 10-01 (net -14 of 14). It
would have kept ACN, MU, PRGS, AEHR, LW and RPM. NKE then lost 8.2%. That is one name, read after
the outcome, and the reserve that would have replaced it is unknown.

## 4. Worst case in dollars (protocol item 4; printed on every sheet)

| | ROT5_TRAIL | ROT5_DIR | MAXTAIL_BH |
|---|---|---|---|
| NAV used for sizing | $1,023,073 | $1,000,000 (own grades: none yet) | $1,000,000 |
| largest admissible book: 5 x cap | $1,000,000 (0.98 of equity) | $1,000,000 (1.00) | $1,000,000 (1.00) |
| at a 5% / 10% stop | -$50,000 / -$100,000 | -$50,000 / -$100,000 | -$50,000 / -$100,000 |
| at a 2-sigma63 move, largest book | -$103,382 | -$103,382 | -$332,217 |
| this sheet's book: gross / equity | $992,709 / 0.97 | $992,709 / 0.99 | $999,833 / 1.00 |
| this book at 2-sigma63 per name | -$48,894 | -$48,894 | -$215,760 |
| this book at 2x trailing earnings move | -$58,600 | -$58,600 | n/a (no event) |

How to read the table:

- **None of these books has a stop**, and an overnight gap fills through any stop. The stop rows
  are reference arithmetic, not a bound.
- **The 2-sigma63 rows use the raw sigma63**, jumps included, so they are conservative. For
  MAXTAIL_BH that is CAPR's 16.6% per day.
- **The sheet refuses** (`CapRefused`, nothing frozen) if any BUY ticket is above min(20% of
  notional, 20% of NAV) at its limit, or if the gross book after the tickets would exceed NAV.

## 5. The live-desk gate (owner decision D1 + registration)

`contest_rehearsal sheet` in CONTEST mode is what `AegisContestDesk` runs. It now calls
`contest_direction.live_gate()` first and refuses unless both of these hold:

1. `backend/data/optimus/contest/wls/` holds a WLS membership export (`MEMB`, CSV or Excel)
   that `contest_calendar.load_wls_export` can read.
2. `backend/data/optimus/contest/REGISTERED` exists. The owner creates it by hand after confirming
   the team's registration. Registration closed **Oct 4 23:59 NY = Oct 5 11:59 HKT**.

A refusal writes three things. All of them are local files, and none is an alert:

- the receipt `contest/live/refusals/live_gate_<day>_<stamp>.json`, with the reasons;
- a line in `contest/logs/contest_live_gate.log`;
- `REFUSED_LIVE_GATE: ...` in `contest/live/runs.jsonl`.

`python -m scripts.contest_rehearsal gate` prints the state. Today it refuses for both reasons. The
rehearsal does not consult the gate.

Two related changes in CONTEST mode:

- Buy sessions that open before **Oct 12 09:00 NY (21:00 HKT)** are refused. These are Asia's
  Oct 12 sessions, so the first contest tickets are on the Oct 12 sheet.
- `contest/live/BOOK` selects the live book: `ROT5_TRAIL` (the default) or `ROT5_DIR`. Any other
  name refuses.

**Times, all derived from New York with the DST rule** (`contest_direction.contest_times`). A test
pins these times and checks that the runbook prints them.

| event | New York | Hong Kong |
|---|---|---|
| registration closed | Oct 4 23:59 | Oct 5 11:59 |
| contest starts | Oct 12 09:00 | Oct 12 21:00 |
| initial positions due | Oct 16 23:59 | Oct 17 11:59 |
| contest ends | Nov 13 17:00 (UTC-5 after Nov 1) | Nov 14 06:00 |

The sheet freezes at 14:30 HKT, which is 02:30 ET (01:30 after Nov 1). A test checks this against
the zone rules, and checks that the freeze comes before that day's 09:30 ET open. The runbook's
old lines ("registration Oct 4 23:59 HKT", "end Nov 13 16:00 NY", "positions 09:00 ET") are
replaced.

## 6. What this cannot do, and what would

- **The rehearsal cannot separate the two books before Oct 11.** There are three buying sheets in a
  mostly Asian window with no analyst rows. Starting Oct 12, the live US earnings season
  (mid-October) is where the books diverge, but only one book can be traded. The side-by-side scoreboard
  keeps grading both through the rehearsal's wind-down only.
- **The prior is weak.** No direction prior has survived here before:
  - the analyst/insider/earnings bridges to CRSP (76 rules, none beats the market);
  - the revision tilt, rated FAILED_VARIANT / CANNOT_DISTINGUISH;
  - the analyst target-upside level, which is CLOSED/PERVERSE.

  So the expected difference between the books is small, and a handful of positions decides
  nothing. The scoreboard's TAIL column (the share of P&L from the top name, and the relative
  return without it) exists so that one ACN-like name is not read as a verdict.
- **The direction source goes stale on Oct 13.** The analyst pull last ran on 2026-09-29; its daily
  receipts stop that day. ROT5_DIR refuses once the source is more than 14 days old, which is
  ~Oct 13 14:45 UTC. Before trading ROT5_DIR live, or rehearsing it past Oct 13, re-run
  `scripts/pull_analyst_targets` (~80 minutes). **Nothing schedules that pull.**
- **The test that would settle the question:** a historical replay of ROT5_TRAIL against ROT5_DIR
  in `contest_strategy_lab`, with the same seasons and the same costs. The dated revision rows go
  back years, and the filter is point-in-time by construction. That replay answers the Oct 11
  choice; three rehearsal nights cannot. It is not built.

## Files

- `scripts/contest_direction.py` (new): the rules and contracts, the direction filter, MAXTAIL
  candidates, the worst case, the cap refusal, the live gate and the NY to HKT times.
- `scripts/contest_rehearsal.py`:
  - every book is built at one `now` and frozen;
  - the shadow books live under `rehearsal/strategies/<book>/`;
  - the grader writes the side-by-side `SCOREBOARD.md`, marks open positions to the last close,
    and adds the TAIL metrics and a same-sheets comparison line;
  - new commands: `contract`, `dry`, `gate`.
- `docs/CONTEST_RUNBOOK_2026-10.md`: the deadline lines, the gate and the shadow books.
- `backend/tests/test_contest_direction.py`: 17 tests.
