# Five external repos, reviewed for what Aegis should port

Date: 2026-09-07. Shallow clones (`git clone --depth 1`) under `C:\Users\mrthn\reference\`:

| repo | HEAD commit | date | license | language | trading repo? |
|---|---|---|---|---|---|
| `ecc` (affaan-m) | `e04ea0b9` | 2026-09-03 | MIT | Shell/TS/Py/Go | **No** (agent-harness OS; see §1) |
| `TradingAgents` (TauricResearch) | `9dee508c` v0.4.1 | 2026-09-01 | Apache-2.0 | Python, 8.4k LOC pkg + 515 tests | Yes (LLM decision graph, no backtester) |
| `freqtrade` | `2ab96e41` | 2026-09-07 | **GPL-3.0** | Python | Yes (crypto bot) |
| `Vibe-Trading` (HKUDS) | `a4f06a29` | 2026-09-07 | MIT | Python (~400k LOC) + TS frontend | Yes (LLM-driven strategy factory + backtester) |
| `OpenAlice` (TraderAlice) | `52b51f29` | 2026-09-05 | **AGPL-3.0** | TypeScript monorepo + py sidecar | Yes (agent shell over brokers) |

Nothing under `C:\Users\mrthn\aegis-finance` was modified. Where a subagent read a repo on my behalf, its findings are folded in and every path was quoted from the clone.

---

## 1. ecc (affaan-m) — an agent harness, not a trading repo

`C:\Users\mrthn\reference\ecc` is **ECC ("Everything Claude Code") v2.2.1** (`VERSION`, `README.md`): an open-source Claude Code *plugin distribution* — 286 skills under `skills/`, 68 subagents under `agents/`, 94 slash commands under `commands/`, 53 lifecycle hook scripts under `scripts/hooks/` wired by `hooks/hooks.json` (23 registered hooks), one MCP server (`chrome-devtools-mcp`, `.mcp.json`), plus mirrored catalogues for a dozen other harnesses (`.cursor/`, `.kiro/`, `.opencode/`, …). The 3,520-file headline is inflated: ~1,450 of the 1,516 files in `docs/` are translations (`docs/ja-JP` 522, `docs/zh-CN` 416), and `SOUL.md` still advertises "135 skills" against 286 on disk. **There is no trading content** — the only finance-adjacent items are `skills/market-research/` (GTM) and a passing "backtest split policy" line in `skills/mle-workflow/SKILL.md:212`.

**Worth adopting for how Aegis runs its Claude/Opus sessions — four files, not 3,520.** The skill and agent catalogue is generic and would add noise to a quant repo; the hook layer is small, unit-tested (`tests/hooks/*.test.js`), cross-platform, and each piece exists because a specific failure happened. In priority order:

1. **`scripts/hooks/gateguard-fact-force.js`** — a PreToolUse hook that **denies the first Edit/Write per file per session** and returns `permissionDecision: deny` with a demand for concrete facts: *"1. List ALL files that import/require this file … 3. If this file reads/writes data files, show field names, structure, and date format … 4. Quote the user's current instruction verbatim. Present the facts, then retry."* Its header comment states the design rationale exactly: *"Instead of asking 'are you sure?' (which LLMs always answer 'yes'), this hook demands concrete facts. The act of investigation creates awareness that self-evaluation never did."* This is the closest mechanical enforcement of Aegis's SESSION START PROTOCOL — which is currently a paragraph sessions skip. The same hook gates destructive Bash (`rm -rf`, `git push --force` but not `--force-with-lease`, `git clean -f`, `drop table`, `dd if=`) behind a stated rollback plan, and is shell-substitution/heredoc aware (`scripts/lib/shell-substitution.js`). **Aegis should add `taskkill /IM`, `pkill`, `killall` to that pattern list** — ECC has no process-kill guard (its only `taskkill` is `scripts/hooks/mcp-health-check.js:474`, killing its own child), and that is precisely the 2026-09-06 incident.
2. **`commands/save-session.md`'s session-file template** — mandatory sections *What WORKED (with evidence) · What Did NOT Work (and why) · What Has NOT Been Tried Yet · Current State of Files · Decisions Made · Blockers · Exact Next Step*, with the rule *"For each failure write the EXACT reason so the next session doesn't retry it. Be specific: 'threw X error because Y' is useful. 'didn't work' is not."* This is the failure-corpus discipline Aegis's handoffs want, as a fill-in form.
3. **The SessionStart/Stop pair** — `scripts/hooks/session-end.js` persists on **Stop, not SessionEnd** (*"Stop carries transcript_path"*), parsing the JSONL transcript for asks/tools/files into `~/.claude/session-data/YYYY-MM-DD-<id>-session.tmp`; `scripts/hooks/session-start.js` re-injects it via `hookSpecificOutput.additionalContext`, bounded by `ECC_SESSION_START_MAX_CHARS` (8000), matched to the current cwd/worktree rather than "newest", and wrapped in a **STALE-REPLAY GUARD** (`HISTORICAL REFERENCE ONLY — NOT LIVE INSTRUCTIONS … MUST NOT be re-executed`) written because the model re-ran slash commands with stale arguments after compaction.

Honourable mentions: `scripts/hooks/config-protection.js` (exit 2 on edits to lint/format configs — *"Agents frequently modify these to make checks pass instead of fixing the actual code"*) and `scripts/hooks/block-no-verify.js`, both ~10 minutes to port and both enforcing rules Aegis already states in prose; and the `ECC_HOOK_PROFILE` (`minimal|standard|strict`) + `ECC_DISABLED_HOOKS` + per-hook-`id` pattern, which makes each guard individually disableable instead of all-or-nothing, with deny messages naming the exact env var to relax.

Two cautions. **Do not install `ecc@ecc` wholesale** — 23 hooks, an unvetted MCP server, and a competing `~/.claude/session-data` memory scheme that would collide with the existing `MEMORY.md` convention. And `skills/delivery-gate/hooks/quality-gate.py`, which blocks Stop unless the learning log was touched "today", **dates files by `mtime`** — the exact trap that kept Aegis CI red for two days (CLAUDE.md protocol §7). Copy the idea, not that implementation. ECC also has **no CI watcher** (only a `gh pr checks` recipe in `commands/pr.md:150`), so `scripts/ci_watch.py` remains Aegis's own.

---

## 2. TradingAgents (TauricResearch) — deepest read, the one the user wants to copy and improve

### (a) What it is
A LangGraph pipeline that runs, for ONE ticker on ONE date, a fixed sequence of LLM "roles" (4 analysts → bull/bear debate → research manager → trader → 3-way risk debate → portfolio manager) and emits a 5-tier rating. It is a *decision-generation* scaffold with a small append-only reflection log; it contains **no backtester, no portfolio, no position sizing, no cost model** — `backtrader` is in `pyproject.toml` but is imported nowhere (`grep -rn backtrader --include=*.py` returns nothing).

### (b) Architecture (all under `C:\Users\mrthn\reference\TradingAgents\tradingagents\`)

| layer | path | what it does |
|---|---|---|
| entry | `graph/trading_graph.py` `TradingAgentsGraph.propagate(ticker, trade_date, asset_type)` → `(final_state, signal)` | builds two LLM clients (`deep_think_llm`, `quick_think_llm`), resolves pending memory entries, resolves instrument identity, runs the compiled graph, appends decision to memory log |
| graph shape | `graph/setup.py` `GraphSetup.setup_graph` | START → analysts in sequence (each: agent node ⇄ ToolNode until no tool calls, then a `Msg Clear` node wipes messages) → Bull ⇄ Bear → Research Manager → Trader → Aggressive → Conservative → Neutral (round-robin) → Portfolio Manager → END |
| routing | `graph/conditional_logic.py` | `should_continue_debate`: stop when `count >= 2*max_debate_rounds`; `should_continue_risk_analysis`: stop when `count >= 3*max_risk_discuss_rounds`. Defaults 1 and 1 (`default_config.py`) |
| state | `agents/utils/agent_states.py` | `AgentState(MessagesState)` with four report strings, `InvestDebateState` (bull/bear/history/count), `RiskDebateState` (3 histories + `latest_speaker`), `past_context` |
| analysts | `agents/analysts/{market,fundamentals,news,sentiment}_analyst.py` | tool-calling agents (quick LLM) except sentiment, which pre-fetches |
| researchers | `agents/researchers/{bull,bear}_researcher.py` | single `llm.invoke(prompt)` each, no tools |
| managers | `agents/managers/research_manager.py`, `managers/portfolio_manager.py` (deep LLM), `trader/trader.py` | structured output via `agents/schemas.py` (`ResearchPlan`, `TraderProposal`, `PortfolioDecision`) |
| risk debators | `agents/risk_mgmt/{aggressive,conservative,neutral}_debator.py` | single `llm.invoke`, no tools |
| tools | `agents/utils/{core_stock,technical_indicators,fundamental_data,news_data,macro_data,prediction_markets,market_data_validation}_tools.py` | thin `@tool` wrappers over `dataflows/interface.route_to_vendor` |
| vendors | `dataflows/interface.py` `VENDOR_METHODS`, `dataflows/{y_finance,alpha_vantage*,fred,polymarket,reddit,stocktwits,yfinance_news}.py` | yfinance default; Alpha Vantage optional; FRED (vintage-pinned); Polymarket Gamma API; Reddit RSS; StockTwits public stream |
| PIT helpers | `dataflows/date_window.py` `in_window`, `dataflows/stockstats_utils.py` `load_ohlcv`, `filter_financials_by_date`, `_assert_ohlcv_not_stale`; `dataflows/market_data_validator.py` | the look-ahead guards (added 2026-03 → 2026-08, see (d)) |
| memory | `agents/utils/memory.py` `TradingMemoryLog` | append-only markdown at `~/.tradingagents/memory/trading_memory.md` |
| reflection | `graph/reflection.py` `Reflector.reflect_on_final_decision` | one quick-LLM call → 2-4 sentences, given raw return + alpha vs benchmark |
| signal | `graph/signal_processing.py`, `agents/utils/rating.py` | regex rating extraction; unparseable → `REVIEW` sentinel (not silent Hold) |
| LLM clients | `llm_clients/{factory,openai_client,capabilities,model_catalog,anthropic_client,google_client,azure_client,bedrock_client}.py` | provider registry, see (f) |
| checkpoint | `graph/checkpointer.py` | LangGraph `SqliteSaver` per ticker; thread id = sha256(ticker:date:graph-signature) |
| CLI | `cli/main.py` (typer + rich), `cli/models.py` | interactive one-ticker run; no batch/backtest command |
| tests | `tests/` 515 test functions / 62 files | mostly provider plumbing, PIT windows, symbol handling |

### (c) Methodology — how a decision is made, how it "learns", how it backtests, how it handles risk

**Every agent role, its prompt, and its inputs** (verbatim key lines):

1. **Market Analyst** (`analysts/market_analyst.py`, quick LLM, tools `get_stock_data`, `get_indicators`, `get_verified_market_snapshot`). System prompt: *"select the most relevant indicators ... choose up to 8 indicators that provide complementary insights without redundancy"* from a fixed menu of 12 stockstats names (`close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr, vwma`; `mfi` exists in `y_finance.py` but is not in the prompt). Then: *"call get_verified_market_snapshot ... treat it as the source of truth for any exact OHLCV, price-level, or indicator-value claim. If another tool's output conflicts with the verified snapshot, flag the discrepancy rather than inventing a reconciled number."* Output: prose + markdown table.
2. **Fundamentals Analyst** (`analysts/fundamentals_analyst.py`, tools `get_fundamentals` (yfinance `.info` snapshot — **not point-in-time**; PE/market cap are today's), `get_balance_sheet/cashflow/income_statement` (columns after `curr_date` dropped by `filter_financials_by_date`, but the *values* are as-restated today, not as-first-reported)). Prompt: *"analyzing fundamental information over the past week about a company"*.
3. **News Analyst** (`analysts/news_analyst.py`, tools `get_news(ticker,start,end)`, `get_global_news(curr_date, look_back_days, limit)` over five fixed macro queries in `default_config.global_news_queries`, `get_macro_indicators` (FRED, vintage-pinned `realtime_start=realtime_end=pit`, `fred.py:181-190`), `get_prediction_markets` (Polymarket, **live only** — `_is_forward_looking` filters by today's clock, so a historical date gets today's markets)).
4. **Sentiment Analyst** (`analysts/sentiment_analyst.py`) — no tool calls; pre-fetches Yahoo news + StockTwits (30 msgs) + Reddit RSS into the prompt between `<start_of_news>`, `<start_of_stocktwits>`, `<start_of_reddit>` delimiters, then structured output `SentimentReport{overall_band(6 tiers), overall_score 0-10, confidence low/med/high, narrative}`. Prompt carries the analysis recipe (*"Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal. A 70/30 ... ≥90/10 may indicate over-extension ... Weight Reddit posts by engagement ... Past sentiment is not predictive"*). Note: `stocktwits.py:77-80` says outright that for a historical run *"they all fall after the window and a clear placeholder is returned"* — so **in any backtest the sentiment channel is empty by construction**.
5. **Bull / Bear Researchers** (`researchers/bull_researcher.py`, `bear_researcher.py`) — one `llm.invoke(prompt)` each, alternating, prompt = role brief + all four reports + `history` + `Last {opponent} argument`. `opponent_argument_or_opening()` (`agent_utils.py`) substitutes *"(The bear analyst has not spoken yet — open the debate with your own case.)"* on the first turn — added because the model fabricated the opponent's position (#1176).
6. **Research Manager** (`managers/research_manager.py`, deep LLM, structured `ResearchPlan{recommendation ∈ 5-tier, rationale, strategic_actions}`). Prompt includes the anti-decisiveness rule *"Choose Hold when the evidence is balanced ... do not manufacture a direction merely to appear decisive. Weigh the bull and bear cases on their merits, independent of which side spoke first or last."*
7. **Trader** (`trader/trader.py`, quick LLM, structured `TraderProposal{action ∈ Buy/Hold/Sell, reasoning, entry_price?, stop_loss?, position_sizing?: str}`). Gets the research plan **and** the raw market report so levels are *"grounded in real ATR / support-resistance"* (#1167). `position_sizing` is a free string like `'5% of portfolio'` — never parsed, never enforced.
8. **Aggressive / Conservative / Neutral risk debators** (`risk_mgmt/*.py`) — one `llm.invoke` each, round-robin, prompts are pure persona (*"actively champion high-reward, high-risk opportunities"*, *"protect assets, minimize volatility"*, *"balanced perspective"*). They see the trader's proposal + four reports + history. There is **no numeric risk computation anywhere** — no vol, no VaR, no exposure, no stop enforcement.
9. **Portfolio Manager** (`managers/portfolio_manager.py`, deep LLM, structured `PortfolioDecision{rating(5-tier), executive_summary, investment_thesis, price_target?, time_horizon?}`). Only node that sees `past_context` (memory).

**Message hygiene**: after each analyst finishes, `create_msg_delete()` issues `RemoveMessage` for every message and inserts a context-anchored placeholder (not a bare "Continue" — some OpenAI-compatible providers answered about the word "continue", #888). Reports are carried in dedicated state fields, not in the message list — this is the main context-cost control.

**How it "learns"** — `TradingMemoryLog` + `Reflector`:
- Phase A: at the end of `propagate()` append `[date | ticker | rating | pending]\n\nDECISION:\n<pm markdown>` to the markdown log (idempotent on (date,ticker)).
- Phase B: at the START of the next run *for the same ticker only* (`_resolve_pending_entries`), fetch yfinance closes, compute `raw = C[t+5]/C[t]-1`, `alpha = raw - bench`, require the full 5-bar window to exist (#1169), call the reflection prompt (*"Write exactly 2-4 sentences ... 1. Was the directional call correct? (cite the alpha figure) 2. Which part of the investment thesis held or failed? 3. One concrete lesson"*), rewrite the tag as `[date|ticker|rating|raw|alpha|5d|resolved:YYYY-MM-DD]`.
- Injection: `get_past_context(ticker, n_same=5, n_cross=3, as_of=trade_date_if_historical)` → the PM prompt line *"Lessons from prior decisions and outcomes:"*. The `as_of` filter on `resolved:` date is the point-in-time guard (#1251, `tests/test_memory_pointintime.py`).
- The "learning" is therefore: last five same-ticker episodes with a fixed 5-day horizon, plus three cross-ticker one-paragraph lessons, as prose, to one node. The 5-day horizon is hard-coded (`_fetch_returns(holding_days=5)`) regardless of the PM's own `time_horizon` field. The earlier BM25 per-agent `FinancialSituationMemory` and `reflect_and_remember()` were **removed** in v0.2.4 (CHANGELOG) — `main.py` still carries the dead comment `# ta.reflect_and_remember(1000)`.

**How it backtests**: it doesn't. There is no date loop, no P&L, no Sharpe/drawdown code in the package (`grep -rn -i "sharpe\|drawdown"` over non-test code: zero hits). "Backtest" in the codebase means only "a `propagate()` call with a past `trade_date`", and the look-ahead work is about making *that single call* PIT-clean.

**How it handles risk**: three personas argue in prose; the PM picks a 5-tier label. No sizing, no limits, no portfolio.

### (d) Evidence — what is claimed, on what, and whether it is credible

**Paper** (arXiv 2412.20138, v1 28 Dec 2024 … v7 3 Jun 2025; "Oral @ Multi-Agent AI in the Real World" workshop):
- Setup: **three tickers** in the results table — AAPL, GOOGL, AMZN (the text also names NVDA/MSFT/META but Table 1 does not report them) — over **1 Jan → 29 Mar 2024** (~60 trading days), quick LLM `gpt-4o-mini`, deep LLM `o1-preview`.
- Claimed (Table 1): TradingAgents CR / AR / SR / MDD = AAPL **26.62% / 30.5% / 8.21 / 0.91%**, GOOGL **24.36 / 27.58 / 6.39 / 1.69**, AMZN **23.21 / 24.90 / 5.60 / 2.11**; Buy&Hold AAPL −5.23%, GOOGL 7.78%, AMZN 17.1%; other baselines MACD, KDJ&RSI, ZMR, SMA.
- Footnote 1 (verbatim): *"We benchmarked TradingAgents over 3 months due to intensive LLM and tool use (11 LLM calls & 20+ tool calls/prediction). The highest Sharpe Ratio exceeds our expected empirical range (SR above 2 – very good, above 3 – excellent). We exported TradingAgents's decision sequences and examined them to ensure calculation correctness. We believe the exceptionally high SR resulted from the phenomenon that there were few pullbacks in TradingAgents during that period."*
- Not stated anywhere: transaction costs, slippage, position sizing / how BUY-SELL-HOLD became a position, number of runs or seeds, confidence intervals, long-only vs long/short (figure arrows show both), and — critically — **nothing on LLM knowledge cutoff vs backtest window**. The only leakage sentence is *"Agents make decisions based solely on data available up to each trading day, ensuring no future data is used (eliminating look-ahead bias)"*, which addresses the tool date filter, not the model's priors. The models used (gpt-4o-mini, o1-preview) have stated training cutoffs of Oct 2023, so the Jan–Mar 2024 window is *nominally* after cutoff — but the paper does not make that argument and, more importantly, o1-preview was released Sept 2024, i.e. the experiment was run ≥6 months after the window closed, with news tools that (in the v0.1.0 code) fetched **undated** social content. The repo's own CHANGELOG documents the leaks that existed in the public code until 2026: Alpha Vantage fundamentals with future-dated reports (#1115, fixed 0.3.1), yfinance news future articles (#992/#1007, 0.3.0), StockTwits/Reddit served today's chatter for historical dates (#1220, fixed **0.4.0, 2026-08-31**), FRED served today's vintage (#1275, 0.4.0), memory injected future outcomes (#1251, 0.4.0), mid-window `curr_date` leak (#475, 0.2.3). The paper's numbers predate every one of these fixes.
- Data sources named in the paper (Bloomberg, EODHD, FinnHub, Reddit, X/Twitter, SEC filings, "60 technical indicators") do not match the released code, which had yfinance + FinnHub-cached CSVs at v0.1.0 and yfinance/AlphaVantage/FRED/Polymarket/Reddit-RSS/StockTwits now. Bloomberg/X are not in any version of the code.
- **Verdict**: n = 3 tickers × 1 quarter × 1 run, no costs, no sizing rule, SR 5.6–8.2 that the authors themselves flag, and a code base whose look-ahead guards were written 15–20 months after the results. Treat Table 1 as a demo, not evidence. The README now says so almost explicitly: *"Backtest results are not guaranteed to match any published figure ... Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return."*
- **Trading-R1** (arXiv 2509.11420, Jan 2026 news entry): SFT + RL three-stage curriculum on "Tauric-TR1-DB, 100k samples, 18 months, 14 equities, five data sources", evaluated on "six major equities and ETFs"; base model size, reward design, exact Sharpe numbers, and any leakage statement are absent from the abstract page; weights/terminal "expected to land soon" — nothing released in this repo.

**Repo evidence**: none. There is no evaluation harness, no results directory, no reproduction script for Table 1. The test suite (515 functions) tests plumbing, not returns.

### (e) License
Apache-2.0 (`LICENSE`). Code and prompts can be copied into Aegis with attribution and a NOTICE line.

### (f) LLM / provider coupling — runs on DeepSeek out of the box
- `llm_clients/openai_client.py` `OPENAI_COMPATIBLE_PROVIDERS` registry: `"deepseek": ProviderSpec(base_url="https://api.deepseek.com", chat_class=DeepSeekChatOpenAI)`; env key `DEEPSEEK_API_KEY`; set `TRADINGAGENTS_LLM_PROVIDER=deepseek`, `TRADINGAGENTS_DEEP_THINK_LLM=deepseek-v4-pro`, `TRADINGAGENTS_QUICK_THINK_LLM=deepseek-v4-flash` (catalog in `model_catalog.py:129-143`; the `deepseek-chat`/`deepseek-reasoner` aliases are noted as deprecated 2026-07-24 and mapped to V4 Flash).
- `DeepSeekChatOpenAI` handles the thinking-mode quirk: captures `reasoning_content` on receive and echoes it on send (`_get_request_payload` / `_create_chat_result`) — otherwise the API 400s on multi-turn.
- `llm_clients/capabilities.py`: `_DEEPSEEK_THINKING = ModelCapabilities(supports_tool_choice=False, supports_json_mode=True, supports_json_schema=False, preferred_structured_method="function_calling", requires_reasoning_content_roundtrip=True)` — structured output binds the Pydantic schema as a tool but sends **no `tool_choice`** (DeepSeek V4/reasoner reject it, #678). `tests/test_deepseek_reasoning.py` pins this and has a live test gated on a real key.
- Also a generic `openai_compatible` provider that requires `backend_url` and tolerates keyless endpoints (`tests/test_openai_compatible_provider.py`).
- Framework coupling: LangChain + LangGraph (`langchain-core>=0.3.81`, `langgraph>=0.4.8`, `langgraph-checkpoint-sqlite`). Aegis's `llm_analyzer` is a raw-HTTP DeepSeek client; porting the *pattern* does not require LangGraph.
- Cost note from the paper: 11 LLM calls + 20+ tool calls per ticker-day with debate rounds = 1. At Aegis's ~$3.68/day DeepSeek budget this is ~1-3 ticker-days per dollar on V4 Flash; a 60-day × 3-ticker replication is ~180 runs.

### (g) What Aegis should port — concrete, with location, benefit, effort

| # | component (source path) | where in Aegis | what it improves | effort |
|---|---|---|---|---|
| 1 | **Verified-snapshot grounding**: `dataflows/market_data_validator.py::build_verified_market_snapshot` + the prompt clause *"treat it as the source of truth for any exact OHLCV ... flag the discrepancy rather than inventing a reconciled number"* | `backend/services/llm_analyzer.py` (central `_call_llm` prompt assembly) and `explain_move.py`; snapshot computed from CRSP/Alpaca parquet, never yfinance | kills the fabricated-price failure mode Aegis has seen (NVDA print resolved facts-first is the same idea, done by hand); makes every LLM narrative auditable against a deterministic table | S |
| 2 | **Typed decision schema + render-back**: `agents/schemas.py` (`PortfolioDecision`, `TraderProposal`, `SentimentReport`, `_coerce_optional_float`) and `agents/utils/structured.py` (`bind_structured` / `invoke_structured_or_freetext`) | `backend/services/llm_analyzer.py` — a `structured()` helper next to `_call_llm`; the pre-open prediction book (`AEGIS_VISION` §) gets a Pydantic row instead of prose | every LLM output becomes a gradeable, typed row (band + score + confidence + narrative); the `REVIEW` sentinel replaces silent defaults (`rating.py::extract_rating` → `None`) | S |
| 3 | **Decision log with deferred outcome resolution and PIT gate**: `agents/utils/memory.py::TradingMemoryLog` (pending tag → resolved tag with `resolved:` date; `get_past_context(as_of=...)`) + `graph/trading_graph.py::_fetch_returns/_resolve_pending_entries` | new `backend/services/decision_log.py`; grade against CRSP/Alpaca closes, not yfinance; horizon comes from the row's own declared horizon, not a constant 5 | this IS the "pre-open prediction book + discovery-failure autopsy" from the VISION file, as ~300 lines; the `as_of` gate is exactly Aegis's PIT discipline applied to *lessons* | M |
| 4 | **Reflection prompt** `graph/reflection.py` (*"1. Was the directional call correct? (cite the alpha figure) 2. Which part of the thesis held or failed? 3. One concrete lesson"*, 2-4 sentences, stored verbatim) | same `decision_log.py`; batch-run nightly on newly-resolved rows | cheap ($0.001/row), gradeable, and the 2-4-sentence cap is what keeps re-injection affordable | S |
| 5 | **Date-window PIT helper** `dataflows/date_window.py::in_window` (UTC-normalised, half-open `[start, end+1d)`, undated item kept only if window reaches now) + tests `tests/test_news_lookahead.py` | `backend/services/` news/Benzinga/EDGAR loaders — a single shared `pit_window()`; port the six tests | Aegis already has "TWO CLOCKS NEED TWO BOUNDS"; this is the one-function version with the midnight-after and mixed-offset regressions already encoded | S |
| 6 | **Stale-data refusal** `stockstats_utils.py::_assert_ohlcv_not_stale` (latest row > 10 calendar days before as-of ⇒ raise `NoMarketDataError`), and `interface.py::route_to_vendor` returning one explicit `NO_DATA_AVAILABLE: ... Do not estimate or fabricate values` sentinel instead of `""` | Aegis collectors/fetchers (`silent-fragility-audit` skill scope) | converts silent-empty into a loud, LLM-readable refusal — Aegis's house failure mode | S |
| 7 | **Bull/Bear + Research Manager as a *hypothesis stress-test*, not a trade generator**: prompts in `researchers/*.py` + `managers/research_manager.py` (with the *"independent of which side spoke first or last"* and *"do not manufacture a direction"* clauses, and `opponent_argument_or_opening`) | `backend/learner/` or a new `backend/services/thesis_debate.py`, invoked on the ≤5 names the deterministic screen already selected; output = `ResearchPlan` row feeding the PRODUCT_EXPERIMENT book as its own selector | gives Aegis a second, *different-error* selector (CLAUDE.md "BOTTLENECK": every book is 12-1 momentum) that is cheap to A/B: debate-on vs debate-off on the same candidate list | M |
| 8 | **Capability table for DeepSeek quirks** `llm_clients/capabilities.py` + `DeepSeekChatOpenAI` reasoning-content round-trip | `backend/services/llm_analyzer.py` provider layer | if Aegis ever uses `deepseek-v4-*` thinking mode multi-turn or tool-bound structured output, this is the exact set of 400s to avoid; 40 lines | S |
| 9 | **Instrument-identity anchoring** `agent_utils.py::resolve_instrument_identity/build_instrument_context` (*"Do not substitute a different company or ticker unless a tool result explicitly disproves this resolved identity"*) | prompt preamble in `llm_analyzer` using CRSP `comnam`/SIC instead of yfinance | fixes the wrong-company hallucination (#814) that is a real risk for Aegis's 3,059-name watchlist of obscure tickers | S |
| 10 | **Message-clearing between roles** `agent_utils.py::create_msg_delete` + reports carried in state fields | any multi-step LLM chain in Aegis | context cost control; each role sees reports, not transcripts | S |

### (h) What NOT to copy, and why
- **The three risk debators and the PM "risk" step.** They are personas arguing in prose with zero numbers; Aegis's rule 4 of the session protocol (print the worst case in dollars) is strictly better. Do not let an LLM sit anywhere on the sizing/stop path (CLAUDE.md: "no LLM authority over real capital").
- **The Trader node's `entry_price/stop_loss/position_sizing` strings** — free text, unparsed, unenforced. Aegis has `TRADABLE_DOLLAR_VOL`, the edge-vs-stop ratio floor, and gross caps; keep those deterministic.
- **The technical-indicator menu as an alpha source.** 12 stockstats indicators on 5y daily yfinance are exactly the factors Aegis's farm already showed to be noise; the analyst prompt is a nicely written but zero-evidence prior.
- **The 5-day fixed grading horizon and same-ticker-only resolution** (`_resolve_pending_entries`): a ticker that is never re-run is never graded, and every thesis is graded at 5 bars whatever its stated horizon. Grade every row nightly at its own horizon.
- **yfinance `.info` fundamentals** — not PIT (today's PE, today's market cap). Aegis has CRSP/IBES/Compustat-style PIT sources; never let a yfinance snapshot into a historical run.
- **Polymarket tool for historical dates** — `_is_forward_looking` uses `datetime.now()`; it is live-only and would leak resolved-event knowledge into any backtest.
- **LangGraph as a dependency.** The graph is ten sequential nodes and two counters; `conditional_logic.py` is 60 lines. A plain Python loop with the same state dict is smaller and testable under Aegis's network-blocked suite.
- **The debate as evidence of anything.** Nothing in the repo or the paper tests whether debate rounds change accuracy vs. a single call (the paper reports no ablation). If Aegis ports (g)#7, the *first* experiment is debate-off vs debate-on on matched candidates — under `PRODUCT_EXPERIMENT`, with a frozen contract.
- **The results in Table 1.** See (d).


---

## 3. freqtrade — the mature engineering baseline

Everything below is read from the clone at `C:\Users\mrthn\reference\freqtrade\` (HEAD `2ab96e41`, 2026-09-07). The package is 333 Python files; the four that matter for Aegis are `freqtrade/strategy/interface.py` (1,908 lines), `freqtrade/optimize/backtesting.py` (1,977), `freqtrade/freqai/freqai_interface.py` (1,064) and `freqtrade/data/dataprovider.py` (654).

### (a) What it is
A crypto trading bot with a strategy DSL, a candle-level backtester, an Optuna-based parameter optimiser, an adaptive-ML module (FreqAI), a plugin system for universe filtering and trading protections, and a Telegram/REST/WebSocket control surface. It is **not** a research framework: no alpha library, no cross-sectional machinery, no statistical testing. What it has that Aegis does not is ten years of production hardening on the boring parts — the exit-priority ladder, the fill assumptions, the strategy-callback contract, the dry-run/live boundary, and two look-ahead detectors that work without reading the strategy's source.

### (b) Architecture (paths under `C:\Users\mrthn\reference\freqtrade\`)

| layer | path | what it does |
|---|---|---|
| strategy contract | `freqtrade/strategy/interface.py` `class IStrategy(ABC, HyperStrategyMixin)` | the whole user API: 3 `populate_*` methods + ~20 optional callbacks + ~15 class-level risk attributes |
| hyperoptable params | `freqtrade/strategy/parameters.py` (`IntParameter`, `RealParameter`, `DecimalParameter`, `CategoricalParameter`, `BooleanParameter`), `strategy/hyper.py` | a parameter declared in the strategy body *is* the search space — no separate config |
| informative merge | `freqtrade/strategy/strategy_helper.py` `_prepare_informative_pair` / `merge_informative_pair`, `strategy/informative_decorator.py` | the higher-timeframe join that does not leak |
| error containment | `freqtrade/strategy/strategy_wrapper.py` `strategy_safe_wrapper` | every user callback is called through it |
| backtester | `freqtrade/optimize/backtesting.py` `class Backtesting` | tuple-row loop, `_get_close_rate*`, `_enter_trade`, `backtest_loop`, `time_pair_generator` |
| look-ahead detector | `freqtrade/optimize/analysis/lookahead.py`, `lookahead_helpers.py` | chained backtests, diffs indicator frames |
| recursion detector | `freqtrade/optimize/analysis/recursive.py`, `recursive_helpers.py` | same indicators at different `startup_candle_count` |
| optimiser | `freqtrade/optimize/hyperopt/hyperopt_optimizer.py` (Optuna), `hyperopt/hyperopt.py`, `hyperopt_epoch_filters.py` | TPE / GP / CMA-ES / NSGA-II / NSGA-III / QMC samplers |
| objectives | `freqtrade/optimize/hyperopt_loss/*.py` (13 files) | Sharpe, SharpeDaily, Sortino, SortinoDaily, Calmar, MaxDrawdown (+PerPair, +Relative), ProfitDrawdown, MultiMetric, ShortTradeDur, OnlyProfit |
| protections | `freqtrade/plugins/protections/{iprotection,stoploss_guard,cooldown_period,low_profit_pairs,max_drawdown_protection}.py`, `plugins/protectionmanager.py` | portfolio-level circuit breakers |
| universe filters | `freqtrade/plugins/pairlist/*` (~20 handlers), `plugins/pairlistmanager.py` | the pairlist pipeline |
| adaptive ML | `freqtrade/freqai/{freqai_interface,data_kitchen,data_drawer,utils}.py`, `freqai/prediction_models/*`, `freqai/RL/*`, `freqai/torch/*` | rolling retrain + sklearn `Pipeline` of outlier filters |
| PIT data access | `freqtrade/data/dataprovider.py` `DataProvider` | one object, four runmodes, different slicing per mode |
| live loop | `freqtrade/freqtradebot.py` (2,695 lines), `worker.py` | order lifecycle, timeouts, replacement, reconciliation |
| control surface | `freqtrade/rpc/{telegram,webhook,discord,rpc,rpc_manager}.py`, `rpc/api_server/*` (FastAPI) | ~40 Telegram commands, REST + WebSocket, shared implementation in `rpc.py` |

### (c) Methodology

**The `IStrategy` interface.** A strategy is a class with three required dataframe methods, all pure and vectorised: `populate_indicators(dataframe, metadata)` (features), `populate_entry_trend(...)` (sets integer columns `enter_long`/`enter_short` plus free-text `enter_tag`), `populate_exit_trend(...)` (`exit_long`/`exit_short`, `exit_tag`). Risk lives in **declared class attributes**, not in signal code (`interface.py:72-131`):

```python
minimal_roi: dict = {}          # {minutes_held: min_profit_ratio} -- time-decayed take-profit
use_custom_roi: bool = False
stoploss: float                 # mandatory, negative ratio
trailing_stop: bool = False
trailing_stop_positive: float | None = None
trailing_stop_positive_offset: float = 0.0
trailing_only_offset_is_reached = False
use_custom_stoploss: bool = False
max_open_trades: IntOrInf
position_adjustment_enable: bool = False
max_entry_position_adjustment: int = -1
ignore_buying_expired_candle_after: int = 0
startup_candle_count: int = 0   # warm-up candles the indicators need
protections: list = []
```

`minimal_roi` is the single cleverest object in the file: `{0: 0.10, 40: 0.04, 100: 0.02, 240: 0}` means "take 10% immediately; after 40 minutes accept 4%; after 4 hours accept anything positive". `min_roi_reached_entry` (`interface.py:1675`) picks `max(k for k in minimal_roi if k <= trade_duration_minutes)`. It is a **declarative, backtestable, hyperoptable time-decayed exit curve** — exactly the object Aegis's frozen contracts gesture at with `expected_horizon_sessions` / `min_normal_hold_sessions` but express as two scalars instead of a curve. `custom_roi` (`interface.py:477`) lets a callback return a lower ROI for a given bar; the engine takes `min(custom, table)`.

**The exit ladder.** `should_exit` (`interface.py:1419-1522`) evaluates *every* exit reason and returns a **list** of `ExitCheckTuple`, in a documented priority written in the source:

```
# Sequence:
# Exit-signal
# Stoploss
# ROI
# Trailing stoploss
```

Every exit is a typed `ExitType` enum; `custom_exit` returning a `str` becomes a `CUSTOM_EXIT` whose reason is carried through, truncated to `CUSTOM_TAG_MAX_LENGTH` with a warning. Aegis already has typed exit reasons; what it lacks is (i) the *ranking*, so a bar where a stop and a signal both fire resolves deterministically and identically in paper and replay, and (ii) the free downstream attribution that follows — `/exit_reason_performance`, `/entries`, `/mix_tags` in Telegram and `exit_reason` summaries in `optimize/optimize_reports/`.

**Callbacks** — all optional, all no-ops by default, all invoked through `strategy_safe_wrapper`: `bot_start`, `bot_loop_start`, `custom_entry_price`, `custom_exit_price`, `custom_stake_amount`, `custom_stoploss`, `custom_roi`, `custom_exit`, `adjust_trade_position`, `adjust_entry_price` / `adjust_exit_price` / `adjust_order_price`, `confirm_trade_entry`, `confirm_trade_exit`, `order_filled`, `check_entry_timeout` / `check_exit_timeout`, `leverage`, `informative_pairs`, `plot_annotations`.

`custom_stake_amount` (`interface.py:625`) is the sizing hook, and its signature is the part worth copying verbatim — the sizer is handed the bounds and must return inside them, i.e. **the engine bounds the sizer, the sizer does not bound itself**:

```python
def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                        min_stake, max_stake, leverage, entry_tag, side, **kwargs) -> float:
    """:return: A stake size, which is between min_stake and max_stake."""
    return proposed_stake
```

`confirm_trade_entry` / `confirm_trade_exit` are pure veto hooks returning `bool` — the last gate before an order leaves, structurally separate from signal generation.

`strategy_safe_wrapper` (`strategy/strategy_wrapper.py`, 60 lines) catches `ValueError` and everything else, logs the **user's** frame (`__format_traceback` walks past its own file), and either returns `default_retval` or raises a typed `StrategyError`. It also `deepcopy`s a `trade` kwarg before handing it to user code — *"Protect accidental modifications from within the strategy"*.

**Protections** (`freqtrade/plugins/protections/`) are the piece Aegis has no equivalent of: portfolio-level circuit breakers that lock **entries only** (never exits), for one pair or globally, declared as data on the strategy:

- `StoplossGuard` — `trade_limit` (default 10) stop-outs with `close_profit < required_profit` inside `lookback_period` ⇒ lock. Counts only `ExitType.{TRAILING_STOP_LOSS, STOP_LOSS, STOPLOSS_ON_EXCHANGE, LIQUIDATION}`; `only_per_pair` / `only_per_side` narrow the scope.
- `MaxDrawdown` — `calculate_max_drawdown(...)` over closed trades in the window, in two modes: `"equity"`, which reconstructs the pre-window balance from `close_profit_abs` and reports a true `relative_account_drawdown`, and the legacy `"ratios"`.
- `CooldownPeriod` — after any closed trade on a pair, no re-entry for N candles.
- `LowProfitPairs` — lock a pair whose windowed profit is below a floor.

The base class `IProtection` (`plugins/protections/iprotection.py`) is ~200 lines and the entire contract is two methods (`global_stop`, `stop_per_pair`) returning `ProtectionReturn(lock, until, reason, lock_side)`, plus two class flags `has_global_stop` / `has_local_stop`. Lookback and stop duration are expressible in **candles, minutes, or an absolute wall-clock `unlock_at`**, and every lock carries a human-readable `reason` surfaced by `/locks`. Protections are **on in live, off by default in backtesting** (`--enable-protections`), and hyperopt auto-enables them when `--space protection` is selected.

**Backtest fill and cost model.** Costs are a single round-trip rate. `set_fee()` (`backtesting.py:268`) takes `config["fee"]`, else `max(fee for fee in fees)` across probed pairs — logged as *"Using fee {fee:.4%} - worst case fee from exchange (lowest tier)"*. It is applied at both ends (`fee_open=self.fee, fee_close=self.fee`, `backtesting.py:1223-1224`) and inside each simulated order's cost (`cost=amount * close_rate * (1 + self.fee)`). **There is no slippage model and no market-impact model.** Fills come from `_get_close_rate` (`backtesting.py:574`):

- ordinary signal exit ⇒ `row[OPEN_IDX]`, the *next* candle's open;
- stop-loss ⇒ exactly `trade.stop_loss`, even if the low went lower — unless the stop sits outside the candle, in which case the open is used;
- trailing stop firing on the entry candle ⇒ a deliberately pessimistic reconstruction (*"Worst case: price ticks tiny bit above open and dives down"*), then floored at the candle low so the fill is never outside the bar (*"This still remains 'worst case' - but 'worst realistic case'"*);
- ROI ⇒ `min(max(close_rate, row[LOW_IDX]), row[HIGH_IDX])` — the ROI level clamped into the bar.

The assumptions are **written down**, which is the transferable part (`docs/backtesting.md:556-591`): *"All orders are filled at the requested price (no slippage) as long as the price is within the candle's high/low range"* · *"Stoploss exits happen exactly at stoploss price, even if low was lower, but the loss will be `2 * fees` higher than the stoploss price"* · *"Low happens before high for stoploss, protecting capital first"* · *"Stoploss is evaluated before ROI within one candle"* · *"Exits are never 'below the candle', so a ROI of 2% may result in an exit at 2.4% if low was at 2.4% profit"* — closing with *"backtesting will **never** replace running a strategy in dry-run mode."* Aegis's `portfolio_farm.Policy` refuses zero costs; it has never published a list like this that a reader can attack.

Intra-candle path is optional: `--timeframe-detail` (`_load_bt_data_detail`, `get_detail_data`) replays a finer timeframe inside each signal candle — freqtrade's answer to "the OHLC bar hides the path". `_get_ohlcv_as_lists` converts frames to tuples of scalars before the loop, which is why a multi-year backtest finishes at all.

**Hyperopt.** `hyperopt_optimizer.py` wraps **Optuna** (`optuna_samplers_dict`, line 55: `TPESampler`, `GPSampler`, `CmaEsSampler`, `NSGAIISampler`, `NSGAIIISampler`, `QMCSampler`), seeds `INITIAL_POINTS = 30` random startup trials, and supports stagnation-based early stopping via `optuna.terminator.BestValueStagnationEvaluator` (`self.es_epochs = config.get("early_stop", 0)`). Spaces come from two places: the pre-defined `roi_space` / `stoploss_space` / `trailing_space` / `max_open_trades_space` in `hyperopt/hyperopt_interface.py` (e.g. `SKDecimal(-0.35, -0.02, decimals=3, name="stoploss")`, `Integer(-1, 10, name="max_open_trades")`), and any `IntParameter`/`DecimalParameter`/`CategoricalParameter` declared in the strategy body and auto-discovered by `HyperStrategyMixin`.

Objectives implement one abstract method (`hyperopt_loss/hyperopt_loss_interface.py`):

```python
@staticmethod
@abstractmethod
def hyperopt_loss_function(*, results: DataFrame, trade_count: int, min_date, max_date,
                          config, processed, backtest_stats, starting_balance, **kwargs) -> float:
    """Objective function, returns smaller number for better results"""
```

The interesting one is `MultiMetricHyperOptLoss` (`hyperopt_loss/hyperopt_loss_multi_metric.py`) — a product of logged sub-objectives with an explicit trade-count penalty:

```python
DRAWDOWN_MULT = 0.055; TARGET_TRADE_AMOUNT = 50
profit_draw_function = total_profit - (relative_account_drawdown * total_profit) * (1 - DRAWDOWN_MULT)
return -1 * (profit_draw_function * log_profit_factor * log_expectancy_ratio
             * log_winrate_coef * trade_count_penalty)
```

`trade_count_penalty` linearly discounts any epoch with fewer than 50 trades, floored at 0.1. That is the only n-awareness anywhere in the optimiser.

**How it avoids overfitting: essentially not at all — and it is only half honest about that.** `grep -rn -i "out.of.sample|walk.forward|cross.valid|purged|embargo|deflated sharpe|PBO|combinatorial"` over `docs/` and `freqtrade/optimize/` (excluding freqai) returns **zero hits**. There is no holdout, no CV, no multiplicity control, no deflated Sharpe, no PBO. The complete set of defences is:

1. decimals capped at 3 places, with the note *"every value more precise than this will usually result in overfitted results"* (`docs/hyperopt.md:660, 702, 740`);
2. `hyperopt_epoch_filters.py` — post-hoc leaderboard filters (`only_best`, `only_profitable`, min/max trades, min/max average duration, min/max profit, objective range). These filter the *display*, not the search;
3. `--random-state` for reproducibility (`docs/hyperopt.md:742-750`);
4. the `MultiMetric` trade-count penalty above;
5. `docs/utils.md:336`, on selecting pairs from backtest results: *"Only using winning pairs can lead to an overfitted strategy, which will not work well on future data."*

Under Aegis's canon this is a `PRODUCT_EXPERIMENT`-grade optimiser and nothing more. Port the loss-function *interface* and the protection space; keep Aegis's own gates (CANON §63 BH-FDR / Holm, §64 power, DSR/PBO from S38g) around them.

**FreqAI — the adaptive retraining loop.** The closest thing in these five repos to Aegis's learner, and the design is worth reading in full.

- *Walk-forward by construction.* `FreqaiDataKitchen.split_timerange(tr, train_split=train_period_days, bt_split=backtest_period_days)` (`freqai/data_kitchen.py:315`) emits paired `(train_window, predict_window)` lists by sliding a fixed-width training window forward by `backtest_period_days` each step, with `timerange_backtest.startts = timerange_train.stopts`. A model never predicts on a bar inside its own training window. Config example (`docs/freqai-configuration.md:13-14`): `"train_period_days": 30, "backtest_period_days": 7`.
- *The cost of that honesty is stated, not hidden.* `docs/freqai-running.md:112`: *"by setting a `--timerange` of 10 days, and a `backtest_period_days` of 0.1, FreqAI will need to train 100 models per pair to complete the full backtest. Because of this, a true backtest of FreqAI adaptive training would take a very long time. The best way to fully test a model is to run it dry and let it train constantly. In this case, backtesting would take the exact same amount of time as a dry run."*
- *The documented leak that remains.* `docs/freqai-running.md:71`: *"Backtesting calls `set_freqai_targets()` one time for each backtest window … so the targets simulate dry/live behavior without look ahead bias. However, the definition of the features in `feature_engineering_*()` is performed once on the entire training timerange. This means that you should be sure that features do not look-ahead into the future."* Targets are windowed; features are the user's problem. That is a real, admitted hole and the reason `lookahead-analysis` exists.
- *Live cadence.* `live_retrain_hours` (default 0 = as often as possible) and `expired_hours`; `check_if_model_expired` / `check_if_new_training_required` (`data_kitchen.py:516-583`). An expired model does not silently keep scoring — it emits null predictions with `do_predict == 2` and logs *"Model expired for {pair}, returning null values to strategy. Strategy construction should take care to consider this event"* (`freqai_interface.py:520-525`).
- *Feature engineering as a naming convention.* Three strategy hooks (`interface.py:916-1000`). `feature_engineering_expand_all(df, period, metadata)` is called once per `indicator_periods_candles` entry and its output is then cross-multiplied by `include_timeframes` × `include_shifted_candles` × `include_corr_pairlist`; `feature_engineering_expand_basic` skips the period axis; `feature_engineering_standard` runs once for non-expandable features (day-of-week). Features must be prefixed `%-`, labels `&-`. One line of user code becomes hundreds of columns whose *names encode their full provenance*.
- *Outlier detection is a sklearn `Pipeline`, not a special case.* `define_data_pipeline` (`freqai_interface.py:557-586`) assembles, in order: `VarianceThreshold(threshold=0)` → `MinMaxScaler(-1,1)` → optional `PCA(n_components=0.999)` + re-scale → optional `SVMOutlierExtractor(**svm_params)` (sklearn `SGDOneClassSVM`, default `{"shuffle": False, "nu": 0.01}`) → optional `DissimilarityIndex(di_threshold=...)` → optional `DBSCAN(n_jobs=...)` → optional `Noise(sigma=noise_standard_deviation)`. The **same fitted pipeline is applied to inference rows**, so a live feature vector that is an outlier *relative to the training set* is flagged rather than scored.
- *And the flag reaches the strategy.* `do_predict` is an integer in [-2, 2] carried in the prediction frame (`docs/freqai-configuration.md:166`): `1` = trustworthy; each of DI, SVM, DBSCAN that rejects the row subtracts 1 (so `0` = one detector objected, `-1` = two, `-2` = three); `2` = model expired. Strategies gate on `df["do_predict"] == 1` (`docs/freqai-reinforcement-learning.md:78`). **This is the best single idea in freqtrade for Aegis**: a per-row, per-prediction trust flag with a decomposable cause, travelling in the same frame as the prediction.
- *Outlier protection.* `outlier_protection_percentage` (default 30): if SVM/DBSCAN would discard more than 30% of the training set, FreqAI logs a warning and **ignores outlier detection entirely rather than training on a decimated set** — a refusal, not a silent shrink.
- *Anti-overfit knobs, each documented with its downside.* `noise_standard_deviation` (Gaussian noise on normalised features); `reverse_train_test_order` (*"you should be careful to understand the unorthodox nature of this parameter before employing it"*); `early_stopping_patience` (requires `test_size > 0`); and `continual_learning`, which the parameter table itself disowns: *"this is currently a naive approach to incremental learning, and it has a high probability of overfitting/getting stuck in local minima while the market moves away from your model. We have the connections here primarily for experimental purposes."*
- *Feature-set drift guard.* `check_if_feature_list_matches_strategy` raises `OperationalException` when a reused `identifier` points at a model trained on a different feature list. Loading a stale model against changed features is an error, not a warning.
- *`buffer_timerange`* (`data_kitchen.py:977`) trims **both** edges of the training window by `buffer_train_data_candles` — the correct fix for targets built with `argrelextrema`, which *"cannot know the maxima/minima at the edges of the timerange"*.

**Two look-ahead detectors that never read the strategy source.** The most portable ideas in the repo.

- `lookahead-analysis` (`freqtrade/optimize/analysis/lookahead.py`, `docs/lookahead-analysis.md`): run a full backtest as baseline, then re-run with the dataframe **cut just before each entry/exit signal's timestamp**, and diff the indicator frames (`cut_full_df.compare(cut_df)`) plus the signal timestamps. Any indicator whose value at time *t* changes when future rows are deleted is reported **by column name**. The command forces `--cache none`, `max_open_trades >= len(pairs)`, a 1-billion wallet, a static 10k stake, protections off and market orders — *"These are set to avoid users accidentally generating false positives."* The docs are blunt about salvage: *"Usually the bias in the strategy is THE driving factor for 'too good to be true' profits."*
- `recursive-analysis` (`freqtrade/optimize/analysis/recursive.py`, `docs/recursive-analysis.md`): recompute indicators at `startup_candle_count` ∈ {20, 40, 80, 100, 150, 300, 999} and table the % deviation of the last row against the longest run. It catches the *other* replay-vs-live gap — an EWM-style indicator that has not converged at 500 bars but has at 5,000, so the farm's number is unreproducible live and nobody knows why.

Both are model-free differential tests. Aegis has PIT rules, a network-blocked suite and `feature_leakage_guard`; it does not have a mechanical "prove this feature does not move when you delete the future" harness.

**Common mistakes list** (`docs/strategy-customization.md:1261-1279`) — five rules, at least three of which Aegis has re-derived at cost: no `shift(-1)`; no `.iloc[-1]` inside `populate_*` (safe in callbacks); no whole-column aggregates (`df['volume'].mean()`) — use `rolling()`; `.resample('1h', label='right')` not `.resample('1h')`; and never plain-`merge()` a slower timeframe onto a faster one — *"A plain merge can implicitly cause a lookahead bias as date refers to open date, not close date."* With the honest caveat: *"Please treat them as what they are - helpers to identify most common problems. A negative result of each does not guarantee that there are none of the above errors included."*

**Dry-run vs live separation.** One boolean, `config["dry_run"]`, threaded through the **exchange layer**, not the strategy. `Exchange.__init__` keeps `self._dry_run_open_orders: dict` (`exchange/exchange.py:253`), `create_dry_run_order` (line 1195) mints a synthetic order with the same shape as a real one, and ~18 call sites branch on `if self._config["dry_run"]` for balance, positions, leverage, margin mode, fees and order fetch. `Wallets` starts from `dry_run_wallet` and only reconciles against the venue when `not dry_run or runmode == RunMode.LIVE` (`wallets.py:259`). **Strategy code is byte-identical in both modes.** That is the right layering for Aegis's six paper books: the frozen contract should not know whether it is paper.

**DataProvider / PIT.** `DataProvider` is one object whose behaviour switches on `RunMode`, and the PIT logic sits in two private setters called **by the backtester**, never by the strategy:

```python
def _set_dataframe_max_index(self, pair, limit_index): ...  # "Only relevant in backtesting."
def _set_dataframe_max_date(self, limit_date): ...          # "Only relevant in backtesting."
```

`get_pair_dataframe` then enforces them:

```python
if self.runmode in (RunMode.DRY_RUN, RunMode.LIVE):
    data = self.ohlcv(...)
else:
    data = self.historic_ohlcv(...)
    # Cut date to timeframe-specific date.
    # This is necessary to prevent lookahead bias in callbacks through informative pairs.
    if self.__slice_date:
        cutoff_date = timeframe_to_prev_date(timeframe, self.__slice_date)
        data = data.loc[data["date"] < cutoff_date]
```

and `get_analyzed_dataframe` returns the full frame live but `df.iloc[max(0, max_index - MAX_DATAFRAME_CANDLES) : max_index]` in backtest — a callback that peeks at "the dataframe" gets a **physically truncated** one. `historic_ohlcv` additionally calls `timerange.subtract_start(tf_seconds * startup_candles)` so warm-up data is loaded *before* the evaluation window rather than eaten out of it. The cross-timeframe join is `_prepare_informative_pair` (`strategy/strategy_helper.py`), which forward-shifts the slow frame by `minutes_inf - minutes` before merging and **raises** rather than guesses on the wrong direction: *"Tried to merge a faster timeframe to a slower timeframe. This would create new rows, and can throw off your regular indicators."*

**Control surface.** `freqtrade/rpc/telegram.py:268-311` registers ~40 commands: read (`/status`, `/profit`, `/balance`, `/daily`, `/weekly`, `/monthly`, `/count`, `/locks`, `/order`, `/logs`, `/health`, `/show_config`, `/version`), attribution (`/performance`, `/entries`, `/exits`, `/mix_tags`, `/stats`) and control (`/start`, `/stop`, `/pause`, `/forceexit`, `/forceenter`, `/reload_config`, `/reload_trade`, `/blacklist`, `/unlock`, `/marketdir`, `/cancel_open_order`). The same functionality is a FastAPI app under `rpc/api_server/` (`api_v1.py`, `api_trading.py`, `api_backtest.py`, `api_background_tasks.py`, `api_auth.py`, `ws/`), with a **webserver-only mode** that runs backtests and lookahead-analysis as background tasks and places no orders. `rpc/rpc.py` is the single shared implementation, so Telegram, REST and webhooks cannot drift apart.

### (d) Evidence and its credibility
**freqtrade makes no performance claims whatsoever, and that is the correct answer.** `README.md:13-20` leads with *"This software is for educational purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK."* No bundled strategy carries a track record; `freqtrade/templates/` ships `SampleStrategy` and `FreqaiExampleStrategy` explicitly as scaffolding. `docs/backtesting.md:588-589`: *"backtesting will never replace running a strategy in dry-run mode. Also, keep in mind that past results don't guarantee future success."* So there is no edge evidence here, and none is claimed. What *is* evidenced is the engineering: a large `tests/` suite and behaviour documented down to the fill-assumption level. Read freqtrade as a source of interface designs and negative controls, never as a source of alpha.

### (e) License — **GPL-3.0**, and this constrains use
`C:\Users\mrthn\reference\freqtrade\LICENSE` is the GNU GPL v3. Aegis-Finance is a **public** repo. Copying freqtrade source into it would make the combined work GPL-3.0 and force Aegis to distribute under GPL — a licence change nobody has chosen. The working rule for this whole section:

- **Ideas, interface shapes, parameter names, documented assumptions and algorithms are not copyrightable.** Reimplement `minimal_roi`, the exit ladder, the `IProtection` contract, `do_predict` and the two differential analyses from the descriptions above, in Aegis's own code and idiom.
- **Do not paste `interface.py`, `backtesting.py`, `stoploss_guard.py` or any freqtrade file into Aegis**, even with attribution, unless Aegis relicenses to GPL-3.0.
- Short quotes in an internal review document (this file) are fair use; shipping them is not.
- This is the opposite of TradingAgents (Apache-2.0, §2e), where copying code is fine with a NOTICE line.

### (f) LLM coupling / DeepSeek
**None.** There is no LLM anywhere in the project — no provider clients, no prompts, no `openai`/`anthropic`/`deepseek` dependency. This is a purely numerical, rule-based system. For Aegis that is a feature: freqtrade is the control group showing how far deterministic scaffolding goes with no model in the loop, and every design below is therefore portable without touching the DeepSeek path.

### (g) What Aegis should port

| # | component (source path) | where in Aegis | what it improves | effort |
|---|---|---|---|---|
| 1 | **`do_predict` trust flag** — `freqai/freqai_interface.py::define_data_pipeline` + semantics at `docs/freqai-configuration.md:166`; per-row integer in [-2,2] whose decrements name *which* detector rejected the row | `backend/learner/` — emit `do_predict` beside every prediction; books gate entries on `do_predict == 1` | turns "the model scored this name" into "the model scored it **and the feature vector is inside the training manifold**". Aegis has no in-manifold check at all; the decomposable cause makes the refusal auditable | M |
| 2 | **Model-free look-ahead detector** — `optimize/analysis/lookahead.py` + `docs/lookahead-analysis.md` | new `scripts/lookahead_analysis.py` over the farm's replay path; mandatory before any signal becomes a book | a mechanical test for the failure that has bitten Aegis repeatedly (target leakage, the `IC -0.99` leak, the shuffled-date null). It does not read code, so it catches leaks no reviewer would spot | M |
| 3 | **Recursive / warm-up stability check** — `optimize/analysis/recursive.py` + a `startup_candle_count` field on every feature spec | same script, second mode | catches replay-vs-live divergence from unconverged EWM-style features — the class of bug where a farm number cannot be reproduced live | S |
| 4 | **`minimal_roi` time-decayed exit curve + ranked exit ladder + typed `ExitType`** — `strategy/interface.py:1675-1732` and `:1419-1522` | `aegis-alpha-terminal` `alpha/contract.py` — replace the `expected_horizon_sessions` scalar with `{sessions_held: min_profit}`, give `should_exit` a written priority order | a contract that says "I want 8%, but after 5 sessions I'll take 2%" is more expressive *and* more testable than a fixed horizon; the ranking removes the ambiguity when a stop and a signal fire on the same bar | M |
| 5 | **Protections as declarative circuit breakers** — `plugins/protections/*`, `ProtectionReturn(lock, until, reason, lock_side)`, entries-only locking | new `alpha/protections.py`, evaluated in `run_pass.py` before entries | Aegis's session-protocol rule 4 ("print the worst case in dollars") is a *pre-trade arithmetic* check; this is the *in-flight* one. `MaxDrawdown` in `"equity"` mode and `CooldownPeriod` speak directly to the leverage incident and to "the books re-entered post-expiry" | M |
| 6 | **A published fill/cost assumption list** — `docs/backtesting.md:556-591` | `docs/` beside `portfolio_farm.Policy`; printed in every farm receipt header | Aegis refuses zero costs but has never written its fill convention as an enumerated list. A wrong assumption you can see beats a right one you cannot | S |
| 7 | **`custom_stake_amount` bounded-sizer contract** — `interface.py:625` | the `alpha/` sizing path | the engine hands `min_stake`/`max_stake` and clamps the return, so a learned or LLM-suggested size is bounded *by construction* — the enforceable form of "no LLM authority over real capital" | S |
| 8 | **`strategy_safe_wrapper`** — `strategy/strategy_wrapper.py` | wrap every per-book callback in `run_pass.py` | one bad book cannot take down a six-book pass, the log names the user frame not the wrapper, and the `deepcopy` of `trade` stops a callback mutating shared state. 60 lines | S |
| 9 | **Runmode-switched DataProvider with private `_set_dataframe_max_date`** — `data/dataprovider.py:72-86, 371-425` | `backend/services/` data access for the farm and the learner | makes PIT a property of the **data object** rather than a discipline in every caller — the strategy physically cannot see past the cutoff. Today Aegis's PIT is a convention enforced by review | M |
| 10 | **`_prepare_informative_pair` refusal** — `strategy/strategy_helper.py` (forward-shift, then `raise ValueError` on fast-into-slow) | any join of daily onto intraday, or quarterly fundamentals onto daily | the "TWO CLOCKS NEED TWO BOUNDS" lesson as a function that refuses instead of warning | S |
| 11 | **`IHyperOptLoss` interface + `MultiMetric`'s trade-count penalty** — `optimize/hyperopt_loss/` | the farm's objective layer: one pluggable `objective(results, n, start, end, starting_balance) -> float`, one file per declared personality | CLAUDE.md rule 3 says every ranked comparison names its objective. This is that, as code — and `TARGET_TRADE_AMOUNT` is a cheap n-awareness the farm lacks | S |
| 12 | **Exit-reason / entry-tag attribution reports** — `rpc/rpc.py` `_rpc_exit_reason_performance` / `_rpc_enter_tag_performance`, `optimize/optimize_reports/` | the paper-book nightly report | "which exit reason made or lost the money" is the first question about a live book, and Aegis answers it by hand | S |
| 13 | **The common-mistakes list** — `docs/strategy-customization.md:1261-1279` | five lines in `docs/CLAUDE_LESSONS_2026-08.md` | free; Aegis has re-derived at least three of the five at cost | S |

### (h) What NOT to copy
- **Any source file.** GPL-3.0 — see (e). Reimplement from the descriptions; do not paste.
- **The hyperopt methodology.** No holdout, no CV, no multiplicity control, no PBO, no deflated Sharpe: an Optuna TPE search over a 3-decimal grid with post-hoc leaderboard filters. Aegis's CANON §63/§64 and the DSR/PBO work in S38g are strictly stronger. Port `IHyperOptLoss`, not the search.
- **Zero-slippage fills.** Defensible for a liquid crypto pair on a 5m candle; wrong for a 3,059-name watchlist where `TRADABLE_DOLLAR_VOL` and the execution floor are binding. Keep Aegis's cost model; adopt freqtrade's *documentation habit*, not its numbers.
- **`continual_learning`** — disowned in its own parameter table.
- **Optimising `--space trailing` / `--space roi` on the same history that produced the signal.** That is precisely the construction tax S38 measured (TC 0.13→0.49); freqtrade offers no defence against it.
- **`ignore_roi_if_entry_signal` and the re-entry / position-adjustment logic, unexamined.** It silently converts a take-profit into a hold — the interaction class that emptied hack6.
- **The Telegram command list as-is.** ~40 commands including `/forceenter` is a retail-crypto product decision. Aegis wants read + halt. Port `rpc.py`'s one-implementation-three-transports layering, not the surface.
- **`freqtrade/freqai/RL/`** — a stable-baselines3 environment learning entry/exit actions directly. No evidence is offered for it anywhere in the repo, and it is the highest-variance, least-auditable component in the codebase.

---

## 4. Vibe-Trading (HKUDS) — the LLM strategy factory, with the statistics in the wrong subsystem

Clone at `C:\Users\mrthn\reference\Vibe-Trading\` (HEAD `a4f06a29`, 2026-09-07; `.git/shallow` exists, so history is unavailable — a single squashed commit).

### (a) What it is
An LLM agent workspace that turns natural-language finance questions into runnable backtests: `pyproject.toml` name `vibe-trading-ai` v0.1.14, MIT. Three things run — a `vibe-trading` CLI, a **read-only** MCP server (`agent/mcp_server.py`, 74 tools; the module header states no order tool is ever surfaced over MCP), and a FastAPI app assembled in `agent/api_server.py` over ~15 routers in `agent/src/api/`. There is a React 19 + Vite frontend and an Electron shell.

The ~400k LOC is **real first-party Python** — no vendored dependencies, no data dumps: `agent/src/` 188,919 · `agent/tests/` 163,486 (576 files) · `agent/backtest/` 26,988 · `agent/cli/` 14,881, total 401,046, plus 63,947 lines of markdown and ~36k of TS/TSX. But the count is inflated by *breadth*, not depth: `agent/src/factors/zoo/` alone is 28.6k LOC of ~470 one-formula-per-file alpha modules (alpha101 x103, gtja191 x193, qlib158 x157), and `agent/src/skills/` is 90 skill directories of mostly prose. ~41% of the Python is tests.

### (b) Architecture (paths under `C:\Users\mrthn\reference\Vibe-Trading\`)

```
agent/
  api_server.py           FastAPI assembler (394 L) -> src/api/*_routes.py
  mcp_server.py           3,092 L, 74 read-only MCP tools
  cli/_legacy.py          265KB argparse monolith
  backtest/
    runner.py             1,677 L -- config.json + code/signal_engine.py -> engine
    engines/base.py       2,270 L -- the shared bar loop
    engines/{china_a,global_equity,crypto,forex,korea_equity,india_equity,
             vietnam_equity,china_futures,global_futures,options_portfolio,composite}.py
    loaders/              37 loaders; VALID_SOURCES has 28 entries
    optimizers/           equal_volatility, risk_parity, mean_variance,
                          max_diversification, turnover_aware
    metrics.py  validation.py  factor_costs.py  run_card.py  risk_xray.py
    constraints.py  rebalance_mask.py
  src/
    agent/loop.py         134KB ReAct loop, five-layer context compaction
    agent/grounding.py    157KB anti-hallucination evidence ledger
    tools/                78 auto-discovered BaseTool subclasses; _shell_safety.py
    skills/               90 SKILL.md dirs, progressive disclosure
    swarm/                DAG orchestrator, 29 preset "teams" of 6-12 agents
    quantlib/             27 modules incl. multipletesting.py, crossvalidation.py, impact.py
    factors/              zoo (470 alphas) + registry.py + bench_runner{,_strict}.py
    live/                 mandate/, halt.py, enforcement.py, sdk_order_gate.py, audit
    trading/connectors/   alpaca binance dhan etoro futu ibkr longbridge mt5 okx
                          robinhood shoonya tiger trading212 zerodha
    strategy_discovery/   evidence-gated catalog over completed runs
    governance/           ledger.py (hash chain) + manifest.py (run fingerprint)
    hypotheses/ goal/ memory/ session/ shadow_account/ scheduled_research/
    providers/            llm_providers.json (24 providers), llm.py
```

Persistence is **flat files, no database**: sessions as JSON/JSONL (`src/session/store.py`), memory as markdown-with-frontmatter under `~/.vibe-trading/memory` (`src/memory/persistent.py`).

### (c) Methodology

**Natural language -> executable code**, per `agent/src/skills/strategy-generate/SKILL.md`:

1. the LLM parses intent and writes a `config.json` into a run directory;
2. the LLM writes `code/signal_engine.py` implementing exactly one contract —

```python
class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        # code -> signal in [-1.0, 1.0]
```

3. `ast.parse` syntax check via the `bash` tool;
4. the `backtest` tool (`src/tools/backtest_tool.py`) validates and shells out to `backtest/runner.py` under a 300 s timeout;
5. the LLM reads `artifacts/metrics.csv`, judges it against gates, edits the file, reruns — capped at 3 iterations per `backtest-diagnose` cycle.

There is **no templating and no codegen DSL** — the model writes plain Python against one interface. (The single exception is `src/shadow_account/codegen.py`, which renders a Jinja2 template from a mined trade-journal profile.) This is the direct analogue of Aegis's LLM-mutated strategy genomes, and the difference is instructive: Aegis templates the genome and computes every return in code; Vibe-Trading lets the model write arbitrary Python and then *contains* it.

**Validation and containment of generated code** — two layers, both in `backtest/runner.py`:

- structural: `_validate_signal_engine_source` (line 776) rejects any executable top-level statement, self-imports, and non-defaulted `__init__` arguments;
- a **runtime-reachable AST scrubber** (`_scan_runtime_reachable`, lines ~314-800) that walks only the code reachable from `SignalEngine.generate()` and denies network / process / dynamic-exec / filesystem-write. It denies `importlib`, `builtins`, `sys`, `pkgutil`, `runpy` and the two binary object-serialisation modules by name; blocks `src.trading` and `src.live` by dotted prefix; blocks the process- and environment-mutating `os` helpers (`system`, `popen`, `environ`, `remove`, ...); and blocks object-graph escapes (`__mro__`, `__globals__`, `__subclasses__`). It is unusually honest about its own limits (`runner.py:334-338`):

> `# ... This is defense-in-depth, not a kernel-level`
> `# guarantee: an AST denylist cannot be complete.`
> `# MEASURED RESIDUAL, so it is not left implied. After the lists below, these`
> `# still reach the executed path: inspect, operator, threading, codeop, tempfile, and os.makedirs.`

Defence in depth is a subprocess run as an unprivileged `vibe-sandbox` UID with `RLIMIT_AS` / `RLIMIT_NOFILE` applied post-exec (`src/core/runner.py`, `Dockerfile:104`) — degrading to a *warning* outside the hardened Docker image.

**Backtesting.** Own engine, bar-by-bar, `backtest/engines/base.py` (2,270 lines).

- *Fill model*: signal shifted one bar, filled at the **next bar's open** with slippage — `base.py:244`, *"Signal is shifted by 1 bar (next-bar-open semantics) then normalised"*. Price-limit bands are derived only from `pre_close`/`pre_settle`/prior close, with an explicit look-ahead note at `base.py:604`.
- *Costs, per market, config-overridable*: **US equity commission 0.0**, slippage 5 bps. HK 15 bps commission + 10 bps stamp + SFC/FRC levy + CCASS. UK 0.5% SDRT on purchases only, `Decimal` ROUND_HALF_UP. China A 2.5 bps (Y5 minimum) + 5 bps sell stamp + transfer fee, slippage 10 bps. Canada rounds against the trader on the TSX tick grid. The market-specific microstructure is genuinely good; the US default of zero commission plus 5 bps is thinner than Aegis's own floor.
- *Universe*: whatever tickers the LLM puts in `config["codes"]`. **No survivorship-free universe and no index-membership history.**
- *Data*: 37 loaders (yfinance, tushare, okx, akshare, ccxt, baostock, stooq, finnhub, tiingo, fmp, pykrx, mt5, longbridge...). PIT discipline exists for A-share fundamentals only — `backtest/loaders/tushare_fundamentals.py` cuts on `f_ann_date`/`ann_date`.
- *Frequency*: 1m / 5m / 15m / 30m / 1H / 4H / 1D.
- *Risk*: `backtest/constraints.py` (max/min weight, group exposure caps), `rebalance_mask.py` (execution cadence), a `rebalance_tolerance` drift band, five portfolio optimizers, `risk_xray.py`.

**Overfitting control — and the split that is the headline finding of this section:**

| control | where | wired into what |
|---|---|---|
| DSR, PSR, expected-max-Sharpe, BH-FDR, **PBO via CSCV** | `src/quantlib/multipletesting.py` (568 L) | only `src/factors/bench_runner.py`, the 462-alpha zoo bench |
| purged + embargoed + combinatorial CV, `detect_boundary_leakage()` | `src/quantlib/crossvalidation.py` (585 L) | **no production caller** — agent-callable only, via `quantlib_tool` |
| random-control shuffle + train/test OOS gate | `src/factors/bench_runner_strict.py` (629 L) | opt-in, alpha zoo only |
| Monte-Carlo permutation, bootstrap Sharpe CI, N-window walk-forward | `backtest/validation.py` (505 L) | **opt-in** — runs only if `config["validation"]` is present |

So the strategy-generate loop that the entire product is built around — LLM writes code, sees metrics, tweaks parameters, reruns — has **no trial counting and no multiplicity correction of any kind**. The DSR/PBO machinery exists, is well written, and lives in a different subsystem that the loop never calls. The skill's own worked `action_items` are literally *"Change short MA from 5 to 10 days to reduce whipsaw signals"*. To their credit the review criteria deliberately refuse to grade on performance: *"Poor return / low Sharpe alone should not push the score below 60; they are optimization suggestions only."*

### (d) Evidence and its credibility
**There is no cost-aware, P&L-level, or forward-traded performance evidence in this repository.** Stated plainly because it matters:

- the 283KB README claims no Sharpe, return or accuracy figure for the product; `accuracy`, `leaderboard` and `BibTeX` appear zero times; there is no paper;
- zero notebooks, zero logs, zero `runs/` / `results/` / `artifacts/` directories, zero db or parquet files. The 23 committed CSVs are alpha-formula golden fixtures on **synthetic** series (`agent/tests/factors/fixtures/goldens/`);
- `agent/evals/` is an **LLM-behaviour** harness, not a performance eval — it is *"deterministic and read-only: it does not call an LLM, invoke a tool, load market data."* Exactly one case is committed (A-share vs H-share identity disambiguation), with no scored results;
- the single genuine out-of-sample result is a blog post, `wiki/research-lab/posts/alpha-191-in-2026.html`: of the 191 GTJA alphas on CSI 300 over 2018-2025, **10 (5%) alive, 15 (8%) reversed, 165 (87%) decayed**, best `gtja191_171` at IC 0.0432 / IR 0.269. Its own stated caveats: *"1-day IC is not profitability... No t-cost adjustment... No sector neutralisation... Survivorship bias in the universe"* (current CSI 300 constituents applied retroactively). The raw bench output is not committed.

That last item is the most useful number in the repo and it is a **negative** result, honestly caveated — 87% decay on a public alpha zoo is a better prior for Aegis than any headline the project could have claimed. Cost per run is not stated anywhere; token usage is persisted per run as `llm_usage.json`, explicitly *"provider-reported only; no price estimation."*

### (e) License
**MIT** (`LICENSE`, "Copyright (c) 2026 Vibe-Trading Contributors"). Copying into Aegis (also public) is clean — one MIT header line travels with each ported file. `NOTICE` adds two wrinkles: `src/factors/zoo/qlib158/` bundles Microsoft Qlib feature definitions under **Apache-2.0** (that subtree carries extra obligations), and the alpha101/gtja191/academic formulas are reimplemented as uncopyrightable mathematics with per-directory `LICENSE.md`. Frontend fonts are OFL 1.1. Nothing here is copyleft. This is the **most permissive and most portable** of the four trading repos.

### (f) LLM coupling / DeepSeek
24 providers in `agent/src/providers/llm_providers.json`, all OpenAI-compatible via `base_url` except a native Anthropic Messages path and two OAuth paths (Codex, Copilot).

**DeepSeek is supported out of the box and is the shipped default.** `agent/.env.example:8` is uncommented:

```
LANGCHAIN_MODEL_NAME=deepseek/deepseek-v4-pro
```

with the direct provider entry `{"name": "deepseek", "api_key_env": "DEEPSEEK_API_KEY", "base_url_env": "DEEPSEEK_BASE_URL", "default_base_url": "https://api.deepseek.com/v1"}`, plus an optional native `langchain-deepseek` adapter behind `VIBE_TRADING_DEEPSEEK_ADAPTER=auto|native` (`src/providers/llm.py:870`), and SiliconFlow CN/global and OpenRouter as alternative DeepSeek routes. For Aegis, whose only provider is DeepSeek, this is the one repo in the five that needs **no** provider work to run as-is.

### (g) What Aegis should port

| # | component (source path) | where in Aegis | what it improves | effort |
|---|---|---|---|---|
| 1 | **`agent/src/tools/_shell_safety.py`** (59 L) — `broad_python_kill_error()`, regexes for `taskkill /IM python*`, `pkill`/`killall ... python`, PowerShell `Stop-Process -Name python` and `Get-Process python \| Stop-Process`; splits on `;`/`&`/newline, quote- and whitespace-normalised | a PreToolUse Bash guard for both repos (pairs with §1's `gateguard-fact-force.js`) | **this is the code fix for the 2026-09-06 incident** that killed two agents' jobs, a test suite, ~1,676 already-billed extractions and the Optimus MCP server. Its error text even names the alternative: *"Use cancel_background with the task_id returned by background_run."* CLAUDE.md protocol §6 is currently prose | **S** |
| 2 | **`agent/src/quantlib/multipletesting.py`** (568 L) — DSR, PSR, expected-max-Sharpe, BH-FDR, PBO via CSCV | `backend/services/` or `engine/stats/` | Aegis computes DSR/PBO ad hoc per session (S38g). This is a tested library, and its header documents the two gotchas Aegis has already hit (per-observation vs annualised Sharpe; non-excess kurtosis). Serves CANON §63/§64 directly | **S** |
| 3 | **`agent/src/quantlib/crossvalidation.py`** (585 L) — purged / embargoed / combinatorial-purged splits + `detect_boundary_leakage()` | `backend/learner/` | CLAUDE.md mandates purged CV with embargo; this is a clean implementation *with* the off-by-one self-check that the mandate does not describe | **S** |
| 4 | **`agent/backtest/factor_costs.py`** (416 L) + **`agent/src/quantlib/impact.py`** (281 L) — ADV participation cap (10%) with **shortfall carried forward**, not silently filled or dropped; sqrt/linear impact; borrow cost by market | `scripts/portfolio_farm*` | upgrades the farm's cost realism above `Policy`'s flat rates and expresses `TRADABLE_DOLLAR_VOL` in weight space instead of as a pre-filter. The carried-forward shortfall is the part Aegis lacks: an unfillable target becomes a *tracked deficit*, not a rounding | **M** |
| 5 | **`breakeven_fee_bps`** in `agent/src/strategy_discovery/models.py` (~30 L of 453) — `ln(1+gross)/(2*trades*size)*10_000` | a column on every farm result row | the fee level at which the edge vanishes, printed beside every book — the cheapest possible enforcement of "quote the cost rate or don't quote the count", and directly comparable across books with different turnover | **S** |
| 6 | **`agent/src/governance/ledger.py`** (738 L) — hash-chained, fsynced, append-only JSONL that **raises `LedgerCorruptionError` and refuses to extend a broken chain** | the terminal repo's ledger | Aegis's ledger hash chain has been broken since 25 Aug and has printed 53+ times without blocking anything. A chain that refuses is a chain; one that warns is a log | **M** |
| 7 | **`agent/src/governance/manifest.py`** (566 L) — `RunManifest`: content-addressed hash of system prompt + per-skill `(name, content_hash)` + tool registry + package versions, with `timestamp`/`run_id` **deliberately excluded** so identical methodology hashes identically across days | receipts / run cards | answers "did the methodology change between run A and run B", which Aegis cannot currently answer for LLM-in-the-loop runs. Note upstream ships it **unmounted** — nothing calls it, so port the design and verify the wiring yourself | **M** |
| 8 | **`agent/backtest/run_card.py`** (249 L) — sha256 of config + strategy source + **every artifact**, emitted as JSON *and* markdown | Aegis receipts | near-identical to Aegis's receipt concept; the per-artifact hash list is the missing piece ("a headline number belongs in a receipt", plus "and the receipt names the bytes it came from") | **S** |
| 9 | **`agent/src/live/{halt,enforcement,sdk_order_gate}.py` and `live/mandate/{model,commit}.py`** (~1,600 L) — `HardCaps(max_order_notional_usd, max_total_exposure_usd, max_leverage, allowed_instruments, max_trades_per_day)` as a frozen dataclass; a **filesystem-sentinel kill switch** (`live/HALT`) enforced independently of the LLM; and structurally, `commit_mandate` is **not** a `BaseTool` subclass, so the agent's tool registry cannot reach it | the terminal repo's six paper books | this is "no LLM authority over real capital" implemented in code rather than declared in prose. `max_total_exposure_usd` would have blocked the 300%-gross book of 28 Aug; the not-a-tool trick is a stronger guarantee than any prompt | **L** |
| 10 | **The reachability-scoped AST scrubber** — `agent/backtest/runner.py:314-800` + post-exec rlimits and UID drop in `src/core/runner.py` | LLM-mutated strategy genomes | if Aegis ever executes genome code it did not template, this is the reference implementation — *including its measured-residual disclosure*, which is the part to copy culturally: a guard that publishes what still gets through | **M** |
| 11 | **`agent/src/factors/registry.py`** (453 L) + the `__alpha_meta__` convention in any `zoo/*/alpha_*.py` — a dict literal read by **AST scan, never import**, carrying `theme`, `columns_required`, `universe`, `min_warmup_bars`, `decay_horizon` | `backend/learner/` feature families | kills the unreachable-module class of bug at the metadata layer (Aegis's `signal_reachability.py` catches it at test time; this prevents it), gives the farm a typed feature catalogue, and `min_warmup_bars` is exactly freqtrade's `startup_candle_count` (§3 g#3) | **M** |
| 12 | **`agent/backtest/validation.py`** (505 L) — Monte-Carlo trade-permutation p-value + bootstrap Sharpe CI + N-window walk-forward with a `consistency_rate`, written out as a JSON block | the farm | cheap, already receipt-shaped, and the `consistency_rate` across windows is the number that would have flagged "83.6% of the excess is five months" without anyone having to go looking for it | **S** |
| 13 | **`agent/src/tools/quantlib_tool.py`** (453 L) — one allowlisted "call any function in these 27 modules" tool, with a writer-prefix exclusion and a 5,000-leaf result cap | Aegis's MCP / tool surface | one tool instead of dozens of hand-written wrappers, with the cap that stops a tool result eating the context | **S** |
| 14 | **`agent/src/agent/skills.py::split_sections`** — section-addressed skill paging (`"Mode 3 > Workflow"`) instead of character paging, motivated by *"35 of the 88 skills do not fit a single tool result"* | `.claude/skills/` in both repos | Aegis's five discipline skills are already long enough to hit this | **S** |

Worth *reading* rather than porting: `agent/src/factors/bench_runner_strict.py` (a same-universe random-control shuffle as the gate, citing Harvey-Liu-Zhu's |t| ~ 3.5 — the same construction as Aegis's model-null work), and `agent/src/agent/grounding.py`'s evidence ledger (a price claim may not contradict the untruncated tool result, and a figure may not attach to an instrument no tool call ever returned — a stronger version of TradingAgents' verified-snapshot idea from §2 g#1).

### (h) What NOT to copy
1. **The strategy-generate iteration loop as-is.** LLM writes code -> reads metrics -> tweaks parameters -> reruns, up to 3x per diagnose cycle, with no trial counter anywhere. It is an overfitting machine wearing a hard-gate checklist that only checks for crashes. Port the sandbox, the run card and the cost model; leave the loop.
2. **~25 of the 90 skills are retail-TA folklore** — `elliott-wave`, `chanlun`, `harmonic`, `smc` (ICT "smart money"), `ichimoku`, `candlestick`, `seasonal`. They generate hypotheses with nothing that adjudicates them; Aegis's rule that every intuition is owed *"what observation would separate this from ordinary factor beta?"* is exactly what they lack.
3. **`agent/src/hypotheses/registry.py`.** Presented as a hypothesis registry; it is a mutable JSON blob whose `update()` rewrites `thesis`, `signal_definition` and `status` in place with only an `updated_at` bump. No hash, no freeze, no decision rule, no earliest-decision date. Aegis's `pre-register-trial` skill is strictly stronger — importing this would be a downgrade wearing the right name.
4. **The default benchmark.** With `config["benchmark"]` unset, `engines/base.py:925` uses `bench_ret = ret_df.mean(axis=1)` — the equal-weight average of the strategy's *own traded universe*. Aegis has already paid for exactly this ([[an-EW-average-against-a-VW-market-is-the-regime]]).
5. **`backtest/metrics.py` has `benchmark_beta` but no regression alpha**; `excess_return` is a raw difference, not an intercept. Given S43 ("the ruler changed — excess is a LOADING"), this metric block must not be adopted unmodified.
6. **The monoliths.** `loop.py` 134KB, `grounding.py` 157KB, `mcp_server.py` 123KB, `cli/_legacy.py` 265KB. Whatever is worth taking from these, take by reimplementation.
7. **The 28-source loader layer and the Chinese-market coupling.** tushare/akshare/eastmoney/mootdx/baostock exist for A-shares; Aegis has CRSP/IBES/TAQ parquets. `extra_fields` and `fundamental_fields` are tushare-only by design.
8. **The 14 broker connectors and the live runtime.** Aegis needs Alpaca paper only. Take the mandate/halt/gate primitives (g#9); do not import the connector fleet, the `pending_action` re-auth state machine, or `live/runtime/runner.py` (46KB).
9. **The decay thresholds in `src/skills/strategy-dev-manager/references/decay_thresholds.md`** (IC ratio > 0.7 "healthy", IR > 1.0, Sharpe > 1.0). The hysteresis state machine is a good shape; the numbers have no evidence behind them and would import a false floor.
10. **`agent/evals/` as a template for performance evaluation.** It grades agent behaviour, not strategy skill. Useful as a model for auditing LLM output discipline; useless as a performance harness.

---

## 5. OpenAlice (TraderAlice) — a workbench for the plumbing around a decision

Clone at `C:\Users\mrthn\reference\OpenAlice\` (HEAD `52b51f29`, single squashed commit "Merge PR #1373", version `0.91.1`, remote `github.com/TraderAlice/OpenAlice`).

### (a) What it is
An **agent orchestration workbench for discretionary trading research — not a quant system.** Its own tagline (`README.md:9`): *"The AI orchestrator for trading. Your one-person Wall Street."* An Electron/web app that launches third-party coding-agent CLIs inside git-backed "Workspaces", gives them market-data tools, and routes any resulting order through a git-verb (stage / commit / push) approval flow to a broker.

**One correction to the header table:** the "TypeScript monorepo + Python sidecar" description is wrong. It is a pnpm/turbo TypeScript monorepo — 1,959 `.ts` + 376 `.tsx`, ~218k non-spec LOC (`src` 68k, `ui/src` 106k, `services` 20k, `packages` 15k). Of the 256 `.py` files, **252 are Interactive Brokers' vendored reference client** (`packages\ibkr\ref\source\pythonclient\ibapi\*` plus `ref/samples`) and 4 are asset-packaging scripts. There is no Python service, no `requirements.txt`, no `pyproject.toml`.

The Python *does* exist — **in a different repository that is not in this checkout.** `src\workspaces\templates\auto-quant-v2\template.json` pins a git clone of `https://github.com/TraderAlice/Auto-Quant-V2.git` at `v0.9.34` / commit `52d63148…`, whose README describes a Python 3.11 `uv`-managed `aq` CLI; same for `Auto-Prediction`. **All quantitative research machinery lives outside what we have.** Any claim about OpenAlice's quant capability from this clone alone would be an inference, not an observation — noted explicitly, per the "absence of a local object is not evidence of absence" rule.

