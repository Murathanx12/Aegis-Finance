# HANDOFF — 2026-08-20, ORDER 24 discovery run (day session)

Order 23 was not executed verbatim. Two independent reviews landed first,
both making the same objection — eight hours of compute could produce an
impressive dataset without producing eight hours of evidence — and the
run was restructured around their amendments
(`docs/ORDER_24_DISCOVERY_RUN_REVISED.md`). Every headline below is a
measurement, and three of them close a line of work rather than opening
one, which is the point.

---

## NEW INFORMATION ACQUIRED

### 1. Aegis DOES beat the options market on risk — but only with options, and only on ordering

`OPTION-INCREMENTAL-RISK-1`, the test both reviews named as top priority.
Nine arms on identical rows, folds and missingness; QLIKE primary, rank
IC secondary, bias carried explicitly. Modern era (226,228 stock-months,
8 folds 2017-2024):

| arm | QLIKE | MSE(log var) | rank IC | bias | %under |
|---|---|---|---|---|---|
| iv_only | 0.3118 | 0.7543 | 0.7510 | −0.3227 | 31.3% |
| har_iv | 0.3783 | 0.5827 | 0.7665 | +0.0284 | 51.2% |
| iv_scaled | 0.3853 | 0.6431 | 0.7510 | +0.0332 | 52.6% |
| **lgbm_options** | 0.5003 | **0.4991** | **0.7978** | +0.0420 | 49.7% |
| mlp_options | 0.5870 | 0.5169 | 0.7934 | +0.0318 | 49.0% |
| har | 0.6700 | 0.7740 | 0.6584 | +0.1177 | 54.9% |
| lgbm_numeric | 0.7093 | 0.6123 | 0.7587 | +0.0583 | 49.5% |
| rv_m | 0.8042 | 0.9654 | 0.6587 | −0.0282 | 48.2% |

Raw implied variance wins QLIKE. It wins it by **over-forecasting**: bias
−0.32 in logs, under-forecasting only 31% of the time. That is the
variance risk premium, and QLIKE punishes under-forecasting ~linearly
while punishing over-forecasting only ~logarithmically, so the asymmetry
pays it. On the symmetric loss the ordering inverts:

| contrast (MSE log var) | modern | early |
|---|---|---|
| lgbm_options vs iv_scaled | +0.144 (MDE 0.064) **CLEARS** | +0.064 (MDE 0.016) **CLEARS** |
| lgbm_options vs numeric twin | +0.113 (MDE 0.062) **CLEARS** | +0.064 (MDE 0.016) **CLEARS** |
| har vs iv_scaled | −0.131 **CLEARS** (IV wins) | −0.169 **CLEARS** (IV wins) |
| **lgbm_numeric vs iv_scaled** | +0.031, **below MDE** | −0.000, **below MDE** |

Read the last row carefully. **Without options features the model family
does not clear the IV baseline at all.** Options are not a refinement;
they are the reason there is an edge over the market's own estimate.

Two corrections to the standing story:
- **HAR-RV is not the baseline that threatens us.** The review was right
  to demand it and wrong about which way it would cut: HAR loses to IV
  in both eras and beats only trailing realized variance. The baseline to
  beat is **IV-scaled**.
- **"0.79" was always a rank IC on a volatility target, never accuracy.**
  It survives — 0.7978 modern, 0.7991 early — and it is an *ordering*
  claim. Anything consuming the LEVEL must use the calibrated model.

Reproduced out of era: the entire ladder repeats on 1990–2012
(261,158 rows, folds 2001-2012).

### 2. Risk is era-invariant where return is not — the session's strongest result

`ERA-TRANSFER-1`. Era transfer became a first-class metric under this
order, run in both directions with the ratio reported. Rank IC ~0.80
*within* each era is compatible with two very different worlds: one
relationship stable across three decades, or two era-specific
relationships each memorised separately. Only a cross-era fit separates
them, and the answer decides how much a model trained today should be
trusted forward.

Both within- and transfer cells are out-of-sample (each era's model
trained on its own first 60% of dates), so the ratio compares like with
like — an in-sample denominator would have inflated the within cell and
flattered nobody.

| cell | rank IC | MSE(log var) | QLIKE | bias | n |
|---|---|---|---|---|---|
| early → early | 0.7903 | 0.4709 | 0.3525 | +0.0201 | 120,335 |
| **early → modern** | **0.8161** | 0.4393 | 0.3350 | −0.0535 | 97,182 |
| modern → modern | 0.8155 | 0.4046 | 0.3615 | −0.0029 | 97,182 |
| **modern → early** | **0.7836** | 0.4713 | 0.3999 | +0.0408 | 120,335 |

| transfer ratio | rank IC | MSE(log var) |
|---|---|---|
| early-trained model | **1.001** | 0.921 |
| modern-trained model | **0.992** | 0.999 |

**A model trained on 1990–2006 ranks 2020–2024 variance as well as a
model trained on 2013–2020 does** — slightly better, in fact. The risk
relationship is essentially era-invariant.

Set that against the return side, which flips **sign** between the same
two eras (price-only return ICs positive 1990–2012, negative 2017–2024).
Same panel, same universe, same features, same three decades:

> **Risk is stationary where return is not.**

That is the strongest structural justification the programme has for the
RISK product framing (§59), and it is the kind of result the mission
asks for — a property of the world, not of a fitted model.

One caveat, consistent with everything else today: what transfers is the
**ordering**. The bias differs across cells (−0.0535 vs −0.0029), so the
LEVEL still needs era-local recalibration. Ordering travels; calibration
does not.

### 3. Shift-invariance PASSES — the risk finding is not living on same-instant information

Every feature lagged one extra month. All arms degrade **gracefully**
(rank IC −0.04, no collapse) and every comparative conclusion holds:
lgbm_options still beats iv_scaled (+0.110 CLEARS) and its numeric twin
(+0.050 CLEARS). A result that collapsed here would have been living on
information it should not have had.

### 4. A single stock-month is 70% of ridge's entire loss

Early era, per-arm QLIKE tail:

| arm | mean QLIKE | p99 | max single row | share of total |
|---|---|---|---|---|
| lgbm_options | 0.319 | 3.77 | 902 | 1.1% |
| ridge_numeric | 581.3 | 4.53 | 105,935,854 | **69.8%** |
| mlp_options | 585.5 | 3.86 | 105,935,854 | **69.3%** |

Ridge and the MLP have *ordinary* p99s and *healthy* MSE(log var). One
row of unbounded extrapolation to a near-zero variance forecast produces
~70% of their total loss. **Fine on average, ruinous in the tail that
sizing actually cares about.** This is why the shipped artifact is LGBM
despite the MLP's competitive rank IC — and it is a general warning about
judging risk models by average losses.

### 5. Perfect regime foresight is worth +0.24%/yr — the family closes

`REGIME-ORACLE-CEILING-1`. Lead with the oracle instead of building a
predictor and discovering the ceiling afterwards. 153 JKP US factors ×
420 months; regime = contemporaneous quartile of realized market vol (the
oracle's private knowledge); compared against a null regime sequence with
the **same transition matrix**.

| policy | gross gap | switch drag | NET gap | null p95 | p |
|---|---|---|---|---|---|
| oracle | +9.97%/yr | 3.63% | +6.34% | +2.87% | 0.000 |
| oracle_loo (honest) | +4.33%/yr | 4.09% | **+0.24%** | −0.77% | 0.032 |

Excess over the selection null: **+1.00%/yr** against a 3%/yr economic
bar. `CEILING_STATISTICALLY_PRESENT_BUT_ECONOMICALLY_NEGLIGIBLE`.

The null is the experiment: picking the best of 153 factors four times
over manufactures a large gap from nothing (the naive oracle's null p95
alone is +2.87%/yr). And switching costs eat essentially the whole honest
gross gap. **Perfect** state knowledge nets +0.24%/yr; a real predictor
is imperfect and pays the same costs.

**Scope:** this closes regime-conditional **factor selection** on this
zoo. It does not close regime conditioning of **risk**, where §59 says
the clock runs ~30× faster — that half was taken up separately and
answered in §10 (the ceiling exists, but it is in the *level*, not the
ordering, and the observable proxies tested do not reach it).

### 6. 86 books are 3.5 behaviours — so MEGA-SWEEP-2 was replaced

`STRATEGY-EFFECTIVE-DIMENSION-1`, on the existing corpus at zero new
simulation cost:

| view | participation ratio | effective rank | top eigenvalue share | n for 90% |
|---|---|---|---|---|
| return | 2.36 | 3.53 | 0.610 | 3 |
| style-residual | 2.41 | 3.63 | 0.598 | 3 |
| co-crash tail | 2.67 | 4.81 | 0.590 | 6 |

Consensus clusters 6/3/3/2 at cuts 0.2/0.3/0.4/0.5; stability 0.903.
Running 1,500–3,000 more combinations of the same seven signals cannot
raise a dimensionality the signal set has already exhausted. It buys a
longer leaderboard and a worse selection problem — precisely what the
reviews predicted. **The blind mega-sweep was cancelled on this evidence**
and the compute redirected to §6.

Selection-overfit battery on the same corpus: best book
`low_vol|inverse_vol|trim|50`, Sharpe 0.918; matched null (demeaned,
block-bootstrapped rows preserving cross-book correlation) max-Sharpe p95
0.682 → p=0.0050; **deflated Sharpe 0.8367, FAILS at 0.95**; PBO 0.2197.
The two disagree informatively — the matched null respects the corpus's
effective n (~3.5), DSR charges nearer the nominal 86. Honest reading: a
*family* is showing, not a book, and one family out of ~3.5 independent
behaviours is weak evidence. Note the winner is a **low-vol** book.

### 7. No new information class opens a new direction — the bottleneck is construction, not data

`INFORMATION-DIMENSION-1`, 216 books over 18 signals in 6 classes.
Owned (price + fundamental, 72 books) effective rank **3.694**. Each
candidate class is compared against **size-matched** random subsets of an
extra-price-signal control pool, because effective rank rises mechanically
with the number of series added:

| class | books | increment | control (same n) | excess | p | verdict |
|---|---|---|---|---|---|---|
| price_extra | 48 | +0.299 | — | — | — | CONTROL POOL |
| options | 36 | +0.159 | +0.283 | −0.124 | 1.000 | no new direction |
| expectations | 36 | **−0.247** | +0.283 | −0.530 | 1.000 | no new direction |
| liquidity | 24 | +0.191 | +0.245 | −0.054 | 0.925 | no new direction |

None beats a matched dose of *more price signals*. Expectations actively
**collapses** the space.

Corroboration from an independent route: clustering all **216** books —
18 signals spanning six information classes — at correlation distance 0.3
yields **3 clusters**. Six times the signal families of mega-sweep-1
produced fewer distinct behaviours than mega-sweep-1's own 86 books did
(which gave 3 at the same cut). Adding information classes did not add
behaviours.

**Put §1 and §7 together.** Options carry real, replicated information at
the security-risk level (+0.113 / +0.064 MSE log var, CLEARS in both
eras). The same options carry **no new behavioural direction** once
poured through a top-N long-only monthly-rebalance grammar.

> ⚠️ **The obvious interpretation of that — "the construction layer
> destroys the information" — was tested in §12 and REFUTED.** Removing
> the top-N cut collapses effective rank from 3.72 to 1.31 rather than
> raising it. §12's apparent counter-example (options beating control
> under a rank-only grammar) was itself withdrawn the same day: it
> reproduces in exactly one of eight cells and vanishes in every superset.
> Read §7 as the measurement that survives — now across the full
> factorial, not one setting. The surviving claim is narrower than the
> original interpretation: the space of long-only monthly top-N books is
> intrinsically low-dimensional, and we have no demonstrated construction
> that raises it.

