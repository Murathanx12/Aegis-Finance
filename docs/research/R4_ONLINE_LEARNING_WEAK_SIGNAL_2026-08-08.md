# R4 — Online Belief Updating in Very Low SNR: Methods Survey (deep-research receipt)

**Provenance:** produced 2026-08-08 by an autonomous Opus deep-research agent
(47 web fetches). Archived verbatim as the receipt behind
`RESEARCH_SYNTHESIS_2026-08-08_R1-R4.md`. Not a registration — the
hyperparameter card becomes binding only through the registered posterior-store
build (P1 task 3). Items the agent derived itself are marked "arithmetic mine."

---

## (a) Executive summary

- **The binding constraint is arithmetic, not algorithmic.** At δ ≈ 5bps against σ ≈ 150bps daily noise, a t=2 read needs n ≈ (2σ/δ)² = 3,600 independent resolutions. With K≈30 cells sharing ~30 resolutions/week (~52/cell/year) and a clustering deflation of ~2×, a **per-cell** effect-size posterior needs ~140 years. Per-cell effect sizes are *unidentified*; only the **pooled** hierarchical mean is estimable in useful time. Single most important design implication: shrink almost all the way to the pool, and say so.
- **Hit-rate legs resolve ~10× faster than effect-size legs.** 0.55 vs 0.50 needs n≈400 (×2 for clustering = 800). Pooled across the whole ledger that's ~6 months; per-cell still ~15 years. Run the Beta layer as the *fast* learner (attention, calibration) and the hierarchical-Normal layer as the *slow* learner (promotion evidence).
- **The right prior scale is NOT the published-finance one.** Chen & Zimmermann estimate σ_θ ≈ 3.0 in t-units — but for a *selection-filtered* published set (t>2), which is why their shrinkage is only 10–15%. An unselected internal claim pool should use σ_θ ≈ 0.5–1.0, implying **50–80% shrinkage**.
- **Our own measured base rate sets the promotion bar, and it is brutal.** With π₁ ≈ 1.5–5% real (our 3/196 money legs, matching Chen-Velikov), Efron's local-FDR at lfdr ≤ 0.10 lands at **t ≈ 3.9–4.9** — stricter than Harvey-Liu-Zhu's 3.0, far stricter than a 1.5 bar.
- **Hedge/exponential-weights regret guarantees are vacuous at this scale.** With N=30 experts and n=500 rounds, the bound √((n/2)·lnN) ≈ 29 cumulative → **0.058 Brier/round** of allowed regret — larger than any plausible skill difference. ~68,000 rounds (≈43 years) needed for the guarantee to bite at 0.005 Brier/round. Use shrunk-toward-uniform weights, not Hedge.
- **The forecast-combination puzzle applies with force:** equal weights beat estimated weights when weights are noisy. Default to uniform; move toward inverse-Brier only as a cell's calibration ESS grows.
- **Extremizing is the wrong default here.** Claim-types are correlated (same macro drivers). Lichtendahl et al. show optimal Bayesian aggregators do *not* always extremize; with redundant information the correct move is anti-extremizing. Start at exponent a = 1.0.
- **Correlated resolutions are the #1 premature-convergence risk.** Kish's design effect, DEFF = 1 + (m̄−1)ρ, implemented as a **power-likelihood / tempered update** with η = 1/DEFF. Day-1: ρ=0.2, m̄=6 → η=0.5 (halve every day's evidence).
- **Adaptivity and detectability are in direct conflict at this SNR.** An EWMA half-life h caps effective sample size at ≈ 2h/ln2 ≈ 2.9h. Any half-life fast enough to track regime drift caps ESS below the detection threshold. Resolution: **two-timescale posteriors** — fast for attention, slow (BOCPD-gated *partial* reset, never hard reset) for promotion.
- **Bandit attention allocation biases the very estimates being accrued.** Keep a uniformly-randomized attention floor (ε ≈ 0.2) so unbiased pooled estimates always exist.

---

## (b) Per-topic sections

### 1. Hierarchical / empirical-Bayes shrinkage for small-n cells