What runs: a Guardian supervisor -> `UTA` (trading service, loopback) + `Alice` (product/API) + a Vite/Electron renderer, optionally a Connector service (Telegram/Discord/Slack/Feishu). `pnpm dev`, `docker compose up`, or the desktop app.

### (b) Architecture (paths under `C:\Users\mrthn\reference\OpenAlice\`; owner map at `docs\project-structure.md`)

| path | what it holds |
|---|---|
| `src/` | **Alice**: `core/` (70 files — config, paths, sealing, event-log, tool-call-log, provenance-store, entity-store, inbox-store, migrations), `ai-providers/` (preset catalog only — no model loop), `domain/{market-data,analysis,news,thinking}`, `tool/` (agent-facing tool definitions), `workspaces/` (PTYs, adapters, templates, issues, schedules, CLI shims), `webui/` (Hono), `server/` (MCP + CLI gateway), `migrations/` |
| `services/uta/` | **UTA**: broker connections, accounts, `domain/trading/git/` (Trading-as-Git), `guards/`, snapshots, FX — all trading writes |
| `services/connector/` | Telegram/Discord/Slack/Feishu Inbox delivery, with `core/io-journal.ts` + `io-replay.ts` |
| `packages/uta-protocol` | the wire contract shared Alice<->UTA (`types/{broker,git,history,manager}.ts`, `brokers/preset-catalog.ts`) |
| `packages/uta-broker-*` | Alpaca / CCXT / IBKR / LeverUp / Longbridge "broker packs" — each a ~9-line re-export of the in-repo broker |
| `packages/ibkr` | TWS wire protocol, 203 `.proto` files, vendored IB Python reference client |
| `packages/guardian-runtime` | single-writer locks, heartbeat, process identity, takeover |
| `packages/cli`, `apps/desktop`, `ui/` | installable CLI, Electron shell, React/Vite renderer |
| `safe/` | an agent-first **red-team kit**: `THREAT_MODEL.md`, `playbooks/01-auth-bypass.md`…, `findings/`, `harness/runner.ts` |

