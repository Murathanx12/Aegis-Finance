# Causal / news "logic brain" — own research, fact-check of four AI reviews (2026-07-28)

**Status: RESEARCH NOTE + FACT-CHECK. Nothing here is registered, nothing
graduates, nothing re-opens a closed family.** Produced in response to Murat's
thesis (news + causal reasoning + LLM belief engine over brute-force factor
mining) and four AI responses (GPT, Gemini, DeepSeek, Bigdata). Every load-bearing
claim below was verified against a primary or near-primary source; claims I could
not verify are marked as such. Verification matters here because two of the four
responses contain confident statements that are wrong, and one contains a
correction that changes the plan.

---

## 0. Headline

**Murat's instinct is better supported by the evidence than this program's current
posture assumes — but not for the reason he gave, and his own worked example has
the sign backwards half the time.** The single most useful finding below is that
the commodity→equity link he described is REAL, REGIME-DEPENDENT, and reverses
sign between expansions and recessions. That is precisely the shape a belief/
regime engine can exploit and a naive causal chain cannot.

Separately: the "you can't backtest an LLM because it knows the future" objection —
the strongest argument against his plan — **is real but has been solved**, and the
solution is free and open-weight.

---

## 1. What the four reviews got wrong (corrections, with receipts)

| Claim | Source | Verdict |
|---|---|---|
| "LLM backtests are a terminal trap — the model knows what happened, any backtest shows fake alpha" | Gemini | **OVERSTATED.** Glasserman & Lin (Columbia, arXiv 2309.17322) measured exactly this. Two effects: look-ahead bias AND a *distraction* effect (general knowledge of the named company interfering with sentiment measurement). Their finding: **anonymized headlines OUTPERFORM**, meaning the distraction effect is LARGER than the look-ahead bias. They publish an anonymization procedure explicitly for debiased backtesting. So the trap is real, measurable, and has a documented mitigation — not terminal. |
| "Thomas Wehlen, top 0.5% of 170,000 funds, anti-alpha philosophy" | DeepSeek | **REAL — I expected a hallucination and was wrong.** Coburn Barrett / GLI Fund, launched Jan 1998, ~$1,000→$23,000 since 1998 (≈12.3%/yr over 27y). **But read what he actually does:** anti-prediction, global diversification, no short-term trading, flat 2% fee, no performance fee. His method is the *opposite* of a causal news brain — it is asset allocation and risk management. Source quality caveat: the numbers come from Opalesque TV, a promotional interview platform, not an audited database. |
| "FinLLM-Predict: 12.3% directional accuracy improvement, 18.7% volatility error reduction"; "Liu et al. 2025 sentiment+ARIMA significantly improved trading" | DeepSeek | **UNVERIFIED — could not locate either.** Treat as unsourced. They also sit in direct tension with FINSABER (below), which is peer-reviewed and covers 20 years. |
| "Retail pays a speed tax erasing up to 18% of returns annually"; several "Causal AI" and "AlphaGo moment" citations | Bigdata | **LOW-QUALITY SOURCING.** These trace to vendor press releases and outlets like Crypto Wire, Tech Times, Eastmoney promotional pieces. The underlying point (institutions are faster) is true; the 18% figure is marketing, not measurement. |
| "Renaissance is the exception; mostly short-horizon statistical signals + execution" | GPT | **CORRECT and correctly hedged.** Medallion is closed, employee-only, and not a template. |
| The hindsight caution: "Trump elected → defense stocks up was obvious" is only obvious afterwards | GPT | **CORRECT, and it is the most important methodological sentence in all four responses.** This is precisely what a point-in-time replay is for. |

---

## 2. How outperformance actually happens (verified)

### 2.1 The base rate is brutal, and it is the thing to beat

S&P SPIVA, 20 years to end-2024: **94.1% of US domestic funds underperformed** the
S&P 1500 Composite. On a **risk-adjusted** basis, **97.3%** underperformed. Only
**48.5% of funds even survived** the full 20 years. Underperformance rates *rise*
with horizon; past 15 years there is no domestic or international equity category
where a majority of active managers beat their benchmark.