### 8. The risk head's ranking edge does NOT convert into sizing value

`RISK-SIZING-VALUE-1` / `RISK-SIZING-DISPERSION-1`. The bridge from the
programme's best asset to an actual portfolio, and it does not carry the
weight the security-level result suggested.

Same signal, same picks, same dates, same costs — only the weighting
differs: `1/sqrt(trailing 63d var)` vs `1/sqrt(model predicted var)`,
predictions strictly walk-forward. Declared direction: the model should
reduce realised book volatility.

Pooled over 12 matched pairs, 94 months: **d_ann_vol +0.0103, ns**. The
wrong sign, and not significant.

Three explanations tested and **killed**:

| hypothesis | test | result |
|---|---|---|
| weight concentration | 5× cap on any weighting | contrast moved +0.0103 → +0.0109. Cap does not bind. |
| prediction coverage | coverage of each signal's picks | value_bm 93.3% — *higher* than mom_12_1 90.8%, low_vol 89.9% |
| model is wrong on those names | rank IC / QLIKE restricted to picks | model is **most** accurate on value picks (IC 0.764, QLIKE 0.381), **least** on opt_iv_low (0.499) — the reverse of where sizing helped |

The fourth survives and is measurable. Cross-sectional dispersion of log
predicted variance:

| signal | sd log pred | sd log trailing | ratio | sd log realized |
|---|---|---|---|---|
| value_bm | 0.847 | 1.056 | 0.80 | 1.093 |
| opt_iv_low | 0.922 | 1.131 | 0.82 | 1.300 |
| mom_12_1 | 0.717 | 1.062 | **0.67** | 1.112 |
| low_vol | 1.029 | 1.007 | 1.02 | 1.441 |

**The model is shrunk.** A regularised learner minimising squared error
on log variance is rewarded for pulling toward the mean, so it orders the
cross-section well while understating its spread. **Inverse-vol weights
are driven by the SPREAD of the estimator, not its ordering** — a shrunk
estimator produces near-equal weights and cannot reduce book volatility
however well it ranks. On the value book, model-sized realised vol was
0.596 against **0.608 for plain equal weight**: it was barely sizing.

The fix, and its honest result: a per-date **rank-preserving quantile
map** onto the trailing-variance distribution (Spearman preserved at
exactly 1.000; sd log 0.828 → 1.254).

| contrast | d_ann_vol | MDE | verdict |
|---|---|---|---|
| corrected − uncorrected model | **−0.0084** | 0.0083 | **POWERED** |
| corrected − trailing (primary) | +0.0019 | 0.0453 | ns |
| uncorrected − trailing | +0.0103 | 0.0392 | ns |

The correction is a real, powered improvement over the uncorrected model
— the shrinkage diagnosis is confirmed — and it wins on 3 of 6 signals
(mom_12_1, quality_roe, exp_breadth, the last two with *higher* return
too). **But it still does not beat trailing inverse-vol.**
`RISK-SIZING-VALUE-1` stands as **NOT_ESTABLISHED**.

One residual anomaly, named rather than explained away: `value_bm`
survives every correction (trailing 0.331 vs corrected model 0.589 vs
equal 0.608). Ordering is good there, dispersion is now matched, and
coverage is high — so the mechanism is still unidentified. Queued, not
hand-waved.

