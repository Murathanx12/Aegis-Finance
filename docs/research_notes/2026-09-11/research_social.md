# Social Media Research: Retail Trading Strategies & Projects 2025-2026

## Access notes
- X/Twitter: no login search; try site:x.com web search, nitter mirrors (mostly dead 2025-26), syndication
- Threads: site:threads.net
- Reddit: site:reddit.com, old.reddit.com JSON endpoints
- LinkedIn: site:linkedin.com/posts (often blocked/thin)

## Raw findings (append as gathered)


## Batch 1 results
- Automated Trading Strategies (Substack) - runs live forward-tests, posts weekly. https://automatedtradingstrategies.substack.com/ - Q1/Q2/Q3 2025 forward test results, "found some champions" post. Forward test = simulated acct on live data, NOT real capital.
- Alpaca LLM agent projects on GitHub 2025: matthewchung74/llm_trader (multi-model GPT-4o/Claude/Gemini + Alpaca paper), MariumAhsan/agentic-trading-bot (RL + Alpaca paper sim), huygiatrng/AlpacaTradingAgent (LangGraph multi-agent, paper+live), quantinsti article "Agentic AI Portfolio Manager" (LLM news sentiment + quant signals + Alpaca exec).
- WSB attention -8.5% HPR finding: ScienceDirect "Dumb money? Social network attention herding..." — positions opened at peak WSB attention realize -8.5% HPR vs positive avg HPR. Also conflicting: arxiv 2301.00170 (WSB vs analysts) claims WSB avg returns competitive/beat analysts in some cases (methodology disputed - selection/survivorship issues likely).
- Discord communities: LuxAlgo (202,520 members - large but is a charting/indicator product community, high noise, not pure hypothesis gen), Quant Trading App (11,618), Quant Talk (2,864, some hedge fund members claimed), Quant Trade Edge (2,300).
- Job postings alt data: validated signal per industry sources (ExtractAlpha, JobsPikr) - predicts revenue/M&A/pivots ahead of earnings; hedge fund adoption 78%; Point72/Cubist hiring 70+ eng roles signal. Vendors: JobsPikr, Apify "Hiring Signal Tracker" (scraper-as-service).
- Congress trading: Pelosi +12% YTD 2025 vs SPX +10.22%; various trackers (pelositracker.app, quiverquant, capitoltrades, insiderfinance) claim outperformance; CNN Nov 2025 "traders will need new hero" (Pelosi retiring, disclosure ends). Trump claims insider info. NOTE: known academic finding not yet retrieved directly here - the "45-day lag" STOCK Act disclosure delay makes real-time copying impossible; need to fetch actual paper.


## Batch 2 results
- Congress trading lag: STOCK Act requires filing within 30-45 days of transaction; H.R.7008 passed House 232-198 (Jul 2026) would largely eliminate individual-stock trading by members going forward. Academic consensus: mixed/conflicting on post-2012 abnormal returns; 45-day lag creates temporal disconnect for copy-traders; returns from original transaction date unavailable to a copier acting after disclosure. Good "crowd is wrong" candidate.
- YouTube: "Trade Algo" channel (coding+backtesting). Medium "Quant Factory" series "Backtesting Popular Strategies from Youtube" - explicitly tests popular YT claims against real backtests (useful skeptic source). strategyarena.io "YouTube Strategy Tester" tool. Most YT strategy channels are discretionary/unreproducible per this search.
- Substacks: MomentumLAB (momentum stock rankings + backtest CAGR/Sharpe/DD), QuantSeeker (weekly research recap), Rogue Quant (same-weekday momentum on futures), Larry Swedroe's Substack (factor research, "Beyond the 12-1 Rule"), Quant Scientist Newsletter, quantjourney.substack.com, Quantocracy (aggregator "Quant Mashup" - meta-source of many quant blogs).
- Insider cluster buying: 3+ insiders buying within 30-day window = cluster buy; historically ~2x excess return of single buys; academic estimates 4-8%/yr excess (older lit) but "reduced but still measurable" post-2015; 2025 study (3.7M transactions) composite insider signal -> monthly alpha >=1% when combining role/size/clustering/R&D/history. Vendors: form4api.com, avantinsider.com, markettriage.com, insiderfinance.io.


