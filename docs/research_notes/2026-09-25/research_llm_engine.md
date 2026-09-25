# LLM-as-forecaster vs LLM-as-extractor for equity returns — literature check (2026-09-25)

Context this was run against: DeepSeek-only system (`deepseek-chat`, sometimes reports as
`deepseek-flash`) + local Qwen3-30B-A3B via llama-server, a deterministic LightGBM-style
cross-sectional ranker, a forecast ledger (~25k frozen, ~17k graded), and one measured
in-house result: a structured "investigator" evidence-packet process scores **+8.97%
Brier skill OOS** at h=1 day, held out, while nine thematic "persona" prompts score
**-27.98% skill at optimal weight ZERO** (anti-signal). Evidence strength tags:
**[STRONG]** = peer-reviewed / large-N / replicated, **[MODERATE]** = single paper,
plausible method, not yet replicated, **[WEAK]** = preprint, small-N, or contested,
**[CONTESTED]** = literature actively disagrees.

---

## Q1. LLMs as forecasters vs as evidence extractors

### The foundational claim and its erosion
- Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?" (arXiv:2304.07619,
  published version *Review of Financial Studies* / SSRN 4412788) reported GPT-4 scores
  from news headlines predict next-day return direction, with the effect concentrated in
  **small stocks and negative news**, and ~90% hit rate on the *contemporaneous* (already
  priced) reaction rather than the tradable drift. **[STRONG]** as a documented
  contemporaneous-sentiment-extraction result; **[CONTESTED]** as a forecasting result,
  because:
  - Lopez-Lira, Tang & Zhu (2025) and Sarkar & Vafa (2024) themselves flag that **any**
    such study must use a sample strictly after the model's knowledge cutoff or the
    result conflates prediction with memorization. [MODERATE/STRONG — flagged by the
    original authors]
  - "Detecting Lookahead Bias in LLM Forecasts" (arXiv 2512.23847, late 2025) is a direct
    methodological rebuttal genre — the field now treats look-ahead/memorization as the
    default null hypothesis for any LLM stock-forecast paper, not an edge case.
  - **"Profit Mirage: Revisiting Information Leakage in LLM-based Financial Agents"**
    (arXiv:2510.07920, Oct 2025) is the most quantified version of this critique: it
    names the mechanism "pre-training contamination" (LLMs memorize historical price
    moves and post-hoc narratives rather than learning causal drivers) and introduces
    FinLake-Bench to measure it directly. **[STRONG — this is exactly the failure mode
    your persona arms are suspected of falling into.]**
  - **"The Alpha Illusion: Reported Alpha from LLM Trading Agents Should Not Be Treated
    as Deployment Evidence"** (arXiv 2605.16895) is the single most load-bearing paper
    for this system's architecture. Key numbers: testing FinMem and QuantAgent **outside**
    their pretraining cutoff dropped total return by **≈71.85%** and Sharpe by **≈51.48%**
    — i.e. most of the "alpha" in the original papers was memorized history. Reproducing
    TradingAgents and QuantAgent with realistic costs (commissions, spread, market impact,
    token cost) fell further: TradingAgents Sharpe **0.43 → 0.22**, QuantAgent
    **-0.96 → -1.15**, both below buy-and-hold. It explicitly recommends the architecture
    this system already uses: LLM restricted to Stage 1, "extracting structured
    information from news/filings" as an **auditable information interface**, with
    calibration, risk control and execution kept in a separate, non-LLM pipeline — because
    "language confidence isn't calibrated probability, narrative reasoning doesn't equal
    numerical execution." **[STRONG, and directly on-point.]**

### Benchmarks of end-to-end LLM trading agents
- **StockBench** (arXiv 2510.02209 / OpenReview 9tFRj7cmrS, 2025): contamination-controlled
  (forward window Mar–Jun 2025, post-cutoff), 20 DJIA names, OHLCV + fundamentals + up to
  5 recent news items/stock. Finding: **model rankings flip between downturn (Jan–Apr 2025)
  and upturn (May–Aug 2025) regimes**, and LLM agents generally fail to beat passive
  buy-and-hold in downturns. **[MODERATE]** — one benchmark, but methodologically the
  cleanest (contamination-aware) of the trading-agent evals found.
- **Vals AI Finance Agent Benchmark** (arXiv 2508.00828, 537 expert-authored questions
  over real SEC filings, 9 task categories): **no model exceeds 50% accuracy**; best
  (Claude Opus 4.1 Thinking) still <50%; strong log-relationship between accuracy and
  inference cost with sharp diminishing returns past ~$1/question. This benchmark is
  about *analysis/retrieval* tasks, not price forecasting, but it bounds how much to trust
  LLM "reasoning" outputs generally. **[STRONG, large-N, but off-target for return
  forecasting specifically.]**
