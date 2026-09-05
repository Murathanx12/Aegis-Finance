# Alpaca AI Trading Agents Hackathon (lablab.ai, 2026-08-28→09-04) — Winners and Lessons

## Status: OFFICIAL WINNERS NOT FOUND (judging in progress as of 2026-09-05)

The hackathon page itself states judging is not complete: the results page
(`/live`) reads *"Judges are reviewing every finalist"* and *"Results will be
published here as soon as judging wraps."* `lablab.ai/apps/recent-winners`
does not list this hackathon. No Alpaca blog post, X/Twitter post, or
LinkedIn post announcing a winner was found. **What follows is the
community-vote ("hearts") leaderboard, which is not the judged result** —
Murat's own prior note on this exact rubric (`reference_lablab_judge_rubric.md`)
is that a low-vote, honesty-forward entry won a past Alpaca/lablab hackathon,
so vote rank is not a reliable proxy for judged rank here either.

Queries run: `lablab.ai Alpaca Trading Agents hackathon winners 2026` ·
`Alpaca "Trading Agents" hackathon lablab.ai September 2026` ·
`alpaca.markets blog hackathon winners trading agents` ·
`"Alpaca AI Trading Agents Hackathon" winners announced first place` ·
`lablab.ai hackathon judging timeline how long after submission winners
announced`. Pages fetched directly: the hackathon landing page, its `/live`
results page, six individual submission pages, Alpaca's "Weekly Roundup #1"
blog post (does not mention this hackathon), and `lablab.ai/apps/recent-winners`.

