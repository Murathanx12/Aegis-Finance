# Holding-period policy: how long should the engine hold what it admits?

> ## ⚠ VOID — SUPERSEDED 2026-09-05 (roadmap B1 task 4)
>
> **Every number below was computed on a corrupted tape.** Each arm selects
> inside `in_admissible`, which is a threshold on `ratio` — and `ratio` divided a
> SPLIT-ADJUSTED IBES consensus by a RAW close, so the arms were buying a
> different set of names than this document says. The instrument (holding the
> admission signal constant and varying only the horizon) was sound; its
> opportunity set was not.
>
> Re-issued: **`backend/data/optimus/tracker_backtest/holding_period_policy_20260905.json`**.
> The conclusion **REVERSES**: at 25bps per side **no arm of 150 has a positive
> excess CAGR** over the value-weighted market (the best is −6.33pp/yr), and the
> champion quoted here — `rev_top50/fixed_H6m_25bps` — goes from terminal wealth
> **3.743** (excess +1.674pp/yr, t +0.69) to **1.284** (excess −10.08pp/yr,
> t −1.00) against an **unchanged** market terminal wealth of 3.41. The market
> leg did not move; the selection did.
>
> The tables below have NOT been rewritten. See
> `docs/FINDING_2026-09-04_THE_TAPE_REBUILT.md` §2d.


**Date** 2026-09-03 · **Licence** `PRODUCT_EXPERIMENT` · **Receipt**
`backend/data/optimus/tracker_backtest/holding_period_policy_20260903.json`
(every number below is in it) · **Code** `scripts/holding_period_policy.py`

---

## 0. The question, in Murat's words

> "rn because of the hackathon we are day trading but I want engine to be able
> to invest in any timeframe it sees fit. I normally invest around ~52 week
> based on the analyst reviews but it should be able to hold, sell, buy based on
> what it sees fit. I think holding 6-12 months and being adaptive is much
> better but sometimes daily opportunities appear we should catch them. But I
> also see day trading reading graphs and movements doesn't work and makes you
> lose. Test that with multiple scenarios and backtests. Read multiple research
> papers."

Four claims, all of them testable, none of them previously tested here:

1. 6–12 months beats faster.
2. Adaptive (exit early on a reason) beats a fixed clock.
3. Sometimes a daily opportunity is worth taking.
4. Day trading off charts and movements loses.

**All four were tested. Three survive in a modified form; one — number 3 — does
not survive in the form it was asked, and the modification matters.**

---

## 1. RESULTS SCOREBOARD

| | |
|---|---|
| **Best net horizon, level signal (band prior)** | **12 months.** 2.808x over 10 yrs at 25bps vs 2.345x at 1 month — **+19.8% terminal wealth from horizon alone** |
| **Best net horizon, revision signal** | **6 months.** 3.743x at 25bps; the **only** arm in the study that beats the VW market net at every cost tier (+1.67%/yr) |
| **Day trading, measured** | 1-day reversal: **19.97x gross → 0.0004x at 25bps.** Breakeven cost **5.48 bps/side** |
| **12m hold vs 1-day reversal at 25bps** | terminal-wealth ratio **7,021x**, paired **t +13.4**, 12m wins **91%** of months |
| **Best adaptive rule** | stop at −20% **and redeploy into the market**: 3.010x vs 2.808x plain, drawdown **−37.0% vs −48.9%**. Better on **both** axes |
| **The single most expensive convention found** | "exit to cash" vs "exit to market": **1.58x of terminal wealth** (1.910x vs 3.010x) on the identical trigger |
| **Fast-lane allocation that improves anything** | **none.** Every allocation to a chart lane is monotonically worse |
| **RESULT IMPROVEMENT** | a horizon policy, a cost-breakeven for every arm, and a measured refutation of chart day-trading. **No new alpha claim.** |

**Scope, said before the numbers are quoted.** US common stocks with IBES
coverage, 2013–2024 formation, **scored 2015-01-16 → 2024-12-31 (119 months)**
after a 24-month sleeve warm-up so that every arm including the 24-month hold is
stationary before it is scored. Benchmark is the **value-weighted** CRSP
common-stock market (TW 3.41x, CAGR 13.11%); the equal-weighted market is
reported beside it (TW 2.66x, CAGR 10.32%) and is never the headline.

**And the caveat that governs everything below: the level-signal book does not
beat the market.** Every fixed-horizon arm on the broad admissible set has a
*negative* excess CAGR versus the VW market (**−2.2% to −4.4%/yr at 25 bps**;
the best of them, the 18-month hold, is −2.17%). This study
ranks horizons **within one signal**; it is not a claim that the signal is
alpha. Only the revision selector clears the VW market net, and at t +0.69 it
does not clear a significance bar either. Nothing here is a `RESEARCH_CLAIM`.

