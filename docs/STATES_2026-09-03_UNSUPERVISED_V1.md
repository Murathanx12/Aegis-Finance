# STATES v1 — unsupervised market states, and what they do and do not condition

**Licence: `PRODUCT_EXPERIMENT`.** Places nothing, recommends nothing, has no
broker path. Receipt:
`backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json`.
Code: `learner/states.py`, `scripts/learner_states_run.py`,
`backend/tests/test_learner_states.py` (13 tests, offline, ~14s).
Assignments: `backend/data/optimus/learner/states/` (parquet, untracked — see
`DATA_MANIFEST.md`).

---

## RESULTS SCOREBOARD

| | |
|---|---|
| **New actionable finding** | **4 stable states, and they clear a within-month shuffled null at every k (p = 0.000).** Inside the dominant band `lt_1_5` — 242,440 rows, where the engine says ONE constant — the states *still* separate returns (spread 0.01415 vs null p95 0.00649, p = 0.000). They are not the band prior wearing a new coat. |
| **The money question** | **Partly yes.** `lgbm_clf` is the only arm established in all four states (worst state t 3.20). `mlp__raw`, `ridge__raw`, `lgbm__raw`, `lgbm__residual` all collapse in state 1 — **half the panel**. Inside `lt_1_5` with the band held fixed, `mlp__raw` is **+0.029 (t 2.05)** in state 2 and **−0.011 (t −0.87)** in state 3. That is the mixture-of-experts foundation. It is real and it is small. |
| **RESULT IMPROVEMENT to the book** | **NONE.** No state has a positive forward excess. Nothing here was traded, sized, or seeded. |
| **Independent selector count** | unchanged. This is a *conditioner*, not a selector. |
| **Market-regime layer** | **NOT TRUSTWORTHY at n = 120 months.** The 3–5 band's premium is not regime-conditional (p = 0.698), and the shuffled-**target** null arm scores t 2.72 inside one market regime. |
| **Autoencoder** | **NOT KEPT.** Spread 0.00996 vs PCA+KMeans 0.01332, at ~10× the runtime. |
| **LLM spend** | **$0.00.** No model was called. |

---

## 1. What was built, and the one property that makes it worth reading

Two halves, and a line between them that is enforced in code rather than
promised in prose:

```
FITTING SIDE     RobustScaler(train median/IQR) -> clip ±5 -> PCA(8)
                   -> KMeans  (the state)
                   -> GaussianMixture  (a second opinion)
                   -> IsolationForest  (an anomaly score)
                   -> NearestNeighbours (3 historical analogues + their outcomes)
                 sees 18 PIT features. Sees NO fwd_*, excess_*, resid_*,
                 prior_*, mat_date_*, mkt_*, pos_*.

------------------------ the contract -------------------------------

GRADING SIDE     may see matured future returns. That is what grading is.
```

`learner.states.assert_no_target_columns` **refuses** a fitting matrix carrying
any of those prefixes; `assert_block_ordering` **refuses** a block whose last
training `entry_date` is not strictly before its first assigned one. Both are
tested in both directions — the guards can go red, which is the only reason to
believe them when they are green.

**The OOS protocol.** 144 months, 24 burn-in, then 20 refit blocks of 6 months.
Block 0 trains through **2014-12-19** and assigns from **2015-01-16**; block 19
trains through **2024-06-21** and assigns from **2024-07-19**. **371,848**
company-vintages over **120 months** were assigned by a representation fitted
only on data strictly before them. Blocked rather than monthly is *more*
conservative, not less: a month in the middle of a block is scored by a fit that
saw even less of the recent past than a monthly refit would have allowed.

**k = 4 was chosen without the target** — argmax mean silhouette on a train-only
subsample of block 0: `{3: 0.289, 4: 0.303, 5: 0.153, 6: 0.161, 8: 0.172}`. Every
other k on the ladder was assigned and graded anyway, so a reader can see the
choice is not load-bearing (the null is cleared at all five).

**PCA(8) explains 93.9%** of the scaled variance; PC1 43.2%, PC2 19.1%.

---

## 2. The four states, and whether they are the same states over ten years

Centroid profiles in scaled units (final block), most extreme features:

