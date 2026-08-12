# GRAND-ARENA-1 CHUNK 6 — EXPOSURE-ARENA-1

**Eight exposure controllers, three beds, 144 scored arms, and a
matched-average-exposure frontier that was written to disk before the first
controller existed.**

Pre-registered `Aegis module/TRIALS/PREREG_EXPOSURE_ARENA_1.md` at commit
`31a49f8`, with five clarifications at `f36f321`, **both before any runner file
existed**. `lint_prereg`: **PASS** against 324 prior experiments, with both
resurrections (EXPOSURE-CONTROL-1 at 0.382 similarity, TRIAL-COND-VT at 0.251)
declared and argued rather than asserted. Runner
`Aegis module/scripts/run_exposure_arena_1.py` (+ `exposure_arena_core.py`,
`exposure_arena_learn.py`, `exposure_arena_report.py`). Receipts
`Aegis module/data/factory/exposure_arena_1_*.json` (untracked — `/data/` is
gitignored).

---

> ## VERDICT: **NO CONTROLLER BEAT MATCHED-AVERAGE-EXPOSURE ON ANY BED WE CAN CALL A REPLICATION. THE ONE FAMILY THAT CLEARED DID IT ON ONE MARKET PATH, MOSTLY BEFORE 1976, AND IT IS NEGATIVE ON EVERY DECADE SINCE 2005.**
>
> **Forty-two of the forty-five real controller configurations on the primary
> bed did not clear their own MDE against matched exposure — twenty-nine of them
> labelled `DE_RISKING_ONLY` by the frozen rule. They did not discover timing.
> They discovered de-risking.** Said in §A1's own words because that is what the
> numbers say: their net CAGR minus the net CAGR of their own average exposure
> held constant sits inside their own 80%-power ruler, while their drawdowns
> fall the way a smaller constant position's drawdown falls. On BED-3, the only
> structurally different bed, it is **44 of 45**.
>
> **The exception, and it is a real statistical event, is the trend/regime
> family (E).** On BED-1 (CRSP value-weighted market, 25,649 days, 1927-2024)
> three of its six configurations clear: the best is `E_REGIME_ma50_trend` at
> **+1.598 pp/yr against its own MDE of 1.143 — 1.40x**, sign in 8 of 10 decade
> blocks. **Four things stop that from being a finding.**
> 1. **It is one market path.** BED-2 detected six of six, but BED-2 is BED-1
>    levered 2.15x — **excess-return correlation exactly 1.000000**, measured,
>    not argued. The two beds count once. The only structurally different bed,
>    BED-3 (the real equal-weighted liquid-1500 CRSP book, 2004-2024, carrying
>    the idiosyncratic gap risk the factor beds cannot), **detected nothing, and
>    all six E configurations there are NEGATIVE** (−1.52 to −3.29 pp/yr).
> 2. **It is a pre-1976 effect.** First half **+3.054 pp/yr**, second half
>    **+0.032**. The §8 coverage clause "same sign in both halves" was satisfied
>    by *three basis points a year* — and by **+0.002 pp/yr** for
>    `ma100_trend`. A coverage test passing on rounding dust is a coverage test
>    that passed, and it is reported as such rather than quietly cashed.
> 3. **Every recent decade is negative.** 2005-14 **−1.04**, 2015-24
>    **−1.38** pp/yr on the primary bed.
> 4. **The pre-registered PRIMARY configuration of the family failed on the
>    primary bed.** `E_REGIME_ma200_2x2` is +1.101 against an MDE of 1.398 —
>    **0.79x, NOT DETECTABLE.** The three that cleared are grid variants, and
>    the §20 self-check says the 47-arm grid is worth **2.40 effective distinct
>    arms**, not 47.
>
> **§A11(3) is therefore NOT awarded, and the word BREAKTHROUGH is not used.**
> The summary artifact computes it mechanically and returns
> `breakthrough_eligible: false` on the measured bed-independence check.
>
> **How much timing was available, so the null can be read correctly.** A
> 21-trading-day oracle — labelled IMPOSSIBLE, and the one arm the look-ahead
> tripwire is *required* to catch — is worth **+21.563 pp/yr over its own
> matched exposure at 10.4x its MDE** on BED-1 (+81.486 at k=1). **The best
> observable controller captured 7.4% of that**, and did not replicate. This is
> WORLD-D's known-answer shape on real data: **the failure is observability,
> not availability.**
>
> **H2 is refuted in one direction and confirmed in the other, and the split is
> the useful part.** On the 98-year bed the rule-based de-risking controllers
> *do* shape drawdown beyond their matched cousin, detectably —
> `E_REGIME_ma200_2x2` −45.6% vs the matched −72.9% (**+27.4pp, MDE 26.2**),
> vol targeting **+14.7pp (MDE 13.4)**, the NIGHT-13 ladder **+17.3pp
> (MDE 13.8)**. But the **learned** controllers go the other way: ridge and
> LightGBM hold *less* on average and draw down **20.1 and 21.8pp DEEPER** than
> their own matched cousins. Path shape is real; on this evidence a fitted
> policy makes it worse.
>
> **The strongest non-oracle detection in the entire trial is negative.** On
> BED-3, the daily-GPR geopolitical conditioner — which is **not
> point-in-time** and therefore had every advantage — is **TIMING_HARMFUL at
> −6.865 pp/yr against an MDE of 2.040 (3.37x), 7 of 7 blocks, both halves.**
>
> **The frontier itself is the quietest result and possibly the most
> important.** On all three beds the constant-exposure frontier is
> **monotonically increasing in mean exposure**: there is no interior optimum on
> the wealth objective, at any leverage, over 98 years. The only way to beat
> full exposure on wealth is to time it, and nothing observable here did.
>
> **§A7 is binding: nothing in this document is certified.** CRSP 2002-2024 is
> interrogated data, and the 200-day moving average on the US market since 1927
> is arguably the most data-mined rule in the history of finance. `lint_prereg`
> says it plainly: *PASS means UNMATCHED, not novel — it knows nothing about the
> literature.* Nothing here moves a lane, a size, a default, or a dollar.

