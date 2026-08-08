# R2 — LLM Trading-Agent Memory & Reflection: What the Ablations Actually Show (deep-research receipt)

**Provenance:** produced 2026-08-08 by an autonomous Opus deep-research agent
(47 web fetches; every table quoted from the paper unless marked UNVERIFIED).
The agent's brief was explicitly adversarial: sharpen or CHALLENGE the
"never P&L-train" boundary. Archived verbatim as the receipt behind
`RESEARCH_SYNTHESIS_2026-08-08_R1-R4.md`. Not a registration.

---

## (a) Executive Summary

- **The rule survives contact with the literature, and got stronger — but the load-bearing reason is not the one we cited.** The strongest support is not "P&L reflection has been shown to destroy alpha"; it's that **the daily P&L signal is too noisy to carry weight updates**, and that the one memory design that explicitly *refuses to store resolved outcomes* beats Reflexion-style reflection memory by ~50% on Brier.

- **The "KTD-Fin" result is REAL and the number was cited correctly — but the mechanism was misattributed.** KTD-Fin (Zhu et al., arXiv:2605.28359, May 2026) finds **9 of 10 frontier LLM agents have negative Barra stock-selection alpha** (range −0.7% to −77.8%; only Claude Opus 4.7 at +0.2%). But **those agents do not self-train or reflect on their own P&L.** They are frontier LLMs making trades under a masking protocol. The paper says nothing about P&L-based reflection. **Stop citing KTD-Fin as evidence that P&L reflection causes negative alpha — it isn't.**

- **The single best direct receipt for the rule is ForecastCompass** (Chang et al., arXiv:2605.30858, May 2026): factor-centric memory that stores *calibration principles and factor failure modes* and explicitly **excludes resolved outcomes** achieves Brier 0.075–0.187 vs **Reflexion-style reflection memory at 0.150–0.252 — statistically indistinguishable from no memory at all (0.150–0.266)**. Reflection summaries added ~nothing; process/calibration memory halved the Brier.

- **Trade-R1** (Sun et al., arXiv:2601.03948, Jan 2026) makes the exact argument in print, in finance: outcome (P&L) rewards "conflate skill with luck"; process-level reasoning verification is proposed precisely because realized returns are too noisy to train on. The comparative *tables* could not be extracted — treat the direction as supported, the magnitude as UNVERIFIED.

- **The strongest counter-argument found is FinCon** (NeurIPS 2024). Its risk-control component critiques on **CVaR of realized daily P&L**, and ablating it is catastrophic: portfolio CR 113.8%→14.7%, SR 3.27→1.14; NIO 17.5%→**−52.9%**. This is the best published pro-P&L-feedback ablation in existence. Adjudicated below: it does *not* refute the rule — because it is an **exposure gate, not a belief update** — but the distinction must be held explicitly.

- **FinMem — the canonical layered-memory paper — already agrees.** Its memory-importance update is keyed on **prediction correctness against price ground-truth labels**, not on realized P&L. "Pivotal" events get +5 importance for correlating with actual price movement. The most-cited memory architecture in this space uses prediction resolution as its learning signal.

- **Nearly the entire LLM-trading literature is one 5-ticker, ~127-trading-day window.** FinMem, FinCon and TradingGroup all test TSLA/NFLX/AMZN/MSFT/COIN over roughly Oct 2022–Apr/Jun 2023. FinAgent uses 5 stocks + 1 crypto over ~150 days. TradingAgents uses **3 tickers over 63 days** and reports **Sharpe 8.21**. Every memory/reflection ablation number below sits on this sand.

- **When you widen the window, it all vanishes.** FINSABER (Li et al., arXiv:2505.07078, 2025): 2004–2024, 63–91 symbols — **FinMem Sharpe −0.228, FinAgent 0.241, buy-and-hold 0.703, p<0.001**. Neither agent produced significant alpha (all p>0.34). FinMem's commissions ran **5–9× FinAgent's** — value destroyed by turnover.

- **What correlates with failure is turnover and ticker-keyed retrieval, not model size.** KTD-Fin: ~100% turnover agents post −38% to −62% selection alpha; ~32% turnover agents post ~0%. Blinding tickers made the anchor agent stop trading entirely (0.00%, holds cash) — the ticker handle, not the data, was driving the trades. Model capability is *orthogonal*: frontier models span −0.2% to −77.8%.

- **Reflection without external ground truth is actively harmful, and this is well-established outside finance.** Huang et al. (ICLR 2024) — intrinsic self-correction degrades reasoning; prior gains were an oracle-label artifact. "Honest Lying" (Dixit et al., arXiv:2605.29463, May 2026) — under *binary* feedback, **0 of 121 reflections named the correct target**; 82% of WebShop environments had frozen (confabulated) memory vs 17% for HumanEval, where feedback is step-level. **Coarse feedback → confabulated memory. Daily P&L is coarse feedback.**

---

## (b) Per-Paper Sections

### 1. FinMem (Yu et al., AAAI-SS 2024; also IEEE Trans. Big Data 2025)
`arXiv:2311.13743` · https://arxiv.org/abs/2311.13743 · full text via https://ar5iv.labs.arxiv.org/html/2311.13743

**Setup:** 5 tickers (TSLA, NFLX, AMZN, MSFT, COIN). Test window **2022-10-06 → 2023-04-10** (~127 trading days).

**Main results (Table 2):**