- **SoK: "Trading Agents or Market Crashers?"** (arXiv 2609.19705, FARSIGHT framework):
  ran 15 academic LLM trading schemes through robustness (flash-crash-like stress) and
  security tests. **80% failed at least one core robustness metric; 100% had security
  vulnerabilities** (prompt/tool/memory injection, no isolation). Also notes the field has
  "essentially no stop-loss enforcement" and decision latencies **>240s** for TradingAgents
  — orders of magnitude too slow for the execution claims made. **[STRONG on robustness
  audit methodology; damning for any design that gives an LLM direct trading authority —
  consistent with this project's own "no LLM authority over real capital" rule.]**
- **TradingAgents** (arXiv 2412.20138, AAAI 2025): multi-role debate architecture
  (fundamental/sentiment/technical analysts → bull/bear researchers → trader → risk mgmt →
  fund manager). Reports better Sharpe/return/drawdown than baselines in its own backtest.
  **[WEAK as deployment evidence** given the Alpha Illusion and SoK re-analyses above used
  this exact system and found the reported edge collapses under contamination control and
  realistic costs.]
- **FinMem** (AAAI-SS 2024 / IEEE TBD 2025, arXiv/OpenReview sstfVOwbiG): layered memory
  (shallow/intermediate/deep) + character design; reports leading performance vs
  algorithmic baselines on its own backtest. Same caveat: cited by Alpha Illusion as one of
  the two systems whose reported return dropped ~72% out of pretraining window.
  **[WEAK as a forecasting result; MODERATE as a memory-architecture design worth
  borrowing — see Q5.]**
- **FinRobot**: agentic LLM for document analysis, generation, and per-stock forecasts;
  positioned as an analyst-assistant rather than an autonomous trader. No independent
  large-N replication found; **[WEAK]**, treat as an interface pattern, not evidence.
- Survey coverage: "LLM Agents in Financial Trading: A Survey" (ACM 2026,
  doi 10.1145/3802463.3802475) and "Agentic Trading: When LLM Agents Meet Financial
  Markets" (arXiv 2605.19337, 77-study evidence ledger through March 2026) — both surveys'
  own framing has shifted from "can LLMs trade" to "why do reported LLM trading results
  not survive contamination/cost controls," which matches the Profit Mirage / Alpha
  Illusion / SoK cluster above. **[MODERATE, meta-level convergence signal.]**

### Forecasting calibration (Brier) literature
- **ForecastBench** (ICLR 2025, faculty.wharton.upenn.edu PDF; forecastbench.org live
  leaderboard): as of Oct 2025, superforecasters led with difficulty-adjusted Brier
  **0.081** vs best LLM (GPT-4.5) **0.101** — roughly a 20% edge to humans. By mid-2026,
  several systems (Cassi AI, xAI, Google DeepMind entries) are "statistically
  indistinguishable" from superforecaster accuracy on ForecastBench's general-knowledge
  question set. **[STRONG, but note: ForecastBench questions are Metaculus-style world
  events, not equity 1-day-ahead returns — do not directly transfer the Brier number,
  only the *methodology* (difficulty-adjustment, aggregation-then-extremize).]**
- **AIA Forecaster** (arXiv 2511.07678): reaches superforecaster-level performance via
  **agentic search + supervisor-based aggregation + extremization** — i.e. it is not one
  LLM call, it's an ensemble/aggregation pipeline around LLM search, which is structurally
  close to what this system should be building (Q3). **[MODERATE]**
- General overconfidence literature: "Large Language Models Are Overconfident in Their
  Own Responses" (arXiv 2606.03437) and the calibration survey work (KDD 2025 tutorial,
  ACM Computing Surveys) converge on: **LLMs are persistently overconfident at
  high-stated-probability levels**, the miscalibration is a *reporting* problem more than
  a *representation* problem (internal activations often encode better-calibrated
  estimates than the emitted number — "What LLM Forecasters Know but Don't Say," arXiv
  2607.08046), and **RL with a proper scoring rule reward (log/Brier) measurably improves
  calibration** and generalizes OOD. Ensemble-of-diverse-LLMs (median/mean pooling)
  reduces variance and overconfidence versus any single model. **[STRONG converging
  evidence]** — directly supports (a) never trusting a single DeepSeek-stated probability
  raw, (b) building a numeric calibration layer on top (Q3), and (c) this project's
  measured result that a *structured extraction process* beats *persona-styled free
  probability statements* is exactly what this literature predicts.

