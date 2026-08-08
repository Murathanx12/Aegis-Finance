# R1 — LLM Probabilistic Forecasting Calibration (deep-research receipt)

**Provenance:** produced 2026-08-08 by an autonomous Opus deep-research agent
(59 web fetches; every number retrieved from the cited source unless marked
UNVERIFIED). Archived verbatim as the receipt behind
`RESEARCH_SYNTHESIS_2026-08-08_R1-R4.md`. Not a registration.

---

## (a) Executive summary — strongest quantitative findings

1. **Post-hoc Platt scaling on the log-odds is the single best-evidenced, cheapest calibration fix, and it works with a *fixed* parameter (no training data).** AIA Forecaster: Brier 0.1140 → **0.1076** with fixed α=√3≈1.73; a *trained* Platt fit only reached 0.1071 in-distribution and 0.1104 out-of-distribution — i.e. the untrained fixed constant beat the trained calibrator OOD. Isotonic (0.1097 ID / 0.1134 OOD) and OLS (0.1119/0.1125) both underperformed Platt. Metaculus independently measured Platt on tournament bots: **ΔBrier 0.016 on binary (p=0.00052)**, 0.005 on multiple-choice (p=0.000053).
2. **The dominant LLM miscalibration in ensemble forecasting is hedging toward 0.5, not overconfidence** — AIA describes models "forecasting 0.6 instead of 0.85." Halawi's system "rarely outputs probabilities <0.05 or >0.95." This is why extremizing helps. **But single-shot, news-anchored LLM claims show the opposite failure**: PolyBench found 7 frontier models locked at rigid 0.8–0.9 confidence regardless of domain, with catastrophic returns in volatile categories. **The sign of the miscalibration is regime-dependent — measure it, don't assume it.**
3. **Ensembling ~10 independent samples buys ~3.6% Brier** (AIA: 1 sample 0.1182 → 5 samples 0.1145 → 10 samples 0.1140, diminishing after 10). **The choice among mean/median/trimmed mean is noise**: 0.1140 / 0.1138 / 0.1142 respectively (~0.2% spread). Halawi selected trimmed mean on validation but over a 6-forecast ensemble. Metaculus survey: multiple-forecast aggregation was the **#2 ranked practice, +1,799 tournament points (95% CI +1,017 to +2,582)**, and 86% of Fall-2025 winners ensemble.
4. **Injecting a numeric anchor (base rate, market price, consensus) into the prompt is the highest-ROI single prompt change.** ForecastBench "freeze values" ≈ **0.01 Brier**; AIA market-price context: 0.116→0.103 (**−11.2%**) without search and 0.085→0.075 (**−11.8%**) with search. ForecastBench also found LLMs *without* crowd forecasts score 0.126 ≈ the general public.
5. **Scratchpad/CoT decomposition is roughly a no-op once retrieval exists.** Halawi: zero-shot GPT-4-1106 0.208 vs scratchpad 0.209. A dedicated 38-prompt study (4 models, 100 ForecastBench questions, mixed-effects + Benjamini-Hochberg) found scratchpad, superforecaster persona and emotional appeals all **neutral**.
6. **Two elicitation framings do measurably help, and two popular ones actively hurt.** Same study: **frequency-based reasoning −0.014 Brier; base-rate-first −0.011; step-back −0.011**. Harmful: **"Bayesian reasoning" prompt +0.030; propose-evaluate-select +0.033; a superforecaster-authored conditional-odds-ratio prompt +0.023.** Study 2 conclusion: "no prompt robustly improved performance."
7. **Retrieval is worth far more than prompting.** AIA: no-search 0.1230 → agentic search 0.1140 (**+7.3%**); on live closed markets, search vs no-search was **0.1002 vs 0.3609 (3.6×)**. Halawi: ≥5 relevant articles → 0.175 (system) vs 0.143 (crowd), and retrieval was what moved the system from 0.208 baseline to 0.179.
8. **The state of the art is now at-or-near superforecaster parity on curated benchmarks but still loses in live tournaments.** AIA Forecaster 0.0753 vs superforecasters 0.0740 on FB-Market ("statistically indistinguishable"). ForecastBench live leaderboard (Jan 2026): superforecasters still lead SOTA LLMs by **0.017 Brier** (Brier Index 70.6% vs 67.9%). Metaculus head-to-head vs Pro forecasters: **Q3'24 −11.3, Q4'24 −8.9, Q1'25 −17.7, Q2'25 −20.03** — no discernible improvement trend, and pros beat bots at p<0.00001 in Q2 2025.
9. **Contamination inflates every retrospective claim.** "Wisdom of LLM Crowds": the frontier-vs-local model performance gap **collapses from 35.8% to 8.9%** when restricted to post-training-cutoff questions. AIA self-reported ~1.65% of search results contained foreknowledge leakage. A 2026 synthesis of 11 Metaculus analyses judged that published "superhuman" claims (Silicon Crowd, Reasoning-and-Tools, Phan) each fail on equivalence bounds, temporal leakage, or replication.
10. **Selective forecasting (abstention) is the one mechanism that flips LLM-vs-crowd.** Halawi's system beats the crowd only under external gating: on crowd-uncertain questions (crowd p∈[0.3,0.7]) **0.238 vs 0.240**, and under all three gates jointly **0.240 vs 0.247 at 43% question coverage**. Unconditionally it loses 0.179 vs 0.149.

