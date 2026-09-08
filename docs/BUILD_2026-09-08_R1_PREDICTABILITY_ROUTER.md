# BUILD 2026-09-08 — R1: THE PREDICTABILITY ROUTER

**Licence:** `PRODUCT_EXPERIMENT` (explore dirty). No order, no seal, no deploy,
no push. $0 spent on DeepSeek — this lane uses no LLM at all.
**Code:** `scripts/predictability_router_r1.py` (label, walk-forward, book,
nulls), `..._r2.py` (ceiling, deciles, inverse, engine routing), `..._r3.py`
(the mechanism), `..._r4_ensemble.py` (the side observation).
**Tests:** `backend/tests/test_predictability_router_r1.py` — **13 passed** (12 + the receipt pin, which skips when the lane has not been run).
**Receipts:** `backend/data/optimus/predictability_router/`
`R1_router_receipt.json` · `R1_router_stage2_receipt.json` ·
`R1_router_stage3_receipt.json` · `R1_side_ensemble_receipt.json` ·
`R1_within_decile_ic_by_era.json` · `R1_size_neutralised_scalefree.json`.

The six JSON receipts above are the committed evidence. Three parquets are
written beside them and are **not committed** — `*.parquet` is gitignored at
`.gitignore:63` — so they are named here as rebuildables, not as receipts:
`router_panel_v1.parquet` (124 MB, ~80 s to rebuild with
`python -m scripts.predictability_router_r1 --force-panel`),
`router_scores_v1.parquet` (10.6 MB, ~50 s via
`scripts.predictability_router_r2`), and `R1_arm_series.parquet` (68 KB, every
arm's monthly net series, so any number in this document can be re-graded — it
is small enough to commit if the lead session wants the re-grade path, and that
is the lead's call, not mine).

---

## RESULTS SCOREBOARD

| line | value |
|---|---|
| **Best historical net strategy vs the market (this lane)** | unchanged for capital purposes. The lane's own books are the existing engines; the routed versions are worse than the unrouted ones in 31 of 36 cells |
| **Best forward paper strategy** | untouched |
| **Independent selector count** | unchanged (0 added) |
| **New actionable finding** | **YES, and it is a mechanism finding, not a P&L finding:** predictability is forecastable out of sample (within-decile rank IC 0.046 → 0.142, t 7.03, Holm-clean; the primary engine's spread clears its own MDE in all three eras, the other three engines' are 2022-2024 regimes) but **abstaining on it does not buy terminal wealth** (0 of the 36 declared cells survive Holm, 0 survive the BH-FDR screen, and 31 of 36 are outright worse than always trading). An oracle that abstains on the realised label buys **+26.5%/yr**, so the mechanism is not empty — our forecast of it does not survive the truncation to the traded region. Caveat printed in the same breath: **`abs_u_c` alone beats the fitted router on the scale-free metric (+0.192 vs +0.096)**, so most of what is forecastable is the engine's own rank extremity, which is constant inside a top-50 book |
| **RESULT IMPROVEMENT** | **NONE in terminal wealth.** The improvement is in what is now known and receipted |
| **LLM spend** | **$0.00** |
| **Tests** | baseline at lane start **7,409 passed / 1 failed / 20 skipped** — the failure inherited: `test_signal_reachability::test_every_orphan_is_classified`, seven unclassified `backend.strategy.*` modules from another agent's S lane. Final full run on the shared tree: **7,610 passed / 2 failed / 20 skipped** (the count grew by ~200 because three other agents landed lanes during the 19 minutes). **Both failures pass in isolation on re-run** — the inherited one because its owner classified the modules while my suite was running, the second (`test_guard_missing_input_contract::test_every_guard_is_enrolled`) with no reproduction at all. I am not claiming a green suite from that: a suite run against a tree three agents are writing to is not a clean measurement, and the honest statement is **this lane's 13 tests pass and neither failure is reachable from anything this lane changed** (no `backend/` module was added; everything here lives under `scripts/`, which `signal_reachability` treats as a seed) |

---

## 1. THE QUESTION, AND WHY IT IS A DIFFERENT QUESTION

Every engine here has been asked *"what will this stock do?"* and killed when it
failed universally. This lane asks **"is this name predictable RIGHT NOW, and by
which engine?"** — predictability as a modelled quantity that varies by name and
by state. It matches the standing belief that strategies are situational, not
universal, and it is the only version of that belief with an executable test.

## 2. THE LABEL

For engine `e`, month `m`, name `i`:

```
u = cross-sectional percentile rank of the engine's prediction        in (0,1)
v = cross-sectional percentile rank of the realised excess return     in (0,1)
s_e(i,m) = 12 * (u - 1/2) * (v - 1/2)
```

The `12` is `Var(U(0,1))^-1`, so **the cross-sectional mean of `s` over a month
is that month's Spearman rank IC.** Verified numerically against `scipy` for all
four engines over all 107 months: max absolute gap **3.05e-4** (lgbm_clf),
**3.7e-7** (the other three), correlation **0.99999991**
(`R1_router_receipt.json::label_identity_check`).

The label is therefore a *decomposition of the metric the house already grades
on* — one cell's contribution to the month's IC — not a new metric invented for
this lane. Return used: `excess_vw_1m`. (Within a month `mkt_vw_1m` is a
constant, so ranks of `fwd_1m` and `excess_vw_1m` are identical; the choice is
cosmetic and is stated so nobody has to check.)

**What the label is NOT.** Not "this stock is easy to forecast in the absolute".
Not "this stock will go up". Not volatility. Not a confidence the engine
emitted. Not a claim about any engine other than the one it is computed for.

**The direction firewall — the design decision that makes this a router and not
another alpha model.** In a long-only top-k book every selected name has
`u > 1/2`, so `s` collapses to `v`, and *any* cell score that improves such a
book is mathematically a return forecast restricted to the top of the ordering.
So the primary feature set is direction-neutral by construction: magnitudes,
dispersions, densities, and the routed engine's own centred rank. A contrast set
with the signed features is run beside it and reported as exactly that.

## 3. THE FEATURES, AND THE PIT ARGUMENT FOR EACH

All features are read at `entry_date` — the month's formation date — from the
learner's own PIT panel (`train_table_long.parquet`, 925,757 name-months) plus
`features_price.parquet` merged on the **exact** `entry_date` (hit rate 99.93%
for `attention_z`, 99.98% for `amihud_21d`, 98.20% for the 52-week proximities)
plus new SEC Form 4 features built here.

| feature | PIT justification |
|---|---|
| `log_coverage`, `numest`, `dispersion`, `disagreement` | IBES consensus state as of the formation vintage; already vintage-stamped in the learner panel |
| `vol_20d`, `vol_60d`, `log_dollar_vol_20d`, `amihud_21d` | trailing realised windows ending before `entry_date` |
| `log_market_cap` | close × shares at the formation date |
| `attention_z`, `attention_z_5d` | the repo's volume-attention z-score, trailing |
| `abs_ret_1m/3m`, `abs_mom_12_1`, `dd_60d_mag`, `range_52w` | trailing magnitudes; the absolute value is what makes them direction-neutral |
| `abs_net_rev_4w`, `abs_upside` | revision and target-gap **magnitude**, not sign |
| `ins_activity_90d`, `ins_buy_90d`, `ins_sell_90d`, `ins_opp_buy_90d`, `ins_cluster_90d`, `ins_any_90d` | **new today.** SEC Form 4 bulk sets (`insider_events_v1.parquet`, 3,127,624 events, 2,439,106 with a permno, link rate 0.7799). Counted over the **strict** half-open window `[entry_date − 90d, entry_date)`: `observed_at_utc` is the *filing day's end* per the parquet's own receipt, so a filing stamped on the formation day is not knowable at formation. Pinned by `test_insider_window_is_strictly_before_the_formation_day`. Coverage: 53.2% of cells carry ≥1 filing in 90 days, 4.4% an opportunistic buy, 3.9% a cluster buy |
| `engine_disagree` | s.d. of the four engines' centred cross-sectional ranks — all four predictions exist at `entry_date` |
| `abs_u_c` | magnitude of the routed engine's own centred rank |
| `u_c` (FS_A only) | the routed engine's **signed** rank. This is the engine's output, not an independent view of direction — the router is allowed to know what the engine said, because that is the question |

Feature sets: **FS_A** 28 (primary), **FS_A0** 27 (drops `u_c`), **FS_B** 43
(adds signed momentum, revisions, upside, 52-week proximities, net insider buys),
**FS_S** 26 and **FS_S0** 25 (stage three: no rank term of any kind).

**13F/ownership was not used.** `I2` has not landed; there is no 13F table in
this repo to read. Recorded as absent, not as tried.

## 4. THE WALK-FORWARD

Engines' out-of-sample predictions exist for **2016-01 → 2024-11** only
(107 months, 332,092 (name, month) cells after the inner join, mean 3,103.7
names per month). Expanding window, **annual refit**, purge/embargo **2 months**
before each test year (`fwd_1m` matures about one month out; two leaves a
spare). First test year **2017**, so the graded window is **95 months,
2017-01 → 2024-11**. Never random k-fold; pinned by
`test_walk_forward_never_trains_on_a_month_it_tests`.

**The era grid is declared, not borrowed.** `learner.evaluate.ERAS` is
2016-2018 / 2019-2021 / 2022-2024, and its first window *cannot* be tested here
because 2016 is the router's only training data. An era that can only ever be
empty is a gate that cannot go green, so the grid is renamed:

```
ROUTER_ERAS = {"2017-2018": 24 months, "2019-2021": 36, "2022-2024": 35}
```

**The book.** Top-50, value-weighted, 10 bps per side on **measured weight
turnover**, both sides — `learner.evaluate.book`'s conventions, including its
seeded `(permno, month)` tie-break (never permno-ascending: that is listing age,
and the farm's oldest-listings null beat 13 of 15 real signals). `routed_book`
reproduces `evaluate.book` **to 1.4e-17 on every monthly return** when nothing
is abstained — pinned by test. Abstention replaces a slot with the market held
as a real instrument (permno −1) that **pays the spread on entry and exit**; a
free abstention would flatter every routed book.

## 5. RESULT ONE — PREDICTABILITY IS FORECASTABLE (survives Holm), BUT MOST OF THE FORECASTABLE PART IS THE ENGINE'S OWN RANK EXTREMITY

Stage one's out-of-sample score, correlated with the realised label
cross-sectionally, month by month, n = 95 **months**:

| engine × feature set | mean xs Spearman | t across months |
|---|---|---|
| lgbm_clf / FS_A | 0.0895 | 7.95 |
| lgbm_clf / FS_B | 0.0868 | 7.91 |
| lgbm_clf / FS_A0 | 0.0814 | 8.15 |
| encoder_clf_resid / FS_A | 0.0837 | 7.31 |
| mlp_raw / FS_A | 0.0781 | 7.51 |
| ridge_raw / FS_A | 0.0858 | 8.38 |

The label's own decile table is steeply monotone — but the label carries the
mechanical `|u_c|` term, so the **scale-free** version is the one that counts:
the ordinary Spearman IC *inside* each decile of predicted skill.

**Within-decile rank IC, `lgbm_clf`, whole cross-section, 95 months:**

| decile of predicted skill | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| realised rank IC | 0.046 | 0.026 | 0.028 | 0.023 | 0.041 | 0.045 | 0.065 | 0.085 | 0.127 | **0.142** |
| t across months | 3.85 | 2.69 | 2.86 | 2.26 | 3.45 | 3.50 | 4.81 | 5.37 | 7.08 | 10.55 |

Top minus bottom **+0.0963, t 7.03, MDE(80%) 0.0384** — three times the MDE.
Replicated on all four engines (+0.092 t 5.80; +0.085 t 5.50; +0.108 t 6.76),
**all four survive Holm** in the stage-three family of 10. The table is not
perfectly monotone: decile 1 sits above deciles 2-4 (Spearman of decile index
vs realised IC = 0.78, not 1.0). Reported as it is.

**THE THREE-ERA TABLE, on the scale-free spread** (top-minus-bottom
within-decile rank IC; each cell against its own 80% MDE — the receipt is
`R1_within_decile_ic_by_era.json`):

| engine | 2017-2018 (24m) | 2019-2021 (36m) | 2022-2024 (35m) |
|---|---|---|---|
| **lgbm_clf** (primary) | **+0.078** t 3.09 (MDE 0.070) ✓ | **+0.103** t 4.05 (MDE 0.071) ✓ | **+0.102** t 4.96 (MDE 0.058) ✓ |
| encoder_clf_resid | +0.020 t 0.65 (MDE 0.085) ✗ | +0.093 t 3.15 (MDE 0.083) ✓ | +0.141 t 7.29 (MDE 0.054) ✓ |
| mlp_raw | +0.043 t 1.73 (MDE 0.069) ✗ | +0.047 t 2.32 (MDE 0.057) ✗ | +0.154 t 5.22 (MDE 0.083) ✓ |
| ridge_raw | +0.061 t 2.29 (MDE 0.075) ✗ | +0.043 t 2.24 (MDE 0.054) ✗ | +0.206 t 7.64 (MDE 0.076) ✓ |

**The primary engine's router clears its own MDE in all three eras — that is a
finding. The other three are era-concentrated in 2022-2024 — those are
regimes**, and every engine's spread is largest in the last era, so a
regime-drift reading of the whole table cannot be excluded from 95 months.
(The *label* decile spread — which still carries the `|u_c|` term — is larger and
cleaner in all three eras: 0.229 t 4.59 · 0.310 t 3.82 · 0.538 t 11.58, all above
their MDEs. That is the flattering version and it is not the one this section
rests on.)

**IS "PREDICTABLE" JUST "SMALL-CAP" WEARING A NEW NAME?**  This has to be
answered rather than waved at, because a cross-lane measurement taken on the
live fleet the same day says a small-cap factor dominates this universe: hack3
and hack6 share only **3 of 22 names (Jaccard 0.14)** yet their equal-weighted
returns correlate at **rho 0.719**, and over 380 sessions both load more on IWM
(0.75, 0.77) than on SPY (0.61, 0.68).  Whatever those two books think they are
selecting, size is doing a large part of the work, and the router's raw score
does lean the same way (ρ −0.259 with log market cap — the router calls
**small**, **volatile** (+0.220), **thinly covered** (−0.205) and **less liquid**
(−0.236) names the more predictable ones, which is the opposite of the naive
prior but is still a size tilt).

Three measurements, receipted in `R1_size_neutralised_scalefree.json`, and they
do not all point the same way:

| score used for the decile split | within-decile IC, D1 → D10 | top−bottom | t | MDE(80%) |
|---|---|---|---|---|
| the raw router (FS_A) | 0.046 → 0.142 | +0.096 | 7.03 | 0.038 |
| **−log market cap alone** ("small = predictable") | 0.029 → 0.112 | **+0.083** | 5.01 | 0.046 |
| router, residualised on log market cap | 0.047 → 0.188 | **+0.140** | 10.30 | 0.038 |
| router, residualised on size + vol + coverage + dollar volume | 0.058 → 0.193 | **+0.135** | 9.55 | 0.040 |

1. **Size alone really does route.** A rule that says nothing but "small names
   are more predictable" recovers +0.083 of the raw router's +0.096. The
   coordinator's worry is a real ingredient, not a phantom.
2. **But the finding is not size.** Removing the linear size component makes the
   router **better**, +0.096 → +0.140 (t 7.03 → 10.30) — size was *diluting* the
   signal, not carrying it. The monthly cross-sectional R² of the score on all
   four columns is only **0.179**; 82% of it is something else.
3. **"Orthogonal to size" would be too strong.** The neutralisation is a linear
   OLS on z-scores and the underlying relation is not linear: the residual's
   rank correlation with log market cap is **+0.218** — the sign has flipped, so
   the fit over-corrects. The defensible sentence is *"the linear size component
   has been removed and what is left routes better than the original"*, not
   *"size has been eliminated"*.

Residualising and re-routing the **book** changes nothing that matters:
−0.89%/yr (t −0.52) against −1.64%/yr (t −0.81) for the raw router. The size
question is decisive for the stage-one claim and irrelevant to the stage-two
one, because stage two has no gain to explain away.

**What it IS, in large part:** the router score's Spearman with `abs_u_c` is
**+0.523**, and `abs_u_c` is its top feature by split importance (740, ahead of
`engine_disagree` 574 and `u_c` 554). A state-only router with no rank term at
all (`FS_S0`, 25 features) still separates: within-decile IC spread **+0.0287,
t 2.37** — but that is *below* its own 80% MDE of 0.0340, so it is a positive
that the study was not powered to find, and is flagged as such. `FS_S`
(26 features, keeps `engine_disagree`) gives +0.0434, t 3.85, MDE 0.0316 —
above its MDE.

**And the uncomfortable comparator, printed because it is the honest one:**
`|u_c|` used ALONE as the routing score — one free variable, no model, no
features, no fitting — gives a within-decile IC spread of **+0.192 (t 9.41)**,
**twice** the fitted 28-feature router's +0.096. Same on every engine: +0.212
(t 12.12), +0.186 (t 12.25), +0.180 (t 11.03). Part of that is a range effect
(the top decile of `|u_c|` is the union of both tails of the engine's ordering,
and an IC computed inside a group that spans both tails is mechanically higher),
but it cannot be waved away: **on the scale-free metric, the fitted router is a
worse version of "trust the engine most where its ranking is most extreme."**
The state-only routers, which cannot use that variable at all, are what the
"predictability is a state" claim actually rests on, and they are three to four
times smaller.

## 6. RESULT TWO — ABSTENTION DOES NOT BUY TERMINAL WEALTH

**Primary cell, declared before fitting** (engine chosen on the router's
*training* months only, so it carries no full-sample look: 2016 rank IC
lgbm_clf 0.0583 > mlp 0.0427 > ridge 0.0357 > encoder_clf_resid 0.0301):
`lgbm_clf__1m` / `FS_A` / abstain 30% of the top-50.

**Beta first.**

| arm | β | β t | α ann. | α t | TW net | TW market | maxDD | maxDD mkt |
|---|---|---|---|---|---|---|---|---|
| always trade | **1.132** | 12.69 | +5.72% | 0.93 | 6.170 | 3.723 | −42.9% | −33.3% |
| route + abstain 30% | **1.074** | 13.57 | +5.15% | 0.95 | 5.652 | 3.723 | −37.3% | −33.3% |
| market (VW, same 95 months) | 1 | — | 0 | — | 3.723 | 3.723 | −33.3% | −33.3% |

**Against always-trade** (paired monthly difference, n = 95 months):
**−1.64%/yr, t −0.807, p 0.42**, share of months ahead 42.1%.

**Against the market** (the "vs SPY" line; the benchmark is the VW market return
`mkt_vw_1m`, which is what the panel carries — not the SPY ETF, and the
difference matters at the second decimal, so it is named rather than implied):
routed **+6.54%/yr, t 1.251, p 0.214**, MDE(80%) **14.65%/yr**; always-trade
**+8.19%/yr, t 1.379**. Both books beat the market's terminal wealth (5.65 and
6.17 against 3.72) and **neither does so significantly, and neither has a
significant alpha once β is taken out** (α t 0.95 and 0.93). Over 2017-2024 a
β-1.1 long-only book beating a bull market is a loading, not a result — this is
the S43 ruler and it binds here.

**POWER CHECK, RUN BEFORE THE VERDICT (CANON §64).** With 95 months and the
observed s.d. of the paired difference (1.653%/month), the **MDE at 80% power,
5% two-sided is 5.70%/yr**. So this test could only ever have separated a gain
of about six points a year. It excludes a large gain; it does **not** exclude a
small one. Every cell in the sweep carries its own MDE in the receipt.

**The whole sweep** (36 cells: 4 engines × {FS_A, FS_B} × q ∈ {10,20,30,50}%,
plus FS_A0 × 4 on the primary engine). **5 of 36 cells positive**, median
−1.45%/yr; sign test p = 1e-05 against 50/50. Family min p **0.00904**
(`encoder_clf_resid / FS_A / q30`, and that cell is a **harm**: −4.69%/yr,
t −2.67). Holm-adjusted **0.325 — nothing survives**. BH-FDR at q = 0.10 —
**nothing survives the screen either**. DSR on the primary routed book against
its own 36-trial family: Sharpe 0.2886/month, expected-max-noise 0.1499,
**DSR 0.890, does not clear 0.95**.

## 7. THE TWO NULLS, AND WHY THEY MATTER MORE THAN THE SWEEP

**Null A — random abstention, matched count** (200 draws, same 15 slots a month,
seeded): mean **−0.00245/month = −2.94%/yr**, s.d. 0.00184. **Abstention itself
is expensive.** The observed routed arm (−0.00137) sits at the **75.5th
percentile** of that null (one-sided p 0.245).

**Null B — the router trained on labels permuted within the date block** (10
draws, identical universe, features, splits, model, costs): mean **−0.00214**,
s.d. 0.00116, one-sided p 0.200. A shuffled router loses about as much as a
random one, as it must.

**The inverse arm** (abstain on the *highest* predicted skill), stage two:
**−7.15%/yr, t −2.26** for lgbm_clf; −11.9%/yr t −2.38 for encoder_clf_resid.

So the ordering across the three abstention rules is monotone and in the right
direction:

```
forward routing  −1.64%/yr   >   random  −2.94%/yr   >   inverse  −7.15%/yr
```

**The router has real information inside the traded region. It is simply smaller
than the drag of holding the benchmark in those slots.** That is a sharper
statement than "abstention does not work", and it is the one the evidence
supports.

## 8. THE CEILING, AND WHERE THE INFORMATION DIES

**Oracle abstention** — the same book, abstaining on the *realised* label. Future
information; not a strategy; a bound only:

| engine | oracle vs always trade | t |
|---|---|---|
| lgbm_clf | **+26.45%/yr** | 8.06 |
| encoder_clf_resid | +19.81%/yr | 7.93 |
| mlp_raw | **+47.99%/yr** | 10.10 |
| ridge_raw | +36.68%/yr | 8.34 |

There is a very large amount to win. Stage one captures essentially none of it,
and stage three says why.

**Inside the traded region, `|u_c|` stops varying.** Across the whole
cross-section the s.d. of `|u_c|` is **0.1443**; among the top 50 by engine rank
it is **0.0047** — a factor of 31. The router's single most important feature is
constant in exactly the place the book has to choose.

**The traded-region table** (top-50 by `lgbm_clf`, quintiles of router score,
95 months). The label column is what the router was trained on; the **excess
return** column is what the book actually spends:

| quintile | realised IC contribution | realised excess return | t |
|---|---|---|---|
| 1 (lowest predicted skill) | 0.139 | +0.11% | 0.14 |
| 2 | 0.193 | −0.04% | −0.08 |
| 3 | 0.182 | +0.34% | 0.57 |
| 4 | 0.164 | +0.60% | 0.91 |
| 5 (highest) | 0.337 | **+1.37%** | 2.14 |
| **5 − 1** | +0.198 (t 2.40) | **+1.26%/month (t 1.78, p 0.079)** | MDE 2.00%/month |

The best of the four engines, and it does not clear — and the other three are
−0.23% (t −0.22), +0.20% (t 0.14), +0.84% (t 0.59). **0/4 survive Holm** in the
stage-three family. The lgbm_clf cell is the only one that even reaches the
BH screen boundary, and it misses it.

**State-only routers, same book:** `FS_S` −1.72%/yr (t −0.70, MDE 6.93%/yr);
`FS_S0` −1.16%/yr (t −0.46, MDE 7.14%/yr).

## 9. ENGINE ROUTING (the "which engine" half)

Per name-month, pick the engine with the highest predicted skill and score the
book with that engine's rank. Choice shares: lgbm_clf 33.5%, encoder_clf_resid
27.2%, ridge 19.7%, mlp 19.6% — the router does not collapse onto one engine.

| arm | TW net | β | α ann. | α t |
|---|---|---|---|---|
| routed engine | 9.39 | 1.245 | +9.18% | 1.76 |
| **equal-weight rank ensemble of all four** | **22.09** | 1.187 | +22.69% | 2.49 |

Routed minus the ensemble: **−12.43%/yr, t −1.58** (MDE 22.1%/yr — underpowered,
so this is not "the ensemble is proven better", it is "routing did not beat the
comparator and the test could not have seen a small difference either way").
Against each single engine the routed arm is +5.6% / −6.8% / +8.4% / +1.7%/yr,
all |t| < 1.3. **Engine routing is not earned.**

## 10. A SIDE OBSERVATION THAT IS NOT A CLAIM

The comparator beat the thing it was built to measure, so it got its own receipt
(`R1_side_ensemble_receipt.json`, family of 18 cells enumerated before the run).
The mean of the four engines' cross-sectional **ranks** — no new information, no
fitting, no weights — makes a top-50 VW book with TW **22.09** against a market
TW of 3.723 over the same 95 months, CAGR 47.8% vs 18.1%, β 1.187, α +22.7%/yr
t 2.49, maxDD −36.8% vs −33.3%. It survives 25 bps (TW 17.64) and the $3m/day
execution floor (TW 24.67, α +23.4%/yr t 2.77). Its rank IC (0.0981) is **not**
higher than the best single engine's (0.1016) — the gain is entirely at the top
of the ordering, which is the only part a top-k book touches.

**Four reasons it is an observation and not a result, all of them binding:**

1. **0 of 18 cells survive Holm** (min p 0.0141, Holm 0.253); 0 survive BH-FDR
   at q = 0.10.
2. **The alpha lives entirely in the value weighting.** Every `ew` and `rank`
   weighted cell has α between −1.7% and −5.5%/yr with β ≈ 1.40-1.42. Only the
   `vw` cells show α > 0. This has the shape of the house's own
   "an EW average against a VW market is the regime" lesson, and here it points
   the other way: the VW book is the matched comparison and the EW books carry
   an unmatched small-cap tilt.
3. **No era clears alone**: α t = 0.55 (2017-18) / 1.72 (2019-21) / 1.71
   (2022-24) — and the last era's **β is 2.30**, which is a loading story about
   2022-2024, not an alpha story.
4. It is **post-hoc**. It was found while building a control.

It is nonetheless the cheapest thing on the board relative to the standing
bottleneck (ten books, one alpha source), and it deserves its own pre-registered
lane rather than a paragraph here.

## 11. WHAT DID NOT WORK, AND WHAT I GOT WRONG

- **Abstention as a wealth mechanism**: 0/36, and the drag is measured
  (−2.94%/yr for *any* 30% abstention). `FAILED_VARIANT` for
  `abstain-to-benchmark on a monthly VW top-50`, not `MECHANISM_REJECTED` for
  routing — the traded-region test is underpowered by a factor of ~1.6.
- **Engine routing**: not earned; loses to a comparator that makes no choice.
- **FS_B (the signed contrast) did not rescue anything** — it is *worse* than
  FS_A on the primary engine (two of its cells are the sweep's second- and
  third-smallest p-values, both harms). The direction firewall cost nothing.
- **My first DSR was a gate that could not go green.** It reported
  `expected_max_noise_sharpe = 2.1475` per **month** for a 36-trial family,
  because it omitted the `sqrt(V)` scaling and returned SR0 in units of standard
  normals. No strategy in any universe clears a monthly Sharpe of 2.15, so the
  DSR was structurally 0.0. Fixed to use the variance of the family's own
  Sharpes (SR0 = 0.1499, DSR 0.890) and documented in the docstring.
- **`routed_book` originally fell through to the engine's own bottom ranks**
  when given neither a score nor a seed — it now **REFUSES**, because that
  silent fallback would have made the router look like it did something the
  engine did.
- **13F/ownership features were not built** — there is no 13F table in this repo
  yet (roadmap `I2` is open). Absence, not a negative.
- **`beta_panel.parquet` was not used.** Beta here is the time-series loading of
  the book's monthly net on `mkt_vw_1m`, which is what "beta printed first"
  means for a book. Per-name ex-ante beta is a different question and was left
  alone.

## 12. FAMILY ACCOUNTING (invariant 16 — every cell LOOKED AT is charged)

| family | cells | min p | Holm survivors | BH-FDR q=0.10 survivors |
|---|---|---|---|---|
| `R1-ABSTAIN` (stage 1) | 36 | 0.00904 | 0 | 0 |
| `R1-STAGE2` (inverse, engine routing, decile spreads) | 9 | 0.0 | 4 (the four decile tables) | 4 |
| `R1-STAGE3` (within-decile IC, traded region, state-only books) | 10 | 0.0 | 4 (the four within-decile IC spreads) | 4 |
| `R1-SIDE-ENSEMBLE` | 18 | 0.01409 | 0 | 0 |
| **total looked at** | **73** | | **8, all of them stage-one skill tests, none of them a book** | |

Not charged as separate cells but recorded as looks: 4 engines' full-sample rank
ICs (read before the primary engine was fixed on the training window only), the
`|u_c|`-alone comparator tables, the four size-neutralisation splits of §5, the
per-era within-decile splits, and the feature-importance fit. None of these is a
book; all of them are diagnostics on a metric that was already computed.

## 13. WHAT WOULD MOVE THIS NEXT (gates, not dates)

1. **Test the router where `|u_c|` still varies.** A long-**short** book, or a
   top-k drawn from a much wider slice, keeps the router's main axis alive. The
   present result is specific to a long-only top-50, which is the one geometry
   that kills the router's best feature. This is the single highest-value
   follow-up and it is one `run_one` call away once `S1` exists.
2. **Abstain into cash or a hedge instead of the benchmark.** The −2.94%/yr drag
   is the cost of holding a β-1.0 instrument in a slot that would otherwise hold
   a β-1.13 book in a bull decade. That drag is a *choice of destination*, not a
   property of abstention.
3. **Size the position on predicted skill instead of dropping it.** Continuous
   weighting uses the whole decile table rather than only its bottom tail, and
   the decile table is the part that clears Holm.
4. **The ensemble lane, pre-registered**, with the value-weight confound as the
   pre-declared primary control.
5. **More engines.** The router's second feature is `engine_disagree`, which is
   nearly saturated at four correlated engines.
6. **Carry the size control into every downstream use.** The live fleet's own
   books load more on IWM than on SPY (hack3 0.75 vs 0.61, hack6 0.77 vs 0.68,
   380 sessions) while sharing 3 names in 22, so *any* selector in this universe
   has to print its size-neutralised version beside its raw one. This lane's
   scale-free finding survives that; a future lane's may not, and the check now
   costs one function call (`predictability_router_r1.neutralise`).

---

*Nothing in this document is a `CAPITAL_CANDIDATE` or a `RESEARCH_CLAIM`. The
only Holm-clean statements are stage-one skill tests, and a skill test is not a
book.*