---

## 2. The literature

Twenty papers, read for the number rather than the conclusion. Every row states
what it implies for **our** engine, whose core signal is a **12-month analyst
target ratio** (`ratio = mean_target / close`) currently traded on a **monthly**
clock, with hackathon books running **daily**.

### 2.1 Does trading fast lose?

| Paper | Headline number | Implied horizon | For us |
|---|---|---|---|
| **Barber, Odean (2000)**, "Trading Is Hazardous to Your Wealth", *JF* 55(2) 773–806 | **Gross** returns across turnover quintiles are flat (18.5%–18.7%); **net**, high-turnover earns **11.4%** vs **18.5%**. Turnover costs the top quintile **6.8%/yr** | — | The failure mode is not a bad signal. It is a good signal traded too often. Exactly our 8.27x-vs-1.50x turnover gap |
| **Barber, Lee, Liu, Odean (2009)**, "Just How Much Do Individual Investors Lose by Trading?", *RFS* 22(2) 609–632 | Every Taiwan trade 1995–99: individuals lose **3.8pp/yr = 2.2% of GDP**. Split: trading losses 27%, **commissions 32%, transaction taxes 34%**, timing 7%. Institutions **+1.5pp/yr** | — | **66% of the loss is pure friction.** Friction is a deterministic function of turnover; the signal is not |
| **Barber, Lee, Liu, Odean (2014)**, "The Cross-Section of Speculator Skill", *JFM* 18, 1–24 | Taiwan day traders 1992–2006: top-500 earn **61.3 bps/day gross, 37.9 net**; **<1%** predictably earn positive abnormal net returns | intraday | Day-trading skill exists and is confined to under 1% of participants. It is not a policy, it is a lottery with a known base rate |
| **Barber, Lee, Liu, Odean, Zhang**, "Do Day Traders Rationally Learn About Their Ability?" (wp) | **1.6%** profitable in the average year; **80% quit within two years**, 7% survive five | intraday | The population you would be joining is defined by survivorship |

### 2.2 Where does the drift actually live?

| Paper | Headline number | Implied horizon | For us |
|---|---|---|---|
| **Jegadeesh, Titman (1993)**, *JF* 48(1) 65–91 | 6/6 momentum **12.01% compounded excess/yr**; best cell **1.49%/mo (t 4.28)** at 12-month formation / 3-month hold with a 1-week lag. **Month 1 is negative** | 3–12 mo form, 3–12 mo hold | The profitable band starts *after* month 1 and ends by month 12 |
| **Jegadeesh, Titman (2001)**, *JF* 56(2) 699–720 | Post-formation monthly profit: months **1–12 +0.93% (t 6.12)**; 13–24 −0.14; **37–48 −0.29 (t −2.51)**; **49–60 −0.39 (t −3.10)** | ≤12 months | A hard ceiling. Our own 24-month arm underperforms our 18-month arm at every cost tier — the same shape |
| **Jegadeesh (1990)**, *JF* 45(3) 881–898 | Extreme-decile monthly reversal spread **2.49%/mo**, 1934–1987 | 1 month = **reversal** | Buying last month's winners loses. Our own measured anti-signal (short-horizon winner-chasing) is this paper |
| **Lehmann (1990)**, *QJE* 105(1) 1–28 | One week's winners and losers **reverse the next week**, surviving bid–ask corrections | 1 week = reversal | Our 5-day reversal arm is **38.2x gross** — the effect is real. See §4 for what it is worth after costs |
| **Bernard, Thomas (1989 JAR Supp; 1990 JAE 13(4) 305–340)** | Price reactions to quarters t+1…t+4 predictable from quarter t. Drift ~**10–25% annualised** over roughly **60 trading days** | ~1 quarter | A genuine sub-annual horizon — but it is an **event** signal, not a chart signal. Untested here |
| **Chordia, Goyal, Sadka, Sadka, Shivakumar (2009)**, *FAJ* 65(4) 18–32 | PEAD is **0.04%/mo in the most liquid** decile vs **2.43%/mo in the most illiquid** | quarterly | The quarterly horizon is real and the money is where you cannot trade it — our own liquidity-band finding restated |
| **Moskowitz, Ooi, Pedersen (2012)**, *JFE* 104(2) 228–250 | 58 instruments: persistence **1–12 months**, partial reversal thereafter for ~4 years; **all 58** positive at 12 months | 12-mo signal, 1-mo hold | Twelve months is where the sign flips, across every asset class tested |

### 2.3 Analyst targets specifically — the paper that names our mechanism

