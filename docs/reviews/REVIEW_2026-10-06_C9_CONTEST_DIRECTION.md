# REVIEW C9: contest direction sheet (ROT5_DIR, MAXTAIL_BH, worst case, cap, live gate, NY/HKT)

Reviewer: Opus 5.5, adversarial, written as a contest trader. Read-only, apart from this file and
one throwaway replay script in the scratchpad. Reviewed: WIP `f4dbd0c0` plus the working tree on
`wip/2026-10-06-v1-beta`, read on 2026-10-07 HKT before the 14:30 HKT rehearsal freeze.
Licence of the reviewed work: `PRODUCT_EXPERIMENT`.

## VERDICT: MERGE WITH FIXES

The rehearsal half is honest and can merge. The worst case prints, the cap refuses, the
contracts are declared, the times are right, and 86 tests pass. **The live half must not run on
Oct 11 as it is.** Four problems:

- A `dry` sheet in contest mode skips the gate, and it still prints as "ORDER SHEET ... (frozen ...)".
- The runbook's fallback book (MAXTAIL_BH) has no contest-mode path.
- The two natural PowerShell ways to write `contest/live/BOOK` both kill that day's sheet.
- The "frozen" contracts exist only as uncommitted lines, and their hash does not cover the code that runs.

The note says the question that matters (does the direction filter help?) needs a replay that
"is not built". It took six minutes with code already in the repo. The answer is in F2. It says
the filter is a **mean-for-variance trade**, not a free lunch.