## Batch 3 - exa access to reddit/X worked well (direct web search doesn't reach reddit/old.reddit via WebFetch - blocked; exa's cached index does)
- Composer.trade: symphony marketplace, sortable by backtested Sharpe/return/DD; $200M AUM Sep 2025, $10B+ YTD volume, Jan 2026 $1.6B monthly volume record. "2025 Symphony Year-in-Review" blog breaks down 10 symphonies live behavior. composer.trade/symphony is the live leaderboard-ish DB.
- QuantConnect: Alpha Streams (live colocated tick-fed track records, 80k quants); "Quant League" being replaced by "Strategies" platform Q4 2025.
- r/algotrading real posts found via exa (2025-2026):
  - u/Ok-Professor3726 "Reactivated my algo...Real money results" (Oct 2025) - ES futures, 2 lots, 6 trades/day, weekly P&L posted gross before commissions (+$1837.50/wk) - NO cost accounting shown.
  - u/Background_Egg_8497 "Update on my SPX Algo Project" (Nov 2025, 192 upvotes) - $25k acct, SPX 0DTE rules-based ensemble, +$13,802 in 2 months (~55%), added bootstrap/permutation testing, blowup risk estimated 20%->5%. Self-named "Falling Knife Project" - self-aware high risk.
  - u/Clicketrie "My first month live results" (Oct 2025) - monthly rebalance, momentum+value factors, claims 2.5x SPY in first month (tiny sample, single month = noise).
  - u/inspiredfighter "Live algo results after ~30 days trading BTC on Binance" (Aug 2025) - 20x leverage on $5 margin (toy size), had a live bug vs backtest mismatch initially.
  - u/JrichCapital "2025 performance, 2026 ready!" (Jan 2026) - dashboard built with Claude/vibe-coded, strategy undisclosed.
  - u/criptolibertari0 "2025 was my best year" - FX (XAUUSD, USDJPY), breakout strategy 2:1 RR, reduced pair count 32->2, +39% 2025, max DD 6.65%, cites Taleb's Antifragile.
  - u/Sweet_Brief6914 "bots up 30% since August, 6% over Christmas week" (Dec 2025) - commenters note H2 2025 was broadly bullish, so outperformance vs indices unclear/possibly beta.
- X/Twitter LLM-signal-following projects:
  - @aleabitoreddit "Serenity" - claims peak +501% annualized, ~122% sustained, 38+ tickers named, "Chokepoint theory" (AI/semiconductor supply chain small caps). Independent "Serenity Tracker" site found the headline 3,840% annualized figure came mainly from a few early small-cap AI/semi picks (survivorship/lucky-pick risk). A third party (FMZ Quant blog, blog.mathquant.com, July 2026) built a live system scraping her tweets via RSSHub + LLM signal extraction + Binance TradFi perp execution. Good example of "social signal -> typed hypothesis" pipeline design, with explicit "notify-only" mode before going live - good practice to cite.
  - @milesdeutscher thread (unrollnow.com mirror, Sep 2026): "I built a trading bot with Claude that printed +$168,236" using Claude Code, offers to share the prompt. No backtest/cost/live verification shown - classic unverifiable screenshot claim.
  - fintwit.ai / MWM app: aggregates 500+ X financial analysts into buy/sell signals with AI ranking - a productized version of "scrape fintwit, extract signal."
  - GitHub Layr-Labs/hypesignal: OSS crypto trading agent monitoring X influencers, LLM sentiment scoring, auto-trades on Hyperliquid.
  - GitHub BinayakJha/Xchange: Grok-AI-based platform, sentiment from X, OCR of options-flow screenshots (tracks @FL0WG0D unusual flow, @earnings_guy earnings tweets), natural-language trade execution.


