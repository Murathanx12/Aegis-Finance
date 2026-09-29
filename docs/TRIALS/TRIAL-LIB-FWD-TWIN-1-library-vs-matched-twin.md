# TRIAL-LIB-FWD-TWIN-1 — the strategy library's frozen books vs their frozen twins, pooled by cluster (pre-registered decision rule)

> Pre-registered 2026-09-28 (lane M6 of `docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`),
> **before the first forward session**: every book below enters at the **2026-09-28 open**
> (13:30Z). This file is the tamper-evident commitment ONLY IF it is committed before that
> open; if it is committed later, the inception moves to the next session and the 2026-09-28
> session is excluded, never grandfathered. The same rule is embedded in
> `rule_experiments.notes` (param `lib-forward-vs-twin-pooled-by-cluster`) by
> `backend/services/lib_forward_trial.ensure_lib_forward_trial`. The frozen inputs (pairs,
> clusters, every sigma, both correlations) are in
> `backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json`. Changing this rule
> after data accrues invalidates the trial.
>
> **This trial creates no book, no twin, no account.** It registers a comparison over books
> already frozen in `backend/data/optimus/llm_portfolio/books.jsonl`. Licence of the books:
> `PRODUCT_EXPERIMENT`. Licence of any reading of this trial: none beyond it — a SURVIVES is a
> candidate for a longer forward record, not a claim.

## Hypothesis

The strategy library's frozen forward books earn more than their frozen twins over the same
sessions, pooled so that each distinct bet (a bridge cluster) counts once.

**Honest prior: weak.** On the backtest, 2 of 288 cells cleared t >= 2 against the
characteristic-matched twin in both windows, against ~0.8 expected by luck
(`docs/BOOK_2026-09-27_LEADS_FROM_THE_FAMILY_POOL.md`); the median rule loses to its matched
twin in 2024-26 (−0.2%, `docs/SIGNAL_STRUCTURE_2026-09-26.md`); the leads' monthly t overstates
a hold-3 rule: on rebalance blocks, with the reference run's own twin seed, `disp_short_avoid`
reads t 1.94 (dev) / 1.66 (2024-26) and `mom_12_1_q_trend` 2.24 / 1.96, so neither clears 2 in
both windows (`strategy_library/calendar_offsets_2026-09-28T055923Z.json`, `default` rows), and
at their other two quarterly calendars both are CANNOT_DISTINGUISH. A null here is the expected
outcome.

## The books (counted from disk, 2026-09-28)

| count | value |
|---|---:|
| rows in `books.jsonl` | 308 |
| live parent books (all kinds, VOID excluded) | 61 |
| twins | 245 |
| VOID before entry | 1 (`lib_mom_12_1_liqw_sealed_2026-09-26`) |
| **library books in this trial** (live `lib_` parents) | **30** |
| of which read against a `matched_random` twin (size band x vol tercile x 12-1 tercile) | 5 |
| of which read against a `random_same_band` twin (size band only) | 25 |
| **clusters in this trial** (bridge `cluster_full`, a forward-only book is its own cluster) | **17** |

The bridge's own count is 18 distinct bets over 31 rows; the 31st row is the equal-weight twin
of the voided parent, a twin with no twin of its own, which cannot enter a book-minus-twin read.

**The twin rule.** Each book is read against its first frozen twin in the order
`matched_random`, `random_same_band` (`lib_forward_trial.select_pairs`). The 25 band-only twins
do not remove the volatility / past-return style the matched twin removes: a momentum book beats
a band-only random twin in a momentum month by style alone. Their sigma is frozen as the LARGER
of (rule - matched twin) and (rule - uniform random) on the backtest, so the style noise widens
the band and does not flatter z. The 5-pair `matched_random` subset is printed beside the
primary as a secondary; it never decides.

## Primary metric (the only deciding number)

For each book i: d_i = (book return) - (twin return), each from its entry-session open over the
same sessions, from the llm_portfolio grader's own marks. Each cluster's value is the mean d_i of
its books; **D = the mean over clusters**. z = D / sd(D), where sd(D) is computed from the
**frozen** per-book sigmas and the **frozen** within-cluster (0.66) and between-cluster (0.09)
correlations of the backtest's single-draw rule - twin differences (`pooled_sd`). Nothing is
re-estimated on forward data.

