# Night report, 2026-09-29 (the night of Monday 28 September, Hong Kong time)

Written by the night operator (two sessions: the first was cut off at ~22:10, the second ran
02:00-07:30 HKT). Everything here is PAPER money. No LLM has authority over capital. The night
operator placed no order and changed no cap, stop or size. Times are Hong Kong unless marked Z (UTC).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** The machine ran cleanly all night and traded as designed, but
nothing made tonight has been graded yet, so nothing can be called better.

| item | tonight |
|---|---|
| 10-hour paper sim `f496cf18b433` | **COMPLETED**, 103 cycles, **0 unit errors**, 20:26 to 06:29. One DEGRADED moment (see section 2) |
| paper orders sent | **3**, all in the 21:47 cycle just after the US open: SELL ALLE 129, SELL GOOG 58 (labelled POLICY CHANGE), BUY TSM 44. Nothing in the other 102 cycles |
| forecast rows made 28-29 Sep, by writer | **2,479**: review 1,077 (deterministic) · `source:` claims 504 (browser reader + DeepSeek) · investigator `evidence_v3` 270 · five investigator arms A-D 600 (120 each) · thesis cards 28 |
| LLM dollars, by the provider's balance (DeepSeek, the only provider) | $30.70 at 20:26 · $29.45 at 02:09 · **$29.23** at 06:50: **$1.47 for the night**. The operator's own work spent $0.00 |
| PC-PAPER (the book the sim trades) | **-0.09%** since 22 Sep vs SPY **-0.79%** (+0.70 pp); equity $999,355 at the last cycle; 10 names, 80% cash |
| all 39 priced paper accounts | 7 ahead of SPY, 32 behind; pooled -1.40% |
| health check | 53 rows: 24 ALIVE, 20 STALE, 8 UNKNOWN, 1 DEAD. **Real problems: 4** (section 3) |
| browser reader | 953 pages loaded on 28 Sep, **858 readable**, 379 articles stored, 125 of 132 tickers. **Stalled since 00:58**: every page BLANK, gateway connection refused, 4 restarts. Another builder is repairing it |
| network lab | models frozen for 2,964 names; **in charge: LightGBM**, trust (a shrunk rank IC) at 21 sessions 0.0075; ensemble weights LightGBM 0.39 / ridge 0.31 / momentum 0.28 / NN 0.02; size-of-move model `ridge_abs`. 0 forward grades yet |

## 1. IS THE ENGINE BETTER THAN YESTERDAY?

**Cannot say yet.** Judged only on forecasts made before their outcome was known:

- The only forecasts graded since yesterday are 40 one-day rows from `investigator:evidence_v2`,
  made 24 Sep: direction right **15 of 39 (38.5%)**, Brier score 0.254 against 0.250 for a coin.
  No better than a coin, on a tiny sample.
- When the first grades of tonight's work arrive: investigator one-day rows on the 29 Sep
  session, five-day rows on **5 Oct**; the network lab's first five-day grades **~6 Oct**;
  PC-PAPER's own grade needs 21 scored days (**~26 Oct**); the frozen library books are read
  **26 Oct**; the shadow book **27 Oct**.
- The sim's learning report (`backend/data/optimus/learning_reports/report_2026-09-28.md`) repeats
  the standing finding. For "how big will the move be", the free 63-day volatility formula beats
  the LLM arms (+10.0% vs +5.5% skill on 775 held-out rows; the formula wins 7 of 8 days). For
  "which way", the LLM arms score **-7.9%** held out, worse than the base rate.

## 2. What the sim decided and traded

- Every cycle ran the same nine units. The candidate list (25 names, built 24 Sep) was fresh
  enough to reuse. The ranker ran once (21:28) and then skipped, because no new prices arrived.
  Analyst revisions were pulled once (60 min). The investigator forecast ran once.
- **The plan** acted only through the small PROBE book: 10 names at 2% each (20% of capital),
  equal weights, in the candidate list's own order. The bigger EXPLOIT book did not trade, because
  the ranker's measured result is negative (-1.07% vs the market over 21 days). `policy_state` was
  read on all 103 cycles and changed nothing, because no shortlisted name has a graded component yet.
- **The GOOG to TSM change happened and was labelled correctly.** GOOG was sold as `POLICY CHANGE
  (share-class collapse) ... Not a change of view`: Alphabet was held twice (GOOG and GOOGL), and
  GOOGL was kept. TSM, next on the list, was bought as an ordinary PROBE entry. ALLE was sold as an
  exit.
- **No paper order touched a stitched ticker.** These are the 62 tickers whose price history joins
  two companies. The three orders, the ten holdings, the shadow book and its random twin were all
  checked against `stitched_tickers/stitched_20260928T153245Z.json`.
