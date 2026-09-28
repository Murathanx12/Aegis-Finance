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