| horizon | read date (XNYS session n from 2026-09-28) | sd(D) | MDE at 80% power (2.8 sd) |
|---|---|---:|---:|
| 21 sessions | **2026-10-26** | 2.76% | **7.73%** |
| 63 sessions | **2026-12-24** | 4.90% | **13.73%** |

slice_purpose: EXPLORE

Why EXPLORE and not CONFIRM: linted as CONFIRM on 2026-09-28, `lint_prereg` returned `CONFIRMATION_WINDOW_ABUTS_SELECTION` (selection 2017-01-31..2026-09-25, slice starts 3 days later, a 63-day horizon needs a 103-day gap). No label actually crosses: the backtest's last resolved monthly label ends at the 2026-09-01 open and every forward difference here starts at the 2026-09-28 open. But the gate is right about what may be CLAIMED: the rules were chosen on data that ends days before this slice, by a process the gate cannot audit. **No outcome of this trial may be written up as independent confirmation**; it is a PRODUCT_EXPERIMENT forward read, and a SURVIVES licenses a longer forward record only.

Slice identity (lint R13 / R13e / R13f):

slice_securities: the 30 frozen lib_ books' holdings and their 30 frozen twins' holdings (US equities, `llm_portfolio/books.jsonl`, ids in the receipt)
slice_period: 2026-09-28 to 2026-12-24
information_cutoff: 2026-09-25 (the last bar any book or twin was frozen on; books frozen 2026-09-26 and 2026-09-27)
selection_period: 2017-01-31 to 2026-09-25
hypothesis_source: strategy_library leaderboard 2026-09-27T082553Z, matched_twins and family_pool of the same run, bridge_2026-09-28
hypothesis_source_period: 2017-01-31 to 2026-09-25
outcome_horizon_days: 63

Power fields (lint R13):

declared_effect_size: 13.73pp over 63 sessions (the MDE at 80% power; ~4.6% a month pooled)
event_frequency_per_year: 4 (one 63-session primary read per quarter; 30 books in 17 clusters each read once per horizon)
outcome_dispersion: sd(D) 2.76% at 21 sessions, 4.90% at 63 sessions (per-book sigma median 7.5% at 21 sessions, range 3.3%-11.0%)

**What the MDE means:** this comparison can detect a pooled edge of ~4.6% a month over its
first quarter and nothing smaller. It can find a large effect; it cannot certify a realistic one,
and a failure does not show that no edge exists.

## Decision rule

- **EARLY KILL (session 21, 2026-10-26):** z_21 <= −2. Otherwise the 21-session read is
  reported, never acted on.
- **SURVIVES (session 63, 2026-12-24):** z_63 >= 2 AND the 21-session pooled D > 0. The library's
  forward books become candidates for a 126-session record, not a claim.
- **KILL (session 63):** z_63 < 1. Using the library as a SOURCE OF NEW BOOKS is
  `DEPRIORITIZED`. No new `lib_` book, lead, twin or paper account is minted from the strategy
  library for 126 sessions. The word "lead" is removed from any document describing these books.
  The existing books keep accruing, with every read printed beside the luck table. The
  mechanisms are NOT rejected: at this MDE a KILL means "no large edge", never "no edge".
- **Otherwise (1 <= z_63 < 2):** `CANNOT_DISTINGUISH`. Extend to 126 sessions under this same
  rule and these frozen sigmas. No new book in the meantime.
- **Individual books decide nothing.** The best single book is reported beside the luck table
  below, and nowhere as a result.
- **Power of this rule** (normal approximation, effect in units of sd(D)): at 0 sd,
  P(SURVIVES) ~ 2.3% and P(KILL) 84%; at 1 sd, 16% / 50%; at 2 sd, 50% / 16%; at 2.8 sd (the MDE),
  79% / 4%.
- **Crash override:** if SPY closes >= 20% below its in-window peak, no SURVIVES / KILL is taken
  until the window includes >= 63 sessions after the trough. The override delays; it never changes
  the metric or the threshold.
