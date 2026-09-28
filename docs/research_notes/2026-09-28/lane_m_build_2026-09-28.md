# Lane M build, 2026-09-28: measurement honesty (M1-M6)

Licence: `PRODUCT_EXPERIMENT` diagnostics. $0 LLM. No order was placed and no book or account
was created. Nothing is committed here (the orchestrator commits). Every number below is read
from the receipt named beside it.

**RESULT IMPROVEMENT: NONE.** Nothing here adds edge. It removes two flattering readings (the
lucky quarterly calendar, and a narrower paper-account scope) and registers the one forward
comparison.

## M1. The quarterly-offset triplet

- **Receipt:** `backend/data/optimus/strategy_library/calendar_offsets_2026-09-28T055923Z.json`.
  Monthly series in `calendar_offsets_monthly_2026-09-28T055923Z.parquet`.
- **Engine:** `strategy_library.run_strategy` with `rebalance_months`, band costs on (cost_scale
  1.0), at k = 20, the k every lead is frozen at.
- **Twin:** `matched_twins` with 21 seeded draws (twin21). Twin net = twin gross minus the rule's
  own cost.
- **Statistics:** t is on non-overlapping REBALANCE blocks; MDE = 2.8 × SE per month; years are
  keyed on the HOLD month.
- **DSR:** vs SPY at n = 884 (868 reference cells + 16 run here); rule − twin21 at n = 288.
- **SPY** (`spy_tr_yf_adjclose`): CAGR 15.1% over the full window, +162% since 2020. Without its
  own best 5 months: 9.5-9.9%, by window.
- **Panel:** identical to the reference run `2026-09-27T082553Z` (372,754 rows, 117 dates, 4,787
  symbols, 393,586 revision events). The run refuses on any shrink.
- **Cost:** peak working set 2,278 MB, 50 s.

