# Fact-check: an external reviewer's numbers on the strategy library and the paper accounts (2026-09-28)

Research only. Nothing was run; every number below is read from a receipt already on disk, or
from `git log` / `schtasks /query` (read-only). File timestamps are UTC unless marked HKT/local.

## Verdict table

| # | Reviewer's claim | Verdict | Correct number / detail | Source (file, timestamp) |
|---|---|---|---|---|
| 1 | "~288 real rules / 868 evaluated cells" | **CONFIRMED** | `n_candidate_rules: 288`, `cells_looked_at: 868` (306 rules registered, 5 refused, 13 excluded as controls → 288 ranked) | `backend/data/optimus/strategy_library/leaderboard_2026-09-27.json` (`multiplicity`), written 2026-09-27 08:30:04Z, run `2026-09-27T082553Z` |
| 2 | 12-1 quarterly momentum +1,323% cum. since 2020 vs SPY +162%, CAGR ~49.7% vs ~15.7% | **CONFIRMED**, exactly | `mom_12_1_q`: CAGR-since-2020 +49.7%, cum +1323%; SPY CAGR +15.7%, cum +162% | `backend/data/optimus/strategy_library/LEADERBOARD.md`, "Top 10 by hindsight CAGR since 2020" and "SPY" sections, mtime 2026-09-27 16:30 (commit `77893aaf`, 2026-09-27 16:35:57+08:00) |
| 3 | px_vs_ma200_large +1,290%, mom_6_1_large +1,240%, disp_short_avoid +1,207%, qc395\* +1,012%, insider_mom +799% | **CONFIRMED**, exactly, all five | Same table, same rows | Same file |
| 4 | "Top DSR is only ~0.198" | **CONFIRMED** | Highest DSR(n=868) on the entire board is `mom_12_1_q` at 0.198 (Harvey-Liu-Zhu bar is a t ≥ 3.0 on horizon-wide blocks; 0.95 is the promotion bar used elsewhere) | Same file, "Top 10 by deflated Sharpe" |
| 5 | Dev-selected top-10 → +8.8pp mean / +2.6pp median vs SPY in 2024-26, 6/10 beat SPY, dev-vs-later Spearman ≈0.20 | **CONFIRMED**, exactly | `mean 0.088481`, `median 0.026124`, `n_beat_spy 6`, Spearman ρ 0.204385 (p 0.000482, n=288) | `leaderboard_2026-09-27.json` → `dev_selected_sealed_evaluated`, same run |
| 6 | "39 priced accounts: 7 ahead, 32 behind", aggregate ≈ −1.31% | **STALE** | That is a same-day intermediate figure from 2026-09-27 (commit `6a7a2465`: "7 ahead / 32 behind"; prose figure "−1.31%" in `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md:20`, mtime 15:43+08:00). An entry-date fix later the same day (`3204eb4d`, 14:45+08:00 — earlier commit hash, later logical fix; see note below) reclassified several books from priced→pending. **Current**: 33 priced, 6 ahead / 27 behind, aggregate **−0.27%** (all priced) / **−0.31%** (ex. 14 control twins) | `backend/data/optimus/paper_accounts/roi_2026-09-27.json`, `generated_utc 2026-09-27T23:51:21Z` (latest committed receipt); `docs/PAPER_ACCOUNTS.md` (regenerated from it) |
| 7 | Legacy Alpaca: hack2 −1.18%, hack5 −4.95%, hack1 −8.47%, hack6 −17.70%, hack4 −20.17%, SPY +0.28% | **CONFIRMED**, exactly, but **not reproducible from a committed receipt** | Matches `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md:315-320` (as-of last mark 2026-09-25) exactly. The two committed `roi_*.json` receipts do NOT carry these values: 09-26's receipt shows all 6 `alpaca_fleet` rows as `UNPRICED` (network ReadTimeout) except hack3 (`CREDENTIAL_INVALID`, HTTP 401, "NOT a $0 account"); 09-27's receipt has **no `alpaca_fleet` rows at all**, because the scheduled caller runs `paper_accounts_roi --no-broker` (see §C). The numbers exist only in a manual, broker-included run captured in that research note. | `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md` (commit `ed8d0c47`, 2026-09-27 15:45:37+08:00); contrast `backend/data/optimus/paper_accounts/roi_2026-09-26.json` (`alpaca_fleet` rows) and `roi_2026-09-27.json` (`sources` has no alpaca leg) |
| 8 | PC-PAPER ≈ −0.10% vs SPY −0.28% | **CONFIRMED**, exactly, same caveat as #7 | `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md:321`: PC-PAPER, inception 2026-09-22, ROI −0.10, SPY −0.28, vs SPY +0.18pp, last mark 2026-09-25. Consistent in direction with `backend/data/optimus/pc_book/nav.jsonl`'s last tick (2026-09-25T13:48:58Z, equity $999,142.66 vs $1,000,000 start = −0.086%). Not in either committed `roi_*.json`'s `pc_paper` row for the same reason as #7 (09-26: `UNPRICED`, "read operation timed out"; 09-27: absent, `--no-broker`) | Same research note; `backend/data/optimus/pc_book/nav.jsonl` (mtime 2026-09-27 14:44) |
| 9 | Old night books: two ≈+7.0% vs SPY +1.17%, 12-1 momentum ≈+3.2%, only 3 marks | **CONFIRMED**, exactly | Two `night_books` rows at +7.04% (`b109c886`, `3b3e7049`), one at +3.19% (`8dbbb73b`, "12-1 momentum, k=12"), SPY same window +1.17%, all "3 marks", inception 2026-09-11, last mark 2026-09-25 | `docs/PAPER_ACCOUNTS.md` (2026-09-28), sourced from `roi_2026-09-27.json` |
| 10 | "Website lane NAVs are still last marked September 18" | **CONFIRMED**, and still true today | All 10 `website_lane` rows: `last mark 2026-09-18`, `fresh: false`, deploy "expected NAV date 2026-09-25" never arrived. Today is 2026-09-28 → **10 days stale**, 3 days past the deploy's own expected-refresh date | `docs/PAPER_ACCOUNTS.md`; `roi_2026-09-27.json.sources.website_lanes` (`"fresh": false`, `"all_fresh": false`) |
| 11 | `paper_accounts_roi.py` reads real Alpaca state, never treats 401 as $0, separates PC-PAPER / Railway lanes / legacy books / twins / frozen LLM books, uses each account's own window, has dedicated tests | **CONFIRMED** | `FAMILY_ORDER` = website_lane, alpaca_fleet, pc_paper, night_books, night_books_twin, murat_book, agency, llm_portfolio:{personal,competition,lib,twin} — 11 families. `test_401_is_credential_invalid_never_zero` asserts `status == CREDENTIAL_INVALID` and `equity is None` on a 401. 20 test functions in `backend/tests/test_paper_accounts_roi.py`. One caveat not in the claim: the **scheduled** run always passes `--no-broker`, so `alpaca_fleet`/`pc_paper` separation exists in code but is never exercised by the automated pass (see #7, #8, §C) | `scripts/paper_accounts_roi.py` (git `d8b4badc`, 2026-09-27 19:16:45+08:00); `backend/tests/test_paper_accounts_roi.py` |
| 12 | "You now have hundreds of books" | **CONFIRMED** | 347 book-rows in the `--no-broker` receipt alone (33 LIVE, 306 PENDING, 7 UNGRADED, 1 VOIDED), +6 `alpaca_fleet` +1 `pc_paper` = **354** total tracked accounts/books across 11 families | `roi_2026-09-27.json` (`aggregate.status_counts`, `len(rows)==347`) |
| 13 | "The free 63-day volatility prior beat the investigator on the magnitude question" | **CONFIRMED** | "the free 63-day-vol prior on magnitude (+10.0% held out at h=1; the LLM +5.5%)" | `docs/HANDOFF_2026-09-26_WAVE2_THE_REVIEW_LOOP_CLOSED_FOUR_IDEAS.md`, §6 "The three sentences (chunk I)", commit `ca5e07bb` 2026-09-27 19:45:43+08:00 |

