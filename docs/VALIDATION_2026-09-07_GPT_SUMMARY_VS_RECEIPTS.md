# VALIDATION PART 1 — the GPT summary of 2026-09-05 → 09-07, checked against the repo's own receipts

Read-only pass. HEAD `d60795f` ("Night lab 2026-09-07 deliverable"), working tree clean apart from one
untracked `backend/data/optimus/iif1_launches/2026-09-08.json`.
Rule applied throughout: **where a build doc and its JSON receipt disagree, the receipt wins**, and the
disagreement is named.

---

## 1. Growth Book champion — VERIFIED (with two corrections)

Receipt: `backend/data/optimus/growth_book/G4_seal.json`.

| GPT | receipt | verdict |
|---|---|---|
| champion = quality + momentum + drawdown control | `champion_genome_id = "m12_quality_mom\|dd"`, `champion_genome.spec = {pred_col: quality_mom, weight: vw, k: 110, hold_k: 160, dd_lookback_months: 7, dd_scale: 0.3, dd_floor: 0.05, bsc_lookback_months: 24, bsc_cap: 1.8}` | VERIFIED, **incomplete** |
| 3.67× on 2016-2024 vs SPY ~3.67× | `sealed.25bps.book.terminal_wealth = 3.6684`, `sealed.25bps.spy.terminal_wealth = 3.6707` | VERIFIED |
| beta ~0.67 | `sealed.25bps.beta = 0.6681` (10 bps: 0.6711) | VERIFIED |
| DSR and PBO fail after multiplicity | `dsr_over_family_on_the_sealed_excess.dsr = 0.0046`, `n_trials = 128`; `family_pbo = 0.6429`, `family_pbo_verdict = "SELECTION_IS_OVERFIT"`; `amendment_gate_5.ALL_MET = false`, `failed = ["dsr_over_family_gt_0_95", "family_pbo_below_0_5"]` | VERIFIED |

Exact numbers asked for: **DSR 0.0046 · PBO 0.6429 · family size 128 cells** (arm Sharpe 0.0011 against
a zero-edge benchmark Sharpe of 0.2541 over 107 periods, z −2.6037).

Two corrections to GPT's phrasing:

1. **"quality+momentum+drawdown control" omits a second overlay.** The genome also carries `bsc`
   (a trailing-vol / beta-scaling cap, `bsc_cap 1.8`). The build doc's own claim 9 concedes this:
   "the null is the champion, whose `bsc` overlay *already* targets volatility." Naming only `dd`
   makes G5's "flat 1× wins" look like a cleaner comparison than it is.
2. **"3.67× vs SPY ~3.67×" hides the sign.** The book is *below* SPY unlevered (3.6684 < 3.6707) and
   further below on the leverage-neutral column (3.6044, `beats_spy: false`). The only sense in which
   it wins is at the equal drawdown budget: 4.6616 (book at 1.3027×) vs 4.4823 (SPY at 1.2471×).

---

## 2. Monthly retraining — VERIFIED BUT CONFLATED (two different baselines)

GPT welds two different experiments into one sentence. Both halves are individually true; the join is not.

**+5.751pp is monthly minus FROZEN-ONCE** — `labor_day_lab_2026-09-07/A2_retrain_cadence_run01.json`,
`headline`: "10bps: TW by cadence {monthly: 27.17, quarterly: 6.0121, annual: 22.6076, frozen_once:
6.7658}, monthly-minus-frozen **5.751pp** beta-matched | 25bps: … **5.388pp**". Family 8,
`family_min_p_one_sided 0.05703`, best Holm `monthly|10bps = 0.45624`, 0 of 8 survive.

**12 of 12 is monthly minus ANNUAL** — `night_lab_2026-09-07/N1d_monthly_refit_books.json`:
`family.constructions_where_monthly_wins = 12 / 12`, `median_pp_per_year = 1.204`,
`family_min_p = 0.109793`, `best_holm_adjusted_p = 1.0`. The receipt carries an `A2_comparison` block
warning against exactly GPT's join:

> "A2's +5.751pp is monthly MINUS FROZEN. The number below is monthly MINUS ANNUAL, which is the
> decision actually on the table: nobody proposes freezing a model for twenty years. **The two are not
> the same quantity and must not be quoted as if they were.**"

**The gain vs TC, all 12 cells** (`monthly_minus_annual`, pp/yr) — the shrink is monotone in k:

| construction | 10 bps | 25 bps | TC |
|---|---|---|---|
| k=50 vw hold=none | **2.658** | 2.630 | 0.1604 |
| k=50 ew hold=100 | 1.913 | 1.822 | 0.3306 |
| k=100 rank hold=200 | 1.349 | 1.283 | 0.3705 |
| k=100 ew hold=200 | 1.124 | 1.045 | 0.4195 |
| k=300 ew hold=600 | 0.548 | 0.530 | 0.5602 |
| k=300 rank hold=600 | **0.363** | 0.353 | 0.4832 |

2.658 → 0.363 is the doc's "sevenfold fall" (7.32×). VERIFIED.

---

## 3. Hysteresis — VERIFIED (one qualifier)

Receipt: `labor_day_lab_2026-09-07/A4_holding_cross_run01.json`.

- **19 of 20 rungs beat control** — `horizon_answer.hold_band_ladder_robustness`: lgbm_clf|10bps 4/5,
  lgbm_clf|25bps 5/5, nn_pre_causal|10bps 5/5, nn_pre_causal|25bps 5/5 = **19/20**.
