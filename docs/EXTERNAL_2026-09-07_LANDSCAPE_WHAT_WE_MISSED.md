# External Landscape Report for Aegis Finance

Compiled 2026-09-07 from web search/fetch. Every entry: what it is, what it does that is distinctive, evidence quality, URL, and a one-line "gap for Aegis". Items I could not confirm are marked **UNVERIFIED**. Nothing here was written under the repo.

Context assumed: Aegis has CRSP/IBES/TAQ 1999-2024, Alpaca paper accounts, Alpaca/Benzinga news + EDGAR 8-K, LightGBM + small NNs, DeepSeek only, no strategy beating SPY after honest statistics; diagnosis = weak prediction information, portfolio construction/holding destroyed part of it, event data incomplete, no winner/loser autopsy pipeline.

---

## A. Winning hackathon projects

### A1. Alpaca AI Trading Agents Hackathon (lablab.ai, 28 Aug - 4 Sep 2026) — the one Aegis entered
- **What**: 7-day online hackathon, Alpaca Trading API + MCP server/CLI, paper trading only, single track "Options Alpha Agents" (351 submissions), $5,000 pool (1st $2,500 / 2nd $1,500 / 3rd $1,000) + 2 social awards.
- **Scale**: 427 projects, 1,269 teams, 3,602 participants, 752 community votes. Status on 2026-09-07: **"judging in progress"; official winners NOT published** (UNVERIFIED which projects placed).
- **Community-vote leaders** (not judge results): 1) *Alpha Hunter — Autonomous AI Trading Scientist* (145 votes), 2) *TradePilot AI* (132), 3) *QASIX* (36).
- **Recap page**: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon · live/results page: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live
- **Notable entries with disclosed P&L (all self-reported, 2-5 sessions, paper)**:
  - *Alpaca Options Trading Agents* (Miramar Labs): three-agent "trading floor" on k3s + Ollama qwen2.5-32B, LLM proposes one contract, deterministic re-validation, 8 gates. Reported +3.7% ($103,709 on $100k) by 3 Sep close. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/miramar-labs/alpaca-options-trading-agents
  - *Glass Box Trading*: LLM has "no code path to an order", 8 fixed-order gates, append-only public journal; +$583.59 (0.58%), openly states 61% came from one QQQ call and names two defects. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/glass-box-trading/glass-box-trading
  - *NorthStar* (lovepsy): goal-first ("where do you want to end up"), Monte Carlo honesty check, 22-rule gate; **-7.04%** for the week, root-caused in the write-up. Uses TimesFM. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/lovepsy/northstar-an-ledger-ai-trading-agent-on-alpaca
  - *EasoLab*: weekly SPY iron condors, VRP+skew filter, "backtested Sharpe 2.53 / 90.9% win" on one year of Alpaca option data; explicitly reports 4 directional strategies that failed to beat the index. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/easo-lab/easolabs-alpaca-ai-trading-agent
  - *FLINCH* (Convex): "code proposes, model disposes" — LLM restricted to VETO/SIZE_DOWN/APPROVE, 11 gates, own Black-Scholes for 0DTE. https://lablab.ai/submissions/vwt9bvsrimtnx4exhe5z0e63
  - *TradeProof* (earlgreyroom): whole-universe scan (6,171 optionable names -> 1 passed edge threshold), 23 gates, **prepared 124 trades and submitted none**, every refusal logged. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/earlgreyroom/tradeproof
  - *Alpha Hunter* (vote leader): "Discover -> Test -> Challenge -> Score -> Allocate -> Execute -> Monitor -> Learn", adversarial LLM tries to break candidate strategies, Edge Score, capital allocation across surviving strategies. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/crazyxyz/alpha-hunter-autonomous-ai-trading-scientist
  - *Aizen*: 9-agent LangGraph, 3 XGBoost models + GATv2 GNN over option chain, supervisor vetoes disagreement. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/aizen-syndicate/aizen-autonomus-trading-agent
- **Evidence quality**: none of this is evidence of edge — self-reported, days-long samples, no benchmark or cost accounting. The convergent *design* pattern is the information: (i) LLM narrates/proposes, deterministic code decides; (ii) hash-chained or append-only decision journals including refusals; (ii) honest disclosure of failures; (iv) options-first with defined risk.
- **Gap for Aegis**: architecture parity is already there; what most top entries have that Aegis lacks is a *public read-only cockpit* and a single end-to-end worked example (one decision, rejected alternatives, graded outcome) at the top of the write-up.

### A2. Prior lablab trading track: AI Agent Olympics / Kraken Trading Performance (Milan, 13-19 May 2026)
- Winners (Kraken track, ranked *solely* by net PnL audited via read-only API key): 1) **Kraken Alpha Agent** (Damso74) — +$19.18 over 10 trades, 80% win rate, 0.06% max DD, **and it was a backtest** because xStocks execution was venue-blocked; 2) *Trading AI Agent* by Falcon; 3) *Bee Sentinel-X*. Repo: https://github.com/Damso74/kraken-alpha-agent · Recap: https://lablab.ai/ai-hackathons/milan-ai-week-hackathon · Winners post: https://www.linkedin.com/posts/lablab-ai_728-teams-266-ai-applications-one-week-activity-7467171942928871424-vsHH
- **Gap for Aegis**: the P&L bar at these events is tiny; auditability and candour decided it. Already in Aegis memory (`reference_lablab_judge_rubric.md`).
- **UNVERIFIED**: I found **no 2025 lablab/Alpaca edition**; the 2026 event appears to be the first Alpaca-branded lablab hackathon. Earlier lablab trading tracks were Kraken/Surge (Mar-Apr 2026, $55k) and the Milan event.