**Bottom line for Q1:** the 2025–2026 literature has moved decisively away from "LLM
predicts returns" toward "LLM extracts evidence, something else adjudicates" — and the
single most relevant paper (Alpha Illusion) independently arrives at the same
architecture this system already committed to (`llm_analyzer` extraction → deterministic
ranker → calibration → sizing). The system's own measured +9%/-28% split is not an
outlier; it is the textbook instance of "structured evidence extraction beats persona
narrative" that the memorization/leakage/overconfidence literature would predict.

---

## Q2. Fine-tuning / RL-from-P&L vs extractor + calibration layer

**No paper found reports a clean OOS, cost-inclusive, post-cutoff comparison showing
RL-fine-tuned trading beats an extractor+calibration pipeline.** Every RL-finance paper
found either (a) doesn't report true forward/post-cutoff OOS, (b) reports metrics that
critique papers (Alpha Illusion, SoK, Profit Mirage) would flag as contaminated, or (c) is
explicitly about *fixing* RL's failure mode rather than about beating extraction.

- **Trading-R1** (arXiv 2509.11420): SFT + RL (three-stage curriculum) on a proprietary
  100k-sample, 18-month, 14-equity corpus (Tauric-TR1-DB). Reports better risk-adjusted
  return / drawdown than both instruction-tuned and reasoning baselines on 6
  equities/ETFs. **No mention of a strictly post-training-window holdout or realistic
  cost model in the summarized reporting** — treat as **[WEAK]** pending a Profit-Mirage-
  style re-audit; the training window (18 months, 14 names) is small enough that
  memorization cannot be ruled out.
- **Trade-R1** (arXiv 2601.03948, Jan 2026) is the most intellectually honest paper on
  this question: it states outright that **"applying standard RL to financial tasks often
  leads to reward hacking, where models become momentum machines, memorizing historical
  winners while hallucinating justifications."** Its fix is not "RL from P&L is good," it's
  a *process-level* verifier (Triangular Consistency: factuality/deduction/consistency
  between evidence, reasoning chain, and decision) used as a **validity filter on the noisy
  return-based reward**, precisely because raw P&L reward is too noisy/hackable to train
  on directly. **[MODERATE, but the finding cuts against naive RL-from-P&L]** — it is
  independent, arXiv-native evidence that raw-P&L RL degenerates, and the fix it proposes
  is structurally a "verify the extracted evidence chain before trusting the numeric
  signal" layer, i.e. still closer to extractor+verifier than to end-to-end RL alpha.
- **Fin-R1** (arXiv 2503.16252): SFT+RL (GRPO, format+accuracy reward) 7B model distilled
  from DeepSeek-R1 CoT traces, evaluated on **FinQA/ConvFinQA (financial QA/reasoning
  tasks)**, not on realized-return prediction or trading P&L. Its SOTA claims are about
  financial *reasoning benchmarks*, not market forecasting skill — **do not read this as
  evidence for RL-from-P&L in a trading context.** **[N/A to Q2, WEAK if misapplied.]**
- **FinGPT-Forecaster**: fine-tunes an open model (Llama/DeepSeek-R1-Distill-Llama-8B
  variants exist) to output stock-movement predictions/analysis. No large-N, cost-
  inclusive, post-cutoff replication found; treat existing reported numbers as
  **[WEAK]**, same contamination risk profile as FinMem/TradingAgents above.
  Also relevant: **"Fine-Tuning Llama and DeepSeek for Financial Forecasting"** (practitioner
  write-up, not peer-reviewed) reports the fine-tuning process was hard and results were
  mixed — anecdotal, **[WEAK]**, but consistent with the harder literature.
- **"ChatGPT and DeepSeek: Can They Predict the Stock Market and Macroeconomy?"**
  (arXiv 2502.10008): explicitly tests DeepSeek-derived news sentiment 1996–2022 and finds
  the signal **"effectively capture[s] contemporaneous stock market reactions, yet lack[s]
  forecasting power."** **[MODERATE-STRONG]** — this is a direct, non-agentic test of the
  exact question ("does a DeepSeek-family model's read of news forecast forward returns")
  and it says no for the raw contemporaneous signal, forecasting power only shows up (in
  the Lopez-Lira/Tang lineage) after separating initial reaction from *drift*, which is
  what the structured extraction → calibration path is designed to isolate.
- **"Finance-Grounded Optimization For Algorithmic Trading"** (arXiv 2509.04541): not an
  LLM fine-tune paper, but directly relevant methodology — replacing MSE training loss with
  Sharpe/PnL/MaxDD-derived losses plus turnover regularization **beats MSE loss on trading
  metrics** for a return-prediction model. This is evidence *for* objective-aligned
  training generally (echoes this project's "objective is terminal wealth, not accuracy"
  rule), but it is about a numeric prediction model's loss function, not about RL-tuning an
  LLM's own weights from P&L. **[MODERATE]** — reusable idea for the deterministic ranker
  training loss, not evidence for LLM RL fine-tuning specifically.

