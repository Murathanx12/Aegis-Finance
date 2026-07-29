# Red team on the reasoning-engine design — six claims attacked (2026-07-29)

Hostile-referee pass over the six design claims behind the post-freeze reasoning
engine, run **before** any of them reached a spec. Result: **2 DEAD, 3 WOUNDED,
1 SURVIVES on its distinction but not its protocol.**

Two findings matter more than the verdicts:
1. **A defect in the LIVE engine** (`INSTR-REGIME-ANALOG` phase 1, built
   2026-07-26) — its self-exclusion window is roughly 8× too short.
2. **One of our own citations is wrong** and must not reach the paper (§C5).

Status: evidence review. Nothing registers. The freeze holds.

---

## C1 — Proper scoring rules beat Sharpe on power → **WOUNDED: premise survives, the "therefore" is DEAD**

**The power advantage is real and was measured, not asserted.** Simulation:
2-state Markov (p_stay 0.97/0.90), N=252 months, 600 histories per cell, paired
Diebold-Mariano on the Brier difference with **Newey-West 12-lag** variance — so
serial correlation is handled explicitly.

| true skill | t(Brier) HAC | **P(t≥2) Brier** | t(Sharpe) | **P(t≥2) Sharpe** |
|---|---|---|---|---|
| 0.05 | 3.50 | **82.6%** | 0.16 | **8.4%** |
| 0.10 | 4.52 | 91.0% | 0.40 | 10.2% |
| 0.20 | 5.32 | 95.2% | 1.11 | 23.2% |

HAC cuts the raw t from 11.54 to 5.30 at skill 0.20 — serial correlation bites,
but leaves a ~10× power edge. **The effective-N attack fails as a kill.**

**What kills the "therefore" is the reference forecast.** All of the above scores
against **climatology**. Score the dumbest possible rule — *persistence*, "next
month looks like this month" — against climatology:

> **Brier Skill Score of persistence vs climatology = 0.713**

**71% of the "skill" is free and requires no engine at all.** Re-benchmark the
same forecaster against persistence and the sign flips:

| skill | vs climatology (t / P(t≥2) / BSS) | **vs persistence (t / P(t≥2) / BSS)** |
|---|---|---|
| 0.05 | 3.35 / 81.8% / +0.080 | **−3.96 / 0.0% / −2.704** |
| 0.20 | 5.22 / 94.6% / +0.342 | **−3.29 / 0.0% / −1.663** |
| 0.40 | 5.84 / 94.8% / +0.623 | **−1.28 / 0.3% / −0.450** |
| 0.80 | 7.16 / 96.1% / +0.945 | 2.99 / 94.1% / +0.787 |

A forecaster significant at **t = 5.2 in 95% of 21-year histories** is
**decisively worse than the dumbest rule available** (t = −3.3, 0.0% power).
The failure is silent, self-flattering, and produces exactly the publication-grade
statistic that stops you looking further. Independently reproduced at a different
seed (persistence BSS ≈ 0.728).

**Second wound:** at skill 0.05 the Brier test screams (82.6% power) while
t(Sharpe) = 0.16 — *zero* economic value — and the simulation **flattered** the
Sharpe arm. So C1 buys statistical power to detect something that does not pay.
Gneiting-Balabdaoui-Raftery's "sharpness subject to calibration" is the standard
statement of why calibration is not the target.

**BINDING DESIGN CHANGE:** the reference forecast is **persistence** (plus a
Markov surrogate), **never climatology**, and a minimum **BSS-vs-persistence**
threshold is pre-registered before any scoring run. *This reverses the baseline
this session proposed earlier today* — the earlier note naming climatology as the
S6 baseline is superseded.

### C1 addendum — the scoring metric itself needs correcting (verification pass)

Three corrections that change what gets pre-registered:

**1. The Brier SKILL Score is not strictly proper — do not make it the deciding
metric.** Gneiting & Raftery (2007) *JASA* p.362: *"Mason's (2004) claim of the
propriety of the Brier skill score rests on unjustified approximations and
generally is incorrect."* The disputed step is Mason's per-case Eq. (9)
differentiation. The **Brier score** is proper; the **skill score** is not.