**Broker adapters** implement `IBroker` (`packages\uta-protocol\src\types\broker.ts:477-620`): `placeOrder / modifyOrder / cancelOrder / closePosition / getAccount / getPositions / getOrders / getQuote / getMarketClock / getCapabilities / getNativeKey / resolveNativeKey`. Alpaca (`services\uta\src\domain\trading\brokers\alpaca\AlpacaBroker.ts:146-149`):

```ts
this.id    = config.id    ?? (config.paper ? 'alpaca-paper' : 'alpaca-live')
this.label = config.label ?? (config.paper ? 'Alpaca Paper' : 'Alpaca Live')
```

That id then prefixes every instrument handle — `aliceId = "{accountId}|{nativeKey}"`, e.g. `alpaca-paper|AAPL`. Bars use a parallel `barId = "{sourceId}|{nativeSymbol}"` with **no cross-source normalisation — "redundancy is the feature"** (`src\domain\market-data\bars\types.ts:1-14`).

**Persistence: files, no database.** One `OPENALICE_HOME` (`~/.openalice`) holding `data/` (portable), `sealing.key` (machine-bound, deliberately *outside* `data/`), `workspaces/`, `runtime/`. Journals are append-only JSONL with an in-memory ring buffer (`src\core\event-log.ts`, `src\core\tool-call-log.ts`). State changes go through numbered migrations with a generated index (`src\migrations\registry.ts`, `INDEX.md`).