**The canonical machinery.** James-Stein and its empirical-Bayes reading (Efron & Morris, 1975, *JASA* 70(350):311–319) gives, for cell k with observed mean ȳ_k and sampling variance σ²/n_k under a N(μ₀, τ²) prior:

```
E[θ_k | ȳ_k]  =  (1 − B_k)·ȳ_k  +  B_k·μ₀
B_k = (σ²/n_k) / (σ²/n_k + τ²)          ← shrinkage weight
```

With n_k = 3 and τ small relative to σ, B_k → 1: the cell is essentially fully pooled. That is the correct answer, not a failure. Efron's *Large-Scale Inference* (2010, IMS Monographs 1, Cambridge UP) is the reference text for the many-parallel-problems regime and the local-FDR apparatus in §5.

**Setting the hyperprior with K ~ 20–50 cells.** Gelman & Hill (2007, ch. 11): below ~5 groups there is not enough information to estimate group-level variation; 5–10 Level-2 units is the practical floor. K=20–50 is comfortable — **but the hyperprior on τ still dominates when the n_k are tiny.** Gelman (2006, *Bayesian Analysis* 1(3)): inverse-gamma(ε,ε) "noninformative" priors are actively harmful here; use the **half-t / half-Cauchy family**, scale set slightly larger than the plausible variability.

**Finance calibration of the scale — the key number.** Chen & Zimmermann (2022/23, "Publication Bias in Asset Pricing Research", arXiv:2209.13623) fit exactly this model, in t-units:

```
t_i = θ_i + Z_i ,  Z_i ~ N(0,1) ,  θ_i ~ N(0, σ_θ²)
publication if t_i > 2
→  σ̂_θ ≈ 3.0 ,  shrinkage ≈ 10–15% ,  FDR < 10%
```
(207 predictors, 140 papers.) **Do not import σ_θ = 3.0** — it is that large precisely because the sample is selection-filtered at t>2. Chen (2022/24, "Do t-Statistic Hurdles Need to be Raised?", arXiv:2204.10275): published t-stats are biased upward **by at most 28%**, published-predictor FDR **at most 22%** (95% conf.); but the share of false factors π_F is only bounded to 0–70% (90% CI) and the FDR-5% t-hurdle to 0–3.0 (90% CI). **Shrinkage and local-FDR on the observed set are strongly identified; extrapolated hurdles are not** — a direct argument for the ledger design: estimate shrinkage and lfdr, don't estimate a hurdle from unobserved failures.

For an *unselected* internal pool, the empirical anchor is Chen & Velikov (2023, *JFQA* 58(3):968–1004): net of spreads, decay, and the post-2000 era, **the average anomaly nets 4 bps/month; the strongest at best 10 bps.** Our EXT-POWER-1 finding of 3/196 money legs reproduces this. Together: π₁ ≈ 1.5–5% and σ_θ ≈ 0.5–1.0, i.e. shrinkage factor σ_θ²/(1+σ_θ²) = **0.20–0.50** → keep only 20–50% of a cell's raw signal.

**Fund-skill precedent.** Jones & Shanken (2005, *JFE* 78:507–552, NBER w9392) is the direct template: fund alphas drawn from a Normal whose mean and variance are estimated across all funds → precision-weighted individual estimates; prior independence across funds is untenable once learning-across is allowed. Pástor & Stambaugh mispricing-uncertainty priors (prior SD of alpha ~5–9%/yr) — UNVERIFIED, snippet only. Harvey & Liu ("Backtesting" SSRN 2345489; "Lucky Factors"): the multiple-testing haircut is **nonlinear** — top Sharpes lightly penalized, marginal ones heavily. That non-linearity is exactly what an EB posterior mean produces automatically — a good reason to prefer the EB formulation over a fixed haircut.

**Updating the hyperprior online.** Method-of-moments beta-binomial / Normal-Normal EB, recomputed nightly across all K cells, with a half-Cauchy hyperprior to stabilize; **freeze the hyperprior update when fewer than ~10 cells have n_k ≥ 10** (below that, re-estimating τ̂ daily just injects correlated noise into every cell simultaneously).