| rule @k20 | offset | cum since 2020 | CAGR (vs SPY) | 2024-26 vs SPY | vs random panel | rule - twin21 /mo, t (blocks), MDE | dev t / 2024-26 t | by year vs SPY (hold) | LOO-worst vs SPY | CAGR w/o best 5 (SPY w/o 5) | SE / MDE vs SPY /mo | DSR vs SPY / vs twin | twin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `mom_12_1_q` | JAJO | +1323% | +40.7% (+25.4%) | +37.9% | +31.5% | +1.88%, +2.53, +2.07% | +1.91 / +1.68 | `-+++-+++++` | +1.81% (drop 2020) | +22.0% (+9.9%) | +0.95% / +2.66% | +0.197 / +0.404 | BEATS |
| `mom_12_1_q` | FMAN | +424% | +23.4% (+8.4%) | -5.0% | +14.5% | +0.70%, +1.21, +1.61% | +1.44 / -0.20 | `--++-++-+-` | +0.48% (drop 2020) | +7.3% (+9.5%) | +0.81% / +2.28% | +0.021 / +0.033 | n.s. |
| `mom_12_1_q` | MJSD | +433% | +26.4% (+11.3%) | +8.4% | +17.3% | +1.00%, +2.04, +1.37% | +1.74 / +1.06 | `+-++-+++-+` | +0.99% (drop 2020) | +9.4% (+9.6%) | +0.80% / +2.23% | +0.032 / +0.062 | BEATS |
| `mom_12_1_q` | **1/3 each (calendar-neutral)** | +661% | +30.9% (+15.8%) | +13.5% | -- | +1.20%, +2.49, +1.35% | +2.17 / +1.18 | -- | -- | -- | -- | -- | read beside, not a verdict input |
| `mom_12_1_q` | **VERDICT** | spread +899% | | spread +42.8% | | spread +1.18%/mo | | | | | | | **CANNOT_DISTINGUISH** (beats: jajo, mjsd; loses: none) |
| `disp_short_avoid` | JAJO | +1207% | +39.2% (+23.9%) | +29.0% | +30.1% | +1.61%, +2.32, +1.94% | +1.81 / +1.49 | `-+++++++++` | +1.62% (drop 2020) | +21.3% (+9.9%) | +0.97% / +2.72% | +0.177 / +0.326 | BEATS |
| `disp_short_avoid` | FMAN | +275% | +18.3% (+3.4%) | -9.5% | +9.5% | +0.52%, +0.96, +1.52% | +1.39 / -0.54 | `--++-+--+-` | +0.13% (drop 2020) | +3.8% (+9.5%) | +0.77% / +2.16% | +0.008 / +0.023 | n.s. |
| `disp_short_avoid` | MJSD | +233% | +18.3% (+3.2%) | +1.6% | +9.2% | +0.21%, +0.46, +1.25% | +0.30 / +0.46 | `+-++-+-+-+` | +0.54% (drop 2020) | +4.4% (+9.6%) | +0.73% / +2.03% | +0.009 / +0.005 | n.s. |
| `disp_short_avoid` | **1/3 each (calendar-neutral)** | +466% | +26.1% (+11.0%) | +6.7% | -- | +0.81%, +1.80, +1.26% | +1.72 / +0.61 | -- | -- | -- | -- | -- | read beside, not a verdict input |
| `disp_short_avoid` | **VERDICT** | spread +974% | | spread +38.5% | | spread +1.40%/mo | | | | | | | **CANNOT_DISTINGUISH** (beats: jajo; loses: none) |
| `qc470_mom252_quarterly_riskparity` | JAJO | +719% | +32.7% (+17.4%) | +31.1% | +23.5% | +1.37%, +2.12, +1.81% | +1.64 / +1.30 | `-++++-++++` | +1.37% (drop 2020) | +15.6% (+9.9%) | +0.92% / +2.58% | +0.088 / +0.238 | BEATS |
| `qc470_mom252_quarterly_riskparity` | FMAN | +705% | +31.0% (+16.0%) | +25.2% | +22.1% | +1.27%, +2.51, +1.41% | +1.91 / +1.76 | `--++--++++` | +1.08% (drop 2020) | +14.1% (+9.5%) | +0.77% / +2.16% | +0.071 / +0.212 | BEATS |
| `qc470_mom252_quarterly_riskparity` | MJSD | +328% | +22.2% (+7.1%) | -5.2% | +13.1% | +0.67%, +1.31, +1.44% | +1.55 / -0.40 | `--++-+++-+` | +0.83% (drop 2020) | +6.1% (+9.6%) | +0.73% / +2.05% | +0.015 / +0.023 | n.s. |
| `qc470_mom252_quarterly_riskparity` | **1/3 each (calendar-neutral)** | +585% | +29.7% (+14.6%) | +16.9% | -- | +1.12%, +2.62, +1.19% | +2.22 / +1.34 | -- | -- | -- | -- | -- | read beside, not a verdict input |
| `qc470_mom252_quarterly_riskparity` | **VERDICT** | spread +391% | | spread +36.2% | | spread +0.70%/mo | | | | | | | **CANNOT_DISTINGUISH** (beats: fman, jajo; loses: none) |
| `mom_12_1_q_trend` | JAJO | +648% | +28.4% (+13.1%) | +20.8% | +19.2% | +1.95%, +2.87, +1.91% | +2.17 / +1.87 | `-+-+-+++++` | +0.88% (drop 2020) | +10.8% (+9.9%) | +0.96% / +2.69% | +0.027 / +0.548 | BEATS |
| `mom_12_1_q_trend` | FMAN | +172% | +10.6% (-4.4%) | -17.1% | +1.7% | +0.73%, +1.40, +1.46% | +1.82 / -0.46 | `---+-+----` | -0.55% (drop 2020) | -3.5% (+9.5%) | +0.82% / +2.30% | +0.001 / +0.042 | n.s. |
| `mom_12_1_q_trend` | MJSD | +199% | +14.4% (-0.7%) | -5.9% | +5.2% | +0.97%, +2.12, +1.28% | +1.83 / +1.03 | `++-+---+--` | -0.15% (drop 2020) | -1.2% (+9.6%) | +0.80% / +2.23% | +0.002 / +0.070 | BEATS |
| `mom_12_1_q_trend` | **1/3 each (calendar-neutral)** | +304% | +18.2% (+3.1%) | -1.0% | -- | +1.22%, +2.80, +1.22% | +2.47 / +1.27 | -- | -- | -- | -- | -- | read beside, not a verdict input |
| `mom_12_1_q_trend` | **VERDICT** | spread +477% | | spread +37.9% | | spread +1.23%/mo | | | | | | | **CANNOT_DISTINGUISH** (beats: jajo, mjsd; loses: none) |

**The verdict rule was declared in code before the run** (`backend/services/calendar_offsets.py`):

