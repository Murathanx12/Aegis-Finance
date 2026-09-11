# Research: Qanat / Fidetolabs vs Aegis Finance

## Status: starting

## Qanat README summary (from github.com/fidetolabs/qanat)
- Agent-native workflow engine for building/backtesting alphas as DAGs. "Declare the alpha as a DAG. Hand the backtest to an agent."
- Pipeline: sources -> raw -> normalized -> features -> weights (alphas) -> PnL
- SQL or Python steps, dependency resolution, web console at 127.0.0.1:8420
- MCP server: 27 tools (discover 6, validate 3, choose 4, run 6, author 2, watch 2) - agents can read lineage, plan changes, run backtests, compare, write steps
- PIT replay: "Before each pass, every table is shadowed by a view holding only rows that existed at that moment" - purge/embargo, PIT universes
- Backtest: fees, slippage, rebalance freq, decay blending (blends last N portfolios), --split date for IS/OOS
- No benchmark by design: "There is no benchmark. Nothing separates edge from beta" - metrics: gross/net return, hit rate, turnover
- 4 built-in alphas: momentum (long-only trailing return rank), reversal (short-term mean reversion), low_vol (vol-weighted quiet names), neutral_momentum (momentum minus market avg, long/short)
- Data: bundled ECB FX 27yr example, REST/SQL/CSV/synthetic connectors, DuckDB default or Postgres, NO outbound calls of its own
- Paper only, no live trading: "Qanat produces a portfolio, it does not place an order." Forward mode = cron/event triggered; backward = qanat backtest replay
- Install: uv tool install qanat-fdtl / pip install qanat-fdtl; qanat init --demo; qanat serve; docker compose up
- MIT licence, copyright fidetolabs 2026. ~123 stars, 25 forks. Beta / "first packaged release public beta". Python 3.10+
- Dirs: src/qanat (core), examples/ (equity, fx-bundled, fx-real, scheduled-ingest), steps/, docs/ (words.md, contract.md, agents.md, console.md, backtest.md), docker/, tests/, .github/workflows/

## GitHub metadata (api.github.com, checked 2026-09-11)
- created_at 2026-09-05, pushed_at 2026-09-10 -> repo is SIX DAYS OLD at time of this research
- stars 123, forks 25, watchers 123, open_issues 0
- Contributors: ONE (org account "fidetolabs", 13 contributions) - single-team/founder project, org login masks individual authorship
- License: MIT, size 3020 KB
- src/qanat/ files: __init__.py, __main__.py, alphas.py, api.py, backtest.py, cli.py, console/ (dir), context.py, editor.py, mcp.py, models.py, plan.py, progress.py, project.py, project_io.py, retention.py, runner.py, scaffold.py, scheduler.py, sources/ (dir), store.py
- Takeaway: 123 stars in <1 week for a single-contributor MIT repo is a high velocity that likely reflects a launch push (HN/Twitter/PH) rather than organic multi-year adoption. Treat "stars" as launch-day marketing signal, not maturity signal.

## docs/agents.md (MCP)
- 27 MCP tools: 20 read-only (list_tables, list_steps, describe_table, sample_table, list_backtests, list_alphas...), 7 write (run, backtest, use_alpha, save_step, remove_step, save_source, open_console)
- sample_table honours as_of param -> PIT-safe agent exploration
- backtest_conditions tool returns data ranges/universes/defaults, explicit design to make "the agent stop and ask" rather than assume
- --read-only mode restricts agent to the 20 read tools
- NO agent memory system, NO hypothesis tracking, NO automated evaluation/grading framework documented (contrast with Aegis belief ledger)

## docs/backtest.md
- Cost params: --fee-bps, --slippage-bps, --purge, --embargo (CLI overrides of yaml config); exact formulas not shown in doc
- PIT universe via from/to columns: ctx.universe() returns members as of the deciding day only
- Time-travel prevented via per-pass table views showing only rows that existed at that moment
- Compounding: each period earned on prior period's equity, net agrees with equity curve
- NOT covered in docs: walk-forward/IS-OOS split mechanics detail, decay blending math, specific metrics list, benchmark handling, significance testing (README states "there is no benchmark" as a design philosophy)

## docs/contract.md (stage contract, 6 rules)
1. raw stage immutable, written only by a source
2. data flows forward only (no reading later stages) -> prevents cycles/leakage
3. one weights stage, last (optionally + pnl stage)
4. one step writes one weights table (one alpha = one portfolio)
5. no alpha reads another alpha's weights (combining only visible at replay time)
6. every read table must have a producer (fails at validation, not runtime)
- Weights carry no budget/share counts -> same weights table can drive backtest AND live paper/live account

## fidetolabs.com/products/notes
- "Notes" = replication studies: pick one published quant finance paper, test on real market data from scratch, preregister plan BEFORE loading data, publish code+charts+results including negative findings, framed explicitly as "not investment advice"
- Example findings quoted on site: a factor at 0.90 Sharpe with 7bps breakeven cost; accruals anomaly decayed 0.38%/mo historical -> 0.08%/mo post-publication; turn-of-month effect down to 7% of old size
- Uses Ken French data library + "real market data"; no LLM/memory mentioned for this product

## fidetolabs.com (company)
- Tagline: "Fidelity to every detail in data products." Single founder (a quant trader), no team listed
- Products: Data (cleaned/joined market data over MCP, NOT YET LAUNCHED - "in progress, no date promised", waitlist only), Agents (404 on /products/agents - page doesn't exist or moved), Open Source (=Qanat), Research (=Notes), Community (Discord ~1,173 members)
- Contact: contact@fidetolabs.com; Instagram + Discord links; ToS/Privacy pages exist
- No pricing shown anywhere checked; no public performance claims for a live strategy (Notes' numbers are replication-study factor stats, not a track record)

## Other 2025-2026 OSS personal-investing-agent projects found
- TauricResearch/TradingAgents - 104,540 stars (already known/excluded per task, went 9.3k->99k in 2026, LangGraph multi-agent, decision-log memory, v0.4.0 Aug 2026 added PIT fixes)
- Kahtaf/OpenCandle - 23 stars, created 2026-03-29, read-only terminal/browser financial research agent, BYO LLM, cites sources, no execution
- OnePunchMonk/AgentQuant - 195 stars, created 2025-08-12, "self-improving AI agents using adaptive harness evolution" - closest analog to Aegis's night evolutionary farm
- mitchellbernstein/openquant - 2 stars, created 2026-04-22, "AI agents, risk engine, insider monitor, strategy backtesting", low traction
- NeuPortal - not a github repo per se / forecasting-accountability lab: every forecast locked pre-event + OpenTimestamps Bitcoin-anchored + Brier-scored publicly (92 graded: 73 HIT/6 NEAR/4 PARTIAL/9 MISS, aggregate Brier 0.0958) - closest analog to Aegis's belief ledger (24,828 forecasts) but cryptographically tamper-evident vs Aegis's internal hash chain (which per memory has been BROKEN since 2026-08-25, unrepaired)

## STATUS: research complete, writing final report