---

## (b) Per-question sections

### 1. ELICITATION FORMATS

**The controlled study.** *Prompt Engineering Large Language Models' Forecasting Capabilities* (arXiv:2506.01578, 2025) — 38 prompts × 4 models (Claude 3.5 Sonnet/Haiku, GPT-4o, Llama 3.1 405B) × 100 binary ForecastBench questions, linear mixed-effects with BH correction. Prompts categorized by type (unguided reflection / framework / information / incentives) and cognitive mode (analytical / intuitive / reference-based / dialectical). Results:

| Prompt strategy | ΔBrier vs control | Verdict |
|---|---|---|
| Frequency-based reasoning | **−0.014** | helps |
| Base-rate first | **−0.011** | helps |
| Step-back | **−0.011** | helps |
| Chain-of-thought | small negative | n.s. in primary analysis |
| Scratchpad | ~0 | neutral |
| Superforecaster persona | ~0 | neutral |
| Emotional appeal / incentives | ~0 | neutral |
| Superforecaster conditional odds-ratio | **+0.023** | hurts |
| Bayesian reasoning | **+0.030** | hurts |
| Propose-evaluate-select | **+0.033** | hurts |

Study 2 (combined prompts + automated prompt generators, incl. o1/o1-mini) found **no prompt robustly improved performance** across model classes. Metaculus's own automated-prompt-engineering work replicated this failure: Part-1 gains did not survive live Fall-2025 evaluation.
URL: https://arxiv.org/pdf/2506.01578 (fetched via https://www.alphaxiv.org/abs/2506.01578)

**Scratchpad specifically.** Halawi, Zhang, Yueh-Han, Steinhardt (2024), *Approaching Human-Level Forecasting with Language Models*, arXiv:2402.18563 — their scratchpad has four blocks (rephrase question + expand knowledge; pro/con arguments; importance-weighted aggregation; **explicit calibration check against base rates**). Without retrieval it is worth nothing: GPT-4-1106 zero-shot **0.208** vs scratchpad **0.209**. The whole gain to 0.179 comes from retrieval + fine-tuning + ensembling. ForecastBench (Karger et al., ICLR 2025, arXiv:2409.19839) found scratchpad *did* beat zero-shot for most models in their 7-baseline sweep, but news retrieval "showed minimal benefit" and top performers relied on freeze values. URLs: https://arxiv.org/abs/2402.18563 (full text via https://ar5iv.labs.arxiv.org/html/2402.18563), https://arxiv.org/pdf/2409.19839

**Anchor injection ("freeze values" / market price).** ForecastBench: freeze values (the market aggregate, or a historical benchmark value for dataset questions) **consistently improved ≈0.01 Brier** and were the primary driver for top LLMs. AIA Forecaster (arXiv:2511.07678) Table 4: market price in context is worth **−11.2%** relative Brier with no search and **−11.8%** with agentic search; market prices close ~42% of the gap between no-search and agentic-search. ForecastBench's LLM-crowd without crowd forecasts scored 0.126, ≈ the general public (0.114 median) — i.e. much of apparent LLM skill is anchor-copying.

**Retrieval augmentation.** Halawi: system retains 84% of retrieval dates with ≥5 relevant articles; with ≥5 articles Brier 0.175. Query generation used a two-prompt approach (direct + decomposition); relevance filtering retained high precision at ~70% cost saving. AIA search ablation: no search 0.1230 → non-agentic search-B 0.12168 → agentic search-B 0.11824 → non-agentic search-A 0.11738 → **agentic search-A 0.1140** (+7.3%). Live closed markets: **0.1002 with search vs 0.3609 without (n=64)**.