---

## 1. What was built

### 1.1 The beds, printed as found

| bed | construction | span | eval days | ann vol | maxDD unmanaged | one-way cost |
|---|---|---|---:|---:|---:|---:|
| **BED-1 MARKET (primary)** | `r = 1.0·mktrf + rf`, CRSP VW market total return, `ff_factors_daily.parquet` | 1926-07-01 → 2024-12-31 | **25,649** (1927-05-05 →) | 17.09% | **−84.07%** | 5.0 bps |
| **BED-2 LEVERED** | `r = 2.15·mktrf + rf`, the frozen NIGHT-13 proxy | same | 25,649 | 36.75% | **−98.87%** | 5.0 bps |
| **BED-3 REAL CRSP BOOK** | EW top-1,500-by-63d-median-dollar-volume liquid universe, monthly reconstitution, **7,283 CRSP delistings spliced**, mean 1,497.6 members | 2003-01-02 → 2024-12-31 | 5,285 (2004-01-02 →) | 22.74% | −58.96% | 30.2 bps |

A frozen **252-trading-day warm-up is excluded from every evaluation window**,
so no arm is scored on a day its own signal did not exist.

**Costs are the repo's model, not a new one.** BED-1/2 charge
`exit_lab_core.BENCH_BPS = 5.0` — the repo's declared index-leg cost. BED-3
charges EXIT-LAB-1's **measured** Corwin-Schultz median of 24.2 bps on this
exact universe plus `SimConfig.slippage_bps 5.0` and `commission_bps 1.0` =
**30.2 bps**. Cash earns the daily risk-free rate for every arm including every
control (NIGHT-13 froze cash at zero and recorded that as a limitation worth
~1.5pp on its holdout; the limitation is removed here identically for all arms
and was declared before any result).

### 1.2 The instrument

Exposure `w` sits in the book, `1 − w` sits in cash at `rf`, `|Δw|` is charged.
**A weight decided from data at `t` is applied to the return of `t+1`, for every
controller without exception including the oracle.** The prereg's runtime
identity

```
net_X − net_FULL  =  avoided-loss − missed-upside − costs      (arithmetic, exact)
```

holds to **1.8e-15** on the 98-year bed, which is what makes the §A10
decomposition in §7 a measurement rather than decoration.

### 1.3 Causality, and the tripwire that gives the causality proofs meaning

Eight primary controllers per bed were perturbation-proved: every return
strictly after a probe date corrupted, the decided weight required to come back
**bit-identical**. **24 of 24 came back identical.** Two of those 24 are worth
less than they look and are marked as such in the receipt: the GPR conditioner
is exogenous to the book path, so nothing the perturbation touches can reach it;
and the k=21 oracle *also* came back identical, which is precisely the problem —
see below.

A clean causality proof is worthless if the harness could not have produced a
violation — the same argument WORLD-I makes about null verdicts. So the oracle
is run through a perturbation *designed* to be caught (every post-probe excess
return negated) and is **required to move**:

| bed | probe | oracle w before | after | verdict |
|---|---|---:|---:|---|
| BED-1 | 1974-02-22 | 0.0 | 1.0 | **PASS — look-ahead DETECTED** |
| BED-2 | 1974-02-22 | 0.0 | 1.0 | **PASS — look-ahead DETECTED** |
| BED-3 | 2014-07-02 | 1.0 | 0.0 | **PASS — look-ahead DETECTED** |

**The tripwire earned its place immediately: it caught a bug in the oracle
itself.** The first implementation summed the foresight window from day `t`
rather than `t+1`, which — because the weight is applied with a one-day lag —
made the "oracle" a *momentum rule on yesterday's return*, and the tripwire
reported no look-ahead for an arm that was supposed to be nothing but
look-ahead. §9 records the rest.

### 1.4 The matched-average-exposure frontier — built FIRST (§A1)

Stage 2 of the runner computes, for `w̄ ∈ {0.00, 0.05, …, 1.00}` on every bed,
the constant-exposure policy: constant `w̄` in the book, `1 − w̄` in cash at
`rf`, **one switching trade charged inside the evaluated window** (the dumb
cousin is not handed a free rebalance), zero ongoing turnover. It is a pure
function of `w̄` and the bed — no parameters, no fitting, no knowledge of any
controller — and Stage 3 refuses to build a controller if the frontier file is
not already on disk. **It cannot have been tuned to lose.**

**BED-1 frontier (extract):**