### (c) Methodology

**How a decision is made — there is no in-house agent loop.** A human asks in a Workspace; an *external* agent CLI runs its own model loop; it reaches OpenAlice's tools **through shell shims on PATH** (`alice`, `alice-workspace`, `alice-uta`, `traderhub`), not through MCP. `src\workspaces\context-injector.ts:21`: *"The launcher injects NO MCP into workspaces at all… these skills are how the agent learns the CLI surface that is now its ONLY path to OpenAlice's tools."* Claude headless is locked to exactly those four (`adapters\claude.ts:85`: `'Bash(alice:*)','Bash(alice-workspace:*)','Bash(alice-uta:*)','Bash(traderhub:*)'`). `src\workspaces\adapters\index.ts` registers `claude, codex, cursor, agy, grok, omp, opencode, pi, shell` and spawns them as child processes (PTY when interactive, plain `spawn` when headless). 95 tools total (73 global + 22 workspace-scoped), defined with Vercel-AI-SDK `tool({description, inputSchema: z.object(…), execute})` and re-exported over MCP at `/mcp` and `/mcp/:wsId`.

Method lives in **prompts**, not code: `default\skills\build-thesis\SKILL.md` (left side = variant view vs consensus, right side = relative strength / rotation, "no variant view, no edge"), plus `scan-value-chain`, `sector-rotation`, `retrospective`, `delegate-autoquant`.

