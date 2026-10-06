# Borrow from outside — 2026-10-06

**Licence: `PRODUCT_EXPERIMENT` research note.** Nothing here is a `RESEARCH_CLAIM`.
Every number about an outside project is that project's own stated figure or a
primary-source citation, never Aegis-measured. Per CLAUDE.md, this note
recommends nothing be added to the roadmap by itself — "new guards/new work
are no longer roadmap work by default; add one when an actual failure shows
it is necessary." Read, then decide.

**What this extends rather than repeats.**
`docs/research_notes/2026-09-28/outside_methods_compared_2026-09-28.md`
already fact-sheeted Numerai, QuantConnect LEAN, Qlib, RD-Agent(Q), StockBench,
TradingAgents, FinMem, AlphaAgents, NautilusTrader, alphalens/pyfolio-reloaded,
mlfinlab, and Kronos, and found: TradingAgents' flagship Sharpe 6-8 traces to
a confirmed look-ahead leak (GitHub issue #203); Qlib/RD-Agent(Q) ship no free
US data and were validated on OpenAI-tier models, not DeepSeek; mlfinlab's
free version is dead (now a paid `PortfolioLab`, £100/mo) and its techniques
are already built and stress-tested in-house (GATE-M1). This note does not
re-litigate those verdicts. It (1) runs the Alpaca hackathon question the
owner actually asked, (2) goes one level deeper into RD-Agent(Q)'s loop
MECHANICS (not just its evidence) because `hyp_lab` needs the mechanism, not
the backtest number, (3) adds OpenBB (not in the 09-28 note), (4) answers the
LEAN data-availability question precisely instead of generally, and
(5) adds FinRL, which the 09-28 note did not cover.

---

## Table: five systems

| System | Already borrowed (our module) | ONE new piece to borrow | Cost / licence | Verdict | Opus build spec (3 lines) |
|---|---|---|---|---|---|
| **Alpaca hackathon winners** (Autobelay, Killswitch, Deflow) | `backend/services/fleet_manager.py`'s `check_limits()` — the single "hard gate" (no short, no leverage, gross cap, name cap, limit-only orders) that only refuses or shrinks, never enlarges, same principle as all three winners' gate layers | **Named, enumerable, separately-logged gates** (Killswitch's 15: kill switch, sector concentration, cooldown, directional balance, risk budget, …) instead of one `check_limits()` function; and an automated **end-of-day audit model call** per account (Autobelay's "separate model end-of-day critique"), not a human-run session review | $0 — pattern only, no code to license | **ADOPT-as-pattern** | 1. Split `check_limits()` into named gate functions in a list, each returning `(name, pass/refuse/shrink, reason)`, logged per-order. 2. Add `cooldown` (no re-entry on a symbol within N sessions of an exit) and `sector_concentration` (cap `Σ notional` per GICS sector) to the list — gaps Aegis's current single gate does not check. 3. Add a scheduled `fleet_eod_audit()` DeepSeek call per account that reads the day's decisions + gate log and writes a critique row to the ledger, run automatically, not only in a human review session. |
| **Microsoft RD-Agent(Q)** | `backend/services/hyp_lab.py`'s `family_record()` + `score()` — already a Beta(a,b) posterior per hypothesis **family**, already used to weight EV (`p_positive_family`) | RD-Agent(Q)'s **multi-armed bandit scheduler feeds the posterior BACKWARD into generation**, not just forward into ranking: it decides which research DIRECTION gets the next round's budget before new hypotheses exist. `hyp_lab`'s posterior currently only re-ranks hypotheses already generated; `generation_prompt()` never sees it | $0, MIT, no Qlib/data-stack dependency needed for this piece | **ADOPT — build directly, no port** | 1. Pass `family_record(state)` into `generation_prompt()` and down-weight (or outright exclude) a family from the LLM's generation request once its Beta posterior mean falls below 0.15 (owner decision #13), instead of generating it anyway and only discounting its EV after the fact. 2. Log each generation round's per-family budget split (how many of the 8 requested hypotheses came from which family) next to the posterior that produced it, so the policy is auditable. 3. No Qlib, no RD-Agent(Q) code — the bandit-over-families IS `family_record()`; only the feedback wiring (posterior → generation prompt) is missing. |
| **OpenBB platform + MCP server** | `backend/services/finra_short_volume.py`, `official_sources.py`, `world_digest.py` already pull FINRA short-volume and CFTC-adjacent data by hand; yfinance/SEC/FRED-equivalent macro is already covered | OpenBB's genuinely new piece is **not data** (its free-no-key providers — yfinance, SEC, CFTC, TMX, ECB, OECD — mostly overlap what Aegis already hand-pulls) but the **uniform MCP tool interface**: `available_categories`/`available_tools` discovery over 70+ providers in one server, so a session can self-serve an ad-hoc non-US or niche-provider query (TMX/Canada, ECB/OECD macro, international equities — relevant to the VISION file's "Asia first, whole-market") without hand-writing a collector first | Apache-2.0, free; `pip install openbb-mcp-server` + only the needed provider extras (not the full `openbb` meta-package, to bound install footprint — not independently measured this session) | **ADOPT-as-research-tool, not as a production data dependency** | 1. Install `openbb-mcp-server` + `yfinance`/`sec`/`cftc`/`tmx`/`ecb` provider extras only, in a throwaway venv, not the full `openbb` package. 2. Point it at one concrete gap — a non-US or Asia-session ticker the yfinance pipeline handles poorly — and compare its answer against the existing collector for one week before anything production depends on it. 3. Never let it become a second, parallel data path for a provider Aegis already hand-pulls (FINRA, CFTC) — one path per fact, per house discipline. |
| **QuantConnect LEAN as a second engine** | The adapter design was already scoped in `docs/research_notes/2026-09-26/research_library_expansion_and_lean.md` §2.5 (a `PythonData` adapter replaying `top10_for_replication_<date>.json`); `scripts/pull_delisted_bars.py` already rebuilt the 2,433-name survivorship-free panel LEAN itself cannot supply for free | Confirms, precisely: LEAN's OWN free data (AlgoSeek US Equities, US Equity Security Master with delistings, ~27,500 names since 1998) is **not free** — both require a paid org tier through the LEAN CLI. A free 1991-2024 CRSP-grade replication through LEAN's native data **does not exist**. The only honest path is feeding Aegis's ALREADY-ASSEMBLED survivorship-free bars panel into LEAN as the second engine's input, never relying on LEAN to supply history itself | LEAN engine: Apache-2.0, free, local Docker/CLI. LEAN's OWN historical US equity data with delistings: paid, no free tier found | **DEFER** (engine is adoptable; its data is not, and the workaround — feed our own panel in — is already fully scoped and unbuilt, so this is a backlog item, not a new discovery) | 1. Format the already-pulled survivorship-free bars panel (not LEAN's own data) into a `PythonData` custom adapter. 2. Replay `top10_for_replication_<date>.json` through it as a SECOND, architecturally independent backtest of an already-decided strategy, never a new one. 3. Treat any disagreement with the pandas engine as a BUG TO FIND in one of the two engines, not a vote — LEAN's own statistics layer has a documented bug history (PR #3979, issue #6810) and is not ground truth either. |
| **FinRL (contextual-bandit-shaped env)** | Nothing currently — Aegis has no RL/bandit router; CLAUDE.md's own bottleneck section explicitly defers a "learned router" until several independent `PRODUCT_EXPERIMENT` selectors exist | The smallest borrowable piece is NOT the RL machinery — it's the **documented failure mode**: FinRL's own portfolio-allocation env reward is literally `r = Δ(portfolio value)` (raw P&L, no benchmark subtraction, no risk adjustment), state = `{covariance matrix, MACD, RSI, CCI, ADX}`, action = softmax weights. An unconditioned raw-P&L reward, trained on a mostly-rising sample, is maximized by tilting toward the highest-beta/momentum names — i.e. it re-derives THE BOTTLENECK's own 99.5%-momentum diagnosis as an RL failure mode rather than fixing it | Apache/MIT-family, free; irrelevant until a router is built | **DEFER** — note the warning now, revisit only once ≥2-3 independent selector books exist (per THE BOTTLENECK) | 1. When (not before) a learned router is built, define its state as `{per-book edge vector, regime flag, current portfolio weights}` exactly as FinRL does, but 2. reward it on EXCESS return over the live composite (or over equal-weight-of-books), never raw `Δportfolio value` — the one line that avoids FinRL's own documented failure. 3. Until then: nothing to build; this is a guardrail for a future ticket, not a task today. |

