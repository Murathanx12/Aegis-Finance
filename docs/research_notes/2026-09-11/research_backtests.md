# Research notes — backtests, hackathons, methodology (raw, in progress)

## 1. Alpaca hackathons 2025-2026
- Alpaca AI Trading Agents Hackathon 2026, co-hosted with lablab.ai, Aug 28 - Sep 4 2026, $5,000-$6,000 prize pool, 3 winners. Must use Alpaca Trading API + Alpaca MCP server or CLI, strategies must incorporate options trading.
  - https://x.com/AlpacaHQ/status/2092250644711391342
  - https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon (recap page - "Results" link exists at /live but WebFetch could not extract winner names/numbers from static page - likely JS-rendered)
  - Example submission found: "Dawn Of The Trading Agents" - https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/dawn-of-the-trading-agents (not confirmed winner)
  - Need to check /live results page and Devpost for other Alpaca hackathons (there may be earlier ones, e.g. 2025 "Alpaca Hackathon" on Devpost).
  - Alpaca blog: "Building a Multi-Agent AI Trading System on Alpaca" - https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca

## 2. Open-source repos
### virattt/ai-hedge-fund
- https://github.com/virattt/ai-hedge-fund — 18 analyst agents + 2 management agents mimicking named investors, LLM signals, has backtest capability computing Sharpe/Sortino/max DD vs benchmark. No published SPY-relative numbers found in initial search; need README direct read.

### TauricResearch/TradingAgents
- https://github.com/TauricResearch/TradingAgents — most-starred OSS AI trading framework (~80k stars claimed by a secondary source, verify)
- One documented run: ~7% over 30 days vs SPY 4.5% same window, but 22% drawdown, "no guarantee of repeatability" (source: pinggy.io blog, secondary, needs verification against repo/paper directly)
- Repo disclaimer: backtest results NOT guaranteed to match published figures; depends on backbone LLM, temperature, period, data quality, non-determinism.
- https://github.com/TauricResearch/TradingAgents/issues/60 (backtest and portfolio issue - check for real discussion)
- Related paper: GuruAgents arXiv:2510.01664

### FinRL / AI4Finance
- FinRL-X (arXiv 2603.21330 per secondary blog - VERIFY, this number looks like a hallucinated future-dated arXiv id, need to check) claims 62% annualized in live paper trading, Sharpe 1.10, max DD -21.46%; README paper trading: 19.76% total return vs SPY -2.51% (dates/window unclear - NEED VERIFICATION, sounds promotional)
- FinRL-Meta: NeurIPS 2022 benchmark paper, arxiv 2211.03107 - legitimate research benchmark infra, not a "beats SPY" claim itself.
- SUSPICION: FinRL-X numbers via blog.brightcoding.dev are likely unreliable/SEO content; verify against actual GitHub README before citing as credible evidence.

(more repos to research: Qlib/RD-Agent, freqtrade, LEAN/QuantConnect, vnpy, backtrader/zipline/vectorbt, OpenBB, StockFormer/FinAgent/FinMem)

## 3. Methodology citations (TODO)

## 4. What works at retail scale (TODO)

## 5. Infinite backtests / learn without fooling yourself (TODO)
