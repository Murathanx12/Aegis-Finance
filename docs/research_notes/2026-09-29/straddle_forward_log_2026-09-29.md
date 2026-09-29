# The straddle forward log (2026-09-29)

Licence `PRODUCT_EXPERIMENT`, $0. No LLM, no broker, no orders. This note covers the build.
The commitment is `docs/TRIALS/TRIAL-STRADDLE-FWD-1-size-forecast-vs-implied-move.md`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE (built, not yet graded).**

**New actionable finding: at closing quotes, the straddle costs are about twice what the lab
assumed.** The quoted cost was measured on 400 names. In the 2026-09-28 closing-quote dry run:

| measure | value |
|---|---|
| names that passed the quote filters | 164 of 400 |
| median straddle spread, names that passed | 11.5% of mid (p25 7.4%, p75 16.3%, p90 18.2%) |
| median straddle spread, every quoted name | 21.2% |
| entry half-spread, names that passed | about 5.8% of premium |

The lab's straddle P&L charged 10% of premium for a full round trip. Holding to expiry avoids
the exit spread, so the entry half-spread is the whole cost. At closing quotes that still makes
the lab's figure optimistic beyond the top ~100 names. Spreads widen fast down the liquidity
ranking:

| liquidity rank | median straddle spread |
|---|---|
| top 50 | 7.4% |
| 51-100 | 16.0% |
| 101-150 | 21.8% |
| 151-400 | 22-30% |

## What was built

| piece | file |
|---|---|
| pure pieces: ET sessions, the expiry rule, quote filters, straddle build, live features, frozen model, ranking, contract, hash-chained frozen writer, grader, book-vs-twin statistics, worst case | `backend/services/straddle_forward.py` |
| runner: scheduled pass, dry run, grade, freeze, status, schtasks print | `scripts/straddle_forward.py` |
| frozen size model fit | `scripts/straddle_model_fit.py` -> `backend/data/optimus/straddle_forward/model_ridge_pit_v1.json` |
| config (appended) | `backend/config.py` `STRADDLE_FWD_*` |
| tests (21, offline, derived dates, injected calendar) | `backend/tests/test_straddle_forward.py` |
| contract | `backend/data/optimus/straddle_forward/contract_v1.json` |
| entries / grades (append-only) | `backend/data/optimus/straddle_forward/entries.jsonl`, `grades.jsonl` |
| dry run / observations | `backend/data/optimus/straddle_forward/observations/` |
| schedule | Windows task `AegisStraddleForward`, every 30 min via `pythonw`, STOP file, log `straddle_forward.log` |

**Hashes.**
- Contract policy hash: **`a0f7e02d84444332`** (frozen 2026-09-29T03:44:12Z).
- Model sha: **`6d65591f62156cae`**.

**The frozen model.**
- It is the lab's point-in-time ridge on |r21|, fitted once on all 258,712 CRSP rows
  2013-01 to 2024-10.
- Its coefficients match the last monthly walk-forward fit to about 3 decimals. For example
  vol_21 is 0.0379 in both, and maxabs_21 is -0.0229 vs -0.0230.
- In-sample per-date IC 0.362; walk-forward out-of-sample IC 0.368.

The live features are recomputed from `prices_2025_26/bars.parquet` (adjustment=all, refreshed
nightly), using exactly the lab's windows and earnings conventions. The next-earnings flag is the
point-in-time projection: the last completed report plus 91-day steps. The scheduled future date
is discarded at fetch time, and dropped again in the feature code, which counts what it drops. On
the dry run it dropped 0.

## The first log: a DRY RUN, not an entry

`observations/dry_run_2026-09-28_20260929T034126Z.json`, labelled `DRY_RUN_NOT_AN_ENTRY`.

**Why it is a dry run.**
- It ran at 23:41 ET after the 2026-09-28 close, on the closing quotes (every underlying
  reported `POSTPOST`).
- 2026-09-29 has no standard monthly expiry 21-35 days out. Oct 16 is 17 days away and Nov 20
  is 52. It would have been an observation day in any case.

**Headline numbers.**