| Ticker | FinMem CR% | Sharpe | MaxDD% | Best baseline |
|---|---|---|---|---|
| TSLA | 61.78 | 2.68 | 10.80 | DQN 33.34 |
| NFLX | 36.45 | 2.02 | 15.85 | B&H 35.51 |
| AMZN | 4.89 | 0.23 | 22.93 | B&H −10.77 |
| MSFT | 23.26 | 1.44 | 14.99 | DQN 14.74 |
| COIN | 34.98 | 0.72 | 35.75 | B&H −30.01 |

**Memory-span ablation (Table 5, top-K retrieved):**

| K | CR% | Sharpe | MaxDD% |
|---|---|---|---|
| 1 | 52.09 | 1.86 | 25.24 |
| 3 | **29.44** | 1.12 | 27.10 |
| 5 | 54.70 | 2.50 | 12.57 |
| 10 | **79.44** | 2.75 | 17.14 |

**The most important number in this section is not a finding — it is noise.** The response is non-monotonic and wildly so: K=3 is *worse than K=1*, K=10 is 2.7× K=3. A monotone cognitive-capacity mechanism cannot produce this. On a single ticker over 127 days, ±25pp swings are within sampling error. **Do not use "bigger memory span helps" as an established result — the paper's own table refutes a clean reading.**

**Risk-profile ablation (Table 4):** Risk-Seeking CR −19.41 / SR −0.79; Risk-Averse −12.47 / −1.58; Self-Adaptive **+54.70 / 2.50**. A *prompt persona* swings returns by 74pp on one ticker. Same critique.

**Backbone ablation (Table 3):** GPT-4 62.62%/2.23; GPT-4-Turbo 54.70%/2.50; GPT-3.5-Turbo 16.15%/2.16. Sharpe is nearly flat across a 4× return spread — the metric and the return disagree, another small-n tell.

**Memory retrieval design (verified):** score = recency + relevance + importance. Recency `e^(−δ/Q)` with **Q_shallow = 14d, Q_intermediate = 90d, Q_deep = 365d**. Relevance = cosine similarity between event embedding and query embedding. Importance decays by `α^δ` with α = 0.9 / 0.967 / 0.988 by layer.

**Learning signal — directly relevant:** FinMem reflects against **market ground labels (daily adjusted price differences)**, and an event "identified as pivotal for investment success receives an additional 5 points in its importance score." This is **prediction-resolution-keyed, not P&L-keyed.**

**Evidential weight: WEAK.** 5 tickers, 127 days, in-cutoff, no cost model. Demolished by FINSABER below.

---

### 2. FinAgent (Zhang et al., KDD 2024)
`arXiv:2402.18485` · https://arxiv.org/html/2402.18485v3 · https://dl.acm.org/doi/10.1145/3637528.3671801

**Setup:** AAPL, AMZN, GOOGL, MSFT, TSLA + ETHUSD. 2022-06-01→2024-01-01 (398 days total); **test 2023-06-01→2024-01-01 (~150 trading days for equities)**.

**Ablation (Table 5)** — M = market intelligence, L = low-level reflection, H = high-level reflection, T = tools:

| Config | TSLA ARR% | TSLA SR | ETHUSD ARR% | ETHUSD SR |
|---|---|---|---|---|
| M only | 39.01 | 0.90 | 16.21 | 0.63 |
| M+L | 57.16 | 1.02 | 52.33 | 1.34 |
| M+L+H | 89.25 | 1.46 | 54.80 | 1.40 |
| M+L+H+T | 92.27 | 2.01 | **43.08 (−21.4%)** | **1.18 (−16.1%)** |

**The reflection split is exactly our question, and the answer leans our way.** Verified from the paper:
- **Low-level reflection** consumes **price change direction and magnitude** ("connection between market intelligence, Kline chart and price changes") — a *prediction-resolution* signal.
- **High-level reflection** consumes **realized P&L of the agent's own trades** ("buy and sell points on a trading chart, coupled with a cumulative return plot", "successes and mistakes").

Marginal contribution: **L (prediction-resolution) = +46% ARR on TSLA and +101% on ETH — large and consistent. H (P&L) = +56% on TSLA but only +4.7% on ETH — large and inconsistent.** The prediction-keyed layer is the reliable one; the P&L-keyed layer is regime/asset-dependent. Directional receipt for the rule, but with n=2 assets it is **suggestive, not probative** — and adding L first means H is measured on an already-improved base.

**Also worth flagging:** the tool layer *hurt* crypto by 21%. Adding capability is not monotone.

**Evidential weight: WEAK-to-MODERATE.** Ablation only reported on 2 of 6 assets — the four missing assets are exactly where a sceptic would look.

---

### 3. TradingAgents (Xiao, Sun, Luo, Wang — AAAI 2025 oral)
`arXiv:2412.20138` · https://arxiv.org/abs/2412.20138v6

**Setup:** **AAPL, GOOGL, AMZN. 2024-01-01 → 2024-03-29. ~63 trading days.** The authors state they limited to 3 months "due to intensive LLM and tool use."

**Results (Table 1):** CR 26.62 / 24.36 / 23.21%; **Sharpe 8.21 / 6.39 / 5.60**; MDD 0.91 / 1.69 / 2.11%.