- One DEGRADED moment: the first forecast attempt failed on a Windows file lock while renaming its
  receipt (`PermissionError` on `forecasts/day_2026-09-28.tmp`). The next cycle resumed it and
  finished 270 rows for $0.19. The run was not left half-way, and nothing needed resuming.

## 3. Health check: what is red, and whether it matters

| row | verdict | real? |
|---|---|---|
| `railway_backend` (website lanes) | STALE | **REAL.** The ten website lanes have not been marked since **18 Sep** (11 days). The container restarts from sleep and its scheduler does not run |
| `decision_contract`, `accrual_canary` | STALE | **REAL.** `n_considered` has been 2 on six straight days. The contract still sees a static candidate input |
| `llama_server`, `lab_loop:l2_typing` | STALE | **REAL.** The local model is off, so no typed events are made from news unattended (30 h) |
| `openclaw_gateway` | STALE | **REAL**, and the cause of the reader stall: it is connected without operator scope. Another builder is repairing it |
| `always_on_lab` DEAD + ten `lab_loop:*` STALE | | EXPECTED. The lab was stopped on purpose with a STOP file on 27 Sep. PROBE DEFECT: the probe cannot tell a deliberate stop from a death |
| `live_market_loop` | STALE | EXPECTED: `sim_run` does its job |
| `news_collectors`, `social:youtube`, `optimus_brain` | STALE | EXPECTED/minor: one quiet source (Benzinga has no key); the brain refresh has no scheduler |
| `zero_byte_receipts` | STALE | PROBE DEFECT: the 13 files are `.lock` files, which are empty by design |
| `task:AegisNNLabNightly`, `task:AegisContestDesk` | UNKNOWN | EXPECTED: neither has run yet (first runs 08:30 today and 9 Oct) |
| `task:AegisWRDSPullNight` | UNKNOWN | EXPECTED: a retired one-shot task that can be deleted |
| `social:reddit`, `railway_fleet`, `openclaw_api_bridge`, `task:AegisAlerts`, `task:AegisAnalystPanelDaily` | UNKNOWN | EXPECTED: no key, no receipt mapped, or a weekday-only task |

## 4. Paper accounts (each account's own window, against SPY over the same days)