## Batch 4
- LinkedIn "I built an AI trading agent" posts (2025-2026), mostly Alpaca "AI Trading Agents Hackathon" by lablab.ai:
  - Muhammad Hammad "OFFLeash" - guardrail/self-stopping agent, hackathon submission, GitHub linked. No live P&L reported.
  - Cynthia Nosiri "Devil's Advocate" - two-agent adversarial (propose/challenge) + code has final say, Alpaca API + MCP + GitHub Actions. No live P&L.
  - Vivan Rangra "Execution Agent" - execution-quality agent on Binance futures historical replay (aggTrades/bookTicker), research system w/ dashboard. Backtest/replay only, no live results claimed.
  - Kapil Tanwar - DQN reinforcement learning agent, simulated env only.
  - Rakshit Poonia - 4-philosophy multi-agent (value/macro/systematic/innovation) paper portfolios, real prices, explicitly "not deployable," feedback-seeking, not a live result.
  - Ahmad Mansur "replaced a $200K analyst" using DeepSeek reasoning - salesy/no verifiable results, likely lead-gen for a paid course.
  - Raj Pandav - n8n+OpenAI+Telegram agent, structured buy/sell/hold w/ stop/target, blog writeup, no track record shown.
  - Pattern: virtually ALL hackathon/LinkedIn "built an agent" posts show ARCHITECTURE, not audited live P&L vs SPY with costs. This is itself a finding for section 2/4.
- WSB earnings-play threads (self-graded, u/Mobile_Tism_420 series, Aug 2025): "top-comment" options plays win rate 57%, explicitly NOT accounting for options cost/IV/strike (self-admitted); a later post "blindly bet earnings this week, up 21%" - small sample, cherry-picked week, they acknowledge survivorship ("why didn't that person post the 100k [loss]").
- PEAD (post-earnings drift) academic-grade backtest, finlab.finance (Jun 2026), 2016-2026, 19,083 earnings events, liquid top-500: single-name PEAD is WEAK (+2.75%/yr annualized long-short, rank IC 0.012); beat-minus-miss spread ~1.97pp over 60 days, driven mainly by AVOIDING misses not chasing beats; only 48.3% of big beats outperform (right-tail driven). The tradable version instead uses SURPRISE BREADTH (% of universe beating >5%) as a regime/risk-on gate combined with QQQ 200dma + momentum, rotating into 3x leveraged ETFs (TQQQ/TECL) vs defensives (IEF/GLD/SHY): 39.5% CAGR, monthly Sharpe 1.57 (OOS 1.93), max DD -21.1%, BUT zero modeled costs and author admits research-window Sharpe (1.45) did NOT beat QQQ's own Sharpe (1.47) - edge concentrated in 2022+ OOS window. Good precise "crowd is directionally right (drift exists) but overstates the single-name tradability" citation.
- Sector rotation / macro regime content:
  - VolSignals (X, via Thread Reader) - daily 0DTE SPX gamma/dealer-positioning "morning prep" threads, technical/mechanistic (dealer gamma flip levels), no track record quantified, pure day-trading color.
  - Frank Trading (Substack, franktrading.substack.com) - detailed Merrill-Lynch-clock-style macro regime -> sector rotation playbook (paywalled after Part I), narrative-driven, no backtest shown.
  - r/TQQQ u/Wongkok "RVol Shifter Strategy" - realized-vol-based leverage shifting + 200SMA trend + credit-spread filter + 4-asset defensive rotation; 2-state 51.39% CAGR/-37.68%DD, 3-state 43.02%/-33.41%DD, backtest to 2007, ~70-172 trades — self-described "stress tested against curve fitting" but single-author, unaudited, no OOS/live confirmation, no costs mentioned.
  - r/tradingwizardai "bond rotation into VCLT" post - ETF flow-scanner-based rotation call (VGIT/IWD/VTV/VCLT inflows), essentially product marketing for TradingWizard.ai tool, thin evidence.
  - Macro Manv (manveersahota.substack.com) - vol-control fund flow modeling (systematic vol-targeting fund rebalancing flows as a forecastable driver of realized vol/summer chop) - legit institutional-flow mechanism, cites MacroTourist.


