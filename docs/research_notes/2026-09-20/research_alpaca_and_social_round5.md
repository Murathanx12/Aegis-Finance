# Alpaca hackathon/tactics + social data-gathering round 5 (2026-09-20)

Prior reading before this note was written: `NEGATIVE_RESULTS.md` §19 (LLM/agent
trading alpha comprehensively dead — three external receipts, family closed) and
`docs/research_notes/2026-09-11/research_social.md` (round 1 social research,
already covers Alpaca-hackathon LinkedIn posts, WSB attention, insider clusters,
alt-data pricing, Discord/Substack landscape, r/algotrading live-result threads,
buy-the-dip literature). This note does not repeat those findings except where a
new receipt changes them.

## Top-of-screen table

| Item | Verdict | Cost | Citation |
|---|---|---|---|
| Hackathon winners | **UNPUBLISHED** (judging in progress as of 2026-09-20) | $0 | [lablab.ai/live](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live) |
| New Alpaca hackathon/bounty | **NONE FOUND OPEN** | $0 | checked lablab.ai, Alpaca X, hackathonradar, hackalendar |
| AlphaDesk's LLM decision node (BUY/SELL/HOLD) | **ALREADY_HAVE** (closed harder) — our rule is LLM never allocates at all, not "gated by a risk node" | $0 | `alpha/human.py`; NEGATIVE_RESULTS §19 |
| AlphaDesk's risk-node hard guardrails | **ALREADY_HAVE**, more granular | $0 | `alpha/guards.py`, `alpha/refusal_classes.py`, `alpha/admission.py` |
| AlphaDesk's Pinecone news-sentiment RAG node | **IGNORE** for allocation; sentiment-as-typed-precursor already on our roadmap | $0 (Pinecone free tier exists, not needed) | AlphaDesk case study |
| Alpaca options-chain snapshot (`/v1beta1/options/snapshots/{underlying}`, Greeks+IV) | **ALREADY_HAVE**, wired | live-key cost only | `alpha/broker/alpaca.py:211` |
| Alpaca Skills Library (`alpacahq/alpaca-skills`) | **TAKE** — the Backtesting-Skill's assumption-tracking/reporting checklist, not the code | $0, OSS | [github.com/alpacahq/alpaca-skills](https://github.com/alpacahq/alpaca-skills) |
| Alpaca MCP Server v2 | **TEST** (dev convenience only, no new data) | $0 | [docs.alpaca.markets/us/docs/alpaca-mcp-server](https://docs.alpaca.markets/us/docs/alpaca-mcp-server) |
| Alpaca CLI (`--live` opt-in flag) | **TAKE** — the explicit opt-in pattern is a stricter version of what we already gate in `seal_authority.py` | $0 | [docs.alpaca.markets/us/docs/alpacas-cli](https://docs.alpaca.markets/us/docs/alpacas-cli) |
| Revelio Labs (LinkedIn-derived workforce data) | **IGNORE at $10M scale** | $85,000/yr (AWS Data Exchange listing) | Datarade / AWS Marketplace |
| LinkUp / Lightcast job-postings data | **IGNORE** (enterprise-only, no public pricing) | quote-only, likely 5-figure+/yr | lightcast.io, datarade.ai |
| Free Greenhouse/Lever/Ashby ATS collector (ours) | **ALREADY_HAVE** | $0 | `backend/services/lab_themes.py` |
| "Retail Trader's Ruin" (arXiv 2607.20093) | **IGNORE as a source of new ideas** — it refutes the same five families we've mostly already closed | $0 (read) | [arxiv.org/abs/2607.20093](https://arxiv.org/abs/2607.20093) |
| Insider cluster-buy, post-disclosure 0-1d | **TEST** — our own N1 licenses it, doesn't prove it | $0 (Form4 on disk) | NEGATIVE_RESULTS §46 |
| Post-earnings surprise-breadth regime gate (retail Substack) | **IGNORE as-is** — costed research window did not beat QQQ's own Sharpe | $0 | `research_social.md` Batch 4; our own §14 (monthly PEAD inverted) |
| WSB-attention short overlay | **TEST, low priority** | $0 (StockTwits/Reddit public) | ScienceDirect "Dumb money" study; `research_social.md` |
| Congress-trading copy | **IGNORE** | $0 | 45-day STOCK Act lag; `research_social.md` |
| StockTwits trending-symbols endpoint | **TAKE** for a cheap crowd-attention control variable | $0 (free tier) | `api.stocktwits.com/developers` |
| Hiring-signal vendors as a hedge-fund comp point | **ALREADY_HAVE the free version; TAKE the comp number** for future budget asks | $0 to know, $85K+/yr to buy | Datarade/AWS |

---

## 1. The hackathon

**Not yet decided.** Checked three surfaces on 2026-09-20:

- `lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon` (the recap page)
  says the event **"Has Finished"** (ran 2026-08-28 → 2026-09-04, $6,000 prize
  pool per the page; Alpaca's own launch post on X quoted $5,000 — the number
  moved between announcement and recap) but does not list winners.
- `lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live` (the results
  page) states explicitly **"Judging in progress"** / **"Results will be
  published here as soon as judging wraps."** It reports **428 projects
  submitted across 1,268 teams and 3,602 participants**, and lists a
  community-*heart*-voted leaderboard (not judge-determined): "Alpha Hunter —
  Autonomous AI Trading Scientist" (146 hearts), "TradePilot AI" (136),
  "QASIX-Alpaca AI Trading Agent" (37). These are popularity counts, not prizes.
- Targeted searches for a winner announcement on Alpaca's blog/X and on
  hackathonradar/hackalendar turned up nothing dated after 2026-09-04.

**No new Alpaca hackathon or bounty is open now.** Searches for "now open,"
"apply now," and a November 2026 successor returned only the same
already-finished event and unrelated third-party repos of contestants' code.

## 2. Alpaca tactics

### AlphaDesk (the newsletter case study)

Built by Yuvraj Singh Hajari (final-year CSE, VIT; Alpaca community member,
not an Alpaca employee), it is an **educational, paper-only** LangGraph state
machine on a 5-minute cron: **Signal node** (RSI/SMA/EMA/Bollinger on 5-min
bars for five hardcoded tickers, author calls this math "elementary") →
**Risk node** ("arguably the most important node" — buying power, positions,
drawdown, hard rule-based veto, independent of the LLM) → **Sentiment node**
(news headlines embedded into **Pinecone**, RAG-scored bullish/bearish/neutral
over a 24h window) → **Decision node** (Llama-3.3-70B on Groq returns
structured BUY/SELL/HOLD JSON with rationale) → conditional routing that only
submits an order via `alpaca-py`'s `MarketOrderRequest` if `decision in
['BUY','SELL'] and risk_approved == True`. Infra: Postgres+TimescaleDB,
Redis pub/sub, Next.js dashboard. The author's own disclaimers are unusually
blunt: paper-only, no slippage/impact modeling, and the signals need "deeper
domain expertise" before any live consideration.

**What §19 already closed, precisely:** AlphaDesk's Decision node is exactly
the design pattern FINSABER (arXiv 2505.07078) tested at scale and found dead
net of costs — an LLM given technical + risk + sentiment context returning a
structured trade decision. Our standing rule (LLM narrates, never allocates)
is *stricter* than AlphaDesk's risk-gated LLM: AlphaDesk still lets the LLM's
BUY/SELL choose direction and size is implicit in a flat market order; our
`alpha/human.py` makes even a *human's* thesis pass through the identical
claim-matrix/sizer/refuted-routes/admission/book-limits/daily-latch pipeline
as every other brain, and no LLM output enters that pipeline as a decision at
all — only as text. AlphaDesk's risk node (buying power/position/drawdown
veto) is a rougher version of `alpha/guards.py` + `alpha/refusal_classes.py`,
which already classify 43 distinct gate sentences into typed refusal classes
across GROSS_NOTIONAL, DRIVER_CONCENTRATION, CROSS_BOOK, OPENING_RANGE,
PAST_LIQUIDATION_DEADLINE, CLOCK_SKEW, SESSION_CLOSED and more — a taxonomy
AlphaDesk doesn't have. The one AlphaDesk piece with no Aegis equivalent is
the **Pinecone RAG sentiment node's freshness discipline** (per-ticker,
24-hour lookback) — worth noting as a pattern, not worth building: it feeds
the same dead decision node.

### Alpaca's Skills Library for AI Agents

Open-source `SKILL.md` files (`github.com/alpacahq/alpaca-skills`) that give a
coding-assistant agent (Claude Code, Cursor, Codex) step-by-step instructions
for two workflows: a **Backtesting Skill** (formalize a strategy → pull
historical data via the Trading CLI → compare to a benchmark → track
assumptions → produce a reproducible report) and a **Paper Trading Skill**
(confirm strategy → preview order with buying-power checks → paper-only
safety gate → post-submission monitoring). Aegis already has a stronger,
code-enforced version of both disciplines — `portfolio_farm.Policy` refuses
zero costs outright rather than "tracking the assumption," and
`scripts/seal_authority.py` freezes and content-hashes every book rather than
producing a narrative report. **The one thing worth taking**: the skill's
explicit "reproducible report" checklist format is a decent template for our
own farm-run receipts if a future session wants a standard one-pager per farm
run — cheap to borrow, not worth a dependency.

### Alpaca's MCP Server (v2)

`alpacahq/alpaca-mcp-server`, a FastMCP/OpenAPI rewrite exposing **65 tools**
across account/portfolio, trading, market data, watchlists, options
(including `get_option_snapshot` for Greeks/IV), crypto, fixed income, news,
and corporate actions, defaulting to paper trading
(`ALPACA_PAPER_TRADE=true`) with an explicit `ALPACA_PAPER_TRADE=false` flip
required for live capital
([docs.alpaca.markets/us/docs/alpaca-mcp-server](https://docs.alpaca.markets/us/docs/alpaca-mcp-server)).
This is a developer-ergonomics wrapper, not a new data source — every
endpoint it exposes is already reachable from `alpha/broker/alpaca.py`
(`option_chain`, `stock_bars_multi`, `stock_quote`, `portfolio_history`,
etc.), which is a thinner, audited client with no order path leaking outside
`submit()`. **Not worth adopting**: our client is purpose-built and pinned by
smoke tests (`tests_smoke_allocator_artery.py`, `tests_smoke_seal_delivery.py`)
to have no unintended order surface; a 65-tool general MCP server is a larger
attack/mistake surface for a coding agent to accidentally invoke `submit`
through, which is the opposite of what `alpha/human.py`'s design is trying to
prevent. Worth trying only as a throwaway exploration aid in a sandboxed
session, never wired into the loop.

### Alpaca's CLI (`alpacahq/cli`)

Trades, queries market data, and manages the account from the terminal with
**no confirmation prompts** — deliberately built for agent use, with an
explicit `--live` flag or `ALPACA_LIVE_TRADE=true` required to leave paper
(`docs.alpaca.markets/us/docs/alpacas-cli`). **The one thing worth taking**:
this is the same shape as our own `seal_authority.py` fail-closed default
(paper unless a specific, loud override is present) — a useful external
confirmation that "opt-in to real money via an explicit env flag, default
closed" is the industry pattern, not an Aegis idiosyncrasy. No new capability;
confirms an existing design choice.

## 3. Data and strategy gathering from socials, without scraping

### (a) What practitioners say works now

- **arXiv 2607.20093, "Retail Trader's Ruin: An Anatomy of Popular Signal
  Failure"** (2026): tests trend, oscillator, candlestick, volume, and
  calendar rule families under a three-gate framework — statistical edge
  after multiplicity correction, economic viability after costs, finite-
  bankroll survival under leverage. Result: oscillator, volume, calendar, and
  candlestick are **REFUTED**; trend/momentum are **INCONCLUSIVE** (wide CIs,
  not proven dead). No family is licensed as a clean win. This maps almost
  exactly onto our own closed families (§9/#10 momentum+trend-filter, §21
  conditional-vol-targeting) — it is confirmation, not a new lead.
- **Quantocracy** (quantocracy.com, aggregator) recent notable posts: "PEAD
  decomposed by earnings predictability and gross profitability" and
  "Piotroski F-score backtest on the S&P 500, point-in-time, 2000-2025" (both
  Quanter Lab), and "Do LLM Crowds Produce Investment Signals? An Empirical
  Test" (Quantpedia) — directly on-topic for §19 and worth a follow-up read if
  a session wants one more external LLM-crowd receipt before the §19 family
  can be reopened.
- **r/algotrading**: the useful pattern this round is *methodological*, not a
  new signal — multiple third-party audits (Kalena.ai, LedgerMind) of
  r/algotrading's most-upvoted strategies find backtested 2.5%/month
  strategies running 0.8-1.2%/month live, and a 2026 r/Daytrading poll found
  only 14% of retail traders systematically backtest at all. This is a
  reminder to distrust vote counts, not a signal source — consistent with
  round 1's finding that virtually no LinkedIn/hackathon "built an agent"
  post shows audited live P&L.
- **StockTwits public trending endpoints** (`GET /trending/symbols.json`,
  `GET /trending/symbols/equities.json`, `api.stocktwits.com/developers`):
  free, returns up to 30 tickers/page with a `trending_score` (message-volume
  velocity, not sentiment polarity). Structurally identical in kind to the
  WSB-attention literature already in round 1 (`research_social.md`) — a
  crowd-attention *contrarian* control variable, not a long signal on its own.

### (b) LinkedIn-derived signals via licensed vendors vs. our free collector

| Vendor | What it sells | Price found | Verdict |
|---|---|---|---|
| Revelio Labs | 1.1B+ LinkedIn-style profiles, transitions, job postings, sentiment, layoffs | **$85,000/yr** for the AWS Data Exchange "Human Capital Dynamics" bundle (4 S3 datasets, monthly, since 2008); no public API price | IGNORE at $10M book size — the fee alone would be ~85bps of AUM before any trade is placed |
| LinkUp | Employer-career-page/ATS-sourced postings since 2007; 315M+ historical, ~5M daily active | Enterprise-only, no public price, no self-serve, no free tier | IGNORE — can't even get a quote without a sales call |
| Lightcast | US job postings back to 2010, labor-market analytics marketed explicitly to hedge funds | Enterprise, demo-gated, no public price | IGNORE, same reason |
| **Our Greenhouse/Lever/Ashby ATS collector** | Same underlying idea (hiring as a forward-revenue/pivot signal) sourced directly from employer ATS pages, already in the news registry as `greenhouse_lever_ashby_ats` | **$0** | ALREADY_HAVE — `backend/services/lab_themes.py` explicitly tracks its own coverage as "a MEASURED fraction with a large structural [gap]" against named demo/test accounts (Airbnb's Greenhouse, a Lever demo, Ashby's own listing), i.e. it is honest about being a partial map, not a Revelio-grade census |

**Read:** the licensed vendors are not buying a *different* signal from ours —
job-postings-as-forward-indicator is the same mechanism LinkedIn scraping
would target, and it's exactly what our ToS-compliant ATS collector already
does for $0. The vendors are selling *coverage completeness* (1.1B profiles
vs. our named handful of companies) and *history* (back to 2008/2010), which
matters for a cross-sectional factor study but not for the situational,
single-name use our collector is built for. At $10M AUM the $85K/yr price is
not obviously irrational (< 1% of AUM) if the coverage gap turns out to bind,
but nothing in this research found an audited return number that would
justify paying it before testing whether our own free coverage already binds
first.

### (c) YouTube channels whose transcripts would be worth typing

Ranked for "reproducible/checkable claims worth ingesting as typed events,"
not for subscriber count:

1. **QuantPy** (293k+ subs per acquisition coverage; code on
   `TheQuantPy/youtube-tutorials`, 281 GitHub stars) — reproducible Python
   backtests with public code; **caveat**: acquired by ThetaData Feb 2026, so
   post-acquisition content likely skews toward promoting ThetaData's own
   options feed — worth typing, discount for vendor bias.
2. **Algovibes** — established Python/backtest channel, prior round already
   flagged as reproducible-code-forward.
3. **QuantInsti Quantitative Learning** — the education arm of QuantInsti
   (EPAT program); tutorials cover Python/ML/HFT strategy build with
   accompanying blog code, useful for typed-event extraction of *claimed*
   strategy mechanics even when not independently verified.
4. **Trade Algo** — coding + backtesting focus per round-1 findings.
5. **Rogue Quant** (also a Substack) — posts backtested strategies with
   explicit code and "edge breakdowns," i.e. states the mechanism, not just
   the equity curve — good for extracting a falsifiable claim.
6. **Better System Trader** (podcast, YouTube-syndicated, Andrew Swanscott,
   242 episodes) — long-running interview format with professional systematic
   traders; value is in *what experienced practitioners say fails*, which is
   exactly the "study losers" instinct CLAUDE.md asks for, from people who
   aren't selling a course.
7. **Robot Wealth / Kris Longmore** (Edge Alchemy Substack + YouTube/IBKR
   Campus interviews) — former prop-firm partner, explicit "edges are
   rules-based and falsifiable" framing; useful for typed hypothesis
   extraction because the content is already structured as claim + rule.
8. **QuantConnect's own channel** — platform-tutorial content, but backed by
   Alpha Streams (80k quants, live colocated track records per round-1
   research) — worth typing for which *live-tracked* strategies the platform
   itself surfaces as durable, since that's closer to an audited signal than
   a one-off backtest video.
9. **AlphaStreet** — earnings-call video coverage landing within hours of the
   print; not a strategy channel, but a cheap, structured source of
   *management-text* events (tone, Q&A evasion) for the "revision-mediated
   route closed, management text not closed" carve-out already in CLAUDE.md's
   EXPLORE-DIRTY section.
10. **Quantocracy's own linked video/podcast features** (it aggregates, and
    occasionally features, YouTube/podcast content alongside blog posts) —
    typing its weekly "Quant Mashup" digest itself is cheaper than typing ten
    separate channels and catches whichever one produced something citable
    that week.

## Top 10 concrete strategy ideas, ranked by P(real) × tradability at $10M, checked against NEGATIVE_RESULTS

| # | Idea | Source | P(real) | Tradability @ $10M | NEGATIVE_RESULTS check | Verdict |
|---|---|---|---|---|---|---|
| 1 | Insider cluster-buy, post-disclosure 0-1 day hold | round-1 social research + our own corpus | Moderate — our own N1 found the post-disclosure move DETECTABLE at 0-1d lag on 608 events, but the corpus is 5 filing-days deep and 1,175/1,589 events came from one day | High — liquid names, short hold, small size | **§46**: "licence to continue, not evidence of an edge"; needs the R12 Form4 backfill before it's a claim | TEST (cheapest next step, not a new idea — it's our own open thread) |
| 2 | Surprise-breadth regime gate → leveraged-ETF rotation (finlab.finance PEAD variant) | round-1 social research | Low — author's own research-window Sharpe (1.45) did not beat QQQ's own Sharpe (1.47); costs unmodeled | Low — the "39.5% CAGR" version needs 3x leveraged ETFs, which is a different risk budget entirely | **§14**: monthly PEAD is already inverted on our data; **#9/#10**: our own momentum+trend-filter work is dead | IGNORE |
| 3 | Job-postings-as-forward-revenue-signal, our own ATS collector, wider coverage | this round's vendor pricing research | Moderate — validated mechanism per multiple vendors (predicts revenue surprise/M&A ahead of earnings) but "validated" here means vendor claims, not our own receipt | Moderate — bound by our collector's named-company coverage gap | Not directly addressed by any NEGATIVE_RESULTS section — no prior test | TEST — pre-register before touching it (cheap, $0, novel to our ledger) |
| 4 | WSB-attention peak as a short/fade overlay | round-1 social research (ScienceDirect "Dumb money") | Moderate — -8.5% HPR finding is peer-reviewed, but a conflicting arXiv paper (2301.00170) disputes it on methodology grounds | Moderate — needs the attention-peak timing to be tradable intraday, not just identifiable after the fact | Not directly tested by us; adjacent to §24 (flow signals: more rank info, less tradability) | TEST, low priority |
| 5 | Congress-trading copy (STOCK Act disclosures) | round-1 social research | Low — 30-45 day disclosure lag means a copier trades on stale prices; H.R.7008 may end individual-stock trading by members altogether | Low — by the time it's legally copyable the move is gone | Not tested by us; the lag alone is disqualifying without a test | IGNORE |
| 6 | Index-level broad-basket dip-buying with quality/trend overlays (S&P Global 2018) | round-1 social research | Moderate — this is the one BTD variant with a positive peer-reviewed result (contradicts the naive-BTD-never-works consensus) | Moderate — index/basket scale suits $10M | **§1**: "the timing strategy underperforms buy-and-hold" — our own timing family is already dead, and this is a timing strategy | IGNORE (same family we already closed, different dressing) |
| 7 | Retail-transaction/card-panel long-short (Facteus/YipitData/Earnest, ~16%/yr academic estimate) | round-1 social research | Moderate-High academically, but vendor-priced at $300K-$1.5M/yr | Low at $10M — the data cost alone is 3-15% of AUM before any trade | Not tested by us | IGNORE (cost, not mechanism) |
| 8 | Analyst-consensus / synthetic LLM-crowd signal (Quantpedia's "Do LLM Crowds Produce Investment Signals?") | this round (Quantocracy) | Unknown — flagged, not yet read in full | Unknown | **§19** family — any LLM-signal proposal must rebut all three §19 receipts, not just cite a new paper | IGNORE unless a session reads the full paper and it survives the §19 bar |
| 9 | Distress-8-K "drift" reruns under a different filter | pattern-matches multiple social threads on 8-K reactions | Low | N/A | **§20**: already adjudicated as selection, not information | IGNORE |
| 10 | FDA-approval / regulatory-catalyst drift, retail-social framing | pattern seen in Discord/Substack catalyst content | Low | N/A | **§11 and §16**: dead at monthly AND daily resolution | IGNORE |

**Net of this round**: one genuinely novel, untested, $0-cost idea (#3, our
own ATS coverage as a forward signal, pre-register before running) and one
open thread worth continuing (#1, insider cluster-buy 0-1d, needs the R12
backfill). Everything else ranked either duplicates a family NEGATIVE_RESULTS
has already closed, or is priced out of a $10M book. Result improvement this
session: **NONE** — this is a research-gathering pass, no code or trial
touched.