| family | books | result | status |
|---|---|---|---|
| PC-PAPER (the sim's book) | 1 | -0.09% vs SPY -0.79% since 22 Sep | LIVE, marked 28 Sep |
| website lanes (Railway) | 10 | 1 ahead of SPY (conservative-atr +4.85% vs +3.32%), 9 behind; mirror -22.2%; family -2.1% | **marks stale since 18 Sep** |
| Alpaca hackathon fleet | 6 | all 5 readable accounts behind SPY (-1.2% to -19.9%, vs -0.23% since 28 Aug); hack3's key is invalid | LIVE |
| night books (from 11 Sep) | 9 (+17 twins) | cash/index book and Book D +7.04% vs SPY +1.17%; momentum +3.19%; five books at 0.00% (never traded); family +2.16% | marked to 25 Sep |
| Murat's own book | 1 | -5.09% vs SPY +0.35% since 11 Aug (share counts unconfirmed) | LIVE |
| frozen LLM, library and twin books | 311 | not graded yet. They entered at the 28 Sep open (some enter 29 Sep), and the grader needs the 28 Sep close | UNGRADED 306, PENDING 4, VOIDED 1 |
| agency books | 3 | not graded | UNGRADED |

**Entry prices of the frozen library books.** The books are registered to enter at the
**28 Sep open** (TRIAL-LIB-FWD-TWIN-1, committed 20:21 HKT on 28 Sep, before the 21:30 open).
The grader takes the entry price from that session's opening bar. That bar did not exist on disk
until the 06:31 bar refresh, so no entry price could be checked during the night. See the
daily-pass section below.

**The 06:30 daily pass had not finished by 07:25.** It started 06:30:01 (PID 138448). The bar
refresh landed at 06:31, and the 28 Sep session is now on disk (e.g. SPY open 768.35, TSM 448.39,
JAZZ 235.67). At 07:25 the pass was on the analyst-snapshot step at 250 of 2,362 symbols, about
158 minutes in total, so the book grade and the paper-accounts receipt come after roughly 09:30.
Two things are therefore **still to be checked** by whoever reads this first:
(a) that `llm_portfolio` grades the 28 Sep entries from the 28 Sep open, as registered;
(b) that `paper_accounts/roi_2026-09-28.json` is not replaced by a narrower one. At 07:25 it is
still the broker-included receipt written at 02:11 (scope `with_broker: True`, 7 broker accounts,
sha256 `1facb281...`). The script refuses a narrower overwrite by design
(`scripts/paper_accounts_roi.py:1015`), and a new receipt would take the run-id filename.

## 5. The shadow book (decisions as probabilities, with weights that shrink toward zero)

**It was frozen and registered before entry.** Book **`439fd84f869744e0`**, "SHADOW_BAYES_v0 sleeve
2026-09-28", was frozen at 14:05Z on 28 Sep. It enters at the **29 Sep open**, is graded daily and
places no broker orders. Its matched control was frozen with it: the random same-band twin
**`ec29c635db8ac686`**, plus an SPY twin `d00f3ab5451adc9e` and an equal-weight twin
`3e0a91bed8759db0`. Registration:
`backend/data/optimus/shadow_bayes/REGISTRATION_SHADOW_BAYES_v0_2026-09-28.json`. Holdings: JAZZ
32.8%, TS 31.1%, SNDR 19.3%, TSM 16.8%. The "live-size" version is 3.7% of this sleeve plus 96.3%
SPY. First read 27 Oct, decisive read 24 Dec.

It does **not** yet use the network lab's ensemble or size forecast. Those were frozen 90 minutes
after it, and v0 may not change before its 63-session read. The rule already gives LLM direction
calls a weight of zero: in tonight's fiction test, DeepSeek scored 43-45% and Claude Opus 44.6% on
post-cutoff cases, where a coin scores 50%. A **v1** would use the lab's size forecast to set
position sizes and its trust-weighted ensemble for direction (today's trust is tiny, an IC of
0.004-0.0075). It would be a second new book, and the current roadmap says no new book before
26 Oct. **That is the owner's decision** (section 6). I did not freeze a v1.

## 6. What needs the owner's decision

1. **Shadow book v1: now, or on 26 Oct?** Starting now gives it a forward record 4 weeks longer,
   but it breaks the roadmap's "no new book" rule a second time.
2. **The 80% cash.** PC-PAPER holds 80% cash. That is a bigger bet (a market exposure of about
   0.2) than any signal the machine has. Should the part no signal claims sit in cash or in SPY?
3. **The website lanes** have not been marked in 11 days, because the Railway container sleeps. Fix
   them or retire them.
4. **20 of the 30 pairs in TRIAL-LIB-FWD-TWIN-1 hold a stitched ticker.** Most are momentum books
   that bought JAN, LIFE and AKTS because two companies' prices were joined. The forward
   measurement is honest; the reason those names were chosen was a data error. Keep reading them
   as registered (the dated note in the trial file says so), or void them before the first read?
5. Housekeeping: delete the retired `AegisWRDSPullNight` task, and rotate or retire hack3's key.

## 7. Defects found (not fixed; files I may not edit are only reported)

- `scripts/llm_cost_audit.py:122-134` (`find_ledgers`) reads only the legacy `llm_calls.jsonl`,
  which has not existed since the monthly rotation. The real ledger is `llm_calls_2026-09.jsonl`,
  which `llm_telemetry.ledger_files()` (`backend/services/llm_telemetry.py:139`) lists. So the audit
  prints $0 of telemetry and counts the whole provider change as "unaccounted", every time.
- `scripts/night_investigator_forecast.py:681-683`: `tmp.replace(rpath)` has no retry. A Windows
  reader holding the file open made the first attempt fail with `PermissionError`; it recovered on
  the next cycle.
- `scripts/health_probe.py`, probe `always_on_lab`, reports DEAD for a lab stopped by its own STOP
  file (`always_on_lab_lock.json` says `exit_reason: STOP_file`). Probe `zero_byte_receipts` counts
  empty `.lock` files as zero-byte receipts.
- Already being handled by others: the stitched tickers (the ranker fix is in the working tree,
  uncommitted) and the reader/gateway stall.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS:** The plumbing works: a 10-hour paper sim ran 103 cycles with zero errors, sent
exactly the three orders its rules called for and labelled the policy change correctly. The one
real skill on record is predicting the SIZE of a move (the volatility formula and the network lab's
size model), not its direction.
**WHAT DOES NOT:** No direction forecast (LLM, persona, investigator or ranker) beats a coin or a
plain rule when graded out of sample. News still has no path to an order. The website lanes have
gone 11 days without a mark.
**HIGHEST-EV EXPERIMENT:** Freeze the shadow book's v1 so that the network lab's size forecast sets
position sizes, compared against v0 and the random twin from the next open. Size is the only input
with demonstrated skill, and every week of delay is a week less of forward evidence by the 26 Oct
read.