| w̄ | net CAGR pp/yr | maxDD | CVaR5 monthly | P(ruin) |
|---:|---:|---:|---:|---:|
| 0.00 | 2.994 | 0.0% | 0.00% | 0.000 |
| 0.25 | 4.819 | −32.1% | −2.85% | 0.000 |
| 0.50 | 6.460 | −57.1% | −5.87% | 0.000 |
| 0.75 | 7.916 | −73.5% | −8.86% | 0.000 |
| 0.90 | 8.701 | −80.4% | −10.64% | 0.011 |
| **1.00** | **9.187** | **−84.1%** | **−11.82%** | **0.026** |

**The frontier is monotonically increasing in `w̄` on all three beds**
(BED-1 2.994 → 9.187; BED-2 2.994 → 12.625 *despite a −98.9% drawdown*;
BED-3 1.524 → 9.646). There is no interior optimum on the frozen wealth
objective. Every de-risking controller therefore starts the comparison behind,
and its only route to a positive number is timing.

**Ruin, with the definition stated as §A9 requires.** `P(ruin)` = the
probability that a **10-year (2,520 trading day)** path drawn by 21-day
circular block bootstrap (N = 2,000, seed 20260812) from the arm's own **net
daily return series** ever falls below **0.50 × its starting wealth**. It is a
property of the return distribution, computed identically for every arm and
every control.

---

## 2. THE HEADLINE — the matched-exposure comparison

`D_matched = netCAGR(controller) − netCAGR(constant policy at that controller's
OWN realised mean applied exposure)`, paired on the same days. MDE is the
80%-power minimum detectable effect from a 21-day circular block bootstrap
(N = 2,000) on the demeaned paired daily log-return difference, annualised.
**Below its own MDE is NOT DETECTABLE — never a kill and never a win.**

### 2.1 BED-1 — the primary bed, primary configurations

| controller | w̄ | net CAGR | **matched CAGR** | **D_matched pp/yr** | **its MDE** | ratio | blocks | halves | verdict |
|---|---:|---:|---:|---:|---:|---:|:--:|:--:|---|
| `H_ORACLE_k21` *(IMPOSSIBLE)* | 0.600 | 28.625 | 7.062 | **+21.563** | 2.076 | **10.39x** | 10/10 | yes | DIAGNOSTIC |
| `E_REGIME_ma200_2x2` | 0.739 | 8.956 | 7.854 | **+1.101** | 1.398 | 0.79x | 8/10 | yes | **DE_RISKING_ONLY** |
| `G_EVOLUTIONARY` | 0.659 | 9.156 | 8.324 | **+0.832** | 2.325 | 0.36x | 4/7 | no | **DE_RISKING_ONLY** |
| `F_EVENT_t1.0_f0.5` *(NON-PIT)* | 0.888 | 9.014 | 8.641 | **+0.373** | 1.051 | 0.36x | 7/10 | yes | **DE_RISKING_ONLY** |
| `D_LADDER_s0.15_d10` *(NIGHT-13)* | 0.754 | 8.262 | 7.938 | **+0.324** | 1.320 | 0.25x | 7/10 | no | **DE_RISKING_ONLY** |
| `G_RIDGE` | 0.394 | 6.917 | 6.764 | **+0.154** | 1.604 | 0.10x | 5/7 | no | **DE_RISKING_ONLY** |
| `C_VOLTGT_s0.15_w63` | 0.905 | 8.771 | 8.727 | **+0.044** | 1.393 | 0.03x | 6/10 | no | **DE_RISKING_ONLY** |
| `B_STATIC_50` | 0.500 | 6.460 | 6.460 | **+0.000** | 0.001 | — | — | — | identical by construction |
| `A_FULL` | 1.000 | 9.187 | 9.187 | **0.000** | 0.000 | — | — | — | reference |
| `C2_BETATGT_b1.5` | 1.000 | 9.187 | 9.187 | **0.000** | 0.000 | — | — | — | **degenerate, declared in advance** |
| `G_LIGHTGBM` | 0.403 | 6.448 | 6.820 | **−0.373** | 1.640 | 0.23x | 4/7 | no | **DE_RISKING_ONLY** |

**Not one pre-registered primary configuration of any real controller family
clears its own MDE on the primary bed.** The best of them, the regime
controller, reaches 0.79x.

`C2_BETATGT` is degenerate on BED-1 because the book *is* the market, so
`β_63d ≡ 1` and `w ≡ 1`. That degeneracy was declared in the prereg before the
run, and it is reported here rather than presented as a null.

### 2.2 BED-2 — the same market path, levered 2.15x

| controller | w̄ | D_matched pp/yr | its MDE | ratio | blocks | halves | verdict |
|---|---:|---:|---:|---:|:--:|:--:|---|
| `H_ORACLE_k21` *(IMPOSSIBLE)* | 0.596 | **+46.506** | 4.476 | 10.39x | 10/10 | yes | DIAGNOSTIC |
| `G_EVOLUTIONARY` | 0.613 | **+5.009** | 5.027 | **1.00x** | 5/7 | yes | DE_RISKING_ONLY |
| `E_REGIME_ma200_2x2` | 0.723 | **+3.199** | 3.092 | **1.03x** | 8/10 | yes | **TIMING_DETECTED** |
| `G_RIDGE` | 0.400 | +0.858 | 3.295 | 0.26x | 5/7 | no | DE_RISKING_ONLY |
| `F_EVENT_t1.0_f0.5` | 0.888 | +0.804 | 2.319 | 0.35x | 6/10 | yes | UNRESOLVED |
| `C_VOLTGT_s0.15_w63` | 0.591 | +0.306 | 2.797 | 0.11x | 6/10 | no | DE_RISKING_ONLY |
| `D_LADDER_s0.15_d10` | 0.484 | +0.247 | 1.895 | 0.13x | 5/10 | no | DE_RISKING_ONLY |
| `C2_BETATGT_b1.5` | 0.698 | +0.000 | 0.002 | — | — | — | **degenerate (constant 0.698), declared** |
| `G_LIGHTGBM` | 0.414 | −0.013 | 3.432 | 0.00x | 3/7 | no | DE_RISKING_ONLY |