**Learning / memory: none.** Zero embeddings, vectors, RAG, or outcome->policy feedback anywhere. "Memory" is git-committed markdown, JSONL journals, and an Inbox/Issue/entity index the model must choose to re-read. `src\core\entity-store.ts` is a four-field `[[wiki-link]]` watchlist, explicitly *"never parse prose to infer entities."*

**Backtester: one 185-line single-name replayer, no costs, no statistics.** `src\domain\analysis\simulate.ts` takes an entry date and one exit rule (`trailing_stop | ma_break | stop | target | hold`) and returns `returnPct`, `mfePct`, `maePct`, `open`. Its discipline is fine as far as it goes (`simulate.ts:124`: *"exit checks evaluate from the bar AFTER entry"*; the fetch window is capped at `asOf`). But repo-wide and case-insensitive, over `src/`, `services/` and `packages/uta-protocol/`: **`sharpe` 0 hits, `drawdown` 0 hits, `sortino` 0 hits** (verified directly). No commission, no slippage, no portfolio, no benchmark, no walk-forward, no out-of-sample. `ui\src\pages\portfolio-metrics.ts` is 25 lines computing today's percentage change — that is the entirety of portfolio analytics.

**Risk controls: a good framework, empty by default.** `services\uta\src\domain\trading\guards\` defines `OperationGuard.check(ctx) -> string | null` over a `GuardContext {operation, positions, account}`, with the pipeline as the only thing that touches the account. Three guards exist: `max-position-size` (per-symbol % of equity, default 25), `cooldown` (60 s/symbol), `symbol-whitelist`. But `src\core\config.ts:454` is `guards: z.array(guardConfigSchema).default([])` (verified) and `guard-pipeline.ts:17` is `if (guards.length === 0) return dispatcher` — **out of the box every order is unchecked.** There is no notional cap, no gross-exposure cap, no daily loss limit, no leverage cap, no fat-finger price band, no dry-run mode. `MaxPositionSizeGuard` fails **open** on exactly the case that matters (`max-position-size.ts:36`): *"If we can't estimate (new symbol + qty-based without existing position), allow — broker will validate."* No idempotency key or client order id exists anywhere (`orderRef` is never assigned).

**Paper vs live: two unrelated axes, neither enforced at the order.** `tradingMode: 'lite'|'readonly'|'pro'` (`src\services\trading-mode.ts`) is off / read-only / on and is env-lockable via `OPENALICE_TRADING_MODE` (`envLocked: true`) — but it is enforced **only in Alice's proxy and SDK**; `grep TRADING_MODE services/uta/src` returns nothing, so a direct loopback POST to UTA bypasses it. Paper-ness is a per-account config flag (`AlpacaBroker.configSchema`: `paper: z.boolean().default(true)`); `isPaperPreset` exists but is **never consulted in the order path**.

**Human approval.** `agent.allowAiTrading`, default `false`, read live at call time, enforced in one place (`src\tool\trading.ts:786`):

```ts
if (!allowAiTrading()) {
  return { message: 'Push requires manual approval (AI trading is disabled). Tell the user to review and approve the pending operations in the Web UI…', pending: … }
}
```

Both the MCP tool and the `alice-uta git push` CLI route to the same tool (`src\server\cli-commands.ts:284`: `push: 'tradingPush'`), so the gate covers both surfaces. It is a *tool-layer* gate, though: the underlying `POST /wallet/push` route is unauthenticated loopback, and `services\uta\src\domain\trading\order-entry.ts:19-23` documents a deliberate one-shot stage->commit->push bypass for the Web UI form.

**Kill switch: none.** No `killSwitch`, `halt`, `panic`, `flatten` or `closeAll` in the trading domain. The only stop levers are an env change plus restart (`lite`/`readonly`), flipping `allowAiTrading`, or per-account auto-disable on `CONFIG`/`AUTH` errors only.

**Audit trail — the best thing in the repo.** `packages\uta-protocol\src\types\git.ts:93-102`:

```ts
export interface GitCommit {
  hash: CommitHash          // sha256(JSON).slice(0,8)
  parentHash: CommitHash | null
  message: string           // the thesis
  operations: Operation[]
  results: OperationResult[]
  stateAfter: GitState      // netLiq, cash, uPnL, rPnL, positions[], pendingOrders[]
  timestamp: string
}
```

`Operation` is a discriminated union that includes `observeExternalOrder` (an order placed outside the system) and `reconcileBalance` (a broker balance change the system did not cause) — so the ledger stays faithful instead of pretending it is the only actor. Rejections are recorded rather than deleted (`[rejected] …`, status `'user-rejected'`). Push carries an optimistic-concurrency token: `push(expectedPendingHash)` -> `PendingHashConflictError('Pending commit changed')`. And `src\core\provenance-store.ts` links each `{kind:'trade-decision', accountId, decisionId}` back to `{workspaceId, resumeId, agent, execution}` — with the identity stamped **server-side from spawn context**, never claimed by the agent.

### (d) Evidence and its credibility
**There is none, and the project does not pretend otherwise.** `README.md`, `CHANGELOG.md`, `AGENTS.md`, `PLANS.md`, `docs/README.md` + ~40 docs and `docs/incidents/` contain no track record, no returns, no P&L, no hit rate, no decision-quality evaluation, no agent benchmark, no held-out test of anything. The only outcome statement in the repository is a disclaimer (`README.md:105-109`):

> **Trading execution is beta.** Start with simulator, paper, demo, or testnet accounts. OpenAlice is experimental software… it provides **no guarantees of correctness, reliability, profitability, or loss prevention.**

The product is positioned entirely as orchestration, never as edge. What it *does* have is engineering evidence: 743 spec files, a four-axis test taxonomy, and one written postmortem (`docs\incidents\2026-07-28-broker-pack-upgrade-gap.md`).

### (e) License — **AGPL-3.0**, the strictest of the five
`LICENSE` is verbatim GNU AGPL-3.0 (35 KB, "Version 3, 19 November 2007"); `README.md:184` confirms. `CHANGELOG.md` records an *"AGPL-3.0 relicense"* — it was not always AGPL. There is no CLA, no copyright assignment in `CONTRIBUTING.md`, and **no per-file SPDX headers** (grep for `SPDX` over `src/ services/ packages/uta-protocol/` returns zero).

Implications for Aegis, which is public and serves a FastAPI backend:

- **Copying code** — any TS file, or a line-by-line Python transliteration of one — makes the derivative AGPL-3.0. AGPL §13 additionally requires offering Corresponding Source to **users interacting with the software over a network**, which a FastAPI backend does. That would bind the whole Aegis backend, not just the copied file. This is strictly worse than freqtrade's GPL-3.0 (§3e), which at least does not reach network users.
- **Copying ideas** — schemas, guard interfaces, naming, workflow shape, the git-verb approval concept, the freshness-contract fields — is not copyrightable expression.
- **Working rule**: read the TypeScript, write a one-paragraph spec in your own words, close the file, implement from the spec. Do not paste doc comments or prompt text — the `SKILL.md` files are as copyrightable as the code.
- Attribution costs nothing: "design informed by TraderAlice/OpenAlice (AGPL-3.0)" in a docs file, with no code copied.

### (f) LLM coupling / DeepSeek
14 provider presets in `src\ai-providers\preset-catalog.ts:606`: `CLAUDE_OAUTH, CLAUDE_API, CODEX_OAUTH, CODEX_API, XAI_API, OPENROUTER, MINIMAX, GLM, KIMI, DEEPSEEK, LONGCAT, GEMINI, CURSOR_DASHBOARD, CUSTOM`.

**DeepSeek is first-class** (`preset-catalog.ts:481`), and interestingly it is routed over DeepSeek's *Anthropic-compatible* endpoint so that the Claude Agent SDK drives it:

```ts
export const DEEPSEEK: PresetDef = {
  id: 'deepseek',
  description: 'DeepSeek models via Claude Agent SDK (Anthropic-compatible)',
  zodSchema: z.object({
    backend: z.literal('agent-sdk'),
    baseUrl: z.string().default('https://api.deepseek.com/anthropic'),
    model: z.string().default('deepseek-v4-pro'),
    apiKey: z.string().min(1),
  }),
  regions: [{ id: 'default', wires: {
    anthropic: 'https://api.deepseek.com/anthropic', 'openai-chat': 'https://api.deepseek.com',
  }}],
```

So it declares **both wires** — the Anthropic-shaped one and the OpenAI-compatible one. `WireShape` is `'anthropic' | 'google-generative-ai' | 'openai-chat' | 'openai-responses'` (`preset-catalog.ts:61`), and the `CUSTOM` preset (`:580`) accepts any `baseUrl` + provider. Credentials reach the child process **only via env, never argv** (`adapters\claude.ts:227`: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_API_KEY`). That `https://api.deepseek.com/anthropic` route is a small, concrete finding for Aegis: it means a Claude-shaped agent harness can be pointed at DeepSeek without an OpenAI-compat shim — relevant to CLAUDE.md's "the Claude branch stays, dormant" position.