## Batch 5
- BUY THE DIP - crowd wrong candidate confirmed strongly:
  - AQR "Hold the Dip" (2025 paper, 196 BTD variants, S&P500 1965-Sep2025): BTD underperforms buy-and-hold; avg Sharpe -0.04 vs passive (-16% degradation) full sample, -0.27 (-47%) since 1989; trend-following (SG Trend Index) beats BTD on both return and behavior-in-drawdowns; BTD is "anti-momentum."
  - Bonini/Shohfi/Simaan 2023 (eufm.12465): BTD optimality is condition/estimation-risk-sensitive, doesn't reliably beat cash/buy-hold.
  - Robinhood paper (SSRN 4112307): retail "buy-the-dip effect" documented empirically as a behavior driver, tied to WSB sentiment; predicts short-horizon (1mo) returns/price discovery - so BTD flow itself can be informative even if the strategy isn't optimal for the retail trader doing it.
  - S&P Global 2018: index-level 10%+ single-day-dip BTD in Russell 1000 DOES show positive significant excess returns 2002-2017 (up to 28% cum over 240 days) - so index/broad-basket dip-buying with institutional-ownership/trend/valuation overlays can work; contradicts naive "BTD never works" - nuance: works better as a broad reversal factor with quality filters, not as blind single-name dip buying.
  - Summitward/PWL Capital: only 1.14% of months are ATH->10% drop within 12mo, so "wait for the dip" cash-drag mostly never gets deployed.
  - Bessembinder: most individual stocks underperform T-bills lifetime; single-stock dip-buying conflates "discount" with "permanent impairment."
  - papersforquanttraders.substack (Yin & Zou paper, 2017-2024 actual retail flow data): retail DOES buy dips (asymmetric - buys after losses, doesn't sell after gains equally); driven likely by absorbing institutional forced-selling; does NOT establish it's profitable for retail (no realized return/cost data in the flow study).
- Discord quant communities: QuantQuestionsIO (5,505 members, career/interview focus), Quant Corner (1,060), Waterloo Quant Club (1,271, university-affiliated), "Quant Enthusiasts" via r/quant_hft (4,400+, mentorship/career focus). None of these are alpha-generation communities - all skew student/career/interview-prep, useful only as hypothesis-generation noise, not signal.
- Alt-data landscape (confirms and prices out the RFC brief's section d):
  - Market size: $18.74B (2025) -> $135.8B (2030) projected; hedge funds spend $1.6M+/yr avg on alt data (institutional scale, not retail-feasible).
  - Consumer transaction/card panels (Facteus, YipitData, Earnest Analytics, Second Measure/Bloomberg): T+2 to T+7 latency, $300K-$1.5M/yr per provider; academic: long-short return ~16%/yr from transaction signals; Earnest claims 90% earnings-surprise prediction accuracy (vendor claim, unaudited).
  - Geolocation/foot traffic (Placer.ai, Advan, PassBy): $150K-$600K/yr; PassBy claims 94% correlation to ground truth (self-reported, no independent audit found).
  - Satellite (Planet Labs, Maxar, Orbital Insight, RS Metrics): derived products $150K-$800K/yr (vs $1.5-3M to build in-house CV pipeline).
  - Sentiment/NLP (RavenPack, MarketPsych): cheapest, fastest (ms-sec latency), fastest alpha decay, "hardest to trade on."
  - Cheap/retail-accessible layer: AltIndex.com (Reddit mentions, web traffic, hiring, Glassdoor, app downloads, social followers -> composite AI score, has public daily leaderboards /toplist - LOW COST, good for retail-scale ingestion), HSH Data-on-Demand (hiring+insider+GitHub+Wikipedia+app rank+HN mentions composite, per-call API pricing, explicitly positioned as a cheap alternative to Thinknum/Revelio's $15-50K/yr contracts).
  - Job postings specifically: validated predictive signal (predicts revenue/M&A/pivots ahead of earnings per multiple vendors) - JobsPikr, Apify scrapers much cheaper than Revelio ($15-50k/yr).
  - Failure modes flagged by vendors themselves (useful for aegis-finance's own PIT discipline parallel): look-ahead bias without point-in-time/bitemporal storage, survivorship bias in panel composition, crowding/alpha decay (single-source half-life 6-18mo, composite 20-30mo).


## Batch 6 (final)
- YouTube: QuantPy (93,000 subs per ThetaData Feb 2026 acquisition post; reproducible code on GitHub TheQuantPy/youtube-tutorials, 281 stars), Algovibes (established Python/backtest channel). ThetaData ACQUIRED QuantPy channel Feb 2026 - notable, means it's now vendor-affiliated content (options data vendor), watch for bias toward promoting their data.
- Subreddit sizes (2025-2026): r/options 1.3-1.4M, r/ValueInvesting 794K, r/SecurityAnalysis 180-213K (highest S/N of the finance subs per multiple directories - fundamental/deep-dive focus), r/wallstreetbets/r/stocks/r/investing/r/daytrading also large (WSB largest, lowest S/N, r/algotrading is the systematic-strategy-specific one used heavily above).
