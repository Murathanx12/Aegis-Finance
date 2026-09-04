# Aegis Finance — external briefing for AI collaborators (2026-07-30)

**Purpose.** Murat is consulting several AI models on how to maximise ROI on a
~$100k US-equity book. This document exists so that advice arrives *informed*.
It lists what has already been tested, with numbers, and what has already been
refuted, with receipts. **Please read §7 (what NOT to re-propose) before
answering.** Every recommendation that lands in §7 costs a review round and
teaches us nothing.

**Repos:** `Murathanx12/Aegis-Finance` (product + live paper lanes),
`Murathanx12/investing-test-module` a.k.a. "Aegis module" (the research factory).
Heads at time of writing: `c937a9e` / `017d33d`.

---

## 1. What the project is

A pre-registered research program plus a live paper-trading track record, built
around one rule: **a hypothesis must be registered — with its metric, its bar,
and its kill condition — before it touches data.** If it isn't pre-registered,
it didn't happen. Explore window 2004-2018; confirm window 2019-2024 held out
and readable exactly once per graduate.

**Current state:** 162 cumulative candidates tested. **4 partial survivors, 0
confirmed beat-SPY strategies.** The search is FROZEN. The deliverable of the
research arm is now a paper about the graveyard ("The Empty Shelf").

### The single most important number

`INSTR-OVERFIT-CEILING` measured what pure post-hoc selection can manufacture
on our own data:

| | t-stat |
|---|---|
| Best honest-direction signal, full-sample, from our 53-signal closed library | **2.94** |
| Best top-5 composite | 3.27 |
| **Zero-skill expected maximum for a library this size** (Bailey/López de Prado) | **3.6 – 4.0** |
| Best result if sign-flips are allowed (the realistic mining move) | 6.16 single / 6.58 top-5, **Sharpe 1.44** |

**Read that carefully: the best full-sample result our entire library can
produce is indistinguishable from selection noise — and a fake track record
with Sharpe 1.44 is trivially manufacturable from the same data.** Any proposal
that would be judged on a backtest must clear ~t 3.6-4.0 to mean anything here.

---

## 2. Live paper track record (the only forward evidence)

10 lanes, $100k each, real prices, hourly mark-to-market, inception
**2026-06-08**. As of **2026-07-29 — day 52.** `nav.all_fresh` true.

Benchmarks over the identical window (yfinance, auto-adjusted):
**SPY −1.07% · QQQ −7.49% · IWM +1.81%**

| Lane | Since inception | vs benchmark | What it is |
|---|---|---|---|
| conservative-atr | **+3.60%** | +4.7pp vs SPY | conservative mandate + ATR trailing stop + vol cap |
| aggressive | **+3.36%** | +4.4pp vs SPY | rules-based aggressive mandate |
| balanced | +2.21% | +3.3pp vs SPY | HRP-optimised balanced mandate |
| conservative | +1.58% | +2.6pp vs SPY | frozen conservative control |
| tsmom-6040-control | +0.73% | +1.8pp vs SPY | frozen 60/40 SPY/TLT control |
| tsmom-overlay | +0.06% | +1.1pp vs SPY | cross-asset trend overlay (trails its own control by 0.68pp) |
| smallmid-quality | −0.64% | **−2.4pp vs IWM** | the gp-small survivor, live |
| balanced-ew-control | −2.15% | −1.1pp vs SPY | equal-weight control for HRP |
| **conviction** | **−11.92%** | **−10.9pp vs SPY** | Murat's own stock-picking decisions |
| **mirror** | **−20.13%** | **−19.1pp vs SPY** | Aegis rules applied to Murat's actual book |

**How to read this — and how NOT to.** 52 days decides nothing; house policy
forbids skill claims before 24 months, and no lane's decision date has arrived.
But two structural facts are already visible:

- Mirror and conviction hold **the same book** under different management rules.
  Both are down double digits against a flat market. The dominant driver is the
  **book's concentration**, not the management method. QQQ −7.5% over the window
  says much of it is concentrated growth beta.
- The four boring rules lanes all beat SPY; the two conviction-flavoured lanes
  both lost badly to it. One 52-day sample, proves nothing — but it is the shape
  the literature predicts.