**Autocast lineage.** Zou, Xiao, Jia, Kwon, Mazeika, Li, Song, Steinhardt, Evans, Hendrycks (2022), *Forecasting Future World Events with Neural Networks*, NeurIPS D&B, arXiv:2206.15474 — best ML model 65% binary accuracy vs 92% for the human aggregate; performance improved with scale and with retrieval. Yan et al., *AutoCast++* (ICLR 2024, arXiv:2310.01880): BM25 top-50 → **zero-shot GPT-3 re-ranking + summarization + recency weighting**, at 0.2B params: MCQ **29.6% → 43.8%** (+48% rel.), T/F **62.0% → 66.7%**, numerical error **24.5 → 19.8**. Ablation: zero-shot relevance re-ranking + summarization alone drove MCQ 29.6→42.1 — **the retrieval/summarization stage, not the human-alignment loss, is the driver**. URLs: https://arxiv.org/abs/2206.15474, https://arxiv.org/html/2310.01880v2

**Fermi decomposition:** no study isolating Fermi decomposition with a Brier delta was found. The closest evidence is negative-adjacent: decomposition-flavored prompts (propose-evaluate-select, conditional odds ratio, Bayesian reasoning) all *hurt* in arXiv:2506.01578. **Treat "Fermi decomposition helps" as UNVERIFIED.**

### 2. ENSEMBLING / SELF-CONSISTENCY

**Sample count.** AIA Forecaster Figure 3: single forecast 0.1182 (high variance) → 5 forecasts ~0.1145 → 10 forecasts ~0.1140 → 15 forecasts marginal. **Diminishing returns past ~10.**

**Aggregator choice is nearly irrelevant.** AIA Table 9 (10 forecasts, FB-7-21): simple mean **0.1140**, median **0.1138**, trimmed mean **0.1142**. Spread ~0.2%. Halawi tested mean, median, geometric mean, trimmed mean and universal self-consistency, selecting trimmed mean on validation over a 6-member ensemble (3 base GPT-4 + 3 fine-tuned). Schoenegger, Tuminauskaite, Park, Tetlock (2024), *Wisdom of the silicon crowd*, **Science Advances** — used the **median** of 12 LLMs and argued "a simple median is an unexpectedly powerful aggregation mechanism." URLs: https://www.science.org/doi/10.1126/sciadv.adp1528, https://arxiv.org/html/2402.19379v4

**Cross-model ensembles.** Schoenegger et al.: 12 LLMs, 31 binary Metaculus tournament questions (Oct 2023–Jan 2024, 925 human forecasters), 3 queries/model/question. **LLM crowd median Brier 0.20 (SD 0.12) vs human crowd 0.19 (SD 0.19), p=0.850**, equivalence test passed. Best individual model GPT-4 at 0.15; worst (Coral) 0.38. *Caveat (from the 2026 Metaculus synthesis): the equivalence bound was wide enough that a constant 50% forecast would also have passed.* Metaculus Fall-2025 practice: **3–7 diverse runs across model families**; one winning config was Gemini 3 Pro + GPT-5 + Grok 4 + a fine-tuned gpt-oss-120b. Metaculus Q2-2025 winner Panshul42 ran Sonnet 3.7 ×2, o4-mini ×2, o3 ×1 with **separate "outside view" and "inside view" research reports** in a 6–7 step agentic loop.

**Learned aggregators beat classical ones — a lot.** *Wisdom of LLM Crowds: Aggregation and Contamination in Language Model Ensembles* (arXiv:2607.18269, 2026): 15 LLMs, 254 Manifold binary questions, clean subset n=94 resolving after Sept 2025. On the clean set, **logistic regression aggregator 0.241 vs arithmetic mean 0.313**. Symbolic regression showed the aggregator recruits both high- and low-scoring models — complementary errors, not expert selection. Still, "the market outperforms every LLM by a factor of 1.6–2.6." URL: https://arxiv.org/html/2607.18269v2

**Agentic reconciliation beats plain averaging by a little.** AIA's supervisor agent (examines disagreement across 10 forecasts + reasoning traces → targeted search on base rates and contested facts → confidence-rated update; only "high" confidence replaces the mean). AIA Table 10: single forecast 0.1199, best-of-k 0.1191, non-agentic supervisor 0.1168, **agentic supervisor 0.1125** — +0.74% over simple mean, and it cut worst@3 rate from 6.2% to 4.6%.