**What this means for G2.** Note what is *not* being said. Risk sizing
itself works: both estimators beat equal weight substantially (value_bm
0.331/0.589 vs 0.608; opt_iv_low 0.091/0.077 vs 0.105). So the G2 lane
pair — equal-weight vs risk-sized — remains well posed and should show a
real effect. What is a wash is **which estimator**. The lane can use the
cheap trailing estimator; if it uses the model, the receipt must not
claim the model is *why* it works.

### 9. Covariance explains the value anomaly — and is not a free upgrade

`CONSTRUCTION-SIZING-1`. The loose end §8 refused to hand-wave, tested.

Every property of the *estimator* checked out on the value book, so the
suspect was never the estimator: **every inverse-volatility rule
optimises each name's marginal variance and is blind to how the names
co-move.** A book can be assembled entirely from individually quiet names
that all fall together. Added a covariance-aware arm — long-only minimum
variance on the programme's own Marchenko-Pastur **denoised** covariance
of the picks' trailing 252-day returns.

Realised annualised volatility, trim handling:

| signal | equal | inverse_vol | model_vol_ds | min_var | best |
|---|---|---|---|---|---|
| mom_12_1 | 0.320 | 0.293 | **0.276** | 0.315 | model_vol_ds |
| low_vol | 0.104 | **0.078** | 0.081 | 0.116 | inverse_vol |
| value_bm | 0.608 | 0.331 | 0.589 | **0.289** | **min_var** |
| quality_roe | 0.207 | 0.187 | **0.164** | 0.195 | model_vol_ds |
| exp_breadth | 0.208 | 0.188 | **0.176** | 0.194 | model_vol_ds |
| opt_iv_low | 0.105 | 0.091 | **0.088** | 0.121 | model_vol_ds |

**Supported where it was raised, refuted in general.** `min_var` is the
only arm that fixes the value book (0.289, beating even trailing's
0.331) — covariance-blindness *was* the mechanism. But pooled it is
significantly **worse** than the incumbent:

| contrast | d_ann_vol | MDE | verdict |
|---|---|---|---|
| min_var − inverse_vol | **+0.0150** | 0.0078 | **POWERED** (worse) |
| min_var − model_vol_ds | +0.0131 | 0.0475 | ns |
| min_var − equal | −0.0138 | 0.0330 | ns |

Inverting a 50×50 covariance estimated from 252 observations costs more
in estimation error than it gains in diversification for most books —
min-variance concentrates on exactly that error. The declared direction
was refuted, and the refutation is the finding.

**The positive result, and the one that matters for G2:**

| contrast | observed | CI | verdict |
|---|---|---|---|
| inverse_vol − equal, ann vol | **−0.0288** | [−0.0529, −0.0134] | significant |
| inverse_vol − equal, max DD | **+0.0348** | [+0.0073, +0.0929] | significant |

**Risk sizing itself works.** The G2 lane pair (equal-weight vs
risk-sized) is well posed and should show a real effect using the cheap
trailing estimator.

One reading rule this run kept re-teaching: **`model_vol_ds` is the best
arm on 4 of 6 signals yet does not beat trailing pooled**, because the
pooled average is dominated by value_bm. Per-signal and pooled disagree
here for a reason that is now understood rather than averaged over.

### 10. Regime conditioning for RISK: the ceiling is in the level, not the ordering

`REGIME-RISK-CONDITIONING-1`. §5 closed regime-conditional factor
*selection* and explicitly left risk conditioning open. Same oracle-first
discipline, applied to the risk head — with an arm that cannot exist in
practice, because that is the ceiling no predictor can beat.

| arm | rank IC | MSE(log var) | QLIKE |
|---|---|---|---|
| baseline | 0.7978 | 0.49908 | 0.5003 |
| + trailing state (observable) | 0.8006 | 0.52204 | 0.5062 |
| + **oracle** state | 0.7991 | 0.48447 | **0.4336** |
| + both | 0.7991 | **0.45210** | 0.4376 |

| contrast (MSE log var) | Δ | MDE | verdict |
|---|---|---|---|
| + trailing − baseline | **−0.02296** | 0.03662 | significant (**worse**) |
| + oracle − baseline | +0.01461 | 0.06176 | ns |
| + both − baseline | **+0.04698** | 0.05829 | significant |

**Verdict: `CEILING_IS_IN_THE_LEVEL_ONLY`.** Rank IC barely moves
(+0.0013 for the oracle) — a perfectly-known market-variance state adds
essentially nothing to the *ordering*. But QLIKE falls 0.500 → 0.434, a
13% improvement in the calibrated level, which makes sense: market-wide
variance rescales everything at once. And the observable trailing state
does not reach any of it — six market-state features make MSE log
variance significantly **worse**, adding variance without signal.

So regime conditioning of risk is not dead, but it is not what it was
hoped to be: it is a **level/calibration** lever, not an ordering lever,
and the observable proxies tested here do not capture it. That is the
same ordering-vs-level split as §1, §2, §8 and §9.

**A decision rule was corrected mid-trial and the correction is
disclosed.** The rule as first written tested only the `plus_oracle_state`
arm and would have printed
`REGIME_CONDITIONING_CLOSED_FOR_RISK` — it ignored `plus_both`, an arm
this same script deliberately runs and which *is* significant, and it
conflated ordering with level. A rule that cannot see an arm the design
includes is an incomplete rule, not a verdict. Both the corrected rule
and what the original would have said are recorded in the receipt.