**Bottom line for Q2:** there is no credible OOS evidence that RL-fine-tuning an LLM on
realized P&L beats extractor+calibration. The strongest recent paper on RL-in-finance
(Trade-R1) is itself a paper about *why naive RL-from-return reward fails* (reward hacking
into "momentum machines" that hallucinate justifications) and *patches it* by inserting a
verification/consistency layer between evidence and decision — which is architecturally an
extractor-with-a-checker, not end-to-end RL alpha. Do not spend budget on RL fine-tuning
DeepSeek/Qwen on P&L; the literature's median finding is reward hacking, not skill.

---

## Q3. Calibration / reputation / aggregation layers — and the formulae

### Individual-forecaster calibration
- **Platt scaling**: fit `p_cal = sigmoid(a*logit(p_raw) + b)` on a **held-out** slice.
  Standard for over/under-confident-but-monotonic scores; needs relatively few points but
  assumes a logistic-in-logit relationship.
- **Isotonic regression**: fit a monotone step function `p_cal = f(p_raw)` on held-out
  data; more flexible, needs more data (roughly n≥1,000 bins-worth) to avoid overfitting
  the calibration curve itself — with ~17k graded rows this is very much affordable if
  split further by forecaster/process, not just pooled.
- Given this system's own finding (structured process discriminates, persona prompts are
  *anti-signal*), calibration must be fit **separately per process/arm**, never pooled
  across "investigator" and "persona" — pooling would let the anti-signal arm's miscalibration
  contaminate the good arm's calibration curve.

### Aggregating many forecasters into one number — Good Judgment Project (GJP) recipe
GJP's published method (elitist weighting + extremizing) is the most battle-tested formula
set for exactly this problem (many humans/processes, track records, need one probability):

1. **Track-record weight**: for each forecaster *i*, compute an accuracy weight
   `w_i = w_min + (w_max - w_min) * (their historical Brier-based percentile)`, GJP used
   raw weights in **[0.1, 1.0]** based on past-period Brier score, then
   **raised the weights to the 4th power** (`w_i^4`) before normalizing — chosen because it
   empirically minimized aggregate Brier in prior seasons. This is a strong non-linear
   amplification of skill differences; directly implementable: rank arms by out-of-sample
   Brier skill, map to [0.1,1.0], raise to a tunable exponent (start at 2–4 and tune on a
   held-out season), renormalize to sum to 1.
2. **Recency weighting**: more recent forecasts from the same forecaster get more weight
   than older ones from the same forecaster (exponential time-decay is the standard
   implementation choice in the aggregation literature this maps to).
3. **Pooling in logit/log-odds space, not probability space**: `logit(p_agg) = Σ w_i *
   logit(p_i)` (logarithmic pooling / log-odds aggregation) rather than
   `p_agg = Σ w_i * p_i` (linear pooling). Logarithmic pooling is the Bayesian-consistent
   choice under (approximate) conditional independence of the forecasters' errors and is
   what "Prior-Agnostic Robust Forecast Aggregation" (arXiv 2604.24517) formalizes as the
   general log-odds aggregation family; linear pooling is only appropriate when you want to
   preserve extreme disagreement rather than resolve it.
4. **Extremizing**: after pooling, push the aggregate away from 0.5:
   `p_final = sigmoid(k * logit(p_agg))`, `k > 1`. GJP's own examples: 70% → ~85%,
   30% → ~15%. The right `k` depends on crowd diversity/sophistication and should be
   fit/validated on a held-out period, not asserted; over-extremizing without validation
   is a classic way to turn good calibration into confident wrongness. AIA Forecaster
   (arXiv 2511.07678) independently reaches superforecaster parity using this same
   aggregate-then-extremize recipe, which is corroborating, not just historical, evidence.
5. **Bayesian shrinkage by n**: for a forecaster/process with few observations, shrink its
   estimated skill toward the population mean skill:
   `skill_shrunk = (n_i / (n_i + k)) * skill_i + (k / (n_i + k)) * skill_pop_mean`, with `k`
   a prior-strength hyperparameter tuned by leave-one-out CV (this is the standard
   hierarchical-Bayes / James-Stein-style shrinkage the forecast-combination literature
   ("Forecast combinations: an over 50-year review," arXiv 2205.04216) recommends over
   raw unshrunk weights, which overfit small samples).