**A Sharpe of 8.21 over 63 days is not a finding, it is a diagnostic.** Under Lo (2002), the standard error on a Sharpe estimate from 63 daily observations is enormous; and the paper reports MDD under 1% on AAPL in a quarter where AAPL itself drew down materially.

**No ablation table exists in v6 isolating debate rounds, reflection, or memory.** The paper describes a "reflective agent" in the conclusion with no technical specification of what it reflects on. **The most-cited multi-agent-debate trading paper contains no component ablation.** "Debate helps" is not established.

**Independent replication (The Alpha Illusion, below): TradingAgents portfolio Sharpe 0.43 → 0.22 after commission, spread, market impact and token cost; +9.61% gross → +9.56% net vs buy-and-hold +9.61%. It exactly matched, then lost to, doing nothing.**

**Evidential weight: ANECDOTAL.** 63 days, 3 mega-caps, no ablation, no costs, in-cutoff.

---

### 4. FinCon (Yu et al., NeurIPS 2024) — **the strongest counter-argument**
`arXiv:2407.06567` · https://proceedings.neurips.cc/paper_files/paper/2024/hash/f7ae4fe91d96f50abc2211f09b6a7e49-Abstract-Conference.html

**Setup:** 8 single-stock tickers (TSLA, AMZN, NIO, MSFT, AAPL, GOOG, NFLX, COIN) + 2 portfolios. Train 2022-01-03→2022-10-04 (273d); **test 2022-10-05→2023-06-10 (249d)**.

**Ablation Table 4 — within-episode CVaR risk control:**

| Task | With CVaR | Without CVaR |
|---|---|---|
| GOOG | CR 25.08%, SR 1.052 | CR −1.46%, SR −0.006 |
| NIO | CR 17.46%, SR 0.335 | **CR −52.89%, SR −1.002** |
| Portfolio (TSLA/MSFT/PFE) | CR 113.84%, SR 3.269 | CR 14.70%, SR 1.142 |

**Ablation Table 5 — over-episode CVRF belief updates:**

| Task | With belief update | Without |
|---|---|---|
| GOOG | 25.08%, 1.052 | −11.94%, −0.496 |
| NIO | 17.46%, 0.335 | 8.20%, 0.156 |
| Portfolio | 113.84%, 3.269 | 28.43%, 1.181 |

**The trigger is explicitly P&L-derived:** CVaR is "the average of the worst-performing 1% of daily trading Profits and Losses (PnLs)", and the self-critique fires "when CVaR decreases or daily PnL turns negative."

**This is the paper that most directly threatens the rule.** The rebuttal, in three parts (judge whether it holds):

1. **It is a gate, not a gradient.** CVaR-of-P&L is used to *cut exposure and re-examine beliefs* when losses cluster in the tail. It is not gradient-descending stock-selection weights on daily return. The rule bans the latter. FinCon is evidence for a **P&L-triggered risk brake**, which the architecture arguably should have and which is orthogonal to the learning signal.
2. **The magnitudes are the exact ones Alpha Illusion flags as non-credible** — FinCon's per-ticker SR 2.37 and portfolio SR 3.269 are named in that critique as headline numbers that should not be read as deployment evidence.
3. **The test window (Oct 2022–Jun 2023) is inside GPT-4's training cutoff.** Li et al. quantify a **~71.85% drop in FinMem's return** when evaluation crosses the cutoff. FinCon has not been re-run post-cutoff.

**Evidential weight: MODERATE-but-contaminated.** Best-designed ablation in the set (8 tickers, 249 days, two separate ablation axes) — and simultaneously the one with the most implausible headline numbers.

---

### 5. TradingGroup (Tian, Salim, Xue — Aug 2025)
`arXiv:2508.17565` · https://arxiv.org/html/2508.17565v1

**Setup:** identical to FinMem — TSLA/NFLX/AMZN/MSFT/COIN, **2022-10-06→2023-04-10, 127 trading days**.

**Reflection design — uses BOTH signals, separated:** the Stock-Forecasting Agent reflects on **successful and failed prediction cases**; the Trading-Decision Agent labels the last 20 days of decisions with actual outcomes. Two explicit reward terms: `w_hit` (**prediction accuracy** weighted by confidence and return magnitude) and `reward_a` (**trading-action profitability** net of benchmark and costs). This is the closest thing in the literature to a system that runs the rule and its negation side by side — but it does **not** ablate the two against each other, which is the experiment the field needs and nobody has run.

**Ablation (Table 3), removing Self-Reflection + reranker:**

| Ticker | Ablated CR | Full CR |
|---|---|---|
| TSLA | 5.28% | 25.66% |
| **NFLX** | **53.24%** | **20.46%** |
| AMZN | 11.39% | 40.46% |
| MSFT | 17.54% | 20.27% |
| COIN | 50.71% | 70.60% |

**On 1 of 5 tickers, removing reflection more than doubled the return (NFLX 53.2% vs 20.5%).** A component that costs 33pp on 20% of a 5-name universe has not been shown to work; it has been shown to have high variance. *(Confidence MEDIUM — this table reading came via an extraction pass; re-check column orientation at source before quoting the NFLX reversal externally.)*

**Evidential weight: WEAK.** Same 127-day window as FinMem; ablation confounds reflection with a reranker change.

---

### 6. Reflexion (Shinn et al., NeurIPS 2023)
`arXiv:2303.11366` · https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html