## Tests (as asked)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_contest_direction.py backend/tests/test_contest*.py -q
........................................................................ [ 83%]
..............                                                           [100%]
86 passed in 5.71s
```

These tests do **not** cover:
- the contest-start filter in `sheet()` (only the timestamp is pinned);
- `live_book()` file parsing;
- `dry` in contest mode;
- `sigma_ex_max` / `maxtail_ranked`.

## Findings

### F1 [HIGH]: the PIT guard is vacuous, because the pull overwrites `pulled_at`

`pull_analyst_targets.py:305` dedupes on `(ticker, event_date, firm, to_grade)` with
`keep="last"`. Every re-served row therefore takes the **newest** pull time. On disk now:

- 394,848 of 395,127 rows carry `pulled_at` 2026-10-06.
- 2,983 of 2,994 tickers have exactly one `pulled_at`.

So `event_date <= pulled_at` can never fail for a row that is re-served. The "AMR row dated after
its pull" the note cites is gone, overwritten. `pit_safe` is True on 100% of rows.

"Dated" here means the vendor's (yfinance's) `event_date`, not our first-seen date. **First-seen
is not stored anywhere.**

- **Forward sheets:** acceptable. Only rows dated before the sheet day are used, the freeze is at
  06:30 UTC, and the cutoff is 00:00 UTC.
- **The proposed replay:** PIT rests entirely on the vendor's honesty.

Evidence that the vendor rewrites history:
- The 09-29 receipt says 393,839 rows; the table now holds 395,127, which is +1,288.
- Only 1,258 of those are dated after the 09-29 pull. The other **30 rows are dated before
  09-29**, but either appeared or changed `to_grade` in the 10-06 pull.

Fix:
- Store `first_seen_utc` with `keep="first"` semantics, and filter on it rather than on `pulled_at`.
- Write the source file's sha256 and row count into every ROT5_DIR sheet. Today a frozen ROT5_DIR
  decision cannot be re-derived after the next pull rewrites the table. That breaks "frozen
  information states", which CLAUDE.md says never relaxes.

### F2 [HIGH, for the Oct 11 choice]: the replay the note calls unbuilt answers the question, and it is not "small"

I ran it read-only, with the repo's own machinery:
- events: `contest_desk.build_events` over the SEC8K pool, US, 2019 onward, 66,338 events;
- verdicts: `contest_direction.analyst_direction` at each event's own `pre_date`;
- return: `r_o2o`, open before the print to open after it, which is exactly ROT5's hold.

Results:

| subset (ranked by `trail_abs` per buy day) | drop share | mean `r_o2o` DROP / kept | month-clustered diff (t) | P(>+20%) DROP / kept | P(<-20%) DROP / kept | sd DROP / kept |
|---|---|---|---|---|---|---|
| top 5 (ROT5's book) | **28.1%** (1,905 by net lowering, 476 by net Sell) | +0.31% / +0.78% | -0.45 pp (t -1.33, 93 months) | **4.8% / 4.0%** | **4.4% / 2.9%** | 12.1% / 10.9% |
| top 20 | 27.9% | +0.23% / +0.59% | -0.43 pp (t -2.69) | n/a | n/a | n/a |
| Oct-Nov, top 20 | 25.6% | +0.19% / +0.71% | -0.49 pp (t -1.28, 14 months) | n/a | n/a | n/a |

By year, top 5:
- The DROP-minus-kept difference is positive in 2019, 2023 and 2024, and negative in the other five years.
- Leave-one-year-out (event-pooled) stays negative in all 8 cuts: -0.25 to -0.67 pp.

What this says:

1. **The note's framing is wrong for the contest window.** It says the books "will hold the same
   names most nights". That is true for the three rehearsal nights. It is false for Oct 12-Nov 13.
   On the contest calendar, 2,429 of 2,922 US reporters are rated, and **747 would be dropped
   (31% of rated)**. Over a US earnings season, ROT5_DIR is a different book on roughly every
   fourth slot.
2. **The mean effect is plausibly real but not decisive.** At the top-5 level it is about +0.45 pp
   per swapped slot-event, with t -1.33 and two of eight years the wrong way. That is CANNOT
   DISTINGUISH at the book's own breadth. At top 20 it is t -2.7.
3. **The filter sells right tail to buy left-tail protection.** The dropped names have *more*
   right tail (4.8% vs 4.0% above +20%) and much more left tail. For a top-10-of-~2,700
   objective this is not obviously good. It is a variance cut that the "variance bet, not edge"
   book never declared.
4. **What would separate it from ordinary factor beta?** Target cuts follow price falls. Nothing
   here separates "net lowering" from 63-day price momentum. Control for the trailing 63-day
   return before calling it analyst information. The repo's own revision-tilt verdict
   (FAILED_VARIANT) was cross-sectional at 21 days; this is a different, conditional question, so
   that verdict does not answer it.

Caveats:
- The SEC8K pool is survivor-selected.
- The ratings come from a live-ticker vendor, so dead names are UNRATED.
- No first-seen guard (F1).
- Returns are raw, not relative to WLS. Both groups share the day's market move, so the
  difference is roughly benchmark-free.
- Not a claim. It is an exploration receipt, and its numbers are only in this review. Put it in
  a receipt before anyone cites it.

### F3 [HIGH]: the live gate is bypassable by `dry`, and a DRY sheet reads as a frozen order sheet

- `sheet()` checks the gate only when `MODE == "CONTEST" and not dry`.
- `python -m scripts.contest_rehearsal dry --mode contest` writes a full ticket list to
  `contest/live/dry/<day>/ROT5_TRAIL/order_sheet_DRY.md`.
- That file's first line is `# ORDER SHEET 2026-10-07  (frozen 2026-10-06T16:24:23 UTC)`, as on
  tonight's rehearsal DRY. Only the filename says DRY.

An owner at 14:45 who opens the wrong file can type un-gated, un-frozen tickets.

Fix: in contest mode, either refuse `dry` while the gate is closed, or stamp
`DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER` in the title and in every ticket row, and
drop "frozen" from DRY titles.

Lesser gate gaps:
- `load_wls_export` accepts **any** CSV or Excel file with a column whose name contains
  "ticker", "security" or "member". A 10-row partial export, or another index's MEMB, opens the
  gate. Add a minimum row count; WLS has roughly 10k members, so refuse below a few thousand.
  Also print the export's file name and row count on every sheet.
- `REGISTERED` is existence-only. That is fine, because it is an owner attestation.
- The gate lives in `sheet()`, not in `freeze()`/`_emit()`, so any future contest-mode caller of
  `freeze` skips it. Low.

### F4 [HIGH]: the fallback book has no live path

The runbook says: if rule items 1, 2, 5 or 13 go the wrong way, "trade **MAXTAIL_BH**: buy once
on the first sheet". But:

- `live_book()` refuses MAXTAIL_BH: "bought once by hand from its rehearsal sheet".
- `alt_sheets` runs only in REHEARSAL mode.
- The rehearsal MAXTAIL_BH sheet is the **Oct 7** sheet. It is ranked on Oct 6 closes, sized with
  limits 5% above those closes, and its buy sessions are Oct 7-8.