| state | share | rows | names | what it is | signature |
|---|---|---|---|---|---|
| **0** | 18.9% | 70,156 | 3,376 | **the broken lottery ticket** | `log_ratio +6.98`, `dispersion +2.22`, `vol_60d +2.47`, `drawdown_60d −2.14`, `log_close −1.46`, `log_market_cap −0.93`, `ret_12m −1.14` |
| **1** | 50.7% | 188,448 | 4,547 | **the ordinary market** — every feature within ±0.4 of the median | nothing is extreme; that is the state |
| **2** | 14.0% | 51,950 | 4,899 | **the knife** — analysts cutting into a selloff | `target_rev_1m −3.53`, `net_rev_4w −2.51`, `ret_3m −1.32`, `drawdown_60d −2.00`, `vol_20d +1.72` |
| **3** | 16.5% | 61,294 | 4,513 | **the upgrade** | `target_rev_1m +3.12`, `net_rev_4w +2.58`, `ret_3m +0.94`, `ret_12m +0.68` |

**They are the same states across refits.** KMeans hands out arbitrary integers,
so each block's centroids are pushed back into a fixed reference space and
Hungarian-matched to the previous block's before anything is stored. Mean
matched-centroid drift is **0.0257** of the typical inter-centroid distance
(max 0.0632) — two orders below the 0.5 bar. All **4 of 4** states are present
above 2% in **every** block. **n_stable_states = 4.**

That matching is not bookkeeping. `test_without_cross_block_matching_the_planted_effect_cancels`
runs the identical loop *without* it and the planted effect collapses by more
than half, because two consecutive blocks named the same group 0 and then 1.
It is pinned as a test so deleting the step names the number it breaks.

**States persist.** Month-over-month, per name, over 365,459 consecutive-month
pairs: mean diagonal **0.4985** against a 0.25 random baseline. The two extreme
states are the sticky ones (0 → 0 = **0.722**, 1 → 1 = 0.667); the two revision
states are transient by construction (2 → 2 = 0.290, 3 → 3 = 0.315) — a name is
being downgraded *this month*, not for a year.

---

## 3. What the states are followed by

Forward **excess over the value-weighted market**. `t` is over MONTHS (date
blocks), never name-months.

| state | 1m mean | 1m monthly-mean-of-means | t | worst-5% tail (1m) | 3m mean | 3m t | 3m tail | P(+20% in 3m) |
|---|---|---|---|---|---|---|---|---|
| **0** broken lottery | −1.47% | **−1.36%** | −1.79 | **−50.7%** | **−4.93%** | **−3.36** | **−75.5%** | **21.7%** |
| **1** ordinary | −0.22% | −0.18% | −0.86 | −25.2% | −0.53% | −1.16 | −40.7% | 14.3% |
| **2** knife | +0.16% | −0.66% | −1.31 | −38.6% | −0.93% | −2.70 | −62.6% | 23.3% |
| **3** upgrade | +0.12% | −0.03% | −0.11 | −25.6% | +0.34% | +0.13 | −43.1% | 17.1% |

**The most economically distinct state is state 0, and it is distinct in three
directions at once**: the worst mean (−4.93% over three months, t −3.36), the
fattest tail (worst 5% averages −75.5% over three months), *and* the **highest
large-upside frequency in the panel** (21.7% of these names are up more than
20% within three months, against 14.3% for the ordinary state). It is a
genuine lottery: it pays off more often than anything else and still loses,
badly, on average. Study losers as hard as winners — this is the loser, and it
is the one with the most winners in it.

**Say the honest thing plainly: no state has a positive forward excess.** All
four monthly means are ≤ 0. This is a VW-excess panel in which the average
*name* underperforms the cap-weighted market, so what the states rank is loss
and tail exposure, not profit. **The discovery is a loss-avoidance ordering.**
Anyone reading it as a long-only selector is reading a different table.

Note also that state 2's pooled row mean (+0.16%) and its monthly mean (−0.66%)
have opposite signs. The monthly figure is the one with a `t` attached and the
one a monthly book earns; the row mean is dominated by the months with the most
names in the state.

---

## 4. The null — do the states beat a random partition?

**Yes, decisively, at every k.** The null permutes the state labels **within
each month**, preserving the month, the per-month state sizes, the calendar and
the return distribution — so it asks "would a random partition of *these*
months look like this?", which is the question S24 learned to ask after a
shuffled-date null turned out to be measuring the calendar.