→ **The deciding metric is the paired Diebold-Mariano test on Brier
*differences* vs persistence, with a Newey-West / N_eff variance** — which is
what the C1 simulation actually did. **BSS is reported alongside as descriptive
only.** An improper score can be gamed by a forecaster shading its probabilities;
a paired proper-score difference cannot.

⚠️ *Citation trap:* Mason's **abstract** contains "is not strictly proper" — but
that refers to his **alternative** score BSS_ran (Eq. 11), not BSS_clim. Quoting
the abstract line as if it described BSS_clim inverts his actual position.

**2. Sample size — we may not have enough, and this is checkable now.**
Bradley, Schwartz & Hashino (2008), *Weather and Forecasting* 23(5):992-1006 is
the correct source for the finite-sample side (**not** Mason 2004, whose
mechanism is structural, not sampling): **~300 forecasts** are needed before a
BSS of 0.2 at a 5% base rate separates from zero, and **N=50 gives a 95% CI of
[−0.26, +0.57]**.

We hold **283 belief states**. But they are **month-end observations of 6- and
12-month forward horizons**, so they overlap heavily — 283 monthly obs of a 12m
horizon is on the order of **~23 independent observations**. That is an order of
magnitude below the threshold. **Computing N_eff is a precondition for scoring,
not a footnote**, and the low-base-rate states (`crash12m_dd20` ≈ 16%) are the
worst affected.

Use **N_eff = N(1−ρ)/(1+ρ)** — verbatim in Santer et al. (2000) *JGR* Eq. (6),
attributed there to Bartlett (1935). (Bartlett confirmed to exist via Crossref
but not read; primary attribution is second-hand.)

**3. The power comparison must haircut BOTH arms or it is rigged.** The C1
simulation applied HAC to the Brier arm; the Sharpe-side sample-size formula
`T = t²(1 + SR²/2)/SR²` assumes i.i.d. returns, and Bradley's ~300 assumes
i.i.d. forecast-observation pairs. **Applying N_eff to only one side manufactures
the very advantage C1 claims.** The C1 power table is therefore **indicative, not
settled** — it must be rebuilt with a common haircut before it is cited anywhere,
and it is our own derivation, not a citable published comparison.

**4. Method note for anything that quotes mathematics from a PDF.** Extraction
mangles glyphs silently: AMS PDFs drop `−`/`=` to U+FFFD; old AGU PDFs remap
`=`→5, `−`→2, `+`→1. Every equation quoted in this program needs glyph-level or
rendered-image verification. Adding to the data-integrity protocol beside "an
empty 200 is not evidence of absence."

## C2 — Analog distance as confidence/abstention → **WOUNDED, and my proposed attack FAILED**

**The curse-of-dimensionality attack does not work, and that is worth recording.**
Concentration of distances requires i.i.d. dimensions. Durrant & Kabán (2009),
*Journal of Complexity* 25(4):385-397, prove the converse for **linear latent
variable models** — "the Euclidean distance will not concentrate as long as the
amount of 'relevant' dimensions grows no slower than the overall data dimensions."
A macro state vector *is* that: a few common factors driving many correlated
series. Confirmed numerically (relative contrast, N=252):

| d | i.i.d. dims | latent-factor (realistic macro) |
|---|---|---|
| 10 | 2.26 | **13.65** |
| 40 | 0.73 | **9.35** |
| 80 | 0.48 | **12.32** |

**The real kill: the "analogs" are largely not analogs.** At d=10, k=5:

> **52.6%** of 5-NN fall within **±3 months** of the query.
> **73.1%** fall within **±12 months**.

The engine would be measuring the **local smoothness of its own state path**, not
historical precedent. Purging ±24 months **doubles** the nearest-analog distance
(0.654 → 1.347) — that gap is how much of the "similarity" was temporal
autocorrelation.

### ⚠️ This is a live defect in `INSTR-REGIME-ANALOG` phase 1