**Where it works:** HumanEval 80%→91%; ALFWorld 130/134 tasks; HotPotQA CoT(GT) 61%→75%, with self-reflection worth **+8% absolute over plain episodic-memory replay** (Figure 4).

**Where it fails, and why it matters:**
- **WebShop: complete failure** — no improvement across four trials; "the agent does not generate helpful, intuitive self-reflections after failed attempts." WebShop is the environment with the largest search space and the sparsest signal — the one most like markets.
- **MBPP: 16% false-positive rate** on self-generated tests vs 1.4% on HumanEval — and Reflexion *underperforms* on MBPP as a direct result. **When the self-generated evaluator is wrong 16% of the time, reflection stops paying.**
- Authors' own caveat: verbal policy optimization "may still succumb to non-optimal local minima solutions."

**The structural point:** Reflexion's gains all come from environments with a **crisp, near-oracle evaluator** (unit tests, exact-match). Trading has no oracle at daily horizon — it has a realized return that is ~all noise. Reflexion is not evidence that reflection works in markets; it is evidence that reflection works *when you have a reliable grader*, which is an argument for grading predictions (where Brier is exactly computable) over grading trades (where skill and luck are inseparable).

**Evidential weight: STRONG (for its own domains), NON-TRANSFERABLE to trading.**

---

### 7. "Honest Lying: Memory Confabulation in Reflexive Agents" (Dixit, Kamal, Oates — arXiv:2605.29463, May 2026)
https://arxiv.org/html/2605.29463

The mechanism paper for *why* P&L reflection should fail. Reflexion-style agents under **binary** feedback "store confident but incorrect interpretations of the task and continue acting on them."

- ALFWorld frozen environments: **0 of 121 reflections mentioned the correct target object.**
- Frozen-memory rates by feedback granularity: **WebShop 82%, HotpotQA 46%, ALFWorld 32%, HumanEval 17%** — HumanEval has *step-level unit tests*, the others pass/fail.
- Spearman ρ between frozen-memory rate and trials-to-solve: **0.808, p<0.0001.**
- **Causal:** in 2 environments, the agent solved the task in 1 trial *with memory removed* but needed 7–8 trials with confabulated reflections. **Bad memory is worse than no memory.**
- Fix: replacing self-diagnosis with **programmatic feedback extraction** took correct-object mention from **0% → 86%** and frozen-memory rate 0.64 → 0.10.
- Capability is orthogonal: GPT-4o-mini eliminated confabulation entirely yet still solved only 2/16.

**Read-across:** daily P&L is the canonical coarse signal, delivered at trajectory level, with SNR far worse than ALFWorld's. Predicted failure mode: confidently-wrong stored beliefs that persist. The paper's prescribed fix — *extract the failure signal programmatically instead of asking the model to diagnose itself* — is precisely "resolve the claim, compute the Brier, write the number."

**Evidential weight: STRONG mechanism, ZERO financial data.** Use for the *why*, never as a finance receipt.

---

### 8. Huang et al., "LLMs Cannot Self-Correct Reasoning Yet" (ICLR 2024)
`arXiv:2310.01798` · https://arxiv.org/abs/2310.01798

Intrinsic self-correction — no external feedback — **degrades** performance on reasoning benchmarks. The methodological finding matters more than the numbers: prior self-correction gains were an artifact of **oracle labels used to decide when to stop correcting**.

**The exact failure shape to watch for in our own loop:** any reflection step allowed to see whether it was right *and* to decide whether to revise is running the oracle-label protocol. A pre-registered resolver that grades regardless of outcome is immune. *(Exact per-benchmark degradation numbers: UNVERIFIED — abstract only.)*

---

### 9. **The Alpha Illusion** (Ye et al., arXiv:2605.16895, May 2026)
https://arxiv.org/html/2605.16895v1

The single most useful paper for the §17-style honesty posture.

- **Friction:** across FinMem, TradingAgents, FinAgent, FinCon, QuantAgent, **35 of 40 friction components are unmodeled.**
- **Replication:** 1yr, 5-ticker EW portfolio (TSLA/NVDA/KO/XOM/MSTR). Buy-and-hold +9.61%. TradingAgents +9.61% gross → +9.56% net (Sharpe 0.43→0.22). QuantAgent −26.07% → −29.12% (Sharpe −0.96→−1.15). **Net results inferior to buy-and-hold on 54 of 55 tickers tested.**
- **Contamination:** citing Li et al. (2025) — FinMem return −71.85%, QuantAgent Sharpe −51.48% once evaluation crosses the training cutoff.
- **Power:** FinBen's GPT-4 FinTrade headline **Sharpe 1.51 ± 1.08** — the standard error exceeds half the mean. "Most published results sit within confidence intervals where between-system differences are statistically indistinguishable." *(The UNDERPOWERED finding, arrived at independently, in the LLM-agent literature.)*
- **Their prescription is our architecture.** Six protocols P1–P6, of which **P4 is "Epistemic calibration — measure Expected Calibration Error."** Their §5 recommends placing LLMs upstream as "auditable information interfaces" in a 6-stage pipeline with **independent probability calibration as a separate stage** and **final decision authority held by non-LLM modules**. That is "LLM narrates / engine computes" written by someone else.

**Evidential weight: STRONG.** Position paper with original replication; the replication is small (5 tickers, 1yr) but the friction accounting and the Lo-standard-error argument are analytic.

---