Entering it on Oct 12-16 means names that move about 8-10% a day, at limits set a week earlier,
with no gate, no freeze and no `verify`. The fallback the runbook sends you to four times does
not exist in contest mode.

Fix: allow `BOOK=MAXTAIL_BH` in contest mode, with a single buying sheet on the first contest
sheet, through the same gate, freeze and `verify` path.

### F5 [MEDIUM]: the `contest/live/BOOK` file fails closed on the two most natural Windows writes

Tested with Windows PowerShell 5.1:
- `echo ROT5_DIR > BOOK` writes UTF-16LE, and `read_text(utf-8)` raises `UnicodeDecodeError`.
- `Set-Content -Encoding utf8` writes a BOM, giving `'﻿ROT5_DIR'`, which is not in the
  allowed set, so `SheetRefused`.

Only `Set-Content` without `-Encoding` works. In both failure cases `daily()` logs
`FAILED ...` to `runs.jsonl`, writes no receipt and no sheet, and **a contest day is lost**.

Fix:
- Read with `utf-8-sig` and fall back to `utf-16`.
- Strip `﻿`.
- Print the exact command in the runbook.
- Write a refusal file next to where the order sheet would be, so the owner sees it at 14:45.

The same applies to `DirectionRefused` when `BOOK=ROT5_DIR`: it is uncaught in `sheet()`, gives
`FAILED`, and produces no sheet. Decide in advance: either fall back to ROT5_TRAIL with a banner,
or refuse with a visible file. Never refuse in silence.

### F6 [MEDIUM]: the "frozen" contracts are neither committed nor a policy hash

- The two `STRATEGY_CONTRACT` rows (`7d7cb923...`, `13073746...`) are among six **uncommitted**
  lines in `freeze_log.jsonl`; `HEAD` has four rows. They are tamper-evident only against a
  reader who trusts this laptop's working tree. The repo has already lost tracked-file rows to
  git surgery once.
- `contract_sha` hashes the `RULES` dict, which is the *prose*, not the behaviour. You can edit
  `analyst_direction`, `sigma_ex_max` or the bucket arithmetic in `direction_rank`, keep the hash,
  and pass `ContractChanged`. CLAUDE.md requires a **policy hash**.

Fix: hash `RULES` plus `inspect.getsource` of every function the book calls, and commit the
contract lines before the 14:30 HKT freeze.

### F7 [MEDIUM]: MAXTAIL_BH's ex-max ranking is a prior chosen after the diagnostic, applied to the wrong layer

Formally, yes, it is a prior chosen after the diagnostic. The ranking was changed after reading
the top of a preview. Two things in its favour:
- It was disclosed in the contract (`why_ex_max`).
- No outcome was read, which makes it the less dangerous kind.

Against it:

1. **The evidence was not kept.** The raw-sigma preview was overwritten in the same `dry/`
   folder. "CTVA x6.2, SION x11, MRNA x2.8" exists only in prose.
2. **It treats the symptom.** A x6.2 or x11 one-day ratio is a split, spin-off or stitching
   defect. Such a name should be **refused by the defect rule**, because its prices are wrong for
   grading and sizing too, not quietly down-weighted. Proof that it did not work: **SION is still
   reserve #10** on tonight's MAXTAIL sheet (ex-max sigma 6.5% a day). A reserve gets bought
   whenever the owner skips a name.
3. **It changes the estimator for every name to fix three.** For a tail-seeking book, a
   genuinely jumpy biotech is the property you want. CAPR tops the list on both measures
   (16.6% raw, 10.4% ex-max), so the change re-orders rather than cleans.
4. **The odds no longer describe the book.** `contest_strategy_lab` ranks MAXTAIL_BH on **raw**
   `m.sig`, so the runbook's MAXTAIL odds now describe a different book from the frozen contract.

A defensible declared rule: refuse any series with a single-day |log return| above log(2) that
no corporate-action record explains, keep raw sigma63 for the rest, and use the same rule in the
lab.

### F8 [MEDIUM]: the 20% cap is entry-only, and nothing prints the drift trim

`assert_cap` checks BUY tickets at entry. That matches the public text ("no single position ...
greater than 20% of the notional amount", §B), which does **not** settle "at all times" (item 4,
OWNER-ONLY).