**Registered forward clocks not yet decidable:** TRIAL-001 (HRP vs EW, decides
2027-06-10), TRIAL-CMP-INSIDER-IC (2027-07-21), TRIAL-SMQ-FWD (2028-07-22),
TRIAL-TSMOM-XA (24mo), TRIAL-SMARTGROWTH (2027-01-12), TRIAL-CONGRESS-IC
(2027-01-11), TRIAL-ARK-IC, TRIAL-FORECAST-LEDGER (2027-07-16).

---

## 3. Backtest results — the survivors

Explore 2004-2018 / confirm 2019-2024 held out, CRSP survivorship-free panel
(11,098 permnos, real delisting returns), honest costs.

| Survivor | Explore | Confirm (held out) | Caveats — all disclosed |
|---|---|---|---|
| **gp-small** (gross profitability, small caps; Novy-Marx) | 50bps t_net 1.96 → 2.19 after EAD re-timing | **+24.1 bps/mo, net t 0.89, IC t 4.29**; after EAD re-timing **+33.5 bps/mo, net t 1.24, IC t 4.35** (IC essentially unchanged — the two t-stats measure different things and are labelled here after a reviewer misread the pair as an IC collapse); under measured KO costs net t **1.11–1.45** | DSR **0.098**, FF6 alpha **negative**, Newey-West t **0.77**. Of the +9.4 bps EAD headline gain, +6.8 is benchmark composition. **Not significant by any conventional bar.** |
| **INSTR-TSMOM-XA** (cross-asset 12-1 trend overlay) | passed | **2020 +9.2%, 2022 flat**; overlay maxDD **−18.8% vs SPY −33.7%** | Return drag vs SPY **t −1.86**. This is a *defensive diversifier*, explicitly **not** beat-SPY. Now live as a paper lane. |
| **insider CMP** (opportunistic buyers, Cohen-Malloy-Pomorski rule) | FF5+UMD alpha **+102 bps/mo, t 1.89** largemid | forward-only clock, undecided until 2027 | Null in microcap. Post-2010 literature says the effect decayed **60-70%** off CMP's 82 bps/mo baseline. |
| **fusion** (BRAIN-007 composite) | re-opened on 2 survivors | pending | — |

**There is no confirmed strategy that beats SPY.** The strongest thing the
program owns is a small-cap quality tilt that fails every significance bar, and
a trend overlay whose claim is *shallower drawdowns at a disclosed return cost*.

### Cost model (measured, not assumed)
Kyle-Obizhaeva invariance half-spreads on our panel, one-way:

| segment | 2004-2010 | 2011-2018 | 2019-2024 |
|---|---|---|---|
| large/mid (dollar-vol rank 1-1000) | 4.2 bps | 3.4 bps | 3.4 bps |
| small (rank 1001-3000) | 13.1 bps | 12.1 bps | 11.6 bps |

Below rank 3000 the eligible universe is a **median of 35 names/month** (zero in
123 of 276 months) at $1 price / $200k ADV floors; the marginal name at rank
3000 already trades $379k/day. **`small` IS the retail-accessible frontier —
there is no smaller shelf to appeal to.**

### Harness validation (so you can trust the numbers above)
`INSTR-HARNESS-VALID` vs Ken French factors: EW market 0.927 (bar 0.90),
small−largemid vs SMB 0.778 (bar 0.60), momentum vs UMD 0.645 (bar 0.40).
All three passed — the plumbing is not the explanation for the graveyard.

---

## 4. Backtest results — the graveyard (23 recorded negative results)

Every row is a pre-registered, one-shot run. Full text in
`NEGATIVE_RESULTS.md`.