- An offset **BEATS** its twin when the full-window mean monthly rule − twin21 is > 0 and t >= 2
  on rebalance blocks.
- An offset **LOSES** when that mean is <= 0.
- **ROBUST_TO_CALENDAR** = all three offsets beat. **CALENDAR_ARTEFACT** = at least one beats and
  another loses. **CANNOT_DISTINGUISH** = anything else.

**Verdicts: all four rules are CANNOT_DISTINGUISH.**

- No rule is ROBUST_TO_CALENDAR. JAJO is the only calendar on which all four rules beat their
  twins.
- No offset of any rule LOSES to its twin: all 12 point estimates are positive. So under the
  declared rule none is a CALENDAR_ARTEFACT either.

How to read it:

1. **The headline numbers are the best calendar.**
   - Since 2020, `disp_short_avoid` makes +1,207% at JAJO, +275% at FMAN and +233% at MJSD.
     `mom_12_1_q_trend` makes +648% / +172% / +199%.
   - In 2024-26 vs SPY, the spread across calendars is 36-43 pp for every rule.
   - At FMAN, three of the four rules are behind SPY in 2024-26, and `mom_12_1_q_trend` is behind
     SPY over the full window (−4.4%/yr).
2. **Under the roadmap's looser wording** ("a lead whose other two calendars do not beat their
   matched twins is relabelled a calendar artefact"), `disp_short_avoid` qualifies:
   - Its FMAN t is 0.96 and its MJSD t is 0.46, and its FMAN 2024-26 rule − twin is negative.
   - `qc470` does not qualify (FMAN beats), and neither does `mom_12_1_q_trend` (MJSD beats).
   - The declared rule is stricter about ARTEFACT (it needs an offset to LOSE), and the verdicts
     above follow the declared rule.
   - The spread between calendars (0.7-1.4%/mo) is inside one MDE (1.25-2.07%/mo), so the
     offsets cannot be told apart from each other either.
3. **The calendar-neutral book is the honest single number.** It holds one third in each offset,
   which is how rebalance-timing luck is removed.
   - `disp_short_avoid`: +0.81%/mo vs its twin, t 1.80; in 2024-26, +0.52%/mo, t 0.61.
   - `mom_12_1_q_trend`: +1.22%/mo vs its twin, t 2.80, but only +3.1%/yr vs SPY over the full
     window and −1.0%/yr in 2024-26.
   - `mom_12_1_q` and `qc470` clear t 2.5 vs the twin over the full window, and fail it in
     2024-26 (t 1.18 and 1.34).
4. **The leads were selected on a monthly t, but they hold for three months.**
   - The `default` rows use the reference run's own twin seed and reproduce
     `signal_structure/matched_twins_2026-09-27T082553Z.json` exactly.
   - On the monthly t, `disp_short_avoid` reads 2.07 / 2.02 (dev / 2024-26). That is the (b)
     pass that made it a lead.
   - On rebalance blocks it reads **1.94 / 1.66**, and `mom_12_1_q_trend` reads 2.24 / **1.96**.
     Neither lead clears t >= 2 in both windows.
   - With another seed of the same twin design (the JAJO offset cell), `disp_short_avoid`'s
     monthly t falls to 1.93 / 1.68. So the pass depended on the blocking and on the twin's
     random draw.
5. **Which part of the sample (protocol 11).**
   - For every rule, the worst leave-one-year-out drops 2020.
   - For `disp_short_avoid` at MJSD, rule − twin by hold year is −8.7 (2020), −16.9 (2021) and
     +28.8 (2022) pp: one year carries it.
   - The matched twin is drawn from the same 12-1 TERCILE. A top-20 momentum sort therefore still
     beats it partly on momentum extremity within the tercile. That is a limit of tercile
     matching, and it was not tested here.
6. **Reconfirmation.**
   - The `mom_12_1_q` offsets reproduce the reference board's controls to the last digit: JAJO
     +1,323.4% / FMAN +423.9% / MJSD +432.5% since 2020, and 2024-26 vs SPY +37.9 / −5.0 / +8.4 pp.
   - The default (un-offset) run of every rule equals its JAJO run
     (`default_matches_offset_series: true`). The engine puts every hold-3 rule on JAJO.

**In one sentence:** a hold-3 lead's number is one draw out of three calendars. Read on the
calendar-neutral book, with a rebalance-blocked t, none of the four clears t >= 2 against its
matched twin in 2024-26.