| Paper | Headline number | Implied horizon | For us |
|---|---|---|---|
| **Brav, Lehavy (2003)**, "An Empirical Analysis of Analysts' Target Prices", *JF* 58(5) 1933–1967 | Targets are explicit **one-year-ahead** objects. Long-run TP/P ratio **β = 1.28 mean, 1.26 median**, and **inversely related to size** (small 1.37, large 1.23). Revision-decile announcement BHARs **−3.96% to +3.21%**; favourable-revision drift accrues to **+6.22% by month 6 (t 11.0)**. **Decisive:** when TP/P deviates from its long-run level the adjustment is **α_target = +9.0%/week** vs **α_market = −0.02%, indistinguishable from zero** | level: not a price event · revision: ~6 months | **The ratio mean-reverts because analysts move the target, not because the market moves the price.** This is the academic form of the finding already in our memory: *BAND_PRIOR is a 12-month object on a 1-month clock*. It also predicts, in advance, the single strongest result in §3.2 |
| **Bradshaw, Brown, Huang (2013)**, *RAS* 18(4) 930–955 | 12-month targets 2000–09: implied returns exceed actual by **~15%**; absolute error **45%**; **only 38%** of targets are met at 12 months (64% at *some* point within it); differential analyst ability statistically significant, **economically weak** | 12 months | The unit of our signal is a 12-month forecast with 45% error. Trading it on a 1-month clock samples 1/12 of its information and pays 12x the friction |

### 2.4 What the costs actually are, and the fix the literature endorses

| Paper | Headline number | For us |
|---|---|---|
| **Frazzini, Israel, Moskowitz**, "Trading Costs of Asset Pricing Anomalies" / "Trading Costs" (2018) | **5,310,387 live orders, $721.4bn traded, 1998–2011.** Mean market impact **12.18 bps**, implementation shortfall **13 bps**; **VW means 18.65 / 20.20**; **large cap 11.21 vs small cap 21.27 bps**; long-only 16 vs long-short 10. ~70% of impact permanent. Breakeven fund size: momentum **$52bn**, value $83bn, size $103bn — **short-term reversal only $9bn** | Our 10bps arm is roughly AQR's *large-cap* execution. Our **25bps arm is the honest one** for the small/beaten-down names the ratio selects. And the paper's own capacity numbers say short-horizon reversal is the one strategy costs kill |
| **Novy-Marx, Velikov (2016)**, *RFS* 29(1) 104–147 | **Anomalies with one-sided monthly turnover below 50% mostly survive net; above it, few do.** Costs reduce spreads by **>1% of monthly one-sided turnover**. Of three mitigations — cheap-stock restriction, slower rebalancing, and the **buy/hold spread** (a stricter bar to enter than to stay) — **the buy/hold spread dominates** | The operational line in the whole literature. Tested directly in §3.4 — and it **only reproduces here when the band is on the RANK, not on the ratio level.** That divergence has a mechanism, and it is ours, not theirs |
| **DeMiguel, Garlappi, Uppal (2009)**, *RFS* 22(5) 1915–1953 | **14 optimising models, 7 datasets: none consistently beats 1/N** on Sharpe, CEQ, or turnover | Equal weight is the honest default at every horizon. We use it throughout |

### 2.5 Chart reading, adjudicated

| Paper | Headline number | For us |
|---|---|---|
| **Brock, Lakonishok, LeBaron (1992)**, *JF* 47(5) 1731–1764 | Moving-average and range-break rules on the DJIA 1897–1986 reject four null models. **No transaction costs** | The original positive result, and the omission that makes it one |
| **Sullivan, Timmermann, White (1999)**, *JF* 54(5) 1647–1691 | White's Reality Check over **7,846 rules**, 100 years of DJIA. No profitable simple trading rule survives for DJIA / S&P 500 / S&P futures | The multiplicity control kills it. §63 of our own canon is the same instrument |
| **Hsu, Kuan (2005)**, *JFEc* | **39,832 rules**: significance survives for **NASDAQ Composite and Russell 2000**, not DJIA/S&P | Whatever survives lives in the small and illiquid tail — where costs are 21.27 bps, not 11.21 |
| **Park, Irwin (2007)**, *JES* 21(4) 786–826 | 95 modern studies: **56 positive, 20 negative, 19 mixed** — "most are subject to data snooping, ex post rule selection, and difficulties in estimation of risk and transaction costs" | A positive-result majority produced by selection is not evidence |