| k | observed spread | null mean | null p95 | null max (200 draws) | p |
|---|---|---|---|---|---|
| 3 | 0.01082 | 0.00112 | 0.00228 | 0.00318 | **0.000** |
| **4** | **0.01332** | 0.00174 | 0.00310 | 0.00430 | **0.000** |
| 5 | 0.01515 | 0.00253 | 0.00420 | 0.00628 | **0.000** |
| 6 | 0.01589 | 0.00293 | 0.00540 | 0.00694 | **0.000** |
| 8 | 0.02275 | 0.00377 | 0.00601 | 0.00802 | **0.000** |

At k = 4 the observed spread is **3.1× the largest of 200 random partitions**.

The null owes two tests, and it gets them: on a synthetic panel with a planted
group difference the null is cleared; on the same panel with the difference
removed it is not (`p > 0.05`). A null that always fires is decoration; a null
that never fires is a rubber stamp.

### 4b. The control we would not have chosen: hold the band fixed

State 0 is 45% `no_opinion` + 25% `toxic_ge_5`; state 1 is 85% `lt_1_5`. So
every state-conditional number above could be a **band-conditional number in
disguise** — "the prior works in state 0 and not state 1" would then mean only
"state 1 contains one band, and a constant cannot rank a constant."

Held inside one band:

| band | rows | observed spread | null p95 | p | states still separate? |
|---|---|---|---|---|---|
| **`lt_1_5`** | **242,440** | **0.01415** | 0.00649 | **0.000** | **YES** |
| `no_opinion` | 55,475 | 0.01227 | 0.01881 | 0.250 | no |
| `b_1_5_3` | 46,249 | 0.00561 | 0.01253 | 0.515 | no |
| `toxic_ge_5` | 21,537 | 0.01515 | 0.28612 | 0.970 | no (cells too thin to read) |
| `b_3_5` | 6,147 | — | — | — | not tested (too few rows) |

**The one that matters passes.** `lt_1_5` is 55% of the panel and is precisely
the region where BAND_PRIOR v2 says a single constant and S33's Fama-MacBeth
found six simple features empty. Inside it, with the band held fixed, the
states still order the future: state 1 −0.21%/month against state 3 −0.01%,
and P(+20% in 3m) runs 13.3% → 20.0% → 16.7% across states 1, 2, 3. **The
states carry information the band prior does not.**

The other three bands do not clear their own null, and the honest reading is
that they are too small to say — `toxic_ge_5`'s null p95 is 0.286 against an
observed 0.015: a random partition of that band produces a *larger* spread
**97% of the time**. That is a *cannot determine*, not a negative.

---

## 5. Does model reliability vary by state? (the mixture-of-experts question)

Rank IC against `excess_vw_1m`, 107 months, predictions from LEARNER v1's
stored OOS parquet (`sha256_16 38f6eb31890d84a5`).

| model | overall | s0 lottery | s1 ordinary | s2 knife | s3 upgrade | verdict |
|---|---|---|---|---|---|---|
| `prior` (BAND_PRIOR v2) | 0.0713 (t 12.7) | **0.0732** (t 13.9) | **0.0007 (t 0.12)** | 0.0563 (t 5.92) | 0.0182 (t 2.37) | CONDITIONAL |
| **`lgbm_clf`** (v1 champion) | 0.0954 (t 8.21) | 0.0911 (t 10.1) | **0.0328 (t 3.20)** | 0.0870 (t 6.73) | 0.0405 (t 4.13) | **UNIFORM** |
| `mlp__raw` | 0.0777 (t 8.32) | 0.1050 (t 13.8) | **0.0082 (t 0.94)** | 0.0761 (t 5.94) | 0.0046 (t 0.39) | CONDITIONAL |
| `ridge__raw` | 0.0710 (t 6.96) | 0.1002 (t 15.4) | 0.0125 (t 1.72) | 0.0497 (t 4.65) | 0.0254 (t 2.22) | CONDITIONAL |
| `lgbm__raw` | 0.0668 (t 6.56) | 0.0729 (t 9.55) | 0.0153 (t 2.04) | 0.0519 (t 4.13) | 0.0106 (t 1.10) | CONDITIONAL |
| `lgbm__residual` | 0.0652 (t 7.20) | 0.0752 (t 12.0) | 0.0152 (t 1.99) | 0.0537 (t 4.52) | 0.0164 (t 1.93) | CONDITIONAL |
| `rank_upside` | −0.0900 (t −5.69) | −0.1009 (t −11.2) | −0.0058 (t −0.54) | −0.0821 (t −4.81) | −0.0174 (t −1.57) | negative where it is anything |
| **`NULL_shuffled_target`** | 0.0046 (t 0.81) | 0.0045 (t 0.73) | −0.0049 (t −0.78) | 0.0031 (t 0.42) | 0.0060 (t 0.81) | **flat in every state — the table is clean** |