- **Contamination clause:** a book VOIDED after entry, or a book or twin without a grader mark
  for >= 5 consecutive sessions, is dropped from the pool with its reason recorded. If more than
  25% of the 30 books drop, the verdict is `CANNOT_DETERMINE` and the window extends by the
  defect's length.

## The luck table (printed beside every read)

With K zero-skill books whose z's are equicorrelated at rho, the probability that the BEST one
reads z >= 2 (100,000 simulations, seed 20260928; `lib_forward_trial.luck_table`):

| K (what) | rho 0 | rho 0.08 (median pairwise, backtest) | rho 0.30 (the adversarial review's active-return rho) |
|---|---:|---:|---:|
| 17 (clusters in this trial) | 32.4% | 29.7% | 23.6% |
| 30 (library books in this trial) | 49.9% | 44.7% | 32.8% |
| 61 (every live parent book) | 75.4% | 65.9% | 46.3% |

E[best z] with zero skill: 1.79 / 2.04 / 2.33 at rho 0 for K = 17 / 30 / 61. **A single book at
z = 2 on 2026-10-26 is what luck produces about half the time.** Only the pooled D decides.

## Frozen parameters

The 30 pairs (book id -> twin id and type), the 17 cluster ids, every sigma at 21 and 63
sessions, rho_within 0.66, rho_between 0.09, the entry session, the two read dates, the
thresholds 2 / 1 / −2 and the 25% drop limit, all in
`backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json` and
`backend/services/lib_forward_trial.py`. The sigma basis per book is printed in the receipt
(`sigma_basis`); the two forward-only books take the median of the others.

## What this rule may NOT do

No metric substitution after the fact; no switching a book to a friendlier twin; no dropping a
cluster because it lost; no re-estimating sigma on the forward data; no reading the best single
book as a result; no new book, twin or account in its name. The 21-session read cannot rescue a
book, only end the trial early. A SURVIVES licenses a longer forward record only; `CAPITAL_CANDIDATE`
and `RESEARCH_CLAIM` keep every stricter gate.

## Owed (not done by this registration)

- The production registry: one startup line in `backend/main.py` calling
  `lib_forward_trial.ensure_lib_forward_trial` (the `ensure_r2_trial` pattern). Not made here
  (file ownership); the local registry row is registered by
  `python -m scripts.lib_forward_trial --register`.
- The read itself: at each read date, `lib_forward_trial.pooled_z` over the grader's marks and
  `decide(...)`. No scheduled caller exists yet.

---

## AMENDMENT 2026-09-28 (written ~06:50Z, BEFORE the 13:30Z open; nothing above is edited)

Answers `docs/reviews/REVIEW_2026-09-28_LANE_M_MEASUREMENT.md` F1 (frozen inputs not under
version control) and F2 (the error bar used one twin type for sigma and another for rho).
**No return from 2026-09-28 or later is used anywhere in this amendment**: the only series read
are the backtest's monthly parquets of run `2026-09-27T082553Z`, whose last month is 2026-07-31.

### A1. The frozen inputs, by sha256 (F1)

| sha256 | bytes | path | git state at amendment |
|---|---:|---|---|
| `09239739802eb4540d8498f2da4bdc4d48af0846142a4ee29c662747e8b401f8` | 18,344 | `backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json` (the registration receipt: 30 pairs, 17 clusters, 30 x 2 sigmas, registered rho) | untracked |
| `2c75c2d318e56ed8aceab7632f39d3662e2696e075acd39b613598681f83a54d` | 2,577 | `backend/data/optimus/trials/lib_forward_trial_amendment_2026-09-28T065024Z.json` (this amendment's receipt) | untracked |
| `23fb7eec1958033eb701306ff8a7be2395133ee68a041ff9f6f5ab55398af776` | 11,183 | `backend/services/lib_forward_trial.py` (`select_pairs`, `pooled_sd`, `pooled_z`, `decide`, the amended rho constants) | untracked |
| `370d0b6e0f7429aac8791fb177403a1a3ffaa86200dd8970d9158a7c88846563` | 16,382 | `scripts/lib_forward_trial.py` (`estimate`, `amend`) | untracked |
| `380d878a902c4fba087adb09b9a90e2319d18be8e41f47e8e75a36aaada9555c` | 8,197 | `backend/tests/test_lib_forward_trial.py` | untracked |
| `88bd40926c1237316aeaa310389923d472ed04cc3b8cc65887b3de88d78225de` | 185,658 | `backend/data/optimus/bridge/bridge_2026-09-28.json` (the cluster source) | untracked |
| `62c2bd18a9d4b8e2030d08d24f27d5e4c27d0255f8793c3b26d8bf1312104e2c` | 908,303 | `backend/data/optimus/llm_portfolio/books.jsonl` (the frozen books and twins) | tracked, unmodified |
| `4b2b1d33801c7d6271170372de2b74bbcc34cc80efab05e8a5d2a228b7dd88ad` | 1,072,667 | `backend/data/optimus/signal_structure/matched_twins_monthly_2026-09-27T082553Z.parquet` (rule - matched twin series) | gitignored (`*.parquet`) |
| `c55aea9b8f67cd73e0a963a93ad800ba37331029e7be28310349330b17b8ce22` | 1,521,776 | `backend/data/optimus/signal_structure/monthly_returns_2026-09-27T082553Z.parquet` (rule and `random_1@k50` series) | gitignored (`*.parquet`) |
| `b80708f3006e5c346cf32d43a1e16aed90f8d18f75364635e74ec747dfdae9ea` | 316,152 | `backend/data/optimus/paper_accounts/roi_2026-09-28T060842Z.json` (the paper-account receipt the corrections cite) | untracked |
| `2e03e098a9e21bbaaef5bd03af4019db350bd2409cfb7f30601fffabaad1f6c7` | 78,435 | `backend/data/optimus/strategy_library/calendar_offsets_2026-09-28T055728Z.json` | untracked |
| `537977fa169638b78261110e4281a186cbf965a411deb3dff83fa8c3fc43f57b` | 83,586 | `backend/data/optimus/strategy_library/calendar_offsets_2026-09-28T055923Z.json` (cited in the Hypothesis section above) | untracked |
| `143fbb599ee2a582b18fe88cbfbc1e23fca9a32ad97868bff01e99b524e307b1` | 30,985 | `backend/data/optimus/strategy_library/calendar_offsets_monthly_2026-09-28T055923Z.parquet` | gitignored (`*.parquet`) |

A reader on 2026-10-26 recomputes each sha256 before reading. A mismatch on any row is
`CANNOT_DETERMINE` until the difference is explained; it is never silently regenerated.

### A2. The error bar, estimated on the twin type the trial reads (F2)

The registered rho were computed from the MATCHED-twin differences (`rule_minus_twin0`) for all
30 books, while 25 of the 30 are read against a SIZE-BAND-ONLY twin whose difference keeps the
vol / momentum style (8+ of the 17 clusters are momentum variants). Re-estimated with the
difference type actually read (band-only pairs: rule - `random_1@k50`, the same proxy the
sigmas already used; the 5 matched pairs: rule - matched twin), same months, same pairs, same
clusters. The per-book sigmas are **unchanged**: `amend` re-derives them and refuses unless they
equal the registration receipt's to 1e-12 (they do).

| | **registered** (receipt T062024Z) | **corrected (as read)** |
|---|---:|---:|
| rho within cluster (37 pairs) | 0.66 | **0.78** |
| rho between clusters (341 pairs) | 0.09 | **0.40** |
| sd(D), 21 sessions | 2.76% | **4.79%** |
| sd(D), 63 sessions | 4.90% | **8.47%** |
| MDE at 80% power, 21 / 63 sessions | 7.73% / 13.73% | **13.40% / 23.72%** |
| P(false fire, one side) under zero skill if the registered bar is used | 2.3% (as documented) | **12.4%** (the real rate of the registered rule) |
| effective independent bets among the 17 clusters, 17 / (1 + 16 rho_between) | 6.8 | **2.3** |

Cross-check: the directly measured sd of the equal-weight cluster pool of the as-read series is
4.45% a month and 8.43% a quarter (115 months), agreeing with the closed form. The band-only
proxy is not size-matched, so 0.40 is an upper-side estimate; the truth lies between the columns.
This amendment takes the wider bar, which can only make the trial harder to pass or to kill.

**The reads on 2026-10-26 and 2026-12-24 use the CORRECTED sd(D).** Both z's are printed at
every read (`pooled_z` returns `z` = corrected, deciding; `z_registered` beside it, never
deciding). The deciding correlations are frozen as constants in
`backend/services/lib_forward_trial.py` (`RHO_WITHIN_AS_READ`, `RHO_BETWEEN_AS_READ`), and
`amend` refuses if its estimate ever differs from them.

### A3. The thresholds, restated (false fire under zero skill <= 5%)

The z thresholds are unchanged (−2 / +2 / +1); they now apply to the corrected sd(D), which
restores the rates the registration documented. In pooled-D units:

- **EARLY KILL (2026-10-26):** pooled D_21 <= **−9.57%** (z_21 <= −2 on sd 4.79%).
- **SURVIVES (2026-12-24):** pooled D_63 >= **+16.95%** (z_63 >= 2 on sd 8.47%) AND D_21 > 0.
- **KILL, relabelled `DEPRIORITIZED` in effect as the registration already states:** D_63 < **+8.47%** (z_63 < 1).
- Otherwise `CANNOT_DISTINGUISH`, extend to 126 sessions under this same corrected bar.

Zero-skill false fire on the corrected bar (2,000,000 simulations, seed 20260928, D_63 containing
D_21 at correlation sqrt(1/3)): P(EARLY_KILL) 2.27%, P(SURVIVES) 2.14%, **P(either) 4.41% <= 5%**.
A KILL under zero skill (84%) is the correct outcome, not a false fire.

What this means, plainly: the pool behaves like about two independent bets. It can detect a
pooled edge of ~24% over a quarter and nothing smaller. As registered, it is a monitor with a
pre-committed interpretation, not a test that can confirm a realistic edge.

Receipt: `backend/data/optimus/trials/lib_forward_trial_amendment_2026-09-28T065024Z.json`
(`python -m scripts.lib_forward_trial --amend backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json`).
Test: `backend/tests/test_lib_forward_trial.py::test_the_grader_decides_on_the_as_read_correlation_and_prints_the_registered_beside_it`
and `::test_estimate_takes_rho_from_the_difference_type_the_trial_reads`.


---

## NOTE 2026-09-28 ~15:40Z (answering review 2026-09-29 F4; after the first session opened, BEFORE any forward return of this trial was read; nothing above is edited): stitched tickers in the books

**What was found.** `docs/reviews/REVIEW_2026-09-29_NN_LAB.md` F4, verified and widened by
`backend/services/stitched_tickers.py` (receipt
`backend/data/optimus/stitched_tickers/stitched_20260928T153245Z.json`; the first run `stitched_20260928T151537Z.json` has the same verdicts and a spurious `recent_file_first_trade` line, fixed; note
`docs/research_notes/2026-09-29/stitched_tickers_2026-09-29.md`): the bar panel the library
ranked on joins two companies' histories under one reused ticker for **62 symbols**. For 42 of
them the new company resumed inside the 12-1 window. JAN ($2.21 in 2024, a $23.34 IPO on
2026-03-20), LIFE ($1.90 -> $16.85) and AKTS ($0.04 -> $22.40) read as enormous 12-1 winners
purely because the window straddles the hole; MLPI does the same from the delisted file.

**Which books in this trial are affected** (from `books.jsonl`, sha256 as in A1, not modified):
20 of the 30 pairs.

- **Parent holds a stitched name (16 pairs, 7 clusters, 6 of them entirely):**
  `lib_disp_short_avoid_2026-09-27` (AKTS, LIFE, JAN, MLPI, 5% each),
  `lib_frog_in_pan_2026-09-26` (MLPI 5%), `lib_illiquid_sealed_2026-09-26` (ITG 5%),
  `lib_low_dtc_mom_sealed_2026-09-26` (MLPI 5%), `lib_mom_12_1_2026-09-26`,
  `lib_mom_12_1_q_2026-09-26`, `lib_mom_12_1_q_trend_lead_2026-09-27`,
  `lib_mom_12_1_secrel_sealed_2026-09-26`, `lib_mom_no_downgrades_2026-09-26`,
  `lib_qc470_mom252_quarterly_riskparity_2026-09-27__control` (each AKTS, LIFE, JAN at 5%),
  `lib_mom_12_1_ivw_lead_2026-09-27__control` (26.3%: JAN 14.9%),
  `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control` (26.5%: JAN 15.0%),
  `lib_mom_12_1_small_2026-09-26` (AKTS, MLPI), `lib_mom_flow_2026-09-26` (JAN),
  `lib_mom_flow_ivw_2026-09-27` (JAN), `lib_mom_no_downgrades_small_2026-09-27__control` (AKTS).
- **Only the twin holds one (4 pairs):** `lib_forecast_dispersion_v1_2026-09-26` (twin: SMHD),
  `lib_margin_mom_sealed_2026-09-26` (twin: FIYY), `lib_rev_5d_sealed_2026-09-26` (twin: PCI, MB),
  `lib_skill_mom_2026-09-27` (twin: ULTI). A random twin holding the NEW company is a real random
  draw of a real security; it is listed for completeness.
- The receipt lists every one of the 45 books (of 312) that hold a stitched name, with weights.

**What is and is not contaminated.** The forward MEASUREMENT is not: JAN, LIFE and AKTS are
real, tradable securities and the grader marks them from their own bars. What is contaminated is
WHY they were bought: for the momentum books the 12-1 score that selected them was the splice.
A forward "momentum book minus twin" therefore partly grades a data error that picked three
recent IPOs.

**How the reads on 2026-10-26 and 2026-12-24 handle it (decided now, before any data):**

1. **The deciding read is unchanged:** the registered pooled D over all 30 books and 17
   clusters, on the corrected sd(D) of A2. No book is dropped from it, and no frozen book, twin,
   weight or id is changed. The contamination clause's 25% drop limit is not invoked, because
   nothing is dropped.
2. **Three sensitivity reads are printed beside it at both dates**, each on the SAME frozen
   per-book sigmas and the A2 correlations:
   - **S1:** excluding the 16 pairs whose parent holds a stitched name (14 books, 11 clusters);
   - **S2:** excluding all 20 affected pairs (10 books, 8 clusters);
   - **S3:** every book kept, but each affected book's (and twin's) return recomputed from its
     non-stitched holdings, re-weighted to its original gross, from the same bars.
3. **A SURVIVES stands only if S3 also reads z_63 >= 2 and D_21 > 0.** Otherwise the verdict
   is printed as `NOT_ROBUST_TO_STITCH` and licenses nothing. EARLY KILL, KILL and
   CANNOT_DISTINGUISH are taken from the deciding read as registered, with S1-S3 printed beside.
   This can only make the trial harder to pass.
4. S1 removes the momentum family's clusters entirely (170, 181, 84, 120, 138, 186), so S1 and S2
   say little about momentum; S3 is the one that keeps it. That is why S3, not S1, is the
   condition.

No return from 2026-09-28 or later was read to write this note.

## AMENDMENT 2026-09-29 (sensitivity only; BEFORE the 2026-10-26 read; no forward return of this trial was read to write it; nothing above is edited): broken price histories beyond the stitched tickers

**What was found.** The stitch detector counts gaps between bars, and the vendor fills some holes
with flat ZERO-VOLUME bars, so there is no gap to count (LINE: Linn Energy at $0.1641 every
session from 2016-05-24 to 2024-07-24, Lineage at $73.66 the next day). Other rows jump on an
unadjusted corporate action or a re-issued equity. `backend/services/bar_defects.py` now runs
inside `stitched_tickers.split_stitched`, so every bar reader gets it. It removes 174,417 non-trade
rows (dark runs, zero-volume prints, spike prints) and cuts 95 proven level breaks. With the holes
visible, the stitch detector finds 766 STITCHED gaps instead of 62. Note:
`docs/research_notes/2026-09-29/broken_price_histories_2026-09-29.md`; receipt
`backend/data/optimus/bar_defects/bar_defects_2026-09-29T033458Z.json`.

**Which books in this trial are affected.** Receipt
`backend/data/optimus/bar_defects/books_2026-09-29T034841Z.json`. It is read-only on
`books.jsonl`. The test: at the book's `asof`, compute each holding's 12-1 momentum and 63-day
volatility from the same bars with the reader before and after the screen. A holding counts as
**selected on a broken row** when the screen cuts its history inside the 12-1 window, moves
ln(1+mom) by more than 0.10, or changes vol_63 by more than 1.5x.

- Across all 314 frozen books: **21 positions in 21 books, two tickers.**
  - **WOLF**, 20 books. Wolfspeed's old equity closed at $1.21 on 2025-09-26 and the
    post-reorganisation equity opened at $22.10 on 2025-09-29, an 18x "move" on 1.1x normal
    volume. The 12-1 score that bought it was that splice.
  - **ISRL**, 1 twin: `cards_supports_2026-09-25__random_same_band`.
- **Pairs of this trial: 9 of 30, all on the book side** (WOLF at 5%, or 3.5% in the two
  inverse-vol `__control` books). No twin of the trial is affected.
  - **Already listed** in the 2026-09-28 stitched note (7):
    - `lib_disp_short_avoid_2026-09-27`
    - `lib_mom_12_1_2026-09-26`
    - `lib_mom_12_1_q_2026-09-26`
    - `lib_mom_12_1_q_trend_lead_2026-09-27`
    - `lib_qc470_mom252_quarterly_riskparity_2026-09-27__control`
    - `lib_mom_12_1_ivw_lead_2026-09-27__control`
    - `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control`
  - **New** (2):
    - `lib_low_asset_growth_sealed_2026-09-26`
    - `lib_resid_mom_12_1_large_sealed_2026-09-26`
- No holding had a SUSPECT break in its window. A suspect is a >= 3x move on 2-10x volume,
  which the screen keeps but cannot prove.

**What is and is not contaminated.** It is the same shape as the stitched note. WOLF is a real
tradable security, and the grader marks it from its own bars. What is contaminated is WHY the
momentum books bought it.

**How the reads handle it (decided now, before any data):**

1. **The deciding read is unchanged.** No book, twin, weight or id changes.
2. **S1 and S2 are unchanged.** They are defined on the stitched pairs.
3. **S3 is widened to S3'.** Each affected book's return is recomputed without its stitched
   holdings AND without WOLF (and ISRL on its twin), then re-weighted to the original gross from
   the same bars. **A SURVIVES stands only if S3' reads z_63 >= 2 and D_21 > 0.** Otherwise the
   verdict prints as `NOT_ROBUST_TO_BAR_DEFECTS` and licenses nothing.
4. This can only make the trial harder to pass.

**The backtest the trial's leads came from moved** (hindsight, costs on, calendar-neutral,
rule minus 21-draw matched twin; receipt
`backend/data/optimus/strategy_library/broken_price_histories_compare_2026-09-29T034617Z.json`):