6. **Skill decay**: because forecaster skill is not static (regime change, an arm
   discovering/losing its edge — exactly the pattern already logged for this project's
   momentum-vs-composite bottleneck and the SanDisk-archetype refutation), weight recent
   performance windows more than distant ones, i.e. compute the track-record Brier on a
   rolling window (e.g. trailing 60–90 graded forecasts) rather than all-time, and re-derive
   weights on every grading cycle rather than freezing them once.

### Concrete formula set to implement (synthesis, not any single paper verbatim)
```
For each process/arm i with n_i graded forecasts and rolling Brier skill s_i (vs a naive
base rate benchmark):
  skill_shrunk_i = (n_i / (n_i + k_prior)) * s_i        # k_prior tuned by LOO-CV
  raw_weight_i   = clip(skill_shrunk_i, floor, 1.0)      # floor prevents negative-skill arms
                                                          # (persona arms) from flipping sign
  amp_weight_i   = raw_weight_i ** gamma                 # gamma in [2,4], tuned OOS
  norm_weight_i  = amp_weight_i / sum(amp_weight_j)
  logit_agg      = sum(norm_weight_i * logit(p_i))
  p_pooled       = sigmoid(logit_agg)
  p_final        = sigmoid(kappa * logit(p_pooled))       # kappa tuned OOS, kappa>=1
```
Note the **explicit floor on raw_weight_i**: given the measured persona result
(-27.98% skill, negative discrimination), any aggregation that doesn't floor or
zero-clip negative-skill arms will let them act as *anti-signal injectors* — the
literature's crowd-wisdom results all assume forecasters are at worst noise, not
adversarial-to-truth, and this system has already measured an arm that is
worse than noise.