The arithmetic: a 20% slot that rallies 24% intraday becomes 0.2 × 1.24 / (1 + 0.048) = **23.7%**
of NAV.

- ROT5 holds for 1-2 sessions, so the exposure is short.
- MAXTAIL holds 5 weeks of 8-10%-a-day names, so a slot above 24% is close to certain.

The runbook's failure table says "sell the trim printed by the drift check". But
`contest_orders.drift_check` is called **only by a drill** (`contest_drills.py:339`). No sheet
prints a trim.

Fix: put `drift_check` on every contest sheet, and for MAXTAIL on every day, as an
"if the rule is at all times" line.

Related: the binding cap is min(20% of $1M, 20% of NAV). After gains, the book cannot stay fully
invested: at a $1.5M NAV, gross is 67%. This dampens the right tail exactly when you lead. It is
defensible as conservative, but say so.

### F9 [MEDIUM]: the worst case is a one-day, diffusive number on books whose risk is gaps and horizon

The note reports "2σ63, largest book: -$103k (TRAIL/DIR) vs -$332k (MAXTAIL)". Two problems:

- **ROT5's risk is the print gap.** sigma63 is diffusive. On the replay above, the top-5 events
  have a 5th percentile of **-16% to -19%**. One name at -40% on a 20% slot is -$80k.
- **MAXTAIL is held for about 23 sessions.** On a one-day basis it is understated by about
  √23 ≈ 4.8. With σ about 8% a day and ρ about 0.3 across five small-cap tech and biotech names,
  the horizon 2σ is about **-$500k**. The lab's worst realised October was -16% relative.

Fix: print the 1st-percentile gap of the pre-print event distribution (ROT5) and a horizon line
(MAXTAIL).

### F10 [LOW]: the note's staleness claims are already false

- The note says the analyst pull "last ran 09-29" and that "**Nothing schedules that pull**".
  In fact, `target_revisions.parquet` was rewritten **2026-10-06 17:09 UTC**. That is after the
  contracts were declared at 16:22 UTC and after the DRY previews.
- Scheduled tasks `AegisAnalystPull` and `AegisAnalystPanelDaily` exist, and `sim_run.py` calls
  the pull.
- So the cliff moves from about Oct 13 to about **Oct 20, in the middle of the contest**. It only
  holds if the schedule keeps running; see F5 for what happens if it stops.
- The NVEC/MAN/RHI/IRDM readings still hold on the refreshed data (UNRATED / ADMIT / ADMIT / ADMIT).

Minor:
- The note and runbook say only Asia's Oct 12 sessions are refused. **Europe's Oct 12 open
  (03:00-04:00 NY) is refused too.** The code is right; the prose is wrong.
- There is no end-side counterpart to the start filter. A Nov 12 sheet can buy Asian Nov 13
  sessions whose print reacts after 17:00 NY Nov 13: a round trip with no event inside the
  contest.

### F11 [INFO]: the times are correct

Checked by hand against the zone rules:

| event | New York | UTC | Hong Kong |
|---|---|---|---|
| registration closed | Oct 4 23:59 EDT | Oct 5 03:59 | **Oct 5 11:59** |
| contest starts | Oct 12 09:00 EDT | 13:00 | **21:00** (`contest_start_utc` = 13:00 UTC is pinned) |
| initial positions due | Oct 16 23:59 EDT | n/a | **Oct 17 11:59** |
| contest ends | Nov 13 17:00 EST (US DST ends Sun Nov 1 2026) | 22:00 | **Nov 14 06:00** |

- The 14:30 HKT freeze is 02:30 EDT before Nov 1 and 01:30 EST after it.
- Europe opens 15:00 HKT before Oct 25 (EU change) and 16:00 after.
- The US opens 21:30 / 22:30 HKT. Japan and Korea open 08:00, Taiwan 09:00, Hong Kong and China
  09:30, India 11:45.
- Oct 12 2026 is Monday, Japan's Sports Day.

### F12 [INFO]: power, the honest answer

- **The rehearsal: no.** Three buying sheets, all mostly Asian and UNRATED. Tonight's two books
  are identical. At most a few US names will differ by Oct 9.