### 11. Exposure targeting — the last untested route, and it also does not pay

`VOL-TARGET-VALUE-1`. §8 tried the model's *ordering* inside the book and
it failed; §10 found the remaining ceiling is in the **level**. Exposure
targeting is the one use that consumes a level rather than an ordering,
so it is the last route this run could test: scale the book's total
exposure so its predicted volatility hits a 15% target. Leverage known at
the start of each month, capped [0.25, 2.0]; predicted portfolio variance
is `w' S w` with the model supplying the diagonal and a trailing window
the correlations.

| arm | mean \|vol − target\| | sd(realized vol) | ann vol | ann ret | maxDD |
|---|---|---|---|---|---|
| none | 0.1079 | 0.1054 | 0.2511 | 0.1349 | −0.3529 |
| trailing | 0.0558 | 0.0750 | 0.1949 | 0.0820 | −0.3339 |
| model | **0.0548** | 0.0790 | 0.2081 | 0.0917 | −0.3541 |

| contrast (tracking error; negative = first arm better) | Δ | MDE | verdict |
|---|---|---|---|
| model − trailing | −0.00211 | 0.01215 | ns |
| model − none | −0.01516 | 0.03414 | ns |
| trailing − none | −0.01305 | 0.03797 | ns |

The model tracks the target marginally better than trailing (0.0548 vs
0.0558) and it is nowhere near significant. **NOT_ESTABLISHED.**

Note the second and third rows honestly: vol targeting *itself* roughly
halves tracking error (0.108 → ~0.055) and cuts realised vol from 0.251
to ~0.20, but at 12 pairs over 94 months the MDE is 0.034–0.038 against
an observed 0.013–0.015. Those two contrasts are **NOT_ANSWERABLE_AT_N**,
not "no effect" — a distinction this programme pays for when it is
skipped.

**This closes the loop.** Every route from the risk head to a portfolio
decision that Order 24 could test has now been tested:

| route | what it consumes | result |
|---|---|---|
| cross-sectional sizing (§8) | ordering | NOT_ESTABLISHED |
| …with shrinkage corrected (§8) | ordering | POWERED vs itself, still loses to trailing |
| covariance-aware construction (§9) | ordering + covariance | significantly worse pooled |
| regime conditioning (§10) | level | ceiling exists, observables do not reach it |
| exposure targeting (§11) | level | NOT_ESTABLISHED |

The head is genuinely good at ranking variance, era-invariantly. **None
of that has yet been converted into a portfolio decision that beats a
trailing 63-day standard deviation.** That is the honest state, and it is
a far more useful thing to know than another leaderboard.

### 12. The cut is NOT the culprit — §7's interpretation is refuted

`CONSTRUCTION-CUT-1`. §7 reported a measurement (no information class
beats a size-matched control) and then offered an *interpretation*: that
the top-N long-only monthly grammar is what collapses them, because a cut
is a coarse quantisation that discards everything the signal says about
the other ~2,000 names. That interpretation had a falsifiable
implication — remove the cut and the classes should separate — and it was
the basis for the "defer Order 22, fix construction first" redirect. So
it was tested.

Two grammars, same signals, same handlings, same costs, same dates:

| grammar | owned effective rank | options | expectations | liquidity |
|---|---|---|---|---|
| **cut** (top-50, rank-weighted) | **3.721** | +0.475 vs ctrl +0.346, p=0.000 **BEATS** | +0.010, p=1.000 | +0.288, p=0.507 |
| **continuous** (no cut, full cross-section tilt) | **1.313** | −0.044, p=0.963 | −0.046, p=0.965 | −0.035, p=0.950 |

**Removing the cut destroys diversity rather than creating it.** Effective
rank falls from 3.72 to **1.31** — under a diffuse tilt across every
eligible name, all 36 books collapse into essentially one behaviour,
because a rank tilt over ~2,000 names is dominated by market beta. No
class separates, and every increment goes negative.

The prediction was refuted, and in the opposite direction from the one
anticipated. **The top-N cut is not what collapses the information; it is
what creates what little behavioural diversity exists.** Concentration is
what differentiates books.

**The disagreement was resolved the same day, and it killed this run's
own positive.** Under this narrower grammar options appeared to beat its
size-matched control (+0.475 vs +0.346, p=0.000), disagreeing with §7.
`INFORMATION-DIMENSION-RECONCILE` re-analysed the existing 216-book
corpus — no new simulation, complete factorial of cells, candidate *and*
control subsampled to the same k:

| cell | k | increment | control | excess | p | |
|---|---|---|---|---|---|---|
| ALL (full grammar) | 36 | 0.159 | 0.281 | −0.121 | 1.000 | no |
| ALL, matched to 6 | 6 | 0.141 | 0.096 | +0.045 | 0.182 | no |
| weighting = equal | 12 | 0.166 | 0.189 | −0.023 | 0.758 | no |
| weighting = inverse_vol | 12 | 0.109 | 0.275 | −0.166 | 1.000 | no |
| weighting = rank | 12 | 0.294 | 0.287 | +0.007 | 0.445 | no |
| top_n = 50 | 18 | 0.337 | 0.352 | −0.015 | 0.697 | no |
| top_n = 100 | 18 | 0.054 | 0.181 | −0.126 | 1.000 | no |
| **rank & top_n=50** (§12's exact cell) | 6 | 0.475 | 0.344 | **+0.131** | 0.000 | **BEATS** |

Options beats its control in **exactly one of eight cells — the precise
cell §12 happened to use** — and the effect vanishes in every superset of
it. Widen to all rank-weighted books and it is +0.007 (p=0.445); widen to
all top-50 books and it is −0.015. Matching book count alone does not
reproduce it (+0.045, p=0.182).

That is the signature of a cell-specific artifact, not a finding.
**§12's positive is withdrawn.** §7's negative stands, and it now stands
across the full factorial rather than at one setting.

Worth naming plainly: this run's own machinery killed this run's own
result, which is what the selection-overfit discipline is for. It also
shows how the artifact was produced without anyone p-hacking — §12 chose
rank & top-50 for a principled reason (it was the natural "cut" grammar
for testing the cut), and a principled choice of one cell is still one
cell.

**What this does to the §7 redirect.** It weakens it. The evidence no
longer supports "the construction layer is destroying the information"
as a confident claim — the one obvious construction fix makes things far
worse. The defensible statement is narrower: *the space of long-only
monthly top-N books is intrinsically low-dimensional, we have no
demonstrated construction that raises it, and the obvious candidate is
counterproductive.* Deferring Order 22 is still reasonable — but on the
grounds that we cannot yet spend the information we own, not on the
grounds that we know how to fix the layer.

### 13. Every grammar decision is a risk decision, not a return decision

`RULE-INTERVENTION-1`, matched paired contrasts (each pair differs in
exactly one coordinate, so signal/universe/dates/costs cancel; unit of
evidence is the date block):

| contrast | dRet/yr | ret? | dVol | vol? | dMaxDD | dd? |
|---|---|---|---|---|---|---|
| inverse_vol − equal | −1.24% | ns | −6.93% | sig | +6.10% | sig |
| rank − equal | +1.47% | ns | +8.26% | sig | −3.94% | ns |
| rank − inverse_vol | +2.70% | ns | +15.19% | sig | −10.04% | sig |
| exempt − trim | −1.66% | ns | −3.78% | sig | +2.08% | ns |
| top_n 50 − 100 | +2.44% | ns | +8.01% | sig | −4.60% | ns |

Not one decision moves return detectably (return MDEs of 5–18%/yr dwarf
the 1–3%/yr effects). All five move volatility significantly. §59 on the
grammar itself.

---

## WHAT DIED

- **Regime-conditional factor selection.** Closed by ceiling, not by a
  failed predictor. Cost: one run.
- **The blind 1,500–3,000-book MEGA-SWEEP-2.** Cancelled by the effective
  dimension measurement before it consumed the session.
- **"HAR-RV is the baseline to beat".** It is not; IV is.
- **The MLP as a risk-head candidate.** Loses to LGBM on both losses,
  degrades worst under lag, and blows up in the tail.
- **Expectations/liquidity/options as sources of new portfolio-behaviour
  diversity** *under this grammar*. Not as sources of information.
- **Every tested route from the risk head to a portfolio decision**
  (§8, §9, §11): cross-sectional sizing, shrinkage-corrected sizing,
  covariance-aware construction, exposure targeting. The head's ranking
  is real; none of these converts it into a decision that beats a
  trailing 63-day standard deviation.

## WHAT REMAINS NOT ESTABLISHED

- Whether the options-augmented head's advantage survives to a forward
  lane. Nothing here is forward evidence.
- Whether a better construction layer recovers the information §7 shows
  is being destroyed. That is the top open question, and CONSTRUCTION-CUT-1
  (running at handoff-write time) tests its load-bearing implication
  directly: remove the top-N cut and see whether any information class
  separates that could not before. If none does under either grammar, the
  "fix construction before buying feeds" redirect needs rewriting and the
  honest conclusion becomes that these families genuinely carry the same
  portfolio information.
- Whether any OBSERVABLE state variable reaches the level-calibration
  ceiling §10 found (the six trailing market-state features tested make
  things significantly worse).
- Any return claim about the new signal families. INFORMATION-DIMENSION-1
  measured structure only and deliberately printed no leaderboard.

---

## INTEGRITY: two audits, two real defects

**WRDS-META-INTEGRITY-1** — all **119** dataset metas claimed
`window = [2013-01-01, 2024-12-31]`, including every 1990–2012 slice and
every per-year 13F/OptionMetrics file, because `_write()` stamped module
constants instead of reading the frame. Verdict **LABELS_ONLY**: 0/119
row-count mismatches. The pulls were right, the labels lied. Window and
universe now derive from the data; metas regenerated with the stale claim
preserved under `metadata_correction`. The derived metadata immediately
surfaced what the constant hid — `compustat_fundq`'s `rdq` runs to
2026-03-26 against `datadate ≤ 2024` (legitimate late/restated filings).

**CHRONOLOGY-AUDIT-1** — 9 checks, 2 FAIL:
- **C1 PASS** — the options risk head is chronologically clean. 307,924
  joins, lag(formation − opt_date) min 0, p50 0, max 30, **zero
  negatives**. The review's top suspicion (IV at t joined to vol over
  t..t+h) is **refuted by measurement**. The live `lag > 14` filter is a
  staleness cap and is one-sided, so both consumers now assert the sign
  rather than relying on it holding by luck.