Three readings, in order of how much they are worth:

1. **State 1 is where models go to die, and it is half the panel.** 188,448
   rows, 50.7%. The MLP's IC there is 0.008 (t 0.94), ridge 0.013 (t 1.72), the
   incumbent prior 0.0007 (t 0.12). Every headline IC in `learner_v1.json` is
   an average over a panel in which half the rows carry almost no signal for
   most arms.
2. **`lgbm_clf` is the only arm established everywhere** — its worst state is
   t 3.20. That is a property none of the other five arms has, and it was
   invisible in v1's pooled scoreboard, where `mlp__raw` (0.0777) and
   `ridge__raw` (0.0710) look like near-peers of the champion (0.0954).
3. **The null arm is flat in all four states** (|t| ≤ 0.81). A state table in
   which the shuffled-target null looked skilful would be a broken table; this
   one is not.

**The band-composition caveat, stated rather than buried.** Much of the *prior*
column above is compositional: `mean_distinct_predictions` is 5.0 in state 0
and 3.5 in state 1, because state 1 is 85% one band and a constant cannot rank
a constant. Inside `lt_1_5` the prior becomes *unmeasurable* (one value; the
receipt reports `months: 0, note: too few months to read`, not a zero IC —
absence of a reading is not a reading of zero).

**The ML columns do not have that excuse**, and this is the finding:

> Inside `lt_1_5`, band held fixed, `mlp__raw` scores **+0.0293 (t 2.05)** in
> state 2 and **−0.0107 (t −0.87)** in state 3, while `lgbm_clf` holds
> 0.027–0.033 (all t ≥ 2.5) across states 1, 2 and 3.

An IC range of 0.040 with a sign difference, inside one band, on 107 months, is
a routing signal: it says *send the knife state to the MLP and do not send it
the upgrade state*. It is also modest, single-band, and one comparison among
several — **a `PRODUCT_EXPERIMENT` lead, not a `RESEARCH_CLAIM`.** The next
step is a router trained on this partition and graded on terminal wealth, not
on IC, because IC is not the objective.

---

## 6. The market-level state: what it did not show

Monthly market states from 15 trailing cross-sectional aggregates (dispersion,
breadth, median vol, band shares, revision breadth — no forward market return
is touched; `mkt_vw_1m` in the train table is *next* month's return and is
excluded by the same guard). Strict protocol here: refit **every month** on
months strictly before M. k = 2 by train-only silhouette; 120 months split 73 / 47;
centroid drift 0.119 of separation.

**The 3–5 band's premium is NOT regime-conditional.**

| | months | mean monthly excess | annualised | t |
|---|---|---|---|---|
| pooled | 119 | +0.686% | +8.55% | 0.74 |
| market state 0 | 72 | +0.382% | +4.68% | 0.33 |
| market state 1 | 47 | +1.153% | +14.75% | 0.74 |

Observed spread 0.0077; the null p95 for a random permutation of the
month → state map is **0.0369**, `p = 0.698`. The apparent 3× difference is
what a 73/47 split of 120 noisy monthly means produces on its own.

Across all bands the only regime-stable statement is that `toxic_ge_5` is bad
in both regimes (−4.62%/mo, t −4.57 and −2.82%/mo, t −3.11).

**And the market-state layer fails its own hygiene check.** `NULL_shuffled_target__lgbm_raw`
— a model trained on permuted targets — scores IC **0.0213, t 2.72** inside
market state 1. A partition that can make the null look skilful cannot be used
to certify that anything else is skilful. At n = 120 date blocks and k = 2,
**market-regime conditioning is CANNOT DETERMINE, and that is a statement about
sample size, not about regimes.** The company-state layer, on 371,848 rows and
the same null flat in all four states, does not have this problem — which is
exactly why the two are reported separately rather than averaged into one
"states work" sentence.

---

## 7. The other two rungs