### 10. **KTD-Fin** (Zhu et al., arXiv:2605.28359, 27 May 2026) — *the paper we were citing*
https://arxiv.org/html/2605.28359v1 · Tsinghua / Stepfun / SJTU / Adelaide

**Setup:** 10 frontier LLM agents — Qwen3.6-Plus, GPT-5.5, Doubao-Seed-2.0, Claude-Opus-4.7, MiniMax-M2.7, Step-3.5-Flash, Gemini-3.1-Pro, DeepSeek-V4-Pro, GLM-5.1, Kimi-K2.6. **CSI300, 2024-01-01→2026-04-10, 548 trading days.**

**Barra selection alpha (Table 5):**

| Model | Selection α | Turnover |
|---|---|---|
| Claude Opus 4.7 | **+0.2%** | 31.75% |
| Qwen3.6-Plus | −0.7% | 31.88% |
| Doubao-Seed-2.0 | −4.7% | — |
| MiniMax-M2.7 | −7.4% | — |
| Step-3.5-Flash | −13.7% | — |
| GPT-5.5 | −14.9% | — |
| Gemini-3.1-Pro | −38.5% | 101.23% |
| DeepSeek-V4-Pro | −43.0% | 73.49% |
| GLM-5.1 | −61.9% | 100.25% |
| Kimi-K2.6 | −77.8% | — |

**9 of 10 negative. The number is right.**

**Masking ablation (Table 3, anchor model Step-3.5-Flash):**

| Mode | Bright (real tickers/dates) | Blinded |
|---|---|---|
| Memory-only | −0.16% | **0.00% (holds cash, zero trades)** |
| Open-research | −2.11% | −1.83% |

**The most important memory-design result in the survey.** With tickers visible and *no data channel at all*, the agent trades actively — pretraining memory of the ticker alone generates trades. Anonymize the ticker, hand it identical numbers, and it does nothing. Rationales shift from "Kweichow Moutai, liquor leader" to "20-day return +27.4%, low volatility 0.0255." **De-anonymization probe: joint ticker+date recovery only 1.5%** — the mask is real. Conclusion: **"the ticker handle, not the calendar handle, carries the dominant pretraining prior."**

**And the sting:** even under blinded factor-based reasoning, selection alpha stays negative for 9/10. Killing ticker-keyed retrieval **removes a contamination channel; it does not create skill.**

Stats: Wilcoxon signed-rank (α=0.05) for mask contrasts; multi-seed cells report medians with IQR. No per-agent t-stats.

**Evidential weight: STRONG** — 548 days, 300-name universe, leakage-controlled, attribution-aware, spans the models' post-cutoff period. Easily the best-designed study in this survey. **Caveat: CSI300 only; A-share microstructure and retail dominance may not generalize to US equities.**

---

### 11. FINSABER (Li, Kim, Cucuringu, Ma — arXiv:2505.07078, 2025)
https://arxiv.org/html/2505.07078v3

**The out-of-sample execution of the entire LLM-trading literature.** 2004–2024, 63–91 symbols, explicit survivorship / look-ahead / data-snooping controls.

| Selection | B&H Sharpe | FinMem | FinAgent |
|---|---|---|---|
| Volatility-effect | **0.703** | **−0.228** | 0.241 |
| Momentum composite | **0.384** | 0.025 | 0.104 |

p < 0.001 for B&H outperformance. **Neither agent produced statistically significant alpha (all p > 0.34).**

Diagnostics: "pathological miscalibration" — too conservative in bull markets (Sharpe −0.19 to 0.12), too aggressive in bear markets (−0.97 to −0.38). **FinMem's commission costs ran 5–9× FinAgent's** — the layered-memory agent overtraded itself into the ground.

**Evidential weight: STRONG.** 20 years, bias-controlled. The paper that turns FinMem's Table 2 into a 127-day artifact.

---

### 12. Trade-R1 (Sun et al., arXiv:2601.03948, Jan 2026)
https://arxiv.org/pdf/2601.03948

Our rule, published, in finance. Core argument: **outcome-based (realized P&L) rewards "conflate skill with luck"** — a well-reasoned position loses by chance, a bad one profits by chance; this signal-to-noise problem "prevents models from learning robust strategies when trained solely on realized returns." Remedy: process-level reasoning verification — score the intermediate logic independent of immediate outcome, "decoupling reward from stochastic returns."

Reported direction: process-reward beats outcome-reward on risk-adjusted return and consistency; outcome-reward exhibits "high variance, inconsistent strategies, and overfitting to lucky trades."

**Evidential weight: MODERATE, flagged — the comparative tables (Tables 5/12/14) did not extract from the PDF. The argument is verified; the magnitudes are UNVERIFIED.** Pull the numbers before citing as a receipt.

---

### 13. Agentic Trading survey (Xia et al., arXiv:2605.19337, May 2026)
https://arxiv.org/html/2605.19337v1

Audit of 77 studies (19 primary, screened 2022-01→2026-03). **The reporting numbers to quote whenever someone waves an LLM-trading paper:**

| Criterion | Primary studies passing |
|---|---|
| Time-consistent data splits | **2 / 19** |
| Explicit transaction-cost model | **1 / 19** |
| Universe / survivorship handling | **1 / 19** |
| Reproducibility tier R0 (no artifacts) | 15 / 19 |
| Reproducibility tier R3 (full replay) | **0 / 19** |

**"No included primary study reports systematic ablations isolating reflection benefit from confounding factors."** The honest state of the field on our exact question.