## Reviewer claims: true, false, unverifiable

| claim (source) | verdict | evidence |
|---|---|---|
| `mom_12_1_q` +37.9 / −5.0 / +8.4 pp; +1,323 / +424 / +433% (review §1) | **TRUE** | reference board controls; reproduced here |
| `disp_short_avoid` rebalances only in months 1/4/7/10 and was never offset-checked (review §1, §5.2) | **TRUE** | `default_equals_offset: jajo`, identical series |
| `QUARTER_OFFSETS` near `strategy_library.py:1323` | **TRUE** | line 1323 |
| the two cells that beat their twins in both windows share one calendar (review) | **TRUE, and more:** on rebalance blocks neither clears t >= 2 in both windows | this receipt, `default` rows |
| `mom_12_1_q` is not one of the two twin survivors (fact check §A) | **TRUE** | dev t 2.1, 2024-26 t 1.7 in the reference twin receipt |
| "39 priced / 7 ahead / 32 behind / −1.31%" is STALE, superseded by `3204eb4d` (fact check #6, roadmap M4, the brief) | **FALSE** | See below this table. |
| roadmap §0 line "33 priced, 6 ahead, 27 behind, −0.27%" | **narrower scope**: it excludes the six broker accounts | as below; not edited (not this lane's file) |
| fleet hack2 −1.18 / hack5 −4.95 / hack1 −8.47 / hack6 −17.70 / hack4 −20.17 (fact check #7) | **TRUE as of 09-25.** Today −1.18 / −4.95 / −8.72 / −17.68 / −20.00; hack3 HTTP 401 | `paper_accounts/roi_2026-09-28T060842Z.json` |
| fundamentals closed at −1.34% per 21 sessions, t −2.55, `3255206b` (review §1, §3) | **TRUE** | See below this table. |
| the rehearsal and core-satellite books tilt on that signal (review §3) | **TRUE for the inputs; the construction is UNVERIFIED** | all five proxy legs are among §60's six ratios; the rank-average proxy itself was never backtested |
| trailing-vol prior "+10.2% vs +5.7%" (review §5.3) | **PARTLY TRUE**: the receipt says **+10.0% vs +5.5%** (+5.7% is the LLM on the prior's own rows), 7 of 8 days | `learning_reports/report_2026-09-27.json` `closing.vol_prior`; 10.2 not found |
| the pitch's "+8.97% vs −27.98%" (TIER 0 §8) | **UNVERIFIED against its named receipt, and on mixed bases** | `specialists/scoreboard_2026-09-24.json` (both committed versions and disk) has no held-out split; +8.97% is recalibrated, −27.98% is raw |
| "the factory has no scheduled caller and no staleness check" (fact check §C) | **TRUE** | it now has a probe; a caller is proposed in M3 |
| 62 books give P(best at 2σ) = 46% (review §4) | **CONSISTENT** | 61 live parents at ρ 0.30 give 46.3% (`trials/lib_forward_trial_2026-09-28T062024Z.json`) |
| "the forward lib books = 18 bets" (review, bridge) | **TRUE for the bridge's 31 rows** | the trial's 30 books are 17 clusters |
| "without best 5 months: `mom_12_1` 14.6% vs SPY 15.3%, below SPY" (review §1, fact check §A) | **comparator mismatch** | 15.3% is SPY with its best months; SPY without its own best 5 is 9.5-9.9%; now printed on every row (M2) |

Detail for the "39 priced" row:

- `3204eb4d`'s `roi_2026-09-27.json` (generated 06:44:32Z) still prints 39 / 7 / 32 / −1.315%.
- The 33 / 6 / 27 / −0.27% file is the 23:51Z `--no-broker` pass, which overwrote the same file
  name. It is a narrower scope, without the six broker accounts.
- The same thing happened on 09-26: `b137fff7` (39 / −1.124%) was overwritten by `b09de800`
  (33 / +0.007%).
- A live broker read today gives 39 / 7 / 32 / **−1.34%** (`roi_2026-09-28T060842Z.json`).

Detail for the fundamentals row:

- `xs_ranker/bakeoff_fundamentals.json`: net −1.336%, `t_across_blocks` −2.555, negative at every
  k from 10 to 500. The commit message matches.
- The commit's own scope is FAILED_VARIANT of a model over six ratios, not a rejected mechanism.

## M2. The leaderboard never shows a big number alone

In `scripts/night_backtest_factory.py`, every table row in `LEADERBOARD.md`, and every row list in
the leaderboard JSON, now carries a **BESIDE THE HEADLINE** column with five fields:

- **matched_twin** — the matched-twin verdict with its t. A hold-N rule gets a warning that its
  monthly t overstates.
- **family** — the family verdict, vs twin and vs SPY.
- **dsr** — DSR, with n and the 0.95 bar.
- **without_best_5** — CAGR without the best 5 months, beside **SPY without its own best 5**.
  That comes from a new `evaluate` field, `spy_cagr_without_best_5_months`.
- **calendar_offsets** — for hold-3 rules, the three calendars' cum since 2020 and the M1 verdict.
  A monthly rule prints `n/a (hold 1 month ...)`.

Rules for the column:

- A field the run did not compute prints **NOT COMPUTED**.
- A verdict taken from another run's receipt carries that run's id.

Where the code lives: `strategy_library.headline_context` and `headline_context_text`, plus the
factory's `headline_sources` and `annotate_headline_context`. It is pinned by
`backend/tests/test_headline_context.py` (10 tests). No existing leaderboard was rewritten.

**Owed:** the README section is rendered by `scripts/bridge_report.py`, which is not this lane's
file. Its README row should call `strategy_library.headline_context_text` the same way.

## M3. Staleness

`backend/services/backtest_staleness.py` provides `p_backtest_leaderboard`:

- It dates the newest `leaderboard_<run id>.json` by the stamp in its NAME, cross-checked against
  the body's `run_id`. It never reads mtime.
- **ALIVE** up to `config.BACKTEST_LEADERBOARD_STALE_DAYS = 7`, **STALE** beyond that.
- **UNKNOWN** when there is no board, the stamp cannot be dated, or the name and body disagree.
- It is registered by one line in `system_health.PROBES` (`backtest_leaderboard`).
- The factory prints the previous board's age at start-up. That is also the module's static
  caller.
- Today it reads **ALIVE, 0.9 d**.
- Tests: `backend/tests/test_backtest_staleness.py` (7): it goes red, it goes green, UNKNOWN, and
  mtime is ignored.

**Proposed scheduled caller (not registered):**

- A weekly Windows task, Sunday 02:00 HKT (after the weekend bars), running
  `python -m scripts.night_backtest_factory --no-freeze`, then
  `python -m scripts.calendar_offset_triplet` (about 2.3 GB peak, 1 minute).
- Gates: `disk_guard` (already in the factory), and >= 8 GB free RAM checked before the load.
- **`--no-freeze` is required**: the factory freezes forward books by default, and the roadmap
  forbids new books until 2026-10-26.
- One heavy job at a time, never overlapping the 06:30 daily pass.

## M4. The record, corrected in documents (the books are untouched)

- **(a) "39 priced", in three documents.** Each now carries a dated correction block, which says:
  - `3204eb4d` did **not** supersede the figure.
  - "39" is the broker-included scope; "33" is the `--no-broker` scope.
  - Today's broker-included receipt reads 39 / 7 / 32 / −1.34%.

  The three documents:
  - `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md`
  - `docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §9
  - `docs/research_notes/2026-09-26/research_value_proposition_and_competitor_ranking.md`
- **(b) `docs/BOOK_2026-09-27_BLOOMBERG_DRESS_REHEARSAL.md`** has two annotations:
  - Book A's proxy paragraph now cites §60 (−1.34%, t −2.55, `3255206b`,
    `bakeoff_fundamentals.json`), its scope, and marks the proxy's own construction UNVERIFIED.
  - Book B's satellite now points to that annotation.
  - Book ids, holdings and `books.jsonl` are unchanged. The core-satellite book lives in this same
    document; no separate core-satellite document exists.
- **(c) TIER 0 §8** now prints the trailing-volatility prior beside +8.97%, from its receipt:
  +10.0% vs +5.5% at h = 1, and +5.9% vs +2.6% at h = 5. It also marks +8.97% UNVERIFIED against
  its named receipt, and says where that was checked.

## M5. The broker legs, in a receipt

Changes to `scripts/paper_accounts_roi.py`:

- **Every row** carries `mark_status` (LIVE / STALE / PENDING / VOID / BROKER_ERROR) and
  `mark_age_days`. A mark older than `config.PAPER_ACCOUNT_MARK_STALE_DAYS = 4` is STALE, and a
  row that was never marked is STALE, not LIVE.
- **A failed broker read** carries `broker_error` by name: HTTP_401, TIMEOUT, NETWORK, HTTP_500,
  NO_CREDENTIAL, or KEY_SHARED_WITH_<role>. It is never $0.
- **A key id shared by two roles** is refused, not read.
- **The receipt** has a `broker_read` block: whether the read was performed, its mode, and every
  error by account. The mode is READ-ONLY: GET `/v2/account` and `/v2/positions`; PC-PAPER goes
  through `pc_broker.snapshot`, whose calls are GETs.
- **Every run** also writes `roi_<run id>.json`, which is never overwritten. That is the fix for
  the 09-26 and 09-27 overwrites.

**A live read ran today** (keys never printed, no order): `roi_2026-09-28T060842Z.json`.

- 39 priced, 7 ahead of SPY, 32 behind, −1.34%.
- 1 BROKER_ERROR: hack3, HTTP 401.
- Mark status: 29 LIVE, 17 STALE (the 10 website lanes at 10 days, and night books never
  marked), 306 PENDING, 1 VOID, 1 BROKER_ERROR.
- `docs/PAPER_ACCOUNTS.md` was NOT re-rendered; the rendered docs went to the scratchpad.

Tests: `backend/tests/test_paper_accounts_broker_read.py` (9). The existing 19 tests are unchanged
and green.

**Owed: one line in `scripts/daily_pass.py` (not changed here).** In the paper-accounts step,
`paper_accounts_roi --no-broker --json` becomes `paper_accounts_roi --json`. Two notes:

- The date-named `roi_<day>.json` is still rewritten by any later run that day; the run-id copy
  is not.
- `roi_2026-09-28.json` (the broker read above) will be replaced by tonight's 22:30Z pass.

## M6. The one forward comparison, pre-registered

- **Documents and code.** The trial is
  `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md`. Its frozen inputs are in
  `backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json`. The code is
  `backend/services/lib_forward_trial.py` and `scripts/lib_forward_trial.py`.
- **Lint.** `lint_prereg` returns PASS as EXPLORE. As CONFIRM it returned
  CONFIRMATION_WINDOW_ABUTS_SELECTION. The doc records that verdict, and that no outcome may be
  written up as independent confirmation.
- **Registration.** Local registry, `rule_experiments` row 17, cumulative 17, idempotent.
- **Counted from disk.** 308 rows, 61 live parents, 245 twins, 1 VOID. **30 lib books in 17
  clusters.** 5 are read against `matched_random` twins and 25 against `random_same_band` twins.
  For the band-only twins, σ is widened to max(matched, unmatched).
- **Primary read.** The pooled-by-cluster (book − twin) at 63 sessions (**2026-12-24**), with an
  interim read at 21 sessions (**2026-10-26**). sd(D) is 2.76% / 4.90%, so the **MDE is 7.7% /
  13.7%**.
- **Kill rule.**
  - EARLY_KILL if z_21 <= −2.
  - SURVIVES if z_63 >= 2 and D_21 > 0.
  - KILL if z_63 < 1: no new lib book, lead, twin or account from the library for 126 sessions,
    and the word "lead" is dropped. The mechanisms are not rejected.
  - Otherwise, extend to 126 sessions under the same rule.
- **Luck.** With zero skill, P(best of K books reads z >= 2) is 32% / 50% / 75% for K = 17 / 30 /
  61 at ρ 0, and 24% / 33% / 46% at ρ 0.30.
- **Timing.** The books enter at the 2026-09-28 open (13:30Z). The registration is only "before
  the first observation" if it is committed before then. Otherwise the doc's own rule moves the
  inception to 2026-09-29.
- **Owed.** One startup line in `backend/main.py` calling `ensure_lib_forward_trial` (the
  `ensure_r2_trial` pattern), and a scheduled caller for the two reads.

## Tests

The command was the brief's gate command plus the three new test files, gated on the exit code.
Result: **742 passed, 1 failed, exit 1.**

The one failure is `test_guard_missing_input_contract.py::test_every_guard_is_enrolled`. It
reports an untracked `backend/services/muratclaw_instance.py` that belongs to another builder's
OpenClaw lane, not to this one. This lane's two cases (`calendar_offsets`, `lib_forward_trial`)
are enrolled and pass.