Two rows deserve to be read slowly. `E_REGIME_ma200_2x2` clears on BED-2 at
**1.03x** its MDE, having *failed* on BED-1 at 0.79x — the same rule, on the
same market, at a different leverage, lands on opposite sides of the bar.
`G_EVOLUTIONARY` lands at **exactly 1.00x** and is called NOT DETECTABLE, which
is what a pre-registered rule compared on unrounded values does.

**The NIGHT-13 ladder, imported verbatim and not re-tuned, reproduces its
parent's own conclusion on 98 years instead of one window:** its timing content
over holding its own average is +0.247 pp/yr against an MDE of 1.895 — 0.13x.
NIGHT-13 measured the same thing at n=188 days and called it "not detectable
and pointing the wrong way". With 25,649 days it is still not detectable, now
pointing very slightly the right way, and still a rounding error beside the
thing it is meant to buy.

### 2.3 BED-3 — the only structurally different bed. **Nothing.**

| controller | w̄ | D_matched pp/yr | its MDE | ratio | blocks | halves | verdict |
|---|---:|---:|---:|---:|:--:|:--:|---|
| `H_ORACLE_k21` *(IMPOSSIBLE)* | 0.588 | **+23.173** | 5.077 | 4.56x | 7/7 | yes | DIAGNOSTIC |
| `G_EVOLUTIONARY` | 0.737 | +2.334 | 4.768 | 0.49x | 4/5 | yes | DE_RISKING_ONLY |
| `F_EVENT_t1.0_f0.5` | 0.905 | +0.581 | 2.520 | 0.23x | 3/7 | no | UNRESOLVED |
| `A_FULL` | 1.000 | 0.000 | 0.000 | — | — | — | reference |
| `C_VOLTGT_s0.15_w63` | 0.812 | **−1.585** | 3.680 | 0.43x | 4/7 | yes | DE_RISKING_ONLY |
| `D_LADDER_s0.15_d10` | 0.741 | **−1.654** | 3.537 | 0.47x | 4/7 | yes | DE_RISKING_ONLY |
| `E_REGIME_ma200_2x2` | 0.754 | **−1.878** | 4.287 | 0.44x | 4/7 | yes | DE_RISKING_ONLY |
| `G_RIDGE` | 0.532 | **−3.334** | 5.435 | 0.61x | 5/5 | yes | DE_RISKING_ONLY |
| `G_LIGHTGBM` | 0.415 | **−4.091** | 5.155 | 0.79x | 4/5 | no | DE_RISKING_ONLY |
| **`F_EVENT_DAILY_t1.0_f0.5`** *(NON-PIT)* | 0.920 | **−6.865** | **2.040** | **3.37x** | **7/7** | **yes** | **TIMING_HARMFUL** |

**Every point estimate below `F_EVENT` is negative, and the only detectable one
is the worst.** The daily-GPR conditioner is not point-in-time — the
Caldara-Iacoviello series is revised and backfilled, and the archive is a
2026-07 vintage — so it enters with an advantage no tradeable rule would have,
and it still **detectably subtracts 6.9 pp/yr** from simply holding the same
average exposure, with the sign in 7 of 7 blocks and both halves. That is the
single cleanest result in this document, and it is a negative one.

---

## 3. The one family that cleared, taken apart

Six configurations of controller E on BED-1 and BED-2, and the same six on
BED-3:

| config | BED-1 D / MDE | BED-2 D / MDE | **BED-3 D / MDE** |
|---|---:|---:|---:|
| `ma50_trend` | **+1.598 / 1.143 (1.40x)** | **+4.481 / 2.530 (1.77x)** | **−3.291** / 3.446 |
| `ma100_trend` | **+1.421 / 1.198 (1.19x)** | **+4.303 / 2.627 (1.64x)** | **−1.996** / 3.650 |
| `ma200_trend` | **+1.370 / 1.199 (1.14x)** | **+3.711 / 2.743 (1.35x)** | **−1.523** / 3.745 |
| `ma50_2x2` | +1.291 / 1.300 (0.99x) | **+3.839 / 2.847 (1.35x)** | **−3.232** / 3.776 |
| `ma100_2x2` | +1.143 / 1.361 (0.84x) | **+3.678 / 2.992 (1.23x)** | **−2.179** / 4.131 |
| **`ma200_2x2`** *(the pre-registered primary)* | +1.101 / 1.398 (**0.79x**) | **+3.199 / 3.092 (1.03x)** | **−1.878** / 4.287 |

**Decade by decade on BED-1, `ma50_trend` (pp/yr):**

| 1926-34 | 1935-44 | 1945-54 | 1955-64 | 1965-74 | 1975-84 | 1985-94 | 1995-04 | 2005-14 | 2015-24 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| +4.85 | +2.08 | +2.14 | +2.19 | +4.27 | +1.86 | +0.49 | +0.74 | **−1.04** | **−1.38** |

