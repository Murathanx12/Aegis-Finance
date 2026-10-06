# Contest: ROT5_DIR, MAXTAIL_BH and MAXTAIL_EVT graded beside ROT5_TRAIL (chunk C9, v2 after review)

Written 2026-10-07 (HKT). Licence `PRODUCT_EXPERIMENT`. No LLM, $0. Nothing here places an order.

This is v2. It was revised after the adversarial review `docs/reviews/REVIEW_2026-10-06_C9_CONTEST_DIRECTION.md`
(58/100) and before the 14:30 HKT freeze. The v1 claims that the review showed to be wrong are
corrected in place, and marked.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE.** This adds measurement and closes live-path failure modes. It adds no edge |
| the measurement that matters | **The review's event-level replay** (US, SEC8K pool, 2019 onward, held open-before to open-after the print, which is exactly ROT5's hold). In ROT5's top 5, the direction filter drops **28.1%** of slots. The dropped names returned **-0.45 pp per event** against the kept ones (month-clustered t **-1.33**, 93 months), and they had **more tail on both sides**: P(> +20%) 4.8% vs 4.0%, P(< -20%) 4.4% vs 2.9%. This is **a trade of right tail for left-tail protection, not a direction edge**. The figures are in the review only; they have not been re-derived into a receipt here |
| books frozen by the 14:30 HKT rehearsal task | ROT5_TRAIL (the order sheet) and three shadow books: **ROT5_DIR v2**, **MAXTAIL_BH v2** and **MAXTAIL_EVT v1** (the reviewer's proposal, declared and hashed at 2026-10-06T18:26:11 UTC, before the freeze) |
| recommended book (runbook) | **ROT5_TRAIL**, if fills are at the open and commissions are at most about 10 bps. Otherwise **MAXTAIL_BH**. ROT5_DIR is not recommended. MAXTAIL_EVT is not preferred over MAXTAIL_BH (section 5) |
| worst case, largest admissible book | 5 x $200,000 = **$1,000,000** (0.98 of equity for ROT5_TRAIL, 1.00 for the shadow books). Loss **$50,000 at a 5% stop** and **$100,000 at a 10% stop**. At a 2-sigma63 move: **$103,382** for the two rotations, **$190,465** for MAXTAIL_BH and MAXTAIL_EVT |
| live gate | Refuses without both of these: a WLS MEMB export in `contest/wls/` that names WLS and has at least 1,000 rows, and the owner's hand-made `contest/REGISTERED`. Today it refuses for both reasons |

## 1. What the review changed (and why)

| finding | fix |
|---|---|
| **F1** The PIT guard was a tautology: the pull overwrote `pulled_at` on every re-served row, and the vendor rewrote 30 rows dated before 09-29 | `pull_analyst_targets` now keeps `first_seen_utc` with MIN semantics. ROT5_DIR uses a row only if `first_seen_utc` is no later than the freeze. Every ROT5_DIR sheet prints the source file's sha256 and row count, so a frozen decision can be rebuilt. Rows from before the column carry their last `pulled_at`, which is an **upper** bound (honest, never earlier than the truth) |
| **F3** A `dry` sheet read as a frozen ORDER SHEET and skipped the gate | DRY files are titled `DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER` in the title, the body banner, the one-line summary and every ticket note. They are written to `contest/dry_preview/` (contest) or `contest/rehearsal/dry/` and never under `contest/live/` (enforced). The MEMB check now requires WLS in the file name or header rows and at least 1,000 member rows |
| **F4** The fallback had no contest-mode path | `contest/live/BOOK` = `MAXTAIL_BH` or `MAXTAIL_EVT` builds a live sheet through the same gate, freeze, cap, worst case and `verify`. It buys once on the first contest sheet with a session at or after 09:00 NY Oct 12 (the Oct 12 sheet) and holds to the end; no SELL ticket is issued inside the contest |
| **F5** The BOOK file broke on PowerShell encodings | The reader accepts UTF-16 (from `echo >`), a UTF-8 BOM (from `Set-Content -Encoding utf8`), case and whitespace. An unreadable or unknown book, or a refused ROT5_DIR source, still produces the ROT5_TRAIL sheet with a banner, and writes `contest/live/REFUSED_<day>.txt` |
| **F6** The contract hashed only the rule's prose | The policy hash is sha256(rule sha256 \| code sha256). The code hash covers `contest_direction.py` and `contest_rehearsal.py` with line endings normalised. Both are recorded. An edit to either file under the same (name, version) refuses, and a new version records what it supersedes |
| **F7** The MAXTAIL ex-max ranking was a prior chosen after looking | v2 reverts to the **raw** sigma63 (the lab's measure). Series with a one-day move of x2 or more within 63 sessions are refused as data defects and printed (tonight: SION x11.3, CTVA x6.2, EYPT x3.0, CAPR x2.8, MRNA x2.8, ...). The same rule is now in `contest_strategy_lab`, so the lab and the frozen book are one definition |
| **F8** The cap is enforced at entry only | Every sheet prints a DRIFT line per held name: weight at the last close, and the trim **if** the cap applies at all times. The sheet states that the public rules do not settle this (OWNER-ONLY item 4) |
| **F10** Prose | Europe's Oct 12 open (03:00-04:00 NY) is refused as well as Asia's. Buys whose print reacts after 17:00 NY Nov 13 are now refused in code. **Two v1 claims were wrong**: the analyst pull did run again (2026-10-06 17:09 UTC), and the tasks `AegisAnalystPull` / `AegisAnalystPanelDaily` exist and `sim_run` calls the pull. Its next scheduled run is Oct 11 10:00, so ROT5_DIR's 14-day limit falls around Oct 20, not Oct 13, and only if the schedule keeps running |

Still owed:
- **F9:** the worst case is still a one-day, diffusive number. It has no print-gap percentile and
  no horizon line for MAXTAIL (the review estimates about -$500k horizon 2-sigma for a 23-session
  hold).
- **F2:** a receipted event-level replay with a 63-day momentum control.

## 2. Contracts (in `backend/data/optimus/contest/rehearsal/freeze_log.jsonl`, declared 2026-10-06T18:26:11 UTC)

| book | contract sha256 | rule sha256 | supersedes |
|---|---|---|---|
| ROT5_DIR v2 | `298ee42706e4a2a60548c81daa7d7146ee798e30a6e176f3a19dd84e80fc2ec4` | `f4f0fce799dc8bcd166de153a78d6455f2f8655e278423029a0c083bd33387af` | v1 `7d7cb923…85a2c8b` |
| MAXTAIL_BH v2 | `bdc7348f5ac2bdbb9dc68745430ae035254789df21109b77e987cf33f7289628` | `29c30e5cd23fd97106b9f80ab8d5e1b9cbc25f37abd10f5d29e23b4e04737e16` | v1 `13073746…22a7f1` |
| MAXTAIL_EVT v1 | `5cfe5e7293a63b3319de098d46472ffba29e0680cf4323ef1a2e7a345bd87605` | `00c9e6d21cd9ea1e598d6f58337e7353f0decc14d1b31bb813bff68a5a8061bb` | none |

The shared code sha256 is `0d671d2fd221682f22dfed7c037e529489f2aadf38654f6b341394bf53eddfb6`. No
v1 shadow sheet was ever frozen; only DRY previews existed.

**These lines and the two code files must be committed together before 14:30 HKT, and the two code
files must not change before then.** Any edit makes every shadow sheet refuse with
`ContractChanged`.

## 3. The rules in one paragraph each

**ROT5_DIR v2.**
- **Same as ROT5_TRAIL:** the universe, the sizing (5 x min(20% NAV, $200k) at a limit 5% above
  the close), the entry (the open before the print) and the exit (the open after it).
- **Drops:** names with net-Sell consensus (each firm's latest grade in the last 365 days) and names
  with net analyst lowerings over 90 days.
- **Point in time:** event date before the sheet day, and first seen no later than the freeze.
- **Unrated names are admitted.** That includes every non-US listing.
- **Order:** by a 1-percentage-point move-size bucket, then revision momentum.
- **Refusal:** the sheet refuses if the source is more than 14 days old.

**MAXTAIL_BH v2.**
- **Universe:** liquid operating companies (at least 3 past reactions), excluding defect-flagged,
  stitched or NOT_IN_WLS names, one line per issuer.
- **Rank:** raw sigma63. Series with a x2 jump are refused.
- **Trading:** buys 5 x min(20% NAV, $200k) once and holds. In the rehearsal it holds to the
  wind-down; in the contest it holds to the end.

**MAXTAIL_EVT v1.** The same, restricted to US names whose latest contest calendar
(`calendar_2026-09-29.parquet`) carries a VENDOR_ANNOUNCED or CONFIRMED_EXCHANGE print between
Oct 13 and Nov 12. There are 2,807 such names.

## 4. Tonight's sheets (sheet day 2026-10-07; DRY previews, not frozen)

These come from `dry --date 2026-10-07 --no-refresh`, written to
`backend/data/optimus/contest/rehearsal/dry/2026-10-07/<book>/`. The real freeze at 14:30 HKT
refreshes the calendar and the bars, so the names can differ.

| | ROT5_TRAIL | ROT5_DIR | MAXTAIL_BH | MAXTAIL_EVT |
|---|---|---|---|---|
| code | 2D2355E3 | 54E1AEAC | 087D635E | D9E3B113 |
| BUY | 6323 JT, 9983 JT, 2809 JT, 7649 JT, 3382 JT | the same five, all UNRATED | AXTI, AEHR, RXT, UTZ, QMCO | AXTI, RXT, UTZ, QMCO, RARE |
| SELL | 3391 JT (held from Oct 6) | none | none | none |
| refused | n/a | 0 dropped | 9 x2-jump series | 6 x2-jump series |
| BUY notional | $992,709 | $992,709 | $999,915 | $999,954 |
| direction source | n/a | `target_revisions.parquet`, sha256 `de10c593106f4ccc…`, 395,127 rows, last pull 2026-10-06 17:09 UTC | n/a | n/a |

The two rotations hold the same names tonight. Over the contest they will not: the review counts
747 of 2,429 rated US reporters on the contest calendar as dropped.

## 5. Worst case in dollars, and the choice

**Worst case:**

| | ROT5_TRAIL | ROT5_DIR | MAXTAIL_BH | MAXTAIL_EVT |
|---|---|---|---|---|
| largest admissible book | $1,000,000 (0.98) | $1,000,000 (1.00) | $1,000,000 (1.00) | $1,000,000 (1.00) |
| at a 5% / 10% stop | -$50,000 / -$100,000 | -$50,000 / -$100,000 | -$50,000 / -$100,000 | -$50,000 / -$100,000 |
| at a 2-sigma63 move, largest book | -$103,382 | -$103,382 | -$190,465 | -$190,465 |
| tonight's book at 2-sigma63 | -$48,894 | -$48,894 | -$168,057 | -$166,372 |

How to read it:
- **No book has a stop**, and a gap fills through one.
- **These are one-day numbers.** A 23-session MAXTAIL hold is about √23 wider; F9 is still owed.

**The lab:** `contest_strategy_lab` was rerun with the x2 rule and a MAXTAIL_EVT line: receipt
`backend/data/optimus/contest/strategy_lab/lab_20261006T182305Z.json`, 2,000 draws. The October
seasons 2019-25, n = 7 per pool:

| book | cost | SEC8K: null P(> +40%) | SEC8K: realised median | IBES_ALL: null P(> +40%) | IBES_ALL: realised median |
|---|---|---|---|---|---|
| ROT5_TRAIL | 10 bps | 3.6% | -2.3% | 4.2% | +12.0% |
| ROT5_TRAIL | 25 bps | 1.5% | -8.2% | 2.2% | +4.9% |
| MAXTAIL_BH | 10 bps | 3.8% | -10.8% | 3.3% | -5.9% |
| MAXTAIL_BH | 25 bps | 3.0% | -11.0% | 3.3% | -6.1% |
| MAXTAIL_EVT | 10 bps | 2.6% | -4.8% | 2.2% | -9.0% |

**Paired differences (Octobers, 10 bps):**
- MAXTAIL_EVT minus MAXTAIL_BH: +1.0 pp (t 0.5) on SEC8K and +1.4 pp (t 0.36) on IBES_ALL.
  The two cannot be distinguished.
- In all seasons from 2024 on (SEC8K), MAXTAIL_EVT's realised median is +15.0%, against +5.5% for
  MAXTAIL_BH and +3.4% for ROT5_TRAIL. That is 11 seasons in one regime.

**The choice (runbook):**
- **ROT5_TRAIL**, if fills are at the open and commissions are at most about 10 bps a side. It has
  the largest null right tail at those costs.
- **MAXTAIL_BH**, if commissions are 25 bps or more, or if items 1, 5 or 13 go wrong. It is
  insensitive to cost, and its right tail is then larger than the rotation's.
- **ROT5_DIR: not recommended.** The replay says it gives up right tail, which a top-10-of-~2,700
  objective needs, to protect the left.
- **MAXTAIL_EVT: declared and rehearsed, but not preferred.** It is not separable from MAXTAIL_BH
  in Octobers, and its null tail is smaller. Its 2024-26 run is one regime.

## 6. What this cannot do

- **The rehearsal cannot separate the books before Oct 11.** There are three buying sheets, in a
  mostly Asian, unrated window.
- **The replay numbers are the reviewer's** (survivor-selected pool, live-ticker ratings, no
  first-seen data for history, raw returns). Nothing separates "net lowering" from 63-day price
  momentum yet.
- **The worst case is still one-day and diffusive** (F9).

## Files

- `scripts/contest_direction.py`: v2 rules, policy hash, first-seen PIT, source fingerprint, WLS
  check, BOOK reader, raw-sigma MAXTAIL with x2 refusal, the EVT filter.
- `scripts/contest_rehearsal.py`:
  - contest-mode MAXTAIL path;
  - BOOK and ROT5_DIR fallbacks with `REFUSED_<day>.txt`;
  - the contest start and end filters;
  - DRY banners and location;
  - DRIFT lines;
  - four books in the rehearsal.
- `scripts/pull_analyst_targets.py`: `first_seen_utc`, min semantics.
- `scripts/contest_strategy_lab.py`: the x2 rule and the MAXTAIL_EVT line.
- `docs/CONTEST_RUNBOOK_2026-10.md`: the recommendation, BOOK commands, the MEMB rule, prose fixes.
- `backend/tests/test_contest_direction.py`: 29 tests.