Our built engine uses a **63-trading-day (~3 month) self-exclusion**. The red
team's threshold is **±24 months** — roughly **8× longer**. The 21-td non-max
suppression spreads analogs but does not stop them clustering in the two years
before the query.

The engine's face-validity receipts are genuinely good (2020-03-31 → GFC;
2021-12-31 → the 2017-2020 melt-up *and* Oct-2007), so it is clearly reaching far
back at least sometimes. **But we have never measured the age distribution of
accepted analogs.** That measurement is cheap, runs on the 283 belief states
already on disk, and is now mandatory before any belief state is scored or cited.

**Confidence channel — conditional, and marginal.** Rigged *in favour* of the
claim (genuine heteroskedasticity, ±24m purge applied):

| true heteroskedasticity | corr(distance, \|error\|) | bin-test t |
|---|---|---|
| 0.0 | +0.032 | — |
| 1.0 | +0.196 | **2.00** |
| 2.0 | +0.288 | 3.25 |

The mechanism is real *only if* forecast difficulty genuinely varies with state
novelty, and the test reaches just t=2.00 at a large true effect on 252 months.
**Threshold: if the purged distance/error correlation is under ~0.15, the
confidence channel does not exist in our data and abstention is decoration.**

## C3 — Shuffled label as the control → **shuffled WOUNDED · phase-randomisation DEAD · "not buy-and-hold" DEAD**

**Naive shuffling destroys more than the signal** (2000 sims, 252 months,
long-only 0.90/0.30 de-risking):

| label | switches/month | 21y turnover |
|---|---|---|
| real | 0.046 | 6.86 (1.00×) |
| **i.i.d. shuffle** | 0.330 | **49.64 (7.24×)** |
| block bootstrap (12m) | 0.070 | 10.53 (1.53×) |
| **Markov surrogate** | 0.045 | **6.85 (1.00×)** |

The shuffled control trades **7.2× more**, handing the treatment a free
**0.10-0.41%/yr** handicap with zero predictive content. Fix is exact: resample
from the **estimated transition matrix**. Ang & Bekaert: "Because the probability
of staying within the same regime is relatively high, portfolio turnover is low"
— shuffling destroys precisely the property that makes regime allocation
cost-viable.

**Phase randomisation is invalid here.** In surrogate methodology the null *is*
the generation algorithm; Fourier/AAFT surrogates test a linearly-correlated
Gaussian null, which a discrete 3-state regime label can never satisfy for
reasons unrelated to regimes.

**Dropping buy-and-hold was the real error.** No paper in this literature uses a
shuffled-label control: Sharpe (1975) uses buy-and-hold *and* constant mix;
Merton (1981) "always holding the market"; Ang & Bekaert (2002) i.i.d. weights;
Kritzman-Page-Turkington (2012) static 60/40; DeMiguel-Garlappi-Uppal (2009) 1/N.
The exhibit that ends it — Ang & Bekaert (2002) *RFS* 15(4):

> "failing to hold overseas equity is always more costly than using i.i.d.
> weights. For T = 12 months, the 95% tail estimate of the cost of no
> diversification is 4.47 cents (4.86 cents) in regime 1 (2), while the cost of
> ignoring RS is 1.01 cents (0.45 cents) in regime 1 (2)."

**The canonical regime-switching allocation paper finds the regime machinery worth
~4× LESS than the single most boring passive decision** — a comparison a
shuffled-label control makes structurally invisible.

**BINDING DESIGN CHANGE:** run **both** controls. The **Markov surrogate**
(turnover-matched, isolates the regime channel) is **necessary**; **buy-and-hold
/ static 60-40** is the **economic yardstick** and is **binding**. Passing the
surrogate is necessary and not sufficient.

**Citation correction:** Sharpe (1975)'s threshold is **83%** to beat
buy-and-hold; the commonly quoted 74% is the threshold against *constant mix*.
The "seven times out of ten" phrasing is unverified — do not quote it.

