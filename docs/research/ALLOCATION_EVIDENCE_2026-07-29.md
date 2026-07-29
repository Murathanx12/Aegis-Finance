# Allocation-layer evidence review — verified (2026-07-29)

Every number below was read off a fetched document (PDFs text-extracted locally).
Failed fetches, derivations and genuine nulls are flagged. Status: evidence
review. Nothing registers. The freeze holds.

**Headline: the strongest finding is a PROOF, not a backtest — and it invalidates
the metric this session proposed twelve hours ago.**

---

## F (reported first, because it changes everything) — calibration does NOT imply profitability

This is settled by identity, not by evidence, so it cannot decay out of sample.
The Brier decomposition (Murphy 1973), quoted from Siegert (arXiv:1303.6182):

> **Br = REL − RES + UNC**, where REL\* = E[p − π(p)]², RES\* = E[π(p) − π̄]²,
> UNC\* = π̄(1 − π̄).
> "**A forecasting scheme that constantly issues the same probabilities has zero
> resolution.**"
> "A 'useful' forecast should have a Brier Score lower than its uncertainty
> component… **the resolution should be larger than the reliability.**"

Gneiting & Raftery (2007) *JASA* 102(477), same point:

> "**Climatological forecasts… are calibrated by construction, but often lack
> sharpness.**"

**A forecast that always emits the base rate is perfectly calibrated (REL = 0),
has zero resolution, and is worth exactly nothing.** Calibration is necessary and
nowhere near sufficient. **Resolution is the part that can pay.**

**BINDING: track RESOLUTION, not calibration.** Report REL / RES / UNC
separately; never BSS alone.

And skill ≠ value: Richardson (2000) *QJRMS* 126(563) shows the same ECMWF system
scoring ROC-skilful past day 10 while BSS shows "no skill at all beyond day 8",
with users outside a cost/loss ratio of 0.2–0.6 getting **no benefit at all**.
Different scores rank the same system oppositely, and value is user-specific.
Granger & Pesaran (*J. Forecasting* 19(7)) is the finance statement of it.

## E — the scoring machinery, and one gap where we needed it most

**BSS is improper *and* structurally biased against sharpness.** Gneiting &
Raftery: *"skill scores of the form (8) are generally improper, even if the
underlying scoring rule S is proper… Mason's (2004) claim of the propriety of the
Brier skill score… generally is incorrect."* Mason (2004) *MWR* 132(7) himself:

> "the expected value of these skill scores is **less than 0 if
> nonclimatological forecast probabilities are issued**."
> "forecast systems with **greater variance in the forecast probabilities will
> have a lower (more negative) expected Brier skill score**."

**BSS penalises the sharpness you are told to maximise. A negative BSS on a sharp
crash model is close to uninformative on its own.** Deciding metric must be a
paired proper-score difference, not BSS.

**Sample size.** Bradley, Schwartz & Hashino (2008) *Wea. Forecasting* 23(5):
*"with infrequently occurring events, verification sample sizes of a few hundred
forecast–observation pairs are needed"*; *"for sample sizes up to about 300, one
cannot reject the hypothesis that the true skill score is 0"*; N=50 → 95% CI
**[−0.26, +0.57]**, actual coverage **77.3%** not 95%.

**Serial correlation.** N_eff ≈ n·(1−r₁)/(1+r₁) — Santer et al. (2000) *JGR*
105(D6) Eq. 6, attributing to Bartlett (1935). Ferro (2007): use **block
bootstrap**. Thiébaux & Zwiers (1984): *"effective sample size is quite difficult
to estimate reliably."*

### ⚠️ Genuine null — the comparison C1 rested on does not exist
Two independent search efforts, six query formulations: **no source compares the
statistical power of proper-scoring-rule forecast evaluation against Sharpe-ratio
strategy evaluation.** Two literatures that do not cite each other.

**Consequence:** our power table is **our own derivation**, not a citable result,
and must be labelled as such. Also — the "17 years to t=2, 40 years to t=3"
figures are a derivation from `T = t²(1+SR²/2)/SR²`; **Lo (2002) says nothing
about years-to-significance and must not be cited for them.** The SE formula
itself was established by numerical reproduction of Lo's Table 1, not quoted.

## D — analog forecasting: a hard analytical ceiling that our engine violates

**van den Dool (1994)** *Tellus A* 46(3), verbatim:

> "**it would take a library of order 10³⁰ years to find 2 observed flows that
> match to within current observational error over a large area**… with only
> 10–100 years of data, the probability of finding natural analogues is very
> small, **unless one is satisfied with analogy over small areas or in just 2 or
> 3 degrees of freedom**."

Independently confirmed by Bothe & Zorita (2021) *Climate of the Past* 17(2).
The mechanism — Cecconi et al. (arXiv:1210.6758) §IV.3:

> "the minimum length of the time series is **M ∼ (L/ε)^{D_A}**"
> "when D_A is that large **only mediocre analogues can be found** and those are…
> **usually not so informative about the future evolution**."