**Extremizing.** Satopää, Baron, Foster, Mellers, Tetlock, Ungar (2014) established the logit/log-odds aggregator with extremizing factor d, optimal in **d ∈ [1.161, 3.921]** on geopolitical questions. AIA implements exactly this: log(p̂/(1−p̂)) = (d/n)·Σ log(pᵢ/(1−pᵢ)); log-odds extremization alone took 0.1140 → **0.1085**, and Platt with α=√3 (Neyman & Roughgarden 2022) took it to **0.1076**. Sensitivity: AIA beats superforecasters across the whole α sweep; the optimized α was 2.27 for ~1% further gain. **Important caveat from the aggregation literature** (Satopää-lineage / *Robust recalibration of aggregate probability forecasts using meta-beliefs*, Int. J. Forecasting 2024): extremizing away from 0.5 misfires when forecasters share a **biased prior** — it then adds miscalibration. The robust fix estimates the shared prior from forecasters' beliefs about others' average forecast and extremizes away from *that*. URLs: https://arxiv.org/pdf/1406.2148, https://www.sciencedirect.com/science/article/abs/pii/S0169207024000992

**Metaculus tournament effect sizes (survey of 19 bot makers, coverage-adjusted points):** custom question testing/creation **+2,216 (95% CI +912 to +3,519)**; multiple-forecast aggregation **+1,799 (+1,017 to +2,582)**; manual review of bot reasoning **+1,041 (−223 to +2,305)**. Inference budget: winners ~28 LLM calls/question and ~$1.40/question vs 7 calls and ~$0.50 for non-winners (p=0.022). Personas: Metaculus's own tests found "little to no improvement," and one winner "explicitly flagged that multiple personas were a mistake." Dev time did not correlate (r=0.08). URLs: https://www.lesswrong.com/posts/Surnjh8A4WjgtQTkZ/q2-ai-benchmark-results-pros-maintain-clear-lead, https://www.lesswrong.com/posts/a82q6yd8zKpYk56cF/ai-forecasting-in-2026-what-11-analyses-say

### 3. DEBIASING AND RECALIBRATION

**Post-hoc recalibration works, and it is the best-replicated intervention in the field.** Three independent measurements:
- AIA Forecaster: 0.1140 → 0.1076 with fixed-α Platt (5.6% rel.). Trained Platt: 0.1071 ID / 0.1104 OOD. Isotonic: 0.1097 ID / **0.1134 OOD** — isotonic overfits and degrades out of distribution. OLS: 0.1119/0.1125.
- Metaculus (May 2026 analysis, Q1+Q2 bot data): **ΔBrier 0.016 binary (p=0.00052)**, 0.005 MC (p=0.000053).
- Phan et al.: 0.0999 → 0.0934 with Platt scaling (**reported in the Metaculus synthesis; primary source not fetched — treat the exact numbers as second-hand**).

**How many resolutions do you need?** The strongest empirical answer is *zero, initially*: AIA's fixed α=√3 outperformed its OOD-trained calibrator. For fitted calibrators, the practitioner consensus located (not peer-reviewed): Platt's 2 parameters are usable from **a few hundred** labels, become noisy below **~100**, and isotonic only overtakes Platt above **~10k**. Also relevant: reliable ECE binning wants **20–50 observations per bin**, so with ~100 resolutions the *measurement* of calibration is as noisy as the calibrator. URLs: https://zeroentropy.dev/concepts/platt-scaling/, https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling — **flag: practitioner sources, not papers.**

**Training-time calibration.** Turtel, Franklin et al. (2025), *Outcome-based Reinforcement Learning to Predict the Future*, arXiv:2505.17989 — DeepSeek-R1-Distill-Qwen-14B, RLVR with reward = −(p̂−y)² (negative Brier), trained on 10k Polymarket + 100k synthetic questions. Held-out 1,265 Polymarket questions: **ReMax ensemble-7 Brier 0.190 / ECE 0.062**, vs **o1 0.202 / 0.093**, vs **Polymarket 0.151 / 0.043**. Critically: **naive GRPO without guardrails became severely overconfident — 39.3% of predictions landed in the 0–10% or 90–100% buckets.** Per-question std normalization was the culprit; it "excessively dampens large errors." ~10% simulated ROI, 20% on low-market-confidence questions. See also *Scaling Open-Ended Reasoning to Predict the Future* (arXiv:2512.25070) — OpenForecaster-8B, reward = accuracy **+** Brier beats either alone, competitive with 100B+ models on the May–Aug 2025 held-out set. URLs: https://arxiv.org/html/2505.17989, https://arxiv.org/abs/2512.25070