---

## The Alpaca hackathon section — the owner's question, answered

**Has it concluded? Who won? How?**

The Alpaca AI Trading Agents Hackathon ran **Aug 28 – Sep 4, 2026** on lablab.ai,
$6,300 total pool, judged on P&L in Alpaca's paper environment + technical
implementation + creativity + presentation. It **has concluded** and results
are posted.
[lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) ·
[.../live](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live) ·
[lablab.ai/apps/recent-winners](https://lablab.ai/apps/recent-winners)

| Place | Project / team | Architecture | Verified result | Over how many trades |
|---|---|---|---|---|
| **1st** | **Autobelay — "Long Premium, Short Leash"**, team RazorsEdge (William McCormick) [lablab.ai/submissions/z2pvao27ysyqirbqo70xjqp1](https://lablab.ai/submissions/z2pvao27ysyqirbqo70xjqp1) | Open-source models (Qwen3.8-Flash-Next, Kimi variants) PROPOSE defined-risk short-dated options-premium trades by JSON; deterministic code SIZES, STOPS, and closes every one before expiry; hard-coded whitelist/notional-cap/position-count/expiry-window/entry-cutoff/daily-loss-halt gates, never negotiable; only proprietary code talks to Alpaca's order API; a separate model writes an end-of-day critique | **$100,000 → $105,096, +5.1%**, judged account Aug 31–Sep 3, nothing held past expiry | **15 round trips** |
| **2nd** | **Should-AI Buy?**, team SquadBlessingMiracle | "Autonomous AI Trading Council" — every trade is challenged before capital deploys (debate-plus-veto pattern) | Not independently verified this session (no primary numbers surfaced in the fetched pages) | unknown |
| **3rd** | **Killswitch Capital**, Team Quantus [lablab.ai/ai-hackathons/.../team-quantus/killswitch-capital](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/team-quantus/killswitch-capital) | **Claude Opus 5** reads 82 sessions of price history + pre-filtered option contracts + live Greeks/IV + news per symbol and proposes direction/confidence/rationale; plain Python runs **15 named gates** (kill switch, market clock, position slots, sector concentration, cooldown, delta band, spread width, expiry window, directional balance, premium richness, theta burden, risk budget, buying power, …) that can only reject or SHRINK an order, never enlarge it; exits are never gated ("a rule that can block an exit can trap a loss"); reads via the Alpaca MCP server, writes via the Alpaca CLI over subprocess; unattended since Sep 1, polling every 15 min | **$102,361 vs $100,000 (+2.36%)**; realized gains $3,280 | **3 closed trades** (NVDA +59.3%, IBIT +52.2%, GLD −27.2% — a 2-of-3 record with one large loss) |
| **Finalist** | **Deflow — Autonomous Multi-Agent Options Desk**, team Deflow [lablab.ai/submissions/dtwcnktg4sb9itzhzr95uh6r](https://lablab.ai/submissions/dtwcnktg4sb9itzhzr95uh6r) | Four agents (macro/vol analyst, options structurer, adversarial risk auditor, execution agent) on a 5-minute cycle PROPOSE; 12 deterministic circuit breakers (`risk_gate.py`), zero LLM, fail-closed, microsecond checks (e.g. refuses naked calls) DECIDE/execute | **No P&L figures disclosed** in any fetched page | unknown |
| **Finalist** | **PRISM**, team ISKOLAR | Multi-agent AI + deterministic risk controls, governed through a "ShadowFund" testing mechanism | Not surfaced this session | unknown |

Autobelay's own GitHub repo (`github.com/bill-mccormick-dg/alpaca-hackathon`,
cited by the owner) returned **404 on both `gh api` and WebFetch as of
2026-10-06** — it is not currently resolvable as a public repo (renamed,
privated, or moved after judging). Test count and exact code structure could
**not** be independently verified this session; treat the architecture
description above as sourced from the lablab.ai submission page and search
snippets, not from reading the code. Absence of a reachable repo today is not
evidence the result is fabricated — it is a verification gap, flagged rather
than silently dropped.

**What they did that we failed at, in our own entry.** Per this session's own
memory (S59/S60), Aegis's `hack3` paper account went **unmanaged on a revoked
API key** and the Railway loops **drifted** during the live window. All three
placing/finalist teams share one structural property Aegis's hack3 did not
have for that account: a **hard, automated kill switch and liveness check as
gate #1**, not an afterthought — Killswitch Capital's own first-listed gate is
literally named "kill switch"; Autobelay's gates include a "daily-loss halt."
Aegis's `fleet_manager.py` DOES have equivalent machinery (`check_limits`,
turnover budgets, the worst-case-dollars discipline CLAUDE.md's protocol
item 4 requires) — the failure was not a missing gate design, it was an
**unmonitored credential and an unmonitored process** (a revoked key silently
stopping the loop, with nothing watching that the loop was still alive). None
of the three winners' writeups claim a credential-liveness check either —
this is not a piece to borrow from them; it is a gap in Aegis's OWN
operational discipline that a hackathon loss made visible, matching
`verify-prod-after-deploy`'s existing mandate (a green build is not a live
check) applied to a credential instead of a deploy.