| rule | cum net since 2020 | rule - twin %/mo | t | verdict |
|---|---|---|---|---|
| `mom_12_1_q` | +661% -> +458% | +1.20 -> +0.92 | 2.49 -> 1.83 | CANNOT_DISTINGUISH -> CALENDAR_ARTEFACT |
| `mom_12_1_q_trend` | +304% -> +186% | +1.22 -> +0.96 | 2.80 -> 2.03 | CANNOT_DISTINGUISH -> CALENDAR_ARTEFACT |
| `qc470_mom252_quarterly_riskparity` | +585% -> +395% | +1.12 -> +0.84 | 2.62 -> 1.91 | CANNOT_DISTINGUISH |
| `disp_short_avoid` | +466% -> +342% | +0.81 -> +0.58 | 1.80 -> 1.26 | CALENDAR_ARTEFACT -> CANNOT_DISTINGUISH |

This does not change the trial. The trial reads forward returns, not these numbers. It is
recorded here because this backtest is the reason these books were frozen.

## AMENDMENT 2026-09-29 b (context only; BEFORE the 2026-10-26 read; no forward return of this trial was read to write it; nothing above is edited): the leads rebuilt on CRSP, and a universe bias in the panel they were selected on

**What was done.** The four leads were rebuilt on CRSP daily total returns, 1991-2024, with delisting
returns and dead names included. The run used the library's own engine unchanged: quarterly offsets,
band costs, the 21-draw matched twin on two seed sets, and the v2 calendar rule. Note:
`docs/research_notes/2026-09-29/momentum_on_crsp_2026-09-29.md`. Receipts are in
`backend/data/optimus/crsp_rebuild/`:

- `momentum_on_crsp_2026-09-29T042053Z.json`
- `slots_2026-09-29T042802Z.json`
- `emulate_vendor_universe_2026-09-29T043122Z.json`

**Rule minus 21-draw twin**, calendar-neutral, %/month (t on 3-month blocks, MDE):

| rule | CRSP 1991-2024 | CRSP 2017-24 | vendor 2017-24 | CRSP 2017-24 under the vendor's universe rule |
|---|---|---|---|---|
| `mom_12_1_q` | +0.10 (t 0.33, MDE 0.83) | +0.22 (t 0.37) | +1.09 (t 1.97) | +0.93 (t 1.63) |
| `mom_12_1_q_trend` | +0.01 (t 0.03, MDE 0.75) | -0.11 (t -0.21) | +1.11 (t 2.13) | +0.70 (t 1.30) |
| `qc470_mom252_quarterly_riskparity` | +0.26 (t 0.90, MDE 0.82) | +0.48 (t 0.81) | +1.00 (t 2.14) | +1.01 (t 1.89) |
| `disp_short_avoid` (1999-2024) | -0.14 (t -0.43, MDE 0.90) | +0.34 (t 0.55) | +0.82 (t 1.69) | not run |

**Verdicts on CRSP:**

- All four are CANNOT_DISTINGUISH on the calendar rule. None is ROBUST_TO_CALENDAR.
- As implementations, all four are **FAILED_VARIANT**. The reasoning is in the note, section 2.
- `mom_12_1_q` and `disp_short_avoid` carry negative four-factor alphas: -0.78%/mo (t -2.27) and
  -1.05%/mo (t -2.83).