**Guard: limited translation.** Efron-Morris limited-translation estimators cap how far any single cell is pulled from its raw estimate (typically ~1 SE), preserving genuinely extreme cells. Recommended as a display-layer guard. *(Concept verified; specific cap value UNVERIFIED.)*

### 2. Bandit-style attention allocation

**Why bandits, not capital.** Reward = *information yield per unit of scrutiny*, never P&L — consistent with D3. Arms = claim-types; reward = "produced a resolvable, informative claim" or "reduced posterior entropy."

**Nonstationary variants.** Garivier & Moulines (2008/2011, arXiv:0805.3415, ALT 2011): Discounted-UCB and Sliding-Window-UCB match the lower bound up to log factors. Reference implementation (SMPyBandits):

```
SW window:  τ = 2·sqrt( T · log T / (1 + Υ_T) )      [verified]
default discount:  γ = 0.95   (DiscountedklUCB, DiscountedThompson)
```
The companion rule γ = 1 − ¼·√(Υ_T/T) is widely quoted but UNVERIFIED from the paper. Sanity check anyway: T=1,250 trading days, Υ_T=5 regime breaks → γ ≈ 0.984; the *verified* τ formula gives a ~77-day window — the two agree, corroborating a ~0.985/day discount.

**Thompson-specific.** Raj & Kalyani (2017, arXiv:1707.09727) apply **discounting directly to the prior's parameters** — α ← γα, β ← γβ each round — exactly the mechanism wanted for Beta cells (identical to ESS decay). Qi et al. (2025, *Entropy* 27(1):51): DS-TS / SW-TS with Õ(√(T·B_T)) regret vs B_T breakpoints. All note: **γ and τ require a priori assumptions about temporal dynamics** — the argument for tying them to in-house BOCPD rather than guessing.

**Restless arms.** Claim-type quality decays whether or not you look (crowding, post-publication decay) → formally Whittle's restless bandit; practically, at K=30, discounted TS with a decay term approximates it adequately (UNVERIFIED as a formal claim).

**Critical guardrail.** Adaptive allocation makes n_k endogenous to ŷ_k → the pooled EB estimates become selection-biased. Mitigations: (i) hold back a uniformly-randomized ε ≈ 0.2 of attention; (ii) report the pooled estimate on the randomized slice as the honest number; (iii) per-cell exploration floor (≥1 slot/2 weeks) so cells at n=3 can escape.

### 3. Calibration-weighted forecast combination

**Start from the null result.** The *forecast combination puzzle* — equal-weight averages routinely beat estimated optimal weights (Stock & Watson 2004; Smith & Wallis 2009; Claeskens et al. arXiv:1505.00475). Mechanism is exactly our problem: **estimated weights are poorly identified and highly variable**. ECB SPF studies: PCA, trimmed means, optimal weights all fail to beat the simple mean.

**But linear pooling of calibrated forecasts is itself miscalibrated.** Ranjan & Gneiting (2010): any linear combination of calibrated forecasts is uncalibrated and lacks sharpness — hence the GJP lineage's **log-odds (logarithmic) pooling**: recalibrate individually, average in logit space, invert. A reported result in this lineage: 26.7% Brier improvement over simple averaging, better on 86% of problems *(UNVERIFIED — snippet; attribution likely Satopää et al. 2014, IJF)*.

**Extremizing — and why not, here.** Baron, Mellers, Tetlock, Stone & Ungar (2014, *Decision Analysis* 11(2):133–145) give the two reasons averages are underconfident. But Lichtendahl, Grushka-Cockayne, Jose & Winkler (2017, arXiv:1705.02391), verified: **optimal aggregators do not always extremize** — underconfidence of the average comes from *conditionally independent* information; when forecasters share information (our case: claim-types driven by the same macro prints), the average is already over-confident and the optimal move is **anti-extremizing**. Specific numeric extremizing exponents (1.5/2.5): UNVERIFIED, no fetchable source states them.

**Online learning with expert advice — the regret bound is vacuous here.** Cesa-Bianchi & Lugosi (2006, Thm 2.2):

