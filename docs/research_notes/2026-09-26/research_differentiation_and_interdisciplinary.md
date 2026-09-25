# Differentiation and interdisciplinary research — 2026-09-26

Requested by Murat (evening, 2026-09-25/26): *"what are we doing that is
different? compare it to other products, other companies ... I will join a
hackathon: this uses an LLM and the data gives it better purpose, better
clarity to make decisions ... hoping to beat the S&P 500 but we don't have
proof yet ... find interdisciplinary points and join them: neuropsychology,
how people think, how companies think, how demand exists and how companies
fill this demand ... read research papers on this, make a condensed
research, give links."*

Method: three parallel research passes (web search, with Exa as fallback
where the daily WebSearch budget was exhausted) covering (A) ~20 AI-investing
products/companies, (B) ~24 academic papers across behavioral finance,
innovation diffusion, CEO psychology and political economy, (C) evidence on
which news/social sources carry measured forward information plus the ToS
reality of reading WSJ/Yahoo with a browser agent. Every claim below is
sourced; items the researchers could not verify precisely are marked as
such. This document does not modify any repo source — it is a research note
only.

---

## PART A — Differentiation: the honest version for a hackathon pitch

### A.1 What each product actually does, and whether it proves anything forward

One line each on (a) what it does, (b) its headline feature, (c) forward/
OOS/cost-inclusive evidence vs SPY, (d) whether it grades its own past
calls against outcomes.