This is the correct denominator for any "we will beat the S&P" ambition.

### 2.2 Buffett — the most famous "logic brain" — has been decomposed into a formula

Frazzini, Kabiller & Pedersen, *Buffett's Alpha* (Financial Analysts Journal
74(4), 2018; NBER w19681). Findings:

- Berkshire's Sharpe ratio is **0.79** — high, but not superhuman.
- Buffett applies leverage of about **1.7:1**, sourced cheaply (insurance float).
- His alpha is **statistically significant against standard factor models — and
  becomes INSIGNIFICANT once you control for Betting-Against-Beta (BAB) and
  Quality-Minus-Junk (QMJ).**
- Public stock picks outperform the wholly-owned businesses, so it is selection,
  not management influence.

Their own summary: *"neither luck nor magic, but reward for leveraging cheap,
safe, quality stocks."*

**Why this matters more than anything else in this document:** the single most
celebrated discretionary reasoning investor in history reduces to *leverage ×
cheap × safe × quality*. Those factors are computable from Compustat and CRSP —
**data already on this module's disk.** If the goal is "learn how the greats do
it and test it," this is the highest-evidence, lowest-cost test available, and it
is not another anomaly fish: it is a replication of the best-documented
outperformance record that exists.

### 2.3 Global macro (Soros / Druckenmiller) — the camp Murat's thesis belongs to

No comparable body of evidence supports it as a *replicable* method. The famous
records are concentrated, leveraged, discretionary, and largely pre-2008.
Discretionary macro as an industry has broadly disappointed since. I found no
peer-reviewed decomposition of Soros or Druckenmiller equivalent to Buffett's
Alpha. This does not prove the style doesn't work; it means there is no recipe to
copy, and the honest prior is low.

---

## 3. Murat's own example — the finding that actually changes the plan

His thesis: *"metal prices up → metal companies up; metal prices down →
manufacturers make things cheaper."*

The literature says the first half is roughly right, the second half is roughly
right, **and the net effect on equities flips sign with the business cycle.**

*Stock Market Predictability and Industrial Metal Returns* (and the four-century
commodity/stock work in Finance Research Letters):

- Industrial metals — copper, aluminium — **do predict aggregate stock returns**,
  in-sample AND out-of-sample, and the predictability "compares favorably with
  more established predictors."
- **The sign is regime-conditional:** rising metal prices are **good news in
  recessions and bad news in expansions.**
- Magnitude: a one-standard-deviation rise in industrial metal returns predicts
  roughly **−1.5% monthly** stock returns in expansions and **+0.5%** in
  recessions.

**Read that again.** In expansions, the naive causal chain "copper up → buy
equities" is not merely weak, it is **backwards, and the reversed effect is three
times larger than the recession effect.** A causal graph that encodes "copper up →
miners up" as a fixed edge would have lost money for most of the last 20 years.

This is simultaneously the best support for Murat's thesis and its sharpest
correction:
- **Support:** cause-and-effect linkages between commodities and equities are real
  and predictive — this is not folklore.
- **Correction:** the edges are *state-dependent*. Which is exactly what
  INSTR-REGIME-ANALOG's belief engine is built to represent, and exactly what a
  hand-drawn causal graph gets wrong. It also matches JM2's lesson (NEG_RESULTS
  §18): a fixed encoded story about an event fails out of sample.

---

## 4. News and LLMs — what is actually established

### 4.1 Horizon structure (directly relevant, because Murat wants mid/long-term)

- **Daily** news predicts returns for **1–2 days** only.
- **Weekly-aggregated** news predicts returns out to **one quarter.**
- Bloomberg news sentiment forecasts 7–14 day horizons; Twitter sentiment predicts
  only one day.
- **Asymmetry:** positive news is incorporated fast; **negative news has a long,
  delayed reaction.**

Two consequences. First, Murat's instinct to reject day-trading is *supported* —
aggregation over weeks is where the horizon extends. Second, the negative-news
asymmetry is the same shape as Lerman-Livnat's distress-8-K finding and this
program's own reframe of batch 10 into an exclusion screen. That convergence is
worth something.