### A3. Kaggle finance competitions (2024-2026)
- **Jane Street Real-Time Market Data Forecasting** (Oct 2024-2025): 79 anonymised features, 9 responders, target responder_6, live forecasting API. Winner: Team Patrick Yam (Yam is an ML quant at Jane Street). Walkthrough video https://www.youtube.com/watch?v=lfzzPZZyzjE · competition https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting . **UNVERIFIED** details of the winning method (video not transcribed here); community consensus in that competition was GBDT/NN ensembles with online (rolling) refits on newest data.
- **Optiver Trading at the Close** (2023): LightGBM/XGBoost + heavy feature engineering on closing-auction imbalance; purged K-fold. 1st-place writeup: https://www.kaggle.com/competitions/optiver-trading-at-the-close/writeups/hyd-1st-place-solution
- **Hull Tactical Market Prediction** (Sep-Dec 2025, $100k): predict S&P 500 excess return under a volatility constraint; Hull's own "micro alphas" thesis. https://www.kaggle.com/competitions/hull-tactical-market-prediction · winner **UNVERIFIED** (not found).
- **DRW Crypto Market Prediction** (2025): https://www.kaggle.com/competitions/drw-crypto-market-prediction
- **Evidence quality**: leaderboard metrics are pure prediction (Pearson/R^2), not tradable P&L; but they are the best public evidence of *what works for weak-signal tabular finance*: GBDT ensembles, feature neutralisation, online refitting, purged CV.
- **Gap for Aegis**: Aegis already uses LightGBM; what Kaggle winners do and Aegis does not is **online/rolling refits on the newest data with era-aware validation** and ensembling of many weak models.

### A4. Other venues
- **QuantConnect Quant League** (student, quarterly, 2024 - Q4 2025, now ended): https://www.quantconnect.com/league/
- **FinRL Contests (ACM ICAIF 2023-2025)**: 230+ participants; tasks include "FinRL-DeepSeek" (LLM-engineered signals into RL). Results are backtests; the 2025 accepted-paper list is at https://finrl-contest.readthedocs.io/en/latest/finrl2025/accepted_paper.html · overview https://open-finance-lab.github.io/FinRL_Contest_2025/
- **IMC Prosperity, CUATS 2026 (QuantConnect live Jan-Feb 2026)**: https://www.cuats.co.uk/challenge2026/
- Databento/Polygon: no hackathon winners found (UNVERIFIED that any exist).

---

## B. Open-source frameworks and research systems