| Product | (a) What it does | (b) Headline feature | (c) Forward, cost-inclusive evidence vs SPY | (d) Grades its own past calls |
|---|---|---|---|---|
| **TradingAgents** (Tauric) | Open-source multi-agent LangGraph framework; analyst/researcher/trader/risk-manager LLM agents debate to a simulated trade decision | Structured bull/bear debate before a "Portfolio Manager" agent approves/rejects | **None found.** README disclaims "research purposes," no track record anywhere ([github](https://github.com/TauricResearch/TradingAgents)) | No — no persisted ledger, simulated exchange only |
| **ai-hedge-fund** (virattt) | Open-source proof-of-concept; Buffett/Munger-styled agent personas analyze stocks, user runs local backtests | Configurable "investment mandates" with a local equity-curve-vs-benchmark chart | **None found** — explicitly "not intended for real trading" ([github](https://github.com/virattt/ai-hedge-fund)) | No — backtests run locally by users, nothing centrally tracked |
| **FinRL** (AI4Finance) | Open-source deep-RL library (A2C/DDPG/PPO/SAC/TD3) for building trading agents over simulated markets | End-to-end train-test-trade RL pipeline vs DJIA/mean-variance baselines | **None** — only backtest tutorials vs DJIA/MVO, no live results ([github](https://github.com/AI4Finance-Foundation/FinRL)) | No |
| **FinGPT** (AI4Finance) | Open-source financial-LLM ecosystem (sentiment, RAG, benchmarks) — an NLP toolkit, not a trading system | Instruction-tuned financial LLMs + FinGPT_Benchmark | Not applicable — no strategy is claimed | No |
| **Composer** | No-code platform; users/AI build "symphonies" (rule-based rotation strategies) auto-rebalanced in a real brokerage account | AI natural-language strategy builder + public Symphony Database with backtested Sharpe/return/drawdown | Self-labeled backtest/"OOS" figures per symphony (e.g. one page claims ~58.8% ann. "OOS" vs ~25.2% SPY) — **self-reported, not independently audited, no platform-wide cost-inclusive live number** ([composer.trade](https://www.composer.trade/trading-strategies)) | No aggregate forecast-vs-outcome ledger, only per-symphony charts |
| **QuantConnect / Lean** | Infrastructure (open-source Lean + hosted QuantConnect) for coding/backtesting/deploying algos with realistic fees/slippage and live execution | "Mia" AI assistant for strategy design + 375,000+ live algos deployed since 2015 | Not applicable at platform level — it's a tool, not a strategy; individual users' results aren't aggregated/disclosed | No — users see their own curves only |
| **Numerai** | Crowdsourced hedge fund: anonymous data scientists submit staked ML predictions on encrypted data, combined into a "Meta Model" trading a real book | Tournament staking/burning of NMR against live OOS correlation each round | **Mixed.** Self-published 2021 claim of beating Russell 2000 by +46pts and "beat S&P 500 too" since Sept 2019 — but an independent 13F-based analysis ([13foresight.com](https://13foresight.com/fund/numerai-gp-llc)) shows 2023–2026 annualized 6.2% vs SPY 21.3%, 8 underperformance periods, worst −24.4% vs SPY | **Yes, partially** — every model's live OOS CORR/MMC is scored each round with real stake consequences; fund-level disclosure has been sparse since 2022 |
| **Danelfin** | Assigns every US/EU stock/ETF a daily 1–10 "AI Score" estimating P(beat S&P 500 over ~3mo) from ~900–10,000 features | Public self-service "AI Score Audit" with rolling alpha, factor adjustment, cost sensitivity | **The most rigorous self-published evidence found.** Publishes gross and 25bps-cost-adjusted alpha across 3 non-overlapping OOS windows (2017–19/2020–22/2023–25), Fama-French residual alpha, explicit "simulated" (pre-Jul 2025) vs "live" (post-Jul 2025) split — i.e. **true live forward evidence exists for only ~14 months so far**, self-published not third-party audited ([audit.danelfin.com](https://audit.danelfin.com/)) | **Yes** — continuously grades historical scores vs realized 1w/1m/3m/6m returns, publishes win rates, t-stats, decay curves |
| **Kavout** | AI research platform (pivoted from institutional "K Score" feed); now "InvestGPT" + 8 AI research agents, "Smart Money" (insiders/Congress/13F) tracking | K Score (legacy) / InvestGPT agents (current) | **None current.** A stale 2018 vendor blog claimed 21.9% CAGR since 2012 vs 13.3% SPY — not repeated in 2025/2026 materials, which make no performance claims | No, in current materials |
| **Tickeron** | Retail platform: pattern-recognition scanning + trend prediction + three tiers of "AI Robots" for signals/copy-trading (stocks/ETFs/crypto) | Per-robot self-reported annualized returns/Sharpe/profit-factor + a "confidence score" per pattern | Company-reported only, explicitly called "hypothetical" backtests by Tickeron itself; reviewers flag as not independently audited ([aiflowreview.com](https://aiflowreview.com)) | Partial — some "Brokerage Agents" show real-money trade histories, but no consolidated audited ledger vs benchmark |
| **Toggle AI → Reflexivity** | Rebranded Oct 2024; institutional B2B knowledge-graph + LLM research tool for PMs (backed by Druckenmiller et al.) | "Zero-hallucination" knowledge graph + proactive alerts | Not applicable — B2B research tool, not a managed strategy, no claim made | No |
| **Magnifi** (TIFIN) | Conversational AI fund/ETF search + portfolio fee/overlap analysis + integrated brokerage | Natural-language investment discovery, not stock-picking | Not applicable — a discovery tool | No |
| **Boosted.ai** | Institutional B2B generative-AI research ("Alfa"/"Alfa Prime"); monitors filings/news, multi-model bull/bear "debates" produce conviction-scored memos | AI investment-committee debate producing cited research | Not applicable — sells research infra to funds ($5T+ AUM clients), client portfolio performance is private | No |
| **Bloomberg AI** (BQuant, ASKB, Terminal AI) | AI news/earnings summaries, Document Search, "ASKB" (Feb 2026) agentic Q&A grounded in Bloomberg data | Coordinated multi-agent research answers with source citations | Not applicable — data/productivity tools, no strategy claimed | No |
| **Robinhood Cortex** | AI assistant (Mar 2025+) generating "Digests" explaining price moves; "Trade Builder" screens options matching a stated thesis | Real-time sourced explanations of stock moves | **None** — Robinhood's own disclosure states "no guarantee that AI will improve investing performance...or reduce losses" | No — explains moves after the fact, no predictive track record |
| **Public.com Alpha** | Free GPT-4-based research co-pilot in-app (2023+) using filings/calls/news/sentiment; newer "Agents" automate recurring trade instructions | Conversational, portfolio-aware research + thesis pressure-testing | **None** — explicit disclaimer it is not investment advice/research | No |
| **Perplexity Finance** | Free AI-search finance dashboard (2024+): quotes, transcripts, NL screener, Polymarket data | NL screener + integrated live earnings-call transcripts | **None** — explicitly "not intended for trading...or investment advice" | No — issues no predictions |
| **2026 launches** (Abundance $100M seed; Lumenai Innovation Fund; Valour/Neuronomics crypto fund) | Newly launched agentic AI hedge funds | Heavy funding/press at launch | **None — too new to have any history**; Lumenai states outright "the Fund has no operating history" | No |

**Pattern across ~21 entities surveyed:** effectively **zero** have
independently audited, cost-inclusive, live forward evidence of beating SPY.
Danelfin is the one partial exception — rigorous, but self-published and only
~14 months genuinely live. Numerai has one dated (2021) self-reported forward
claim, contradicted by an independent 2023–2026 analysis showing
underperformance. Only **Danelfin and Numerar** do any real self-grading of
past calls against outcomes — everyone else markets "AI-powered" research,
ranking, or idea generation while confining actual return claims to
backtests, in-sample statistics, or stale figures. **The absence of
independently verifiable forward evidence is, industry-wide, the finding.**

### A.2 What Aegis has that they do not (restricted to what Aegis can prove from its own receipts)

| Capability | The receipt |
|---|---|
| A frozen forecast ledger scored against real outcomes, not backtests | `predictions.jsonl` / decision ledger, ~25k rows, every forecast written **before** its outcome is known, at fixed horizons (h=1/5/20/120) |
| A measured result that a *process* beats a *persona* — evidence discipline over model choice | §64 (2026-09-24): `investigator` (a procedure) **+8.97% held-out skill** vs nine thematic personas at **−27.98% at optimal weight zero** (negative discrimination = anti-signal); every persona's reputation weight is 0.0 in the 2026-09-25 reputation run |
| Every book frozen against a random twin, at commit time, before any grading | Book factory (`llm_portfolio.py`/`book_factory.py`): `human_ai_thematic_v1`/`v2`, `revision_flow_v0`, 6 factory books + twins, each with a frozen policy hash and timestamp |
| An adversarial review loop that argues the money case, not the code case | `docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md` + its adjudication: 13/14 points accepted, including a correction that the investigator's reputation weight was magnitude-skill, not direction-skill |
| Refusal machinery that is itself logged and graded | `u_plan`/PROBE path refuses EXPLOIT while the ranker is measured negative; every refusal prints the worst-case dollar figure before it is made (e.g. PROBE −$16,452 at 10×2%×3σ; EXPLOIT would be −$64,800 at gross 1.00) |
| Point-in-time discipline enforced, not promised | "Fact before price" (freeze the fundamental read before revealing market reaction); frozen information states; no training on future information; costs never omitted (`Policy` refuses zero-cost runs unless explicitly flagged) |
| A negative-results / corpse ledger that is itself queried before new research starts | `aegis_postmortems`, `docs/TRIALS/*`, the `FAILED_VARIANT → DEPRIORITIZED → RETIRED_FROM_CURRENT_SEARCH` / `MECHANISM_REJECTED` vocabulary — a failed *implementation* closes that implementation, not the mechanism family |
| A licence system that separates what may be *tested* from what may be *claimed* | Three licences (`PRODUCT_EXPERIMENT` / `CAPITAL_CANDIDATE` / `RESEARCH_CLAIM`): exploration needs no significance gate, but promotion to a claim needs full preregistration, MDE, matched controls, holdout |
| Survivorship and selection audits printed on the receipt, not assumed away | `xs_ranker.survivorship_audit()`; the 2026-09-22 finding that a 3,060-symbol panel had **zero** delistings (impossible in a real cross-section) was caught and the dead names were pulled back in |
| Per-forecaster calibration, not just accuracy | `forecast_reputation.py`: held-out skill, shrink→floor 0→γ→log-odds→κ, a calibration curve showing stated 0.58 confidence realizing at 0.48 |

### A.3 What they have that Aegis does not

- **Real capital and scale.** Numerai runs an actual fund; Boosted.ai's
  clients manage $5T+; QuantConnect has 375,000+ live deployed algorithms.
  Aegis is 100% paper.
- **Distribution and brand trust.** Robinhood, Public.com, Bloomberg, Yahoo
  and Perplexity each sit in front of millions of existing users; Aegis has
  none.
- **Institutional data and execution infrastructure.** Bloomberg's terminal
  data/latency advantage and RavenPack's sub-second news analytics are
  documented (Part C) to matter most at HFT speed — infrastructure Aegis does
  not have and, per Part C, would get little marginal value from at its
  current LLM-cadence pace.
- **A longer, if unaudited, live history.** Danelfin has ~14 months of live
  score-vs-outcome data; Numerai has run its tournament since 2019. Aegis's
  paper books entered the market on 2026-09-25/26 — days old.
- **Funding and team size.** Abundance raised $100M seed; Lumenai is backed
  by an asset-management factory. Aegis is one person plus agents.
- **Polished product surface.** Every consumer product surveyed (Cortex,
  Alpha, Perplexity Finance, Magnifi) has a shipped, designed UI in front of
  real users; Aegis's frontend exists but is not the current focus.

### A.4 The pitch, and the one number Murat cannot yet say

> "Aegis is not another AI stock-picker chatbot — it is a system where every
> decision is written down and dated *before* the outcome is known, and then
> graded against what actually happened, which almost none of the ~20
> 'AI-investing' products we surveyed do at all. Our one measured result so
> far is that a structured evidence-gathering *process* beats persona-styled
> LLM prompting by a wide margin out of sample (+8.97% vs −27.98% held-out
> skill), which is evidence that discipline matters more than model choice.
> What we cannot yet say — and won't claim until we can show the receipt,
> not a backtest — is that this beats the S&P 500 forward, net of costs; that
> test is running now, live, in paper accounts, and the honest answer today
> is 'best historical net strategy vs market: none.'"

**The one number he cannot yet say: beating SPY forward, cost-inclusive, out
of sample.** Everything else in this pitch is provable from receipts already
on disk; that one is not, and per the handoff it is the thing the whole
engine is currently pointed at proving.

---

## PART B — Interdisciplinary: demand, minds and firms

24 items, grouped as requested. Evidence strength and operationalizability
are the researchers' honest judgment, not marketing. Items are mapped to the
existing Aegis file/quest that could carry them; "no — what's missing" is
given where nothing exists yet.

### B.1 Attention, herding, extrapolation

| # | Paper | Finding | Strength | Testable with what we have? |
|---|---|---|---|---|
| 1 | Barber & Odean, "All That Glitters," *RFS* 2008 ([doi](https://doi.org/10.1093/rfs/hhm079)) | Retail investors are net *buyers* of high-attention (volume/extreme-return/news) stocks — attention shapes the buy set, not the sell set | Strong | Yes — a volume/return/news attention proxy belongs in the planned `world_state_panel` (chunk 3) or as the chunk-6 social/attention column |
| 2 | Greenwood & Shleifer, "Expectations of Returns and Expected Returns," *RFS* 2014 / NBER 18686 | Survey return expectations are extrapolative and *negatively* correlated with subsequent realized returns | Strong | Partial — no survey feed exists; `revision_flow.py`'s net-raises trend is the closest available extrapolation proxy |
| 3 | Bordalo, Gennaioli, La Porta & Shleifer, "Diagnostic Expectations and Stock Returns," *JoF* 2019 | Stocks with the most optimistic analyst long-term growth forecasts earn *lower* subsequent returns | Strong | Yes — analyst LTG-forecast extremity/dispersion is an IBES-style field `revision_flow.py`/the analyst module already touches; a natural new `expected_return.py` component |
| 4 | Da, Engelberg & Gao, "In Search of Attention," *JoF* 2011 (+ "The Sum of All FEARS," *RFS* 2014) | Google Search Volume (retail attention) predicts ~30bps 2-week outperformance, fully reversing within a year | Strong | Yes, directly — Google Trends API is free; a new column in `world_state_panel` (chunk 3), graded like every other component |
| 5 | Frazzini, "The Disposition Effect and Underreaction to News," *JoF* 2006 | Prospect-theory reference points (unrealized fund gains/losses) predict PEAD magnitude; long-short overhang spread earns 2.43%/mo (t=6.60) | Strong (theoretical link to disposition effect flagged as contested by Barberis & Xiong 2009) | No — would need 13F-based cost-basis reconstruction; not yet a column, plausible new feature for `expected_return.py` |
| 6 | Stallen, Borg & Knutson, "Brain Activity Foreshadows Stock Price Dynamics," *J. Neurosci* 2021 (+ Caplin & Dean, *QJE* 2008) | fMRI reward/loss-anticipation activity forecasts aggregate price direction/inflections in a lab market, preregistered | Suggestive-moderate (small N, lab paradigm) | No — no fMRI feed on real investors exists or could; theoretical scaffold only for why attention/sentiment proxies should work |

### B.2 How companies fill demand — diffusion as a forecastable pattern

| # | Paper | Finding | Strength | Testable with what we have? |
|---|---|---|---|---|
| 7 | Christensen et al., "Know Your Customers' Jobs to Be Done," *HBR* 2016 | Customers "hire" products for a situational job, not a demographic match — correctly framing the job reveals a larger TAM | Moderate (qualitative/case-based, not return-tested) | Partial — `thesis_card.py`'s qualitative narrative field and the chunk-4 "future-facing quests" (pivots, what the world will need) are the natural home; not a computed signal today |
| 8 | Bass, "A New Product Growth Model," *Mgmt Sci* 1969 | The canonical adoption S-curve (innovator/imitator effects) fits historical durable-goods sales timing/height | Strong as diffusion theory, **thin/absent as a return-predictor** — no rigorous recent finance application verified | No — would need unit/shipment data fit to a Bass curve; a DIY feature for the `catalyst` YAML, not literature-backed for returns |
| 9 | Wright, *J. Aeronautical Sciences* 1936; ARK Invest, "Wright's Law" 2019/2022 | Cost falls as a power law of *cumulative production*; ARK claims 40% lower forecast error than Moore's Law across 62 technologies. **Credible critiques**: Nemet (IIASA 2005) shows learning-rate estimation sensitivity shifts cost-parity forecasts by decades; Lafond/Greenwald/Farmer's WWII natural experiment finds "learning-by-doing" explains only 40–67% of cost decline, the rest confounded with calendar time | Moderate original claim, strong critique — time and cumulative experience are often statistically indistinguishable out of sample | Yes as a **fundamentals** input (cumulative-unit cost-curve extrapolation), explicitly **not validated as a standalone return predictor** — a candidate feature for `thesis_card`/catalyst state changes (`STATE_CHANGE_ELASTICITY`, invariant #14), not for `expected_return.py` directly |
| 10 | Theory of Constraints / bottleneck migration (Goldratt); Tyan/Chen/Wang 2002, Lin/Spiegler/Naim 2017 (Intel-calibrated) | Peer-reviewed wafer-fab TOC studies show real operational (not return) gains from identifying the binding constraint node | Moderate — operational evidence only, no stock-return evidence | Partial — matches `AEGIS_STRATEGIC_INVARIANTS` #4 ("the best trade may be…the bottleneck owner") and chunk-4's supplier/customer-shift quests; no bespoke bottleneck-tracking pipeline exists yet |

### B.3 CEO/founder psychology and firm outcomes

| # | Paper | Finding | Strength | Testable with what we have? |
|---|---|---|---|---|
| 11 | Malmendier & Tate, *JoF* 2005 / *JFE* 2008 | Overconfident CEOs (revealed via options-holding behavior) are 65% more likely to make acquisitions; market reacts with −90bp CAR vs −12bp for others | Strong, widely replicated | Yes, laboriously — Form 4/ExecuComp-derived overconfidence proxy feeding chunk-4's CEO-track-record quest |
| 12 | Fahlenbrach, "Founder-CEOs...," *JFQA* 2009; caveat: Hendricks & Howell 2021 (premium concentrated at IPO, decays after) | Founder-CEO firms earn 4.4%+ abnormal returns 1993–2002, but the premium is period/regime-dependent, not permanent | Moderate (strong original, fragile follow-up) | Yes — founder-CEO status is extractable from proxy bios; a `thesis_card` field, feeding chunk-4 quests |
| 13 | Chatterjee & Hambrick, *ASQ* 2011; Ham, Seybert & Wang, *Rev. Acct. Studies* 2018 | CEO narcissism (signature size, self-referential language) predicts R&D/M&A overinvestment and lower profitability — a slow fundamentals signal, no direct stock-price reaction | Moderate | Yes now — LLM-scored self-referential/superlative language from earnings-call transcripts is exactly a DeepSeek-synthesis task for `thesis_card.py`'s chunk-4 CEO quest |
| 14 | Hutton & Stocken 2009; Rogers & Stocken, *Acct. Review* 2005; Zhang, *Acct. Review* 2012 | A firm's guidance-accuracy track record predicts the market's reaction size to new guidance and dampens PEAD | Moderate | Yes — a per-company guidance-accuracy score is computable from historical management EPS forecasts vs actuals; a natural extension of `forecast_reputation.py`'s per-arm skill machinery, applied per-company instead of per-arm |
| 15 | Larcker & Zakolyukina, *J. Acct. Research* 2012 | Linguistic deception classifiers on earnings-call Q&A beat random guessing 6–16% OOS predicting restatements; long-highest-deception-score portfolio: −4% to −11% annualized alpha | Strong (foundational, peer-reviewed; underlying restatement-labeled sample is small) | Yes, directly — this is precisely a DeepSeek/`thesis_card.py` synthesis task once earnings-call transcripts are ingested; the adversarial review loop is a natural place to score it |

### B.4 Political economy

| # | Paper | Finding | Strength | Testable with what we have? |
|---|---|---|---|---|
| 16 | Faccio, "Politically Connected Firms," *AER* 2006 | New political connections produce a significant positive value jump across 47 countries; connections buy market power, not efficiency (lower ROE) | Strong | Yes — political-connection entity-linking (news/lobbying/bio data) is an LLM-pipeline task; feeds chunk-4's political/regulatory-exposure quest |
| 17 | Baker, Bloom & Davis, "Economic Policy Uncertainty," *QJE* 2016 | Newspaper-based EPU index predicts higher volatility, reduced investment in policy-sensitive sectors; EPU innovations foreshadow output declines across 12 economies | Strong, industry-standard | Yes, directly — the index is free and public; a natural input to `expected_return.py`'s `w_r·regime(market_sensor)` term alongside VIX |

### B.5 Extras (2023–2026 emphasis)

| # | Paper | Finding | Strength | Testable with what we have? |
|---|---|---|---|---|
| 18 | Shiller, "Narrative Economics," *AER* 2017 / Princeton 2019 | Popular narratives spread epidemiologically and causally shape spending/investing, not merely reflect it | Suggestive (Shiller concedes causality is hard) | Partial — narrative-frequency text mining over the news corpus is directly buildable; a candidate `thesis_card`/quest feature, not yet built |
| 19 | Bordalo, Gennaioli, La Porta & Shleifer, "Finance Without Exotic Risk," NBER 33004, 2024 | Analyst-forecast-error-based "expectations-based returns" explain most value/size/investment/momentum spreads — these premia are largely mispricing, not risk | Strong | Yes — built entirely from IBES-style analyst data; directly relevant to re-deriving `xs_ranker`'s factor set from forecast errors rather than raw factors |
| 20 | Augenblick, Lazarus & Thaler, "Overinference from Weak Signals...," *QJE* 2024 | People overreact to weak signals, underreact to strong ones — replicated in lab, sports betting, and 20 years of S&P options data | Strong | Moderate — maps to sizing conviction by signal magnitude in `expected_return.py` rather than treating all news identically |
| 21 | Afrouzi, Kwon, Landier, Ma & Thesmar, "Overreaction in Expectations," *QJE* 2023 | Overreaction to the latest data point is stronger for less-persistent processes and longer horizons | Strong (large RCT) | Moderate — "less persistent → more overreaction" maps to a computable volatility-of-fundamentals proxy in the ranker |
| 22 | Sias, *RFS* 2004; Grinblatt/Titman/Wermers, *AER* 1995; Koch, *Mgmt Sci* 2016 | Institutional herding is real but modest (~2.5–2.7% excess same-direction trading), concentrated in buying past winners; "leader" funds others follow do outperform, mere herders don't | Moderate | Yes — 13F-based herding measures are standard and already referenced in chunk-3's panel ("insider/13F/Congress rows") |
| 23 | Han, Hirshleifer & Walden, "Social Transmission Bias," *JFQA* 2021 (NBER 24281) | Investors selectively share wins over losses; listeners under-discount this, explaining demand for lottery/high-skew stocks | Moderate (theory calibrated to known anomalies, transmission itself not directly observed) | Partial — social-media/Reddit chatter volume is the plausible modern proxy; feeds chunk-6's social column, but per Part C the Reddit evidence itself is mixed |
| 24 | Siano, "The News in Earnings Announcement Disclosures," *Mgmt Sci* 2025 | LLM-derived textual "news" from earnings releases explains 3x more short-window return variance than dictionary/ML text measures; calls add ~25% more R² | Strong (top journal, rigorous OOS design) | Yes, directly — this is the class of signal `thesis_card.py`/DeepSeek synthesis is already positioned to build in-house rather than merely cite |

**Honesty note carried over from the researchers:** the strongest, most
replicated results (Barber-Odean, Baker-Bloom-Davis, Faccio,
Da-Engelberg-Gao, Larcker-Zakolyukina, Malmendier-Tate) are pre-2015 and
already well known. Several items are explicitly thin and should not be
treated as settled precursors without independent replication on Aegis's own
data: the Bass-diffusion-to-returns link (#8), some LLM-sentiment-portfolio
claims outside #24, and the narcissism-to-stock-reaction link (#13, which
Ham et al. themselves find has *no* direct price reaction, only a downstream
fundamentals effect).

---

## PART C — Sources: is WSJ / Yahoo / OpenClaw worth it, and is WallStreetBets bad?

### C.1 The evidence, by source

| Source | Measured forward content | Link |
|---|---|---|
| **WSJ "Abreast of the Market" column** | Tetlock (2007, *JoF*): media pessimism predicts next-day downward price pressure (t=3.94) followed by mean reversion — a **sentiment/noise-trader barometer**, not new fundamental information; a hypothetical 7.3%/yr strategy would likely be erased by turnover costs | [doi.org/10.1111/j.1540-6261.2007.01232.x](https://doi.org/10.1111/j.1540-6261.2007.01232.x) |
| **Dow Jones Newswire (fast) vs WSJ column (slow)** | Tetlock, Saar-Tsechansky & Macskassy (2008): negative words forecast low future earnings; effect on earnings-related stories is ~5x larger than other stories; a strategy worked on the fast newswire, not on the slower daily column, and realistic costs "could easily eliminate" even that | [doi.org/10.1111/j.1540-6261.2008.01362.x](https://doi.org/10.1111/j.1540-6261.2008.01362.x) |
| **RavenPack / machine-readable news analytics** | von Beschwitz, Keim & Massa: ~300ms-latency sentiment tags speed up price reaction (+1.3pp share of move in first 5 seconds), strongest for press releases; sentiment factors show up to 2.78%/6mo, concentrated in small/illiquid names and largely disappearing for liquid/cap-weighted portfolios | [Fed IFDP 1233](https://www.federalreserve.gov/econres/ifdp/files/ifdp1233.pdf) |
| **Wire latency / HFT speed** | Chordia, Green & Kottimukkalur (*RFS*): SPY/ES react to macro surprises within 5 milliseconds, but total profit from being fast is only $19k–$50k **per event** — a real but HFT-infrastructure edge, not one an LLM-cadence system can monetize | [doi.org/10.1093/rfs/hhy025](https://doi.org/10.1093/rfs/hhy025) |
| **SeekingAlpha** | Chen, De, Hu & Hwang (2014, *RFS*): article/comment negative words predict lower returns over the **next 3 months** (not reversed) and predict subsequent earnings surprises — the strongest positive result in this set for a cheap, crowd-generated text source | [doi.org/10.1093/rfs/hhu001](https://doi.org/10.1093/rfs/hhu001) |
| **Reddit/WallStreetBets** | **Genuinely mixed.** Anand & Pathak (2022) and Long/Lucey/Xie/Yarovaya (2022) find real but narrow predictive tone effects on GME at 5–30 min horizons, driven by ~462 top posters. A Springer 2022 study finds Reddit volume predicts trading *volume*, not abnormal *returns*. An Oxford working paper concludes WSB provides "little to no signal about future asset prices" outside already-manic meme names | [Anand & Pathak](https://ideas.repec.org/a/eee/ecolet/v211y2022ics0165176521004808.html); [Oxford WP](https://ora.ox.ac.uk/objects/uuid:6f3c53d3-f0d6-4232-b3cf-bf1696b200f9/files/dsf268587w) |
| **Yahoo Finance** | No dedicated predictive-news study found. Yahoo's role is data plumbing (prices/consensus estimates), not a demonstrated news-content signal; its distributed consensus target prices are predictive when analyst dispersion is low but *reverse sign* when dispersion is high (Zhang, Yale/Mgmt Sci forthcoming) | [Yale working paper](https://insights.som.yale.edu/sites/default/files/2025-01/Consensus%20target%20prices.pdf) |

**Murat's instinct on WSB is supported by the literature, with a caveat**:
it is not that social media is worthless — it is that the (thin) positive
evidence is concentrated in a handful of accounts and in mania-regime names,
and at least two independent studies find no return-predictive content
outside that narrow slice. Treat it as an attention/volume signal, not an
information signal, unless proven otherwise on Aegis's own data.

### C.2 The ToS / licensing reality of reading WSJ and Yahoo with OpenClaw

- **WSJ / Dow Jones** ([terms](https://register.wsj.com/terms)): explicitly
  bars "automated means...**browser automation tool**, API client, **AI
  agent or assistant**" from accessing content without prior written
  consent, separately bars using content for AI "including...**grounding**
  purposes" without a license, and its `robots.txt` states the same. This
  names the OpenClaw pattern directly — there is no "personal research
  assistant" exception in the text.
- **Yahoo** ([terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)):
  similarly categorical — bars "robots, spiders, scrapers, data mining
  tools" without express prior permission, no personal-use carve-out stated;
  Yahoo does offer a licensed Developer API as the legitimate programmatic
  path.
- **hiQ Labs v. LinkedIn** (9th Cir. 2022; district court on remand,
  Nov 2022): scraping fully public, unauthenticated pages is not a **CFAA**
  ("hacking") violation — but hiQ was separately found to have **breached
  LinkedIn's contract** by doing it anyway. Two things cut *against* a
  favorable reading for OpenClaw specifically: (1) LinkedIn's pages were
  ungated/public, while WSJ articles behind a personal paid login are a
  "gates-up" fact pattern the CFAA analysis treats differently; (2) both
  WSJ's and Yahoo's contracts name "personal consumption" as the line and
  separately name AI/browser agents as prohibited regardless of volume.
- **Net, plain-terms (not legal advice)**: reading your own subscribed pages
  by hand carries no criminal exposure. Automating that reading with
  OpenClaw against explicit ToS language is a real but **low-severity civil
  contract-breach risk** (most likely consequence: account
  termination), with severity scaling with volume, persistence after any
  cease-and-desist, and any redistribution — a single subscriber's private
  research notes are a much lower-risk case than bulk scraping/republishing,
  but the sites' own text does not carve out that exception.

### C.3 Answer the question empirically, not by opinion

The literature above is someone else's sample, someone else's era, someone
else's costs — WSJ's own signal decays and reverses within days, the fast
Dow Jones Newswire is tradable only before costs, SeekingAlpha's signal is
durable over three months and doesn't reverse, RavenPack's edge is
concentrated in the first seconds and in small/illiquid names, and WSB's
signal (if real at all) is concentrated in ~462 accounts and mania regimes.
No single verdict — "WSJ is worth $40/month," "Reddit is useless" — can
survive contact with that much heterogeneity. Aegis already has the
mechanism to settle this the way it settles everything else: **every item
read from a source becomes a dated, frozen forecast row** (source,
timestamp, ticker, extracted claim/direction) and is scored later against
the realized move at fixed horizons — exactly what `predictions.jsonl` and
`forecast_reputation.py` already do for forecasters. Point that same
machinery at *sources* instead of (or alongside) *personas*, and each source
earns its own held-out reliability weight, by regime and by horizon, the same
way §64 found a process forecaster at +8.97% against nine personas at
−27.98%. A source registry is not a new subsystem; it is `forecast_reputation`
with `source_id` added as a grouping key.

### C.4 Starting set, ranked by expected information per dollar

1. **SEC EDGAR full-text search + Form 4 / 13F** — free, primary, government
   data; the insider/fundamentals channel this system's own backtests
   already call "GO."
2. **Congressional trading disclosures (STOCK Act)** — free, primary, zero
   ToS friction; thinner academic base but zero cost.
3. **Analyst revision data** — moderate cost, already shown valuable in
   Aegis's own revision-flow backtest, with independent academic backing
   (item B.19, B.3 #14).
4. **8-K / press-release feeds** — free-to-cheap; von Beschwitz et al. find
   the RavenPack effect is *largest for press releases specifically* — the
   cheapest way to capture that effect without paying for RavenPack.
5. **Company IR pages / earnings-call transcripts** — free-to-cheap; targets
   the "fundamentals-focused stories" channel Tetlock et al. (2008) found
   carries the strongest, most durable signal; also the direct input to
   Larcker-Zakolyukina-style deception scoring and Siano-style LLM text
   mining (B.15, B.24).
6. **WSJ / Dow Jones Newswire** — ~$40/mo; the only source here with a
   40-year, two-paper academic pedigree showing measurable (if
   cost-fragile) signal — real ToS friction for automation, so read at
   human pace, not bulk-ingested.
7. **SeekingAlpha** — free-to-cheap; the strongest positive result for a
   low-cost text source, predicting both returns and earnings surprises
   without WSJ's reversal.
8. **Reddit / WallStreetBets** — free but low expected information per unit
   of analyst/LLM effort; real evidence exists only in mania regimes and a
   handful of accounts. Worth a cheap monitoring feed, not a research
   budget line — Murat's skepticism is well-founded.
9. **Yahoo Finance** — free; keep for prices and consensus
   estimates/analyst-rating aggregation (Zhang's dispersion-conditioned
   result), not as a news-content source — none of the predictive-news
   literature is actually about Yahoo's own journalism.
10. **RavenPack / commercial news analytics** — expensive; its own best
    evidence shows the edge concentrated at millisecond/HFT speed and in
    small/illiquid names — likely low marginal value at LLM-cadence
    research speed relative to cost. Lowest priority to add now; a
    Bloomberg terminal would rank below this for the same reason — its
    documented edge belongs to sub-second traders, not overnight research.

---

## Sources for this note

Full source lists with links are inline in each part above. The three
research passes used WebSearch where available and `mcp__exa__web_search_exa`
/ `mcp__exa__web_fetch_exa` / WebFetch as fallback; Bigdata.com was skipped
per instruction (out of credits).