**Halves: +3.054 (1927-1975) vs +0.032 (1976-2024).** The first half is
**95 times** the second. `ma100_trend`'s second half is **+0.002 pp/yr** — two
ten-thousandths of a percent a year, and it is what satisfied the frozen "same
sign in both halves" coverage clause. The rule is not stable; it is a decayed
one, and its last two decades on the primary bed are negative.

> **What this licenses, exactly.** *A trend-state exposure rule on the CRSP
> value-weighted market contained timing content over its own average exposure
> between 1927 and 1975, at 1.1–1.8x an 80%-power ruler; over 1976-2024 the same
> rule's timing content is indistinguishable from zero on that market and
> negative on a real equal-weighted book.* It licenses nothing about the future,
> nothing about any book, and no size.
>
> **And the thing a search cannot see about itself.** The 50/100/200-day moving
> average on the US equity market since 1927 is plausibly the most examined rule
> in the history of the subject. `lint_prereg` returned PASS, and PASS means
> *unmatched against this programme's own 324 receipts* — the linter's own
> printed caveat is that "it knows nothing about the literature." A result that
> replicates a century-old published family on the same century-old data is
> exactly what §A7 exists to refuse to certify.

---

## 4. How much timing was even available — the oracle bound

Labelled **IMPOSSIBLE** everywhere it appears. It exists so a null on A-G can be
read as a statement about *observability* rather than about *availability*.

| bed | k=1 | k=21 (primary) | k=63 |
|---|---:|---:|---:|
| BED-1 | **+81.486 / MDE 4.388 (18.6x)** | **+21.563 / 2.076 (10.4x)** | **+12.613 / 2.216 (5.7x)** |
| BED-2 | +181.185 / 9.451 (19.2x) | +46.506 / 4.476 (10.4x) | +27.275 / 4.822 (5.7x) |
| BED-3 | +85.705 / 13.109 (6.5x) | +23.173 / 5.077 (4.6x) | +13.055 / 5.978 (2.2x) |

**The best observable controller captured 7.4% of the 21-day oracle's
matched-adjusted value on BED-1 and 9.6% on BED-2, and captured a negative
share on BED-3.**

This is WORLD-D's known-answer result arriving on real data. There, perfect
foresight over the bad months was worth +19.03%/yr while the best *observable*
precursor policy was worth +3.01%/yr — 84% of the value unreachable in
principle. Here 90-100% of it is unreached in practice. **The bet "exposure is
where the money is" survives; the bet "and we can see when" does not.**

---

## 5. Risk profiles — they qualify a verdict, they never rescue one (§A9)

Frozen before optimisation: max drawdown, CVaR(5%) of monthly net returns and
ruin probability are reported *beside* the wealth objective and never inside it.

**BED-1, controller vs its OWN matched cousin:**

| controller | maxDD | matched maxDD | **Δdd pp [MDE]** | CVaR5 | matched | P(ruin) | matched |
|---|---:|---:|---:|---:|---:|---:|---:|
| `A_FULL` | −84.1% | −84.1% | 0.0 [1.7] | −11.82% | −11.82% | 0.026 | 0.026 |
| `F_EVENT_t1.0_f0.5` | −78.1% | −80.0% | +1.8 [13.4] | −10.42% | −10.50% | 0.011 | 0.009 |
| `C_VOLTGT_s0.15_w63` | −65.9% | −80.6% | **+14.7 [13.4]** | −9.00% | −10.70% | 0.003 | 0.013 |
| `D_LADDER_s0.15_d10` | −56.5% | −73.8% | **+17.3 [13.8]** | −7.13% | −8.91% | 0.000 | 0.000 |
| `G_LIGHTGBM` | −46.2% | −24.3% | **−21.8** | −4.96% | −3.62% | 0.000 | 0.000 |
| `E_REGIME_ma200_2x2` | −45.6% | −72.9% | **+27.4 [26.2]** | −6.41% | −8.72% | 0.000 | 0.000 |
| `G_RIDGE` | −43.9% | −23.8% | **−20.1** | −4.87% | −3.53% | 0.000 | 0.000 |
| `H_ORACLE_k21` | −19.0% | −64.5% | **+45.5 [25.0]** | −2.45% | −7.06% | 0.000 | 0.000 |

**This is where H2 is refuted, and the refutation is worth more than the
headline null.** NIGHT-13's holdout found the constant control *shallower* than
the ladder (−11.50% vs −12.55%). Over 98 years it is the other way: vol
targeting, the ladder and the regime rule all draw down materially less than
their own average exposure held constant, and all three clear their (wide)
drawdown MDEs. **Path shape is not fully explained by mean exposure. Wealth
is.**

**And the learned controllers invert it.** Ridge and LightGBM sit at mean
exposure 0.39-0.40 — far *below* the rule-based arms — and still draw down
**20.1 and 21.8 pp deeper** than their own matched cousins. A fitted policy that
holds less and loses more is a policy whose timing is actively wrong, and it is
the WORLD-L failure mode with the sign made visible. **Stated with its
qualification: those two gaps carry no measurable MDE** — the planted-shave
method found no constant exposure shave whose drawdown effect is detected 80% of
the time against these arms' own violent paired null, so they are *directional*,
not detected. The three positive gaps above them do carry MDEs and clear them.