**Evidence strength:** GJP methodology **[STRONG]** (large tournament evidence, replicated
across seasons); log-odds vs linear pooling choice **[MODERATE-STRONG]** (theoretically
grounded, empirically supported in forecast-combination survey literature); the specific
exponents (4th power, GJP's k) are **[WEAK as universal constants]** — they were fit to
GJP's own forecaster pool and should be re-tuned on this system's own held-out grading
data, not imported as magic numbers.

---

## Q4. Analyst-level skill persistence — papers and horizon

- **Mikhail, Walther & Willis (2004)**, *J. Financial Economics* 74:67-91, "Do Security
  Analysts Exhibit Persistent Differences in Stock Picking Ability?" — established
  persistent cross-sectional differences in analyst forecast accuracy: analysts who were
  relatively accurate in the past tend to remain relatively accurate. **[STRONG, canonical]**
- **Cooper, Day & Lewis (2001)**, *J. Financial Economics* — ranked analysts on
  **timeliness**, not just accuracy, and abnormal trading volume around their forecasts;
  found **lead-analyst forecasts (timeliness-ranked) have a bigger price impact than
  follower forecasts**, and that timeliness-based rankings are *more* informative than
  accuracy- or volume-based rankings. **[STRONG]** — the operational implication is:
  weight by *speed of being first with new information*, not only by track-record
  accuracy.
- **Loh & Stulz (2011)**, "When Are Analyst Recommendation Changes Influential?" (RFS
  24(2):593-627): only **~12%** of recommendation changes are actually influential
  (move price); influential ones come from **leader/star/previously-influential analysts**,
  are issued **away from consensus**, and are **accompanied by an earnings estimate**.
  Small/growth/high-institutional-ownership/high-turnover names see more influential
  recommendations; influence also rose post-Reg FD/Global Settlement. **[STRONG]** — this
  is a strong argument for **discounting most analyst signal to zero** by default and only
  upweighting non-consensus, star-analyst, estimate-attached revisions.
- **Jegadeesh & Kim** ("Value of Analyst Recommendations: International Evidence," and the
  related "Analyzing the Analysts: When Do Recommendations Add Value?" with Krische & Lee):
  revision-based strategies profit **independent of momentum or other characteristics**;
  6-month abnormal return spread from recommendation revisions is **10.96% in the US**
  (largest of G7), vs 1.93%–4.66% in other G7 countries. **[STRONG]** — recommendation
  *revisions*, not levels, carry the signal, and the effect is far larger domestically than
  internationally (relevant since this project's stated ambition is whole-market / Asia-
  first — expect the US-calibrated analyst-revision edge to be smaller in Asian markets).
- **Hobbs, Kovacs & Sharma (2012)**, *J. Empirical Finance*, on revision frequency:
  faster-revising analysts' recommendations produced superior subsequent portfolio
  performance — but this is **[CONTESTED]**: their sample construction (only revisions
  within 12 months of the prior one) discards roughly half of all revisions since the
  median inter-revision gap is 11.2 months, and other work in the same area finds
  **slower-revising analysts herd less** and are more "timely" in Cooper/Day/Lewis's sense
  — i.e. "fast" and "good" are not the same axis, and a naive "reward recency of update"
  rule could reward herding rather than skill. **[WEAK-CONTESTED]** on frequency as a
  standalone predictor; treat "was this revision away-from-consensus" (Loh & Stulz) as the
  more robust ingredient than "was this analyst fast."
- **StarMine SmartEstimate** (LSEG/Refinitiv, industry methodology, not academic but with
  20+ years of published live track record): weights analyst estimates by accuracy
  (1–5 star ranking, "roughly 4x more likely to stay in the top accuracy bucket than to
  fall to the bottom") and by timeliness (drops estimates **>4 months stale** or not
  updated since material news). When |Predicted Surprise| > 2%, direction hit-rate is
  **~70%** across regions/sectors. **[MODERATE-STRONG — industry-grade, long-running, but
  not a peer-reviewed randomized/holdout design]** — its two operational rules (drop stale
  estimates, weight by rolling accuracy percentile) map directly onto the skill-decay and
  shrinkage-by-n formulae above.

**Horizon:** across this cluster, the persistent-skill and price-impact effects live at
**event-time (the days around the revision/recommendation) and out to the next
1–2 quarters** for accuracy persistence (Mikhail et al. re-rank analysts on a
rolling-annual basis); they do **not** claim persistence at multi-year horizons. This
matches this project's own §64 finding that "skill is at h=1, gone by h=5" — that is not a
system-specific quirk, it is the same horizon-decay shape the analyst literature has
documented for two decades.

---

## Q5. Memory architectures for an investing agent

- **FinMem** (layered memory: shallow/intermediate/deep-reflection, character design):
  reports better backtest performance vs baselines. **[WEAK as forecasting evidence]**
  given the ~72% return / ~51% Sharpe collapse Alpha Illusion measured for FinMem outside
  its training window — the memory architecture may still be a reasonable interface
  pattern, but its *reported edge* is not trustworthy evidence that layered memory itself
  adds forecasting skill (confounded with contamination).
- **ExpeL** ("LLM Agents Are Experiential Learners," AAAI 2024, arXiv 2308.10144):
  agent extracts natural-language "insights" from its own successful/failed trajectories
  and reuses them as in-context examples, no parameter updates. Shown to improve
  performance monotonically with more accumulated experience **on general agent
  benchmarks (ALFWorld, WebShop, HotpotQA)**, not finance. **[MODERATE evidence of the
  general mechanism, ZERO direct finance evidence]** — treat "self-distilled insights as
  retrieved few-shot context" as a plausible, cheap thing to try (it requires no fine-tune,
  fits the DeepSeek-only + local Qwen constraint), but do not expect the general-benchmark
  gains to transfer to noisy, low-signal-to-noise financial forecasting without measuring
  it directly.
- **Generative Agents** (Park et al.): three-tier memory (observation → reflection →
  retrieval-by-importance); ablating reflection degrades 48-hour simulated social behavior
  to "repetitive, context-free responses." This is **evidence that reflection matters for
  long-horizon *coherence* in an open-ended simulated world**, not evidence that it
  improves *predictive accuracy* in a domain with an external, adversarial, mostly-efficient
  ground truth like markets. **[WEAK transfer to finance]** — the mechanism (periodically
  synthesize raw observations into higher-level abstractions, retrieve by
  recency×importance×relevance) is worth stealing for building a "why did we believe this"
  audit trail (which this project already values — Decision Contracts, autopsies), but
  there is no evidence it increases Brier skill.
- Net assessment: **memory architecture research to date has evidence for
  interpretability/coherence/engagement, not for forecast skill in an efficient-market
  adversarial setting.** The one thing in this literature with genuine evidentiary weight
  for *this* system is the opposite of exotic memory: it's the plain finding (Q1/Q3) that
  **structured, typed evidence extraction beats free-form narrative/persona prompting** —
  that is a prompt/schema design result, not a memory-architecture result. Spend the
  memory-architecture effort on the audit trail / experiential-insight retrieval (ExpeL-
  style, cheap, no fine-tune), and treat FinMem/Generative-Agents-style layered memory as
  **decoration** until it is shown to move OOS Brier skill on this ledger specifically.

---

## Q6. Local (Qwen3-30B-A3B) vs frontier API for financial extraction