### 4.2 LLM trading agents, long-horizon, out-of-sample: they fail

FINSABER (KDD 2026, `arXiv 2505.07078`): 2004–2024, 100+ symbols. Previously
reported LLM advantages **deteriorate significantly** under a broader cross-section
and longer evaluation. The failure has a diagnosable shape: **overly conservative
in bull markets** (underperforming buy-and-hold) and **overly aggressive in bear
markets** (heavy losses). Already banked as NEG_RESULTS §19.

### 4.3 The backtest-contamination problem is SOLVED, and the solution is free

He, Lv, Manela & Wu, *Chronologically Consistent Large Language Models*
(arXiv 2502.21206, 2025): **ChronoBERT and ChronoGPT** — models trained *only* on
text that existed at each point in time. Results:

- They match or beat standard BERT on NLP benchmarks despite the temporal
  constraint, and stay competitive with much larger open-weight models.
- In an asset-pricing task predicting next-day returns from financial news, their
  **real-time outputs achieve Sharpe ratios comparable to a much larger Llama
  model — indicating look-ahead bias is modest.**

There is now also a standardized benchmark (`Look-Ahead-Bench`) and an
instruction-tuned chronologically-consistent line (arXiv 2510.11677).

**This is the direct answer to Murat's insistence on backtesting a reasoning
engine.** A frozen-date replay driven by a chronologically consistent model is
methodologically legitimate in a way that a DeepSeek-or-GPT replay is not. And it
costs nothing but compute — these are open weights, not an API bill.

---

## 5. What this means for Aegis — honest assessment

**What survives from Murat's thesis:**

1. Causal commodity→equity links are real and predictive. ✅
2. Mid/long-horizon over day-trading is the right call for news. ✅
3. A reasoning layer that holds *state-dependent* beliefs beats a fixed rule. ✅ —
   and the program already built the skeleton (REGIME-ANALOG, 283 BeliefStates).
4. Backtesting a reasoning engine PIT is achievable. ✅ — via ChronoBERT/ChronoGPT,
   not via DeepSeek.
5. Narrowing to a small, well-understood universe. ✅ Consistent with the
   concentrated-manager evidence and with the turnover/cost law this program
   already proved the hard way.

**What does not survive:**