**Verification honesty.** Rows for BLLO 2014, the day-trader-learning working
paper, Jegadeesh 1990, Chordia et al. 2009, Bradshaw et al. 2013, DeMiguel et
al. 2009 and Brock et al. 1992 were confirmed at abstract level, not full text.
The widely quoted Bernard-Thomas "4.2% over 60 trading days" figure could **not**
be confirmed from a primary source and is not used. Sullivan-Timmermann-White's
precise in-sample/out-of-sample split is characterised from Hsu & Kuan's
description of it, the publisher having refused the PDF. Lehmann (1990)'s profit
magnitudes are qualitative here.

### 2.6 Our own prior evidence, stated beside the papers

* **`learner_v1.json`, band-prior rank IC by horizon** — and the correction the
  sibling receipt forced on how it may be read:

  | horizon | mean rank IC | t as published | **t_block** | **n_effective** |
  |---|---|---|---|---|
  | 1m | 0.0713 | 12.71 | 14.63 | 143 |
  | 3m | 0.1051 | 20.22 | 13.95 | 47 |
  | 6m | 0.1351 | 28.19 | 13.84 | 23 |
  | 12m | **0.1747** | 34.52 | **13.58** | **11** |

  The raw IC rises with horizon. **The rising t does not** — it is an overlap
  artefact. `band_horizon_20260903.json` recomputes it on non-overlapping date
  blocks and n_effective collapses from 143 to **11** at twelve months, leaving
  t_block essentially *flat* at ~13.6–14.6. It also runs the sqrt(h) test: if
  the prior were a 12-month object sampled monthly, IC(12m) would be about
  sqrt(12) x IC(1m) = **0.2223**; observed is **0.1638**. Sub-sqrt(h) growth
  means the **per-month information DECAYS with horizon.**

  So this table does **not**, on its own, argue for a twelve-month hold, and an
  earlier draft of this document said it did. What argues for a twelve-month
  hold is §3.1 — **net terminal wealth after measured turnover** — which is
  computed on non-overlapping calendar-time monthly returns and is therefore not
  exposed to the overlap problem at all.
* **Short-horizon winner-chasing is a measured ANTI-signal here** (Holm-surviving,
  arc 2026-08-17→20) — Jegadeesh (1990) in our own data.
* **"ALL OF IT HAPPENS OVERNIGHT"** (S17/18): 164.64x overnight vs 0.09x
  intraday, dying above ~1.5bps. A prior study, different construction — quoted
  as precedent for *the shape of the answer* (a real gross effect annihilated by
  a small cost), not as a number this study reproduces.


### 2.7 Where this receipt and its sibling appear to disagree — and why they do not