`src\ai-providers\model-semantics.ts` (496 lines) is a static per-model fact table: `contextWindow`, `maxOutputTokens`, `reasoning:{mode, efforts, defaultEffort}`. **No pricing table and no cost math** — the DeepSeek per-token prices exist only as prose in a UI hint string (`preset-catalog.ts:487`: *"V4 Flash costs $0.0028/M cache-hit input, $0.14/M cache-miss input, and $0.28/M output"*). **Cost controls: none** — no token accounting, no spend ledger, no budget, no cap. Per-turn metrics are `{textBlocks, toolCalls, toolFailures}` (`src\workspaces\agent-runtime-log.ts:52`). Cost is the external CLI's and the provider dashboard's problem — which is exactly the position Aegis rejected when it built `llm_cost_audit`.

### (g) What Aegis should port — patterns, not code (AGPL: reimplement from spec)

| # | source (read for the idea) | where in Aegis | what it improves | effort |
|---|---|---|---|---|
| 1 | **The freshness contract** — `src\domain\market-data\bars\types.ts:80-92`: `{asOf, isLatestActual, staleTradingDays}` + `freshnessWarning`, returned on **every** bar/snapshot read | the market-data return envelope in `backend/services/`; `backend/learner` feature loaders | kills the "stale close reported as current price" class outright. Aegis has PIT discipline in research but no machine-checkable staleness field on live reads. Pairs with the `retrospective` skill's rule *"an empty window means 'not in the feeds', NOT 'nothing happened'"* — which is [[SILENCE IS NOT EVIDENCE]] as a data field | **S** |
| 2 | **Test lanes keyed by risk and side effects** — `scripts\test-lanes.mjs:80-127`: `hermetic / integration / external-readonly / live-paper / system`, each with declared `sideEffects` and `prerequisites`. Two prerequisites are literal strings: *"an all-skipped run is not acceptance evidence"* and *"restore positions and open orders to the pre-run baseline after success or failure"*. `vitest.uta-live.config.ts:15` calls `assertLivePaperAcknowledgement()` at **config load**, so the suite cannot even load without `OPENALICE_UTA_LIVE_PAPER=1` | `pytest.ini` markers + `backend/tests/conftest.py`, extending the existing `-m "not slow"` split | Aegis has the network-blocked/slow axis; this adds the missing one — *which suites may touch a real paper account, and what must be true before and after*. "An all-skipped run is not acceptance evidence" is the `silent-fragility-audit` house failure mode encoded as data, and it is the same shape as "a check that did not run is not a check that passed" | **S-M** |
| 3 | **The `Operation` union with `observeExternalOrder` and `reconcileBalance`, plus `stateAfter`** — `packages\uta-protocol\src\types\git.ts:22-102` | the terminal repo's ledger / paper-book records | the ledger stops lying when a fill, transfer or manual action happens outside the system, instead of silently drifting from broker truth. `stateAfter` (netLiq, cash, uPnL, rPnL, positions, pendingOrders) after every commit is exactly the NAV audit row Aegis wants — and would have made "lane NAVs marked STALE" visible as a typed event | **M** |
| 4 | **The guard pipeline shape** — `services\uta\src\domain\trading\guards\{types,guard-pipeline,registry}.ts`: `check(ctx) -> str \| None`, one pipeline that assembles the context so guards never touch the account, plus a name-keyed factory registry | new `backend/risk/guards.py` + per-book guard config | a clean seam for the checks Aegis needs and OpenAlice conspicuously lacks: gross exposure `Sum|notional|/equity`, worst case `n x notional% x stop%`, per-name cap, daily loss. **Port the shape; write the guards CLAUDE.md §4 already specifies.** Composes with freqtrade's `IProtection` (§3 g#5), which is the same idea at the portfolio level | **M** |
| 5 | **A live-read master switch that returns the pending intent** — `src\tool\trading.ts:786` + `src\core\config.ts:249`: `() => config.agent.allowAiTrading`, default `False`, no restart needed to revoke, and the refusal hands the pending operations back to the model | the terminal repo's arm/disarm | Aegis's `AAT_MANAGE_ONLY` was found **inert** (memory S38f). A live-read getter, plus a refusal that returns *what would have happened*, is strictly better than an env var captured at import — and the returned intent is itself a shadow-book record | **S** |
| 6 | **Server-stamped provenance** — `src\core\provenance-store.ts`: `{artifact, action, origin, at, fingerprint, mutation}` where `origin` comes from spawn context, never from tool arguments (`docs\conversation-provenance.md`: *"An agent does not claim an arbitrary origin through tool arguments"*), and `ACTIVITY_UPDATE_COALESCE_MS` collapses autosaves | Aegis receipts / trial registry | answers "why did you take this trade?" by resuming the exact session; `fingerprint` makes an append idempotent, which Aegis's receipt files need | **M** |
| 7 | **Workspace-scoped tool factories** — `src\core\workspace-tool-center.ts:1-24`: the caller's identity is baked in server-side from the URL, so `inbox_push({docs})` has **no identity parameter**. *"Forgery surface is zero because the URL is the only identity carrier"* | Aegis book/lane tools exposed to any agent | an LLM cannot write to the wrong paper book by passing the wrong id, because there is no id to pass. Structural, not prompted | **S-M** |
| 8 | **Live-paper dogfooding ground rules** — `docs\uta-live-testing.md:129-158`: agent-surface-only, record pre-run positions as the cleanup baseline, *"Never trust the ledger over the venue"*, *"Leave accounts flat"* (0 open orders, clean status, baseline quantities), price-band re-quoting, a regression spec per bug found. Its header reports five rounds surfacing ~20 bugs *"no unit test and no human UI session would ever catch"* | `docs/` + the `verify-prod-after-deploy` skill | directly applicable to the six Alpaca paper books; it is a written procedure, so porting is writing it down. *"Never trust the ledger over the venue"* is the one-line version of the whole reconciliation problem | **S** |
| 9 | **The incident template** — `docs\incidents\2026-07-28-broker-pack-upgrade-gap.md`, six sections, especially **"Why release checks missed it"** (*"The missing test was an existing-user upgrade, not a fresh install"*) and a closing **"Release invariant"** that converts the postmortem into a permanent gate | `docs/` postmortems (Aegis already has `aegis_postmortems`) | Aegis's postmortems record what happened; this adds *why every existing gate was blind to it*, plus a one-sentence invariant. Cheap, high yield, and directly relevant to the mtime-dated CI gate | **S** |
| 10 | **Credential sealing** — `src\core\sealing.ts`: AES-256-GCM envelope `{$sealed:1, alg, iv, tag, data}`, key at `<home>/sealing.key`, **deliberately outside the portable `data/` subtree**, with an honest threat model in the docstring (*"What this does NOT buy: same-user malware… can read the key file exactly like we do"*) | Aegis `.env` / broker credential handling | backups, cloud sync and an agent `cat`-ing a config stop leaking broker keys. The versioned envelope allows a later move to an OS keychain without a format break. Relevant given the 2026-08-24 `.env` incident | **M** |
| 11 | **Numbered state migrations** — `src\migrations\registry.ts` + generated `INDEX.md`, recorded in `data/config/_meta.json`, with a retired pre-baseline chain that can never replay, a `NEXT_MIGRATION_NUMBER`, and the AGENTS.md rule *"never hide one-off cleanup in startup code"* | Aegis persisted state (books, seeds, receipts) | turns "we changed the JSON shape" from an unlogged event into a numbered, tested, indexed one | **M** |
| 12 | **The Verification Ladder** — `AGENTS.md:118-160`: a table mapping change shape -> minimum evidence, a per-surface gate table, and the rules *"Do not cite a green typecheck that did not include the changed code"* and *"an unrelated green test is not substitute evidence"* | `CLAUDE.md` session protocol | Aegis has strong rules but no *ladder* — this makes "how much proof for this size of change" explicit instead of per-session judgement | **S** |
| 13 | **Two-phase tool-call logging** — `src\core\event-log.ts` + `tool-call-log.ts`: append-only JSONL + in-memory ring + subscriber fan-out; the tool log is `start(id,…)` / `complete(id, output)` yielding a real `durationMs` | Aegis LLM/tool telemetry beside `llm_cost_audit` | adds per-call latency, input, output and error classification with a cheap "recent" query. Note OpenAlice built this and **never wired it to trading** — do not repeat that | **S** |
| 14 | **Paper-ness in the identifier** — `alpaca-paper` / `alpaca-live` as the prefix of every instrument handle (`alpaca-paper\|AAPL`) | Aegis book/account identifiers | paper-ness becomes visible in every string an agent, log line or receipt ever touches. Nearly free | **S** |
| 15 | **`default\skills\build-thesis\SKILL.md` and `retrospective\SKILL.md` as prompt *structure*** — left side (variant view vs consensus) / right side (relative strength, rotation), a "priced-in" check, and a freshness gate that runs first, every time | Aegis LLM analyst prompts | rewrite in your own words (AGPL). The transferable shape is: force a named list of disconfirming signals that a later monitoring step consumes — the pre-open prediction book's missing half | **S** |
| 16 | **`packages/uta-protocol` as a standalone wire-contract package**, plus AGENTS.md's `decimal.js` rule (money is never a float) | the Aegis execution/research boundary | Aegis's engine<->research boundary is implicit; a typed contract module (pydantic) makes the split enforceable, and monetary fields as `Decimal`/string end a class of rounding disputes | **M-L** |