Note on #6: the commit graph is not monotonic with the fix narrative because `3204eb4d` ("Entry
dates from the grader's own rule") is the commit that touches `roi_2026-09-27.json` last
(`git log -1`), timestamped 14:45+08:00, while the "39/7/32" figure was written into a *prose*
research note at 15:43+08:00 and into `HANDOFF_2026-09-26_WAVE2…md` even later (its last touch is
19:45+08:00, for an unrelated §21 edit — the 39-count text itself was added earlier that day per
its own commit `6a7a2465`, 2026-09-27 ~08:00 per the handoff's own timestamp references). The
receipt that matters is the **newest** one, `generated_utc 2026-09-27T23:51:21Z`, produced by the
`AegisDailyPass` scheduled task's 2026-09-28 06:30 local run (see §C) — that is the 33/6/27/−0.27%
figure, and it postdates every "39" mention on disk.

---

## A. Backtests: the single honest summary

**Everything in the "Top 10 by hindsight CAGR since 2020" table (claims 2-4) is a HINDSIGHT
backtest.** `LEADERBOARD.md`'s own banner: *"Every rule was registered 2026-09-26, after every
month in these tables; 'since 2020' is what the rule WOULD have done, not what Aegis did."*
Below is what happens when the same 288-rule, 868-cell board is put through every check the
project's own canon requires before a cell is anything but decoration.

**Top cell (`mom_12_1_q`, momentum, k=20) put through all six tests:**

| test | result |
|---|---|
| by-year (hold-month), 2017-2026 | `-+++-+++++` — 8 of 10 years positive |
| leave-one-year-out worst case | drop 2020 → mean active monthly return still **+1.81%** (positive) |
| without its best 5 months | best-5-month share of log return 0.44; CAGR w/o them **+22.0%** vs SPY's own w/o-best-5 **+15.3%** — still beats |
| vs the panel's own random portfolio | random controls (`random_1/2/3`) ran +15.2% / +5.7% / +12.1% CAGR since 2020 (cum +155%/+44%/+113%) — `mom_12_1_q`'s +49.7% clears this by a wide raw margin |
| matched-twin (characteristic-matched: same size band × vol-63 tercile × 12-1 tercile) | one of only **2 of 288** cells that clears t ≥ 2 vs its 21-draw twin in BOTH windows is a close relative, `mom_12_1_q_trend@k20` (dev +1.77%/mo t 2.34, 2024-26 +2.63%/mo t 2.14); `disp_short_avoid@k20` is the other. `mom_12_1_q` itself is not confirmed as one of the two survivors in the matched-twin test (the two named cells use a "_trend" / dispersion variant, not the plain id) |
| DSR at n=868 | **0.198** — the single highest DSR on the whole 868-cell board, far below the 0.95 promotion bar and below the 0.95/HLZ-t≥3.0 bar used everywhere else in this project |

**The other nine of the "top 10 by hindsight CAGR" fare worse on "without its best 5 months":**
`px_vs_ma200_large` (58% of return in top-5 months, CAGR-w/o-them +14.7% < SPY's +15.3% —
**loses to SPY once its best months are removed**), `mom_6_1_large` (60%/+14.0% < +15.3%,
same failure), `qc536_secneutral_multimom_large` (78%/+6.8%), `mom_low_ag` (63%/+11.6%),
`qc597_secneutral_multimom_calm` (81%/+5.5%), `mom_12_1_liqw` (91% of the *entire* return from 5
months, +2.2%) all fail this test outright. Only `mom_12_1_q`, `disp_short_avoid`,
`qc395_sharpe252_above_trend_large` (+17.4% vs +15.3%, barely) and `insider_mom` (+20.4%) survive
it — 4 of 10.

**The library-wide, harder answer (family-pooled, 25 families of ≥3 rules,
`docs/SIGNAL_STRUCTURE_2026-09-26.md`, same run):**

- Pooling the median rule's 2024-26 excess over a size/vol/momentum-matched random twin gives
  **−0.2%** — i.e. the median rule LOSES to its own matched twin in the out-of-window read. The
  median rule's +7.1% excess over an unmatched random portfolio is **"entirely style"** (size,
  volatility, past-return tilt), not selection skill.