| measure | value |
|---|---|
| expiry used | 2026-10-16 (18 calendar days, 14 sessions) |
| candidates | 400 |
| usable | 164 |
| fetch time | 210 s |
| median ATM IV (usable) | 45.3% |
| median implied move to expiry | 7.95% |
| median scaled size forecast | 7.53% |

Refusals: WIDE_STRADDLE 212, THIN_OI_CALL 52, WIDE_CALL 47, WIDE_PUT 44, THIN_OI_PUT 42,
STALE_PUT 22, STALE_CALL 19. A name can have several.

**The books.**
- The 20 and 50 per leg books formed. The 100 per leg cell was **skipped**: it needs 210
  usable names and had 164.
- The forecast-picked and vol-picked books overlap little: at 20 per leg they share 3 long
  and 11 short names; at 50 per leg, 20 long and 24 short.
- The rank correlation between the forecast's gap and trailing vol's gap is 0.31. The
  forecast ranks with implied vol at Spearman 0.92, and trailing vol at 0.88.

**Worst case in dollars.**
- Setup: $1,000,000 equity, 2% premium per leg.
- Long leg: at most −$20,000.
- Short leg, forecast-picked, 20 names:
  - 3σ: −$3,416 on the worst name, −$62,008 if every name moves at once (−6.2% of equity).
  - 10σ: −$12,912 on the worst name, −$248,426 if every name moves at once (−24.8%).
- Short leg, 50 names: −$61,449 at 3σ and −$247,177 at 10σ for the whole leg.

The short leg is unbounded. Any real-money form must be defined-risk: long straddles only, or
short straddles wrapped in wings.

## Dates

| event | date |
|---|---|
| first entry | session **2026-10-16**, the first with a standard monthly 21-35 days out; expiry 2026-11-20 |
| entry sessions for the first expiry | 2026-10-16 to 2026-10-30 (11 sessions) |
| entry sessions for the second expiry (2026-12-18) | 2026-11-13 to 2026-11-27 |
| first grade | the **2026-11-20** expiry close, on the first pass after the nightly bars refresh carries it |
| kill-only looks | from 6 expiries |
| first formal read | 12 expiries (MDE about 15.8 bp, twice the historical effect) |
| confirmation at the historical +8.2 bp | about 44 expiries |

Until 2026-10-16 the task takes one in-session `OBSERVE_ONLY` snapshot per session: intraday
spreads and coverage, never graded.

## Caveats, named

- **Quote source.** yfinance chains are delayed about 15 minutes. There is no quote timestamp
  per contract, so freshness is judged from each leg's last trade and the underlying's
  `regularMarketTime`.
- **Implied vol.** IV is our own European BSM inversion of the mid (r = 4%, q = 0). There is no
  American early exercise and no dividends. That is second-order for 30-day ATM options, and it
  is the same for both books.
- **Exit marking.** Intrinsic value at the expiry close. It ignores pin and assignment
  mechanics, and a delisted name is marked at its last close (flagged).
- **Horizon.** The forecast is for 21 sessions; the straddle's horizon is its own expiry
  (15-25 sessions). The √(sessions/21) scale is the same for every name on a date, so it cannot
  change a rank.
- **Survivorship.** The universe is drawn from the living bars file. That is harmless for a
  forward test, because the names are chosen before the outcome.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS:**
- The whole path runs forward at $0 and is tamper-evident: a frozen model, a frozen contract,
  a hash-chained log that refuses rewrites and refuses rows that predate the contract, and a
  grader that needs only the bars file.
- The forecast and trailing vol pick different straddles (3 of 20 long names shared), so the
  twin comparison has something to measure.

**WHAT DOES NOT:**
- The assumed cost. At closing quotes, median usable straddle spreads are 11.5% of mid and
  21% across all quoted names.
- The 100 per leg cell cannot form at the close (164 < 210). The contract falls back
  mechanically to 50 per leg when 100 per leg fails on more than 20% of sessions.

**HIGHEST-EV EXPERIMENT:** read the in-session observation snapshots (free, from the next US
session until 2026-10-16) before the first entry.
- **If** intraday usable spreads stay above about 10% of mid, the vs-cash question is closed
  NO beyond the top ~100 names. The forward log then continues only as the relative test.
- **If** they fall to 3-5%, the lab's cost assumption was conservative, and the absolute book
  is worth its forward record.