Two concepts worth stealing:
- **The Oracle Fallacy** — "an agent retrieves a similar past episode that contains a post-hoc narrative (e.g. *this trade failed due to news X released tomorrow*)." Episodic memory is a look-ahead vector.
- **Outcome Embargo** — episodes recorded at *t* must not expose outcomes until current time ≥ *t+k*, where *k* is the realization lag. **A concrete guard the claim ledger should implement explicitly** — the memory-side analogue of purge/embargo discipline.

Also notes Reflexion "assumes relatively prompt feedback," which is "in tension with trading settings where outcomes materialize only after meaningful market delay."

**Evidential weight: STRONG for the meta-claims; no new performance data.**

---

### 14. ForecastCompass / FoCo (Chang, Du, Cao, Chen, Lin — Penn State, arXiv:2605.30858, 29 May 2026)
https://arxiv.org/pdf/2605.30858

**The direct head-to-head on memory design for probabilistic forecasting**, scored by Brier and ECE.

| Memory design | Brier (range) | ECE (range) |
|---|---|---|
| **FoCo (factor-centric, adaptive)** | **0.075 – 0.187** | **0.077 – 0.195** |
| FoCo (static) | 0.083 – 0.243 | 0.089 – 0.237 |
| A-Mem | 0.109 – 0.269 | 0.092 – 0.287 |
| Graphiti | 0.134 – 0.275 | 0.097 – 0.301 |
| Mem0 | 0.149 – 0.272 | 0.101 – 0.296 |
| **Reflexion (reflection-summary)** | **0.150 – 0.252** | 0.086 – 0.266 |
| **Base (no memory)** | **0.150 – 0.266** | 0.106 – 0.299 |

**Reflection-summary memory ≈ no memory. Factor-centric memory ≈ 50–55% Brier improvement over base.**

**What FoCo writes is the punchline:** (i) *predictive-factor memory* — reusable signals, factor-specific failure modes, typical probability effects; (ii) *reasoning memory* — calibration principles (how to adjust confidence under uncertainty / conflicting evidence). And it **explicitly refuses to store "resolved outcomes, exact event dates, final rankings, entity-specific conclusions."**

Component ablation (FutureX, GPT-5-mini): full 0.187 Brier; w/o factor memory 0.207; w/o reasoning memory 0.205.

**Caveat, real: datasets are Prophet Arena (640 questions) and FutureX (242 questions) — general forecasting including a finance slice, NOT a stock-market backtest.** Strong result in an adjacent domain, not a trading result.

**Evidential weight: MODERATE-to-STRONG for the memory-design ranking; NOT a trading result.**

---

### 15. Verifiable Rewards for Calibrated Probabilistic Forecasting (Singh, Reddy, Chopra — arXiv:2607.00164, 30 Jun 2026)
https://arxiv.org/html/2607.00164

**The cleanest controlled experiment on "proper scoring rule reward vs outcome reward" found in any domain.** NFL in-game win probability, 2015–2024, 40,246 train / 5,241 selection / 5,185 test states; market odds as reference.

| Reward | Brier | ECE |
|---|---|---|
| Market benchmark | 0.136 | 0.027 |
| **Rate/proper-scoring reward** | **0.144** | **0.029** |
| Masked-CoT variant | 0.152 | 0.030 |
| **Outcome-based (binary realized outcome)** | **0.166** | **0.10** |

**ECE 0.029 vs 0.10 — a 3.4× calibration gap — and "the rate-based reward converges reliably within 50 training steps, whereas outcome rewards drift progressively."** The fix is exactly the noise problem: replace the noisy per-play realized outcome with a state-conditioned empirical rate, `r = 1 − (p − p̂(x))²`.

**Why this matters more than it looks:** NFL win probability has *far better* SNR than daily equity returns, and outcome-based training still drifted and produced 3.4× worse calibration. If outcome rewards fail there, they fail worse on daily P&L.

**Evidential weight: STRONG in-domain, ANALOGICAL to finance.** Authors do not claim finance transfer.

---

### 16. Others, briefly
- **FinBench** (Ghosh & Devarakonda, arXiv:2607.16229, Jun 2026): time-gated calibration benchmark for financial forecasting; strictly proper scoring rules; GPT-4o Brier 0.100 / BSS 0.598. **Pilot is 1 trading day, 3 tickers, 33 forecasts** — authors say it is "too small to draw claims." **ANECDOTAL.** Cite the *protocol*, never the numbers.
- **Toward Expert Investment Teams** (Miyazaki, Kawahara, Roberts, Zohren, arXiv:2602.23330, Feb 2026): TOPIX 100, Sep 2023–Nov 2025 (27mo), market-neutral, monthly rebalance, GPT-4o (cutoff Aug 2023 → **genuinely post-cutoff**). Fine-grained task decomposition worth **+0.08 to +0.26 Sharpe**. Leave-one-out ablations: technical agent critical (−0.4 to −0.66 Sharpe if removed); **removing the quantitative / qualitative / macro agents frequently IMPROVED results**; news agent mixed-to-negative. **MODERATE — one of the few post-cutoff, market-neutral, non-tiny designs. Message: "fewer agents, better-specified," not "more reflection."**
- **Profit Mirage** (Li, Zeng, Xing, Xu, Xu, arXiv:2510.07920, Oct 2025): leakage in LLM financial agents; direction clear, **numbers UNVERIFIED** (PDF did not extract).
- **LiveTradeBench** (Yu, Li, You, arXiv:2511.03628, Nov 2025): live crypto + prediction markets. **Numbers UNVERIFIED.** Flagged for follow-up — a live-market result would be the highest-value missing evidence.