- **Zero of 25 pooled families show alpha vs SPY or vs the random panel in both windows.** 24 are
  `CANNOT_DISTINGUISH`; the one `ALPHA_DETECTED` (`diversified_combo`) is **negative**
  (hedged −0.98%/mo, t −2.06).
- Exactly **one family, `weighted`** (inverse-vol / liquidity-weighted / risk-parity variants of
  momentum, quality, gross-profitability, net-raises), clears rule-minus-matched-twin t ≥ 2 in
  BOTH windows (+0.69%/mo t 2.01 dev, +1.31%/mo t 2.25 in 2024-26), with **DSR 0.83 at n=25
  families — still below 0.95.**
- Best DSR anywhere at the family level: `quality` 0.891 (vs the panel), `weighted` 0.529 (vs
  SPY), `regime_gated` 0.872 (rule−twin). **None reaches 0.95.**

**Which rules survive ALL of the checks (by-year, LOO-worst, without-best-5-months, vs the random
panel, vs a matched twin, and DSR)? None.** Two individual cells (`mom_12_1_q_trend@k20`,
`disp_short_avoid@k20`) and one pooled family (`weighted`) clear the matched-twin test in both
windows — the project's own read of that is "a lead for forward paper, not a claim," and their DSR
(≤0.83) still sits below the 0.95 bar used for promotion everywhere else in this codebase. This is
consistent with the 2026-09-28 handoff's own scoreboard line: *"Best historical net strategy vs
the market: unchanged: no cell with DSR ≥ 0.95."* (`docs/HANDOFF_2026-09-28_THE_READER_NIGHT.md`,
§0, referencing an earlier 336-cell run — the 868-cell run reaches the identical verdict.)