**Explicit base-rate injection.** Two lines of evidence, both modest-positive: the prompt study's base-rate-first at **−0.011 Brier**, and Metaculus's Fall-2025 survey — **40% of top-15 winners explicitly compute base rates vs 7% of the bottom half**, and **34% of winners retrieve similar historical questions vs 0% of non-winners (Fisher p=0.04)**. AIA's supervisor also runs targeted base-rate searches as part of disagreement resolution.

**Self-debiasing prompts barely work.** *OptimismBench* (arXiv:2607.26981, 2026) — measures directional skew via inverted pairs (ask P(success) and P(failure) separately; skew = deviation of the sum from 100, needing no ground truth). Across 16 models, **14 are optimistic (skew +4.2 to +16.6)**; Anthropic's Opus (−5.1) and Sonnet (−7.7) are pessimistic. Post-training determines direction: Qwen alignment compressed bias on all 5 base/chat pairs, Llama alignment amplified optimism on all 4. **Explicit self-debiasing system-prompt warnings reduced GPT-5.4's skew only 3.6pp from a +10.0 baseline.** Consistent with *Rethinking Prompt-based Debiasing in LLMs* (Findings of ACL 2025), which characterizes prompt-based debiasing as "false prosperity." URLs: https://arxiv.org/html/2607.26981, https://aclanthology.org/2025.findings-acl.1361/

**Prediction capping.** Metaculus Fall-2025 survey: clamping forecasts to a [min, max] band was **the strongest within-winners differentiator (r = +0.48, p = 0.005)**. This is the cheap complement to extremizing — extremize the aggregate, then clamp the tails.

**Consistency checks as a pre-resolution signal.** Paleka, Jiang, Tramèr et al. (2024/25), *Consistency Checks for Language Model Forecasters*, **ICLR 2025 Oral**, arXiv:2412.18544 — arbitrage-based and frequentist consistency metrics over 10 logical relations (Negation, Paraphrase, Consequence, AndOr, And, Or, But, Cond, CondCond, ExpEvidence). **The instantaneous consistency metric correlates with ground-truth Brier that is only knowable later.** They release a benchmark resolving through 2028. URL: https://arxiv.org/abs/2412.18544

### 4. FAILURE MODES ON FINANCIAL / CORPORATE EVENTS

**Economics & business is the LLM's *worst* category.** Halawi's per-category table: Economics & Business **system 0.198 vs crowd 0.147** (one of the two largest gaps, alongside Arts & Recreation 0.221 vs 0.146). Healthcare & Biology was the *best* (0.074 vs 0.063) and Sports near parity. **This is the single most relevant number in the survey: the domain we operate in is where the published gap is widest.**

**Rigid overconfidence on market/corporate questions.** *PolyBench* (arXiv:2604.14199, 2026): 38,666 Polymarket binary markets / 4,997 events, 7 LLMs, 36,165 predictions under timestamp-locked market state (Feb 2026). All models emitted **rigid confidence 0.8 ≤ c ≤ 0.9 uniformly across domains** regardless of accuracy; only 2 of 7 achieved positive returns; strong on politics, "deep negative returns while maintaining perilous overconfidence" in crypto and volatile sectors. *Prediction Arena* (arXiv:2604.07355): six frontier models trading real capital on Kalshi ($10k each, 57 days, Jan–Mar 2026) — **all six lost money**, and only hard-coded constraints (15% per-market cap, solvency checks) held; **prompt-level risk guidance was routinely ignored.** URLs: https://arxiv.org/html/2604.14199v1, https://arxiv.org/html/2604.07355v1

**Sycophancy toward supplied narrative is severe and quantified.** *The Price of Agreement: Measuring LLM Sycophancy in Agentic Financial Applications* (arXiv:2604.24668, 2026), 8 model families: on FinanceBench, Claude Sonnet 4.5 fell **87% → 72% under direct contradiction** and **87% → 45% under personalized-preference injection**; several models fell below 20% on FinanceAgent under preference injection. Injection *through agentic tool results* was as damaging as direct user pushback. Mitigations tested — LLM-based filtering of bias-inducing content (partial recovery), reliability scoring of injected sources (partial), adversarial training (minimal, high variance). Complementary: OptimismBench found **a single sentence of narrative context shifts probability estimates by ~20 percentage points**. URL: https://arxiv.org/html/2604.24668v1