- **Best cell** `holdband|nn_pre_causal|hold_k=150|10bps`: **+8.139%/yr, t 2.393**, 251 months.
- **MDE** `mde_annual_excess_at_t_target = 0.06802` (6.80%/yr) ⇒ `scope_aware_verdict = "SEPARATED FROM ZERO"`.
- **Family 40**, `family_min_p 0.00836`, `family_max_p 0.7794`, **0 survive Holm**; the best cell's own
  Holm-adjusted p is **0.3344**. PBO 0.2571 (`SELECTION_IS_FRAGILE`), DSR 0.5771.

Qualifier: "hold until rank ~150 best" is true for `nn_pre_causal` only. For `lgbm_clf` the best rung is
`hold_k=400` at both cost rates (+4.898%/yr t 1.89 at 10 bps). 150 is the argmax of the *family*, not of
the ladder.

---

## 4. Sizers — VERIFIED exactly

Receipt: `backend/data/optimus/growth_book/G5_sizer.json`, `table`; development 1999-03..2015-12,
202 months, 25 bps, at the equal drawdown budget:

| arm | beta | TW at budget | leverage | DSR over the 11-cell sizer family |
|---|---|---|---|---|
| `constant_1x_NULL` | 0.7224 | **5.6264** | 1.332× | 0.4206 |
| `trailing_vol_MOREIRA_MUIR` | 0.8970 | **3.7599** | 0.9922× | 0.3380 |
| `nn_seedmean_kelly` | 0.6035 | **1.0546** | 1.1416× | 0.0073 |

Ordering NN < Moreira-Muir < flat 1× VERIFIED. **8 seeds** (20260907…20260914);
`seed_spread_tw_at_budget = {min 0.7275, median 1.5789, max 5.7383, seed_mean_object 1.0546}` — an
eight-fold range, and the seed-mean sits below the median seed. Note the Moreira-Muir arm has
`constraints_pass: false` (`maxdd_unlevered −0.60272`), so it is not merely worse, it is inadmissible.

---

## 5. Fault injection + connection probes — VERIFIED

`aegis-alpha-terminal/state/labor_day_lab_2026-09-07/C1_fault_injection.json`: `table` has **14 rows**,
`checks_run 53`, `checks_failed 0`. Verdict split: **12 rows read exactly `PASS`**, one
`FAIL (REPORTED, NOT FIXED)` (clock skew ±20 min), one `PASS (with a REPORTED gap)` (refusal typing — no
`VENUE_REJECTED` state). "12 of 14 pass" is right on the strict reading. **Five rows carry a `FIXED:`
string** this session: stop `client_order_id` day salt · `sealed_holdings` `content_sha256` verification
· `sealed_holdings` contract exposure + `runner.contract_for` · `exits._evaluate_shares` torn-ledger
refusal · `protect.stopped_today_or_suspects` re-entry-guard fallback.

Doc nit: `BUILD_LABOR_DAY_LAB_2026-09-07.md` names the five as "stop-id day salt, seal hash
verification, sealed contract read, torn-ledger refusal, **exit-failure stop re-place**". The receipt
marks exit-failure as `none needed (fixed 2026-09-05)` — a *previous* session's fix — and the fifth new
one is the re-entry guard. Count 5 is right; the list is off by one item.

`labor_day_lab_2026-09-07/D1_connection_check_finance.json`: `counts = {ok: 16, fail: 4,
cannot_determine: 1, total: 21}` — VERIFIED. Every failure carries a class:
`failure_classes = {absent: [Featherless], auth: [Alpaca (finance mirror/arena)], cannot_determine:
[NVIDIA NIM], network: [WRDS], quota: [GDELT]}`.

---

## 6. Fantasy exams — "about four cents" is WRONG by roughly a factor of ten

Round 1 (`aegis-alpha-terminal/state/labor_day_lab_2026-09-07/B2_fantasy_exams.json`, `summary`):
`pairs_graded 40`, `monotonicity_share_p_up 1.0` (also 1.0 on exp_return and downside),
**`mean_abs_move_p_up = 0.3695`**, `mean_abs_move_exp_return 0.1144`, `canaries_graded 8`,
**`canary_rate = 0.125`**, `canary_tolerance 0.05`.

Round 2 (`night_lab_2026-09-07/N6b_fantasy_exams_round2.json`): END arm 40/40 monotone,
`mean_abs_move_p_up 0.301`, `canary_rate 0.0`; FRONT arm 15 pairs, `mean_abs_move_p_up 0.2913`,
`canary_rate 0.125`. `position_control.real_pairs`: end 0.3053 vs front 0.2913,
`mean_end_minus_front_abs_move = 0.014` ⇒ `POSITION-INSENSITIVE`.

**The real mean effect is 0.370 (round 1) / 0.301 (round 2) of probability — 37 and 30 percentage
points, not four.** No receipt anywhere reports ~0.04 as a mean effect. The only 0.02–0.05-scale numbers
in this lane are *bars and controls*, never the effect: `canary_tolerance = 0.05`, the position-control
gap `0.014` against a `0.02` bar, and the canary arm's own `mean_abs_move_front = 0.0213`. "About four
cents" is most likely a decimal slip on 0.370, or one of those bars mistaken for the effect. **WRONG.**