**The one concrete piece Aegis's fleet manager genuinely lacks**, comparing
against all three: a **per-account automated end-of-day audit call**
(Autobelay) and **named, individually logged gates including cooldown and
sector concentration** (Killswitch) — see the table above. Aegis's
`check_limits()` is a single function with ~6 implicit checks (ticker
pattern, qty positive, order type, short-refusal, cash/leverage, gross cap,
name cap); it has no cooldown, no sector-concentration cap, and no automated
daily critique distinct from a human review session.

---

Sources: [lablab.ai hackathon page](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) ·
[recent winners](https://lablab.ai/apps/recent-winners) ·
[Autobelay submission](https://lablab.ai/submissions/z2pvao27ysyqirbqo70xjqp1) ·
[Killswitch Capital submission](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/team-quantus/killswitch-capital) ·
[Deflow submission](https://lablab.ai/submissions/dtwcnktg4sb9itzhzr95uh6r) ·
[RD-Agent GitHub](https://github.com/microsoft/RD-Agent) ·
[RD-Agent-Quant arXiv:2505.15155](https://arxiv.org/abs/2505.15155) ·
[OpenBB GitHub](https://github.com/OpenBB-finance/OpenBB) ·
[openbb-mcp-server PyPI](https://pypi.org/project/openbb-mcp-server/) ·
[OpenBB providers docs](https://docs.openbb.co/odp/python/extensions/providers) ·
[QuantConnect LEAN GitHub](https://github.com/QuantConnect/Lean) ·
[QuantConnect AlgoSeek US Equities](https://www.quantconnect.com/data/algoseek-us-equities) ·
[QuantConnect US Equity Security Master](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-security-master) ·
[FinRL GitHub](https://github.com/AI4Finance-Foundation/FinRL) ·
[FinRL Portfolio Allocation docs](https://finrl.readthedocs.io/en/latest/tutorial/Introduction/PortfolioAllocation.html)