| System | What it is / distinctive | Evidence | URL | Gap for Aegis |
|---|---|---|---|---|
| **FinRL** (AI4Finance) | DRL library (PPO/A2C/DDPG etc.) over gym-style market envs; contests annually | Backtests only; RL in low-SNR non-stationary data poorly reproduced | https://github.com/AI4Finance-Foundation/FinRL | Skip RL as alpha source; steal only their *ensemble-of-agents* selection idea if ever needed |
| **Microsoft Qlib** | AI-oriented quant platform: PIT data handling, Alpha158/Alpha360 factor sets, model zoo (GBDT, TRA, HIST etc.), nested workflow | Mature; results on CSI300/US; strong PIT infra | https://github.com/microsoft/qlib | Their **Alpha158** is a ready-made 158-factor library — Aegis's composite is 99.5% one factor |
| **RD-Agent(Q)** (Microsoft) | LLM multi-agent loop that proposes factors, writes code, backtests in Qlib, iterates; joint factor+model optimisation | Paper: IC 0.0532, ARR 14.2% on CSI300 with GPT-4o-mini, "<$10 per run"; "2x return with 70% fewer factors" vs Alpha158; in-sample flavour | https://github.com/microsoft/RD-Agent · https://arxiv.org/abs/2505.15155 | This is the closest public system to "self-improving research loop"; DeepSeek can drive it. Adopt the *loop*, not the claimed numbers |
| **AlphaAgent** (KDD 2025) | LLM alpha mining with originality/complexity/hypothesis-alignment regularisers to fight alpha decay | ~37% cum. excess on S&P 500 test (backtest) | https://arxiv.org/abs/2502.16789 | Regularise for *originality* when generating hypotheses; otherwise LLMs regurgitate crowded factors |
| **Alpha-GPT / QuantAgent / QuantaAlpha / AlphaMemo / AlphaPROBE** | Family of LLM formulaic-alpha search papers (2023-2026) | All backtest, mostly China A-shares | https://aclanthology.org/2025.emnlp-demos.14/ · https://arxiv.org/abs/2602.07085 · https://arxiv.org/abs/2606.20625 | Same as above; evidence of *decay* is the useful part |
| **QuantConnect LEAN** | C#/Python event engine, huge data lake, live deploy | Production-grade | https://github.com/QuantConnect/Lean | Not needed with Alpaca + own farm |
| **NautilusTrader** | Rust-core event-driven backtest + live parity | Production-grade | https://github.com/nautechsystems/nautilus_trader | Only if execution realism becomes the bottleneck |
| **vectorbt / backtrader / zipline-reloaded** | Vectorised research / event-driven retail / Pipeline API factor research | Mature | https://github.com/polakowo/vectorbt · https://github.com/mementum/backtrader · https://github.com/stefan-jansen/zipline-reloaded | Aegis's farm already covers this |
| **alphalens / pyfolio (reloaded)** | IC-by-quantile, turnover, decay-by-horizon tear sheets | Standard | https://github.com/stefan-jansen/alphalens-reloaded | Adopt the **IC-decay-by-horizon and turnover tear sheet** as the first screen for every signal |
| **Riskfolio-Lib / skfolio / PyPortfolioOpt** | Portfolio optimisers (HRP, CVaR, risk parity; skfolio is sklearn-compatible with CV) | Mature; PyPortfolioOpt lightly maintained | https://github.com/dcajasn/Riskfolio-Lib · https://github.com/skfolio/skfolio · https://github.com/robertmartin8/PyPortfolioOpt | skfolio's *cross-validated* optimisation fits Aegis's purged-CV habit |
| **OpenBB** | Open data/terminal aggregator (providers incl. FMP, Finnhub, SEC) | Tooling | https://github.com/OpenBB-finance/OpenBB | Data plumbing shortcut only |
| **Lumibot / Jesse / hummingbot** | Retail live-trading bots (Alpaca-native / crypto / market-making) | Tooling | https://github.com/Lumiwealth/lumibot · https://github.com/jesse-ai/jesse · https://github.com/hummingbot/hummingbot | Not relevant to alpha |
| **AI-Trader** (HKUDS) | Live benchmark of 6 LLMs across 3 markets, minimal-information paradigm; dashboard | Finding: "general intelligence does not translate to trading; most agents poor returns/weak risk mgmt" | https://github.com/HKUDS/AI-Trader · https://arxiv.org/abs/2512.10971 · https://ai4trade.ai | HKU-adjacent; a public arena Aegis's books could be scored against |
| **LiveTradeBench / Agent Market Arena** (UIUC) | Lifelong live benchmark; finding: *agent architecture* dominates *LLM choice* (swapping GPT-4o/Claude/Gemini moved less than swapping agent design) | 2-month live | https://github.com/ulab-uiuc/live-trade-bench · https://arxiv.org/abs/2510.11695 | Supports Aegis's DeepSeek-only stance; invest in architecture not model |
| **TradingAgents** (Tauric) | Most-starred (80k+) multi-agent LLM trading repo | Backtest Jan-Mar 2024 on 5 mega-caps; **documented look-ahead leaks** (issue #203; v0.3.1/0.4.0 "point-in-time fixes") | https://github.com/TauricResearch/TradingAgents · https://github.com/TauricResearch/TradingAgents/issues/203 | Do not copy; use as the canonical example of leakage in LLM agents |
| **FinMem / FinAgent / StockAgent / InvestorBench / FinPos** | Layered-memory LLM agents; benchmarks | Backtests inside LLM knowledge windows | https://arxiv.org/abs/2412.18174 (InvestorBench) · https://arxiv.org/abs/2510.27251 (FinPos) | Ignore headline returns; see C for why |
| **Kronos** (AAAI 2026) | Decoder-only foundation model on 12B K-lines from 45 exchanges, hierarchical OHLCV tokenizer | RankIC +93% vs best TSFM on their benchmark (China-heavy) | https://arxiv.org/abs/2508.02739 · https://huggingface.co/NeoQuasar/Kronos-base | Cheap to fine-tune as *one more independent selector book*, not as a weight |
| **Chronos / TimesFM / Moirai / TimeGPT** | General TSFMs | 2026 benchmark on 5 US mega-caps: TSFMs rank well *relative to each other* but beat random walk only in 2 of 10 cases (Diebold-Mariano) | https://arxiv.org/abs/2606.27100 | Do not expect return forecasting from zero-shot TSFMs; TimesFM was in NorthStar (-7%) |

---

## C. LLM look-ahead / memorisation in financial backtests

**What is established (2023-2026):**
1. **Memorisation is real and masking fails.** Lopez-Lira, Tang & Zhu (2025), *The Memorization Problem: Can We Trust LLMs' Economic Forecasts?*: models reproduce pre-cutoff macro/financial values near-verbatim; **instructions to "respect the date" and masking do not stop recall**; LLMs "see through" anonymisation in long documents. (Cited via Gao-Jiang-Yan below.) Sarkar & Vafa (2024), *Lookahead Bias in Pretrained Language Models*: https://www.researchgate.net/publication/379767258_Lookahead_Bias_in_Pretrained_Language_Models
2. **Anonymising headlines gave a *partial* fix.** Lopez-Lira & Tang (2023) ChatGPT-returns paper; Glasserman & Lin (2023) *Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis*: anonymised headlines cut but did not remove the gap. https://arxiv.org/abs/2309.17322
3. **Entity-neutering** (Engelberg et al. 2025) — LLM strips names/dates before the forecasting LLM sees the text: reduces recognition, leaves subtler channels.
4. **Detection tests exist.** Gao, Jiang & Yan (2025/26), *Detecting Lookahead Bias in LLM Forecasts*: a statistical test comparing forecast accuracy pre/post cutoff. https://arxiv.org/abs/2512.23847
5. **Chronologically consistent LLMs are the clean fix.** He, Lv, Manela & Wu (2025) *ChronoBERT / ChronoGPT*: models trained only on text up to a date, released as a **suite of yearly cutoffs on Hugging Face**; in a next-day-return-from-news test they match a much larger Llama's Sharpe, implying look-ahead bias in the Llama result was *modest* for that task. https://arxiv.org/abs/2502.21206 · https://huggingface.co/manelalab/chrono-bert-v1-20181231 (weights, per-year checkpoints exist under `manelalab/`). Lopez-Lira is not an author.
6. **Point-in-time commercial LLMs + benchmark.** *Look-Ahead-Bench* (Jan 2026): Llama-3.1 and **DeepSeek 3.2** show significant alpha-decay-style look-ahead bias versus PiT models. https://arxiv.org/abs/2601.13770 · code https://github.com/benstaf/lookaheadbench
7. **Agents leak through tools, not just weights.** *Profit Mirage* (Oct 2025): returns of LLM agents "evaporate once the knowledge window ends"; introduces FinLake-Bench and counterfactual perturbation (FactFin). https://arxiv.org/abs/2510.07920 . TradingAgents issue #203 shows tool-level leakage (future-dated reports) even where the model is fine.

**What works / does not (practical):**
- Works: (a) evaluate *only after* the model's training cutoff (DeepSeek-V3.x: cutoff ~mid-2024; check per model) — Aegis's forward paper books already do this; (b) use ChronoBERT/ChronoGPT checkpoints for any *historical* news backtest 1999-2024; (c) run the Gao-Jiang-Yan pre/post-cutoff accuracy test as a gate; (d) counterfactual perturbation of the input (change the number, does the call flip?); (e) freeze tool outputs into dated snapshots (Profit Mirage / TradingAgents lesson).
- Does not work alone: anonymising tickers/names, shifting dates, "forget everything after X" prompts (matches Aegis's own TRIAL-LLM-AMNESIA-1 finding).
- **Gap for Aegis**: Aegis knows this at the level of the AMNESIA trial; it has not adopted ChronoGPT for historical news scoring nor the post-cutoff detection test as a CI gate.

---

## D. Learning from other investors (public tracked accounts)

### D1. 13F "best ideas" literature
- **Cohen, Polk & Silli (2009) / Antón, Cohen & Polk (2021) "Best Ideas"**: the single highest-tilt holding per active manager outperforms the market by ~2.8-4.5%/yr; the rest of the portfolio does not. Best ideas skew small, high-beta, high-momentum. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364827 · https://personal.lse.ac.uk/polk/research/bestideas.pdf
- **Angelini, Iqbal & Jivraj (2019) "Systematic 13F Hedge Fund Alpha"**: hedge-fund conviction+consensus book beats S&P 500 by 3.8%/yr, Sharpe 0.75, 2004-2019 (Barclays/Novus index). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3459526
- **Brown & Schwarz**: abnormal volume/returns right after 13F release (copycats), *little long-term benefit*. https://www.ssrn.com/abstract=1683628 . Cao et al.: disclosing funds lose ~2.56 pp/yr to copycats/front-runners.
- **Clone ETFs realised**: GURU (Global X, 2012) and ALFA (AlphaClone, 2012) beat SPY in year one, then **underperformed by ~1.3-1.6%/yr with higher vol over ~10 years** (CFA Institute 2021 review). https://blogs.cfainstitute.org/investor/2021/09/22/does-guru-investing-work/ · https://www.globalxetfs.com/funds/guru
- **Congress ETFs**: NANC +88% vs KRUZ +73% from Feb-2023 inception to Apr-2026; NANC beat VOO by ~7 pp, KRUZ lagged by ~8 pp — i.e. tech-heavy Democrat holdings = beta, not information. https://www.morningstar.com/funds/2-etfs-that-track-congressional-stock-trades · https://www.etf.com/sections/etf-basics/nanc-vs-kruz-battle-congress-stock-trackers
- **Gap for Aegis**: the tested, replicable version of "learn from experts" is **max-tilt-per-manager**, not "what famous funds hold". Free SEC 13F data (below) is enough to build it as a separate `PRODUCT_EXPERIMENT` book; expect small-cap/momentum beta and a 45-day lag.

### D2. Aggregators / copy-trading
- **Dataroma** (free, 83 "superinvestors", scraped from 13F): https://www.dataroma.com/m/managers.php
- **WhaleWisdom** (13F back to 2001; API on paid tiers $300-$500/yr, 50-200 filers/quarter): https://whalewisdom.com/help/api
- **Quiver Quantitative** (congress/insider/lobbying; API from $30/mo; free dashboards only): https://api.quiverquant.com/datasets/congress-trades
- **eToro Popular Investors**: academic study on 2011-2013 data (popularity vs performance) https://arxiv.org/abs/1406.7729 ; copiers' timing drag documented. **Collective2**: hypothetical track records, monthly "C2 Score" snapshots https://collective2.com/datastudies/strategyAUM . **Composer**: rule-based "symphonies" https://www.composer.trade/learn/how-composer-symphonies-work . Alpaca has no first-party social/copy API (UNVERIFIED beyond docs; Alpaca Broker API supports omnibus/sub-accounts which third parties use for copy trading).
- **Gap for Aegis**: none of these are evidence sources; Dataroma is a free convenience for a best-ideas book.

### D3. Insider (Form 4) alpha literature
- **Cohen, Malloy & Pomorski (2012) "Decoding Inside Information"**: split insiders into *routine* (same calendar month 3 yrs running) vs *opportunistic*; opportunistic trades earn **82 bp/month VW abnormal**, routine ~0. Most informed: local, non-executive insiders at poorly governed, geographically concentrated firms. https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2012.01740.x · NBER WP https://www.nber.org/system/files/working_papers/w16454/w16454.pdf
- **Gap for Aegis**: Aegis's insider collector exists but treats all trades alike; the *routine-vs-opportunistic* classifier is a two-line rule on the free SEC dataset below and is the single most-cited insider signal.

### D4. Free, historical SEC bulk data — confirmed
| Dataset | Coverage start | Cadence | Format | URL |
|---|---|---|---|---|
| **Insider Transactions Data Sets** (Forms 3/4/5, XML portion, flattened) | **2006 Q1** (`2006q1_form345.zip`) | Quarterly (post-5:30pm ET last business day -> next quarter) | ZIP of tab-delimited tables (SUBMISSION, NONDERIV_TRANS, DERIV_TRANS, etc.; readme PDF) | https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets · readme https://www.sec.gov/files/insider_transactions_readme.pdf |
| **Financial Statement Data Sets** (XBRL numeric, sub/num/pre/tag) | **2009 Q1** (first file empty; real rows from 2009 Q2) | Quarterly | ZIP, tab-delimited | https://www.sec.gov/dera/data/financial-statement-data-sets.html · archive https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets-archive |
| **Financial Statement *and Notes* Data Sets** (adds text blocks/notes, 8 tables) | 2009 Q2 | Quarterly (was monthly Nov-2020 to 2024) | ZIP + W3C metadata | https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets · readme https://www.sec.gov/dera/data/fsnds.pdf · python `secfsdstools` https://pypi.org/project/secfsdstools/ |
| **Form 13F Data Sets** (XML info tables) | **2013 Q2 (July 2013)** | Quarterly | ZIP (SUBMISSION, COVERPAGE, INFOTABLE...) | https://www.sec.gov/dera/data/form-13f (announcement 2022) |
| **EDGAR Full-Text Search (EFTS) JSON API** | **4 May 2001** onward, all form types incl. SC 13D/13G | Real-time | JSON (`efts.sec.gov/LATEST/search-index?q=...&forms=SC 13D`) | https://efts.sec.gov/LATEST/search-index (documented at https://www.sec.gov/edgar/search/) |
| **EDGAR full/daily index files** (`form.idx`, `master.idx`, all filings by form type since 1993) | 1993 | Daily/quarterly | text/gz | https://www.sec.gov/Archives/edgar/full-index/ |
| **Schedules 13D/13G structured XML** | Mandatory from **18 Dec 2024** (new form types `SCHEDULE 13D`, `SCHEDULE 13G`); pre-2025 filings are HTML/text only | Real-time | XML per filing (no DERA bulk set found — UNVERIFIED) | https://www.sec.gov/submit-filings/edgar-news-announcements/edgar-release-23-4 · https://www.olshanlaw.com/newsroom/alerts/client-alert-important-reminder-schedules-13d-and-13g-must-be-filed-using-structured-machine-readable-xml-based-language-beginning-december-18-2024 |
- No free *parsed* historical 13D/13G dataset was found (sec-api.io and edgar.tools are paid). For 1999-2024 the path is EFTS/index files + own parser of the cover page (percent of class, item 4 purpose).
- **Gap for Aegis**: Insider (2006-) and 13F (2013-) bulk sets are free and quarterly — enough to close "event data incomplete" for insider/holder events without WRDS.

---

## E. How professionals do it (public and credible)

- **Numerai**: free obfuscated dataset, users submit predictions; **Stake-Weighted Meta Model** aggregated into a portfolio through an optimiser with hundreds of risk neutralisations. Scoring history: CORR -> **TC (True Contribution** = gradient of optimised portfolio return w.r.t. stake, via differentiable convex optimisation) -> Nov-2023 return to **MMC only** (contribution after neutralising to the meta-model) plus **BMC** (vs benchmark models). Key ideas cheap to copy: **per-era scoring** (Sharpe = mean/sd of per-era corr), **feature neutralisation** (regress predictions on features, keep residual), **era-boosting** (upweight worst eras), and scoring a signal by its *marginal* contribution to an ensemble. https://docs.numer.ai/numerai-tournament/scoring/true-contribution-tc · https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc · forum change notice https://forum.numer.ai/t/changing-scoring-payouts-again-to-mmc-only/6794/ · Signals (bring-your-own-data) https://docs.numer.ai/numerai-signals/signals-overview
- **WorldQuant BRAIN**: free web platform where "consultants" build formulaic alphas scored on Sharpe/turnover/correlation-to-existing-pool; alpha *pooling* = many low-correlation weak alphas. Public artefact: Kakushadze (2016) *101 Formulaic Alphas* (mean pairwise correlation ~16%, most hold days-not-months). https://arxiv.org/abs/1601.00991 · python impl. https://github.com/lvlh2/alpha101 · platform https://platform.worldquantbrain.com
- **AQR** — *Fact, Fiction and Momentum Investing* (2014): momentum survives costs, is robust across 200+ years/markets, works best combined with value (corr -0.4); small-cap momentum tradeable. https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Momentum-Investing.pdf · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2435323
- **Renaissance** — Mercer: "We're right 50.75% of the time, but we're 100% right 50.75% of the time" — edge is a slight, *consistent* tilt across thousands of simultaneous positions; the lesson is breadth and consistency, not accuracy. https://www.acquired.fm/episodes/renaissance-technologies
- **Man AHL / Oxford-Man Institute** — publish real methods: *Slow Momentum with Fast Reversion* (change-point detection + LSTM; +33% Sharpe 1995-2020, +66% 2015-2020) https://arxiv.org/abs/2105.13727 · code https://github.com/kieranjwood/slow-momentum-fast-reversion ; *Momentum Transformer* https://arxiv.org/abs/2112.08534 ; OMI papers list https://oxford-man.ox.ac.uk/selected-publications/
- **Bridgewater AIA Labs**: $2B ML-driven macro fund (launched Jul-2024, reportedly +11.9% in 2025), uses OpenAI/Anthropic/Perplexity LLMs behind multi-layer guardrails "reducing error rates from 8% to 1.6%". https://fortune.com/2024/07/01/bridgewater-2-billion-fund-machine-learning-decision-making-openai-anthropic-perplexity (2025 return figure UNVERIFIED beyond secondary sources)
- **Two Sigma**: publishes conference reviews (ICML 2025) and alt-data examples (satellite parking lots -> earnings), no strategy detail. https://www.twosigma.com/type/research/ . **D.E. Shaw**: public research is the biochemistry arm; nothing on trading.
- **Lopez de Prado**: triple-barrier labels, meta-labeling (secondary model sizes/vetoes a primary signal), CPCV, **Deflated Sharpe Ratio**, **PBO**; *10 Reasons Most ML Funds Fail*. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 · https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf . Independent 2024 study: CPCV has the lowest PBO among OOS methods in a synthetic control. https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110
- **Harvey, Liu & Zhu (2016)** *...and the Cross-Section of Expected Returns*: new factor must clear **t > 3.0**; most published findings likely false. https://academic.oup.com/rfs/article/29/1/5/1843824
- **What a one-person system can copy cheaply**: (1) per-era metrics + era-boosting; (2) feature-neutralised predictions; (3) marginal-contribution scoring of each new book against the ensemble (MMC-style) — this is precisely Aegis's "are its errors different errors?" question, formalised; (4) alpha pooling of many *fast, weak, low-correlation* signals (WorldQuant) rather than one 12-1 momentum; (5) meta-labeling as the "when to act on a signal" layer; (6) DSR/PBO — already in Aegis.
- **Gap for Aegis**: Aegis has the gates (DSR, PBO, Holm) but not the *production* habits: neutralisation, era-weighting, and MMC-style marginal scoring of each candidate book.

---

## F. Data sources / scrapers for a small budget

| Source | What / free? | Coverage | URL | Gap for Aegis |
|---|---|---|---|---|
| SEC bulk (see D4) | Free | 2006-/2009-/2013- | above | Insider routine/opportunistic + 13F best-ideas |
| **Google Trends** | Official API is **alpha, application-gated (Jul 2025)**, 5-yr rolling window; unofficial `pytrends` rate-limited | 2004- (web UI) | https://developers.google.com/search/blog/2025/07/trends-api | Attention proxy; apply for alpha |
| **Wikimedia Pageviews REST API** | Free, no key, per-article daily/hourly | **2015-07** onward (older via pagecounts dumps) | https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/ | Cleanest free attention series; Moat et al. 2013 result had data-mining issues — test as a *conditional* precursor (spike before event) |
| **Reddit** | Pushshift closed May-2023; **Arctic Shift** free API + dumps; Academic Torrents monthly dumps | 2005-2025 | https://github.com/ArthurHeitmann/arctic_shift · https://academictorrents.com/details/5d0bf258a025a5b802572ddc29cde89bf093185c | WSB attention-herding events (see H) |
| **StockTwits** | API access restricted since 2023 (UNVERIFIED current terms) | — | https://api.stocktwits.com | Skip |
| **Polymarket** | Gamma API (metadata) + CLOB API (prices/books) **free, no key for reads**; Data API for trades | 2020- | https://docs.polymarket.com | Event-probability sensor for macro/earnings/policy questions |
| **Kalshi** | Public REST v2 incl. `/historical/markets/{ticker}`, trades, orderbook; no key for reads | 2021- | https://docs.kalshi.com/getting_started/quick_start_market_data | Same; US-regulated, more macro (CPI, Fed) |
| **FINRA short interest** | Free, bi-monthly, CSV/JSON via `api.dapi.finra.org`; OTC text archives | ~2010s- (API); consolidated file | https://www.finra.org/finra-data/browse-catalog/equity-short-interest · API pdf https://www.finra.org/sites/default/files/Equity_Short_Interest_Data_File_Download_API.pdf | Cheap; Aegis lacks a short-interest feature |
| **Cboe** | Daily market statistics free (volume/OI aggregates); everything granular is paid DataShop | — | https://www.cboe.com/markets/us/options/market-statistics/daily/ | Free put/call ratio only |
| **ORATS** | Paid only (EOD since 2007, 1-min since 2020); samples on ORATS University | 2007- | https://orats.com/faq | Skip; Alpaca option chain + OptionMetrics (WRDS) already |
| **Earnings-call transcripts** | EarningsCalls.dev (free, 2020-); FMP free tier; Finnhub; API Ninjas (2005- on paid); Motley Fool scrape | 2020- free | https://earningscalls.dev/ · https://finnhub.io/docs/api/earnings-call-transcripts-api | Needed for H (scripting/evasiveness/tone) |
| **Analyst targets** | Finnhub/FMP free tiers (limited); IBES already on WRDS | — | https://site.financialmodelingprep.com/datasets/analyst-estimates-targets | Already covered by IBES |
| **ETF flows** | etf.com fund-flows tool, ETFdb, ICI weekly (free, aggregate); per-ETF daily needs scraping | — | https://www.etf.com/etfanalytics/etf-fund-flows-tool · https://www.ici.org/research/stats/combined_flows | Low priority |
| **FRED** | Free API | 1900s- | https://fred.stlouisfed.org/docs/api/ | Presumably in use |
| **GDELT** | Free; events + GKG every 15 min, 100+ languages; BigQuery public dataset; DOC 2.0 API for article search | 2015- (2.0), 1979- (events 1.0) | https://gdeltproject.org/data.html | The only free *whole-market, multilingual* news firehose — matches the VISION "whole-market news, Asia first" |
| **HKEX news** | HKEXnews announcements searchable/scrapable; IIS real-time feed is paid | 2000s- | https://www1.hkexnews.hk/search/titlesearch.xhtml | Asia-first coverage; free scraper exists on Apify |
| **Nikkei Asia RSS** | Free headlines (personal use terms) | — | https://info.asia.nikkei.com/rss | Headlines only |
| **Caixin** | RSS availability UNVERIFIED; RSSHub routes exist for Chinese media | — | https://rsshub.netlify.app/routes/traditional-media | UNVERIFIED |
| App downloads / job postings / web traffic | Sensor Tower, Apptopia, SimilarWeb, Coresignal, Revelio — all paid; free proxies: TheirStack 200 credits/mo, SimilarWeb free tier, company career-page scrapes | — | https://coresignal.com/alternative-data/job-postings-data/ | Only via own scrapers; low priority for a one-person system |

---

## G. Portfolio construction / holding evidence

- **Transfer coefficient** (Clarke, de Silva & Thorley 2002): IR = TC x IC x sqrt(breadth); constraints (long-only, turnover, caps) leak IR through TC. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=290322 . *Gap*: Aegis's diagnosis "construction destroyed part of the information" is literally a TC < 1 finding — measure TC per book.
- **Buy/hold spread (hysteresis)** — Novy-Marx & Velikov (2016) *A Taxonomy of Anomalies and Their Trading Costs*: stricter entry than exit thresholds is **the single most effective cost-mitigation technique**; anomalies with <50%/month turnover survive costs, few above do. https://academic.oup.com/rfs/article-abstract/29/1/104/1844518 · NBER https://www.nber.org/papers/w20721
- **Garleanu & Pedersen (2013)** *Dynamic Trading with Predictable Returns and Transaction Costs*: "aim in front of the target, trade partially toward the aim"; faster-decaying signals get down-weighted. Closed-form. https://nbgarleanu.github.io/DynTrad.pdf
- **No-trade bands** (NBIM 2018 note): band rebalancing lowers cost with no return penalty. https://www.nbim.no/contentassets/8cb41f89dce345f5a6a295238f7872fb/no-trade-band-rebalancing-rules-expected-returns-and-transaction-costs.pdf
- **Momentum horizon**: Novy-Marx (2012) — returns from t-12..t-7 predict better than t-6..t-2, especially among large liquid stocks ("momentum is not short-term"). https://www.sciencedirect.com/science/article/abs/pii/S0378426614003252 (rebuttal) ; original *Is momentum really momentum?* JFE 2012. Holding-period studies cluster at 3-12 month holds with formation+holding 14-18 months. https://link.springer.com/article/10.1007/s11408-022-00417-8
- **Ensembling across signals**: Gu, Kelly & Xiu (2020) — nonlinear ML (trees/NN) over ~100 characteristics doubles OOS R^2 vs linear; the *portfolio* gain comes from combining many weak predictors. https://academic.oup.com/rfs/article/33/5/2223/5758276 . Kozak-Nagy-Santosh *Shrinking the Cross-Section* (2020): L2 (ridge) shrinkage over many anomalies works OOS; L1 sparsity does not. https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301655
- **Rank/score-weighting vs cap-weighting**: MSCI/Vanguard notes — score-tilt weighting gives more factor exposure per unit tracking error; cap-weighting dilutes it. https://www.msci.com/www/blog-posts/how-portfolio-weighting-schemes/02143435907
- **Kelly under uncertainty**: shrink toward fractional Kelly as parameter uncertainty rises; Bayesian Kelly (Sukhov 2025) https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6195358 ; **Grossman-Zhou (1993)** drawdown-constrained growth (never below a fixed fraction of running max) and a 2026 Bayesian GZ variant https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6942459
- **Cutting losers vs holding**: Odean (1998) retail disposition effect (sell winners, hold losers) is costly. https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/areinvestorsreluctant.pdf . **Akepanidtaworn, Di Mascio, Imas & Schmidt (JF 2023) "Selling Fast and Buying Slow"**: institutional PMs show skill in *buys* but their *sells* underperform even random selling; selling is heuristic-driven (attention, recent extreme returns). https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13271 · NBER https://www.nber.org/papers/w29076
- **Gap for Aegis**: (1) measure TC per book; (2) implement buy/hold spread + partial-trade-toward-aim instead of full monthly re-sort (the "construction tax" in S38 is exactly what NMV fix); (3) treat the *exit* rule as a separate, tested model (meta-label on exits), since the literature says exits are where humans and books leak.

---

## H. Behavioural / psychology precursors that are testable

| Mechanism | Observable precursor (computable before the outcome) | Paper | Direction |
|---|---|---|---|
| **Attention-driven buying** (Barber & Odean 2008 *All That Glitters*) | Stock in news / abnormal volume / extreme 1-day return -> retail net buying next days | https://academic.oup.com/rfs/article-abstract/21/2/785/1607197 | Short-run buying pressure then reversal |
| **Robinhood herding** (Barber, Huang, Odean & Schwarz JF 2022) | Top-N daily increase in Robinhood holders (RH data 2018-2020; proxy today: WSB mentions, Wikipedia views) | https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13183 | **-4.7% 20-day abnormal** for top-bought names |
| **WSB attention herding** | Daily top-attention stocks on r/wallstreetbets (Arctic Shift) | https://www.sciencedirect.com/science/article/pii/S1057521924006537 | Sentiment sign flips next-month alpha; +1.03% for positive-sentiment herding names |
| **Wikipedia pageviews** (Moat et al. 2013) | Weekly view spikes on company pages | https://www.nature.com/articles/srep01801 | Flagged for in-sample selection; test only as conditional |
| **Manager vocal affect** (Mayew & Venkatachalam JF 2012) | Vocal-emotion score from call audio | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1171102 | Positive affect -> positive future unexpected earnings; analysts ignore negative affect |
| **Scripted / non-spontaneous Q&A** (Lee, TAR 2016) | Similarity between prepared remarks and Q&A answers | https://publications.aaahq.org/accounting-review/article-abstract/91/1/229/3799 | Higher scripting -> lower abnormal returns, downward analyst revisions |
| **Evasive / vague answers** (Straight Talkers and Vague Talkers, NBER w23425) | Vagueness/evasiveness lexicon on Q&A only | https://www.nber.org/system/files/working_papers/w23425/w23425.pdf | Evasiveness forecasts lower earnings and returns |
| **Financial tone** (Loughran & McDonald 2011) | LM negative-word share in 10-K/8-K | https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01625.x | Negative tone -> negative filing-period returns |
| **Analyst herding / career concerns** (Hong, Kubik & Solomon 2000) | Analyst age/experience, boldness = distance from consensus | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=142895 | Bold forecasts by experienced analysts carry more information |
| **Extrapolative expectations** (Greenwood & Shleifer 2014) | Survey expectations (Gallup, AAII, Shiller) correlate with past returns, *negatively* with realised returns | https://academic.oup.com/rfs/article/27/3/714/1610886 | Market-level timing sensor, not stock-level |
| **Disposition effect** (Odean 1998) | Fraction of stocks held at a gain vs loss in retail flow; price relative to purchase-price reference (capital gains overhang, Grinblatt-Han) | above | Overhang predicts momentum-like continuation |
| **Selling heuristics** (Akepanidtaworn et al. 2023) | Institutions sell on extreme recent returns regardless of information | above | Exits are where to look for mispricing |
| **Narrative economics** (Shiller 2017) | Epidemic-curve fit of a phrase's frequency (GDELT/Google Trends) | https://www.nber.org/papers/w23075 | Testable as contagion curve; no stock-level result yet |
| **Investor days** (Kirk & Markov) | Event occurrence + language | https://www.smu.edu/cox/academics/research-papers/20150924-markov-research-paper | Disclosure event; direction mixed |
- **Gap for Aegis**: Aegis has the VISION statement ("instinct as a typed hypothesis") but no implemented text-of-Q&A features. Scripting and evasiveness are free to compute from transcripts and are *precursors* by construction.

---

## (1) Twenty things Aegis has most likely missed — ranked

| # | Item | EV | Cost | Why |
|---|---|---|---|---|
| 1 | **Buy/hold spread + partial trade-to-aim** (Novy-Marx-Velikov; Garleanu-Pedersen) replacing full monthly re-sort | High | S | The literature's single best cost fix; matches the measured "construction tax" |
| 2 | **Measure transfer coefficient per book** and report it beside IC | High | S | Diagnoses exactly where information dies (construction vs signal) |
| 3 | **Insider routine-vs-opportunistic classifier** on free SEC 2006- data (Cohen-Malloy-Pomorski) | High | S | 82 bp/mo VW in the paper; Aegis already ingests Form 4 but does not split |
| 4 | **13F "best ideas" (max-tilt-per-manager) book** from free SEC 13F 2013- | Med-High | M | Replicated across mutual funds and hedge funds; expect small/momentum beta; independent selector |
| 5 | **MMC-style marginal-contribution scoring** of every new book vs the ensemble | High | S | Formalises "are its errors different errors?"; Numerai's production metric |
| 6 | **Feature neutralisation + era-boosting** in the learner | Med | S | Standard Numerai practice; cheap; targets the "5 rebound months" problem directly |
| 7 | **Exit rule as a separately tested model** (meta-label on sells) | High | M | Akepanidtaworn: exits are the untested half; the arms currently inherit exits from the entry signal |
| 8 | **ChronoGPT/ChronoBERT checkpoints** for any historical news scoring 1999-2024 | High | S | Only clean fix for LLM look-ahead; free weights |
| 9 | **Post-cutoff detection test (Gao-Jiang-Yan) as a CI gate** for every DeepSeek-scored feature | Med | S | Turns AMNESIA finding into a standing guard |
| 10 | **Earnings-call Q&A scripting/evasiveness features** from free transcripts (2020-) | Med | M | Documented precursors; free; fits "instinct as typed hypothesis" |
| 11 | **GDELT as the whole-market, Asia-first news layer** | Med | M | Free, multilingual, 15-min; the VISION's coverage-normalisation needs a denominator |
| 12 | **RD-Agent-style hypothesis->code->backtest loop driven by DeepSeek** with originality regulariser (AlphaAgent) | Med | M | Closest public "self-improving research" system; cheap per run |
| 13 | **Qlib Alpha158 factor set** as a breadth baseline against the 1-factor composite | Med | S | Instant 158 features; tests whether breadth, not cleverness, was missing |
| 14 | **FINRA short interest** feature | Med | S | Free, bi-monthly, absent from the feature list |
| 15 | **Robinhood/WSB attention-herding reversal** (-4.7%/20d) as a *short/avoid* filter via Arctic Shift + Wikipedia views | Med | M | Documented negative alpha; data free |
| 16 | **Polymarket/Kalshi event probabilities** as a sensor for macro/earnings state | Low-Med | S | Free reads; useful for regime tagging, unproven for stock selection |
| 17 | **Kronos fine-tune as one more independent selector book** | Low-Med | M | Best-in-class K-line model; evidence China-heavy |
| 18 | **skfolio cross-validated optimiser** for the sizing layer | Low | S | Sklearn-native, fits purged CV habit |
| 19 | **Public read-only cockpit + one worked decision with rejected alternatives** at the top of every write-up | Med (for judging/paper) | S | What every well-received hackathon entry has and Aegis does not |
| 20 | **Score Aegis books on AI-Trader (HKUDS) / LiveTradeBench arenas** | Low-Med | S | External, HKU-adjacent, live benchmark; free credibility for the paper |

Deprioritise: zero-shot TSFMs for returns (beat random walk 2/10), RL (FinRL), congress/guru ETF cloning (beta), paid alt-data (app/job/web), TradingAgents-style multi-agent LLM stacks (leakage-prone, architecture > model anyway).

## (2) What winning hackathon entries and real funds have in common that Aegis lacks

The entries that were rewarded (Kraken Alpha Agent, and the 2026 vote leaders) and the funds whose methods are public (Numerai, WorldQuant, AQR, Man AHL, Renaissance's one quote) converge on three things. First, **breadth of small, independent, weak edges** rather than one strong forecast: Numerai's meta-model, WorldQuant's pooled 101 alphas, Mercer's "right 50.75% of the time" across thousands of positions, Kaggle winners' ensembles of many models refit online. Aegis's books all select on one 12-1 momentum composite; its own diagnosis says so, and the fix is a pooling architecture with marginal-contribution scoring, not a better single model. Second, **the construction and exit layer is treated as a first-class research object**: Clarke-de Silva-Thorley measure how much information survives construction, Novy-Marx-Velikov and Garleanu-Pedersen show hysteresis and partial trading preserve it, Numerai neutralises and era-weights, and Akepanidtaworn et al. show that even skilled institutions lose their edge at the sell. Aegis measured a construction tax but still rebalances by full re-sort and inherits exits from entries. Third, **a single, public, auditable decision trail with the failures in front**: the Kraken winner led with what was venue-blocked; Glass Box named its two defects and the one QQQ call that made 61% of its P&L; TradeProof shipped 124 prepared and zero submitted trades with each failing gate named; Bridgewater's public story is guardrails that cut error rates, not returns. Aegis has the receipts and the hash chains internally, but no read-only cockpit and no worked example that shows one real decision, the five alternatives it rejected, and the graded outcome — which is exactly the phrase the lablab judge used to mark an entry down as "idea level".