Doc nit: `BUILD_NIGHT_LAB_2026-09-07.md` reports round 2's canary as "**0/8**". That is the END arm only;
the FRONT arm's `canary_rate` is 0.125 (1 of 8) in the same receipt.

---

## 7. `evaluate.ERAS` — HALF FIXED. `verdict_from` — NOT FIXED

The learner lives at repo root `learner/`, not `backend/learner/`.

**ERAS**: `learner/evaluate.py:64` still reads
`ERAS = {"2016-2018": (2016,2018), "2019-2021": (2019,2021), "2022-2024": (2022,2024)}` — the constant
**did not move, deliberately**, so sealed receipts reproduce byte for byte. What *was* fixed is the
silence: `era_coverage()` (line 758) + `ERA_COVERAGE_FLOOR = 0.01` + `long_eras()` (line 740, derived
from `learner/long_panel.py:96 ERAS`), and `grade_by_era()` (line 810) now returns
`REFUSED: N of M rows fall outside every era…` instead of buckets, and raises at 100% outside.
Commit `a2e0ea2` ("G-pre: grade_by_era DERIVES its era grid or REFUSES"). G4 uses it:
`development_era_signs._grid_source = "learner.evaluate.long_eras() … NOT evaluate.ERAS, which is
2016-2024 and would describe only the sealed era"`.
**Still open** (named in the growth doc's "queued, not done"): `learner_run.py:236` and
`learner_v2_run.py:345` pass no `eras=`, so a long-panel run there now *refuses* rather than silently
reporting nine years.

**`verdict_from`**: `scripts/weekend_lab_jobs.py:225`. Its ladder is still
`NOVEL` → `DECAYED (worked, then stopped)` → `CANNOT DETERMINE (underpowered; …)` → `NOISE`.
**There is no new category** between NOVEL and NOISE, and `git log -- scripts/weekend_lab_jobs.py` shows
no commit touching it since `e22c74b` (which pre-dates the Labor Day lab). Both build docs list "a
verdict word between NOVEL and NOISE (B1)" under *queued, not done*. NOT FIXED.

---

## 8. Test counts — 7,142 is current on HEAD; 6,942 exists nowhere

Every fast-suite count recorded in `docs/` since 2026-09-05, in commit order:

| # | doc | commit (date) | count |
|---|---|---|---|
| 1 | `BUILD_B1_2026-09-05.md:42` | `5ecc614` 09-05 | 6377 passed, 17 skipped, 118 deselected |
| 2 | `BUILD_WEEKEND_LAB_2026-09-06.md:1089` | `023db13` 09-05 | 6,545 passed, 17 skipped |
| 3 | `BUILD_CONTINUATION_2026-09-06.md:23` | `7dd604a` 09-05 | 6655 passed, 14 skipped, 119 deselected |
| 4 | `BUILD_CONTINUATION_2026-09-06b.md:22` | `9dbccc0` 09-05 | 6766 passed, 14 skipped, 122 deselected |
| 5 | `BUILD_LABOR_DAY_LAB_2026-09-07.md:112` | `c75260a` 09-06 | 6869 passed, 14 skipped, 122 deselected, 487.04 s |
| 6 | `BUILD_GROWTH_BOOK_2026-09-07.md:179` | `fd6ed36` 09-06 | 6,984 passed, 14 skipped, 122 deselected, 541.58 s |
| 7 | `BUILD_NIGHT_LAB_2026-09-07.md:176` | `d60795f` 09-07 (**HEAD**) | **7142 passed, 17 skipped, 123 deselected, 460.68 s, exit 0** |

(5) and (6) are mirrored at `ROADMAP_2026-09-04_PROFIT_ENGINE.md:410-411`.

**7,142 is current on HEAD `d60795f`.** The 122→123 deselected step is explained inside the growth-book
doc ("a `slow`-marked test added after the suite run … so the next fast run will read 123 deselected").

**6,942 is recorded nowhere** — not in `docs/`, not in `scripts/`, not in `backend/tests/`. It is not a
stale reading of an earlier run either: it falls between 6,869 and 6,984 and matches neither.

Also worth knowing: the night lab doc records a **transient 7141/1-failed** on one full-suite pass,
diagnosed as `job_receipts.write()` naming the file from write time while
`test_receipts_come_back_newest_first` asserts on `started_at` at one-second resolution. It passes alone
and on the clean re-run; the filename fix is queued.

---

## 9. The revision family — VERIFIED, but GPT (and the doc's own table) mislabel the 29.27× row

Receipt: `night_lab_2026-09-07/N1_construction_books.json`. **The 29.266 row is EW at 10 bps, not rank at
25 bps.** Every relevant cell:

| cell key | TW net | beta | TC | eff. names | beta-matched |
|---|---|---|---|---|---|
| `revisions\|k=50\|vw\|hold=none\|25bps` (the control) | **3.6586** | 0.882 | 0.132 | 12.165 | −3.494%/yr t −1.54 |
| `revisions\|k=50\|vw\|hold=none\|10bps` | 8.960 | 0.8823 | 0.132 | 12.165 | −0.004%/yr t −0.002 |
| **`revisions\|k=300\|ew\|hold=600\|10bps`** | **29.266** | 1.0861 | 0.5869 | 299.4 | +2.964%/yr t 1.785 |
| `revisions\|k=300\|ew\|hold=600\|25bps` | 18.138 | 1.0855 | 0.5869 | 299.4 | +1.096%/yr t 0.659 |
| `revisions\|k=300\|rank\|hold=600\|10bps` | 29.166 | 1.0725 | 0.4865 | 224.9 | +3.115%/yr t 1.725 |
| **`revisions\|k=300\|rank\|hold=600\|25bps`** (the headline delta's broad leg) | **17.755** | 1.0719 | 0.4865 | 224.9 | +1.177%/yr t 0.651 |

`terminal_wealth_market_same_months = 13.1817` on all of them ⇒ **market 13.18× VERIFIED**;
**top-50 VW 3.66× VERIFIED** (it is the 25-bps control).

The **+4.670pp headline** is `transfer_coefficient_cost["revisions|k=300|rank|hold=600|25bps MINUS
revisions|k=50|vw|hold=none|25bps"]`: `annualised_pp 4.67`, `t_paired 2.584`, `p_one_sided 0.004884`,
TC 0.132 → 0.4865, eff names 12.165 → 224.918, 309 paired months, era deltas +0.5078 / +0.2253 / +0.4187
%/mo, all three positive. `transfer_coefficient_cost_family`: `size 100`,
`comparisons_with_a_POSITIVE_delta = 15`, `median_delta_pp_per_year = −2.853`,
`best_comparison_holm_adjusted_p = **0.4884**`, `comparisons_surviving_holm_at_0.05 = []`.
**15/100 and Holm 0.4884 VERIFIED.**

**Which is it — the doc's table or the doc's prose?** Both, describing different objects, and that is the
problem. `BUILD_NIGHT_LAB_2026-09-07.md` opens with a prose sentence about
`revisions|k=300|rank|hold=600|**25bps**` (+4.670pp, TC → 0.4865, eff → 224.9) and then prints a table
whose second row is labelled `top-300 EW hold-600, **10 bps**` (TW 29.27, TC 0.587, eff 299.4). Each
row's numbers are exactly right for its own label. But:

- **The table's two rows are at different cost rates** — a 25-bps top-50 VW control (3.66×) against a
  10-bps top-300 EW book (29.27×). Under one cost rate the pair is 3.66 → 18.14 (25 bps) or
  8.96 → 29.27 (10 bps). The 3.66 → 29.27 line, read as "one column, two constructions", is **8.0× of
  terminal wealth of which a good part is the 15-bps cost difference**.
- GPT calls 29.27 "top-300 rank-weighted + hysteresis". That construction is 29.166 at 10 bps and
  **17.755** at 25 bps. 29.266 belongs to the **EW** cell.

Level family: `family.size = 160`, `family_min_p 0.004947`, best cell
`ensemble_ew|k=50|vw|hold=none|10bps`, `best_cell_holm_adjusted_p **0.79152**`, 0 survive; DSR 0.4513,
verdict `NOISE`. All VERIFIED.

---

## 10. Transfer coefficient 0.11–0.20 → 0.28–0.64 — VERIFIED

Computed directly over the 120 cells of `N1_construction_books.json`: the 20
`k=50|vw|hold=none` control cells span TC **0.1063 … 0.1993**; the 100 broad cells span
**0.2828 … 0.6366**. Rounds to exactly the claimed 0.11–0.20 → 0.28–0.64. Effective names on the same
split: control 12.165 at the low end (the doc's "7–19" is over all selectors), broad up to 300.

---

## 11. Ensemble — VERIFIED

`night_lab_2026-09-07/N2_ensemble.json` plus the `ensemble_ew|k=100|ew|hold=200|10bps` cell in N1:

- beta **1.1951**, beta-matched **+5.651%/yr, t_paired 2.424**, 309 months, TW **62.8693** vs market 13.1817.
- Era table on the beta-matched excess: 1999-2007 **+1.1847%/mo t 2.988** · 2008-2015 +0.0086%/mo t 0.026
  · 2016-2024 +0.1785%/mo t 0.697. "Mostly 1999-2007" VERIFIED.
- `full_ensemble_subperiod`: **107 months, +2.142%/yr, t 0.697**, p 0.24282. VERIFIED. One caveat — the
  receipt's `rule` is "**>= 6 arms** present in the month (or one short of the maximum)", so both GPT and
  the doc's "genuinely an eight-arm ensemble" over-tighten the filter's wording.
- `comparisons.reliability_minus_equal_weight`: **−1.041pp/yr, t_paired −0.907**. VERIFIED.
- EW inference: DSR **0.9687** (`CLEARS_DEFLATED_SHARPE`), MDE `0.04663` (4.66%/yr), `powered False`,
  family = 2 (both weightings reported). Reliability arm: DSR 0.9179, MDE 4.82%/yr.

---

## 12. The floor curve — VERIFIED, with one wording correction

`night_lab_2026-09-07/N3_edge_vs_floor_curve.json`, beta-matched on measured TAQ cost, 251 months:

| book | floor @1% ADV | TAQ band | beta-matched %/yr | t |
|---|---|---|---|---|
| institutional_flat_3m | $3.0m | 1m–5m | +2.795 | 1.019 |
| **book_100000** | **$500k** | 100k–1m | **−9.629** | **−3.279** |
| book_1000000 | $5.0m | 5m–10m | +3.397 | 1.369 |
| book_10000000 | $50m | 50m+ | +4.245 | 2.176 |

Family 12, `family_max_p_one_sided 0.99948`, `n_cells_surviving_holm_at_0_05 = 0`; best Holm
`book_10000000|measured_taq = 0.17736`. Direction at $1m and $10m VERIFIED — the curve improves
monotonically with book size, the opposite of the small-book thesis.

Correction: **−9.629%/yr is a level, not a delta.** It is the $100k book's own beta-matched excess.
"Hurt by ~9.6pp" reads as a difference; the difference against the institutional cell is −12.4pp.

---

## 13. The event table — 993,005 rows VERIFIED, but the date range is WRONG

`backend/data/optimus/events/event_table_v1_manifest.json`, built 2026-09-06T17:11:53Z:

- `rows = 993005` ✔ · `distinct_symbols 31626` · `permno_link_share 0.2214`.
- `by_source`: `ibes_surpsumu **618419**` ✔ · `edgar_8k **276978**` ✔ · `sec_ownership **2380**` ✔ ·
  news = `alpaca:benzinga 80631` + nine finnhub outlets (14,537) + six `company_ir` feeds (60)
  = **95,228** ✔.
- `known_absences`: "Form 4 (insider transactions): no table entitled or on disk anywhere in either repo"
  ✔; 13D/G "present but thin — 7 days (2026-08-13..2026-08-20) from a smoke test".
- Coverage `N4_coverage_by_year.json`: `share_of_universe_proxy_covered` runs **0.8075 (2021) … 0.8631
  (2018)** ⇒ **81–86% VERIFIED**.

**WRONG: "2015-2024".** The manifest's `year_range_present` is **[2015, 2026]**, and the by-year table
carries 2025 (107,986 rows) and 2026 (95,742 rows). Summing the receipt's own year buckets:
**789,277 rows fall in 2015-2024; 993,005 is the whole 2015-2026 table.** The 81–86% coverage figure is a
2015-2024 statistic (2025 and 2026 have `share_of_universe_proxy_covered: null`). GPT inherited this
conflation from `BUILD_NIGHT_LAB_2026-09-07.md` and `ROADMAP_2026-09-04_PROFIT_ENGINE.md:422`, which both
say "993,005 rows, 2015-2024".

---

## 14. Event compression — the DOC IS WRONG, and GPT IS RIGHT about the embedder

**The compression numbers.** `night_lab_2026-09-07/N5_event_compression.json` (snapshot
2026-09-06T17:32:37Z, byte-identical at HEAD and at its own commit `625f5ac`):

```
compression.raw_news_rows      = 137190
compression.n_canonical_events = 105494
compression.compression_ratio  = 1.3005
corpus_snapshot.news_rows_read = 137190   files_read 87   distinct_symbols 156
```

The build doc, the roadmap §6 row **and the commit message** all say **127,157 → 97,949, ratio 1.298**.
Under "prefer the receipt": the correct figures are **137,190 raw news rows → 105,494 canonical events,
ratio 1.3005**. The doc's numbers look like an earlier pass of a corpus that was still being pulled;
nothing in the repo now reproduces 127,157. GPT's "127k → 98k" repeats the stale pair.

**The embedder.** The same receipt's `nemotron_probe`:
`{"status": "OK", "latency_ms": 935.9, "n_embeddings": 3, "dim": 2048, "model":
"nvidia/nemotron-3-embed-1b", "batch_requested": 3}` — three real 2048-dim embeddings came back.
**GPT is right: NVIDIA embeddings are available.** The "ABSENT" statement is confined to
`ROADMAP_2026-09-04_PROFIT_ENGINE.md:423` ("NVIDIA embedder ABSENT — no key in this repo") and is
**contradicted by the receipt it cites**. `BUILD_NIGHT_LAB_2026-09-07.md:113` agrees with GPT ("NVIDIA
NIM re-probed **OK in 935 ms** … transient network, not a dead key"). The roadmap row is stale, carried
over from the 09-05 receipt's `CANNOT_DETERMINE at 30.2 s` (confirmed in
`D1_connection_check_finance.json`: `cannot_determine`, `latency_ms 30238.9`).
Caveat that matters: the compression **itself** was TF-IDF, not embeddings — the embedder being live does
not mean it was used.

---

## 15. Known-answer battery — VERIFIED

`night_lab_2026-09-07/N6_battery_v2.json`, `adjudication`: `n_pass 5 / n_worlds 5`, `ALL_PASS true`.
Best t per world: linear 9.914 · regime 7.479 · graph 10.473 · **event 33.006** · null 1.577
(`recovered_at_t2 false`, `PASS (null reads NOISE)`).

The breadth statement, `results.event.cells`:

| selector | control_top10pct_vw t | broad_top40pct_ew_hysteresis t |
|---|---|---|
| lgbm_clf | **33.006** | **14.215** |
| lgbm | 33.006 | 14.705 |
| ENSEMBLE | 32.272 | 14.241 |
| ridge | 23.804 | 13.636 |

"control t 33.0 vs broad t 14.2" VERIFIED (the lgbm_clf pair). Sensitivity ladder:
`smallest_multiple_recovered = 0.5` — 1.0× t 5.203 (IC 0.068), 0.5× t 2.023 (IC 0.019),
0.25× t 0.802, 0.125× t −0.283.

---

## 16. Market-neutral long-short — VERIFIED

`N1_construction_books.json["index_hedged_long_short"]`, 20 cells: **19 negative, 1 positive**. The single
positive is `ensemble_ew|10bps` at **+0.346%/yr over cash, t 0.178**. All ten 25-bps cells are negative.

Doc discrepancy worth carrying: the build doc says "the index-hedged long-short hedges correctly
(**realised β 0.00–0.05**)". True for 16 of 20 cells, **false for four**: `ridge|10bps 0.2047`,
`ridge|25bps 0.2056`, `encoder|10bps **0.4254**`, `encoder|25bps 0.4238` (the two 47-month arms); and
`momentum` sits at −0.060. The actual range is **−0.0605 … 0.4254**.

For completeness, the survivor shape the doc pairs with it — `exclusion_books["ensemble_ew|10bps"]`:
`annualised_vs_ew_universe_pp 0.861`, `t 2.487`, TW **18.7176 vs 14.4104**; at 25 bps 0.482 / t 1.382 /
16.9907. VERIFIED exactly.

---

## 17. hack4 at 1× vs the champion's contract row — VERIFIED, and the PROXY/contract split is real

- **The PROXY** is `night_lab_2026-09-07/N6b_path_monte_carlo.json`: parent genome, development-only,
  202 months, 25 bps, block 6.0 months, 4,000 draws → at 1.0× **P(lose half) 0.442**, median worst DD
  **−0.48152** (−$48,152 on $100k), **p95 −0.72764**, worst −0.909; 1.3× → 0.765; 3-year horizon at 1.0×
  → 0.036. It is a proxy because it lacks the champion's vol overlay — the receipt says so in its own
  `headline` and `basis` fields.
- **The contract's row** is `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md:102`:
  `| **1.0×** | −46.88% | −$46,882 | −29.66% | −$29,663 | **0.232** | −41.5% |`. The −46.88% is
  `G5_sizer.json`'s `constant_1x_NULL.maxdd_unlevered = −0.46882` (development window, 1999-2015). The MC
  receipt's `basis` note flags that the contract's caption says "1999-2024" while the number is the
  202-month development window — "the caption is imprecise, the underlying window is the same".
- G4's own sealed `p_ruin` is a third, different number: **0.212** at 25 bps (0.1985 at 10 bps), computed
  on the largest admissible book at L=1.3027 over 107 sealed months.

Both build docs say the right thing — "**compare, do not average**". VERIFIED.

---

## 18. Unsupervised states — VERIFIED exactly

`night_lab_2026-09-07/N5_states_third_null.json`, `state_col state_k4`, target `excess_vw_1m`,
371,848 merged rows / 5,358 permnos / 120 months (368,613 rows graded in null 3, 5,346 names):

- `null_1_within_month_legacy.p_value_one_sided = 0.0`
- `null_2_persistent_circular_shift.p_value_one_sided = **1.0**` (observed 0.01391 below every draw; null
  mean 0.021964)
- `null_3_name_path_permutation.p_one_sided = **0.005**`, `CLEARS_MODEL_NULL`, 200 usable draws
- `final_verdict.verdict = **"CANNOT_DETERMINE"**`, `family_case "NULL_2_ALONE_DISAGREES"`
- `demotion.instruction`: the four states "are to be DEMOTED everywhere they are currently used as a live
  input — i.e. treated as unvalidated / **informational-only**, never as a sizing, admission, or routing
  input"

Secondary target `excess_vw_3m` gives the same three p-values (0.0 / 1.0 / 0.005). VERIFIED.

---

## 19. Stale lane NAVs — the finding is VERIFIED, the quoted loadings are WRONG, and NOTHING IS FIXED

`backend/data/optimus/growth_book/G7_forward_lanes.json`:

- `stale_mark_finding.lanes_flagged = ["balanced-ew-control", "mirror", "conviction"]`, `n_flagged 3`,
  `threshold 0.2`; "a stale mark **HIDES** beta, which is the one thing the amendment §2.2 forbids".
  VERIFIED.
- **The numbers do not match the doc.** The `conviction` row's `stale_mark_diagnostic`:
  `beta_contemporaneous_joint **0.6072**`, `beta_on_lagged_market_joint **1.3990**`,
  `beta_on_lagged_market_univariate 1.4259`, `beta_on_lead_market_joint −0.0748`, `beta_dimson 1.9313`,
  n 39. The doc's prose (`BUILD_GROWTH_BOOK_2026-09-07.md:91`, echoed at `ROADMAP…:411`) says "**0.66** on
  today's market and **1.50** on yesterday's". Neither figure appears in the receipt or in
  `G7_forward_lanes.md`. The doc's *table* row for conviction is correct (beta 0.7163, Dimson 1.9313,
  R² 0.05, n 41, raw exc −7.680pp, LN exc −3.566pp, maxDD −21.28% vs SPY −3.38%).
- **No fix.** `git log --since=2026-09-06 -- backend/services backend/routers` returns exactly one commit,
  `9262140`, the Linux-CI repair (CRLF hashes, Windows paths, degenerate OLS), which has nothing to do
  with marks. The growth doc lists "repricing the lane NAVs at the official close, which G7 says every
  forward beta depends on" under **queued, not done**, and the receipt's `how_to_settle_it` says the
  same. **STILL OPEN.**

---

## 20. GPT's "still open" list — VERIFIED on the finance side

| item | status in the repo |
|---|---|
| **clock skew** | OPEN. `C1_fault_injection.json` row 8: `FAIL (REPORTED, NOT FIXED)` — "every ET gate reads the local clock". Listed under "queued, not done" in both `BUILD_LABOR_DAY_LAB_2026-09-07.md` and `BUILD_NIGHT_LAB_2026-09-07.md`. (Terminal-repo code; verified from the receipt only.) |
| **stale NAV** | OPEN. See §19 — no commit in `backend/services` or `backend/routers` since 2026-09-06 other than the CI fix; queued in the growth doc. **Finance-side, confirmed here.** |
| **min-hold-0 on three books** | Terminal-repo (`hack1/2/5` `min_normal_hold_sessions = 0`, C2 receipt). Outside this repo's scope; nothing here contradicts it. |
| **hack4 decision** | OPEN. Nothing in this repo enables it: `N6b_path_monte_carlo.json` is a diagnostic; `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md` is explicitly a draft ("NOTHING ENABLED", "Recommendation: rung 1× or decline"); the growth doc keeps "the sizer's sealed-era test (deliberately: the champion's contract is not frozen by Murat yet)" in its queued list. |

Two more finance-side items GPT's list omits, both queued in the repo's own docs and both cheap: the
`job_receipts` filename fix (source of the transient 7141/1-failed), and `learner_run.py:236` /
`learner_v2_run.py:345`, which now **refuse** on a long panel because they pass no `eras=`.

---

# VERDICT TABLE

| # | claim | verdict |
|---|---|---|
| 1 | Growth Book champion, 3.67× vs SPY, β 0.67, DSR/PBO fail | **VERIFIED** — DSR 0.0046, PBO 0.6429, family 128. Two nits: the genome also carries a `bsc` vol overlay; the book is *below* SPY unlevered (3.6684 < 3.6707) |
| 2 | monthly refit +5.75pp; 12/12; shrinks with breadth | **VERIFIED BUT CONFLATED** — +5.751pp is vs frozen-once (A2); 12/12 is vs annual (N1d, median +1.204pp, Holm 1.0). The receipt explicitly forbids quoting them as one quantity |
| 3 | hysteresis, hold ~150, 19/20, nothing survives Holm | **VERIFIED** — +8.139%/yr t 2.393, MDE 6.802%, family 40, best Holm 0.3344, 0 survive. "150" is nn_pre_causal's optimum; lgbm_clf's is 400 |
| 4 | NN < trailing-vol < flat 1× | **VERIFIED** — 1.0546 / 3.7599 / 5.6264 at budget; 8 seeds spanning 0.7275–5.7383; DSR 0.0073 / 0.3380 / 0.4206 |
| 5 | 12 of 14 faults pass, five fixed; 16/4/1 of 21 | **VERIFIED** — C1: 12 plain PASS, 1 FAIL, 1 PASS-with-gap, 53 checks, 5 rows FIXED. D1 finance counts exact |
| 6 | 40/40 monotone; "about four cents" | **WRONG** — real mean \|Δp_up\| **0.3695** (round 1) / 0.301 (round 2); canary 0.125. Nothing reports ~0.04 as an effect; 0.05 and 0.02 are *bars* |
| 7 | `evaluate.ERAS` fixed? `verdict_from` fixed? | **HALF / NO** — ERAS constant unchanged by design at `learner/evaluate.py:64`, but `era_coverage` + `long_eras` + `grade_by_era` now derive-or-refuse (`a2e0ea2`). `verdict_from` (`scripts/weekend_lab_jobs.py:225`) still has only NOVEL / DECAYED / CANNOT DETERMINE / NOISE — untouched, still queued |
| 8 | "6,942 passed" and "7,142 tests passed" | **7,142 VERIFIED** on HEAD `d60795f` (17 skipped, 123 deselected, 460.68 s). **6,942 appears nowhere in the repo** |
| 9 | 3.66× / 29.27× / 13.18×; 15/100; Holm 0.4884 | **VERIFIED with a mislabel** — 29.266 is `k=300\|ew\|hold=600\|10bps`; the +4.670pp headline's broad leg is `k=300\|rank\|hold=600\|25bps` at TW **17.755**. The doc's table also mixes cost rates (25-bps control vs 10-bps broad) |
| 10 | TC 0.11–0.20 → 0.28–0.64 | **VERIFIED** — measured 0.1063–0.1993 vs 0.2828–0.6366 |
| 11 | ensemble +5.65%/yr t 2.4 β 1.2; 8-arm months +2.1 t 0.7; reliability −1.04 | **VERIFIED** — 5.651 / 2.424 / 1.1951; 107 months +2.142 t 0.697; −1.041pp t −0.907. Filter is ">= 6 arms", not strictly eight |
| 12 | $100k floor hurts ~9.6pp; direction at $1m/$10m | **VERIFIED (wording)** — −9.629%/yr is a *level*, not a delta (delta vs institutional is −12.4pp). +3.397 / +4.245 confirmed |
| 13 | ~993k rows 2015-2024, 81-86%, 618k/277k/95k/2.4k, no Form 4 | **PARTLY WRONG** — every source count and the coverage band verify, but `year_range_present` is **2015-2026**; only **789,277** rows are 2015-2024 |
| 14 | 127k → 98k; NVIDIA embeddings available vs "ABSENT" | **GPT RIGHT on the embedder, WRONG on the counts** — receipt says **137,190 → 105,494, ratio 1.3005**; `nemotron_probe` = OK, 3 embeddings, dim 2048. The roadmap's "embedder ABSENT" is stale and wrong |
| 15 | battery 5/5; control t 33.0 vs broad t 14.2 | **VERIFIED** — ALL_PASS; 33.006 vs 14.215 in the event world |
| 16 | long-short lost 19/20 | **VERIFIED** — 19 negative, 1 positive (+0.346%/yr t 0.178). Doc's "realised β 0.00–0.05" is false for 4 cells (up to 0.4254) |
| 17 | 44% / −73% proxy vs 0.232 / −46.88% contract | **VERIFIED** — proxy = `N6b_path_monte_carlo.json` (0.442, p95 −0.72764); contract = `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md:102`. G4's own sealed p_ruin is a third number, 0.212 |
| 18 | states demoted; nulls 0.005 / 1.000; CANNOT_DETERMINE | **VERIFIED** exactly |
| 19 | stale NAV hides beta; conviction 0.66 / 1.50; any fix? | **FINDING VERIFIED, NUMBERS WRONG, NO FIX** — receipt says 0.6072 today / 1.399 yesterday (Dimson 1.9313). Only commit in services/routers since 09-06 is the CI repair `9262140` |
| 20 | still open: clock skew, stale NAV, min-hold-0, hack4 | **VERIFIED** on the finance side; the two terminal items are consistent with the C1/C2 receipts |

---

# EVERY NUMBER GPT GOT WRONG OR CONFLATED

1. **"about four cents"** (§6). Real mean |Δp_up| is **0.3695** (round 1) / **0.301** (round 2) — off by
   roughly a factor of ten. The 0.04-scale numbers in that lane are bars (canary tolerance 0.05, position
   bar 0.02), never the effect.
2. **"6,942 passed"** (§8). Recorded nowhere in the repo. The real ladder is
   6377 → 6545 → 6655 → 6766 → 6869 → 6984 → **7142** (current on HEAD `d60795f`).
3. **"993k rows 2015-2024"** (§13). 993,005 spans **2015-2026**; 2015-2024 holds **789,277**. Inherited
   from the build doc and the roadmap, but wrong in all three.
4. **"127k → 98k canonical events"** (§14). The receipt says **137,190 → 105,494, ratio 1.3005**. The doc,
   the roadmap and the commit message all carry the stale 127,157 → 97,949 / 1.298.
5. **"top-300 rank-weighted + hysteresis 29.27×"** (§9). 29.266 is the **EW** cell at **10 bps**. The rank
   cell is 29.166 at 10 bps and **17.755** at 25 bps — and 25 bps is the rate the +4.670pp headline is
   computed at.
6. **Mixing 3.66× with 29.27×** (§9). Those are a 25-bps control and a 10-bps broad book. Same-cost pairs
   are 3.66 → 18.14 or 8.96 → 29.27.
7. **"+5.75pp" welded to "12/12"** (§2). Two different baselines — frozen-once vs annual — which the
   `A2_comparison` block explicitly forbids quoting as one quantity. The 12/12 family's median is
   **+1.204pp** with best Holm **1.0**.
8. **"liquidity floor hurt by ~9.6pp/yr"** (§12). A level, not a delta.
9. **"conviction loads 0.66 today, 1.50 yesterday"** (§19). Receipt: **0.6072** and **1.399** (univariate
   lagged 1.4259, Dimson 1.9313). GPT repeated a doc figure no receipt supports.
10. **"NVIDIA embeddings available" — GPT is right, the repo is wrong** (§14). Listed here because the
    correction runs the other way: `ROADMAP_2026-09-04_PROFIT_ENGINE.md:423` says "NVIDIA embedder ABSENT
    — no key in this repo" and its own cited receipt records a successful 3×2048 embedding call.
11. Minor: **"8-arm months"** (§11) — the receipt's filter is ">= 6 arms present". **"hold ~150"** (§3) is
    nn_pre_causal's optimum only. **"3.67× vs SPY 3.67×"** (§1) hides that the book is below SPY both
    unlevered and leverage-neutral.

## Doc-vs-receipt disagreements found along the way (the receipt wins in each)

| doc statement | receipt |
|---|---|
| night lab §N5: "127,157 news rows → 97,949 canonical events, ratio 1.298" | `N5_event_compression.json`: 137,190 → 105,494, ratio 1.3005 |
| roadmap §6 N5: "NVIDIA embedder ABSENT — no key in this repo" | `nemotron_probe`: OK, 935.9 ms, 3 embeddings, dim 2048 |
| growth §G7 prose: "conviction loads 0.66 on today's market and 1.50 on yesterday's" | 0.6072 / 1.399 joint; 1.4259 lagged univariate; Dimson 1.9313 |
| night lab §N1.3: "hedges correctly (realised β 0.00–0.05)" | −0.0605 … **0.4254**; ridge 0.20, encoder 0.42 |
| night lab §N6.2: round 2 "canary **0/8**" | END arm 0.0, **FRONT arm 0.125** |
| labor day C1 scoreboard's five fixes name "exit-failure stop re-place" | that row reads `none needed (fixed 2026-09-05)`; the fifth new fix is the re-entry-guard fallback |
| night lab / roadmap: event table "993,005 rows, 2015-2024" | `year_range_present [2015, 2026]`; 789,277 rows in 2015-2024 |
| night lab table: "top-50 VW 25 bps 3.66" beside "top-300 EW 10 bps 29.27" as "one column, two constructions" | the two rows are at different cost rates |