## C4 — LLM safe as EXTRACTOR, unsafe as PREDICTOR → **SURVIVES on the distinction, WOUNDED on the protocol**

**The distinction is correct and is the standard econometric treatment.** Ludwig,
Mullainathan & Rambachan, *Large Language Models: An Applied Econometric
Framework* (arXiv 2412.07031 / NBER w33344):

> "For prediction problems -- forecasting outcomes from text -- valid conclusions
> require 'no training leakage'… For estimation problems -- automating the
> measurement of economic concepts for downstream analysis -- valid downstream
> inference requires combining LLM outputs with a small validation sample."

**But the protocol proposed was wrong.** Scoring extraction on *fidelity* —
the magnitude of measurement error — is not the requirement:

> "it is not just the magnitude of the measurement error that matters…but also
> its covariance with the other economic variables (unfortunately rarely if ever
> reported)."

An extractor whose errors **covary with the outcome** biases the downstream
regression however good its average fidelity is — and, perversely, **a model that
memorised the period scores *higher* on fidelity precisely because it memorised.**
Over the training window, fidelity is not merely insufficient; it is partially
**anti-diagnostic**.

**Extraction contamination is real and peer-reviewed:** Bradford Levy, "Caution
Ahead: Numerical Reasoning and Look-Ahead Bias in AI Models," *Journal of
Accounting Research* (2026) — the task is numerical reasoning over financial
statements, *not* forecasting:

> "commercial LLMs are found to suffer from significant look-ahead bias… which
> may account for a considerable share of their apparent predictive power."

**My specific hypothesis was wrong, and the evidence runs against it.** I proposed
that contamination leaks in via *hindsight-biased salience* (the model emphasises
facts that turned out to matter). No test of that mechanism exists anywhere.
Glasserman & Lin (arXiv 2309.17322) scored sentiment extraction with and without
company identifiers:

> "In-sample (within the LLM training window), we find, surprisingly, that the
> anonymized headlines outperform, indicating that the distraction effect has a
> greater impact than look-ahead bias."

The dominant channel is **distraction** — general knowledge of the firm
corrupting the reading — not hindsight salience. Logged as my error.

**The remedy is real, free, and covers our whole window.** ChronoBERT/ChronoGPT
(arXiv 2502.21206, He, Lv, Manela & Wu) — "incorporate only the text data that
would have been available at each point in time." Weights are **publicly
downloadable with yearly checkpoints 2000-2024** (`manelalab/chrono-bert-v1-*`,
`chrono-gpt-v1-*`). Scaled up in Kelly, Malamud, Schwab & Xu, NBER **w35247**
(May 2026) — **our existing citation of w35247 is real and correctly
attributed.** Caveat: yearly granularity permits up to 12 months of within-year
leakage.

**BINDING DESIGN CHANGE:** extraction is validated by estimating the
**covariance of extraction error with the outcome** on a validation sample —
never by fidelity alone — and runs on a **chronologically-consistent checkpoint**
wherever it touches historical text.

## C5 — The allocation layer has a cheaper deflation budget → **DEAD**

**The budget is hypotheses ÷ effective sample size, and the claim counts only the
numerator.** A cross-sectional test consumes a *panel* — thousands of stock-months,
many quasi-independent draws per period. An allocation hypothesis consumes **one
time series with a handful of independent episodes.** Our held-out confirm window
2019-2024 contains **one** NBER recession (Feb 2020 peak, Apr 2020 trough) plus
the 2022 drawdown: **N_eff ≈ 1-2 regime events.** Ten hypotheses against N_eff≈2
is a far worse ratio than 158 against a panel.

Second: "5-10 natural hypotheses" is not the effective count once you include
lookback × threshold × n_states × asset set × rebalance frequency × smoothing.
Forking paths bite even when only one test is run, because the choices follow the
data.

### ⚠️ Citation correction — OUR error, and it is in a committed doc

`REDTEAM_2026-07-28.md` §2 states *"Tally V: 0 of 17 monthly-frequency variables
were still both in-sample and out-of-sample significant by 2020."*

