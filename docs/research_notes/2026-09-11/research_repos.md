# Research: open-source repos adjacent to Aegis Finance (2025-2026)

Excluded (already known): TradingAgents, ai-hedge-fund, FinRL/FinGPT/FinRobot, Qlib/RD-Agent, freqtrade, LEAN, vectorbt, OpenBB, Qanat, World Monitor, gods-eye-view, OpenCandle, AgentQuant, openquant, FinMem/FinAgent/FinCon papers.

## Categories
(a) personal investing agent / LLM portfolio manager w/ memory
(b) strategy discovery / alpha mining / evolutionary search
(c) news -> event -> return pipelines / datasets
(d) paper-trading farms / arena tournaments
(e) local-LLM finance tooling / MCP servers
(f) calibration / forecast ledger

## Findings (raw, append as found)


### Batch 1 — alpha evolution / factor mining
- pwb-alphaevolve (paperswithbacktest) https://github.com/paperswithbacktest/pwb-alphaevolve — evolutionary LLM prompts + Backtrader, AlphaEvolve-inspired
- shaansuthar/alphaevolve-trading https://github.com/shaansuthar/alphaevolve-trading — similar AlphaEvolve-inspired
- ZhuLinsen/alphaevo https://github.com/ZhuLinsen/alphaevo — self-evolving stock strategy agent, deterministic research committee retest gate
- algorithmicsuperintelligence/openevolve https://github.com/algorithmicsuperintelligence/openevolve — generic open AlphaEvolve implementation (not finance-specific but usable)
- QuantEvolve paper (arxiv 2510.18569) multi-agent evolutionary framework - check for code
- RndmVariableQ/AlphaAgent https://github.com/RndmVariableQ/AlphaAgent — LLM alpha mining w/ regularized exploration vs decay (arxiv 2502.16789)
- QuantaAlpha/QuantaAlpha https://github.com/QuantaAlpha/QuantaAlpha — LLM + evolutionary factor mining, self-evolving trajectories
- ChenNachuan/WorldQuant https://github.com/ChenNachuan/WorldQuant — LLM-driven factor discovery+backtest, DeepSeek/Ollama support (DeepSeek!! relevant to Aegis)
- jenetics/jenetics https://github.com/jenetics/jenetics — general genetic programming/algorithm java lib
- zameyer1/Evolutionary-Trading-Strategies https://github.com/zameyer1/Evolutionary-Trading-Strategies — GP evolve strategies, multi-objective profit/drawdown
- Cognitive Alpha Mining paper arxiv 2511.18850 — code TBD
- CodeEvolve arxiv 2510.14150 — generic evolutionary coding framework
Need: stars, license, last commit for each - verify via github API/web fetch.

### Batch 2 — personal agents, calibration, MCP
- pipiku915/FinMem-LLM-StockTrading https://github.com/pipiku915/FinMem-LLM-StockTrading — layered memory + character design (already know FinMem paper excluded, but repo itself may be new to list; check overlap - EXCLUDE per instructions since FinMem is explicitly excluded)
- merendamattia/personal-financial-ai-agent https://github.com/merendamattia/personal-financial-ai-agent — multi-LLM (Ollama/Gemini/OpenAI) personal finance conversational agent + portfolio recs
- ATLAS self-improving AI trading system - 25 agents, Darwinian selection, multi-cohort meta-weighting -- need URL
- jmoral4/superforecastinghelper https://github.com/jmoral4/superforecastinghelper — CLI tool recording predictions + Brier scores, SQLite backed (closest "forecast ledger" analog)
- flimao/briercalc https://github.com/flimao/briercalc — brier score/skill/calibration/resolution calc lib
- luferrer/CalibrationTutorial https://github.com/luferrer/CalibrationTutorial — calibration assessment/fix tutorial (reference, not a ledger)
- alpacahq/alpaca-mcp-server https://github.com/alpacahq/alpaca-mcp-server — OFFICIAL Alpaca MCP server (v2 FastMCP/OpenAPI rewrite) - stocks/options/crypto/portfolio mgmt via natural language
- TensorBlock/awesome-mcp-servers (finance--crypto.md list) https://github.com/TensorBlock/awesome-mcp-servers — directory of finance MCP servers, useful index
- laukikk/alpaca-mcp https://github.com/laukikk/alpaca-mcp — alt alpaca MCP
Need to search: SEC EDGAR MCP, yfinance MCP, news->event datasets (FNSPID, EDT), paper-trading arenas, local llama.cpp finance analyst tools.

### FINAL — verified via GitHub API (stars/license/pushed_at) 2026-09-11
[see gh_results.txt for raw dump]
Report delivered to caller inline. Task complete.