`band_horizon_20260903.json` (BAND_HORIZON_SELF_ATTACK, run the same day and
embedded verbatim inside this study's receipt) reports the `b_3_5` band's
annualised excess over the VW market as **18.93 pp/yr at a 1-month horizon**,
falling to 10.39 (3m), 5.55 (6m) and 7.30 (12m), with t_block 1.65 at one month.
Read quickly, that says *the short horizon is the good one* — the opposite of §3.1.

It does not, and the reconciliation is the whole point of this document.

Those are **rates of excess return per year of exposure, before the cost of
achieving them.** A 1-month clock earns its higher rate by turning the book over
**8.27x a year**; a 12-month clock turns it over **1.50x**. The sibling receipt
measures the numerator; this one attaches the denominator. Once it is attached,
the 1-month clock's gross advantage on the broad admissible set is **negative
before the first commission** (breakeven −2.08 bps/side), and on the
concentrated top-50 book it survives only below **29.35 bps/side**.

Both receipts are right. **A higher rate of return per year of exposure is not a
higher terminal wealth**, and the quantity a holding-period policy has to
maximise is the second one. The sibling's own Holm export column is empty and
its ordering arena resolves NO-DIFFERENCE, so neither receipt is making a claim
here — they are jointly describing a signal whose gross information is fastest
at one month and whose *money* is slowest.

---

## 3. What our own data says

Method: **hold the admission signal constant and vary only the holding period.**
Every arm buys the same names on the same days; they differ only in how long
they keep them and how often they touch them. Overlapping monthly cohorts
(Jegadeesh-Titman calendar time), equal weight, no intra-cohort rebalancing,
delisting proceeds to cash, costs in basis points **per side on measured traded
notional** — turnover is never assumed, it is what the simulator actually did.

### 3.1 The level signal: the band prior's admissible region

392 names/month on average. Terminal wealth over 119 months, VW market = **3.41x**:

| Hold | gross | **10 bps** | **25 bps** | 50 bps | turnover/yr | max DD @25bps |
|---|---|---|---|---|---|---|
| 1 month | 2.877 | 2.651 | 2.345 | 1.911 | **8.27x** | −55.5% |
| 3 months | 2.549 | 2.446 | 2.299 | 2.073 | 4.17x | −54.3% |
| 6 months | 2.596 | 2.532 | 2.439 | 2.291 | 2.53x | −50.3% |
| **12 months** | **2.913** | **2.871** | 2.808 | 2.707 | **1.50x** | −48.9% |
| **18 months** | 2.884 | 2.855 | **2.811** | **2.739** | 1.04x | −44.2% |
| 24 months | 2.809 | 2.786 | 2.752 | 2.697 | 0.83x | −43.3% |

Four things to read out of this table.

* **The one-month hold has no gross advantage to pay for.** Its breakeven cost
  against the 12-month hold is **−2.08 bps/side**: it is *behind* before the
  first commission. At any positive cost the 12-month hold wins.
* **The whole ranking is turnover.** Gross terminal wealth spans 2.55–2.91;
  net-at-25bps it spans 2.30–2.81, and the ordering is almost exactly the
  inverse of the turnover column. This is Barber-Odean's flat-gross /
  divergent-net result reproduced on an institutional signal.
* **The peak is 12–18 months and it decays after.** 24 months is worse than 18
  at every cost tier. Jegadeesh-Titman (2001) and Moskowitz-Ooi-Pedersen both
  put the sign flip at ~12 months; we find the *net* optimum a little later
  because their horizon is a gross one and ours is paid for.
* **It is economically material and statistically silent.** 12m vs 1m at 25bps:
  **+19.8% terminal wealth**, paired **t +0.65** over 119 months (NW +0.73), and
  the 12-month arm wins 57% of months. A 10-year, +20%-of-wealth difference that
  does not clear t=2 is exactly what a horizon effect looks like at n=119, and
  the honest statement is *"the point estimate favours 12 months at every cost
  tier and the test cannot resolve it"* — not *"significant"* and not *"nothing"*.
  For the 12- and 24-month arms the independent date blocks are nearer 10 than
  119, so those t's are optimistic, not conservative (canon §58).

### 3.2 The revision signal: the prediction Brav-Lehavy made, and it landed

Same machinery, different admission: top 50 by **`target_rev_1m`** (one-month
change in the consensus target) inside the admissible region.

| Hold | gross | **10 bps** | **25 bps** | 50 bps | turnover/yr | excess vs VW @25bps |
|---|---|---|---|---|---|---|
| 1 month | **5.613** | **4.596** | 3.402 | 2.058 | 20.41x | +0.57%/yr |
| 3 months | 3.781 | 3.527 | 3.177 | 2.667 | 7.10x | −0.21%/yr |
| **6 months** | 4.092 | 3.949 | **3.743** | **3.422** | 3.64x | **+1.67%/yr** |
| 12 months | 3.737 | 3.669 | 3.570 | 3.409 | 1.87x | +1.13%/yr |
| 18 months | 3.440 | 3.399 | 3.337 | 3.236 | 1.24x | +0.35%/yr |
| 24 months | 3.193 | 3.164 | 3.120 | 3.048 | 0.94x | −0.42%/yr |

**Brav & Lehavy said the favourable-revision drift accrues to +6.22% by month 6.
Our net optimum is six months.** The one-month hold has the biggest gross number
in the entire study (5.613x) and gives all of it back: its breakeven against the
12-month hold is **25.95 bps/side**, so it wins at 10bps and loses at 25bps.

This is the single most useful finding for the engine, and it is a *two-clock*
finding, not a faster-clock one: **the level of the ratio is a 12-month object;
the change in the ratio is a 6-month object.** They are different signals with
different natural horizons, and the current engine treats only the first one and
trades it on neither of their clocks.

It is also the only selector in the study whose net excess over the VW market is
positive at every cost tier tested. At t +0.69 that is a *direction*, not a
claim. It is enough to justify its own `PRODUCT_EXPERIMENT` book — which is what
the bottleneck rule requires anyway: a new mechanism arrives as its own book,
never as a weight in a composite.

### 3.3 Day trading, measured on our own universe

Genuine daily signals over the same admissible names, PIT eligibility, long the
decile, rebalanced every session. **Breakeven cost is the number that decides it.**

| Chart arm | gross TW | 10 bps | 25 bps | 50 bps | turnover/yr | **breakeven bps/side** |
|---|---|---|---|---|---|---|
| 1-day reversal | **19.97x** | 0.263x | **0.0004x** | 0.0000x | 435x | **5.48** |
| 5-day reversal | **38.22x** | 4.693x | 0.201x | 0.001x | 211x | **15.70** |
| 20-day momentum | 4.41x | 1.425x | 0.261x | 0.015x | 114x | **4.23** |
| 5-day momentum | 2.88x | 0.381x | 0.018x | 0.0001x | 203x | **−0.06** |

**The claim "day trading loses" is now a measured statement about our own signal,
and it is more interesting than the slogan.**

* The charts are **not** empty. 1-day and 5-day reversal both beat the VW market
  gross with **t +2.49 and +2.96**. Lehmann (1990) and Jegadeesh (1990) are alive
  in this universe in 2015–2024.
* The edge is worth **4 to 16 basis points per side.** Realistic cost for these
  names is 21+ bps (Frazzini-Israel-Moskowitz small cap) before any of our own
  slippage. The edge is real and it is **smaller than the spread**.
* So the mechanism of the loss is precise: not a wrong signal, a **priced-out**
  one. Which is Barber-Odean's finding to the letter — gross flat, net ruinous —
  and Frazzini-Israel-Moskowitz's short-term-reversal capacity of $9bn against
  $52–103bn for the 1–12-month factors.
* **The comparison that ends the argument.** 12-month hold vs 1-day reversal at
  25bps: terminal-wealth ratio **7,021x**, paired **t +13.44** (NW +11.29), the
  12-month book wins **91% of the 119 months**. The 1-day reversal book's max
  drawdown is **−99.96%** and its worst rolling 12 months is **−84.1%**.
* And the cost is not linear in a forgiving way: the drag is **43.6%/yr at
  10bps** and **109.2%/yr at 25bps** for the 1-day arm. There is no execution
  improvement that rescues a 435x turnover.

**"Sometimes daily opportunities appear we should catch them" — priced.**
Blending a chart lane into the 12-month core is monotonically destructive at
every weight tested:

| fast-lane weight | core + 1-day reversal @25bps | core + 20-day momentum @25bps |
|---|---|---|
| 0% | **2.835x** | **2.835x** |
| 5% | 1.867x | 2.543x |
| 10% | 1.226x | 2.278x |
| 20% | 0.525x | 1.823x |

A 5% sleeve costs a third of the book's terminal wealth. There is no allocation
at which a *chart-driven* fast lane pays.

**The scope-aware version of that verdict, which is the one that goes in the
roadmap:** this refutes **price-shape day trading**. It does not refute a fast
lane driven by **a new dated fact** — an 8-K, a guidance change, a halt, a
filing. That object was not tested here and Bernard-Thomas plus our own
observation corpus both suggest it is a different animal with a ~60-day horizon.
`MECHANISM_REJECTED` applies to *chart-reading at daily frequency*.
`RETIRED_FROM_CURRENT_SEARCH` is the correct status for "a daily lane" in general.

### 3.4 The cost of merely touching it, and the buy/hold spread

**Touching it.** Same monthly signal, same names, but the book is dragged back to
equal weight every session. Every trade between vintages carries **zero new
information** and a real cost. Turnover goes 8.27x → **14.02x**; drag at 25bps
goes 2.07% → **3.51%/yr**; terminal wealth 2.345x → 2.250x. The breakeven for
daily re-weighting on the broad book is **7.99 bps/side** — below any honest cost.

*An open question that is not a recommendation.* On the concentrated 50-name
books, daily re-weighting has a **large** gross advantage (top-50-by-ratio:
5.785x vs 3.864x buy-and-hold) with breakevens of **46.5 bps** (level) and 14.4
bps (revision). That is a volatility-harvesting / rebalancing return, i.e. the
same short-horizon reversal the chart arms trade — bought in *weights* instead of
in *names*, which is why it is far cheaper. It may be real. It is also exactly
the kind of effect that lives in the illiquid tail where 25bps is optimistic, and
it is a **different hypothesis from the horizon question**. It gets its own
pre-registered test with a proper cost model, not a line in this recommendation.

**The buy/hold spread — and where the literature does not transfer.**
Novy-Marx & Velikov find the stricter-to-enter-than-to-stay rule dominates
slowing the clock. On our data, banding **on the ratio level fails**:

| banding rule | mean names | retention | gross TW | @10bps | breakeven vs 12m hold |
|---|---|---|---|---|---|
| symmetric control (= 1-month hold) | 393 | 73.9% | 2.877 | 2.651 | −2.08 bps |
| enter ≥1.5, keep ≥1.2 | 576 | 88.2% | 2.461 | 2.356 | **−63.95 bps** |
| enter ≥1.5, keep ≥1.0 | 913 | 93.8% | 2.476 | 2.416 | **−180.02 bps** |
| enter ≥3.0, keep ≥1.2 | 119 | 90.3% | 2.429 | 2.340 | −88.45 bps |
| **enter top-25 by rank, keep while top-100** | **42** | 80.5% | **3.050** | **2.865** | **+10.63 bps** |
| enter top-50, keep while top-200 | 84 | 84.6% | 2.619 | 2.489 | −32.47 bps |

The mechanism of the divergence is ours and it is worth stating, because it is a
genuine correction to importing the result: **our signal is a level whose meaning
changes as the price moves.** A name's ratio falls *because its price rose*. A
loose exit band on the ratio therefore does not "hold a winner through noise" —
it deliberately holds names into the `lt_1_5` band, which our own prior scores at
+2.41%/yr against +5.74% and +16.55% for the bands above it. Novy-Marx & Velikov's
anomalies are **ranks**, and when we band on the **rank** the result reproduces:
top-25-in / top-100-out is the only banded variant with a positive breakeven.

**Band on the rank. Never on the ratio level.**

### 3.5 Adaptive exits, and the convention that was doing the damage

12-month default hold, exit early only on a typed trigger. All at 25bps against
plain 12-month hold = **2.808x, drawdown −48.9%, worst rolling 12m −44.4%**:

| Trigger | proceeds go to | TW | vs plain | max DD | worst 12m | paired t |
|---|---|---|---|---|---|---|
| −20% stop + toxic-band exit | **cash** | **1.910** | **0.68x** | −28.6% | −23.2% | −1.50 |
| −30% stop + toxic exit | cash | 1.960 | 0.70x | −35.5% | — | −1.74 |
| −50% stop + toxic exit | cash | 2.253 | 0.80x | −43.9% | — | −1.99 |
| −20% stop + toxic + left-band | cash | 1.241 | **0.44x** | −15.4% | — | −1.74 |
| **−20% stop + toxic exit** | **market** | **3.010** | **1.07x** | **−37.0%** | **−31.2%** | −0.32 |
| −30% stop + toxic exit | market | 2.701 | 0.96x | −38.8% | — | −0.79 |
| toxic-band exit only | market | 2.732 | 0.97x | −48.0% | — | −1.13 |
| **left-band exit only** (thesis complete) | market | **3.058** | **1.09x** | −38.9% | — | −0.23 |
| toxic + left-band exit | market | 2.995 | 1.07x | −37.5% | — | −0.33 |

Read in the order the numbers force:

1. **"Stops destroy wealth" is the wrong lesson.** The −20% stop with cash
   proceeds costs **32% of terminal wealth**; the *identical trigger* with market
   proceeds **gains 7%**. The difference between 1.910x and 3.010x is one
   convention. **The destroyer was exit-to-cash, not exit.** The stop fired
   36,475 times over 119 months; each firing bought a decade-long 13.1%/yr
   market at 0%.
2. **The stop is a real risk control.** It cuts max drawdown from −48.9% to
   −37.0% (market-parked) or −28.6% (cash-parked). Stop-plus-market-park
   **dominates plain buy-and-hold on both axes** — more terminal wealth *and*
   12pp less drawdown. That is the arm to adopt, and its paired t of −0.32 says
   the improvement is free, not that it is proven.
3. **Exiting the toxic band mid-thesis does not help** (0.97x, t −1.13, 6,255
   firings). A ratio ≥ 5.0 is a decisive reason **not to enter** — the
   decontamination receipt puts the clean cell at −41.40%/yr — and is not, on
   this evidence, a reason to leave a position already held. Entry gates and exit
   gates are different objects and we had been assuming one implies the other.
4. **The one exit with a positive point estimate is thesis completion** — the
   ratio falling below 1.5 because the price caught the target (1.09x, 38,474
   firings). Adopt as a default; it is not a claim at t −0.23.

---

## 4. THE RECOMMENDATION: `AEGIS-HORIZON-1`

Named, decisive, and each clause carries the number that bought it.

> **H1. The engine's default holding period is TWELVE MONTHS for a level
> admission and SIX MONTHS for a revision admission.** The horizon is a
> property of the *signal that admitted the name*, not a global setting.
> (Level: 12m is the net optimum at 10bps and within 0.1% of the optimum at 25
> and 50bps, and the 1-month hold's breakeven against it is **−2.08 bps** —
> negative before the first commission. Revision: 6m is the net optimum at 10,
> 25 and 50bps and matches Brav-Lehavy's +6.22%-by-month-6 drift.)
>
> **H2. Turnover is a budget, and it is 1.5x–3.6x/year.** Any proposed change
> that raises annual turnover must state the gross CAGR it buys and the
> breakeven cost per side, in the same paragraph. Below the breakeven, ship it;
> above, refuse it. (Every arm in the receipt carries its breakeven.)
>
> **H3. No capital trades a price-shape signal at daily frequency.**
> Not as a book, not as a sleeve, not at 5%. (1-day reversal breakeven **5.48
> bps**; 20-day momentum **4.23 bps**; 5-day momentum has *no* gross advantage.
> A 5% chart sleeve costs a third of the book's terminal wealth. At 25bps the
> 12-month book beats the 1-day book **7,021x** with **t +13.44**.) A **fast
> lane remains open in principle** — but only for a **new dated fact**, on a
> ~60-day PEAD-shaped clock, with its own pre-registration. Charts are closed;
> events are untested.
>
> **H4. A per-name price stop may not send proceeds to cash.** If a stop fires,
> the capital goes into the benchmark until the next admission. (Cash-parking
> the identical trigger costs **1.58x of terminal wealth**: 1.910x vs 3.010x.)
> With market parking, keep the −20% stop: it is the only rule tested that
> improves terminal wealth **and** drawdown at once.
>
> **H5. Exit on thesis completion, not on the toxic band.** A held name whose
> ratio falls below 1.5 has done its job — recycle it (1.09x). A held name whose
> ratio rises above 5.0 is *not* thereby a sell (0.97x, t −1.13); ratio ≥ 5.0
> governs **admission**.
>
> **H6. If turnover must be cut, band on the RANK, never on the ratio level.**
> Top-25-in / top-100-out is the only hysteresis variant with a positive
> breakeven (**+10.63 bps**); every level-band variant is between −32 and −180
> bps. A falling ratio means the price rose, so a loose level exit holds names
> into the band our own prior scores worst.
>
> **H7. The hackathon books are running the worst policy in this study, and
> that is a deliberate, dated exception.** Daily rebalancing on a monthly signal
> has a breakeven of **7.99 bps/side**. It is justified only by a six-day
> scoreboard, and it expires with the competition. It is not evidence about the
> engine and must not be cited as such.
>
> **H8. Nothing here is an alpha claim.** The level book underperforms the VW
> market on every horizon. The revision book beats it net at every cost tier at
> **t +0.69**. This is a `PRODUCT_EXPERIMENT` result about *how long to hold*,
> conditional on having decided *what to hold*.

### 4.1 The risk arithmetic, printed before the policy is adopted

The session protocol requires the worst case in dollars before any stop or cap
change, and H4 changes a stop. Measured at **100% gross**, 119 months, 25bps:

| Arm | worst month | worst rolling 12m | max drawdown |
|---|---|---|---|
| 12-month hold, no stop | −23.6% | −44.4% | −48.9% |
| 1-month hold, no stop | −24.8% | −46.3% | −55.5% |
| **−20% stop → market** | **−18.7%** | **−31.2%** | **−37.0%** |
| −20% stop → cash | −12.1% | −23.2% | −28.6% |
| revision top-50, 6-month hold | −22.6% | −37.3% | −43.6% |
| 1-day reversal (chart) | −35.3% | **−84.1%** | **−100.0%** |

The arithmetic bound, stated so it cannot be skipped: **with** a per-name stop
the worst case is `n_names × notional% × stop%`. **Without** one it is −100% per
name, so the gross cap `Σ|notional| / equity` becomes the only binding control
and the worst case must be requoted as `gross × drawdown`. At 100% gross the
12-month book's measured worst year is **−44.4%**; at 300% gross — the
twelve-names-at-25% configuration this house has built before — the same year is
arithmetically **−133%, i.e. ruin**. H4 keeps the stop precisely so this does
not have to rest on the gross cap alone.

### 4.2 What to build next, in order

1. **A `PRODUCT_EXPERIMENT` book on the revision signal at a 6-month hold.** Its
   own book, not a weight in `arena_composite`. It is the only arm here that
   beats the VW market net, and the horizon is predicted by a 2003 paper rather
   than fitted by us.
2. **Give every position a `horizon_months` and an `admitted_by` field.** The
   policy above is unimplementable while the book cannot say which signal
   admitted a name.
3. **Change the stop's parking destination before changing the stop's level.**
   One-line change, 1.58x of terminal wealth in this study.
4. **Pre-register the daily-re-weighting question separately** (breakeven 46.5
   bps on the concentrated level book). It is a volatility-harvest hypothesis,
   not a horizon one, and folding it in here would hide the only thing being
   tested.
5. **Do not test more chart rules.** Sullivan-Timmermann-White searched 7,846 and
   Hsu-Kuan 39,832; we have four with breakevens between −0.06 and 15.70 bps.
   The marginal information per dollar is near zero.

---

## 5. Reproduce

```bash
python -m scripts.holding_period_policy --start 2013 --end 2024
# ~67s; writes backend/data/optimus/tracker_backtest/holding_period_policy_20260903.json
```

The receipt carries every arm at 0/10/25/50 bps, the full monthly return series
for each, all head-to-head paired tests, every breakeven, the blend table, the
banding diagnostics, the adaptive trigger counts and the risk bounds. No headline
number in this document exists only in prose.