```
R_n ≤ (ln N)/η + n·L²·η/8 ;   η* = sqrt(8·lnN/n)  →  R_n ≤ sqrt((n/2)·lnN)
```
At N=30, n=500 resolutions, Brier loss in [0,1] → R ≤ √(250 × 3.40) ≈ 29.2 cumulative = **0.058 Brier per round** — an order of magnitude larger than any real skill difference. To get per-round regret below 0.005: n ≈ 68,000 rounds ≈ **43 years at 30/week**. *(Arithmetic mine, from the verified bound.)* For nonstationary experts, Chernov & Zhdanov (2010, arXiv:1005.1918, ALT 2010) generalize the Aggregating Algorithm to discounted loss — the principled version of "forget old Brier scores."

**Conclusion for topic 3:** log-odds pooling with per-cell recalibration, weights shrunk hard toward uniform:
```
w_k ∝ (1−λ_k)·(1/K) + λ_k·softmax(−Brier_k/T) ,   λ_k = n_eff,k / (n_eff,k + n₀) ,  n₀ ≈ 100
```
Treat exponential weighting as a regularizer with a deliberately small learning rate, not a regret-optimal algorithm.

### 4. Nonstationarity: discounting old resolutions

**The exact trade-off.** EWMA with decay λ has n_eff = (1+λ)/(1−λ) ≈ 2/(1−λ). In half-life terms (λ = 2^(−1/h)):

| half-life h (resolutions) | λ | n_eff ceiling |
|---|---|---|
| 30 | 0.9772 | ~88 |
| 60 | 0.9885 | ~174 |
| 120 | 0.9942 | ~346 |
| 250 | 0.9972 | ~722 |
| ∞ (no decay) | 1.0 | n |

Against §1's requirement of n ≈ 3,600–7,200 for a 5bps effect, **no half-life short enough to be adaptive can ever reach detectability. Not a tuning problem — structural.** (Framing per Luxenberg & Boyd, "Exponentially Weighted Moving Models," arXiv:2404.08136.)

**Therefore: two timescales, explicitly separated.**
- **Fast layer** (hit-rate Betas, calibration weights, bandit attention): half-life ≈ 60–90 resolutions. Purpose is *steering*; steering tolerates noise.
- **Slow layer** (hierarchical-Normal effect sizes, promotion evidence): **no exponential decay at all.** Nonstationarity handled by changepoints, not continuous forgetting.

**Changepoint-gated partial reset.** Adams & MacKay (2007, BOCPD, arXiv:0710.3742) — already in-house (`anomaly_detector.py`). Constant hazard H(r) = 1/λ; λ_gap = 250 reported in one application (search-level verification only). Use the run-length posterior as the gate:

> On P(r_t < 5) > 0.5, **do not reset the slow posterior to prior**. Multiply its effective sample size by 0.5 and inflate τ² by 2×. A hard reset at n≈3,600-required is equivalent to permanently disabling the effect-size learner.

### 5. Guardrails

#### 5a. Correlated resolutions → ESS deflation

Many claims resolving off the same CPI print are one observation wearing many hats.

**Kish design effect:**
```
DEFF = 1 + (m̄ − 1)·ρ ,     n_eff = n / DEFF
```
m̄ = mean resolutions per cluster (per macro event / calendar day), ρ = intraclass correlation. Magnitude matters: a documented example gives ρ=0.73, m=20 → DEFF ≈ 14.9, collapsing n=1,000 to **n_eff ≈ 67**. Our realistic case (ρ≈0.2, m̄≈6) → DEFF = 2.0 — a doubling of every required sample size.

**Beta-Binomial overdispersion** is the model-based version. For sequential online updating, the cleanest implementation is **likelihood tempering / power prior**: raise the day's likelihood to η = 1/DEFF:

```
posterior ∝ prior · L(data)^η ;   Beta form:  α ← α + η·hits,  β ← β + η·misses
```
Power priors (Ibrahim & Chen lineage; normalized power prior arXiv:2204.05615) and "safe Bayes" / generalized Bayes with learning rate η ∈ (0,1] (Safe-Bayesian GLR arXiv:1910.09227; coarsening arXiv:1506.06101) establish the fractional likelihood as the correct correction when the posterior would otherwise **over-concentrate** under misspecification — precisely the premature-convergence failure mode. η can itself be estimated.