On BED-3 none of the drawdown gaps clears its MDE (the ruler is 21-22 pp on
5,285 days), and the event conditioner is 4.3 pp *deeper* than matched.

---

## 6. The learned controller — WORLD-L, on real data

Three families under expanding-window walk-forward, 42-trading-day purge and
embargo (twice the 21-day label horizon), every imputer/scaler/quantile fitted
inside the training fold, predictions used out-of-fold only. **99 model fits
across 33 folds.** First training block ends 1955-12-31 on BED-1/2 (retrain
every 5y) and 2011-12-31 on BED-3 (retrain every 3y, forced by the bed's
length, declared in prereg §11.4).

**Declared non-run:** conservative offline-Q. KNOWN-WORLDS §5 rates it **NOT
TRUSTED for action work** — a pessimism penalty has nothing to subtract from
cash's certain zero, so it is structurally biased toward the do-nothing action.
In an *exposure* trial that bias is the failure mode under test. It is recorded
in the denominator as a declared non-run, not an omission.

| family | bed | D_matched | its MDE | ratio | turnover/yr | cost bps/yr | mean w |
|---|---|---:|---:|---:|---:|---:|---:|
| evolutionary | BED-1 | +0.832 | 2.325 | 0.36x | 15.6 | 78.2 | 0.659 |
| evolutionary | BED-2 | +5.009 | 5.027 | **1.00x** | 14.9 | 74.7 | 0.613 |
| evolutionary | BED-3 | +2.334 | 4.768 | 0.49x | 0.6 | 19.4 | 0.737 |
| ridge | BED-1 | +0.154 | 1.604 | 0.10x | 12.3 | 61.6 | 0.394 |
| ridge | BED-3 | −3.334 | 5.435 | 0.61x | 7.7 | 231.1 | 0.532 |
| lightgbm | BED-1 | −0.373 | 1.640 | 0.23x | 13.0 | 65.1 | 0.403 |
| lightgbm | BED-3 | **−4.091** | 5.155 | 0.79x | **19.6** | **591.7** | 0.415 |

**H3 is confirmed in the exact form it was pre-registered.** The evolutionary
searcher — the learner that invented a timing rule in the no-timing world —
produced the most positive-looking learned number in the trial (+5.009 pp/yr on
BED-2) and it lands at **exactly 1.00x its own MDE**, i.e. not detectable. Its
halves are **+13.26 then +1.66**. Its BED-1 halves are **+4.69 then −0.73**.
And the cost column finishes it: gross +5.754, net +5.009, at 2x costs +4.264,
at 4x +2.772 on BED-2 — but on BED-1 the same arm runs +1.613 gross → +0.832
net → **+0.051 at 2x → −1.512 at 4x**. A policy that turns over 15x a year is a
policy whose verdict is a cost assumption.

**LightGBM on the real book is the clearest single failure:** 19.6x annual
turnover, **591.7 bps/yr of cost**, and −4.091 pp/yr against its own matched
cousin. Giving a fitted model a continuous exposure dial did what EXIT-LAB-1
found when it gave one an action space: it traded.

---

## 7. The §A10 decomposition

Every controller's gap to 100% exposure, split by the identity that holds to
1.8e-15. BED-1, pp/yr except captures:

| controller | Δ vs FULL | its MDE | avoided-loss | missed-upside | costs | bull cap | bear cap | re-entry eff | spells |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `H_ORACLE_k21` | **+19.438** | 3.195 | +50.545 | +31.669 | 0.279 | 0.653 | **0.400** | **−55.4** | 284 |
| `A_FULL` | 0.000 | — | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | — | 0 |
| `F_EVENT_t1.0_f0.5` | −0.173 | 1.263 | +10.404 | +10.839 | 0.035 | 0.881 | 0.876 | −4.07 | 71 |
| `E_REGIME_ma200_2x2` | −0.232 | 2.294 | +30.558 | +31.581 | 0.148 | 0.655 | 0.637 | −1.53 | 215 |
| `C_VOLTGT_s0.15_w63` | −0.416 | 1.677 | +15.514 | +16.559 | 0.034 | 0.819 | 0.816 | −3.30 | 55 |
| `G_EVOLUTIONARY` | −0.921 | 3.400 | +37.260 | +38.164 | 0.782 | 0.557 | 0.538 | −5.15 | 567 |
| `D_LADDER_s0.15_d10` | −0.925 | 2.165 | +27.873 | +29.681 | 0.030 | 0.676 | 0.668 | −2.24 | 50 |
| `B_STATIC_50` | −2.727 | 2.290 | +41.992 | +45.826 | 0.000 | 0.500 | 0.500 | 0.0 | 1 |
| `G_RIDGE` | −3.159 | 3.519 | +50.729 | +54.230 | 0.616 | 0.373 | 0.368 | +0.18 | 357 |
| `G_LIGHTGBM` | −3.629 | 3.464 | +49.769 | +53.683 | 0.651 | 0.380 | 0.381 | −0.14 | 315 |

**The capture columns say the whole thing in two numbers.** Every real
controller's bull capture and bear capture are **equal to within 0.02**
(0.881/0.876, 0.655/0.637, 0.819/0.816, 0.676/0.668, 0.500/0.500). Symmetric
capture is what *less risk* looks like. **The oracle is the only arm whose
captures separate: 0.653 bull against 0.400 bear.** That asymmetry is timing,
and no observable controller has any of it. NIGHT-13 reached the same
conclusion from six drawdown episodes; here it is 25,649 days and eleven arms.