---

## (c) The KTD-Fin Hunt: **FOUND — citation correction required**

**Result: the paper exists, the headline number is correct, the causal attribution in the internal citation is NOT supported by it.**

> **From Knowing to Doing: A Memory-Controlled Benchmark for LLM Trading Agents on Stock Markets.** Zhu et al., arXiv:2605.28359v1, 27 May 2026. Tsinghua University / Stepfun / FinStep / Shanghai Jiao Tong / Adelaide. https://arxiv.org/abs/2605.28359

**What matches the internal citation:** ten frontier LLM agents; **nine of ten have negative Barra stock-selection alpha** (−0.7% to −77.8%); only Claude Opus 4.7 non-negative at +0.2%.

**What does NOT match — and must be fixed:**

1. **The agents do not "self-train or reflect on their own P&L."** KTD-Fin evaluates frontier LLMs under a masking protocol in memory-only and open-research modes. There is **no P&L-based reflection or self-training loop** in the design. The paper does not discuss self-reflection at all.
2. **The finding is about leakage and attribution, not about learning signals.** The claim it supports: *LLM agents' apparent returns are passive market and style exposure; leakage-controlled stock-selection skill is absent.* Strong and useful — but a different claim.
3. **The universe is CSI300 (Chinese A-shares), 2024–2026.** Not US equities.

**Corrected internal citation:**
> "Under leakage-controlled Barra attribution, 9 of 10 frontier LLM trading agents show negative stock-selection alpha on CSI300 over 548 trading days (Zhu et al. 2026, arXiv:2605.28359). LLM agents' returns are passive market/style exposure. Note: these agents do not run P&L-reflection loops — this result establishes *absence of selection skill*, not *harm from P&L-based learning*."

**The argument actually wanted** — that P&L is the wrong daily learning signal — is better carried by **Trade-R1** (published version of the argument, in finance), **arXiv:2607.00164** (controlled outcome-vs-proper-scoring experiment, 3.4× ECE gap), **ForecastCompass** (calibration memory beats reflection memory ~2× on Brier), and **"Honest Lying"** (coarse feedback → confabulated memory, causally worse than no memory).

---

## (d) VERDICT

### The external evidence **SUPPORTS** the rule — with one required sharpening and one honest concession.

**Rule as stated:** *daily weight updates from prediction resolutions only, never from P&L.*

**Adjudication: SUPPORT (moderate-to-strong), conditional on adding an explicit carve-out for risk gating.**

**The supporting chain, ranked by strength:**

1. **The noise argument is decisive and now published in-domain.** Trade-R1 states it plainly: outcome rewards conflate skill with luck at daily horizon. arXiv:2607.00164 demonstrates it under controlled conditions in a domain with *better* SNR than equities — outcome reward gave Brier 0.166 / ECE 0.10 vs 0.144 / 0.029 for the proper-scoring-rule reward, and outcome reward **drifted progressively** while the rate-based reward converged in 50 steps. The MDE finding (72-month windows underpowered at ~0.6 ann. Sharpe) is the same phenomenon measured from the other end; the Alpha Illusion's Lo-standard-error argument (Sharpe 1.51 ± 1.08) is a third independent sighting.

2. **Coarse outcome feedback provably produces confabulated memory.** "Honest Lying": 0/121 reflections named the correct target under binary feedback; frozen-memory rate scales inversely with feedback granularity (17% with unit tests → 82% with pass/fail); ρ=0.808 with time-to-solve; and **removing memory outright beat confabulated memory in the causal ablation**. Daily P&L is the coarsest, noisiest possible grader. Prediction resolution with a deterministic resolver is the granular one.

3. **Where memory designs have been raced head-to-head on a proper scoring rule, calibration-keyed memory wins and reflection-summary memory does nothing.** ForecastCompass: FoCo 0.075–0.187 Brier vs Reflexion 0.150–0.252 vs no-memory 0.150–0.266. FoCo's design rule — *store factor failure modes and calibration principles, do not store resolved outcomes* — is a more specific prescription than the rule currently contains. **Consider adopting it.**

4. **Independent convergence on architecture.** Alpha Illusion §5 independently recommends LLMs upstream as auditable information interfaces, **independent probability calibration as its own stage**, and final decision authority with non-LLM modules — "LLM narrates / engine computes," arrived at by six authors across five institutions with no knowledge of this project.

5. **The canonical memory paper already does it this way.** FinMem's importance updates key on price-label correctness, not realized P&L.

**Required sharpening — restate the rule as two rules:**

> **(a) Learning signal:** daily posterior/weight updates come from *resolved prediction quality* (Brier, calibration, hit-rate vs pre-registered claim) — never from realized P&L.
> **(b) Risk gating:** realized P&L and drawdown/CVaR MAY trigger *exposure reduction, position-size caps, and lane suspension* — control actions that do not write to the belief store.

Without (b), the rule would forbid something that has the best published ablation in its favour (FinCon), and would leave the system without a loss brake. With (b), FinCon becomes evidence *for* the architecture rather than against it. **Enforce the separation mechanically: the risk gate must have no write path to the posterior store.** If P&L can reach the posteriors through a "risk belief," the banned thing has been reintroduced.