**IsolationForest anomaly — predicts the TAIL, not the mean.** Across deciles of
within-month anomaly percentile the mean 1m excess wanders between −0.08% and
−0.64% with no monthly t beyond |1.6|, but the worst-5% tail loss is monotone
and large: **−21.6% at decile 1 → −53.3% at decile 10**, a 2.5× widening. An
unusual name is not a worse bet on average; it is a *wider* bet. That is a
sizing input, not a selection input.

**Nearest-historical-neighbour retrieval works, at a small size.** For each
company-vintage the three closest historical analogues are stored with their
distances (`nn1_dist` mean 0.89, median 0.75) and the mean 1m excess *they* went
on to realise. The reference pool is restricted to rows whose own target had
matured **before the assigned month began**, so this is a PIT predictor and not
a lookup of the answer — pinned by
`test_nearest_neighbours_come_only_from_matured_history`. Its IC is **0.0198,
t 7.33** over 119 months, strongest in state 0 (0.0172, t 3.98) and state 2
(0.0159, t 2.18). Small, clean, and interpretable in a way a gradient boost is
not: it can name the three companies it is reasoning from.

**The autoencoder is NOT KEPT.** Same blocks, same k, same null: spread 0.00996
against PCA+KMeans's 0.01332, at roughly ten times the runtime. It cleared its
own null (p = 0.000) — it is not broken, it is just not better. A neural
embedder that reproduces PCA's partition more slowly is a slower PCA, and the
receipt records the comparison rather than the author's preference.

---

## 8. Caveats, in the order they would mislead someone

1. **No state is profitable.** Every monthly mean excess is ≤ 0. This ranks
   loss and tail, not return.
2. **State-conditional ≠ band-conditional was tested and only partly survives.**
   It survives in `lt_1_5` (55% of the panel, p = 0.000). The other three bands
   are *cannot determine*, not confirmations.
3. **The prior's state-conditional IC is largely compositional.** Read the
   `mean_distinct_predictions` field before quoting it.
4. **`k = 4` was chosen on silhouette, not on returns** — but the ladder was
   graded anyway, and *every* k clears the null, so this is a presentation
   choice, not a result.
5. **Predictions are LEARNER v1's.** `learner_v2_20260903.json` existed while
   this ran but did not yet name a predictions file, so the receipt records
   `v2: RECEIPT PRESENT BUT NAMES NO PREDICTIONS FILE — CANNOT DETERMINE`. The
   runner joins both when both are there (`v2__` prefix) and re-grading is
   `--reuse-assignments`, ~50 seconds. This is not a v2 verdict.
6. **Sector was never a feature.** A sibling session found that the panel's
   sector map labels CRSP SIC 9999 (NONCLASSIFIABLE) as "Public Administration"
   — 99,334 / 441,278 rows, 22.51%. It is missingness wearing an industry's
   name. `sector` is not in `STATE_FEATURES` or `MARKET_FEATURES`, so **no
   discovered state can be an artefact of it**; the clustering never saw a
   sector column. It appears only in the descriptive composition table, where
   the bucket is relabelled `UNKNOWN_sic_9999` so it cannot be read as an
   industry. (State 0 is 49.2% that bucket — which is a fact about which
   companies lack an SIC code, and would have been a very inviting false story.)
7. **10 bps/side, turnover, terminal wealth: none of it is here.** This
   document contains no book, no cost model and no P&L, because the states were
   not used to build one. That is the next piece of work, not a gap in this one.

---

## 9. What this earns, and what it does not

**Earns:** a conditioner with a stable identity, a clean null, and a surviving
within-band control; the first evidence that `lgbm_clf`'s advantage over
`mlp__raw` and `ridge__raw` is *where it works*, not *how well it works on
average*; and a persisted per-company-vintage state file the next router can
train on without refitting anything.

**Does not earn:** a book, a lane, a weight in `arena_composite`, or the
sentence "we have a regime model". The market-regime layer explicitly failed
its own hygiene check and is reported as such.

**Next, in order:**
1. Train a router on `state_k4` and grade it on **terminal wealth net of
   costs**, against the single-expert champion on the same months. IC is not
   the objective and a routing gain in IC may not survive turnover.
2. Extend the within-band control to `b_3_5` when there are enough rows — that
   is the band the book actually buys, and it is the one cell this run could
   not read.
3. Feed the anomaly decile into sizing rather than selection: the finding there
   is a 2.5× tail widening with a flat mean, which is a position-size
   statement.