Event facts (from the landing/live pages, Alpaca's own X announcement):
$5,000–$6,000 prize pool (sources disagree: Alpaca's X post says $5,000/3
winners, the lablab page banner says $6,000), 427 projects shipped, 3,602
participants, 1,269 teams. Challenge: build an autonomous trading agent using
Alpaca's Trading API plus Alpaca's MCP server or CLI.

## Leaderboard (community votes, NOT judged winners)

| rank | team | what it did | technique | evidence shown | repo |
|---|---|---|---|---|---|
| 1 (138 votes) | crazyxyz — Alpha Hunter | AI "trading scientist": generates strategy hypotheses, backtests, adversarial stress-tests, scores an "Edge Score", allocates capital, executes | LLM (ChatGPT) generates/critiques strategies over historical data; equities/ETF/crypto via Alpaca paper | **Neither** — dashboard connects to Alpaca paper trading, no P&L/backtest numbers shown on the page | [github.com/SUMANSHAKTI/alpaca](https://github.com/SUMANSHAKTI/alpaca) |
| 2 (128 votes) | TradePilot — TradePilot AI | Multi-agent (market/strategy/risk/execution agents) options+equity trader | LLM (GPT-4V) reasoning → BUY/SELL/HOLD; hard risk caps (5%/trade, 50% exposure) | **None** — no backtest, no P&L, no live numbers | [github.com/divine308/Tradepilot](https://github.com/divine308/Tradepilot/tree/main) |
| 3 (36 votes) | QASIX | Options agent (covered calls, cash-secured puts) with "AI proposes, deterministic risk layer disposes" | Google Gemini for the proposal, independent verification/risk gate before execution | Live Streamlit dashboard shows account state/positions/decision history, but **no numbers quoted** | [github.com/isianioui/Alpaca-AI-Trading-Agent](https://github.com/isianioui/Alpaca-AI-Trading-Agent) |
| 4 (27 votes) | Quantum Coders — AlphaPilot AI | SPY options paper trader | **Classical technical signals only** (SMA20/50, RSI, MACD, volume) — no LLM in the decision path | **None shown** | [github.com/ibrahimjatt1313-prog/AlphaPilot](https://github.com/ibrahimjatt1313-prog/AlphaPilot) |
| 5 (24 votes) | Agent 00Trade — SentryTheta AI | Options agent explicitly framed around *preventing* LLM hallucination from destroying capital | News-RSS sentiment (LLM) for direction + math for options structuring; hard stop-loss/take-profit/drawdown circuit breakers | **None shown** | [github.com/abdullasibghat/SentryTheta-AI](https://github.com/abdullasibghat/SentryTheta-AI) |
| 7 (12 votes) | trdrbot | "Self-improving" options agent with a memory/feedback loop | Claude/LangChain forms theses from market+news, Kelly-criterion sizing from own track record, feedback loop tunes prompts/thesis-evaluation over time | **None shown** — described only as a theoretical framework | [github.com/emson/trdrbot_hackathon](https://github.com/emson/trdrbot_hackathon) |
| 10 (10 votes) | ApexArbitrage — "AEGIS v3.1" | Wheel-strategy (cash-secured put / covered call) SPY options desk | 6-LLM ensemble vote + Black-Scholes Greeks + IV-rank screening + news-RSS regime classifier | Claims it computes "Sharpe, max drawdown, profit factor, win rate" but **no actual numbers shown** on the page | [github.com/MZunurainTahir/aegis](https://github.com/MZunurainTahir/aegis) |

**Note on the name collision:** rank-10's team called their entry "AEGIS
v3.1" — this is an unrelated team/repo, not Murat's `aegis-alpha-terminal` or
`aegis-finance`. Flagging so this isn't mistaken for self-reference later.

**Not one of the top submissions inspected shows a real number** — no paper
P&L over the hackathon window, no backtest return, no Sharpe/drawdown value
actually printed anywhere on the pages fetched. Every "performance" claim is a
description of what the dashboard *can* show, not a result it *does* show. So
by the letter of the task's honesty rule: **no submission found qualifies as
"ran a genuinely live paper account and reported real numbers."** All of them
built the execution scaffolding (Alpaca paper connectivity, agents, risk
caps) but stopped short of publishing an outcome.

## What the judges appeared to reward — no direct evidence available

Because judging is not complete, there is no judged-result evidence to cite.
The only observable signal is the **community vote count**, which correlates
with polish/marketing (both #1 and #2 have live-hosted demos, README-grade
project pages, and 4-person teams) more than with any visible trading result
— consistent with Murat's prior note that a prior Alpaca/lablab judged winner
was picked for **honesty about failure** on a real backtest, not sophistication
or marketing. Treat any inference about judge preference here as **unverified
until an official winners page appears**; do not report vote rank as a judged
result to anyone.

## 5 ideas worth stealing (from what's visible in these repos' descriptions)

1. **QASIX's "AI proposes, deterministic system disposes" framing** — the LLM
   only produces a candidate; a separate, non-LLM gate has final say before
   an order fires. Aegis's contract/seal system (`alpha/contract.py`,
   Mandate checks) already does this structurally, but QASIX's page-level
   framing is a clean one-sentence explanation worth reusing when describing
   Aegis's own no-LLM-authority-over-capital rule externally.
2. **SentryTheta's explicit "the danger is LLM hallucination destroying
   capital" framing, paired with mechanical stop-loss/take-profit/drawdown
   circuit breakers re-checked every 60 seconds.** Aegis's fleet already has
   typed emergency exits and a curfew; the useful borrow is the *cadence* —
   a tight, fixed-interval re-check loop as a named safety primitive, not
   just an event-triggered one.
3. **trdrbot's Kelly-sizing off the agent's own realized track record**
   (not off a backtest) — position size shrinks/grows with the agent's own
   demonstrated hit rate. Aegis's books currently size by fixed
   notional/profile width; feeding realized book-level skill (once enough
   book-days exist, per L1/L8 in the night lab) into sizing is a natural,
   already-partially-supported next step.
4. **AlphaPilot's simplicity** — no LLM in the decision path at all, just
   SMA/RSI/MACD plus hard paper-trading isolation. It's a useful reminder
   that "no LLM opinion" is itself a legitimate, cheap-to-evaluate arm — a
   sanity baseline the fleet could keep running for comparison, similar to
   Aegis's own signal-only PRODUCT_EXPERIMENT books versus the composite.
5. **Alpha Hunter's "adversarial AI layer" that tries to break its own
   proposed strategies (overfitting, poor generalization) before capital
   allocation** — conceptually close to Aegis's own matched-loser and
   PBO/CSCV discipline (L0 in the night lab), but applied automatically per
   proposal rather than only at the research-review stage. Worth noting as
   validation that this pattern is recognized as good practice outside Aegis
   too — not a new technique to import, since Aegis's PBO/SPA/DSR gate is
   already stricter than anything described in these pages.

## What Aegis already does better — honestly

- **Real reported evidence.** None of the six inspected submissions display
  an actual P&L number, live paper-trading result, or backtest figure on
  their public pages — every one stops at "the dashboard can show this."
  Aegis's fleet has produced actual sealed numbers (first tracker fills,
  hack4 live flip, the L1/L4/L11/L12 lab results with real DSR/SPA/PBO
  figures and a stated "16.1 years needed, 7 on hand"), including negative
  and null results reported as such. That is a materially higher evidence
  bar than anything found in this hackathon's public leaderboard.
- **Statistical discipline.** None of the six pages mention out-of-sample
  significance testing, deflation for multiple strategies tried, or a null
  bar — Alpha Hunter's "Edge Score" and validation language are the closest
  gesture toward this, with no numbers to check. Aegis's L0 lab
  infrastructure (Deflated Sharpe, Hansen SPA, CSCV/PBO) is already ahead of
  the field surveyed here.
- **Explicit multi-account risk mandates and contracts.** Aegis's six-book
  fleet with frozen strategy contracts, typed emergency exits, and a
  curfew keyed to a real mandate end-date is more architected than the
  single-agent-plus-risk-caps pattern seen in the top submissions (most of
  which cap at "5% per trade, 50% exposure" and stop there).
- **Caveat:** Aegis's fleet has not, as of this session, published a
  polished public-facing demo/dashboard the way several of these teams did
  (live Streamlit/Vercel/Railway-hosted pages). If public presentation
  quality is a judged criterion, that is a real, acknowledged gap.