1. **LLM-as-return-predictor is closed** (NEG_RESULTS §19, FINSABER + the withdrawn
   Kim-Muhn-Nikolaev + Glasserman-Lin's own infeasibility admission). Nothing in
   the four responses is a receipt against that closure. The reviews proposing it
   are re-litigating a closed family without new evidence.
2. **Hand-drawn causal graphs are refuted by the very example used to motivate
   them** (§3, sign flip). Edges must be estimated and regime-conditional, not
   authored.
3. **"Obvious in hindsight" is not a signal.** Trump→defense, Iran→oil: these are
   testable *only* under frozen-date replay where the engine commits before the
   outcome. Until then they are stories.
4. **"Beat the S&P" remains a 94%-of-professionals-fail proposition**, and nothing
   here changes that base rate.

**What is genuinely new and gate-eligible** (per AI_PANEL_2026-07-28B S4, the
"genuinely new information source" exemption to the freeze): chronologically
consistent text embeddings and capital-flow data are *not* CRSP/Compustat
characteristic transformations. They qualify for the exemption. They do NOT bypass
prior_check, pre-registration, the explore/confirm wall, or deflation.

---

## 6. Concrete candidates, ranked by evidence-per-dollar

Ranked by *strength of external evidence × cheapness of test*. **None of these is
registered; all are post-freeze candidates requiring the full protocol.**

| # | Candidate | Evidence | Data cost | Notes |
|---|---|---|---|---|
| **1** | **Buffett's Alpha replication** — BAB × QMJ × leverage on the existing panel | Strongest in this document (FAJ 2018) | **$0** — Compustat + CRSP already on disk | Tests the single best-documented outperformance record. Not an anomaly fish. Note: leverage is the *active ingredient*, and this house does not lever — so the honest version is the unlevered quality/low-beta book, whose expected excess is correspondingly smaller. |
| **2** | **Regime-conditional commodity→equity link** | Direct, in- AND out-of-sample; sign flip documented | **$0** — FRED + existing macro panel | Fits REGIME-ANALOG exactly. Tests Murat's own thesis in its corrected (state-dependent) form. |
| **3** | **ChronoBERT PIT news replay** — frozen-date belief formation, weekly aggregation | Horizon evidence supports weekly→quarterly; ChronoBERT solves contamination | **$0** open weights; needs a PIT news archive — **this is the real constraint** | The honest version of Murat's "logic brain." Descriptive first, exactly like REGIME-ANALOG phase 1. |
| **4** | **Capital-flows family** (ETF flows, CFTC COT, issuance) | Adopted as design note in panel 28B with a PIT-feasibility gate | Mixed — COT free; dealer gamma vendor-locked | Already gated. |
| **5** | LLM exposure mapping (Gemini's "librarian" use — read 10-Ks to map supply-chain/commodity exposure) | No return claim; it is a *data construction* tool | DeepSeek key already held | Not a signal, so not a registration — it builds baskets a registered thesis then trades. |

---

## 7. The one thing that must be bought or built before #3 is possible

**A point-in-time news archive.** This is the actual blocker, and it always has
been — the program already established (round 9) that historical news backtests
"deliberately don't exist" here because there is no survivorship-clean free PIT
archive and GDELT is unstable.

ChronoBERT solves *model* contamination. It does **not** solve *corpus*
contamination: today's Yahoo/WSJ archive is a survivor's archive — dead companies'
coverage thins, URLs rot, and retrieval is filtered by what remained interesting.
Feeding a clean model a dirty corpus reproduces the same bias in a new place.

**This is a question for Murat, and it has a price tag** — see the message
accompanying this note.

---

## Sources

- [Buffett's Alpha — Frazzini, Kabiller, Pedersen (FAJ 2018 / NBER w19681)](https://www.nber.org/system/files/working_papers/w19681/w19681.pdf)
- [Buffett's Alpha — Financial Analysts Journal](https://rpc.cfainstitute.org/research/financial-analysts-journal/2018/faj-v74-n4-3)
- [Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis — Glasserman & Lin](https://arxiv.org/abs/2309.17322)
- [Chronologically Consistent Large Language Models — He, Lv, Manela, Wu](https://arxiv.org/abs/2502.21206)
- [Instruction Tuning Chronologically Consistent Language Models](https://arxiv.org/pdf/2510.11677)
- [Can LLM-based Financial Investing Strategies Outperform the Market in Long Run? (FINSABER, KDD 2026)](https://arxiv.org/abs/2505.07078)
- [FINSABER code and data](https://github.com/waylonli/FINSABER)
- [SPIVA U.S. Scorecard — S&P Dow Jones Indices](https://www.spglobal.com/spdji/en/spiva/article/spiva-us-year-end-2021)
- [Active Management's Persistent Failure: A 2025 Perspective (SPIVA 20-year figures)](https://www.wealthmanagement.com/investing-strategies/active-management-s-persistent-failure-a-2025-perspective)
- [Stock Market Predictability and Industrial Metal Returns](https://www.researchgate.net/publication/323462558_Stock_Market_Predictability_and_Industrial_Metal_Returns)
- [Stock return predictability over four centuries: The role of commodity returns](https://www.sciencedirect.com/science/article/pii/S1544612320307947)
- [The persistence of news sentiment: Implications for return predictability (Economics Letters 2026)](https://ideas.repec.org/a/eee/ecolet/v260y2026ics0165176525006408.html)
- [Sentiment, social media and meme stock return predictability](https://www.sciencedirect.com/org/science/article/abs/pii/S1940597926000049)
- [How Thomas Wehlen beat 98% of hedge funds over 27 years — Opalesque](https://www.opalesque.com/711731/How_Thomas_Wehlen_beat_of_hedge_funds173.html)