- **C2 PASS** — `fwd_vol[t] == std(ret[t+1..t+21])`, excludes formation day.
- **C4 FAIL** — `tr_13f.s34` `fdate` is a **vintage stamp, not an SEC
  filing date**: `fdate == rdate` on 97.2% of 76.9M rows and every
  `fdate` is a quarter-end. The table carries **no public-availability
  column**; treating `fdate` as knowledge time grants the full 45-day
  statutory filing window of lookahead.
- **C7 FAIL** — `manager_actions_quarterly_v1`'s meta claims "features key
  on fdate, never rdate", but `fdate` was never propagated into the
  artifact. Its only time column is `q`, derived from **rdate** — which
  the meta itself forbids. The claim was **unsatisfiable by construction**.
- **C3/C5 QUANTIFIED** — 99.9% (modern) / 99.4% (early) of IBES rows
  carrying an `actual` have `anndats_act` *after* `statpers` (median 161d
  / 167d of lookahead if read at `statpers`). Compustat `rdq` is NULL on
  7.1% of rows — no honest knowledge date; drop, never impute.

**Consequence:** `MANAGER-WINNER-HOLDING-1`, `MANAGER-ADD-TO-WINNER-1`,
`MANAGER-DRAWDOWN-BEHAVIOR-1`, `MANAGER-CONVICTION-PERSISTENCE-1` stay
**BLOCKED** until a v2 library gates on `rdate + 45d`. On top of the
already-declared split-adjustment limit, not instead of it.

---

## ARTIFACTS

**`risk_head_vol_lgbm_options@2.0.0@31b9b8d62c777e97`** — the model layer
was the programme's unpinned surface. Now:
`model.txt · features.json · calibration.json · train_window.json ·
model_card.md · MANIFEST.sha256`. A lane may reference a model only by
`name@semver@sha256` and refuses if the hash does not resolve. The model
card states what it beat, on which loss, and **how it fails**.

Held out 2022–2024 (fit <2020, calibrate 2020–21, all disjoint):

| arm | QLIKE | MSE(log var) | rank IC | bias |
|---|---|---|---|---|
| model (raw) | 0.5580 | 0.3963 | 0.8140 | +0.0870 |
| model (calibrated) | 0.5000 | 0.3890 | 0.8140 | −0.0159 |
| iv_only baseline | 0.2668 | 0.7373 | 0.7530 | −0.3151 |

**The calibration caught itself being a no-op.** The first build fitted
the level offset on the fit rows — where the booster had already driven
the mean residual to ~0 — so "raw" and "calibrated" came out
byte-identical while still printing a calibrated column. Green and empty,
the house failure mode. Three disjoint spans in time order fixed it; the
offset is +0.1030 and does real work.

**And then the early-era twin caught the fix's own limitation.** Built as
`risk_head_vol_lgbm_options@2.0.0-early@9b414af5b2d8dfb0` (fit <2008,
calibrate 2008–09, holdout 2010–12), its calibration span landed on the
GFC — and the offset fitted there **makes bias worse** on the calmer
holdout (−0.036 → −0.118) even while QLIKE improves. A single additive
offset on one contiguous span is **hostage to that span's regime**.

Both artifacts now compute and record a regime check, and **both fail
it**: the calibration window is a volatility outlier against its fit span
at z = **0.74** (modern, contains COVID) and z = **0.45** (early,
contains the GFC). The modern artifact's calibration happened to help;
that is luck, not design. Anything consuming the level should either
recalibrate on a rolling window or treat the offset as provisional.

**Datasets** (Tier PRIVATE per the new receipt policy, each with a public
stub in `docs/datasets/`): `STOCK_RISK_DATASET_V1_modern`,
`STRATEGY_STATE_DATASET_V1`. Every row carries a `date_weight` summing to
1.0 within its date; the strategy dataset splits weight by **cluster**
first, so 216 books spanning ~4 behaviours cannot vote 216 times.

---

## THE ONE-LINE VERSION

Risk is stationary where return is not, and the risk head reads the
options market better than the options market reads itself — but only for
*ordering*. Five separate routes from that ordering to a portfolio
decision were tested and none beats a trailing 63-day standard deviation.
Meanwhile the portfolio grammar collapses every information class we own
into ~3 behaviours — and the obvious fix for that (drop the top-N cut)
makes it dramatically worse, collapsing them to ~1. **We have a real,
replicated, era-invariant risk signal, no demonstrated way to spend it,
and no demonstrated construction that would let us. Closing that gap is
the programme's next problem, and this run narrowed where it is without
solving it.**