For the effect-size layer, the frequentist complement is mandatory: **cluster/block-bootstrap by resolution day**, reported as the primary uncertainty.

#### 5b. Multiple comparisons when promoting the best of K

Three simultaneous problems: multiplicity, winner's curse (the selected cell's estimate is upward-biased by construction), selection-invalid naive intervals.

**Do not use Storey q-values at K=20–50.** Direct empirical investigation of low-dimensional settings (PMC5833079): with **≤32 hypotheses**, Storey's/Strimmer's q-value methods most often falsely reject true nulls because π₀ estimation is biased; π₀-estimating methods "should only be applied in high-dimensional settings"; with few hypotheses **FWER methods (or BH) preferred**. K is squarely in the danger zone. Use Benjamini-Hochberg or Holm, **not** adaptive-π₀ methods.

**Better: externally-anchored local FDR.** π₀ does not need estimating from K=30 cells — we have a prior from EXT-POWER-1 (3/196 money legs) and Chen & Velikov. Efron's local FDR:
```
lfdr(t) = π₀·φ(t) / [ π₀·φ(t) + π₁·f₁(t) ] ,   f₁ = N(0, 1+σ_θ²)
```
Solving for t at lfdr = 0.10 *(arithmetic mine, standard formula)*:

| π₁ | σ_θ | t required for lfdr ≤ 0.10 |
|---|---|---|
| 0.03 | 1.0 | **4.9** |
| 0.03 | 2.0 | **4.0** |
| 0.05 | 2.0 | **3.9** |
| 0.10 | 2.0 | 3.5 |

The promotion bar, derived from *our own measured base rate*, is **t ≈ 3.9–4.9** — above Harvey, Liu & Zhu's t > 3.0 (2016, *RFS* 29(1):5–68), far above 1.5. Fully consistent with the §34 measurement that SPY prints t≈1.1 over 72 months: **no 72-month confirm window can clear a base-rate-honest promotion bar. Design conclusion, not tuning conclusion** — independently confirms "the forward paper lane is the adequate instrument."

**Deflated Sharpe Ratio** (Bailey & López de Prado 2014, SSRN 2460551) is the strategy-level analogue: deflates for the **effective number of independent trials** (clustered, not literal count), variance of trial Sharpes, sample length, skew/kurtosis. Structural parallel: DSR's "effective N via clustering" is the *same correction* as §5a's ESS deflation, applied on the trials axis. **Apply both — not redundant.**

**Winner's curse.** The EB posterior mean is itself a winner's-curse correction, automatically nonlinear (as Harvey & Liu require). Report the *shrunk* estimate as the headline for any promoted cell; raw only as diagnostic. Selective-inference refs (arXiv:2607.18545, arXiv:2511.06318) — UNVERIFIED, surfaced not fetched.

**Power reality check** (Grinold & Kahn lineage): SE of estimated IR ≈ 1/√N periods; 36 months → SE ≈ 0.17; industry norm 3–5 years minimum. Consistent with the MDE ≈ 0.6 annualized Sharpe finding.

---

## (c) Day-1 hyperparameter card