**Re-entry efficiency** (annualised book excess return *during* de-risked
spells minus the unconditional rate; negative = out during genuinely bad
stretches) tells the same story with a sting. The oracle: **−55.4 pp/yr**.
The regime rule: −1.53. Vol targeting: −3.30 — *better* timing of its spells
than the regime rule, and less `D_matched`, because it de-risks a third as
often. **On BED-3 the sign flips for every rule-based arm** (ladder **+5.15**,
regime **+1.91**, vol target **+2.30**): on the real book, 2004-2024, the days
these controllers sat out were days the book did *better* than average. That is
why BED-3's `D_matched` column is negative, and it is a mechanism, not a mood.

---

## 8. Robustness

**Cost sensitivity of `D_matched` (pp/yr), BED-1:**

| controller | 0x (gross) | 1x (decides) | 2x | 4x |
|---|---:|---:|---:|---:|
| `H_ORACLE_k21` | +21.841 | +21.563 | +21.284 | +20.726 |
| `E_REGIME_ma200_2x2` | +1.249 | +1.101 | +0.954 | +0.658 |
| `G_EVOLUTIONARY` | +1.613 | +0.832 | +0.051 | **−1.512** |
| `F_EVENT_t1.0_f0.5` | +0.408 | +0.373 | +0.339 | +0.269 |
| `D_LADDER_s0.15_d10` | +0.354 | +0.324 | +0.294 | +0.234 |
| `G_RIDGE` | +0.769 | +0.154 | −0.462 | **−1.693** |
| `C_VOLTGT_s0.15_w63` | +0.078 | +0.044 | +0.010 | −0.059 |
| `G_LIGHTGBM` | +0.277 | −0.373 | −1.023 | **−2.323** |

**No verdict in this trial is created by the cost model, and one class of arm is
destroyed by it.** The rule-based controllers are nearly cost-insensitive (they
turn over 0.6-3.0x a year). Every learned arm crosses zero between 1x and 4x.
EXIT-LAB-1's opposite qualification — a verdict that lived *entirely* in the
cost term — does not recur here.

**Regime blocks and halves** are in §3 and in the receipts for all 144 arms.
**Sign consistency was checked on all of them, not only the winners.**

**Beds.** The measured excess-return correlations are `BED1~BED2 = 1.000000`,
`BED1~BED3 = 0.957337`, `BED2~BED3 = 0.957337`. BED-1 and BED-2 are one path;
BED-3 is a different book but **still the same asset class in an overlapping
period**, so even "BED-3 disagrees" is a weaker independence statement than it
looks. There is no out-of-market replication in this chunk and none is claimed.

---

## 9. §20 batch self-check and the full search denominator

### 9.1 The batch, checked against itself

| bed | arms (excl. FULL) | mean abs pairwise corr of daily `D_matched` | **effective distinct arms** |
|---|---:|---:|---:|
| BED-1 | 47 | 0.4045 | **2.40** |
| BED-2 | 47 | 0.4098 | **2.37** |
| BED-3 | 47 | 0.4851 | **2.02** |

**Forty-seven configurations are worth about two and a half independent
chances.** At the one-sided 5% rate implied by the MDE construction, the
expected false-positive count is therefore roughly **0.12 per bed** and ~0.24
across the two independent bed groups — not 2.4. Observed: **one mechanism
detected positive** (family E, on the BED-1/BED-2 group, in three and six
costume variants respectively) and **one detected negative** (the daily-GPR
conditioner on BED-3). One positive against an expectation of ~0.2 is not
noise-shaped; it is also not replication-shaped, and §3 explains it better than
either — the effect is real, old, and gone.

### 9.2 Every configuration executed, including the ones that failed

| stage | configurations | note |
|---|---:|---|
| beds built | 3 | 25,649 / 25,649 / 5,285 evaluation days |
| **matched-exposure frontier** | **63** | 21 constant policies x 3 beds, on disk before any controller |
| controller configs built | 135 | 45 per bed (A 1, B 1, C 12, C2 3, D 9, E 6, F 10, H 3) |
| learned families | 9 | 3 families x 3 beds |
| **arms scored against matched** | **144** | 0 skipped, 0 voided |
| learned model fits | **99** | 33 folds x 3 families |
| perturbation proofs | 24 | 8 primaries x 3 beds, **24/24 bit-identical** |
| look-ahead tripwires | 3 | 3/3 caught the oracle |
| cost-sensitivity cells | 132 | 33 primary arms x 4 multipliers |
| ruin simulations | 288 | 2 per arm (arm + matched), N=2,000 paths each |
| **declared non-run** | **1** | conservative offline-Q (KNOWN-WORLDS §5) |

**The non-overlapping total: 207 scored policies** (144 controller arms + 63
frontier constant policies — the 144 *are* the 135 built configs plus the 9
learned families, so those rows are not added twice), evaluated through 99 model
fits, 24 perturbation proofs, 3 tripwires, 132 cost-sensitivity cells and 288
ruin simulations. **0 skipped, 0 voided, 0 dropped for being unflattering.**

### 9.3 What went wrong, recorded rather than tidied away

1. **The oracle was not an oracle.** The first implementation summed the
   foresight window from day `t`; because weights are applied with a one-day
   lag, that made it a momentum rule on *yesterday's* return. **The look-ahead
   tripwire caught it** by reporting no look-ahead in the one arm built entirely
   out of look-ahead. Fixed to `t+1 … t+k`.