- **The contest: no.** Only one book can be traded.
- **The season-level replay in `contest_strategy_lab`: also underpowered.** It has 7 Octobers
  and 11 windows for 2024-26. It needs:
  - a `rank: "dir"` spec that filters `evs` per decision day with `analyst_direction` at `pre_date`;
  - `paired()` on ROT5_DIR vs ROT5_TRAIL, with an MDE printed;
  - a first-seen guard (F1);
  - the IBES_ALL pool, so dead names are not all UNRATED.
- **The powered test is the event-level one in F2** (8,461 top-5 events). Run it as a receipt
  with a momentum control.

## Trader's question: is holding through the print the right variance bet?

**Yes: the event gap is the right *kind* of variance.** It is idiosyncratic, it is not shared
with WLS, and it is front-loaded into one session. **But the rotation pays for it with turnover,
and the filter now trims it.** In the lab:

- ROT5_TRAIL loses about **10 pp of median per season going from 0 to 25 bps a side** (Octobers
  +1.9% to -8.2%), because it turns over about 2× notional a day.
- ROT5_RANDOM beat ROT5_TRAIL on the October median.
- ROT5_BLEND carries the fattest right tail in both pools.

With the commission unconfirmed (item 2), the rotation's tail is a bet on commissions as much as
on prints.

**What I would freeze instead, as one concrete alternative: `MAXTAIL_EVT_v1`.** On the first
contest sheet (Oct 12, US session), buy the 5 liquid US operating names with the highest **raw**
sigma63. Restrict to names whose **vendor-announced** earnings date falls between Oct 13 and
Nov 12, and refuse defect / stitched / x2-jump series by rule (F7). Weight 5 × min(20% NAV,
$200k), hold through the print to the end, and never rotate.

- **Why:** it buys diffusive variance *and* one event gap per name. Turnover is 1× instead of
  about 50×, so commissions are nearly irrelevant: about -0.5 pp at 25 bps against roughly -10 pp
  for the rotation. It needs no daily ticket entry, which removes the largest operational risk.
  It is long-only and 1.0× gross, so ruin is impossible.
- **Worst case, largest admissible book:**
  - gross: 5 × $200,000 = $1,000,000, which is 1.00 of equity;
  - one-day 2σ63 on tonight's MAXTAIL basis: -$332k;
  - horizon 2σ (σ 8% a day × √23, ρ 0.3): about **-$500k**;
  - a print-day 1st-percentile gap of about -40% on one slot: -$80k.
  Stops are meaningless through gaps, so none are declared.
- **Gate before freezing:** one line in `contest_strategy_lab`: `rank="maxtail"` restricted to
  reporters, `exit="hold"`. Run it on the same seasons as ROT5_TRAIL, and read the worst cell and
  P(>+40%), not the median.

## Three things I would have done instead

1. **Run the event-level replay first, then decide whether a second book is needed.** It took
   about six minutes. It shows a 28% drop rate, a weak mean effect and a variance cost. That would
   have turned ROT5_DIR from "a measurement the rehearsal cannot make" into a decision with a
   number before Oct 11.
2. **Fix the data, not the estimator.** Defect-refuse x2+ one-day series, keep raw sigma, and make
   the lab and the contract use one definition. Keep the raw-preview receipt that motivated the
   change.
3. **Spend the remaining live-path effort on the contest-day failure modes.** In order:
   - a contest-mode MAXTAIL path;
   - DRY sheets that cannot be mistaken for orders;
   - a BOM- and UTF-16-tolerant BOOK file;
   - a visible refusal file;
   - the drift trim on the sheet;
   - a committed policy-hash contract.

   Each of these can lose a contest day. The direction filter cannot win one by itself.

## Score: 58 / 100

- **For:** worst case and cap on every sheet; contracts declared before the first shadow sheet;
  honest "cannot settle this" scoreboard; correct DST arithmetic; the MarketWatch "Sell" reading
  corrected against dated data.
- **Against:** a vacuous PIT check (F1); the decisive replay left "unbuilt" while being cheap (F2);
  a live gate with a dry-sheet hole (F3); a fallback with no live path (F4); a fragile BOOK file
  (F5); contracts that are neither committed nor behavioural (F6); a post-hoc estimator change that
  leaves the defect it targeted on the reserve list (F7).

RESULT IMPROVEMENT: NONE (a review).