- Direct, controlled, apples-to-apples Qwen3-30B-A3B-vs-frontier numbers **on financial
  NER/event typing specifically were not found** — this is a genuine gap, not a null
  result; the closest available numbers are on other 7B-30B-class open models:
  - **FINER-ORD** (financial NER benchmark): GPT-4 scores **0.83 Entity F1**. Domain
    fine-tuned **FinMA-7B reaches 0.88 F1 on FPB sentiment** (a different, easier task
    than NER) — i.e. **domain fine-tuning of a 7B model can beat GPT-4 on a narrow,
    single-task benchmark**, but general 7B instruction models (LLaMA2-7B-chat class)
    "continue to struggle with both NER and complex extraction tasks" without that
    domain tuning. **[MODERATE]**
  - A more recent comparison found a **fine-tuned RoBERTa (small, non-generative) beats
    Gemini-1.5** on the specific classification task tested (0.8792 vs 0.8369 F1) —
    reinforcing that **for narrow, well-defined extraction/classification subtasks, a
    small fine-tuned encoder can beat a much larger general LLM**, frontier or not.
    **[MODERATE]**
  - "Financial Named Entity Recognition: How Far Can LLM Go?" (arXiv 2501.02237) is the
    most directly relevant paper name found but its full numeric breakdown was not
    retrieved in this pass — worth a follow-up fetch before finalizing local-vs-API
    task allocation.
- **Practical implication given the gap**: since no clean Qwen3-30B-A3B financial-
  extraction F1 number exists in the literature, **this system's own held-out grading
  ledger is the only real evidence source it has** — the honest move is to run the
  "investigator" evidence-packet extraction on both DeepSeek and local Qwen3-30B-A3B for
  a matched sample and diff their downstream Brier skill contribution, rather than
  assume either is better from benchmarks that don't cover this model or this task.
  The literature pattern above (fine-tuned small model ≥ general frontier model, on
  *narrow* typed-extraction subtasks) is at least directionally supportive of keeping
  well-defined, schema-constrained extraction (entity/event typing against the existing
  43-id enum) on the local Qwen, and reserving DeepSeek for the harder, less-structured
  synthesis/reasoning step (composing the evidence packet into a probability) — but this
  is an inference from adjacent-model literature, **not** a measured result for this
  system's exact stack, and should be labeled as a hypothesis to test, not a decided
  allocation.

---

## One-page design recommendation, in the system's own terms

**Keep the pipeline shape the system already has, and the literature agrees with it more
than it agrees with almost anything else tested here:**

```
LLM (DeepSeek + local Qwen) --> typed evidence packet (schema-constrained, per the
    43-id enum already enforced) --> deterministic forecast-quality model (the
    LightGBM-style ranker + a numeric calibration layer) --> track-record-weighted,
    log-odds-pooled, extremized aggregation across arms/processes --> sizing by the
    numeric engine (never by LLM-stated confidence directly)
```

This is, almost verbatim, the "Stage-1-only LLM as auditable information interface"
architecture "The Alpha Illusion" (arXiv 2605.16895) recommends after showing end-to-end
LLM trading alpha collapses ~70% out of its training window and further under realistic
costs — and it is why this project's own measured contrast (structured investigator
+8.97% vs persona -27.98%) looks exactly like a textbook instance of the
extraction-vs-narrative gap the 2025-2026 literature describes, not a fluke.

**What to measure first (ordered by information-per-dollar):**
1. **Per-arm rolling Brier skill with the GJP-style shrink/amplify/extremize aggregation
   formula above**, refit every grading cycle — this is cheap (pure arithmetic over the
   existing ledger) and directly answers whether the current single "investigator" arm's
   edge survives being blended with anything else, before spending on new arms.
2. **A negative-skill floor/clip in the aggregator**, immediately — the persona arms are
   measured anti-signal (-27.98%), and no aggregation formula in the literature (GJP,
   log-odds pooling, StarMine) assumes a forecaster can be *worse than a coin flip on
   purpose*; without a floor, a well-intentioned "more diversity is good" instinct will
   silently reintroduce the anti-signal.
3. **A same-sample DeepSeek-vs-local-Qwen extraction diff** on the typed evidence packet,
   because Q6 found no literature answer specific to this model pair/task — it has to be
   measured, not assumed, and it's cheap since the schema and grading pipeline already
   exist.
4. **A Profit-Mirage-style leakage/contamination check** on the investigator process
   itself: does its measured +9% skill survive when restricted to genuinely
   post-cutoff, never-seen tickers/dates, and does it survive a realistic-cost overlay?
   This is the single highest-value check because it is exactly the failure mode that
   invalidated FinMem/TradingAgents/QuantAgent's headline numbers in three independent
   2025-2026 papers, and this project has not yet run that specific audit on its own
   winning arm.