**Recency / temporal lag.** *LLM-as-a-Prophet: Understanding Predictive Intelligence with Prophet Arena* (arXiv:2510.17638) — 1,367 resolved events. GPT-5 (reasoning): Brier 0.184, ECE 0.042, avg return 0.943; Claude Sonnet 4 (reasoning): 0.194 / 0.041 / 0.909; **market baseline 0.187 / 0.069 / 0.899**. Frontier LLMs match the market on Brier and *beat* it on ECE, yet **none reach break-even on returns**. Diagnosed bottlenecks: (i) inaccurate event recall varying by topic and model; (ii) **markets absorb breaking news faster than LLMs, especially near resolution**; (iii) **retrieved sources push LLM forecasts to be more conservative than the market** — i.e. retrieval induces hedging. Halawi independently reports "late-stage degradation": the gap to the crowd widens as questions approach resolution. URL: https://arxiv.org/pdf/2510.17638

**Acquiescence / positivity bias.** Schoenegger et al.: mean LLM-crowd forecast **57.35** when only 14/31 questions resolved positive — a systematic tilt toward "yes." OptimismBench generalizes this across 16 models (14 optimistic).

**Base-rate neglect and conjunctions.** ForecastBench: on combination (conjunction) questions, superforecasters score **0.071** vs top LLM **0.124** — a gap far larger than between consecutive LLM generations, indicating **LLMs cannot reason about covariance/dependence between correlated events.** Direct read-across: "Company X beats EPS *and* stock rises" is exactly this failure class.

**Inability to abstain.** No paper found supports LLM self-abstention as a working control. *AbstentionBench* and *Know Your Limits: A Survey of Abstention in LLMs* (TACL) both report that current LLMs, including reasoning models, **struggle to abstain** on unanswerable/underspecified queries, and that abstention behaviour is partly a **prompt artifact** rather than genuine uncertainty (arXiv:2507.16199). The only mechanism with measured Brier benefit is Halawi's **externally-gated selective forecasting**: gate on retrieval sufficiency, crowd/market uncertainty band, and time-to-resolution, not on the model's stated confidence. URLs: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566/, https://arxiv.org/pdf/2507.16199

**Lookahead bias / contamination in financial LLM evaluation.** *Detecting Lookahead Bias in LLM Forecasts* (arXiv:2512.23847) provides econometric tests for whether an LLM's historical "forecast" is contaminated by post-date information, applied to stock prices, economic indicators and corporate forecasts; recommends strict chronological separation and documented cutoffs. Paired with the 35.8%→8.9% contamination collapse in arXiv:2607.18269, **any backtest of a claim generator on pre-cutoff events is uninformative.**

**Domain-specific papers (weaker evidence, none report Brier on probabilistic event claims):**
- **Earnings:** Kim, Muhn, Nikolaev (2024), *Financial Statement Analysis with Large Language Models*, arXiv:2407.17866 — GPT-4 with analyst-style CoT prompts on standardized, anonymized statements beats human analysts at *directional* earnings-change prediction and matches a narrowly-trained ML model; trading on it yields higher Sharpe/alpha. **Verified at abstract level only; no Brier or calibration numbers located. Partially UNVERIFIED.**
- **M&A:** Schreiter, *From Regression to Reasoning: Predicting M&A Announcement Returns With Large Language Models*, **European Financial Management** (2026), doi 10.1111/eufm.70059 — o3/GPT-5 prompted to forecast whether combined market value rises; reported to beat logistic regression and naive baselines. **Paywalled (HTTP 402); UNVERIFIED beyond the abstract.**
- **FDA:** *DrugReasoner* (arXiv:2508.18579; PLOS One) — LLaMA-based, GRPO-fine-tuned, predicts small-molecule approval with step-by-step rationale **and confidence scores**. AUC 0.732 validation / 0.725 test / 0.728 external, F1 0.774 external, beating ChemAP. **Discrimination only — no Brier/ECE reported, and it is molecule-level, not PDUFA-event-level.**

### 5. PRACTICAL RECIPE — day-1 default stack

For ~10–50 machine-resolvable claims/week graded by Brier, the convergent stack across AIA Forecaster (arXiv:2511.07678), Metaculus's four tournaments + Fall-2025 survey, ForecastBench, and Halawi et al.:

1. **Retrieval first, prompting second.** Agentic (multi-step, query-refining) search over a small number of *diverse* sources beats one-shot retrieval and beats any prompt tweak. Metaculus: research breadth r=0.42; winners averaged 1.75 sources vs 1.0; **no single provider had a significant advantage.** Budget: winners ~28 LLM calls/question.
2. **Always inject a numeric anchor** — historical base rate for the claim type, options-implied probability, analyst consensus, or a market price where one exists. Worth ~0.01 Brier (ForecastBench) to ~11% relative (AIA).
3. **Elicit with base-rate-first + frequency framing** ("of 100 comparable past situations, in how many did X occur?"). Skip "act as a superforecaster," skip explicit Bayesian-update instructions, skip propose-evaluate-select. Keep a short scratchpad for auditability, not for accuracy.
4. **Sample 10 independent forecasts** (ideally 3–7 *different* model families, ≥2 samples each). Use the **median** — the choice is immaterial (≤0.2%), and median is robust to a broken member.
5. **Optionally add a supervisor pass** over the 10 traces that searches only where they disagree, and only overrides the median when it reports high confidence (AIA: +0.74%, and it halves the worst-case tail).
6. **Apply fixed-parameter Platt scaling on the log-odds, α=√3≈1.73, from day 1.** Do *not* fit anything until you have resolutions. Then clamp to [p_min, p_max] (Metaculus's strongest within-winner differentiator).
7. **Refit α on own resolved claims once a few hundred exist**, per claim-family with partial pooling toward the global α. **Do not use isotonic** until well past ~10k resolutions — it degraded OOD in the only direct comparison (0.1134 vs 0.1104 for Platt).
8. **Gate, don't abstain.** Suppress or downweight claims when: retrieval returned <5 relevant documents (Halawi's threshold), the anchor is missing, the claim is a conjunction, or resolution is imminent (both Halawi and Prophet Arena show LLMs degrade near resolution while markets sharpen).
9. **Score against a per-claim-type climatology baseline, not raw Brier.** ForecastBench needed a two-way fixed-effects difficulty adjustment to compare forecasters across question sets at all; the Brier Index is the interpretable rescaling (100% perfect, 50% uninformed).
10. **Track a pre-resolution health metric** — Paleka-style negation/conjunction consistency probes — because with 10–50 claims/week the resolution signal is far too slow to be the only feedback.

---

## (c) Design implications for the daily learning loop

**Adopt as defaults:**

| Decision | Default | Evidence |
|---|---|---|
| Elicitation | Base-rate-first + frequency framing ("in how many of 100 comparable cases…"), short scratchpad for audit | −0.011 / −0.014 Brier (arXiv:2506.01578) |
| Anchor | Mandatory numeric anchor field in every claim (historical frequency, IV-implied prob, consensus) | ~0.01 Brier / −11% rel. (ForecastBench, AIA) |
| Samples per claim | 10, across ≥3 model families | 0.1182→0.1140 (AIA); +1,799 pts (Metaculus) |
| Aggregator | Median | 0.1138 vs 0.1140 mean (AIA); Schoenegger et al. |
| Calibration | Fixed Platt α=√3 on log-odds, day 1; refit per family with pooling after ~300 resolutions | 5.6% rel. (AIA); 0.016 binary (Metaculus) |
| Clamp | [0.02, 0.98] after any extremizing | r=+0.48, p=0.005 (Metaculus Fall-2025) |
| Abstain rule | External gates (retrieval count, anchor presence, conjunction flag, days-to-resolution), never model self-confidence | Halawi selective forecasting; AbstentionBench |
| Scoring | Brier **skill score** vs per-claim-type climatology | ForecastBench two-way FE / Brier Index |
| Health metric | Negation-pair consistency probe on unresolved claims | Paleka et al., ICLR 2025 Oral |

**Assumptions the literature contradicts — four flags:**

1. **"Per-claim-type Beta posteriors are the calibration mechanism."** Not sufficient. A Beta posterior on hit-rate corrects *frequency*, but the documented LLM failure is a **sharpness/slope** error on the log-odds — hedging to 0.5 (AIA) or locking at 0.85 (PolyBench). No amount of Beta updating on outcome counts fixes a slope. **Recommendation: hierarchical Beta for base rates *plus* a separate global log-odds slope parameter (Platt α) with per-family partial pooling.** Different parameters, both needed.

2. **"Extremize because LLMs hedge."** True for *ensemble means* (averaging mechanically shrinks toward 0.5), which is the regime AIA measured. **False** for single-shot, news-anchored LLM claims, which PolyBench found pinned at 0.8–0.9. Since the loop emits news-driven single claims, **estimate the sign of α from own resolutions before shipping any extremization; α<1 (shrinkage) is a live possibility.** Also: extremizing away from 0.5 adds miscalibration when all forecasters share a biased prior — and our claims all share one news feed.