| # | Parameter | Day-1 default | One-line justification |
|---|---|---|---|
| 1 | **Beta prior, new claim-type cell** | `Beta(m₀·p₀, m₀·(1−p₀))`, **m₀ = 20**, p₀ = the cell's mechanical base rate (0.5 for a directional call) | Prior ESS 20 → an n=3 cell is 87% prior-driven; a 3-for-3 run cannot promote itself; within Gelman-Hill's weakly-informative regime. |
| 2 | **Hierarchical mean μ₀ (hit rate)** | Pooled cross-cell mean, re-estimated nightly by beta-binomial method-of-moments; **freeze the update** unless ≥10 cells have n_k ≥ 10 | Shrinkage target must be the pool, not 0.5 (Efron-Morris); freezing prevents noisy nightly τ̂ from perturbing all K cells simultaneously. |
| 3 | **Hyperprior on cross-cell hit-rate SD** | `τ_p ~ half-Cauchy(0, 0.05)` | Gelman (2006) explicit recommendation for few groups; scale 0.05 puts ±5pp cross-cell spread in the bulk. Never inverse-gamma(ε,ε). |
| 4 | **Hierarchical-Normal effect-size prior** | `θ_k ~ N(μ_pool, σ_θ²)` in **t-units with σ_θ = 0.75**; hyperprior `σ_θ ~ half-Cauchy(0, 1)` | C-Z's σ̂_θ ≈ 3.0 is selection-filtered (t>2); unselected pool → σ_θ=0.75 → retain **36%** of raw signal, matching π₁≈1.5–5% (Chen-Velikov; our 3/196). |
| 5 | **Effect-size prior in bps** | `θ_k ~ N(0, (4 bps)²)` per-resolution mean; hyperprior scale `half-Cauchy(0, 5 bps)` | Chen & Velikov: average anomaly nets 4 bps/month, best ≈10 — the empirical ceiling on a real cell. |
| 6 | **Resolution-correlation ESS deflation** | `η = 1/DEFF`, `DEFF = 1 + (m̄−1)·ρ̂`; **day-1 ρ = 0.20, m̄ = same-day resolution count** → η ≈ 0.5 at m̄=6. Apply as `α += η·hits, β += η·misses`. Re-estimate ρ̂ from within-day ICC once ≥300 resolutions exist. | Kish design effect as tempered/power likelihood — the "safe Bayes" fix for posterior over-concentration, exactly the premature-convergence mode. |
| 7 | **Decay half-life — FAST layer** (hit-rate Betas, calibration weights, bandit) | **h = 75 resolutions** (λ = 0.9908 per resolution), ESS ceiling ≈ 218 | Enough memory to distinguish 0.55 from 0.50 within-pool while turning over inside a year. Steering tolerates noise. |
| 8 | **Decay half-life — SLOW layer** (effect sizes, promotion evidence) | **No exponential decay (h = ∞).** Nonstationarity handled only by #9. | Any adaptive half-life caps ESS far below the n≈3,600–7,200 needed for a 5bps effect. Decay here permanently prevents detection. |
| 9 | **Changepoint handling** | BOCPD, constant hazard **1/λ with λ = 250 trading days**. On `P(r_t < 5) > 0.5`: **partial reset** — multiply slow-layer ESS by 0.5, inflate τ² by 2×. **Never hard-reset.** | Adams & MacKay (2007); partial reset is the only reset compatible with #8's sample-size requirement. |
| 10 | **Thompson discount (attention bandit)** | **γ = 0.985 per day** applied to (α,β) directly; ≈ γ = 0.99 per resolution | Raj & Kalyani (2017) discount the prior parameters directly. γ=0.985/day ≈ Garivier-Moulines' 77-day SW window at T=1,250, Υ_T=5. (SMPyBandits' γ=0.95 default is far too aggressive at 6 resolutions/day.) |
| 11 | **Exploration floor / randomized holdout** | **ε = 0.20** of attention uniformly at random; per-cell floor ≥1 slot per 2 weeks | Adaptive allocation makes n_k endogenous and biases pooled EB estimates; the randomized slice is the only place an unbiased pooled number can live. |
| 12 | **Combination rule** | **Log-odds pooling** after per-cell recalibration; `w_k ∝ (1−λ_k)/K + λ_k·softmax(−Brier_k/T)`, `λ_k = n_eff,k/(n_eff,k + 100)` | Ranjan & Gneiting (2010): linear pools of calibrated forecasts are miscalibrated. Shrink-to-uniform per the combination puzzle: estimated weights can't beat 1/K until ~100 resolutions. |
| 13 | **Extremizing exponent** | **a = 1.0 (none).** Revisit only after measuring pairwise cross-cell forecast correlation; cap a ≤ 1.5 even then. | Lichtendahl et al. (2017): with shared/redundant information (macro-driven cells) the optimal move is anti-extremizing. |
| 14 | **Hedge / EWA learning rate** | Regularizer only: **η = 0.05**, not η* = √(8·lnN/n) ≈ 0.23 | Optimal η yields per-round regret 0.058 Brier at N=30, n=500 — larger than any real skill gap. Small η keeps weights near uniform, which the puzzle says is right anyway. |
| 15 | **Promotion bar to registered track** | **local FDR ≤ 0.10 with π₁ = 0.03, σ_θ = 2.0 ⟹ t ≥ 4.0** on the block-bootstrapped, cluster-deflated statistic. Plus DSR > 0.95 with N = *effective* (clustered) trial count. Plus: the reported number must be the **EB-shrunk** estimate. | Efron local FDR anchored on our own measured base rate (3/196), not a π₀ estimated from K=30 cells (biased at K≤32). HLZ t>3.0 is too loose at π₁≈3%. DSR adds the trials-axis correction. |
| 16 | **Minimum evidence gate before *any* promotion** | Per-cell `n_eff ≥ 400` for the hit-rate leg; effect-size leg promotes on the **pooled** posterior only, never per-cell, until per-cell `n_eff ≥ 1,000` | (2σ/δ)² arithmetic: 0.55-vs-0.50 needs n≈400 (×DEFF); a 5bps effect needs n≈3,600 (×DEFF), unreachable per-cell at ~52 resolutions/cell/year. Publishing a per-cell effect size below this is a category error. |

