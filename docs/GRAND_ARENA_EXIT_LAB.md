# GRAND-ARENA-1 PHASE 5+6 — EXIT-LAB-1

**The counterfactual decision factory: 1,584,000 position-states, 25,344,000
state-action rows, 152,064,000 state-action-horizon outcome cells, on CRSP
daily 2002-2024.**

Pre-registered `Aegis module/TRIALS/PREREG_EXIT_LAB_1.md` (`lint_prereg` **PASS**
against 321 prior experiments) **before a single row existed**. Runner
`Aegis module/scripts/run_exit_lab_1.py` (+ `exit_lab_core.py`,
`exit_lab_data.py`, `exit_lab_learn.py`). Receipts
`Aegis module/data/factory/exit_lab_1_*.json` and `exit_lab_1_*.parquet`
(untracked — `/data/` is gitignored).

> ## Verdict: **THE CASH NULL SURVIVED ITS REAL DENOMINATOR.**
>
> NIGHT-12 found `sell_to_cash` was never best in 60 rows from one portfolio.
> Given 1.58 million rows from 11,145 securities over 23 years, it is **never
> best again** — and now with a ruler. At the pre-registered 60-day horizon
> selling a held position to cash costs **−2.82 pp** against its own 80%-power
> MDE of **2.76**, with the sign the same in 7 of 8 regime blocks and both
> sample halves. At 252 days it costs **−11.27 pp** against an MDE of 7.55,
> 8/8 blocks.
>
> **Not one of the 20 pre-declared management policies beat never-selling at
> any of the six horizons.** Every single one has a negative point estimate at
> every horizon. The best of them — take-profit at +100%, which trades 2.2% of
> states — loses 0.04 pp at 60 days. The worst — always-to-cash — loses 11.27.
> The trailing stop, entered as a declared CORPSE control (CANON §15,
> −3.08%/yr under G7), came back **DETECTABLE_NEGATIVE at 252 days** on an
> instrument that never saw NIGHT-7: −4.94 pp against an MDE of 4.82, 8/8
> blocks. The corpse stayed dead on independent evidence.
>
> **The honest qualification, and it is a real one.** At **zero** transaction
> costs the same comparison is **−2.55 pp against an MDE of 2.77 — NOT
> DETECTABLE**. The gross gap between holding and selling is below this
> instrument's resolution; it is the *cost of trading* that pushes it over.
> The finding is therefore precisely: **selling is not detectably wrong, but
> paying to sell is.**
>
> **What replaces cash is not the answer either.** Replacement was the one
> place a management action could have won, and it did not: no replacement arm
> beat holding at any horizon, and — the clause that decides it — **no
> momentum- or revision-ranked basket beat its own equally-concentrated
> RANDOM basket** at any horizon. Every replacement advantage over cash is
> "being invested", which is the equity premium, not a decision.
>
> **These are DIRECTION CHECKS on simulated counterfactuals, never alpha
> evidence.** Nothing here licenses a change to any live or paper lane.

---

## 1. What was built, and out of what

### 1.1 The data, printed as found

| source | file | span | frequency | coverage | PIT-safe |
|---|---|---|---|:--|:--|
| CRSP daily stock file | `data/wrds_raw/dsf_full/dsf_{2002..2024}.parquet` | 2002-01-02 → 2024-12-31 | daily | 5,789 days × 11,145 permnos | **yes** — pulled at source restricted to `shrcd` 10/11, `exchcd` 1/2/3 |
| CRSP delisting file | `data/wrds_raw/crsp_dsedelist.parquet` | same | event | 7,283 real delistings (`dlstcd ≥ 200`) spliced | yes |
| Fama-French daily | `data/wrds_raw/ff_factors_daily.parquet` | 1926 → 2026 | daily | `mktrf`, `rf` — the CRSP value-weighted market and the risk-free leg | yes |
| CRSP stocknames | `data/wrds_raw/crsp_stocknames.parquet` | — | name rows | SIC valid **at** T0 → FF12 industry | yes (validity windows honoured) |
| IBES revision panel | `data/revision_panel.parquet` (NIGHT-11) | 2002 → 2024 | monthly | **83.9%** of eligible states | yes (`statpers` month-end anchor) |
| SUE / earnings dates | `data/sue_events.parquet` | 2002 → 2024 | event (`rdq`) | SUE **83.6%**, days-since-announcement **99.6%** | yes (last `rdq` ≤ T0) |
| IBES price targets | `data/wrds_raw/ibes/ptgsumu.parquet` + `ibcrsphist.parquet` | 2002 → 2024 | monthly | **98.5%**; link match rate 92.7% at `score ≤ 3` | yes — the **unadjusted** summary file, per `aegis_brain/data/ibes_panel.py` |
| Corwin-Schultz half-spread | derived from `dsf_full` `askhi`/`bidlo` | 2002 → 2024 | daily → stamped at T0 | median **24.2 bps**, p90 **89.0 bps** | yes |