Goyal, Welch & Zafirov, *RFS* 37(11):3490 says:

> "More than one-third of these new variables no longer have empirical
> significance even in-sample. Of those that do, half have poor out-of-sample
> performance."

and explicitly notes "a small number of variables still perform reasonably well
both in-sample and out-of-sample." **Non-zero.**

Both statements could co-exist if "Tally V" is a specific restrictive table row,
but that has not been verified against the table. **Status: CONTESTED. The
"0 of 17" figure is barred from the paper and from any further argument until
verified against the primary table.** The attrition finding still argues against
C5 — by attrition rate, not by annihilation. This is a second instance of the
full-sample-vs-subsample class of error already logged in `REDTEAM_2026-07-28` §8.

## C6 — Market-observable variables are PIT "by construction" → **DEAD as stated**

**C6's own lead example is restated exactly the way NFCI is.** Federal Reserve
Board, Gürkaynak-Sack-Wright yield curve data page:

> "The current vintage data are generally pretty close to the original Gurkaynak,
> Sack, and Wright data, but they are not identical, as small modifications have
> been made over time… Further modifications could be made in the future."

> "a staff research product and not an official statistical release. Accordingly,
> it is subject to delay, revision, or methodological changes without advance
> notice."

Weekly re-estimation, whole-history refit, no notice. **The identical charge C6
levies against NFCI to dismiss macro data.**

Three more: FRED's ICE BofA OAS is truncated to a 3-year window from April 2026
(**we already hit this** — it is a disclosed data departure in
`INSTR-REGIME-ANALOG`, which fell back to Baa−10y); yfinance adjusted closes are
retroactively rescaled on every dividend and split, so realised vol, correlation,
momentum and breadth built from them are **not** what was observable — **our own
`docs/LOOKAHEAD_AUDIT.md` already concedes this**; and the Goyal-Welch predictor
set that attrits so badly is *dominated by market-observable variables*.

**And the asymmetry runs the other way:** NFCI vintages **are** available in
ALFRED. GSW vintages are **not**.

**BINDING DESIGN CHANGE:** neither class is PIT by construction. Whatever the
state vector uses, we build **our own vintage archive with observation
timestamps**. Market data may still be preferred operationally (cheaper to
snapshot ourselves) — but never on the stated reason, which is false.

---

## Attacks attempted and NOT substantiated (recorded, per house practice)

1. Effective-N destroying C1's power advantage — **failed**, HAC halves t but
   leaves ~10× edge. Caveat, not kill.
2. Curse of dimensionality killing k-NN analogs — **refuted**, by Durrant & Kabán's
   converse theorem and by simulation.
3. Hindsight-biased salience in LLM extraction — **no empirical test exists**;
   nearest evidence (Glasserman & Lin) points the other way. **[SPECULATIVE]**
4. Aggarwal-Hinneburg-Keim (2001) verbatim — paper real (ICDT 2001, LNCS
   1973:420-434) but extracted text was internally inconsistent. Not relied on.
5. Schreiber & Schmitz (2000) verbatim — existence verified (*Physica D*
   142:346-382); PDF extraction failed. C3 Part 2 rests on a secondary source.
6. Sharpe (1975) primary text — paywalled, no OA copy. Figures via the
   Buzzacchi & Ghezzi (2021) *JRFM* 14:250 replication.
7. FRED ICE BofA truncation first-hand — network blocked; search-index
   corroboration only (but independently confirmed by our own fetch on 2026-07-26).
8. Levy's memorization-vs-reasoning detail — from a search summary, not fetched
   text. Lower confidence than the look-ahead sentence, which is first-hand.

## Weakest link in the whole design

**C1's "therefore."** It is the load-bearing justification that the engine can be
validated at all on 20 years, and it fails in the most dangerous way available:
scoring against climatology manufactures BSS 0.713 for free and yields t≈5 on a
forecaster that is *significantly worse* than "next month looks like this month."

Which is the same shape as the two trials that died this round — a statistic with
nothing forcing it to answer **compared to what?** Three for three.