5. **Only after (1)-(4):** decide whether analyst-style track-record weighting (Loh &
   Stulz's "non-consensus + estimate-attached" filter, StarMine's staleness cutoff) is
   worth building for the *human* analyst/insider arms already in the system, since that
   literature's horizon (days to ~2 quarters) matches this project's own measured h=1-to-h=5
   skill decay almost exactly.

**Which premises in the task's framing the literature pushes back on:**
- *"LLMs used as forecasters"* — the 2025-2026 literature (StockBench regime-flip result,
  Profit Mirage, Alpha Illusion, SoK) treats this framing itself as close to obsolete for
  single-name short-horizon prediction; the live research question has moved to "LLMs as
  evidence interfaces feeding a separate adjudicator," which is what this system already
  does. Don't chase "a better forecasting prompt" — chase "a better evidence schema and a
  better aggregator."
- *"Fine-tuning ... beats extractor + calibration"* (Q2's premise) — no paper supports
  this; the best 2026 RL-in-finance paper (Trade-R1) exists specifically because naive
  RL-from-P&L reward-hacks into "momentum machines that hallucinate justifications." Do
  not fund an RL-fine-tune project on this premise without first getting a positive
  result from cheaper structured-extraction work.
- *Memory architecture as a source of edge* (Q5) — the evidence for FinMem/Generative-
  Agents-style memory is about coherence and interpretability in open-ended or social
  simulations, not about Brier skill in an adversarial market; don't over-invest here
  before (1)-(4) above are done.
- *Local vs API allocation by borrowed benchmarks* (Q6) — there is no published number for
  this exact model pair on this exact task; any allocation decision made without running
  (3) above is an assumption dressed as a finding.

---

## Sources (representative, not exhaustive — full list embedded above by section)

- Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?" — https://arxiv.org/abs/2304.07619
- "Detecting Lookahead Bias in LLM Forecasts" — arXiv:2512.23847
- "Profit Mirage: Revisiting Information Leakage in LLM-based Financial Agents" — https://arxiv.org/abs/2510.07920
- "The Alpha Illusion" — https://arxiv.org/html/2605.16895v1
- StockBench — https://huggingface.co/papers/2510.02209 ; https://openreview.net/forum?id=9tFRj7cmrS
- Vals AI Finance Agent Benchmark — https://arxiv.org/pdf/2508.00828 ; https://www.vals.ai/benchmarks/finance_agent-08-12-2025
- SoK: "Trading Agents or Market Crashers?" — https://arxiv.org/abs/2609.19705
- TradingAgents — https://arxiv.org/abs/2412.20138
- FinMem — https://openreview.net/forum?id=sstfVOwbiG
- Trade-R1 — https://arxiv.org/abs/2601.03948
- Trading-R1 — https://arxiv.org/html/2509.11420.pdf
- Fin-R1 — https://arxiv.org/abs/2503.16252
- "Finance-Grounded Optimization For Algorithmic Trading" — https://arxiv.org/abs/2509.04541
- "ChatGPT and DeepSeek: Can They Predict the Stock Market and Macroeconomy?" — https://arxiv.org/html/2502.10008v1
- ForecastBench — https://www.forecastbench.org/ ; ICLR 2025 paper (faculty.wharton.upenn.edu)
- AIA Forecaster — https://arxiv.org/pdf/2511.07678
- "Large Language Models Are Overconfident in Their Own Responses" — arXiv:2606.03437
- "What LLM Forecasters Know but Don't Say" — https://arxiv.org/html/2607.08046v1
- Good Judgment Project aggregation writeups — https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/
- "Prior-Agnostic Robust Forecast Aggregation" — https://arxiv.org/pdf/2604.24517
- "Forecast combinations: an over 50-year review" — https://arxiv.org/pdf/2205.04216
- Mikhail, Walther & Willis (2004), J. Financial Economics 74:67-91
- Cooper, Day & Lewis (2001), J. Financial Economics 61:383-416 ("Following the leader")
- Loh & Stulz (2011), Review of Financial Studies 24(2):593-627 — https://www.nber.org/papers/w14971
- Jegadeesh & Kim, "Value of Analyst Recommendations: International Evidence" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=411521
- Jegadeesh, Kim, Krische & Lee, "Analyzing the Analysts" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=291241
- Hobbs, Kovacs & Sharma (2012), J. Empirical Finance
- StarMine SmartEstimates methodology — https://www.lseg.com/en/data-catalogue/analytics/quantitative-analytics/starmine-smartestimates
- ExpeL — https://arxiv.org/html/2308.10144v2
- FINER-ORD / financial NER LLM comparison — https://arxiv.org/pdf/2501.02237