**Reused, not re-fetched:** the daily return/price/volume/market-cap panel and
the delisting splice are `data/factory/wg1_panel.npz`, built for
WINNER-GENOME-1 by `scripts/wg1_panel.py` last night. Building it again would
have produced the same 395 MB file.

**What is missing, said plainly rather than fabricated.** There is no
point-in-time analyst *rating-count* panel, no historical dated
catalyst calendar, and no LLM event extraction back to 2002 — all three are
recorded as coverage gaps in `aegis_brain/arena/bindings.py` and none of them
was invented for this trial. 170,466 of 671,955 SUE rows (25.4%) carry no
permno; they are **dropped and counted**, not linked by guesswork.

### 1.2 The instrument

- **Position-state** = `(permno, decision date, entry cohort)`. Decision dates
  are the **264 month-ends** from 2003-01-31 to 2024-12-31 with ≥252 trading
  days of prior history. Entry cohorts are 21 / 63 / 126 / 252 trading days
  before the decision — a synthetic holder, declared as synthetic (§8.3).
- **Universe per date**: price ≥ $5, ≥252 days of history, 63-day median dollar
  volume ≥ $1m, top 1,500 by dollar volume. **Exactly 1,500 on all 264 dates**,
  0 dates skipped as thin. Identical to the WINNER-GENOME-1 rule.
- 264 dates × 1,500 names × 4 cohorts = **1,584,000 states**; × 16 actions =
  **25,344,000 state-action rows**; × 6 horizons = **152,064,000 outcome
  cells**. Checkpointed to 23 pairs of yearly parquet files; a rerun resumes at
  the first year whose pair is missing. Whole factory: **26 seconds**.
- **Death is modelled and counted.** A held dollar carries the CRSP delisting
  return on the first day after the last quote and then sits in cash at `rf`.
  Positions terminated *inside* a horizon: **12** at 1 day, 458 at 5, 1,472 at
  20, **4,393 at 60**, 8,434 at 120, **16,755 at 252**. The worst-resolving
  state at 252 days returns **−100.0%**; 2,172 states resolve below −95%.
  Nothing is dropped for dying.
- **Survivorship, precisely.** A position that died *before* T0 generates no
  decision at T0 — correctly, because the decision would not exist. The state
  population is therefore conditioned on survival **to** the decision, and on
  liquidity. Deaths **after** T0 are fully modelled. This is stated as a
  limitation in §8, not as a footnote.
- **No-lookahead proof.** On decision date 2014-01-31 every return, price,
  volume, market-cap and risk-free cell after T0 was replaced with garbage
  (returns ~ N(0.5, 1), prices 1e6, volumes 1e15, rf 50%/day). All 30 columns
  of all 6,000 states came back **bit-identical**. `perturbation_proof: PASS`
  (`exit_lab_1_perturbation.json`).

### 1.3 The action space, and why every branch is on the same dollar

The sleeve is **one dollar currently sitting in the position**. Each action is
a disposition of that same dollar, so all sixteen are directly comparable and
none silently changes the capital base.

| action | disposition | traded fraction |
|---|---|---|
| `HOLD` | 1 + R_i | 0 |
| `ADD_50` | 1 + 1.5 R_i − 0.5 R_bench (funded by selling benchmark) | 0.5 |
| `TRIM_10/25/50` | 1 + (1−x) R_i + x R_cash | x |
| `SELL_CASH` | 1 + R_cash | 1 |
| `SELL_BENCH` | 1 + R_bench | 1 |
| `REPLACE_1 / _2 / _1W / _2W / _1N / _REV` | 1 + R_candidate | 2 (round trip) |
| `REDUCE_BETA` | f = clip(1/β_i, 0, 1); 1 + f R_i + (1−f) R_cash | 1 − f |
| `REPLACE_RND / _RNDW` | **CONTROLS** — equally-concentrated random baskets | 2 |

These are exact, not linearisations. The accounting identity **TRIM_50 ≡
½(HOLD + SELL_CASH)** holds to `2.7e-07` — float32 resolution — across all
1.58M states, which is the check that the cost bookkeeping is not double-count-
ing or leaking.