2. **The first tripwire was the wrong test, and BED-3 refused it.** The original
   assertion was that the *random multiplicative* perturbation must flip the
   k=21 oracle's weight. It does not have to: a probe can sit 20 days after its
   own decision date, so only 1 of 21 foresight days is post-probe and a random
   rescaling of one day need not flip the window's sign. The run aborted on
   BED-3. **The assertion was rebuilt (post-probe excess returns negated), not
   the failing bed dropped** — EXIT-LAB-1's rule that an assertion which is
   wrong is worse than no assertion.
3. **`detectable` was true for a degenerate arm.** An arm identical to its own
   control has a zero effect *and* a zero ruler, and `0 >= 0` read as a
   detection. Guarded to require a strictly positive MDE.
4. **The breakthrough clause counted BED-1 and BED-2 as two beds.** They are one
   path. Replaced with a **measured** independence check (excess-return
   correlation 1.000000 → one group), which is what turned
   `breakthrough_eligible` from `true` to `false`.
5. **Two zero rows in the 2026-07 daily-GPR vintage** produced `log(0)`. Dropped
   and counted, never imputed.
6. **The ladder's drawdown overflowed float64** as a 98-year levered cumulative
   product; moved to log space. Values unchanged where both were finite.

Nothing was dropped for being unflattering: the three trend configurations that
cleared are reported although they are non-primary grid variants; the
`ma200_2x2` primary failure is reported although the family "won"; the
evolutionary arm at exactly 1.00x is reported as not detectable; and the only
clean non-oracle detection in the trial is the negative one.

---

## 10. What this cannot tell us

1. **Nothing here is certified (§A7).** BED-3 is CRSP 2002-2024, interrogated
   across many nights of this programme. BED-1/2 extend to 1926, but a moving
   average on the US market since 1927 is public, famous and exhaustively mined.
   **Certification requires genuinely untouched data or the forward paper
   tournament, and this chunk has neither.**
2. **No alpha, Sharpe, skill or money claim.** No lane, no shadow default, no
   sizing change, no product default, no buy/sell language. Nothing moves.
3. **A null on these eight controllers is a null on THESE controllers.** The
   oracle bound says 90-100% of the available timing value went uncaptured, so a
   better-*observed* controller — different data, faster clock, a conditioner
   this trial did not have — could still find something. The MDE beside every
   arm says exactly how large it would have to be.
4. **Detection is not stability.** The family that cleared did so at 1.0-1.8x
   its ruler with a second half 95x smaller than its first. On this programme's
   own standard (§19 in both directions) that is a measurement, not a rule.
5. **BED-1 and BED-2 have no idiosyncratic gap risk**, and BED-3's 1,500-name
   equal-weighted book is not a 12-name concentrated one. A binary readout gaps
   *through* a daily overlay with a one-day lag. NIGHT-13 stated this limitation
   and it is only partly answered here.
6. **Controller F is NOT point-in-time.** The GPR series is revised and
   backfilled; the arm is an optimistic bound, labelled `NON_PIT` throughout, and
   its one detectable result is negative anyway.
7. **This is a single-asset exposure overlay.** It says nothing about which
   names to hold, nothing about intraday execution, nothing about tax lots,
   liquidity needs, or any constraint a real saver optimises. The book's own
   rebalancing cost is not charged on BED-3 (every arm shares the same book, so
   it cancels in every comparison) — declared, not discovered.
8. **The learned arms have a shorter window** (out-of-fold from 1956 on
   BED-1/2, 2012 on BED-3), so their MDEs are wider than the rule-based arms' by
   construction. Their matched controls are computed on their own windows, so
   the primary metric is unaffected; cross-family comparison of the *raw* numbers
   is not like-for-like.
9. **Below MDE is not a kill (§19).** Forty-two of BED-1's forty-five real
   configurations came back NOT DETECTABLE, and forty-four of BED-3's. **None of
   them is refuted.** Each is below this instrument's resolution at 25,649
   (respectively 5,285) days, and the resolution is printed beside every one of
   them.

---

## 11. What this does to the standing bet

Five nights, then EXIT-LAB-1, said the same thing: *the only thing this
programme has repeatedly measured as large is exposure — whether you are
invested, and how much.* This chunk was built to ask the obvious next question,
and it answers it in the narrowest available way.

> **Exposure is large. Exposure *timing* is not — not by any observable
> controller we built, on any bed we can call a replication, at any cost level.
> What repeatedly survives is the level, not the schedule: the matched-average-
> exposure control does everything the controllers do to wealth, and the
> constant-exposure frontier has no interior optimum on 98 years of any of these
> beds. The value that a 21-day oracle proves is sitting there — 10x its own
> ruler — remains, after eight controllers and ninety-nine model fits,
> essentially entirely unobserved.**

The one qualification, and it is the one worth carrying forward: **drawdown is
not fully explained by mean exposure even when wealth is.** Vol targeting, the
NIGHT-13 ladder and the regime rule each cut the 98-year drawdown by 14-27 pp
*beyond* what their own average exposure held constant achieves, above their own
(wide) rulers — while a fitted policy does the opposite. If there is a live
question left in exposure, it is a **path-shape** question and not a wealth
question, and §A9 forbids this trial from promoting it to one after the fact.

**None of this is a forward record and none of it moves a lane.**