---

## (d) Confidence notes

**Verified by fetching the source:** Chen & Zimmermann model spec, σ̂_θ ≈ 3.0, 10–15% shrinkage, FDR<10% (arXiv:2209.13623 HTML); Chen t-stat bias ≤28%, FDR ≤22%, π_F CI 0–70%, hurdle CI 0–3.0 (arXiv:2204.10275v4); Lichtendahl et al. non-extremizing (arXiv:1705.02391); Raj & Kalyani prior-parameter discounting (arXiv:1707.09727); SW-UCB window formula + γ=0.95 default (SMPyBandits); Garivier & Moulines abstract (arXiv:0805.3415); GJP extremizing diversity-dependence (AI Impacts).

**Verified only at search-snippet level (citation reliable, numbers as-reported):** Efron *Large-Scale Inference* (2010); Efron & Morris (1975); Jones & Shanken (2005); Harvey, Liu & Zhu (2016, t>3.0); Harvey & Liu *Backtesting*; Bailey & López de Prado DSR; Gelman (2006) half-Cauchy; Gelman & Hill 5–10 groups; Kish DEFF + the ρ=0.73/m=20/DEFF=14.9 example; Cesa-Bianchi & Lugosi Thm 2.2; Chernov & Zhdanov (2010); Chen & Velikov 4bps/10bps; Storey-vs-BH at K≤32 (PMC5833079); Smith & Wallis (2009); Ranjan & Gneiting (2010); Adams & MacKay λ_gap=250; Grinold-Kahn SE(IR)≈1/√N.

**UNVERIFIED:** Garivier-Moulines γ = 1 − ¼√(Υ_T/T) (corroborated numerically by the verified τ formula, not proven); any specific numeric extremizing exponent; the "26.7% Brier improvement / 86% of problems" log-odds pooling result; Jones-Shanken hyperparameter values; Pástor-Stambaugh prior SDs; Efron-Morris limited-translation cap value; Whittle-index-approximation claim; selective-inference winner's-curse papers (2607.18545, 2511.06318).

**Arithmetic mine (check before shipping):** all sample-size figures n = (2σ/δ)²; the EWMA n_eff ≈ 2/(1−λ) half-life table; the Hedge per-round regret 0.058 and 68,000-round break-even; the entire local-FDR → t-bar table in §5b. Derived from verified formulas; the substitutions are the agent's.

**Flag for Murat directly:** the §5b bar (t ≈ 4.0 at our measured base rate) and the §34 measurement (SPY t≈1.1 over 72 months) are the same statement seen from two sides. They independently confirm the UNDERPOWERED framing — no 72-month confirm window can clear a base-rate-honest promotion bar. The learning loop's promotion gate should therefore be specified against the **forward paper lane**, and the daily posterior layer scoped explicitly to attention and calibration, never to promotion. Exactly what D3 already rules; the literature supplies the arithmetic for why.