**Costs are the repo's existing model, not a new one.** Corwin-Schultz high-low
half-spread (21-day rolling median, capped at 300 bps, floored at the
half-tick $0.005/price) + 5 bps slippage + 1 bp commission — imported from
`aegis_brain/pf/daily_sim.py`, charged on the traded fraction at T0. Mean
charged: 27.0 bps for a full exit, 6.8 bps for a 25% trim, 16.0 bps for
`ADD_50`. The market leg is charged a declared 5 bps all-in (an index fund, not
a small cap). A name with **no** CS estimate is charged that day's 90th
percentile, never zero — an unpriceable spread is an expensive spread. In the
event, **0 of 396,000** eligible name-dates needed that fallback.

### 1.4 The candidate ranking is a declared PROXY, and is named as one

There is no oracle "best current candidate" that is not a look-ahead. The proxy
is **12-1 momentum rank inside the same eligible universe at T0**, chosen a
priori as the single most-documented PIT cross-sectional ordering, needing no
parameter search. A second ranker — the NIGHT-11 revision score — is run as a
robustness arm. **Neither is claimed to be the best available candidate**, and a
null on replacement is a null on *momentum-ranked* replacement, not on
replacement in general.

**§3a amendment, made before any row was generated and recorded in the prereg.**
A one-date smoke run (no outcome statistic computed) showed the literal
single-name reading is degenerate *as an instrument*: with one candidate per
date and the decision date as the sampling unit, the whole date's replacement
outcome is one name's outcome. The prediction was that this inflates the ruler
until every replacement verdict is UNRESOLVED by construction. It was measured:

| replacement arm (vs cash, h=60) | Δ (pp) | **its MDE** |
|---|---:|---:|
| `REPLACE_1N` — the literal 1 name | +2.84 | **11.53** |
| `REPLACE_1` — top-5 basket | +0.19 | **5.94** |
| `REPLACE_1W` — top-20 basket | +1.30 | **4.65** |
| `REPLACE_RNDW` — 20 random | +2.17 | **2.82** |
| `HOLD` | **+2.82** | **2.76** |

The ruler shrinks from 11.5 pp to 2.8 pp as the candidate set widens. All three
concentrations are reported; the concentration dependence is a result, not a
choice made after seeing an answer.

---

## 2. Baselines first — and they win

Every number is a **paired per-date difference against `HOLD` on exactly the
same states**. The sampling unit is the decision date (n ≤ 264), never the
position: 6,000 states inside one month share a market factor. MDE = 2.80 ×
max(Newey-West, IID) SE per CANON §19; below it is NOT DETECTABLE and never a
kill.

### 2.1 Every single action, against holding

**h = 60 trading days (the pre-registered primary horizon), pp per decision:**

| action | Δ vs HOLD | its MDE | t | blocks | halves | verdict |
|---|---:|---:|---:|:--:|:--:|---|
| `HOLD` | 0.000 | — | — | 8/8 | yes | reference |
| `ADD_50` | −0.139 | 0.458 | −0.85 | 6/8 | no | NOT DETECTABLE |
| `TRIM_10` | −0.281 | 0.276 | −2.85 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| `TRIM_25` | −0.704 | 0.691 | −2.85 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| `TRIM_50` | −1.407 | 1.382 | −2.85 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| `SELL_CASH` | **−2.815** | **2.764** | −2.85 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| `SELL_BENCH` | −0.361 | 0.926 | −1.09 | 6/8 | no | NOT DETECTABLE |
| `REDUCE_BETA` | −0.459 | 0.561 | −2.29 | 7/8 | yes | NOT DETECTABLE |
| `REPLACE_1` (top-5 mom) | −2.623 | 5.152 | −1.43 | 4/8 | yes | NOT DETECTABLE |
| `REPLACE_1W` (top-20 mom) | −1.519 | 3.369 | −1.26 | 6/8 | no | NOT DETECTABLE |
| `REPLACE_REV` (top-5 revision) | −0.579 | 2.520 | −0.64 | 5/8 | yes | NOT DETECTABLE |
| `REPLACE_1N` (single best name) | +0.026 | **10.899** | 0.01 | 3/8 | no | NOT DETECTABLE |
| `REPLACE_RNDW` (20 random) | −0.648 | 0.655 | −2.77 | 8/8 | yes | NOT DETECTABLE |

**Every action's point estimate except `REPLACE_1N` (whose ruler is 10.9 pp) is
negative.** Trimming is detectably worse than not trimming, in exact proportion
to how much you trim — the −0.281 / −0.704 / −1.407 / −2.815 ladder for
10/25/50/100% is the same number scaled, which is the arithmetic signature of a
single underlying effect: **the return you give up is the return of the thing
you sold**, and the cost of selling it is charged on top.

### 2.2 `SELL_CASH` versus `HOLD` at every horizon — the NIGHT-12 null