| # | What was tested | Result |
|---|---|---|
| 1 | Signal-engine market timing, 2020-2025 | **+250.9% vs +740.0% buy-and-hold**; Sharpe 0.675 vs 0.921; sell-signal 3M hit rate **28.6%** (target >55%). All 7 sells fired at VIX>25 — the best buying opportunities. [VOID 2026-09-04 — the +250.9/+740.0 pair was measured against ^GSPC (price index) with 66 OVERLAPPING windows compounded as if sequential. Regenerated on SPY total return, non-overlapping: **+28.3% net vs +114.8% buy-and-hold**, Sharpe 0.432 vs 0.837, sell hit rate 0.0% of 5. The DIRECTION below stands; the magnitudes do not. See `backend/BACKTEST_RESULTS.md` and `docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §3.1] |
| 2 | 12-month crash prediction | ≈ climatological base rate, **no skill** |
| 3 | LPPLS bubble timing | predictive skill **refuted twice**; ships descriptive-only |
| 4 | Survivorship-free universe on free data | **1 of 20** delisted names usable on yfinance; 4 returned a *different* company on a recycled ticker |
| 6 | Crash-model retrain | loads, predicts, passes 214 tests, **still not deployable** — label sparsity; walk-forward AUC unmeasurable |
| 7 | Crash severity model (TRIAL-CRASH-2) | **0 of 6 dense cells passed**; negative Brier skill vs climatology at every cell |
| 8 | EODHD paid data acceptance gate | **14/20 vs bar 16 → FAIL**, subscription cancelled. Phase-1's "16/20 PASS" was itself inflated by recycled-symbol false positives |
| 9 | Long-only 12-1 momentum, survivorship-free — **window 2017-01→2026-06 on the 50,462-name delisting-aware panel, NOT the 2004-2018 CRSP explore window** | CAGR **17.9%** vs SPY 15.3% — and **REJECTED**: Sharpe 0.629 vs 0.871, maxDD **−54.7%** vs SPY −33.7% (the COVID drawdown; SPY's −55.2% figure elsewhere in this document belongs to the 2004-2018 window and the two are not comparable). Out-returns and is uninvestable |
| 10 | Momentum + 10-month SMA trend filter | **CAGR 4.8%, Sharpe 0.307, maxDD −61.3%** — worse than the thing it was built to fix. Filter fired on the right months; monthly cadence takes the first leg down and misses the V-rebound |
| 11 | FDA approval drift, monthly | −30.1 bps/mo net, **t −0.89** |
| 12 | Supply-chain / customer momentum, annual | decile spread **t 0.10** |
| 13 | conc_low — first full-strength explore graduate | explore net t 2.28, IC t 4.46 → **confirm −5.5 bps/mo, t −0.20, DSR 0.0003** |
| 14 | **The self-deception ceiling** | see §1. Also: agreement-gated PEAD came out **inverted** (IC t −2.6) |
| 15 | Regime rotation (statistical jump model) | explore 11.2% CAGR vs SPY 7.7%, maxDD −26.6% vs −55.2% → **confirm REJECT: 2022 −21.6%** (went risk-off into TLT during the dual crash), 2020 missed the rebound (+4.8% vs +18%) |
| 16 | FDA approval drift, daily CAR | CAR(+1,+20) +2.1%, **t 1.45** vs bar 2.0. Drift lives in HIGH-attention events — the opposite of the proposed gate |
| 17 | Analyst price targets | **strongly perverse**: largemid −90 bps/mo (t −3.62), small **−199 bps/mo (t −7.21)**. Dispersion-conditioning halves the bleed but never reaches a positive sign |
| 18 | Inflation-gated regime rotation (JM2) | explore flattered it (2008 +32.4%) → **confirm made 2022 WORSE than the design it repaired** (−23.9% vs −21.6%) |
| 19 | LLM / AI-agent trading alpha | closed on external receipts — see §6 |
| 20 | Distress 8-K exclusion screen | headline passed (−5.95%, t −7.06) and **the control beat it** (−6.79%, t −11.33). Measured eligibility selection, not filing information |
| 21 | **Conditional volatility targeting** (the "go to cash when vol spikes" family) | explore PASS → **confirm REJECT. Overlay maxDD identical to SPY to 4 decimal places on the same trough date.** 2020: +3.28% vs SPY +18.33% — a 63-day vol window entered March 2020 at full weight because the prior 60 days were the calmest in years. Bootstrap CI on Sharpe diff vs SPY: **[−0.164, +0.055]** |
| 22 | Small-cap cost-killed shelf (NEW, 2026-07-30) | cohort non-empty (5), **zero graduates**. Across the 160 candidates that existed *when this trial ran* exactly **one** signal is genuinely cost-killed (`rec_mom`), executioner **36.8%/month turnover**. (Cumulative is 162 today; INSTR-RESID-MOM added 2 afterwards — the counts differ by timing, not by error) |
| 23 | **Residual momentum** (NEW, 2026-07-30) | **REJECT.** See §5 |

### Two cross-cutting measurements

- **`INSTR-CZ-CALIB`:** Spearman correlation between a signal's *published*
  t-stat and our measured in-window t is **−0.544** (p 0.055, n=13). **The more
  celebrated the published effect, the deader it runs on our data.** Sign
  agreement 0.923 — directions survive, magnitudes invert (median level ratio
  0.378).
- **Empty cost-killed cohort:** across 155 large/mid candidates, **zero** were
  killed by costs alone. Best gross t among rank-informative rejects was 1.48 —
  below the bar, so it could not graduate *at zero cost*. Rejections were
  informational: the edges were arbitraged away, not eaten by fees.

---

## 5. Newest result (2026-07-30) — residual momentum, and why it matters

Residual/idiosyncratic momentum was the strongest remaining candidate in the
literature: one of the few anomalies with an explicit **post-publication
out-of-sample survival** claim (Blitz-Huij-Martens 2011; Blitz-Hanauer-Vidojevic
2020 — comparable returns at ~half the volatility, no long-term reversal).
Spec followed verbatim: FF3 OLS over m-35..m, signal = mean residual over
m-11..m-1 / its sd, direction +1.

| | segment | net bps/mo | t_net | **t_IC** | **maxDD** | β_mkt | FF3 alpha |
|---|---|---|---|---|---|---|---|
| resid_mom | small | −16.9 | −1.34 | **0.81** | **−54.3%** | **0.956** | −8.8 bps (t −0.78) |
| mom_12_1 | small | −37.5 | −1.83 | **3.05** | −65.7% | 1.189 | −52.4 bps (t −3.04) |
| resid_mom | largemid | −20.6 | −1.29 | 0.33 | −58.5% | 1.045 | −15.0 bps (t −0.92) |
| mom_12_1 | largemid | −28.6 | −1.17 | 0.63 | −64.1% | 1.286 | −44.1 bps (t −1.94) |

**The construction worked exactly as advertised, and that is why it failed.**
Residualising pulled market beta back to ~1.0, stripped the size/value tilts,
made the drawdown **11.4 points shallower**, and killed a significantly-negative
alpha (−52.4 bps, t −3.04 → −8.8 bps, t −0.78). **And the rank information left
with the tilt: small-cap IC t fell 3.05 → 0.81.**

**Conclusion: in this window, the cross-sectional information in small-cap
total-return momentum WAS its factor tilt, not idiosyncratic continuation.**
Strip the tilt and there is nothing underneath. Momentum is now closed at both
total-return and residual resolution.

*Validation performed before writing this up (a null is worthless if the signal
is broken): rank correlation with mom_12_1 = 0.662 (related but distinct,
exactly as BHM describe), 180/180 explore months scored, sane dispersion.
Disclosure: the first execution was VOID — an off-by-one put the formation
month inside the signal window; a spec test caught it, both sets of numbers are
published.*

---

## 6. The reasoning/"logic brain" — graded, and the grade is bad

Murat's central idea is an engine that reads the current situation, finds
historical analogs, and emits probabilities. **It was built** (283 belief states
over a 15-feature daily macro descriptor, k-NN analog retrieval, 2002-2026) and
then **graded** against a persistence baseline with a Murphy decomposition and
Diebold-Mariano tests:

| Diagnostic | Result |
|---|---|
| D1 — analog age (is it just measuring autocorrelation?) | did NOT fire (10.78% of analogs ≤12mo vs a 40% kill line) |
| D2 — effective dimension | **FIRED**: 9 PCs at 90% variance vs a 15-D retrieval. But the 2-3-PC remedy changes ~85% of analogs and moves output probabilities by ≤0.05 — retrieval is near-no-op on the output |
| D3 — skill vs **persistence** | fwd-6m beats persistence (DM t −2.31) but **87.6% of the win is hedging (reliability), not resolution**. Other 3 surfaces inconclusive. **REL > RES on all four — a constant at the base rate strictly beats the engine everywhere** |
| D4 — confidence channel | corr(distance, \|error\|) = 0.104 / 0.063 for return-sign outcomes vs a 0.15 kill line — **the abstention channel is decoration** for returns; plausibly present only for drawdown-flavoured outcomes |

**Plain statement: the analog/belief engine is a hedged base-rate emitter. It
has no demonstrated resolution.** It ships descriptive-only and never allocates.
Any proposal to "build a market-state engine" or "search historical analogs"
must engage with these four diagnostics, not restate the idea.

---

## 7. ⚠️ DO NOT RE-PROPOSE — closed families with receipts

Each of these has been run or refuted. Proposing one without rebutting its
receipt costs a round.

**Timing / allocation**
- Go to cash / reduce exposure when VIX or realised vol spikes → §21, §1, §10
- Regime switching with a state machine + one macro gate → §15, §18 (two receipts)
- Continuous or conditional volatility targeting → §21 + 4 published refutations
- Trend filters on monthly cadence → §10
- Historical-analog / market-state engines → §6

**Stock selection**
- Total-return momentum, any holding rule → §9, §10; residual momentum → §23
- Analyst price targets / recommendations / estimate revisions → §17 (0-for-3)
- PEAD at monthly cadence (incl. agreement-gated) → §14, inverted
- Low-vol / lottery / idiosyncratic skew → closed family
- Accruals, asset growth, value (RE/ME) → closed in-window
- Supply-chain and connected momentum → §12; conn_mom net t −0.78 at 67% turnover
- FDA approval drift, monthly AND daily → §11, §16
- Distress 8-K screens → §20 (needs a valid control)
- Lazy Prices / 10-K text similarity → net t 0.87, family closed
- Insider **cluster** buys (3+ in a window) → adds nothing over single opportunistic buys
- Short interest: level = filter, trend = net-dead

**Method / tooling**
- "Use vectorbt to sweep thousands of parameters" → the bottleneck is held-out
  windows, not compute. Faster sweeps raise the deflation count, which is the
  binding constraint. **Actively harmful here.**
- "Fix survivorship bias, get CRSP" → done, §4 and §8 record what it cost
- "Align to release dates, model slippage, use walk-forward" → all done, and
  improved on (purged CV + embargo, EAD re-timing, per-name KO cost frame)
- LLM/agent trading alpha → §19: the flagship paper was **withdrawn**, FINSABER
  kills the agent literature net of costs 2004-2024, and the one honest
  replication self-describes as infeasible. Any new proposal must rebut **all
  three**, not cite a fourth paper. **Scope correction (2026-07-30, credit
  DeepSeek):** these receipts close *LLM-as-trader* — an LLM deciding what or
  when to trade. They do **not** close *LLM-as-feature-extractor*, where an LLM
  produces a typed input that a deterministic, tested engine consumes. The house
  already does the latter (EVENT-INTEL classifies enums; the engine computes),
  and the standing rule permits it by construction. A feature-extraction
  proposal is admissible and needs its own control arm, not a rebuttal of §19.
- Neural nets / "virtue of complexity" → INSTR-VOC: not supported on our data
- Kelly sizing from model probabilities → the binary-bet formula doesn't apply
  to continuous returns, and §6 says our probabilities have no resolution
- **Options income / covered calls / put-writing / JEPI-class** → killed at
  prior-check 2026-07-30: Dew-Becker & Giglio find index-option alphas
  **indistinguishable from zero over the past ~15 years**

---

## 8. What is genuinely open — where help is actually wanted

1. **OptionMetrics (`optionm`, 578 tables catalogued, never touched).** The only
   untried *information class*: not price/volume, fundamentals, analyst,
   insider, text or macro. Daily resolution. Candidate constructs: call-put
   implied-vol spread, option/stock volume ratio (Roll-Schwartz-Subrahmanyam),
   realised-minus-implied vol, IV skew. Long-only executable (options are the
   *input*; the trade is a stock). **Blocked on a WRDS entitlement test.**
2. **Full daily CRSP (`crsp.dsf`) for the general universe.** We hold only the
   pharma slice. Both the 8-K and PEAD families are closed at monthly resolution
   with the explicit note that a **daily event harness is the only admissible
   successor** — and it cannot be built without this.
3. ~~**13F best-ideas.** Data already on disk (3.6M rows, 1980→present,
   untouched).~~ **❌ CORRECTION 2026-07-30 (v2): THIS WAS WRONG. `best_ideas`
   WAS tested — factory batch 3b, 180 explore months.** Construction: count of
   distinct 13F managers holding the name among their **top-3** positions,
   45-day filing lag (`altstores2.load_best_ideas`). Result:

   | segment | net bps/mo | t_net | t_gross | **t_IC** | turnover |
   |---|---|---|---|---|---|
   | small | −5.7 | −0.53 | 0.51 | **2.70** | 0.226 |
   | largemid | −15.3 | −1.28 | −0.92 | −0.02 | 0.084 |

   Recorded verdict (`docs/STRATEGY_FACTORY.md`): *"real information in small
   caps (IC t 2.70), net-negative book."* **What genuinely remains open** is
   narrower than "run 13F": the tested version is a *count* proxy, and the
   protocol itself flags that *"the crude count proxy ≠ CPS's weight-tilt
   construction; a tilt-based variant is a legitimate NEW future candidate."*
   So: a portfolio-weight-tilt implementation of Cohen-Polk-Silli is open; the
   naive best-ideas clone is not. **This error propagated — four external
   reviewers independently made "run 13F best-ideas" their top recommendation
   because this document told them it was untouched.**
4. **Meta-labeling** (López de Prado) as a *sizing* layer. Never tried. Weak
   prior: sizing a t≈1.1 signal mostly amplifies estimation error.
5. **The honest non-alpha levers**, which are larger than anything above:
   tax-loss harvesting (**+69–110 bps/yr**, Chaudhuri-Burnham-Lo — but **exactly
   zero for a Hong Kong resident**, no capital gains tax); cost discipline; the
   behaviour gap; and position-concentration risk, which the mirror lane is
   currently demonstrating at −20%.

### The question we most want answered
Given §1 (best achievable t ≈ 2.94 against a zero-skill ceiling of 3.6-4.0) and
the empty cost-killed cohort: **is there any information class reachable by a
retail account that we have not already exhausted — or is the correct conclusion
that the search is over and the remaining levers are allocation, risk-shaping,
cost and behaviour?** Arguments for "the search is over" are as welcome as
arguments against; we are not looking for encouragement.

---

## 9. References

**Verified by us this session (2026-07-30), with numbers checked:**
- Dew-Becker, I. & Giglio, S. (2025). *The Decline of the Variance Risk Premium:
  Evidence from Traded and Synthetic Options.* Chicago Fed WP 2025-17 / SSRN
  5525882.
- Chaudhuri, S., Burnham, T. & Lo, A. (2020). *An Empirical Evaluation of
  Tax-Loss-Harvesting Alpha.* Financial Analysts Journal 76(3). — 1.10% gross /
  0.94% net; 0.85% / 0.69% under the wash-sale constraint.
- Blitz, D., Huij, J. & Martens, M. (2011). *Residual Momentum.* J. Empirical
  Finance 18.
- Blitz, D., Hanauer, M. & Vidojevic, M. (2020). *The Idiosyncratic Momentum
  Anomaly.* Int. Review of Financial Analysis.
- Hanauer, M. & Windmüller, S. (2023). *Enhanced Momentum Strategies.* JBF.
- Cohen, L., Malloy, C. & Pomorski, L. (2012). *Decoding Inside Information.*
  Journal of Finance / NBER w16454. — 82 bps/mo; post-2010 decay 60-70%.
- Huang et al. *Time Series Momentum: Is It There?* — pooled regressions
  overstate 12-month predictability.
- Schroeder, J. & Posch, P. (2024). *Portfolio Strategy Cloning from SEC 13F
  Filings.* — with the documented post-2008 decline.
- Cohen, Polk & Silli. *Best Ideas.*

**Cited in the program's own ledger (used to build or to kill something):**
Kyle, A. & Obizhaeva, A. (2016) Econometrica — invariance spreads, eq. 33 ·
Bailey & López de Prado — Deflated Sharpe, PBO, expected maximum Sharpe ·
López de Prado, *Advances in Financial Machine Learning* — purged CV,
triple-barrier, fractional differentiation · McLean & Pontiff (2016) ·
Chen & Zimmermann — Open Source Asset Pricing / SignalDoc (331 signals) ·
Chen & Velikov — cost model · Chen & Welch (2026) — 7 bps/mo post-2005 non-micro ·
Fama & French (1992, 1993, 2015) · Novy-Marx (2013) · Ball et al. (2016, 2020) ·
Sloan (1996) · Cooper, Gulen & Schill (2008) · Pontiff & Woodgate (2008) ·
Jegadeesh et al. (2004) · Cohen & Frazzini — supply-chain links ·
Ali & Hirshleifer — connected momentum · Cohen, Malloy & Nguyen (2020) —
*Lazy Prices* · Livnat & Mendenhall — PEAD · Lerman & Livnat (2010) RAST — 8-K ·
Bali, Cakici & Whitelaw (2011) — MAX · Ang et al. (2006) — downside risk ·
Amihud (2002) · George & Hwang — 52-week high · Da & Schaumburg — analyst
optimism · PSZ (Management Science 2025) — dispersion-conditioned targets ·
Dasgupta, Prat & Verardo (2011) · Chen, Hong & Stein (2002) — breadth ·
Boehmer et al.; Rapach et al. (2016) — short interest · Bongaerts, Kang &
van Dijk (2020) FAJ — conditional vol targeting · Liu, Tang & Zhou (2019);
Cederburg et al. (2020, Jobson-Korkie p=0.30); DeMiguel et al. (2024, OOS net
p=0.979); Angelidis & Tessaromatis (2023) — the four vol-targeting refutations ·
Moskowitz, Ooi & Pedersen — time-series momentum · Berkin & Wang · Shumway
(1997), Shumway & Warther (1999) — delisting returns · Merton (1976) — jump
compensator · Adams & MacKay (2007) — BOCPD · Sornette — LPPL · Kritzman —
turbulence & absorption ratio · Gu, Kelly & Xiu (2020) · BIS WP 1250 (2025) ·
NBER 33554 — rebalance-date randomization.

**LLM/agent-alpha closure receipts (§19) — cite these before proposing LLM alpha:**
- Kim, Muhn & Nikolaev, arXiv 2407.17866 — **WITHDRAWN 2025-02-20** after a
  co-author's own replication found inconsistencies.
- FINSABER, arXiv 2505.07078 (KDD 2026) — FinMem / FinAgent / FINCON /
  Lopez-Lira-style prompting alpha disappears over 2004-2024 after commissions.
- Glasserman & Lin, arXiv 2309.17322 — the authors describe their own profitable
  configuration as "not a feasible strategy."

**Data sources in use:** CRSP + Compustat + IBES + Thomson-Reuters 13F (WRDS) ·
SEC EDGAR (Form 4, 8-K daily index, 10-K full text) · FRED · Kenneth French
Data Library (pinned vintage, sha256 `54e3b8dd…`) · openFDA · GDELT · yfinance ·
Polygon.io · Finnhub · FMP · QuantConnect/LEAN (the survivorship-free replay
venue, chosen after EODHD failed its acceptance gate).

---

## 10. Ground rules for anything you propose

1. **State a prior before results exist**, and state it honestly.
2. **Name the kill condition.** What result would make you abandon it?
3. **Assume it costs a deflation slot.** We are at 162 cumulative candidates;
   a new candidate needs roughly t 3.6-4.0 to be distinguishable from noise.
4. **Costs are not the missing ingredient.** Measured, and the cost-killed
   cohort came back empty in large/mid and produced zero graduates in small.
5. **Backtests do not decide anything here.** Explore numbers are hypothesis
   generation; only the held-out confirm window and the forward paper clocks
   count. We can manufacture Sharpe 1.44 on demand and have the receipt.
6. **Nothing an LLM produces may allocate.** The LLM narrates; a deterministic,
   tested engine computes.