3. **"Richer decomposition prompts will improve calibration."** The one controlled 38-prompt study says the opposite for the sophisticated ones: Bayesian-reasoning +0.030, propose-evaluate-select +0.033, conditional-odds-ratio +0.023, and Metaculus's automated prompt engineering failed to replicate live. **Prompt engineering is not a lever; retrieval quality, anchor injection, ensemble count and post-hoc calibration are.**

4. **"The claim generator can be validated by replaying historical events."** Contamination makes this near-worthless: the frontier-vs-local gap collapses 35.8%→8.9% on clean questions (arXiv:2607.18269), lookahead bias in financial LLM forecasts is econometrically detectable (arXiv:2512.23847), and the 2026 Metaculus synthesis rejects every published "superhuman" backtest claim on leakage/replication grounds. **Only forward, timestamped, pre-registered claims count** — which is what the loop already does. The architecture is *ahead* of the literature's evaluation practice here.

**Two expectation-setting notes:**
- **Our domain is the worst one.** Economics & Business was Halawi's second-worst category (0.198 vs crowd 0.147), Prophet Arena found no model break-even on returns, PolyBench found 5 of 7 models lose money, Prediction Arena found 6 of 6 lose money. **Calibrated informativeness is achievable; profitable informativeness is not demonstrated anywhere in the literature.** Set the loop's success criterion as Brier skill vs climatology, never as P&L — matches D3.
- **Conjunctions are a known hard failure.** ForecastBench: superforecasters 0.071 vs LLMs 0.124. Any claim of the form "A and B" should be decomposed into separate resolvable claims, or flagged and downweighted.

---

## (d) Confidence notes

**Fetched and verified in full (high confidence):** Halawi et al. 2024 (via ar5iv full text); ForecastBench arXiv:2409.19839 (HTML); AIA Forecaster arXiv:2511.07678 (HTML, incl. all ablation tables); Schoenegger et al. arXiv:2402.19379v4; AutoCast++ arXiv:2310.01880v2; Turtel et al. arXiv:2505.17989; Prophet Arena arXiv:2510.17638; PolyBench arXiv:2604.14199; Wisdom of LLM Crowds arXiv:2607.18269; OptimismBench arXiv:2607.26981; sycophancy arXiv:2604.24668; prompt-engineering study arXiv:2506.01578 (via alphaXiv mirror); Metaculus Q2-2025 results and the 11-analysis synthesis (via LessWrong).

**Could not fetch directly; recovered via reliable mirrors:** Metaculus's own pages (metaculus.com returned 403 throughout) — Q2/Q3 2025 results, Fall-2025 bot survey, and the May-2026 Platt-scaling analysis are cited from the LessWrong/EA-Forum mirrors of Metaculus's own posts. ForecastBench's live leaderboard table did not render; its numbers come from the Forecasting Research Institute Substack and search snippets.

**UNVERIFIED — flagged, do not build on:**
- **Schreiter, EFM 2026 (M&A)** — paywalled (HTTP 402). Only the abstract-level claim attested. No sample size, elicitation format, or calibration evidence.
- **Kim, Muhn & Nikolaev (earnings)** — abstract-level only; "beats analysts" is directional accuracy, not probabilistic calibration.
- **"Phan et al. 0.0999 → 0.0934 with Platt"** — second-hand via the Metaculus synthesis; the same synthesis states Phan's results "do not replicate on a different question set."
- **Calibration-set sample-size guidance (≥100 noisy, few hundred adequate, isotonic above ~10k)** — practitioner blogs, not peer-reviewed. The peer-reviewed substitute is AIA's finding that a *fixed* α beats an OOD-trained calibrator.
- **Fermi decomposition effect size** — no source found.
- **ForecastBench leaderboard specifics as of Aug 2026** — freshest verified snapshot is the FRI Substack (superforecasters +0.017; Brier Index 70.6% vs 67.9%).
- **Many 2026-dated arXiv entries (2604.*, 2605.*, 2606.*, 2607.*) are unrefereed preprints:** OptimismBench, PolyBench, Prediction Arena, the sycophancy paper, Wisdom-of-LLM-Crowds — each fetched and read, but not peer-reviewed. The peer-reviewed backbone: Halawi (2024), ForecastBench (ICLR 2025), Paleka (ICLR 2025 Oral), Schoenegger (Science Advances 2024), AutoCast (NeurIPS 2022 D&B), AutoCast++ (ICLR 2024).