**Minimum detectable effect** — a reader needs this to know what "cannot distinguish" means here:
- Single rule, 2024-26 window (32 monthly blocks): median active σ 5.44%/mo → SE 0.96% → **MDE
  2.69%/mo at 80% power** (an annualised ~32%). A window this long can kill an implausible rule; it
  cannot certify a realistic sub-1%/month edge.
- Pooled family (25 families): MDE falls only to ~1.0-2.2%/mo (0.7-0.8× the single-rule MDE, not
  half — family members are correlated, median n_eff ≈ 2-4, not the nominal member count).

---

## B. Paper accounts: every family, one table

Source: `backend/data/optimus/paper_accounts/roi_2026-09-27.json` (`generated_utc
2026-09-27T23:51:21Z`, produced by the `AegisDailyPass` Windows scheduled task — confirmed live via
`schtasks /query /tn AegisDailyPass`: **Enabled, Last Run 2026-09-28 06:30, Last Result 0**), plus
`docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md` for the two broker-backed families
the scheduled run skips.

| family | n (books) | start date(s) | marks | return | benchmark (own window) | status |
|---|---:|---|---|---|---|---|
| website_lane | 10 | 2026-06-08 → 2026-07-27 | — | +4.85% … −22.16% (10 rows, mean ≈ −2.1% pooled) | SPY +2.03% to +5.53% (per-lane window) | **LIVE but STALE** — last mark 2026-09-18, 10 days old; deploy's own "expected" refresh date (09-25) also missed |
| alpaca_fleet (hack1-6) | 6 | 2026-08-28 | daily (broker-native) | −1.18% (hack2) to −20.17% (hack4); hack3 CREDENTIAL_INVALID (401, not $0) | SPY +0.28% (same window) | **LIVE, but only via a manual/live run.** The scheduled pass never prices this family (`--no-broker`); last confirmed live read 2026-09-25 per the research note |
| pc_paper (PC-PAPER) | 1 | 2026-09-22 (first trades 2026-09-25) | 3 ticks (`nav.jsonl`) | −0.10% (research note) / −0.086% (raw last tick in `pc_book/nav.jsonl`) | SPY −0.28% | **LIVE, same caveat as alpaca_fleet** — last local tick 2026-09-25, 3 days stale as of that note, ~6 as of today |
| night_books | 9 | 2026-09-11 | 3 | +7.04% (×2), +3.19% (12-1 mom), +0.00% (×5, unfilled) | +1.17% | 8 LIVE, 1 UNGRADED (never marked) |
| night_books_twin | 17 | 2026-09-11 / 2026-09-12 | 3 | +11.57% to −3.39% (spread across 14 twins) | +1.17% | 14 LIVE, 3 UNGRADED |
| murat_book | 1 | 2026-08-11 | to 2026-09-25 | −5.09% (window return, not P&L-since-purchase; 11/12 names priced) | +0.35% | LIVE |
| agency | 3 | — | — | — | — | UNGRADED — proposals in `decisions/2026-09-28.json`, no `paper_books` entry, no NAV path exists |
| llm_portfolio:personal | 20 | — | 0 | — | — | PENDING, entry 2026-09-28 |
| llm_portfolio:competition | 11 | — | 0 | — | — | PENDING, entry 2026-09-28 |
| llm_portfolio:lib | 31 | registered 2026-09-26 | 0 | — | — | PENDING, entry 2026-09-28; 1 of these VOIDED before entry (`lib_mom_12_1_liqw_sealed_2026-09-26`: 97.5% concentrated in MU+SNDK) |
| llm_portfolio:twin | 245 | registered 2026-09-26 | 0 | — | — | PENDING, entry 2026-09-28 |

