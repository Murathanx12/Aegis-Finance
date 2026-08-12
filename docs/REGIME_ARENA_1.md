# GRAND-ARENA-1 CHUNK 5 — REGIME-ARENA-1

**Three cross-sectional decisions, fifteen state definitions, 408 simulations,
84 scored arms — and gross exposure measured at 1.000000 in every one of them,
so the de-risking channel that decided chunk 6 cannot exist here.** (The §A3
matched variants scale deliberately and are reported separately; no *scored*
arm varies exposure.)

Pre-registered `Aegis module/TRIALS/PREREG_REGIME_ARENA_1.md` at commit
`9e5dd09`, **before any runner file existed**. `lint_prereg`: **PASS** against
333 prior experiments, with three resurrections declared and argued.
Runner `Aegis module/scripts/run_regime_arena_1.py` (+ `regime_arena_core.py`,
`regime_arena_aux.py`). Receipts `Aegis module/data/factory/
regime_arena_1_{states,proof,sim,score,summary,aux}.json` and
`regime_arena_1_paths.parquet` (untracked — `/data/` is gitignored).

---

> ## VERDICT: **CONDITIONING A SELECTION, A SIGNAL WEIGHTING OR A RISK MODEL ON AN OBSERVABLE STATE IS NOT DETECTABLE AGAINST MAKING THE SAME DECISION UNCONDITIONALLY. THIRTY-FIVE OF THIRTY-SIX REAL PRIMARY ARMS SIT INSIDE THEIR OWN RULER, AND THE ONE THAT DOES NOT IS NEGATIVE AND DISSOLVES UNDER RISK MATCHING.**
>
> **The primary metric is `D_cond` — the arm minus its own unconditional twin,
> the identical machinery with the state label deleted.** Across three decision
> families × twelve real states, **one** real arm clears its own 80%-power MDE:
> `D2_WEIGHTING|S_BREADTH3` at **−7.364 pp/yr against an MDE of 5.952 (1.24×,
> 6/7 blocks, both halves)** — conditioning that *costs* money. Under §A3
> beta-matching it falls to **−3.130 [MDE 3.951]** and under vol-matching to
> **−2.975 [MDE 3.830]**, both NOT DETECTABLE: most of the "harm" was the
> conditioned arm quietly carrying more beta (0.787 vs the control's 0.656).
> It is recorded **`UNRESOLVED_MATCHING`**, not as a kill.
>
> **§A11(4) is NOT awarded.** It requires the same state to clear in two of the
> three families independently. Zero states clear in one. The summary artifact
> computes it mechanically and returns `breakthrough_eligible: false`.
>
> **The most useful number in this document is the placebo, and it is not
> zero.** A **random** partition of the trailing window — same marginal
> frequencies, same block persistence, alignment with the market destroyed —
> changes performance systematically. In `D1_SELECTION` the 20-seed pooled
> placebo is **−7.024 pp/yr against its own MDE of 6.132, t = −3.21, 7/7 blocks,
> both halves, 0 of 20 seeds positive: DETECTABLE_NEGATIVE.** In `D3_RISKMODEL`
> it is **+2.008 pp/yr with 20 of 20 seeds positive** (not detectable on the
> monthly ruler). **Conditioning has a mechanical effect on the answer that owes
> nothing whatever to information: it shortens the estimation window.** That
> effect is larger than every real state's effect in two of the three families,
> and no real state separates from the placebo on the pre-registered primary
> comparison.
>
> **The ceiling is low, and that is the finding that shrinks the search tree.**
> Chunk 6's exposure oracle was worth **+21.563 pp/yr at 10.4× its MDE**. Routed
> through *selection*, an oracle that knows next month's market direction is
> worth **+13.179 pp/yr at 0.64× its MDE — the oracle itself is not detectable.**
> Through *signal weighting*, **+15.989 at 1.02×**. Through *risk-model choice*,
> **+11.096 at 1.74×**, and even that collapses to **+2.718 [8.597]** once beta
> is matched. **Perfect knowledge of the regime, spent on cross-sectional
> decisions rather than on exposure, buys about half the effect it buys on
> exposure and cannot reliably be measured on 227 months.** Chunk 6's diagnosis
> was *observability*; chunk 5's is **availability** — on this decision there is
> much less there to observe.
>
> **The look-ahead tripwire earned its keep and it caught a real defect.** The
> decision-level perturbation proof failed `S_BOCPD2` at 3 of 3 probes with its
> own label unchanged: the inherited core passed the **full-sample variance** of
> the monthly market series as the BOCPD prior, so corrupting the future changed
> *past* labels, and the conditioning set is built from past labels. Fixed to a
> declared constant and re-run. After the fix **all twelve real states are
> bit-identical in label AND in chosen option across nine corruption cells**,
> and both required-to-move arms move at every probe.
>
> **§A7 is binding. Nothing here is certified.** CRSP 2003-2024 is interrogated
> data, this is one bed, and regime-switching asset allocation is a very large
> published field that `lint_prereg` knows nothing about. Nothing in this
> document moves a lane, a size, a default or a dollar.

---

## 1. What was built

### 1.1 The bed, declared as found — and reused, not rebuilt

`data/factory/arena_panel.parquet`, built by `scripts/arena_panel.py` for
PORTFOLIO-ARENA-1 and **reused unmodified**:

| item | value |
|---|---|
| decision dates | **263 monthly**, 2003-01-31 → 2024-11-29 |
| eligible names per date | **1,500** (price ≥ $5, ≥ 252d history, 63d median dollar volume ≥ $1m, top 1,500 by that median) |
| delistings spliced | **7,283** — a death is a realised return, never a disappearance |
| burn-in (frozen pre-registration) | first **36** dates, every arm holds the identical frozen default |
| **evaluation window** | dates 36…262, **n = 227 months, 2006-01-31 → 2024-11-29**, identical for every arm |
| cost model | **G7, reused**: Corwin-Schultz half-spread stamped per name per date (median 24.2 bps) + 5 bps slippage + 1 bp commission on the one-way traded fraction; no CS estimate pays that date's 90th percentile |

Every feature is computed from rows at or before its decision date; the forward
return runs decision-date → next decision date and is disjoint from every
feature by construction.

### 1.2 The three decisions and their option sets (prereg §4, frozen)

| family | what is conditioned | options |
|---|---|---|
| **D1_SELECTION** | which single signal ranks the top-K | 6: `MOM` `REV` `SUE` `TGT` `LOWVOL` `NMAX` |
| **D2_WEIGHTING** | the blend over the six signals' z-scores | softmax of cross-standardised trailing rank-IC, **τ = 1.0 frozen** |
| **D3_RISKMODEL** | which risk scheme allocates inside a **fixed** selection | 5: `EW` `IVOL` `IVAR` `MINVAR1F` `IBETA` |

D3 holds selection fixed at the equal-weight six-signal composite top-K on
purpose, so the only thing conditioned is the risk model.

**The conditioning rule is identical for all three**, so the *state* is the only
thing that varies: at date `k`, score each option by its mean realised outcome
over the **conditioning set** — all past months for the control, past months
carrying the current state label for a conditioned arm — then take the argmax
(D1, D3) or the softmax blend (D2). Minimum in-state history **12 months**, then
fall back to the unconditional choice, then to the frozen default.

### 1.3 The unconditional control, which is the whole point

`S_NONE` is not a different system. It is the **same code path** with a
single-valued label, so its conditioning set is the entire realised past. Every
`D_cond` in this document is a **paired monthly difference against that twin**,
annualised ×12. *"Regime-conditioned X beats regime-conditioned nothing"* is
never computed anywhere in the runner.

The three controls, for context (K=20, 1× G7, 227 months):

| control | net CAGR | mean ann | vol | maxDD | turnover 1-way/yr | cost bps/yr | ex-ante β |
|---|---:|---:|---:|---:|---:|---:|---:|
| `D1_SELECTION\|S_NONE` | 9.217 pp | 13.280 | 29.96% | −65.5% | 4.73 | 361.9 | 1.439 |
| `D2_WEIGHTING\|S_NONE` | 2.989 pp | 3.971 | 14.19% | −57.1% | 7.83 | 326.5 | 0.656 |
| `D3_RISKMODEL\|S_NONE` | 4.248 pp | 5.445 | 15.79% | −50.5% | 8.79 | 381.1 | 0.772 |

### 1.4 The fifteen states, printed as they actually came out

`min share` is the smallest state's share of the 227 evaluated months — the
statistic that decides whether an arm could condition at all.

| id | class | states | eval counts | switch rate | min share |
|---|---|---:|---|---:|---:|
| `S_NONE` | **CONTROL** | 1 | [227] | 0.000 | 1.000 |
| `S_VOL3` | observable | 3 | [66, 75, 86] | 0.278 | 0.291 |
| `S_DD2` | observable | 2 | [184, 43] | 0.088 | 0.189 |
| `S_TREND2` | observable | 2 | [43, 184] | 0.062 | 0.189 |
| `S_YC2` | observable, **SNAPSHOT_VINTAGE** | 2 | [38, 189] | 0.049 | 0.167 |
| `S_BREADTH3` | observable | 3 | [99, 62, 66] | 0.238 | 0.273 |
| `S_KMEANS3` | clustering, refit annually | 3 | [150, 57, 20] | 0.159 | 0.088 |
| `S_BOCPD2` | change-point | 2 | **[3, 224]** | 0.018 | **0.013** |
| `S_HMM2` | **§A2 CONTROL, NOT_TRUSTED** | 2 | [107, 120] | 0.119 | 0.471 |
| `S_HMM3` | **§A2 CONTROL, NOT_TRUSTED** | 3 | [55, 143, 29] | 0.185 | 0.128 |
| `S_SUP2` | supervised (market-sign) | 2 | [56, 171] | 0.256 | 0.247 |
| `S_SUPSIG6` | supervised (**the pre-registered one**) | 6 | [44, 27, 15, 83, 35, 23] | 0.533 | 0.066 |
| `S_SHUFFLE3` | **PLACEBO** | 3 | [62, 85, 80] | 0.300 | 0.273 |
| `S_ORACLE2` | **IMPOSSIBLE** | 2 | [76, 151] | 0.418 | 0.335 |
| `S_LEAKY3` | **TRIPWIRE (look-ahead)** | 3 | [69, 76, 82] | 0.286 | 0.304 |

`S_BOCPD2` is effectively a constant label: **3 of 227 evaluated months** sit in
the short-run-length state. Read every `S_BOCPD2` number in this document as
"the unconditional decision with up to ten months removed from the trailing
average", not as a regime effect. §7 returns to this.

---

## 2. The look-ahead proof, and the defect it caught

A state label fitted on the full sample and then used to condition is the single
likeliest way this trial fools itself, so the proof is mechanical, not argued.

**Method.** At each of three probe dates (`date_ix` 100 / 144 / 200 =
2011-05-31, 2015-01-30, 2019-09-30) and **three corruption draws each**, every
panel cell and every market cell **observed strictly after the probe** is
replaced with garbage — including `fwd_ret_1m` and `mkt_fwd_1m` **at** the probe,
because month *k*'s forward return is realised at *k+1* and is therefore a
future observation at *k*. The FRED yield-curve series is corrupted after the
probe date too. Everything is then rebuilt through the **same construction
path** — a proof that runs a tidier second code path proves something about the
second path.

Two things are required, not one:
1. the **label** at the probe returns bit-identical, and
2. the **chosen option** at the probe returns bit-identical, for all three
   families.

### 2.1 DEFECT — `S_BOCPD2` was reading the future, and only the decision-level clause caught it

First run: `S_BOCPD2` passed the label check at all three probes and **failed
the decision check for `D2_WEIGHTING` at all three**. The cause:

```python
bc = BayesianChangepoint(hazard_rate=BOCPD_HAZARD, mu_prior=0.0,
                         var_prior=float(np.nanvar(monthly_ret)) or 1.0)
```

`monthly_ret` is the **whole** series. A full-sample variance entered the
predictive at every step, so corrupting the future moved **past** labels — and
the conditioning set at *k* is built from past labels, which is why the label at
*k* could be unchanged while the decision at *k* changed. **A label-only proof
would have passed this.**

Fixed to `BOCPD_VAR_PRIOR = 0.05 ** 2` — declared once, never tuned against any
result. After the fix, **zero violations** across `15 states × 3 families × 9
probe/draw cells`.

### 2.2 The tripwire was rebuilt twice rather than the failing arm dropped

`S_ORACLE2` (label = sign of next month's market return) and `S_LEAKY3`
(`S_VOL3` with full-sample tercile breakpoints) are **required to move**. They
did not, at first, and the harness was rebuilt both times:

1. `S_LEAKY3`'s label survived a same-scale `N(0.5,1)` corruption at 3 of 3
   probes — a full-sample tercile breakpoint absorbs a perturbation of its own
   magnitude. Market state features are now corrupted by **three orders of
   magnitude**.
2. `S_ORACLE2` survived at **8 of 9** cells, because `N(0.5,1)` is positive 69%
   of the time and the true label was already 1. The corruption family now
   **spans the sign**: draw 0 forces positive, draw 1 negative, draw 2 free.

**Final:** `S_ORACLE2` fires at 1 of 3 draws at **every** probe (the sign-forcing
draw, exactly as designed); `S_LEAKY3` fires at **9 of 9** cells;
`tripwire_has_teeth: true`.

### 2.3 One arm is exempt, and the exemption is declared rather than silent

**`S_SHUFFLE3` cannot be point-in-time and is excluded from the PIT
requirement.** A block permutation of the *whole* label sequence is non-causal
by construction — the placebo at month *k* carries some other month's tercile,
sometimes a future one. That is what makes it a placebo (a random partition of
the trailing window) and it is never promotable. Recorded in the artifact as
`non_pit_by_construction_excluded`.

---

## 3. The headline table — every primary configuration (K = 20, 1× G7)

`D` = `D_cond` in pp/yr; `x` = |D| ÷ its own 80%-power MDE; `div` = the share of
the 227 months where the conditioned choice **differed** from the unconditional
twin's choice on the same date; `plc` = the arm's percentile against 20 placebo
seeds.

| id | D pp/yr | its MDE | x | blocks | halves | div | plc | verdict |
|---|---:|---:|---:|:--:|:--:|---:|---:|---|
| `D1\|S_ORACLE2` | **+13.179** | 20.526 | 0.64 | 5/7 | yes | 0.93 | 1.00 | DIAGNOSTIC — NOT_DETECTABLE |
| `D1\|S_DD2` | +0.666 | 11.933 | 0.06 | 3/7 | no | 0.71 | 1.00 | NOT_DETECTABLE |
| `D1\|S_TREND2` | −0.430 | 11.671 | 0.04 | 3/7 | no | 0.62 | 1.00 | NOT_DETECTABLE |
| `D1\|S_BOCPD2` | −0.846 | 3.892 | 0.22 | 2/7 | yes | **0.03** | 1.00 | NOT_DETECTABLE |
| `D1\|S_HMM3` | −1.910 | 12.464 | 0.15 | 3/7 | no | 0.56 | 0.90 | NOT_DETECTABLE |
| `D1\|S_VOL3` | −2.449 | 14.888 | 0.16 | 3/7 | yes | 0.73 | 0.90 | NOT_DETECTABLE |
| `D1\|S_SUP2` | −2.671 | 16.430 | 0.16 | 4/7 | no | 0.74 | 0.80 | NOT_DETECTABLE |
| `D1\|S_LEAKY3` | −3.909 | 15.081 | 0.26 | 5/7 | yes | 0.88 | 0.75 | DIAGNOSTIC — NOT_DETECTABLE |
| `D1\|S_SHUFFLE3` | −5.138 | 9.818 | 0.52 | 6/7 | yes | 0.32 | 0.65 | NOT_DETECTABLE |
| `D1\|S_BREADTH3` | −5.652 | 11.512 | 0.49 | 4/7 | yes | 0.50 | 0.60 | NOT_DETECTABLE |
| `D1\|S_HMM2` | −6.820 | 10.774 | 0.63 | 4/7 | yes | 0.57 | 0.50 | NOT_DETECTABLE |
| `D1\|S_KMEANS3` | −7.286 | 10.617 | 0.69 | 5/7 | yes | 0.36 | 0.50 | NOT_DETECTABLE |
| `D1\|S_YC2` | −9.970 | 10.522 | 0.95 | 5/7 | yes | 0.51 | 0.25 | NOT_DETECTABLE |
| `D1\|S_SUPSIG6` | −12.550 | 12.618 | 0.99 | 5/7 | yes | 0.44 | 0.00 | NOT_DETECTABLE |
| `D2\|S_ORACLE2` | **+15.989** | 15.704 | 1.02 | 6/7 | yes | 0.99 | 1.00 | DIAGNOSTIC — CONDITIONING_DETECTED |
| `D2\|S_TREND2` | +7.157 | 9.528 | 0.75 | 6/7 | yes | 0.97 | 1.00 | NOT_DETECTABLE |
| `D2\|S_DD2` | +6.686 | 10.545 | 0.63 | 5/7 | yes | 0.96 | 1.00 | NOT_DETECTABLE |
| `D2\|S_BOCPD2` | +5.381 | 5.899 | 0.91 | 5/7 | yes | 0.98 | 1.00 | NOT_DETECTABLE |
| `D2\|S_LEAKY3` | +2.568 | 11.835 | 0.22 | 3/7 | no | 0.97 | 1.00 | DIAGNOSTIC — NOT_DETECTABLE |
| `D2\|S_HMM3` | +1.457 | 8.798 | 0.17 | 2/7 | no | 0.79 | 1.00 | NOT_DETECTABLE |
| `D2\|S_SUP2` | +1.403 | 13.263 | 0.11 | 3/7 | no | 0.95 | 1.00 | NOT_DETECTABLE |
| `D2\|S_YC2` | +0.655 | 2.610 | 0.25 | 4/7 | no | 0.95 | 0.90 | NOT_DETECTABLE |
| `D2\|S_HMM2` | −0.542 | 7.633 | 0.07 | 2/7 | no | 0.80 | 0.65 | NOT_DETECTABLE |
| `D2\|S_SUPSIG6` | −1.381 | 8.637 | 0.16 | 3/7 | no | 0.74 | 0.65 | NOT_DETECTABLE |
| `D2\|S_SHUFFLE3` | −2.238 | 11.946 | 0.19 | 5/7 | no | 0.97 | 0.40 | NOT_DETECTABLE |
| `D2\|S_KMEANS3` | −4.185 | 10.959 | 0.38 | 4/7 | no | 0.85 | 0.35 | NOT_DETECTABLE |
| `D2\|S_VOL3` | −5.343 | 8.973 | 0.60 | 5/7 | yes | 0.93 | 0.10 | NOT_DETECTABLE |
| **`D2\|S_BREADTH3`** | **−7.364** | **5.952** | **1.24** | 6/7 | yes | 0.92 | 0.00 | **UNRESOLVED_MATCHING** |
| `D3\|S_ORACLE2` | **+11.096** | 6.394 | **1.74** | 6/7 | yes | 0.63 | 1.00 | DIAGNOSTIC — CONDITIONING_DETECTED |
| `D3\|S_VOL3` | +2.786 | 5.410 | 0.51 | 6/7 | yes | 0.65 | 0.80 | NOT_DETECTABLE |
| `D3\|S_LEAKY3` | +2.715 | 4.034 | 0.67 | 7/7 | yes | 0.70 | 0.75 | DIAGNOSTIC — NOT_DETECTABLE |
| `D3\|S_SHUFFLE3` | +2.438 | 6.466 | 0.38 | 4/7 | yes | 0.66 | 0.65 | NOT_DETECTABLE |
| `D3\|S_SUPSIG6` | +1.852 | 3.740 | 0.50 | 5/7 | yes | 0.54 | 0.50 | NOT_DETECTABLE |
| `D3\|S_SUP2` | +1.608 | 5.294 | 0.30 | 4/7 | yes | 0.62 | 0.45 | NOT_DETECTABLE |
| `D3\|S_TREND2` | +1.531 | 3.560 | 0.43 | 5/7 | no | 0.60 | 0.40 | NOT_DETECTABLE |
| `D3\|S_YC2` | +1.288 | 3.894 | 0.33 | 4/7 | no | 0.63 | 0.25 | NOT_DETECTABLE |
| `D3\|S_DD2` | +1.028 | 3.489 | 0.29 | 3/7 | no | 0.60 | 0.20 | NOT_DETECTABLE |
| `D3\|S_HMM3` | +0.974 | 4.023 | 0.24 | 4/7 | yes | 0.59 | 0.20 | NOT_DETECTABLE |
| `D3\|S_BREADTH3` | +0.598 | 3.283 | 0.18 | 5/7 | no | 0.61 | 0.05 | NOT_DETECTABLE |
| `D3\|S_KMEANS3` | +0.114 | 2.957 | 0.04 | 4/7 | no | 0.44 | 0.00 | NOT_DETECTABLE |
| `D3\|S_HMM2` | −0.484 | 2.855 | 0.17 | 4/7 | yes | 0.36 | 0.00 | NOT_DETECTABLE |
| `D3\|S_BOCPD2` | −0.486 | 0.905 | 0.54 | 4/7 | yes | 0.11 | 0.00 | NOT_DETECTABLE |

**The K = 40 grid (42 more arms) reproduces this exactly:** one arm above its own
MDE, the same one, the same sign — `D2|S_BREADTH3|K40` at **−6.163 [5.058],
1.22×**, which the artifact still labels `CONDITIONING_HARMFUL` **only because
the §A3 matched variants were run for the K = 20 primaries and not for the K = 40
grid**; its K = 20 twin dissolves under beta-matching and there is no reason to
think this one would not. Nothing positive anywhere clears.

---

## 4. The hypotheses, each answered with a number

| # | prior | outcome |
|---|---|---|
| **H1** — some (family, state) beats its unconditional twin above its own MDE, ≥5/8 blocks, both halves, surviving matching | LOW ~12% | **REFUTED as stated.** 0 of 36 real primary arms. The only arm above its MDE is negative, and it fails matching. |
| **H2** — the placebo is indistinguishable from the real states | HIGH ~70% | **CONFIRMED on the pre-registered comparison.** No real state separates from `S_SHUFFLE3` above the MDE of that difference, in any family. §5 has the two secondary cells that do, and why they change nothing. |
| **H3** — the HMM does not beat the simple observables | HIGH ~75% | **CONFIRMED, direction unanimous, magnitude undetectable.** `S_HMM2` − best simple observable: **−7.486 [10.673]** (D1), **−7.699 [11.232]** (D2), **−3.270 [5.122]** (D3). `S_HMM3`: −2.576, −5.700, −1.813. All six negative; none detectable. The §A2 control does not earn promotion, and it also is not *detectably* worse. |
| **H4** — the oracle bound is large and observables capture almost none of it | HIGH ~80% | **HALF WRONG, and this is the chunk's real finding.** The oracle bound is **small** on these decisions: 0.64× / 1.02× / 1.74× its own MDE, versus chunk 6's exposure oracle at **10.4×**. §6. |
| **H5** — conditioning raises turnover and costs eat a material share | MEDIUM ~55% | **CONFIRMED in D1, absent elsewhere.** D1 control turns over **4.73×/yr**; conditioned arms **4.83–7.30** (median 6.58), costs 361.9 → up to **558.0 bps/yr**, and every D1 arm's `D_cond` falls from 0× to 2× costs by **0.14–4.02 pp/yr (median 2.17)**. D2 controls already turn over 7.83×/yr (arms 7.00–8.92) and D3 8.79×/yr (arms 8.71–8.90), where conditioning barely moves it. There was no gain for the costs to eat. |
| **H6** — the look-ahead tripwire beats its PIT twin, proving the bed expresses the failure mode | MEDIUM ~50%, *"if it does NOT, the tripwire is weak on this bed and that must be stated"* | **NOT SHOWN, and it is stated.** `S_LEAKY3` − `S_VOL3`: **−1.459 [10.894]** (D1), **+7.911 [13.562]** (D2), **−0.071 [2.482]** (D3). None detectable, two negative. **At the return level this bed does not express the full-sample-breakpoint failure mode.** The tripwire that worked is the *mechanical* one in §2, which fired at 9 of 9 cells. A P&L tripwire on 227 months is the weaker instrument, and that is the honest reading. |

---

## 5. The placebo is not centred on zero — the mechanism finding

The 20-seed placebo (`S_VOL3`'s marginals and 12-month block persistence,
permuted in time, seeds 0…19) exists to answer: *does conditioning add
information, or does partitioning the trailing window change the answer by
itself?*

| family | seeds > 0 | mean pp/yr | range | **pooled placebo `D_cond`** | its MDE | t | blocks | verdict |
|---|---:|---:|---|---:|---:|---:|:--:|---|
| `D1_SELECTION` | **0 / 20** | −7.024 | −11.98 … −1.31 | **−7.024** | 6.132 | −3.21 | **7/7** | **DETECTABLE_NEGATIVE** |
| `D2_WEIGHTING` | 5 / 20 | −2.304 | −7.11 … +1.12 | −2.304 | 5.048 | −1.28 | 5/7 | NOT_DETECTABLE |
| `D3_RISKMODEL` | **20 / 20** | +2.008 | +0.42 … +4.02 | +2.008 | 3.108 | +1.81 | 5/7 | NOT_DETECTABLE |

**Read that first row carefully.** Splitting the trailing window at random — no
information, by construction — costs the selection family **7 pp/yr with the
sign in every one of seven regime blocks and both halves.** The mechanism is not
mysterious: the argmax over six options is estimated from a third as many
months, so it is noisier and it churns (turnover rises, costs rise). In the
risk-model family the same random partition *helps*, +2.0 pp/yr with 20 of 20
seeds positive, presumably by making the trailing estimate more recency-weighted
where the risk schemes' ordering drifts slowly.

Two consequences, both binding on how the rest of this document may be read:

1. **Most real states in D1 are "less bad than random", not "good".** `S_DD2` at
   **+0.666** and `S_TREND2` at **−0.430** sit above a placebo of −7.024 — that
   is an estimator-quality statement, not an information statement, and it does
   not clear the primary metric.
2. **Any comparison against the placebo instead of against the control flatters
   the arm in D1 and D2, and penalises it in D3.** The pre-registered primary
   metric is the control. It was frozen before results and it has not moved.

### 5.1 The secondary comparison that *does* clear, and why it promotes nothing

Tested against the lower-variance **pooled** placebo rather than the control,
two cells clear their own MDE (§18: a difference tested as a difference, with
its own SE):

| cell | vs pooled placebo | its MDE | t | blocks | halves |
|---|---:|---:|---:|:--:|:--:|
| `D2_WEIGHTING\|S_TREND2` | **+9.461** | 8.881 | 2.98 | 7/7 | yes |
| `D2_WEIGHTING\|S_BOCPD2` | **+7.685** | 6.442 | 3.34 | 7/7 | yes |

**Neither is promotable, for three independent reasons, and switching to this
comparison would be outcome-shopping against a metric frozen at `9e5dd09`.**

* **It is not the primary metric.** Against their unconditional twins these are
  **+7.157 [9.528] = 0.75×** and **+5.381 [5.899] = 0.91×** — both
  NOT_DETECTABLE. §8's rule requires clearing the control **and** the placebo.
  They clear only the placebo.
* **The comparator is penalised.** The D2 pooled placebo sits at −2.304 pp/yr.
  Beating a comparator that carries an estimation penalty is not beating the
  control.
* **`S_BOCPD2` is not a regime state on this bed.** Three of 227 evaluated months
  carry the short-run-length label. "Conditioning" on it means computing the
  same unconditional IC average with up to ten months deleted. Its D2 divergence
  rate is 0.98 only because the softmax blend is continuous — dropping three
  months moves every weight slightly. That is an estimator perturbation, not a
  state.

---

## 6. The oracle bound — chunk 6's shape does **not** reproduce

`S_ORACLE2` is IMPOSSIBLE (label = sign of **next** month's market return) and
is a bound, never a result.

| family | oracle `D_cond` | its MDE | ratio | beta-matched | vol-matched | best observable | share |
|---|---:|---:|---:|---:|---:|---|---:|
| `D1_SELECTION` | +13.179 | 20.526 | **0.64×** | +5.037 [19.030] | +4.438 [18.767] | `S_DD2` +0.666 | 5.1% |
| `D2_WEIGHTING` | +15.989 | 15.704 | **1.02×** | −1.194 [8.149] | −1.883 [7.961] | `S_TREND2` +7.157 | 44.8% |
| `D3_RISKMODEL` | +11.096 | 6.394 | **1.74×** | +2.718 [8.597] | +4.427 [8.170] | `S_VOL3` +2.786 | 25.1% |

**Chunk 6, for contrast: +21.563 pp/yr at 10.4× its MDE on exposure, with the
best observable controller capturing 7.4%.**

Three things follow, and the third is the one worth carrying forward:

1. **The selection oracle is not even detectable** (0.64×). Perfect regime
   knowledge, spent on *which signal ranks the book*, produces an effect this
   bed cannot measure in 227 months.
2. **What the oracle does buy is largely beta.** D3's oracle is the only
   diagnostic that clears (1.74×) and it falls to +2.718 [8.597] — not
   detectable — once ex-ante beta is matched. The oracle mostly learns *hold the
   higher-beta risk scheme when the market is about to rise*, which is an
   exposure statement wearing a risk-model costume. Chunk 6 already owns it.
3. **The "share of oracle captured" column is a ratio of two undetectable
   numbers in D1 and is not evidence of anything.** It is printed because the
   prereg required it, not because it means much.

**The licensed comparison:** chunk 6 concluded the failure was *observability* —
the information existed and no observable rule found it. On the cross-sectional
decisions the ceiling itself is near the noise floor. **Chunk 5's failure is
availability.**

---

## 7. Did the arms actually condition? (the fallback and divergence audit)

The prereg required fallback rates: *"an arm that never actually conditioned is
not evidence about conditioning."* Fallback rates turned out to be the weaker
statistic, so a stronger one was added — the **decision divergence rate**, the
share of evaluated months where the conditioned arm's chosen option differs from
its unconditional twin's on the same date.

* **Fallback to unconditional** (fewer than 12 in-state months) never exceeded
  **26.4%** and was 0–11% for every state except the two supervised ones.
  Fallback-to-default was **0.000 everywhere**.
* **Divergence** ranges 0.03 → 0.99. The bulk of arms sit at 0.4–0.99, so most
  arms genuinely made different decisions and the null is a null about
  conditioning, not about a machine that never engaged.
* **Three degenerate arms are declared rather than averaged in:**
  `D1|S_BOCPD2|K20` diverges in **3%** of months; at K = 40,
  `D1|S_YC2|K40` and `D1|S_BOCPD2|K40` each diverge in **exactly one month of
  227** — and consequently produce **byte-identical paths** (both −0.490 [1.347]).
  The trailing-performance argmax in D1 at K = 40 chooses `SUE` in 226 of 227
  months whatever the state. Those arms are not tests of conditioning and are
  named as such.

---

## 8. §A3 matching, and the symmetry fix

Gross exposure and concentration are matched **by construction and verified, not
asserted**: `gross_exposure` measured **1.000000 (min = max = 1.0) in all 84
scored arms**, `voided: []`; effective N is 20.0 in D1/D2 (K identical) and
17.6 in D3. Beta, volatility and turnover are matched by re-simulation:
beta/vol via an ex-ante cash blend computed from quantities known at the
decision date (clipped to [0.20, 2.00]), turnover via `partial_rebalance` with
**both** arm and control capped at the same one-way budget.

The single detectable real arm, fully matched:

| `D2_WEIGHTING\|S_BREADTH3\|K20` | value | its MDE | detectable |
|---|---:|---:|:--:|
| raw `D_cond` | **−7.364** | 5.952 | **yes** (6/7 blocks, both halves) |
| beta-matched | −3.130 | 3.951 | no |
| vol-matched | −2.975 | 3.830 | no |
| turnover-matched | −7.212 | 5.660 | yes |
| vs placebo seed 0 | −5.126 | 12.865 | no |
| cost 0× / 1× / 2× | −6.622 / −7.364 / −8.113 | | |

Its ex-ante beta is **0.787** against the control's **0.656**. Roughly 60% of
the harm is that beta difference, and once it is removed the effect is inside
the ruler.

**A defect in my own scoring code, fixed and recorded.** The first version
applied the matching downgrade only to `CONDITIONING_DETECTED`, which would have
held positive results to §A3 and let a negative one through unmatched — exactly
the asymmetry the amendment exists to remove. The rule is now symmetric, which
is why this arm reads `UNRESOLVED_MATCHING` rather than `CONDITIONING_HARMFUL`.
**A harm that is really a beta effect is a beta effect.**

---

## 9. §A8 — the complete search denominator, PBO, DSR, and the §20 self-check

### 9.1 Everything that was executed

| item | count |
|---|---:|
| primary grid (3 families × 15 states × 2 K) | 90 |
| cost cells (0× and 2×, K=20) | 90 |
| placebo seeds (3 families × 20) | 20 seeds → 60 paths |
| §A3 matched variants (beta, vol, turnover + its control) | 168 |
| **total simulations executed** | **408** |
| scored arms (K=20 and K=40) | **84** |
| primary arms (K=20) | 42 — of which **36 real, 6 diagnostic** |
| voided arms | **0** |
| declared non-run | **no exposure arm exists in this trial by construction** |

### 9.2 §20 — the arms are not 36 chances

| | n | mean abs pairwise corr of monthly `D_cond` | **effective distinct arms** |
|---|---:|---:|---:|
| all real primary arms | 36 | 0.155 | **5.60** |
| `D1_SELECTION` | 12 | 0.327 | **2.61** |
| `D2_WEIGHTING` | 12 | 0.199 | **3.77** |
| `D3_RISKMODEL` | 12 | 0.341 | **2.52** |

Chunk 6 measured 47 configurations as **2.02–2.40** effective arms. **The
collapse reproduces:** 12 states per family are worth about **2.5–3.8**
independent chances, and 36 arms are worth **5.6**. The cross-family correlation
is low (families are genuinely different decisions), which is why the pooled
number is larger than any single family's.

### 9.3 PBO (CSCV, S = 8, 70 combinations) and DSR for the FAMILY

| | value |
|---|---:|
| **PBO — all real states + placebo (36 configs)** | **0.257** |
| **PBO — real states only (33 configs)** | **0.271** |
| mean OOS `D_cond` of the IS-best configuration | **+0.676 pp/yr** |
| share of splits where the IS-best is OOS-negative | 0.257 |

A PBO near 0.26 is not a clean bill of health; it says roughly one split in four
picks an in-sample winner that is out-of-sample worse than median. And the
IS-best config's average OOS value is **+0.68 pp/yr**, an order of magnitude
below every arm's own MDE — **selecting the best-looking conditioning rule
in-sample buys essentially nothing out-of-sample.**

**DSR for the family (§A8 — computed for the family, not the winner):**
V[SR] is estimated from this family's **own** spread across arms
(0.009458 monthly), not assumed. Best arm by Sharpe of its `D_cond` series:
`D2_WEIGHTING|S_BOCPD2|K20`, monthly SR 0.201 on 227 months, skew 2.71,
kurtosis 15.76.

| assumed independent trials N | 1 | 5 | 10 | 25 | 42 | 100 | 333 | 1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **DSR** | 0.9999 | 0.9499 | 0.823 | 0.552 | 0.395 | 0.192 | 0.053 | 0.013 |

**Break-even N at 0.95 is 5.** The §20 self-check says this family is worth
**5.60** effective distinct arms — *before* counting the 333 experiments the
programme has already registered, against which deflation is cumulative. **The
best arm in this trial does not survive its own trial's search, let alone the
programme's.**

---

## 10. Defects, deviations and checks that did not run

**Defects found and fixed, all recorded rather than tidied:**

1. **`S_BOCPD2` full-sample variance prior** — a look-ahead in the inherited
   core, caught by the decision-level clause of the perturbation proof and not
   by the label clause. Fixed to a declared constant; everything re-run. §2.1.
2. **The tripwire was too weak, twice** — same-scale corruption for `S_LEAKY3`,
   sign-blind corruption for `S_ORACLE2`. The harness was rebuilt both times
   rather than the arms dropped, as the prereg requires. §2.2.
3. **My verdict rule was asymmetric** — matching downgrades applied to positive
   results only. Fixed. §8.
4. **Three degenerate arms** with divergence ≤ 3%, two of them byte-identical.
   Named, not averaged away. §7.

**Deviations from the pre-registration, declared:**

5. **The trailing score is the option's GROSS return, not net** (prereg §4 says
   "mean realised net monthly return"). Cost is path-dependent — it depends on
   last month's holdings — so a net score would make the number a conditioner
   reads depend on *which arm is asking*, and the option sets could no longer be
   precomputed once. Costs are charged in full in the simulator for every arm
   and every cost multiplier; only the *ranking signal* is gross.
6. **`S_SUP2` as inherited was not the pre-registered state.** Prereg §5 defines
   it as "predict **which base signal wins** next month"; the inherited core
   predicted the **sign of next month's market return**. Both are now built and
   both are reported: `S_SUP2` (market-sign, the observable twin of the oracle)
   and **`S_SUPSIG6`, the pre-registered definition**, which is the worst arm in
   D1 at −12.550 [12.618].
7. **`S_YC2` is `SNAPSHOT_VINTAGE`** — the 2026-07 FRED snapshot. Treasury
   constant-maturity yields are not revised, but it is labelled throughout and
   may not be read as PIT-clean. It is the second-most-negative D1 arm
   (−9.970, 0.95×).
8. **`S_SHUFFLE3` is non-PIT by construction** and is excluded from the PIT
   requirement, declared in the artifact. §2.3.

**Checks that did NOT run, stated rather than implied:**

* **No second bed.** One panel, one market path. Chunk 6 had three beds and then
  measured two of them to be the same path; this trial has one and says so.
  Cross-family replication (§A11(4)) is the only replication instrument here.
* **No market-impact model.** G7 only, at 0×/1×/2×. NIGHT-8 recorded that G7
  cannot price impact; the impact term exists in `arena_core` and was left off.
* **No CPCV beyond CSCV.** PBO is computed by CSCV on the D_cond matrix; a full
  combinatorially-purged CV of the conditioning rule was not run.
* **No K beyond {20, 40}, no τ other than 1.0, no in-state minimum other than
  12.** All frozen in the prereg and none was swept — which is a deliberate
  restriction of the search denominator, not an oversight.
* **The placebo comparison was not turnover-matched.**
* **§A3 matching was run for the K = 20 primaries only**, not for the 42-arm
  K = 40 grid, which is why one K = 40 arm still carries an unmatched verdict.
* **Nothing was run forward.** This is entirely historical.

---

## 11. What this trial may not conclude

1. **Nothing about exposure.** Chunk 6 owns that question; this trial has no
   exposure arm and gross was verified at 1.000000 in all 84 arms.
2. **No alpha, Sharpe, skill or money claim.** No lane, no shadow default, no
   sizing change, no product default, no buy/sell language. **ACCRUES ZERO
   ARMS**, as registered.
3. **Nothing certified (§A7).** CRSP 2003-2024 is interrogated data.
4. **The null is a null on THESE states and THESE decisions**, bounded by the
   oracle arm, with every arm's own MDE stating exactly how large an effect
   would have had to be. Most MDEs here are **3–20 pp/yr** — this bed cannot see
   a 2 pp/yr conditioning effect, and no arm may be called dead for failing to
   clear a ruler that coarse (§19).
5. **The HMM is not promoted** whatever it printed (§A2), and it is also not
   *detectably* worse than the simple observables — six negative point estimates,
   zero detectable.
6. **A plausible-looking label sequence is still not evidence.** No state in
   this document earned anything by its labels reading sensibly against known
   history, and none was inspected for that.
7. **`lint_prereg` PASS means UNMATCHED, not novel.** Regime-switching asset
   allocation is a large published field and the linter knows nothing about it.

---

## 12. What this buys the campaign

A well-measured null that **shrinks the tree in a specific direction**:

* **Regime → exposure** — tested (chunk 6), refused, with a large and
  measurable oracle bound proving the information exists and is unobservable.
* **Regime → selection / weighting / risk model** — tested here, not detectable,
  and the **oracle bound itself is at or below the noise floor**. This is a
  weaker place to look than exposure, not a stronger one. The remaining chunks
  should not spend compute conditioning cross-sectional choices on a market
  state.
* **A reusable finding for every future "conditioning" idea:** partitioning a
  trailing estimation window has a **first-order mechanical effect on
  performance that is independent of information** — **−7.024 pp/yr, 7/7 blocks,
  detectable** in the selection family. Any future conditioned rule that does
  not carry a permuted-label placebo will mistake that effect for a discovery.

---

*Receipts: `Aegis module/data/factory/regime_arena_1_*.json` (+
`regime_arena_1_paths.parquet`, 408 simulated paths). Code:
`Aegis module/scripts/{regime_arena_core,run_regime_arena_1,regime_arena_aux}.py`.
Reproduce end-to-end with `python -m scripts.run_regime_arena_1 --stage all`
followed by `python -m scripts.regime_arena_aux` (~7 minutes, single process).*