### (h) What NOT to copy
1. **The 8-character commit hash.** `TradingGit.ts:38-43`: `createHash('sha256').update(JSON.stringify(content)).digest('hex').slice(0, 8)` — 32 bits, described as *"the durable trading-decision identity"* in `src\server\trade-provenance.ts:41-45`. Birthday collision around ~77k commits. Worse, it covers `{message, operations, timestamp, parentHash}` computed **before** execution, so `results` and `stateAfter` sit outside the hash and can be edited on disk undetected; and `JSON.stringify` is key-order dependent. If Aegis rebuilds its (currently broken) chain, hash the **full** record with a canonical serialisation and keep the whole digest.
2. **The ledger write path.** `services\uta\src\domain\trading\git-persistence.ts:43-48` rewrites the *entire* history with `writeFile(filePath, JSON.stringify(state, null, 2))` on every commit — no tmp+rename, no fsync. The same repo's `entity-store.ts` *does* use tmp+rename, so this is an inconsistency, not a philosophy. A crash mid-write truncates the account's whole trading history. Append-only JSONL.
3. **`loadGitState`'s silent fallback.** Same file, lines 30-39: `catch { /* try legacy */ }` then `catch { /* no saved state */ }` then `return undefined`. A corrupt or permission-denied ledger reads as *"this account has no history"* and it starts empty — Aegis's exact house failure mode. Refuse, don't default. (Also note the legacy map points **both** `alpaca-paper` and `alpaca-live` at the same `securities-trading/commit.json`.)
4. **`resolveGuards` skipping unknown types.** `guards\registry.ts`: `console.warn('guard: unknown type "…", skipped')`. A typo in a risk config silently disarms the guard and the process starts green. A guard config that does not resolve must abort startup — this is [[a gate that cannot go green is a broken gate]]'s twin.
5. **A fail-open size guard.** `max-position-size.ts:36`: *"If we can't estimate… allow — broker will validate."* The unestimatable case is every new position. Aegis's own memory ([[a one-sided guard catches half the error]], the 300%-gross / −9% episode) says a guard that cannot compute must **refuse**, and must check **gross exposure**, not one symbol at a time — ten names at 25% each passes this guard cleanly.
6. **Guards defaulting to `[]`.** Do not ship an execution path whose safety layer is opt-in. If Aegis adds a guard pipeline, the default config carries the caps, and a book with zero guards is an explicit, logged declaration.
7. **A single global `allowAiTrading` boolean.** One flag covering a paper book and a live account, with no notional threshold above which a human is still required, is too coarse for six books with different mandates. Scope it per book and add a size ceiling.
8. **Enforcement in the client rather than the domain.** `readonly` mode and `allowAiTrading` both live in Alice; UTA is mode-blind, and `POST /wallet/push` is an unauthenticated loopback route that `order-entry.ts:19-23` documents a deliberate bypass through. Put the check where the order is emitted, once.
9. **No idempotency key.** `orderRef` is never assigned; a retried push duplicates the order at the venue, and `expectedPendingHash` is in-process only and does not survive a crash mid-push. Any Aegis order write needs a `client_order_id` derived from the decision id.
10. **Unvalidated wire types.** `packages\uta-protocol\src\schemas\index.ts` is `export {}` — the whole Alice<->UTA protocol is compile-time-only, and `Order.action` / `orderType` / `tif` are bare `string`. Keep pydantic validation at the process boundary.
11. **`simulate.ts` as a backtester.** No costs, no slippage, one name, one rule, no statistics. `portfolio_farm.Policy` (which refuses zero costs) is already strictly better. Take the no-lookahead framing and the MFE/MAE + `open: true` output fields; take nothing else.
12. **The market-data stack as a research source.** yfinance is the default for equity, crypto, FX and commodities; fundamentals come from current FMP/yfinance endpoints with no as-of restatement; universes are hardcoded lists with no delisting handling. It has *freshness* discipline but no *vintage* discipline — survivorship and restatement leakage are structural. CRSP/IBES/TAQ parquets are a different class of input; do not regress toward this.
13. **The unauthenticated tool surface.** `src\server\mcp.ts:46` states the MCP listener is unauthenticated by design and loopback-only, and `safe\findings\2026-05-23-pre-implementation.md` records that at that date **every** red-team playbook case succeeded. Fine for a single-user desktop app; wrong for anything Aegis exposes on Railway.
14. **TypeScript itself.** ~218k LOC, half of it React. Nothing here is worth a Python shop transliterating — and under AGPL it would be the worst possible thing to transliterate. Every item in (g) is a page of design, not a module.