## FOR MURAT (three minutes)

1. **The G2 risk lane hold is resolved by measurement — but the reason
   to run it changed.** The review asked to hold it because the options
   head was unbenchmarked against HAR-RV and unaudited for the timestamp
   bug class. Both are now done: it beats the baseline that actually
   threatens it (IV, not HAR), in both eras, and the chronology audit
   passes with zero negative lags. Pin
   `risk_head_vol_lgbm_options@2.0.0@31b9b8d62c777e97`, and note **two**
   conditions: anything consuming the LEVEL must use the calibrated
   prediction **and know that the calibration is provisional** — its
   offset is fitted on 2020–21, a volatility outlier at z=0.74 against
   the fit span, and the early-era twin shows exactly this design making
   bias worse when its window was the GFC; and the receipt must not claim
   the model is why the lane works. §8 found the model's ranking edge does **not** convert into
   sizing value over a nearly-free trailing estimator. Risk *sizing*
   works; the *estimator choice* is a wash. The cheap estimator is
   defensible and easier to defend.
2. **Order 22's world-sensor arc should still wait — but the argument
   for waiting got weaker during the run, and you should have the weaker
   version.** The original reasoning was §7: our construction layer
   cannot express the information classes we already bought. §12 then
   tested that reasoning's own implication and **refuted it** — removing
   the top-N cut collapses behavioural diversity from 3.72 to 1.31 rather
   than freeing it, and options actually *beat* its control under a
   narrower grammar. So we cannot claim to have located a fixable
   bottleneck. What we can claim: we own information we have not managed
   to spend, through five tested routes, and buying more feeds does not
   address that. That is a reason to wait, not a diagnosis.
3. **The manager/teacher library needs a v2 before any behaviour claim.**
   Its PIT column does not exist in the artifact and would not be a
   knowledge date if it did.
4. **`NEGATIVE_RESULTS.md` #4 amended** — survivorship "not buildable on
   free data" is still true on free data and is no longer the operative
   constraint. Recorded as an amendment, never a deletion, with what does
   NOT change listed.
5. **Two decisions await you:** the WRDS receipt policy
   (`docs/DECISION_WRDS_RECEIPT_POLICY.md`) and the benchmark-restamp
   acceptance criteria added to P-day-2026-08-19a.

## NEXT 10 MACHINE JOBS

1. ~~Resolve the §7-vs-§12 disagreement on options.~~ **DONE in
   session** — `INFORMATION-DIMENSION-RECONCILE` settled it by
   re-analysis: §12's positive appears in one of eight cells and is
   withdrawn. §7's negative stands across the full factorial.
1b. `CONSTRUCTION-BOTTLENECK-1`, now much narrower. §8 tested sizing by
   predicted vol (wash), §9 tested covariance-aware construction (worse
   pooled, better only on the value book), §12 tested removing the cut
   (much worse). What has NOT been tested: concentration *between* 50 and
   the full cross-section, long-short constructions, and sector/factor
   neutralisation. Effective dimension is the readout.
2. Reach the §10 ceiling, or close it: the oracle market-variance state
   cuts QLIKE 13% while leaving rank IC flat, and six trailing proxies
   made MSE log variance significantly WORSE. Either find an observable
   that captures a market-wide variance level shift (implied index vol,
   term structure, dispersion of IV rather than of returns), or declare
   the level ceiling unreachable and stop.
3. Manager library **v2**: `rdate + 45d` knowledge gate, `cfacshr`
   split adjustment, v1-vs-v2 transition matrix diff. Unblocks four
   MANAGER-* trials.
4. Persist per-book **holdings and turnover paths** in the next sweep —
   two of the five similarity views are currently unanswerable.
4b. Re-run §11's targeting contrasts at the n they need. `trailing − none`
   and `model − none` are NOT_ANSWERABLE_AT_N (MDE 0.034-0.038 vs
   observed 0.013-0.015); more signals or a longer window would settle
   whether vol targeting pays at all, which is a cheaper and more
   important question than which estimator drives it.
5. Early-era artifact twin of the risk head + era-transfer both
   directions with the ratio reported.
6. `REENTRY-OPTION-VALUE-1` design (hold / trim / exit / exit+confirmation
   re-entry variants), all triggers declared before outcomes.
7. Frozen PIT-CRSP replication of `CONVEXITY-PRESERVATION-1`.
8. `STREAK-MECHANISM-1` — is five-up-day reversal concentrated in
   abnormal volume, skew, lottery/MAX state, attention, illiquidity?
   Target distinction: transient winner vs structural winner.
9. Add `reproducibility` fields to receipt writers, and enforce the
   stub-on-withhold rule in code rather than by checklist.
10. Prequential state estimator (filtered probabilities only) — only if
    §2 above finds a ceiling worth predicting.

---

## LANE RAIL

Nightly IIF launcher fires **17:00 local** and is mid-receipt-clock
(clean-clock firing #1 tonight). All heavy compute for this run
checkpointed and stopped before it. No lane write-paths were touched, no
NAV/positions deployment, SIMULATION labels throughout. Screen survivors
earned registrations, never promotions.