**Totals:** 11 distinct families; **354** distinct book/account rows (347 in the `--no-broker`
receipt + 6 `alpaca_fleet` + 1 `pc_paper`). Of those, **33 are LIVE-and-priced** (39 including the
two broker families when a live run is done), **306 PENDING**, 7 UNGRADED, 1 VOIDED — all PENDING
books enter **today, 2026-09-28** (the US session), with first grades due **2026-09-29** per
`docs/HANDOFF_2026-09-28_THE_READER_NIGHT.md` §0 ("NOT GRADEABLE YET").

**Registered before entry?** The 307 `llm_portfolio:*` books (personal/competition/lib/twin) were
frozen/registered 2026-09-26, two days before their 2026-09-28 entry — satisfies the
`PRODUCT_EXPERIMENT` licence's "frozen contract before first decision." `night_books` /
`night_books_twin` were seeded 2026-09-11/12 via the attended `seed-a-lane` procedure (predates
this fact-check's window; not independently re-verified here). The `website_lane` family and the
`alpaca_fleet` legacy hackathon accounts predate the 2026-08-23 licensing framework entirely and
were never registered under it — they are carried forward as historical record, not as
`PRODUCT_EXPERIMENT` claims. `agency` proposals have no NAV path so registration is moot until one
is built.

---

## C. Code currency

Git dates below are `git log -1 --format=%ci` (read-only; no checkout/reset/stash run).

| component | file | last commit | scheduled caller? | tests? | data currency note |
|---|---|---|---|---|---|
| Backtest factory | `backend/services/strategy_library.py` | 2026-09-27 11:17:46+08:00 | **No.** Not called by `daily_pass.py`, not called by `scripts/run_night_launcher.py` (the only other always-on scheduler, task `AegisIIF1NightLauncher`, last ran 2026-09-25). No `schtasks` entry names it (`AegisAnalystPanelDaily`, `AegisDailyPass`, `AegisIIF1NightLauncher`, `AegisTelegramAgent`, `AegisWRDSPullNight` are the only 5 registered tasks) | Yes: `test_strategy_library.py`, `test_strategy_library_ext.py`, `test_strategy_library_rates.py` | Code is current; the 868-cell board is only as fresh as the last **manual** run (`2026-09-27T082553Z`, 16:30 local). Nothing pages anyone if a week goes by without a re-run — no staleness probe exists for this specific artifact (unlike `system_health.p_book_grader`, below) |
| Backtest factory driver | `scripts/night_factory_jobs.py` (job `B_backtest_factory`) | 2026-09-27 23:09:51+08:00 | same as above (invoked from a manually-launched `night_factory.py` run, not a cron/task) | shares the strategy_library tests | same |
| Grader (`llm_portfolio`) | `backend/services/llm_portfolio.py` | 2026-09-27 19:16:45+08:00 (`d8b4badc`: "The book grade has a scheduled caller") | **Yes, as of this commit** — `scripts/daily_pass.py` now runs `scripts.llm_portfolio grade --json` (PULL mode) as a boxed step, and `daily_pass` itself is the `AegisDailyPass` Windows task, confirmed **Enabled, last run 2026-09-28 06:30, exit 0** | Yes: `test_llm_portfolio_grade.py`, `test_llm_portfolio_twins.py`, `test_llm_portfolio_void.py`, `test_llm_portfolio_cli.py`, `test_forecast_grader.py`, others | Current and running daily. `system_health.p_book_grader` (added same commit) reads the newest leaderboard and goes STALE when bars are >1 session behind or a book past entry has no grade row |
| Daily pass driver | `scripts/daily_pass.py` | 2026-09-27 19:51:09+08:00 | **Yes** — `AegisDailyPass`, confirmed live via `schtasks`, next run 2026-09-29 06:30 | Yes: `test_daily_pass.py` | Current; each step boxed (900/600/600s) so one hung step can't repeat the 2026-09-14 4-day-hang incident |
| `paper_accounts_roi.py` | `scripts/paper_accounts_roi.py` | 2026-09-27 19:16:45+08:00 (same commit as the grader) | **Yes** — `daily_pass` runs it as `paper_accounts_roi --no-broker --json` | Yes: 20 test functions in `backend/tests/test_paper_accounts_roi.py`, incl. the 401-never-$0 guard | **Code supports `alpaca_fleet`/`pc_paper`, but the scheduled invocation always passes `--no-broker`, so those two families are never refreshed automatically.** The only way their numbers exist on disk is a manual, credentialed run (see claims #7/#8). This is the single biggest "code current, data stale" gap found in this pass |
| `bridge_report` | (called from `daily_pass`) | rolled into `d8b4badc` | Yes, same `daily_pass` step | not independently checked this pass | `bridge_2026-09-28.json` exists, mtime 2026-09-28 07:51, consistent with today's scheduled run |

**Summary:** the grading/paper-accounts/bridge pipeline gained a real scheduler only **one day
before this fact-check** (commit `d8b4badc`, 2026-09-27 19:16) and is now verifiably running
(today's `AegisDailyPass` exit 0). The backtest factory that produces every number in claims 1-5
has **no scheduler at all** — it is exactly as fresh as the last person who remembered to run it,
with no alarm if nobody does.

---

## D. Five cheapest measurement improvements, ranked by information/hour

1. **Add a staleness probe for the backtest-factory leaderboard**, mirroring the pattern already
   built for `system_health.p_book_grader` (same commit `d8b4badc`) and for the funnel
   (`FUNNEL_STALE_DAYS`, `investment_committee.py`). Right now nothing goes red when the 868-cell
   board ages — the exact failure class this project already paid for once (the 44-day-old funnel
   file, 2026-09-22). *Touches:* `backend/services/system_health.py` (new probe) +
   `backend/services/strategy_library.py` (expose `run_id`/`written_utc` for the probe to read).
   Effort: ~1 hour, reusing an existing pattern.

2. **Put the matched-twin / family-pool verdict into the leaderboard's own `read_me_first` and
   into `LEADERBOARD.md`'s top table**, not only in `docs/SIGNAL_STRUCTURE_2026-09-26.md`. An
   external reviewer (and any future session) who opens `LEADERBOARD.md` sees the "+1,323%"
   hindsight table first and has no reason to go looking for the twin/family-pool result that
   overturns it — which is exactly what produced claims 2-4 here. One sentence
   ("median rule loses to its matched twin by 0.2% in 2024-26; 0 of 25 families clear alpha in
   both windows") at the top of the same file closes this. *Touches:* the leaderboard-rendering
   code path in `backend/services/strategy_library.py` / `night_factory_jobs.py`. Effort: ~30 min.

3. **Stamp `alpaca_fleet` and `pc_paper` rows with their own `last_priced_utc` and an explicit
   `stale_days` field**, separate from the receipt's overall `generated_utc`, since the scheduled
   run never prices them (§C). Without this, a reader has no on-receipt signal that these two
   families' numbers (when present at all) may be days older than everything else in the same
   table. *Touches:* `scripts/paper_accounts_roi.py` (the row builder already has `last_mark`;
   promote it to a top-level, always-present field with an age computed against `date.today()`).
   Effort: ~30-45 min, small code + one test.

4. **Compute and print `n_days_stale` on every `website_lane` row** instead of the boolean
   `fresh: false`. Confirming claim #10 required subtracting "2026-09-18" from "today" by hand;
   a printed integer (and a red flag past some threshold, e.g. 7 days) makes this a receipt fact
   instead of arithmetic a reader has to redo. *Touches:* `scripts/paper_accounts_roi.py`
   (website_lane row builder). Effort: ~15 min.

5. **Never let a headline paper-account percentage live in prose without the receipt path beside
   it, and add a cheap lint/test for it.** The stale "39 priced / −1.31%" figure is still sitting,
   uncorrected, in at least three committed docs
   (`docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md:20`,
   `docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md:120`,
   `docs/research_notes/2026-09-26/research_value_proposition_and_competitor_ranking.md:87,202`) —
   exactly the number an external reviewer picked up and quoted as current. `docs/PAPER_ACCOUNTS.md`
   already does this right (headline number + receipt link on line 2); the cheap fix is a grep-based
   test (in the spirit of the existing AST-based "headline number belongs in a receipt" house rule)
   that flags a bare `±N.NN%` near the words "priced accounts" outside `docs/PAPER_ACCOUNTS.md` and
   its dated archive copies. *Touches:* a new `backend/tests/test_*` doc-scanning guard, in the
   family of the repo's existing docstring-aware AST guards. Effort: ~1 hour (mind the "grep-shaped
   guard that cannot tell an explanation from an instance" lesson — read the AST/context, don't
   regex-ban the phrase itself).