**Two additional guards the literature says are currently missing:**

- **Outcome Embargo on the claim ledger** (Xia et al. §Memory): an episode recorded at *t* must not expose its resolution to retrieval until current time ≥ *t+k*. Otherwise the ledger becomes a look-ahead vector — the Oracle Fallacy. The backtest harness has purge/embargo discipline; the gap is that the *memory retrieval path* likely lacks the same guard.
- **Retrieval must be keyed on market state / factor exposure, NOT on ticker.** KTD-Fin is unambiguous: the ticker handle carries the dominant pretraining prior; the anchor agent traded actively on ticker memory alone with zero data, and held cash at exactly 0.00% once blinded. Any per-ticker episodic retrieval will preferentially surface the model's pretraining narrative about that name. Key on regime/factor/state features and mask the identifier at retrieval time. **Honest note: blinding removes a contamination channel but does not manufacture alpha — 9/10 stayed negative even blinded.**

### The strongest counter-argument found

**FinCon (NeurIPS 2024).** A P&L-derived signal — CVaR of the worst 1% of daily P&L, triggering on "CVaR decreases or daily PnL turns negative" — drives a self-critique that updates *systematic investment beliefs*. Ablating the over-episode belief update costs: GOOG 25.1%→−11.9% (SR 1.05→−0.50), portfolio 113.8%→28.4% (SR 3.27→1.18). Ablating within-episode CVaR control costs NIO 17.5%→−52.9%. **A P&L signal writing into a belief store, and removing it is catastrophic, in the only ablation anyone has run on this exact question.**

**Why it does not overturn the rule (stated so it can be disagreed with):** the CVaR trigger is a *tail-loss detector* — a far better-conditioned statistic than mean daily P&L; it fires on clustered extreme losses (genuinely high SNR), not daily return sign. It functions as an exposure brake and a "re-examine your thesis" prompt, not a gradient on stock-selection beliefs. And the evidence is contaminated: 249 days, 8 tickers, entirely inside GPT-4's training cutoff, in a literature where the same window reverses sign under 20-year evaluation (FINSABER) and where the same authors' FinMem posts **Sharpe −0.228** out of sample.

**The honest residual:** nobody has run the decisive experiment. **No published study ablates prediction-resolution-keyed memory against P&L-keyed memory, holding everything else fixed.** TradingGroup implements both signals (`w_hit` and `reward_a`) and does not race them. On the specific comparison the rule adjudicates, the literature is **UNDERDETERMINED**; the rule is supported by convergent indirect evidence — noise arguments, cross-domain controlled experiments, mechanism papers, one adjacent-domain memory bakeoff — not by a direct in-domain test.

**That experiment is cheap to run here, and it would be novel.** Two arms on the existing claim ledger — posterior updated from Brier/resolution vs posterior updated from realized lane P&L — pre-registered, same claims, same resolver, same window. Given 0 of 19 primary studies reach reproducibility tier R3, a pre-registered version would be a genuinely publishable result and would settle D3 on receipts rather than on adjudication.

---

## (e) Confidence Notes

**VERIFIED by fetching the source (numbers quoted from the paper's own tables):** FinMem (main results, all three ablations, retrieval formula, decay constants, prediction-correctness learning signal); FinAgent (Table 5 ablation, reflection module descriptions); TradingAgents (Table 1, absence of any ablation table in v6); FinCon (Tables 4 & 5, CVaR definition); TradingGroup (mechanism, headline metrics); Reflexion (all numbers, limitations); Honest Lying (all statistics); Alpha Illusion (35/40 friction, replication, Sharpe 1.51±1.08, P1–P6); KTD-Fin (all ten alphas, Table 3 masking, turnover, 1.5% de-anon probe); FINSABER (Sharpe table, p-values, 5–9× commissions); ForecastCompass (Table 1, Table 3, memory-content policy); arXiv:2607.00164 (Brier/ECE table, convergence claim); FinBench; Toward Expert Investment Teams.

**UNVERIFIED (extraction failed or secondhand):**
- **Trade-R1 exact comparative numbers** — argument verified from the PDF, Tables 5/12/14 did not extract. **Do not quote magnitudes.** Highest-value follow-up.
- **Li et al. 2025** FinMem −71.85% / QuantAgent −51.48% post-cutoff — quoted *by* Alpha Illusion; primary source not reached.
- **Profit Mirage** (2510.07920) — direction only.
- **LiveTradeBench** (2511.03628) — nothing quantitative extracted.
- **Huang et al. (ICLR 2024)** per-benchmark degradation percentages — abstract verified, numbers not.

**MEDIUM confidence, flagged:**
- **TradingGroup's NFLX reversal** (ablated 53.24% vs full 20.46%) — re-check column orientation at source before external citation.
- **FinAgent test-window length** — reported as both ~150 and ~199 trading days across extraction passes (equity vs crypto calendar likely explains it).

**Scope limitations to carry:**
- KTD-Fin is CSI300 only; the ticker-prior finding may be stronger there.
- ForecastCompass and arXiv:2607.00164 are the two cleanest process-vs-outcome results and **neither is a stock-market backtest**. Both are analogical transfers — discount accordingly.
- **No study anywhere directly ablates prediction-resolution-keyed vs P&L-keyed memory in a trading agent.**