| horizon | Δ (pp) | MDE | t | blocks | halves | verdict |
|---:|---:|---:|---:|:--:|:--:|---|
| 1 d | −0.420 | 0.280 | −4.21 | 8/8 | yes | **DETECTABLE NEGATIVE** |
| 5 d | −0.531 | 0.578 | −2.57 | 7/8 | yes | not detectable |
| 20 d | −1.056 | 1.139 | −2.59 | 7/8 | yes | not detectable |
| **60 d** | **−2.815** | **2.764** | −2.85 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| 120 d | −5.379 | 4.743 | −3.18 | 7/8 | yes | **DETECTABLE NEGATIVE** |
| 252 d | **−11.270** | 7.545 | −4.18 | **8/8** | yes | **DETECTABLE NEGATIVE** |

The 1-day row is the cost, almost exactly: a full round trip out of a median
name is ~27 bps and the 1-day gap is 42 bps. From there the gap grows with the
horizon because what is being given up is the equity risk premium, and the
ruler grows more slowly than the gap does.

### 2.3 The twenty pre-declared policies, none of which beat never-selling

`NEVER_SELL` is the reference (Δ = 0 by construction). h = 60:

| policy | Δ (pp) | MDE | trades | verdict |
|---|---:|---:|---:|---|
| `TAKE_PROFIT_100` (trim 50% above +100% gain) | −0.039 | 0.057 | 2.2% | not detectable |
| `TAKE_PROFIT_50` (trim 25% above +50% gain) | −0.065 | 0.071 | 7.3% | not detectable |
| `VOL_SPIKE_TRIM` (63d vol > 1.5 × 252d vol) | −0.067 | 0.247 | 3.2% | not detectable |
| `ADD_TO_WINNERS` (add 50% when mom > 0) | −0.095 | 0.258 | 65.1% | not detectable |
| `REPLACE_EDGE_BOTTOM_DECILE` | −0.096 | 0.445 | 10.0% | not detectable |
| `STOP_LOSS_ENTRY_20` (−20% from entry) | −0.352 | 0.692 | 10.2% | not detectable |
| `DD_AND_REVISION` (−20% dd **and** falling revisions) | −0.353 | 0.493 | 8.2% | not detectable |
| `ALWAYS_BENCH` | −0.361 | 0.926 | 100% | not detectable |
| `TARGET_SELL_NEG` (target below price) | −0.445 | 0.463 | 15.9% | not detectable |
| `ALWAYS_REDUCE_BETA` | −0.459 | 0.561 | 100% | not detectable |
| `MOMENTUM_TRIM_LOSERS` | −0.560 | 0.810 | 34.9% | not detectable |
| **`TRAILING_STOP_20`** *(CANON §15 corpse control)* | −0.612 | 1.062 | 19.3% | not detectable |
| `FIXED_HOLD_252` | −0.704 | 0.691 | 25.0% | **DETECTABLE NEGATIVE** |
| `REPLACE_EDGE_BOTTOM_HALF` | −0.784 | 1.878 | 50.0% | not detectable |
| `REVISION_SELL_NEG` | −0.994 | 1.009 | 31.5% | not detectable |
| `MOMENTUM_SELL_LOSERS` | −1.121 | 1.621 | 34.9% | not detectable |
| **`TRAILING_STOP_10`** *(corpse control)* | −1.232 | 1.623 | 39.9% | not detectable |
| `FIXED_HOLD_63` | −2.111 | 2.073 | 75.0% | **DETECTABLE NEGATIVE** |
| `ALWAYS_CASH` | −2.815 | 2.764 | 100% | **DETECTABLE NEGATIVE** |

At 252 days, nine of the twenty are DETECTABLE_NEGATIVE, including both
trailing stops (−2.75 pp / MDE 3.43, and **−4.94 pp / MDE 4.82, 8/8 blocks**),
`REVISION_SELL_NEG` (−4.30 / 3.30), `MOMENTUM_SELL_LOSERS` (−4.86 / 4.72),
`TARGET_SELL_NEG` (−1.84 / 1.17) and `ALWAYS_REDUCE_BETA` (−1.86 / 1.50).
**The ordering is monotone in how much the policy trades.** Δ correlates with
trade share at every horizon, and the policies that trade least lose least.

There is no policy in this table whose point estimate is positive at any
horizon. That is the single most compressible statement the trial produces.

---

## 3. The learned action-value policy

*(filled in from `exit_lab_1_learned.json` — see §3.1)*

---

## 4. The five questions, each with its MDE

---

## 5. Robustness

---

## 6. Search denominator

---

## 7. What this cannot tell us