- The only positive stretch in 34 years is 1998-2000.

**The cause of the vendor number.** The living half of the vendor panel is a universe dated
2026-09-01, floored at $3M median dollar volume measured on that date. The delisted pull adds names
that stopped trading. A past winner that collapsed and stayed listed at low volume is in neither.
Applying that rule to CRSP reproduces about 80% of the vendor's `mom_12_1_q` twin gap.

**What this implies for reading the forward books (decided now, before any forward data):**

1. **The trial's rule, metric, thresholds, pairs, twins and sigmas are unchanged.** No book, twin,
   weight or id changes.
2. **The forward read itself is not contaminated by this bias.**
   - The books' universe was fixed on 2026-09-01, before entry on 2026-09-28. Forward, that is a
     point-in-time universe, not look-ahead.
   - The grader marks forward returns from real bars.
   - The bias lives in the BACKTEST that selected the leads. It does not live in the forward
     comparison.
3. **The prior is now weaker than the one this file registered.** It had been written as "weak".
   On a survivorship-free source, the historical reason these books exist is +0.10%/mo over the
   matched twin, with an MDE of 0.83. So the null is the expected outcome. The trial's MDE (about
   4.6% a month pooled) is 46 times the CRSP point estimate, so a SURVIVES would be surprising.
4. **A SURVIVES licenses only a longer forward record.** It is still read as a candidate for more
   forward evidence, never as a confirmation of the backtest. The backtest has no independent
   support left.
5. **A KILL is read against this amendment.** It is consistent with the CRSP rebuild. It does not
   reject momentum as a mechanism: the published UMD was +0.26%/mo for 2017-2024 and +1.21%/mo for
   2025 to June 2026.
6. **Nothing about S1, S2 or S3' changes.** The stitched-ticker and bar-defect sensitivities stand
   as written.