Lorenz (1969) *JAS* 26(4): *"**There are numerous mediocre analogues but no truly
good ones.**"* ⚠️ The circulating "140 years" figure is **not** in Lorenz and
traces only to a non-peer-reviewed teaching document — do not cite it to him.

**Required library length is EXPONENTIAL in effective dimension.** The escape
hatch is explicit and is the same in all three sources: **collapse to 2–3
effective dimensions, or do not bother.** Delle Monache et al. (2013) *MWR*
141(10) trains on just 12–15 months — possible only because it matches one
station, one lead time, a handful of predictors.

**The one finance test shows exactly our failure pattern.** Diebold & Nason
(1990) *J. Int. Econ.* 28(3–4), nearest-neighbour FX:

> In-sample: "MSPE and MAPE reductions in the neighborhood of **10–20 percent**
> relative to the random walk are pervasive."
> "**Out-of-sample, however, the nonparametric predictor fares much less well.**
> Typically, the loss… is **larger than that of the random walk**."

Mizrach (1992) *JAE* 7(S1): improvement *"is not statistically significant… also
not robust."* The proponents' own survey calls results *"rather inconclusive."*
An OpenAlex title filter for equity nearest-neighbour work returned **3 records
total** — the literature barely exists.

## A — volatility targeting: continuous is DEAD, conditional is the best idea in this review

**Moreira & Muir (2017)** *JF* 72(4) report market alpha 4.9% and a 25% Sharpe
increase — but the scaling constant is fitted on the full sample: *"we choose c
so that the managed portfolio has the same unconditional standard deviation as
the buy-and-hold portfolio."* Their own middle subsample 1956–1985 is α 2.06
(s.e. 2.82), **t = 0.73**. Their no-leverage row already halves expected return
(5.61% vs 9.47%).

Four independent refutations:

| Source | Finding |
|---|---|
| Liu, Tang & Zhou (2019) *JPM* 46(1) | after correcting look-ahead, **max drawdown 68–93%**; *"outperforms the market only during the financial crisis"*; *"**One cannot easily beat the market via volatility-timing the market alone**"* |
| Cederburg, O'Doherty, Wang & Yan (2020) *JFE* 138(1) | MKT Sharpe 0.42→0.51, **Jobson-Korkie p = 0.30**; across 103 strategies **8 significantly positive vs 4 significantly negative**; real-time OOS **0.42 vs 0.46 unmanaged**; lower CER in **72 of 103**. Cause: **mean 2.37 structural breaks** per spanning regression, **0 of 103** had none. 99th-pct implied weight **6.47×** — unreachable long-only |
| DeMiguel, Martín-Utrera & Uppal (*JF* 2024) | MKT: in-sample 0.530→0.585 (p 0.244); **OOS 0.530→0.408 (p 0.900)**; **OOS net of costs 0.519→0.325 (p 0.979)** |
| Angelidis & Tessaromatis (2023) *JFM* 65 | profitability *"**disappeared when changes in the trading and information environment in the U.S. in the early 2000s made arbitrage less costly**"* |

**The constructive result.** Bongaerts, Kang & van Dijk (2020) *FAJ* 76(4), open
access, 10 index-futures markets 1982–2019, costs 2–5 bps, **no ex-post scaling**:

> "conventional volatility targeting **fails to consistently improve performance…
> and can lead to markedly greater drawdowns**."
> "it **actually increases the maximum drawdown in the UK, Canadian, Australian,
> and Hong Kong markets, by 4.0%–34.4%**… **increases expected shortfall in 8 out
> of 10 markets, including the US**. This result **defies one of the main
> purposes of volatility targeting**."

US market (base SR 0.59, MDD −52.8%, ES −14.9%):

| | ΔSharpe | ΔMaxDD | ΔES | realized/target vol | turnover/yr |
|---|---|---|---|---|---|
| Conventional VT | +0.15 | −7.0% | **+1.2% (worse)** | **1.16 (overshoots)** | 2.4× |
| **Conditional VT** | **+0.16** | **−8.3%** | **−1.7%** | **0.97** | **1.6×** |
| 10-mkt avg conventional | +0.04 | **+2.3% (worse)** | **+2.8% (worse)** | 1.18 | 2.1× |
| 10-mkt avg conditional | +0.07 | −6.6% | −1.3% | 0.98 | 1.4× |

**Conditional VT = adjust exposure only in the extreme high- and low-volatility
quintiles, unscaled otherwise, leverage capped.** Their own caveat: significant
in **2 of 10 markets** only, and there is **no post-2010 subsample split**.

## B — trend overlays: real drawdown benefit, brutal return cost

Zakamulin (2014/2013 draft), S&P Composite 1926–2012 monthly. "BBT" = best rule
in backtest, no costs; "OOS" = honest out-of-sample with costs:

| | Buy&Hold | SMA BBT | **SMA OOS** | MOM BBT | **MOM OOS** |
|---|---|---|---|---|---|
| Mean return (mo) | 0.90% | 0.83% | **0.71%** | 0.85% | **0.75%** |
| **Max drawdown** | **−79.18%** | −33.69% | **−61.68%** | −32.67% | **−48.57%** |
| Sharpe (mo) | 0.109 | 0.160 | **0.120** | 0.164 | **0.122** |
| **Growth of $100** | **166,155** | 221,436 | **64,345** | 269,275 | **88,871** |

Three things nobody quotes: **you end with $64k vs $166k — 61% of terminal wealth
gone**; **the drawdown benefit itself degrades OOS** (only ~22pp of the ~45pp
improvement survives); Sharpe rises just **~10%**. And 2009–2012: buy-and-hold
Sharpe **0.25** vs SMA **0.09**.

Zakamulin (2018) *IRF* 18(2): *"**In statistical terms, the performance of the
moving average strategy is indistinguishable from the performance of the
buy-and-hold strategy.**"*

Our TSMOM prior confirmed at source — Huang, Li, Wang & Zhou (2020) *JFE* 135:
*"**47 of the 55 assets have a t-statistic of less than 1.65**… only three assets
deliver significant R²_OS."*

The AQR counterweight (Hurst-Ooi-Pedersen) is a **long–short 67-market
vol-targeted managed-futures programme** — net Sharpe 0.76 full-sample but
**0.41 in 2010–2016**, and not transferable to a long-only S&P overlay.

## C — regime classification: positive results carry no significance tests at all

Shu, Yu & Mulvey (2024) *JAM*, S&P 500 1990–2023, 10 bps, 1-day delay:
Buy&Hold Sharpe 0.48 / MaxDD −55.2% → **Jump Model 0.68 / −26.6%**, turnover 44%.
Hyperparameter selection is legitimate walk-forward (8-year backward validation
window) — **not** look-ahead, and I correct any earlier suggestion otherwise.

**But the paper reports no p-value, no standard error, and no confidence interval
for any Sharpe difference.** Three indices, one 34-year window containing 2000–02
and 2008 — the two events any de-risking rule captures. **That is precisely the
profile of a result that passes explore and fails held-out** — which is exactly
what happened to `INSTR-REGIME-JM2` on our own wall (NEG_RESULTS §18). Our
failure is *consistent with* this literature, not an anomaly in it.

Bulla et al. (2011) *JAM* 12, S&P 500: Sharpe 0.390 → 0.577, but *"**the lowest
difference occurs for the S&P 500 (18.5 bp)**"* — the entire gain is a 38%
volatility cut; the return gain is **19 bps/yr**.

The field on itself, verbatim from Bulla's survey: Bauer et al. (2004)
*"substantial parts of the excess returns disappear after accounting for
transaction costs"*; Hess (2006) *"CAPM strategies based on regime forecasts have
**no advantage** w.r.t. a single-state benchmark"*; Dacco & Satchell (1999)
*"**even a small number of wrong regime forecasts is sufficient to lose any
advantage of a superior model**"*; and Ang & Bekaert and Guidolin & Timmermann
*"simply do not take transaction costs into account."*

Welch & Goyal (2008) *RFS* 21(4): *"**the models would not have helped such an
investor**"*; d/p OOS R² **−15.14%** over the most recent 30 years.

---

## Genuine nulls (searched properly — worth stating in the paper)

1. **No source compares the power of probabilistic-forecast evaluation vs
   Sharpe-ratio evaluation.** Confirmed twice independently.
2. **No independent replication or adversarial critique of the statistical-jump-
   model allocation literature exists.** One small mutually-citing cluster
   (Nystrup/Kolm/Lindström; Shu/Yu/Mulvey). Nobody has tried to break it — which,
   given our held-out failure, is the more informative fact.
3. **No peer-reviewed study of a long-only, no-leverage volatility target on the
   S&P 500, out-of-sample, net of costs, with a post-2010 subsample.** Closest is
   Bongaerts et al. (1982–2019, no recency split). ← **This is an open question
   we are equipped to answer, and it is a genuine paper contribution.**
4. Cederburg et al. report **no subsample analysis** (grepped, absent).
5. Post-2010 peer-reviewed 200-day-MA evidence: **only practitioner blogs**.

## Do-not-cite list (carry forward)

- "140 years" attributed to Lorenz (1969) — **not in the paper**.
- "17 years / 40 years to significance" attributed to Lo (2002) — **his paper says
  nothing about years-to-significance**; it is our derivation.
- `SE(SR) ≈ √((1+SR²/2)/T)` as a Lo *quotation* — established by numerical
  reproduction of his Table 1, not quoted.
- Barroso & Detzel (2021) *JFE* 140(3) claims — carried only via DeMiguel et al.'s
  characterisation; the paper itself was unobtainable.
- Ang & Bekaert (2002, 2004), Guidolin & Timmermann (2005, 2007), Dacco &
  Satchell (1999), Leitch & Tanner (1991) — abstracts unfetched; quoted only as
  Bulla et al. characterise them.