**Bottom line.** OpenAlice is a well-engineered *workbench* — process supervision, credential sealing, provenance, a git-shaped approval ledger, an unusually disciplined test taxonomy — wrapped around **someone else's model loop** and pointed at a research capability that lives in a repository we do not have. It makes no performance claim and has no track record, which is honest rather than damning. The exchange for Aegis is asymmetric and favourable: nothing about alpha, statistics or evaluation (it has none), and several genuinely good things about **the plumbing around a decision**. Items 1, 2, 5, 8, 9, 12 and 14 above are each a day or less and land directly on failure modes the memory index already records.

---

## 6. TOP 10 THINGS TO PORT — ranked across all five repos

Ranked by (impact on a failure mode Aegis has actually paid for, or on the stated bottleneck) divided by effort, with licence cleanliness as the tiebreak. Rows merge the per-repo tables in §2(g), §3(g), §4(g), §5(g); the licence column says whether code may be copied or must be reimplemented from a written spec.

| # | item | source repo + path | target in Aegis | benefit | licence | effort |
|---|---|---|---|---|---|---|
| 1 | **Multiple-testing library** — DSR, PSR, expected-max-Sharpe, BH-FDR, **PBO via CSCV**, with the per-observation-vs-annualised-Sharpe and non-excess-kurtosis gotchas documented in the header | Vibe-Trading `agent/src/quantlib/multipletesting.py` (568 L) | `backend/services/` or `engine/stats/`; called by the farm and by every claim-grade verdict | Aegis recomputes DSR/PBO ad hoc per session (S38g: DSR 0.005, PBO 0.64). A tested shared implementation makes CANON §63/§64 a function call instead of a ritual, and makes two sessions' numbers comparable | MIT — **copy** | **S** |
| 2 | **Two model-free leak detectors** — `lookahead-analysis` (re-run the replay with the frame cut before each signal, diff indicator values, name the biased columns) and `recursive-analysis` (recompute at 7 warm-up lengths, table the drift of the last row) | freqtrade `freqtrade/optimize/analysis/{lookahead,recursive}.py` + `docs/lookahead-analysis.md`, `docs/recursive-analysis.md` | new `scripts/leak_analysis.py` over the farm replay path; mandatory before any signal becomes a book | mechanical tests for the two failure classes Aegis keeps re-deriving by hand — target leakage (`IC -0.99`) and replay-vs-live drift. Neither reads the strategy source, so they catch what no reviewer would. The forced-config list (*"to avoid users accidentally generating false positives"*) is half the design | GPL-3.0 — **reimplement** | **M** |
| 3 | **Decision log with deferred outcome resolution** — pending tag written at decision time, resolved later against real closes, `get_past_context(as_of=…)` PIT gate on the `resolved:` date, plus a 2-4 sentence structured reflection (*"1. Was the directional call correct? (cite the alpha figure) 2. Which part of the thesis held or failed? 3. One concrete lesson"*) | TradingAgents `tradingagents/agents/utils/memory.py`, `graph/trading_graph.py::_resolve_pending_entries`, `graph/reflection.py` | new `backend/services/decision_log.py`, graded against CRSP/Alpaca closes at **each row's own declared horizon**, not a constant 5 | this *is* the pre-open prediction book + discovery-failure autopsy from `AEGIS_VISION`, as ~300 lines. The `as_of` filter is Aegis's PIT discipline applied to *lessons*, which nothing currently does | Apache-2.0 — **copy** with NOTICE | **M** |
| 4 | **`do_predict` in-manifold trust flag** — a per-row integer in [-2,2] carried in the prediction frame; each of a dissimilarity index, a one-class SVM and DBSCAN that rejects the row subtracts 1; `2` = model expired; plus `outlier_protection_percentage`, which **refuses** outlier removal rather than training on a decimated set | freqtrade `freqtrade/freqai/freqai_interface.py::define_data_pipeline` + `docs/freqai-configuration.md:166` | `backend/learner/` — emit beside every score; books gate on `do_predict == 1` | turns "the model scored this name" into "the model scored it **and the feature vector is inside the training manifold**". Aegis has no in-manifold check at all, and the decomposable cause makes each refusal auditable. Also the right answer to a stale model: null predictions with a reason, not silent scoring | GPL-3.0 — **reimplement** (the transformers themselves are sklearn) | **M** |
| 5 | **Two agent-safety hooks** — (a) a Bash guard that blocks broad process kills by image name (`taskkill /IM python*`, `pkill`/`killall … python`, PowerShell `Stop-Process -Name python`, `Get-Process python \| Stop-Process`), segment-split and quote-normalised; (b) a first-touch-per-file deny that demands concrete facts before the first Edit/Write | (a) Vibe-Trading `agent/src/tools/_shell_safety.py` (59 L); (b) ecc `scripts/hooks/gateguard-fact-force.js` | `.claude/settings.json` PreToolUse hooks for **both** repos | (a) is the code fix for 2026-09-06 — two agents' jobs, a test suite, ~1,676 already-billed extractions and the MCP server, killed by one `taskkill`. CLAUDE.md §6 is currently prose. (b) is the only mechanical enforcement of the SESSION START PROTOCOL anyone has built: *"Instead of asking 'are you sure?' … this hook demands concrete facts"* | MIT / MIT — **copy** | **S** |
| 6 | **Execution-cost realism** — ADV participation cap (10%) with the **shortfall carried forward** rather than silently filled or dropped; sqrt/linear impact; borrow cost; and `breakeven_fee_bps = ln(1+gross)/(2·trades·size)·10_000` printed on every result row | Vibe-Trading `agent/backtest/factor_costs.py`, `agent/src/quantlib/impact.py`, `agent/src/strategy_discovery/models.py` | `scripts/portfolio_farm*`; a column on every farm receipt | expresses `TRADABLE_DOLLAR_VOL` in weight space instead of as a pre-filter, and the carried-forward shortfall turns an unfillable target into a *tracked deficit*. `breakeven_fee_bps` is the cheapest possible enforcement of "quote the cost rate or don't quote the count", comparable across books with different turnover, and would have priced the S38 construction tax on sight | MIT — **copy** | **M** |
| 7 | **Declarative risk guards, at two levels** — per-order (`check(ctx) -> str \| None`, one pipeline assembles the context so guards never touch the account, name-keyed factory registry) and per-portfolio (`IProtection` returning `ProtectionReturn(lock, until, reason, lock_side)`; `StoplossGuard`, `MaxDrawdown` in equity mode, `CooldownPeriod`; entries locked, exits never) | OpenAlice `services/uta/src/domain/trading/guards/*` + freqtrade `freqtrade/plugins/protections/*` | new `alpha/protections.py` + `backend/risk/guards.py`, evaluated in `run_pass.py` before entries | CLAUDE.md §4 ("print the worst case in dollars") is a *pre-trade arithmetic* check; this is the *in-flight* one, and it is data, not code. Write the guards Aegis actually needs — gross exposure `Σ\|notional\|/equity`, `n × notional% × stop%`, daily loss — which is exactly what OpenAlice omits. **Note both cautionary defaults: OpenAlice's guard list defaults to `[]` and its size guard fails open** | AGPL / GPL — **reimplement** | **M** |
| 8 | **`minimal_roi` time-decayed exit curve + ranked typed exit ladder** — `{minutes_held: min_profit}` with `max(k for k in table if k <= held)`, and `should_exit` returning a *list* in the documented order exit-signal → stoploss → ROI → trailing | freqtrade `freqtrade/strategy/interface.py:1675-1732` and `:1419-1522` | `aegis-alpha-terminal` `alpha/contract.py` — replace the `expected_horizon_sessions` scalar | "I want 8%, but after 5 sessions I'll take 2%" is more expressive *and* more testable than a fixed horizon, and the ranking removes the ambiguity when a stop and a signal fire on the same bar. Aegis already has typed exit reasons; it lacks the curve and the priority. Free downstream: exit-reason attribution on every book | GPL-3.0 — **reimplement** | **M** |
| 9 | **A tamper-evident run record that refuses** — a hash-chained fsynced append-only ledger that raises rather than extending a broken chain; a `RunManifest` hashing system prompt + per-skill content hashes + tool registry + package versions with `timestamp`/`run_id` deliberately excluded; a run card hashing config + source + **every artifact**; and an `Operation` union that includes `observeExternalOrder` / `reconcileBalance` plus a `stateAfter` snapshot (netLiq, cash, uPnL, rPnL, positions, pendingOrders) | Vibe-Trading `agent/src/governance/{ledger,manifest}.py`, `agent/backtest/run_card.py` + OpenAlice `packages/uta-protocol/src/types/git.ts:22-102` | the terminal repo's ledger; Aegis receipts | Aegis's ledger hash chain has been broken since 25 Aug and has printed 53+ times without blocking anything — a chain that warns is a log. `RunManifest` answers "did the methodology change between run A and run B", which cannot currently be answered for LLM-in-the-loop runs. The external-event operations stop the ledger lying when a fill or transfer happens outside the system — the shape of the STALE-NAV problem | MIT (copy) / AGPL (reimplement) | **M** |
| 10 | **Grounding a model in a table it cannot argue with** — a deterministic verified snapshot plus the prompt clause *"treat it as the source of truth for any exact OHLCV, price-level, or indicator-value claim. If another tool's output conflicts … flag the discrepancy rather than inventing a reconciled number"*; a typed Pydantic decision schema with a `REVIEW` sentinel instead of a silent default; and a freshness contract `{asOf, isLatestActual, staleTradingDays, freshnessWarning}` returned on **every** data read | TradingAgents `dataflows/market_data_validator.py`, `agents/schemas.py`, `agents/utils/rating.py` + OpenAlice `src/domain/market-data/bars/types.ts:80-92` | `backend/services/llm_analyzer.py` (central `_call_llm` assembly) and every collector's return envelope | kills the fabricated-price failure mode and makes every LLM narrative auditable against a table computed from CRSP/Alpaca parquet. The typed schema makes every LLM output a gradeable row (feeding #3). The freshness field is [[SILENCE IS NOT EVIDENCE]] as a data field — *"an empty window means 'not in the feeds', NOT 'nothing happened'"* | Apache (copy) / AGPL (reimplement) | **S** |

**Just below the line, all small:** freqtrade's published fill-assumption list (`docs/backtesting.md:556-591`) and its five-line common-mistakes list; freqtrade's `custom_stake_amount` bounded-sizer signature and `strategy_safe_wrapper`; Vibe-Trading's purged/embargoed/combinatorial CV with `detect_boundary_leakage()` (MIT, and CLAUDE.md already mandates the technique); OpenAlice's risk-keyed test lanes with *"an all-skipped run is not acceptance evidence"* as a declared prerequisite, its live-paper dogfooding ritual (*"Never trust the ledger over the venue"*, *"Leave accounts flat"*), and its incident template's **"Why release checks missed it"** section; ecc's `commands/save-session.md` handoff template with its mandatory *What Did NOT Work (and why)*; and Vibe-Trading's `__alpha_meta__`-by-AST-scan feature registry, which prevents the unreachable-module bug that `signal_reachability.py` currently only detects.

**Licence summary for the whole port list:** TradingAgents is Apache-2.0 and Vibe-Trading is MIT — copy freely with a NOTICE/header line (watch the Apache-2.0 `qlib158` subtree). freqtrade is **GPL-3.0** and OpenAlice is **AGPL-3.0**: read, write a one-paragraph spec in your own words, close the file, implement from the spec. AGPL §13 would reach the FastAPI backend's network users, so it is the one to be strictest about — including prompt text, which is as copyrightable as code.

---

## 7. What all five have that Aegis lacks

Every one of these repos — including the two with no evidence and the one with no trading in it at all — has a **single named, versioned, executable contract for what a strategy or a decision *is*, and one command that runs it end to end in front of someone who was not in the session.** freqtrade has `IStrategy` and `freqtrade backtesting --strategy X`; Vibe-Trading has the four-line `SignalEngine.generate` interface and `backtest/runner.py`; TradingAgents has `TradingAgentsGraph.propagate(ticker, date)` returning a typed `PortfolioDecision`; OpenAlice has `IBroker` plus a `GitCommit` whose `operations`/`results`/`stateAfter` fully describe one decision; ecc has `hooks.json` and a session file with fixed sections. Aegis has more research depth than any of them and no such object: a strategy is spread across a book YAML, a frozen contract, a farm preset, a composite weight table and a selector function, with no interface a new mechanism must implement and no one-command path from "here is an idea" to "here is its graded, cost-aware, receipted result." That absence is not cosmetic — it is why every book still selects on 12-1 momentum (the stated bottleneck), why a new mechanism is a session's work rather than a file, why lane NAVs could go stale unnoticed, and why five months of guardrails moved the demonstrated edge by zero: the guardrails guard a process, not a type. The corollary each repo also shows is an **operable surface** — Telegram/REST for freqtrade, an MCP server and CLI for Vibe-Trading and OpenAlice — which forces the system to be legible to someone holding only its outputs. Aegis's equivalent is a session transcript and a memory index, which is why so much of its canon is about not losing what the last session knew. The single highest-leverage thing on this whole list is not any row in §6: it is giving Aegis a `Strategy` interface and a `run_one(strategy, universe, window, objective) -> receipt` entry point, and then porting §6 into *that*.
